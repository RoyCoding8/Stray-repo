"""D-EP episode-core regressions (DEV-01..DEV-04, episode half of DEV-09).

Deterministic doubles only; every broker/sandbox effect is real
(PostgreSQL + LocalLauncher subprocesses). No live inference here: scripted
responses carry ``simulated: True`` receipts and one live-like adapter
proves the provenance flag reflects the adapter, not the call path.
"""

from __future__ import annotations

import hashlib
import json
import sys

sys.path.insert(0, "experiments")
sys.path.insert(0, "tests")

import pytest

from fault_tasks import BY_ID
from test_s3_helpers import EXPERIMENTS, seed_env

from settlement import artifacts, broker, capabilities, db, development, experiment, store, trials
from settlement.common import Command, SettlementError
from settlement.gateway import GatewayAdapter, GatewayError, GatewayStatus, ModelResponse, Usage
from settlement.launcher_local import LocalLauncher

from conftest import unique

GRADER = str(EXPERIMENTS / "run_tests.py")
DEV_TASK = BY_ID["dev-sum"]
CASES = DEV_TASK["cases"]
REPAIR_PROBE = {"broken": DEV_TASK["broken"], "expected": DEV_TASK["fixed"]}
TASKS = [{"id": "dev-sum", "broken": DEV_TASK["broken"],
          "cases": DEV_TASK["cases"]}]

TRIGGERS = [{"task_id": "dev-sum", "family": "off_by_one",
             "evidence": "repeated range(n) exclusion"}]
POLICY = {"families": ["off_by_one"], "material": "development-only",
          "applicability": {"family": "off_by_one"}}

CANDIDATE_CODE = (
    "def sum_to(n):\n"
    '    """Sum 1..n inclusive."""\n'
    "    return sum(range(n + 1))\n"
    "import json as _json\n"
    "import sys as _sys\n"
    "def _repair(source):\n"
    '    return source.replace("range(n)", "range(n + 1)")\n'
    "def main(argv):\n"
    '    if argv == ["--selftest"]:\n'
    '        print(_json.dumps({"status": "ok", "data": {"repairs": 1}}))\n'
    "        return 0\n"
    "    if len(argv) != 2:\n"
    '        print(_json.dumps({"status": "error", "data": {},'
    ' "error": "need [input output]"}))\n'
    "        return 2\n"
    "    with open(argv[0], encoding='utf-8') as handle:\n"
    "        source = handle.read()\n"
    "    with open(argv[1], 'w', encoding='utf-8') as handle:\n"
    "        handle.write(_repair(source))\n"
    '    print(_json.dumps({"status": "ok", "data": {"repaired": True}}))\n'
    "    return 0\n"
    'if __name__ == "__main__":\n'
    "    raise SystemExit(main(_sys.argv[1:]))\n"
)

PROBE_CODE = "print('{\"status\": \"ok\", \"data\": {}}')"


class EpisodeDouble(GatewayAdapter):
    def __init__(self, code=CANDIDATE_CODE, explanations=2, mode="ok", meta=None):
        self.code = code
        self.explanations = explanations
        self.mode = mode
        self.meta = {"simulated": True} if meta is None else dict(meta)
        self.calls: list[dict] = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        try:
            body = json.loads(request.messages[-1]["content"])
        except (ValueError, IndexError, TypeError):
            return GatewayError("protocol", "episode double needs a JSON body",
                                False, request.operation_id)
        if body.get("arm") in ("DEV", "A"):
            self.calls.append({"arm": body["arm"],
                               "task_id": body.get("task_id")})
            return ModelResponse(
                request.operation_id,
                json.dumps({"dev_attempt": body.get("task_id")}),
                dict(self.meta),
                Usage(input_tokens=20, output_tokens=40,
                      charge_units=60), "stop")
        phase = body.get("phase")
        if phase not in ("diagnose", "construct"):
            return GatewayError("protocol", "episode double needs a known phase",
                                False, request.operation_id)
        self.calls.append(body)
        if phase == "diagnose":
            payload = {
                "explanations": [{"id": f"e{i + 1}", "text": f"hypothesis {i + 1}"}
                                 for i in range(self.explanations)],
                "intervention": {"action": "inclusive-bound repair procedure"}}
        elif self.mode == "no-candidate":
            payload = {"no_candidate": "no worthwhile change identified"}
        elif self.mode == "invalid":
            payload = {"code": 42}
        else:
            payload = {"code": self.code}
        return ModelResponse(request.operation_id, json.dumps(payload),
                             dict(self.meta),
                             Usage(input_tokens=40, output_tokens=200,
                                   charge_units=240), "stop")

    def cancel(self, operation_id):
        return True


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _cmd(tag):
    return Command(request_id=f"{tag}-{unique('c')}", payload={})


PANEL_DEV = ["dev-sum"]
PANEL_PANEL = ["panel-triangular"]
PANEL_TRANSFER = ["transfer-discount"]


def _admit(dsn, tag, allocation_id=None, investigation_id=None, panel=False,
           **limits):
    env = seed_env(dsn, tag)
    allocation = allocation_id or env["allocation_id"]
    investigation = investigation_id or env["investigation_id"]
    ep = f"{tag}-ep"
    development.observe(dsn, _cmd(f"{tag}-obs"), episode_id=ep,
                        investigation_id=investigation, trigger_refs=TRIGGERS,
                        bottleneck="range excludes n")
    development.propose(dsn, _cmd(f"{tag}-prop"), episode_id=ep,
                        predicted_effect="inclusive bound fixes dev-sum",
                        competing="spec ambiguity")
    policy = (development.panel_policy_for(
        PANEL_DEV, PANEL_PANEL, PANEL_TRANSFER, families=["off_by_one"])
        if panel else None)
    development.admit(dsn, _cmd(f"{tag}-adm"), episode_id=ep,
                      reference_version="baseline-v0", access_policy=POLICY,
                      allocation_id=allocation, panel_policy=policy, **limits)
    return env, ep


def _frozen_panel(dsn, ep):
    row = development.get_episode(dsn, ep)
    panel = dict(row["comparison_policy"]["panel"])
    panel["evaluator_version"] = "v1"
    return panel


COLLECT_TASKS = [{**task, "family": "off_by_one"} for task in TASKS]


def _collect(dsn, tag, ep, launcher, double=None):
    return development.collect_experience(
        dsn, _cmd(f"{tag}-ex"), double or EpisodeDouble(), launcher,
        episode_id=ep, model="scripted", dev_tasks=COLLECT_TASKS,
        grader_path=GRADER)


def _diagnose(dsn, tag, ep, double=None):
    return development.diagnose(dsn, _cmd(f"{tag}-dg"), double or EpisodeDouble(),
                                episode_id=ep, model="scripted")


def _construct(dsn, tag, ep, launcher, tmp_roots, double=None, stem=None):
    return development.construct(
        dsn, _cmd(f"{tag}-co"), double or EpisodeDouble(), launcher,
        episode_id=ep, model="scripted",
        artifacts_root=tmp_roots["artifacts"], staging_root=tmp_roots["staging"],
        version_stem=stem or f"{tag}-fix", family="off_by_one")


def _op_count(dsn, prefix):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM operations WHERE id LIKE %s",
                        (f"{prefix}%",))
            count = cur.fetchone()[0]
            conn.commit()
    return int(count)


def test_admission_refuses_missing_essentials_before_effects(migrated_db):
    dsn = migrated_db
    tag = unique("dep")
    env = seed_env(dsn, tag)
    ep = f"{tag}-ep"
    with pytest.raises(SettlementError):
        development.observe(dsn, _cmd(tag), episode_id=ep,
                            investigation_id=env["investigation_id"],
                            trigger_refs=[])
    with pytest.raises(SettlementError):
        development.observe(dsn, _cmd(tag), episode_id=ep,
                            investigation_id="missing-inv",
                            trigger_refs=TRIGGERS)
    development.observe(dsn, _cmd(tag), episode_id=ep,
                        investigation_id=env["investigation_id"],
                        trigger_refs=TRIGGERS)
    with pytest.raises(SettlementError, match="needs proposed"):
        development.admit(dsn, _cmd(tag), episode_id=ep,
                          reference_version="baseline-v0",
                          access_policy=POLICY,
                          allocation_id=env["allocation_id"])
    with pytest.raises(SettlementError):
        development.propose(dsn, _cmd(tag), episode_id=ep)
    development.propose(dsn, _cmd(tag), episode_id=ep,
                        predicted_effect="inclusive bound fixes dev-sum")
    with pytest.raises(SettlementError, match="reference version"):
        development.admit(dsn, _cmd(tag), episode_id=ep, reference_version="",
                          access_policy=POLICY,
                          allocation_id=env["allocation_id"])
    with pytest.raises(SettlementError, match="access policy"):
        development.admit(dsn, _cmd(tag), episode_id=ep,
                          reference_version="baseline-v0", access_policy={},
                          allocation_id=env["allocation_id"])
    with pytest.raises(SettlementError, match="unknown allocation"):
        development.admit(dsn, _cmd(tag), episode_id=ep,
                          reference_version="baseline-v0",
                          access_policy=POLICY, allocation_id="missing-alloc")
    with pytest.raises(SettlementError, match="outside seed bounds"):
        development.admit(dsn, _cmd(tag), episode_id=ep,
                          reference_version="baseline-v0",
                          access_policy=POLICY,
                          allocation_id=env["allocation_id"],
                          max_explanations=3)
    with pytest.raises(SettlementError, match="outside seed bounds"):
        development.admit(dsn, _cmd(tag), episode_id=ep,
                          reference_version="baseline-v0",
                          access_policy=POLICY,
                          allocation_id=env["allocation_id"], max_probes=2)
    with pytest.raises(SettlementError, match="outside seed bounds"):
        development.admit(dsn, _cmd(tag), episode_id=ep,
                          reference_version="baseline-v0",
                          access_policy=POLICY,
                          allocation_id=env["allocation_id"], max_candidates=3)
    with pytest.raises(SettlementError, match="needs admitted"):
        development.diagnose(dsn, _cmd(tag), EpisodeDouble(), episode_id=ep,
                             model="scripted")
    assert broker.read_operation(dsn, f"{ep}-explain") is None
    assert _op_count(dsn, f"{tag}-ep") == 0


def test_admission_records_seed_limits_and_freezes_dev_protocol(migrated_db):
    dsn = migrated_db
    tag = unique("dep")
    env, ep = _admit(dsn, tag)
    row = development.get_episode(dsn, ep)
    assert row["state"] == "admitted"
    assert row["trigger_refs"] == TRIGGERS
    assert row["reference_version"] == "baseline-v0"
    assert row["access_policy"] == POLICY
    assert row["allocation_id"] == env["allocation_id"]
    assert (row["max_explanations"], row["max_probes"], row["max_candidates"]) == (2, 1, 2)
    ledger = trials.development_expenditure(dsn, development.dev_protocol_id(ep))
    assert ledger["development_total"] == 0
    tag2 = unique("dep")
    env2, ep2 = _admit(dsn, tag2, max_explanations=1, max_probes=0,
                       max_candidates=1)
    row2 = development.get_episode(dsn, ep2)
    assert (row2["max_explanations"], row2["max_probes"], row2["max_candidates"]) == (1, 0, 1)


def _receipt_meta(dsn, operation_id):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content FROM receipts WHERE operation_id = %s"
                        " ORDER BY created_at", (operation_id,))
            rows = cur.fetchall()
            conn.commit()
    assert rows
    content = rows[-1][0]
    return content.get("model_meta", {})


def test_model_backed_diagnose_marks_provenance(migrated_db, launcher):
    dsn = migrated_db
    tag = unique("dep")
    _, ep = _admit(dsn, tag)
    gathered = _collect(dsn, tag, ep, launcher)
    assert gathered["transcripts"]["dev-sum"]["outcome"] in ("success", "failure")
    assert gathered["claims"] == [f"{ep}-exp-dev-sum-claim"]
    out = _diagnose(dsn, tag, ep)
    assert out["state"] == "diagnosed"
    assert len(out["explanations"]) == 2
    assert out["intervention"]["action"] == "inclusive-bound repair procedure"
    assert out["provenance"] == {"op": f"{ep}-explain", "model": "scripted",
                                 "simulated": True,
                                 "meta": {"simulated": True}}
    assert _receipt_meta(dsn, f"{ep}-explain") == {"simulated": True}
    op = broker.read_operation(dsn, f"{ep}-explain")
    assert op["payload"]["effect"] == broker.MODEL_INFERENCE
    assert op["dispatch_state"] == "observed"
    row = development.get_episode(dsn, ep)
    assert row["state"] == "diagnosed"
    assert len(row["explanations"]) == 2
    tag2 = unique("dep")
    _, ep2 = _admit(dsn, tag2, max_explanations=1)
    _collect(dsn, tag2, ep2, launcher)
    with pytest.raises(SettlementError, match="ceiling is 1"):
        development.diagnose(dsn, _cmd(tag2), EpisodeDouble(explanations=2),
                             episode_id=ep2, model="scripted")
    ledger = trials.development_expenditure(dsn, development.dev_protocol_id(ep2))
    assert ledger["by_category"]["construction"] > 0
    tag3 = unique("dep")
    _, ep3 = _admit(dsn, tag3)
    _collect(dsn, tag3, ep3, launcher)
    live_like = EpisodeDouble(meta={"model": "live-m"})
    out3 = development.diagnose(dsn, _cmd(tag3), live_like, episode_id=ep3,
                                model="live-m")
    assert out3["provenance"]["simulated"] is False
    assert _receipt_meta(dsn, f"{ep3}-explain") == {"model": "live-m"}


def test_diagnose_probe_bound(migrated_db, launcher):
    dsn = migrated_db
    tag = unique("dep")
    _, ep = _admit(dsn, tag)
    _collect(dsn, tag, ep, launcher)
    out = development.diagnose(dsn, _cmd(tag), EpisodeDouble(), episode_id=ep,
                               model="scripted", launcher=launcher,
                               probe={"code": PROBE_CODE})
    assert out["probes_used"] == 1
    assert development.get_episode(dsn, ep)["probes_used"] == 1
    tag2 = unique("dep")
    _, ep2 = _admit(dsn, tag2, max_probes=0)
    _collect(dsn, tag2, ep2, launcher)
    with pytest.raises(SettlementError, match="no diagnostic probe"):
        development.diagnose(dsn, _cmd(tag2), EpisodeDouble(), episode_id=ep2,
                             model="scripted", launcher=launcher,
                             probe={"code": PROBE_CODE})


def test_construct_stages_verifies_and_packages(migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("dep")
    _, ep = _admit(dsn, tag)
    _collect(dsn, tag, ep, launcher)
    _diagnose(dsn, tag, ep)
    out = _construct(dsn, tag, ep, launcher, tmp_roots)
    assert out["status"] == "constructed"
    assert out["slot"] == 0
    assert out["code_digest"] == hashlib.sha256(CANDIDATE_CODE.encode()).hexdigest()
    assert out["provenance"]["simulated"] is True
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT outcome, content FROM receipts WHERE operation_id = %s",
                        (out["stage_op"],))
            stage_receipts = cur.fetchall()
            conn.commit()
    assert stage_receipts and stage_receipts[-1][0] == "success"
    in_dir, _ = launcher.exec_dirs(out["stage_op"], "")
    staged_path = f"{in_dir}/candidate.py"
    with open(staged_path, "wb") as handle:
        handle.write(b"tampered")
    with pytest.raises(SettlementError, match="changed after binding"):
        experiment._verify_staged(out["stage_op"],
                                  {"candidate.py": (staged_path, out["code_digest"])})
    assert artifacts.artifact_available(dsn, tmp_roots["artifacts"],
                                        out["artifact_digest"])
    capability = capabilities.get_version(dsn, out["version_id"])
    assert capability is not None
    assert capability["artifact_digest"] == out["artifact_digest"]
    assert capability["verification_op"].startswith("cap-verify-")
    row = development.get_episode(dsn, ep)
    assert row["state"] == "constructed"
    assert len(row["candidates"]) == 1


def _happy_to_checked(dsn, tag, ep, launcher, tmp_roots, double=None):
    _collect(dsn, tag, ep, launcher, double)
    _diagnose(dsn, tag, ep, double)
    _construct(dsn, tag, ep, launcher, tmp_roots, double)
    return development.check(dsn, _cmd(f"{tag}-ck"), launcher, episode_id=ep,
                             artifacts_root=tmp_roots["artifacts"],
                             grader_path=GRADER, tasks=TASKS,
                             repair_probe=REPAIR_PROBE)


def test_two_freeze_selection_and_no_construction_retry(migrated_db, launcher,
                                                       tmp_roots):
    dsn = migrated_db
    tag = unique("dep")
    _, ep = _admit(dsn, tag, panel=True)
    checked = _happy_to_checked(dsn, tag, ep, launcher, tmp_roots)
    assert checked["grade_outcome"] == "success"
    assert checked["repair"]["match"] is True
    with pytest.raises(SettlementError, match="frozen before"):
        development.select(dsn, _cmd(tag), episode_id=ep)
    with pytest.raises(SettlementError, match="task groups"):
        development.freeze_comparison(dsn, _cmd(tag), episode_id=ep, policy={})
    development.freeze_comparison(dsn, _cmd(tag), episode_id=ep,
                                  policy=_frozen_panel(dsn, ep))
    row = development.get_episode(dsn, ep)
    assert row["comparison_policy"]["eval_protocol"] == \
        development.eval_protocol_id(ep)
    selected = development.select(dsn, _cmd(tag), episode_id=ep)
    assert selected["selection"]["decision"] == "select"
    assert selected["selection"]["basis"] == "development-checks"
    assert selected["selection"]["version_id"] == checked["candidate"]
    bound = development.bind(dsn, _cmd(tag), episode_id=ep)
    assert bound["state"] == "bound"
    assert bound["bindings"]["version_id"] == checked["candidate"]
    assert bound["bindings"]["reference_version"] == "baseline-v0"
    with pytest.raises(SettlementError, match="comparison feedback"):
        _construct(dsn, tag, ep, launcher, tmp_roots)
    trace = development.episode_trace(dsn, ep)
    kinds = [event["kind"] for event in trace]
    assert kinds == ["development.episode_observed",
                     "development.episode_proposed",
                     "development.episode_admitted",
                     "development.experience_collected",
                     "development.episode_diagnosed",
                     "development.episode_constructed",
                     "development.episode_checked",
                     "development.comparison_frozen",
                     "development.episode_selected",
                     "development.episode_bound"]
    epochs = {event["kind"]: (event["epoch"], event["ordinal"]) for event in trace}
    assert epochs["development.episode_constructed"] < \
        epochs["development.episode_bound"]
    row = development.get_episode(dsn, ep)
    assert row["comparison_exposed"] is True
    assert row["disposition"] == "bound"


def test_revision_consumes_a_candidate_slot(migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("dep")
    _, ep = _admit(dsn, tag)
    _collect(dsn, tag, ep, launcher)
    _diagnose(dsn, tag, ep)
    first = _construct(dsn, tag, ep, launcher, tmp_roots)
    development.check(dsn, _cmd(f"{tag}-c0"), launcher, episode_id=ep,
                      artifacts_root=tmp_roots["artifacts"],
                      grader_path=GRADER, tasks=TASKS)
    second = development.construct(
        dsn, _cmd(f"{tag}-c1"), EpisodeDouble(), launcher, episode_id=ep,
        model="scripted", artifacts_root=tmp_roots["artifacts"],
        staging_root=tmp_roots["staging"], version_stem=f"{tag}-fix",
        family="off_by_one")
    assert second["slot"] == 1
    assert second["version_id"] != first["version_id"]
    development.check(dsn, _cmd(f"{tag}-c2"), launcher, episode_id=ep,
                      artifacts_root=tmp_roots["artifacts"],
                      grader_path=GRADER, tasks=TASKS)
    with pytest.raises(SettlementError, match="slots exhausted"):
        development.construct(
            dsn, _cmd(f"{tag}-c3"), EpisodeDouble(), launcher, episode_id=ep,
            model="scripted", artifacts_root=tmp_roots["artifacts"],
            staging_root=tmp_roots["staging"], version_stem=f"{tag}-fix",
            family="off_by_one")
    assert len(development.get_episode(dsn, ep)["candidates"]) == 2


def test_no_candidate_is_truthful(migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("dep")
    env, ep = _admit(dsn, tag)
    _collect(dsn, tag, ep, launcher)
    _diagnose(dsn, tag, ep)
    out = _construct(dsn, tag, ep, launcher, tmp_roots,
                     double=EpisodeDouble(mode="no-candidate"))
    assert out["status"] == "no-candidate"
    assert out["slot_consumed"] is False
    row = development.get_episode(dsn, ep)
    assert row["disposition"] == "no-candidate"
    assert row["candidates"] == []
    ledger = trials.development_expenditure(dsn, development.dev_protocol_id(ep))
    assert ledger["by_category"]["construction"] > 0
    status = store.allocation_status(dsn, env["allocation_id"])
    assert status["consumed"] >= ledger["development_total"]
    assert status["reserved"] == 0


def test_invalid_output_consumes_a_slot(migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("dep")
    _, ep = _admit(dsn, tag)
    _collect(dsn, tag, ep, launcher)
    _diagnose(dsn, tag, ep)
    double = EpisodeDouble(mode="invalid")
    out = _construct(dsn, tag, ep, launcher, tmp_roots, double=double)
    assert out["status"] == "invalid-output"
    assert out["slot_consumed"] is True
    row = development.get_episode(dsn, ep)
    assert row["disposition"] == "invalid-output"
    assert len(row["candidates"]) == 1
    with pytest.raises(SettlementError, match="no constructed candidate"):
        development.check(dsn, _cmd(tag), launcher, episode_id=ep,
                          artifacts_root=tmp_roots["artifacts"],
                          grader_path=GRADER, tasks=TASKS)
    double.mode = "ok"
    retry = development.construct(
        dsn, _cmd(f"{tag}-rt"), double, launcher, episode_id=ep,
        model="scripted", artifacts_root=tmp_roots["artifacts"],
        staging_root=tmp_roots["staging"], version_stem=f"{tag}-fix",
        family="off_by_one")
    assert retry["status"] == "constructed"
    assert retry["slot"] == 1


def test_budget_exhaustion_refuses_before_dispatch(migrated_db, launcher):
    dsn = migrated_db
    tag = unique("dep")
    env = seed_env(dsn, tag)
    store.seed_allocation(dsn, Command(request_id=f"{tag}-tiny", payload={
        "allocation_id": f"{tag}-tiny", "domain": "s3", "authorized": 10,
        "max_occupancy": 64}))
    _, ep = _admit(dsn, tag, allocation_id=f"{tag}-tiny",
                   investigation_id=env["investigation_id"])
    with pytest.raises(SettlementError, match="refused before dispatch"):
        _collect(dsn, tag, ep, launcher)
    assert broker.read_operation(dsn, f"{ep}-exp-dev-sum-infer") is None
    row = development.get_episode(dsn, ep)
    assert row["state"] == "admitted"
    assert row["disposition"] == "budget-exhausted"
    status = store.allocation_status(dsn, f"{tag}-tiny")
    assert status["consumed"] == 0
    assert status["reserved"] == 0


def test_construct_after_drain_marks_budget_exhausted(migrated_db, launcher,
                                                     tmp_roots):
    dsn = migrated_db
    tag = unique("dep")
    env, ep = _admit(dsn, tag)
    _collect(dsn, tag, ep, launcher)
    _diagnose(dsn, tag, ep)
    status = store.allocation_status(dsn, env["allocation_id"])
    free = int(status["authorized"]) - int(status["consumed"]) - \
        int(status["reserved"])
    assert free > 10
    drained = store.reserve(dsn, Command(request_id=f"{tag}-drain", payload={
        "allocation_id": env["allocation_id"],
        "reservation_id": f"{tag}-drain", "amount": free - 5,
        "operation_id": ""}))
    assert drained.code.value in ("applied", "already_applied")
    with pytest.raises(SettlementError, match="refused before dispatch"):
        _construct(dsn, tag, ep, launcher, tmp_roots)
    assert broker.read_operation(dsn, f"{ep}-construct-0") is None
    row = development.get_episode(dsn, ep)
    assert row["disposition"] == "budget-exhausted"
    assert row["candidates"] == []


def test_interruption_after_publication_resumes_without_rebuild(
        migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("dep")
    _, ep = _admit(dsn, tag, panel=True)
    _collect(dsn, tag, ep, launcher)
    _diagnose(dsn, tag, ep)
    built = _construct(dsn, tag, ep, launcher, tmp_roots)
    fresh = EpisodeDouble()
    resumed = development.resume_episode(dsn, ep, tmp_roots["artifacts"])
    assert fresh.calls == []
    assert resumed["episode"]["state"] == "constructed"
    assert len(resumed["episode"]["candidates"]) == 1
    assert resumed["availability"][built["version_id"]] == {
        "artifact_available": True, "capability_published": True}
    assert resumed["ops"][f"{ep}-explain"]["dispatch_state"] == "observed"
    assert resumed["ops"][built["stage_op"]]["dispatch_state"] == "observed"
    assert resumed["ledger"]["development_total"] > 0
    checked = development.check(
        dsn, _cmd(f"{tag}-ck"), launcher, episode_id=ep,
        artifacts_root=tmp_roots["artifacts"], grader_path=GRADER,
        tasks=TASKS, repair_probe=REPAIR_PROBE)
    assert checked["grade_outcome"] == "success"
    development.freeze_comparison(
        dsn, _cmd(f"{tag}-frz"), episode_id=ep,
        policy=_frozen_panel(dsn, ep))
    development.select(dsn, _cmd(f"{tag}-sel"), episode_id=ep)
    bound = development.bind(dsn, _cmd(f"{tag}-bnd"), episode_id=ep)
    assert bound["bindings"]["artifact_digest"] == built["artifact_digest"]
    assert fresh.calls == []
    assert len(development.get_episode(dsn, ep)["candidates"]) == 1
