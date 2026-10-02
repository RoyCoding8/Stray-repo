from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import replace
from typing import Any

import httpx

from .config import GatewayConfig, Settings
from .gateway import (
    GatewayAdapter,
    GatewayError,
    GatewayErrorKind,
    GatewayRouteError,
    GatewayStatus,
    ModelRequest,
    ModelResponse,
    RouteContract,
    Usage,
)

CONTRACT = "settlement-gateway/http-chat-completions-v1"
RESPONSES_CONTRACT = "settlement-gateway/http-responses-v1"

APIS = ("chat", "responses")
_ROUTE_FIELDS = ("endpoint", "requested_model", "resolved_model", "provider", "tier")

_CANCELLATION_REQUESTED = "requested"
_CANCELLATION_WORKER_STOPPED = "worker_stopped"
_CANCELLATION_CONFIRMED = "confirmed"

_STATUS_ERRORS = {
    401: (GatewayErrorKind.AUTH, False),
    403: (GatewayErrorKind.AUTH, False),
    429: (GatewayErrorKind.RATE_LIMIT, True),
}


def _error(kind: GatewayErrorKind, message: str, retryable: bool, operation_id: str,
           usage: Usage | None = None, *, route_error: GatewayRouteError | None = None,
           response_received: bool = False, response_status: int | None = None,
           response_digest: str | None = None) -> GatewayError:
    return GatewayError(
        kind, message, retryable, operation_id, usage,
        response_received=response_received,
        response_status=response_status,
        response_digest=response_digest,
        route_error=route_error,
    )


def _with_response(error: GatewayError, status: int, digest: str) -> GatewayError:
    return replace(error, response_received=True, response_status=status,
                   response_digest=digest)


def _route_mapping(expected: dict[str, Any] | RouteContract) -> dict[str, Any]:
    return expected.as_dict() if isinstance(expected, RouteContract) else expected


def _route_contract(expected: dict[str, Any] | RouteContract | None) -> RouteContract | None:
    if expected is None:
        return None
    try:
        if isinstance(expected, RouteContract):
            return expected
        return RouteContract.from_mapping(expected)
    except ValueError:
        return None


_MISSING_USAGE = object()


def _usage_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _decode_usage(body: dict[str, Any], input_key: str, output_key: str,
                  operation_id: str) -> Usage | GatewayError:
    raw = body.get("usage", _MISSING_USAGE)
    if raw is _MISSING_USAGE:
        return Usage()
    if not isinstance(raw, dict):
        return _error(
            GatewayErrorKind.PROTOCOL, "gateway returned malformed usage", False,
            operation_id, Usage(),
        )
    input_tokens = _usage_int(raw.get(input_key))
    output_tokens = _usage_int(raw.get(output_key))
    charge_present = "charge_units" in raw
    charge_units = _usage_int(raw.get("charge_units"))
    scale_present = "charge_scale" in raw
    charge_scale = _usage_int(raw.get("charge_scale"))
    if charge_units is not None:
        charge_scale = 1000 if not scale_present else charge_scale
    billed_present = "billed" in raw
    billed_value = raw.get("billed")
    billed = billed_value if billed_present and isinstance(billed_value, bool) else None
    usage = Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        charge_units=charge_units,
        charge_scale=charge_scale,
        provider_enforced_ceiling=False,
        billed=billed,
    )
    if billed_present and not isinstance(billed_value, bool):
        return _error(
            GatewayErrorKind.PROTOCOL, "gateway returned malformed usage billing",
            False, operation_id, usage,
        )
    if input_tokens is None or output_tokens is None:
        return _error(
            GatewayErrorKind.PROTOCOL, "gateway returned malformed token usage", False,
            operation_id, usage,
        )
    if charge_present and charge_units is None:
        return _error(
            GatewayErrorKind.PROTOCOL, "gateway returned malformed usage charge", False,
            operation_id, usage,
        )
    if scale_present and charge_scale != 1000:
        detail = "gateway returned malformed usage charge"
        if isinstance(raw.get("charge_scale"), int) \
                and not isinstance(raw.get("charge_scale"), bool):
            detail = ("gateway quoted a non-canonical charge scale:"
                      " convert to milli-units before settling")
        return _error(GatewayErrorKind.PROTOCOL, detail, False, operation_id, usage)
    return usage


def _decode_error_usage(raw: bytes, input_key: str, output_key: str,
                        operation_id: str) -> Usage | GatewayError | None:
    try:
        body = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(body, dict) or "usage" not in body:
        return None
    return _decode_usage(body, input_key, output_key, operation_id)


def gateway_timeout_overrides() -> dict[str, int]:
    def ms(name: str, default: int) -> int:
        raw = os.environ.get(name, "")
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(f"{name}={raw!r} is not an integer")
        if value <= 0:
            raise ValueError(f"{name}={raw!r} must be a positive integer")
        return value

    return {"timeout_connect_ms": ms("SETTLEMENT_GATEWAY_TIMEOUT_CONNECT_MS", 5_000),
            "timeout_read_ms": ms("SETTLEMENT_GATEWAY_TIMEOUT_READ_MS", 60_000),
            "timeout_total_ms": ms("SETTLEMENT_GATEWAY_TIMEOUT_TOTAL_MS", 300_000)}


def _responses_input(messages: tuple[dict[str, Any], ...]) -> Any:
    if len(messages) == 1 and isinstance(messages[0].get("content"), str):
        return messages[0]["content"]
    return [{"role": message.get("role", "user"), "content": message.get("content", "")}
            for message in messages]


def _free_tier(model: dict[str, Any]) -> str | None:
    explicit = model.get("tier")
    if isinstance(explicit, str) and explicit:
        return explicit
    pricing = model.get("pricing")
    if not isinstance(pricing, dict):
        return None
    values = []
    for key in ("prompt", "completion"):
        value = pricing.get(key)
        if isinstance(value, bool):
            return None
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            return None
    return "free" if values and all(value == 0 for value in values) else None


def _model_namespace(model_id: str) -> str | None:
    namespace, separator, _ = model_id.partition("/")
    return namespace.lower() if separator and namespace else None


def _catalog_free_signal(model: dict[str, Any], model_id: str) -> str | None:
    if "tier" in model:
        tier = model["tier"]
        if not isinstance(tier, str) or not tier:
            return "tier is malformed"
        if tier.lower() != "free":
            return "explicit paid tier"
        if "pricing" not in model:
            return "tier without pricing"
    if "pricing" in model:
        pricing = model["pricing"]
        if not isinstance(pricing, dict):
            return "pricing is malformed"
        if any(key not in pricing for key in ("prompt", "completion")):
            return "pricing incomplete"
        values = []
        for key in ("prompt", "completion"):
            value = pricing.get(key)
            if isinstance(value, bool):
                return "pricing is malformed"
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                return "pricing is malformed"
        if not all(value == 0 for value in values):
            return "explicit paid pricing"
        return "free"
    if model_id.endswith(":free"):
        return "free"
    return None


def _sanitized_catalog_entry(model: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {"id": model["id"]}
    for key in ("provider", "tier", "owned_by"):
        if isinstance(model.get(key), str):
            sanitized[key] = model[key]
    if "pricing" in model:
        pricing = model["pricing"]
        if isinstance(pricing, dict):
            sanitized["pricing"] = {
                key: pricing[key]
                for key in ("prompt", "completion")
                if key in pricing and isinstance(
                    pricing[key], (str, int, float, bool))
            }
        else:
            sanitized["pricing"] = None
    return sanitized


def reconcile_model_route(body: Any, expected: dict[str, Any] | RouteContract) -> dict[str, Any]:
    presence = {"requested_model": False, "resolved_model": False}
    expected = _route_mapping(expected)
    if not isinstance(expected, dict):
        return _route_reconciliation(
            presence, [], "expected route must be an object")
    if any(not isinstance(expected.get(key), str) or not expected[key]
           for key in _ROUTE_FIELDS):
        return _route_reconciliation(
            presence, [], "expected route is incomplete")
    if expected["tier"].lower() != "free":
        return _route_reconciliation(
            presence, [], "expected route tier is not free")
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        return _route_reconciliation(
            presence, [], "model list is malformed")
    model_entries = [entry for entry in body["data"]
                     if isinstance(entry, dict)
                     and isinstance(entry.get("id"), str)]
    exact_ids = {
        "requested_model": expected["requested_model"],
        "resolved_model": expected["resolved_model"],
    }
    entries_by_id: dict[str, list[dict[str, Any]]] = {}
    for entry in model_entries:
        if entry["id"] in exact_ids.values():
            entries_by_id.setdefault(entry["id"], []).append(entry)
    relevant = sorted(
        (_sanitized_catalog_entry(entry) for entries in entries_by_id.values()
         for entry in entries),
        key=lambda entry: entry["id"],
    )
    for key, model_id in exact_ids.items():
        presence[key] = bool(entries_by_id.get(model_id))
    missing = [key for key, present in presence.items() if not present]
    if missing:
        return _route_reconciliation(
            presence, relevant,
            "model list is missing exact %s" % ", ".join(missing))
    for model_id, entries in entries_by_id.items():
        sanitized = [_sanitized_catalog_entry(entry) for entry in entries]
        if any(entry != sanitized[0] for entry in sanitized[1:]):
            return _route_reconciliation(
                presence, relevant,
                "model list has conflicting metadata for %s" % model_id)
    resolved_namespace = _model_namespace(expected["resolved_model"])
    if resolved_namespace != expected["provider"].lower():
        return _route_reconciliation(
            presence, relevant,
            "resolved model namespace does not match provider")
    for key, model_id in exact_ids.items():
        entry = entries_by_id[model_id][0]
        if "provider" in entry:
            provider = entry["provider"]
            if not isinstance(provider, str) or not provider:
                return _route_reconciliation(
                    presence, relevant, "explicit provider is malformed")
            if provider.lower() != expected["provider"].lower():
                return _route_reconciliation(
                    presence, relevant,
                    "explicit provider does not match resolved namespace")
        free_signal = _catalog_free_signal(entry, model_id)
        if free_signal != "free":
            return _route_reconciliation(
                presence, relevant,
                "model entry has no trustworthy free signal: %s"
                % (free_signal or "no signal"))
    return _route_reconciliation(
        presence, relevant, None,
        route={key: expected[key] for key in _ROUTE_FIELDS})


def _route_reconciliation(presence: dict[str, bool],
                          relevant_entries: list[dict[str, Any]],
                          reason: str | None,
                          route: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "catalog": {
            "exact_id_presence": dict(presence),
            "relevant_entries": list(relevant_entries),
        },
        "result": {
            "verdict": "accepted" if route is not None else "refused",
            "reason": reason,
            "route": route,
        },
    }


def validate_model_route(body: Any, expected: dict[str, Any] | RouteContract) -> dict[str, str]:
    reconciled = reconcile_model_route(body, expected)
    if reconciled["result"]["verdict"] != "accepted":
        raise ValueError(reconciled["result"]["reason"])
    return reconciled["result"]["route"]


def _returned_route(body: dict[str, Any]) -> dict[str, Any]:
    provider = body.get("provider")
    if not isinstance(provider, str) or not provider:
        provider = body.get("provider_id")
    tier = body.get("tier")
    if not isinstance(tier, str) or not tier:
        tier = _free_tier(body)
    return {"model": body.get("model", ""),
            "provider": provider if isinstance(provider, str) else None,
            "tier": tier if isinstance(tier, str) else None}


class HttpGatewayAdapter(GatewayAdapter):
    def __init__(
        self,
        endpoint: str,
        api_key: str = "",
        timeout_connect_ms: int = 5_000,
        timeout_read_ms: int = 60_000,
        timeout_write_ms: int | None = None,
        timeout_total_ms: int = 300_000,
        client: httpx.Client | None = None,
        api: str = "chat",
        expected_route: dict[str, Any] | RouteContract | None = None,
        route_mode: str = "free",
    ) -> None:
        if api not in APIS:
            raise ValueError(f"unknown gateway api {api!r}: expected one of {APIS}")
        if route_mode not in ("free", "paid"):
            raise ValueError(f"unknown gateway route mode {route_mode!r}: expected free or paid")
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.api = api
        self.route_mode = route_mode
        self.timeouts = {
            "connect": timeout_connect_ms / 1000,
            "read": timeout_read_ms / 1000,
            "write": (timeout_write_ms if timeout_write_ms is not None else timeout_connect_ms)
            / 1000,
            "pool": timeout_connect_ms / 1000,
        }
        self.total_s = timeout_total_ms / 1000
        self._client = client
        self.expected_route = (
            expected_route.as_dict() if isinstance(expected_route, RouteContract)
            else dict(expected_route) if expected_route is not None else None
        )
        self._route_contract = _route_contract(expected_route)
        self._cancelled: set[str] = set()
        self._cancel_stopped: set[str] = set()
        self._cancel_confirmed: set[str] = set()

    @classmethod
    def from_settings(cls, settings: Settings, api_key: str | None = None,
                      api: str | None = None,
                      expected_route: dict[str, Any] | RouteContract | None = None,
                      route_mode: str = "free",
                      ) -> "HttpGatewayAdapter":
        gateway: GatewayConfig = settings.gateway
        key = api_key if api_key is not None else os.environ.get(gateway.api_key_env, "")
        shape = api if api is not None else os.environ.get("SETTLEMENT_GATEWAY_API", "chat")
        return cls(
            endpoint=gateway.endpoint,
            api_key=key,
            timeout_connect_ms=gateway.timeout_connect_ms,
            timeout_read_ms=gateway.timeout_read_ms,
            timeout_total_ms=gateway.timeout_total_ms,
            api=shape,
            expected_route=expected_route,
            route_mode=route_mode,
        )

    @property
    def route_contract(self) -> RouteContract | None:
        return self._route_contract

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _http_timeout(self, budget_s: float) -> httpx.Timeout:
        capped = max(min(self.timeouts["read"], budget_s), 0.001)
        narrow = max(min(self.timeouts["connect"], budget_s), 0.001)
        return httpx.Timeout(
            connect=narrow,
            read=capped,
            write=narrow,
            pool=narrow,
        )

    def _client_for(self, timeout: httpx.Timeout) -> tuple[httpx.Client, bool]:
        if self._client is not None:
            return self._client, False
        return httpx.Client(timeout=timeout), True

    def _status_error(self, status: int, operation_id: str,
                      response_digest: str | None = None,
                      usage: Usage | None = None) -> GatewayError:
        if status in _STATUS_ERRORS:
            kind, retryable = _STATUS_ERRORS[status]
            return _error(
                kind, f"gateway refused request: http {status}", retryable,
                operation_id, usage, response_received=True, response_status=status,
                response_digest=response_digest,
            )
        return _error(
            GatewayErrorKind.TRANSPORT,
            f"gateway request failed: http {status}",
            status >= 500,
            operation_id, usage, response_received=True, response_status=status,
            response_digest=response_digest,
        )

    def check_discovery(self) -> GatewayStatus | GatewayError:
        if not self.endpoint:
            return _error(
                GatewayErrorKind.TRANSPORT, "gateway endpoint is not configured", False, "discovery"
            )
        try:
            timeout = self._http_timeout(self.total_s)
            client, owned = self._client_for(timeout)
            try:
                response = client.get(
                    f"{self.endpoint}/models", headers=self._headers(), timeout=timeout
                )
            finally:
                if owned:
                    client.close()
        except httpx.TimeoutException:
            return _error(
                GatewayErrorKind.TIMEOUT, "gateway discovery timed out", True, "discovery"
            )
        except httpx.HTTPError as exc:
            return _error(GatewayErrorKind.TRANSPORT, f"gateway unreachable: {exc}", True, "discovery")
        return GatewayStatus.REACHABLE

    def check_auth(self) -> GatewayStatus | GatewayError:
        if not self.endpoint:
            return _error(
                GatewayErrorKind.TRANSPORT, "gateway endpoint is not configured", False, "auth"
            )
        if not self.api_key:
            return _error(
                GatewayErrorKind.AUTH, "gateway credentials are not configured", False, "auth"
            )
        try:
            timeout = self._http_timeout(self.total_s)
            client, owned = self._client_for(timeout)
            try:
                response = client.get(
                    f"{self.endpoint}/models", headers=self._headers(), timeout=timeout
                )
            finally:
                if owned:
                    client.close()
        except httpx.TimeoutException:
            return _error(GatewayErrorKind.TIMEOUT, "gateway auth check timed out", True, "auth")
        except httpx.HTTPError as exc:
            return _error(GatewayErrorKind.TRANSPORT, f"gateway unreachable: {exc}", True, "auth")
        if response.status_code == 200:
            return GatewayStatus.AUTHENTICATED
        return self._status_error(
            response.status_code, "auth",
            hashlib.sha256(response.content).hexdigest())

    def discover_model_route(
        self, expected_route: dict[str, Any] | RouteContract,
    ) -> dict[str, Any]:
        expected_route = _route_mapping(expected_route)
        request_url = f"{self.endpoint}/models"
        base = {
            "request": {"method": "GET", "url": request_url},
            "response": {"status": None, "sha256": None, "model_count": 0},
        }

        def refused(reason: str,
                    response_record: dict[str, Any] | None = None
                    ) -> dict[str, Any]:
            return {
                **base,
                "response": response_record or base["response"],
                "catalog": {
                    "exact_id_presence": {
                        "requested_model": False,
                        "resolved_model": False,
                    },
                    "relevant_entries": [],
                },
                "result": {"verdict": "refused", "reason": reason, "route": None},
            }

        if not isinstance(expected_route, dict):
            return refused("expected route is malformed")
        if not self.api_key:
            return refused("gateway credentials are not configured")
        if self.endpoint != expected_route.get("endpoint"):
            return refused("gateway endpoint is not the frozen endpoint")
        try:
            timeout = self._http_timeout(self.total_s)
            client, owned = self._client_for(timeout)
            try:
                response = client.get(
                    request_url, headers=self._headers(), timeout=timeout)
            finally:
                if owned:
                    client.close()
        except httpx.TimeoutException:
            return refused("model discovery timed out")
        except httpx.HTTPError as exc:
            return refused("model discovery transport failed: %s" % exc)
        raw = response.content
        response_record = {
            "status": response.status_code,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "model_count": 0,
        }
        if response.status_code != 200:
            return refused(
                "model discovery failed: http %d" % response.status_code,
                response_record)
        try:
            body = json.loads(raw)
        except (TypeError, ValueError) as exc:
            return refused(
                "model discovery returned invalid JSON: %s" % exc,
                response_record)
        if isinstance(body, dict) and isinstance(body.get("data"), list):
            response_record["model_count"] = len(body["data"])
        reconciled = reconcile_model_route(body, expected_route)
        return {**base, "response": response_record, **reconciled}

    def preflight_route(
        self, expected_route: dict[str, Any] | RouteContract,
    ) -> dict[str, str] | GatewayError:
        expected_route = _route_mapping(expected_route)
        if not isinstance(expected_route, dict):
            return _error(GatewayErrorKind.PROTOCOL,
                          "expected route is malformed", False, "preflight")
        if not self.api_key:
            return _error(GatewayErrorKind.AUTH,
                          "gateway credentials are not configured", False,
                          "preflight")
        if self.endpoint != expected_route.get("endpoint"):
            return _error(GatewayErrorKind.PROTOCOL,
                          "gateway endpoint is not the frozen endpoint", False,
                          "preflight")
        try:
            timeout = self._http_timeout(self.total_s)
            client, owned = self._client_for(timeout)
            try:
                response = client.get(
                    f"{self.endpoint}/models", headers=self._headers(), timeout=timeout
                )
            finally:
                if owned:
                    client.close()
        except httpx.TimeoutException:
            return _error(GatewayErrorKind.TIMEOUT,
                          "model preflight timed out", True, "preflight")
        except httpx.HTTPError as exc:
            return _error(GatewayErrorKind.TRANSPORT,
                          f"model preflight transport failed: {exc}", True,
                          "preflight")
        response_digest = hashlib.sha256(response.content).hexdigest()
        if response.status_code != 200:
            return self._status_error(
                response.status_code, "preflight", response_digest)
        try:
            body = json.loads(response.content)
            return validate_model_route(body, expected_route)
        except (TypeError, ValueError) as exc:
            return _with_response(
                _error(GatewayErrorKind.PROTOCOL,
                       f"model preflight route refused: {exc}", False, "preflight"),
                response.status_code, response_digest,
            )

    def _cancelled_error(self, operation_id: str, *, worker_stopped: bool = True
                         ) -> GatewayError:
        if worker_stopped:
            self._cancel_stopped.add(operation_id)
        return _error(
            GatewayErrorKind.CANCELLED,
            "operation cancelled; external outcome unknown",
            False,
            operation_id,
        )

    def _response_meta(self, body: dict[str, Any], contract: str) -> dict[str, Any]:
        route = _returned_route(body)
        returned_endpoint = body.get("endpoint")
        meta = {"adapter": "http", "contract": contract,
                "response_received": True,
                "endpoint": self.endpoint, "request_endpoint": self.endpoint,
                "returned_endpoint": (
                    returned_endpoint if isinstance(returned_endpoint, str) else None
                ),
                "model": route["model"], "provider": route["provider"],
                "tier": route["tier"]}
        if self.expected_route is not None:
            expected = self.expected_route
            expected_complete = all(
                isinstance(expected.get(key), str) and expected[key]
                for key in _ROUTE_FIELDS
            )
            returned_endpoint_valid = (
                "endpoint" not in body or returned_endpoint == self.endpoint
            )
            if (not expected_complete
                    or self.endpoint != expected.get("endpoint")
                    or route["model"] != expected.get("resolved_model")
                    or route["provider"] != expected.get("provider")
                    or route["tier"] != expected.get("tier")
                    or not returned_endpoint_valid):
                meta["route_error"] = GatewayRouteError.RESPONSE_METADATA.value
        return meta

    def _pre_dispatch_route_error(self, request: ModelRequest) -> GatewayError | None:
        if self.expected_route is None:
            if self.route_mode == "paid":
                return None
            return _error(
                GatewayErrorKind.PROTOCOL, "expected free route is required", False,
                request.operation_id, route_error=GatewayRouteError.EXPECTED_ROUTE,
            )
        if self._route_contract is None:
            return _error(
                GatewayErrorKind.PROTOCOL, "expected route is incomplete", False,
                request.operation_id, route_error=GatewayRouteError.EXPECTED_ROUTE,
            )
        if self.route_mode == "free" and self._route_contract.tier.lower() != "free":
            return _error(
                GatewayErrorKind.PROTOCOL, "expected route tier is not free", False,
                request.operation_id, route_error=GatewayRouteError.EXPECTED_ROUTE,
            )
        if self.endpoint != self._route_contract.endpoint:
            return _error(
                GatewayErrorKind.PROTOCOL,
                "gateway endpoint is not the frozen endpoint", False,
                request.operation_id, route_error=GatewayRouteError.ENDPOINT,
            )
        if request.model != self._route_contract.requested_model:
            return _error(
                GatewayErrorKind.PROTOCOL,
                "requested model is not the frozen model", False,
                request.operation_id, route_error=GatewayRouteError.REQUESTED_MODEL,
            )
        return None

    def infer(self, request: ModelRequest) -> ModelResponse | GatewayError:
        if request.operation_id in self._cancelled:
            return self._cancelled_error(request.operation_id, worker_stopped=False)
        if not self.endpoint:
            return _error(
                GatewayErrorKind.TRANSPORT,
                "gateway endpoint is not configured",
                False,
                request.operation_id,
            )
        route_error = self._pre_dispatch_route_error(request)
        if route_error is not None:
            return route_error
        budget_s = min(request.deadline_ms / 1000, self.total_s)
        if budget_s <= 0:
            return _error(
                GatewayErrorKind.TIMEOUT, "deadline already expired", False, request.operation_id
            )
        if self.api == "responses":
            url = f"{self.endpoint}/responses"
            payload = {
                "model": request.model,
                "input": _responses_input(request.messages),
                "max_output_tokens": request.max_output_tokens,
            }
            if request.reasoning_effort is not None:
                payload["reasoning"] = {"effort": request.reasoning_effort}
        else:
            if request.reasoning_effort is not None:
                return _error(
                    GatewayErrorKind.PROTOCOL,
                    "reasoning_effort needs the responses api", False,
                    request.operation_id,
                )
            url = f"{self.endpoint}/chat/completions"
            payload = {
                "model": request.model,
                "messages": list(request.messages),
                "max_tokens": request.max_output_tokens,
            }
        started = time.monotonic()
        deadline = started + budget_s
        timeout = self._http_timeout(budget_s)
        outcome: dict[str, Any] = {}
        finished = threading.Event()
        resigned = threading.Event()

        def _work() -> None:
            try:
                client, owned = self._client_for(timeout)
                try:
                    with client.stream(
                        "POST", url,
                        headers=self._headers(), json=payload, timeout=timeout,
                    ) as streamed:
                        if resigned.is_set() or request.operation_id in self._cancelled:
                            return
                        raw = bytearray()
                        for chunk in streamed.iter_raw():
                            raw += chunk
                            if request.operation_id in self._cancelled:
                                outcome["cancelled"] = True
                                return
                            if resigned.is_set() or time.monotonic() >= deadline:
                                outcome["expired"] = True
                                return
                        outcome["status"] = streamed.status_code
                        outcome["body"] = bytes(raw)
                finally:
                    if owned:
                        try:
                            client.close()
                        except httpx.HTTPError:
                            pass
            except httpx.TimeoutException:
                outcome["timeout"] = True
            except httpx.HTTPError as exc:
                outcome["transport"] = str(exc)
            except Exception as exc:
                outcome["raised"] = exc
            finally:
                finished.set()

        worker = threading.Thread(target=_work, daemon=True)
        worker.start()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if request.operation_id in self._cancelled:
                outcome["cancelled"] = True
                break
            finished.wait(timeout=min(0.05, remaining))
            if finished.is_set():
                break
        resigned.set()
        if "raised" in outcome:
            raise outcome["raised"]
        if "status" not in outcome:
            if request.operation_id in self._cancelled or outcome.get("cancelled"):
                return self._cancelled_error(request.operation_id)
            if outcome.get("timeout"):
                return _error(
                    GatewayErrorKind.TIMEOUT, "gateway request timed out", True,
                    request.operation_id,
                )
            if outcome.get("transport") is not None:
                return _error(
                    GatewayErrorKind.TRANSPORT,
                    f"gateway transport failed: {outcome['transport']}", True,
                    request.operation_id,
                )
            return _error(
                GatewayErrorKind.TIMEOUT, "total attempt deadline exceeded", True,
                request.operation_id,
            )
        if time.monotonic() >= deadline:
            return _error(
                GatewayErrorKind.TIMEOUT, "total attempt deadline exceeded", True,
                request.operation_id,
            )
        if request.operation_id in self._cancelled or outcome.get("cancelled"):
            return self._cancelled_error(request.operation_id)
        status = outcome["status"]
        body = outcome["body"]
        response_digest = hashlib.sha256(body).hexdigest()
        if status != 200:
            decoded_usage = _decode_error_usage(
                body,
                "prompt_tokens" if self.api == "chat" else "input_tokens",
                "completion_tokens" if self.api == "chat" else "output_tokens",
                request.operation_id,
            )
            if isinstance(decoded_usage, GatewayError):
                return _with_response(decoded_usage, status, response_digest)
            return self._status_error(
                status, request.operation_id, response_digest, decoded_usage)
        if self.api == "responses":
            response = self._decode_responses_body(body, request.operation_id)
        else:
            response = self._decode_body(body, request.operation_id)
        if isinstance(response, GatewayError):
            return _with_response(response, status, response_digest)
        if isinstance(response, ModelResponse):
            route_error = response.model_meta.get("route_error")
            if route_error == GatewayRouteError.RESPONSE_METADATA.value:
                return _with_response(
                    _error(
                        GatewayErrorKind.PROTOCOL,
                        "gateway response route refused: returned route metadata mismatch",
                        False,
                        request.operation_id,
                        response.usage,
                        route_error=GatewayRouteError.RESPONSE_METADATA,
                    ),
                    status,
                    response_digest,
                )
        return response

    def _decode_body(self, raw: bytes, operation_id: str) -> ModelResponse | GatewayError:
        try:
            body: Any = json.loads(raw)
        except ValueError:
            return _error(
                GatewayErrorKind.PROTOCOL, "gateway returned non-JSON body", False, operation_id
            )
        if not isinstance(body, dict):
            return _error(
                GatewayErrorKind.PROTOCOL, "gateway returned malformed body", False, operation_id
            )
        choices = body.get("choices") or []
        first = choices[0] if choices else {}
        message = first.get("message") or {} if isinstance(first, dict) else {}
        text = message.get("content") if isinstance(message, dict) else None
        decoded_usage = _decode_usage(
            body, "prompt_tokens", "completion_tokens", operation_id)
        if isinstance(decoded_usage, GatewayError):
            return decoded_usage
        usage = decoded_usage
        if (isinstance(first, dict) and first.get("finish_reason") == "cancelled") \
                or body.get("cancelled") is True:
            self._cancel_confirmed.add(operation_id)
            return _error(
                GatewayErrorKind.CANCELLED, "gateway confirmed cancellation", False,
                operation_id, usage,
            )
        if not isinstance(text, str):
            return _error(
                GatewayErrorKind.PROTOCOL, "gateway response has no message content", False,
                operation_id, usage,
            )
        stop = first.get("finish_reason", "stop") if isinstance(first, dict) else "stop"
        return ModelResponse(
            operation_id=operation_id,
            text=text,
            model_meta=self._response_meta(body, CONTRACT),
            usage=usage,
            stop_reason=str(stop),
        )

    def _decode_responses_body(self, raw: bytes, operation_id: str) -> ModelResponse | GatewayError:
        try:
            body: Any = json.loads(raw)
        except ValueError:
            return _error(
                GatewayErrorKind.PROTOCOL, "gateway returned non-JSON body", False, operation_id
            )
        if not isinstance(body, dict):
            return _error(
                GatewayErrorKind.PROTOCOL, "gateway returned malformed body", False, operation_id
            )
        decoded_usage = _decode_usage(
            body, "input_tokens", "output_tokens", operation_id)
        if isinstance(decoded_usage, GatewayError):
            return decoded_usage
        usage = decoded_usage
        status = body.get("status", "")
        if status == "cancelled":
            self._cancel_confirmed.add(operation_id)
            return _error(
                GatewayErrorKind.CANCELLED, "gateway confirmed cancellation", False,
                operation_id, usage,
            )
        if status == "failed":
            error = body.get("error")
            detail = error.get("message") if isinstance(error, dict) else error
            return _error(
                GatewayErrorKind.PROTOCOL, f"gateway responses call failed: {detail}", False,
                operation_id, usage,
            )
        pieces: list[str] = []
        output = body.get("output") or []
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "message" or isinstance(item.get("text"), str):
                    for part in item.get("content") or []:
                        if not isinstance(part, dict):
                            continue
                        if isinstance(part.get("text"), str):
                            pieces.append(part["text"])
                        elif part.get("type") == "refusal" \
                                and isinstance(part.get("refusal"), str):
                            pieces.append(part["refusal"])
                    if isinstance(item.get("text"), str):
                        pieces.append(item["text"])
        text = "".join(pieces)
        if not text:
            return _error(
                GatewayErrorKind.PROTOCOL, "gateway responses output has no text", False,
                operation_id, usage,
            )
        if status == "completed":
            stop: str = "stop"
        elif status == "incomplete":
            reason = (body.get("incomplete_details") or {}).get("reason", "")
            stop = "length" if reason == "max_output_tokens" else f"incomplete-{reason}"
        else:
            stop = str(status) if status else "stop"
        return ModelResponse(
            operation_id=operation_id,
            text=text,
            model_meta=self._response_meta(body, RESPONSES_CONTRACT),
            usage=usage,
            stop_reason=stop,
        )

    def cancel(self, operation_id: str) -> bool:
        self._cancelled.add(operation_id)
        return True

    def cancel_status(self, operation_id: str) -> str:
        if operation_id in self._cancel_confirmed:
            return _CANCELLATION_CONFIRMED
        if operation_id in self._cancel_stopped:
            return _CANCELLATION_WORKER_STOPPED
        if operation_id in self._cancelled:
            return _CANCELLATION_REQUESTED
        return "unknown"
