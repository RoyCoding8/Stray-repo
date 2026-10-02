"""Pass-3 entry sweep: clean refusal at every public entry, resume converges."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

DSN = os.environ.get(
    "P3E_DSN", "dbname=ec02test_p3e_entry host=/var/run/postgresql user=ubuntu")
MISSING_DSN = "dbname=ec02test_p3e_missing host=/var/run/postgresql user=ubuntu"
MIGRATIONS = ROOT / "migrations"

# This battery truncates its store, so the property worth asserting is that the
# store is disposable and private to the run -- not that it carries the name
# this module defaults to. `tests/conftest_isolation.py` hands every session
# `s09iso_<token>_<original>`, so a name comparison could never hold and the
# seam was pinned rather than redirected. The shared and live names are the
# ones that must actually be refused.
_SHARED_PREFIX = "ec02test_"
_SHARED_NAMES = ("postgres", "template0", "template1")


def _assert_disposable_store(dsn: str) -> str:
    """Refuse a store this battery must not empty, and return its dbname."""
    name = conninfo_to_dict(dsn).get("dbname") or ""
    if not name:
        raise AssertionError("P3E_DSN carries no dbname: %r" % (dsn,))
    if (name.startswith(("live", _SHARED_PREFIX)) or name.endswith("_live")
            or name in _SHARED_NAMES):
        raise AssertionError(
            "the pass-3 entry battery truncates its store, so it must not be "
            "aimed at a shared or live database, got %r" % (name,))
    return name


@pytest.fixture()
def pg():
    _assert_disposable_store(DSN)
    from settlement import db
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute('TRUNCATE TABLE "%s" CASCADE' % row[0])
        conn.commit()
    return DSN


def test_run_tests_needs_two_args(capsys):
    from run_tests import main
    assert main([]) == 2
    assert "Traceback" not in capsys.readouterr().err
    assert main(["only-one"]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_run_tests_bad_budget(capsys):
    from run_tests import main
    assert main(["a", "b", "notafloat"]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_run_tests_missing_cases_is_typed_json(capsys):
    from run_tests import main
    assert main(["/tmp/p3e-cand.py", "/tmp/p3e-no-such-cases.json"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["status"] == "error"


def test_cli_unknown_task_clean(pg, capsys):
    from experiments.ad01.cli import main
    rc = main(["run", "--dsn", pg, "--world", "0", "--arm", "I",
               "--tasks", "bogus-task", "--agenda-authorized", "10"])
    assert rc == 2
    assert "Traceback" not in capsys.readouterr().err


def test_cli_missing_db_clean(capsys):
    from experiments.ad01.cli import main
    rc = main(["run", "--dsn", MISSING_DSN, "--world", "0", "--arm", "I",
               "--agenda-authorized", "10"])
    assert rc == 3
    assert "Traceback" not in capsys.readouterr().err


def test_cli_missing_repertoire_clean(pg, capsys):
    from experiments.ad01.cli import main
    rc = main(["use", "--repertoire", "/tmp/p3e-no-repertoire.json",
               "--dsn", pg, "--allocation-id", "a", "--release", "p3e-rel",
               "--world", "0", "--arm", "I"])
    assert rc == 2
    assert "Traceback" not in capsys.readouterr().err


def test_cli_negative_boundaries_exits_2():
    from experiments.ad01.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["run", "--dsn", DSN, "--world", "0", "--arm", "I",
              "--max-boundaries", "-1"])
    assert exc.value.code == 2


def test_cli_malformed_campaign_exits_2():
    from experiments.ad01.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["resume", "--dsn", DSN, "--campaign", "bogus"])
    assert exc.value.code == 2


def test_cli_resume_unknown_world_clean(capsys):
    from experiments.ad01.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["resume", "--dsn", DSN, "--campaign", "ad01-w9-I-00"])
    assert exc.value.code == 2


def test_live_abc_unknown_task_before_db(capsys, monkeypatch):
    import run_live_abc
    monkeypatch.setattr(sys, "argv", ["run_live_abc.py", "--dsn", "x",
                                      "--allocation", "a",
                                      "--artifacts-root", "/tmp/p3e-art",
                                      "--deterministic", "--dev", "bogus"])
    assert run_live_abc.main() == 2
    assert "Traceback" not in capsys.readouterr().out


def test_live_abc_missing_db_clean(capsys, monkeypatch):
    import run_live_abc
    monkeypatch.setattr(sys, "argv", ["run_live_abc.py", "--dsn", MISSING_DSN,
                                      "--allocation", "a",
                                      "--artifacts-root", "/tmp/p3e-art",
                                      "--deterministic"])
    assert run_live_abc.main() == 3
    assert "Traceback" not in capsys.readouterr().out


def test_dev_episode_unknown_task_clean(capsys, tmp_path):
    from run_dev_episode import main
    rc = main(["--dsn", "x", "--allocation", "a",
               "--artifacts-root", str(tmp_path), "--dev", "bogus"])
    assert rc == 2
    assert "Traceback" not in capsys.readouterr().out


def test_dev_episode_missing_db_clean(capsys, tmp_path):
    from run_dev_episode import main
    rc = main(["--dsn", MISSING_DSN, "--allocation", "a",
               "--artifacts-root", str(tmp_path)])
    assert rc == 3
    assert "Traceback" not in capsys.readouterr().out


def test_run_use_bad_disposition_before_db(capsys):
    from run_use import main
    rc = main(["--dsn", "x", "--artifacts-root", "/tmp/p3e-art",
               "--allocation", "a", "--investigation", "i",
               "--episode", "e", "--use-task", "dev-sum",
               "--disposition-json", "notjson"])
    assert rc == 2
    assert "Traceback" not in capsys.readouterr().out


def test_run_use_missing_db_clean(capsys):
    from run_use import main
    rc = main(["--dsn", MISSING_DSN, "--artifacts-root", "/tmp/p3e-art",
               "--allocation", "a", "--investigation", "i",
               "--episode", "e", "--use-task", "dev-sum"])
    assert rc == 3
    assert "Traceback" not in capsys.readouterr().out


def test_run_use_unknown_episode_clean(pg, capsys, tmp_path):
    from run_use import main
    rc = main(["--dsn", pg, "--artifacts-root", str(tmp_path),
               "--allocation", "a", "--investigation", "i",
               "--episode", "p3e-no-such-episode", "--use-task", "dev-sum"])
    assert rc == 2
    assert "Traceback" not in capsys.readouterr().out


def test_resume_after_complete_converges(pg):
    from experiments.ad01 import trajectory
    tasks = ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01"]
    caps = {"max_boundaries": 6, "diagnostic_queries": 16,
            "agenda_authorized": 50}
    charter = {"objective": "p3e resume probe", "freeze_id": "ad01"}
    trajectory.authorize_campaign(
        pg, trajectory.campaign_id(0, "I", 41), authorized=50)
    first = trajectory.run_campaign(0, "I", charter, caps, tasks=tasks,
                                    campaign_seq=41, dsn=pg)
    assert len(first["boundaries"]) == 2
    second = trajectory.resume_campaign(pg, first["campaign_id"],
                                        charter, caps, tasks=tasks)
    assert second["queries"] == first["queries"]
    assert [b["spend"] for b in second["boundaries"]] == [
        b["spend"] for b in first["boundaries"]]
    assert all(b.get("resumed") for b in second["boundaries"])


def test_resume_after_kill_half_published(pg):
    from experiments.ad01 import trajectory
    tasks = ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01"]
    auth = {"max_boundaries": 1, "diagnostic_queries": 16,
            "agenda_authorized": 50}
    caps = {"max_boundaries": 6, "diagnostic_queries": 16,
            "agenda_authorized": 50}
    charter = {"objective": "p3e kill probe", "freeze_id": "ad01"}
    trajectory.authorize_campaign(
        pg, trajectory.campaign_id(0, "I", 42), authorized=50)
    first = trajectory.run_campaign(0, "I", charter, auth, tasks=tasks,
                                    campaign_seq=42, dsn=pg)
    assert len(first["boundaries"]) == 1
    cid = first["campaign_id"]
    obs0 = first["boundaries"][0]["observation_id"]
    trajectory.record_decision(
        pg, cid, 1,
        {"basis_references": [obs0], "question": "killed mid-run",
         "next_action": {"kind": "diagnostic", "diagnostic": "software",
                         "task_id": tasks[1]},
         "requested_resources": {"diagnostic_queries": 1},
         "charter": charter["objective"]})
    second = trajectory.resume_campaign(pg, cid, charter, caps, tasks=tasks)
    assert len(second["boundaries"]) == 2
    assert second["boundaries"][0].get("resumed") is True
    assert (second["queries"] == first["queries"]
            + second["boundaries"][1]["spend"])
    third = trajectory.resume_campaign(pg, cid, charter, caps, tasks=tasks)
    assert third["queries"] == second["queries"]
    assert all(b.get("resumed") for b in third["boundaries"])
