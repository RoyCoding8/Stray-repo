"""Deterministic child for P02 memory-consumer integration tests."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
scenario = sys.argv[2]
args = sys.argv[3:]


def emit(event):
    print(json.dumps(event), flush=True)


if args[:2] == ["debug", "models"]:
    print(json.dumps({"models": [{"slug": "gpt-6-luna", "context_window": 1024}]}))
    raise SystemExit(0)

if args[:2] == ["debug", "prompt-input"]:
    print(json.dumps([]))
    raise SystemExit(0)

if not args or args[0] != "exec":
    raise SystemExit(f"unexpected Codex arguments: {args!r}")

workspace = Path(args[args.index("-C") + 1])
prompt = args[-1]
match = re.search(
    r"^Continuation \(JSON\):\n(.*?)(?:\n\nInput digest:|\Z)",
    prompt,
    re.MULTILINE | re.DOTALL,
)
continuation = json.loads(match.group(1)) if match else None
packet = continuation.get("context_packet") if isinstance(continuation, dict) else None
memory_view = (
    packet.get("memory_view") if isinstance(packet, dict)
    else continuation.get("memory") if isinstance(continuation, dict)
    else None
)
observations = {
    item.get("observation_id"): item
    for item in (memory_view or {}).get("observations", [])
    if isinstance(item, dict)
}


def memory_conditions_changed_input():
    if not isinstance(memory_view, dict):
        return False
    if memory_view.get("view") == "raw-history":
        rows = list(observations.values())
        return (
            not memory_view.get("claims")
            and any(row.get("content", {}).get("passed") is True
                    and row.get("content", {}).get("task_instruction", "")
                    .startswith("Implement maximum(xs) for a nonempty list")
                    for row in rows)
            and any(row.get("content", {}).get("passed") is False
                    and row.get("content", {}).get("task_instruction", "")
                    .startswith("Implement maximum(xs) and return 0 when xs is empty;")
                    for row in rows)
        )
    if memory_view.get("view") != "structured":
        return False
    for claim in memory_view.get("claims", []):
        if (claim.get("status") != "challenged"
                or "nonempty" not in claim.get("text", "").lower()
                or "empty" not in claim.get("text", "").lower()
                or claim.get("scope", {}).get("domain") != "task"):
            continue
        support_ids = set(claim.get("support", []))
        opposition_ids = set(claim.get("opposition", []))
        support = [observations[item] for item in support_ids if item in observations]
        opposition = [observations[item] for item in opposition_ids if item in observations]
        if (len(support) == 1 and len(opposition) == 1
                and support_ids.isdisjoint(opposition_ids)
                and support[0].get("content", {}).get("passed") is True
                and opposition[0].get("content", {}).get("passed") is False
                and "nonempty" in support[0].get("content", {}).get(
                    "task_instruction", "").lower()
                and "empty" in opposition[0].get("content", {}).get(
                    "task_instruction", "").lower()):
            return True
    return False


repair = scenario == "conditioned" and memory_conditions_changed_input()
source = (
    b"def maximum(xs):\n    return max(xs) if xs else 0\n"
    if repair else
    b"def maximum(xs):\n    return sorted(xs)[-1]\n"
)
(workspace / "solution.py").write_bytes(source)
(workspace / "worker-result.txt").write_text(
    "used challenged empty-input lesson\n" if repair else "no applicable lesson\n",
    encoding="utf-8",
)
call_number = 1
if log_path.exists():
    with log_path.open(encoding="utf-8") as handle:
        call_number += sum(1 for _ in handle)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({
        "call": call_number,
        "operation_id": workspace.parent.name,
        "workspace": str(workspace),
        "prompt": prompt,
        "continuation": continuation,
        "used_memory": repair,
        "solution": source.decode("utf-8"),
    }, sort_keys=True) + "\n")

emit({"type": "thread.started", "thread_id": f"p02-{call_number}"})
emit({"type": "turn.started"})
emit({"type": "item.completed", "item": {
    "type": "command_execution", "command": "write solution.py", "exit_code": 0,
}})
emit({"type": "item.completed", "item": {
    "type": "agent_message",
    "text": "Applied the scoped lesson." if repair else "No qualifying memory was available.",
}})
emit({"type": "turn.completed", "usage": {
    "input_tokens": 800,
    "cached_input_tokens": 0,
    "output_tokens": 60,
    "reasoning_output_tokens": 0,
}})
