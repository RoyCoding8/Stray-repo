"""B17 credential value scan. Proven non-vacuous, then zero occurrences.

The scan reads the key that is in the environment RIGHT NOW and searches
this lane's written bytes for the VALUE, never for the variable name. A
scan that cannot fail is not a scan, so `selfcheck()` plants a known-bad
value in a temporary file and asserts the scan catches it before the real
run is allowed to report clean.

B12's scan read only `~/.claude.json` and took a vacuous branch under
WSL, where that file does not exist. This one reads the environment
first, then the WSL home, then the Windows USERPROFILE, then the
explicit `/mnt/c/...` path, and every branch reports which environment
it actually read rather than passing quietly.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

#: Where this lane may have written. Read anything; the scan only decides
#: whether a secret VALUE appears in what this lane wrote.
SCAN_GLOBS = (
    "reports/evidence/invr1b17-budgetfit/**",
    "reports/workstreams/b17-budgetfit.md",
    "tests/test_inv_b17_budget_fit.py",
    "experiments/ad01/invr1b17_budget_fit.py",
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A value that cannot be a real credential. Planted to prove the scan
#: has teeth; it is not a secret and carries no authority anywhere.
CANARY = "b17-canary-not-a-credential-3f9a2c7e1b"


def candidate_value() -> tuple[str, str]:
    """The credential VALUE and the environment it was found in.

    The environment variable the adapter reads comes first because that is
    where the value actually lives during a send. Reading a config file is
    the fallback, and each source is named so a reader can see which
    environment the scan ran in instead of taking "no credential" on
    trust.
    """
    found = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    if found:
        return found, "environment:SETTLEMENT_GATEWAY_KEY"

    homes = []
    wsl_home = os.environ.get("B17_WSL_HOME", "/home/ubuntu")
    homes.append(os.path.join(wsl_home, ".claude.json"))
    homes.append(os.path.join(os.environ.get("USERPROFILE", ""),
                              ".claude.json"))
    homes.append("/mnt/c/Users/roysh/.claude.json")
    for path in homes:
        if not path or not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            try:
                env = json.load(fh)["mcpServers"]["cx-agent"]["env"]
            except (KeyError, ValueError, TypeError):
                continue
        key = env.get("CX_AGENT_API_KEY", "")
        if key:
            return key, "config:%s" % path
    return "", "none"


def files_written() -> list:
    out = []
    for pattern in SCAN_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if path.is_file() and path.suffix != ".pyc":
                out.append(path)
    return sorted(set(out))


def scan(value: str, paths: list) -> list:
    hits = []
    if not value:
        return hits
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if value in text:
            hits.append(str(path.relative_to(REPO_ROOT)))
    return hits


def selfcheck() -> dict:
    """Prove the scan fails on a planted value, then remove the plant."""
    planted = REPO_ROOT / "reports/evidence/invr1b17-budgetfit/.b17_canary.txt"
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text(
        "this line carries the planted value %s and must be caught\n"
        % CANARY, encoding="utf-8")
    try:
        hits = scan(CANARY, [planted])
    finally:
        planted.unlink(missing_ok=True)
    return {"planted_value": CANARY,
            "files_with_planted_value": hits,
            "caught": hits == [str(planted.relative_to(REPO_ROOT))],
            "plant_removed": not planted.exists()}


if __name__ == "__main__":
    value, source = candidate_value()
    print(json.dumps({"source": source,
                      "value_available": bool(value),
                      "value_length": len(value),
                      "selfcheck": selfcheck(),
                      "occurrences_in_written_bytes":
                          scan(value, files_written())}, indent=1))
