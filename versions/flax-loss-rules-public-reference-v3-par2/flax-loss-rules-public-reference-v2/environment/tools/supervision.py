"""POSIX session cleanup of workers, native children, and orphan descendants."""
import os
from pathlib import Path
import signal
import time
from runtime import Infrastructure

ACTIVE = set()


def members(sid):
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[3]) == sid and fields[0] != 'Z':
                found.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return found


def cleanup(sids):
    start = time.monotonic()
    def signal_all(sig):
        for sid in sids:
            for pid in members(sid):
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass
    signal_all(signal.SIGTERM)
    until = start + 5.0
    while any(members(sid) for sid in sids) and time.monotonic() < until:
        time.sleep(.02)
    signal_all(signal.SIGKILL)
    until = time.monotonic() + .5
    while any(members(sid) for sid in sids) and time.monotonic() < until:
        time.sleep(.01)
    if any(members(sid) for sid in sids):
        raise Infrastructure('cleanup_failed', 'Worker/native descendants remained alive after the fixed cleanup grace.')
    ACTIVE.difference_update(sids)
    return time.monotonic() - start
