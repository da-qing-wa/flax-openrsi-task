"""Second arithmetic implementation: reads raw records, never imports the scorer."""
import argparse
import hashlib
import json
import math
from pathlib import Path

TOLERANCE = 1e-10


def independent(records_path, roster_path):
    records = [json.loads(line) for line in Path(records_path).read_text().splitlines() if line.strip()]
    roster = json.loads(Path(roster_path).read_text())
    assert len(records) == len(roster) == 400
    assert len({r['instance_id'] for r in records}) == 400
    identity = records[0]['identity']
    buckets = {}
    for expected, row in zip(roster, records):
        assert row['instance_id'] == expected['group_id'] and row['sha256'] == expected['sha256']
        assert row['stratum'] == expected['stratum'] and row['identity'] == identity and row['cleaned'] is True
        assert row['protocol_id'] == 'flax-loss-rules-public-reference-v2' and type(row['seed']) is int and row['seed'] == 0
        t, deadline, status = row['elapsed'], row['deadline'], row['outcome']
        assert type(t) in (int, float) and math.isfinite(t) and t >= 0
        assert type(deadline) is int and deadline == (20 if row['stratum'].startswith('12') else 40)
        assert status in {'valid', 'deadline', 'no_plan', 'invalid_plan'}
        if status == 'valid':
            assert row['validity'] is True and t <= deadline
            assert type(row['plan_length']) is int and row['plan_length'] >= 0
            values = (1 - t / (2 * deadline), t / deadline, 1 - t / (10 * deadline), 1)
        else:
            assert row['validity'] is (False if status == 'invalid_plan' else None)
            values = (0, 2, 0, 0)
        buckets.setdefault(row['stratum'], []).append(values)
    assert set(buckets) == {f'{size}_{d}' for size in ('12x12', '15x15') for d in ('easy', 'medium', 'hard', 'expert')}
    assert all(len(rows) == 50 for rows in buckets.values())
    means = [math.fsum(math.fsum(v[k] for v in rows) / len(rows) for rows in buckets.values()) / 8 for k in range(4)]
    score, cost, old, coverage = 100 * means[0], means[1], 100 * means[2], means[3]
    assert math.isclose(score, 100 * (1 - cost / 2), rel_tol=0, abs_tol=TOLERANCE)
    assert math.isclose(score, 5 * old - 400 * coverage, rel_tol=0, abs_tol=TOLERANCE)
    return {'primary_score': score, 'normalized_par2_cost': cost, 'legacy_par10_utility_score': old,
            'macro_coverage': coverage, 'records': len(records),
            'records_sha256': hashlib.sha256(Path(records_path).read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', required=True)
    parser.add_argument('--roster', required=True)
    parser.add_argument('--aggregate', required=True)
    args = parser.parse_args()
    check = independent(args.records, args.roster)
    derived = json.loads(Path(args.aggregate).read_text())
    for key in ('primary_score', 'normalized_par2_cost', 'legacy_par10_utility_score', 'macro_coverage'):
        assert math.isclose(check[key], derived[key], rel_tol=0, abs_tol=TOLERANCE), key
    print(json.dumps({'status': 'PASS', 'check': check, 'record_origin': derived['record_origin']}))
