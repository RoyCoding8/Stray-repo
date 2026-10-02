from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.ad01 import packet

HOSTILE = {
    "task_id": "t-1",
    "family": "software",
    "ops": [{"kind": "get", "key": "a"}],
    "witness": {"ref": "SECRET-REF", "faulty": "SECRET-FAULTY"},
    "fault": "SECRET-FAULT",
    "answer": "SECRET-ANSWER",
    "private_target": "SECRET-TARGET",
    "split_label": "audit",
    "checker_secret": "SECRET-CHECKER",
    "hidden_answer": "SECRET-HIDDEN",
    "sealed_answer": "SECRET-SEALED",
    "access_label": "evaluator",
    "nested": {"hidden_answer": "SECRET-NESTED", "note": "keep-me"},
}


def test_known_public_fields_survive():
    cleaned = packet.strip_task(HOSTILE)

    assert cleaned["task_id"] == "t-1"
    assert cleaned["family"] == "software"
    assert cleaned["ops"] == [{"kind": "get", "key": "a"}]


@pytest.mark.parametrize("secret", [
    "witness", "fault", "answer", "private_target", "split_label",
    "checker_secret", "hidden_answer", "sealed_answer", "access_label",
])
def test_assessor_secrets_never_reach_the_policy_view(secret):
    cleaned = packet.strip_task(HOSTILE)

    assert secret not in cleaned


def test_nested_sealed_keys_are_stripped():
    cleaned = packet.strip_task(HOSTILE)

    assert "hidden_answer" not in (cleaned.get("nested") or {})


def test_unknown_named_secret_cannot_pass_through():
    hostile = dict(HOSTILE)
    hostile["some_future_assessor_secret"] = "SECRET-NEW-NAME"

    cleaned = packet.strip_task(hostile)

    assert "some_future_assessor_secret" not in cleaned


def test_real_frozen_task_witness_is_removed():
    task = json.loads(Path(
        "experiments/ad01/worlds/world-0/transfer/"
        "ad01-w0-transfer-sw-00.json").read_text())
    assert "witness" in task, "fixture changed; test is not exercising the leak"

    cleaned = packet.strip_task(task)

    assert "witness" not in cleaned
    assert "fault" not in cleaned
    assert cleaned["task_id"] == task["task_id"]


def test_boolean_public_view_survives_stripping():
    from experiments.ad01 import boolean_rule

    view = {
        "instrument": boolean_rule.INSTRUMENT_ID,
        "task_id": "rule-audit-0023",
        "split": "audit",
        "max_queries": 8,
        "remaining": 3,
        "observed": [{"x": 1, "y": [1, 0, 1, 0]}],
        "hypothesis_class": {"class_digest": "285113caf4ab", "n_inputs": 4},
    }

    cleaned = packet.strip_task(view)

    assert set(cleaned) == set(view)


def test_policy_view_excludes_the_witness_a_method_view_keeps():
    task = json.loads(Path(
        "experiments/ad01/worlds/world-0/transfer/"
        "ad01-w0-transfer-sw-00.json").read_text())

    policy_view = packet.strip_task(task)
    method_view = packet.method_task_view(task)

    assert "witness" not in policy_view
    assert "fault" not in policy_view
    assert "witness" in method_view
    assert method_view["witness"] == task["witness"]


def test_method_view_still_drops_sealed_generic_keys():
    method_view = packet.method_task_view(
        dict(HOSTILE, witness={"ref": "r"}, fault="f"))

    assert "hidden_answer" not in method_view
    assert "sealed_answer" not in method_view
    assert "access_label" not in method_view
    assert "answer" in method_view or "private_target" in method_view

