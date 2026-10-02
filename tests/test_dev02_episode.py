"""D02 seam regressions (D02-001..D02-004, CTX-08, CTX-10).

Proves the repaired episode path through real entry points on real
PostgreSQL + LocalLauncher subprocesses. Model inference is doubled with an
explicit local double (deterministic); every broker/sandbox/store effect is
real. No live inference here.

Supersedes reviews/probes/test_development_01_readiness.py: each
characterization probe's gap is closed below and recorded in that file's
header on retirement.
"""

from __future__ import annotations

import json
import subprocess
import sys

sys.path.insert(0, "experiments")
sys.path.insert(0, "tests")

import pytest

from fault_tasks import BY_ID
from test_dev01_episode import CANDIDATE_CODE
from test_s3_helpers import EXPERIMENTS, seed_env

from settlement import broker, capabilities, db, development, evidence, experiment, store
from settlement.common import Command, SettlementError
from settlement.gateway import GatewayAdapter, GatewayError, ModelResponse, Usage
from settlement.launcher_local import LocalLauncher

from conftest import unique

GRADER = str(EXPERIMENTS / "run_tests.py")
DEV_TASK = BY_ID["dev-sum"]
TRIGGERS = [{"task_id": "dev-sum", "family": "off_by_one"}]
POLICY = {"families": ["off_by_one"], "material": "development-only",
          "applicability": {"family": "off_by_one"}}
FAILING_CASES = [{"fn": "f", "args": [], "expected": "no-such-value"}]


class SeamDouble(GatewayAdapter):
    def __init__(self, code=CANDIDATE_CODE, mode="ok"):
        self.code = code
        self.mode = mode
        self.calls: list[dict] = []

    def check_discovery(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        try:
            body = json.loads(request.messages[-1]["content"])
        except (ValueError, IndexError, TypeError):
            return GatewayError("protocol", "seam double needs a JSON body",
                                False, request.operation_id)
        if isinstance(body, dict) and body.get("arm"):
            self.calls.append({"arm": body["arm"],
                               "task_id": body.get("task_id")})
            return ModelResponse(
                request.operation_id,
                json.dumps({"dev_attempt": body.get("task_id")}),
                {"simulated": True},
                Usage(input_tokens=20, output_tokens=40,
                      charge_units=60), "stop")
        phase = body.get("phase") if isinstance(body, dict) else None
        if phase not in ("diagnose", "construct"):
            return GatewayError("protocol", "seam double needs a known phase",
                                False, request.operation_id)
        self.calls.append(body)
        if phase == "diagnose":
            payload = {
                "explanations": [{"id": "e1", "text": "boundary handling"}],
                "intervention": {"action": "inclusive-bound repair procedure"}}
        elif self.mode == "no-candidate":
            payload = {"no_candidate": "no worthwhile change identified"}
        else:
            payload = {"code": self.code}
        return ModelResponse(request.operation_id, json.dumps(payload),
                             {"simulated": True},
                             Usage(input_tokens=40, output_tokens=200,
                                   charge_units=240), "stop")

    def cancel(self, operation_id):
        return True


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _cmd(tag):
    return Command(request_id=f"{tag}-{unique('c')}", payload={})


def _admit_panel(dsn, tag):
    env = seed_env(dsn, tag)
    ep = f"{tag}-ep"
    development.observe(dsn, _cmd(f"{tag}-obs"), episode_id=ep,
                        investigation_id=env["investigation_id"],
                        trigger_refs=TRIGGERS, bottleneck="range excludes n")
    development.propose(dsn, _cmd(f"{tag}-prop"), episode_id=ep,
                        predicted_effect="inclusive bound fixes dev-sum")
    policy = development.panel_policy_for(
        ["dev-sum"], ["panel-triangular"], ["transfer-discount"],
        families=["off_by_one"])
    development.admit(dsn, _cmd(f"{tag}-adm"), episode_id=ep,
                      reference_version="baseline-v0", access_policy=POLICY,
                      allocation_id=env["allocation_id"], panel_policy=policy)
    return env, ep, policy


def _dev_tasks(cases=None):
    return [{"id": "dev-sum", "family": "off_by_one",
             "broken": DEV_TASK["broken"],
             "cases": cases if cases is not None else DEV_TASK["cases"]}]


def _collect(dsn, tag, ep, launcher, double=None, cases=None):
    return development.collect_experience(
        dsn, _cmd(f"{tag}-ex"), double or SeamDouble(), launcher,
        episode_id=ep, model="scripted", dev_tasks=_dev_tasks(cases),
        grader_path=GRADER)


def _diagnose(dsn, tag, ep, double=None):
    return development.diagnose(dsn, _cmd(f"{tag}-dg"), double or SeamDouble(),
                                episode_id=ep, model="scripted")


def _construct(dsn, tag, ep, launcher, tmp_roots, double=None):
    return development.construct(
        dsn, _cmd(f"{tag}-co"), double or SeamDouble(), launcher,
        episode_id=ep, model="scripted",
        artifacts_root=tmp_roots["artifacts"], staging_root=tmp_roots["staging"],
        version_stem=f"{tag}-fix", family="off_by_one")


def _bind_episode(dsn, tag, ep, launcher, tmp_roots, double=None):
    _diagnose(dsn, tag, ep, double)
    _construct(dsn, tag, ep, launcher, tmp_roots, double)
    development.check(dsn, _cmd(f"{tag}-ck"), launcher, episode_id=ep,
                      artifacts_root=tmp_roots["artifacts"],
                      grader_path=GRADER, tasks=_dev_tasks())
    row = development.get_episode(dsn, ep)
    panel = dict(row["comparison_policy"]["panel"])
    panel["evaluator_version"] = "v1"
    development.freeze_comparison(dsn, _cmd(f"{tag}-frz"), episode_id=ep,
                                  policy=panel)
    development.select(dsn, _cmd(f"{tag}-sel"), episode_id=ep)
    return development.bind(dsn, _cmd(f"{tag}-bnd"), episode_id=ep)


def test_diagnosis_refuses_without_batch(migrated_db, launcher):
    dsn = migrated_db
    tag = unique("d02")
    _, ep, _ = _admit_panel(dsn, tag)
    with pytest.raises(SettlementError, match="refused"):
        _diagnose(dsn, tag, ep)
    assert broker.read_operation(dsn, f"{ep}-explain") is None


def test_batch_materializes_resolved_experience(migrated_db, launcher):
    dsn = migrated_db
    tag = unique("d02")
    _, ep, _ = _admit_panel(dsn, tag)
    double = SeamDouble()
    gathered = _collect(dsn, tag, ep, launcher, double)
    assert gathered["claims"] == [f"{ep}-exp-dev-sum-claim"]
    out = development.diagnose(dsn, _cmd(f"{tag}-dg"), double, episode_id=ep,
                               model="scripted")
    assert out["state"] == "diagnosed"
    assert out["packet_id"].startswith("pkt_")
    prompt = next(call for call in double.calls if call.get("phase") == "diagnose")
    assert prompt["packet_id"] == out["packet_id"]
    assert "experience" not in prompt
    assert "dev-sum" in prompt["packet"]
    assert "grade_op" in prompt["packet"]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT proposition FROM claims WHERE id = %s",
                        (gathered["claims"][0],))
            proposition = cur.fetchone()[0]
            conn.commit()
    assert proposition["broken"] == DEV_TASK["broken"]
    assert proposition["cases"] == DEV_TASK["cases"]


def test_construct_packet_binds_and_states_contract(migrated_db, launcher,
                                                    tmp_roots):
    dsn = migrated_db
    tag = unique("d02")
    _, ep, _ = _admit_panel(dsn, tag)
    double = SeamDouble()
    _collect(dsn, tag, ep, launcher, double)
    _diagnose(dsn, tag, ep, double)
    out = _construct(dsn, tag, ep, launcher, tmp_roots, double)
    assert out["status"] == "constructed"
    prompt = next(call for call in double.calls if call.get("phase") == "construct")
    assert prompt["packet_id"] == out["packet_id"]
    assert prompt["response_shape"]["code"]
    assert "--selftest" in prompt["packet"]
    assert "candidate.py" in prompt["packet"]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT rendered_digest FROM packet_invocations"
                        " WHERE packet_id = %s AND operation_id = %s",
                        (out["packet_id"], out["model_op"]))
            row = cur.fetchone()
            conn.commit()
    assert row is not None and row[0] == out["rendered_digest"]


def _run_entry_episode(dsn, tag, env, launcher, tmp_roots, double, cases=None,
                       prefix=None):
    from run_dev_episode import _run_episode
    from types import SimpleNamespace

    prefix = prefix or f"{tag}-px"
    by_id = {"dev-sum": {"id": "dev-sum", "family": "off_by_one",
                         "broken": DEV_TASK["broken"],
                         "cases": cases if cases is not None
                         else DEV_TASK["cases"]}}
    args = SimpleNamespace(episode=f"{tag}-ep", investigation=env["investigation_id"],
                           reference_version="baseline-v0",
                           evaluator_version="v1",
                           artifacts_root=tmp_roots["artifacts"])
    return _run_episode(dsn, args, double, launcher, "scripted",
                        env["allocation_id"], prefix, ["dev-sum"],
                        [by_id["dev-sum"]], by_id, ["panel-triangular"],
                        ["transfer-discount"])


def test_rejected_candidate_never_reaches_comparison(migrated_db, launcher,
                                                     tmp_roots):
    dsn = migrated_db
    tag = unique("d02")
    env = seed_env(dsn, tag)
    double = SeamDouble()
    ep = _run_entry_episode(dsn, tag, env, launcher, tmp_roots, double,
                            cases=FAILING_CASES)
    assert ep["checked"]["grade_outcome"] == "failure"
    assert ep["selected"]["selection"]["decision"] == "reject"
    assert ep["bindings"]["version_id"] is None
    assert ep["synthesize"]([{"broken": DEV_TASK["broken"]}]) is None
    assert ep["fixer_version"] == ""
    report = experiment.run_abcs(
        dsn, launcher=launcher, artifacts_root=tmp_roots["artifacts"],
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"],
        tasks=[{**BY_ID[i], "cases": (FAILING_CASES if i == "dev-sum"
                                      else BY_ID[i]["cases"])}
               for i in ("dev-sum", "panel-triangular", "transfer-discount")],
        dev_ids=["dev-sum"], panel_ids=["panel-triangular"],
        transfer_ids=["transfer-discount"],
        lessons={"off_by_one": "test lesson"}, gateway=double,
        grader_path=GRADER, protocol_prefix=f"{tag}-px",
        fixer_version=ep["fixer_version"], simulated=True, model="scripted",
        synthesize=ep["synthesize"],
        dev_transcripts=ep["gathered"]["transcripts"],
        panel_protocol={"eval_protocol": ep["panel_eval_protocol"],
                        "groups": ep["panel_groups"],
                        "evaluator_version": "v1"})
    assert report["development"]["reused"] == ["dev-sum"]
    assert any("no-applicable-method" in mark
               for mark in report.get("abstentions", []))


def test_no_candidate_yields_no_comparison_candidate(migrated_db, launcher,
                                                     tmp_roots):
    dsn = migrated_db
    tag = unique("d02")
    env = seed_env(dsn, tag)
    ep = _run_entry_episode(dsn, tag, env, launcher, tmp_roots,
                            SeamDouble(mode="no-candidate"))
    assert ep["built"] == {}
    assert ep["bindings"] == {}
    assert ep["synthesize"]([{"broken": DEV_TASK["broken"]}]) is None
    assert ep["fixer_version"] == ""


def test_panel_frozen_before_feedback(migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02")
    _, ep, policy = _admit_panel(dsn, tag)
    panel_pid = development.panel_protocol_id(ep)
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT task_groups, candidate_version FROM trial_protocols"
                        " WHERE id = %s", (panel_pid,))
            row = cur.fetchone()
            conn.commit()
    assert row is not None
    assert row[1] == ""
    names = {group["name"]: tuple(group.get("tasks") or []) for group in row[0]}
    assert names["development"] == ("dev-sum",)
    assert names["panel"] == ("panel-triangular",)
    _collect(dsn, tag, ep, launcher)
    _diagnose(dsn, tag, ep)
    _construct(dsn, tag, ep, launcher, tmp_roots)
    development.check(dsn, _cmd(f"{tag}-ck"), launcher, episode_id=ep,
                      artifacts_root=tmp_roots["artifacts"],
                      grader_path=GRADER, tasks=_dev_tasks())
    divergent = json.loads(json.dumps(policy))
    divergent["task_groups"][1]["tasks"] = ["panel-swap"]
    with pytest.raises(SettlementError, match="differ"):
        development.freeze_comparison(dsn, _cmd(f"{tag}-bad"), episode_id=ep,
                                      policy=divergent)
    matched = dict(policy)
    matched["evaluator_version"] = "v1"
    development.freeze_comparison(dsn, _cmd(f"{tag}-frz"), episode_id=ep,
                                  policy=matched)
    development.select(dsn, _cmd(f"{tag}-sel"), episode_id=ep)
    bound = development.bind(dsn, _cmd(f"{tag}-bnd"), episode_id=ep)
    bound_pid = bound["bindings"]["comparison_protocol"]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT candidate_version, supersedes FROM trial_protocols"
                        " WHERE id = %s", (bound_pid,))
            brow = cur.fetchone()
            cur.execute("SELECT supersedes FROM trial_protocols WHERE id = %s",
                        (development.eval_protocol_id(ep),))
            erow = cur.fetchone()
            conn.commit()
    assert brow[0] == bound["bindings"]["version_id"]
    assert brow[1] == development.eval_protocol_id(ep)
    assert erow[0] == panel_pid


def test_subsequent_use_invokes_selected_version(migrated_db, launcher,
                                                 tmp_roots):
    dsn = migrated_db
    tag = unique("d02")
    env, ep, _ = _admit_panel(dsn, tag)
    _collect(dsn, tag, ep, launcher)
    bound = _bind_episode(dsn, tag, ep, launcher, tmp_roots)
    assert bound["bindings"]["version_id"]
    version = bound["bindings"]["version_id"]
    capabilities.save_router_policy(
        dsn, _cmd(f"{tag}-router"), version=f"{tag}-router",
        mapping={"off_by_one": version})
    task = BY_ID["panel-triangular"]
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tmp_roots["artifacts"], launcher=launcher,
        adapter=SeamDouble(), model="scripted",
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], episode_id=ep,
        bindings=bound["bindings"],
        use_task={"id": task["id"], "family": task["family"],
                  "broken": task["broken"], "cases": task["cases"]},
        grader_path=GRADER, protocol_prefix=f"{tag}-px",
        prior_exposure="panel-comparison",
        disposition={"released": {"off_by_one": version},
                     "router_policies": {"off_by_one": f"{tag}-router"},
                     "trial": False})
    assert use["method"] == "selected"
    assert use["version_id"] == version
    assert use["outcome"] in ("success", "failure")
    assert use["ops"]["invoke_op"].startswith("invoke-")
    assert use["prior_exposure"] == "panel-comparison"
    assert isinstance(use["pending_operations"], list)
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT payload FROM domain_events WHERE kind = %s"
                        " AND payload->>'episode_id' = %s",
                        ("development.subsequent_use", ep))
            rows = cur.fetchall()
            conn.commit()
    assert len(rows) == 1 and rows[0][0]["outcome"] == use["outcome"]


def test_reject_use_follows_incumbent_path(migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02")
    env = seed_env(dsn, tag)
    ep = _run_entry_episode(dsn, tag, env, launcher, tmp_roots, SeamDouble(),
                            cases=FAILING_CASES)
    assert ep["bindings"]["version_id"] is None
    task = BY_ID["transfer-discount"]
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tmp_roots["artifacts"], launcher=launcher,
        adapter=SeamDouble(), model="scripted",
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], episode_id=ep["episode_id"],
        bindings=ep["bindings"],
        use_task={"id": task["id"], "family": task["family"],
                  "broken": task["broken"], "cases": task["cases"]},
        grader_path=GRADER, protocol_prefix=f"{tag}-px",
        prior_exposure="transfer-comparison")
    assert use["method"] == "incumbent"
    assert use["version_id"] == ""
    assert use["outcome"] in ("success", "failure")
    assert "model_op" in use["ops"]


def test_fresh_process_use_records_receipts(migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02")
    env, ep, _ = _admit_panel(dsn, tag)
    _collect(dsn, tag, ep, launcher)
    bound = _bind_episode(dsn, tag, ep, launcher, tmp_roots)
    assert bound["bindings"]["version_id"]
    version = bound["bindings"]["version_id"]
    capabilities.save_router_policy(
        dsn, _cmd(f"{tag}-router"), version=f"{tag}-router",
        mapping={"off_by_one": version})
    cmd = [sys.executable, str(EXPERIMENTS / "run_use.py"),
           "--dsn", dsn, "--artifacts-root", tmp_roots["artifacts"],
           "--allocation", env["allocation_id"],
           "--investigation", env["investigation_id"], "--episode", ep,
           "--use-task", "panel-triangular",
           "--prior-exposure", "panel-comparison",
           "--protocol-prefix", f"{tag}-px",
           "--disposition-json", json.dumps(
               {"released": {"off_by_one": version},
                "router_policies": {"off_by_one": f"{tag}-router"},
                "trial": False})]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    use = json.loads(proc.stdout)
    assert use["method"] == "selected"
    assert use["version_id"] == version
    assert use["outcome"] in ("success", "failure")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM trial_protocols WHERE id = %s",
                        (use["protocol_id"],))
            assert cur.fetchone() is not None
            cur.execute("SELECT payload FROM domain_events WHERE kind = %s"
                        " AND payload->>'episode_id' = %s",
                        ("development.subsequent_use", ep))
            rows = cur.fetchall()
            conn.commit()
    assert len(rows) == 1


def test_release_orchestrator_never_invokes(migrated_db):
    dsn = migrated_db
    names = ("get_version", "quarantine_status", "scoped_release",
             "save_router_policy", "route", "pin_capability")
    saved = {name: getattr(experiment.capabilities, name) for name in names}
    saved_worker = experiment._fresh_worker
    experiment._fresh_worker = lambda *args, **kwargs: "fresh-attempt"
    calls = []
    for name, result in {
        "get_version": {"applicability": {"family": "off_by_one"}},
        "quarantine_status": None, "scoped_release": {}, "save_router_policy": {},
        "route": {"version_id": "candidate-s0"}, "pin_capability": {},
    }.items():
        def action(*args, _name=name, _result=result, **kwargs):
            calls.append(_name)
            return _result
        setattr(experiment.capabilities, name, action)
    try:
        groups = ("panel-C", "transfer-C")
        result = experiment._maybe_release(
            dsn, artifacts_root="/tmp", allocation_id="allocation",
            investigation_id="inv", protocol_prefix="probe",
            evaluator_version="v1", simulated=False,
            protocols={group: group for group in groups},
            group_candidate={group: "candidate-s0" for group in groups},
            group_families={group: ["off_by_one"] for group in groups},
            verdicts={group: {"label": "observed-gain"} for group in groups})
    finally:
        for name in names:
            setattr(experiment.capabilities, name, saved[name])
        experiment._fresh_worker = saved_worker
    assert all(rel["status"] == "released" for rel in result.values())
    assert "route" in calls and "pin_capability" in calls
    assert "invoke" not in calls and "infer" not in calls


def test_dev_batch_runs_once(migrated_db, launcher):
    dsn = migrated_db
    tag = unique("d02")
    env = seed_env(dsn, tag)
    double = SeamDouble()
    experiment._freeze_eval_protocol(dsn, f"{tag}-px-dev", "", "dev-heldout",
                                     "v1")
    first = experiment._run_development(
        dsn, launcher=launcher, adapter=double, model="scripted",
        workdir=None, artifacts_root="/tmp", allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"],
        tasks=[{**BY_ID["dev-sum"], "cases": DEV_TASK["cases"]}],
        dev_ids=["dev-sum"], grader_path=GRADER,
        protocol_prefix=f"{tag}-px", supplied_lessons={"off_by_one": "x"},
        method_version="m", protocols=[f"{tag}-px-dev"], synthesize=None,
        dev_transcripts=None)
    assert first["reused"] == []
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM operations WHERE id LIKE %s",
                        (f"model-{tag}-px-DEV-%",))
            before = cur.fetchone()[0]
            conn.commit()
    second = experiment._run_development(
        dsn, launcher=launcher, adapter=double, model="scripted",
        workdir=None, artifacts_root="/tmp", allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"],
        tasks=[{**BY_ID["dev-sum"], "cases": DEV_TASK["cases"]}],
        dev_ids=["dev-sum"], grader_path=GRADER,
        protocol_prefix=f"{tag}-px", supplied_lessons={"off_by_one": "x"},
        method_version="m", protocols=[f"{tag}-px-dev"], synthesize=None,
        dev_transcripts={"dev-sum": first["transcripts"]["dev-sum"]})
    assert second["reused"] == ["dev-sum"]
    assert second["outcomes"] == first["outcomes"]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM operations WHERE id LIKE %s",
                        (f"model-{tag}-px-DEV-%",))
            after = cur.fetchone()[0]
            conn.commit()
    assert after == before


def _challenge_episode(dsn, tag, env, claim_id=None):
    ep = f"{tag}-ep"
    refs = [dict(TRIGGERS[0])]
    if claim_id:
        refs[0]["claim_id"] = claim_id
    development.observe(dsn, _cmd(f"{tag}-obs"), episode_id=ep,
                        investigation_id=env["investigation_id"],
                        trigger_refs=refs, bottleneck="range excludes n")
    development.propose(dsn, _cmd(f"{tag}-prop"), episode_id=ep,
                        predicted_effect="inclusive bound fixes dev-sum")
    policy = development.panel_policy_for(
        ["dev-sum"], ["panel-triangular"], ["transfer-discount"],
        families=["off_by_one"])
    development.admit(dsn, _cmd(f"{tag}-adm"), episode_id=ep,
                      reference_version="baseline-v0", access_policy=POLICY,
                      allocation_id=env["allocation_id"], panel_policy=policy)
    return ep


def _construct_decision(ep, investigation_id, budget):
    return {"decision_kind": "construct", "purpose": "challenge",
            "required_inputs": [], "allowed_actions": [],
            "access": "candidate", "budget": budget,
            "current_versions": {"reference_version": "baseline-v0"},
            "candidate_contract": {
                "invocation": {"entry": "candidate.py",
                               "verify_args": ["--selftest"]},
                "applicability": {"family": "off_by_one"},
                "effect": {"sandbox": "local-process"}, "resource": {}},
            "investigation_id": investigation_id, "episode_id": ep}


def test_challenge_panel_expectations(migrated_db, launcher):
    import dev02_challenge

    from settlement import context

    assert [scenario["id"] for scenario in dev02_challenge.SCENARIOS] == [
        "missing-content", "counterexample-preserved",
        "superseded-conclusion-alternative-route", "oversized-mandatory-content",
        "restart-unresolved-operation", "rejected-candidate-incumbent-use"]
    dsn = migrated_db
    tag = unique("d02")
    env = seed_env(dsn, tag)
    claim_id = f"{tag}-ep-exp-dev-sum-claim"
    ep = _challenge_episode(dsn, tag, env, claim_id)
    double = SeamDouble()
    gathered = _collect(dsn, tag, ep, launcher, double)
    assert gathered["claims"] == [claim_id]
    attempt_id = f"{ep}-exp-dev-sum-worker"
    obs2 = evidence.register_observation(
        dsn, _cmd(f"{tag}-obs2"), attempt_id, {"task_id": "dev-sum"},
        source_identity="sensor")
    evidence.admit_warrant(
        dsn, _cmd(f"{tag}-w2"), f"{tag}-w2", claim_id, "second-look", "v1",
        [[(obs2.data["receipt_id"], "observation")]])
    evidence.register_opposition(
        dsn, _cmd(f"{tag}-opp"), f"{tag}-opp", claim_id, "opposition",
        {"note": "fails on empty range"})
    _diagnose(dsn, tag, ep, double)
    decision = _construct_decision(
        ep, env["investigation_id"],
        {"input_chars": 24000, "output_reserve": 2000})
    ready = context.build_packet(dsn, _cmd(f"{tag}-pkt"), decision=decision)
    assert ready.data["outcome"] == "ready"
    bundle = next(bundle for bundle in ready.data["evidence_bundles"]
                  if bundle["claim_id"] == claim_id)
    assert any(opposition["id"] == f"{tag}-opp"
               for opposition in bundle["opposition"])
    assert bundle["selected_route"]["derivation"] == f"{ep}-exp-dev-sum-warrant"
    evidence.retract(dsn, _cmd(f"{tag}-retract"),
                     f"obs_{ep}-exp-dev-sum-obs", "superseded observation")
    failed_over = context.build_packet(dsn, _cmd(f"{tag}-pkt2"),
                                       decision=decision)
    assert failed_over.data["outcome"] == "ready"
    switched = next(bundle for bundle in failed_over.data["evidence_bundles"]
                    if bundle["claim_id"] == claim_id)
    assert switched["selected_route"]["derivation"] == f"{tag}-w2"
    assert any("blocked" in qual for qual in switched["qualifications"])
    small = context.build_packet(
        dsn, _cmd(f"{tag}-small"),
        decision={**decision,
                  "budget": {"input_chars": 120, "output_reserve": 2000}})
    assert small.data["outcome"] == "needs_information"
    assert any("stage a narrower" in gap.get("proposal", "")
               for gap in small.data["gaps"])


def test_resume_packet_surfaces_unresolved_operation(migrated_db, launcher,
                                                     tmp_roots):
    from settlement import context

    dsn = migrated_db
    tag = unique("d02")
    env, ep, _ = _admit_panel(dsn, tag)
    _collect(dsn, tag, ep, launcher)
    _bind_episode(dsn, tag, ep, launcher, tmp_roots)
    pending_op = f"{tag}-pending-op"
    broker.ensure_operation(
        dsn, operation_id=pending_op, effect="sandbox-exec",
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 10_000, "max_output_bytes": 1024},
        allocation_id=env["allocation_id"],
        attempt_id=f"{ep}-exp-dev-sum-worker")
    store.advance_dispatch(dsn, Command(
        request_id=f"{tag}-adv-{unique('c')}",
        payload={"operation_id": pending_op,
                 "launcher_id": LocalLauncher.launcher_id,
                 "execution_version": "exec-default"}))
    assert broker.read_operation(dsn, pending_op)["dispatch_state"] == \
        "dispatching"
    context.save_continuation(
        dsn, _cmd(f"{tag}-cont"), tmp_roots["artifacts"],
        env["investigation_id"], f"{ep}-exp-dev-sum-worker", "comp-v1",
        position={}, completed_refs=[], unresolved_ops=[pending_op],
        obligations={}, next_decision={"action": "invoke bound method"})
    decision = {"decision_kind": "resume", "purpose": "challenge resume",
                "required_inputs": [], "allowed_actions": [],
                "access": "candidate",
                "budget": {"input_chars": 24000, "output_reserve": 2000},
                "current_versions": {}, "investigation_id": env["investigation_id"],
                "episode_id": ep}
    made = context.build_packet(dsn, _cmd(f"{tag}-resume"), decision=decision)
    assert made.data["outcome"] == "ready"
    pending = made.data["mandatory_content"]["pending_operations"]["pending"]
    assert any(op["id"] == pending_op for op in pending)
    assert made.data["mandatory_content"]["next_decision"][
        "next_decision"]["action"] == "invoke bound method"
