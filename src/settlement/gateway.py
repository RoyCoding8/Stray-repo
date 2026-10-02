from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .common import new_id


class GatewayStatus(str, Enum):
    CONFIGURED = "configured"
    REACHABLE = "reachable"
    AUTHENTICATED = "authenticated"
    EXERCISED = "exercised"


class GatewayErrorKind(str, Enum):
    TRANSPORT = "transport"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PROTOCOL = "protocol"
    BILLING_UNKNOWN = "billing_unknown"


class GatewayRouteError(str, Enum):
    EXPECTED_ROUTE = "expected_route"
    ENDPOINT = "endpoint"
    REQUESTED_MODEL = "requested_model"
    RESPONSE_METADATA = "response_metadata"


@dataclass(frozen=True)
class RouteContract:
    endpoint: str
    requested_model: str
    resolved_model: str
    provider: str
    tier: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RouteContract":
        if not isinstance(value, Mapping):
            raise ValueError("expected route must be an object")
        if any(not isinstance(value.get(key), str) or not value[key]
               for key in ("endpoint", "requested_model", "resolved_model",
                           "provider", "tier")):
            raise ValueError("expected route is incomplete")
        return cls(
            endpoint=value["endpoint"],
            requested_model=value["requested_model"],
            resolved_model=value["resolved_model"],
            provider=value["provider"],
            tier=value["tier"],
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "endpoint": self.endpoint,
            "requested_model": self.requested_model,
            "resolved_model": self.resolved_model,
            "provider": self.provider,
            "tier": self.tier,
        }


@dataclass(frozen=True)
class ModelRequest:
    model: str
    messages: tuple[dict[str, Any], ...]
    max_output_tokens: int
    deadline_ms: int
    operation_id: str = field(default_factory=lambda: new_id("op"))
    dispatch_generation: int = 0
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    charge_units: int | None = None
    charge_scale: int | None = None
    provider_enforced_ceiling: bool = False
    billed: bool | None = None


@dataclass(frozen=True)
class ModelResponse:
    operation_id: str
    text: str
    model_meta: dict[str, Any]
    usage: Usage
    stop_reason: str


@dataclass(frozen=True)
class GatewayError:
    kind: GatewayErrorKind
    message: str
    retryable: bool
    operation_id: str
    usage: Usage | None = None
    response_received: bool = False
    response_status: int | None = None
    response_digest: str | None = None
    route_error: GatewayRouteError | None = None


class GatewayAdapter(ABC):
    @abstractmethod
    def check_discovery(self) -> GatewayStatus | GatewayError:
        raise NotImplementedError

    @abstractmethod
    def check_auth(self) -> GatewayStatus | GatewayError:
        raise NotImplementedError

    @abstractmethod
    def infer(self, request: ModelRequest) -> ModelResponse | GatewayError:
        raise NotImplementedError

    @abstractmethod
    def cancel(self, operation_id: str) -> bool:
        raise NotImplementedError


class FakeGatewayAdapter(GatewayAdapter):
    def __init__(self, text: str = "simulated"):
        self._text = text
        self.cancelled: set[str] = set()

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        if request.operation_id in self.cancelled:
            return GatewayError(GatewayErrorKind.CANCELLED, "cancelled", False, request.operation_id)
        return ModelResponse(request.operation_id, self._text, {"simulated": True}, Usage(), "stop")

    def cancel(self, operation_id):
        self.cancelled.add(operation_id)
        return True
