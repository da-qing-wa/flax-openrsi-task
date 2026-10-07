"""Fixed stratum-normalized PAR-2 utility; parent-owned complete records only."""
import json
import math
import statistics
from runtime import STRATA, require
from metric_config import PROTOCOL, METRIC, FAILURE_PENALTY, ABS_TOLERANCE

ORDINARY = {'valid', 'no_plan', 'invalid_plan', 'deadline'}


def case_values(outcome, elapsed, deadline, validity):
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0 and
            type(deadline) is int and deadline in (20, 40),
            'timing_record', 'Timing must be finite, nonnegative, and use a fixed deadline.')
    require(outcome in ORDINARY, 'unscored_record', 'Only ordinary completed outcomes are scoreable.')
    if outcome == 'valid':
        require(validity is True and elapsed <= deadline, 'invalid_success',
                'Original-instance validation must finish by the external deadline.')
        ratio = elapsed / deadline
        return ratio, 1 - ratio / FAILURE_PENALTY, 1 - ratio / 10
    require(validity is (False if outcome == 'invalid_plan' else None),
            'failure_validity', 'Ordinary failures must retain their authoritative validity facts.')
    return float(FAILURE_PENALTY), 0.0, 0.0


def utility(outcome, elapsed, deadline, validity):
    return case_values(outcome, elapsed, deadline, validity)[1]


def normalized_cost(outcome, elapsed, deadline, validity):
    return case_values(outcome, elapsed, deadline, validity)[0]


def legacy_par10_utility(outcome, elapsed, deadline, validity):
    return case_values(outcome, elapsed, deadline, validity)[2]


def summarize_strata(buckets):
    """Pure macro summary; production roster admission remains in aggregate()."""
    require(set(buckets) == set(STRATA) and all(buckets.values()),
            'stratum_inventory', 'Every declared stratum needs complete nonempty records.')
    summaries = {}
    for stratum in STRATA:
        rows = buckets[stratum]
        values = [case_values(r['outcome'], r['elapsed'], r['deadline'], r['validity']) for r in rows]
        valid = [r for r in rows if r['outcome'] == 'valid']
        require(all(type(r['plan_length']) is int and r['plan_length'] >= 0 for r in valid),
                'plan_length_record', 'Successful plan lengths must be nonnegative integers.')
        summaries[stratum] = {
            'count': len(rows), 'successes': len(valid), 'coverage': len(valid) / len(rows),
            'mean_utility': statistics.mean(v[1] for v in values),
            'normalized_par2_cost': statistics.mean(v[0] for v in values),
            'legacy_par10_mean_utility': statistics.mean(v[2] for v in values),
            'successful_mean_seconds': statistics.mean(r['elapsed'] for r in valid) if valid else None,
            'successful_mean_plan_length': statistics.mean(r['plan_length'] for r in valid) if valid else None,
            # Historical diagnostic deliberately retains the ONE-deadline penalty.
            'failure_penalized_mean_seconds': statistics.mean(
                r['elapsed'] if r['outcome'] == 'valid' else r['deadline'] for r in rows),
            'outcome_counts': {o: sum(r['outcome'] == o for r in rows) for o in sorted(ORDINARY)}}
    cost = statistics.mean(s['normalized_par2_cost'] for s in summaries.values())
    reward = 100 * statistics.mean(s['mean_utility'] for s in summaries.values())
    require(math.isclose(reward, 100 * (1 - cost / FAILURE_PENALTY), rel_tol=0, abs_tol=ABS_TOLERANCE),
            'metric_equivalence', 'Cost and utility aggregation must agree within absolute tolerance.')
    require(math.isfinite(reward) and 0 <= reward <= 100 and 0 <= cost <= 2,
            'reward_domain', 'Utility score and dimensionless cost must stay within their bounds.')
    count = sum(len(rows) for rows in buckets.values())
    successes = [r for rows in buckets.values() for r in rows if r['outcome'] == 'valid']
    return {'status': 'complete', 'protocol_id': PROTOCOL, 'metric_id': METRIC,
            'primary_score': reward, 'reward': reward, 'count': count, 'strata': summaries,
            'normalized_par2_cost': cost, 'normalized_par2_cost_units': 'dimensionless',
            'normalized_par2_cost_direction': 'minimize', 'primary_score_direction': 'maximize',
            'primary_score_units': 'points on 0-100 scale',
            'legacy_par10_utility_score': 100 * statistics.mean(
                s['legacy_par10_mean_utility'] for s in summaries.values()),
            'macro_coverage': statistics.mean(s['coverage'] for s in summaries.values()),
            'micro_coverage': sum(s['successes'] for s in summaries.values()) / count,
            'successful_mean_seconds': statistics.mean(r['elapsed'] for r in successes) if successes else None,
            'successful_mean_plan_length': statistics.mean(r['plan_length'] for r in successes) if successes else None,
            'outcome_counts': {o: sum(s['outcome_counts'][o] for s in summaries.values()) for o in sorted(ORDINARY)},
            'failure_penalized_timing': 'legacy diagnostic: valid elapsed; ONE fixed deadline for ordinary failures'}


def aggregate(roster, records, identity):
    require(len(roster) == len(records) == 400 and len({r['group_id'] for r in roster}) == 400,
            'record_cardinality', 'The trial requires all 400 unique expected case records.')
    buckets = {s: [] for s in STRATA}
    for expected, record in zip(roster, records):
        require(type(record) is dict and {'identity', 'protocol_id', 'seed', 'instance_id', 'sha256',
                'stratum', 'deadline', 'cleaned', 'outcome', 'elapsed', 'validity', 'plan_length'} <= record.keys(),
                'incomplete_record', 'Every authoritative case record must contain all scoring and identity facts.')
        require(record['identity'] == identity and record['protocol_id'] == PROTOCOL and
                type(record['seed']) is int and record['seed'] == 0,
                'trial_identity', 'Every record must match tuple, checkpoint, protocol digest, run, and seed.')
        require(record['instance_id'] == expected['group_id'] and record['sha256'] == expected['sha256'] and
                record['stratum'] == expected['stratum'] and record['deadline'] == (20 if expected['stratum'].startswith('12') else 40),
                'record_order_policy', 'Every case identity, order, stratum, and deadline must match the frozen roster.')
        require(record['cleaned'] is True, 'record_cleanup', 'Every case requires successful cleanup.')
        buckets[record['stratum']].append(record)
    require(all(len(b) == 50 for b in buckets.values()), 'stratum_cardinality',
            'All eight production strata require exactly 50 records.')
    return summarize_strata(buckets)


def error_feedback(error):
    """Preserve unscored classification/reason; never produce a reward scalar."""
    require(error.get('status') in {'candidate_invalid', 'infrastructure_unscored'},
            'unscored_status', 'Only existing unscored classifications belong in error feedback.')
    return {**error, 'protocol_id': PROTOCOL, 'metric_id': METRIC, 'primary_score': None}


def reward_artifact(result):
    require(result.get('status') == 'complete' and result.get('protocol_id') == PROTOCOL and
            result.get('metric_id') == METRIC, 'reward_identity', 'Only the current completed metric is authoritative.')
    score = result.get('primary_score')
    require(type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 100 and
            result.get('reward') == score, 'reward_value', 'Reward must equal the finite current primary score.')
    return {'reward': score}


def write_reward(result, destination):
    # Existing Harness transport is a 0-100 reward scalar; no 0-1 mapping.
    artifact = reward_artifact(result)
    with open(destination, 'x', encoding='utf-8') as stream:
        json.dump(artifact, stream, allow_nan=False)
