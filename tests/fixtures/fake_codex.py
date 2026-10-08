"""Stand-in for the Codex CLI: `debug prompt-input` and `exec --json`.

Usage: fake_codex.py <mode> <codex args...>. Modes: ok, leak, infra, hang.
Every exec appends a line to <workspace>/../fake-calls.txt so tests can count sends.
"""
import json
import sys
import time
from pathlib import Path

mode, args = sys.argv[1], sys.argv[2:]
if args[:2] == ["debug", "models"]:
    print(json.dumps({"models": [{"slug": "gpt-5.4", "context_window": 1}]}))
    sys.exit(0)
if args[:2] == ["debug", "prompt-input"]:
    agents = Path("AGENTS.md")
    text = agents.read_text() if agents.exists() else ""
    if mode == "leak":
        text += "\n### Skill roots\n- r0 = somewhere"
    print(json.dumps([{"type": "message", "content": [{"type": "input_text", "text": text}]}]))
    sys.exit(0)
assert args[0] == "exec", args
ws = Path(args[args.index("-C") + 1])
with open(ws.parent / "fake-calls.txt", "a") as calls:
    calls.write(" ".join(args[1:4]) + "\n")
emit = lambda e: print(json.dumps(e), flush=True)
emit({"type": "thread.started", "thread_id": "t1"})
emit({"type": "turn.started"})
if mode == "hang":
    time.sleep(120)
if mode == "infra":
    emit({"type": "error", "message": "Reconnecting... 1/5 (unexpected status 503 Service Unavailable)"})
    emit({"type": "turn.failed", "error": {"message": "unexpected status 503 Service Unavailable"}})
    sys.exit(1)
(ws / "done.txt").write_text("agents=%s\n" % (ws / "AGENTS.md").exists())
emit({"type": "item.completed", "item": {"type": "command_execution", "command": "x", "exit_code": 0}})
emit({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}})
emit({"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 200,
                                          "output_tokens": 50, "reasoning_output_tokens": 10}})
