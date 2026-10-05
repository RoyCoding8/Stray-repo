"""A2 rerun: archived candidates through an injected execution path.

Proves the runner records new outcome plus next failure without editing
source bytes, and proves the current tree reproduces the archived
NameError through the real method_exec child path. No model calls.
"""
import hashlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from execution_authority import authority_for, execution_store

from scripts import s89_diagnose as diag

EXPORT_DIR = os.path.join(os.path.dirname(__file__), "..",
                          "evidence_inv01_live", "exports")


@pytest.fixture(scope="module")
def store():
    """The store the rerun executes archived candidate source under.

    `current_tree_execute` forwards its authority to the child executor, and
    the executor refuses without a store, an allocation and an operation
    identity. A refusal here reads as `gate-refusal`, which is a claim about
    the candidate that was never measured: the bytes did not run at all.
    """
    with execution_store("s89a2rerun") as authority_store:
        yield authority_store


def _stub_fixed(member, task, max_queries=16):
    return {"ok": True,
            "result": {"candidate": dict(task), "queries": 1}}


def test_runner_passes_source_bytes_unedited_to_injected_path():
    seen = []

    def spy(member, task, max_queries=16):
        seen.append(member["method_source"])
        return {"ok": True, "result": {"candidate": {}, "queries": 0}}

    cand = diag.extract_candidates(EXPORT_DIR)[0]
    report = diag.run_candidate(cand, execute_fn=spy, max_queries=16)
    assert report["digest"] == cand["digest"]
    assert hashlib.sha256(seen[0].encode("utf-8")).hexdigest() == \
        cand["digest"]
    assert report["new_outcome"] == "executed"


def test_runner_records_next_failure_from_injected_path():
    def spy(member, task, max_queries=16):
        return {"ok": False, "stage": "check",
                "reason": "not_preserved/witness-lost-bipartite"}

    cand = diag.extract_candidates(EXPORT_DIR)[0]
    report = diag.run_candidate(cand, execute_fn=spy, max_queries=16)
    assert report["new_outcome"] == "no-useful-improvement"
    assert report["next_failure"] == \
        "not_preserved/witness-lost-bipartite"


def test_fixed_tree_executes_archived_candidates_past_nameerror(store):
    found = diag.extract_candidates(EXPORT_DIR)
    assert len(found) == 4
    for index, cand in enumerate(found):
        report = diag.run_candidate(
            cand, execute_fn=diag.current_tree_execute, max_queries=16,
            authority=authority_for(store, "s89a2-archived-%d" % index))
        assert "NameError" in report["old_failure"]
        assert report["new_outcome"] == "executed"
        assert report["next_failure"] is None


def test_rerun_leaves_committed_evidence_untouched(store):
    before = {}
    for name in sorted(os.listdir(EXPORT_DIR)):
        path = os.path.join(EXPORT_DIR, name)
        with open(path, "rb") as handle:
            before[name] = hashlib.sha256(handle.read()).hexdigest()
    for index, cand in enumerate(diag.extract_candidates(EXPORT_DIR)):
        diag.run_candidate(cand, execute_fn=diag.current_tree_execute,
                           max_queries=16,
                           authority=authority_for(
                               store, "s89a2-untouched-%d" % index))
    for name, digest in before.items():
        with open(os.path.join(EXPORT_DIR, name), "rb") as handle:
            assert hashlib.sha256(handle.read()).hexdigest() == digest
