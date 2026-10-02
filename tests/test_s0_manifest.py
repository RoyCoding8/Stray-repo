from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_manifest_has_required_sections():
    from scripts import manifest

    data = manifest.build_manifest()
    for key in (
        "python",
        "packages",
        "postgres",
        "sandbox",
        "kernel",
        "limits",
        "gateway_contract",
    ):
        assert key in data


def test_manifest_locked_versions_match_installed():
    import importlib.metadata

    from scripts import manifest

    data = manifest.build_manifest()
    assert data["packages"]["pydantic"] == importlib.metadata.version("pydantic")
    assert data["packages"]["httpx"] == importlib.metadata.version("httpx")


def test_manifest_reports_this_hosts_sandbox_gap():
    from scripts import manifest

    data = manifest.build_manifest()
    assert data["sandbox"]["runsc_present"] is False
    assert data["sandbox"]["docker_present"] is False


def test_manifest_prints_no_secrets(monkeypatch, capsys):
    import os

    from scripts import manifest

    monkeypatch.setenv("SETTLEMENT_GATEWAY_KEY", "marker-secret-xyz")
    monkeypatch.setenv(
        "SETTLEMENT_DSN", "postgresql://user:marker-pw-xyz@localhost/db?host=/var/run/postgresql"
    )
    manifest.main()
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert isinstance(parsed, dict)
    assert "marker-secret-xyz" not in out
    assert "marker-pw-xyz" not in out


def test_manifest_is_deterministic():
    from scripts import manifest

    assert manifest.build_manifest() == manifest.build_manifest()
