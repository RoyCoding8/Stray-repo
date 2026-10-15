"""Cooperative solver child used only by the disposable fixture qualification."""

import json
import sys
from pathlib import Path

SOLUTIONS = {
    "score.py": "def sum_positive(values):\n    return sum(value for value in values if value > 0)\n",
    "selection.py": "def first_nonempty(lines):\n    return next((line for line in lines if line.strip()), None)\n",
    "counts.py": "def merge_counts(left, right):\n    merged = dict(left)\n    for key, value in right.items():\n        merged[key] = merged.get(key, 0) + value\n    return merged\n",
    "pair_ops.py": "def rotate_pair(pair):\n    if len(pair) != 2:\n        raise ValueError('pair must contain two items')\n    return pair[1], pair[0]\n",
}

args = sys.argv[1:]
if args[:2] == ["debug", "models"]:
    print(json.dumps({"models": [{"slug": "gpt-6-luna", "context_window": 1}]}))
    raise SystemExit(0)
if args[:2] == ["debug", "prompt-input"]:
    advice = Path("AGENTS.md")
    text = advice.read_text(encoding="utf-8") if advice.exists() else ""
    print(json.dumps([{"type": "message", "content": [{"type": "input_text", "text": text}]}]))
    raise SystemExit(0)
if not args or args[0] != "exec":
    raise SystemExit("unsupported fixture command")

workspace = Path(args[args.index("-C") + 1])
matches = [name for name in SOLUTIONS if (workspace / name).is_file()]
if len(matches) != 1:
    raise SystemExit("fixture task did not identify one known solution slot")
(workspace / matches[0]).write_text(SOLUTIONS[matches[0]], encoding="utf-8")
emit = lambda event: print(json.dumps(event), flush=True)
emit({"type": "thread.started", "thread_id": "p10-fixture"})
emit({"type": "turn.started"})
emit({"type": "item.completed", "item": {
    "type": "command_execution", "command": "fixture solution", "exit_code": 0}})
emit({"type": "item.completed", "item": {"type": "agent_message", "text": "fixture completed"}})
emit({"type": "turn.completed", "usage": {
    "input_tokens": 1000, "cached_input_tokens": 100, "output_tokens": 20,
    "reasoning_output_tokens": 0}})
