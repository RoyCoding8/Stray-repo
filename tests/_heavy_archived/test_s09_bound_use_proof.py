"""Does a bound STEP policy govern fresh-process use, and if not, what does.

Finding S09R-02. The bound P1 STEP policy's digest is
`b71a7f8f39ad1655555f0ac47ab2ab81321a78d98ac90f1079944fc626194706`.
The four P1 software use records name that same digest on
`policy_digest` while their `executed_source` bytes hash to
`3834317f66d4fb086d9e4cc93c36c0b08e4a108478dd26b776de66ea04c58685`,
the authored `ENTRY` at `scripts/s09_pilot.py:299`.

These tests recompute both digests from bytes rather than reading either
digest field out of a record. A test that reads a digest the pipeline
itself wrote proves only that the pipeline can write a digest.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import agenda_policy
from experiments.ad01 import method_exec
from experiments.ad01 import policy_action
from experiments.ad01 import policy_step
from experiments.ad01 import s09_bound_use_proof as proof
from experiments.ad01 import trajectory

BOUND_POLICY_DIGEST = (
    "b71a7f8f39ad1655555f0ac47ab2ab81321a78d98ac90f1079944fc626194706")
AUTHORED_METHOD_DIGEST = (
    "3834317f66d4fb086d9e4cc93c36c0b08e4a108478dd26b776de66ea04c58685")
SEED_GREEDY_METHOD_DIGEST = (
    "370aed697dc503aecee7d8faad5de775f4f7019c86e672e8d93f3df590527058")


@pytest.fixture
def proof_store():
    with proof.proof_authority() as authority:
        yield authority


def test_the_bound_policy_source_hashes_to_its_recorded_digest():
    """The bytes that ran must be the bytes that were bound."""
    binding = proof.load_bound_policy()

    recomputed = hashlib.sha256(
        binding.source.encode("utf-8")).hexdigest()

    assert recomputed == BOUND_POLICY_DIGEST
    assert binding.recorded_digest == BOUND_POLICY_DIGEST
    assert binding.verified().digest == BOUND_POLICY_DIGEST
    assert len(binding.source) == 534


def test_the_bound_policy_source_is_the_committed_construction_response():
    """The source came from persisted state, not from a literal here."""
    binding = proof.load_bound_policy()
    committed = json.loads(
        (proof.EVIDENCE / "construction.json").read_text())["P1"]

    assert committed["bound_digest"] == BOUND_POLICY_DIGEST
    assert committed["policy_source"] == binding.source
    assert hashlib.sha256(
        committed["policy_source"].encode("utf-8")).hexdigest() \
        == BOUND_POLICY_DIGEST


def test_a_tampered_policy_is_refused_before_execution():
    binding = proof.load_bound_policy()
    tampered = proof.PolicyBinding_(
        source=binding.source + "\n# appended\n",
        recorded_digest=binding.recorded_digest, origin="authored-control")

    with pytest.raises(proof.PolicyNotProved, match="does not equal the"):
        tampered.verified()


def test_a_policy_absent_from_durable_state_is_refused():
    binding = proof.load_bound_policy()
    persisted_elsewhere = proof.PolicyBinding_(
        source=proof.seed_policy_source(proof.BASELINE_METHOD),
        recorded_digest=proof.sha256_of(
            proof.seed_policy_source(proof.BASELINE_METHOD)),
        origin="fixture-stand-in")

    assert persisted_elsewhere.digest != BOUND_POLICY_DIGEST
    with pytest.raises(proof.PolicyNotProved,
                       match="not the bytes persisted at digest"):
        persisted_elsewhere.verified()


def test_the_bound_policy_executes_in_a_fresh_interpreter(proof_store):
    binding = proof.load_bound_policy()
    view = proof.use_view()
    result = proof.execute_bound_policy(
        binding, view, {}, authority=proof_store,
        operation_id=proof._operation_id(binding, view))
    fresh = proof.fresh_process_evidence(result)

    assert fresh.launcher_profile == "local-process"
    assert fresh.worker_status == "ok"
    assert fresh.child_argv[1].endswith("driver.py")
    assert fresh.receipt_identity.startswith("local:")
    assert fresh.child_argv[0] == sys.executable
    assert fresh.executed_digest == BOUND_POLICY_DIGEST
    assert fresh.policy_digest == BOUND_POLICY_DIGEST


def test_the_fresh_process_runs_the_real_scrubbed_launcher(
        monkeypatch, proof_store):
    """The child is launched by the shipped scrubbed local launcher."""
    import settlement.launcher_local as launcher_local
    from settlement.exec_profile import scrub_env

    binding = proof.load_bound_policy()
    monkeypatch.setenv("S09_FAKE_KEY", "never-reaches-the-child")
    seen = []
    real_popen = launcher_local.subprocess.Popen

    def spy(argv, **kwargs):
        env = kwargs.get("env")
        if env is not None:
            seen.append(dict(env))
        return real_popen(argv, **kwargs)

    monkeypatch.setattr(launcher_local.subprocess, "Popen", spy)
    view = proof.use_view()
    result = proof.execute_bound_policy(
        binding, view, {}, authority=proof_store,
        operation_id=proof._operation_id(binding, view))

    assert len(seen) == 1
    assert set(seen[0]) == set(scrub_env()) | {"SETTLEMENT_OPERATION"}
    assert "S09_FAKE_KEY" not in seen[0]
    assert result["receipt"]["details"]["raw_payload"][
        "launcher_receipt"]["containment"] is False


def test_the_bound_policy_admits_no_use_action_at_all(proof_store):
    """The bound P1 policy never admits a use."""
    binding = proof.load_bound_policy()
    admitted = proof.admitted_actions(
        binding, proof.use_view(), authority=proof_store)

    assert [action["kind"] for action in admitted] \
        == ["construct_method", "stop"]
    assert admitted[0] == {
        "kind": "construct_method",
        "target": "ad01-w1-within-sw-00",
        "inputs": {"max_queries": 4},
        "evidence_refs": [],
        "requested_resources": {"queries": 4},
    }
    assert admitted[1] == {
        "kind": "stop",
        "target": "ad01-w1-within-sw-00",
        "inputs": {"reason": "candidate complete"},
        "evidence_refs": [],
        "requested_resources": {},
    }
    assert all(action["kind"] != policy_action.USE for action in admitted)
    assert all(action["kind"] != "use_method" for action in admitted)


def test_the_two_columns_never_overlap_except_at_stop():
    columns = proof.vocabulary_columns()

    assert columns["step_abi"] == (
        "construct_method", "diagnose", "propose_revision", "request_model",
        "stop", "use_method")
    assert columns["shared_contract"] == (
        "check", "construct", "observe", "probe", "stop", "use")
    assert columns["shared_between"] == ("stop",)
    assert columns["step_only"] == (
        "construct_method", "diagnose", "propose_revision", "request_model",
        "use_method")
    assert columns["shared_only"] == (
        "check", "construct", "observe", "probe", "use")


def test_the_two_vocabularies_refuse_each_others_use_action(proof_store):
    """A fixture that only satisfies one parser proves nothing."""
    view = proof.use_view()
    shared_use = proof.seed_policy_source(proof.BASELINE_METHOD).replace(
        "'use_method'", "'use'")

    with pytest.raises(policy_action.ActionRefused) as refusal:
        policy_action.parse_action(
            {"kind": "use_method", "target": "ad01-w1-within-sw-00",
             "inputs": {}, "evidence_refs": [],
             "requested_resources": {}})
    assert "unknown action kind 'use_method'" in str(refusal.value)

    step_binding = proof.PolicyBinding_(
        source=shared_use, recorded_digest=proof.sha256_of(shared_use),
        origin="fixture-stand-in", durable=False)
    with pytest.raises(method_exec.MethodExecutionError) as step_refusal:
        method_exec.run_step_out_of_process(
            shared_use, view, {}, dsn=proof_store["dsn"],
            allocation_id=proof_store["allocation_id"],
            operation_id=proof._operation_id(step_binding, view))
    assert "unknown policy action kind: 'use'" in str(step_refusal.value)


def test_the_step_fixture_satisfies_the_real_step_abi(proof_store):
    """The fixture must pass the shipped validator, not a private one."""
    source = proof.seed_policy_source(proof.BASELINE_METHOD)
    record = proof.make_record(source)
    artifact = policy_step.verify_policy_record(record)
    result = proof.execute_bound_policy(
        proof.PolicyBinding_(source=source,
                             recorded_digest=proof.sha256_of(source),
                             origin="fixture-stand-in", durable=False),
        proof.use_view(), {}, authority=proof_store,
        operation_id=proof._operation_id(
            proof.PolicyBinding_(source=source,
                                 recorded_digest=proof.sha256_of(source),
                                 origin="fixture-stand-in", durable=False),
            proof.use_view()))

    assert artifact["entry"] == "STEP"
    assert artifact["abi"] == "ad01-policy-step-v1"
    assert artifact["source_digest"] == proof.sha256_of(source)
    policy_step.validate_step_result(
        {"action": result["action"], "state": result["state"]})
    assert result["action"]["kind"] == "use_method"


def test_the_report_names_the_operational_policy_as_governing(proof_store):
    """The policy governs, because the use phase takes its method from it.

    An intermediate version of this test said `task-method` and explained it
    by the bound policy admitting only `construct_method` then `stop`. That
    explanation was about the pipeline, and the pipeline has since changed:
    the pilot now hands the use phase a policy built for that step, so the
    admitted action reaches use and the verdict follows the evidence.
    """
    report = proof.column_report(authority=proof_store)

    assert report["governing_column"] == proof.PROVING
    assert report["operational_policy"]["verdict"] == proof.PROVING
    assert report["task_method"]["verdict"] == proof.NOT_PROVING
    assert report["operational_policy"]["reaches_use_phase"] is True
    assert [a["kind"] for a in report["operational_policy"]["admitted_actions"]] \
        == ["construct_method", "stop"]
    assert report["digest_copy_site"] == "scripts/s09_pilot.py:1142"


def test_the_use_phase_the_pilot_calls_now_takes_a_policy():
    """`run_study` passes a policy to `run_use`, which accepts one."""
    reach = proof.use_phase_names_policy()

    assert "policy" in reach["signature"]


def test_the_use_phase_refuses_instead_of_running_the_repertoire_method():
    """With no policy the use phase refuses. It no longer answers greedy."""
    records = proof.use_episode(None)

    assert len(records) == 1
    record = records[0]
    assert record["selected"] == "refused"
    assert record["executed"] == "refused"
    assert record["fallback_reason"] == (
        "use ran with no policy: the method identity must come from an"
        " admitted policy action")
    assert record["output"] == {}


def test_the_four_committed_p1_use_records_name_two_different_columns():
    census = proof.recorded_p1_use_census()

    assert len(census["rows"]) == 4
    assert census["recomputation_agrees"] is True
    assert census["policy_column_equals_method_column"] is False
    for row in census["rows"]:
        assert row["recorded_policy_digest"] == BOUND_POLICY_DIGEST
        assert row["recorded_executed_source_digest"] \
            == AUTHORED_METHOD_DIGEST
        assert row["recomputed_executed_source_digest"] \
            == AUTHORED_METHOD_DIGEST
        assert row["selected"] == "acquired-sw-3834317f"
    assert sorted(row["task_id"] for row in census["rows"]) \
        == sorted(proof.P1_SOFTWARE_USE_TASKS)


def test_the_pilot_authored_method_hashes_to_the_executed_column():
    """The digest the review named is the method the pipeline ran."""
    from scripts import s09_pilot

    assert proof.sha256_of(s09_pilot.METHOD_SOURCE) == AUTHORED_METHOD_DIGEST
    assert proof.sha256_of(s09_pilot.P1_POLICY_SOURCE) == BOUND_POLICY_DIGEST
    assert proof.SEED_METHOD_SOURCE == s09_pilot.METHOD_SOURCE


def test_substitution_changes_the_admitted_action_with_the_repertoire_fixed(
        proof_store):
    baseline = proof.seed_policy_source(proof.BASELINE_METHOD)
    substitute = proof.seed_policy_source(proof.SUBSTITUTE_METHOD)
    result = proof.substitute(baseline, substitute, authority=proof_store)

    assert result.repertoire_digest == AUTHORED_METHOD_DIGEST
    assert result.method_digests[0] == result.method_digests[1] \
        == AUTHORED_METHOD_DIGEST
    assert result.actions[0][0] == (
        "use_method", "ad01-w1-within-sw-00",
        '{"max_queries": 4, "method_id": "seed-sw-greedy"}')
    assert result.actions[1][0] == (
        "use_method", "ad01-w1-within-sw-00",
        '{"max_queries": 4, "method_id": "seed-sw-ddmin"}')
    assert result.actions[0][1] == result.actions[1][1] == (
        "stop", "ad01-w1-within-sw-00", '{"reason": "episode complete"}')
    assert result.differs is True
    assert result.changes_the_episode is True
    assert result.differing_action == (
        "use_method", "ad01-w1-within-sw-00",
        '{"max_queries": 4, "method_id": "seed-sw-ddmin"}')


def test_substitution_changes_the_candidate_the_episode_produces(proof_store):
    result = proof.substitute(
        proof.seed_policy_source(proof.BASELINE_METHOD),
        proof.seed_policy_source(proof.SUBSTITUTE_METHOD),
        authority=proof_store)

    assert result.outcomes[0][0] == (
        "69261adb2d554896bc5255930f7de441166b84259cf80abbfe4124f49a9e2f25")
    assert result.outcomes[1][0] == (
        "8982a65da5f192a736333e1768031657dbd27f3b2bb58c8d4c0e40ed3e832aa3")
    assert result.outcomes[0][0] != result.outcomes[1][0]
    assert result.outcomes[0][1] == result.outcomes[1][1]


def test_substitution_is_backed_by_the_policy_that_governs_use(proof_store):
    """Substitution changes the episode, and a policy is what runs it.

    While no policy reached the use phase these two were independent, and
    that independence was the diagnosis. They agree now.
    """
    result = proof.substitute(
        proof.seed_policy_source(proof.BASELINE_METHOD),
        proof.seed_policy_source(proof.SUBSTITUTE_METHOD),
        authority=proof_store)
    report = proof.column_report(authority=proof_store)

    assert result.differs is True
    assert report["governing_column"] == proof.PROVING
    assert report["operational_policy"]["reaches_use_phase"] is True


def test_disconnect_refuses_with_the_exact_typed_refusal():
    outcome = proof.disconnect_probe()

    assert outcome.refused is True
    assert outcome.refusal_recorded is True
    assert outcome.fell_back_to_method is False
    assert outcome.executed == "refused"
    assert outcome.decision == {
        "status": "refused",
        "reason": "decision consumer disconnected: policy dispatcher unavailable",
        "corrections": 0,
    }


def test_a_disconnected_policy_blocks_the_method_from_running():
    """The refusal is not cosmetic: no method output is produced."""
    binding = proof.load_bound_policy()
    consumer = agenda_policy.step_policy_consumer({
        "artifact": binding.as_policy_record()["artifact"],
        "source_digest": binding.recorded_digest,
        "entry": "STEP",
        "policy_source": binding.source,
    }, dsn=None, cid=proof.CAMPAIGN_ID)
    outcome = proof.disconnect(consumer, proof.use_view())
    records = outcome.records

    assert outcome.refused is True
    assert outcome.fell_back_to_method is False
    assert len(records) == 1
    assert records[0]["status"] == "refused"
    assert records[0]["executed"] == "refused"
    assert records[0]["normalized_reduction"] == 0.0
    assert records[0]["fallback_reason"] == (
        "decision consumer disconnected: policy dispatcher unavailable")
    assert records[0]["output"] == {}


def test_the_shipped_use_path_refuses_while_the_policy_is_gone():
    """The fallback is gone. This was the blocker; the docstring records that.

    It used to assert that the shipped path produced `seed-sw-greedy` at 0.625
    reduction while the policy consumer refused in the same process, kept
    green so the finding would not be lost. `run_use` now takes a policy and
    refuses, so the shipped path refuses too, and the fallback is deleted
    rather than left beside the refusal that replaced it.
    """
    fallback = proof.shipped_path_fallback()

    assert fallback["consults_policy"] is True
    assert fallback["consumer_refused"] == {
        "status": "refused",
        "reason": "decision consumer disconnected: policy dispatcher unavailable",
        "corrections": 0,
    }
    assert fallback["shipped_selected"] == "refused"
    assert fallback["shipped_executed"] == "refused"
    assert fallback["shipped_reduction"] == 0.0
    assert fallback["identical_to_policy_run"] is True


def test_the_shipped_use_path_must_refuse_when_the_policy_is_gone():
    """BLOCKER S09R-02. Left red on purpose.

    The review required a disconnect that refuses rather than falls back
    silently. The shipped `trajectory.run_use` takes no policy at all, so
    removing one cannot change it: the use phase answers
    `seed-sw-greedy` while the connected consumer is refusing in the same
    process. The asserts below name the values that should replace what
    the pipeline returns today.

    Closing this needs a change in `trajectory.run_use` or
    `scripts/s09_pilot.py`.
    """
    fallback = proof.shipped_path_fallback()

    assert fallback["shipped_executed"] == "refused", (
        "run_use executed %r after the policy dispatcher refused; it must"
        " refuse instead of falling back to the authored method"
        % fallback["shipped_executed"])
    assert fallback["shipped_reduction"] == 0.0, (
        "a refused policy must yield a zero reduction, not %r"
        % fallback["shipped_reduction"])
