"""The relevance contrast has never been scored, only built.

Expansion question 2 asks whether relevant experience beats a
size-matched irrelevant control. `learner.matched_experience_arms` builds
that pair and `equal_length_experience_pair` refuses an unequal one, but
nothing called the pair and then compared what came back. The suite only
ever exercised `acquisition_cost_arms`, which is the cost side.

These tests pin the parts that decide what the contrast can claim: the two
arms are the same length before anything is dispatched, a difference in
method is read as `differs` and a sameness as `tie`, an unparseable
acquisition is `none` and not credited with a method it did not choose, and
a failed arm is `unscored` rather than a zero.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import learner
from experiments.ad01 import s09_e2_relevance as e2


def _task(task_id="ad01-w1-target-gr-00", family="graph"):
    return {"task_id": task_id, "family": family, "seed": 3, "template": "graph"}


def test_the_pair_is_equal_length_before_anything_is_dispatched():
    """The whole point of the control: same context volume, different content.

    If the two arms are not the same length, a difference in what the model
    writes could be attributed to how much text it was shown rather than to
    whether the text was relevant. The constructor raises on an unequal
    pair, and this re-asserts it.
    """
    pair = e2.build_scored_contrast(
        _task(), ["ad01-w1-dev-gr-00", "ad01-w1-dev-gr-01"],
        ["ad01-w1-within-sw-00", "ad01-w1-within-sw-01",
         "ad01-w1-within-sw-02"], visible=[])

    assert pair["relevant_chars"] == pair["irrelevant_chars"]
    assert learner.equal_length_experience_pair(
        pair["relevant"], pair["irrelevant"])
    assert pair["condition"] == "relevant-versus-shuffled"
    assert pair["differs_in"] == "semantic-relevance-only"


def test_the_two_prompts_differ_only_in_the_experience_line():
    """A difference in output is attributable to the experience, not the contract.

    Both arms carry the same interface, budget and action vocabulary. The
    only thing that should move between the two rendered prompts is the
    trailing `Prior observations:` line.
    """
    pair = e2.build_scored_contrast(
        _task(), ["ad01-w1-dev-gr-00", "ad01-w1-dev-gr-01"],
        ["ad01-w1-within-sw-00", "ad01-w1-within-sw-01",
         "ad01-w1-within-sw-02"], visible=[])
    prompts = e2.render_prompts(pair)

    relevant_lines = prompts["relevant"].splitlines()
    irrelevant_lines = prompts["irrelevant"].splitlines()
    assert len(relevant_lines) == len(irrelevant_lines)
    differing = [(a, b) for a, b in zip(relevant_lines, irrelevant_lines)
                 if a != b]
    assert len(differing) == 1, differing
    assert differing[0][0].startswith("Prior observations:")


def _scored(relevant_source, irrelevant_source):
    return e2.score_from_proposals(
        {"source": relevant_source}, {"source": irrelevant_source},
        target_task_id="t", relevant_chars=10, irrelevant_chars=10)


def test_different_methods_score_as_differs_and_identical_ones_as_tie():
    differs = _scored('reduce_software(task, oracle, method="ddmin")',
                      'reduce_software(task, oracle, method="greedy")')
    tie = _scored('method="ddmin"', 'method="ddmin"')

    assert differs.outcome == "differs" and differs.differs
    assert differs.relevant.method == "ddmin"
    assert differs.irrelevant.method == "greedy"
    assert tie.outcome == "tie" and not tie.differs


def test_an_unparseable_acquisition_is_none_and_never_credited():
    """A model that named no method has not chosen one.

    Reading the answer out of a default is the failure this campaign
    already paid for once: `reduce_software` defaulted to `ddmin`, every
    acquisition matched the control, and the menu looked settled because
    the default was the answer. So an acquisition with no parseable
    `method=` reads as `none`.
    """
    unparsed = _scored("I will think about it and write something useful",
                       'reduce_software(task, oracle, method="ddmin")')

    assert unparsed.relevant.method == "none"
    assert unparsed.outcome == "differs", "none is not the same as ddmin"


def test_a_failed_arm_is_unscored_rather_than_a_zero():
    """A dispatch that raised did not produce a worse policy; it produced none.

    Scoring a failed arm as a method would let a transport error masquerade
    as a substantive result.
    """
    failed = e2.score_from_proposals(
        {"source": "x", "error": "LearnerRefused: no settled response"},
        {"source": 'method="ddmin"'}, target_task_id="t",
        relevant_chars=10, irrelevant_chars=10)

    assert failed.outcome == "unscored"
    assert not failed.differs
    assert "no settled response" in failed.relevant.error
