from __future__ import annotations

import json
import os
import threading
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
RESPONSES_CONTRACT = "settlement-gateway/http-responses-v1"

APIS = ("chat", "responses")

_CANCELLATION_REQUESTED = "requested"
_CANCELLATION_CONFIRMED = "confirmed"

_STATUS_ERRORS = {
    401: (GatewayErrorKind.AUTH, False),
    403: (GatewayErrorKind.AUTH, False),
    429: (GatewayErrorKind.RATE_LIMIT, True),
}


def _error(kind: GatewayErrorKind, message: str, retryable: bool, operation_id: str,
           usage: Usage | None = None) -> GatewayError:
    return GatewayError(kind, message, retryable, operation_id, usage)


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
    ) -> None:
        if api not in APIS:
            raise ValueError(f"unknown gateway api {api!r}: expected one of {APIS}")
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.api = api
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
    def from_settings(cls, settings: Settings, api_key: str | None = None,
                      api: str | None = None) -> "HttpGatewayAdapter":
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
        )

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
        return self._status_error(response.status_code, "auth")

    def _cancelled_error(self, operation_id: str) -> GatewayError:
        self._cancel_confirmed.add(operation_id)
        return _error(
            GatewayErrorKind.CANCELLED,
            "operation cancelled; external outcome unknown",
            False,
            operation_id,
        )

    def infer(self, request: ModelRequest) -> ModelResponse | GatewayError:
        if request.operation_id in self._cancelled:
            return self._cancelled_error(request.operation_id)
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
        if status != 200:
            return self._status_error(status, request.operation_id)
        if self.api == "responses":
            return self._decode_responses_body(body, request.operation_id)
        return self._decode_body(body, request.operation_id)

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
        charge_units = 0
        charge_scale = 1000
        billed = False
        if "charge_units" in usage_raw:
            charge = usage_raw["charge_units"]
            if isinstance(charge, bool) or not isinstance(charge, int) or charge < 0:
                return _error(
                    GatewayErrorKind.PROTOCOL, "gateway returned non-numeric usage charge",
                    False, operation_id,
                )
            charge_units = charge
            billed = True
        if "charge_scale" in usage_raw:
            scale = usage_raw["charge_scale"]
            if isinstance(scale, bool) or not isinstance(scale, int) or scale <= 0:
                return _error(
                    GatewayErrorKind.PROTOCOL, "gateway returned non-numeric usage charge",
                    False, operation_id,
                )
            if scale != 1000:
                return _error(
                    GatewayErrorKind.PROTOCOL,
                    "gateway quoted a non-canonical charge scale:"
                    " convert to milli-units before settling",
                    False, operation_id,
                )
            charge_scale = scale
        usage = Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            charge_units=charge_units,
            charge_scale=charge_scale,
            provider_enforced_ceiling=False,
            billed=billed,
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
            model_meta={
                "adapter": "http",
                "contract": CONTRACT,
                "endpoint": self.endpoint,
                "model": body.get("model", ""),
            },
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
        status = body.get("status", "")
        if status == "failed":
            error = body.get("error")
            detail = error.get("message") if isinstance(error, dict) else error
            return _error(
                GatewayErrorKind.PROTOCOL, f"gateway responses call failed: {detail}", False,
                operation_id,
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
        usage_raw = body.get("usage")
        if not isinstance(usage_raw, dict):
            usage_raw = {}
        try:
            input_tokens = int(usage_raw.get("input_tokens", 0))
            output_tokens = int(usage_raw.get("output_tokens", 0))
        except (TypeError, ValueError):
            return _error(
                GatewayErrorKind.PROTOCOL, "gateway returned non-numeric usage", False,
                operation_id,
            )
        usage = Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            charge_units=0,
            charge_scale=1000,
            provider_enforced_ceiling=False,
            billed=False,
        )
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
        elif status == "cancelled":
            return _error(
                GatewayErrorKind.PROTOCOL, "gateway responses call cancelled", False,
                operation_id,
            )
        else:
            stop = str(status) if status else "stop"
        return ModelResponse(
            operation_id=operation_id,
            text=text,
            model_meta={
                "adapter": "http",
                "contract": RESPONSES_CONTRACT,
                "endpoint": self.endpoint,
                "model": body.get("model", ""),
            },
            usage=usage,
            stop_reason=stop,
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
