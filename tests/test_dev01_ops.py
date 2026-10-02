"""Dev01 operator/entry lane (D-OPS): DEV-11 operator view, DEV-12 entry point."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "experiments")

import pytest
from fastapi.testclient import TestClient

from settlement import api, development, evaluation, store, trials
from settlement.common import Command, ResultCode, SettlementError, payload_digest

import run_dev_episode
from test_s3_helpers import EXPERIMENTS, seed_env

GROUPS = [{"name": "development", "kind": "development"},
          {"name": "panel", "kind": "protected-eval"}]


def _argv(dsn, tag, artifacts_root, extra=()):
    return ["--dsn", dsn, "--allocation", f"{tag}-alloc",
            "--artifacts-root", str(artifacts_root),
            "--episode", f"{tag}-episode",
            "--investigation", f"{tag}-inv",
            "--protocol-prefix", tag, *extra]


def test_deterministic_episode_passes_end_to_end(migrated_db, tmp_path,
                                                capsys):
    dsn = migrated_db
    seed_env(dsn, "opse2e")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    assert run_dev_episode.main(_argv(dsn, "opse2e", artifacts,
                                      ("--gateway", "fixture"))) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["simulated"] is True
    assert [p["phase"] for p in record["phases"]] == list(
        run_dev_episode.EPISODE_PHASES)
    assert all(p["status"] == "complete" for p in record["phases"])
    assert set(record["arms"]) == {"A", "B", "C"}
    assert all(record["arms"][arm] for arm in ("A", "B", "C"))
    assert record["ablation_noop"], "no-op control must stay visible"
    assert set(record["verdicts"]) == {"panel-B", "panel-C", "transfer-B",
                                       "transfer-C"}
    assert record["disposition"]["decision"] == "fixture-only"
    assert "baseline-v0" in record["disposition"]["selected"]
    assert record["environment"]["launcher"] == "local-process"
    assert record["environment"]["model"] == "scripted"
    stored = json.loads((artifacts / "opse2e-episode.json").read_text())
    assert stored == record
    episode = development.get_episode(dsn, "opse2e-episode")
    assert episode["state"] == "bound"
    assert [c["status"] for c in episode["candidates"]] == ["constructed"]
    assert len(episode["explanations"]) <= 2
    bindings = record["environment"]["episode_bindings"]
    assert bindings["version_id"] == record["environment"]["fixer_version"]
    assert record["development"]["methods"] == {
        "off_by_one": bindings["version_id"]}


def test_hidden_answer_setup_is_idempotent(migrated_db):
    dsn = migrated_db
    first = evaluation.propose_hidden_answer(
        dsn, Command(request_id="idem-1", payload={}), "idem-task",
        {"cases": []})
    assert first.code == ResultCode.APPLIED
    again = evaluation.propose_hidden_answer(
        dsn, Command(request_id="idem-2", payload={}), "idem-task",
        {"cases": []})
    assert again.code == ResultCode.ALREADY_APPLIED
    with pytest.raises(SettlementError, match="different content"):
        evaluation.propose_hidden_answer(
            dsn, Command(request_id="idem-3", payload={}), "idem-task",
            {"cases": [{"fn": "other"}]})


def test_live_refuses_naming_exact_missing_inputs(monkeypatch, capsys):
    for var in ("SETTLEMENT_GATEWAY_ENDPOINT", "SETTLEMENT_GATEWAY_URL",
                "SETTLEMENT_GATEWAY_KEY", "SETTLEMENT_GRANT_UNITS",
                "SETTLEMENT_MODEL"):
        monkeypatch.delenv(var, raising=False)
    base = ["--dsn", "dbname=x", "--allocation", "a",
            "--artifacts-root", "/tmp/x", "--gateway", "live"]
    assert run_dev_episode.main(base) == 2
    out = capsys.readouterr().out
    assert "SETTLEMENT_GATEWAY_ENDPOINT" in out
    assert "SETTLEMENT_GATEWAY_KEY" in out
    assert "SETTLEMENT_GRANT_UNITS" in out
    monkeypatch.setenv("SETTLEMENT_GATEWAY_ENDPOINT", "https://gw.invalid")
    assert run_dev_episode.main(base) == 2
    out = capsys.readouterr().out
    assert "SETTLEMENT_GATEWAY_KEY" in out and "SETTLEMENT_GRANT_UNITS" in out
    monkeypatch.setenv("SETTLEMENT_GATEWAY_KEY", "k")
    monkeypatch.setenv("SETTLEMENT_GRANT_UNITS", "not-an-int")
    monkeypatch.setenv("SETTLEMENT_MODEL", "m")
    assert run_dev_episode.main(base) == 2
    assert "not-an-int" in capsys.readouterr().out
    monkeypatch.setenv("SETTLEMENT_GRANT_UNITS", "100")
    monkeypatch.delenv("SETTLEMENT_MODEL", raising=False)
    assert run_dev_episode.main(base + ["--model", ""]) == 2
    assert "--model" in capsys.readouterr().out


def test_live_refuses_uncontained_profile(monkeypatch, capsys):
    monkeypatch.setenv("SETTLEMENT_GATEWAY_ENDPOINT", "https://gw.invalid")
    monkeypatch.setenv("SETTLEMENT_GATEWAY_KEY", "k")
    monkeypatch.setenv("SETTLEMENT_GRANT_UNITS", "100")
    monkeypatch.setenv("SETTLEMENT_MODEL", "m")
    base = ["--dsn", "dbname=x", "--allocation", "a",
            "--artifacts-root", "/tmp/x", "--gateway", "live"]
    assert run_dev_episode.main(base) == 3
    assert "runsc-image" in capsys.readouterr().out


PASS_CODE = "def add(a, b):\n    return a + b\n"
FAIL_CODE = "def add(a, b):\n    return a - b\n"
CASES = [{"fn": "add", "args": [1, 2], "expected": 3}]


def _craft_episode(dsn, tag):
    import hashlib
    import tempfile

    from settlement import experiment
    from settlement.launcher_local import LocalLauncher

    env = seed_env(dsn, tag)
    launcher = LocalLauncher(tempfile.mkdtemp(prefix=f"{tag}-runs-"))
    grader = str(EXPERIMENTS / "run_tests.py")
    pin = hashlib.sha256(Path(grader).read_bytes()).hexdigest()
    evaluation.register_evaluator(
        dsn, Command(request_id=f"{tag}-eval", payload={}),
        "s3-eval", "v1", {"scope": "test"}, code_digest=pin)
    for suffix in ("-dev", "-panel-C"):
        trials.freeze_protocol(
            dsn, Command(request_id=f"{tag}-frz{suffix}",
                         payload={}), protocol_id=f"{tag}{suffix}",
            candidate_version="fixer-v1", reference_version="baseline-v0",
            evaluator_version="v1", task_groups=GROUPS,
            budgets={}, metrics=["success_rate"], stopping={}, exclusions=[],
            uncertainty={})
    for arm, code in (("candidate", PASS_CODE), ("reference", FAIL_CODE)):
        aid = f"{tag}-panel-C:{arm}:t1"
        trials.assign(dsn, Command(request_id=f"{tag}-a-{arm}", payload={}),
                      f"{tag}-panel-C", "t1", "panel", arm,
                      {"entry_fn": "add"})
        op_id, staged = experiment._prepare_grade(
            dsn, launcher, code, CASES, f"{tag}-{arm}",
            env["allocation_id"], None, grader)
        body = {"code": code}
        evaluation.submit_candidate(
            dsn, Command(request_id=f"{tag}-sub-{arm}", payload={}), aid,
            body)
        evaluation.bind_evaluation(
            dsn, Command(request_id=f"{tag}-bind-{arm}", payload={}), aid,
            candidate_digest=payload_digest(body), evaluator_id="s3-eval",
            evaluator_version="v1", invocation_ref=op_id,
            executable_digest=staged["grader.py"][1],
            input_digest=staged["cases.json"][1])
        outcome = experiment._dispatch_grade(dsn, launcher, op_id,
                                             len(CASES), staged)
        evaluation.submit_evaluator_receipt(
            dsn, Command(request_id=f"{tag}-rc-{arm}", payload={}),
            receipt_id=f"{tag}-r-{arm}", assignment_id=aid,
            evaluator_id="s3-eval", evaluator_version="v1",
            invocation_ref=op_id,
            result={"outcome": outcome,
                    "detail": {"task_id": "t1"},
                    "conditions": {"model": "scripted", "arm": arm},
                    "cost": {}, "simulated": True})
    trials.record_expenditure(dsn, f"{tag}-panel-C", "evaluation", 42,
                              "panel grades")
    with store.db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO capability_versions (id, family, hypothesis,"
                        " reference_version, artifact_digest, protocol_id)"
                        " VALUES (%s, %s, %s, %s, %s, %s)",
                        (f"{tag}-fixer", "off_by_one", "loop bounds exclude n",
                         "baseline-v0", "digest-1", f"{tag}-panel-C"))
        conn.commit()


def _client(dsn):
    return TestClient(api.create_app(dsn, gateway=None, token="t"),
                      headers={"x-operator-token": "t"})


def test_learning_view_inspects_episode_phase_lineage_and_costs(migrated_db):
    dsn = migrated_db
    _craft_episode(dsn, "opsUI")
    body = _client(dsn).get("/learning").text
    assert "episode opsUI" in body
    assert "compared-simulated" in body
    assert "next decision" in body and "incumbent baseline-v0 stays selected" in body
    assert "opsUI-fixer" in body and "loop bounds exclude n" in body
    assert "observed-gain" in body or "verdict" in body
    assert "evaluation" in body and "42" in body
    assert "True" in body


def test_investigation_links_episode_report(migrated_db):
    dsn = migrated_db
    seed_env(dsn, "opsLink")
    body = _client(dsn).get("/investigations/opsLink-inv").text
    assert 'href="/learning"' in body
    assert "episode report" in body


def test_episode_view_pending_without_t5_tables(migrated_db, monkeypatch):
    from settlement import api as _api

    monkeypatch.setattr(_api, "t5_state",
                        lambda dsn: {"installed": False, "tables": []})
    body = _client(migrated_db).get("/learning").text
    assert "pending" in body
    assert "no frozen episode protocols recorded" in body


def test_episode_gets_never_mutate_domain_state(migrated_db):
    dsn = migrated_db
    _craft_episode(dsn, "opsRO")
    before = len(store.read_events(dsn)["events"])
    client = _client(dsn)
    assert client.get("/learning").status_code == 200
    assert api.episode_data(dsn)["episodes"]
    assert len(store.read_events(dsn)["events"]) == before


def test_record_carries_source_revision(migrated_db, tmp_path, capsys):
    dsn = migrated_db
    seed_env(dsn, "opsrev")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    assert run_dev_episode.main(_argv(dsn, "opsrev", artifacts,
                                      ("--gateway", "fixture"))) == 0
    record = json.loads(capsys.readouterr().out)
    try:
        expected = subprocess.run(
            ["git", "-C", str(EXPERIMENTS.parent), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        expected = ""
    assert record["revision"] == (expected or "unknown")
