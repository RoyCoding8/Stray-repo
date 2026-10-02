from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.team01 import checker, entry, panel, template
from experiments.team01.oracle import SPLITS


def _synth(where, arm, task, rep, solved, fam="fam-ind",
           tin=1000, tout=250, tools=4, calls=2):
    return {"arm": arm, "task_id": task, "repeat": rep, "family": fam,
            "panel": where, "episode_id": "%s-%s-%s-r%s" % (where, arm, task, rep),
            "plan_id": "plan_%s_%s_%s" % (arm, task, rep),
            "manifest_sha256": "sha", "outcome": "success" if solved else "failure",
            "protected": {"passed": 4 if solved else 1, "failed": 0 if solved else 3,
                          "total": 4,
                          "failures": [] if solved else [
                              {"input": {"texts": ["  X  "], "numbers": [1]},
                               "expected": {"texts": ["x"], "numbers": 1},
                               "got": {"texts": ["X"], "numbers": 1}, "error": ""}]},
            "public": {"passed": 4, "failed": 0, "total": 4},
            "join": {"passed": solved, "join_receipt": "rc",
                     "check_operation": "op", "candidate_digest": "ab" * 32},
            "frozen_digest": "ab" * 32 if solved else None,
            "template_digest": None, "template_changed_decision": False,
            "receipts": {"w1": ["rc"]}, "simulated": True,
            "costs": {"model_tokens": {"in": tin, "out": tout},
                      "tool_executions": tools, "model_invocations": calls,
                      "wall_s": 1.0}}


def _doubled(where, solved, **over):
    tasks = SPLITS["evaluation"] if where == "eval" else SPLITS["transfer"]
    arms = panel.ARMS if where == "eval" else panel.TRANSFER_MODES
    return { (where, r["arm"], r["task_id"], r["repeat"]): r
             for arm in arms for task in tasks for rep in panel.REPEATS
             for r in [solved(arm, task, rep, **over)] }


def test_template_frozen_dev_evidence_only(tmp_path):
    dev = [_synth("dev", "T", t, 1, True) for t in SPLITS["development"]]
    cands = template.build_candidates(dev)
    assert 1 <= len(cands) <= 2
    winner, frozen_out = template.select_candidate(cands, dev)
    assert winner["version"] == "coordination-template/1"
    assert winner["supporting_episodes"]
    assert all(task in SPLITS["development"]
               for task in winner["supporting_episodes"])
    rec = template.freeze_template(tmp_path, winner=winner,
                                   frozen_out=frozen_out, builds=cands)
    assert rec["digest"]
    assert rec["frozen_out"] and rec["frozen_out"][0]["reason"]
    with pytest.raises(Exception):
        bad = dev + [_synth("eval", "T", SPLITS["evaluation"][0], 1, True)]
        template.build_candidates(bad)


def test_comparison_runner_binds_48_episodes(migrated_db, tmp_path):
    out = panel.run_comparison(migrated_db, evidence_root=tmp_path / "ev",
                               runs_root=tmp_path / "runs", tag="t%s" % uuid.uuid4().hex[:6])
    assert len(out["records"]) == 48
    cells = {(r["arm"], r["task_id"], r["repeat"]) for r in out["records"]}
    assert len(cells) == 48
    for record in out["records"]:
        assert record["plan_id"] and record["join"]["join_receipt"]
        assert record["join"]["check_operation"]
        assert record["receipts"]
        assert record["protected"]["passed"] + record["protected"]["failed"] \
            == record["protected"]["total"] > 0
        assert record["costs"]["model_tokens"]["in"] >= 0
    problems = checker.check_evidence(tmp_path / "ev", *checker.load_manifest()[0:2])[1]
    assert problems == []


def test_transfer_runner_binds_24_episodes(migrated_db, tmp_path):
    dev = panel.run_development(migrated_db, evidence_root=tmp_path / "ev",
                                runs_root=tmp_path / "runs", tag="d%s" % uuid.uuid4().hex[:6])
    assert len(dev) <= 24
    assert {r["probe"] for r in dev} >= {"template-use", "diagnostic", "incompatible"}
    cands = template.build_candidates(dev)
    winner, frozen_out = template.select_candidate(cands, dev)
    frozen = template.freeze_template(tmp_path / "ev", winner=winner,
                                      frozen_out=frozen_out, builds=cands)
    out = panel.run_transfer(migrated_db, evidence_root=tmp_path / "ev",
                             runs_root=tmp_path / "runs", tag="x%s" % uuid.uuid4().hex[:6],
                             template=frozen)
    assert len(out["records"]) == 24
    warm = [r for r in out["records"] if r["arm"] == "warm-T"]
    cold = [r for r in out["records"] if r["arm"] == "cold-T"]
    assert warm and cold
    assert all(r["template_digest"] == frozen["digest"] for r in warm)
    assert all(r["template_digest"] is None for r in cold)
    assert any(r["template_changed_decision"] for r in warm)


def test_checker_quotes_every_failure(tmp_path):
    rec = _synth("eval", "T", "team01-t02", 1, False)
    (tmp_path / "episodes").mkdir()
    (tmp_path / "episodes" / "r.json").write_text(json.dumps(rec))
    records, _ = checker.check_evidence(tmp_path, {"version": "x"}, "sha")
    quoted = checker.failure_quotes(records)
    assert quoted and '"texts"' in quoted[0] and "expected" in quoted[0]
    assert checker.main(["--evidence-root", str(tmp_path)]) in (0, 1)
    bare = dict(rec)
    bare["protected"] = {"passed": 0, "failed": 4, "total": 4, "failures": []}
    (tmp_path / "episodes" / "r.json").write_text(json.dumps(bare))
    _, problems = checker.check_evidence(tmp_path, {"version": "x"}, "sha")
    assert any("unquoted-failure" in p for p in problems)


def test_replay_and_operator_view(migrated_db, tmp_path):
    tag = "r%s" % uuid.uuid4().hex[:6]
    for arm in panel.ARMS:
        panel.run_episode(migrated_db, task_id="team01-t02", arm=arm, repeat=1,
                          runs_root=tmp_path / "runs", panel_name="eval",
                          evidence_root=tmp_path / "ev", tag=tag)
    replayed = checker.replay_panel(migrated_db, tmp_path / "ev")
    assert replayed["replayed"] == 3 and replayed["mismatches"] == []
    view = checker.operator_view(migrated_db, tmp_path / "ev")
    for key in ("graph", "pending", "selected", "joins", "costs"):
        assert key in view
    assert len(view["graph"]) == 3 and view["joins"]
    (list((tmp_path / "ev" / "episodes").glob("*T-team01-t02*"))[0]).unlink()
    replayed = checker.replay_panel(migrated_db, tmp_path / "ev")
    assert any("missing-pair" in m for m in replayed["mismatches"])


def test_finite_panel_rule_accepts_rejects():
    t_win = _doubled("eval", lambda a, t, r: _synth(
        "eval", a, t, r, a == "T" or (t, r) != ("team01-t02", 1)))
    rule = checker.finite_panel_rule(t_win, {"oracle": True, "barrier": True})
    assert rule["promising"] is True and rule["release_eligible"] is False
    s_win = _doubled("eval", lambda a, t, r: _synth(
        "eval", a, t, r, a == "S" or (t, r) == ("team01-t02", 1) and a == "T"))
    assert checker.finite_panel_rule(
        s_win, {"oracle": True, "barrier": True})["promising"] is False
    all_fail = _doubled("eval", lambda a, t, r: _synth("eval", a, t, r, False))
    assert checker.finite_panel_rule(
        all_fail, {"oracle": True, "barrier": True})["promising"] is False
    public_only = _doubled("eval", lambda a, t, r: _synth("eval", a, t, r, False))
    for record in public_only.values():
        record["outcome"] = "success"
    assert checker.finite_panel_rule(
        public_only, {"oracle": True, "barrier": True})["promising"] is False
    assert checker.finite_panel_rule(
        t_win, {"oracle": False, "barrier": True})["promising"] is False


def test_entry_names_highest_phase_completed(migrated_db, tmp_path):
    with pytest.raises(Exception):
        entry.run_team_panel(migrated_db, tag="bad", evidence_root=tmp_path,
                             runs_root=tmp_path, phases=("nope",))
    status = entry.run_team_panel(
        migrated_db, tag="e%s" % uuid.uuid4().hex[:6], evidence_root=tmp_path / "ev",
        runs_root=tmp_path / "runs", phases=("development", "template"))
    assert status["phases_completed"] == ["development", "template"]
    assert status["phase_completed"] == "template"
    assert (tmp_path / "ev" / ("experiment-%s.json" % status["tag"])).is_file()
