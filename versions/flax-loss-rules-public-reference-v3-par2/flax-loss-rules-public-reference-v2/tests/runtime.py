"""Fixed paths, startup policy, source/input checks, and private IPC helpers."""
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import socket
import stat
import sys
import time

ROOT = Path(__file__).resolve().parent
SOURCE = Path('/opt/flax')
ASSETS = Path('/opt/flax-assets')
PYTHON = '/opt/python/bin/python3.10'
VAL = SOURCE / 'VAL/build/linux64/Release/bin/Validate'
FD = SOURCE / 'planning/FD/fast-downward.py'
STRATA = [f'{size}_{difficulty}' for size in ('12x12', '15x15') for difficulty in ('easy', 'medium', 'hard', 'expert')]
from metric_config import PROTOCOL


class Infrastructure(Exception):
    def __init__(self, code, condition):
        self.code, self.condition = code, condition
        super().__init__(code)


def require(ok, code, condition):
    if not ok:
        raise Infrastructure(code, condition)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def configure():
    require(platform.machine() == 'x86_64' and sys.version_info[:3] == (3, 10, 12), 'runtime_version', 'Use the baked Linux amd64 CPython 3.10.12 runtime.')
    allowed = sorted(os.sched_getaffinity(0))
    require(len(allowed) >= 4, 'cpu_allocation', 'The allocation must permit at least four logical CPU IDs.')
    selected = allowed[:4]
    os.sched_setaffinity(0, selected)
    require(os.environ.get('OMP_NUM_THREADS') == os.environ.get('MKL_NUM_THREADS') == '1', 'thread_policy', 'OMP and MKL threads must both equal one.')
    return selected


def clean_env(scratch):
    return {'PATH': '/opt/python/bin:/usr/local/bin:/usr/bin:/bin', 'HOME': str(scratch),
            'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'PYTHONHASHSEED': '0',
            'PYTHONDONTWRITEBYTECODE': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
            'OPENBLAS_NUM_THREADS': '1', 'TMPDIR': str(scratch), 'MPLCONFIGDIR': str(scratch / 'mpl'),
            'XDG_CACHE_HOME': str(scratch / 'cache')}


def command(entry, *args):
    return [PYTHON, '-S', '-B', '-u', str(ROOT / 'launcher.py'), entry, *map(str, args)]


def verify_fixed():
    manifest = read_json(ROOT / 'assets/fixed-inputs.json')
    for path, expected in manifest.items():
        p = Path(path)
        require(p.is_file() and not p.is_symlink() and sha(p) == expected,
                'fixed_input_integrity', 'A fixed source or public asset differs from task-owned authority; rebuild the Environment.')
    # Source identities are portable; historical machine-specific binary hashes are not.
    native = read_json(ROOT / 'assets/native-sources.json')
    for path, expected in native.items():
        p = Path(path)
        require(p.is_file() and not p.is_symlink() and sha(p) == expected,
                'native_source_integrity', 'A locked native runtime source differs from task authority.')
    expected_source = {p for p in manifest.keys() | native.keys() if p.startswith('/opt/flax/')}
    generated_roots = (SOURCE / 'planning/FD/builds', SOURCE / 'VAL/build')
    for path in SOURCE.rglob('*'):
        if any(path.is_relative_to(generated) for generated in generated_roots):
            continue
        require(not path.is_symlink(), 'fixed_source_symlink', 'Fixed source paths may not be replaced by links.')
        if path.is_file():
            require(str(path) in expected_source, 'unexpected_source_file', 'Unexpected source files are prohibited; rebuild the Environment.')
    for executable in (VAL, FD, SOURCE / 'planning/FD/builds/release/bin/downward'):
        require(executable.is_file() and os.access(executable, os.X_OK), 'native_tool_missing', 'Build the locked FD and VAL native tools before evaluation.')
    import importlib.metadata
    lock = (ASSETS / 'dependencies/dependencies.freeze.txt').read_text().splitlines()
    for line in lock:
        if '==' in line:
            name, version = line.split('==', 1)
            require(importlib.metadata.version(name) == version, 'dependency_version', 'Installed dependencies must match the released exact lock.')


def send(sock, message):
    sock.sendall((json.dumps(message, allow_nan=False) + '\n').encode())


def receive(sock, seconds, max_bytes=16777216, process=None):
    end = time.monotonic() + max(0, seconds)
    data = bytearray()
    while time.monotonic() < end:
        remaining = max(0, end - time.monotonic())
        ready, _, _ = select.select([sock], [], [], min(remaining, .1) if process is not None else remaining)
        if not ready:
            if process is not None and process.poll() is not None:
                raise Infrastructure('worker_ipc_closed', 'The worker exited before completing its control message.')
            continue
        chunk = sock.recv(65536)
        if not chunk:
            raise Infrastructure('worker_ipc_closed', 'A fixed worker exited without its required control message.')
        data.extend(chunk)
        require(len(data) <= max_bytes, 'worker_ipc_bound', 'Worker control message exceeded the fixed IPC bound.')
        if b'\n' in data:
            line, rest = data.split(b'\n', 1)
            require(not rest, 'worker_ipc_extra', 'Unexpected extra worker control bytes.')
            return json.loads(line)
    return None


def safe_error(exc):
    from admission import CandidateInvalid
    if isinstance(exc, CandidateInvalid):
        return {'status': 'candidate_invalid', 'errors': [exc.error]}
    if isinstance(exc, Infrastructure):
        return {'status': 'infrastructure_unscored', 'code': exc.code, 'condition': exc.condition}
    return {'status': 'infrastructure_unscored', 'code': 'unexpected_runtime_failure',
            'condition': 'Fixed runtime/evaluator failure; no score was produced.', 'exception_type': type(exc).__name__}
