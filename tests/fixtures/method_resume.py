"""Restart the public method consumer without a model route."""

import json
import os
import sys
from pathlib import Path

from rsi import investigate
from settlement.launcher_local import LocalLauncher

mode, root_arg = sys.argv[1:]
root = Path(root_arg)
if mode == "interrupt":
    investigate.verifier.verify_episode = lambda *args, **kwargs: os._exit(17)
elif mode != "resume":
    raise SystemExit("unknown mode")
result = investigate.step(os.environ["SETTLEMENT_TEST_DSN"], None,
                          LocalLauncher(root / "native"), "later-use",
                          staging_root=root / "stage", artifacts_root=root / "art")
print(json.dumps({"status": result["status"]}))
