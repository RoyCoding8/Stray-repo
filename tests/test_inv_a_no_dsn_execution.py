"""L2: no source file becomes trusted merely because it is local.

`method_exec.run_step_out_of_process` and
`method_exec.run_member_out_of_process` each carried a live `dsn is None`
branch that executed policy source through `launcher.dispatch` directly,
outside the broker. Containment held (the bytes still ran in a child), but
authority did not: that route minted no operation row, no allocation, no
receipt and no attribution, so nothing recorded that the source had run.

The mandate is now the type of the call, not a runtime branch. A policy
source executes only under a `dsn`, an `allocation_id` and an
`operation_id`. Anything else is refused before a byte is staged.

Three claims are proved here:

1. `run_step_out_of_process` with no dsn raises `MethodExecutionError` and
   constructs nothing that could execute.
2. `run_member_out_of_process` with no dsn likewise.
3. The raw branch is gone from the source, so re-introducing it is red.

The positive control runs a real STEP policy against a real PostgreSQL
store, because a refusal test alone cannot tell a closed seam from a
permanently broken executor.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import method_exec, worlds
from experiments.ad01 import policy_step
from experiments.ad01.s09_run_isolation import create_disposable_db, \
    drop_disposable_db

MIGRATIONS = ROOT / "migrations"

STEP_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    action = {\"kind\": \"diagnose\", \"target\": target,\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"unknown\": \"does the seed disagree\",\n"
    "                         \"question\": \"why this verdict\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {\"n\": 1}}\n"
)

MEMBER_SOURCE = (
    "def carried(task, oracle):\n"
    "    return {\"candidate\": {\"lines\": [\"x\"]}, \"queries\": 0}\n"
)


def _step_view() -> dict:
    return policy_step.materialize_view(
        task=worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00"),
        observations=[], open_questions=[], last_result=None,
        eligible_methods=[], remaining={"steps": 1})


@pytest.fixture(scope="module")
def store():
    database = create_disposable_db("inva-nodsn", migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database)


@pytest.fixture
def no_execution(monkeypatch):
    """Record every route by which policy source could reach a child.

    `LocalLauncher` is the only object in the executor that can start one,
    so constructing it at all means the executor committed to running the
    source. The broker pair is recorded separately because an admitted
    operation with no dispatch would still be a state change worth seeing.
    """
    seen = {"launchers": 0, "ensure": [], "dispatch": []}

    class UnreachableLauncher:
        def __init__(self, *args, **kwargs):
            seen["launchers"] += 1

    monkeypatch.setattr(method_exec, "LocalLauncher", UnreachableLauncher)
    monkeypatch.setattr(
        method_exec.broker, "ensure_operation",
        lambda dsn, **kwargs: seen["ensure"].append(kwargs))
    monkeypatch.setattr(
        method_exec.broker, "dispatch_operation",
        lambda *a, **k: seen["dispatch"].append(kwargs))
    return seen


def test_step_source_without_a_dsn_is_refused_and_runs_nothing(no_execution):
    with pytest.raises(method_exec.MethodExecutionError) as raised:
        method_exec.run_step_out_of_process(STEP_SOURCE, _step_view(), {})

    assert "refused:" in str(raised.value)
    assert no_execution == {"launchers": 0, "ensure": [], "dispatch": []}


def test_step_source_with_a_dsn_but_no_operation_id_is_refused(no_execution):
    with pytest.raises(method_exec.MethodExecutionError,
                       match="refused:"):
        method_exec.run_step_out_of_process(
            STEP_SOURCE, _step_view(), {}, dsn="postgresql://unused",
            allocation_id="alloc-x")

    assert no_execution["launchers"] == 0
    assert no_execution["dispatch"] == []


def test_step_source_with_a_dsn_but_no_allocation_is_refused(no_execution):
    with pytest.raises(method_exec.MethodExecutionError,
                       match="refused:"):
        method_exec.run_step_out_of_process(
            STEP_SOURCE, _step_view(), {}, dsn="postgresql://unused",
            operation_id="op-x")

    assert no_execution["launchers"] == 0
    assert no_execution["dispatch"] == []


def test_member_source_without_a_dsn_is_refused_and_runs_nothing(no_execution):
    member = {"capability_id": "no-dsn-member",
              "method_source": MEMBER_SOURCE, "entry": "carried"}

    with pytest.raises(method_exec.MethodExecutionError) as raised:
        method_exec.run_member_out_of_process(member, {})

    assert "refused:" in str(raised.value)
    assert no_execution == {"launchers": 0, "ensure": [], "dispatch": []}


def test_member_source_with_a_dsn_but_no_operation_id_is_refused(no_execution):
    member = {"capability_id": "no-op-member",
              "method_source": MEMBER_SOURCE, "entry": "carried"}

    with pytest.raises(method_exec.MethodExecutionError,
                       match="refused:"):
        method_exec.run_member_out_of_process(
            member, {}, dsn="postgresql://unused", allocation_id="alloc-y")

    assert no_execution["launchers"] == 0
    assert no_execution["dispatch"] == []


def test_the_raw_launcher_branch_no_longer_exists_in_the_executor():
    """The grep pin. Re-introducing an unbrokered send is red here.

    Every send and every receipt read in the executor must name the broker.
    A `launcher.dispatch` or `launcher.read_result` line is by definition a
    policy source running on the executor's own authority, which is the hole
    this lane closes.
    """
    source = (ROOT / "experiments" / "ad01" / "method_exec.py").read_text(
        encoding="utf-8")

    assert "launcher.dispatch(" not in source
    assert "launcher.read_result(" not in source
    assert "broker.BrokerOp(" not in source
    assert "if dsn is None:" not in source
    assert "if dsn is not None:" not in source


def test_a_durable_step_still_executes_and_leaves_a_receipt(store):
    """The positive control: the closed seam is still a working seam.

    A refusal proves only that something is refused. This runs the same
    bytes through the same public entry with authority, so a mandate that
    refused everything would fail here rather than look like a fix.
    """
    from settlement import db
    from experiments.ad01 import trajectory

    trajectory.set_namespace_token("")
    cid = trajectory.campaign_id(0, "I", 71)
    allocation_id = trajectory._alloc_id(cid)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    operation_id = "ad01-%s-nodsn-control" % cid

    result = method_exec.run_step_out_of_process(
        STEP_SOURCE, _step_view(), {}, dsn=store,
        allocation_id=allocation_id, operation_id=operation_id)

    assert result["action"]["kind"] == "diagnose"
    assert result["operation_id"] == operation_id
    assert result["operation_ids"] == [operation_id]
    assert result["receipt"]["receipt_identity"]

    with db.connect(store) as conn:
        row = conn.execute(
            "SELECT o.dispatch_state, o.settled, o.allocation_id,"
            " r.receipt_identity FROM operations o"
            " JOIN receipts r ON r.operation_id = o.id"
            " WHERE o.id = %s", (operation_id,)).fetchone()
    assert row is not None
    assert row[0] == "observed"
    assert row[1] is True
    assert row[2] == allocation_id
    assert row[3] == result["receipt"]["receipt_identity"]
