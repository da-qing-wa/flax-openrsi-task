"""Explicitly selected public development runs; never produces a Judge reward."""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import time
from admission import admit
from metric_config import PROTOCOL, METRIC
from metrics import error_feedback
from runtime import (ASSETS, SOURCE, VAL, configure, clean_env, command,
                     receive, require, read_json, sha, safe_error)
from supervision import ACTIVE, cleanup


def launch_training(out):
    require(out.is_relative_to(Path('/workspace/research')) and not out.exists(),
            'development_output', 'Choose a new absolute attempt directory below /workspace/research/.')
    manifest, blobs, identity = admit()
    out.mkdir(parents=True)
    candidate = out / 'candidate'
    candidate.mkdir()
    for name, data in blobs.items():
        (candidate / name).write_bytes(data)
    tmp = out / 'tmp'
    tmp.mkdir()
    parent, channel = socket.socketpair()
    process = None
    try:
        with (out / 'training.log').open('xb') as log:
            process = subprocess.Popen(command('train', '--candidate', candidate, '--out', out / 'training', '--fd', channel.fileno()),
                                       cwd=out, env=clean_env(tmp), stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, pass_fds=(channel.fileno(),))
            ACTIVE.add(process.pid)
            channel.close()
            message = receive(parent, 3600, process=process)
            require(message is not None, 'development_training_timeout', 'Development training exceeded 3600 seconds; see the retained development log.')
            process.wait(timeout=5)
            # Retain the complete structured child diagnostic as well as its
            # public training stream; IPC errors otherwise vanish from the log.
            log.write((json.dumps(message, allow_nan=False) + '\n').encode())
        print(json.dumps(message), flush=True)
        require(message.get('kind') == 'TRAINED' and process.returncode == 0, 'development_training_failed', 'Development training did not complete; see its diagnostic and log.')
        record = {'candidate_id': manifest['candidate_id'], 'components': identity,
                  'protocol_id': PROTOCOL, 'metric_id': METRIC, 'primary_score': None, **message}
        (out / 'training-summary.json').write_text(json.dumps(record, indent=2) + '\n')
    finally:
        parent.close()
        channel.close()
        if process is not None:
            cleanup([process.pid])
            process.wait(timeout=1)
        shutil.rmtree(tmp)


def selected_plan(training, group_id):
    require(training.is_relative_to(Path('/workspace/research')), 'development_training_path', 'Use an existing development attempt under /workspace/research/.')
    roster = read_json(ASSETS / 'manifests/development.json')
    matching = [c for c in roster if c['group_id'] == group_id]
    require(len(matching) == 1, 'development_case_selector', 'Select exactly one group_id from the public development manifest.')
    case = matching[0]
    original = SOURCE / case['path']
    domain = SOURCE / 'pddl_files/domains/mazenamo.pddl'
    candidate = training / 'candidate'
    _, _, identity = admit(candidate, workspace_scope=False)
    record = read_json(training / 'training-summary.json')
    checkpoint = training / 'training/final_seed0_Mazenamo.pt'
    require(record['components'] == identity and record['checkpoint_sha256'] == sha(checkpoint), 'development_identity', 'Use the same tuple snapshot and completed development checkpoint.')
    require(sha(original) == case['sha256'], 'development_problem', 'Development problem bytes must match the public manifest.')
    out = training / 'planning' / group_id
    require(not out.exists(), 'development_attempt_exists', 'This selected-case attempt already exists; retain it and use a new training attempt for another run.')
    out.mkdir(parents=True)
    (out / 'VAL').symlink_to(SOURCE / 'VAL', target_is_directory=True)
    tmp = out / 'tmp'
    tmp.mkdir()
    parent, channel = socket.socketpair()
    processes = []
    try:
        with (out / 'planning.log').open('xb') as log:
            worker = subprocess.Popen(command('worker', '--candidate', candidate, '--checkpoint', checkpoint,
                                               '--case', original, '--domain', domain, '--fd', channel.fileno()),
                                      cwd=out, env=clean_env(tmp), stdout=log, stderr=subprocess.STDOUT,
                                      start_new_session=True, pass_fds=(channel.fileno(),))
            processes.append(worker)
            ACTIVE.add(worker.pid)
            channel.close()
            ready = receive(parent, 60, process=worker)
            require(ready and ready.get('kind') == 'READY', 'development_ready', 'Development worker did not reach READY; inspect the selected-case log.')
            begin = time.monotonic()
            parent.sendall(b'GO\n')
            deadline = 20 if case['stratum'].startswith('12') else 40
            message = receive(parent, deadline, process=worker)
            result = {'group_id': group_id, 'path': str(original), 'deadline': deadline, 'worker': message,
                      'status': 'deadline' if message is None else 'unscored_development'}
            if message and message.get('kind') == 'RESULT' and message.get('plan') is not None:
                plan = out / 'plan.plan'
                plan.write_text('\n'.join(f'{i}: {a}' for i, a in enumerate(message['plan'])) + '\n')
                with (out / 'validation.log').open('xb') as val_log:
                    validator = subprocess.Popen([str(VAL), '-v', str(domain), str(original), str(plan)],
                                                 cwd=out, env=clean_env(tmp), stdout=val_log, stderr=subprocess.STDOUT,
                                                 start_new_session=True)
                    processes.append(validator)
                    ACTIVE.add(validator.pid)
                    try:
                        validator.wait(timeout=max(0, begin + deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        result['status'] = 'deadline'
                    else:
                        text = (out / 'validation.log').read_text(errors='replace')
                        result['original_plan_valid'] = validator.returncode == 0 and 'Plan valid' in text
                        result['validator_exit_status'] = validator.returncode
            result['elapsed'] = time.monotonic() - begin
            if result['elapsed'] > deadline:
                result['status'] = 'deadline'
        result.update(protocol_id=PROTOCOL, metric_id=METRIC, primary_score=None)
        (out / 'development-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result), flush=True)
    finally:
        parent.close()
        channel.close()
        cleanup([p.pid for p in processes])
        for process in processes:
            process.wait(timeout=1)
        shutil.rmtree(tmp)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    train = sub.add_parser('train')
    train.add_argument('--out', type=Path, required=True)
    plan = sub.add_parser('plan')
    plan.add_argument('--training', type=Path, required=True)
    plan.add_argument('--case-id', required=True)
    args = parser.parse_args()
    try:
        configure()
        if args.mode == 'train':
            launch_training(args.out.resolve())
        else:
            selected_plan(args.training.resolve(), args.case_id)
    except BaseException as exc:
        print(json.dumps(error_feedback(safe_error(exc))), flush=True)
        raise SystemExit(1)
