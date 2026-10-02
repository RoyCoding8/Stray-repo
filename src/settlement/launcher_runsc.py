"""gVisor/runsc launcher: same interface as the local launcher, probe-gated.

Unavailable on this host, so every dispatch attempt raises IncompatibleVersion
carrying the probe reason. It never routes to the local launcher. The class
carries the declared image digest, runtime and profile so the real launcher
slots in on a runsc host without changing the broker contract.
"""

from __future__ import annotations

import re
from typing import Any

from .broker import BrokerOp, LaunchOutcome
from .common import IncompatibleVersion
from .exec_profile import probe_gvisor

PROFILE = "gvisor"
RUNTIME = "runsc"


def _sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


class RunscLauncher:
    launcher_id = "runsc-1"
    profile = PROFILE
    idempotent_resend = False

    def __init__(self, image_digest: str, runtime: str = RUNTIME,
                 network: str = "none", scratch_bytes: int = 100 * 1024 * 1024) -> None:
        if not (isinstance(image_digest, str) and image_digest.startswith("sha256:")):
            raise ValueError("image_digest must be a pinned sha256 digest")
        self.image_digest = image_digest
        self.runtime = runtime
        self.network = network
        self.scratch_bytes = scratch_bytes
        self._probe = probe_gvisor()

    @property
    def reason(self) -> str:
        return self._probe.reason

    @property
    def available(self) -> bool:
        return self._probe.available

    def native_id(self, operation_id: str, execution_version: str) -> str:
        return f"{_sanitize(operation_id)}_{_sanitize(execution_version or 'exec-default')}_{RUNTIME}"

    def declaration(self) -> dict[str, Any]:
        return {"profile": PROFILE, "runtime": self.runtime, "image_digest": self.image_digest,
                "network": self.network, "scratch_bytes": self.scratch_bytes,
                "inputs": "read-only", "credentials": "none"}

    def dispatch(self, op: BrokerOp) -> LaunchOutcome:
        raise IncompatibleVersion(f"{PROFILE} unavailable: {self._probe.reason}")

    def prior_send(self, operation_id: str) -> bool:
        return False

    def stop(self, operation_id: str) -> bool:
        return False

    def live_ids(self) -> list[str]:
        return []

    def is_live(self, operation_id: str) -> bool:
        return False

    def read_result(self, operation_id: str) -> dict[str, Any] | None:
        return None
