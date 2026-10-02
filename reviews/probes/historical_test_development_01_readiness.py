"""RETIRED characterization probes at e1b95a6 (D02-001..D02-004).

Kept uncollected for the record; their doubles predate the repaired episode
contracts (admission-frozen panel policy, pre-diagnosis experience batch,
binding-only synthesis, subsequent use) and no longer drive the entry.
Superseded by real-DB regressions in tests/test_dev02_episode.py:

- D02-001 test_constructor_prompt_has_unresolved_ids_not_experience ->
  test_batch_materializes_resolved_experience,
  test_construct_packet_binds_and_states_contract
- D02-002 test_rejected_candidate_still_returned_to_comparison ->
  test_rejected_candidate_never_reaches_comparison,
  test_no_candidate_yields_no_comparison_candidate
- D02-003 test_cli_freezes_task_policy_after_construction ->
  test_panel_frozen_before_feedback
- D02-004 test_release_reuse_path_only_routes_and_pins ->
  test_release_orchestrator_never_invokes,
  test_subsequent_use_invokes_selected_version,
  test_reject_use_follows_incumbent_path,
  test_fresh_process_use_records_receipts
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiments")]

import run_dev_episode as entry
from settlement import development, experiment
from settlement.common import Command


def test_constructor_prompt_has_unresolved_ids_not_experience(monkeypatch, tmp_path):
    captured = []
    episode = {
        "id": "probe", "state": "diagnosed", "comparison_exposed": False,
        "allocation_id": "allocation", "max_candidates": 2, "candidates": [],
        "trigger_refs": [{"task_id": "dev-case", "family": "off_by_one"}],
        "access_policy": {"families": ["off_by_one"]},
        "explanations": [{"hypothesis": "boundary handling"}],
        "intervention": {"action": "construct a repair method"},
    }

    def infer(*args, **kwargs):
        captured.append(json.loads(kwargs["prompt"]))
        return kwargs["operation_id"], json.dumps({"no_candidate": "probe"}), None

    monkeypatch.setattr(development, "_require_episode", lambda *a: episode)
    monkeypatch.setattr(development, "_provenance", lambda *a: {"simulated": True})
    monkeypatch.setattr(development, "_mark", lambda *a: None)
    monkeypatch.setattr(experiment, "_infer_via_broker", infer)
    monkeypatch.setattr(experiment, "_settle_costs", lambda *a: None)
    result = development.construct(
        "unused", Command(request_id="probe"), None, None,
        episode_id="probe", model="fixture", artifacts_root=tmp_path,
        staging_root=tmp_path, version_stem="probe", family="off_by_one")
    assert result["status"] == "no-candidate"
    assert captured[0]["experience"]["trigger_refs"] == episode["trigger_refs"]
    assert set(captured[0]["experience"]) == {
        "trigger_refs", "explanations", "intervention", "access_policy"}
    assert "--selftest" not in json.dumps(captured)


def _drive_rejected_episode(monkeypatch, tmp_path):
    calls, seen = [], {}
    built = {"status": "constructed", "version_id": "candidate-s0",
             "artifact_digest": "digest"}

    def step(name, result):
        def run(*args, **kwargs):
            calls.append(name)
            seen[name] = kwargs
            return result
        return run

    for name, result in {
        "observe": {}, "propose": {}, "admit": {}, "diagnose": {},
        "construct": built, "check": {"grade_outcome": "failure"},
        "freeze_comparison": {},
        "select": {"selection": {"decision": "reject", "version_id": None}},
        "bind": {"bindings": {"version_id": None}},
    }.items():
        monkeypatch.setattr(development, name, step(name, result))
    monkeypatch.setattr(entry, "_episode_code", lambda *a: "REJECTED_CANDIDATE_BYTES")
    monkeypatch.setattr(entry.tempfile, "mkdtemp", lambda **kw: str(tmp_path))
    task = {"id": "dev-case", "family": "off_by_one", "broken": "source",
            "cases": [{"fn": "f", "args": [], "expected": 1}]}
    args = SimpleNamespace(episode="probe", investigation="inv",
                           reference_version="baseline-v0", artifacts_root=str(tmp_path))
    result = entry._run_episode(
        "unused", args, None, None, "fixture", "allocation", "prefix",
        [task["id"]], [task], {task["id"]: task}, ["panel"], ["use"])
    return result, calls, seen


def test_rejected_candidate_still_returned_to_comparison(monkeypatch, tmp_path):
    result, _, _ = _drive_rejected_episode(monkeypatch, tmp_path)
    assert result["bindings"]["version_id"] is None
    assert result["synthesize"]([{"broken": "source"}]) == "REJECTED_CANDIDATE_BYTES"
    assert result["fixer_version"] == "prefix-cand"


def test_cli_freezes_task_policy_after_construction(monkeypatch, tmp_path):
    _, calls, seen = _drive_rejected_episode(monkeypatch, tmp_path)
    assert calls.index("construct") < calls.index("freeze_comparison")
    assert set(seen["freeze_comparison"]["policy"]) == {"task_groups"}
    assert seen["observe"]["trigger_refs"] == [
        {"task_id": "dev-case", "family": "off_by_one"}]


def test_release_reuse_path_only_routes_and_pins(monkeypatch, tmp_path):
    calls = []
    for name, result in {
        "get_version": {"applicability": {"family": "off_by_one"}},
        "quarantine_status": None, "scoped_release": {}, "save_router_policy": {},
        "route": {"version_id": "candidate-s0"}, "pin_capability": {},
    }.items():
        def action(*args, _name=name, _result=result, **kwargs):
            calls.append(_name)
            return _result
        monkeypatch.setattr(experiment.capabilities, name, action)
    monkeypatch.setattr(experiment, "_fresh_worker", lambda *a, **kw: "fresh-attempt")
    monkeypatch.setattr(experiment, "_invoke_method", lambda *a, **kw: calls.append("invoke"))
    monkeypatch.setattr(experiment, "_infer_via_broker", lambda *a, **kw: calls.append("infer"))
    groups = ("panel-C", "transfer-C")
    result = experiment._maybe_release(
        "unused", artifacts_root=tmp_path, allocation_id="allocation",
        investigation_id="inv", protocol_prefix="probe", evaluator_version="v1",
        simulated=False, protocols={g: g for g in groups},
        group_candidate={g: "candidate-s0" for g in groups},
        group_families={g: ["off_by_one"] for g in groups},
        verdicts={g: {"label": "observed-gain"} for g in groups})
    assert all(r["status"] == "released" for r in result.values())
    assert "route" in calls and "pin_capability" in calls
    assert "invoke" not in calls and "infer" not in calls
