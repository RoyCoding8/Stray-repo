"""N-36's refusal must refuse, not strand.

`read_deny` is a boundary, and a dispatch that declares one on a kernel that
cannot provide it is refused rather than run unbounded. That refusal shipped
broken: the branch that declines to run the child called `_unwind_claim` with
`seen`, a name first bound six lines below it, so on every host where the
boundary is unavailable the refusal raised `UnboundLocalError` instead of
returning an outcome.

The crash was the visible half. `_claim` had already written the pid file by the
time the refusal ran, so the unwind never happened and the operation was
permanently unrunnable: the first dispatch raised, and the correct response to
a crash -- retry -- was answered with `prior-send-recorded`. A refusal is the
one branch whose whole contract is that the caller can act on the answer, so
this is measured on the retry, not on the exception.

The gap that let it through was in the coverage, not the code. The two tests
that declare a `read_deny` both skip when `landlock_available()` is false --
which is every run on this host, and the refusal branch is the only branch
that runs there. So the refusal path was executed by no test on the machine
that could not avoid it. The tests below are therefore written to be
capability-independent: they drive the branch by pinning the probe, so the
refusal is exercised whether or not this kernel can confine, and a host that
gains Landlock later does not silently stop covering the branch.

The second half is the property that matters. A name-hoist fixes the exception
and leaves the strand exactly as it was, so the retry is asserted as a
successful dispatch of the same operation, through the real launcher, and the
run directory is asserted clean of the markers a refused launch must not leave.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

from settlement import broker
from settlement.launcher_local import (
    LocalLauncher,
    PROFILE,
    LandlockProbe,
    probe_landlock,
)

_UNAVAILABLE = LandlockProbe(
    "landlock", False,
    "landlock unavailable: pinned unavailable so the refusal branch is the "
    "one taken regardless of what this kernel can actually do", 8)


def _op(operation_id: str, generation: int, deny: list[str] | None,
        work: Path) -> broker.BrokerOp:
    payload: dict = {
        "profile": PROFILE,
        "argv": [sys.executable, "-c",
                 "import json; print(json.dumps({'status': 'ok', 'data': {}}))"],
        "timeout_ms": 30_000,
        "max_output_bytes": 65_536,
    }
    if deny is not None:
        payload["read_deny"] = deny
    return broker.BrokerOp(operation_id=operation_id, effect=broker.SANDBOX_EXEC,
                           payload=payload, execution_version="exec-default",
                           dispatch_generation=generation)


def _launcher(tmp: Path, monkeypatch) -> tuple[LocalLauncher, Path]:
    """A launcher whose ledger is this test's, and whose probe is pinned off."""
    work = tmp / "work"
    work.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(work / "ledger.jsonl"))
    monkeypatch.setattr("settlement.launcher_local.probe_landlock",
                        lambda: _UNAVAILABLE)
    monkeypatch.setattr("settlement.launcher_local.landlock_available", lambda: False)
    return LocalLauncher(work / "launcher"), work / "launcher"


def test_a_refused_dispatch_leaves_no_evidence_of_a_send(tmp_path, monkeypatch):
    """The refusal returns an outcome, and the run directory it returns to is
    the one a refused launch should leave: no pid, no spawn, no generation.

    Asserted on the real launcher, with the probe pinned rather than skipped,
    because this is the branch a host that can confine never takes.
    """
    launcher, run_dir = _launcher(tmp_path, monkeypatch)
    outcome = launcher.dispatch(_op("strand-clean", 1, [str(tmp_path)], tmp_path))

    assert outcome.sent is False
    assert outcome.refused_reason.startswith("read-boundary-unavailable:")
    # The reason is the caller's only account of why nothing ran, so it has to
    # name the boundary that was missing rather than read as a bare refusal.
    assert "landlock" in outcome.refused_reason.lower()

    leftovers = sorted(p.suffix for p in run_dir.iterdir())
    assert leftovers == [".work"], (
        "a dispatch that never spawned left the markers of one that did: %r"
        % leftovers)
    # The never-sent proof is what the broker consults before a redispatch. If
    # the refusal left a claim behind, this is the assertion that fails, and it
    # fails for the same reason the retry below would.
    assert launcher.prove_never_sent("strand-clean", 1) is True


def test_a_refused_dispatch_is_retryable(tmp_path, monkeypatch):
    """The property a name-hoist leaves broken.

    Unwind the claim, keep the boundary pinned off, and the retry is refused
    again -- correctly, because the boundary is still unavailable. The thing
    under test is that the second refusal is a *decision* rather than an
    UnboundLocalError, and that it is the same decision twice: the first
    refusal left nothing for the second one to trip over.
    """
    launcher, _ = _launcher(tmp_path, monkeypatch)
    first = launcher.dispatch(_op("strand-retry", 1, [str(tmp_path)], tmp_path))
    second = launcher.dispatch(_op("strand-retry", 1, [str(tmp_path)], tmp_path))

    assert first.sent is False
    assert second.sent is False, (
        "a refused dispatch that spawned on retry: the refusal did not hold")
    assert second.refused_reason == first.refused_reason, (
        "the retry was answered from evidence the refusal left behind: %r vs %r"
        % (second.refused_reason, first.refused_reason))


def test_a_dispatch_retried_after_a_refusal_runs(tmp_path, monkeypatch):
    """The strand, measured end to end: crash, retry, actually runs.

    This is the shape the defect produced and the only assertion here that
    observes a send. The first dispatch declares a boundary this host cannot
    provide and is refused; the second declares none and must run. Before the
    repair the second dispatch returned `prior-send-recorded` and the
    operation could never be dispatched again, which is the whole harm: the
    refusal was supposed to protect the operation and instead consumed it.
    """
    launcher, run_dir = _launcher(tmp_path, monkeypatch)

    refused = launcher.dispatch(_op("strand-run", 1, [str(tmp_path)], tmp_path))
    assert refused.sent is False
    assert refused.refused_reason.startswith("read-boundary-unavailable:")

    # The caller drops the boundary it cannot have. This is what an operator
    # does after reading the refusal, and it is the only retry available to a
    # launcher that cannot confine.
    monkeypatch.setattr("settlement.launcher_local.landlock_available", lambda: True)
    retried = launcher.dispatch(_op("strand-run", 1, None, tmp_path))

    assert retried.sent is True, (
        "the operation was stranded by its own refusal: %r"
        % (retried.refused_reason,))
    assert retried.receipt is not None
    assert retried.receipt.outcome == "success"
    assert (run_dir / "strand-run_exec-default.result.json").exists()
    assert (run_dir / "strand-run_exec-default.spawns").read_text().strip() == "1", (
        "the refused dispatch consumed a spawn, so the spawn count is evidence "
        "of work that never ran")
    # And the send really happened, so the never-sent proof has to be honest
    # about it now.
    assert launcher.prove_never_sent("strand-run", 1) is False


def test_the_refusal_preserves_a_spawn_count_earlier_dispatches_earned(
        tmp_path, monkeypatch):
    """`seen` is the count as it stood *before* this dispatch, not after.

    The unwind writes that count back, so a refusal restores it rather than
    zeroing it. Zeroing would erase a spawn that really happened, which is the
    same class of damage in the other direction and would leave a dispatch that
    did run looking like one that never did.

    The prior spawn is reconstructed rather than faked. A dispatch that spawns
    and then dies before its result write leaves exactly this state -- counted,
    claimed, no result -- which is the crash N-201 recorded as a known limit of
    this file, and it is the only state in which `seen` is above zero when the
    refusal branch runs. Deleting the result file reproduces it through the
    launcher's own writes; nothing is written to the run directory by hand.
    """
    launcher, run_dir = _launcher(tmp_path, monkeypatch)
    first = launcher.dispatch(_op("strand-count", 1, None, tmp_path))
    assert first.sent is True
    assert (run_dir / "strand-count_exec-default.spawns").read_text().strip() == "1"

    (run_dir / "strand-count_exec-default.result.json").unlink()
    assert not list(run_dir.glob("*.pid")), (
        "precondition: a completed dispatch reclaims its own pid, so the only "
        "marker left is the result this removes")

    refused = launcher.dispatch(_op("strand-count", 2, [str(tmp_path)], tmp_path))
    assert refused.sent is False
    assert refused.refused_reason.startswith("read-boundary-unavailable:")

    assert (run_dir / "strand-count_exec-default.spawns").read_text().strip() == "1", (
        "the refusal rolled the spawn count back past a spawn that ran")
    # The generation goes back too, so the next dispatch of this operation is
    # not read as superseded by a generation whose dispatch never happened.
    assert (run_dir / "strand-count_exec-default.gen").read_text().strip() == "1"
    # A restored marker is a marker, and `_never_sent_on_disk` reads .gen: a
    # generation left at 2 would report a dispatch that never happened. Left
    # at 1 it describes a dispatch that did, which is what the count says too.
    assert sorted(p.suffix for p in run_dir.iterdir()) == [".gen", ".spawns", ".work"]


def test_the_refusal_is_not_conditional_on_this_host(tmp_path, monkeypatch):
    """Why the branch is pinned rather than skipped, asserted as a fact.

    The two N-36 tests that declare a deny list both skip when
    `landlock_available()` is false, so on a host without Landlock the refusal
    branch is reached by no test in the suite -- which is the host where it is
    the only branch that runs. This records which host that is, so the
    coverage gap is a stated fact rather than something a future reader has to
    rediscover from a green run.
    """
    if probe_landlock().available:
        pytest.skip("this kernel can confine, so the refusal branch is not the "
                    "default here and the skip-based gap does not apply")
    # Unpinned, on the host that cannot confine, a dispatch declaring a
    # boundary must refuse rather than raise. This is the whole defect, and it
    # is asserted against the real probe with nothing stubbed.
    launcher, _ = _launcher(tmp_path, monkeypatch)
    monkeypatch.undo()
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER",
                        str(tmp_path / "work" / "ledger.jsonl"))
    outcome = launcher.dispatch(_op("strand-real", 1, [str(tmp_path)], tmp_path))
    assert outcome.sent is False
    assert outcome.refused_reason.startswith("read-boundary-unavailable:")
    assert outcome.refused_reason.endswith(probe_landlock().reason)


def test_a_confinement_capable_host_still_denies_rather_than_silently_running():
    """The other half of the branch, so a pinned-unavailable suite is not a
    suite that stopped testing anything.

    With the probe reporting available, a declared deny list is honoured and
    the child runs inside the boundary. Where the kernel can confine, this is
    the only assertion that reaches the increment that `seen` feeds.
    """
    if not probe_landlock().available:
        pytest.skip("landlock unavailable on this kernel: %s"
                    % probe_landlock().reason)
    with tempfile.TemporaryDirectory(prefix="n36-strand-") as tmp:
        work = Path(tmp)
        launcher = LocalLauncher(work / "launcher")
        script = work / "child.py"
        script.write_text("import json\nprint(json.dumps({'ok': True}))\n",
                          encoding="utf-8")
        op = broker.BrokerOp(
            operation_id="strand-capable", effect=broker.SANDBOX_EXEC,
            payload={"profile": PROFILE,
                     "argv": [sys.executable, str(script)],
                     "timeout_ms": 30_000, "max_output_bytes": 65_536,
                     "read_deny": [str(work / "denied")]},
            execution_version="exec-default", dispatch_generation=1)
        (work / "denied").mkdir()
        outcome = launcher.dispatch(op)
        assert outcome.sent is True, outcome.refused_reason
        assert outcome.receipt.content["containment"] is False


def test_a_superseded_generation_refusal_also_unwinds(tmp_path, monkeypatch):
    """The same strand, in the branch above it, and the one I found sweeping.

    A dispatch that has claimed the pid file re-reads the generation to catch
    a newer one landing under it. When that re-read disagrees it refuses with
    `superseded-generation` -- and, before this repair, it refused while still
    holding the durable pid claim from `_claim`. That is the identical strand:
    the caller retries the operation it legitimately owns and is told
    `prior-send-recorded` by its own abandoned claim.

    `RunscLauncher` unwinds at exactly this decision (`launcher_runsc.py:401`),
    so the two launchers disagreed about it. They do not now.

    The re-read is gated rather than raced, because a real interleaving needs
    the loser paused between its write and its re-read, which is a window a test
    cannot open by scheduling alone. Gating `_recorded_generation` is what
    `test_r01c_redispatch.py` already does to reach the neighbouring branch, and
    it drives the launcher's real code with one seam.

    The newer generation is written by dispatching a real one, not by editing
    the file. Editing it is what the first version of this test did, and it is
    a test that passes against a repair which erases live evidence: a real
    newer dispatch is the only way to produce the state honestly, and it is the
    state whose preservation is under test.
    """
    launcher, run_dir = _launcher(tmp_path, monkeypatch)
    real_read = LocalLauncher._recorded_generation
    state = {"gen_reads": 0, "fired": False}

    def gated(self, path):
        value = real_read(self, path)
        if not path.name.endswith(".gen"):
            return value
        state["gen_reads"] += 1
        if state["gen_reads"] == 2 and not state["fired"]:
            # The window under test: this dispatch has claimed the pid file
            # and written its own generation, and is about to re-read it. A
            # newer generation arriving now is exactly what the re-read is
            # there to catch, and the newer dispatch below produces it the way
            # one really arrives -- by taking the pid claim it cannot have,
            # bumping the generation, and refusing.
            state["fired"] = True
            newer = launcher.dispatch(_op("strand-superseded", 99, None, tmp_path))
            assert newer.refused_reason == "superseded-claim"
            # Re-read, rather than return the value read before the newer
            # dispatch landed. The re-read in the launcher is what observes the
            # change, and a seam that handed back a stale value would be testing
            # the seam rather than the branch.
            return real_read(self, path)
        return value

    monkeypatch.setattr(LocalLauncher, "_recorded_generation", gated)
    refused = launcher.dispatch(_op("strand-superseded", 1, None, tmp_path))
    monkeypatch.setattr(LocalLauncher, "_recorded_generation", real_read)

    assert state["fired"], "precondition: the re-read window was never reached"

    assert refused.sent is False
    assert refused.refused_reason == "superseded-generation"
    # Only the claim goes. The generation file now holds the *newer*
    # dispatch's record, and rolling it back would erase a live generation's
    # evidence -- which is the damage this class of bug causes in the other
    # direction, and is what `test_paused_after_claim_never_spawns` pins.
    assert sorted(p.name for p in run_dir.iterdir()) == [
        "strand-superseded_exec-default.gen"], (
        "a superseded dispatch left the pid claim behind, or took the newer "
        "generation's record with it")
    assert (run_dir / "strand-superseded_exec-default.gen").read_text().strip() == "99"

    # And the retry is the property, not the absence of the exception.
    retried = launcher.dispatch(_op("strand-superseded", 99, None, tmp_path))
    assert retried.sent is True, (
        "the operation was stranded by a refusal that owned its claim: %r"
        % (retried.refused_reason,))
    assert (run_dir / "strand-superseded_exec-default.spawns").read_text().strip() == "1"
