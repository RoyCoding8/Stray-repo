"""A pre-send refusal the broker could not tell from a lost response.

`broker._validate_model` (src/settlement/broker.py:81-87) accepts
`reasoning_effort` in a `low|medium|high` domain and carries it into the
cleaned payload. `HttpGatewayAdapter.infer` (src/settlement/gateway_http.py:822)
refuses that same value on a chat route with

    reasoning_effort needs the responses api

The two are not the same kind of thing, and the receipt is where that shows.
`_model_error_receipt` (src/settlement/broker.py:584) branches on
`route_error is not None and not response_received`, and only that branch
files `pre-send-route-refusal` / `failure` / `actual_cost=0`. The chat refusal
was built with no `route_error`, so it fell to the `else` and was recorded as
`lost-response` / `unknown` / `actual_cost=None` -- a dispatch that was refused
before a byte left the process, recorded as a send whose answer is missing.
That is the expensive direction to be wrong in: `unknown` is a liability the
study ceiling carries, and it is unrecoverable without a reconciliation pass.

The validator is not the party at fault. `ensure_operation` calls
`validate_effect` (src/settlement/broker.py:271) with no adapter and no route,
and the same operation is legal on the responses surface, which every in-repo
producer of a `reasoning_effort` payload is already routed to. A validator that
refused the parameter would refuse work the responses route can do. The
disagreement is resolved where the route lives: the refusal now carries
`GatewayRouteError.REASONING_EFFORT`, the same typed marker every other
pre-send route refusal uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REFUSAL = "reasoning_effort needs the responses api"


def _payload() -> dict:
    return {"model": "m", "messages": [{"role": "user", "content": "hi"}],
            "max_output_tokens": 64, "deadline_ms": 1000,
            "reasoning_effort": "low"}


def _request():
    from settlement.gateway import ModelRequest

    return ModelRequest(model="m", messages=({"role": "user", "content": "hi"},),
                        max_output_tokens=64, deadline_ms=1000,
                        operation_id="c17-offline", reasoning_effort="low")


def _adapter(api: str, endpoint: str):
    from settlement.gateway_http import HttpGatewayAdapter

    return HttpGatewayAdapter(endpoint=endpoint, api_key="x", api=api,
                              route_mode="paid")


def test_the_validator_admits_the_parameter_the_route_refuses() -> None:
    """The defect in one assertion pair: admitted here, refused there."""
    from settlement.broker import _validate_model

    admitted = _validate_model(_payload())

    assert admitted["reasoning_effort"] == "low"


def test_the_chat_route_refuses_it_without_contacting_the_gateway() -> None:
    """Endpoint is a closed port, so a `transport` failure would mean the
    request was built and sent. A `protocol` refusal means it never was.

    `route_error` is the load-bearing part: it is what tells the broker this
    refusal is not a lost answer."""
    from settlement.gateway import GatewayError, GatewayRouteError

    result = _adapter("chat", "http://127.0.0.1:1/v1").infer(_request())

    assert isinstance(result, GatewayError)
    assert result.message == REFUSAL
    assert result.retryable is False
    assert "protocol" in str(result.kind).lower()
    assert result.response_received is False
    assert result.route_error is GatewayRouteError.REASONING_EFFORT


def test_the_refusal_is_not_filed_as_a_lost_response() -> None:
    """The defect's actual cost. `_model_error_receipt` classifies on
    `route_error`, so a refusal without the marker is recorded as
    `lost-response` / `unknown` / `actual_cost=None`: a send that never
    happened, carried as a liability whose answer is missing."""
    from settlement.broker import _model_error_receipt

    refused = _adapter("chat", "http://127.0.0.1:1/v1").infer(_request())

    receipt, sent = _model_error_receipt("c17-offline", refused)

    assert receipt.content["response_class"] == "pre-send-route-refusal"
    assert receipt.outcome == "failure"
    assert receipt.actual_cost == 0
    assert sent is False
    assert receipt.content["route_error"] == "reasoning_effort"


def test_the_responses_route_accepts_the_same_request() -> None:
    """The surface that would resolve the disagreement is offered, and it takes
    the parameter. The transport failure is the expected outcome here: the
    point is that the request was built rather than refused, which is what the
    chat route refused to do."""
    from settlement.gateway import GatewayError

    result = _adapter("responses", "http://127.0.0.1:1/v1").infer(_request())

    assert isinstance(result, GatewayError)
    assert result.message != REFUSAL
    assert "protocol" not in str(result.kind).lower()


def test_the_validator_is_oblivious_to_the_route() -> None:
    """It is not a near-miss: the validator has no route in its signature and
    no api to consult, so it cannot be made correct by supplying one."""
    import inspect

    from settlement.broker import _validate_model

    assert list(inspect.signature(_validate_model).parameters) == ["p"]


def test_the_default_route_is_the_one_that_refuses_it() -> None:
    """Why this is a live hazard rather than a theoretical one."""
    import inspect

    from settlement.gateway_http import APIS, HttpGatewayAdapter

    default = inspect.signature(
        HttpGatewayAdapter.__init__).parameters["api"].default

    assert APIS == ("chat", "responses")
    assert default == "chat"


def test_the_producers_of_the_parameter_route_to_responses() -> None:
    """Why the validator must not refuse it. `team01` builds its own adapter
    and pins `api=API` with `API = "responses"`, and `construct.py` takes the
    adapter from its caller, which is a `from_settings(..., api="responses")`
    site. So the payload carrying `reasoning_effort` is routed to the surface
    that carries it, and refusing the parameter at admission would refuse work
    the repository already knows how to do."""
    team = (ROOT / "experiments/team01/live.py").read_text(encoding="utf-8")
    construct = (ROOT / "experiments/ad01/construct.py").read_text(
        encoding="utf-8")

    assert '"reasoning_effort"' in team
    assert 'API = "responses"' in team
    assert "api=API" in team
    assert '"reasoning_effort"' in construct
    assert "gateway: Any" in construct


def test_the_repository_never_constructs_a_messages_api_route() -> None:
    """Only two surfaces exist. `/v1/messages` is the gateway's third surface
    but `APIS` does not offer it, so the choice is binary."""
    from settlement.gateway_http import APIS

    assert "messages" not in APIS
