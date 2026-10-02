from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.acquire import panel, run
from experiments.representation.experiment import checker


def _control_files(root: Path, claimed: dict) -> None:
    controls = root / "controls"
    controls.mkdir(parents=True, exist_ok=True)
    for arm in panel.ARMS:
        for task_id in panel.CONTROLS:
            name = "%s-%s" % (arm, task_id)
            (controls / ("%s.json" % name)).write_text(
                json.dumps({"control_pass": claimed.get(name, True)}))


def _execution_inputs(monkeypatch) -> dict:
    manifest, sha, problems = checker.load_manifest()
    assert manifest is not None and not problems
    monkeypatch.setattr(
        run, "ensure_foundation", lambda _dsn, _tag: {
            "manifest": manifest, "manifest_sha": sha})
    monkeypatch.setattr(run, "ensure_episodes", lambda *_args: None)
    monkeypatch.setattr(run, "ensure_compositions", lambda *_args: {})
    monkeypatch.setattr(run, "ensure_protocols", lambda *_args: None)
    return manifest


def test_read_only_control_gate_is_unverifiable(tmp_path):
    _control_files(tmp_path, {"A-ctrl-gr-bipartite": True})
    problems = []

    summary = checker.check_controls(tmp_path, problems)

    assert set(summary) == {
        "%s-%s" % (arm, task_id)
        for arm in panel.ARMS for task_id in panel.CONTROLS}
    assert set(summary.values()) == {False}
    assert all(problem.startswith("control-failed ") for problem in problems)


def test_execution_dsn_cannot_be_verification_dsn(tmp_path):
    _control_files(tmp_path, {})
    problems = []

    summary = checker.check_controls(
        tmp_path, problems, execution_dsn="same",
        verification_dsn="same")

    assert set(summary.values()) == {False}
    assert problems == ["control-execution-unavailable"]


def test_executed_control_result_overrides_forged_field(tmp_path, monkeypatch):
    manifest = _execution_inputs(monkeypatch)
    control_task, _ = run.load_task("ctrl-sw-invalid")

    def passing(_dsn, _ctx, arm, _task_id):
        method = run.method_for(
            manifest["selectors"], arm, control_task,
            run.incumbent_of(control_task)[1])
        native = run.run_native(control_task, method)
        return {"skipped": False, "record": {
            "oracle_queries": native["history"],
            "result": {"final_verdict": native["verdict"],
                       "delivered_digest": native["delivered_digest"]}}}

    _control_files(tmp_path, {"A-ctrl-sw-invalid": False})
    problems = []

    summary = checker.check_controls(
        tmp_path, problems, execution_dsn="scratch", runner=passing)

    assert summary["A-ctrl-sw-invalid"] is True
    assert problems
    assert all(problem.startswith(("control-failed ", "control-execution-failed "))
               for problem in problems)


def test_refused_executed_control_fails(tmp_path, monkeypatch):
    _execution_inputs(monkeypatch)
    control_task, _ = run.load_task("ctrl-gr-triangle")
    incumbent, _ = run.incumbent_of(control_task)

    def refuse(_dsn, _ctx, _arm, _task_id):
        return {"skipped": False, "record": {
            "oracle_queries": [],
            "result": {"disposition": "unsupported",
                       "delivered_digest": run._digest(run._canon(incumbent))}}}

    _control_files(tmp_path, {})
    problems = []

    summary = checker.check_controls(
        tmp_path, problems, execution_dsn="scratch", runner=refuse)

    assert summary["C-ctrl-gr-triangle"] is False
    assert "control-failed C-ctrl-gr-triangle" in problems
