"""Non-workload tests. All event records here are synthetic, not Judge executions."""
import ast
import contextlib
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK / 'tests'))
from metric_config import PROTOCOL, PARENT_PROTOCOL, METRIC, FAILURE_PENALTY, ABS_TOLERANCE
from runtime import STRATA, Infrastructure, safe_error
from admission import CandidateInvalid
from metrics import case_values, aggregate, summarize_strata, error_feedback, reward_artifact, write_reward
import evaluate
from rescore_par2 import rescore, load_source, strict_json, PARENT_SHA
from check_par2_independent import independent

ROSTER = json.loads((TASK / 'tests/assets/evaluation.json').read_text())
SOURCE_FEEDBACK = TASK.parent / 'parent_snapshot/validation/reference.log'
IDENTITY = json.loads(SOURCE_FEEDBACK.read_text().splitlines()[1])['provenance']


def fixtures(protocol=PROTOCOL):
    identity = copy.deepcopy(IDENTITY)
    identity['run_id'] = 'synthetic_fixture_only'
    if protocol == PROTOCOL:
        identity['protocol_sha256'] = hashlib.sha256((TASK / 'tests/protocol-v3-par2.json').read_bytes()).hexdigest()
    records = []
    for i, case in enumerate(ROSTER):
        deadline = 20 if case['stratum'].startswith('12') else 40
        outcome = ('valid', 'no_plan', 'deadline', 'invalid_plan')[i % 4]
        records.append({'instance_id': case['group_id'], 'sha256': case['sha256'], 'stratum': case['stratum'],
                        'protocol_id': protocol, 'identity': copy.deepcopy(identity), 'seed': 0,
                        'deadline': deadline, 'elapsed': deadline * (i % 20) / 20,
                        'outcome': outcome, 'validity': True if outcome == 'valid' else False if outcome == 'invalid_plan' else None,
                        'plan_length': i % 10 if outcome == 'valid' else None, 'cleaned': True})
    return records, identity


def synthetic_feedback(records, identity):
    buckets = {s: [r for r in records if r['stratum'] == s] for s in STRATA}
    summary = summarize_strata(buckets)
    old = {'status': 'complete', 'reward': summary['legacy_par10_utility_score'], 'count': 400,
           'macro_coverage': summary['macro_coverage'], 'micro_coverage': summary['micro_coverage'],
           'strata': copy.deepcopy(summary['strata']), 'provenance': identity}
    for s in STRATA:
        old['strata'][s]['mean_utility'] = old['strata'][s]['legacy_par10_mean_utility']
    return [{'status': 'started', **{k: identity[k] for k in ('run_id', 'candidate_id', 'components', 'protocol_sha256')}}, old]


class MetricTests(unittest.TestCase):
    def test_cutoff_values(self):
        for ratio, expected in [(0, 1), (.05, .975), (.5, .75), (.95, .525), (1, .5)]:
            for deadline in (20, 40):
                with self.subTest(ratio=ratio, deadline=deadline):
                    cost, value, legacy = case_values('valid', ratio * deadline, deadline, True)
                    self.assertAlmostEqual(value, expected)
                    self.assertAlmostEqual(cost, ratio)
                    self.assertAlmostEqual(legacy, 1 - ratio / 10)

    def test_fast_and_late_failure_are_not_rewarded(self):
        for outcome in ('no_plan', 'invalid_plan', 'deadline'):
            for elapsed in (0, .01, 19, 20, 25):
                self.assertEqual(case_values(outcome, elapsed, 20, False if outcome == 'invalid_plan' else None), (2, 0, 0))

    def test_integrity_rejects_contradictory_timing_and_validation(self):
        for args in [('valid', 20.000001, 20, True), ('valid', 1, 20, False),
                     ('deadline', 21, 20, True), ('invalid_plan', 1, 20, None), ('no_plan', 1, 20, False),
                     ('valid', -1, 20, True), ('valid', math.inf, 20, True), ('valid', math.nan, 20, True),
                     ('valid', True, 20, True), ('valid', 1, 20.0, True)]:
            with self.subTest(args=args), self.assertRaises(Infrastructure):
                case_values(*args)

    def test_unscored_cases_and_feedback(self):
        for outcome in ('candidate_invalid', 'infrastructure_unscored', 'incomplete'):
            with self.assertRaises(Infrastructure):
                case_values(outcome, 0, 20, None)
        candidate = CandidateInvalid('fixture', '/workspace/candidate/loss.py', 'compute_loss', 'synthetic invalid')
        for error in (candidate, Infrastructure('incomplete_record', 'Missing case')):
            result = error_feedback(safe_error(error))
            self.assertIsNone(result['primary_score'])
            self.assertEqual(result['metric_id'], METRIC)
            self.assertNotIn('reward', result)
            with self.assertRaises(Infrastructure):
                reward_artifact(result)

    def test_complete_production_identity_and_invalid_inventories(self):
        records, identity = fixtures()
        result = aggregate(ROSTER, records, identity)
        self.assertEqual(result['count'], 400)
        variants = [records[:-1], records + [records[0]], [records[0], *records[:-1]]]
        for field, value in [('stratum', STRATA[-1]), ('instance_id', 'extra'), ('protocol_id', PARENT_PROTOCOL),
                             ('identity', {}), ('sha256', '0' * 64), ('cleaned', False), ('seed', 1),
                             ('seed', False), ('deadline', 40), ('plan_length', -1)]:
            bad = copy.deepcopy(records)
            bad[0][field] = value
            variants.append(bad)
        missing = copy.deepcopy(records)
        del missing[0]['elapsed']
        variants.append(missing)
        for bad in variants:
            with self.assertRaises(Infrastructure):
                aggregate(ROSTER, bad, identity)

    def test_macro_weighting_with_unequal_fixture_sizes(self):
        valid = {'outcome': 'valid', 'elapsed': 0, 'deadline': 20, 'validity': True, 'plan_length': 0}
        failure = {**valid, 'outcome': 'no_plan', 'validity': None}
        buckets = {s: [copy.deepcopy(valid)] for s in STRATA}
        buckets[STRATA[0]] = [copy.deepcopy(failure) for _ in range(9)]
        result = summarize_strata(buckets)
        self.assertEqual(result['primary_score'], 87.5)
        self.assertEqual(result['macro_coverage'], .875)
        self.assertEqual(result['micro_coverage'], 7 / 16)

    def test_bounds_and_undefined_diagnostics(self):
        for outcome, expected in [('valid', 100), ('no_plan', 0)]:
            buckets = {s: [{'outcome': outcome, 'elapsed': 0, 'deadline': 20,
                            'validity': True if outcome == 'valid' else None, 'plan_length': 0}] for s in STRATA}
            result = summarize_strata(buckets)
            self.assertEqual(result['primary_score'], expected)
            if outcome != 'valid':
                self.assertIsNone(result['successful_mean_seconds'])
                self.assertIsNone(result['successful_mean_plan_length'])
                self.assertEqual(result['strata'][STRATA[0]]['failure_penalized_mean_seconds'], 20)
        records, identity = fixtures()
        result = aggregate(ROSTER, records, identity)
        self.assertTrue(0 <= result['primary_score'] <= 100 and 0 <= result['normalized_par2_cost'] <= 2)

    def test_latency_monotonicity_and_ranking_reversal(self):
        self.assertGreater(case_values('valid', 1, 20, True)[1], case_values('valid', 2, 20, True)[1])
        slow = {'outcome': 'valid', 'elapsed': 19, 'deadline': 20, 'validity': True, 'plan_length': 1}
        fast = {**slow, 'elapsed': 0}
        fail = {**slow, 'outcome': 'no_plan', 'validity': None}
        a = summarize_strata({s: [copy.deepcopy(slow)] * 4 for s in STRATA})
        b = summarize_strata({s: [copy.deepcopy(fast)] * 3 + [copy.deepcopy(fail)] for s in STRATA})
        self.assertGreater(a['legacy_par10_utility_score'], b['legacy_par10_utility_score'])
        self.assertLess(a['primary_score'], b['primary_score'])
        self.assertGreater(a['macro_coverage'], b['macro_coverage'])

    def test_equivalence_legacy_and_frozen_coefficient(self):
        records, identity = fixtures()
        result = aggregate(ROSTER, records, identity)
        self.assertEqual(FAILURE_PENALTY, 2)
        protocol = json.loads((TASK / 'tests/protocol-v3-par2.json').read_text())
        self.assertEqual(protocol['metric']['failure_penalty'], 2)
        self.assertAlmostEqual(result['primary_score'], 100 * (1 - result['normalized_par2_cost'] / 2), delta=ABS_TOLERANCE)
        self.assertAlmostEqual(result['primary_score'], 5 * result['legacy_par10_utility_score'] - 400 * result['macro_coverage'], delta=ABS_TOLERANCE)
        with self.assertRaises(Infrastructure):
            reward_artifact({**result, 'metric_id': 'candidate-chosen'})

    def test_actual_judge_main_result_and_reward_serialization_without_workloads(self):
        records, identity = fixtures()
        result = aggregate(ROSTER, records, identity)
        result['resources'] = {}
        with tempfile.TemporaryDirectory() as temp:
            reward = Path(temp) / 'reward.json'
            captured = io.StringIO()
            with patch.object(evaluate, 'run', return_value=result), patch.object(evaluate, 'write_reward',
                    side_effect=lambda value, ignored: write_reward(value, reward)), contextlib.redirect_stdout(captured):
                self.assertEqual(evaluate.main(), 0)
            feedback = json.loads(captured.getvalue())
            self.assertEqual(feedback['metric_id'], METRIC)
            self.assertEqual(json.loads(reward.read_text()), {'reward': result['primary_score']})
            with self.assertRaises(FileExistsError):
                write_reward(result, reward)
        for exc in (Infrastructure('incomplete_record', 'synthetic missing'),
                    CandidateInvalid('fixture', '/workspace/candidate/loss.py', 'compute_loss', 'synthetic invalid')):
            captured = io.StringIO()
            with patch.object(evaluate, 'run', side_effect=exc), patch.object(evaluate, 'write_reward') as writer, contextlib.redirect_stdout(captured):
                self.assertEqual(evaluate.main(), 1)
            writer.assert_not_called()
            self.assertIsNone(json.loads(captured.getvalue())['primary_score'])

    def test_synthetic_400_record_adapter_and_independent_check_read_only(self):
        records, identity = fixtures(PARENT_PROTOCOL)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            source.mkdir()
            events, feedback = source / 'events.jsonl', source / 'feedback.jsonl'
            events.write_text(''.join(json.dumps(r) + '\n' for r in records))
            feedback.write_text(''.join(json.dumps(r) + '\n' for r in synthetic_feedback(records, identity)))
            before = events.read_bytes(), feedback.read_bytes()
            derived = rescore(events, feedback, Path(temp) / 'derived', 'synthetic_fixture')
            checked = independent(events, TASK / 'tests/assets/evaluation.json')
            for key in ('primary_score', 'normalized_par2_cost', 'legacy_par10_utility_score', 'macro_coverage'):
                self.assertAlmostEqual(derived[key], checked[key], delta=ABS_TOLERANCE)
            self.assertEqual(before, (events.read_bytes(), feedback.read_bytes()))
            self.assertEqual(len((Path(temp) / 'derived/cases.jsonl').read_text().splitlines()), 400)
            self.assertEqual(derived['original_execution_protocol_id'], PARENT_PROTOCOL)
            self.assertEqual(records[0]['protocol_id'], PARENT_PROTOCOL)
            # Legacy adapter also rejects omissions and aggregate disagreement.
            events.write_text(''.join(json.dumps(r) + '\n' for r in records[:-1]))
            with self.assertRaises(Infrastructure):
                load_source(events, feedback)
            events.write_bytes(before[0])
            bad = synthetic_feedback(records, identity)
            bad[1]['reward'] += 1
            feedback.write_text(''.join(json.dumps(r) + '\n' for r in bad))
            with self.assertRaises(Infrastructure):
                load_source(events, feedback)

    def test_strict_json(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}'):
            with self.assertRaises((Infrastructure, ValueError)):
                strict_json(text)

    def test_nonmetric_execution_and_frozen_protocol_preserved(self):
        parent = TASK.parent / 'parent_snapshot' / TASK.name
        for relative in ('tests/train.py', 'tests/worker.py', 'tests/admission.py', 'tests/rule_guard.py',
                         'tests/supervision.py', 'tests/protocol.json', 'solution/solve.sh',
                         'environment/reference.tar.gz', 'environment/flax-source.tar.gz', 'environment/work-inputs.tar.gz',
                         'tests/assets/evaluation.json', 'tests/assets/fixed-inputs.json', 'environment/Dockerfile'):
            self.assertEqual((TASK / relative).read_bytes(), (parent / relative).read_bytes(), relative)
        old = ast.parse((parent / 'tests/evaluate.py').read_text())
        new = ast.parse((TASK / 'tests/evaluate.py').read_text())
        original = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == 'case_evaluate')
        amended = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == 'case_evaluate')
        self.assertEqual(ast.dump(original), ast.dump(amended))
        for name in ('metrics.py', 'metric_config.py', 'runtime.py', 'launcher.py'):
            self.assertEqual((TASK / 'tests' / name).read_bytes(), (TASK / 'environment/tools' / name).read_bytes())
        protocol = json.loads((TASK / 'tests/protocol-v3-par2.json').read_text())
        self.assertEqual(protocol['parent_protocol_sha256'], PARENT_SHA)
        for name, sha in protocol['scoring_code_sha256'].items():
            self.assertEqual(hashlib.sha256((TASK / 'tests' / name).read_bytes()).hexdigest(), sha)
        for path in TASK.rglob('*.py'):
            ast.parse(path.read_text(), filename=str(path))


if __name__ == '__main__':
    unittest.main(verbosity=2)
