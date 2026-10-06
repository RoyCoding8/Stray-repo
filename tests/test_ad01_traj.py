"""AD01 trajectory lane, first tracer: investigation proposal from experience."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict

from test_s09_migrate_callers import first_eligible

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.conftest_isolation import admin_dsn  # noqa: E402

DSN = os.environ.get("EC02_ADTR_DSN", "dbname=ec02test_adtr")
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
        raise AssertionError("EC02_ADTR_DSN carries no dbname: %r" % (dsn,))
    if (name.startswith(("live", _SHARED_PREFIX)) or name.endswith("_live")
            or name in _SHARED_NAMES):
        raise AssertionError(
            "the AD01 trajectory battery truncates its store, so it must not "
            "be aimed at a shared or live database, got %r" % (name,))
    return name


@pytest.fixture()
def pg():
    # The authority refuses when no route is named, and the refusal converts
    # to a skip on a routeless session (conftest_isolation) -- a routed
    # session that refuses has a defect worth a red line.
    admin_dsn()
    _assert_disposable_store(DSN)
    from settlement import db
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute('TRUNCATE TABLE "%s" CASCADE' % row[0])
            for n in range(14):
                cur.execute(
                    "INSERT INTO allocations (id, domain, authorized)"
                    " VALUES (%s, 'agenda', 1000)"
                    " ON CONFLICT (id) DO NOTHING",
                    ("ad01-campaign-ad01-w0-I-%02d" % n,))
        conn.commit()
    return DSN


CAPS = {"max_boundaries": 6, "diagnostic_queries": 16}

EXPERIENCE = {
    "observations": [
        {"observation_id": "obs-ad01-w0-sw-00-greedy",
         "task_id": "ad01-w0-dev-sw-00",
         "capability_id": "seed-sw-greedy",
         "verdict": "preserved",
         "final_measure": 9},
    ],
}

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}


def test_propose_investigation_references_actual_experience():
    from experiments.ad01.trajectory import propose_investigation
    investigation = propose_investigation(EXPERIENCE, CHARTER)
    observed = {o["observation_id"] for o in EXPERIENCE["observations"]}
    assert observed & set(investigation["basis_references"])
    assert investigation["question"]
    assert investigation["next_action"]
    assert investigation["requested_resources"]


def test_admit_refuses_invented_basis_refs():
    from experiments.ad01.trajectory import admit_investigation
    invented = {"basis_references": ["obs-never-recorded"],
                "question": "why",
                "next_action": {"kind": "diagnostic",
                                "task_id": "ad01-w0-dev-sw-00"},
                "requested_resources": {"diagnostic_queries": 1}}
    outcome = admit_investigation(invented, EXPERIENCE, CHARTER)
    assert outcome["decision"] == "refused"
    assert "obs-never-recorded" in outcome["reason"]


def test_admit_accepts_explicit_exploratory_option():
    from experiments.ad01.trajectory import admit_investigation
    exploratory = {"basis_references": [],
                   "question": "unknown witness behavior on transfer tasks",
                   "unknown": "whether reversed priority preserves the witness",
                   "next_action": {"kind": "diagnostic",
                                "task_id": "ad01-w0-dev-sw-00"},
                   "requested_resources": {"diagnostic_queries": 1}}
    outcome = admit_investigation(exploratory, EXPERIENCE, CHARTER)
    assert outcome["decision"] == "admitted"


def test_run_diagnostic_returns_attributed_observation():
    from experiments.ad01.trajectory import run_diagnostic
    admitted = {"basis_references": ["obs-ad01-w0-sw-00-greedy"],
                "question": "which observations distinguish causal events",
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "diagnostic_resolves",
                                "task_id": "ad01-w0-dev-sw-00"},
                "requested_resources": {"diagnostic_queries": 1}}
    observation = run_diagnostic(admitted, EXPERIENCE)
    assert observation["observation_id"] != "obs-ad01-w0-sw-00-greedy"
    assert observation["basis_references"] == ["obs-ad01-w0-sw-00-greedy"]
    assert observation["verdict"] == "preserved-vs-not_preserved"


def test_changed_evidence_changes_next_decision():
    from experiments.ad01.trajectory import next_decision
    before = next_decision(EXPERIENCE, CHARTER)
    changed = {"observations": [
        {**EXPERIENCE["observations"][0], "verdict": "not_preserved"}]}
    after = next_decision(changed, CHARTER)
    assert before["question"] != after["question"]


def test_renamed_identities_do_not_change_next_decision():
    from experiments.ad01.trajectory import next_decision
    before = next_decision(EXPERIENCE, CHARTER)
    renamed = {"observations": [
        {**EXPERIENCE["observations"][0],
         "observation_id": "obs-renamed-bookkeeping-99"}]}
    after = next_decision(renamed, CHARTER)
    assert before["question"] == after["question"]
    assert before["next_action"] == after["next_action"]


def test_construct_check_retains_reduced_candidate():
    from experiments.ad01.trajectory import dev_episode
    outcome = dev_episode("ad01-w0-dev-sw-00", "seed-sw-greedy",
                          max_queries=16)
    assert outcome["disposition"] == "retained"
    assert outcome["final_size"] < outcome["initial_size"]
    assert outcome["check"]["verdict"] == "preserved"
    assert outcome["lineage"][-1]["capability_id"] == "seed-sw-greedy"


def test_construct_check_rejects_broken_candidate():
    from experiments.ad01.trajectory import dev_episode
    outcome = dev_episode("ad01-w0-dev-sw-00", "seed-sw-greedy",
                          max_queries=1, break_candidate=True)
    assert outcome["disposition"] == "rejected"
    assert outcome["check"]["verdict"] != "preserved"
    assert outcome["reason"]


def test_no_candidate_falls_back_to_incumbent():
    from experiments.ad01.trajectory import dev_episode
    outcome = dev_episode("ad01-w0-dev-sw-00", "seed-sw-greedy",
                          max_queries=0, break_candidate=False)
    assert outcome["disposition"] == "no-candidate"
    assert outcome["fallback"] == "incumbent"
    assert outcome["fallback_reason"]


def test_run_campaign_terminates_with_episodes_and_stop():
    from experiments.ad01.trajectory import run_campaign
    campaign = run_campaign(0, "I", CHARTER,
                            {"max_boundaries": 2, "diagnostic_queries": 16})
    assert campaign["world"] == 0
    assert campaign["arm"] == "I"
    assert len(campaign["boundaries"]) <= 2
    assert campaign["episodes"]
    assert campaign["stop"]["reason"]
    assert campaign["campaign_id"].startswith("ad01-w0-I-")


def test_kill_at_recorded_decision_resumes_same_campaign(pg):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 10)
    trajectory.authorize_campaign(pg, cid, authorized=1000)
    trajectory.ensure_campaign(pg, cid, 0, "I", CHARTER, CAPS,
                               tasks=["ad01-w0-dev-sw-00"])
    decision = {"basis_references": ["obs-ad01-w0-dev-sw-00-seed"],
                "question": "q0",
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "diagnostic_resolves",
                                "task_id": "ad01-w0-dev-sw-00"}}
    did = trajectory.record_decision(pg, cid, 0, decision)
    resumed = trajectory.resume_campaign(
        pg, cid, CHARTER, CAPS, tasks=["ad01-w0-dev-sw-00"])
    assert resumed["campaign_id"] == cid
    assert resumed["boundaries"][0]["decision_id"] == did
    assert resumed["boundaries"][0]["decision"] == decision
    assert resumed["episodes"][0]["disposition"] == "inspected"
    assert resumed["queries"] == resumed["boundaries"][0]["spend"] == 1
    direct = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=["ad01-w0-dev-sw-00"], campaign_seq=11)
    assert resumed["queries"] == direct["queries"]


def test_i_and_r_arms_run_one_world_without_sharing():
    from experiments.ad01 import rotation, trajectory
    order = [s["task_id"] for s in rotation.r_schedule(0)]
    rotation_caps = dict(CAPS, diagnostic_queries=160)
    arm_i = trajectory.run_campaign(0, "I", CHARTER, rotation_caps,
                                    tasks=[t for t in order
                                           if "-sw-" in t])
    arm_r = trajectory.run_campaign(0, "R", CHARTER, rotation_caps,
                                    tasks=order)
    assert [b["task_id"] for b in arm_r["boundaries"]] == order[:6]
    assert arm_i["stop"]["reason"] and arm_r["stop"]["reason"]
    assert arm_i["campaign_id"] != arm_r["campaign_id"]
    obs_i = {b["task_id"]: b["observation_id"]
             for b in arm_i["boundaries"]}
    obs_r = {b["task_id"]: b["observation_id"]
             for b in arm_r["boundaries"]}
    shared = set(obs_i) & set(obs_r)
    assert shared
    assert all(obs_i[t] == obs_r[t] for t in shared)
    assert {b["task_id"] for b in arm_i["boundaries"]} <= set(order)


def test_retained_episode_carries_executable_spec():
    from experiments.ad01.trajectory import dev_episode
    outcome = dev_episode("ad01-w0-dev-sw-00", "seed-sw-greedy",
                          max_queries=16)
    assert outcome["disposition"] == "retained"
    exe = outcome["executable"]
    assert exe["capability_id"] == "seed-sw-greedy"
    assert exe["scope"] == {"family": "software"}
    assert exe["authored"] is True


class RecordingLearner:
    """Labeled model-seam double: replays one valid proposal."""

    label = "RECORDING-DOUBLE"

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.calls: list = []

    def __call__(self, experience: dict, charter: dict) -> dict:
        self.calls.append({"experience": experience, "charter": charter})
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "replayed question",
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "software",
                                "task_id": self.task_id},
                "requested_resources": {"diagnostic_queries": 1}}


def test_recording_double_proposal_enters_through_campaign():
    from experiments.ad01 import trajectory
    double = RecordingLearner("ad01-w0-dev-sw-01")
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=["ad01-w0-dev-sw-01"], propose=double)
    assert len(double.calls) == 1
    assert campaign["boundaries"][0]["task_id"] == "ad01-w0-dev-sw-01"
    assert campaign["episodes"][0]["disposition"] == "inspected"


def test_use_phase_runs_the_method_a_policy_admits_and_verifies(tmp_path):
    from experiments.ad01 import checker, trajectory

    def develop(experience, charter):
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "develop the visible task",
                "next_action": {"kind": "development",
                                "diagnostic": "software",
                                "task_id": "ad01-w0-dev-sw-00"},
                "requested_resources": {"diagnostic_queries": 1}}

    campaign = trajectory.run_campaign(0, "I", CHARTER, dict(CAPS),
                                       tasks=["ad01-w0-dev-sw-00"],
                                       propose=develop)
    frozen = tmp_path / "repertoire.json"
    trajectory.freeze_repertoire(campaign, frozen)
    repertoire = trajectory.load_repertoire(frozen)
    use_tasks = ["ad01-w0-within-sw-00", "ad01-w0-transfer-sw-00",
                 "ad01-w0-transfer-gr-00"]
    records = trajectory.run_use(repertoire, 0, "I", use_tasks,
                                 {"tokens": 0, "sandbox_ops": 0},
                                 policy=first_eligible)
    assert len(records) == 3
    by_task = {r["task_id"]: r for r in records}
    for task_id in ("ad01-w0-within-sw-00", "ad01-w0-transfer-sw-00"):
        record = by_task[task_id]
        assert checker._verify_record(record, checker.worlds.FROZEN_DIR,
                                      []) == [], task_id
        assert record["selected"] == "seed-sw-greedy"
        assert record["executed"] == "seed-sw-greedy"
        assert record["fallback_reason"] == ""
        assert record["verdict"] == "preserved"
    graph = by_task["ad01-w0-transfer-gr-00"]
    assert graph["status"] == "refused"
    assert graph["selected"] == "refused"
    assert graph["executed"] == "refused"
    assert graph["output"] == {}
    assert graph["costs"]["witness_queries"] == 0
    assert "cannot answer a graph task" in graph["fallback_reason"]


def test_cost_union_covers_acquisition_and_use_once(tmp_path):
    from experiments.ad01 import trajectory
    campaign = trajectory.run_campaign(0, "I", CHARTER, dict(CAPS),
                                       tasks=["ad01-w0-dev-sw-00"])
    frozen = tmp_path / "repertoire.json"
    trajectory.freeze_repertoire(campaign, frozen)
    repertoire = trajectory.load_repertoire(frozen)
    use_tasks = ["ad01-w0-within-sw-00", "ad01-w0-transfer-sw-00"]
    records = trajectory.run_use(repertoire, 0, "I", use_tasks,
                                 {"tokens": 0, "sandbox_ops": 0},
                                 policy=first_eligible)
    union = trajectory.cost_union(campaign, records)
    assert union["acquisition"]["witness_queries"] == campaign["queries"]
    assert union["use"]["witness_queries"] == sum(
        r["costs"]["witness_queries"] for r in records)
    for key in ("tokens", "witness_queries", "sandbox_ops"):
        assert union["total"][key] == (union["acquisition"][key]
                                       + union["use"][key])
    assert union["mechanism"]["boundaries"] == len(campaign["boundaries"])
    assert union["mechanism"]["retained"] == sum(
        1 for e in campaign["episodes"] if e["disposition"] == "retained")
    assert "witness_queries" not in union["mechanism"]


def test_agency_envelope_separates_human_and_system():
    from experiments.ad01 import records
    envelope = records.make_envelope(
        {"objective": "o", "freeze_id": "ad01", "freeze_digest": "d",
         "seed_capabilities": [], "allocation_caps": {},
         "benefit_rule_digest": "b", "stop_conditions": {},
         "interventions": []},
        {"selected_opportunity": "q", "competing_explanation": "e",
         "diagnostic": "d", "candidate_lineage": [],
         "abandoned": [], "reuse_decision": "r",
         "next_allocation": "a"})
    assert envelope["charter"]["objective"]["set_by"] == "human"
    assert envelope["trajectory"]["selected_opportunity"][
        "set_by"] == "system"
    amended = records.record_intervention(envelope, "stop",
                                          "human halted the trajectory")
    assert amended["charter"]["interventions"]["value"][-1][
        "set_by"] == "human"


def test_protected_use_feedback_cannot_drive_development():
    from experiments.ad01 import trajectory
    feedback = {"observations": [
        {"observation_id": "use-ad01-w0-I-ad01-w0-within-sw-00",
         "task_id": "ad01-w0-within-sw-00",
         "capability_id": "seed-sw-greedy",
         "verdict": "preserved"}]}
    outcome = trajectory.admit_investigation(
        {"basis_references": ["use-ad01-w0-I-ad01-w0-within-sw-00"],
         "question": "q", "next_action": {"kind": "diagnostic",
                                "task_id": "ad01-w0-dev-sw-00"},
         "requested_resources": {}}, feedback, CHARTER)
    assert outcome["decision"] == "refused"
    assert "protected-use" in outcome["reason"]


def test_fresh_process_resumes_published_campaign(pg, tmp_path):
    import json
    import subprocess
    import sys
    dsn = pg
    run = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "run",
         "--dsn", dsn, "--world", "0", "--arm", "I", "--seq", "20",
         "--max-boundaries", "1", "--agenda-authorized", "1000",
         "--tasks", "ad01-w0-dev-sw-02,ad01-w0-dev-sw-00"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    first = json.loads(run.stdout)
    resume = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "resume",
         "--dsn", dsn, "--campaign", first["campaign_id"],
         "--max-boundaries", "6"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert resume.returncode == 0, resume.stderr
    resumed = json.loads(resume.stdout)
    assert resumed["campaign_id"] == first["campaign_id"]
    assert [b["task_id"] for b in resumed["boundaries"]] == [
        "ad01-w0-dev-sw-02", "ad01-w0-dev-sw-00"]
    assert [b["seq"] for b in resumed["boundaries"]] == [0, 1]
    assert resumed["queries"] == first["queries"] + next(
        b["spend"] for b in resumed["boundaries"] if b["seq"] == 1)


@pytest.mark.parametrize("replacement", [[], ["ad01-w0-dev-sw-01"]])
def test_resume_refuses_schedule_change_before_new_boundary(pg, replacement):
    from experiments.ad01 import trajectory
    from settlement.common import ConflictPayload
    trajectory.authorize_campaign(
        pg, trajectory.campaign_id(0, "I", 12), authorized=1000)
    first = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=["ad01-w0-dev-sw-02", "ad01-w0-dev-sw-00"],
        campaign_seq=12, dsn=pg)
    with pytest.raises(ConflictPayload):
        trajectory.resume_campaign(
            pg, first["campaign_id"], CHARTER, CAPS, tasks=replacement)
    settled, pending = trajectory._read_campaign(pg, first["campaign_id"])
    assert list(settled) == [0]
    assert pending == {}
    resumed = trajectory.resume_campaign(pg, first["campaign_id"], CHARTER, CAPS)
    assert [b["task_id"] for b in resumed["boundaries"]] == [
        "ad01-w0-dev-sw-02", "ad01-w0-dev-sw-00"]


def test_kill_after_publication_resumes_without_duplicate_spend(pg):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 12)
    trajectory.authorize_campaign(pg, cid, authorized=1000)
    first = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01"],
        campaign_seq=12, dsn=pg)
    assert first["campaign_id"] == cid
    assert len(first["boundaries"]) == 1
    resumed = trajectory.resume_campaign(
        pg, cid, CHARTER, dict(CAPS, max_boundaries=2),
        tasks=["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01"])
    seqs = [b["seq"] for b in resumed["boundaries"]]
    assert seqs == sorted(set(seqs)) == [0, 1]
    direct = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=2),
        tasks=["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01"],
        campaign_seq=13)
    assert resumed["queries"] == direct["queries"]


def test_mismatched_diagnostic_family_refuses_without_crash():
    from experiments.ad01 import trajectory

    def mismatch(experience, charter):
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "software diagnostic on a graph task",
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "software",
                                "task_id": "ad01-w0-dev-gr-00"},
                "requested_resources": {"diagnostic_queries": 1}}

    campaign = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=["ad01-w0-dev-gr-00"], propose=mismatch)
    assert campaign["episodes"][0]["disposition"] == "no-candidate"
    assert "mismatches" in campaign["episodes"][0]["fallback_reason"]


def test_mismatched_development_diagnostic_family_refuses_without_crash():
    from experiments.ad01 import trajectory

    def mismatch(experience, charter):
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "development with software diagnostic on graph",
                "next_action": {"kind": "development",
                                "diagnostic": "software",
                                "task_id": "ad01-w0-dev-gr-00"},
                "requested_resources": {"diagnostic_queries": 1}}

    campaign = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=["ad01-w0-dev-gr-00"], propose=mismatch)
    assert campaign["episodes"][0]["disposition"] == "no-candidate"
    assert "mismatches" in campaign["episodes"][0]["fallback_reason"]


def test_learner_instruction_binds_curriculum_item():
    from experiments.ad01.learner import (
        LEARNER_INSTRUCTION, LearnerRefused, validate_proposal)
    assert "curriculum_item" in LEARNER_INSTRUCTION
    with pytest.raises(LearnerRefused):
        validate_proposal(
            {"basis_references": [], "question": "q",
             "next_action": {"task_id": "ad01-w0-dev-sw-00"},
             "requested_resources": {}})


def test_learner_instruction_requires_exact_basis_refs():
    from experiments.ad01.learner import LEARNER_INSTRUCTION
    assert "character for character" in LEARNER_INSTRUCTION


def test_parse_entry_accepts_fenced_json():
    import json
    from experiments.ad01.construct import _parse_entry
    body = json.dumps({"entry": "def ENTRY(task, oracle, max_queries=16):\n    return None",
                       "notes": "n"})
    source, problem = _parse_entry("```json\n%s\n```" % body)
    assert problem == ""
    assert source.startswith("def ENTRY")


def test_unknown_scheduled_task_refuses_without_crash():
    from experiments.ad01 import trajectory
    with pytest.raises(ValueError, match="unknown task"):
        trajectory.run_campaign(
            0, "I", CHARTER, dict(CAPS, max_boundaries=1),
            tasks=["not-a-task"])
    with pytest.raises(ValueError, match="unknown task"):
        trajectory.run_use({"campaign_id": "ad01-w0-I-00", "members": []},
                           0, "I", ["not-a-task"], {})


def test_malformed_campaign_id_refuses_without_crash():
    from experiments.ad01 import trajectory
    with pytest.raises(ValueError, match="malformed campaign id"):
        trajectory.resume_campaign(
            "dbname=ec02test_adtr", "foo", CHARTER, CAPS)


def test_cli_rejects_bad_world_arm_and_campaign(capsys):
    from experiments.ad01 import cli
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--dsn", "x", "--world", "99", "--arm", "I"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--dsn", "x", "--world", "0", "--arm", "Z"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        cli.main(["resume", "--dsn", "x", "--campaign", "foo"])
    assert exc.value.code == 2


def test_acquired_repertoire_without_bytes_refuses_without_crash(tmp_path):
    import json
    from experiments.ad01 import trajectory
    frozen = tmp_path / "repertoire.json"
    frozen.write_text(json.dumps(
        {"campaign_id": "c", "queries": 0,
         "members": [{"capability_id": "acquired-sw-x", "authored": False,
                      "method_source": "", "source_digest": "zzz"}]}) + "\n")
    with pytest.raises(ValueError, match="no executable bytes"):
        trajectory.load_repertoire(frozen)
