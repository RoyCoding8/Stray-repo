from __future__ import annotations

import copy

import pytest
from rsi_search_fixture import bundle

from rsi import search


def _bundle(selected: str = "easy") -> dict:
    data = bundle(selected)
    data["results"][0]["invocation"]["method_digest"] = data["policy"]["method_digest"]
    return data


def test_offline_replay_recomputes_supported_outcome_and_screening_cost():
    baseline = _bundle()
    assert len(baseline["branches"]) == 2
    assert {baseline["branch_artifacts"][key]["frame"]
            for key in baseline["branches"]} == set(baseline["frames"])

    assert search.recompute(baseline) == {
        "supported": 1, "gaps": 0, "stops": 0, "refusals": 0,
        "passed": 1, "failed": 0, "screening_cpu_seconds": 0.02,
        "continuation_gaps": 0,
        "screening_cpu_seconds_unknown": 0, "screening_cpu_units": 4,
        "screening_cpu_units_known": 4, "screening_cpu_units_unknown": 0,
    }


def test_same_frame_corpus_supports_a_different_policy_choice():
    result = search.recompute(_bundle("hard"))

    assert (result["supported"], result["passed"], result["failed"], result["gaps"]) == (
        1, 0, 1, 0)


def test_eligible_choice_without_a_recorded_branch_is_a_charged_gap():
    data = _bundle()
    row = data["results"][0]
    hard_digest = next(digest for digest in data["branches"]
                       if data["branch_artifacts"][digest]["opportunity_id"] == "hard")
    row.update(selected="hard", branch=None, branch_status="gap", outcome=None, quality=None)
    _set_policy_output(row, {"action": "choose", "opportunity_id": "hard"})
    data["branches"].remove(hard_digest)
    data["branch_artifacts"].pop(hard_digest)
    data["pinned_evaluation"]["branches"] = data["branches"]

    result = search.recompute(data)
    assert (result["supported"], result["gaps"], result["passed"], result["failed"]) == (
        0, 1, 0, 0)
    assert result["screening_cpu_units"] == 4


def test_requested_child_query_is_gap_without_capture_provenance():
    data = _bundle()
    data["max_decisions"] = 2
    data["pinned_evaluation"]["max_decisions"] = 2
    row = data["results"][0]
    row["continuation_query"] = {
        "status": "gap", "reason": "recorded child frame is missing"}
    # An untrusted frame claim in an authored branch is not capture evidence.
    data["branch_artifacts"][row["branch"]]["child_frame"] = "f" * 64
    old = row["branch"]
    branch = data["branch_artifacts"].pop(old)
    new = search._digest(search._artifact_bytes(search.BRANCH_SCOPE, "branch", branch))
    data["branch_artifacts"][new] = branch
    data["branches"] = [new if item == old else item for item in data["branches"]]
    data["pinned_evaluation"]["branches"] = data["branches"]
    row["branch"] = new

    result = search.recompute(data)
    assert (result["supported"], result["gaps"], result["continuation_gaps"]) == (1, 1, 1)


@pytest.mark.parametrize("mutation", ["unexecuted", "missing-child", "input",
                                       "worker", "runtime", "future"])
def test_offline_replay_counts_unsupported_or_forged_support_as_gap(mutation):
    baseline = _bundle()
    assert search.recompute(baseline)["supported"] == 1
    changed = copy.deepcopy(baseline)
    row = changed["results"][0]
    branch = changed["branch_artifacts"][row["branch"]]
    if mutation == "unexecuted":
        row.update({"branch_status": "gap", "outcome": None, "quality": None})
        branch.update({"status": "gap", "outcome": None, "quality": None})
    elif mutation == "missing-child":
        branch.update({"status": "gap", "reason": "recorded child is missing"})
        row.update({"branch_status": "gap", "outcome": None, "quality": None})
    elif mutation == "input":
        branch["consumed_input"] = {"task": "changed-context"}
    elif mutation == "worker":
        branch["actual"]["model"] = "changed-worker"
    elif mutation == "runtime":
        branch["actual"]["runtime"]["execution_version"] = "changed-runtime"
    else:
        frame = changed["frame_artifacts"].pop(row["frame"])
        frame["visible"]["future_result"] = "secret"
        new_frame = search._digest(search._artifact_bytes(search.FRAME_SCOPE, "frame", frame))
        changed["frame_artifacts"][new_frame] = frame
        changed["frames"] = [new_frame if item == row["frame"] else item
                              for item in changed["frames"]]
        changed["pinned_evaluation"]["frames"] = changed["frames"]
        row["frame"] = new_frame
        replacements = {}
        new_docs = {}
        for digest in changed["branches"]:
            item = changed["branch_artifacts"].pop(digest)
            item["frame"] = new_frame
            replacement = search._digest(search._artifact_bytes(
                search.BRANCH_SCOPE, "branch", item))
            replacements[digest] = replacement
            new_docs[replacement] = item
        changed["branches"] = [replacements[item] for item in changed["branches"]]
        changed["branch_artifacts"].update(new_docs)
        changed["pinned_evaluation"]["branches"] = changed["branches"]
        row["branch"] = replacements[row["branch"]]
    if mutation != "future":
        old_branch_digest = row["branch"]
        changed["branch_artifacts"].pop(old_branch_digest)
        new_branch = search._digest(search._artifact_bytes(search.BRANCH_SCOPE, "branch", branch))
        changed["branch_artifacts"][new_branch] = branch
        changed["branches"] = [new_branch if item == old_branch_digest else item
                                for item in changed["branches"]]
        changed["pinned_evaluation"]["branches"] = changed["branches"]
        row["branch"] = new_branch

    assert search.recompute(changed)["supported"] == 0
    assert search.recompute(changed)["gaps"] == 1


@pytest.mark.parametrize("mutation", ["missing-receipt", "changed-receipt",
                                       "changed-operation", "changed-method",
                                       "changed-execution"])
def test_policy_effect_evidence_is_required_for_supported_replay(mutation):
    changed = _bundle()
    row = changed["results"][0]
    if mutation == "missing-receipt":
        row["receipts"] = []
    elif mutation == "changed-receipt":
        row["receipts"][0]["operation_id"] = "different-operation"
    elif mutation == "changed-operation":
        row["operation"]["id"] = "different-operation"
    elif mutation == "changed-method":
        row["invocation"]["method_digest"] = "another-closure"
    else:
        row["invocation"]["execution_version"] = "another-runtime"

    result = search.recompute(changed)
    assert result["supported"] == 0
    assert result["gaps"] == 1


def test_offline_replay_does_not_relabel_an_executed_policy():
    baseline = _bundle()
    assert search.recompute(baseline)["supported"] == 1
    changed = copy.deepcopy(baseline)
    for identity in (changed["policy"], changed["pinned_evaluation"]):
        identity.update(genome="another-policy", name="another-method",
                        method_digest="another-closure")

    result = search.recompute(changed)

    assert (result["supported"], result["gaps"]) == (0, 1)
    assert result["screening_cpu_units"] == 4


def _set_policy_output(row, value):
    output = {"value": value, "files": {}}
    raw = search._canonical(output)
    manifest = {"kind": search.capability.CAPABILITY_SCOPE,
                "operation_id": row["operation_id"],
                "files": [{"path": "result.json", "kind": "file", "size": len(raw),
                           "digest": search._digest(raw)}]}
    row["policy_output"] = output
    row["policy_result"] = value
    row["invocation"]["output_digest"] = search._digest(search.artifacts.package_bytes(
        manifest, {"result.json": raw}, search.capability.CAPABILITY_SCOPE))


def test_screening_cost_includes_deliberate_stop():
    data = _bundle()
    row = data["results"][0]
    row.update(status="stop", selected=None, reason="all remaining work exceeds budget",
               branch=None, branch_status=None, outcome=None, quality=None)
    _set_policy_output(row, {"action": "stop", "reason": row["reason"]})

    assert search.recompute(data) == {
        "supported": 0, "gaps": 0, "stops": 1, "refusals": 0,
        "passed": 0, "failed": 0, "screening_cpu_seconds": 0.02,
        "continuation_gaps": 0,
        "screening_cpu_seconds_unknown": 0, "screening_cpu_units": 4,
        "screening_cpu_units_known": 4, "screening_cpu_units_unknown": 0,
    }


def test_screening_cost_includes_refusal_and_unknown_reservation_is_not_zero():
    data = _bundle()
    row = data["results"][0]
    row.update(status="refused", selected=None, reason="choice is malformed",
               branch=None, branch_status=None, outcome=None, quality=None)
    _set_policy_output(row, {"action": "maybe"})
    row["resources"] = None

    result = search.recompute(data)
    assert (result["refusals"], result["supported"], result["gaps"]) == (1, 0, 0)
    assert result["screening_cpu_seconds"] == 0.02
    assert result["screening_cpu_units"] is None
    assert result["screening_cpu_units_known"] == 0
    assert result["screening_cpu_units_unknown"] == 1


def test_screening_cost_uses_actual_settled_charge_when_present():
    data = _bundle()
    data["results"][0]["operation"]["actual_cost"] = 2

    result = search.recompute(data)
    assert result["supported"] == 1
    assert result["screening_cpu_units"] == 2
    assert result["screening_cpu_units_known"] == 2


def test_infeasible_actual_charge_gaps_and_marks_cost_unknown():
    data = _bundle()
    data["results"][0]["operation"]["actual_cost"] = 5

    result = search.recompute(data)
    assert result["supported"] == 0
    assert result["gaps"] == 1
    assert result["screening_cpu_units"] is None
    assert result["screening_cpu_units_unknown"] == 1
