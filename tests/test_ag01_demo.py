from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "agenda01.py"
DSN = os.environ.get("SETTLEMENT_TEST_DSN")
if not DSN:
    pytest.skip("SETTLEMENT_TEST_DSN is not configured", allow_module_level=True)

JOURNEY_MARKS = ("[propose]", "[grant]", "[admit]", "[dispatch]", "[observe]",
                 "[observe-forged]", "unknown receipt", "[continue]",
                 "useful continuation", "justified refusal", "[decline]", "dormant",
                 "[wake]", "reopened", "[resume", "[resumable]", "[costs]",
                 "outstanding_liability=", "reason=")


def run_cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--dsn", DSN, *argv],
                          capture_output=True, text=True, timeout=170)


def test_demo_journey():
    proc = run_cli("demo")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for mark in JOURNEY_MARKS:
        assert mark in proc.stdout, f"missing journey mark {mark!r}"
    assert "VIOLATED" not in proc.stdout
    for token in ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE "):
        assert token not in proc.stdout, f"operator output leaks SQL: {token!r}"


def test_demo_deterministic_rerun():
    proc = run_cli("demo")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[demo] journey complete" in proc.stdout


def test_stale_decline_refused():
    assert run_cli("grant", "--root", "agenda-root").returncode == 0
    assert run_cli("propose", "--option", "k-stale",
                   "--question", "stale version probe").returncode == 0
    proc = run_cli("decline", "--option", "k-stale", "--expected-version", "99",
                   "--reason", "stale attempt", "--wake-type", "authorized-scan-due",
                   "--wake-ref", "scan-nightly")
    assert proc.returncode != 0
    assert "stale" in proc.stdout


def test_wrong_attempt_observe_refused():
    proc = run_cli("observe", "--option", "k-stale", "--attempt", "att-no-such",
                   "--receipt", "rc-no-such")
    assert proc.returncode != 0
    assert "wrong attempt" in proc.stdout


def test_forged_receipt_observe_refused():
    assert run_cli("grant", "--root", "agenda-root").returncode == 0
    assert run_cli("propose", "--option", "k-forge",
                   "--question", "forged receipt probe").returncode == 0
    assert run_cli("admit", "--option", "k-forge", "--probe", "probe-a",
                   "--decision", "do-a").returncode == 0
    proc = run_cli("observe", "--option", "k-forge", "--attempt", "att-k-forge-probe-a",
                   "--receipt", "rc-forged")
    assert proc.returncode != 0
    assert "unknown receipt" in proc.stdout
