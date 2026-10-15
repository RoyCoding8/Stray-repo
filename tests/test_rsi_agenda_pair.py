from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from isolation_db import disposable_db

from experiments.agenda05 import driver
from experiments.agenda05.check import recompute_pair
from experiments.agenda05.freeze import freeze


def test_valid_pair_without_failed_experience_remains_a_null_observation(
    migrated_db, tmp_path, monkeypatch
):
    launcher = driver.CodexLauncher

    def passing_fixture(*args, **kwargs):
        command = list(kwargs["codex_cmd"])
        assert Path(command[1]).name == "fixture_worker.py"
        command[3] = ""
        return launcher(*args, **{**kwargs, "codex_cmd": command})

    monkeypatch.setattr(driver, "CodexLauncher", passing_fixture)
    repo = Path(__file__).resolve().parents[1]
    scenario = tmp_path / "scenario.json"
    scenario.write_text(json.dumps(driver.build_scenario(
        (datetime.now(UTC) + timedelta(hours=1)).isoformat())), encoding="utf-8")
    bundle = tmp_path / "freeze"
    frozen = freeze(repo, bundle, scenario)
    seed = driver.run_arm(repo, bundle, tmp_path / "seed", migrated_db, "seed", "fixture")
    with disposable_db("p05null") as adaptive_db:
        adaptive = driver.run_arm(repo, bundle, tmp_path / "adaptive", adaptive_db.dsn,
                                  "adaptive", "fixture")

    for report in (seed, adaptive):
        choices = [row["data"]["opportunity_id"]
                   for row in report["agenda_export"]["decisions"]
                   if row["kind"] == "p05.choice"]
        assert choices == ["source", "priority-task"]
        assert report["result"]["status"] == "deferred"
    pair = recompute_pair(frozen, [seed, adaptive])
    assert pair["feedback_observed"] == {"seed": False, "adaptive": False}
    assert pair["different_selections"] is False
    for arm in pair["arms"].values():
        assert arm["verified"] == 2
        assert arm["failed"] == arm["unscored"] == 0
        assert arm["feedback_effects"] == []

    different_clock = copy.deepcopy(adaptive)
    different_clock["initial_claim"]["revision"] += 100
    assert recompute_pair(frozen, [seed, different_clock])["same_initial_evidence"] is True

    for counts in ({"tests": 0}, {"skipped": 1}, {"tests": True}, {"failures": -1}):
        invalid = copy.deepcopy(seed)
        verifier_id = invalid["initial_investigation"]["observations"][0]["content"]["verdict"]
        receipt = next(row for row in invalid["operations"]
                       if row["operation_id"] == verifier_id)["receipts"][0]
        receipt["content"]["data"]["worker"]["data"].update(counts)
        with pytest.raises(ValueError):
            recompute_pair(frozen, [invalid, adaptive])
