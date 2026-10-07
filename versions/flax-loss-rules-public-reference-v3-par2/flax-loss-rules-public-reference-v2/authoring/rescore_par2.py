"""Read-only, explicit v2-record adapter. Never runs training or planning."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import tarfile
import time

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK / 'tests'))
from metric_config import PROTOCOL, PARENT_PROTOCOL, METRIC, ABS_TOLERANCE
from metrics import case_values, summarize_strata
from runtime import STRATA, require

PARENT_SHA = '6fd1cceed8c8660fabd4b886a24d1ebb2ee3e815f3f6d44126ffb73d87356a64'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate_json_key', 'Source JSON must have unique keys.')
        result[key] = value
    return result


def strict_json(text):
    def invalid(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def load_source(records_path, feedback_path):
    """Supported legacy identity is pinned here, never in normal Judge admission."""
    parent_path = TASK / 'tests/protocol.json'
    roster_path = TASK / 'tests/assets/evaluation.json'
    require(digest(parent_path) == PARENT_SHA, 'parent_protocol', 'Require the exact executed v2 protocol.')
    parent = strict_json(parent_path.read_text())
    roster = strict_json(roster_path.read_text())
    require(parent['protocol_id'] == PARENT_PROTOCOL and digest(roster_path) == parent['roster_sha256'],
            'roster_identity', 'Use the frozen original roster and protocol.')
    messages = [strict_json(line) for line in Path(feedback_path).read_text().splitlines() if line.strip()]
    require(len(messages) == 2 and messages[0]['status'] == 'started' and messages[1]['status'] == 'complete',
            'source_feedback', 'Require the original started and complete parent feedback, without omissions.')
    started, feedback = messages
    identity = feedback['provenance']
    require(identity['protocol_sha256'] == PARENT_SHA and started['protocol_sha256'] == PARENT_SHA and
            all(started[k] == identity[k] for k in ('run_id', 'candidate_id', 'components')) and
            identity['candidate_id'] == 'reference' and len(identity['checkpoint_sha256']) == 64,
            'source_trial', 'Require a complete unchanged-reference v2 trial identity.')
    with tarfile.open(TASK / 'environment/reference.tar.gz') as archive:
        reference = {Path(m.name).name: hashlib.sha256(archive.extractfile(m).read()).hexdigest()
                     for m in archive if m.isfile()}
    require(identity['components'] == reference, 'reference_tuple', 'Require all four unchanged reference components.')
    require(len(roster) == 400 and len({r['group_id'] for r in roster}) == 400 and
            all(sum(r['stratum'] == s for r in roster) == 50 for s in STRATA),
            'roster_cardinality', 'Require all frozen 400 cases and eight strata.')
    records = [strict_json(line) for line in Path(records_path).read_text().splitlines() if line.strip()]
    require(len(records) == 400, 'record_cardinality', 'Exactly 400 authoritative case records are required.')
    buckets = {s: [] for s in STRATA}
    for expected, record in zip(roster, records):
        require(type(record) is dict and {'identity', 'protocol_id', 'seed', 'instance_id', 'sha256',
                'stratum', 'deadline', 'cleaned', 'outcome', 'elapsed', 'validity', 'plan_length'} <= record.keys(),
                'incomplete_record', 'Every original record must contain complete authoritative facts.')
        require(record['identity'] == identity and record['protocol_id'] == PARENT_PROTOCOL and
                type(record['seed']) is int and record['seed'] == 0,
                'source_record_identity', 'Original records must retain their original v2 trial identity.')
        require(record['instance_id'] == expected['group_id'] and record['sha256'] == expected['sha256'] and
                record['stratum'] == expected['stratum'] and
                record['deadline'] == (20 if expected['stratum'].startswith('12') else 40) and record['cleaned'] is True,
                'source_record_policy', 'Case order, identity, deadline, stratum and cleanup must match the frozen manifest.')
        case_values(record['outcome'], record['elapsed'], record['deadline'], record['validity'])
        buckets[record['stratum']].append(record)
    require(feedback['count'] == 400 and set(feedback['strata']) == set(STRATA),
            'feedback_inventory', 'Source aggregate must contain the complete roster.')
    # Old formula is recomputed FIRST from raw timing, not stored utilities or averages.
    old = 100 * statistics.mean(statistics.mean(
        1 - r['elapsed'] / (10 * r['deadline']) if r['outcome'] == 'valid' else 0 for r in buckets[s]) for s in STRATA)
    require(type(feedback['reward']) in (int, float) and math.isfinite(feedback['reward']) and
            math.isclose(old, feedback['reward'], rel_tol=0, abs_tol=ABS_TOLERANCE),
            'legacy_reconciliation', 'Raw-record legacy score must reconcile with the original stored score.')
    result = summarize_strata(buckets)
    for s in STRATA:
        prior = feedback['strata'][s]
        current = result['strata'][s]
        require(all(prior[k] == current[k] for k in ('count', 'successes', 'outcome_counts')) and
                math.isclose(prior['mean_utility'], current['legacy_par10_mean_utility'], rel_tol=0, abs_tol=ABS_TOLERANCE),
                'stratum_reconciliation', 'Each original stratum must reconcile independently.')
    require(all(math.isclose(feedback[k], result[k], rel_tol=0, abs_tol=ABS_TOLERANCE)
                for k in ('macro_coverage', 'micro_coverage')), 'coverage_reconciliation', 'Original coverage must reconcile.')
    require(math.isclose(result['primary_score'], 5 * old - 400 * result['macro_coverage'],
                         rel_tol=0, abs_tol=ABS_TOLERANCE), 'algebra_check', 'The macro algebraic identity must hold.')
    return records, result, identity


def rescore(records_path, feedback_path, destination, source_kind):
    began = time.monotonic()
    inputs = [Path(records_path), Path(feedback_path), TASK / 'tests/assets/evaluation.json',
              TASK / 'tests/protocol.json', TASK / 'tests/protocol-v3-par2.json', TASK / 'environment/reference.tar.gz']
    hashes = {str(p.resolve()): digest(p) for p in inputs}
    records, result, identity = load_source(records_path, feedback_path)
    destination = Path(destination).absolute()
    require(not destination.exists() and not any(p.is_symlink() for p in [destination, *destination.parents]),
            'output_isolation', 'Use a new non-symlink derived-output directory.')
    require(not any(destination.is_relative_to(p.parent.resolve()) for p in inputs[:2]),
            'source_isolation', 'Derived outputs must be outside source-record and feedback directories.')
    result.update({'record_origin': source_kind, 'result_kind': 'retrospective_rescoring',
                   'original_execution_protocol_id': PARENT_PROTOCOL, 'original_execution_provenance': identity,
                   'input_sha256': hashes, 'scorer_sha256': digest(TASK / 'tests/metrics.py'),
                   'adapter_sha256': digest(__file__), 'rescored_at': datetime.now(timezone.utc).isoformat(),
                   'rescoring_wall_seconds': time.monotonic() - began,
                   'fresh_execution': 'NOT RUN', 'maintainer_approval': 'PENDING'})
    derived = []
    for record in records:
        cost, value, legacy = case_values(record['outcome'], record['elapsed'], record['deadline'], record['validity'])
        derived.append({'original_record': record, 'amendment_protocol_id': PROTOCOL, 'metric_id': METRIC,
                        'normalized_par2_cost': cost, 'utility': value, 'legacy_par10_utility': legacy})
    require(all(digest(p) == hashes[str(p.resolve())] for p in inputs), 'input_mutation', 'Read-only inputs changed during rescoring.')
    destination.mkdir(parents=True)
    with (destination / 'aggregate.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    with (destination / 'cases.jsonl').open('x') as stream:
        for record in derived:
            stream.write(json.dumps(record, allow_nan=False) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', required=True, type=Path)
    parser.add_argument('--feedback', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--source-kind', required=True, choices=('authoritative_reference_records', 'synthetic_fixture'))
    args = parser.parse_args()
    try:
        result = rescore(args.records, args.feedback, args.out, args.source_kind)
        print(json.dumps({'status': result['status'], 'primary_score': result['primary_score'],
                          'record_origin': result['record_origin'], 'result_kind': result['result_kind']}))
    except Exception as exc:
        print(json.dumps({'status': 'BLOCKED', 'primary_score': None, 'reason': str(exc)}))
        raise SystemExit(1)
