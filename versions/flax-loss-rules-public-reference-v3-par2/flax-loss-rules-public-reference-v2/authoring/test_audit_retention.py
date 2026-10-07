"""Eight synthetic cases; no model, real planner, teacher or real VAL invocation."""
import contextlib
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK / 'tests'))
import evaluate
from audit import Audit, digest, publish_json
from metrics import summarize_strata, case_values
from metric_config import PROTOCOL, METRIC, PROTOCOL_FILE
from runtime import Infrastructure, STRATA
from admission import CandidateInvalid
from verify_audit import retained


def setup_fixture(root):
    source = root / 'fixture-task'
    assets = source / 'assets'
    assets.mkdir(parents=True)
    (assets / 'mazenamo.pddl').write_text('; SYNTHETIC DOMAIN, never parsed by real VAL\n')
    (assets / 'native-sources.json').write_text('{}\n')
    roster = []
    for i, s in enumerate(STRATA):
        problem = root / f'problem-{i}.pddl'
        problem.write_text('; SYNTHETIC CASE ' + str(i) + '\n')
        roster.append({'group_id': 'SYNTHETIC_CASE_' + str(i), 'stratum': s, 'sha256': digest(problem), 'path': problem.name})
    (assets / 'evaluation.json').write_text(json.dumps(roster) + '\n')
    protocol = json.loads((TASK / 'tests' / PROTOCOL_FILE).read_text())
    protocol['roster_sha256'] = digest(assets / 'evaluation.json')
    protocol['fixture_notice'] = 'eight synthetic cases only; not a scientific protocol execution'
    (source / PROTOCOL_FILE).write_text(json.dumps(protocol) + '\n')
    candidate = root / 'candidate'
    candidate.mkdir()
    for n in ('loss.py', 'relaxation_rules.json', 'complementary_rules.json', 'manifest.json'):
        (candidate / n).write_text('SYNTHETIC component ' + n + '\n')
    checkpoint = root / 'synthetic-checkpoint'
    checkpoint.write_text('SYNTHETIC hash input; no model loaded\n')
    worker = root / 'stub_worker.py'
    worker.write_text('''import argparse,hashlib,json,socket
from pathlib import Path
p=argparse.ArgumentParser()
for n in ('case','domain','checkpoint','candidate','fd'):p.add_argument('--'+n)
p.add_argument('--fixture-mode',default='valid')
a=p.parse_args();h=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
s=socket.socket(fileno=int(a.fd));s.sendall((json.dumps({'kind':'READY','identity':{n:h(Path(a.candidate)/n) for n in ('loss.py','relaxation_rules.json','complementary_rules.json','manifest.json')},'checkpoint_sha256':h(a.checkpoint),'original_sha256':h(a.case),'domain_sha256':h(a.domain),'case_graph_constructed':False})+'\\n').encode())
assert s.recv(3)==b'GO\\n'
print('SYNTHETIC WORKER DIAGNOSTIC ONLY',flush=True)
message={'kind':'RESULT','plan':['(synthetic-action)'],'statuses':[]}
if a.fixture_mode=='no_plan':message={'kind':'RESULT','plan':None,'exception':'PlanningFailure','statuses':[{'kind':'fd_search','exit_status':10,'negative_residual':False,'seconds':0}]}
if a.fixture_mode=='candidate_invalid':message={'kind':'ERROR','status':'candidate_invalid','errors':[{'code':'synthetic','path':'/workspace/candidate/loss.py','field':'compute_loss','condition':'Synthetic invalid fixture','hint':'fixture only'}]}
if a.fixture_mode=='infrastructure':message={'kind':'ERROR','code':'synthetic_worker_failure','condition':'Synthetic infrastructure fixture'}
s.sendall((json.dumps(message)+'\\n').encode())
s.close()
''')
    validator = root / 'stub_validator.py'
    validator.write_text('#!' + sys.executable + '\nprint("SYNTHETIC VALIDATION FIXTURE ONLY\\nPlan valid")\n')
    validator.chmod(0o755)
    return source, roster, candidate, checkpoint, worker, validator


def fixture_identity(audit, candidate, checkpoint):
    identity = {'run_id': audit.run_id, 'candidate_id': 'synthetic_fixture',
                'components': {p.name: digest(p) for p in candidate.iterdir()},
                'checkpoint_sha256': digest(checkpoint), 'protocol_sha256': digest(audit.path / 'protocol.json')}
    audit.set_identity(identity, candidate)
    return identity


def direct_case(audit, root, index, outcome='valid'):
    case = audit.roster[index]
    path = audit.begin_case(index, case, audit.identity)
    (path / 'worker.log').write_text('SYNTHETIC worker log\n')
    scratch = root / f'scratch-{index}'
    scratch.mkdir()
    deadline = 20 if case['stratum'].startswith('12') else 40
    elapsed = 2.0
    row = {'instance_id': case['group_id'], 'sha256': case['sha256'], 'stratum': case['stratum'],
        'protocol_id': PROTOCOL, 'identity': audit.identity, 'seed': 0, 'deadline': deadline,
        'elapsed': elapsed, 'outcome': outcome, 'validity': True if outcome == 'valid' else False if outcome == 'invalid_plan' else None,
        'plan_length': 1 if outcome in ('valid', 'invalid_plan') else None, 'cleaned': True,
        'startup_seconds': 0., 'cleanup_seconds': 0., 'domain_sha256': digest(audit.path / 'domain.pddl'),
        'timing': {'go_monotonic': 100., 'cutoff_monotonic': 100. + deadline, 'scored_end_monotonic': 102., 'ipc_received_monotonic': 101.},
        'validation': {'attempted': outcome in ('valid', 'invalid_plan'), 'observed_result': 'valid' if outcome == 'valid' else 'invalid' if outcome == 'invalid_plan' else None,
                       'exit_status': 0 if outcome == 'valid' else 1 if outcome == 'invalid_plan' else None},
        'worker_exit_status': 0, 'native_statuses': [], 'error': None}
    message = {'kind': 'RESULT', 'plan': ['(synthetic-action)'] if outcome in ('valid', 'invalid_plan') else None, 'statuses': []}
    if message['plan'] is not None:
        (scratch / 'plan.plan').write_text('0: (synthetic-action)\n')
        (path / 'val.log').write_text('SYNTHETIC VALIDATION ONLY\n' + ('Plan valid' if outcome == 'valid' else 'Plan invalid') + '\n')
    audit.retain_case(index, row, message, scratch)
    evaluate.shutil.rmtree(scratch)  # same exporter verification preceding task-owned cleanup
    return row


def summarize(rows):
    return summarize_strata({s: [r for r in rows if r['stratum'] == s] for s in STRATA})


def independent(rows):
    # Independent raw-record arithmetic, without any production scoring call.
    strata = {r['stratum'] for r in rows}
    means = []
    for s in strata:
        group = [r for r in rows if r['stratum'] == s]
        means.append([math.fsum((1 - r['elapsed']/(penalty*r['deadline'])) if r['outcome'] == 'valid' else 0
                               for r in group) / len(group) for penalty in (2, 10)])
    return tuple(100 * math.fsum(m[k] for m in means) / len(means) for k in (0, 1))


class RetentionTests(unittest.TestCase):
    def fixture(self, root, run_id='1' * 32):
        source, roster, candidate, checkpoint, worker, validator = setup_fixture(root)
        logs = root / 'logs'
        logs.mkdir()
        audit = Audit(logs, run_id, source, 'synthetic_fixture')
        fixture_identity(audit, candidate, checkpoint)
        return audit, source, candidate, checkpoint, worker, validator

    def test_complete_survives_cleanup_hashes_and_independent_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit, *_ = self.fixture(root)
            rows = [direct_case(audit, root, i, ('valid', 'deadline', 'no_plan', 'invalid_plan')[i % 4]) for i in range(8)]
            before = {str(p.relative_to(audit.path)): digest(p) for p in audit.path.rglob('*') if p.is_file()}
            result = summarize(rows)
            audit.finish(result, complete=True)
            records, marker = retained(audit.path)
            self.assertTrue(all(digest(audit.path / name) == sha for name, sha in before.items()))
            self.assertFalse(any(root.glob('scratch-*')))
            self.assertEqual(marker['origin'], 'synthetic_fixture')
            self.assertEqual(len(records), 8)
            self.assertEqual(summarize(records)['primary_score'], result['primary_score'])
            new, old = independent(records)
            self.assertAlmostEqual(new, result['primary_score'], delta=1e-10)
            self.assertAlmostEqual(old, result['legacy_par10_utility_score'], delta=1e-10)
            self.assertAlmostEqual(new, 5 * old - 400 * result['macro_coverage'], delta=1e-10)

    def test_missing_duplicate_and_corrupted_fail_closed(self):
        for defect in ('missing', 'duplicate', 'corruption'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                audit, *_ = self.fixture(root)
                rows = [direct_case(audit, root, i) for i in range(7 if defect == 'missing' else 8)]
                if defect == 'duplicate':
                    with self.assertRaises(Infrastructure):
                        audit.begin_case(0, audit.roster[0], audit.identity)
                    rows[-1]['instance_id'] = rows[0]['instance_id']
                    # Corrupt only this fixture's private file to challenge verification.
                    (audit.path / 'cases/0007/record.json').write_text(json.dumps(rows[-1]))
                elif defect == 'corruption':
                    (audit.path / 'cases/0000/worker.log').write_text('corrupt fixture log')
                with self.assertRaises((Infrastructure, KeyError)):
                    audit.finish(summarize(rows) if defect != 'missing' else {'count': 7}, complete=True)
                self.assertFalse((audit.path / 'COMPLETE.json').exists())

    def test_run_collision_and_failed_case_export_preserves_only_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit, source, *_ = self.fixture(root)
            original = (audit.path / 'run.json').read_bytes()
            with self.assertRaises(Infrastructure):
                Audit(root / 'logs', audit.run_id, source, 'synthetic_fixture')
            self.assertEqual(original, (audit.path / 'run.json').read_bytes())
            audit.begin_case(0, audit.roster[0], audit.identity)
            scratch = root / 'only-source'
            scratch.mkdir()
            row = {'outcome': 'valid', 'notice': 'SYNTHETIC minimal export-failure fixture'}
            real = __import__('audit').publish_json
            def failing(path, value):
                if path == audit.path / 'cases/0000/record.json':
                    raise Infrastructure('audit_export_failed', 'Injected synthetic storage failure')
                return real(path, value)
            with patch('audit.publish_json', side_effect=failing), self.assertRaises(Infrastructure):
                audit.retain_case(0, row, None, scratch)
            self.assertTrue((scratch / 'authoritative-record.json').is_file())
            self.assertTrue(audit.pending_records)
            with self.assertRaises(Infrastructure):
                audit.finish({'status': 'partial'}, complete=False)

    def test_term_partial_and_hard_kill_do_not_claim_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit, *_ = self.fixture(root)
            direct_case(audit, root, 0)
            audit.finish({'status': 'partial', 'failure': {'status': 'infrastructure_unscored', 'code': 'trial_terminated'}}, complete=False)
            self.assertTrue((audit.path / 'PARTIAL.json').exists())
            self.assertFalse((audit.path / 'COMPLETE.json').exists())
            with self.assertRaises(AssertionError):
                retained(audit.path)
            # Actual TERM reaches main's handler and partial-export/cleanup path.
            code = """import os,signal
from pathlib import Path
from unittest.mock import patch
import evaluate
from test_audit_retention import fixture_identity,direct_case
root=Path(%r)
def interrupted(scratch,audit):
    fixture_identity(audit,root/'candidate',root/'synthetic-checkpoint')
    direct_case(audit,scratch,0)
    os.kill(os.getpid(),signal.SIGTERM)
with patch.object(evaluate,'ROOT',root/'fixture-task'),patch.object(evaluate,'LOGS',root/'logs'),patch.object(evaluate,'AUDIT_ORIGIN','synthetic_fixture'),patch.object(evaluate,'require_private_mount'),patch.object(evaluate,'run',interrupted):
    raise SystemExit(evaluate.main())
""" % str(root)
            stopped = subprocess.run([sys.executable, '-B', '-c', code], env={'PATH': str(Path(sys.executable).parent)+':/usr/bin:/bin', 'PYTHONPATH': os.pathsep.join((str(TASK/'tests'), str(TASK/'authoring'))), 'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, timeout=10)
            self.assertEqual(stopped.returncode, 1, stopped.stderr)
            feedback = json.loads(stopped.stdout)
            self.assertEqual(feedback['status'], 'infrastructure_unscored')
            self.assertIsNone(feedback['primary_score'])
            partial = [p for p in (root/'logs/audit').iterdir() if p.name != '1'*32]
            self.assertEqual(len(partial), 1)
            self.assertTrue((partial[0]/'PARTIAL.json').exists())
            self.assertTrue((partial[0]/'cases/0000/record.json').exists())
            self.assertFalse((partial[0]/'COMPLETE.json').exists())
            self.assertFalse((root/'logs/reward.json').exists())
            code = "import os,signal;from pathlib import Path;from audit import Audit;a=Audit(Path(%r),'2'*32,Path(%r),'synthetic_fixture');(a.phase/'partial.log').write_text('SYNTHETIC interruption evidence');os.kill(os.getpid(),signal.SIGKILL)" % (str(root/'logs'), str(root/'fixture-task'))
            killed = subprocess.run([sys.executable, '-B', '-c', code], env={'PATH': str(Path(sys.executable).parent)+':/usr/bin:/bin', 'PYTHONPATH': str(TASK/'tests'), 'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, timeout=10)
            self.assertEqual(killed.returncode, -signal.SIGKILL)
            interrupted = root / 'logs/audit' / ('2' * 32)
            self.assertTrue((interrupted / 'phases/partial.log').exists())
            self.assertTrue((interrupted / 'evaluation.json').exists())
            self.assertFalse((interrupted / 'COMPLETE.json').exists())

    def test_real_case_parent_path_with_stub_processes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit, source, candidate, checkpoint, worker, validator = self.fixture(root)
            command = lambda entry, *args: [sys.executable, '-B', str(worker), *map(str, args)]
            real_env = evaluate.clean_env
            def env(path):
                result = real_env(path)
                result['PATH'] = str(Path(sys.executable).parent) + ':/usr/bin:/bin'
                return result
            with patch.object(evaluate, 'command', command), patch.object(evaluate, 'VAL', validator), patch.object(evaluate, 'clean_env', env):
                row = evaluate.case_evaluate(audit.roster[0], root / 'problem-0.pddl', source / 'assets/mazenamo.pddl',
                    checkpoint, candidate, audit.identity, root / 'actual-case-scratch', audit, 0)
            self.assertEqual(row['outcome'], 'valid')
            self.assertEqual(row['validation']['exit_status'], 0)
            self.assertEqual(row['worker_exit_status'], 0)
            self.assertFalse((root / 'actual-case-scratch').exists())
            self.assertIn('SYNTHETIC', (audit.path / 'cases/0000/val.log').read_text())
            self.assertTrue((audit.path / 'cases/0000/plan.plan').exists())
            self.assertFalse(evaluate.ACTIVE)

    def test_actual_case_failure_attribution_with_stub_events(self):
        for kind in ('no_plan', 'invalid_plan', 'deadline', 'candidate_invalid', 'infrastructure'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                audit, source, candidate, checkpoint, worker, validator = self.fixture(root)
                mode = kind if kind in ('no_plan', 'candidate_invalid', 'infrastructure') else 'valid'
                command = lambda entry, *args: [sys.executable, '-B', str(worker), '--fixture-mode', mode, *map(str, args)]
                if kind == 'invalid_plan':
                    validator.write_text('#!' + sys.executable + '\nimport sys\nprint("SYNTHETIC VALIDATION ONLY\\nPlan invalid")\nsys.exit(1)\n')
                real_receive = evaluate.receive
                calls = []
                def receive(*args, **kwargs):
                    calls.append(1)
                    if kind == 'deadline' and len(calls) == 2:
                        return None  # synthetic timeout event, not a 20-second workload
                    return real_receive(*args, **kwargs)
                with (patch.object(evaluate, 'command', command), patch.object(evaluate, 'VAL', validator),
                      patch.object(evaluate, 'receive', receive)):
                    arguments = (audit.roster[0], root / 'problem-0.pddl', source / 'assets/mazenamo.pddl',
                                 checkpoint, candidate, audit.identity, root / 'case-scratch', audit, 0)
                    if kind in ('candidate_invalid', 'infrastructure'):
                        with self.assertRaises(CandidateInvalid if kind == 'candidate_invalid' else Infrastructure):
                            evaluate.case_evaluate(*arguments)
                        row = json.loads((audit.path / 'cases/0000/record.json').read_text())
                        self.assertEqual(row['error']['status'], 'candidate_invalid' if kind == 'candidate_invalid' else 'infrastructure_unscored')
                        self.assertIsNone(row['outcome'])
                    else:
                        row = evaluate.case_evaluate(*arguments)
                        self.assertEqual(row['outcome'], kind)
                        self.assertEqual(case_values(row['outcome'], row['elapsed'], row['deadline'], row['validity'])[1], 0)
                self.assertTrue(row['cleaned'])
                self.assertFalse(evaluate.ACTIVE)

    def test_main_success_and_failure_feedback_stays_sanitized(self):
        for kind in ('complete', 'candidate_invalid', 'infrastructure', 'export_failure'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source, _, candidate, checkpoint, *_ = setup_fixture(root)
                logs = root / 'logs'
                logs.mkdir()
                scratches = []
                def run(scratch, audit):
                    scratches.append(scratch)
                    fixture_identity(audit, candidate, checkpoint)
                    direct_case(audit, root, 0)
                    if kind == 'candidate_invalid':
                        raise CandidateInvalid('synthetic', '/workspace/candidate/loss.py', 'compute_loss', 'Synthetic invalid fixture')
                    if kind == 'infrastructure':
                        raise Infrastructure('trial_terminated', 'Synthetic interruption fixture')
                    rows = [json.loads((audit.path / 'cases/0000/record.json').read_text())]
                    rows.extend(direct_case(audit, root, i) for i in range(1, 8))
                    result = summarize(rows)
                    result['resources'] = {}
                    if kind == 'export_failure':
                        (audit.path / 'cases/0000/worker.log').write_text('INJECTED synthetic corruption')
                    return result
                output = io.StringIO()
                with (patch.object(evaluate, 'ROOT', source), patch.object(evaluate, 'LOGS', logs),
                      patch.object(evaluate, 'AUDIT_ORIGIN', 'synthetic_fixture'), patch.object(evaluate, 'run', run),
                      patch.object(evaluate, 'require_private_mount'), contextlib.redirect_stdout(output)):
                    code = evaluate.main()
                feedback = json.loads(output.getvalue())
                for hidden in ('SYNTHETIC_CASE_', 'synthetic-action', 'worker.log', 'Traceback', 'phases/', 'cases/'):
                    self.assertNotIn(hidden, output.getvalue())
                if kind == 'complete':
                    self.assertEqual(code, 0)
                    self.assertEqual(feedback['status'], 'complete')
                    self.assertTrue((logs / 'reward.json').exists())
                    self.assertFalse(scratches[0].exists())
                    run_path = next((logs / 'audit').iterdir())
                    self.assertEqual(len(retained(run_path)[0]), 8)
                else:
                    self.assertEqual(code, 1)
                    self.assertIsNone(feedback['primary_score'])
                    self.assertFalse((logs / 'reward.json').exists())
                    self.assertEqual(feedback['status'], 'candidate_invalid' if kind == 'candidate_invalid' else 'infrastructure_unscored')
                    if kind == 'export_failure':
                        self.assertTrue(scratches[0].exists())
                        self.assertTrue((next((logs / 'audit').iterdir()) / 'failure.json').exists())
                        evaluate.shutil.rmtree(scratches[0])  # fixture-owned teardown only after assertions


if __name__ == '__main__':
    unittest.main(verbosity=2)
