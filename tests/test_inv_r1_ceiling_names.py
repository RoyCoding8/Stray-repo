"""A study's cap sheet must be authorizable as written.

`inv01_study` writes its ceilings as `max_model_calls`,
`max_construction_calls`, `max_boundaries`, `max_witness_queries` and
`max_execution_units`, and `check_caps_against_runner` pins every value. The
store's validator knew only `model_calls` and `execution_units`, so
authorization refused the whole sheet and `inv01_study` could never start
even with a valid grant: four tests failed with
`study refused: unsupported study ceiling max_model_calls`.

Two separate things were wrong. The `max_` prefix is the study's own
spelling of a counter the store names without it, so a ceiling the store
counts was unreachable under the name the study used. And `boundaries` and
`witness_queries` are enforced by the trajectory runner, not the broker, so
they have no operation row to count and no counter to bind to.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from settlement import store


def test_a_prefixed_counter_names_the_same_counter():
    assert store._ceiling_counter("max_model_calls") == "model_calls"
    assert store._ceiling_counter("max_construction_calls") == (
        "construction_calls")
    assert store._ceiling_counter("max_execution_units") == "execution_units"
    assert store._ceiling_counter("model_calls") == "model_calls"


def test_a_ceiling_the_sheet_declares_is_accepted():
    """`max_boundaries` has no counter and is still a real ceiling.

    A boundary is a trajectory-level decision and an oracle query is a child
    call, so neither is a durable operation row. The sheet declares them and
    the runner enforces them, so refusing the declaration at authorization
    would make the sheet unusable rather than safer.
    """
    for name in ("max_boundaries", "max_witness_queries", "boundaries",
                 "witness_queries"):
        assert store.is_ceiling_name(name), name


def test_an_invented_ceiling_is_still_refused():
    for name in ("max_vibes", "vibes", "", "max_"):
        assert not store.is_ceiling_name(name), name


def test_the_frozen_sheet_is_authorizable_as_written():
    """The sheet itself, not a rewritten copy of it."""
    from scripts import inv01_study

    effective = inv01_study._v1_effective_config(
        "live", "m", "low", 600)
    sheet = inv01_study._v1_sheet(effective)
    checked = inv01_study.check_caps_against_runner(sheet)
    assert checked["problems"] == []

    study = sheet["study"]
    for key, value in study.items():
        if key.startswith("max_"):
            assert store.is_ceiling_name(key), key
            assert value >= 0
