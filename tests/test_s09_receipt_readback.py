"""Which receipt does the post-restart binding actually attest?

N-54 reported that `live_construct.py:976-980` reads `receipts[0]` and
therefore reads a fenced `unknown` ahead of a reconciled decision, because
`store.operation_receipts` orders by `(created_at, receipt_identity)` and
`fenced:` sorts before `reconciled:`.

That mechanism is not reachable at this site, and the tests below say so
against the boundary rather than by argument.

`probe["receipts"]` is not a store read. `drive_improve_round` builds the
list by appending `stepped["receipt"]` as it walks the three improve steps
(`improve_channel.py:1148-1149`). Every element is a
`child-execution` evidence record minted by `_step_evidence`
(`method_exec.py:682-709`), and a store receipt row cannot pass for one:
`frontier.validate_evidence_record` refuses a bare
`{receipt_identity, outcome, content}` row as incomplete.

The defect that IS at this line is a different one and it is real. A round
runs probe, construct, construct, so the list holds three receipts, and
position 0 is the step-0 probe. The candidate that
`record_revision_receipt` is about to certify was built by the step-1
construct. The binding therefore stores a child receipt attesting a
`probe` as the execution evidence for a package that a `construct`
produced. `test_1` is red against the current code and green after the fix.

Each test names what makes it fail. Every one was shown red by breaking the
behaviour deliberately and restoring afterwards.
"""

from __future__ import annotations

import json

import pytest

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import frontier as _frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live

from settlement.gateway import ModelRequest, ModelResponse, Usage

# The charter shape `ensure_live_store` accepts, as a fixture. It was a
# production helper with no production caller, deleted in 8d354a5.
from conftest import live_mission


def _acquired_store(tmp_path):
    """A store holding one retained, acquired, model-sourced package.

    The package is acquired through the real acquisition boundary: a stub
    gateway returns a model response, the response is parsed into a
    package, and the package is retained against its dispatch evidence.
    """
    store = live.ensure_live_store(
        tmp_path / "store.json",
        live_mission(live.LIVE_MISSION_OBJECTIVE,
                          [{"instrument": "boolean-rule-v1",
                            "split": "dev", "seed": 4}]),
        dict(live.LIVE_AUTHORITY))
    live.propose_live_work(store, [{
        "opportunity_id": "opp-first",
        "mission_link": live.LIVE_MISSION_OBJECTIVE,
        "question": "what does input 3 reveal",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004", "inputs": {"x": 3}},
        "resources": {"queries": 1, "steps": 1}}])
    base = channel.make_control("low")
    store.bind_active(base)

    class Gateway:
        def infer(self, request):
            return ModelResponse(
                request.operation_id,
                json.dumps({"entry": channel.IMPROVE_LOW_SOURCE}),
                {}, Usage(), "stop")

    guard = live.LiveGuard(Gateway(), pinned_model="test-model", ceiling=1)
    operation_id = "op-acquired"
    raw_prompt = "construct an improver"
    response = guard.infer(ModelRequest(
        model="test-model",
        messages=({"role": "user", "content": raw_prompt},),
        max_output_tokens=8, deadline_ms=1000, operation_id=operation_id),
        evidence={"arm": "test", "task": "rule-dev-0004", "attempt": 1,
                  "raw_prompt": raw_prompt})
    dispatch = guard.provenance(operation_id)
    package = live.parse_and_build_live_package(
        dict(base), response.text, "acquired-test-r1", dispatch=dispatch)
    store.record_evidence(dispatch)
    dispatch = guard.finalize_evidence(
        operation_id, parse_outcome="accepted",
        accepted_candidate_digest=package["package_digest"],
        parsed_source_digest=package["imp_digest"],
        package_digest=package["package_digest"],
        parent_digest=package["parent_digest"], round_no=1)
    live.retain_acquired(store, package, dispatch)
    store.save()
    return store, package


def _attested_action(receipt):
    action = receipt["details"]["raw_payload"]["action"]
    return action["inputs"]["frontier_action"]


# ---------------------------------------------------------------------------
# 1. The binding certifies a receipt for the step that built the package.
# ---------------------------------------------------------------------------

def test_1_binding_certifies_the_receipt_of_the_step_that_built_the_package(
        tmp_path):
    """RED against the current code. The recorded receipt is the step-0 probe.

    `drive_improve_round` runs three steps: probe, construct, construct.
    `receipts[0]` is the probe. The package being bound was built by the
    step-1 construct. Certifying the probe makes the durable
    `post_restart` evidence attest a different action from the one that
    produced the package.

    Fails if the binding records any receipt whose attested frontier action
    is not the construct that staged the candidate. It goes green when the
    binding selects by the attested action rather than by position.
    """
    store, package = _acquired_store(tmp_path)
    result = live.bind_live_revision(
        str(store.path), dict(package), rules.make_task("dev", 4), "test")

    assert result["disposition"] == "bound"
    attested = _attested_action(live.restart_store(
        str(store.path)).accepted_revisions[-1]["receipt"])

    assert attested["kind"] == "construct", (
        "the post-restart receipt must attest the construct that produced "
        f"the bound package, not a {attested['kind']!r}: the binding reads "
        "receipts[0], which is the step-0 probe")
    assert attested["inputs"]["strategy"] in ("high", "low")


def test_2_the_receipts_list_holds_every_step_so_position_is_meaningless(
        tmp_path):
    """The precondition test_1 depends on, stated against the boundary.

    A three-step round yields three receipts in step order. Any consumer
    that reads one by index is choosing a step, not finding a receipt.
    """
    store = live.ensure_live_store(
        tmp_path / "store.json",
        live_mission(live.LIVE_MISSION_OBJECTIVE,
                          [{"instrument": "boolean-rule-v1",
                            "split": "dev", "seed": 4}]),
        dict(live.LIVE_AUTHORITY))
    store.bind_active(channel.make_control("low"))
    probe = live.run_live_improve_round(
        store, rules.make_task("dev", 4), store.active_package, 1)

    kinds = [_attested_action(r)["kind"] for r in probe["receipts"]]

    assert len(probe["receipts"]) == 3
    assert kinds == ["probe", "construct", "construct"]
    assert all(r["kind"] == "child-execution" for r in probe["receipts"])


# ---------------------------------------------------------------------------
# 3. A store receipt row cannot masquerade as a step receipt.
# ---------------------------------------------------------------------------

def test_3_a_fenced_store_row_is_not_a_step_receipt():
    """N-54's mechanism cannot reach this site, proven at the validator.

    `probe["receipts"]` holds child-execution evidence records, not rows
    from the receipts table. A fenced `unknown` row, the row N-54 expects
    to sort ahead of a decision, cannot be validated as one.

    Fails if `validate_evidence_record` ever accepts a receipts-table row as
    a child-execution record. It passes while the two shapes stay distinct,
    which is why N-54's site claim is wrong.
    """
    fenced = {"receipt_identity": "fenced:op-1:g2", "outcome": "unknown",
              "content": {"fenced": True, "admitted_generation": 1,
                          "current_generation": 2}}

    with pytest.raises(_frontier.Refused):
        _frontier.validate_evidence_record(
            fenced, kind="child-execution", outcome="success")

    with pytest.raises(_frontier.Refused):
        _frontier.validate_evidence_record(
            fenced, kind="child-execution", outcome="unknown")


def test_4_the_known_safe_sites_guard_on_count_not_on_order():
    """N-54 named three sites as safe. Verified rather than asserted.

    Each refuses a two-receipt state before it reads position 0, so a
    fenced `unknown` arriving first cannot be mistaken for a decision.
    Fails if any of the three drops its count guard.
    """
    import inspect

    from experiments.ad01 import assessment_profile, method_exec

    guards = {
        "assessment_profile._settled_model_response":
            inspect.getsource(assessment_profile._settled_model_response),
        "method_exec._durable_receipt":
            inspect.getsource(method_exec._durable_receipt),
    }
    for name, source in guards.items():
        head = source.index("receipts = store.operation_receipts") \
            if "receipts = store.operation_receipts" in source else None
        assert head is not None or "len(receipts) != 1" in source, (
            f"{name} lost its count guard")
        if head is not None:
            window = source[head:head + 200]
            assert "len(receipts) != 1" in window, (
                f"{name} reads position 0 without a count guard first")
            assert source.index("len(receipts) != 1") < source.index(
                "receipts[0]"), (
                f"{name} indexes receipts[0] before it counts them")

    # store.reconcile_operation guards the terminal-unknown resolution, the
    # only site in it that reads a position.
    from settlement import store as settlement_store
    reconcile = inspect.getsource(settlement_store.reconcile_operation)
    assert "len(receipt_rows) != 1 or receipts[0] != \"unknown\"" in reconcile
