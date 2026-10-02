def STEP(view, state):
    by_family = {"graph": ["ctl-graph-ddmin", "ctl-graph-greedy"], "software": ["ctl-software-ddmin", "ctl-software-greedy"]}
    by_shape = {"graph": {"template:C5+joined-by-path|vertices:10e11": "ctl-graph-greedy", "template:C5+shared-edge|vertices:8e9": "ctl-graph-greedy", "template:C5+shared-vertex|vertices:9e10": "ctl-graph-greedy", "template:C5+tree|vertices:6e6": "ctl-graph-greedy", "template:C7+tree|vertices:8e8": "ctl-graph-greedy", "template:C9+tree|vertices:10e10": "ctl-graph-greedy"}, "software": {"template:stale-clear-core|ops:10": "ctl-software-ddmin", "template:stale-clear-core|ops:13": "ctl-software-ddmin", "template:stale-clear-del-core|ops:13": "ctl-software-ddmin", "template:stale-clear-del-core|ops:14": "ctl-software-ddmin", "template:stale-read-2chain|ops:10": "ctl-software-ddmin", "template:stale-read-2chain|ops:11": "ctl-software-ddmin", "template:stale-read-2chain|ops:13": "ctl-software-ddmin", "template:stale-read-2chain|ops:8": "ctl-software-greedy", "template:stale-read-3chain|ops:12": "ctl-software-ddmin", "template:stale-read-3chain|ops:13": "ctl-software-ddmin", "template:stale-read-3chain|ops:14": "ctl-software-ddmin", "template:stale-read-3chain|ops:9": "ctl-software-ddmin"}}
    by_template = {"graph": {"template:C5+joined-by-path": "ctl-graph-greedy", "template:C5+shared-edge": "ctl-graph-greedy", "template:C5+shared-vertex": "ctl-graph-greedy", "template:C5+tree": "ctl-graph-greedy", "template:C7+tree": "ctl-graph-greedy", "template:C9+tree": "ctl-graph-greedy"}, "software": {"template:stale-clear-core": "ctl-software-ddmin", "template:stale-clear-del-core": "ctl-software-ddmin", "template:stale-read-2chain": "ctl-software-ddmin", "template:stale-read-3chain": "ctl-software-ddmin"}}
    eligible = list(view.get('eligible_methods') or [])
    task = dict(view.get('task_content') or {})
    family = task.get('family')
    named = list(by_family.get(family) or [])
    if not named:
        raise ValueError(
            'no repertoire member is scoped to %r' % (family,))
    if len(named) == 1:
        picked = named[0]
        rule = 'sole-member'
        feature = 'n/a'
    else:
        table = by_shape.get(family) or {}
        template = task.get('template')
        if not isinstance(template, str) or not template:
            template = 'unshaped'
        key = 'template:%s' % template
        for field, noun in (('ops', 'ops'),
                          ('vertices', 'vertices')):
            atoms = task.get(field)
            if isinstance(atoms, list) and atoms:
                edges = task.get('edges')
                suffix = ('e%d' % len(edges)
                          if isinstance(edges, list) and edges
                          else '')
                key = '%s|%s:%d%s' % (key, noun, len(atoms),
                                       suffix)
                break
        picked = table.get(key)
        rule = 'shape-table' if picked else 'template-table'
        if picked is None:
            picked = (by_template.get(family) or {}).get(
                'template:%s' % template)
        feature = key
        if picked is None:
            raise ValueError(
                'no member of family %r is keyed to public shape' ' %r among %s' % (family, key, sorted(table)))
    if picked not in eligible:
        raise ValueError(
            'selected %r is not among the eligible methods'
            % (picked,))
    why = ['family=%s' % (family,),
           'rule=%s' % (rule,),
           'feature=%s' % (feature,),
           'scope[%s]=%s' % (picked, family)]
    for other in sorted(named):
        if other != picked:
            why.append('not-picked[%s]=%s'
                       % (other, family))
    return {'action': {'kind': 'use_method',
                     'target': task['task_id'],
                     'inputs': {'method_id': picked,
                                'max_queries': 4},
                     'evidence_refs': why,
                     'requested_resources': {'queries': 4}},
            'state': {'picked': picked, 'why': why}}
