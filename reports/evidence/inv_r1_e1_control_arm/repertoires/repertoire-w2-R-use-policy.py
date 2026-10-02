def STEP(view, state):
    by_family = {"graph": ["acquired-gr-b0bd83b7"], "software": ["acquired-sw-b0bd83b7"]}
    unscoped = []
    eligible = list(view.get('eligible_methods') or [])
    family = (view.get('task_content') or {}).get('family')
    if by_family:
        named = by_family.get(family, [])
        if len(named) != 1:
            raise ValueError(
                'no single repertoire member is scoped to %r' ' among %s' % (family, sorted(by_family)))
        picked = named[0]
        why = ['family=%s' % (family,),
               'scope[%s]=%s' % (picked, family)]
        for other in sorted(by_family):
            if other != family:
                why.append(
                    'not-scoped-to-task[%s]=%s' % (by_family[other][0], other))
    else:
        picked = unscoped[0]
        why = ['family=%s' % (family,),
               'scope[%s]=unscoped' % (picked,)]
    if picked not in eligible:
        raise ValueError(
            'selected %r is not among the eligible methods' % (picked,))
    return {'action': {'kind': 'use_method',
                     'target': view['task_content']['task_id'],
                     'inputs': {'method_id': picked,
                                'max_queries': 4},
                     'evidence_refs': why,
                     'requested_resources': {'queries': 4}},
            'state': {'picked': picked, 'why': why}}
