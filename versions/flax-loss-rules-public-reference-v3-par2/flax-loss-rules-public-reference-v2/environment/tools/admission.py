"""Public-data-only tuple admission. Judge uses this injected copy as authority."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat

COMPONENTS = ('loss.py', 'relaxation_rules.json', 'complementary_rules.json')
FIELDS = {'candidate_id', 'abi_version', 'description'} | {
    n.rsplit('.', 1)[0] + suffix for n in COMPONENTS for suffix in ('_path', '_sha256')}
SIGNATURES = {**{p: ('obstacle',) for p in ('onground', 'clear', 'isheavy', 'islight', 'ismoveable')},
              **{p: ('robot',) for p in ('dirisup', 'dirisdown', 'dirisleft', 'dirisright')},
              'posempty': ('pos',), 'upon': ('obstacle', 'obstacle'),
              'holding': ('robot', 'obstacle'), 'rat': ('robot', 'pos'), 'oat': ('obstacle', 'pos'),
              **{p: ('pos', 'pos') for p in ('upto', 'downto', 'leftto', 'rightto')}, 'handempty': ()}


class CandidateInvalid(Exception):
    def __init__(self, code, path, field, condition, hint='', **context):
        self.error = dict(code=code, path=str(path), field=field, condition=condition, hint=hint, **context)
        super().__init__(code)


def fail(code, path, field, condition, hint='', **context):
    raise CandidateInvalid(code, path, field, condition, hint, **context)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data, path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                fail('duplicate_key', path, key, 'Each JSON object member must be unique.')
            out[key] = value
        return out
    def constant(value):
        fail('non_json_constant', path, '$', 'NaN and Infinity are not JSON constants.')
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        fail('invalid_json', path, '$', 'UTF-8 JSON must parse within the parser nesting limit.',
             actual=type(exc).__name__)


def regular_bytes(path, limit=1048576):
    path = Path(path)
    try:
        st = path.lstat()
    except FileNotFoundError:
        fail('missing_artifact', path, '$', 'A complete regular file is required.')
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        fail('unsafe_file_type', path, '$', 'Use a regular file, without symlinks or hard links.')
    if st.st_size > limit:
        fail('file_size', path, '$', 'File exceeds the public parser bound.', expected=limit, actual=st.st_size)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        actual = os.fstat(stream.fileno())
        if (st.st_dev, st.st_ino, st.st_size) != (actual.st_dev, actual.st_ino, actual.st_size):
            fail('changing_file', path, '$', 'Close and flush each file before validation.')
        data = stream.read(limit + 1)
    if len(data) != st.st_size:
        fail('changing_file', path, '$', 'File size changed during admission.')
    return data


def directory(path):
    try:
        st = Path(path).lstat()
    except FileNotFoundError:
        fail('missing_directory', path, '$', 'Required directory is missing.')
    if not stat.S_ISDIR(st.st_mode):
        fail('unsafe_directory', path, '$', 'Use a real directory, without a symlink.')


def object_value(value, path, field):
    if type(value) is not dict:
        fail('object_required', path, field, 'Expected a JSON object.')


def indices(value, path, field, arity=None, length=None):
    if type(value) is not list or len(value) > 1024:
        fail('index_list', path, field, 'Expected an integer list with at most 1024 entries.')
    if length is not None and len(value) != length:
        fail('index_arity', path, field, 'The index list must have the declared length.', expected=length, actual=len(value))
    if any(type(i) is not int or i < 0 or (arity is not None and i >= arity) for i in value):
        fail('invalid_index', path, field, 'Indices are nonnegative integers, excluding booleans, within predicate arity when selecting arguments.')
    return value


def signature(name, path, field):
    if name not in SIGNATURES:
        fail('unknown_predicate', path, field, 'Use a declared lowercase MazeNamo predicate.')
    return SIGNATURES[name]


def check_relaxation(rules, path):
    object_value(rules, path, '$')
    if len(rules) > 1024:
        fail('rule_count', path, '$', 'At most 1024 rules are accepted by this parser.')
    for label, rule in rules.items():
        field = label
        object_value(rule, path, field)
        if set(rule) != {'pre_compute', 'precond', 'delete_objects', 'delete_effects', 'add_effects'}:
            fail('rule_fields', path, field, 'A relaxation rule has exactly the five documented sections.')
        for section in ('pre_compute', 'precond', 'delete_effects', 'add_effects'):
            object_value(rule[section], path, field + '.' + section)
            for pred, slots in rule[section].items():
                f = field + '.' + section + '.' + pred
                sig = signature(pred, path, f)
                if section == 'pre_compute':
                    indices(slots, path, f, len(sig), 2)
                elif section == 'precond':
                    indices(slots, path, f, len(sig))
                else:
                    if (section == 'add_effects' and len(sig) != 1) or (section == 'delete_effects' and len(sig) not in (1, 2)):
                        fail('unsupported_effect', path, f, 'Only unary additions and unary/binary deletions are supported.')
                    indices(slots, path, f, length=len(sig))
        indices(rule['delete_objects'], path, field + '.delete_objects')
        # Each precondition is an alternative trigger. Propagate types in native order.
        for trigger, selectors in rule['precond'].items():
            bound = {i: SIGNATURES[trigger][i] for i in selectors}
            for i in rule['delete_objects']:
                if i not in bound:
                    fail('unbound_object_slot', path, field + '.delete_objects', 'Object deletion precedes effects and requires a trigger-bound slot.', slot=i, trigger=trigger)
            for section in ('delete_effects', 'add_effects'):
                for pred, slots in rule[section].items():
                    sig = SIGNATURES[pred]
                    f = field + '.' + section + '.' + pred
                    for position, slot in enumerate(slots):
                        if slot not in bound:
                            if section != 'delete_effects' or len(sig) != 2 or 0 not in bound or pred not in rule['pre_compute']:
                                fail('unbound_effect_slot', path, f, 'Each effect slot must be seeded or derived by an ordered binary deletion relation.', slot=slot, trigger=trigger)
                            a, b = rule['pre_compute'][pred]
                            if bound[0] != sig[a]:
                                fail('relation_anchor_type', path, f, 'Binding slot zero must match the relation key type.', trigger=trigger)
                            bound[slot] = sig[b]
                        if bound[slot] != sig[position]:
                            fail('binding_type', path, f, 'Bound object type must match the effect argument type.', slot=slot, expected=sig[position], actual=bound[slot], trigger=trigger)


def check_complementary(rules, path):
    object_value(rules, path, '$')
    for pred, rule in rules.items():
        sig = signature(pred, path, pred)
        object_value(rule, path, pred)
        if set(rule) != {'cond', 'cmpl'}:
            fail('complementary_fields', path, pred, 'A complementary entry has exactly cond and cmpl.')
        cond, cmpl = rule['cond'], rule['cmpl']
        if type(cond) is not list or type(cmpl) is not list or len(cond) not in (1, 2) or len(cond) != len(cmpl):
            fail('complementary_shape', path, pred, 'cond/cmpl have equal outer lengths of one or two.')
        for key in ('cond', 'cmpl'):
            for i, value in enumerate(rule[key]):
                indices(value, path, f'{pred}.{key}[{i}]', len(sig))


def check_loss_syntax(data, path):
    try:
        tree = ast.parse(data, filename=str(path))
    except (SyntaxError, ValueError, RecursionError) as exc:
        fail('loss_syntax', path, 'compute_loss', 'Loss source must be valid Python.', line=getattr(exc, 'lineno', None))
    # Practical static controls, supplemented by counted-call mutation/state checks.
    # They do not claim isolation against arbitrary root-capable Python.
    banned_names = {'open', 'eval', 'exec', 'compile', '__import__', 'globals', 'locals', 'vars', 'getattr', 'setattr', 'delattr', 'input', 'breakpoint'}
    banned_attrs = {'load', 'save', 'load_state_dict', 'backward', 'step', 'manual_seed', 'seed', 'set_num_threads', 'set_grad_enabled', 'no_grad', 'inference_mode', 'from_file', 'frombuffer', 'from_dlpack'}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or '']
            if any(n.split('.')[0] not in {'torch', 'numpy', 'math', 'itertools', 'functools', 'collections', 'statistics', 'operator'} for n in names) or getattr(node, 'level', 0):
                fail('loss_import', path, 'imports', 'Use baked tensor libraries and pure numerical/collection standard-library helpers; no Work runtime dependencies.')
            if isinstance(node, ast.ImportFrom) and any(a.name in banned_names | banned_attrs for a in node.names):
                fail('loss_import_control', path, 'imports', 'Do not import runtime I/O, state, or optimizer controls.')
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            fail('loss_state', path, 'compute_loss', 'The loss must be a stateless function without persistent adaptive state.')
        if isinstance(node, ast.Name) and node.id in banned_names:
            fail('loss_lookup', path, 'compute_loss', 'Dynamic execution, runtime lookup, and reflection are prohibited.', line=node.lineno)
        if isinstance(node, ast.Attribute) and (node.attr.startswith('_') or node.attr in banned_attrs):
            fail('loss_runtime_control', path, 'compute_loss', 'Runtime access, hidden attributes, model/optimizer control, and stateful I/O are prohibited.', line=node.lineno)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'compute_loss']
    if len(functions) != 1:
        fail('loss_entrypoint', path, 'compute_loss', 'Define exactly one compute_loss(logits, targets, graph, *, epoch, step).')
    f = functions[0]
    if ([a.arg for a in f.args.posonlyargs + f.args.args] != ['logits', 'targets', 'graph'] or
            [a.arg for a in f.args.kwonlyargs] != ['epoch', 'step'] or f.args.vararg or f.args.kwarg or f.decorator_list):
        fail('loss_signature', path, 'compute_loss', 'Use the documented compute_loss-v1 signature without decorators.')


def admit(root=Path('/workspace/candidate'), workspace_scope=True):
    root = Path(root)
    directory(root.parent)
    directory(root)
    if workspace_scope:
        extras = set(os.listdir(root.parent)) - {'candidate', 'research'}
        if extras:
            fail('workspace_scope', root.parent, '$', 'Only candidate/ and research/ belong in WORKDIR.', hint='Move development output under /workspace/research/.')
        if (root.parent / 'research').exists() or (root.parent / 'research').is_symlink():
            directory(root.parent / 'research')
    if set(os.listdir(root)) != set(COMPONENTS) | {'manifest.json'}:
        fail('candidate_inventory', root, '$', 'The candidate directory must contain exactly the four submission files.')
    blobs = {n: regular_bytes(root / n) for n in (*COMPONENTS, 'manifest.json')}
    manifest = strict_json(blobs['manifest.json'], root / 'manifest.json')
    object_value(manifest, root / 'manifest.json', '$')
    if set(manifest) != FIELDS:
        fail('manifest_fields', root / 'manifest.json', '$', 'Exactly the nine documented manifest fields are required.')
    if type(manifest['candidate_id']) is not str or re.fullmatch(r'[A-Za-z0-9_-]+', manifest['candidate_id']) is None:
        fail('candidate_id', root / 'manifest.json', 'candidate_id', 'Use one or more ASCII letters, digits, underscores, or hyphens.')
    if manifest['abi_version'] != 'flax-loss-rules-v2' or type(manifest['description']) is not str:
        fail('manifest_abi', root / 'manifest.json', 'abi_version/description', 'Use ABI flax-loss-rules-v2 and a string description.')
    for name in COMPONENTS:
        stem = name.rsplit('.', 1)[0]
        h = manifest[stem + '_sha256']
        if manifest[stem + '_path'] != name:
            fail('component_path', root / 'manifest.json', stem + '_path', 'Use exactly the relative component filename.', expected=name)
        if type(h) is not str or re.fullmatch(r'[0-9a-fA-F]{64}', h) is None or h.lower() != digest(blobs[name]):
            fail('component_digest', root / name, stem + '_sha256', 'Manifest digest must match the actual submitted bytes.', expected=digest(blobs[name]))
    relaxation = strict_json(blobs['relaxation_rules.json'], root / 'relaxation_rules.json')
    complementary = strict_json(blobs['complementary_rules.json'], root / 'complementary_rules.json')
    check_relaxation(relaxation, root / 'relaxation_rules.json')
    check_complementary(complementary, root / 'complementary_rules.json')
    check_loss_syntax(blobs['loss.py'], root / 'loss.py')
    identity = {n: digest(b) for n, b in blobs.items()}
    return manifest, blobs, identity
