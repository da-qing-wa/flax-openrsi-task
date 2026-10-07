"""Fixed-runtime child preflight; never imports a candidate or calls a teacher."""
import argparse
from pathlib import Path
import socket
import subprocess
from runtime import configure, verify_fixed, require, VAL, FD, safe_error, send, clean_env


def run(scratch):
    configure()
    verify_fixed()
    from scorer import checked_cache, guider, schema, ASSETS, read_json, torch, fixed_model
    data = checked_cache()
    g = guider()
    graphs, targets = g._create_graph_dataset(data)
    require(len(graphs) == len(targets) == 195 and schema(g) == read_json(ASSETS / 'feature-schema.json'),
            'fixed_graphs', 'Fixed cache graph construction and schema must succeed.')
    fixed_model()  # Dimension-only constructor, no model forward or candidate code.
    x = torch.tensor([1.0], requires_grad=True)
    (x * x).sum().backward()
    env = clean_env(scratch)
    val = subprocess.run([str(VAL)], cwd=scratch, env=env, capture_output=True, timeout=30)
    require(b'VAL: The PDDL+ plan validation tool' in val.stdout + val.stderr, 'val_startup', 'The locked VAL binary must initialize successfully.')
    fd = subprocess.run([str(FD), '--help'], cwd=scratch, env=env, capture_output=True, timeout=30)
    require(fd.returncode == 0, 'fd_startup', 'The locked Fast Downward driver must initialize successfully.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fd', type=int, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    args = parser.parse_args()
    with socket.socket(fileno=args.fd) as control:
        try:
            run(args.scratch)
            send(control, {'kind': 'PREFLIGHT_OK'})
        except BaseException as exc:
            send(control, {'kind': 'ERROR', **safe_error(exc)})
            raise SystemExit(1)
