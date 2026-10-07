"""Fixed tensor-only model and immutable graph construction; no candidate imports."""
import pickle
import numpy as np
import torch
from pddlgym.parser import PDDLDomainParser, PDDLProblemParser
from pddlgym.structs import State, LiteralConjunction
from guidance.gnn_guidance import GNNSearchGuidance
from gnn.gnn import setup_graph_net
from gnn.gnn_dataset import GraphDictDataset
from runtime import ASSETS, SOURCE, require, read_json, sha

CACHE = ASSETS / 'data/training_data_Mazenamo.pkl'


class ForbiddenTeacher:
    def __call__(self, *args, **kwargs):
        raise RuntimeError('Teacher collection is prohibited.')


def guider(callback=None, output=None):
    return GNNSearchGuidance(ForbiddenTeacher(), 200, 301, 'bce', 10, False, True,
                             str(CACHE.parent / 'training_data'), str(output or '/tmp/unused'), True,
                             compute_loss=callback)


def schema(g):
    return {'node_features': {str(k): v for k, v in g._node_feature_to_index.items()},
            'edge_features': {str(k): v for k, v in g._edge_feature_to_index.items()}}


def checked_cache():
    require(sha(CACHE) == '6622009ab767a0d2db5d40a5e6efa577820569ed88a7dca804ac0d4c09db7a8c', 'cache_identity', 'The exact frozen cache is required.')
    with CACHE.open('rb') as f:
        data = pickle.load(f)  # Only this hash-verified fixed asset is ever unpickled.
    require(len(data[0]) == len(data[1]) == 195, 'cache_count', 'Frozen cache must contain 195 ordered labels.')
    return data


def parse_problem(path, domain_path=None):
    domain = PDDLDomainParser(str(domain_path or SOURCE / 'pddl_files/domains/mazenamo.pddl'),
                              expect_action_preds=False, operators_as_actions=True)
    problem = PDDLProblemParser(str(path), domain.domain_name, domain.types, domain.predicates,
                               list(domain.actions), domain.constants)
    goal = problem.goal
    if type(goal).__name__ == 'Literal':
        goal = LiteralConjunction([goal])
    return domain, State(frozenset(problem.initial_state), frozenset(problem.objects), goal)


def fixed_model():
    graph = {'nodes': np.zeros((1, 23)), 'edges': np.zeros((1, 24)), 'globals': None,
             'n_node': np.array([1]), 'n_edge': np.array([1]), 'senders': np.array([0]), 'receivers': np.array([0])}
    target = dict(graph, nodes=np.zeros((1, 1)))
    return setup_graph_net(GraphDictDataset([graph], [target]), use_gpu=False, num_steps=3)


def validate_tensors(state, model):
    from admission import fail
    expected = model.state_dict()
    if not isinstance(state, dict) or state.keys() != expected.keys():
        fail('model_keys', '/workspace/candidate/loss.py', 'compute_loss', 'Fresh training must produce the fixed-model tensor dictionary.')
    for key, value in state.items():
        if (not isinstance(value, torch.Tensor) or value.shape != expected[key].shape or
                value.dtype != expected[key].dtype or not torch.isfinite(value).all()):
            fail('model_tensor', '/workspace/candidate/loss.py', 'compute_loss', 'Training produced an incompatible or nonfinite model tensor.', tensor=key)


def load_scorer(checkpoint, domain):
    state = torch.load(checkpoint, map_location='cpu', weights_only=True)
    model = fixed_model()
    validate_tensors(state, model)
    model.load_state_dict(state)
    s = read_json(ASSETS / 'feature-schema.json')
    g = guider()
    def resolve(name):
        if name.startswith('WANT'):
            return g.wrap_goal_literal(resolve(name[4:]))
        if name.startswith('REV'):
            return g.reverse_binary_literal(resolve(name[3:]))
        return domain.types[name] if name in domain.types else domain.predicates[name]
    g._node_feature_to_index = {resolve(k): v for k, v in s['node_features'].items()}
    g._edge_feature_to_index = {resolve(k): v for k, v in s['edge_features'].items()}
    g._num_node_features, g._num_edge_features, g._model = 23, 24, model
    require(schema(g) == s, 'feature_schema', 'Loaded feature schema must match the frozen ordering.')
    return g
