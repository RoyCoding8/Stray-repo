"""Three properties of the r4 panel that a run cannot show after the fact.

A run that got any of them wrong has already spent its dispatches, and two
of the three fail silently: a use phase that never ran contributes no record
rather than a fallback, and a gate that pairs on an intersection reports
whatever intersection it happened to reach.

**The panel is paired by construction.** `control_distinct` refuses when the
symmetric difference of the two arms' task ids is non-empty. r3's control ran
eighteen tasks and its acquired arms one each, so `unpaired_tasks` was 16
and `distinct` could not have been True however the two arms behaved. The
gate's own refusal named the mechanism, but the run's design was the cause.

**The authority covers every child.** One campaign and one use phase per
acquisition, plus the control, is thirteen subdivisions. `_v1_study_units`
multiplies the sheet's allowance by `n + _v1_use_arms() - 1`, so the count
it is handed has to be the count this run creates.

**The dispatch ceiling is the retry arithmetic.** `LiveGuard.automatic_retries`
defaults to 3 and the read timeout is 240s, so one task can burn four times
that. This pins retries at zero.

Nothing here dispatches. Every test calls the functions the driver calls.

Run: PYTHONPATH=. .venv/bin/pytest tests/test_ad01_r4_compare.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def test_both_arms_run_the_same_tasks_so_the_gate_can_pair():
    """The control's task set is the acquisition panel, not the study's.

    `control_arm.control_tasks(world)` returns six tasks per world, and the
    gate counts a task the other arm never ran as unpaired, which refuses
    the whole verdict. The acquired arms hold one member each and can only
    answer the task they were acquired for, so the panel is what both arms
    can run and the control is held to it.
    """
    from experiments.ad01 import control_arm
    from scripts import ad01_r4_compare as driver
    from scripts import inv01_study as study

    panel = set(driver.ACQUISITION_TASKS)
    assert len(panel) == len(driver.ACQUISITION_TASKS), "the panel repeats"
    for world in (0, 1, 2):
        mine = {task_id for task_id in panel
                if driver._world_of(task_id) == world}
        assert mine, "world %d has no panel task" % world
        assert mine <= set(control_arm.control_tasks(world)), world
        assert mine <= set(study._use_tasks(world)), world


def test_the_authority_covers_every_child_the_run_creates():
    """One campaign and one use phase per acquisition, plus the control.

    Under-counting is not a small shortfall: the last subdivisions arrive to
    a free balance of zero and `subdivide_allocation` refuses them with
    `parent ... has 0 free`, and a use phase that never ran contributes no
    record rather than a fallback the gate could read.
    """
    from scripts import ad01_r4_compare as driver
    from scripts import inv01_study as study

    acquisitions = len(driver.ACQUISITION_TASKS)
    children = driver._arms_run()

    assert children == acquisitions * 2 + 1
    assert driver.study_units() == study._v1_study_units(children)
    assert children > acquisitions + 1, (
        "this is the count the first run used, which is short by the use"
        " phases")


def test_retries_are_zero_and_the_ceiling_is_the_task_count():
    """One task, one send, and the repair slot is the second send.

    `MAX_RETRIES` is 3, so a task that times out burns four times the read
    timeout: 960s on this route, and r3 lost an arm to a fourth of that.
    The ceiling is twice the task count because a repair is a second send on
    the same slot, not a retry inside one.
    """
    from experiments.ad01 import live_construct
    from scripts import ad01_r4_compare as driver

    source = Path(driver.__file__).read_text(encoding="utf-8")
    assert "automatic_retries=0" in source, (
        "the guard is left at MAX_RETRIES, so one timed-out task can spend"
        " four times the read timeout")
    assert live_construct.MAX_RETRIES == 3
    assert driver.DISPATCH_CEILING == 2 * len(driver.ACQUISITION_TASKS)


def test_the_ceilings_admit_every_execution_and_one_campaign_of_headroom():
    """The store's own exposure arithmetic, with margin.

    `_sandbox_exposure` is `timeout_ms // 1000 + STOP_SETTLE_S + 1` and
    `DEFAULT_TIMEOUT_MS` is 30000, so one sandbox exec is 30 + 80 + 1 = 111
    units -- which is where the study's own per-task figure of 111 comes
    from. This run draws one validation exec per acquisition and one use exec
    per task, and the margin is one acquisition campaign. Two runs lost their
    last world at an exactly-sized ceiling, and the phase that loses is the
    one the loop reaches last.
    """
    from experiments.ad01 import method_exec
    from settlement import broker, exec_profile
    from scripts import ad01_r4_compare as driver

    per_exec = (method_exec.DEFAULT_TIMEOUT_MS // 1000
                + exec_profile.STOP_SETTLE_S + 1)
    assert broker._sandbox_exposure(
        {"timeout_ms": method_exec.DEFAULT_TIMEOUT_MS}, 0) == (
            per_exec, "hard-ceiling")
    assert per_exec == 111

    derivation = driver.ceiling_derivation()
    assert derivation["per_sandbox_exec_units"] == per_exec
    acquired = len(driver.ACQUISITION_TASKS)
    phases = (derivation["validation_execs"] + derivation["use_execs"]
              + derivation["margin_execs"])
    assert derivation["validation_execs"] == acquired
    assert derivation["use_execs"] == 2 * acquired
    assert driver.ceilings()["max_execution_units"] == phases * per_exec
    assert derivation["margin_execs"] > 0, (
        "a ceiling sized at exactly the sum is a race for the last unit")


def test_the_ceiling_names_are_ones_the_authority_accepts():
    """`authorize_study` refuses a name it does not recognise.

    The derivation is written beside the ceilings rather than inside them
    for this reason, and a driver that folded it back in would refuse the
    study at its first operation.
    """
    from settlement import store
    from scripts import ad01_r4_compare as driver

    for name in driver.ceilings():
        assert store.is_ceiling_name(name), name
    for name in driver.ceiling_derivation():
        assert not store.is_ceiling_name(name) or name in {
            "construction_call_ceiling"}, (
            "%s is in the derivation and would be read as a binding ceiling"
            % name)
