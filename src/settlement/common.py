from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ResultCode(str, Enum):
    APPLIED = "applied"
    ALREADY_APPLIED = "already_applied"
    ACCEPTED = "accepted"
    STALE_REVISION = "stale_revision"
    UNAUTHORIZED = "unauthorized"
    INSUFFICIENT_RESOURCES = "insufficient_resources"
    INCOMPATIBLE_VERSION = "incompatible_version"
    MISSING_EVIDENCE = "missing_evidence"
    INVALID_INPUT = "invalid_input"
    UNAVAILABLE_DEPENDENCY = "unavailable_dependency"
    OBSERVED_SUCCESS = "observed_success"
    OBSERVED_FAILURE = "observed_failure"
    OUTCOME_UNKNOWN = "outcome_unknown"


SUPERVISION_SCOPE = "supervision"


class SettlementError(Exception):
    code: ResultCode = ResultCode.INVALID_INPUT


class StaleRevision(SettlementError):
    code = ResultCode.STALE_REVISION


class Unauthorized(SettlementError):
    code = ResultCode.UNAUTHORIZED


class InsufficientResources(SettlementError):
    code = ResultCode.INSUFFICIENT_RESOURCES


class IncompatibleVersion(SettlementError):
    code = ResultCode.INCOMPATIBLE_VERSION


class MissingEvidence(SettlementError):
    code = ResultCode.MISSING_EVIDENCE


class UnavailableDependency(SettlementError):
    code = ResultCode.UNAVAILABLE_DEPENDENCY


class ConflictPayload(SettlementError):
    code = ResultCode.INVALID_INPUT


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def payload_digest(payload: dict[str, Any]) -> str:
    import json

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def open_nofollow(path, flags: int, mode: int = 0o644) -> int:
    """`os.open` that refuses a symlink at `path` on every platform.

    POSIX refuses atomically through O_NOFOLLOW. Windows has no such flag, so
    the link is checked immediately before opening (a narrow check-then-open
    window, which Windows' symlink privilege requirement keeps small in practice).
    """
    import errno
    import os

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow and os.path.islink(path):
        raise OSError(errno.ELOOP, "refusing to follow a symlink", str(path))
    return os.open(path, flags | nofollow | getattr(os, "O_BINARY", 0), mode)


def fsync_dir(path) -> None:
    """Make a rename into `path` durable. Windows has no directory fsync."""
    import os
    import sys

    if sys.platform == "win32":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Command(BaseModel):
    request_id: str = Field(default_factory=lambda: new_id("req"))
    expected_revision: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    deadline_ms: int = 30_000

    model_config = {"extra": "forbid"}


class CommandResult(BaseModel):
    code: ResultCode
    request_id: str
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}
