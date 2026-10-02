"""Can the frozen AST node set express the ordering world's decision?

The typed AST is refused on the ordering world with `probe target must be
schedule.compare`. That refusal is real, but the handoff asks a sharper
question than "was it refused": it asks whether the *node set* cannot
express the decision, or whether the frozen executor is simply bound to
the Boolean world's action targets.

The distinction decides what the matrix cell means. A grammar limit is a
property of the representation and no policy on any world could get
past it. A world binding is a property of one executor, and the same
document would run unchanged on a second instrument.

These tests pin the answer rather than assert it: the ordering document
is loaded by the *frozen* loader in `boolean_ast_policy`, executed by the
*frozen* executor, and driven through a real `second_active` episode. The
only thing this module supplies is the ordering world's view projection
and its action rules. No substitute interpreter is involved, so a pass
here is evidence about the frozen node set itself.

The one limit that *is* real is recorded too: the node set has no
symbolic ordering, so it cannot compare two job ids and pick the earlier
one. That is the missing cell, and it is a grammar cell.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(""))

from experiments.ad01 import boolean_ast_policy as frozen
from experiments.ad01 import ordering_ast_policy as ordering
from experiments.ad01 import policy_action
from experiments.ad01 import second_active

POLICY_ID = "e1-ordering-ast"
JOB_IDS = set(second_active.JOB_IDS)


def _fresh_state(split: str = "dev", seed: int = 4):
    task = second_active.make_task(split, seed)
    return second_active.ScheduleSession(task)


def _view(session) -> dict:
    return second_active.public_state(session)


# --- the node set accepts the document ----------------------------------


def test_the_ordering_document_loads_under_the_frozen_loader():
    """Question one, first half: the grammar accepts it.

    `load_policy` is the frozen Boolean loader, imported unchanged. If
    this passes, the refusal the matrix records is not a property of the
    node set.
    """
    record = ordering.make_ordering_ast_record()

    document, entry = frozen.load_policy(record, POLICY_ID)

    assert document["policy_id"] == POLICY_ID
    assert entry.op == "if"


def test_the_frozen_boolean_executor_refuses_the_very_same_document():
    """The refusal is real, and it is a world binding rather than a
    grammar limit.

    The identical record, run through the identical executor, is refused
    on the ordering world's view. So the document is well-formed; what
    refuses it is the hardcoded Boolean action target. This is the
    concrete attempted behaviour the handoff asks for, on the typed AST
    side: the Boolean arms cannot express the ordering decision, but the
    node set can.
    """
    record = ordering.make_ordering_ast_record()
    decide = frozen.choose_action(record)
    session = _fresh_state()

    action = decide(_view(session))

    assert action["kind"] == policy_action.STOP
    assert action["target"] == "boolean.task"
    reason = action["inputs"]["bridge_refusal"]["reason"]
    assert "probe target must be boolean.query" in reason


# --- it runs, on the real world ------------------------------------------


def test_the_first_turn_probes_a_real_pair():
    session = _fresh_state()
    decide = ordering.choose_action(ordering.make_ordering_ast_record())

    action = decide(_view(session))

    assert action["kind"] == policy_action.PROBE
    assert action["target"] == "schedule.compare"
    assert {action["inputs"]["left"], action["inputs"]["right"]} <= JOB_IDS
    assert action["inputs"]["left"] != action["inputs"]["right"]


def test_the_world_accepts_every_action_the_arm_emits():
    """Not just well-formed actions: actions the world actually applies.

    Applied through `second_active.apply_action`, so the arm's output is
    checked by the world's own rules rather than by the test's reading of
    them.
    """
    session = _fresh_state()
    decide = ordering.choose_action(ordering.make_ordering_ast_record())

    for _ in range(2):
        action = decide(_view(session))
        effect = second_active.apply_action(session, action)

    assert effect["kind"] == policy_action.CONSTRUCT
    assert effect["committed"] is True


def test_the_second_turn_commits_a_permutation_of_the_job_ids():
    session = _fresh_state()
    decide = ordering.choose_action(ordering.make_ordering_ast_record())
    decide(_view(session))
    second_active.apply_action(session, decide(_view(session)))

    action = decide(_view(session))

    assert action["kind"] == policy_action.CONSTRUCT
    assert action["target"] == "schedule.commit"
    order = action["inputs"]["order"]
    assert isinstance(order, list)
    assert len(order) == len(second_active.JOB_IDS)
    assert set(order) == JOB_IDS


def test_a_whole_episode_runs_and_commits_with_one_comparison():
    """End to end through the world's own `run_episode`.

    No turn is refused, so the arm's output is admissible at every step
    of a real episode rather than only on a hand-built view.
    """
    decide = ordering.choose_action(ordering.make_ordering_ast_record())

    result = second_active.run_episode(decide, split="dev", seed=4)

    assert result["committed"] is True
    assert result["turns"] == 2
    assert len(result["comparisons"]) == 1
    assert not [t for t in result["trace"] if "refused" in t]
    assert result["final"]["overall"] in (0.0, 1.0)


# --- the arm's own guards ------------------------------------------------


def test_the_arm_cannot_re_probe_a_pair_the_world_already_answered():
    """The view-guard, exercised through the world's own rule.

    A repeated pair would be refused by the world mid-episode, which the
    harness records as `world-action-refused` and an arm that spends its
    whole budget on doomed actions never commits. The program asks only
    while the view is empty, so it cannot.
    """
    session = _fresh_state()
    decide = ordering.choose_action(ordering.make_ordering_ast_record())
    first = decide(_view(session))
    second_active.apply_action(session, first)
    second = decide(_view(session))
    second_active.apply_action(session, second)
    with pytest.raises(second_active.ActionRefused, match="already compared"):
        second_active.apply_action(
            session, dict(second, kind=policy_action.PROBE,
                          target="schedule.compare",
                          inputs={"left": first["inputs"]["left"],
                                  "right": first["inputs"]["right"]}))


def test_a_state_carrying_hidden_tables_is_refused():
    """The projection owns the view, so a caller cannot widen its own.

    Same guard as the Boolean executor: the program is handed the
    contract view, never a world state the caller assembled. The
    callback records the refusal as a `stop` rather than raising, which
    is the shape the harness reads.
    """
    decide = ordering.choose_action(ordering.make_ordering_ast_record())
    session = _fresh_state()
    view = _view(session)
    view["tables"] = {"answer": [1, 2, 3]}

    action = decide(view)

    assert action["kind"] == policy_action.STOP
    assert "hidden tables" in action["inputs"]["bridge_refusal"]["reason"]


def test_the_state_carries_across_a_fresh_interpreter():
    """`state_contract` promises the step state survives a process.

    `ast_step` is the entry that keeps that promise: the caller owns the
    state, so a second call resumes mid-episode rather than restarting at
    the program's first branch.
    """
    record = ordering.make_ordering_ast_record()
    session = _fresh_state()

    first = ordering.ast_step(record, _view(session))
    second_active.apply_action(session, first["action"])
    second = ordering.ast_step(record, _view(session), first["state"])

    assert second["action"]["kind"] == policy_action.CONSTRUCT
    assert isinstance(second["state"], dict)


# --- the limit that is real ---------------------------------------------


def test_the_document_a_policy_would_want_is_refused_by_the_loader():
    """The genuine missing cell, with its exact refusal.

    Choosing the earlier of two job ids needs a symbolic `lt`. The node
    set's `lt` requires two numeric operands, so the document a
    comparison-sorting policy would write is refused at load. This is a
    limit of the *node set*: no policy on any world gets past it.
    """
    document = ordering.symbolic_order_document(POLICY_ID)

    with pytest.raises(frozen._LoadRefused) as caught:
        frozen._document(document)

    assert "lt requires two numeric operands" in str(caught.value)


def test_the_node_set_can_still_equality_test_two_job_ids():
    """The contrast that makes the limit specific rather than total.

    The very same document, asking the same two questions of the same two
    values, loads when the question is `eq` and is refused when it is
    `lt`. So the node set can ask which job the world named and cannot
    order two, which is exactly the cell the expressivity record names.
    """
    loadable = ordering.symbolic_order_document(POLICY_ID, comparison="eq")

    document, entry = frozen.load_policy(
        ordering._record(POLICY_ID, loadable), POLICY_ID)

    assert entry.op == "if"
    assert document["entry"]["cond"]["op"] == "eq"


# --- the record ----------------------------------------------------------


def test_the_record_is_accepted_by_the_frozen_loader_verbatim():
    """The record shape is the Boolean one, not a variant.

    Same artifact fields, same canonical digest rule, derived from the
    frozen module's own canonicalizer so the two cannot drift.
    """
    record = ordering.make_ordering_ast_record()

    assert set(record) == {"artifact", "policy_ast"}
    assert set(record["artifact"]) == {
        "kind", "representation", "version", "policy_id", "ast_digest"}
    assert record["artifact"]["kind"] == "learning-policy"
    assert record["artifact"]["representation"] == "typed-ast"
    assert record["artifact"]["version"] == frozen._REPRESENTATION
    assert record["artifact"]["policy_id"] == POLICY_ID
    frozen.load_policy(record, POLICY_ID)


def test_a_tampered_digest_is_refused():
    """A record whose digest does not match its bytes is refused.

    Guards the property that makes the record self-certifying: the
    digest is recomputed from the canonical bytes, not trusted.
    """
    record = ordering.make_ordering_ast_record()
    record["policy_ast"]["entry"]["then"]["target"] = "schedule.task"

    with pytest.raises(frozen._LoadRefused, match="canonical AST bytes"):
        frozen.load_policy(record, POLICY_ID)


# --- what the arm can do is not what it may do -------------------------


def test_a_runnable_arm_still_commits_an_order_it_contradicts():
    """The strongest statement of the missing cell, and it is a behaviour.

    The node set runs on this world, so an inexpressive representation
    cannot be the reason the arm scores zero. The reason is narrower and
    demonstrable: it commits a fixed order that contradicts the one
    comparison it paid for. The world says `build` is earlier than
    `analysis`; the arm commits `analysis` first.

    This is the Boolean matrix's finding reproduced on a second
    instrument, and it is what the missing `lt` costs in practice.
    """
    record = ordering.make_ordering_ast_record()
    result = second_active.run_episode(ordering.choose_action(record),
                                       split="dev", seed=0)

    comparison = result["comparisons"][0]
    order = next(turn["action"]["inputs"]["order"]
                 for turn in result["trace"]
                 if turn["action"]["kind"] == policy_action.CONSTRUCT)
    earlier = comparison["earlier"]
    other = comparison["right"] if earlier == comparison["left"] \
        else comparison["left"]

    assert earlier == "build" and other == "analysis"
    assert order.index(earlier) > order.index(other)
    assert result["final"]["overall"] == 0.0


def test_a_full_sweep_never_contradicts_a_turn_it_did_not_pay_for():
    """The arm is well-behaved everywhere; it is only not deriving.

    Every episode across a sweep must commit exactly one permutation and
    spend exactly one comparison, with no refused turn. If the node set
    could not express the decision, runs would break rather than merely
    score zero.
    """
    record = ordering.make_ordering_ast_record()

    for seed in range(10):
        result = second_active.run_episode(ordering.choose_action(record),
                                           split="dev", seed=seed)
        assert result["committed"] is True
        assert result["turns"] == 2
        assert len(result["comparisons"]) == 1
        assert set(result["final"]) >= {"overall", "exact", "n_comparisons"}


# --- the recorded finding ------------------------------------------------


def test_the_recorded_limits_name_the_frozen_loader_as_the_witness():
    """The finding is recorded, with the refusal that backs it.

    An expressivity claim is only worth the refusal behind it, so each
    `cannot` row names the loader call that produces its text.
    """
    limits = ordering.ordering_expressivity()

    assert limits["world"] == second_active.INSTRUMENT_ID
    assert limits["node_set"] == frozen._REPRESENTATION
    assert limits["can"], "the ordering decision must be claimed where proven"
    rows = limits["cannot"]
    assert rows, "the symbolic-ordering limit must be recorded"
    for row in rows:
        assert row["behavior"] and row["missing_cell"] and row["witness"]
    symbolic = next(r for r in rows if r["missing_cell"].startswith("no `lt`"))
    assert "lt requires two numeric operands" in symbolic["witness"]


def test_the_boolean_executor_still_records_its_own_limit():
    """The frozen claim is untouched by this module.

    `boolean_ast_policy.expressivity_limits` asserts the AST cannot act
    on the ordering world. That claim is true of *that executor* and this
    module does not edit it; what changes is that the matrix can now name
    the cause as the world binding rather than the node set.
    """
    limits = frozen.expressivity_limits()

    assert limits["representation"] == frozen._REPRESENTATION
    assert limits["worlds"]["ordering-constraints"]["can"] == []
