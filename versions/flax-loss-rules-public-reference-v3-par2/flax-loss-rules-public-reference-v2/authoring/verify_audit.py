"""Operator-only retained-evidence verification. Not a Work tool or feedback."""
import argparse
import hashlib
import json
from pathlib import Path


def retained(path):
    path = Path(path)
    complete = path / 'COMPLETE.json'
    assert complete.is_file() and not (path / 'failure.json').exists(), 'No completed trial evidence claim'
    marker = json.loads(complete.read_text())
    inventory_file = path / 'inventory.json'
    assert hashlib.sha256(inventory_file.read_bytes()).hexdigest() == marker['inventory_sha256']
    inventory = json.loads(inventory_file.read_text())
    for name, sha in inventory.items():
        relative = Path(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        file = path / relative
        assert file.is_file() and not any(p.is_symlink() for p in (file, *file.parents))
        assert hashlib.sha256(file.read_bytes()).hexdigest() == sha, name
    actual = {str(p.relative_to(path)) for p in path.rglob('*') if p.is_file()}
    assert actual == set(inventory) | {'inventory.json', 'COMPLETE.json'}
    roster = json.loads((path / 'evaluation.json').read_text())
    records = [json.loads((path / 'cases' / f'{i:04d}' / 'record.json').read_text()) for i in range(len(roster))]
    assert marker['completeness'] == 'complete' and marker['expected_records'] == marker['retained_terminal_records'] == len(records)
    assert len({r['instance_id'] for r in records}) == len(roster)
    assert all(row['instance_id'] == case['group_id'] and row['sha256'] == case['sha256'] and row['stratum'] == case['stratum']
               for row, case in zip(records, roster))
    return records, marker


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit_directory', type=Path)
    args = parser.parse_args()
    records, marker = retained(args.audit_directory)
    print(json.dumps({'status': 'PASS', 'records': len(records), 'origin': marker['origin'],
                      'scope': 'private payload completeness/hashes, not a new execution or validator approval'}))
