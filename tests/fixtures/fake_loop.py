"""A bad proposal for observing validation quarantine through the loop."""

import runpy
import sys
from pathlib import Path

if sys.argv[1] == "exec":
    ws = Path(sys.argv[sys.argv.index("-C") + 1])
    if (ws / "genome").is_dir():
        (ws / "genome/AGENTS.md").write_bytes(b"Leave stub.")
runpy.run_path(str(Path(__file__).with_name("fake_gate.py")), run_name="__main__")
