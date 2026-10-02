"""The shared contract is not yet the shared vocabulary.

Five action vocabularies are in play. `policy_step` is translated onto the
contract, so a policy written to one is usable where the other is expected.
`frontier.OPERATE_KINDS` and `improve_channel.IMPROVE_KINDS` are not.

The census is the measurement. It exists because the two gaps run in
opposite directions, and only one of them is a mapping problem. Five kinds
appear in those vocabularies with no contract equivalent, including `wait`,
which appears in both and has nothing to map onto. Meanwhile three contract
kinds name nothing outside the contract itself.

Closing this properly is a design decision, not a refactor: either the
contract grows, or those five kinds are re-expressed. Both change the public
interface three representations depend on, so this pins the measurement and
leaves the decision open rather than making it silently.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_vocabulary_census as census


def test_the_contract_is_exactly_six_kinds():
    coverage = census.coverage()

    assert coverage["contract_is_six"] is True
    assert census.CONTRACT == frozenset(
        {"probe", "observe", "construct", "use", "check", "stop"})


def test_policy_step_is_translated_onto_the_contract():
    """The translation is a bijection over the six, not a partial map."""
    from experiments.ad01 import policy_step

    mapping = census.coverage()["policy_step_translated"]

    assert set(mapping) == set(policy_step.ACTION_KINDS)
    assert sorted(mapping.values()) == sorted(census.CONTRACT)
    assert len(mapping) == 6


def test_wait_has_no_contract_equivalent_in_either_vocabulary():
    """The gap that is not a mapping problem, named explicitly."""
    coverage = census.coverage()

    assert "wait" in coverage["operate_unmapped"]
    assert "wait" in coverage["improve_unmapped"]
    assert "wait" in coverage["kinds_with_no_contract_equivalent"]


def test_three_contract_kinds_are_named_by_nothing_else():
    """The asymmetry: the contract has vocabulary the code never exercises.

    A kind nothing emits is a contract nobody is holding to, which is how a
    shared contract quietly stops being shared.
    """
    assert census.kinds_missing_from_every_vocabulary() == [
        "check", "observe", "use"]


def test_the_remaining_unmapped_kinds_are_the_measured_five():
    coverage = census.coverage()

    assert coverage["operate_unmapped"] == [
        "investigate", "reuse", "revise", "wait"]
    assert coverage["improve_unmapped"] == ["select", "wait"]
    assert sorted(set(coverage["kinds_with_no_contract_equivalent"])) == [
        "investigate", "reuse", "revise", "select", "wait"]


def test_census_reads_the_real_modules():
    vocabularies = census.vocabularies()

    assert len(vocabularies["policy_step"]) == 6
    assert "use_method" in vocabularies["policy_step"]
    assert "construct_method" not in vocabularies["contract"]
