"""Authored Codex-protocol child for a deterministic P05 fixture arm."""

import json
import re
import sys
import time
from pathlib import Path

log_path = Path(sys.argv[1])
fail_pairs = {tuple(map(int, item.split(","))) for item in sys.argv[2].split(";") if item}
delay_text = next((item.partition("=")[2] for item in sys.argv[3:]
                   if item.startswith("--delay-pairs=")), "")
delay_pairs = {tuple(map(int, item.split(","))) for item in delay_text.split(";") if item}
command_index = next((index for index, item in enumerate(sys.argv)
                      if item in {"debug", "exec"}), len(sys.argv))
args = sys.argv[command_index:]

if args[:2] == ["debug", "models"]:
    print(json.dumps({"models": [{"slug": "gpt-6-luna", "context_window": 1024}]}))
    raise SystemExit(0)
if args[:2] == ["debug", "prompt-input"]:
    print(json.dumps([]))
    raise SystemExit(0)
if not args or args[0] != "exec":
    raise SystemExit("unexpected fixture child command")

workspace = Path(args[args.index("-C") + 1])
count = len(log_path.read_text(encoding="utf-8").splitlines()) if log_path.exists() else 0
prompt = args[-1]
match = re.search(r"add\((-?\d+),\s*(-?\d+)\)", prompt)
pair = tuple(map(int, match.groups())) if match else None
if pair in delay_pairs:
    time.sleep(5)
correct = pair not in fail_pairs
source = "def add(a, b):\n    return a + b\n" if correct else (
    "def add(a, b):\n    return a - b\n")
(workspace / "calc.py").write_text(source, encoding="utf-8")
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"call": count + 1, "task_pair": pair,
                             "authored_outcome": "pass" if correct else "fail"}) + "\n")
for event in (
    {"type": "thread.started", "thread_id": f"p05-fixture-{count + 1}"},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {
        "type": "command_execution", "command": "write calc.py", "exit_code": 0}},
    {"type": "item.completed", "item": {
        "type": "agent_message", "text": "Authored deterministic fixture result."}},
    {"type": "turn.completed", "usage": {
        "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
        "reasoning_output_tokens": 0}},
):
    print(json.dumps(event), flush=True)
