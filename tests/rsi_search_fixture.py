"""Authored, bounded worlds for replay-mechanics tests."""

from __future__ import annotations

import copy

from rsi import search


def worlds() -> dict:
    frame = {"schema": "p06-frame/1", "visible": {
        "objective": "select a prepared opportunity",
        "menu": [{"opportunity_id": "easy"}, {"opportunity_id": "hard"}],
        "prefix": [], "limits": {"calls": 1},
    }, "starts": {
        "easy": {"investigation_id": "fixture-easy", "target_revision": 0,
                 "visible_input": {"task": "easy-task"}, "task": "easy-task",
                 "genome": "g1", "model": "fixture", "method": None,
                 "runtime": {"execution_version": "worker-v1",
                             "verifier_execution_version": "verifier-v1"},
                 "evaluator_version": "test-v1", "limits": {"cpu": 3}},
        "hard": {"investigation_id": "fixture-hard", "target_revision": 0,
                 "visible_input": {"task": "hard-task"}, "task": "hard-task",
                 "genome": "g1", "model": "fixture", "method": None,
                 "runtime": {"execution_version": "worker-v1",
                             "verifier_execution_version": "verifier-v1"},
                 "evaluator_version": "test-v1", "limits": {"cpu": 5}},
    }, "source": {"fixture": "authored"}}
    easy = {"schema": "p06-branch/1", "frame": "", "opportunity_id": "easy",
            "status": "supported", "outcome": "passed",
            "quality": {"passed": True, "verdict": "passed"},
            "actual": {"task": "easy-task", "genome": "g1", "model": "fixture",
                       "evaluator_version": "test-v1",
                       "runtime": {"execution_version": "worker-v1",
                                   "verifier_execution_version": "verifier-v1"}},
            "consumed_input": {"task": "easy-task"},
            "receipts": {"worker": [{"identity": "fixture-worker"}],
                         "verifier": [{"identity": "fixture-verifier"}]},
            "resources": {"worker": {"amount": 1}, "verifier": {"amount": 1}}}
    hard = copy.deepcopy(easy)
    hard.update({"opportunity_id": "hard", "outcome": "failed",
                 "quality": {"passed": False, "verdict": "failed"},
                 "consumed_input": {"task": "hard-task"},
                 "actual": {**easy["actual"], "task": "hard-task",
                            "runtime": dict(easy["actual"]["runtime"])}})
    frame_digest = search._digest(search._artifact_bytes(search.FRAME_SCOPE, "frame", frame))
    easy["frame"] = hard["frame"] = frame_digest
    easy_digest = search._digest(search._artifact_bytes(search.BRANCH_SCOPE, "branch", easy))
    hard_digest = search._digest(search._artifact_bytes(search.BRANCH_SCOPE, "branch", hard))
    return {"frame": frame, "frame_digest": frame_digest,
            "branches": {easy_digest: easy, hard_digest: hard},
            "branch_digests": {"easy": easy_digest, "hard": hard_digest}}


def bundle(selected: str = "easy") -> dict:
    items = worlds()
    branch_digest = items["branch_digests"][selected]
    branch = items["branches"][branch_digest]
    frame_digest = items["frame_digest"]
    request = {"interface": search.POLICY_INTERFACE, "value": items["frame"]["visible"],
               "files": {}, "context": {}}
    evaluation_id = "fixture-evaluation"
    operation_id = f"p06-policy-{evaluation_id}-0000"
    policy_output = {"value": {"action": "choose", "opportunity_id": selected},
                     "files": {}}
    output_raw = search._canonical(policy_output)
    output_manifest = {"kind": search.capability.CAPABILITY_SCOPE,
                       "operation_id": operation_id,
                       "files": [{"path": "result.json", "kind": "file",
                                  "size": len(output_raw),
                                  "digest": search._digest(output_raw)}]}
    output_digest = search._digest(search.artifacts.package_bytes(
        output_manifest, {"result.json": output_raw}, search.capability.CAPABILITY_SCOPE))
    result = {"frame": frame_digest, "branch": branch_digest,
              "request_digest": search._digest(search._canonical(request)),
              "selected": selected, "status": "choose",
              "operation_id": operation_id, "policy_result": policy_output["value"],
              "policy_output": policy_output,
              "branch_status": branch["status"], "outcome": branch["outcome"],
              "quality": branch["quality"],
              "continuation_query": None,
              "receipts": [{"receipt_identity": "fixture-policy-receipt",
                            "operation_id": operation_id,
                            "outcome": "success", "content": {"status": "completed"},
                            "provenance": "authored fixture"}],
              "resources": {"id": "fixture-policy-reservation",
                            "operation_id": operation_id,
                            "allocation_id": "fixture-screening-cpu",
                            "amount": 4, "state": "settled"},
              "operation": {"id": operation_id, "allocation_id": "fixture-screening-cpu",
                            "reservation_id": "fixture-policy-reservation",
                            "effect": "sandbox-exec", "actual_cost_present": True,
                            "actual_cost": None,
                            "execution_version": "fixture-policy-runtime-v1",
                            "settled": True, "dispatch_state": "observed",
                            "reconcile_state": "clear"},
              "invocation": {"seconds": 0.02, "output_digest": output_digest,
                             "execution_version": "fixture-policy-runtime-v1",
                             "status": "completed"}}
    branch_ids = list(items["branches"])
    frame_ids = [frame_digest]
    return {"evaluation_id": evaluation_id, "max_decisions": 1,
            "evaluation_decision": "p06-evaluation:" + evaluation_id,
            "policy": {"genome": "fixture-policy", "name": "explore",
                       "interface": search.POLICY_INTERFACE,
                       "method_digest": "fixture-method", "timeout_ms": 100,
                       "max_output_bytes": 1024},
            "allocation_id": "fixture-screening-cpu", "frames": frame_ids,
            "branches": branch_ids,
            "pinned_evaluation": {"genome": "fixture-policy", "name": "explore",
                                  "interface": search.POLICY_INTERFACE,
                                  "method_digest": "fixture-method",
                                  "timeout_ms": 100, "max_output_bytes": 1024,
                                  "frames": frame_ids, "branches": branch_ids,
                                  "allocation_id": "fixture-screening-cpu",
                                  "max_decisions": 1},
            "frame_artifacts": {frame_digest: items["frame"]},
            "branch_artifacts": items["branches"], "results": [result]}
