"""Deterministic Codex CLI fixture for P04 constructor tests.

The valid method is authored in this fixture. It exercises constructor
publication and identity plumbing; it does not claim that a model learned it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


mode, *args = sys.argv[1:]

if args[:2] == ["debug", "models"]:
    print(json.dumps({"models": [{"slug": "gpt-5.4", "context_window": 1}]}))
    raise SystemExit(0)

if args[:2] == ["debug", "prompt-input"]:
    print(json.dumps([{
        "type": "message",
        "content": [{"type": "input_text", "text": "Fixture prompt input."}],
    }]))
    raise SystemExit(0)

assert args[0] == "exec", args
workspace = Path(args[args.index("-C") + 1])
with (workspace.parent / "fake-calls.jsonl").open("a", encoding="utf-8") as calls:
    calls.write(json.dumps({"mode": mode, "instruction": args[-1]}) + "\n")

if mode in ("valid", "invalid", "outside"):
    skill = workspace / "genome" / "skills" / "number-product"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_bytes(
        b"---\nname: number-product\ndescription: Multiply two finite numbers.\n---\n"
    )
    descriptor = {
        "schema": "rsi-capability/1",
        "interface": "scalar-product/1",
        "entrypoint": "method.py:invoke",
        "dependencies": ["python-stdlib"],
        "effects": ["return", "solution-files"],
        "limits": {"timeout_ms": 5000, "max_output_bytes": 65536},
    }
    if mode == "invalid":
        descriptor["entrypoint"] = "../outside.py:invoke"
    (skill / "capability.json").write_text(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (skill / "method.py").write_bytes(
        b"def invoke(request):\n"
        b"    if request['interface'] != 'scalar-product/1':\n"
        b"        raise ValueError('unsupported interface')\n"
        b"    value = request['value']['left'] * request['value']['right']\n"
        b"    return {'value': value, 'files': {'solution.txt': f'{value}\\n'}}\n"
    )
    if mode == "outside":
        (workspace / "genome" / "AGENTS.md").write_bytes(
            b"Changed outside the requested skill.\n"
        )

events = [
    {"type": "thread.started", "thread_id": "p04-fixture"},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {
        "type": "command_execution", "command": "write candidate", "exit_code": 0}},
    {"type": "item.completed", "item": {
        "type": "agent_message", "text": "Candidate files prepared."}},
    {"type": "turn.completed", "usage": {
        "input_tokens": 1000,
        "cached_input_tokens": 200,
        "output_tokens": 50,
        "reasoning_output_tokens": 10,
    }},
]
for event in events:
    print(json.dumps(event), flush=True)
