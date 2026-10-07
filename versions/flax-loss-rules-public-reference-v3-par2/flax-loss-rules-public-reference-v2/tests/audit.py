"""Private local-Docker Judge evidence; never printed or mounted into Work."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import uuid

from metric_config import PROTOCOL, METRIC, PROTOCOL_FILE
from metrics import case_values, summarize_strata
from runtime import Infrastructure, STRATA


def demand(ok, code='audit_integrity'):
    if not ok:
        raise Infrastructure(code, 'Private audit export is incomplete or inconsistent; no reward is valid.')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(path, data):
    """Exclusive atomic publication; a failed write leaves its temp for recovery."""
    demand(not path.exists() and not path.is_symlink(), 'audit_collision')
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, path)  # atomic and fails if an earlier artifact exists
        temp.unlink()
        sync_directory(path.parent)
    except OSError as exc:
        raise Infrastructure('audit_export_failed', 'Private audit storage failed; no reward is valid.') from exc


def publish_json(path, value):
    publish(path, (json.dumps(value, indent=2, allow_nan=False) + '\n').encode())


def require_private_mount(logs):
    demand(os.path.ismount(logs) and not logs.is_symlink(), 'audit_mount_missing')


class Audit:
    def __init__(self, logs, run_id, task_root, origin='scientific_execution'):
        demand(re.fullmatch(r'[a-f0-9]{32}', run_id) is not None, 'audit_run_id')
        logs = Path(logs).absolute()
        demand(not any(p.is_symlink() for p in (logs, *logs.parents)), 'audit_path')
        self.root = logs / 'audit'
        self.root.mkdir(mode=0o700, exist_ok=True)
        demand(not self.root.is_symlink(), 'audit_path')
        self.path = self.root / run_id
        try:
            self.path.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise Infrastructure('audit_collision', 'Private audit run identity already exists; nothing was overwritten.') from exc
        sync_directory(self.root)
        self.run_id, self.origin = run_id, origin
        self.phase = self.path / 'phases'
        self.phase.mkdir(mode=0o700)
        (self.path / 'cases').mkdir(mode=0o700)
        self.case_hashes = {}
        self.pending_records = {}
        self.identity = None
        for name, source in [('protocol.json', task_root / PROTOCOL_FILE),
                             ('evaluation.json', task_root / 'assets/evaluation.json'),
                             ('domain.pddl', task_root / 'assets/mazenamo.pddl'),
                             ('native-sources.json', task_root / 'assets/native-sources.json')]:
            demand(source.is_file() and not source.is_symlink(), 'audit_fixed_input')
            publish(self.path / name, source.read_bytes())
        self.roster = json.loads((self.path / 'evaluation.json').read_text())
        self.protocol = json.loads((self.path / 'protocol.json').read_text())
        demand(len({r['group_id'] for r in self.roster}) == len(self.roster))
        demand(self.protocol['protocol_id'] == PROTOCOL and self.protocol['metric']['metric_id'] == METRIC)
        demand(self.protocol['roster_sha256'] == digest(self.path / 'evaluation.json'))
        publish_json(self.path / 'run.json', {'run_id': run_id, 'origin': origin,
            'protocol_id': PROTOCOL, 'metric_id': METRIC, 'source_commit': self.protocol['source_commit'],
            'domain_sha256': digest(self.path / 'domain.pddl'), 'protocol_sha256': digest(self.path / 'protocol.json'),
            'assigned_cases': len(self.roster), 'state': 'open; no completeness claim'})
        publish_json(self.path / 'task-code.json', {p.name: digest(p) for p in task_root.glob('*.py')})
        self.header_hashes = {p.name: digest(p) for p in self.path.iterdir() if p.is_file()}

    def capture(self, name, data):
        demand('/' not in name and name not in self.header_hashes)
        publish(self.path / name, data)
        self.header_hashes[name] = digest(self.path / name)

    def set_identity(self, identity, candidate):
        demand(self.identity is None and identity['run_id'] == self.run_id and
               identity['protocol_sha256'] == digest(self.path / 'protocol.json'))
        self.identity = identity.copy()
        self.capture('identity.json', (json.dumps(identity, indent=2) + '\n').encode())
        if 'candidate.json' not in self.header_hashes:
            self.snapshot_tuple(identity['candidate_id'], identity['components'], candidate)
        admitted = json.loads((self.path / 'candidate.json').read_text())
        demand(admitted['candidate_id'] == identity['candidate_id'] and admitted['components'] == identity['components'])
        demand(all(digest(self.path / ('candidate-' + name)) == value for name, value in identity['components'].items()))

    def snapshot_tuple(self, candidate_id, components, candidate):
        demand(set(components) == {'loss.py', 'relaxation_rules.json', 'complementary_rules.json', 'manifest.json'})
        self.capture('candidate.json', (json.dumps({'candidate_id': candidate_id, 'components': components}, indent=2) + '\n').encode())
        for name, expected in components.items():
            demand(name in {'loss.py', 'relaxation_rules.json', 'complementary_rules.json', 'manifest.json'})
            demand(digest(candidate / name) == expected)
            self.capture('candidate-' + name, (candidate / name).read_bytes())

    def begin_case(self, index, case, identity):
        demand(type(index) is int and 0 <= index < len(self.roster) and self.roster[index] == case and identity == self.identity)
        destination = self.path / 'cases' / f'{index:04d}'
        try:
            destination.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise Infrastructure('audit_collision', 'A case audit already exists; nothing was overwritten.') from exc
        publish_json(destination / 'started.json', {'index': index, 'assignment': case, 'identity': identity,
            'origin': self.origin, 'domain_sha256': digest(self.path / 'domain.pddl')})
        return destination

    def retain_case(self, index, row, message, scratch):
        destination = self.path / 'cases' / f'{index:04d}'
        # Private fallback is deliberately not cleaned if export cannot verify.
        publish_json(scratch / 'authoritative-record.json', row)
        self.pending_records[index] = scratch / 'authoritative-record.json'
        if message is not None:
            publish_json(destination / 'worker-message.json', message)
        if (scratch / 'plan.plan').exists():
            publish(destination / 'plan.plan', (scratch / 'plan.plan').read_bytes())
        publish_json(destination / 'record.json', row)
        files = {}
        for path in destination.iterdir():
            demand(path.is_file() and not path.is_symlink())
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
            files[path.name] = digest(path)
        publish_json(destination / 'files.json', files)
        self.case_hashes[index] = {**files, 'files.json': digest(destination / 'files.json')}
        demand(all(digest(destination / name) == value for name, value in self.case_hashes[index].items()))
        demand((destination / 'record.json').read_bytes() == self.pending_records[index].read_bytes())
        sync_directory(destination)
        del self.pending_records[index]

    def verify_complete(self, result):
        demand(set(self.case_hashes) == set(range(len(self.roster))), 'audit_incomplete')
        records = []
        for index, case in enumerate(self.roster):
            destination = self.path / 'cases' / f'{index:04d}'
            row = json.loads((destination / 'record.json').read_text())
            demand(row['instance_id'] == case['group_id'] and row['sha256'] == case['sha256'] and
                   row['stratum'] == case['stratum'] and row['identity'] == self.identity and
                   row['protocol_id'] == PROTOCOL and row['seed'] == 0 and row['cleaned'] is True)
            deadline = 20 if case['stratum'].startswith('12') else 40
            demand(row['deadline'] == deadline and row['domain_sha256'] == digest(self.path / 'domain.pddl'))
            case_values(row['outcome'], row['elapsed'], row['deadline'], row['validity'])
            timing = row['timing']
            demand(all(type(timing[k]) in (int, float) and math.isfinite(timing[k])
                       for k in ('go_monotonic', 'cutoff_monotonic', 'scored_end_monotonic')))
            demand(timing['cutoff_monotonic'] == timing['go_monotonic'] + deadline and
                   timing['scored_end_monotonic'] - timing['go_monotonic'] == row['elapsed'])
            if row['outcome'] == 'valid':
                demand(timing['scored_end_monotonic'] <= timing['cutoff_monotonic'] and
                       row['validation']['observed_result'] == 'valid' and row['validation']['exit_status'] == 0)
                demand((destination / 'plan.plan').is_file() and (destination / 'val.log').is_file())
                demand('Plan valid' in (destination / 'val.log').read_text(errors='replace'))
                message = json.loads((destination / 'worker-message.json').read_text())
                demand(len(message['plan']) == row['plan_length'])
                demand((destination / 'plan.plan').read_text() ==
                       '\n'.join(f'{i}: {a}' for i, a in enumerate(message['plan'])) + '\n')
            records.append(row)
        buckets = {s: [r for r in records if r['stratum'] == s] for s in STRATA}
        recomputed = summarize_strata(buckets)
        demand(result['count'] == len(records) and result['protocol_id'] == PROTOCOL and result['metric_id'] == METRIC)
        demand(all(math.isclose(result[k], recomputed[k], rel_tol=0, abs_tol=1e-10)
                   for k in ('primary_score', 'legacy_par10_utility_score', 'normalized_par2_cost', 'macro_coverage')))
        return records

    def finish(self, outcome, complete=False):
        demand(not self.pending_records, 'audit_unexported_record')
        if complete:
            self.verify_complete(outcome)
        self.capture('outcome.json', (json.dumps(outcome, indent=2, allow_nan=False) + '\n').encode())
        for name, expected in self.header_hashes.items():
            demand(digest(self.path / name) == expected, 'audit_corruption')
        for index, files in self.case_hashes.items():
            destination = self.path / 'cases' / f'{index:04d}'
            demand(set(p.name for p in destination.iterdir()) == set(files), 'audit_extra_file')
            demand(all(digest(destination / name) == expected for name, expected in files.items()), 'audit_corruption')
        inventory = {}
        for path in self.path.rglob('*'):
            demand(not path.is_symlink(), 'audit_path')
            if path.is_file():
                demand('.tmp' not in path.name, 'audit_unfinished_write')
                with path.open('rb') as stream:
                    os.fsync(stream.fileno())
                inventory[str(path.relative_to(self.path))] = digest(path)
            elif path.is_dir():
                sync_directory(path)
        publish_json(self.path / 'inventory.json', inventory)
        demand(all(digest(self.path / name) == expected for name, expected in inventory.items()), 'audit_corruption')
        marker = {'export_status': 'verified', 'completeness': 'complete' if complete else 'partial',
                  'origin': self.origin, 'run_id': self.run_id, 'expected_records': len(self.roster),
                  'retained_terminal_records': len(self.case_hashes),
                  'inventory_sha256': digest(self.path / 'inventory.json')}
        publish_json(self.path / ('COMPLETE.json' if complete else 'PARTIAL.json'), marker)
        sync_directory(self.path)
        return marker
