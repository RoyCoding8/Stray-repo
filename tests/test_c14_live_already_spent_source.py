"""The live paths' already-spent count has no source, and two of three can
have one.

`scripts/invl02_live.py:221 _already_spent` reads
`S09_STUDY_CALLS_ALREADY_SPENT`. Nothing in the repository writes that name:
`_load_live_environment` (line 124) copies four variables out of the
environment file, the allowlist at lines 140-142 does not include it, and
`reports/opus-completion/live-recompute.sh:14` unsets it. The value was
hand-authored from a cap sheet and never moved as sends happened, so a resume
after a crash seeds `already_spent` with what it read before the first send
and `LiveGuard.dispatch_count` starts below the true position. The ceiling was
then enforced against a fiction, which is the same hole `9a1884d` closed in
`s09_study_preflight.already_spent_in_store`.

C14 asks where the count should come from at each of the three call sites. The
answer differs by site, and the difference is structural:

  - `run_e0` (line 2214) and `run_e12` (line 2665) both already hold a `dsn`
    and have already called `_authorize`, which binds a stable
    `allocation_id` to the study root. Every send on these paths goes through
    `_DurableBrokerOutput.infer`, which calls `broker.ensure_operation` with
    that `allocation_id`, and `store.prepare_operation` writes it to
    `operations.allocation_id` (store.py:1507-1512). So a store read is
    available, and the unit it counts in is settled by what the ceiling is a
    ceiling on: all three consumers spend it as model sends. `probe` builds
    `ceiling = already_spent + 1` (line 4368), `run_e0` adds it to
    `freeze["bounds"]["model_calls"]`, and `run_e12` adds it to the per-arm
    `init + repair`. So the query is
    `SELECT COUNT(*) FROM operations WHERE allocation_id = %s AND
    payload->>'effect' = 'model-inference'`, which is the predicate
    `_study_operation_counts` (store.py:1570-1571) charges to `model_calls`.

  - `sandbox_calls` is a different currency over the same allocation, and it
    is not this counter's business. A round now executes under this study's
    own allocation, so a `sandbox-exec` row lands beside the sends
    (`method_exec.py:1174-1176`). Counting it would price one child execution
    as one model call and refuse the live arm's first dispatch. The store
    already separates the two without consulting this function at all:
    `_counters_spent_by` (store.py:1400-1412) charges `sandbox-exec` to
    `sandbox_calls` and `execution_units` and nothing to `model_calls`, and
    `_check_study_ceilings` (store.py:1441-1445) enforces each declared ceiling
    against only the counters its operation moves.

  - `probe` (line 4331) was the exception. It was handed a bare
    `HttpGatewayAdapter`, never a `_DurableBrokerOutput`, so no send on that
    path created an operation row to count. Lane A7 made the probe take the
    same `--dsn` and `--allocation-id` pair the other two sites hold and
    send through the durable gateway, so it is now the third derivation
    rather than the third refusal. It refuses a caller who omits the dsn,
    because a send with no store is a model call that leaves no trace.

So the fix was two derivations and one refusal, and the refusal was the
point: `probe` must not keep reading a number nobody writes. It now reads
the store, and it refuses rather than guessing when it cannot.

All three read the same store, and the narrowing to `effect =
'model-inference'` is the same currency the store itself charges to
`model_calls`. The count is a model-send count on every one of its three
call sites, because every one of them spends it as one.

This file pins the reader census. The derivations themselves are in
`scripts/invl02_live.py` and are exercised by the live paths and by
`tests/test_inv_a7_probe_durable.py`, not here; what is testable offline is
that the dead name is gone, that each derivation reads the store, that the
probe now takes the store it needs, and that the count is a send count which
does not charge a child execution to it.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

import pytest

import worktree_checkouts as checkouts

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from tests.conftest_isolation import admin_dsn, dsn_with_dbname  # noqa: E402

DEAD = "S09_STUDY_CALLS_ALREADY_SPENT"


def _driver() -> ast.Module:
    return ast.parse(
        (ROOT / "scripts/invl02_live.py").read_text(encoding="utf-8"))


def test_the_dead_name_is_gone_from_the_driver() -> None:
    literals = {node.value for node in ast.walk(_driver())
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)}
    assert DEAD not in literals


def test_the_dead_name_is_no_longer_a_reader_anywhere() -> None:
    """No live code path may read it again, in this checkout or any lane's.

    Prose that names the variable as the thing that was removed is kept: the
    preflight's docstring at `s09_study_preflight.py:1228`, the driver's at
    `invl02_live.py:248`, and this lane's own `_already_spent` docstring all
    have to name it to say what they replaced. So the check is for a read, not
    a mention: an `environ.get` or `os.environ` lookup of the name, which is
    the only way a value could reach a ceiling. A census over the tracked
    sources confirms exactly one file carries the name outside a docstring, and
    no subscript read of it exists, so this pattern is the whole reader set.

    `scripts/s09_pilot.py:1101` is that reader. It defaults the name to `"2"`
    rather than zero and is out of C14's scope, which named the e0, frontier
    and probe paths. It is a live-path guard seeded a dispatch count from a
    name nothing writes, so the same hole is open there with a worse default.
    It is recorded in the test rather than fixed, because fixing it is the same
    decision C14 is making and belongs in the same wave.

    The scan resolves its own identity instead of trusting where it was
    invoked. A lane worktree is a copy of this tree, so a `rglob` from
    wherever the file happens to live sees one tree or eleven, and the answer
    would depend on the invocation directory. What makes a file a copy rather
    than a second reader is that its checkout already tracks it, so the reader
    set is this checkout's tracked sources plus each sibling checkout's
    untracked ones. A lane's own edit to a tracked file is reported once under
    its own lane path, and the same edit committed to the repository would be
    reported once under the repository path.
    """
    import re

    reader = re.compile(
        r"""environ\s*\.?\s*(?:\.get\s*\(\s*)?\(?\s*['"]%s['"]"""
        % DEAD)
    canonical = checkouts.canonical_root(ROOT)
    hits: list[tuple[str, int]] = []

    def scan(paths: list[tuple[Path, str]]) -> None:
        for path, key in paths:
            for number, line in enumerate(
                    path.read_text(encoding="utf-8", errors="ignore")
                    .splitlines(), 1):
                if reader.search(line):
                    hits.append((key, number))

    # This checkout's tracked sources, keyed the way the assertion reads.
    scan([(ROOT / name, name)
          for name in checkouts.tracked_paths(canonical, ("*.py",))])

    # A sibling's untracked sources, keyed by their lane-relative path so an
    # untracked reader is never confused with a copy of a tracked file.
    for lane in checkouts.sibling_checkouts(canonical, ROOT):
        prefix = checkouts.label_for(canonical, lane)
        scan([(lane / name, "%s/%s" % (prefix, name))
              for name in checkouts.untracked_paths(
                  canonical, lane, ("*.py",))])

    # Which file still reads the name, and how many places in it, is the
    # claim. The line number is not: this test used to pin
    # `scripts/s09_pilot.py:1101`, and every edit that added a line above the
    # reader moved the number without moving a reader, so an unrelated lane's
    # refactor turned this red over a fact it does not assert. Dropping the
    # number is not dropping the count -- a second reader in the same file is
    # still a moved reader, so a duplicate occurrence still fails. The line
    # numbers are printed in the failure so a real move is one jump away.
    counted = Counter(key for key, _ in hits)
    assert counted == {"scripts/s09_pilot.py": 1}, (
        "the live readers of the dead name moved: %r" % (
            sorted("%s:%d" % pair for pair in hits),))


def test_the_two_store_backed_paths_derive_from_the_allocation() -> None:
    """`run_e0` and `run_e12` hold a dsn and a bound allocation id, so their
    count is the store's operation rows for that allocation."""
    from scripts import invl02_live as driver

    for function in (driver.run_e0, driver.run_e12):
        params = function.__code__.co_varnames[:function.__code__.co_argcount]
        assert params[0] == "dsn", function.__name__


def test_the_authorization_binds_an_allocation_the_store_can_be_read_by() -> None:
    """The derivation is only sound because the id it counts by is durable.

    `_authorize` reaches `trajectory.authorize_campaign`, which reaches
    `authority.authorize_study`, and an existing binding returns the stored
    `allocation_id` rather than minting a new one. A resume therefore counts
    the same rows the first run did.
    """
    import inspect

    from scripts import invl02_live as driver

    assert list(inspect.signature(driver._authorize).parameters) == [
        "dsn", "study_root", "authorized", "ceilings"]


def test_the_probe_path_reads_its_count_from_the_store() -> None:
    """The third site was the exception; it is a derivation now.

    `probe` used to be handed a bare `HttpGatewayAdapter` and seeded
    `already_spent=0`, so its ceiling was enforced against a number nothing
    moved. Lane A7 made the probe send through `_DurableBrokerOutput`, which
    is what admits the operation, so the probe now holds the same pair the
    other two sites hold and reads the same store.
    """
    from scripts import invl02_live as driver

    params = list(driver.probe.__code__.co_varnames
                  [:driver.probe.__code__.co_argcount
                   + driver.probe.__code__.co_kwonlyargcount])
    assert "dsn" in params
    assert "allocation_id" in params


def test_the_probe_verb_refuses_a_caller_with_no_dsn() -> None:
    """Establishing the same fact at the invocation surface, where a caller
    would actually look for the store.

    This test used to read `assert "--dsn" not in block`, and that was a
    statement about the defect rather than about the behavior: any probe
    that had simply not been made durable satisfied it, and the bare send it
    approved left no operation row behind. The durable version is a strictly
    stronger claim. The verb now offers `--dsn`, and a caller who omits it
    is refused rather than silently sending, which is what `probe` itself
    raises on and what `tests/test_inv_a7_probe_durable.py` asserts against a
    real store.
    """
    import inspect

    from scripts import invl02_live as driver

    body = inspect.getsource(driver.main)
    block = body.split('if verb == "probe"')[1].split(
        "return 0 if result.get")[0]
    assert "--dsn" in block
    assert "--allocation-id" in block
    assert "probe(out, read_ms=read_ms, api=api, dsn=dsn" in block
    assert "PROBE_STORE_REFUSAL" in inspect.getsource(driver.probe)


def test_the_probe_ceiling_is_the_stores_count_and_not_a_seed() -> None:
    """A count nobody writes must not decide whether a probe may send.

    `probe` used to build its guard with `ceiling=1, already_spent=0`,
    because there was no durable count to add to. That was the refusal C14
    asked for while the send was bare. Lane A7 gave the probe a store, so
    the probe now reads the store's count and adds the one send it is about
    to make to it. The claim this test carries is unchanged and is about
    the source of the number rather than about its absence: the ceiling is
    built from a store read, and the guard is given that same read as its
    `spend_reader` so it re-asks rather than trusting the seed.
    """
    import inspect

    from scripts import invl02_live as driver

    source = inspect.getsource(driver.probe)
    assert "already_spent = _already_spent(dsn, allocation_id)" in source
    assert "ceiling=already_spent + 1" in source
    assert "dsn=dsn, allocation_id=allocation_id)" in source


DATABASE = "v3_c14_spend_source"
ALLOCATION = "ad01-campaign-invl02-live-e0"


@pytest.fixture()
def dsn():
    """A real store, because the derivation is a query and not a lookup.

    The route resolves here rather than at import: a session with no route
    skips on the refusal instead of failing to collect this file."""
    import psycopg
    from settlement import db

    dsn = dsn_with_dbname(admin_dsn(), DATABASE)
    admin = psycopg.connect(admin_dsn(), autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS %s" % DATABASE)
    admin.execute("CREATE DATABASE %s" % DATABASE)
    admin.close()
    db.apply_migrations(dsn, ROOT / "migrations")
    yield dsn
    admin = psycopg.connect(admin_dsn(), autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS %s" % DATABASE)
    admin.close()


def _payload_for(effect: str) -> dict:
    """A payload the store's own validator accepts, so the row is real."""
    from settlement import broker

    if effect == broker.MODEL_INFERENCE:
        return {"model": "c14-model",
                "messages": [{"role": "user", "content": "c14"}],
                "max_output_tokens": 1, "deadline_ms": 1000}
    if effect == broker.SANDBOX_EXEC:
        return {"profile": "local-process", "argv": ["c14"],
                "timeout_ms": 1000}
    raise ValueError("no seed payload for effect %r" % effect)


def _seed_allocation(store_dsn: str, allocation_id: str) -> None:
    """Seed the allocation once. `seed_allocation` refuses an existing id, and
    a test that mixes two effects under one allocation asks twice."""
    from psycopg.rows import dict_row
    from settlement import db
    from settlement import store as settlement_store
    from settlement.common import Command

    with db.read_connect(store_dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT 1 FROM allocations WHERE id = %s", (allocation_id,))
            present = cur.fetchone() is not None
        conn.commit()
    if present:
        return
    settlement_store.seed_allocation(store_dsn, Command(
        request_id="c14-alloc-%s" % allocation_id,
        payload={"allocation_id": allocation_id, "domain": "study",
                 "authorized": 1000}))


def _operations(store_dsn: str, allocation_id: str, count: int,
                effect: str = "model-inference") -> None:
    """Seed `count` rows the way production writes them.

    `broker.ensure_operation` is the single writer on every path this file
    counts: `_DurableBrokerOutput.infer` calls it for a send
    (invl02_live.py:963) and `method_exec.run_step_out_of_process` calls it for
    a child execution (method_exec.py:1174). It puts `effect` at the top level
    of the envelope that becomes `operations.payload` (broker.py:280,
    store.py:1507-1512).

    The seed used to hand `prepare_operation` a literal `{"effect": "note"}`
    body instead. That put `effect` one level below where the query reads it
    and named an effect `broker.EFFECTS` does not contain. It passed because
    the query it was checking had no predicate to disagree with, so the
    fixture asserted a number the reader arrived at for an unrelated reason.
    Going through the production entry point makes that drift unreachable
    rather than corrected once.
    """
    from settlement import broker

    _seed_allocation(store_dsn, allocation_id)
    for index in range(count):
        broker.ensure_operation(
            store_dsn,
            operation_id="op-%s-%s-%d" % (allocation_id, effect, index),
            effect=effect, payload=_payload_for(effect),
            allocation_id=allocation_id, retries=0)


def _every_row(store_dsn: str, allocation_id: str) -> int:
    """Every row under the allocation, whatever its effect.

    `_already_spent` deliberately does not read this. It is here so the test
    that excludes a child execution can prove the row it excludes is really
    there, under this allocation, rather than absent for some other reason.
    """
    from settlement import db
    from psycopg.rows import dict_row

    with db.read_connect(store_dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT COUNT(*) AS rows FROM operations WHERE allocation_id"
                " = %s", (allocation_id,))
            total = cur.fetchone()["rows"]
        conn.commit()
    return int(total)


def test_the_count_is_the_stores_and_not_a_declaration(dsn) -> None:
    from scripts import invl02_live as driver

    _operations(dsn, ALLOCATION, 3)

    assert driver._already_spent(dsn, ALLOCATION) == 3


def test_a_child_execution_is_not_counted_as_a_model_send(dsn) -> None:
    """The ceiling this count feeds is a model-send ceiling, and a round now
    executes under this same allocation, so a `sandbox-exec` row lands beside
    the sends. Counting it would price one child execution as one model call.

    This is the narrowing's whole claim, so the test carries both halves. The
    three sends are counted and the four child executions are not, and the
    unscoped count says all seven rows are on this allocation, so the
    exclusion is the predicate's doing and not the rows having gone missing.
    """
    from scripts import invl02_live as driver

    _operations(dsn, ALLOCATION, 3, effect="model-inference")
    _operations(dsn, ALLOCATION, 4, effect="sandbox-exec")

    assert _every_row(dsn, ALLOCATION) == 7
    assert driver._already_spent(dsn, ALLOCATION) == 3


def test_another_studys_rows_are_not_counted(dsn) -> None:
    """The allocation scopes the count. An unscoped `COUNT(*)` would read a
    shared study cluster's whole history as this study's spend and refuse
    every send."""
    from scripts import invl02_live as driver

    _operations(dsn, ALLOCATION, 3)
    _operations(dsn, "ad01-campaign-some-other-study", 7)

    assert driver._already_spent(dsn, ALLOCATION) == 3


def test_an_empty_store_spends_nothing(dsn) -> None:
    from scripts import invl02_live as driver

    assert driver._already_spent(dsn, ALLOCATION) == 0


def test_an_unreadable_store_refuses_rather_than_reporting_zero() -> None:
    """A zero here is indistinguishable from a genuine no-spend, which is the
    hole the preflight's `None` avoids."""
    from scripts import invl02_live as driver

    with pytest.raises(ValueError, match="was not readable"):
        driver._already_spent(
            dsn_with_dbname(admin_dsn(), "v3_c14_absent"), ALLOCATION)


def test_the_env_var_could_not_have_produced_that_number(dsn, monkeypatch) -> None:
    """The defect stated as a pair: the declaration says zero, the store says
    three, and only the store moves the ceiling."""
    from scripts import invl02_live as driver

    monkeypatch.setenv(DEAD, "0")
    _operations(dsn, ALLOCATION, 3)

    assert driver._already_spent(dsn, ALLOCATION) == 3
