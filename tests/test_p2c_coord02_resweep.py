"""Pass-2 resweep (coord02): live-grant gate covers every live panel.

Regression pin: entry.main used to demand the finite live grant only for
evaluation/transfer panels, so `--panel development --model <live>` spent
through the real gateway with no grant declaration. Every LIVE label run
now passes the preflight gate first.
"""

from __future__ import annotations

_GRANT_VARS = ("SETTLEMENT_GATEWAY_ENDPOINT", "TEAM01_LIVE_API_KEY",
               "SETTLEMENT_GATEWAY_KEY", "TEAM01_LIVE_MODEL",
               "EC02_LIVE_GRANT_EPISODES", "EC02_LIVE_GRANT_CALLS")


def test_entry_blocks_live_development_without_grant(monkeypatch, capsys):
    from experiments.coord02 import entry
    for var in _GRANT_VARS:
        monkeypatch.delenv(var, raising=False)
    rc = entry.main(["--panel", "development", "--model", "live-model",
                     "--dsn", "dbname=ec02test_p2c_unused"])
    assert rc == 2
    assert "blocked" in capsys.readouterr().out
