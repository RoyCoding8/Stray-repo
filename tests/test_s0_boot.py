from __future__ import annotations

import json

import httpx
import pytest

from settlement import boot
from settlement.config import GatewayConfig, Settings
from settlement.gateway import GatewayStatus
from settlement.gateway_http import HttpGatewayAdapter

ENDPOINT = "http://gateway.test/v1"
ROUTE = {
    "endpoint": ENDPOINT,
    "requested_model": "vendor/request-model",
    "resolved_model": "vendor/resolved-model",
    "provider": "vendor",
    "tier": "free",
}


def _settings() -> Settings:
    return Settings(dsn="unused", gateway=GatewayConfig(endpoint=ENDPOINT))


def _ready_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("database", "artifacts", "sandbox", "interpreters"):
        monkeypatch.setattr(boot, f"check_{name}", lambda *_args, name=name: boot.DependencyStatus(
            name, True, True, True, True, "deterministic test"
        ))


def _adapter(
    models_body: object | None = None,
) -> tuple[HttpGatewayAdapter, list[httpx.Request]]:
    requests: list[httpx.Request] = []
    body = models_body if models_body is not None else {
        "data": [
            {"id": ROUTE["requested_model"], "pricing": {"prompt": 0, "completion": 0}},
            {"id": ROUTE["resolved_model"], "pricing": {"prompt": 0, "completion": 0}},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            raw = json.dumps(body).encode()
        else:
            raw = json.dumps({
                "endpoint": ENDPOINT,
                "model": ROUTE["resolved_model"],
                "provider": ROUTE["provider"],
                "tier": ROUTE["tier"],
                "choices": [{"message": {"content": "boot-ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }).encode()
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=ENDPOINT,
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        expected_route=ROUTE,
    )
    return adapter, requests


def test_boot_without_exercise_never_advertises_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ready_checks(monkeypatch)
    adapter, requests = _adapter()

    report = boot.validate(_settings(), gateway_adapter=adapter)

    gateway = {entry.name: entry for entry in report.entries}["gateway"]
    assert gateway.reachable is True
    assert gateway.authenticated is True
    assert gateway.exercised is False
    assert report.models_available is False
    assert "model-inference" not in report.available_operations
    assert [request.method for request in requests] == ["GET"]


def test_boot_exercises_inference_before_advertising_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ready_checks(monkeypatch)
    adapter, requests = _adapter()

    report = boot.validate(_settings(), gateway_adapter=adapter, exercise_gateway=True)

    gateway = {entry.name: entry for entry in report.entries}["gateway"]
    assert gateway.authenticated is True
    assert gateway.exercised is True
    assert report.models_available is True
    assert "model-inference" in report.available_operations
    assert [request.method for request in requests] == ["GET", "POST"]
    probe = json.loads(requests[-1].content)
    assert probe["model"] == ROUTE["requested_model"]
    assert probe["messages"] == [{"role": "user", "content": "Reply with boot-ok."}]
    assert probe["max_tokens"] == 4


def test_boot_rejects_invalid_models_body_without_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ready_checks(monkeypatch)
    adapter, requests = _adapter(models_body={"data": {}})

    report = boot.validate(_settings(), gateway_adapter=adapter, exercise_gateway=True)

    gateway = {entry.name: entry for entry in report.entries}["gateway"]
    assert gateway.exercised is False
    assert report.models_available is False
    assert "model-inference" not in report.available_operations
    assert [request.method for request in requests] == ["GET"]


def test_authentication_without_frozen_route_cannot_qualify_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ready_checks(monkeypatch)

    class AuthenticatedGateway:
        def __init__(self) -> None:
            self.infer_calls = 0

        def check_discovery(self):
            return GatewayStatus.REACHABLE

        def check_auth(self):
            return GatewayStatus.AUTHENTICATED

        def infer(self, _request):
            self.infer_calls += 1
            raise AssertionError("inference without a frozen route must not run")

        def cancel(self, _operation_id: str) -> bool:
            return False

    adapter = AuthenticatedGateway()
    report = boot.validate(_settings(), gateway_adapter=adapter, exercise_gateway=True)

    assert adapter.infer_calls == 0
    assert report.models_available is False
    assert "model-inference" not in report.available_operations


def test_fake_gateway_never_enables_live_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready_checks(monkeypatch)
    from settlement.gateway import FakeGatewayAdapter

    report = boot.validate(_settings(), gateway_adapter=FakeGatewayAdapter())

    assert report.models_available is False
    assert "model-inference" not in report.available_operations
    assert "simulated-demonstration" in report.available_operations
