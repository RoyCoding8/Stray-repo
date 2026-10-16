"""Fresh-process campaign controls use the same durable owner as the Python API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fixtures.p10_campaign import prepare_campaign

from rsi import agenda, campaign
from settlement import db


def _cli(*arguments, offline=False):
    env = dict(os.environ)
    if offline:
        env = {key: value for key, value in env.items()
               if not key.startswith("SETTLEMENT_GATEWAY_")}
        env["SETTLEMENT_TEST_DSN"] = "dbname=absent host=127.0.0.1 port=1 user=none"
    completed = subprocess.run(
        [sys.executable, "-m", "rsi.campaign", *map(str, arguments)],
        cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, check=False,
        text=True, encoding="utf-8", timeout=90,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _start(dsn, tmp_path, identity):
    case = prepare_campaign(dsn, tmp_path, campaign_id=identity,
                            round_count=1, max_turns=1)
    root = case["run"]["roots"]["staging_root"].parent
    for name in ("charter", "protocol"):
        (tmp_path / (name + ".json")).write_text(
            json.dumps(case[name]), encoding="utf-8")
    arguments = ("--dsn", dsn, "--id", identity, "--root", root)
    created = _cli("start", *arguments, "--charter", tmp_path / "charter.json",
                   "--protocol", tmp_path / "protocol.json")
    assert created["status"] == "active"
    return case, arguments


def test_fresh_process_controls_block_the_same_public_runner(migrated_db, tmp_path):
    identity = "p10-cli-control"
    case, arguments = _start(migrated_db, tmp_path, identity)
    initial = _cli("inspect", *arguments)
    suspended = _cli("suspend", *arguments,
                     "--expected-revision", initial["revision"])
    assert suspended["status"] == "suspended"
    held = campaign.run(migrated_db, case["run"]["agent"], case["run"]["checker"],
                        identity, max_wakes=1, wall_seconds=30,
                        **case["run"]["roots"])
    assert held["status"] == "suspended"
    inspected = _cli("inspect", *arguments)
    assert inspected["revision"] == suspended["revision"]
    assert inspected["turns"] == 0
    resumed = _cli("resume", *arguments,
                   "--expected-revision", inspected["revision"])
    assert resumed["status"] == "active"
    stopped = _cli("stop", *arguments,
                   "--expected-revision", resumed["revision"])
    assert stopped["status"] == "stopped"
    after = campaign.run(migrated_db, case["run"]["agent"], case["run"]["checker"],
                         identity, max_wakes=1, wall_seconds=30,
                         **case["run"]["roots"])
    assert after["status"] == "stopped"
    assert _cli("inspect", *arguments)["turns"] == 0
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 0


def test_cli_export_recomputes_without_gateway_or_database(migrated_db, tmp_path):
    identity = "p10-cli-offline"
    _, arguments = _start(migrated_db, tmp_path, identity)
    exported = tmp_path / "export.json"
    _cli("export", *arguments, "--output", exported)
    bundle = json.loads(exported.read_text(encoding="utf-8"))
    expected = campaign.recompute(bundle)
    observed = _cli("recompute", "--bundle", exported, offline=True)
    assert observed == expected


def test_fresh_process_resume_does_not_consume_the_first_development_choice(
    migrated_db, tmp_path
):
    identity = "p10-cli-first-choice"
    case, arguments = _start(migrated_db, tmp_path, identity)
    initial = _cli("inspect", *arguments)
    held = _cli("suspend", *arguments,
                "--expected-revision", initial["revision"])
    resumed = _cli("resume", *arguments,
                   "--expected-revision", held["revision"])
    assert resumed["revision"] > 0
    result = campaign.run(
        migrated_db, case["run"]["agent"], case["run"]["checker"], identity,
        max_wakes=1, wall_seconds=30, **case["run"]["roots"])
    assert result["results"][0]["status"] == "acknowledged"
    state = _cli("inspect", *arguments)
    assert state["turns"] == 1 and state["flight_pending"] is False


@pytest.mark.parametrize("expired", [False, True])
def test_interrupted_development_flight_resumes_before_due_assessment(
    migrated_db, tmp_path, monkeypatch, expired
):
    identity = "p10-flight-before-assessment-" + str(expired).lower()
    case = prepare_campaign(migrated_db, tmp_path / "case", campaign_id=identity,
                            round_count=1, max_turns=1)

    class Clock(datetime):
        current = datetime.now(UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz is None else cls.current.astimezone(tz)

    deadline = Clock.current + timedelta(hours=1)
    case["charter"]["deadline"] = deadline.isoformat()
    campaign.start(migrated_db, campaign_id=identity, charter=case["charter"],
                   protocol=case["protocol"], **case["run"]["roots"])
    finish = agenda._finish

    def interrupt(*args, **kwargs):
        raise InterruptedError("process stopped after development admission")

    monkeypatch.setattr(agenda, "_finish", interrupt)
    with pytest.raises(InterruptedError):
        campaign.run(migrated_db, case["run"]["agent"], case["run"]["checker"], identity,
                     **case["run"]["roots"], max_wakes=1, wall_seconds=120)
    admitted = campaign.inspect(migrated_db, identity)
    assert admitted["flight_pending"] is True and admitted["turns"] == 1

    if expired:
        Clock.current = deadline + timedelta(seconds=1)
        monkeypatch.setattr(campaign, "datetime", Clock)
    monkeypatch.setattr(agenda, "_finish", finish)
    resumed = campaign.run(migrated_db, case["run"]["agent"], case["run"]["checker"], identity,
                           **case["run"]["roots"], max_wakes=8, wall_seconds=120)
    assert resumed["status"] == ("deadline" if expired else "complete"), resumed
    assert resumed["results"][0]["status"] == "acknowledged", resumed
    final = campaign.inspect(migrated_db, identity)
    assert final["flight_pending"] is False and final["turns"] == 1
    if expired:
        assert not any(result["status"] in {"assigned", "assessed"}
                       for result in resumed["results"])


def test_development_choice_commit_rechecks_deadline_under_owner_lock(
    migrated_db, tmp_path, monkeypatch
):
    identity = "p10-choice-deadline-lock"
    case = prepare_campaign(migrated_db, tmp_path / "case", campaign_id=identity,
                            round_count=1, max_turns=1)

    class Clock(datetime):
        current = datetime.now(UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz is None else cls.current.astimezone(tz)

    deadline = Clock.current + timedelta(seconds=10)
    case["charter"]["deadline"] = deadline.isoformat()
    campaign.start(migrated_db, campaign_id=identity, charter=case["charter"],
                   protocol=case["protocol"], **case["run"]["roots"])
    real_rank = agenda.agenda_policy.rank

    def expire_after_ranking(options, policy):
        ranked = real_rank(options, policy)
        Clock.current = deadline + timedelta(seconds=1)
        return ranked

    monkeypatch.setattr(agenda, "datetime", Clock)
    monkeypatch.setattr(agenda.agenda_policy, "rank", expire_after_ranking)
    result = campaign.run(migrated_db, case["run"]["agent"], case["run"]["checker"], identity,
                          **case["run"]["roots"], max_wakes=1, wall_seconds=60)
    state = campaign.inspect(migrated_db, identity)
    assert result["status"] == "stale", result
    assert state["turns"] == 0 and state["flight_pending"] is False
    bundle = campaign.export(migrated_db, identity,
                             artifacts_root=case["run"]["roots"]["artifacts_root"])
    assert bundle["operations"] == []
    assert not any(row["kind"] == "choice" for row in bundle["decisions"])
