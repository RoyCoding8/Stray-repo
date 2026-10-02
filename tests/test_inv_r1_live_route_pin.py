"""A live study must pin the route it is about to spend on.

`HttpGatewayAdapter` refuses every dispatch when `expected_route` is None
and the mode is not `paid`: `expected free route is required`. `inv01_study`
built its adapter through `from_settings` with no expected route, so a live
study dispatched three operations and recorded three `failure` receipts with
empty text, then exited 0. The test that would have caught this has been
failing on `assert len(rows) >= 1` ever since.

Exiting 0 on a study that spent nothing and learned nothing is the more
serious half. The study has a cap sheet and a freeze, so a route belongs in
them; a run that cannot prove it is on the free route has no reason to
dispatch at all.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from settlement.gateway import RouteContract
from settlement.gateway_http import HttpGatewayAdapter


def test_an_adapter_with_no_expected_route_refuses_every_dispatch():
    adapter = HttpGatewayAdapter(endpoint="http://127.0.0.1:9/v1",
                                 api_key="k", api="responses")
    from settlement.gateway import ModelRequest
    error = adapter._pre_dispatch_route_error(ModelRequest(
        model="m", messages=(), max_output_tokens=2048, deadline_ms=1000))

    assert error is not None
    assert "expected free route is required" in str(error.message)


def test_a_pinned_free_route_admits_the_dispatch():
    """A pinned free route admits a dispatch, on the surface that can attest it.

    Chat, and not responses. The frozen route names a `provider` and
    `route_matches` refuses a response that does not carry one; the
    responses surface publishes no `provider` at all, so a route pinned
    there is refused before the wire rather than after it. This test is
    about the pin admitting a dispatch, and it would have kept passing
    while `responses` was the pinned surface had the refusal been about
    the model rather than the surface. See
    `tests/test_w1_responses_route_contract.py`.
    """
    adapter = HttpGatewayAdapter(
        endpoint="http://127.0.0.1:9/v1", api_key="k", api="chat",
        expected_route=RouteContract(
            endpoint="http://127.0.0.1:9/v1", requested_model="m",
            resolved_model="m", provider="openrouter", tier="free"))
    from settlement.gateway import ModelRequest

    assert adapter._pre_dispatch_route_error(ModelRequest(
        model="m", messages=(), max_output_tokens=2048,
        deadline_ms=1000)) is None


def test_the_study_pins_a_route_instead_of_dispatching_without_one():
    from scripts import inv01_study

    assert hasattr(inv01_study, "_v1_expected_route")
    route = inv01_study._v1_expected_route(
        "http://127.0.0.1:9/v1", "nemotron", "nemotron", "openrouter", "free")

    assert RouteContract.from_mapping(route).tier == "free"


def test_a_pinned_route_must_name_the_model_the_study_asks_for(monkeypatch):
    """The requested model must match; the resolved one legitimately differs.

    The router serves `openrouter/nvidia/nemotron-...` and reports back
    `nvidia/nemotron-...`. A guard that required both fields to equal the
    study's model refused every real route, and the first live run then
    discarded a 579-token response because the pin guessed the resolution
    wrong. The requested field is the check; the resolved field only has to
    be a real string, since an empty one would make the adapter's response
    comparison vacuous.
    """
    from scripts import inv01_study

    monkeypatch.setenv(inv01_study.ROUTE_ENV, json.dumps({
        "endpoint": "http://127.0.0.1:9/v1",
        "requested_model": "nemotron", "resolved_model": "nvidia/nemotron",
        "provider": "Nvidia", "tier": "free"}))

    assert inv01_study._v1_route_from_env("nemotron")["resolved_model"] \
        == "nvidia/nemotron"

    monkeypatch.setenv(inv01_study.ROUTE_ENV, json.dumps({
        "endpoint": "http://127.0.0.1:9/v1",
        "requested_model": "something-else", "resolved_model": "nvidia/x",
        "provider": "Nvidia", "tier": "free"}))
    with pytest.raises(ValueError, match="pins requested="):
        inv01_study._v1_route_from_env("nemotron")

    monkeypatch.setenv(inv01_study.ROUTE_ENV, json.dumps({
        "endpoint": "http://127.0.0.1:9/v1",
        "requested_model": "nemotron", "resolved_model": "   ",
        "provider": "Nvidia", "tier": "free"}))
    with pytest.raises(ValueError, match="empty resolved model"):
        inv01_study._v1_route_from_env("nemotron")
