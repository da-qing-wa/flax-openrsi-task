"""Fresh fixed training child; only this child loads the submitted loss."""
import argparse
import importlib.util
import json
from pathlib import Path
import resource
import socket
import sys
import time
import tokenize
import types

from admission import CandidateInvalid, fail
from runtime import configure, require, safe_error, send, sha


def exception_details(exc, candidate_source, source_lines, *, fallback_line=1,
                      fallback_kind='module_start'):
    """Candidate/public-training repair details, without a traceback or locals.

    Training has no primary-case input. Only the admitted candidate source and
    the exception message are exposed; private snapshot paths map to the public
    candidate path. Bounded single-line strings keep diagnostics within IPC.
    """
    public_path = '/workspace/candidate/loss.py'
    def text(value):
        return ' '.join(str(value).replace(candidate_source, public_path).split())[:4096]
    location = {'path': public_path, 'line': fallback_line, 'kind': fallback_kind}
    details = {'exception_type': type(exc).__name__, 'message': text(exc)}
    tb = exc.__traceback__
    while tb is not None:
        frame = tb.tb_frame
        details['operation'] = text(frame.f_code.co_name)
        if frame.f_code.co_filename == candidate_source:
            location = {'path': public_path, 'line': tb.tb_lineno,
                        'function': text(frame.f_code.co_name), 'kind': 'exception_frame'}
        tb = tb.tb_next
    if 1 <= location['line'] <= len(source_lines):
        location['statement'] = text(source_lines[location['line'] - 1])
    details['source'] = location
    if isinstance(exc, (NameError, ImportError)) and exc.name is not None:
        details['identifier'] = text(exc.name)
    return details


def run(candidate, out, control):
    from scorer import torch, checked_cache, guider, schema, ASSETS, read_json, validate_tensors, fixed_model
    from gnn.gnn_dataset import GraphDictDataset, graph_batch_collate
    from gnn import gnn_utils
    import guidance.gnn_guidance as guidance_module
    import numpy as np
    configure()
    checked_cache()
    started = time.monotonic()
    phase_path = out.parent / 'candidate-phase.json'
    def mark(phase, **values):
        phase_path.write_text(json.dumps({'phase': phase, **values}))
    candidate_source = str(candidate / 'loss.py')
    # Respect Python source encodings already admitted by ast.parse(bytes).
    with tokenize.open(candidate_source) as source:
        source_lines = source.read().splitlines()
    def audit(event, args):
        restricted = event == 'open' or event.startswith(('socket.', 'subprocess.')) or event in {
            'os.listdir', 'os.scandir', 'os.chdir', 'os.system', 'os.putenv', 'os.unsetenv', 'os.remove', 'os.rename', 'os.mkdir'}
        if not restricted:
            return
        frame = sys._getframe()
        while frame is not None and frame.f_code.co_filename != candidate_source:
            frame = frame.f_back
        if frame is None:
            return
        if event == 'open' and isinstance(args[0], str):
            # Loading installed numerical-library code is permitted; data,
            # environment probing, writes, subprocesses, and sockets are not.
            name, mode, flags = args
            if name.startswith('/opt/python/lib/') and name.endswith(('.py', '.pyc', '.so')) and not (flags & 3):
                return
        fail('loss_runtime_lookup', '/workspace/candidate/loss.py', 'compute_loss',
             'Candidate code attempted prohibited runtime I/O, environment mutation, or process/service access.', operation=event)
    sys.addaudithook(audit)
    spec = importlib.util.spec_from_file_location('candidate_loss', candidate / 'loss.py')
    module = importlib.util.module_from_spec(spec)
    try:
        mark('candidate_import')
        spec.loader.exec_module(module)
        callback = module.compute_loss
        callback_line = getattr(getattr(callback, '__code__', None), 'co_firstlineno', 1)
        mark('trusted_training')
    except CandidateInvalid:
        raise
    except BaseException as exc:
        fail('loss_import_runtime', '/workspace/candidate/loss.py', 'compute_loss',
             'The admitted loss could not be imported by the fixed training runtime.',
             'Check the reported candidate line and imported name against the baked numerical API.',
             **exception_details(exc, candidate_source, source_lines))

    def module_state():
        def freeze(value):
            if value is None or type(value) in (str, int, float, bool):
                return (type(value).__name__, value)
            if type(value) in (tuple, list):
                return (type(value).__name__, tuple(freeze(x) for x in value))
            if type(value) is dict:
                return ('dict', tuple((freeze(k), freeze(v)) for k, v in value.items()))
            if isinstance(value, torch.Tensor):
                return ('tensor', str(value.dtype), tuple(value.shape), value.detach().cpu().contiguous().numpy().tobytes())
            if isinstance(value, (np.ndarray, np.generic)):
                return ('numpy', str(value.dtype), tuple(value.shape), value.tobytes())
            if isinstance(value, types.ModuleType):
                return ('module', value.__name__)
            if isinstance(value, types.FunctionType):
                return ('function', id(value.__code__), freeze(value.__defaults__), freeze(value.__kwdefaults__),
                        freeze(value.__dict__), tuple(freeze(c.cell_contents) for c in (value.__closure__ or ())))
            if isinstance(value, type) and value.__module__ == 'candidate_loss':
                return ('class', tuple((k, freeze(v)) for k, v in value.__dict__.items()
                                       if k not in ('__dict__', '__weakref__', '__module__', '__doc__')))
            if isinstance(value, (staticmethod, classmethod)):
                return freeze(value.__func__)
            if isinstance(value, (types.BuiltinFunctionType, type)):
                return ('fixed_callable', id(value))
            fail('loss_global_state', '/workspace/candidate/loss.py', 'module', 'Module globals must be inspectable constants or pure functions.')
        try:
            return tuple((k, freeze(v)) for k, v in module.__dict__.items() if not k.startswith('__'))
        except (RecursionError, ValueError, TypeError):
            fail('loss_state_structure', '/workspace/candidate/loss.py', 'module', 'Persistent constants/state must be finite and inspectable without cyclic structures.')

    initial_state = module_state()
    counts = {'train': 0, 'val': 0}
    exposures = {'train': 0, 'val': 0}
    phases = set()
    calls = 0

    def counted(logits, targets, graph, *, epoch, step):
        nonlocal calls
        calls += 1
        original = {k: v.detach().clone() if isinstance(v, torch.Tensor) else v for k, v in graph.items()}
        versions = {k: (id(v), v._version) for k, v in graph.items() if isinstance(v, torch.Tensor)}
        logit_version, target_version = logits._version, targets._version
        logits_before, targets_before = logits.detach().clone(), targets.detach().clone()
        rng = torch.get_rng_state().clone()
        numpy_rng = np.random.get_state()
        try:
            mark('candidate_callback', epoch=epoch, step=step)
            loss = callback(logits, targets, graph, epoch=epoch, step=step)
            mark('trusted_training')
        except CandidateInvalid:
            raise
        except BaseException as exc:
            fail('loss_callback_runtime', '/workspace/candidate/loss.py', 'compute_loss',
                 'The callback raised during a counted fixed-training call.',
                 'Repair the reported candidate expression using the exception message and public input shapes.',
                 epoch=epoch, step=step,
                 input_shapes={'logits': list(logits.shape), 'targets': list(targets.shape)},
                 **exception_details(exc, candidate_source, source_lines,
                                     fallback_line=callback_line,
                                     fallback_kind='callback_definition'))
        def unchanged(key, value):
            before = original[key]
            if isinstance(before, torch.Tensor):
                return (isinstance(value, torch.Tensor) and (id(value), value._version) == versions[key] and
                        value.shape == before.shape and value.dtype == before.dtype and torch.equal(value, before))
            return type(value) is type(before) and value == before
        if (set(original) != set(graph) or any(not unchanged(k, v) for k, v in graph.items()) or
                logits._version != logit_version or targets._version != target_version or
                not torch.equal(logits, logits_before) or not torch.equal(targets, targets_before)):
            fail('loss_input_mutation', '/workspace/candidate/loss.py', 'compute_loss', 'Do not mutate logits, targets, graph tensors, or metadata.')
        def state_unchanged():
            current_numpy = np.random.get_state()
            return (module_state() == initial_state and torch.equal(torch.get_rng_state(), rng) and
                    numpy_rng[0] == current_numpy[0] and np.array_equal(numpy_rng[1], current_numpy[1]) and numpy_rng[2:] == current_numpy[2:])
        if not state_unchanged():
            fail('loss_adaptive_state', '/workspace/candidate/loss.py', 'compute_loss', 'No persistent state or random-state changes are permitted, including validation calls.')
        if not isinstance(loss, torch.Tensor) or loss.ndim != 0 or not torch.isfinite(loss).item() or not loss.requires_grad:
            fail('loss_scalar', '/workspace/candidate/loss.py', 'compute_loss', 'Return one finite differentiable scalar Tensor.')
        try:
            mark('candidate_derivative', epoch=epoch, step=step)
            gradient = torch.autograd.grad(loss, logits, retain_graph=True, allow_unused=True)[0]
            mark('trusted_training')
        except CandidateInvalid:
            raise
        except RuntimeError as exc:
            fail('loss_derivative', '/workspace/candidate/loss.py', 'compute_loss',
                 'Loss must support differentiation with respect to the original logits.',
                 'Check the reported autograd operation and preserve the graph from the original logits to the scalar loss.',
                 epoch=epoch, step=step,
                 input_shapes={'logits': list(logits.shape), 'targets': list(targets.shape)},
                 loss_shape=list(loss.shape),
                 **exception_details(exc, candidate_source, source_lines,
                                     fallback_line=callback_line,
                                     fallback_kind='callback_definition'))
        if gradient is None or not torch.isfinite(gradient).all():
            fail('loss_derivative', '/workspace/candidate/loss.py', 'compute_loss', 'Loss must depend differentiably on original logits with finite derivatives.')
        if not state_unchanged():
            fail('loss_derivative_state', '/workspace/candidate/loss.py', 'compute_loss', 'Derivative computation may not retain adaptive state or alter RNG state.')
        if counts['train'] < (epoch + 1) * 11:
            mark('candidate_backward', epoch=epoch, step=step)
        return loss

    out.mkdir()
    (out / 'checkpoints').mkdir()
    g = guider(counted, out / 'final_seed0')
    data = checked_cache()
    inputs, targets = g._create_graph_dataset(data)
    require(schema(g) == read_json(ASSETS / 'feature-schema.json'), 'training_schema', 'The frozen cache must produce the original ordered feature schema.')
    datasets = {'train': GraphDictDataset(inputs[19:], targets[19:]), 'val': GraphDictDataset(inputs[:19], targets[:19])}
    def fingerprint(mapping):
        import hashlib
        h = hashlib.sha256()
        for key, value in mapping.items():
            h.update(str(key).encode())
            if value is None:
                h.update(b'None')
            else:
                v = value.detach().cpu().contiguous()
                h.update(str((v.dtype, tuple(v.shape))).encode())
                h.update(v.numpy().tobytes())
        return h.hexdigest()
    expected = {phase: [fingerprint(graph_batch_collate([ds[i] for i in range(j, min(j + 16, len(ds)))])['graph_input'])
                         for j in range(0, len(ds), 16)] for phase, ds in datasets.items()}
    def observer(phase, epoch, step, batch, target, output, loss, model, optimizer):
        mark('trusted_training')
        if module_state() != initial_state:
            fail('loss_backward_state', '/workspace/candidate/loss.py', 'compute_loss', 'The backward pass may not update persistent candidate state.')
        index = counts[phase] % len(expected[phase])
        require(fingerprint(batch) == expected[phase][index], 'training_order', 'Training must retain original graph order and input values.')
        counts[phase] += 1
        exposures[phase] += len(batch['n_node'])
        phases.add((phase, epoch))
        if phase == 'train' and any(p.grad is not None and not torch.isfinite(p.grad).all() for p in model.parameters()):
            fail('loss_gradient', '/workspace/candidate/loss.py', 'compute_loss', 'The fixed backward pass produced nonfinite parameter gradients.')
    original_train = gnn_utils.train_model
    def observed(model, *args, **kwargs):
        kwargs.update(save_folder=str(out / 'checkpoints'), batch_observer=observer)
        return original_train(model, *args, **kwargs)
    guidance_module.train_model = observed
    g.seed(0)
    # No new teacher data, model passes, resampling, or altered update schedule.
    try:
        g.train('Mazenamo')
    except CandidateInvalid:
        raise
    except BaseException as exc:
        tb = exc.__traceback__
        while tb is not None:
            if tb.tb_frame.f_code.co_filename == candidate_source:
                fail('loss_execution', '/workspace/candidate/loss.py', 'compute_loss',
                     'Candidate code raised during the fixed forward/loss/backward training path.',
                     'Repair the reported candidate expression; no training or evaluation score was produced.',
                     **exception_details(exc, candidate_source, source_lines))
            tb = tb.tb_next
        raise
    final_path = out / 'final_seed0_Mazenamo.pt'
    final = torch.load(final_path, map_location='cpu', weights_only=True)
    last = torch.load(out / 'checkpoints/model300.pt', map_location='cpu', weights_only=True)
    validate_tensors(final, fixed_model())
    require(final.keys() == last.keys() and all(torch.equal(final[k], last[k]) for k in final), 'final_checkpoint', 'Use final epoch weights, not a selected checkpoint.')
    require(counts == {'train': 3311, 'val': 62} and exposures == {'train': 52976, 'val': 589} and
            calls == 3373 and sum(p == 'val' for p, e in phases) == 31, 'training_exposure', 'All fixed training and validation exposure counts must match.')
    send(control, {'kind': 'TRAINED', 'checkpoint_sha256': sha(final_path), 'counts': counts,
                   'exposures': exposures, 'callback_calls': calls, 'validation_phases': 31,
                   'seconds': time.monotonic() - started, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--fd', type=int, required=True)
    args = parser.parse_args()
    with socket.socket(fileno=args.fd) as control:
        try:
            run(args.candidate, args.out, control)
        except BaseException as exc:
            send(control, {'kind': 'ERROR', **safe_error(exc)})
            raise SystemExit(1)
