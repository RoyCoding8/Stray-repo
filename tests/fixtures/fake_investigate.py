"""Deterministic Codex subprocess for persistent-investigation tests."""

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
    print(json.dumps({"models": [{"slug": "gpt-5.4", "context_window": 1024}]}))
    raise SystemExit(0)

if args[:2] == ["debug", "prompt-input"]:
    agents = Path("AGENTS.md")
    text = agents.read_text(encoding="utf-8") if agents.exists() else ""
    print(json.dumps([{"type": "message", "content": [
        {"type": "input_text", "text": text},
    ]}]))
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
prior_solution = (workspace / "calc.py").read_bytes()
call_number = 1
if log_path.exists():
    with log_path.open(encoding="utf-8") as handle:
        call_number += sum(1 for _ in handle)
with log_path.open("a", encoding="utf-8") as handle:
    record = {
        "call": call_number,
        "operation_id": workspace.parent.name,
        "workspace": str(workspace),
        "prompt": prompt,
        "continuation": continuation,
        "prior_solution": prior_solution.decode("utf-8"),
    }
    handle.write(json.dumps(record, sort_keys=True) + "\n")

question = "Does the solution satisfy the task obligation?"
feedback_is_complete = (
    continuation is not None
    and question in continuation.get("open_questions", [])
    and isinstance(continuation.get("previous_observation"), dict)
    and continuation["previous_observation"].get("passed") is False
    and prior_solution == b"def add(a, b):\n    return a - b\n"
)
repair = scenario == "pass-first" or (
    scenario == "repair-after-feedback" and call_number > 1 and feedback_is_complete
)
objective_marker = (
    f"# objective: {continuation['objective']}\n".encode("utf-8")
    if scenario == "pass-first" and continuation is not None
    else b""
)
source = (
    objective_marker + b"def add(a, b):\n    return a + b\n"
    if repair
    else b"def add(a, b):\n    return a - b\n"
)
(workspace / "calc.py").write_bytes(source)
(workspace / "worker-result.txt").write_text(
    f"{continuation['objective']}\n" if continuation is not None else "no objective\n",
    encoding="utf-8",
)

emit({"type": "thread.started", "thread_id": f"investigate-{call_number}"})
emit({"type": "turn.started"})
emit({"type": "item.completed", "item": {
    "type": "command_execution", "command": "write calc.py", "exit_code": 0,
}})
emit({"type": "item.completed", "item": {
    "type": "agent_message",
    "text": "Repaired from checked feedback." if repair else
            "The implementation needs checked feedback.",
}})
emit({"type": "turn.completed", "usage": {
    "input_tokens": 1000,
    "cached_input_tokens": 0,
    "output_tokens": 50,
    "reasoning_output_tokens": 0,
}})
