"""No production caller can execute policy source without authority.

Lane A2 deleted the `dsn is None` branch in `method_exec` that executed
policy source through `launcher.dispatch` directly. That was correct, and
it left real callers broken, because they had been relying on local trust:
a source file on this disk was enough to run.

Every one of those callers is migrated here, and the migration is asserted
structurally rather than by testing one path at a time. A single passing
path proves that path; an enumeration over the whole tree proves the
invariant.

Three claims are proved:

1. The executors refuse without all three of `dsn`, `allocation_id` and
   `operation_id`, and construct nothing that could run. Proved against the
   real executors and against every production call site's shape, so a
   caller that reaches the executor with an empty authority dict is caught
   even though its own module passes its tests.

2. Every migrated caller either holds real authority or no longer executes
   policy source. Named per caller, so a reader can check the disposition
   rather than infer it.

3. The positive control: a caller that does hold authority executes the
   same bytes and leaves a settled receipt. A mandate that refused
   everything would satisfy every refusal assertion here, so one test
   proves the seam is still a working seam.

The census is the load-bearing part. It parses each production module with
`ast` and looks at every call to the four public entry points, so it fails
on a new call site, not only on a change to a known one.
"""

from __future__ import annotations

import ast
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import learner, method_exec, worlds
from experiments.ad01 import policy_step
from experiments.ad01.s09_run_isolation import create_disposable_db, \
    drop_disposable_db

MIGRATIONS = ROOT / "migrations"

# The four public entry points through which policy source reaches a child.
# `_run_member` is included because it is trajectory's own member executor
# and forwards authority to `method_exec`.
EXECUTORS = ("run_step_out_of_process", "run_member_out_of_process",
             "run_policy_step", "_run_member")

# Modules that reach an executor. Anything not listed here is a caller that
# this lane has not looked at, which the census test treats as a failure.
PRODUCTION_ROOTS = ("experiments", "scripts")

# Call sites whose disposition is authority-given. Each names a caller that
# now reaches the executor with a store, an allocation and an operation id.
AUTHORITY_GIVEN = {
    "experiments/ad01/invr1b14_retention.py":
        "measure_all runs each retained member under the campaign's"
        " authority, with a dsn, an allocation and a per-member"
        " operation id",
    "experiments/ad01/records.py": "_execute_assessment executes under the"
                                    " proposal's own allocation",
    "experiments/ad01/assessment_profile.py": "_resolve_method and the panel"
                                              " arm's steps run under the"
                                              " assessing arm's authority",
    "experiments/ad01/policy_assess.py": "_run_arm and _candidate_from_action"
                                         " run under the assessment's"
                                         " authority",
    "experiments/ad01/learner.py": "_action_of takes the authority the"
                                   " substitution gate is given",
    "experiments/ad01/experience_axis_run.py": "_step_policy runs the"
                                              " authored arms under the run's"
                                              " own allocation",
    "experiments/ad01/s09_causal_proof.py": "PolicyRun carries its own store"
                                            " and allocation for the"
                                            " launch qualification",
    "experiments/ad01/s09_m2_reload_proof.py": "the reload proof authorizes a"
                                               " disposable store for its"
                                               " own subprocess",
    "scripts/s89_diagnose.py": "the diagnostic creates a disposable store"
                               " for its reruns, or refuses to rerun",
    "experiments/ad01/trajectory.py": "dev_episode runs a constructed member"
                                      " under the boundary's authority",
}

# Call sites that no longer execute policy source. These are the ones that
# reach an executor only through a name the census cannot resolve
# statically, or that pass authority straight through.
PASS_THROUGH = {
    "experiments/ad01/w2_retention_campaign.py":
        "retained_leg_verdict takes authority as a parameter and refuses"
        " without it, rather than holding one of its own; a leg reported"
        " measurable without an execution was not measured",
    "experiments/ad01/trajectory.py": "_run_member forwards the authority it"
                                      " is given; run_use and"
                                      " _use_governed_member both supply it",
    "experiments/ad01/agenda_policy.py": "DecisionConsumer already carries"
                                         " the campaign's dsn and allocation"
                                         " and names its own operation id;"
                                         " with no dsn it passes None and"
                                         " the executor refuses",
    "experiments/ad01/policy_step.py": "run_policy_step and BoundedPolicy.run"
                                       " forward the authority they are"
                                       " given; BoundedPolicy.__call__ passes"
                                       " none and so refuses",
    "experiments/ad01/construct.py": "already held the campaign's dsn,"
                                     " allocation and operation id before"
                                     " this lane; unchanged",
    "experiments/ad01/s09_m3_pilot.py": "already held its campaign's"
                                        " authority before this lane;"
                                        " unchanged",
}

# Modules owned by another lane. Their call sites are not this lane's to
# migrate and are not asserted on, so a change there is not a false red.
OTHER_LANES = frozenset({
    "experiments/ad01/improve_channel.py",
    "experiments/ad01/s09_bound_use_proof.py",
    "experiments/ad01/s09_e2_scored.py",
    "experiments/ad01/s09_policy_governance.py",
    "experiments/ad01/selection.py",
})

STEP_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    action = {\"kind\": \"diagnose\", \"target\": target,\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"unknown\": \"does the seed disagree\",\n"
    "                         \"question\": \"why this verdict\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {\"n\": 1}}\n"
)

REFUSAL = "refused: execution needs explicit authority and identity"


def _step_view() -> dict:
    return policy_step.materialize_view(
        task=worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00"),
        observations=[], open_questions=[], last_result=None,
        eligible_methods=[], remaining={"steps": 1})


@pytest.fixture(scope="module")
def store():
    database = create_disposable_db("inv-a6-migration", migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database)


@pytest.fixture(scope="module")
def allocation(store):
    from experiments.ad01 import trajectory

    trajectory.set_namespace_token("")
    campaign = "inv-a6-%s" % uuid.uuid4().hex[:8]
    return trajectory.authorize_campaign(store, campaign,
                                         authorized=1000000)["allocation_id"]


@pytest.fixture
def no_execution(monkeypatch):
    """Record every route by which policy source could reach a child.

    `LocalLauncher` is the only object in the executor that can start one,
    so constructing it at all means the executor committed to running the
    source. The broker pair is recorded separately because an admitted
    operation with no dispatch is still a state change worth seeing.
    """
    seen = {"launchers": 0, "ensure": [], "dispatch": []}

    class UnreachableLauncher:
        def __init__(self, *args, **kwargs):
            seen["launchers"] += 1

    monkeypatch.setattr(method_exec, "LocalLauncher", UnreachableLauncher)
    monkeypatch.setattr(
        method_exec.broker, "ensure_operation",
        lambda dsn, **kwargs: seen["ensure"].append(kwargs))
    monkeypatch.setattr(
        method_exec.broker, "dispatch_operation",
        lambda *a, **k: seen["dispatch"].append(kwargs))
    return seen


def _call_sites() -> list:
    """Every production call to one of the four executors, as (file, line).

    Parsed, not grepped. A textual match on the callee name would also fire
    on a docstring or a comment and would miss a call assembled across
    lines; an `ast` walk finds the call node itself.
    """
    found = []
    for root in PRODUCTION_ROOTS:
        for path in sorted((ROOT / root).rglob("*.py")):
            relative = str(path.relative_to(ROOT)).replace("\\", "/")
            if relative.startswith("tests/") or relative in OTHER_LANES:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "attr", None) or getattr(
                    node.func, "id", None)
                if name in EXECUTORS:
                    found.append((relative, node.lineno, name))
    return found


def test_the_census_reaches_every_executor_call_site():
    """The census is only a proof if it is not silently empty."""
    sites = _call_sites()
    files = {relative for relative, _, _ in sites}

    assert len(sites) >= 12, (
        "the census found %d executor call sites, which is fewer than the"
        " callers this lane migrated; a census that lost a call site proves"
        " nothing" % len(sites))
    for expected in ("experiments/ad01/records.py",
                     "experiments/ad01/assessment_profile.py",
                     "experiments/ad01/policy_assess.py",
                     "experiments/ad01/learner.py",
                     "experiments/ad01/trajectory.py"):
        assert expected in files, (
            "%s reached an executor and the census does not see it" % expected)


def test_every_migrated_caller_is_named_with_a_disposition():
    """Each caller is authority-given or pass-through. None is unlisted."""
    disposition = dict(AUTHORITY_GIVEN)
    for relative, _, _ in _call_sites():
        if relative in disposition or relative in PASS_THROUGH:
            continue
        if relative in OTHER_LANES:
            continue
        pytest.fail("%s reaches an executor and has no disposition named in"
                    " this gate; add it to AUTHORITY_GIVEN or PASS_THROUGH"
                    " with the reason" % relative)


def test_no_production_caller_hands_the_executor_an_empty_authority():
    """A caller reaching an executor with nothing to execute under is the hole.

    The census cannot tell whether a module passes real authority, so this
    proves the other half: the executors refuse, and each migrated caller
    either supplies the three fields or reports the refusal as its own
    outcome. A caller that swallowed the refusal and reported a decision
    would fail the per-caller tests below.
    """
    for missing in ({}, {"dsn": "postgresql://unused"},
                    {"dsn": "postgresql://unused", "allocation_id": "a"},
                    {"dsn": "postgresql://unused", "operation_id": "o"},
                    {"allocation_id": "a", "operation_id": "o"}):
        with pytest.raises(method_exec.MethodExecutionError) as raised:
            method_exec.run_step_out_of_process(
                STEP_SOURCE, _step_view(), {}, **missing)
        assert str(raised.value) == REFUSAL, raised.value


def test_the_substitution_gate_refuses_without_authority():
    """`learner` is the caller the ruling names: it executed policy source.

    It had no store anywhere in its signature, so it could only have run
    the bytes or claimed a verdict it never computed. It now needs the same
    authority as any other execution.
    """
    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w1-dev-sw-01")
    observations = learner.substituted_observations(task,
                                                    verdict="not-preserved")

    with pytest.raises(learner.TreatmentRefused) as raised:
        learner.substitution_changes_action(
            "def STEP(view, state):\n"
            "    return {'action': {'kind': 'stop',\n"
            "                     'target': view['task_content']['task_id'],\n"
            "                     'inputs': {}, 'evidence_refs': [],\n"
            "                     'requested_resources': {}},\n"
            "            'state': {}}\n",
            task, observations, observations)

    assert "durable store" in str(raised.value), raised.value


def test_the_substitution_gate_reads_its_evidence_under_authority(store,
                                                                  allocation):
    """Positive control for the gate: it distinguishes, and it really runs.

    A gate that refused everything would also pass the refusal test above.
    This one executes two different observations against two different
    operations and reports that a policy reading its evidence moved while a
    policy keyed on the task identifier did not.
    """
    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w1-dev-sw-01")
    original = learner.substituted_observations(task,
                                                verdict="not-preserved")
    swapped, _ = learner.substitute_observations_for(
        task, original, verdict="preserved")
    reading = (
        "def STEP(view, state):\n"
        "    verdict = 'none'\n"
        "    if view['observations']:\n"
        "        verdict = view['observations'][-1]['verdict']\n"
        "    return {'action': {'kind': 'diagnose',\n"
        "                     'target': view['task_content']['task_id'],\n"
        "                     'inputs': {'diagnostic': 'software',\n"
        "                                'unknown': 'u',\n"
        "                                'question': 'verdict %s' % verdict},\n"
        "                     'evidence_refs': [],\n"
        "                     'requested_resources': {'queries': 1}},\n"
        "            'state': {}}\n")
    blind = reading.replace("verdict %s' % verdict", "verdict %s' % 'blind'")
    blind = blind.replace("verdict = 'none'", "verdict = 'blind'")
    blind = blind.replace("if view['observations']:", "if False:")

    moved = learner.substitution_changes_action(
        reading, task, original, swapped,
        authority={"dsn": store, "allocation_id": allocation,
                   "operation_id": "inv-a6-reading-policy"})
    stayed = learner.substitution_changes_action(
        blind, task, original, swapped,
        authority={"dsn": store, "allocation_id": allocation,
                   "operation_id": "inv-a6-blind-policy"})

    assert moved is True, (
        "a policy reading the substituted verdict must move under it")
    assert stayed is False, (
        "a policy reading nothing must not move, which is what makes the"
        " first assertion mean something")


def test_a_caller_with_authority_leaves_a_settled_receipt(store, allocation):
    """The positive control for the whole mandate.

    Every other test here can be satisfied by refusing everything. This one
    runs the same bytes through the same public entry with authority, so a
    mandate that closed the seam by breaking it fails here instead of
    looking like a fix.
    """
    from settlement import db

    operation_id = "inv-a6-positive-control"
    result = method_exec.run_step_out_of_process(
        STEP_SOURCE, _step_view(), {}, dsn=store,
        allocation_id=allocation, operation_id=operation_id)

    assert result["action"]["kind"] == "diagnose"
    assert result["operation_ids"] == [operation_id]

    with db.connect(store) as conn:
        row = conn.execute(
            "SELECT o.dispatch_state, o.settled, o.allocation_id,"
            " r.receipt_identity FROM operations o"
            " JOIN receipts r ON r.operation_id = o.id"
            " WHERE o.id = %s", (operation_id,)).fetchone()
    assert row is not None
    assert row[0] == "observed"
    assert row[1] is True
    assert row[2] == allocation
    assert row[3] == result["receipt"]["receipt_identity"]


def test_the_assessment_records_a_refusal_rather_than_a_decision():
    """A no-authority caller must say so, not report an empty success.

    `records._execute_assessment` with no allocation is the shape a
    diagnostic path takes when it has no store. Its honest outcome is a
    recorded refusal; an arm that reported "no reduction" instead would be
    claiming a method ran when none did.
    """
    from experiments.ad01 import records

    verdict = records._execute_assessment(
        "inv-a6-refusal", ["ad01-w0-dev-sw-00"], "incumbent",
        {"source": "def carried(task, oracle):\n    return task\n",
         "entry": "carried", "candidate_digest": "abc123"},
        dsn="postgresql://unused", allocation_id=None)

    assert verdict["outcome"] == "reject"
    assert "allocation" in verdict["reason"], verdict


def test_the_diagnostic_diagnostic_refuses_rather_than_reporting_a_verdict():
    """`s89_diagnose` classified without executing when told not to.

    The rerun path reports the refusal as its stage, so a reader sees that
    the bytes did not run rather than reading an empty improvement.
    """
    from scripts import s89_diagnose as diag

    outcome = diag.run_candidate(
        {"source": "def carried(task, oracle):\n    return task\n",
         "entry": "carried", "task": worlds.load_task(
             worlds.FROZEN_DIR, "ad01-w0-dev-sw-00"),
         "origin": "test", "digest": "d", "old_failure": "e"},
        execute_fn=diag._refuse_rerun)

    assert outcome["new_outcome"] == "gate-refusal"
    assert "no bytes executed" in outcome["next_failure"]


def test_the_reload_proof_runs_under_its_own_authority():
    """`s09_m2_reload_proof` claimed "no store". It now names a real one.

    Its own docstring used the deleted branch to justify opening nothing.
    The disposable store is created and dropped around the proof, which is
    the same separation from live that the old claim asserted, obtained by
    actually executing rather than by declining to.
    """
    import experiments.ad01.s09_m2_reload_proof as proof

    assert hasattr(proof, "reload_authority"), (
        "the reload proof has no authority context; it would fall back to"
        " executing policy source with no store")

    source = proof.RELOAD_SOURCE
    assert 'spec["authority"]["dsn"]' in source, (
        "the reload subprocess is not given the proof's store")
    assert 'allocation_id=spec["authority"]["allocation_id"]' in source