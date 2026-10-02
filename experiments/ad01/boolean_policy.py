"""Run a policy artifact as the decision-maker in the Boolean world."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

from settlement import broker
from settlement.launcher_local import PROFILE, LocalLauncher

from . import boolean_rule as rules
from . import method_exec
from . import policy_action
from . import policy_step


def _shared_action_schema(action_schema: dict) -> dict:
    schema = deepcopy(action_schema)
    actions = schema.get("actions")
    if not isinstance(actions, dict):
        raise TypeError("action schema actions must be an object")
    if policy_action.CONSTRUCT in actions:
        return schema
    if "commit" not in actions:
        raise ValueError("action schema must advertise commit")
    actions[policy_action.CONSTRUCT] = actions.pop("commit")
    return schema


def _shared_view(public_state: dict) -> dict:
    if not isinstance(public_state, dict):
        raise ValueError("public state must be an object")
    if "tables" in public_state:
        raise ValueError("public state exposes hidden tables")
    missing = sorted({"instrument", "task_id", "split", "max_queries",
                      "remaining", "observed", "hypothesis_class",
                      "action_schema"} - set(public_state))
    if missing:
        raise ValueError("public state missing: %s" % ", ".join(missing))
    if type(public_state["remaining"]) is not int \
            or public_state["remaining"] < 0:
        raise ValueError("public state remaining must be a nonnegative integer")
    if not isinstance(public_state["observed"], list):
        raise TypeError("public state observed must be a list")
    return {
        "instrument": public_state["instrument"],
        "task_id": public_state["task_id"],
        "observed": deepcopy(public_state["observed"]),
        "remaining": public_state["remaining"],
        "public_world": {
            "split": public_state["split"],
            "max_queries": public_state["max_queries"],
            "hypothesis_class": deepcopy(public_state["hypothesis_class"]),
        },
        "action_schema": _shared_action_schema(public_state["action_schema"]),
    }


def _run_shared_policy_step(record: dict, view: dict, state: dict, *,
                            timeout_ms: int, cpu_seconds: int,
                            max_output_bytes: int,
                            memory_bytes: int | None) -> dict:
    """Execute one shared-contract step in the existing bounded child.

    `run_policy_step` applies a legacy view and action validator before the
    child starts, and both conflict with the shared contract. This seam keeps
    the verified source bytes and the existing bounded launcher. A shared
    execution entry in `policy_step.py` would remove the duplicate executor.

    Every staged file is written in binary, because the digest checks below
    are over the bytes that reach disk. A text-mode `write_text` translates
    each `\\n` to `os.linesep` on Windows, so a policy staged that way was 44
    bytes longer on disk than the string its digest was taken from and the
    step refused itself with "staged policy source digest mismatch" before
    a child existed. `method_exec._stage_text` already established the rule
    and the reason for this project; this seam simply had not been held to it.
    """
    artifact = policy_step.verify_policy_record(record)
    policy_step.validate_state(state)
    raw_view = json.dumps(view, sort_keys=True)
    if len(raw_view.encode("utf-8")) > policy_step.VIEW_LIMIT_BYTES:
        raise ValueError("policy view exceeds durable size cap")
    source = record["policy_source"]
    with tempfile.TemporaryDirectory(prefix="ad01-boolean-policy-") as raw:
        work = Path(raw)
        source_path = work / "policy.py"
        source_path.write_bytes(source.encode("utf-8"))
        input_data = {"view": view, "state": state}
        (work / "step.json").write_bytes(json.dumps(
            input_data, sort_keys=True).encode("utf-8"))
        driver_source = method_exec._STEP_DRIVER % artifact["entry"]
        (work / "driver.py").write_bytes(driver_source.encode("utf-8"))
        expected_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != expected_digest:
            raise method_exec.MethodExecutionError(
                "refused: staged policy source digest mismatch")
        launcher = LocalLauncher(work / "launcher")
        operation_id = "step"
        payload = {
            "profile": PROFILE,
            "argv": [sys.executable, str(work / "driver.py"), str(work)],
            "timeout_ms": timeout_ms,
            "max_output_bytes": max_output_bytes,
            "cpu_seconds": cpu_seconds,
            "memory_bytes": memory_bytes,
        }
        launched = launcher.dispatch(broker.BrokerOp(
            operation_id=operation_id, effect=broker.SANDBOX_EXEC,
            payload=payload))
        refusal = launched.refused_reason
        if launched.receipt is not None:
            receipt = launched.receipt.content
        else:
            receipt = launcher.read_result(operation_id)
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != expected_digest:
            raise method_exec.MethodExecutionError(
                "refused: executed policy source digest mismatch")
    if refusal:
        # The launcher refused before any child existed, so there is no
        # receipt and `read_result` has nothing to return. Reporting
        # `policy-step-failed: {}` in place of the reason turned a host
        # that cannot install a child's caps into an unreadable failure,
        # and the refusal is the whole diagnosis.
        raise method_exec.MethodExecutionError(f"refused: {refusal}")
    data = (receipt or {}).get("data", {})
    if receipt is None or receipt.get("_verdict") != "success":
        detail = "timeout" if data.get("timed_out") else "policy-step-failed"
        raise method_exec.MethodExecutionError(f"{detail}: {data}")
    result = data.get("worker", {}).get("data")
    if not isinstance(result, dict):
        raise TypeError("shared step result must be an object")
    return result


def _validate_boolean_action(action: policy_action.Action,
                             view: dict) -> None:
    if action.kind == policy_action.PROBE:
        if action.target != "boolean.query":
            raise policy_action.ActionRefused("probe target must be boolean.query")
        x = action.inputs.get("x")
        if type(x) is not int or not 0 <= x <= 15:
            raise policy_action.ActionRefused("probe x must be an integer in 0..15")
        if any(observation.get("x") == x for observation in view["observed"]):
            raise policy_action.ActionRefused(f"input {x} was already queried")
        if view["remaining"] <= 0:
            raise policy_action.ActionRefused("query budget is exhausted")
        return
    if action.kind == policy_action.CONSTRUCT:
        if action.target != "boolean.commit":
            raise policy_action.ActionRefused(
                "construct target must be boolean.commit")
        specs = action.inputs.get("specs")
        try:
            rules.execute_all({"specs": specs})
        except rules.RuleRefused as exc:
            raise policy_action.ActionRefused(str(exc)) from exc
        return
    if action.kind == policy_action.STOP:
        if action.target != "boolean.task":
            raise policy_action.ActionRefused("stop target must be boolean.task")
        return
    raise policy_action.ActionRefused(
        f"action {action.kind!r} is not available in the Boolean world")


def _refusal(stage: str, exc: Exception) -> dict:
    reason = str(exc) or type(exc).__name__
    return {
        "kind": policy_action.STOP,
        "target": "boolean.task",
        "inputs": {
            "bridge_refusal": {
                "stage": stage,
                "reason": reason[:500],
            }
        },
        "evidence_refs": [],
        "requested_resources": {},
    }


def choose_action(record: dict, *,
                  timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
                  cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
                  max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
                  memory_bytes: int | None = None):
    """Return an episode callback backed by one bounded policy step per call."""
    state = {}

    def decide(public_state: dict) -> dict:
        nonlocal state
        try:
            view = _shared_view(public_state)
            result = _run_shared_policy_step(
                record, view, state,
                timeout_ms=timeout_ms,
                cpu_seconds=cpu_seconds,
                max_output_bytes=max_output_bytes,
                memory_bytes=memory_bytes)
            action, next_state = policy_action.parse_step_result(result)
            _validate_boolean_action(action, view)
            policy_step.validate_state(next_state)
            state = next_state
            return action.as_dict()
        except Exception as exc:
            return _refusal("policy-step", exc)

    return decide
