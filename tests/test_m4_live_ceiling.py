"""The output study authorized zero constructions, so it can never acquire.

`run_output_live` binds `{"model_calls": ..., "construction_calls": 0}`. The
ceiling was unenforced when that was written, so nothing noticed. It is
enforced now, and the first construction is refused with
`ceiling construction_calls=0 reached at 0`, which is correct: a study that
authorizes no constructions cannot make one.

That is not a rounding error in a fixture. It is why the M4 baseline could
never be built: the live path refuses before inference, every dispatch ends
unavailable, and a bundle with no dispatches has no receipts to join. The
live path and the M4 verifier were never able to see each other.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def test_the_output_study_authorizes_at_least_one_construction():
    """Otherwise the live path can never produce an acquired artifact."""
    import scripts.invl02_live as driver

    ceilings = driver._output_study_ceilings(
        {"limits": {"max_dispatches": 8}})

    assert ceilings["construction_calls"] >= 1, (
        "a study that authorizes no constructions cannot acquire anything, and"
        " the ceiling is enforced now")
    assert ceilings["model_calls"] >= 1


def test_the_ceilings_come_from_the_freeze_not_a_literal():
    import scripts.invl02_live as driver

    one = driver._output_study_ceilings({"limits": {"max_dispatches": 3}})
    two = driver._output_study_ceilings({"limits": {"max_dispatches": 7}})

    assert one["model_calls"] == 3
    assert two["model_calls"] == 7
