"""Lane F: the property the two pilot worlds do not have.

Both worlds generate their hidden target from a pure function of
`(split, seed)`, both stamp the seed into `task_id`, and both hand
`task_id` to the policy in the public view. The target is therefore a
deterministic function of what the policy is allowed to see, and a policy
can call the public generator and score full marks without spending a
single query.

That is a defect, not a subtlety. It invalidates every acquisition claim
a study draws from these two worlds, because acquisition means the
observations changed the behaviour and here they need not change it at
all. The two tests below are red against the world as it stands and go
green when `task_id` stops naming a generator seed. They are left red on
purpose: closing the leak edits `second_active.make_task` and
`boolean_rule.make_task`, and those functions feed the frozen r4 panel,
every existing task id in the record store, and the secret-isolation
allowlist, none of which this lane owns.

What a fixing lane has to do, in one line: make the public `task_id` an
opaque handle that the generator cannot be re-derived from, and keep a
seed-to-task mapping on the host side for the grader. `TaskIdRetained`
below is the shape the panel carries, so the fix has somewhere to put
the seed once the view no longer exposes it.
"""


import pytest

from experiments.ad01 import boolean_active
from experiments.ad01 import boolean_rule
from experiments.ad01 import s09_instruments as instruments
from experiments.ad01 import second_active


ORDERING_TASK_IDS = tuple(second_active.make_task(split, seed)["task_id"]
                         for split in second_active.SPLITS
                         for seed in (0, 4, 11, 23))
BOOLEAN_TASK_IDS = tuple(boolean_rule.make_task(split, seed)["task_id"]
                         for split in boolean_rule.SPLITS
                         for seed in (0, 4, 11, 23))


def _recoverable(task_ids):
    """Task ids whose trailing field parses back to a generator seed."""
    recovered = []
    for task_id in task_ids:
        try:
            recovered.append(instruments.seed_from_view(
                {"task_id": task_id, "split": "dev"}))
        except instruments.PanelRefused:
            continue
    return recovered


def test_no_ordering_task_id_names_a_generator_seed():
    assert _recoverable(ORDERING_TASK_IDS) == []
    assert len(ORDERING_TASK_IDS) == 12


def test_no_boolean_task_id_names_a_generator_seed():
    assert _recoverable(BOOLEAN_TASK_IDS) == []
    assert len(BOOLEAN_TASK_IDS) == 12


def test_no_ordering_policy_can_identify_the_target_before_its_first_query():
    """The first view is the whole opportunity. If the target is already
    determined there, every later query is decoration."""
    seen = []

    def spy(state):
        seen.append(state)
        with pytest.raises(instruments.PanelRefused):
            seed = instruments.seed_from_view(state)
            instruments.view_leaks_target(
                instruments.ORDERING, state,
                second_active.make_task(state["split"], seed))
        return {"kind": "stop", "target": "schedule.task", "inputs": {},
                "evidence_refs": [], "requested_resources": {}}

    second_active.run_episode(spy, split="audit", seed=23)

    assert len(seen) == 1


def test_no_boolean_policy_can_identify_the_target_before_its_first_query():
    seen = []

    def spy(state):
        seen.append(state)
        with pytest.raises(instruments.PanelRefused):
            seed = instruments.seed_from_view(state)
            instruments.view_leaks_target(
                instruments.BOOLEAN, state,
                boolean_rule.make_task(state["split"], seed))
        return {"kind": "stop", "target": "boolean.task", "inputs": {},
                "evidence_refs": [], "requested_resources": {}}

    boolean_active.run_episode(spy, split="audit", seed=23)

    assert len(seen) == 1


def test_the_panel_carries_the_seed_the_view_would_stop_carrying():
    """The host still has to reach the target to grade it, so the panel
    holds the seed even after the view stops exposing it. This is what
    makes the fix above possible without making the world ungradable."""
    panel = instruments.build_panel(instruments.ORDERING, dev=4, held=8)
    seen = []

    def spy(state):
        seen.append(state)
        return {"kind": "stop", "target": "schedule.task", "inputs": {},
                "evidence_refs": [], "requested_resources": {}}

    for cell in panel.by_split("dev"):
        second_active.run_episode(spy, split=cell.split, seed=cell.seed)

    assert [cell.seed for cell in panel.by_split("dev")] == [0, 1, 2, 3]
    assert len(seen) == 4
    for cell in panel.by_split("dev"):
        assert second_active.make_task(cell.split, cell.seed)["order"]
