"""S89-A1: advertised bare method operations execute through the child.

The construction packet advertises bare ``reduce_graph(...)`` and
``reduce_software(...)`` calls. These tests run independently written
candidates that use exactly those advertised calls through the real
child path (``run_member_out_of_process`` out of process, no fakes)
and assert the observed verdicts and measured query counts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import method_exec, trajectory, worlds

DEV_SW = "ad01-w0-dev-sw-00"
DEV_GR = "ad01-w0-dev-gr-00"

BARE_SW = (
    "def probe_sw(task, oracle, max_queries=16):\n"
    "    return reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
BARE_GR = (
    "def probe_gr(task, oracle, max_queries=16):\n"
    "    return reduce_graph(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
DIRECT_ORACLE = (
    "def probe_direct(task, oracle, max_queries=16):\n"
    "    first = dict(task)\n"
    "    first[\"ops\"] = task[\"ops\"][:-1]\n"
    "    report = oracle.query(first)\n"
    "    if report[\"verdict\"] == \"preserved\":\n"
    "        return {\"candidate\": first, \"queries\": 1}\n"
    "    return {\"candidate\": task, \"queries\": 1}\n"
)
MALFORMED = (
    "def probe_malformed(task, oracle, max_queries=16):\n"
    "    return task\n"
)


def _run(source: str, entry: str, task_id: str, max_queries: int) -> dict:
    member = {"capability_id": "s89a1-probe", "method_source": source,
              "entry": entry}
    return method_exec.run_member_out_of_process(
        member, worlds.load_task(worlds.FROZEN_DIR, task_id),
        max_queries=max_queries)


@pytest.mark.parametrize("task_id,source,entry", [
    (DEV_SW, BARE_SW, "probe_sw"),
    (DEV_GR, BARE_GR, "probe_gr"),
])
def test_bare_advertised_helper_executes_in_child(task_id, source, entry):
    result = _run(source, entry, task_id, 16)
    assert isinstance(result["candidate"], dict)
    assert 0 < result["queries"] <= 16
    report = trajectory._check(
        worlds.load_task(worlds.FROZEN_DIR, task_id),
        result["candidate"])
    assert report["verdict"] == "preserved", report


def test_direct_oracle_candidate_executes_in_child():
    result = _run(DIRECT_ORACLE, "probe_direct", DEV_SW, 16)
    assert isinstance(result["candidate"], dict)
    assert result["queries"] == 1
    report = trajectory._check(
        worlds.load_task(worlds.FROZEN_DIR, DEV_SW),
        result["candidate"])
    assert report["verdict"] in ("preserved", "not_preserved"), report


def test_malformed_envelope_rejected():
    with pytest.raises(method_exec.MethodExecutionError) as excinfo:
        _run(MALFORMED, "probe_malformed", DEV_SW, 16)
    assert "malformed" in str(excinfo.value)


def test_exhausted_budget_stays_bounded():
    result = _run(BARE_SW, "probe_sw", DEV_SW, 2)
    assert result["queries"] <= 2
    report = trajectory._check(
        worlds.load_task(worlds.FROZEN_DIR, DEV_SW),
        result["candidate"])
    assert report["verdict"] in ("preserved", "not_preserved",
                                 "invalid", "unknown"), report


def test_prompt_exposure_derives_from_executor_contract():
    from experiments.ad01 import packet as P
    contract = method_exec.child_contract()
    assert contract["version"]
    for family in ("software", "graph"):
        exposed = P.public_operations(family)
        assert set(exposed) >= set(contract["callables"])
        for name, spec in contract["callables"].items():
            assert exposed[name]["signature"] == spec["signature"]
            assert exposed[name]["returns"] == spec["returns"]
    prompt = P.render_construction_prompt(P.construction_packet(
        task=worlds.load_task(worlds.FROZEN_DIR, DEV_SW),
        experience={"observations": []},
        budget={"max_output_tokens": 512}, prior_failure=None))
    for name in contract["callables"]:
        assert name in prompt
