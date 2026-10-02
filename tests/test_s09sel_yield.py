"""Lane K: the four yield measures, computed from evidence and frozen.

Every measure is derived from a recorded episode, checker verdict or
ledger row, never from the policy's belief about what it achieved. The
measure set is content-addressed before any run, so redefining a measure
after outcomes are visible yields a different digest and the run is
unevaluable against the old one.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from experiments.ad01 import agenda_policy, selection


WORLD = 0


def _run(authorized=40):
    return selection.run_investigations(
        selection.portfolio_for_world(WORLD),
        agenda_policy.agenda_policy(),
        selection.Allocation(authorized=authorized), world=WORLD)


def test_measure_set_is_content_addressed():
    digest = selection.yield_measure_digest()
    assert len(digest) == 64
    assert digest == selection.yield_measure_digest(), "digest is not stable"
    assert digest == selection.FROZEN_MEASURE_DIGEST, (
        "the live digest no longer matches the frozen literal, so the "
        "measures were redefined")

    raw = json.dumps(selection.YIELD_MEASURES, sort_keys=True,
                     separators=(",", ":")).encode()
    assert digest == hashlib.sha256(raw).hexdigest(), (
        "the digest does not cover the measure definitions, so a redefined "
        "measure would keep the old digest")


def test_frozen_digest_refuses_a_relabelled_measure():
    good = selection.yield_measure_digest()
    assert selection.assert_measure_freeze(good) == good

    with pytest.raises(selection.MeasureDrift):
        selection.assert_measure_freeze("0" * 64)


def test_redefining_a_measure_changes_the_digest(monkeypatch):
    before = selection.yield_measure_digest()
    monkeypatch.setitem(selection.YIELD_MEASURES, "held_out_reduction",
                        "whatever the run felt like")
    assert selection.yield_measure_digest() != before
    with pytest.raises(selection.MeasureDrift):
        selection.assert_measure_freeze(before)


def test_retained_behaviors_come_from_retained_episodes():
    run = _run()
    retained = [e for e in run.executions
                if e.episode["disposition"] == "retained"]

    assert run.yield_.retained_behaviors == len(retained)
    assert run.yield_.retained_behaviors > 0
    for execution in retained:
        executable = execution.episode["executable"]
        assert executable["capability_id"] == \
            execution.choice.candidate.capability_id
        assert executable["authored"] is True
        assert executable["scope"]["family"] == \
            execution.choice.candidate.family
        assert executable["params"]["max_queries"] == \
            execution.choice.candidate.max_queries
        assert executable["qualified_on"] == \
            execution.choice.candidate.target


def test_resources_used_equals_the_charged_total():
    run = _run()
    charged = sum(choice.charge for choice in run.choices)
    executed = sum(e.cost for e in run.executions)

    assert run.yield_.resources_used == charged == executed
    assert run.yield_.resources_used <= 40


def test_diagnoses_correct_is_scored_against_the_checker():
    run = _run()

    assert run.yield_.diagnoses_correct == sum(
        1 for e in run.executions if e.correct is True)
    scored = [e for e in run.executions if e.correct is not None]
    assert scored, "no diagnosis was scored, so the measure has no evidence"
    for execution in scored:
        assert execution.claim in ("chain-necessary", "chain-filler",
                                   "seed", "novel", "tie")
        assert isinstance(execution.correct, bool)
        assert execution.observed, "a scored claim has no diagnostic record"


def test_a_chain_claim_is_confirmed_only_by_a_retained_episode():
    """`chain-necessary` predicts a retained episode; nothing else will do.

    Asserted as a fact about the run rather than by re-deriving the
    predicate, so a wrong mapping in the driver shows up here instead of
    being copied faithfully into the test.
    """
    run = _run()
    chain = [e for e in run.executions if e.claim == "chain-necessary"]
    assert chain, "no software diagnosis was made, so nothing to score"

    confirmed = [e for e in chain if e.episode.get("disposition")
                 == "retained"]
    contradicted = [e for e in chain if e.episode.get("disposition")
                    != "retained"]
    for execution in confirmed:
        assert execution.correct is True
    for execution in contradicted:
        assert execution.correct is False, (
            "a chain-necessary claim was contradicted by a %s episode and "
            "still scored as confirmed" % execution.episode.get("disposition"))
    assert contradicted, (
        "no chain diagnosis was contradicted, so the measure is scoring "
        "nothing observable on this substrate")


def test_the_diagnostic_runs_once_per_charged_candidate():
    """The charge says one diagnostic, so only one may execute.

    Reading the claim out of the operation that produced it is what keeps
    these two numbers equal; a driver that diagnosed separately would
    charge for one operation and run two.
    """
    run = _run()
    charged = [c for c in run.choices]
    observed = [e for e in run.executions if e.observation is not None]

    assert len(charged) == len(run.executions)
    assert len(observed) == len(run.executions), (
        "%d of %d executions carry a diagnostic observation"
        % (len(observed), len(run.executions)))
    for execution in run.executions:
        assert execution.observation["observation_id"].startswith("obs-")
        assert execution.episode["diagnostic_observation"] == \
            execution.observation["observation_id"]


def test_held_out_reduction_is_the_mean_of_the_ledger():
    """The measure is a rate over every ledger row, not a raw sum.

    Each retained behavior is scored on the same three transfer tasks, so
    the mean is comparable across runs with different retention counts and
    stays inside [0, 1].
    """
    run = _run()
    assert run.held_out_ledger
    manual = sum((row["initial"] - row["final"]) / row["initial"]
                 for row in run.held_out_ledger) / len(run.held_out_ledger)

    assert abs(run.yield_.held_out_reduction - manual) < 1e-9
    assert 0.0 <= run.yield_.held_out_reduction <= 1.0


def test_every_retained_behavior_is_scored_on_the_whole_held_out_set():
    """Each retained behavior gets the same rows, or the mean is unfair.

    Two behaviors of different quality must not be averaged over unequal
    evidence, so the ledger carries one full pass per retained behavior
    per family.
    """
    run = _run()
    retained = [e for e in run.executions
                if e.episode["disposition"] == "retained"]
    assert retained, "nothing was retained, so the ledger cannot be scored"

    widths = {family: len(selection.transfer_targets(WORLD)[family])
              for family in selection.FAMILIES}
    expected = {}
    for execution in retained:
        family = execution.choice.candidate.family
        expected[family] = expected.get(family, 0) + widths[family]

    actual = {}
    for row in run.held_out_ledger:
        actual[row["family"]] = actual.get(row["family"], 0) + 1

    assert actual == expected, (
        "the ledger holds %r rows per family but %d retained behaviors over "
        "held-out sets of %r require %r"
        % (actual, len(retained), widths, expected))


def test_held_out_targets_were_never_developed_on():
    run = _run()
    developed = {c.candidate.target for c in run.choices}

    assert run.held_out_ledger
    for row in run.held_out_ledger:
        assert row["target"].startswith("ad01-w0-transfer-")
        assert row["target"] not in developed, (
            "%s was both developed on and scored held out" % row["target"])


def test_yield_rejects_an_unmeasured_value():
    with pytest.raises(ValueError):
        selection.Yield(retained_behaviors=1, held_out_reduction=None,
                        diagnoses_correct=0, resources_used=0)


def test_yield_rejects_a_negative_count():
    with pytest.raises(ValueError):
        selection.Yield(retained_behaviors=-1, held_out_reduction=0.5,
                        diagnoses_correct=0, resources_used=0)


def test_yield_rejects_an_out_of_range_rate():
    with pytest.raises(ValueError):
        selection.Yield(retained_behaviors=1, held_out_reduction=1.5,
                        diagnoses_correct=0, resources_used=0)


def test_the_whole_run_carries_its_frozen_digest():
    run = _run()
    assert run.measure_digest == selection.yield_measure_digest()
    assert run.measure_digest == selection.assert_measure_freeze(
        run.measure_digest)
    assert set(run.yield_.as_dict()) == set(selection.YIELD_MEASURES)
