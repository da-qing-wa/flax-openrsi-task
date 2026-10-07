"""Read-only FD checkout/export comparison; no checkout or project execution."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
from urllib.request import Request, urlopen


root = Path(__file__).resolve().parents[1]
revision = '83dfcd7d7f6d9478373b3255047f39d371ff0b63'
repository = 'ronuchit/downward'
prefix = '/opt/flax/planning/FD/'


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': 'Flax-read-only-source-check'}), timeout=60) as response:
        return response.read()


docker = (root / 'environment/Dockerfile').read_text()
steps = [
    f'git clone https://github.com/{repository}.git /opt/build-assets/downward',
    f'cd /opt/build-assets/downward && git checkout {revision}',
    f'test "$(git rev-parse HEAD)" = {revision}',
    'git archive --format=tar --output=/opt/build-assets/downward.tar HEAD',
    'mkdir -p /opt/flax/planning/FD',
    'tar -xf /opt/build-assets/downward.tar -C /opt/flax/planning/FD',
    'cd /opt/flax/planning/FD && python3.10 build.py release -j4',
    'rm -rf /opt/build-assets/downward /opt/build-assets/downward.tar',
]
positions = [docker.index(step) for step in steps]
assert positions == sorted(positions), 'Pinned export must precede the unchanged native build'
assert 'git clone https://github.com/ronuchit/downward.git /opt/flax/planning/FD' not in docker
assert '--worktree-attributes' not in docker

native_bytes = (root / 'tests/assets/native-sources.json').read_bytes()
assert native_bytes == (root / 'environment/tools/assets/native-sources.json').read_bytes()
native = json.loads(native_bytes)
fixed = json.loads((root / 'tests/assets/fixed-inputs.json').read_text())
expected = {p[len(prefix):]: h for p, h in (fixed | native).items() if p.startswith(prefix)}
runtime = (root / 'tests/runtime.py').read_bytes()
assert runtime == (root / 'environment/tools/runtime.py').read_bytes()
for gate in (b'fixed_source_symlink', b'unexpected_source_file', b'native_source_integrity'):
    assert gate in runtime, 'Keep source integrity checks in both runtime copies'

tree = json.loads(fetch(f'https://api.github.com/repos/{repository}/git/trees/{revision}?recursive=1'))
assert not tree['truncated']
blobs = {r['path']: r for r in tree['tree'] if r['type'] == 'blob'}
assert not any(r['type'] == 'commit' for r in tree['tree']), 'Unexpected submodule'
attributes = fetch(f'https://raw.githubusercontent.com/{repository}/{revision}/.gitattributes')
assert hashlib.sha1(b'blob ' + str(len(attributes)).encode() + b'\0' + attributes).hexdigest() == blobs['.gitattributes']['sha']
excluded = []
for line in attributes.decode().splitlines():
    path, attribute = line.split()
    assert attribute == 'export-ignore' and path.startswith('/')
    assert not any(c in path for c in '*?[]'), 'Review any changed export policy explicitly'
    excluded.append(path[1:])
retained = {p: row for p, row in blobs.items()
            if not any(p == x or p.startswith(x + '/') for x in excluded)}
assert set(retained) == set(expected), 'Export policy must retain exactly the represented FD paths'
assert all(row['mode'] in ('100644', '100755') for row in retained.values())

# GitHub's immutable source export is parsed as bytes, never extracted or run.
# Compare it to both the full checkout tree and every authoritative SHA-256.
archive_bytes = fetch(f'https://codeload.github.com/{repository}/tar.gz/{revision}')
actual = {}
with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
    for member in archive:
        if member.isdir():
            continue
        path = PurePosixPath(member.name)
        assert not path.is_absolute() and '..' not in path.parts
        assert path.parts[0] == 'downward-' + revision
        relative = str(PurePosixPath(*path.parts[1:]))
        assert member.isfile() and relative not in actual, 'Export must contain unique regular files'
        data = archive.extractfile(member).read()
        actual[relative] = hashlib.sha256(data).hexdigest()
        assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == retained[relative]['sha']
        assert bool(member.mode & 0o111) == (retained[relative]['mode'] == '100755')
assert actual == expected, 'Final FD source bytes must match the unchanged authority'

print(json.dumps({'status': 'PASS', 'revision': revision, 'checkout_blobs': len(blobs),
                  'exported_regular_files': len(actual), 'excluded_blobs': len(blobs) - len(retained),
                  'excluded_symlinks': sum(r['mode'] == '120000' for p, r in blobs.items() if p not in retained),
                  'public_and_judge_authority': 'identical',
                  'execution': 'None; native build products and untouched-container preflight remain pending.'}, sort_keys=True))
