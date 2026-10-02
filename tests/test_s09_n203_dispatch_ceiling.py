"""N-203: the LiveGuard ceiling must count dispatches, not attempts.

A store-side refusal of a request is decided before any gateway contact, so
it spends nothing and must not consume ceiling. Today ``LiveGuard.infer``
advances ``dispatch_count`` before it calls the delegate, so a refused
prepare burns budget that was never spent and a campaign can be halted by
refusals it did not cause.

``delegate.infer`` is a single call that either returns a response or raises,
so a raised exception does not say which side of the gateway it failed on.
The guard therefore refuses to read one: the refund is driven by
``PreGatewayRefusal``, a marker the delegate raises, and the guard honours it
only for a bare raise out of ``infer`` -- never for a ``GatewayError``
response, which is the gateway having been contacted, and never for the
guard's own ceiling refusal, which never reaches the delegate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import live_construct as live
from settlement.gateway import GatewayError, GatewayErrorKind, ModelResponse, Usage


def _request(operation_id: str, model: str = "test-model"):
    from settlement.gateway import ModelRequest
    return ModelRequest(model=model,
                        messages=({"role": "user", "content": "hi"},),
                        max_output_tokens=4, deadline_ms=300_000,
                        operation_id=operation_id)


def _ok(request):
    return ModelResponse(request.operation_id, "ok", {"model": "test-model"},
                         Usage(input_tokens=1, output_tokens=1,
                               charge_units=0, billed=False), "stop")


class _PreGatewayRefusing:
    """Shaped like ``_DurableBrokerOutput``, marking its refused prepares."""

    def __init__(self, refuse=(), gateway_error=None):
        self.refuse = set(refuse)
        self.gateway_error = gateway_error
        self.reached_gateway: list[str] = []

    def infer(self, request):
        if request.operation_id in self.refuse:
            raise live.PreGatewayRefusal(
                "durable broker refused %s: budget exhausted" % request.operation_id)
        self.reached_gateway.append(request.operation_id)
        if self.gateway_error is not None:
            return self.gateway_error
        return _ok(request)

    def check_discovery(self):
        return "configured"

    def check_auth(self):
        return "authenticated"

    def cancel(self, operation_id):
        return True


def test_a_store_refusal_does_not_burn_the_ceiling():
    """Three dispatches' worth of ceiling must survive one store refusal."""
    delegate = _PreGatewayRefusing(refuse={"op-refused"})
    guard = live.LiveGuard(delegate, pinned_model="test-model", ceiling=3,
                           automatic_retries=0)

    with pytest.raises(live.PreGatewayRefusal):
        guard.infer(_request("op-refused"), evidence={"arm": "P1"})
    assert delegate.reached_gateway == []
    assert not guard.is_ceiling_reached(), (
        "the store refused before any gateway contact, so nothing was spent "
        "and the ceiling must not be spent either")

    for op in ("op-a", "op-b", "op-c"):
        assert guard.infer(_request(op), evidence={"arm": "P1"}) is not None

    assert delegate.reached_gateway == ["op-a", "op-b", "op-c"]
    assert guard.is_ceiling_reached()
    with pytest.raises(live.LiveRefused) as caught:
        guard.infer(_request("op-d"), evidence={"arm": "P1"})
    assert caught.value.reason == "study model-call ceiling 3 reached"
    assert delegate.reached_gateway == ["op-a", "op-b", "op-c"]


def test_the_attempt_ledger_still_records_the_refused_attempt():
    """The ceiling refund must not erase the attempt from the evidence.

    ``offline_recompute`` requires ``guard_status()["dispatch_count"]`` to
    equal the length of the dispatch ledger, so the attempt count stays
    attempt-shaped; the ceiling reads the spent count instead.
    """
    delegate = _PreGatewayRefusing(refuse={"op-refused"})
    guard = live.LiveGuard(delegate, pinned_model="test-model", ceiling=3,
                           automatic_retries=0)

    with pytest.raises(live.PreGatewayRefusal):
        guard.infer(_request("op-refused"), evidence={"arm": "P1"})

    assert guard.dispatch_count == 1
    assert [entry["operation_id"] for entry in guard.ledger] == ["op-refused"]
    assert guard.guard_status()["spent_dispatch_count"] == 0


def test_a_gateway_error_does_not_refund_the_ceiling():
    """The gateway was contacted, so the attempt counts whatever it cost."""
    error = GatewayError(kind=GatewayErrorKind.TRANSPORT, message="reset by peer",
                         retryable=False, operation_id="op-a")
    delegate = _PreGatewayRefusing(gateway_error=error)
    guard = live.LiveGuard(delegate, pinned_model="test-model", ceiling=2,
                           automatic_retries=0)

    for op in ("op-a", "op-b"):
        assert guard.infer(_request(op), evidence={"arm": "P1"}) is error

    assert guard.guard_status()["spent_dispatch_count"] == 2
    assert guard.is_ceiling_reached()
    with pytest.raises(live.LiveRefused) as caught:
        guard.infer(_request("op-c"), evidence={"arm": "P1"})
    assert caught.value.reason == "study model-call ceiling 2 reached"


def test_a_retry_after_a_gateway_error_does_not_refund_the_ceiling():
    error = GatewayError(kind=GatewayErrorKind.TRANSPORT, message="reset",
                         retryable=True, operation_id="op-a")
    delegate = _PreGatewayRefusing(gateway_error=error)
    guard = live.LiveGuard(delegate, pinned_model="test-model", ceiling=2,
                           automatic_retries=1)

    assert guard.infer(_request("op-a"), evidence={"arm": "P1"}) is error

    assert delegate.reached_gateway == ["op-a", "op-a"]
    assert guard.guard_status()["spent_dispatch_count"] == 2
    assert guard.is_ceiling_reached()


def test_ceiling_refusal_never_reaches_the_delegate():
    delegate = _PreGatewayRefusing()
    guard = live.LiveGuard(delegate, pinned_model="test-model", ceiling=0)

    with pytest.raises(live.LiveRefused) as caught:
        guard.infer(_request("op-a"), evidence={"arm": "P1"})
    assert caught.value.reason == "study model-call ceiling 0 reached"
    assert delegate.reached_gateway == []
    assert guard.dispatch_count == 0
    assert guard.guard_status()["spent_dispatch_count"] == 0


def test_already_spent_opens_as_a_spent_count_not_an_attempt_count():
    delegate = _PreGatewayRefusing()
    guard = live.LiveGuard(delegate, pinned_model="test-model", ceiling=3,
                           already_spent=1, automatic_retries=0)

    assert guard.dispatch_count == 1
    assert guard.guard_status()["spent_dispatch_count"] == 1
    assert not guard.is_ceiling_reached()
    guard.infer(_request("op-a"), evidence={"arm": "P1"})
    guard.infer(_request("op-b"), evidence={"arm": "P1"})
    assert guard.is_ceiling_reached()


def test_a_refused_prepare_is_exempt_from_the_ceiling():
    """CONTROL. Inverted from the pre-fix reading, per tests/test_s09_controls.py.

    ``_DurableBrokerOutput`` used to raise a bare ``RuntimeError`` for a
    refused prepare, indistinguishable from one raised after the gateway was
    contacted, so the guard could not refund it and the refusal burned
    ceiling. It now raises the marker, so the two are separable.
    """
    from scripts import invl02_live as driver

    class _BareRefusing:
        def __init__(self):
            self.reached_gateway: list[str] = []

        def infer(self, request):
            self.reached_gateway.append(request.operation_id)
            raise RuntimeError("durable broker refused %s: budget exhausted"
                               % request.operation_id)

    delegate = _BareRefusing()
    guard = live.LiveGuard(delegate, pinned_model="test-model", ceiling=2,
                           automatic_retries=0)

    for op in ("op-a", "op-b"):
        with pytest.raises(RuntimeError):
            guard.infer(_request(op), evidence={"arm": "P1"})

    assert guard.guard_status()["spent_dispatch_count"] == 2
    assert guard.is_ceiling_reached()
    assert hasattr(driver, "_DurableBrokerOutput")


def test_the_durable_delegate_exempts_a_refused_prepare_and_not_a_sent_one(
        monkeypatch):
    """The production refusal must be the marker, and nothing after the send.

    A refused prepare is decided with no gateway contact. A dispatch that was
    sent and came back unsettled is a few lines away in the same method;
    marking that one too would exempt a real send from the ceiling.
    """
    from scripts import invl02_live as driver
    from settlement import broker
    from settlement.common import ResultCode
    from types import SimpleNamespace

    def refused_prepare(*args, **kwargs):
        return SimpleNamespace(code=ResultCode.INSUFFICIENT_RESOURCES,
                               data={"reservation_id": None, "exposure": 0},
                               detail="allocation spent")

    def admits_prepare(*args, **kwargs):
        return SimpleNamespace(code=ResultCode.APPLIED,
                               data={"reservation_id": "res-1", "exposure": 11},
                               detail="")

    def send_then_fail(*args, **kwargs):
        raise RuntimeError("transport stopped")

    monkeypatch.setattr(broker, "ensure_operation", refused_prepare)
    guard = live.LiveGuard(
        driver._DurableBrokerOutput(
            "unused", _PreGatewayRefusing(), allocation_id="allocation-1",
            expected_route={}),
        pinned_model="test-model", ceiling=1, automatic_retries=0)
    with pytest.raises(live.PreGatewayRefusal, match="allocation spent"):
        guard.infer(_request("op-refused"), evidence={"arm": "P1"})
    assert guard.guard_status()["spent_dispatch_count"] == 0
    assert not guard.is_ceiling_reached()

    monkeypatch.setattr(broker, "ensure_operation", admits_prepare)
    monkeypatch.setattr(broker, "dispatch_operation", send_then_fail)
    sent = live.LiveGuard(
        driver._DurableBrokerOutput(
            "unused", _PreGatewayRefusing(), allocation_id="allocation-1",
            expected_route={}),
        pinned_model="test-model", ceiling=1, automatic_retries=0)
    with pytest.raises(RuntimeError, match="transport stopped"):
        sent.infer(_request("op-sent"), evidence={"arm": "P1"})
    assert sent.guard_status()["spent_dispatch_count"] == 1
    assert sent.is_ceiling_reached()


def test_the_marker_is_honoured_only_for_a_bare_raise():
    """The guard trusts the delegate's claim; it cannot see inside infer.

    A delegate that reaches the gateway and then raises the marker is still
    refunded, which is why the exemption is opt-in per delegate rather than
    inferred from the exception.
    """
    class _DeclinesAfterSend:
        def __init__(self):
            self.sent: list[str] = []

        def infer(self, request):
            self.sent.append(request.operation_id)
            raise live.PreGatewayRefusal("unsettled after send for %s"
                                         % request.operation_id)

    delegate = _DeclinesAfterSend()
    guard = live.LiveGuard(delegate, pinned_model="test-model", ceiling=2,
                           automatic_retries=0)

    for op in ("op-a", "op-b"):
        with pytest.raises(live.PreGatewayRefusal):
            guard.infer(_request(op), evidence={"arm": "P1"})

    assert delegate.sent == ["op-a", "op-b"]
    assert guard.guard_status()["spent_dispatch_count"] == 0
    assert not guard.is_ceiling_reached()
