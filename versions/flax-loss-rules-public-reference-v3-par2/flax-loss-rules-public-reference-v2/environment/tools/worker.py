"""Fresh per-case guider; no graph or rule application until parent GO."""
import argparse
from pathlib import Path
import shlex
import socket
import subprocess
import time

from admission import COMPONENTS
from runtime import configure, require, sha, send, safe_error


def run(args, control):
    configure()
    from scorer import parse_problem, load_scorer
    from planning import FlaxPlanner, FD, PlanningFailure, PlanningTimeout
    from rule_guard import install
    domain, state = parse_problem(args.case, args.domain)
    g = load_scorer(args.checkpoint, domain)
    install()
    planner = FlaxPlanner(is_strips_domain=True, base_planner=FD('--alias lama-first'), search_guider=g, seed=0,
                          relaxation_rules=str(args.candidate / 'relaxation_rules.json'),
                          complementary_rules=str(args.candidate / 'complementary_rules.json'))
    require(g._last_processed_state is None, 'early_inference', 'The fresh guider must have no processed case before GO.')
    statuses = []
    counter = 0
    def observed(command, *unused_args, **unused_kwargs):
        nonlocal counter
        counter += 1
        tokens = shlex.split(command)
        started = time.monotonic()
        p = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        text = p.stdout.decode(errors='replace').rstrip('\n')
        kind = 'fd_cleanup' if '--cleanup' in tokens else 'fd_search' if any(t.endswith('fast-downward.py') for t in tokens) else 'val' if tokens and tokens[0].endswith('/Validate') else 'unknown'
        negative_timeout = kind == 'fd_search' and len(tokens) >= 2 and tokens[0] == 'timeout' and float(tokens[1]) < 0
        statuses.append({'kind': kind, 'exit_status': p.returncode, 'negative_residual': negative_timeout,
                         'seconds': time.monotonic() - started})
        # Native VAL defects must not become an ordinary planner failure.
        if kind == 'val':
            valid = p.returncode == 0 and 'Plan valid' in text
            invalid = p.returncode in (0, 1) and any(s in text for s in ('Plan failed', 'Goal not satisfied', 'Plan invalid', 'Bad plan'))
            require(valid or invalid, 'internal_val_failure', 'Internal original planner VAL invocation failed unexpectedly.')
        elif kind == 'fd_cleanup':
            require(p.returncode == 0, 'fd_cleanup_failure', 'The fixed planner cleanup command failed.')
        elif kind == 'unknown':
            require(False, 'unexpected_native_command', 'Pinned planner requested an unrecognized native command.')
        return text
    subprocess.getoutput = observed
    identity = {n: sha(args.candidate / n) for n in (*COMPONENTS, 'manifest.json')}
    send(control, {'kind': 'READY', 'identity': identity, 'checkpoint_sha256': sha(args.checkpoint),
                   'original_sha256': sha(args.case), 'domain_sha256': sha(args.domain), 'case_graph_constructed': False})
    require(control.recv(3) == b'GO\n', 'missing_go', 'Worker requires the parent GO signal.')
    try:
        plan, _ = planner(domain, state, timeout=40)
        send(control, {'kind': 'RESULT', 'plan': [a.pddl_str() for a in plan], 'statuses': statuses})
    except (PlanningFailure, PlanningTimeout) as exc:
        send(control, {'kind': 'RESULT', 'plan': None, 'exception': type(exc).__name__, 'statuses': statuses})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for key in ('checkpoint', 'case', 'domain', 'candidate'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--fd', type=int, required=True)
    args = parser.parse_args()
    with socket.socket(fileno=args.fd) as control:
        try:
            run(args, control)
        except BaseException as exc:
            send(control, {'kind': 'ERROR', **safe_error(exc)})
            raise SystemExit(1)
