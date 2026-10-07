"""Small container fixture using actual Judge main/case/export/cleanup, with stub science."""
import contextlib
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, '/tests')
sys.path.insert(0, '/fixture')
import evaluate
from audit import Audit, digest
from test_audit_retention import setup_fixture, fixture_identity, summarize, independent
from verify_audit import retained

root = Path('/tmp/retention-synthetic-fixture')
root.mkdir()
source, roster, candidate, checkpoint, worker, validator = setup_fixture(root)
before = {}
scratch_paths = []
audit_paths = []
real_retain = Audit.retain_case


def capture_after_export(self, index, row, message, scratch):
    real_retain(self, index, row, message, scratch)
    for p in (self.path / 'cases' / f'{index:04d}').iterdir():
        before[str(p)] = digest(p)


def run_fixture(scratch, audit):
    scratch_paths.append(scratch)
    audit_paths.append(audit.path)
    fixture_identity(audit, candidate, checkpoint)
    rows = []
    for i, case in enumerate(roster):
        rows.append(evaluate.case_evaluate(case, root / case['path'], source / 'assets/mazenamo.pddl',
            checkpoint, candidate, audit.identity, scratch / f'case-{i:04d}', audit, i))
    result = summarize(rows)
    result['resources'] = {}
    return result


command = lambda entry, *args: [sys.executable, '-B', str(worker), *map(str, args)]
captured = io.StringIO()
with (patch.object(evaluate, 'ROOT', source), patch.object(evaluate, 'AUDIT_ORIGIN', 'synthetic_fixture'),
      patch.object(evaluate, 'run', run_fixture), patch.object(evaluate, 'command', command),
      patch.object(evaluate, 'VAL', validator), patch.object(Audit, 'retain_case', capture_after_export),
      contextlib.redirect_stdout(captured)):
    code = evaluate.main()
assert code == 0, captured.getvalue()
assert not any(p.exists() for p in scratch_paths)
records, marker = retained(audit_paths[0])
assert len(records) == 8 and marker['origin'] == 'synthetic_fixture'
assert all(digest(Path(path)) == sha for path, sha in before.items())
new, old = independent(records)
computed = summarize(records)
assert abs(new - computed['primary_score']) <= 1e-10
assert abs(old - computed['legacy_par10_utility_score']) <= 1e-10
for forbidden in ('SYNTHETIC_CASE_', 'synthetic-action', 'Traceback', 'worker.log', 'cases/', 'phases/'):
    assert forbidden not in captured.getvalue(), forbidden
assert not evaluate.ACTIVE
(Path('/logs/verifier') / 'synthetic-feedback.log').write_text(captured.getvalue())
report = {'status': 'PASS', 'origin': 'synthetic_fixture', 'notice': 'No real training/planning/VAL or historical reference records',
          'records': 8, 'audit_directory': str(audit_paths[0]), 'temporary_runtime_removed': True,
          'all_before_cleanup_hashes_match': True, 'before_cleanup_case_sha256': before,
          'independent_primary_score': new, 'independent_legacy_score': old,
          'complete_marker_sha256': digest(audit_paths[0] / 'COMPLETE.json'),
          'research_feedback_boundary': 'no individual identities, plans, logs or raw traceback',
          'supported_mount_used': '/logs/verifier', 'process_cleanup': 'ACTIVE empty'}
(Path('/logs/verifier') / 'fixture-verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k not in ('before_cleanup_case_sha256', 'audit_directory')}))
