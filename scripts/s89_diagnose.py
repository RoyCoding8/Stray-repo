"""Post-fix diagnostic for archived inv01-live construction attempts (lane A2).

Reads committed exports under evidence_inv01_live/exports without
modifying them, classifies all ten construction attempts, and
re-executes the four archived validation candidates through an injected
execution path. The default path is the current tree's public
method_exec child; pass another callable to rerun against a corrected
executor (for example lane A1's fix at merge time). No model calls,
no databases, no secrets.
"""

from __future__ import annotations

import ast
import glob
import hashlib
import json
import os
import sys

TERMINALS = ("timeout-unknown-exposure", "output-truncation",
             "parse-failure", "execution-failure",
             "no-useful-improvement")


def _receipt_index(export: dict) -> dict:
    index = {}
    for transition in export.get("transitions", []):
        for receipt in transition.get("receipts", []):
            index[receipt.get("operation_id", "")] = receipt
    return index


def _content_text(content) -> str:
    if isinstance(content, dict):
        text = content.get("text", "")
        return text if isinstance(text, str) else ""
    return ""


def construct_attempts(export: dict) -> list:
    receipts = _receipt_index(export)
    attempts = []
    for op in export.get("operations", []):
        if "-construct-l" not in op.get("id", ""):
            continue
        inner = op.get("payload", {}).get("payload", {})
        messages = inner.get("messages", [])
        first = messages[0] if messages else {}
        prompt = first.get("content", "") if isinstance(first, dict) \
            else str(first)
        receipt = receipts.get(op["id"], {})
        content = receipt.get("content", {})
        usage = content.get("usage", {}) \
            if isinstance(content, dict) else {}
        attempts.append({
            "operation_id": op["id"],
            "prompt": prompt,
            "max_output_tokens": inner.get("max_output_tokens"),
            "deadline_ms": inner.get("deadline_ms"),
            "outcome": receipt.get("outcome"),
            "stop_reason": content.get("stop_reason")
            if isinstance(content, dict) else None,
            "error": content.get("error")
            if isinstance(content, dict) else None,
            "text": _content_text(content),
            "output_tokens": usage.get("output_tokens"),
            "input_tokens": usage.get("input_tokens"),
        })
    return attempts


def all_attempts(export_dir: str) -> list:
    found = []
    for path in sorted(glob.glob(os.path.join(export_dir, "*.json"))):
        with open(path) as handle:
            export = json.load(handle)
        for attempt in construct_attempts(export):
            attempt["export"] = os.path.basename(path)
            found.append(attempt)
    return found


def parse_task_from_prompt(prompt: str) -> dict:
    marker = "Task (authoritative content, not a reference): "
    for line in prompt.splitlines():
        if marker in line:
            return json.loads(line.split(marker, 1)[1])
    raise ValueError("no task line in construction prompt")


def parse_response(text: str) -> tuple:
    from experiments.ad01 import packet as _packet
    return _packet.parse_construction_response(text)


def _entry_name(source: str) -> str:
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    raise ValueError("no entry function")


def _validate_error(export: dict, operation_id: str):
    receipts = _receipt_index(export)
    receipt = receipts.get(
        operation_id.replace("-construct-l", "-validate-l"))
    if receipt is None:
        return None
    content = receipt.get("content", {})
    worker = (content.get("data", {}) or {}).get("worker", {}) or {}
    return {"error": worker.get("error"),
            "timed_out": (content.get("data", {}) or {}).get("timed_out"),
            "receipt_outcome": receipt.get("outcome")}


def extract_candidates(export_dir: str) -> list:
    found = []
    for path in sorted(glob.glob(os.path.join(export_dir, "*.json"))):
        with open(path) as handle:
            export = json.load(handle)
        for attempt in construct_attempts(export):
            if attempt["outcome"] != "success" \
                    or attempt["stop_reason"] != "stop":
                continue
            source, problem = parse_response(attempt["text"])
            if problem or not source:
                continue
            validated = _validate_error(export, attempt["operation_id"])
            if validated is None:
                continue
            task = parse_task_from_prompt(attempt["prompt"])
            found.append({
                "origin": attempt["operation_id"],
                "export": os.path.basename(path),
                "source": source,
                "entry": _entry_name(source),
                "digest": hashlib.sha256(
                    source.encode("utf-8")).hexdigest(),
                "task": task,
                "old_failure": validated["error"],
                "old_timed_out": validated["timed_out"],
            })
    return found


def classify_attempt(attempt: dict) -> dict:
    if attempt["outcome"] == "unknown":
        return {"receipt": "unknown", "terminal": TERMINALS[0],
                "detail": attempt["error"]}
    if attempt["stop_reason"] == "length":
        source, problem = parse_response(attempt["text"])
        return {"receipt": "success-length", "terminal": TERMINALS[1],
                "downstream_parse": problem or "parsed"}
    source, problem = parse_response(attempt["text"])
    if problem or not source:
        return {"receipt": "success-stop", "terminal": TERMINALS[2],
                "detail": problem}
    return {"receipt": "success-stop", "terminal": TERMINALS[3],
            "detail": "reached-validation"}


def current_tree_execute(member: dict, task: dict,
                         max_queries: int = 16) -> dict:
    from experiments.ad01 import method_exec
    candidate = {"method_source": member["method_source"],
                 "entry": member["entry"]}
    try:
        result = method_exec.run_member_out_of_process(
            candidate, task, max_queries=max_queries)
    except method_exec.MethodExecutionError as exc:
        reason = str(exc)
        stage = "gate" if reason.startswith("refused:") else "execute"
        return {"ok": False, "stage": stage, "reason": reason}
    return {"ok": True, "result": result}


def run_candidate(candidate: dict, execute_fn=None,
                  max_queries: int = 16) -> dict:
    execute = execute_fn or current_tree_execute
    member = {"method_source": candidate["source"],
              "entry": candidate["entry"]}
    outcome = execute(member, candidate["task"], max_queries)
    if outcome.get("ok"):
        return {"origin": candidate["origin"],
                "digest": candidate["digest"],
                "old_failure": candidate["old_failure"],
                "new_outcome": "executed", "next_failure": None,
                "queries": outcome["result"].get("queries")}
    stage = outcome.get("stage", "execute")
    terminal = {"parse": "parse-failure", "gate": "gate-refusal",
                "execute": "execution-failure",
                "check": "no-useful-improvement"}.get(stage, stage)
    return {"origin": candidate["origin"], "digest": candidate["digest"],
            "old_failure": candidate["old_failure"],
            "new_outcome": terminal,
            "next_failure": outcome.get("reason")}


def repair_priors(export_dir: str) -> list:
    found = []
    for path in sorted(glob.glob(os.path.join(export_dir, "*.json"))):
        with open(path) as handle:
            export = json.load(handle)
        for attempt in construct_attempts(export):
            if not attempt["operation_id"].endswith("-repair"):
                continue
            marker = "PRIOR FAILURE (repair it): "
            prior = None
            for line in attempt["prompt"].splitlines():
                if marker in line:
                    prior = json.loads(line.split(marker, 1)[1])
            if prior is None:
                continue
            found.append({
                "repair_operation": attempt["operation_id"],
                "init_operation": attempt["operation_id"].replace(
                    "-repair", "-init"),
                "prior": prior,
            })
    return found


def diagnose(export_dir: str, execute_fn=None,
             max_queries: int = 16) -> dict:
    attempts = all_attempts(export_dir)
    classified = [classify_attempt(a) for a in attempts]
    counts = {name: sum(1 for c in classified
                        if c["terminal"] == name) for name in TERMINALS}
    settings = {
        "all_max_output_tokens_2048": all(
            a["max_output_tokens"] == 2048 for a in attempts),
        "all_deadline_ms_300000": all(
            a["deadline_ms"] == 300000 for a in attempts),
        "truncated_output_tokens": sorted({
            a["output_tokens"] for a in attempts
            if a["stop_reason"] == "length"}),
    }
    candidates = extract_candidates(export_dir)
    reruns = [run_candidate(c, execute_fn=execute_fn,
                            max_queries=max_queries)
              for c in candidates]
    return {"attempts": len(attempts), "terminal_counts": counts,
            "settings": settings,
            "repair_prompts_with_prior": len(repair_priors(export_dir)),
            "candidates": [{"origin": c["origin"],
                            "digest": c["digest"],
                            "task_id": c["task"]["task_id"],
                            "old_failure": c["old_failure"]}
                           for c in candidates],
            "reruns": reruns}


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    export_dir = args[0] if args else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..",
        "evidence_inv01_live", "exports")
    print(json.dumps(diagnose(export_dir), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
