"""Final build operation touching WORKDIR: seed, admit, and verify pristine bytes."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, '/opt/flax-tools')
from admission import admit

workspace = Path('/workspace')
workspace.mkdir(exist_ok=True)
assert not list(workspace.iterdir()), 'WORKDIR must be empty before final seeding'
(workspace / 'candidate').mkdir()
(workspace / 'research').mkdir()
for p in Path('/opt/flax-assets/reference-v2').iterdir():
    shutil.copyfile(p, workspace / 'candidate' / p.name)
admit(workspace / 'candidate')
expected = json.loads(Path('/opt/flax-tools/assets/pristine-workspace.json').read_text())
actual = {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in workspace.rglob('*') if p.is_file()}
assert actual == expected
assert all(not p.is_symlink() for p in workspace.rglob('*'))
