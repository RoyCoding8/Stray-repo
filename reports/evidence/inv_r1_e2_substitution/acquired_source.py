def STEP(view, state):
    observations = view.get('observations', [])
    open_questions = view.get('open_questions', [])
    eligible_methods = view.get('eligible_methods', [])
    last_result = view.get('last_result')
    
    # Initialize state if needed
    if state is None:
        state = {'diagnostic_attempts': 0, 'tried_diagnostics': set()}
    
    # Check for policy-failed verdicts in recent observations
    policy_failed = any(
        obs.get('verdict') == 'policy-failed' 
        for obs in observations[-3:]  # Look at recent observations
    )
    
    # Check for other verdicts
    has_inconclusive = any(
        obs.get('verdict') == 'inconclusive' 
        for obs in observations[-3:]
    )
    has_supported = any(
        obs.get('verdict') == 'supported' 
        for obs in observations[-3:]
    )
    has_refuted = any(
        obs.get('verdict') == 'refuted' 
        for obs in observations[-3:]
    )
    
    # If we have open questions and eligible methods, use a method
    if open_questions and eligible_methods:
        return {
            'action': 'use_method',
            'state': {**state, 'last_action': 'use_method'}
        }
    
    # If we have open questions but no eligible methods, construct one
    if open_questions and not eligible_methods:
        return {
            'action': 'construct_method',
            'state': {**state, 'last_action': 'construct_method'}
        }
    
    # If policy failed recently, try a different diagnostic
    if policy_failed:
        tried = state.get('tried_diagnostics', set())
        # Simple strategy: alternate between different diagnostic types
        diagnostic_types = ['data_check', 'assumption_check', 'boundary_check', 'sanity_check']
        for d in diagnostic_types:
            if d not in tried:
                new_tried = tried | {d}
                return {
                    'action': 'diagnose',
                    'state': {**state, 'diagnostic_attempts': state['diagnostic_attempts'] + 1, 
                              'tried_diagnostics': new_tried, 'last_diagnostic': d}
                }
        # If all tried, request model
        return {
            'action': 'request_model',
            'state': {**state, 'last_action': 'request_model'}
        }
    
    # If inconclusive, try another diagnostic
    if has_inconclusive and state['diagnostic_attempts'] < 3:
        return {
            'action': 'diagnose',
            'state': {**state, 'diagnostic_attempts': state['diagnostic_attempts'] + 1}
        }
    
    # If supported or refuted, we might be done or need revision
    if has_supported or has_refuted:
        if open_questions:
            return {
                'action': 'propose_revision',
                'state': {**state, 'last_action': 'propose_revision'}
            }
        else:
            return {
                'action': 'stop',
                'state': {**state, 'last_action': 'stop'}
            }
    
    # Default: diagnose if we haven't done much yet
    if state['diagnostic_attempts'] < 2:
        return {
            'action': 'diagnose',
            'state': {**state, 'diagnostic_attempts': state['diagnostic_attempts'] + 1}
        }
    
    # Otherwise request model
    return {
        'action': 'request_model',
        'state': {**state, 'last_action': 'request_model'}
    }