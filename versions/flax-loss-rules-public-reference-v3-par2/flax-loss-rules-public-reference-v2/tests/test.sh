#!/bin/bash
set -euo pipefail
cd /tmp
exec /usr/bin/env -i PATH=/opt/python/bin:/usr/local/bin:/usr/bin:/bin HOME=/tmp LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /usr/bin/timeout --signal=TERM --kill-after=10s 41900s /opt/python/bin/python3.10 -S -B -u /tests/launcher.py evaluate
