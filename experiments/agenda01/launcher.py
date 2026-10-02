"""AG01-EXP labeled deterministic simulation launcher.

Nature role, never policy role: this module draws simulated measurement
bytes from world truth supplied by the caller and admits them as labeled
receipts through the real broker receipt path. It must never be imported
by policy code; the grader refuses policy-path callers independently.
"""

from __future__ import annotations

from typing import Any, Callable

from settlement import broker

LAUNCHER_ID = "agenda-sim-launcher"
ADAPTER_KEY = "adapter:agenda-probe"
PROVENANCE = "agenda-sim"


class AgendaProbeLauncher:
    launcher_id = LAUNCHER_ID
    profile = "agenda-probe"
    idempotent_resend = True

    def __init__(self, dsn: str, observe: Callable[..., Any],
                 claim: Callable[..., Any]) -> None:
        self._dsn = dsn
        self._observe = observe
        self._claim = claim
        self._sent: set[str] = set()
        self._results: dict[str, dict] = {}

    def prior_send(self, operation_id: str) -> bool:
        return operation_id in self._sent

    def dispatch(self, op: broker.BrokerOp) -> broker.LaunchOutcome:
        payload = dict(op.payload or {})
        assert payload.get("adapter") == "agenda-probe", payload.get("adapter")
        spec = dict(payload.get("input") or {})
        attempt = spec["attempt_id"]
        dep_versions = dict(spec.get("dep_versions") or {})
        results: dict[str, dict] = {}
        for entry in spec.get("observed", []):
            prop = entry["prop"]
            value = self._observe(spec["probe"], int(spec["sample"]), prop)
            content = {
                "kind": "observation", "prop": prop,
                "scope": entry["scope"], "dep": entry["dep"],
                "dep_version": int(dep_versions.get(entry["dep"], 1)),
                "value": ("unknown" if value is None
                          else ("true" if value else "false")),
                "source_attempt": attempt,
                "receipt": f"{spec['receipt_base']}:{prop}",
                "epoch": int(spec["epoch"]), "simulated": True,
            }
            outcome = "unknown" if value is None else "success"
            broker.admit_launcher_receipt(
                self._dsn, op.operation_id, broker.ReceiptProposal(
                    receipt_identity=content["receipt"], content=content,
                    outcome=outcome, provenance=PROVENANCE))
            results[prop] = content
        if spec.get("dud"):
            content = {"kind": "dud", "probe": spec["probe"],
                       "source_attempt": attempt,
                       "receipt": f"{spec['receipt_base']}:dud",
                       "epoch": int(spec["epoch"]), "simulated": True}
            broker.admit_launcher_receipt(
                self._dsn, op.operation_id, broker.ReceiptProposal(
                    receipt_identity=content["receipt"],
                    content=content, outcome="unknown",
                    provenance=PROVENANCE))
            results["dud"] = content
        if spec.get("product"):
            claims = {prop: bool(self._claim(prop))
                      for prop in spec["product"]}
            content = {"kind": "product-claims", "claims": claims,
                       "source_attempt": attempt,
                       "receipt": f"{spec['receipt_base']}:product",
                       "epoch": int(spec["epoch"]), "simulated": True}
            broker.admit_launcher_receipt(
                self._dsn, op.operation_id, broker.ReceiptProposal(
                    receipt_identity=content["receipt"],
                    content=content, outcome="success",
                    provenance=PROVENANCE))
            results["product"] = content
        self._sent.add(op.operation_id)
        self._results[op.operation_id] = results
        return broker.LaunchOutcome(sent=True)

    def stop(self, operation_id: str) -> bool:
        return False

    def live_ids(self) -> list[str]:
        return []

    def is_live(self, operation_id: str) -> bool:
        return False

    def read_result(self, operation_id: str) -> dict[str, Any] | None:
        return self._results.get(operation_id)

    def stage_input(self, operation_id: str, execution_version: str,
                    relpath: str, data: bytes) -> Any:
        raise NotImplementedError("agenda-probe carries its input in the operation")

    def exec_dirs(self, operation_id: str,
                  execution_version: str) -> tuple[str, str]:
        raise NotImplementedError("agenda-probe runs no external process")

    def staged_python(self) -> str:
        raise NotImplementedError("agenda-probe runs no external process")

    def read_output(self, operation_id: str, execution_version: str,
                    relpath: str) -> bytes:
        raise NotImplementedError("agenda-probe results read via receipts")

    def prove_never_sent(self, operation_id: str) -> bool:
        # No stable run directory: loss of this object voids any
        # never-sent proof, so park instead of claiming True.
        return False
