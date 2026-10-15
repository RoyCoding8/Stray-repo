"""The installed catalogue supplies metadata, never the inference route."""

import json
import sys
from pathlib import Path

import pytest

from settlement.common import SettlementError
from settlement.launcher_codex import CodexLauncher, Provider


@pytest.mark.parametrize("template", [None, "missing-template"])
def test_current_catalogue_keeps_route_and_refuses_missing_template(tmp_path, template):
    settings = {} if template is None else {"catalog_template": template}
    launcher = CodexLauncher(
        tmp_path / "runs",
        codex_cmd=[sys.executable, str(Path(__file__).parent / "fixtures/fake_codex.py"),
                   "ok"],
        provider=Provider("http://gateway.invalid/v1", "openrouter/openrouter/free",
                          "fixture-only", **settings),
        allowed_overrides=frozenset(),
    )
    if template is not None:
        with pytest.raises(SettlementError, match="missing-template"):
            launcher.model_catalog()
        return
    catalogue = json.loads(launcher.model_catalog())
    assert len(catalogue["models"]) == 1
    model, = catalogue["models"]
    assert model["slug"] == "openrouter/openrouter/free"
    assert model["include_skills_usage_instructions"] is False
    assert launcher.provider.model == "openrouter/openrouter/free"
