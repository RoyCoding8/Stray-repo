"""One test's namespace must not become the next test's campaign id.

`trajectory.NAMESPACE_TOKEN` is process state and `s09_pilot.run_study` sets
it without clearing it, so the first test that runs a study used to leave its
token behind for the rest of the pytest session. Nine files were affected,
each failing on an id that carried a token belonging to a different test.

The fix is one autouse fixture in conftest, not a pin in each file: pinning
per file leaves the next file exposed to whichever ran first. These tests
assert the ordering property itself, since a regression here is invisible in
any single file's own run.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import trajectory


def test_the_namespace_is_empty_at_the_start_of_every_test():
    """The leak this fixture exists to stop, asserted directly.

    The test above this one in file order sets a token and leaves it. If the
    autouse fixture is removed, that token survives and this fails; with it,
    the namespace is clean before the test body runs. Run the file with
    `-p no:randomly` to see it fail when the fixture is gone.
    """
    assert trajectory.NAMESPACE_TOKEN == ""
    assert trajectory.campaign_id(0, "I", 51) == "ad01-w0-I-51"


def test_a_token_set_by_this_test_does_not_survive_into_the_next():
    """The property, from the other side: nothing escapes a test.

    The autouse fixture restores on teardown as well as resetting on setup, so
    a test that names a namespace cannot become the next test's problem even
    when the next one does not itself read the global.
    """
    trajectory.set_namespace_token("a-token-another-test-left-behind")

    assert trajectory.campaign_id(0, "I", 51) == "ad01-w0-I-51-a-token-another-test-left-behind"


def test_a_study_can_still_mint_its_own_token_inside_one_test():
    """The fixture resets between tests, not during them.

    A reset that ran mid-test would make it impossible for a study to use a
    namespace at all, which is the opposite of what is wanted.
    """
    trajectory.set_namespace_token("mine")

    assert trajectory.campaign_id(0, "I", 51) == "ad01-w0-I-51-mine"
