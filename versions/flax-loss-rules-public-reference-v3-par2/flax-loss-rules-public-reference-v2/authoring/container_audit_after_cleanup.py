"""Read-only operator probe after the first synthetic container has been removed."""
import json
from pathlib import Path
import sys

sys.path[:0] = ['/tests', '/fixture']
from audit import digest
from test_audit_retention import summarize, independent
from verify_audit import retained

logs = Path('/logs/verifier')
previous = json.loads((logs / 'fixture-verification.json').read_text())
assert previous['origin'] == 'synthetic_fixture'
path = Path(previous['audit_directory'])
records, marker = retained(path)
assert all(digest(Path(name)) == sha for name, sha in previous['before_cleanup_case_sha256'].items())
assert digest(path / 'COMPLETE.json') == previous['complete_marker_sha256']
current = summarize(records)
new, old = independent(records)
assert abs(new - current['primary_score']) <= 1e-10
assert abs(old - current['legacy_par10_utility_score']) <= 1e-10
assert all(row['cleaned'] is True and row['worker_exit_status'] == row['validation']['exit_status'] == 0 for row in records)
print(json.dumps({'status': 'PASS', 'origin': 'synthetic_fixture', 'records': len(records),
    'scope': 'host bind still contains verified payload after temporary scratch and first container removal',
    'all_payload_hashes_match_before_cleanup': True, 'independent_primary_score': new,
    'independent_legacy_score': old, 'audit_directory': previous['audit_directory'],
    'inventory_sha256': marker['inventory_sha256'], 'real_reference_or_VAL_execution': 'NOT RUN'}))
