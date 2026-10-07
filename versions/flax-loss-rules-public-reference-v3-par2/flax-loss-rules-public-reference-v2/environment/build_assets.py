"""Build-only extraction of packaged public data; no downloads at task runtime."""
import hashlib
from pathlib import Path
import tarfile

ROOT = Path('/opt/build-assets')


def extract(name, destination, strip_work=False):
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(ROOT / name) as archive:
        for member in archive:
            if member.isdir():
                continue
            assert member.isfile(), 'Only regular public files are expected'
            rel = Path(member.name)
            assert not rel.is_absolute() and '..' not in rel.parts
            if strip_work:
                assert rel.parts[0] == 'work'
                rel = Path(*rel.parts[1:])
            p = destination / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('xb') as stream:
                stream.write(archive.extractfile(member).read())


assert hashlib.sha256((ROOT / 'work-inputs.tar.gz').read_bytes()).hexdigest() == '3a767617eba31de7aa738f6209315fdd00018be0aa2db59090b36926594ef0c6'
extract('flax-source.tar.gz', Path('/opt/flax'))
extract('development-pddl.tar.gz', Path('/opt/flax'))
extract('work-inputs.tar.gz', Path('/opt/flax-assets'), strip_work=True)
extract('reference.tar.gz', Path('/opt/flax-assets/reference-v2'))
lock = Path('/opt/flax-assets/dependencies/dependencies.freeze.txt').read_text()
(ROOT / 'install-requirements.txt').write_text('\n'.join(line for line in lock.splitlines() if not line.startswith('-e ')) + '\n')
