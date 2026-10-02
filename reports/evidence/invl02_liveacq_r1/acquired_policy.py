def STEP(view, state):
    # Initialize state if not present
    if state is None:
        state = {
            "diagnosed": [],
            "method_used": None,
            "steps": 0
        }
    
    # Increment step counter
    state["steps"] = state.get("steps", 0) + 1
    
    # Safety stop after too many steps
    if state["steps"] > 20:
        return {"action": {"kind": "stop", "target": "", "inputs": {}, "evidence_refs": [], "requested_resources": {}}, "state": state}
    
    # Get open questions
    open_questions = view.get("open_questions", [])
    
    # If there are open questions not yet diagnosed, diagnose the first one
    for i, q in enumerate(open_questions):
        if i not in state["diagnosed"]:
            state["diagnosed"].append(i)
            return {
                "action": {
                    "kind": "diagnose",
                    "target": q,
                    "inputs": {},
                    "evidence_refs": [],
                    "requested_resources": {}
                },
                "state": state
            }
    
    # If all questions diagnosed, check eligible methods
    eligible_methods = view.get("eligible_methods", [])
    if eligible_methods and state["method_used"] is None:
        # Use the first eligible method
        method_name = eligible_methods[0]
        state["method_used"] = method_name
        return {
            "action": {
                "kind": "use_method",
                "target": method_name,
                "inputs": {},
                "evidence_refs": [],
                "requested_resources": {}
            },
            "state": state
        }
    
    # If a method was used and we have a last_result, propose revision
    last_result = view.get("last_result")
    if last_result and state["method_used"] is not None:
        return {
            "action": {
                "kind": "propose_revision",
                "target": "solution",
                "inputs": {"content": str(last_result)},
                "evidence_refs": [],
                "requested_resources": {}
            },
            "state": state
        }
    
    # If no eligible methods, try to construct one based on task content
    if not eligible_methods and state.get("constructed", False) is False:
        state["constructed"] = True
        return {
            "action": {
                "kind": "construct_method",
                "target": "investigation_method",
                "inputs": {"description": "Method to investigate software issue"},
                "evidence_refs": [],
                "requested_resources": {}
            },
            "state": state
        }
    
    # Default: stop
    return {
        "action": {
            "kind": "stop",
            "target": "",
            "inputs": {},
            "evidence_refs": [],
            "requested_resources": {}
        },
        "state": state
    }