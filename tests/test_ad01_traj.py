"""AD01 trajectory lane, first tracer: investigation proposal from experience."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DSN = os.environ.get(
    "EC02_ADTR_DSN",
    "dbname=ec02test_adtr host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"


@pytest.fixture()
def pg():
    assert "live" not in DSN
    assert DSN.split("dbname=")[1].split()[0] == "ec02test_adtr"
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
                "next_action": {"kind": "diagnostic"},
                "requested_resources": {"diagnostic_queries": 1}}
    outcome = admit_investigation(invented, EXPERIENCE, CHARTER)
    assert outcome["decision"] == "refused"
    assert "obs-never-recorded" in outcome["reason"]


def test_admit_accepts_explicit_exploratory_option():
    from experiments.ad01.trajectory import admit_investigation
    exploratory = {"basis_references": [],
                   "question": "unknown witness behavior on transfer tasks",
                   "unknown": "whether reversed priority preserves the witness",
                   "next_action": {"kind": "diagnostic"},
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
    trajectory.ensure_campaign(pg, cid, 0, "I", CHARTER, CAPS)
    decision = {"action": "investigate", "question": "q0",
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "diagnostic_resolves",
                                "task_id": "ad01-w0-dev-sw-00"}}
    did = trajectory.record_decision(pg, cid, 0, decision)
    resumed = trajectory.resume_campaign(pg, cid, CHARTER, CAPS)
    assert resumed["campaign_id"] == cid
    assert resumed["boundaries"][0]["decision_id"] == did
    assert resumed["queries"] == resumed["boundaries"][0]["spend"]
    direct = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=["ad01-w0-dev-sw-00"], campaign_seq=11)
    assert resumed["queries"] == direct["queries"]


def test_i_and_r_arms_run_one_world_without_sharing():
    from experiments.ad01 import rotation, trajectory
    order = [s["task_id"] for s in rotation.r_schedule(0)]
    arm_i = trajectory.run_campaign(0, "I", CHARTER, dict(CAPS),
                                    tasks=[t for t in order
                                           if "-sw-" in t])
    arm_r = trajectory.run_campaign(0, "R", CHARTER, dict(CAPS),
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
    assert campaign["episodes"][0]["disposition"] in ("retained",
                                                      "no-candidate")


def test_use_phase_selects_frozen_repertoire_and_falls_back(tmp_path):
    from experiments.ad01 import checker, trajectory
    campaign = trajectory.run_campaign(0, "I", CHARTER, dict(CAPS),
                                       tasks=["ad01-w0-dev-sw-00"])
    frozen = tmp_path / "repertoire.json"
    trajectory.freeze_repertoire(campaign, frozen)
    repertoire = trajectory.load_repertoire(frozen)
    use_tasks = ["ad01-w0-within-sw-00", "ad01-w0-transfer-sw-00",
                 "ad01-w0-transfer-gr-00"]
    records = trajectory.run_use(repertoire, 0, "I", use_tasks,
                                 {"tokens": 0, "sandbox_ops": 0})
    assert len(records) == 3
    for record in records:
        assert checker._verify_record(record, checker.worlds.FROZEN_DIR,
                                      []) == []
        assert record["requested"] and record["selected"]
        assert record["executed"] == record["selected"]
    by_task = {r["task_id"]: r for r in records}
    assert by_task["ad01-w0-within-sw-00"]["selected"] != "incumbent"
    fallback = by_task["ad01-w0-transfer-gr-00"]
    assert fallback["selected"] == "incumbent"
    assert fallback["fallback_reason"]


def test_cost_union_covers_acquisition_and_use_once(tmp_path):
    from experiments.ad01 import trajectory
    campaign = trajectory.run_campaign(0, "I", CHARTER, dict(CAPS),
                                       tasks=["ad01-w0-dev-sw-00"])
    frozen = tmp_path / "repertoire.json"
    trajectory.freeze_repertoire(campaign, frozen)
    repertoire = trajectory.load_repertoire(frozen)
    use_tasks = ["ad01-w0-within-sw-00", "ad01-w0-transfer-sw-00"]
    records = trajectory.run_use(repertoire, 0, "I", use_tasks,
                                 {"tokens": 0, "sandbox_ops": 0})
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
         "question": "q", "next_action": {"kind": "diagnostic"},
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
         "--max-boundaries", "1",
         "--tasks", "ad01-w0-dev-sw-00,ad01-w0-dev-sw-01"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    first = json.loads(run.stdout)
    resume = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "resume",
         "--dsn", dsn, "--campaign", first["campaign_id"],
         "--max-boundaries", "2",
         "--tasks", "ad01-w0-dev-sw-00,ad01-w0-dev-sw-01"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert resume.returncode == 0, resume.stderr
    resumed = json.loads(resume.stdout)
    assert resumed["campaign_id"] == first["campaign_id"]
    assert [b["seq"] for b in resumed["boundaries"]] == [0, 1]
    assert resumed["queries"] == first["queries"] + next(
        b["spend"] for b in resumed["boundaries"] if b["seq"] == 1)


def test_kill_after_publication_resumes_without_duplicate_spend(pg):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 12)
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
