def STEP(view, state):
    eligible = view['eligible_methods']
    if not eligible:
        raise ValueError('no eligible capability')
    return {'action': {'kind': 'use_method',
                     'target': view['task_content']['task_id'],
                     'inputs': {'method_id': eligible[0],
                                'max_queries': 4},
                     'evidence_refs': [],
                     'requested_resources': {'queries': 4}},
            'state': {'picked': eligible[0]}}
