"""Fixed -S launcher. PYTHONHASHSEED is set by the shell before Python starts."""
import os
import json
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
sys.path[:] = [str(root), '/opt/flax', '/opt/flax/src', '/opt/minigrid',
               '/opt/python/lib/python310.zip', '/opt/python/lib/python3.10',
               '/opt/python/lib/python3.10/lib-dynload',
               '/opt/python/lib/python3.10/site-packages']
if os.environ.get('PYTHONHASHSEED') != '0' or not sys.flags.no_site or not sys.dont_write_bytecode:
    raise SystemExit('Fixed launcher requires PYTHONHASHSEED=0 and -S -B.')
allowed = {'evaluate', 'train', 'worker', 'preflight', 'dev', 'selfcheck'}
if len(sys.argv) < 2 or sys.argv[1] not in allowed:
    raise SystemExit('Unknown fixed entrypoint')
entry = sys.argv.pop(1)
try:
    runpy.run_path(str(root / (entry + '.py')), run_name='__main__')
except SystemExit:
    raise
except BaseException as exc:
    # Startup/import errors precede entrypoint handlers. Raw tracebacks are
    # explicitly outside this protocol's primary feedback boundary.
    from metrics import error_feedback
    print(json.dumps(error_feedback({'status': 'infrastructure_unscored', 'code': 'entrypoint_startup',
                      'condition': 'The fixed entrypoint could not initialize.',
                      'entrypoint': entry, 'exception_type': type(exc).__name__})), flush=True)
    raise SystemExit(1)
