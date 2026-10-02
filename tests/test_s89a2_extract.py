"""A2 extraction: archived validation candidates plus attempt classification.

Reads only evidence_inv01_live/exports. No model calls, no databases.
"""
import hashlib
import json
import os

import pytest

from scripts import s89_diagnose as diag

EXPORT_DIR = os.path.join(os.path.dirname(__file__), "..",
                          "evidence_inv01_live", "exports")

EXPECTED_DIGESTS = {
    "ad01-ad01-w0-I-00-b4-ad01-w0-dev-gr-01-construct-l1-init":
        "d8fa9e5ea2e6e3ff",
    "ad01-ad01-w0-I-00-b4-ad01-w0-dev-gr-01-construct-l2-repair":
        "92f06e0a5d7e32bb",
    "ad01-ad01-w1-I-00-b4-ad01-w1-dev-gr-00-construct-l1-repair":
        "92f06e0a5d7e32bb",
    "ad01-ad01-w1-I-00-b4-ad01-w1-dev-gr-00-construct-l2-init":
        "e8416ad424c898b4",
}


def test_extracts_four_validation_candidates_unedited():
    found = diag.extract_candidates(EXPORT_DIR)
    assert len(found) == 4
    for cand in found:
        assert cand["digest"][:16] == EXPECTED_DIGESTS[cand["origin"]]
        assert hashlib.sha256(
            cand["source"].encode("utf-8")).hexdigest() == cand["digest"]
        assert "reduce_graph" in cand["source"]
        assert cand["old_failure"] == \
            "NameError: name 'reduce_graph' is not defined"


def test_candidate_tasks_are_graph_dev_tasks():
    found = diag.extract_candidates(EXPORT_DIR)
    by_task = {}
    for cand in found:
        by_task.setdefault(cand["task"]["task_id"], []).append(cand["origin"])
    assert set(by_task) == {"ad01-w0-dev-gr-01", "ad01-w1-dev-gr-00"}
    for cand in found:
        assert cand["task"]["family"] == "graph"
        assert cand["task"]["vertices"] and cand["task"]["edges"]


def test_ten_construction_attempts_classified():
    attempts = diag.all_attempts(EXPORT_DIR)
    assert len(attempts) == 10
    terminal = [diag.classify_attempt(a)["terminal"] for a in attempts]
    assert terminal.count("timeout-unknown-exposure") == 3
    assert terminal.count("output-truncation") == 3
    assert terminal.count("execution-failure") == 4
    assert terminal.count("parse-failure") == 0
    assert terminal.count("no-useful-improvement") == 0


def test_truncated_responses_fail_the_real_parse_path():
    attempts = diag.all_attempts(EXPORT_DIR)
    truncated = [a for a in attempts
                 if a["stop_reason"] == "length"]
    assert len(truncated) == 3
    for attempt in truncated:
        assert attempt["output_tokens"] == 2048
        source, problem = diag.parse_response(attempt["text"])
        assert source is None
        assert problem.startswith("parse-failure")


def test_operation_settings_carried_on_every_call():
    attempts = diag.all_attempts(EXPORT_DIR)
    for attempt in attempts:
        assert attempt["max_output_tokens"] == 2048
        assert attempt["deadline_ms"] == 300000


def test_repair_prompts_carry_the_actual_prior_failure():
    priors = diag.repair_priors(EXPORT_DIR)
    assert len(priors) == 4
    stages = sorted(p["prior"]["stage"] for p in priors)
    assert stages == ["execute", "execute", "parse", "parse"]
    for item in priors:
        assert item["prior"]["operation_id"] == item["init_operation"]
