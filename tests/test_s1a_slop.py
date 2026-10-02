"""Slop pass 1 guard: removed dead code stays removed, owners still import."""

from __future__ import annotations


def test_dead_helpers_stay_removed():
    from experiments.ad01 import learner, rotation, run_c3_qualification
    assert not hasattr(learner, "_used_learner_seqs")
    assert not hasattr(rotation, "full_rotation")
    assert not hasattr(run_c3_qualification, "_proposal")


def test_live_helpers_still_importable():
    from experiments.ad01 import learner, rotation, run_c3_qualification
    assert callable(learner.model_propose)
    assert callable(learner.propose_from_model)
    assert callable(rotation.r_schedule)
    assert callable(run_c3_qualification.run_trajectories)
    assert len(rotation.r_schedule(0)) == 6
