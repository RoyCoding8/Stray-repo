"""Crash or resume one agenda wake in a fresh coordinator process."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from rsi import agenda, genome
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

mode, agenda_id, root_arg, fake_path, scenario = sys.argv[1:]
root = Path(root_arg)
agent = CodexLauncher(
    root / "runs",
    codex_cmd=[sys.executable, fake_path, str(root / "worker-inputs.jsonl"), scenario],
    provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
    allowed_overrides=genome.HARNESS_KEYS,
)
checker = LocalLauncher(root / "verifiers")

if mode == "crash-after-choice":
    agenda._finish = lambda *args, **kwargs: os._exit(17)
elif mode == "crash-before-ack":
    agenda._ack = lambda *args, **kwargs: os._exit(17)
elif mode != "resume":
    raise SystemExit(f"unknown mode {mode!r}")

result = agenda.wake(
    os.environ["SETTLEMENT_TEST_DSN"],
    agent,
    checker,
    agenda_id,
    staging_root=root / "stage",
    artifacts_root=root / "art",
)
print(json.dumps(result))
