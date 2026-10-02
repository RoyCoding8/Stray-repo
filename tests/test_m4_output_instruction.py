"""The output prompt's instruction contradicted its only legal reply.

`RuleSession.model_input` tells its reader it may probe *or* commit. The
output study embeds that view in a prompt whose sole legal reply is the
commit, and by then the session has spent all eight queries, so the probe
half is an instruction the model can follow and cannot. Asked to choose
between probe and commit with nothing left to probe, it narrated its
reasoning instead of emitting the JSON: all eight dispatches came back
5000+ characters against a 512-character cap and every one was rejected
`too-long`. The run reported `incomplete` and the M4 baseline could not be
established.

`output_model_input` keeps the public fields identical and changes only the
instruction, so the prompt still describes the same task and the frozen
digest check still has one shape. These tests pin that the two views differ
in the instruction and nowhere else, and that no path feeding the output
prompt is still reaching for the active world's view.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import boolean_rule
from experiments.ad01 import live_construct as live


def _spent_session():
    task = boolean_rule.make_task("audit", 23)
    session = boolean_rule.RuleSession(task)
    for x in range(0, 16, 2):
        if session.remaining > 0:
            session.query(x)
    return session


def test_the_output_view_differs_only_in_the_instruction():
    session = _spent_session()
    active = session.model_input()
    output = session.output_model_input()

    assert set(active) == set(output)
    differing = {k for k in active if active[k] != output[k]}
    assert differing == {"instruction"}, differing
    for key in active:
        if key != "instruction":
            assert active[key] == output[key]


def test_the_output_instruction_offers_no_probe():
    """The prompt must not ask for a probe it will then reject.

    By the time the prompt renders, the budget is spent, so an instruction
    offering a probe is a choice the model can make and cannot satisfy.
    The output instruction does name probes, but only to close them off, so
    the test is that the choice is not offered rather than that the word
    never appears.
    """
    session = _spent_session()
    assert session.remaining == 0

    instruction = session.output_model_input()["instruction"]
    assert "commit" in instruction.lower()
    assert "choose" not in instruction.lower()
    assert "no further probes" in instruction.lower()
    assert "probe," not in instruction.lower(), (
        "the output instruction must not offer a probe to choose")


def test_the_active_view_still_offers_both():
    """The active world's view is unchanged; it really can do either.

    The two worlds differ, and the output fix must not have flattened the
    active world into the output one.
    """
    instruction = _spent_session().model_input()["instruction"]
    assert "probe" in instruction.lower()
    assert "commit" in instruction.lower()


def test_the_output_prompt_carries_no_probe_instruction():
    session = _spent_session()
    prompt = live.render_output_prompt(
        session.output_model_input(), [], 1)

    assert "Commit one executable predictor" in prompt
    assert "Choose an unqueried" not in prompt, (
        "the output prompt must not carry the active world's probe offer")


def test_no_output_path_still_renders_the_active_view():
    """Every renderer of the output prompt must use the output view.

    The frozen digest check compares the live dispatch's prompt against a
    re-render. If one side kept the active view and the other took the
    output view, the two digests would differ and every dispatch would be
    reported as a frozen-rendered-prompt mismatch — the failure this fix
    would otherwise cause rather than remove.
    """
    for relative in ("scripts/invl02_live.py",
                     "experiments/ad01/offline_recompute.py",
                     "experiments/ad01/s09_exposure_ledger.py"):
        source = (ROOT / relative).read_text()
        stale = [line for line in source.splitlines()
                 if "model_input()" in line and "output_model_input()" not in line]
        assert not stale, "%s still renders the active view: %s" % (
            relative, stale)
