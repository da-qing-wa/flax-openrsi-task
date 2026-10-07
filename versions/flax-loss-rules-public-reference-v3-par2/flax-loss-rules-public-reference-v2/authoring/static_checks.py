"""Read-only generation checks. Parses data/source; never imports task modules."""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tomllib

parser = argparse.ArgumentParser()
parser.add_argument('--harness-root', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
assert root.name == 'flax-loss-rules-public-reference-v2'
assert root.parent.name == 'output' and not root.is_symlink()
harness = args.harness_root.resolve()
assert (harness / 'src/rsi_harness/task/compiler.py').is_file()
assert os.access(harness / '.venv/bin/python', os.X_OK)
assert (harness / '.venv/pyvenv.cfg').is_file()

files = sorted(p for p in root.rglob('*') if p.is_file())
assert not any(p.is_symlink() for p in root.rglob('*'))
assert all(p.stat().st_size <= 100 * 1024 * 1024 for p in files)
tests = [p for p in files if p.is_relative_to(root / 'tests')]
assert sum(p.stat().st_size for p in tests) < 1024**3
assert len(list((root / 'tests').rglob('*'))) < 100000
assert not (root / 'OVER_BUDGET.flag').exists()
python_files = [p for p in files if p.suffix == '.py']
for path in python_files:
    ast.parse(path.read_text(), filename=str(path), feature_version=(3, 10))
shell = [root / p for p in ('tests/test.sh', 'solution/solve.sh', 'environment/validate-candidate', 'environment/flax-dev')]
for path in shell:
    assert os.access(path, os.X_OK)
    subprocess.run(['/bin/bash', '-n', str(path)], check=True)
task = tomllib.loads((root / 'task.toml').read_text())
assert task['task']['name'] == 'rsi/' + root.name
assert task['environment']['workdir'] == '/workspace'
assert task['environment']['gpus'] == task['metadata']['rsi_harness']['verifier']['gpus'] == 0
assert task['agent']['timeout_sec'] == 86400 and task['verifier']['timeout_sec'] == 45000
for section in ('environment', 'agent', 'verifier'):
    assert task[section]['network_mode'] == 'no-network'

def sha(data):
    return hashlib.sha256(data).hexdigest()

release_path = root / 'tests/provenance/source-v1.tar.gz'
assert sha(release_path.read_bytes()) == '12bd55f85f419ab748ee3837017b5a96185fc9ac3588e4b8076d84b46aff31b8'
assert sha((root / 'environment/work-inputs.tar.gz').read_bytes()) == '3a767617eba31de7aa738f6209315fdd00018be0aa2db59090b36926594ef0c6'
with tarfile.open(release_path) as release:
    for name, original in [('protocol-v1.json', 'evaluator/protocol.json'), ('measured-lineage.json', 'evaluator/measured-lineage.json')]:
        assert (root / 'tests/provenance' / name).read_bytes() == release.extractfile(original).read()
    roster_data = release.extractfile('evaluator/manifests/evaluation.json').read()
    assert roster_data == (root / 'tests/assets/evaluation.json').read_bytes()
    roster = json.loads(roster_data)
    train = json.loads(release.extractfile('work/manifests/train.json').read())
    validation = json.loads(release.extractfile('work/manifests/validation.json').read())
    development = json.loads(release.extractfile('work/manifests/development.json').read())
    unused = json.loads(release.extractfile('evaluator/manifests/unused.json').read())
    assert (len(roster), len(train), len(validation), len(development), len(unused)) == (400, 176, 19, 280, 720)
    original_reference = {n: release.extractfile(p).read() for n, p in {
        'loss.py': 'work/candidates/reference/loss.py',
        'relaxation_rules.json': 'work/upstream-identity/config/mazenamo_relaxation_rules_1.json',
        'complementary_rules.json': 'work/upstream-identity/config/mazenamo_complementary_rules.json'}.items()}

def contents(relative):
    with tarfile.open(root / relative) as archive:
        members = archive.getmembers()
        assert all(m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
        assert len({m.name for m in members}) == len(members)
        return {m.name: archive.extractfile(m).read() for m in members}

primary = contents('tests/assets/primary-pddl.tar.gz')
public = contents('environment/development-pddl.tar.gz')
assert {n: sha(b) for n, b in primary.items()} == {r['path']: r['sha256'] for r in roster}
assert {n: sha(b) for n, b in public.items()} == {r['path']: r['sha256'] for r in train + validation + development}
assert not set(primary) & set(public)
source = contents('environment/flax-source.tar.gz')
assert not any(n.startswith('pddl_files/problems/') for n in source)
assert sha(source['planning/my_planner.py']) == '49ae77fff2190dadd1568354d3828afde98591ed4186d3f77439ba30335e03c5'
assert source['pddl_files/domains/mazenamo.pddl'] == (root / 'tests/assets/mazenamo.pddl').read_bytes()
reference = contents('environment/reference.tar.gz')
assert {n: reference[n] for n in original_reference} == original_reference
manifest = json.loads(reference['manifest.json'])
assert len(manifest) == 9 and manifest['abi_version'] == 'flax-loss-rules-v2'
assert re.fullmatch(r'[A-Za-z0-9_-]+', manifest['candidate_id'])
for name, data in original_reference.items():
    stem = name.rsplit('.', 1)[0]
    assert manifest[stem + '_path'] == name and manifest[stem + '_sha256'] == sha(data)
pristine = json.loads((root / 'tests/assets/pristine-workspace.json').read_text())
assert pristine == {'candidate/' + n: sha(b) for n, b in reference.items()}
protocol = json.loads((root / 'tests/protocol-v3-par2.json').read_text())
assert protocol['roster_sha256'] == sha(roster_data)
assert protocol['protocol_id'] == 'flax-loss-rules-public-reference-v3-par2'
assert protocol['parent_protocol_id'] == root.name
assert protocol['metric']['failure_penalty'] == 2
assert protocol['candidate_failure_scalar'] is None
assert protocol['training']['callback_calls'] == 3373
assert all(sum(r['stratum'] == s for r in roster) == 50 for s in protocol['strata'])

for name in ('admission.py', 'launcher.py', 'runtime.py', 'scorer.py', 'train.py', 'worker.py', 'rule_guard.py', 'supervision.py', 'metrics.py', 'metric_config.py'):
    assert (root / 'tests' / name).read_bytes() == (root / 'environment/tools' / name).read_bytes(), name
for name in ('fixed-inputs.json', 'native-sources.json', 'pristine-workspace.json'):
    assert (root / 'tests/assets' / name).read_bytes() == (root / 'environment/tools/assets' / name).read_bytes(), name

# Inspect exception producers and consumers without importing/executing them.
trainer = ast.parse((root / 'tests/train.py').read_text())
diagnostic_codes = {'loss_import_runtime', 'loss_callback_runtime', 'loss_derivative', 'loss_execution'}
diagnostic_calls = [node for node in ast.walk(trainer)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'fail'
                    and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in diagnostic_codes
                    and any(isinstance(k.value, ast.Call) and isinstance(k.value.func, ast.Name)
                            and k.value.func.id == 'exception_details' for k in node.keywords)]
assert {node.args[0].value for node in diagnostic_calls} == diagnostic_codes
formatter = next(node for node in trainer.body if isinstance(node, ast.FunctionDef) and node.name == 'exception_details')
formatter_text = ast.unparse(formatter)
for field in ('exception_type', 'message', 'source', 'line', 'statement', 'operation', 'identifier', 'exception_frame'):
    assert repr(field) in formatter_text, field
assert 'exc.name' in formatter_text and 'tb.tb_lineno' in formatter_text and 'text(exc)' in formatter_text
assert not any(isinstance(node, ast.Attribute) and node.attr in {'f_locals', 'format_exc', 'format_exception'}
               for node in ast.walk(formatter))
for call in diagnostic_calls:
    if call.args[0].value in ('loss_callback_runtime', 'loss_derivative'):
        assert any(k.arg == 'input_shapes' for k in call.keywords)
assert 'raise CandidateInvalid(**e)' in (root / 'tests/evaluate.py').read_text()
assert "'errors': [exc.error]" in (root / 'tests/runtime.py').read_text()
dev = (root / 'environment/tools/dev.py').read_text()
assert "log.write((json.dumps(message, allow_nan=False) + '\\n').encode())" in dev
assert 'print(json.dumps(message), flush=True)' in dev
for path in (root / 'environment').rglob('*'):
    if path.is_file() and path.suffix in ('.py', '.sh', '.md'):
        assert '/tests/' not in path.read_text(), path

docker = (root / 'environment/Dockerfile').read_text()
assert 'FROM ubuntu:22.04' in docker and 'VOLUME ' not in docker
assert docker.rfind('close_workspace.py') > docker.rfind('pip install')
for pin in ('83dfcd7d7f6d9478373b3255047f39d371ff0b63', '3c7a1f330bdab0ba28a4762bb45c3f06c27fb6d4', '8ea099e114b7d6465afabc76957e3d689663534c'):
    assert pin in docker
for path in (root / 'README.md', root / 'instruction.md'):
    for relative in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if '://' not in relative and not relative.startswith('#'):
            assert (path.parent / relative.split('#')[0]).is_file(), relative

print(json.dumps({'status': 'PASS', 'preflight': 'read-only Harness/compiler prerequisites present',
                  'compiler_source_sha256': sha((harness / 'src/rsi_harness/task/compiler.py').read_bytes()),
                  'python_syntax_files': len(python_files), 'shell_syntax_files': len(shell),
                  'primary_cases': len(roster), 'public_pddl': len(public),
                  'tests_files': len(tests), 'tests_bytes': sum(p.stat().st_size for p in tests),
                  'package_files': len(files), 'protocol_sha256': sha((root / 'tests/protocol-v3-par2.json').read_bytes()),
                  'execution': 'No task, repository, Environment, Solution, evaluator, baseline, or Agent execution.'}, sort_keys=True))
