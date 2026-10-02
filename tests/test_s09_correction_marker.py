"""A restored correction must be labelled as one in the prompt.

`ab2d28d` moved the prior failure from a trailing `PRIOR FAILURE (correct
it):` line into a `prior_failure` key inside the decision packet. The
information survived and the marker did not, so a resumed learner receives
its correction buried in a JSON field with no signal that this value is the
reason the previous attempt was refused. An existing test has been failing
on exactly this since that commit.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import learner

PRIOR = {"target": "ad01-w0-dev-sw-00",
         "reason": "invented basis references: obs-invented-999",
         "attempt": 0}


def _prompt(prior=None):
    return learner.visible_prompt({"objective": "x", "freeze_id": "f"},
                                  [], {}, [], {}, None, prior)


def test_the_correction_is_named_where_the_model_reads_it():
    prompt = _prompt(PRIOR)

    assert "PRIOR FAILURE (correct it)" in prompt


def test_the_correction_names_both_the_target_and_the_reason():
    prompt = _prompt(PRIOR)

    assert "ad01-w0-dev-sw-00" in prompt
    assert "invented basis references: obs-invented-999" in prompt


def test_a_first_request_carries_no_correction_marker():
    """A prompt with nothing to correct must not claim otherwise."""
    prompt = _prompt()

    assert "PRIOR FAILURE" not in prompt
    assert '"prior_failure"' not in prompt


def test_the_packet_still_carries_it_for_the_structured_path():
    """The marker is prose; the key is the machine-readable form.

    Both existed before `ab2d28d` and only the marker was dropped, so a
    consumer that reads the packet rather than the prose must keep working.
    """
    packet = learner.learner_request({"objective": "x", "freeze_id": "f"},
                                     [], {}, [], {}, None, PRIOR)

    assert packet["prior_failure"] == PRIOR
