"""Timed binding validation; supported transformations delegate to pinned Flax."""
from admission import fail


def install():
    import planning.my_planner as engine
    original = engine.apply_relaxation_rules

    def checked(state, rules, domain, force_include_goal_objects=True):
        # Same original literals, last assignment, trigger order and binary slot order.
        # Missing relation entries still skip binary deletions unless a later required
        # consumer needs the unset slot, which the candidate contract disallows.
        for label, rule in rules.items():
            relations = {}
            for lit in state.literals:
                name = lit.predicate.name
                if name in rule['pre_compute']:
                    a, b = rule['pre_compute'][name]
                    relations.setdefault(name, {})[lit.variables[a]] = lit.variables[b]
            for lit in state.literals:
                name = lit.predicate.name
                if name not in rule['precond']:
                    continue
                bound = {i: lit.variables[i] for i in rule['precond'][name]}
                def require(slot, field):
                    if slot not in bound:
                        fail('runtime_unbound_slot', '/workspace/candidate/relaxation_rules.json', label + '.' + field,
                             'A required slot was not bound on a runtime trigger path.',
                             'Bind every required slot before consuming it; a missing relation does not invent an object.', slot=slot, trigger=name)
                for slot in rule['delete_objects']:
                    require(slot, 'delete_objects')
                for pred, slots in rule['delete_effects'].items():
                    if len(slots) == 1:
                        require(slots[0], 'delete_effects.' + pred)
                    else:
                        for slot in slots:
                            if slot not in bound:
                                require(0, 'delete_effects.' + pred)
                                relation = relations.get(pred, {})
                                if bound[0] in relation:
                                    bound[slot] = relation[bound[0]]
                for pred, slots in rule['add_effects'].items():
                    require(slots[0], 'add_effects.' + pred)
        return original(state, rules, domain, force_include_goal_objects)

    engine.apply_relaxation_rules = checked
