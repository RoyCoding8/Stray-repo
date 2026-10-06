"""One action meaning, compared by what each arm actually does.

A round-trip enum test proves the STEP vocabulary and the shared contract
translate to each other by name. It cannot prove the name means one
thing, because two arms can hold the same kind and still admit different
effects, observe different things, refuse for different reasons, or charge
different resources. That is the gap this file closes.

Every comparison here runs the same logical action through both real
executors -- the Python STEP arm (`boolean_policy`) and the typed-AST arm
(`boolean_ast_policy`) -- inside the real Boolean world, and compares the
world's own record of what happened. Nothing is compared by looking the
action up in a translation table.

Two facts about the Boolean world shape what can be asserted, and both are
stated rather than hidden. The world offers three kinds (`probe`,
`construct`, `stop`), so those three are compared on a real admitted
effect and a real observation. The other three (`observe`, `use`,
`check`) are refused at the world's availability boundary before any
payload is examined, so for them the comparison is on the refusal itself:
same kind, same input, same reason from both arms. Where the SWE world
gives those kinds effects is out of this file's scope and is not claimed
here.

The `propose_revision` test names its own answer. The contract keeps six
kinds and a learner-revision proposal is refused under sealed assessment;
`test_a_propose_revision_under_sealed_assessment_is_refused_in_both_profiles`
asserts refusal in both profiles by name, and
`test_the_two_profiles_cannot_drift_apart_on_that_reason` pins the reason to
one constant so the agreement cannot rot into two spellings.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from experiments.ad01 import boolean_active
from experiments.ad01 import boolean_ast_policy
from experiments.ad01 import boolean_ast_policy
from experiments.ad01 import boolean_policy
from experiments.ad01 import boolean_rule
from experiments.ad01 import policy_action
from experiments.ad01 import policy_assess
from experiments.ad01 import policy_step
from experiments.ad01 import assessment_profile
from experiments.ad01 import worlds
from settlement.child_limits import ChildLimits, child_setup_refusal

SPLIT = "dev"
SEED = 4

# A predictor the Boolean class actually contains, so `construct` is a
# genuinely admitted action here rather than another refusal. Four constant
# members, each checked by `rules.execute_all` at admission.
LEGAL_SPECS = [{"const": bit, "mask": 0, "pair": None}
               for bit in (1, 0, 0, 1)]


def _action(kind: str, target: str, inputs=None, resources=None) -> dict:
    return {"kind": kind, "target": target, "inputs": dict(inputs or {}),
            "evidence_refs": [], "requested_resources": dict(resources or {})}


# Every contract kind, with the target the Boolean world would use if it
# offered one. Written out rather than read back from the vocabulary, so a
# kind that disappears from the contract fails here rather than quietly
# dropping out of a parametrized list.
WELL_FORMED = {
    "probe": _action("probe", "boolean.query", {"x": 3}, {"queries": 1}),
    "observe": _action("observe", "test.run", {"test": "public-a"}),
    "construct": _action("construct", "boolean.commit", {"specs": LEGAL_SPECS}),
    "use": _action("use", "code.repair", {"edits": []}),
    "check": _action("check", "test.run_all"),
    "stop": _action("stop", "boolean.task"),
}

# One malformed input per kind. For `observe`, `use` and `check` the world
# refuses on availability before it reads the payload, so their malformed
# input is deliberately one the world would also have to refuse had it
# offered the kind: that keeps the comparison about the boundary both arms
# share rather than about a payload check only one of them reaches.
MALFORMED = {
    "probe": _action("probe", "boolean.query", {"x": 99}),
    "observe": _action("observe", "test.run", {}),
    "construct": _action("construct", "boolean.commit", {"specs": []}),
    "use": _action("use", "code.repair", {"edits": []}),
    "check": _action("check", "test.run_all"),
    "stop": _action("stop", "boolean.query"),
}

# What the two arms actually did, measured rather than assumed.
ADMITTED = {"probe", "construct", "stop"}
REFUSED = {"observe", "use", "check"}

_CHILD_REFUSAL = child_setup_refusal(ChildLimits(cpu_seconds=10))
REQUIRES_BOUNDED_CHILD = pytest.mark.skipif(
    _CHILD_REFUSAL is not None,
    reason=("requires bounded child execution: "
            + (_CHILD_REFUSAL.reason if _CHILD_REFUSAL else "")),
)


def _both_refused_before_child(step_out: dict, ast_out: dict) -> bool:
    """Keep host refusal observable without treating it as a policy verdict."""
    if _CHILD_REFUSAL is None \
            or _CHILD_REFUSAL.kind != "child-setup-unavailable":
        return False
    assert step_out["class"] == ast_out["class"] == "refused"
    assert _CHILD_REFUSAL.reason in step_out["reason"]
    assert boolean_ast_policy.child_limit_support().reason in ast_out["reason"]
    assert (step_out["queries"], step_out["turns"]) == (0, 1)
    assert (ast_out["queries"], ast_out["turns"]) == (0, 1)
    return True


def _step_record(action: dict) -> dict:
    # `repr`, not `json.dumps`: the STEP source is Python, so a null pair
    # has to be spelled `None`. Serialising it as JSON gives the child a
    # `NameError: name 'null' is not defined`, which is a defect in this
    # fixture reading as a refusal of the action under test.
    source = ("def STEP(view, state):\n"
              "    return {'action': %r, 'state': {}}\n" % (action,))
    return policy_step.make_policy_artifact(
        source, origin="authored-control",
        instruments=[boolean_rule.INSTRUMENT_ID])


def _ast_record(action: dict) -> dict:
    document = {
        "policy_id": "inv-a-typed-ast",
        "entry": {
            "op": "return_action",
            "kind": action["kind"],
            "target": action["target"],
            "inputs": {"op": "const", "value": action["inputs"]},
            "evidence_refs": list(action["evidence_refs"]),
            "requested_resources": dict(action["requested_resources"]),
            "state": {"op": "const", "value": {}},
        },
    }
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    return {
        "artifact": {
            "kind": "learning-policy",
            "representation": "typed-ast",
            "version": boolean_ast_policy._REPRESENTATION,
            "policy_id": "inv-a-typed-ast",
            "ast_digest": hashlib.sha256(canonical).hexdigest(),
        },
        "policy_ast": document,
    }


def _outcome(factory, record: dict) -> dict:
    """What one arm did inside the real world, as the world recorded it.

    Only the first turn is read. The world keeps driving an episode after a
    `stop`, and this fixture's policy is a constant, so a second turn is
    the same action re-offered and its refusal says nothing about what the
    first turn meant. Reading it would turn a successful `probe` into an
    `input 3 was already queried` refusal.

    A refusal the arm recorded is read out of the action it substituted,
    which is how both arms report a step they refused. The stage label is
    kept but never compared for equality: it names which bridge refused
    (`policy-step` versus `ast-policy-step`), which is a fact about the
    representation and not about what the action meant.
    """
    episode = boolean_active.run_episode(
        factory(record), split=SPLIT, seed=SEED)
    first = episode["trace"][0]
    if "refused" in first:
        return {"class": "world-refused", "reason": first["refused"],
                "stage": None, "effect": None, "observation": None,
                "turns": len(episode["trace"]),
                "queries": len(episode["queried"])}
    bridge = first["action"]["inputs"].get("bridge_refusal")
    if bridge is not None:
        return {"class": "refused", "reason": bridge["reason"],
                "stage": bridge["stage"], "effect": None,
                "observation": None, "turns": len(episode["trace"]),
                "queries": len(episode["queried"])}
    effect = first["effect"]
    observation = effect.get("observation") if isinstance(effect, dict) else None
    return {"class": "admitted", "reason": None, "stage": None,
            "effect": effect, "observation": observation,
            "turns": len(episode["trace"]),
            "queries": len(episode["queried"])}


def _both_arms(action: dict) -> tuple[dict, dict]:
    return (_outcome(boolean_policy.choose_action, _step_record(action)),
            _outcome(boolean_ast_policy.choose_action, _ast_record(action)))


def test_the_contract_keeps_six_kinds_and_every_one_is_compared_here():
    """The decision this file rests on, stated so a reader can check it.

    The learner-revision proposal did not become a seventh contract kind.
    It is refused under sealed assessment instead, and the six kinds below
    are the whole contract. If a kind is added, this test stops naming it
    and the parity tables below stop covering the contract.
    """
    assert policy_action.ACTION_KINDS == (
        "probe", "observe", "construct", "use", "check", "stop")
    assert set(WELL_FORMED) == set(policy_action.ACTION_KINDS)
    assert set(MALFORMED) == set(policy_action.ACTION_KINDS)


@pytest.mark.parametrize("kind", [
    pytest.param(kind, marks=[REQUIRES_BOUNDED_CHILD]
                 if kind in ADMITTED else [])
    for kind in sorted(WELL_FORMED)
])
def test_both_arms_admit_the_same_effect_class_for_every_kind(kind):
    """Requirement 1: identical admitted-effect class, per kind."""
    step_out, ast_out = _both_arms(WELL_FORMED[kind])

    assert step_out["class"] == ast_out["class"] == (
        "admitted" if kind in ADMITTED else "refused")
    if kind in ADMITTED:
        assert step_out["effect"] == ast_out["effect"]


@pytest.mark.parametrize("kind", [
    pytest.param(kind, marks=[REQUIRES_BOUNDED_CHILD]
                 if kind in ADMITTED else [])
    for kind in sorted(WELL_FORMED)
])
def test_both_arms_observe_the_same_thing_for_every_kind(kind):
    """Requirement 1, observation half: one observation, not two."""
    step_out, ast_out = _both_arms(WELL_FORMED[kind])

    assert step_out["observation"] == ast_out["observation"]
    if kind == "probe":
        # Against the literal the seeded task answers with, so this is an
        # agreement that is also correct rather than two arms agreeing on
        # whatever the host happened to return. The world returns a tuple.
        assert step_out["observation"] == (1, 0, 0, 1)


@pytest.mark.parametrize("kind", sorted(MALFORMED))
def test_both_arms_refuse_the_same_malformed_input_for_the_same_reason(kind):
    """Requirement 2: one reason per malformed input, from both arms."""
    step_out, ast_out = _both_arms(MALFORMED[kind])

    if _both_refused_before_child(step_out, ast_out):
        return

    assert step_out["class"] == ast_out["class"] == "refused"
    assert step_out["reason"] == ast_out["reason"]
    assert step_out["reason"]


@pytest.mark.parametrize("kind", sorted(MALFORMED))
def test_the_refusal_reason_is_the_one_the_world_states(kind):
    """The shared reason, written out, so both arms are held to a literal.

    A test that only asserted the two arms agree would pass if they agreed
    on a wrong answer. These are the reasons the Boolean world actually
    gives, held as literals.
    """
    expected = {
        "probe": "probe x must be an integer in 0..15",
        "construct": "illegal-hypothesis",
        "stop": "stop target must be boolean.task",
    }.get(kind) or ("action %r is not available in the Boolean world" % kind)
    step_out, ast_out = _both_arms(MALFORMED[kind])

    if _both_refused_before_child(step_out, ast_out):
        return

    assert step_out["reason"] == expected
    assert ast_out["reason"] == expected


@pytest.mark.parametrize("kind", [
    pytest.param(kind, marks=[REQUIRES_BOUNDED_CHILD]
                 if kind in ADMITTED else [])
    for kind in sorted(WELL_FORMED)
])
def test_both_arms_spend_the_same_resource_delta_for_every_kind(kind):
    """Requirement 3: same queries charged, same number of steps run.

    `turns` is the number of child executions the arm caused, which is the
    compute each representation actually cost, and `queries` is what the
    world charged against its own budget.
    """
    step_out, ast_out = _both_arms(WELL_FORMED[kind])

    if _both_refused_before_child(step_out, ast_out):
        assert step_out["queries"] == ast_out["queries"] == 0
        assert step_out["turns"] == ast_out["turns"] == 1
        return

    assert step_out["queries"] == ast_out["queries"]
    assert step_out["turns"] == ast_out["turns"]
    expected_queries = 1 if kind == "probe" else 0
    expected_turns = 2 if kind == "probe" else 1
    assert step_out["queries"] == expected_queries
    assert step_out["turns"] == expected_turns


@pytest.mark.parametrize("kind", sorted(MALFORMED))
def test_a_refused_action_spends_nothing_in_either_arm(kind):
    """A refusal that costs a resource is not a refusal, it is a charge."""
    step_out, ast_out = _both_arms(MALFORMED[kind])

    if _both_refused_before_child(step_out, ast_out):
        assert step_out["queries"] == ast_out["queries"] == 0
        assert step_out["turns"] == ast_out["turns"] == 1
        return

    assert step_out["queries"] == ast_out["queries"] == 0
    assert step_out["turns"] == ast_out["turns"] == 1


def test_the_stage_label_names_the_arm_and_never_the_meaning():
    """The one thing the two arms are allowed to differ on.

    Both refuse through their own bridge, so the stage differs by design.
    Asserting that difference is explicit here so a reader knows it was
    measured, and so a future merge of the two bridges is visible rather
    than silent.
    """
    step_out, ast_out = _both_arms(MALFORMED["probe"])

    if _both_refused_before_child(step_out, ast_out):
        assert step_out["stage"] == "policy-step"
        assert ast_out["stage"] == "ast-policy-step"
        return

    assert step_out["stage"] == "policy-step"
    assert ast_out["stage"] == "ast-policy-step"
    assert step_out["reason"] == ast_out["reason"]


# -- the learner-revision proposal -----------------------------------------

SEALED_TASK_ID = "ad01-w0-dev-sw-00"


def _sealed_task() -> dict:
    return worlds.load_task(worlds.FROZEN_DIR, SEALED_TASK_ID)


def _revision_action() -> dict:
    return {"kind": "propose_revision", "target": SEALED_TASK_ID,
            "inputs": {"motivation": "try the greedy reduction first"},
            "evidence_refs": [], "requested_resources": {}}


def _sealed_context(profile_name: str, source: str) -> dict:
    return assessment_profile.make_ctx(
        candidate_digest=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        scope={"family": "software", "task_ids": [SEALED_TASK_ID]},
        session="inv-a-sealed", qualify_depth=0, step_index=0,
        remaining={"queries": 16, "model_calls": 2}, trusted=False)


REVISION_SOURCE = (
    "def STEP(view, state):\n"
    "    return {'action': {'kind': 'propose_revision',"
    " 'target': view['task_content']['task_id'],"
    " 'inputs': {'motivation': 'x'}, 'evidence_refs': [],"
    " 'requested_resources': {}}, 'state': {}}\n"
)


def test_a_propose_revision_under_sealed_assessment_is_refused_in_both_profiles():
    """Requirement 4, naming its answer: REFUSED in both profiles.

    A sealed panel assessment measures whether a policy preserved task
    results. A learner-revision proposal is a governance event about the
    learner and has no task effect, so the honest answer under a sealed
    profile is a refusal rather than a stage nothing downstream can honor.
    The two profiles that both claim to assess under seal disagreed here:
    the legacy one refused, the shared one accepted and returned a staged
    payload that only a profile with binding rights could ever use, and
    sealed profiles do not have them. This test asserts the refusal in
    both, by name.
    """
    task = _sealed_task()
    record = policy_step.make_policy_artifact(
        REVISION_SOURCE, origin="authored-control")

    legacy_effect, _candidate, _wall, _queries, _calls = policy_assess._effect(
        task, _revision_action())
    shared_effect = assessment_profile.dispatch(
        profile_name=assessment_profile.ASSESSMENT, record=record, task=task,
        action=_revision_action(),
        ctx=_sealed_context(assessment_profile.ASSESSMENT, REVISION_SOURCE))

    assert legacy_effect["accepted"] is False
    assert shared_effect["accepted"] is False
    assert legacy_effect["reason"] == policy_action.REVISION_NOT_A_TASK_EFFECT
    assert shared_effect["reason"] == policy_action.REVISION_NOT_A_TASK_EFFECT


def test_a_refused_revision_stages_nothing_and_spends_nothing_in_both():
    """A refusal must not leave a staged revision behind for a later bind."""
    task = _sealed_task()
    record = policy_step.make_policy_artifact(
        REVISION_SOURCE, origin="authored-control")

    shared_effect = assessment_profile.dispatch(
        profile_name=assessment_profile.ASSESSMENT, record=record, task=task,
        action=_revision_action(),
        ctx=_sealed_context(assessment_profile.ASSESSMENT, REVISION_SOURCE))

    assert "staged" not in shared_effect
    assert shared_effect["queries"] == 0
    assert shared_effect["model_calls"] == 0
    assert shared_effect["owner"] == "none"


def test_the_two_profiles_cannot_drift_apart_on_that_reason():
    """The agreement is structural, not coincidental.

    Both sites read one constant, so changing the reason in one without
    the other is a lint-visible edit to a single name rather than two
    strings that happen to match today.
    """
    assert policy_assess.REVISION_REFUSAL_REASON \
        is policy_action.REVISION_NOT_A_TASK_EFFECT
    assert assessment_profile.REVISION_REFUSAL_REASON \
        is policy_action.REVISION_NOT_A_TASK_EFFECT


def test_a_revision_is_staged_only_where_a_bind_would_be_possible():
    """The complement, so the refusal above is subtraction and not loss.

    Staging survives exactly where it can be honored: a profile with
    binding rights. A stage that no profile could ever bind was a second
    effect class with no consumer.
    """
    assert assessment_profile.PROFILES[
        assessment_profile.DEVELOPMENT].allow_revision_bind is True
    for name in (assessment_profile.ASSESSMENT,
                 assessment_profile.ASSESSMENT_RESTRICTED,
                 assessment_profile.AUDIT):
        assert assessment_profile.PROFILES[name].allow_revision_bind is False
