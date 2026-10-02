"""S89-A1: advertised bare method operations execute through the child.

The construction packet advertises bare ``reduce_graph(...)`` and
``reduce_software(...)`` calls. These tests run independently written
candidates that use exactly those advertised calls through the real
child path (``run_member_out_of_process`` out of process, no fakes)
and assert the observed verdicts and measured query counts.

The child executor executes policy source only under a durable store,
an allocation and an operation id, so these tests hold real authority:
a disposable PostgreSQL database, a study allocation authorized against
it, and one operation id per execution. That is not ceremony. The same
bytes run without authority are refused before a byte is staged, so a
test that passed either way would be asserting nothing about the child.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import method_exec, trajectory, worlds
from experiments.ad01.s09_run_isolation import create_disposable_db, \
    drop_disposable_db

MIGRATIONS = ROOT / "migrations"

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


@pytest.fixture(scope="module")
def authority():
    """A real store, a real allocation, and a mint of fresh operation ids.

    Each call mints its own operation id so no test can replay another's
    settled receipt. Replay would answer with the first test's result and
    hide a second execution that never happened.
    """
    database = create_disposable_db("s89a1-authority", migrations_dir=MIGRATIONS)
    try:
        dsn = database.dsn
        trajectory.set_namespace_token("")
        campaign = "s89a1-%s" % uuid.uuid4().hex[:8]
        allocation = trajectory.authorize_campaign(
            dsn, campaign, authorized=100000)
        counter = {"n": 0}
        last = {"operation_id": ""}

        def run(member: dict, task: dict, **kwargs) -> dict:
            counter["n"] += 1
            operation_id = "%s-op%d" % (campaign, counter["n"])
            last["operation_id"] = operation_id
            return method_exec.run_member_out_of_process(
                member, task, dsn=dsn,
                allocation_id=allocation["allocation_id"],
                operation_id=operation_id, **kwargs)

        yield {"run": run, "dsn": dsn, "last_operation_id": last,
               "allocation_id": allocation["allocation_id"]}
    finally:
        drop_disposable_db(database)


def _run(authority, source: str, entry: str, task_id: str,
         max_queries: int) -> dict:
    member = {"capability_id": "s89a1-probe", "method_source": source,
              "entry": entry}
    return authority["run"](member,
                           worlds.load_task(worlds.FROZEN_DIR, task_id),
                           max_queries=max_queries)


def _child_error(dsn: str, operation_id: str) -> str:
    """What the child itself recorded, read back from the settled receipt."""
    from settlement import store

    receipts = store.operation_receipts(dsn, operation_id)
    assert len(receipts) == 1, receipts
    return str(receipts[0]["content"]["data"]["worker"]["error"])


@pytest.mark.parametrize("task_id,source,entry", [
    (DEV_SW, BARE_SW, "probe_sw"),
    (DEV_GR, BARE_GR, "probe_gr"),
])
def test_bare_advertised_helper_executes_in_child(authority, task_id, source,
                                                  entry):
    result = _run(authority, source, entry, task_id, 16)
    assert isinstance(result["candidate"], dict)
    assert 0 < result["queries"] <= 16
    report = trajectory._check(
        worlds.load_task(worlds.FROZEN_DIR, task_id),
        result["candidate"])
    assert report["verdict"] == "preserved", report


def test_direct_oracle_candidate_executes_in_child(authority):
    result = _run(authority, DIRECT_ORACLE, "probe_direct", DEV_SW, 16)
    assert isinstance(result["candidate"], dict)
    assert result["queries"] == 1
    report = trajectory._check(
        worlds.load_task(worlds.FROZEN_DIR, DEV_SW),
        result["candidate"])
    assert report["verdict"] in ("preserved", "not_preserved"), report


def test_malformed_envelope_rejected(authority):
    """The envelope is judged by the child, not by the refusal for no authority.

    Under the durable mandate a member that returns the bare task instead of
    its envelope does not fail the way it used to. The child runs, records a
    typed error, and the operation settles on that error, so the executor
    refuses with "no successful receipt" rather than echoing the child's
    string. That is the correct new refusal, and it is asserted as a literal.

    Asserting the literal alone would be a tautology in waiting, because any
    execution failure produces it. The second assertion reads the settled
    receipt back and requires the child's own recorded reason to be the
    envelope refusal. So the test still fails if the bytes were refused for
    any other reason, and it still fails if the executor stops surfacing the
    envelope contract at all.
    """
    member = {"capability_id": "s89a1-probe", "method_source": MALFORMED,
              "entry": "probe_malformed"}

    with pytest.raises(method_exec.MethodExecutionError) as excinfo:
        authority["run"](member, worlds.load_task(worlds.FROZEN_DIR, DEV_SW),
                         max_queries=16)

    refusal = str(excinfo.value)
    assert refusal == ("refused: durable child operation has no successful"
                       " receipt"), refusal

    recorded = _child_error(authority["dsn"],
                            authority["last_operation_id"]["operation_id"])
    assert recorded.startswith("malformed-result-envelope"), recorded


def test_exhausted_budget_stays_bounded(authority):
    result = _run(authority, BARE_SW, "probe_sw", DEV_SW, 2)
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
