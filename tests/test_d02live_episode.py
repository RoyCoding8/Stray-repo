"""D02LIVE episode regressions (D2A-001..003, cost union, disposition).

Real PostgreSQL + real LocalLauncher subprocesses throughout. Model
inference alone is doubled with an explicit local double (deterministic,
labeled simulated); every broker/sandbox/store effect is real. No live
inference here: the live episode stays an exact-blocker record.

Probe correspondence
(reviews/probes/test_development_02_acceptance.py is characterization
only and is never edited here):
- test_collected_claim_is_not_resolved_for_diagnosis
  -> test_collect_links_claims_into_trigger_refs,
     test_diagnose_prompt_carries_collected_material
- test_constructor_declares_selftest_without_normal_file_interface
  -> test_diagnose_contract_declares_intervention,
     test_construct_prompt_states_file_abi,
     test_constructed_procedure_survives_consumer
- test_subsequent_use_invokes_unreleased_out_of_family_binding
  -> test_unreleased_binding_falls_back_to_incumbent,
     test_wrong_family_task_falls_back_with_reason,
     test_released_version_resolves_via_router,
     test_trial_invocation_is_labeled,
     test_run_use_disposition_json_plumbing
- test_ready_budget_fallback_removes_counterexample_body -> NOT CLOSED
  here (L-CTX owns D2A-005).
- test_packet_binding_accepts_unrelated_operation_without_reading_input
  -> NOT CLOSED here (L-CTX owns D2A-004).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "experiments")
sys.path.insert(0, "tests")

import pytest

from fault_tasks import BY_ID
from test_dev01_episode import CANDIDATE_CODE
from test_s3_helpers import EXPERIMENTS, seed_env

from settlement import capabilities, context, development, experiment
from settlement.common import Command
from settlement.gateway import GatewayAdapter, GatewayError, ModelResponse, Usage
from settlement.launcher_local import LocalLauncher

from conftest import unique

GRADER = str(EXPERIMENTS / "run_tests.py")
DEV_TASK = BY_ID["dev-sum"]
TRIGGERS = [{"task_id": "dev-sum", "family": "off_by_one"}]
POLICY = {"families": ["off_by_one"], "material": "development-only",
          "applicability": {"family": "off_by_one"}}

LIVE_DIAGNOSE_RESPONSE = '''```json
{
  "explanations": [
    {
      "cause": "The declared bottleneck is 'off-by-one' (inclusive upper bound omitted), but the delivered code already applies the correct fix (`range(n+1)`), and the grading receipt (grade-1) reports success with all 3 tests passed. Therefore the off-by-one error was resolved during inference and no residual defect remains.",
      "support": [
        "obs-1",
        "grade-1",
        "infer-1"
      ],
      "counterevidence": []
    },
    {
      "cause": "No actual development failure occurred: the single observation (obs-1) is listed as unresolved only because the diagnosis pipeline had not yet consumed it, not because the outcome was negative. The task objective ('Repair inclusive summation') was satisfied by the generated code, leaving nothing to diagnose.",
      "support": [
        "obs-1",
        "infer-1"
      ],
      "counterevidence": []
    }
  ],
  "probe": null,
  "intervention": {
    "action": "close-bottleneck",
    "rationale": "All evidence confirms the off-by-one issue is already corrected (code uses n+1, grade passes 3/3). The unresolved observation obs-1 can be marked resolved. No further probe or repair is needed; the bottleneck entry should be retired so it does not trigger unnecessary future diagnosis cycles."
  }
}
```'''

LIVE_CONSTRUCT_RESPONSE = '''Looking at the evidence, I need to understand the problem:

- **Broken code**: `def sum_to(n): return sum(range(n))` — uses `range(n)` which is exclusive of `n`, so `sum_to(5)` returns `0+1+2+3+4 = 10`.
- **Expected**: `sum_to(5)` should return `15` (i.e., `0+1+2+3+4+5 = 15`).
- **Family**: `off_by_one` — the endpoint of `range(n)` is exclusive when it should be inclusive.
- **Model fix**: `def sum_to(n): return sum(range(n+1))` — uses `range(n+1)` to include `n`.

The development feedback confirms the cause: `exclusive endpoint`.

Here is the candidate repair:

```json
{
  "code": "def sum_to(n):\\n    return sum(range(n+1))\\n",
  "no_candidate": null
}
```

**Repair procedure diagnosis:**

1. **Root cause**: `range(n)` produces values `[0, 1, ..., n-1]`, excluding `n`. This is the classic off-by-one error with Python's exclusive upper-bound convention.

2. **Fix**: Change `range(n)` to `range(n+1)` so that `n` is included in the summation.

3. **Verification**: `sum(range(5+1))` = `sum([0,1,2,3,4,5])` = `15`, which matches the expected output for `sum_to(5)`.'''

LIVE_BARE_FUNCTION = "def sum_to(n):\n    return sum(range(n+1))\n"


class PhaseDouble(GatewayAdapter):
    def __init__(self, diagnose=None, construct=None, code=CANDIDATE_CODE):
        self.programmed = {"diagnose": diagnose, "construct": construct}
        self.code = code
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
            return GatewayError("protocol", "phase double needs a JSON body",
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
            return GatewayError("protocol", "phase double needs a known phase",
                                False, request.operation_id)
        self.calls.append(body)
        if self.programmed[phase] is not None:
            text = self.programmed[phase]
        elif phase == "diagnose":
            text = json.dumps({
                "explanations": [{"id": "e1", "text": "boundary handling"}],
                "intervention": {"action": "inclusive-bound repair procedure"}})
        else:
            text = json.dumps({"code": self.code})
        return ModelResponse(request.operation_id, text, {"simulated": True},
                             Usage(input_tokens=40, output_tokens=200,
                                   charge_units=240), "stop")

    def cancel(self, operation_id):
        return True


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _cmd(tag):
    return Command(request_id=f"{tag}-{unique('c')}", payload={})


def _admit(dsn, tag):
    env = seed_env(dsn, tag)
    ep = f"{tag}-ep"
    development.observe(dsn, _cmd(f"{tag}-obs"), episode_id=ep,
                        investigation_id=env["investigation_id"],
                        trigger_refs=[dict(ref) for ref in TRIGGERS],
                        bottleneck="range excludes n")
    development.propose(dsn, _cmd(f"{tag}-prop"), episode_id=ep,
                        predicted_effect="inclusive bound fixes dev-sum")
    policy = development.panel_policy_for(
        ["dev-sum"], ["panel-triangular"], ["transfer-discount"],
        families=["off_by_one"])
    development.admit(dsn, _cmd(f"{tag}-adm"), episode_id=ep,
                      reference_version="baseline-v0", access_policy=POLICY,
                      allocation_id=env["allocation_id"], panel_policy=policy)
    return env, ep


def _dev_tasks():
    return [{"id": "dev-sum", "family": "off_by_one",
             "broken": DEV_TASK["broken"], "cases": DEV_TASK["cases"]}]


def _collect(dsn, tag, ep, launcher, double):
    return development.collect_experience(
        dsn, _cmd(f"{tag}-ex"), double, launcher, episode_id=ep,
        model="scripted", dev_tasks=_dev_tasks(), grader_path=GRADER)


def _diagnose(dsn, tag, ep, double):
    return development.diagnose(dsn, _cmd(f"{tag}-dg"), double,
                                episode_id=ep, model="scripted")


def _construct(dsn, tag, ep, launcher, tmp_roots, double):
    return development.construct(
        dsn, _cmd(f"{tag}-co"), double, launcher, episode_id=ep,
        model="scripted", artifacts_root=tmp_roots["artifacts"],
        staging_root=tmp_roots["staging"], version_stem=f"{tag}-fix",
        family="off_by_one")


def _bind(dsn, tag, ep, env, launcher, tmp_roots, double):
    _diagnose(dsn, tag, ep, double)
    _construct(dsn, tag, ep, launcher, tmp_roots, double)
    checked = development.check(
        dsn, _cmd(f"{tag}-ck"), launcher, episode_id=ep,
        artifacts_root=tmp_roots["artifacts"], grader_path=GRADER,
        tasks=_dev_tasks())
    row = development.get_episode(dsn, ep)
    panel = dict(row["comparison_policy"]["panel"])
    panel["evaluator_version"] = "v1"
    development.freeze_comparison(dsn, _cmd(f"{tag}-frz"), episode_id=ep,
                                  policy=panel)
    development.select(dsn, _cmd(f"{tag}-sel"), episode_id=ep)
    return development.bind(dsn, _cmd(f"{tag}-bnd"), episode_id=ep), checked


def _diagnose_prompt(double):
    return next(call for call in double.calls if call.get("phase") == "diagnose")


def _construct_prompt(double):
    return next(call for call in double.calls if call.get("phase") == "construct")


def test_diagnose_contract_declares_intervention(migrated_db, launcher):
    shape = context._OUTPUT_CONTRACTS["diagnose"]["response_shape"]
    assert "intervention" in shape
    dsn = migrated_db
    tag = unique("d02live")
    _, ep = _admit(dsn, tag)
    double = PhaseDouble()
    _collect(dsn, tag, ep, launcher, double)
    out = _diagnose(dsn, tag, ep, double)
    assert out["intervention"]["action"] == "inclusive-bound repair procedure"
    prompt = _diagnose_prompt(double)
    assert prompt["response_contract"] == shape
    assert prompt["response_contract"]["intervention"]
    assert "raw JSON only" in prompt["format"]
    packet = context.load_packet(dsn, out["packet_id"])
    assert "intervention" in packet["mandatory_content"][
        "output_contract"]["contract"]["response_shape"]


def test_construct_prompt_states_file_abi(migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    _, ep = _admit(dsn, tag)
    double = PhaseDouble()
    _collect(dsn, tag, ep, launcher, double)
    _diagnose(dsn, tag, ep, double)
    out = _construct(dsn, tag, ep, launcher, tmp_roots, double)
    assert out["status"] == "constructed"
    prompt = _construct_prompt(double)
    abi = prompt["file_abi"]
    assert abi["shape"].startswith("reusable file-to-file procedure")
    for token in ("fixed.py", "broken.py", "method.py", "input_path",
                  "output_path", "--selftest", "sandbox-only"):
        assert token in json.dumps(prompt), token
    assert prompt["response_shape"] == context._OUTPUT_CONTRACTS[
        "construct"]["response_shape"]
    packet = context.load_packet(dsn, out["packet_id"])
    invocation = packet["mandatory_content"]["invocation_contract"][
        "invocation"]
    assert invocation["verify_args"] == ["--selftest"]
    assert invocation["invoke_args"] == ["<in-dir>/broken.py",
                                         "<out-dir>/fixed.py"]
    assert "fixed.py" in invocation["writes"]


def test_envelope_policy_on_exact_production_responses():
    assert development._parse_envelope('{"a": 1}') == {"a": 1}
    assert development._parse_envelope(
        '```json\n{"a": 1}\n```') == {"a": 1}
    assert development._parse_envelope('```{"a": 1}```') == {"a": 1}
    assert development._parse_envelope(LIVE_DIAGNOSE_RESPONSE)[
        "intervention"]["action"] == "close-bottleneck"
    assert development._parse_envelope(LIVE_CONSTRUCT_RESPONSE) is None
    assert development._parse_envelope("plain prose") is None
    assert development._parse_envelope("") is None
    assert development._parse_envelope(
        '```json\n{"a": 1}\n```\n```json\n{"b": 2}\n```') is None


def test_live_diagnose_bytes_diagnose_through_production_path(
        migrated_db, launcher):
    dsn = migrated_db
    tag = unique("d02live")
    _, ep = _admit(dsn, tag)
    double = PhaseDouble(diagnose=LIVE_DIAGNOSE_RESPONSE)
    _collect(dsn, tag, ep, launcher, double)
    out = _diagnose(dsn, tag, ep, double)
    assert out["state"] == "diagnosed"
    assert len(out["explanations"]) == 2
    assert out["intervention"]["action"] == "close-bottleneck"


def test_live_construct_bytes_stay_honest_invalid_output(
        migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    _, ep = _admit(dsn, tag)
    double = PhaseDouble(construct=LIVE_CONSTRUCT_RESPONSE)
    _collect(dsn, tag, ep, launcher, double)
    _diagnose(dsn, tag, ep, double)
    out = _construct(dsn, tag, ep, launcher, tmp_roots, double)
    assert out["status"] == "invalid-output"
    assert out["slot_consumed"] is True
    row = development.get_episode(dsn, ep)
    assert row["disposition"] == "invalid-output"


def test_bare_function_fails_procedure_selftest(
        migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    _, ep = _admit(dsn, tag)
    double = PhaseDouble(
        construct=json.dumps({"code": LIVE_BARE_FUNCTION,
                              "no_candidate": None}))
    _collect(dsn, tag, ep, launcher, double)
    _diagnose(dsn, tag, ep, double)
    out = _construct(dsn, tag, ep, launcher, tmp_roots, double)
    assert out["status"] == "invalid-output"
    assert "typed JSON status ok" in next(
        entry["detail"] for entry in
        development.get_episode(dsn, ep)["candidates"])


def test_constructed_procedure_survives_consumer(migrated_db, launcher,
                                                 tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    env, ep = _admit(dsn, tag)
    double = PhaseDouble()
    _collect(dsn, tag, ep, launcher, double)
    _diagnose(dsn, tag, ep, double)
    out = _construct(dsn, tag, ep, launcher, tmp_roots, double)
    assert out["status"] == "constructed"
    capability = capabilities.get_version(dsn, out["version_id"])
    assert capability is not None
    held = BY_ID["panel-triangular"]
    attempt = experiment._fresh_worker(
        dsn, tag=f"{tag}-heldout", investigation_id=env["investigation_id"],
        allocation_id=env["allocation_id"])
    fixed, _ = experiment._invoke_method(
        dsn, launcher, Path(tmp_roots["artifacts"]), capability,
        held["broken"], f"{tag}-heldout", env["allocation_id"], attempt)
    assert fixed == held["fixed"]


def test_abstention_consumes_no_slot(migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    _, ep = _admit(dsn, tag)
    double = PhaseDouble(
        construct=json.dumps({"no_candidate": "no worthwhile change"}))
    _collect(dsn, tag, ep, launcher, double)
    _diagnose(dsn, tag, ep, double)
    out = _construct(dsn, tag, ep, launcher, tmp_roots, double)
    assert out["status"] == "no-candidate"
    assert out["slot_consumed"] is False
    assert development.get_episode(dsn, ep)["candidates"] == []


def test_collect_links_claims_into_trigger_refs(migrated_db, launcher):
    dsn = migrated_db
    tag = unique("d02live")
    _, ep = _admit(dsn, tag)
    double = PhaseDouble()
    gathered = _collect(dsn, tag, ep, launcher, double)
    assert gathered["claims"] == [f"{ep}-exp-dev-sum-claim"]
    assert gathered["trigger_refs"] == [
        {"task_id": "dev-sum", "family": "off_by_one",
         "claim_id": f"{ep}-exp-dev-sum-claim"}]
    row = development.get_episode(dsn, ep)
    assert row["trigger_refs"] == gathered["trigger_refs"]
    trace = development.episode_trace(dsn, ep)
    collected = [event for event in trace
                 if event["kind"] == "development.experience_collected"]
    assert len(collected) == 1
    assert collected[0]["payload"]["claims"] == gathered["claims"]


def test_diagnose_prompt_carries_collected_material(migrated_db, launcher):
    dsn = migrated_db
    tag = unique("d02live")
    _, ep = _admit(dsn, tag)
    double = PhaseDouble()
    gathered = _collect(dsn, tag, ep, launcher, double)
    out = _diagnose(dsn, tag, ep, double)
    packet = context.load_packet(dsn, out["packet_id"])
    assert [bundle["claim_id"] for bundle in
            packet["evidence_bundles"]] == gathered["claims"]
    bundle = packet["evidence_bundles"][0]
    transcript = gathered["transcripts"]["dev-sum"]
    assert bundle["proposition"]["broken"] == DEV_TASK["broken"]
    assert bundle["proposition"]["cases"] == DEV_TASK["cases"]
    assert bundle["proposition"]["outcome"] == transcript["outcome"]
    assert bundle["proposition"]["model_text"] == transcript["model_text"][:2000]
    rendered = _diagnose_prompt(double)["packet"]
    assert "return sum(range(n))" in rendered
    assert f'"outcome":"{transcript["outcome"]}"' in rendered
    assert "dev_attempt" in rendered
    assert transcript["grade_op"] in rendered
    assert transcript["model_op"] in rendered


def _save_policy(dsn, tag, family, version_id):
    return capabilities.save_router_policy(
        dsn, _cmd(f"{tag}-router"), version=f"{tag}-router",
        mapping={family: version_id})


def _use_task(task_id):
    task = BY_ID[task_id]
    return {"id": task["id"], "family": task["family"],
            "broken": task["broken"], "cases": task["cases"]}


def test_unreleased_binding_falls_back_to_incumbent(
        migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    env, ep = _admit(dsn, tag)
    double = PhaseDouble()
    _collect(dsn, tag, ep, launcher, double)
    bound, _ = _bind(dsn, tag, ep, env, launcher, tmp_roots, double)
    assert bound["bindings"]["version_id"]
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tmp_roots["artifacts"], launcher=launcher,
        adapter=PhaseDouble(), model="scripted",
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], episode_id=ep,
        bindings=bound["bindings"], use_task=_use_task("transfer-discount"),
        grader_path=GRADER, protocol_prefix=f"{tag}-px",
        prior_exposure="transfer-comparison",
        disposition={"released": {}, "router_policies": {},
                     "trial": False})
    assert use["method"] == "incumbent"
    assert use["version_id"] == ""
    assert "unreleased" in use["reason"]
    assert use["trial"] is False
    assert "model_op" in use["ops"]


def test_wrong_family_task_falls_back_with_reason(
        migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    env, ep = _admit(dsn, tag)
    double = PhaseDouble()
    _collect(dsn, tag, ep, launcher, double)
    bound, _ = _bind(dsn, tag, ep, env, launcher, tmp_roots, double)
    version = bound["bindings"]["version_id"]
    _save_policy(dsn, tag, "off_by_one", version)
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tmp_roots["artifacts"], launcher=launcher,
        adapter=PhaseDouble(), model="scripted",
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], episode_id=ep,
        bindings=bound["bindings"], use_task=_use_task("transfer-discount"),
        grader_path=GRADER, protocol_prefix=f"{tag}-px",
        prior_exposure="transfer-comparison",
        disposition={"released": {"off_by_one": version},
                     "router_policies": {"off_by_one": f"{tag}-router"},
                     "trial": False})
    assert use["method"] == "incumbent"
    assert "wrong_operator" in use["reason"]
    assert use["version_id"] == ""


def test_released_version_resolves_via_router(
        migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    env, ep = _admit(dsn, tag)
    double = PhaseDouble()
    _collect(dsn, tag, ep, launcher, double)
    bound, _ = _bind(dsn, tag, ep, env, launcher, tmp_roots, double)
    version = bound["bindings"]["version_id"]
    _save_policy(dsn, tag, "off_by_one", version)
    routed = capabilities.route(dsn, f"{tag}-router", "off_by_one")
    assert routed == {"family": "off_by_one", "decision": "select",
                      "version_id": version}
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tmp_roots["artifacts"], launcher=launcher,
        adapter=PhaseDouble(), model="scripted",
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], episode_id=ep,
        bindings=bound["bindings"], use_task=_use_task("panel-triangular"),
        grader_path=GRADER, protocol_prefix=f"{tag}-px",
        prior_exposure="panel-comparison",
        disposition={"released": {"off_by_one": version},
                     "router_policies": {"off_by_one": f"{tag}-router"},
                     "trial": False})
    assert use["method"] == "selected"
    assert use["version_id"] == version
    assert use["reason"] == f"released-{version}-via-{tag}-router"
    assert use["outcome"] == "success"
    assert use["trial"] is False


def test_trial_invocation_is_labeled(migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    env, ep = _admit(dsn, tag)
    double = PhaseDouble()
    _collect(dsn, tag, ep, launcher, double)
    bound, _ = _bind(dsn, tag, ep, env, launcher, tmp_roots, double)
    version = bound["bindings"]["version_id"]
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tmp_roots["artifacts"], launcher=launcher,
        adapter=PhaseDouble(), model="scripted",
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], episode_id=ep,
        bindings=bound["bindings"], use_task=_use_task("transfer-discount"),
        grader_path=GRADER, protocol_prefix=f"{tag}-px",
        prior_exposure="transfer-comparison",
        disposition={"released": {}, "router_policies": {}, "trial": True})
    assert use["method"] == "trial"
    assert use["version_id"] == version
    assert use["trial"] is True
    assert use["reason"] == f"explicit-trial-{version}"
    assert "invoke_op" in use["ops"]


def test_quarantined_release_falls_back_to_incumbent(
        migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    env, ep = _admit(dsn, tag)
    double = PhaseDouble()
    _collect(dsn, tag, ep, launcher, double)
    bound, _ = _bind(dsn, tag, ep, env, launcher, tmp_roots, double)
    version = bound["bindings"]["version_id"]
    _save_policy(dsn, tag, "off_by_one", version)
    capabilities.quarantine(dsn, _cmd(f"{tag}-quar"), version, "test hold")
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tmp_roots["artifacts"], launcher=launcher,
        adapter=PhaseDouble(), model="scripted",
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], episode_id=ep,
        bindings=bound["bindings"], use_task=_use_task("panel-triangular"),
        grader_path=GRADER, protocol_prefix=f"{tag}-px",
        prior_exposure="panel-comparison",
        disposition={"released": {"off_by_one": version},
                     "router_policies": {"off_by_one": f"{tag}-router"},
                     "trial": False})
    assert use["method"] == "incumbent"
    assert "quarantined" in use["reason"]


def test_missing_bytes_fall_back_to_incumbent(
        migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    env, ep = _admit(dsn, tag)
    double = PhaseDouble()
    _collect(dsn, tag, ep, launcher, double)
    bound, _ = _bind(dsn, tag, ep, env, launcher, tmp_roots, double)
    version = bound["bindings"]["version_id"]
    _save_policy(dsn, tag, "off_by_one", version)
    capability = capabilities.get_version(dsn, version)
    (Path(tmp_roots["artifacts"])
     / capability["artifact_digest"]).unlink()
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tmp_roots["artifacts"], launcher=launcher,
        adapter=PhaseDouble(), model="scripted",
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], episode_id=ep,
        bindings=bound["bindings"], use_task=_use_task("panel-triangular"),
        grader_path=GRADER, protocol_prefix=f"{tag}-px",
        prior_exposure="panel-comparison",
        disposition={"released": {"off_by_one": version},
                     "router_policies": {"off_by_one": f"{tag}-router"},
                     "trial": False})
    assert use["method"] == "incumbent"
    assert "missing-bytes" in use["reason"]


def test_run_use_disposition_json_plumbing(migrated_db, launcher, tmp_roots):
    dsn = migrated_db
    tag = unique("d02live")
    env, ep = _admit(dsn, tag)
    double = PhaseDouble()
    _collect(dsn, tag, ep, launcher, double)
    bound, _ = _bind(dsn, tag, ep, env, launcher, tmp_roots, double)
    assert bound["bindings"]["version_id"]
    cmd = [sys.executable, str(EXPERIMENTS / "run_use.py"),
           "--dsn", dsn, "--artifacts-root", tmp_roots["artifacts"],
           "--allocation", env["allocation_id"],
           "--investigation", env["investigation_id"], "--episode", ep,
           "--use-task", "transfer-discount",
           "--prior-exposure", "transfer-comparison",
           "--protocol-prefix", f"{tag}-px",
           "--disposition-json", json.dumps(
               {"released": {}, "router_policies": {}, "trial": False})]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    use = json.loads(proc.stdout)
    assert use["method"] == "incumbent"
    assert "unreleased" in use["reason"]
    bad = subprocess.run(cmd[:-1] + ["{not-json"], capture_output=True,
                         text=True, timeout=60)
    assert bad.returncode == 2


def test_use_disposition_builds_from_releases():
    import run_dev_episode

    releases = {
        "panel-C": {"status": "released", "protocol_id": "p",
                    "router_policy": "pol",
                    "routed": {"off_by_one": {"version_id": "v1"}}},
        "transfer-C": {"status": "skipped-synthetic", "protocol_id": "t"}}
    assert run_dev_episode._use_disposition(releases) == {
        "released": {"off_by_one": "v1"},
        "router_policies": {"off_by_one": "pol"}, "trial": False}
    assert run_dev_episode._use_disposition({}) == {
        "released": {}, "router_policies": {}, "trial": False}


def test_episode_cost_union_covers_all_phases(
        migrated_db, launcher, tmp_roots):
    import run_dev_episode

    dsn = migrated_db
    tag = unique("d02live")
    env, ep = _admit(dsn, tag)
    double = PhaseDouble()
    gathered = _collect(dsn, tag, ep, launcher, double)
    diagnosed = _diagnose(dsn, tag, ep, double)
    built = _construct(dsn, tag, ep, launcher, tmp_roots, double)
    assert built["status"] == "constructed"
    checked = development.check(
        dsn, _cmd(f"{tag}-ck"), launcher, episode_id=ep,
        artifacts_root=tmp_roots["artifacts"], grader_path=GRADER,
        tasks=_dev_tasks())
    tasks = [_use_task(i) for i in
             ("dev-sum", "panel-triangular", "transfer-discount")]
    for task in tasks:
        task["entry_fn"] = BY_ID[task["id"]]["entry_fn"]
    report = experiment.run_abcs(
        dsn, launcher=launcher, artifacts_root=tmp_roots["artifacts"],
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], tasks=tasks,
        dev_ids=["dev-sum"], panel_ids=["panel-triangular"],
        transfer_ids=["transfer-discount"],
        lessons={"off_by_one": "test lesson"}, gateway=double,
        grader_path=GRADER, protocol_prefix=f"{tag}-px",
        fixer_version=built["version_id"], simulated=True, model="scripted",
        synthesize=None, dev_transcripts=gathered["transcripts"],
        panel_protocol=None)
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tmp_roots["artifacts"], launcher=launcher,
        adapter=PhaseDouble(), model="scripted",
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], episode_id=ep,
        bindings={}, use_task=_use_task("transfer-discount"),
        grader_path=GRADER, protocol_prefix=f"{tag}-px",
        prior_exposure="transfer-comparison",
        disposition={"released": {}, "router_policies": {},
                     "trial": False})
    ep_view = {"episode_id": ep, "gathered": gathered,
               "diagnosed": diagnosed, "built": {"off_by_one": built},
               "checked": checked}
    phases = run_dev_episode._episode_phase_ops(ep_view, report, use)
    assert set(phases) == {"collection", "diagnosis", "construction",
                           "checks", "comparison-shared", "comparison-A",
                           "comparison-B", "comparison-C", "subsequent-use"}
    union = experiment.episode_cost_union(dsn, phases)
    assert union["scope"] == "whole-episode-unique-operation-union"
    expected = set(phases["collection"] + phases["diagnosis"]
                   + phases["construction"] + phases["checks"]
                   + phases["subsequent-use"])
    expected |= set(report["accounting"]["ops"])
    assert expected <= set(union["unique_ops"])
    assert union["unique_op_count"] == len(union["unique_ops"])
    assert union["shared_ops"], "reused dev transcripts must show as shared"
    check = {"reserved": 0, "settled": 0, "unresolved": 0}
    for op in union["unique_ops"]:
        entry = experiment._op_accounting(dsn, op)
        for key in check:
            check[key] += entry[key]
    assert union["totals"]["reserved"] == check["reserved"]
    assert union["totals"]["settled"] == check["settled"]
    assert union["unresolved_exposure"] == check["unresolved"]
    assert union["totals"]["reserved"] >= union["totals"]["settled"]
    harness = set(report["accounting"]["ops"])
    beyond = set(phases["collection"] + phases["diagnosis"]
                 + phases["construction"] + phases["checks"]
                 + phases["subsequent-use"]) - harness
    assert beyond, "union must cover operations outside the harness"
    assert union["phases"]["comparison-A"]["ops"]
    assert union["phases"]["comparison-B"]["ops"]
    assert union["phases"]["comparison-C"]["ops"]


def test_cost_union_preserves_unsettled_exposure(migrated_db, launcher):
    dsn = migrated_db
    tag = unique("d02live")
    env = seed_env(dsn, tag)
    attempt = experiment._fresh_worker(
        dsn, tag=f"{tag}-open", investigation_id=env["investigation_id"],
        allocation_id=env["allocation_id"])
    experiment._ensure_sandbox_op(
        dsn, launcher, f"{tag}-open-op", ["/bin/true"],
        env["allocation_id"], attempt, 10_000)
    entry = experiment._op_accounting(dsn, f"{tag}-open-op")
    union = experiment.episode_cost_union(dsn, {"open-probe": [f"{tag}-open-op"]})
    assert union["unique_ops"] == [f"{tag}-open-op"]
    assert union["unresolved_exposure"] == entry["unresolved"]
    assert union["totals"]["reserved"] == entry["reserved"]
    assert union["totals"]["settled"] == entry["settled"]
