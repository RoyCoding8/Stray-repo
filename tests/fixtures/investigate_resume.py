"""Run one investigation step in a fresh coordinator process."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from rsi import genome, investigate
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

mode, investigation_id, root_arg, fake_path = sys.argv[1:]
root = Path(root_arg)
agent = CodexLauncher(
    root / "runs",
    codex_cmd=[sys.executable, fake_path, str(root / "worker-inputs.jsonl"), "pass-first"],
    provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
    allowed_overrides=genome.HARNESS_KEYS,
)
checker = LocalLauncher(root / "verifiers")

if mode == "interrupt-before-check":
    investigate.verifier.verify_episode = lambda *args, **kwargs: os._exit(17)
elif mode != "resume":
    raise SystemExit(f"unknown mode {mode!r}")

state = investigate.step(
    os.environ["SETTLEMENT_TEST_DSN"],
    agent,
    checker,
    investigation_id,
    staging_root=root / "stage",
    artifacts_root=root / "art",
)
print(json.dumps({
    "investigation_id": state["investigation_id"],
    "revision": state["revision"],
    "status": state["status"],
    "pending_decision": state["pending_decision"],
    "last_observation": state["last_observation"],
}))
