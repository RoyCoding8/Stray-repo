"""RPR-08 evidence, disposition and live-blocker record (Lane D)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.acquire import live_campaign, panel
from experiments.representation.acquire import run as panel_run
from experiments.representation.experiment import checker
from settlement import db as _db
from settlement import trials

REP = ROOT / "experiments" / "representation"


def _full_run(dsn, tmp_path, tag):
    roots = {}
    for key in ("artifacts", "staging", "runs", "evidence"):
        path = tmp_path / key
        path.mkdir(parents=True, exist_ok=True)
        roots[key] = path
    index = panel_run.run_panel(
        dsn, tag=tag, artifacts_root=roots["artifacts"],
        staging_root=roots["staging"], runs_root=roots["runs"],
        evidence_root=roots["evidence"])
    return index, roots["evidence"]


def test_full_panel_is_checker_clean(migrated_db, tmp_path):
    dsn = migrated_db
    index, evidence = _full_run(dsn, tmp_path, "ev8")
    assert index["arm_task_records"] == 48
    assert index["control_records"] == 12
    assert index["attribution_records"] == 2
    assert index["use_records"] == 4
    assert index["release"] == "none"
    assert index["unchanged_core"]["equal"] is True
    report = checker.check_all(evidence)
    assert report["clean"], report["problems"]
    report_db = checker.check_all(evidence, dsn=dsn)
    assert report_db["clean"], report_db["problems"]
    rule = report["pilot_rule"]
    assert rule["promising"] is False
    assert index["means"]["C-software"] < index["means"]["A-software"]
    assert index["means"]["C-graph"] < index["means"]["A-graph"]
    assert index["physical_operation_union"] > 0


def test_committed_evidence_is_checker_clean():
    mechanics = checker.check_all(REP / "evidence",
                                  manifest_name="manifest_acq1.json")
    assert mechanics["clean"], mechanics["problems"]
    assert mechanics["records"] == 27
    heldout = checker.check_all(REP / "evidence-heldout")
    assert heldout["clean"], heldout["problems"]
    assert heldout["records"] == 48


def test_trial_disposition_persisted(migrated_db, tmp_path):
    dsn = migrated_db
    _full_run(dsn, tmp_path, "ev8t")
    for base in (panel.PROTOCOL_B, panel.PROTOCOL_C):
        protocol_id = "%s-ev8t" % base
        rows = trials.protocol_results(dsn, protocol_id)
        assert rows
        missing = [r["id"] for r in rows if r["outcome"] is None]
        assert missing == []
        verdict = trials.verdict(dsn, protocol_id)
        assert verdict["label"] in ("observed-gain", "regression",
                                    "inconclusive")
    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM capability_versions"
                        " WHERE family = 'representation'")
            ids = [r[0] for r in cur.fetchall()]
            conn.commit()
    from collections import Counter
    groups = Counter("-".join(i.split("-")[:3]) for i in ids)
    assert all(v <= 2 for v in groups.values()), dict(groups)


def test_no_second_registry(migrated_db):
    with _db.connect(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables"
                        " WHERE schemaname = 'public'"
                        " AND (tablename LIKE '%acq%'"
                        " OR tablename LIKE '%rpr%')")
            assert cur.fetchall() == []
            conn.commit()


def test_live_campaign_is_exact_blocker(tmp_path):
    record = {"protocol": "rpr-acq-C", **live_campaign.preflight({})}
    assert record["blocked"] is True
    assert record["reason"] == "missing-inputs"
    assert record["missing"] == ["SETTLEMENT_GATEWAY_ENDPOINT",
                                 "SETTLEMENT_GATEWAY_KEY",
                                 "SETTLEMENT_GRANT_UNITS"]
    assert "live_campaign.py" in record["command"]
    assert record["spent"] == {"model_calls": 0, "input_tokens": 0,
                               "output_tokens": 0, "grant_units": 0}
    assert record["budget"]["model_calls"] == 12
    assert record["model_output"].startswith("none:")
    proc = subprocess.run(
        [sys.executable, str(REP / "acquire" / "live_campaign.py"),
         "--protocol", "rpr-acq-C", "--write",
         "--evidence-root", str(tmp_path)], capture_output=True, text=True)
    assert proc.returncode == 2
    written = json.loads((tmp_path / "live_blocker.json").read_bytes())
    assert written["blocked"] is True
    assert written["missing"] == record["missing"]
