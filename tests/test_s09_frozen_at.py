"""A freeze must name when it was taken, and that must not change what it is.

The namespace-age check in the preflight refuses a run whose receipts could
predate the freeze, and it could not do that at all: nothing in the bundle
recorded a moment, so every receipt looked contemporaneous. The moment now
exists. The obvious way to add it puts a wall clock inside the identity
digest, which would make an otherwise identical freeze hash differently on
every call. Both properties are pinned here.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts import s09_pilot as pilot
from scripts import s09_verify as verify


def test_the_freeze_names_a_moment():
    assert "frozen_at" in pilot.build_freeze()


def test_the_moment_is_timezone_aware_and_parseable():
    stamp = pilot.build_freeze()["frozen_at"]
    parsed = datetime.fromisoformat(stamp)
    assert parsed.tzinfo is not None, "an offset-free stamp is not comparable to a database timestamp"


def test_the_identity_digest_is_reproducible_for_an_otherwise_identical_freeze():
    assert (pilot.build_freeze()["freeze_digest"]
            == pilot.build_freeze()["freeze_digest"])


def test_the_moment_does_not_enter_the_identity_digest():
    first, second = pilot.build_freeze(), pilot.build_freeze()
    assert first["frozen_at"] != second["frozen_at"]
    assert first["freeze_digest"] == second["freeze_digest"]


def test_the_excluded_fields_are_exactly_the_wall_clock_ones():
    assert verify.NON_IDENTITY_FREEZE_FIELDS == ("freeze_digest", "frozen_at")


def test_changing_a_real_field_still_changes_the_digest():
    """Excluding a timestamp must not weaken the digest into a constant."""
    first = pilot.build_freeze()
    second = pilot.build_freeze()
    second["order"] = list(reversed(second["order"]))
    assert first["freeze_digest"] != verify.freeze_digest(second)
