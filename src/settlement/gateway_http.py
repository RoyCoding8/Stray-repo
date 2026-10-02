from __future__ import annotations

import os
import time
from typing import Any

import httpx

from .config import GatewayConfig, Settings
from .gateway import (
    GatewayAdapter,
    GatewayError,
    GatewayErrorKind,
    GatewayStatus,
    ModelRequest,
    ModelResponse,
    Usage,
)

CONTRACT = "settlement-gateway/http-chat-completions-v1"

_CANCELLATION_REQUESTED = "requested"
_CANCELLATION_CONFIRMED = "confirmed"

_STATUS_ERRORS = {
    401: (GatewayErrorKind.AUTH, False),
    403: (GatewayErrorKind.AUTH, False),
    429: (GatewayErrorKind.RATE_LIMIT, True),
}


def _error(kind: GatewayErrorKind, message: str, retryable: bool, operation_id: str) -> GatewayError:
    return GatewayError(kind, message, retryable, operation_id)


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
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeouts = {
            "connect": timeout_connect_ms / 1000,
            "read": timeout_read_ms / 1000,
            "write": (timeout_write_ms if timeout_write_ms is not None else timeout_connect_ms)
            / 1000,
            "pool": timeout_connect_ms / 1000,
        }
        self.total_s = timeout_total_ms / 1000
        self._client = client
        self._cancelled: set[str] = set()
        self._cancel_confirmed: set[str] = set()

    @classmethod
    def from_settings(cls, settings: Settings, api_key: str | None = None) -> "HttpGatewayAdapter":
        gateway: GatewayConfig = settings.gateway
        key = api_key if api_key is not None else os.environ.get(gateway.api_key_env, "")
        return cls(
            endpoint=gateway.endpoint,
            api_key=key,
            timeout_connect_ms=gateway.timeout_connect_ms,
            timeout_read_ms=gateway.timeout_read_ms,
            timeout_total_ms=gateway.timeout_total_ms,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _http_timeout(self, budget_s: float) -> httpx.Timeout:
        capped = max(min(self.timeouts["read"], budget_s), 0.001)
        return httpx.Timeout(
            connect=self.timeouts["connect"],
            read=capped,
            write=self.timeouts["write"],
            pool=self.timeouts["pool"],
        )

    def _client_for(self, timeout: httpx.Timeout) -> tuple[httpx.Client, bool]:
        if self._client is not None:
            return self._client, False
        return httpx.Client(timeout=timeout), True

    def _status_error(self, status: int, operation_id: str) -> GatewayError:
        if status in _STATUS_ERRORS:
            kind, retryable = _STATUS_ERRORS[status]
            return _error(kind, f"gateway refused request: http {status}", retryable, operation_id)
        return _error(
            GatewayErrorKind.TRANSPORT,
            f"gateway request failed: http {status}",
            status >= 500,
            operation_id,
        )

    def check_discovery(self) -> GatewayStatus | GatewayError:
        if not self.endpoint:
            return _error(
                GatewayErrorKind.TRANSPORT, "gateway endpoint is not configured", False, "discovery"
            )
        try:
            client, owned = self._client_for(self._http_timeout(self.total_s))
            try:
                response = client.get(f"{self.endpoint}/models", headers=self._headers())
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
            client, owned = self._client_for(self._http_timeout(self.total_s))
            try:
                response = client.get(f"{self.endpoint}/models", headers=self._headers())
            finally:
                if owned:
                    client.close()
        except httpx.TimeoutException:
            return _error(GatewayErrorKind.TIMEOUT, "gateway auth check timed out", True, "auth")
        except httpx.HTTPError as exc:
            return _error(GatewayErrorKind.TRANSPORT, f"gateway unreachable: {exc}", True, "auth")
        if response.status_code == 200:
            return GatewayStatus.AUTHENTICATED
        return self._status_error(response.status_code, "auth")

    def infer(self, request: ModelRequest) -> ModelResponse | GatewayError:
        if request.operation_id in self._cancelled:
            self._cancel_confirmed.add(request.operation_id)
            return _error(
                GatewayErrorKind.CANCELLED, "operation cancelled before send", False,
                request.operation_id,
            )
        if not self.endpoint:
            return _error(
                GatewayErrorKind.TRANSPORT,
                "gateway endpoint is not configured",
                False,
                request.operation_id,
            )
        budget_s = min(request.deadline_ms / 1000, self.total_s)
        if budget_s <= 0:
            return _error(
                GatewayErrorKind.TIMEOUT, "deadline already expired", False, request.operation_id
            )
        payload = {
            "model": request.model,
            "messages": list(request.messages),
            "max_tokens": request.max_output_tokens,
        }
        started = time.monotonic()
        try:
            client, owned = self._client_for(self._http_timeout(budget_s))
            try:
                response = client.post(
                    f"{self.endpoint}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
            finally:
                if owned:
                    client.close()
        except httpx.TimeoutException:
            return _error(
                GatewayErrorKind.TIMEOUT, "gateway request timed out", True, request.operation_id
            )
        except httpx.HTTPError as exc:
            return _error(
                GatewayErrorKind.TRANSPORT, f"gateway transport failed: {exc}", True,
                request.operation_id,
            )
        if time.monotonic() - started > budget_s:
            return _error(
                GatewayErrorKind.TIMEOUT, "total attempt deadline exceeded", True,
                request.operation_id,
            )
        if request.operation_id in self._cancelled:
            self._cancel_confirmed.add(request.operation_id)
            return _error(
                GatewayErrorKind.CANCELLED,
                "operation cancelled; external outcome unknown",
                False,
                request.operation_id,
            )
        if response.status_code != 200:
            return self._status_error(response.status_code, request.operation_id)
        return self._decode(response, request.operation_id)

    def _decode(self, response: httpx.Response, operation_id: str) -> ModelResponse | GatewayError:
        try:
            body: Any = response.json()
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
        if not isinstance(text, str):
            return _error(
                GatewayErrorKind.PROTOCOL, "gateway response has no message content", False,
                operation_id,
            )
        usage_raw = body.get("usage")
        if not isinstance(usage_raw, dict):
            usage_raw = {}
        try:
            input_tokens = int(usage_raw.get("prompt_tokens", 0))
            output_tokens = int(usage_raw.get("completion_tokens", 0))
        except (TypeError, ValueError):
            return _error(
                GatewayErrorKind.PROTOCOL, "gateway returned non-numeric usage", False,
                operation_id,
            )
        usage = Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider_enforced_ceiling=False,
        )
        stop = first.get("finish_reason", "stop") if isinstance(first, dict) else "stop"
        return ModelResponse(
            operation_id=operation_id,
            text=text,
            model_meta={
                "adapter": "http",
                "contract": CONTRACT,
                "endpoint": self.endpoint,
                "model": body.get("model", ""),
            },
            usage=usage,
            stop_reason=str(stop),
        )

    def cancel(self, operation_id: str) -> bool:
        self._cancelled.add(operation_id)
        return True

    def cancel_status(self, operation_id: str) -> str:
        if operation_id in self._cancel_confirmed:
            return _CANCELLATION_CONFIRMED
        if operation_id in self._cancelled:
            return _CANCELLATION_REQUESTED
        return "unknown"
