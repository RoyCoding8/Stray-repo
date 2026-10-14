"""Resume one P02 investigation step in a fresh coordinator process."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from rsi import genome, investigate
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

investigation_id, root_arg, artifacts_arg, worker_path = sys.argv[1:]
root = Path(root_arg)
artifacts_root = Path(artifacts_arg)
agent = CodexLauncher(
    root / "runs",
    codex_cmd=[sys.executable, worker_path, str(root / "worker-inputs.jsonl"), "conditioned"],
    provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
    allowed_overrides=genome.HARNESS_KEYS,
)
checker = LocalLauncher(root / "verifiers")
state = investigate.step(
    os.environ["SETTLEMENT_TEST_DSN"], agent, checker, investigation_id,
    staging_root=root / "stage", artifacts_root=artifacts_root,
)
print(json.dumps({
    "investigation_id": state["investigation_id"],
    "revision": state["revision"],
    "status": state["status"],
    "pending_decision": state["pending_decision"],
    "last_observation": state["last_observation"],
}))
