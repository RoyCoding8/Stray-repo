"""A live construction proof carried end to end through the shipped path.

W0 asks for a real gateway probe before any large campaign, and for the
five ways a construction can fail to be told apart. The route being
reachable is already established; what this file settles is the part that
is not, which is whether the functions this repository actually ships
can carry a live Boolean construction and leave behind evidence that
reproduces its verdict with no network at all.

Everything here is a different claim from the route probe. The transport,
the prompt, the dispatch identity, the parser and the scorer are the ones
`live_construct` and `settlement.gateway_http` already own; this test
calls them and records what they returned. A test that reached the
gateway over its own socket would prove the gateway, not the code.

The live test spends one model call and is skipped without the route. The
other tests are the ones that keep the taxonomy honest, and they run
offline: each outcome is produced by a stub adapter that reuses the real
guard, and each is asserted to be distinguishable from the others. A
taxonomy whose branches collapse into one another is the failure this
file exists to catch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import live_construct as live
from settlement.gateway import (
    GatewayError,
    GatewayErrorKind,
    ModelRequest,
    ModelResponse,
    Usage,
)

ROUTE = live.OUTPUT_ROUTE
# Four legal specs that all predict zero. It parses; it is wrong. That
# difference is the whole reason the taxonomy has a task-result value.
ZERO_PROGRAM = json.dumps(
    {"specs": [{"const": 0, "mask": 0, "pair": None}] * 4})


class StubAdapter:
    """A gateway that answers without a network, over the real guard.

    The guard, the dispatch identity, the parser and the scorer are the
    shipped ones. Only the socket is replaced, which is what makes each
    taxonomy branch reachable without spending a call.
    """

    def __init__(self, response):
        self.response = response
        self.dispatches = 0

    def infer(self, request):
        self.dispatches += 1
        if isinstance(self.response, str):
            return ModelResponse(
                request.operation_id, self.response,
                {"adapter": "http", "model": ROUTE["resolved_model"],
                 "provider": ROUTE["provider"], "tier": ROUTE["tier"],
                 "endpoint": ROUTE["endpoint"]},
                Usage(input_tokens=900, output_tokens=48, charge_units=0,
                      charge_scale=1000, provider_enforced_ceiling=None,
                      billed=None),
                "stop")
        return self.response

    def check_discovery(self):
        return None

    def check_auth(self):
        return None

    def cancel(self, operation_id):
        return True


def run(tmp_path, response):
    """One preflight run under `tmp_path`, and the adapter that fed it."""
    gateway = StubAdapter(response)
    return gateway, live.preflight_run(tmp_path, gateway)


def test_the_five_required_failures_are_five_distinct_values(tmp_path):
    """The assignment's five failures cannot collapse into one another.

    Each response below is a different kind of bad news for a
    construction: the gateway refused, the send was lost, the body was
    blank, the bytes will not parse, and the bytes parse but solve
    nothing. Reporting one boolean for all five would make the run
    unreadable, so each is asserted against a literal value here.
    """
    cases = {
        "route-refusal": GatewayError(
            GatewayErrorKind.AUTH, "gateway refused request: http 401",
            False, "op", response_received=True, response_status=401),
        "transport-loss": GatewayError(
            GatewayErrorKind.TIMEOUT, "total attempt deadline exceeded",
            True, "op", response_received=False),
        "empty-content": "   \n  ",
        "invalid-program": "I would rather explain the rule in prose.",
        "poor-task-result": ZERO_PROGRAM,
    }
    for expected, response in cases.items():
        record = run(tmp_path / expected, response)[1]
        assert record["verdict"]["outcome"] == expected, (
            f"{expected} was reported as "
            f"{record['verdict']['outcome']!r}")


def test_constructed_means_solved_not_merely_parsed(tmp_path):
    """`constructed` means the program solved the task, not that it parsed.

    The all-zero program is a legal four-spec policy and parses cleanly.
    It scores 1/16 against a floor of 1.0, so the preflight has to call
    that a poor task result. A taxonomy that called any parseable
    program a construction would report this as a success and mean
    nothing by it.
    """
    record = run(tmp_path, ZERO_PROGRAM)[1]
    assert record["verdict"]["outcome"] == "poor-task-result"
    assert record["attempts"][0]["score"]["overall"] == 0.0625
    assert record["score_floor"] == 1.0


def test_a_pre_dispatch_refusal_is_not_a_route_refusal(tmp_path):
    """A guard that never sent is not a gateway that refused.

    The guard raises `LiveRefused` for a model that is not the pinned one
    and for a cost block, both before the wire. Reading either as
    `route-refusal` would charge a live provider with a refusal it never
    saw and would inflate the count of dispatches the study spent.
    """
    guard = live.LiveGuard(
        StubAdapter(ZERO_PROGRAM), pinned_model=ROUTE["requested_model"],
        ceiling=1, automatic_retries=0, expected_route=dict(ROUTE))
    _task, session = live._preflight_task()
    prompt = live.render_output_prompt(session.output_model_input(), [], 1)
    with pytest.raises(live.LiveRefused):
        guard.infer(
            ModelRequest(model="some/other-model",
                         messages=({"role": "user", "content": prompt},),
                         max_output_tokens=2048, deadline_ms=1000,
                         operation_id="pre-dispatch"),
            evidence={"arm": "P1"})
    assert guard.refusal_kind == "model"
    assert guard.spent_dispatches == 0


def test_one_run_spends_exactly_one_dispatch(tmp_path):
    """The preflight is one attempt, and the guard says so itself.

    `LiveGuard` counts the sends it exempted as well as the ones it did
    not, so this reads `spent_dispatches` rather than `dispatch_count`:
    the number under test is the currency the ceiling is enforced in.
    """
    gateway, record = run(tmp_path, ZERO_PROGRAM)
    assert gateway.dispatches == 1
    assert record["guard_status"]["dispatch_count"] == 1
    assert record["guard_status"]["spent_dispatch_count"] == 1
    assert record["guard_status"]["ceiling_reached"] is True


def test_the_prompt_and_identity_are_the_frozen_ones(tmp_path):
    """The preflight asks the frozen question under the frozen identity.

    A preflight that rendered its own prompt or pinned its own model
    would test a second construction protocol. The prompt compared here
    is the one `render_output_prompt` produces from the frozen template,
    and the operation identity is the one the shipped
    `output_operation_id` builds from the run identity.
    """
    seen = {}
    gateway = StubAdapter(ZERO_PROGRAM)
    answer = gateway.infer

    def capture(request):
        seen.update(model=request.model,
                    content=request.messages[0]["content"],
                    operation_id=request.operation_id)
        return answer(request)

    gateway.infer = capture
    record = live.preflight_run(tmp_path, gateway)

    task, session = live._preflight_task()
    assert seen["model"] == ROUTE["requested_model"]
    assert seen["content"] == live.render_output_prompt(
        session.output_model_input(), [], 1)
    assert seen["operation_id"] == live.preflight_operation_id("P1", 1)
    assert record["task_id"] == task["task_id"]
    assert record["route"] == ROUTE
    assert record["protocol"] == live.OUTPUT_PROTOCOL_ID


def test_the_run_record_reproduces_its_verdict_with_no_network(
        tmp_path, monkeypatch):
    """Re-reading the written record is the proof, and it is offline.

    The transport is withdrawn: any dispatch raises. The record still has
    to recompute the same taxonomy value from the raw response, its
    digest and the dispatch evidence, which is the only thing that makes
    the evidence worth keeping.
    """
    record = run(tmp_path, ZERO_PROGRAM)[1]
    on_disk = json.loads((tmp_path / "preflight.json").read_text())

    def withdrawn(*args, **kwargs):
        raise AssertionError("re-verification reached the network")

    monkeypatch.setattr(live.LiveGuard, "infer", withdrawn)
    recomputed = live.verify_preflight_record(on_disk)
    assert recomputed["outcome"] == record["verdict"]["outcome"]
    assert recomputed["response_digest"] == on_disk["verdict"][
        "response_digest"]
    assert recomputed["recomputable"] is True


def test_a_tampered_response_is_refused_not_re_verified(tmp_path):
    """Swapping the bytes must break the record, not pass it quietly.

    The digest is what ties the raw response to the dispatch the guard
    recorded. A hand-edited response with a stale digest that recomputed
    clean would make the evidence attest to bytes no provider sent.
    """
    run(tmp_path, ZERO_PROGRAM)
    on_disk = json.loads((tmp_path / "preflight.json").read_text())
    on_disk["attempts"][0]["raw_response"] = json.dumps(
        {"specs": [{"const": 1, "mask": 15, "pair": None}] * 4})
    with pytest.raises(live.LiveRefused, match="does not match"):
        live.verify_preflight_record(on_disk)


def test_a_record_cannot_claim_a_program_that_does_not_parse(tmp_path):
    """`invalid-program` must be re-derived, not taken on trust.

    Otherwise a hand-written record could call arbitrary bytes an
    invalid program, and the taxonomy value would carry no claim at all.
    """
    run(tmp_path, "I would rather explain the rule in prose.")
    on_disk = json.loads((tmp_path / "preflight.json").read_text())
    assert on_disk["verdict"]["outcome"] == "invalid-program"

    on_disk["attempts"][0]["raw_response"] = ZERO_PROGRAM
    with pytest.raises(live.LiveRefused, match="does not match"):
        live.verify_preflight_record(on_disk)


def test_the_live_route_carries_one_construction_end_to_end(tmp_path):
    """One real call, through the shipped transport, into a written record.

    Skipped rather than failed when the route is not configured: a
    missing gateway is a deployment fact, and this suite is not what
    settles that.

    The verdict is asserted, not admitted. This test used to assert
    that the outcome was a member of `PREFLIGHT_OUTCOMES`, and
    `route-refusal` is in that set, so it went green on the exact
    failure it exists to catch and stayed green through three
    repairs of that failure. A membership assertion cannot fail on a
    value the code itself chose, and this one had been green while the
    route it pinned refused every answer.

    So it asserts `constructed`, which is the only outcome that says
    the pipeline carried a live model into a scored program. If the
    route refuses, the gateway is unreachable, or the model writes
    something that will not solve the task, this is red and names
    which of those it was. The record is still printed so a reader
    learns the verdict rather than inferring it from a tick.

    The call is routed to `chat`, and that is not a workaround. The
    responses surface publishes no `provider`, so `_response_meta`
    refuses a correct answer on it after the tokens are spent;
    `test_w1_responses_route_contract.py` is the evidence that chat is
    the surface which can attest the frozen route.
    """
    import os

    from settlement.gateway_http import HttpGatewayAdapter

    endpoint = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT", "")
    if not endpoint:
        pytest.skip("SETTLEMENT_GATEWAY_ENDPOINT is not configured")
    key = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    if not key:
        pytest.skip("SETTLEMENT_GATEWAY_KEY is not configured")

    gateway = HttpGatewayAdapter(
        endpoint=endpoint, api_key=key, api="chat",
        expected_route=dict(ROUTE),
        timeout_read_ms=290_000, timeout_total_ms=300_000)
    live.preflight_run(tmp_path, gateway)
    on_disk = json.loads((tmp_path / "preflight.json").read_text())

    verdict = on_disk["verdict"]
    print(f"\nw1 live preflight: {verdict['outcome']} ({verdict['reason']})")
    assert verdict["outcome"] == "constructed", (
        "the pinned free route did not carry a live construction: "
        f"{verdict['outcome']} ({verdict['reason']})")
    assert verdict["requested_model"] == ROUTE["requested_model"]
    assert on_disk["guard_status"]["spent_dispatch_count"] == 1
    assert live.verify_preflight_record(on_disk)["outcome"] == \
        verdict["outcome"]


def test_one_free_signal_serves_both_halves_of_the_route_contract():
    """The two halves of the same contract must not disagree on `tier`.

    The route table in `gateway_http.py` already fixed this shape of
    defect once, for `provider`: one half folded case and the other did
    not, so a correct response was refused as `response_metadata` after
    the tokens were spent. `tier` had the identical split, and this test
    was a strict xfail pinned against it.

    The repair made the derivation one function, `_free_signal`, that
    both halves call, so the assertion is now a statement about the
    invariant rather than a marker for a known defect. It is no longer
    an xfail because there is nothing left to fail.
    """
    from settlement.gateway_http import _free_signal, _returned_route

    # The route-bearing fields of a real 200 from the free route, measured
    # 2026-09-29. `model` and `provider` are present; `tier` and
    # `pricing` are not.
    body = {"model": ROUTE["requested_model"], "provider": "Nvidia",
            "choices": [{"message": {"content": "OK"}}]}

    catalog = _free_signal(body, body["model"])
    assert catalog.refusal is None
    assert catalog.tier == "free"
    assert _returned_route(body)["tier"] == catalog.tier, (
        "the response half derives no free signal from a free model id")
    assert _returned_route(body)["tier"] == "free"


def test_only_tier_used_to_refuse_the_real_body_every_other_half_decoded_it():
    """Name the blast radius: the refusal was one field, not the path.

    Decoding the same body with the shipped decoder and feeding the
    result to the shipped parser both succeed. The construction path
    works; a single route field refused it after the tokens were spent.
    That is why the live result was a route refusal and not a claim
    about the model, and why the fix belonged in the tier derivation
    rather than in the construction path.

    Every other half still decodes it, and now so does the tier: the
    body is the one the live gateway returns, and the adapter carries it
    to a `ModelResponse` with no `route_error`.
    """
    from settlement.gateway_http import HttpGatewayAdapter

    body = json.dumps({
        "model": ROUTE["requested_model"], "provider": "Nvidia",
        "id": "gen-x", "object": "chat.completion", "service_tier": None,
        "choices": [{"index": 0, "message": {
            "role": "assistant", "content": ZERO_PROGRAM},
            "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 48}}).encode()

    adapter = HttpGatewayAdapter(endpoint=ROUTE["endpoint"],
                                 api_key="unused", api="chat")
    decoded = adapter._decode_body(body, "operation")
    assert not isinstance(decoded, GatewayError)
    assert decoded.text == ZERO_PROGRAM
    assert decoded.usage.input_tokens == 900
    assert decoded.usage.output_tokens == 48
    assert live.extract_and_validate_boolean(decoded.text) == json.loads(
        ZERO_PROGRAM)
    # `model` and `provider` both agree with the frozen contract, and the
    # `:free` model id is what carries the tier now that the two halves
    # share one derivation.
    assert decoded.model_meta["model"] == ROUTE["resolved_model"]
    assert decoded.model_meta["provider"] == "Nvidia"
    assert decoded.model_meta["tier"] == "free"
    assert "route_error" not in decoded.model_meta
