"""ECR2-01/05 failing-behavior probes for the exec lane (red before fix).

Covers the review probe's exec-owned claims at the public entry:
genuine four-arm drivers (no protected-overlay reads, distinct S/A
proposals), frozen-order execution, ceiling field shape, and the
fixture-only labeling boundary.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.coord02 import entry, experience, oracle


def _proposal(arm, task):
    with tempfile.TemporaryDirectory(prefix="coord02-exec-red-") as area:
        root = Path(area)
        program, request, response = [root / p for p in
                                      ("policy.py", "request.json",
                                       "response.json")]
        program.write_bytes(entry.arm_policy_entry(
            arm, task_id=task, package_digest="retained-program"))
        request.write_text(json.dumps(dict(
            profile="coordination-procedure",
            profile_version="coordination-procedure/1",
            decision_id="review", package_digest="retained-program",
            source_digest="snapshot", plan_revision=0, phase="post-probe")))
        subprocess.run([sys.executable, str(program), str(request),
                        str(response)], check=True, capture_output=True,
                       timeout=10)
        return json.loads(response.read_text())["proposal"]


def test_arms_avoid_protected_overlay():
    task = oracle.SPLITS["development"][0]
    accessed = []
    for arm in entry.ARMS:
        with patch.object(experience.oracle, "overlay_files",
                          side_effect=RuntimeError("protected-reference-read")):
            try:
                entry.arm_child_factory(arm, task, "retained source")(
                    "w1", {"owned_paths": []}, {})
            except RuntimeError as error:
                if str(error) != "protected-reference-read":
                    raise
                accessed.append(arm)
    assert accessed == []


def test_s_and_a_proposals_differ():
    task = oracle.SPLITS["development"][0]
    assert _proposal("S", task) != _proposal("A", task)


def test_run_panel_preserves_frozen_order():
    task = oracle.SPLITS["development"][0]
    freeze = {"freeze_id": "review", "schedule":
              [{"panel": "evaluation", "task": task, "repeat": 1, "arm": arm}
               for arm in ("L", "F", "A", "S")]}
    executed = []
    with patch.object(entry, "run_cell", side_effect=lambda *a, **k:
                      executed.append(k["arm"])):
        entry.run_panel("unused", freeze=freeze, panel="evaluation",
                        launcher_factory=None, repeats=(1,))
    assert executed == ["L", "F", "A", "S"]


def test_ceilings_read_stored_cost_shape():
    assert entry.check_ceilings({"model_tokens_in": 1_000_000,
                                 "model_tokens_out": 0}) != []
