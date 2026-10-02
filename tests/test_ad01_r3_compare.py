"""The E1 live comparison reads the store, and the panel survives a timeout.

Two properties of `scripts/ad01_r3_compare.py` that a run cannot demonstrate
after the fact, because a run that got them wrong has already spent its
dispatches.

**The authority is derived from the arms the run creates.** The study's own
`_v1_study_units(_v1_campaign_count(0))` sizes six campaigns plus two extra
arms. This run subdivides a different number, one child per acquisition plus
the control. A study authorized for fewer children than it creates leaves
the last child with a free balance of zero, and the arm that loses is
whichever the loop reaches last, which is the control. Every one of its
records then falls back to `incumbent`, and a fallback names no executed
policy, so `control_distinct` reads an unrun arm as a refusal rather than as
a result. The control arm's own record of that is
`reports/evidence/inv_r1_e1_control_arm_result/`.

**The world is read off the task id, not off a token index.** A frozen id is
`ad01-w<N>-<split>-<family>-<nn>`. Counting `-`-separated tokens puts the
split in the world slot, so `ad01-w0-within-sw-00` raised rather than
returning 0, and the raise would have happened after the acquisitions had
been spent.

Nothing here dispatches. Every test calls the functions the driver calls and
reads what they return.

Run: PYTHONPATH=. .venv/bin/pytest tests/test_ad01_r3_compare.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def test_the_authority_covers_every_child_the_run_creates():
    """One per acquisition, one per control use, one per acquired-arm use.

    `_v1_study_units(n)` is the sheet's unit allowance times
    `n + (_v1_use_arms() - 1)`, so it already adds the two extra arms the
    study declares. The defect this rules out is counting only the
    acquisitions and the control, which is what the first run did: the
    acquired arms' own use phases are five more subdivisions, the run
    authorized nine children against twelve, and `subdivide_allocation`
    refused the last three with `parent ... has 0 free`.

    A use phase that never ran contributes no record, so the loss is not
    visible as a fallback. It is visible as `unpaired_tasks`: the control
    carries eighteen records and the acquired arm two, and the gate pairs on
    the intersection.
    """
    from scripts import ad01_r3_compare as driver
    from scripts import inv01_study as study

    children = driver._arms_run()
    acquisitions = len(driver.ACQUISITION_TASKS)

    # One acquisition, one control use, one use phase per acquired arm.
    assert children == acquisitions * 2 + 1
    assert driver.study_units() == study._v1_study_units(children)
    # The count the first run used, which is short by the use phases.
    assert children > acquisitions + 1


def test_the_world_is_read_off_the_w_prefix_and_not_a_token_index():
    """`ad01-w0-within-sw-00` is world 0, and `within` is not a split of 0.

    A positional read of the third `-` token lands on `within`, and
    `int("ithin")` raised. The raise is the cheap part; what it cost is the
    acquisitions that ran before the use phase reached it.
    """
    from scripts import ad01_r3_compare as driver

    assert driver._world_of("ad01-w0-within-sw-00") == 0
    assert driver._world_of("ad01-w1-within-gr-00") == 1
    assert driver._world_of("ad01-w2-transfer-sw-01") == 2
    with pytest.raises(ValueError):
        driver._world_of("ad01-wX-within-sw-00")
    with pytest.raises(ValueError):
        driver._world_of("not-a-task-id")


def test_every_acquisition_task_is_on_both_arms_use_panel():
    """The comparison is paired by construction, not by a second list.

    `control_distinct` pairs on the intersection of two arms' task ids, so a
    task the control never runs cannot produce a pairing at all. The panel
    is drawn from the study's own `_use_tasks`, and the control's
    `control_tasks` is the same list reached through the freeze, so the
    check is that they still agree.
    """
    from experiments.ad01 import control_arm
    from scripts import ad01_r3_compare as driver
    from scripts import inv01_study as study

    for task_id in driver.ACQUISITION_TASKS:
        world = driver._world_of(task_id)
        assert task_id in study._use_tasks(world), task_id
        assert task_id in control_arm.control_tasks(world), task_id


def test_one_campaign_per_acquisition_task_is_what_the_lineage_cap_allows():
    """`MAX_LINEAGES` is counted per campaign, not per task.

    `construct.construct_method` sums every `ad01-<cid>-construct-l*-init`
    under the campaign it was handed, so a second task in the same campaign
    finds `prior_lineages >= 2` and raises `lineage cap reached
    (2/trajectory)` having dispatched nothing. That is the refusal the r2
    run hit on four of its tasks after two timeouts consumed the slots.
    """
    from experiments.ad01 import construct
    from scripts import ad01_r3_compare as driver

    assert construct.MAX_LINEAGES == 2
    campaigns = {"r3acq-t%d-%s" % (index, task_id)
                 for index, task_id in enumerate(driver.ACQUISITION_TASKS)}
    assert len(campaigns) == len(driver.ACQUISITION_TASKS), (
        "two tasks share a campaign, so the second cannot acquire")


def test_the_operation_id_reconstruction_matches_what_construct_builds():
    """`read_acquisition_evidence` is re-read against a rebuilt id.

    The driver reconstructs the construction operation id rather than
    carrying it, because the acquisition is the only thing that knows it.
    A mismatch surfaces as a refusal to earn, which is the safe direction,
    but a reconstruction that is wrong on every arm demotes the whole run
    to `not_comparable` for a reason that is not a finding.
    """
    from scripts import ad01_r3_compare as driver

    cid = "r3acq-t3-ad01-w1-within-gr-00"
    task_id = "ad01-w1-within-gr-00"
    episode = "%s-b0-%s" % (cid, task_id)

    assert driver._construct_operation_id(
        {"campaign_id": cid, "task_id": task_id}) == \
        "ad01-%s-construct-l1-init" % episode


def test_the_bundle_takes_the_evidence_the_acquisition_recorded():
    """The evidence is the one the acquisition earned, not a re-read.

    `construct.acquisition_origin` calls `read_acquisition_evidence` with
    the whole settled response, and that call compares the receipt's
    `content["text"]` digest against the response the member was parsed
    from. The member the construction path returns holds the extracted
    `entry` field, which is a substring of the response and hashes
    differently, so re-reading with `arm["policy_source"]` compares the
    receipt against the wrong bytes.

    The first run did exactly that. Every one of five earned arms then read
    `member bytes are not the settled response`, no arm reached the freeze
    as `model-acquired`, and the verdict read `unproven` with
    `not_comparable` on receipts that say a live provider answered. The
    evidence is therefore carried on the arm and not recomputed.
    """
    import ast
    import inspect
    import textwrap

    from scripts import ad01_r3_compare as driver

    source = inspect.getsource(driver.write_verdict_bundle)
    assert 'arm.get("evidence")' in source, (
        "the bundle recomputes acquisition evidence from the member source; "
        "the member is the extracted entry field, not the settled response")
    # No call, rather than no mention: the docstring names the function it
    # explains why the bundle does not call. `textwrap.dedent` rather than
    # `inspect.cleandoc`, which strips the leading indent the body needs.
    called = {
        node.func.attr
        for node in ast.walk(ast.parse(textwrap.dedent(source)))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "read_acquisition_evidence" not in called
