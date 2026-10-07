"""Candidate-only complete trial with external timing and final-only reward."""
import json
import math
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import socket
import subprocess
import tarfile
import tempfile
import time
import uuid

from admission import admit, CandidateInvalid, fail
from metrics import aggregate, error_feedback, write_reward
from metric_config import PROTOCOL_FILE, METRIC, FAILURE_PENALTY
from runtime import (ROOT, SOURCE, VAL, PROTOCOL, STRATA, Infrastructure, require,
                     configure, sha, read_json, clean_env, command, receive, safe_error)
from supervision import ACTIVE, cleanup
from audit import Audit, require_private_mount

LOGS = Path('/logs/verifier')
AUDIT_ORIGIN = 'scientific_execution'


def child_error(message):
    if message.get('status') == 'candidate_invalid':
        errors = message.get('errors')
        require(type(errors) is list and len(errors) == 1, 'candidate_error_envelope', 'Candidate error report must be complete.')
        e = errors[0]
        require(e.get('path') in ('/workspace/candidate/loss.py', '/workspace/candidate/relaxation_rules.json', '/workspace/candidate/complementary_rules.json'),
                'candidate_error_path', 'Candidate error must refer to a submitted component.')
        raise CandidateInvalid(**e)
    raise Infrastructure(message.get('code', 'worker_failure'), message.get('condition', 'A fixed worker did not complete.'))


def child(entry, args, scratch, limit, audit_dir=None):
    parent, channel = socket.socketpair()
    process = None
    began = time.monotonic()
    with ((audit_dir or scratch) / (entry + '.log')).open('xb') as log:
        try:
            process = subprocess.Popen(command(entry, *args, '--fd', channel.fileno()),
                                       cwd=scratch, env=clean_env(scratch), pass_fds=(channel.fileno(),),
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            ACTIVE.add(process.pid)
            channel.close()
            try:
                message = receive(parent, limit, process=process)
            except Infrastructure as exc:
                if entry == 'train' and exc.code == 'worker_ipc_closed':
                    try:
                        code = process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        code = None
                    phase_path = scratch / 'candidate-phase.json'
                    phase = read_json(phase_path) if phase_path.is_file() else {}
                    if code in (-4, -6, -7, -8, -11) and phase.get('phase') in {
                            'candidate_import', 'candidate_callback', 'candidate_derivative', 'candidate_backward'}:
                        fail('candidate_process_crash', '/workspace/candidate/loss.py', 'compute_loss',
                             'The child crashed while executing the admitted loss or its derivative after fixed runtime preflight.',
                             'Inspect the loss with the public development tool.', signal=-code, execution_phase=phase['phase'])
                raise
            if message is None:
                if entry == 'train':
                    fail('training_budget', '/workspace/candidate/loss.py', 'compute_loss',
                         'Fresh fixed training exceeded its 3600-second guard.', 'Simplify the loss while preserving the frozen recipe.')
                raise Infrastructure('preflight_timeout', 'Fixed runtime preflight exceeded its startup guard.')
            if message.get('kind') == 'ERROR':
                child_error(message)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                raise Infrastructure('child_exit_timeout', 'A completed worker did not exit cleanly.')
            require(process.returncode == 0, 'child_exit_status', 'Worker completion and exit status disagree.')
            return message, time.monotonic() - began
        finally:
            channel.close()
            parent.close()
            if process is not None:
                cleanup([process.pid])
                process.wait(timeout=1)


def unpack_primary(destination, roster):
    expected = {r['path']: r['sha256'] for r in roster}
    seen = set()
    with tarfile.open(ROOT / 'assets/primary-pddl.tar.gz') as archive:
        for member in archive:
            require(member.isfile() and member.name in expected and member.name not in seen,
                    'primary_archive', 'Primary archive must contain exactly the frozen regular problem files.')
            p = destination / member.name
            require(p.is_relative_to(destination) and '..' not in Path(member.name).parts and not Path(member.name).is_absolute(),
                    'primary_archive_path', 'Primary archive contains an unsafe member path.')
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('xb') as f:
                shutil.copyfileobj(archive.extractfile(member), f)
            require(sha(p) == expected[member.name], 'primary_digest', 'Original primary PDDL bytes must match the frozen manifest.')
            seen.add(member.name)
    require(seen == set(expected), 'primary_inventory', 'All frozen primary problems are required.')


def native_statuses(message, elapsed, deadline):
    search = []
    for row in message.get('statuses', []):
        code, kind = row['exit_status'], row['kind']
        if kind == 'fd_search':
            search.append(row)
            if code == 125:
                require(row.get('negative_residual') is True and elapsed >= deadline,
                        'unexplained_timeout_125', 'Native timeout exit 125 is ordinary only for the documented externally late negative-residual path.')
            else:
                require(code in {0, 1, 2, 3, 10, 11, 12, 20, 21, 22, 23, 24, 124},
                        'native_search_failure', 'The fixed planner returned an unexplained process status.')
        elif kind in ('fd_cleanup', 'val'):
            require(code in ({0} if kind == 'fd_cleanup' else {0, 1}), 'native_validation_failure', 'Fixed native validation or cleanup failed.')
        else:
            raise Infrastructure('native_command_kind', 'Unexpected native command classification.')
    return search


def case_evaluate(case, original, domain, checkpoint, candidate, identity, scratch, audit=None, index=None):
    scratch.mkdir()
    work = scratch / 'work'
    work.mkdir()
    (work / 'VAL').symlink_to(SOURCE / 'VAL', target_is_directory=True)
    tmp = scratch / 'tmp'
    tmp.mkdir()
    env = clean_env(tmp)
    deadline = 20 if case['stratum'].startswith('12') else 40
    require(sha(original) == case['sha256'], 'case_digest', 'Original PDDL must retain its frozen identity.')
    parent, channel = socket.socketpair()
    processes = []
    began = time.monotonic()
    active_start = None
    elapsed = None
    outcome, validity, plan_length = None, None, None
    case_output = audit.begin_case(index, case, identity) if audit is not None else scratch
    message = None
    received = None
    cutoff = None
    scored_end = None
    validator = None
    validation_result = None
    case_error = None
    cleaned_seconds = None
    cleaned = False
    with (case_output / 'worker.log').open('xb') as log:
        try:
            worker = subprocess.Popen(command('worker', '--case', original, '--domain', domain,
                                               '--checkpoint', checkpoint, '--candidate', candidate, '--fd', channel.fileno()),
                                      cwd=work, env=env, pass_fds=(channel.fileno(),), stdout=log,
                                      stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(worker)
            ACTIVE.add(worker.pid)
            channel.close()
            ready = receive(parent, 60, process=worker)
            if ready and ready.get('kind') == 'ERROR':
                child_error(ready)
            require(ready is not None and ready.get('kind') == 'READY', 'ready_timeout', 'A fresh fixed worker must reach READY within 60 seconds.')
            require(ready.get('identity') == identity['components'] and ready.get('checkpoint_sha256') == identity['checkpoint_sha256'] and
                    ready.get('original_sha256') == case['sha256'] and ready.get('domain_sha256') == sha(domain) and ready.get('case_graph_constructed') is False,
                    'worker_identity', 'Worker must reload the exact tuple, checkpoint, original problem, and domain before GO.')
            startup_seconds = time.monotonic() - began
            active_start = time.monotonic()
            parent.sendall(b'GO\n')
            cutoff = active_start + deadline
            message = receive(parent, cutoff - time.monotonic(), process=worker)
            received = time.monotonic()
            elapsed = received - active_start
            if message and message.get('kind') == 'ERROR':
                child_error(message)
            search = native_statuses(message, elapsed, deadline) if message else []
            if message is None or received > cutoff:
                outcome = 'deadline'
            else:
                require(message.get('kind') == 'RESULT', 'case_result', 'Worker must complete a well-formed planning result.')
                if message.get('plan') is None:
                    require(message.get('exception') in ('PlanningFailure', 'PlanningTimeout') and bool(search),
                            'ambiguous_search_failure', 'No-plan classification requires an ordinary planner outcome with native search evidence.')
                    require(message['exception'] == 'PlanningTimeout' or any(r['exit_status'] in {10, 11, 12, 20, 21, 22, 23, 24, 124} for r in search),
                            'unparsed_success', 'A successful native status without a parsed plan is an evaluator failure.')
                    outcome = 'no_plan'
                else:
                    plan = message['plan']
                    require(type(plan) is list and all(type(a) is str and re.fullmatch(r'\([a-zA-Z0-9_\-\s]+\)', a) for a in plan),
                            'malformed_plan_ipc', 'Planner must send a syntactically well-formed action list.')
                    plan_length = len(plan)
                    plan_path = scratch / 'plan.plan'
                    with plan_path.open('x') as f:
                        f.write('\n'.join(f'{i}: {a}' for i, a in enumerate(plan)) + '\n')
                    with (case_output / 'val.log').open('xb') as val_log:
                        validator = subprocess.Popen([str(VAL), '-v', str(domain), str(original), str(plan_path)],
                                                     cwd=work, env=env, stdout=val_log, stderr=subprocess.STDOUT,
                                                     start_new_session=True)
                        processes.append(validator)
                        ACTIVE.add(validator.pid)
                        try:
                            validator.wait(timeout=max(0, cutoff - time.monotonic()))
                        except subprocess.TimeoutExpired:
                            outcome = 'deadline'
                        else:
                            text = (case_output / 'val.log').read_text(errors='replace')
                            if validator.returncode == 0 and 'Plan valid' in text:
                                outcome, validity = 'valid', True
                                validation_result = 'valid'
                            elif validator.returncode in (0, 1) and any(s in text for s in ('Plan failed', 'Goal not satisfied', 'Plan invalid', 'Bad plan')):
                                outcome, validity = 'invalid_plan', False
                                validation_result = 'invalid'
                            else:
                                raise Infrastructure('final_val_failure', 'Independent original-instance VAL failed unexpectedly.')
            scored_end = time.monotonic()
            elapsed = scored_end - active_start
            if elapsed > deadline:
                outcome, validity = 'deadline', None
        except BaseException as exc:
            case_error = safe_error(exc)
            raise
        finally:
            parent.close()
            channel.close()
            try:
                cleaned_seconds = cleanup([p.pid for p in processes])
                for process in processes:
                    process.wait(timeout=1)
                cleaned = True
            except BaseException as exc:
                case_error = safe_error(exc)
                raise
            finally:
                if audit is not None:
                    row = {'instance_id': case['group_id'], 'sha256': case['sha256'], 'stratum': case['stratum'],
                           'protocol_id': PROTOCOL, 'identity': identity.copy(), 'seed': 0, 'deadline': deadline,
                           'elapsed': elapsed, 'outcome': outcome, 'validity': validity, 'plan_length': plan_length,
                           'cleaned': cleaned, 'startup_seconds': locals().get('startup_seconds'),
                           'cleanup_seconds': cleaned_seconds, 'domain_sha256': sha(domain),
                           'timing': {'go_monotonic': active_start, 'cutoff_monotonic': cutoff,
                                      'ipc_received_monotonic': received, 'scored_end_monotonic': scored_end},
                           'validation': {'attempted': validator is not None, 'observed_result': validation_result,
                                          'exit_status': validator.returncode if validator is not None else None,
                                          'completion_evidence': 'return status and original VAL text observed before scored_end; no invented exact exit timestamp'},
                           'worker_exit_status': processes[0].returncode if processes else None,
                           'native_statuses': message.get('statuses', []) if message else [], 'error': case_error}
                    audit.retain_case(index, row, message, scratch)
    require(outcome is not None and active_start is not None and elapsed is not None, 'incomplete_case', 'No partial case may reach aggregation.')
    if audit is None:
        raise Infrastructure('audit_missing', 'A scored case requires private audit export.')
    # retain_case verified record/log hashes before this destructive cleanup.
    shutil.rmtree(scratch)
    return row


def run(scratch, audit):
    started = time.monotonic()
    os.environ.update(clean_env(scratch))
    tempfile.tempdir = str(scratch)
    allocation = configure()
    preflight_dir = scratch / 'preflight'
    preflight_dir.mkdir()
    message, preflight_seconds = child('preflight', ['--scratch', preflight_dir], preflight_dir, 300, audit.phase)
    require(message.get('kind') == 'PREFLIGHT_OK', 'preflight_result', 'Fixed runtime preflight did not complete.')
    manifest, blobs, components = admit()
    candidate = scratch / 'candidate'
    candidate.mkdir()
    for name, data in blobs.items():
        with (candidate / name).open('xb') as f:
            f.write(data)
    audit.snapshot_tuple(manifest['candidate_id'], components, candidate)
    protocol = read_json(ROOT / PROTOCOL_FILE)
    require(protocol['protocol_id'] == PROTOCOL, 'protocol_identity', 'The local amended protocol must have its own identity.')
    require(protocol['metric']['metric_id'] == METRIC and protocol['metric']['failure_penalty'] == FAILURE_PENALTY,
            'metric_identity', 'Use the fixed task-owned amended metric.')
    require(all(sha(ROOT / n) == h for n, h in protocol['scoring_code_sha256'].items()),
            'scoring_code_identity', 'Scorer/config bytes must match the amended protocol.')
    roster = read_json(ROOT / 'assets/evaluation.json')
    require(sha(ROOT / 'assets/evaluation.json') == protocol['roster_sha256'] and len(roster) == 400 and
            len({r['group_id'] for r in roster}) == 400 and all(sum(r['stratum'] == s for r in roster) == 50 for s in STRATA),
            'frozen_roster', 'Retain the exact original ordered 400-case roster.')
    primary = scratch / 'primary'
    primary.mkdir()
    unpack_primary(primary, roster)
    domain = ROOT / 'assets/mazenamo.pddl'
    require(sha(domain) == '2d2ff224dcf3e9e6f7232e3cf9dc8bc2b46d868eddd062a5b7277d87188115bf', 'domain_digest', 'Independent VAL requires the immutable original domain.')
    require(sha(ROOT / PROTOCOL_FILE) == sha(audit.path / 'protocol.json') and
            sha(ROOT / 'assets/evaluation.json') == sha(audit.path / 'evaluation.json'),
            'audit_input_identity', 'The private export must preserve the exact executed protocol and roster.')
    run_id = audit.run_id
    print(json.dumps({'status': 'started', 'run_id': run_id, 'candidate_id': manifest['candidate_id'],
                      'components': components, 'protocol_sha256': sha(ROOT / PROTOCOL_FILE)}), flush=True)
    train_message, train_wall = child('train', ['--candidate', candidate, '--out', scratch / 'training'], scratch, 3600, audit.phase)
    audit.capture('training-summary.json', (json.dumps(train_message, indent=2) + '\n').encode())
    require(train_message.get('kind') == 'TRAINED' and train_message.get('counts') == {'train': 3311, 'val': 62} and
            train_message.get('exposures') == {'train': 52976, 'val': 589} and train_message.get('callback_calls') == 3373 and
            train_message.get('validation_phases') == 31, 'training_completion', 'Every prescribed training and validation exposure must complete.')
    checkpoint = scratch / 'training/final_seed0_Mazenamo.pt'
    require(sha(checkpoint) == train_message['checkpoint_sha256'], 'checkpoint_identity', 'Reload exactly the completed final tensor artifact.')
    # Parent imports trusted tensor loader only after candidate child exits.
    from scorer import torch, fixed_model, validate_tensors
    validate_tensors(torch.load(checkpoint, map_location='cpu', weights_only=True), fixed_model())
    identity = {'run_id': run_id, 'candidate_id': manifest['candidate_id'], 'components': components,
                'checkpoint_sha256': sha(checkpoint), 'protocol_sha256': sha(ROOT / PROTOCOL_FILE)}
    audit.set_identity(identity, candidate)
    records = []
    evaluation_start = time.monotonic()
    for index, case in enumerate(roster):
        require(time.monotonic() - evaluation_start < 38300 and time.monotonic() - started < 41900,
                'whole_trial_guard', 'The whole evaluation/trial guard expired; incomplete records cannot be scored.')
        records.append(case_evaluate(case, primary / case['path'], domain, checkpoint, candidate, identity, scratch / f'case-{index:04d}', audit, index))
    require(time.monotonic() - evaluation_start < 38300, 'evaluation_guard', 'Evaluation must complete inside the whole-evaluation guard.')
    from runtime import verify_fixed
    verify_fixed()
    require(all(sha(candidate / n) == h for n, h in components.items()) and sha(checkpoint) == identity['checkpoint_sha256'],
            'trial_input_mutation', 'The admitted tuple and final checkpoint must remain unchanged throughout evaluation.')
    result = aggregate(roster, records, identity)
    result['provenance'] = identity
    result['resources'] = {'logical_cpu_ids': allocation, 'training_wall_seconds': train_wall,
                           'training_peak_rss_kib': train_message['peak_rss_kib'],
                           'preflight_seconds': preflight_seconds, 'evaluation_wall_seconds': time.monotonic() - evaluation_start,
                           'parent_peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                           'completed_child_peak_rss_kib': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                           'startup_seconds': sum(r['startup_seconds'] for r in records),
                           'active_seconds': sum(r['elapsed'] for r in records),
                           'cleanup_seconds': sum(r['cleanup_seconds'] for r in records)}
    require(time.monotonic() - started < 41900, 'trial_guard', 'Complete trial exceeded its guard.')
    return result


def terminated(signum, frame):
    raise Infrastructure('trial_terminated', 'The complete trial was terminated before finalization; no reward is valid.')


def main():
    signal.signal(signal.SIGTERM, terminated)
    signal.signal(signal.SIGINT, terminated)
    began = time.monotonic()
    audit = None
    scratch = None
    result = None
    try:
        require_private_mount(LOGS)
        audit = Audit(LOGS, uuid.uuid4().hex, ROOT, AUDIT_ORIGIN)
        scratch = Path(tempfile.mkdtemp(prefix='flax-judge-', dir='/tmp'))
        os.chmod(scratch, 0o700)
        try:
            result = run(scratch, audit)
        finally:
            cleanup(list(ACTIVE))
        require(not ACTIVE and time.monotonic() - began < 41900, 'final_cleanup_guard',
                'All trial cleanup must finish within the complete-trial guard.')
        require(math.isfinite(result['reward']) and 0 <= result['reward'] <= 100, 'final_reward',
                'Reward must be finite and in range.')
        # No TemporaryDirectory destructor: only verified exports permit deletion.
        audit.finish(result, complete=True)
        shutil.rmtree(scratch)
        require(time.monotonic() - began < 41900, 'final_cleanup_guard',
                'Audit export and temporary cleanup count toward the complete-trial guard.')
        result['resources']['total_seconds'] = time.monotonic() - began
        print(json.dumps(result, allow_nan=False), flush=True)
        write_reward(result, LOGS / 'reward.json')
        return 0
    except BaseException as exc:
        error = error_feedback(safe_error(exc))
        if audit is not None:
            try:
                audit.capture('failure.json', (json.dumps({'scientific_result_before_failure': result,
                    'failure': error, 'temporary_cleanup_permitted': False}, indent=2, allow_nan=False) + '\n').encode())
                if not (audit.path / 'outcome.json').exists():
                    audit.finish({'status': 'partial', 'failure': error}, complete=False)
                    if scratch is not None and not getattr(exc, 'code', '').startswith('audit_'):
                        shutil.rmtree(scratch)
            except BaseException:
                # Retain unexported scratch; never convert storage failure to a candidate failure/zero.
                error = error_feedback({'status': 'infrastructure_unscored', 'code': 'audit_export_failed',
                    'condition': 'Private audit export failed; available partial evidence was retained.'})
        error['resources'] = {'total_seconds': time.monotonic() - began,
                              'parent_peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                              'completed_child_peak_rss_kib': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss}
        print(json.dumps(error, allow_nan=False), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
