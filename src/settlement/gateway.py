from __future__ import annotations

from abc import ABC, abstractmethod
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


@dataclass(frozen=True)
class ModelRequest:
    model: str
    messages: tuple[dict[str, Any], ...]
    max_output_tokens: int
    deadline_ms: int
    operation_id: str = field(default_factory=lambda: new_id("op"))


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    charge_units: int = 0
    charge_scale: int = 1000
    provider_enforced_ceiling: bool = False


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
