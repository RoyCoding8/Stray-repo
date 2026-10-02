"""The STEP vocabulary and the shared contract must name the same actions.

Six kinds on each side, and until the two are translated a STEP policy is
refused by the contract and a contract policy is refused by the STEP ABI.
These tests hold the translation: every kind in both directions, checked
against the real parsers, and the refusals that keep a gap from passing
as agreement.
"""

from __future__ import annotations

import pytest

from experiments.ad01 import policy_action as contract
from experiments.ad01 import policy_step as step


def _step_action(kind: str, target: str = "task-1", **overrides) -> dict:
    action = {"kind": kind, "target": target,
              "inputs": {"note": "n"},
              "evidence_refs": ["obs-1"],
              "requested_resources": {"steps": 1}}
    action.update(overrides)
    return action


# The kind each STEP action is expected to become, written out rather than
# read back from the table under test.
TRANSLATED = [
    ("diagnose", "probe"),
    ("construct_method", "construct"),
    ("use_method", "use"),
    ("request_model", "observe"),
    ("propose_revision", "check"),
    ("stop", "stop"),
]


def test_the_table_covers_every_kind_of_both_vocabularies_in_both_directions():
    coverage = step.vocabulary_coverage()

    assert coverage["step_unmapped"] == []
    assert coverage["contract_unmapped"] == []
    assert coverage["step_kinds"] == sorted(step.ACTION_KINDS)
    assert coverage["contract_kinds"] == sorted(contract.ACTION_KINDS)


def test_the_contract_still_names_exactly_six_kinds():
    """The point of the table is that the contract needed no widening."""
    assert contract.ACTION_KINDS == (
        "probe", "observe", "construct", "use", "check", "stop")
    assert len(step.STEP_KIND_TO_CONTRACT) == 6


@pytest.mark.parametrize("step_kind, contract_kind", TRANSLATED)
def test_each_step_action_becomes_the_expected_contract_action(
        step_kind, contract_kind):
    translated = step.as_contract_action(_step_action(step_kind))

    assert translated == {
        "kind": contract_kind, "target": "task-1",
        "inputs": {"note": "n"}, "evidence_refs": ["obs-1"],
        "requested_resources": {"steps": 1}}


@pytest.mark.parametrize("step_kind, contract_kind", TRANSLATED)
def test_the_contract_parser_accepts_every_translated_action(
        step_kind, contract_kind):
    """Running the real parser, not asserting the fields by hand."""
    parsed = contract.parse_action(step.as_contract_action(
        _step_action(step_kind)))

    assert parsed.kind == contract_kind
    assert parsed.target == "task-1"
    assert parsed.inputs == {"note": "n"}
    assert parsed.evidence_refs == ("obs-1",)
    assert parsed.requested_resources == {"steps": 1}


@pytest.mark.parametrize("step_kind, contract_kind", TRANSLATED)
def test_each_contract_action_becomes_the_expected_step_action(
        step_kind, contract_kind):
    shared = {"kind": contract_kind, "target": "task-1",
              "inputs": {"note": "n"}, "evidence_refs": ["obs-1"],
              "requested_resources": {"steps": 1}}

    assert step.as_step_action(shared) == _step_action(step_kind)


@pytest.mark.parametrize("step_kind, contract_kind", TRANSLATED)
def test_the_step_abi_accepts_every_reverse_translated_action(
        step_kind, contract_kind):
    shared = {"kind": contract_kind, "target": "task-1"}

    accepted = step.validate_action(step.as_step_action(shared))

    assert accepted["kind"] == step_kind


@pytest.mark.parametrize("step_kind, contract_kind", TRANSLATED)
def test_both_directions_round_trip(step_kind, contract_kind):
    """Payload survives the round trip; the kind survives by bijection."""
    original = _step_action(step_kind)
    through_contract = step.as_contract_action(original)

    assert step.as_step_action(through_contract) == original
    assert contract.parse_action(through_contract).kind == contract_kind


def test_the_translation_is_a_bijection_not_a_partial_map():
    """A shared `probe` does have a STEP equivalent: `diagnose`.

    The brief expected this direction to be one-way. It is not, and the
    reason is that the table is total in both directions over two
    six-kind vocabularies, so a bijection is the only shape available.
    What is genuinely one-way is the payload: a shared `probe` carries
    its acceptance criterion in `inputs`, which no STEP kind promises.
    """
    assert step.CONTRACT_KIND_TO_STEP == dict(
        (contract_kind, step_kind)
        for step_kind, contract_kind in TRANSLATED)
    assert set(step.CONTRACT_KIND_TO_STEP.values()) == set(step.ACTION_KINDS)
    assert step.CONTRACT_KIND_TO_STEP[contract.PROBE] == "diagnose"


def test_translation_does_not_leak_the_source_vocabulary_name():
    """`request_model` and `propose_revision` name an instrument and a
    governance event, neither of which survives into the contract."""
    translated = step.as_contract_action(_step_action("request_model"))

    assert "request_model" not in translated.values()
    assert translated["kind"] == "observe"

    revision = step.as_contract_action(_step_action("propose_revision"))

    assert revision["kind"] == "check"


def test_an_extra_field_is_refused_rather_than_silently_dropped():
    """The STEP ABI admits extra fields the contract does not name.

    Dropping one here would let a policy smuggle state past the contract
    that no representation could see, and the action would still pass as
    translated. It refuses in the contract's exception instead.
    """
    with pytest.raises(contract.ActionRefused, match="unknown action fields"):
        step.as_contract_action(
            _step_action("diagnose", campaign_state={"seen": 2}))


def test_an_unknown_step_kind_is_a_typed_refusal_not_a_default():
    """Refused by the STEP ABI, before translation is reached at all.

    `teleport` is not in the STEP vocabulary, so this is the ABI's own
    pre-existing typed refusal. The test below covers the case that is
    genuinely the translator's: a kind the STEP vocabulary accepts but
    the table cannot place.
    """
    with pytest.raises(ValueError, match="unknown policy action kind"):
        step.as_contract_action(_step_action("teleport"))


def test_a_step_kind_with_no_shared_equivalent_is_an_explicit_refusal(
        monkeypatch):
    """The table is not silently bypassable when STEP grows a kind.

    `validate_action` consults the module tuple, so a newly added STEP
    kind is accepted by the ABI and then has nowhere to go. That must be
    an explicit refusal naming the gap, never a fallthrough default.
    """
    monkeypatch.setattr(step, "ACTION_KINDS", step.ACTION_KINDS + ("rewrite",))

    with pytest.raises(contract.ActionRefused, match="no shared-contract"):
        step.as_contract_action(_step_action("rewrite"))


def test_an_unknown_contract_kind_is_a_typed_refusal_not_a_default():
    with pytest.raises(contract.ActionRefused, match="unknown action kind"):
        step.as_step_action({"kind": "teleport", "target": "task-1"})


def test_a_contract_action_missing_a_required_field_still_refuses():
    with pytest.raises(contract.ActionRefused, match="non-empty string"):
        step.as_step_action({"kind": "check", "target": ""})


def test_a_step_action_that_never_reached_the_abi_is_refused_as_step_shaped():
    """Order matters: a missing field is a STEP ABI problem, and reporting
    it as a contract problem would point at the wrong module."""
    with pytest.raises(ValueError, match="policy action missing"):
        step.as_contract_action({"kind": "diagnose", "target": "task-1"})


def test_both_vocabularies_now_express_every_kind_the_other_names():
    """The recorded gap, closed. `test_policy_action_contract.py` asserts
    the opposite and is owned elsewhere; this states the fact the way a
    reader of this table needs it."""
    shared = set(contract.ACTION_KINDS)
    reachable_from_step = set(step.STEP_KIND_TO_CONTRACT.values())

    assert reachable_from_step == shared
    assert set(step.CONTRACT_KIND_TO_STEP) == shared
