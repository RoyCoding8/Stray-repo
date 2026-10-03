"""The crossing driver must read the record the world actually runs.

`twodomain._swe_episode` used to rebuild its own task from
`(split, seed)` through a second derivation while `swe_world.run_episode`
selected the instance through `swe_tasks.instances_for_seed`. The two agreed
only for the seeds the driver happened to use, and the driver kept the
public test list of one task while running another.

The module's own docstring promised the opposite: "Derived rather than
authored, so two readers cannot disagree about which instance an episode
ran." These tests are the check that promise was never backed by, and are
now the check that it holds for every seed rather than the three the
crossing used.

No model call, no network, no dispatch, no database.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_swe_tasks as swe_tasks
from experiments.ad01 import twodomain


def _crossing_seeds() -> list[tuple[str, int]]:
    return list(twodomain.SWE_CROSSING_EPISODES)


def test_the_driver_runs_the_task_it_reports():
    """One derivation, asserted through the episode the driver actually runs.

    Comparing `instances_for_seed` with itself proves nothing, because both
    readers can call it. The check has to go through `_swe_episode`, which
    is where the second derivation used to live, and read the task_id the
    episode reports against the one `run_episode` ran.
    """
    for split, seed in _crossing_seeds():
        episode = twodomain._swe_episode(split, seed, [])
        world = swe_tasks.instances_for_seed(split, seed)
        assert episode["task_id"] == world["task_id"], (
            "the driver reported %s while the world ran %s"
            % (episode["task_id"], world["task_id"]))
        assert episode["template"] == world["template"]


def test_the_module_does_not_rebuild_the_instance_a_second_time():
    """The defect was a duplicate derivation, so its absence is the check.

    `_swe_record` indexed the split's template and mechanism lists itself.
    Nothing else in the repo may do that: the world selects the instance,
    and a caller that recomputes it can disagree with the world by
    construction, which is how the two crossing seeds disagreed.
    """
    assert not hasattr(twodomain, "_swe_record"), (
        "twodomain._swe_record re-derives an instance the world already "
        "selected; call swe_tasks.instances_for_seed instead")
    source = Path(twodomain.__file__).read_text()
    assert "swe_tasks.instance(" not in source, (
        "twodomain rebuilds a SWE instance instead of reading the one the "
        "world runs")


def test_the_seeds_the_crossing_uses_agree_on_the_template():
    """Two of the three crossing seeds disagreed before this repair.

    `dev/1` and `held_out/2` named `scan-depth` and `scan-net` to the
    driver while the world ran `count-lead-sum` and `count-tail-sum`, so
    the driver read one task's public tests while another ran. The census
    was not affected: `_actual_assessment_families` already read
    `instances_for_seed`, the derivation the world uses.
    """
    expected = {("dev", 0): "count-lead-sum",
                ("dev", 1): "count-lead-sum",
                ("held_out", 2): "count-tail-sum"}
    for split, seed in _crossing_seeds():
        world = swe_tasks.instances_for_seed(split, seed)
        assert world["template"] == expected[(split, seed)]


def test_the_driver_never_requests_a_test_the_world_does_not_publish():
    """The mismatch was harmless to the public test names only by luck.

    Both worlds happen to publish `case-01` and `case-02`, so the episode
    never asked for a test the world lacked. That coincidence is what kept
    this defect invisible; the test names the coincidence rather than
    trusting it.
    """
    for split, seed in _crossing_seeds():
        world = swe_tasks.instances_for_seed(split, seed)
        published = {case["name"] for case in world["public_tests"]}
        episode = twodomain._swe_episode(split, seed, [])
        assert episode["queried"], "the episode ran no test at all"
        for queried in episode["queried"]:
            assert queried in published, (
                "%s asked for %s, which %s does not publish"
                % (episode["task_id"], queried, world["task_id"]))