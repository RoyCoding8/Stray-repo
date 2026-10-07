"""Real execution authority for a test that runs policy source.

`method_exec.run_step_out_of_process` refuses before it stages a byte unless
`dsn`, `allocation_id` and `operation_id` are all present. That refusal is the
contract (lane A2), so it is not relaxed here or anywhere else in this tree.

The consequence for a test is that a call carrying none of the three measures
the refusal while reading it as a result. Three files hit that shape, and each
had its own answer to it: the string `"assessment-store"`, the string
`"unused-dsn"`, and no argument at all. A string is not a store. The executor
reads it as one, the allocation lookup finds nothing, and the test either
fails at the lookup or, where it catches broadly, never notices that the
policy never ran.

This module is the one answer. `execution_authority` mints a disposable
PostgreSQL store, an allocation the broker knows about, and an operation id,
and drops the store when the caller is done. It follows the shape lane
MIG-MIGRATE used in `tests/test_m1_shared_executor.py`, lifted into one place
because three files need it and three per-file copies are how they drift.

Call sites name the three keywords themselves rather than splatting what this
returns. A splat reads as `arg is None` to the Z2-02a guard, so a test that
forwarded authority through one would be invisible to the very check that
exists to catch an execution with no authority.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "migrations"


@contextlib.contextmanager
def execution_store(token: str, *, sandbox_calls: int = 10_000):
    """Yield `{"dsn", "allocation_id"}` for a whole file's executions.

    The store is created and migrated for the length of the `with` and dropped
    after it, so one file's authority can never be another file's, and a dropped
    store is never a store somebody else still runs on.

    One store serves a whole file rather than one test, because creating a
    database and migrating it is most of the cost and none of the subject.
    `authority_for` names the third key per execution against this one.

    `sandbox_calls` is the ceiling the executor actually draws on, and every
    execution in the file spends from it. It is a ceiling rather than a cost,
    so ordinary steps stay well inside it and a runaway is refused by the
    broker instead of by the test's own patience.
    """
    import isolation_db as isolation
    from settlement import authority

    database = isolation.create_disposable_db(
        token, migrations_dir=MIGRATIONS)
    try:
        handle = authority.authorize_study(
            database.dsn, isolation.study_root_for(token),
            authorized=1_000_000, allocation_id="%s-alloc" % token,
            ceilings={"sandbox_calls": sandbox_calls, "model_calls": 1_000})
        yield {"dsn": database.dsn, "allocation_id": handle.allocation_id}
    finally:
        isolation.drop_disposable_db(database)


def authority_for(store: dict, operation_id: str) -> dict:
    """The three executor keywords for one execution under `store`.

    The executor is idempotent on `operation_id`: a second call with the same
    bytes and the same operation id reads back the first receipt rather than
    executing again. That is what makes a shared store safe here, because a
    repeated measurement of the same bytes under the same view is the same
    execution and should not cost a second child. A caller that wants a second
    execution of the same bytes under a different identity names a different
    `operation_id`.
    """
    return {"dsn": store["dsn"],
            "allocation_id": store["allocation_id"],
            "operation_id": str(operation_id)}


@contextlib.contextmanager
def execution_authority(token: str, *, sandbox_calls: int = 10_000):
    """One store, one allocation and one operation id, for one execution.

    The one-shot form, for a file with a single call. A file with several
    takes `execution_store` once and calls `authority_for` per execution.
    """
    with execution_store(token, sandbox_calls=sandbox_calls) as store:
        yield authority_for(store, "%s-op" % token)


def child_receipt(dsn: str, operation_id: str) -> dict:
    """The record the child settled for one execution, or `{}`.

    Every child failure settles a receipt and the executor then raises one
    message for all of them, so a refusal's text says only that an execution
    failed. What actually happened is here: `data["worker"]["error"]` for a
    child that ran and failed, and `data["timed_out"]` for one the wall clock
    stopped, which is not under `worker` at all. `tests/test_s89a1_contract.py`
    and `tests/test_s09step_arm.py` established the idiom; this is it, in the
    one place every migrated test can reach instead of in each file again.

    Read this while the store is still open. `execution_store` drops the
    database on the way out, so a read after the block is a connection to a
    store that no longer exists.
    """
    from settlement import store

    receipts = store.operation_receipts(dsn, operation_id)
    if len(receipts) != 1:
        return {}
    return dict(receipts[0]["content"].get("data") or {})


def child_error(dsn: str, operation_id: str) -> str:
    """What the child itself reported, for an execution that failed."""
    worker = child_receipt(dsn, operation_id).get("worker") or {}
    return str(worker.get("error", ""))