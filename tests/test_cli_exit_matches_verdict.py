"""A CLI must not exit 0 while holding a verdict that says it failed.

Four entry points computed a strict verdict, wrote it into a status
document, printed it, and then returned 0. An operator reading the exit
code learned the opposite of what the document beside it said. Each test
here calls one surface the way a shell does and asserts the code agrees
with the verdict that surface itself produced.

Nothing re-verifies anything. The collaborator that produces the verdict
stands in, and the assertion is about the decision the CLI makes from it,
which is the only part these four got wrong.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def _ag01_argv(tmp_path, world_id: str, *extra: str) -> list:
    from experiments.agenda01 import manifest

    doc, digest = manifest.build()
    manifest_path = tmp_path / "manifest.json"
    hash_path = tmp_path / "manifest.sha256"
    manifest_path.write_text(json.dumps(doc, sort_keys=True, indent=2))
    hash_path.write_text(digest + "\n")
    return ["run", "--base-dsn", "unused", "--world", world_id,
            "--arm", "R", "--tie", "0", "--manifest", str(manifest_path),
            "--manifest-hash-file", str(hash_path),
            "--out-dir", str(tmp_path / "traces"), *extra]


def _trajectory(complete: bool, end_reason: str) -> dict:
    return {"traj_id": "ag01-t-0", "complete": complete,
            "end_reason": end_reason, "grade": None}


# ---------------------------------------------------------------------------
# agenda01 replay
# ---------------------------------------------------------------------------


def test_replay_run_refuses_a_trajectory_that_ran_out_of_budget(
        tmp_path, monkeypatch):
    """`--max-ticks` asks for a short run, which is not a pass.

    The trace is the runner's own verdict about itself, and `unfundable`
    is the one reason that no amount of asking will change: the
    trajectory could not pay for its own next decision. The guard used to
    wave through any run that carried the flag, so that failure exited 0.
    """
    from experiments.agenda01 import replay, runner

    monkeypatch.setattr(
        runner, "run_trajectory",
        lambda *a, **k: _trajectory(False, "unfundable"))
    code = replay.main(_ag01_argv(tmp_path, "w00", "--max-ticks", "5"))
    assert code == 1, (
        "a trajectory that stopped unfundable exited 0 with --max-ticks set")


def test_replay_run_accepts_the_short_run_its_caller_asked_for(
        tmp_path, monkeypatch):
    """The bound must stay meaningful, or --max-ticks always fails.

    A trajectory stopped at the horizon before reaching its own horizon is
    exactly the prefix that was requested. Refusing that too would be a
    different defect, and the same fix would have introduced it.
    """
    from experiments.agenda01 import replay, runner

    monkeypatch.setattr(
        runner, "run_trajectory",
        lambda *a, **k: _trajectory(False, "horizon"))
    code = replay.main(_ag01_argv(tmp_path, "w00", "--max-ticks", "5"))
    assert code == 0, "the requested short run was refused"


# ---------------------------------------------------------------------------
# team01 entry
# ---------------------------------------------------------------------------


def test_team01_entry_refuses_a_panel_whose_disposition_is_not_clean(
        tmp_path, monkeypatch):
    """The disposition's own `clean` is the strict verdict on the panel.

    The same package's checker exits 1 on the same field, so an entry
    point returning 0 here reported a dirty panel as a finished run. The
    reasons are already in the status document it prints.
    """
    from experiments.team01 import entry

    status = {"tag": "t", "phases_completed": ["disposition"],
              "disposition": {"clean": False, "records": 4,
                              "promising": {"eval": False},
                              "reasons": ["missing-panel-evidence eval+transfer"],
                              "release_eligible": False}}
    monkeypatch.setattr(entry, "run_team_panel", lambda *a, **k: status)
    code = entry.main(["--dsn", "unused", "--tag", "t",
                       "--evidence-root", str(tmp_path)])
    assert code == 1, (
        "the panel's own disposition says clean=false and the CLI exited 0")


def test_team01_entry_exits_zero_when_it_never_ran_a_disposition(
        tmp_path, monkeypatch):
    """A run that did not ask for a phase cannot have failed one.

    `--phases` is selective, so a development-only run holds no
    disposition at all. Reading the absent key as a failed disposition
    would make every partial run red.
    """
    from experiments.team01 import entry

    status = {"tag": "t", "phases_requested": ["development"],
              "phases_completed": ["development"]}
    monkeypatch.setattr(entry, "run_team_panel", lambda *a, **k: status)
    code = entry.main(["--dsn", "unused", "--tag", "t",
                       "--evidence-root", str(tmp_path),
                       "--phases", "development"])
    assert code == 0


# ---------------------------------------------------------------------------
# representation acquire entry
# ---------------------------------------------------------------------------


def test_representation_entry_refuses_a_disposition_that_found_problems(
        tmp_path, monkeypatch):
    """`problems` is the strict verdict, and it is never empty by design.

    `decide_disposition` accumulates manifest drift, evidence gaps, a
    failed barrier, controls that did not pass and a cross-check that
    blew up into one list. A non-empty list is a broken evidence root, and
    the checker that owns it exits 1 on exactly that list.
    """
    from experiments.representation.acquire import experiment

    status = {"tag": "t", "phases_completed": ["disposition"],
              "disposition": {"promising": False, "release_eligible": False,
                              "use_authorized": False,
                              "reasons": ["missing-manifest"],
                              "problems": ["missing-manifest"]}}
    monkeypatch.setattr(experiment, "run_experiment", lambda *a, **k: status)
    code = experiment.main(["--dsn", "unused", "--tag", "t",
                            "--evidence-root", str(tmp_path),
                            "--phases", "disposition"])
    assert code == 1, (
        "the disposition carried problems and the CLI exited 0")


def test_representation_entry_exits_zero_when_no_pilot_is_promising(
        tmp_path, monkeypatch):
    """A pilot that certifies nothing is still a clean run.

    `release_eligible` and `use_authorized` are false for every pilot by
    construction, and `promising` is a finding rather than a fault. If the
    gate read those it would refuse every experiment this module exists to
    run; only `problems` says the evidence root is broken.
    """
    from experiments.representation.acquire import experiment

    status = {"tag": "t", "phases_completed": ["disposition"],
              "disposition": {"promising": False, "release_eligible": False,
                              "use_authorized": False,
                              "reasons": ["no separation"], "problems": []}}
    monkeypatch.setattr(experiment, "run_experiment", lambda *a, **k: status)
    code = experiment.main(["--dsn", "unused", "--tag", "t",
                            "--evidence-root", str(tmp_path),
                            "--phases", "disposition"])
    assert code == 0, (
        "a clean pilot that certifies nothing was refused; the gate is "
        "reading a finding as a fault")


def test_representation_entry_refuses_a_dirty_final_check(tmp_path, monkeypatch):
    """`use` adds a second strict verdict and it is not optional.

    `final_check` is `checker.check_all` over the same evidence root, and
    that checker's own CLI exits 1 when `clean` is false. Reading only the
    disposition would leave the phase that runs last ungated.
    """
    from experiments.representation.acquire import experiment

    status = {"tag": "t", "phases_completed": ["use"],
              "disposition": {"promising": False, "problems": []},
              "final_check": {"clean": False, "records": 12,
                              "problems": ["db-cross-check-failed"]}}
    monkeypatch.setattr(experiment, "run_experiment", lambda *a, **k: status)
    code = experiment.main(["--dsn", "unused", "--tag", "t",
                            "--evidence-root", str(tmp_path),
                            "--phases", "use"])
    assert code == 1, "the final check was unclean and the CLI exited 0"


# ---------------------------------------------------------------------------
# ad01 experience axis
# ---------------------------------------------------------------------------


def test_experience_axis_refuses_a_report_over_a_broken_freeze(monkeypatch):
    """The `verify` subcommand already refuses this exact predicate.

    `main` computed `verify_committed() + audit(all_tasks())` for the
    report, printed it under `freeze`, and returned 0, three lines below a
    subcommand that computes the same two lists and returns 1. A freeze
    whose digests do not re-derive is the measurement failing, and the
    report that publishes it is the last place that can say so.
    """
    from experiments.ad01 import experience_axis as axis

    monkeypatch.setattr(axis, "verify_committed",
                        lambda: ["digest-mismatch world-0/dev/sw-1.json"])
    code = axis.main([])
    assert code == 1, (
        "the report published a freeze whose verifier lists problems and "
        "the CLI exited 0")


def test_experience_axis_exits_zero_over_an_intact_freeze(monkeypatch):
    """The refusal must key on the problems, not on the run having happened.

    Both verifier lists empty is the ordinary case, and it has to stay 0
    or every honest census of this axis is reported as a failure.
    """
    from experiments.ad01 import experience_axis as axis

    monkeypatch.setattr(axis, "verify_committed", lambda: [])
    code = axis.main([])
    assert code == 0, "an intact freeze and a clean audit were refused"


def test_experience_axis_refuses_a_clean_freeze_with_a_failing_audit(
        monkeypatch):
    """The freeze verifier and the task audit are two different checks.

    `verify_committed` re-derives file digests; `audit` re-derives the
    task invariants the files are supposed to encode. An audit problem on
    an intact freeze is still a broken panel, and it is the audit half
    that this report's other claims rest on.
    """
    from experiments.ad01 import experience_axis as axis

    monkeypatch.setattr(axis, "audit",
                        lambda tasks: ["dev-use-leakage exp-axis-w0-sw-dev-0"])
    code = axis.main([])
    assert code == 1, "the task audit failed and the CLI exited 0"
