"""Review findings for the final-acceptance pass, 2026-10-01.

Written by the independent reviewer against `8a207ab`. No production code
was repaired here; each test is a record for the repair lane.

Three findings, all in the freeze or the chain's causal binding.

RF-01 (mechanism). The freeze admits a revision that writes a frozen field.
`_attempts_frozen_write` resolves a subscript key only when it is a string
literal, so `view.update({"grant": ...})`, `view |= {...}`, `view.clear()`
and `view.pop("grant")` all pass the static check. The documented limit
names only the computed-subscript key and says the runtime `frozen_state`
comparison in `admit_revision_under_freeze` is the layer that catches it.
That comparison cannot fire: the revision executes in a bounded child
process against a JSON view that carries no frozen field, so a revision's
bytes never reach the store being compared. Proved here by an admitted
`eligible` revision whose write lands.

RF-02 (mechanism). Arrow 3 of the milestone-A chain has no causal join.
`s09_policy_state.effect_id` was a synthesized constant
`ad01-<cid>-b<seq>-effect` (`trajectory.py:257`) that matched no
`operations` row, and no `attempt_observations` row carried an
`operation_id` or `effect_id`. Every row existed; the arrow from the effect
to the observation was bound only by `(investigation_id, seq)`. Repaired by
lane X4b: the effect identity is now the operation the boundary admitted, and
the boundary observation carries it. The record below is inverted to assert
the repair; the substantive proof against a real database is in
`tests/test_inv_x4b_effect_identity.py`.

RF-03 (trials, outside the milestone-A chain). `amend_protocol` reads the
superseded protocol on one connection, commits, and writes `supersedes`
on a second connection with autocommit. Four concurrent amends of one
protocol all apply, leaving four frozen children of the same parent and
no unique successor. Same shape as the four defects two search passes
already found: a read and a write split across connections.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import improve_channel as channel

AUTHORISED = '3 if not view["experience"] else 8'


def _mission() -> dict:
    return {
        "objective": "probe boolean rules within eight queries",
        "constraints": ["deterministic only", "no live network"],
        "success_criteria": ["committed predictor"],
        "environments": [{"instrument": "boolean-rule-v1",
                          "split": "dev", "seed": 4}],
    }


def _bound_store(tmp_path, name="rf.json"):
    from experiments.ad01 import frontier
    store = frontier.create_store(
        tmp_path / name, namespace=frontier.NAMESPACE, mission=_mission(),
        authority={"queries": 16, "steps": 12})
    base = channel.make_control("low")
    store.bind_active(base)
    return store, base


def _views(store, base, seeds=(0, 1, 2, 3)):
    from experiments.ad01 import frontier
    views = []
    for _ in seeds:
        view = store.step_view(frontier.IMPROVE, base)
        view["experience"] = []
        view["round"] = 1
        views.append(view)
    return views


# --- RF-01: a frozen write the static guard cannot see -------------------
#
# The write is smuggled into the probed-input expression, which the scope
# check blanks before comparing shapes, so the revision stays the
# authorised kind and the guard has nothing to compare against.

# `view.update(...) or 3` is the whole trick: `update` returns None, so
# the expression is `3` for the policy and the write still happens.
_SMUGGLED = ('(view.update({"grant": {"queries": 999999, "steps": 999999}})'
             ' or 3) if not view["experience"] else 8')


def _run_revision(source, view):
    """Execute revision bytes the way the bounded child does."""
    namespace = {}
    exec(source, namespace)          # noqa: S102 - the product does this
    return namespace["STEP"](view, {})


def _writable_view():
    """A view shaped like the one the child receives."""
    return {"grant": 0, "harmless": 1, "task_content": {},
            "observations": [], "frontier": [], "purpose": "improve",
            "mission": "m", "experience": [], "open_questions": [],
            "last_result": None, "eligible_methods": [],
            "remaining": {"queries": 4, "steps": 4},
            "authority_remaining": {"queries": 4, "steps": 4}, "round": 1}


# The four forms. Each names a frozen field and each writes it at runtime.
FROZEN_WRITES_THROUGH_A_METHOD = [
    ("dict.update", 'view.update({"grant": 7})'),
    ("dict augassign", 'view |= {"grant": 7}'),
    ("dict.pop", 'view.pop("grant", None)'),
    ("dict.clear", 'view.clear()'),
    ("computed subscript key", 'k = "grant"\nview[k] = 7'),
]


def test_the_guard_refuses_a_frozen_write_made_through_a_dict_method(tmp_path):
    """RF-01. `view["grant"] = x` is refused. `view.update({"grant": x})`
    writes the same key and is not.

    The assertion is on the refusal, because the refusal is the contract a
    caller observes.
    """
    store, base = _bound_store(tmp_path)
    source = channel._revision_source(_SMUGGLED)

    assert channel._attempts_frozen_write(source), (
        "a revision writing grant through dict.update was admitted by the"
        " static guard: %r" % (source,))
    assert channel.admit_revision_under_freeze(
        store, source, _views(store, base))["eligibility"] == \
        channel.INELIGIBLE_FROZEN_WRITE


@pytest.mark.parametrize("label,body",
                         FROZEN_WRITES_THROUGH_A_METHOD)
def test_every_writing_form_reaches_the_frozen_key_at_runtime(label, body):
    """The fixture each case rests on. If the bytes did not actually
    write `grant`, the refusal test above would pass on a program that
    writes nothing, and would prove nothing.

    `label` is unused by the assertion and exists so a failure names the
    form rather than a line number.
    """
    view = _writable_view()
    lines = ["def STEP(view, state):"]
    lines.extend("    " + line for line in body.splitlines())
    lines.append('    return {"action": {"kind": "stop", "target": "t",'
                 ' "inputs": {}, "requested_resources": {}}, "state": {}}')
    _run_revision("\n".join(lines) + "\n", view)

    assert view.get("grant") != 0, (
        "the %s form did not write grant, so this case proves nothing:"
        " %r" % (label, view))


def test_a_revision_writing_a_frozen_field_is_not_admitted_as_eligible(
        tmp_path):
    """RF-01 end to end, at the boundary a caller reads.

    The clean control has no frozen write. The smuggled revision must be
    refused for its write before execution or other eligibility checks.
    """
    store, base = _bound_store(tmp_path)
    source = channel._revision_source(_SMUGGLED)
    clean = channel._revision_source(AUTHORISED)

    assert channel._frozen_write_reason(clean) == "", "clean control must have no frozen write"

    verdict = channel.admit_revision_under_freeze(
        store, source, _views(store, base))

    assert verdict["eligibility"] != channel.ELIGIBLE, (
        "a revision that writes the grant was admitted as an eligible"
        " intervention: %r" % (verdict,))


def test_the_smuggled_write_lands_and_still_reports_a_decision(tmp_path):
    """Direct Python can perform the write; admission must refuse those bytes."""
    store, base = _bound_store(tmp_path)
    source = channel._revision_source(_SMUGGLED)
    view = _writable_view()

    verdict = channel.admit_revision_under_freeze(
        store, source, _views(store, base))
    action = _run_revision(source, view)

    assert view["grant"] == {"queries": 999999, "steps": 999999}, (
        "the frozen field was not overwritten, so this case proves"
        " nothing: %r" % (view,))
    assert action["action"]["inputs"]["frontier_action"]["inputs"] == {"x": 3}
    assert verdict.get("informs_decision") is not True
    assert verdict["eligibility"] != channel.ELIGIBLE


def test_the_runtime_comparison_cannot_see_a_childs_write(tmp_path):
    """RF-01, the second layer. `admit_revision_under_freeze` compares
    `frozen_state` either side of admission and raises
    `FrozenFieldViolation`. The revision runs out of process, so nothing
    it does to the view can move the store it compares.

    If this ever fires for a real revision, the freeze is two layers deep
    rather than one, and the report's limit paragraph becomes true.
    """
    store, base = _bound_store(tmp_path)
    source = channel._revision_source(_SMUGGLED)
    before = channel.frozen_state(store)

    channel.admit_revision_under_freeze(store, source, _views(store, base))

    assert channel.frozen_state(store) == before
    assert store._doc["grant"] == {"queries": 16, "steps": 12}, (
        "the store moved, so this case no longer demonstrates that the"
        " comparison is blind")


# --- RF-02: arrow 3 has a durable row but no causal join ------------------

def test_the_policy_state_effect_id_now_names_a_settled_operation(tmp_path):
    """RF-02, repaired by lane X4b. The effect id is an operation identity.

    This test was written as the reviewer's record of RF-02 and asserted that
    `effect_id` was the synthesized constant `ad01-<cid>-b<seq>-effect`,
    matching no `operations` row, with no `operation_id` on any observation.
    All of that was true and has been repaired, so the record now asserts the
    repair. It is inverted rather than deleted, because a deleted record would
    leave the finding looking unrepaired.

    The substantive claim is proven against a real database in
    `tests/test_inv_x4b_effect_identity.py`, which drives three boundaries and
    queries `operations`. What is asserted here is the shape that made the
    defect possible and the shape that closes it, so that a later change which
    reopened the gap would break a test that does not need a database.
    """
    from experiments.ad01 import trajectory

    import inspect
    source = inspect.getsource(trajectory._effect_operation_id)
    assert "operations" in source, (
        "the derivation no longer asks the operations table; the identity is"
        " being minted rather than derived")
    # What the derivation returns when it cannot reach a database is the whole
    # contract of the repair: an identity it cannot verify is not an identity.
    # No dsn is passed, so the read cannot succeed and the answer must be the
    # refusal rather than a name. A helper returning a constant would answer
    # with a string here, which is exactly the RF-02 defect.
    assert trajectory._effect_operation_id(
        None, "ad01-w0-I-901", {"operation_id": "some-operation"}) == "", (
        "the derivation produced an identity with no database to verify it"
        " against")

    import glob
    import re
    schema = ""
    for path in sorted(glob.glob(str(ROOT / "migrations" / "*.sql"))):
        schema += Path(path).read_text(encoding="utf-8") + "\n"
    columns = {}
    for table in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", schema,
                            re.S):
        columns[table[0]] = table[1]

    assert "effect_id" in columns["s09_policy_state"], (
        "the column moved; this finding is about where it points")

    # `operations.id` is a TEXT primary key, so the effect identity joins the
    # operation table directly rather than through a mapping table.
    assert "id TEXT PRIMARY KEY" in columns["operations"], (
        "operations.id changed shape; re-derive this finding")

    # The observation carries the operation identity inside `content`, which is
    # JSONB with no closed schema. It is still not a column, and it is still
    # not required to be one: the repair binds the arrow by value.
    observations = columns["attempt_observations"]
    assert "operation_id" not in observations, (
        "attempt_observations gained an operation_id column; the repair binds"
        " the arrow through content, and a column would be a second identity"
        " to keep in step: %r" % (observations,))
    assert "content JSONB" in observations, (
        "attempt_observations.content changed shape; the effect identity is"
        " carried inside it")


# --- RF-03: amend_protocol reads and writes across connections ------------

def test_amendment_passes_the_observed_lineage_to_atomic_freeze(monkeypatch):
    """The real race is qualified by test_inv_x5_amend_race on PostgreSQL."""
    from settlement import trials
    from settlement.common import Command, CommandResult, ResultCode

    calls = []
    monkeypatch.setattr(trials, "_observed_successors", lambda dsn, parent: {"child-0"})

    def freeze(dsn, cmd, **kwargs):
        calls.append(kwargs)
        return CommandResult(request_id=cmd.request_id, code=ResultCode.APPLIED)

    monkeypatch.setattr(trials, "freeze_protocol", freeze)
    cmd = Command(request_id="amend-control", payload={})
    result = trials.amend_protocol("unused", cmd, protocol_id="child-1",
                                   supersedes="parent", candidate_version="cand-1")
    assert result.code is ResultCode.APPLIED
    assert calls == [{"protocol_id": "child-1", "supersedes": "parent",
                      "_amend": {"candidate_version": "cand-1"},
                      "_observed": {"child-0"}, "_frozen": True}]

    monkeypatch.setattr(trials, "freeze_protocol", lambda *args, **kwargs:
                        CommandResult(request_id=cmd.request_id, code=ResultCode.STALE_REVISION,
                                      detail="concurrent amend"))
    with pytest.raises(trials.StaleRevision, match="concurrent amend"):
        trials.amend_protocol("unused", cmd, protocol_id="child-1", supersedes="parent")
