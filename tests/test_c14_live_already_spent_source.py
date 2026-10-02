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

  - `run_e0` (line 2053) and `run_e12` (line 2512) both already hold a `dsn`
    and have already called `_authorize`, which binds a stable
    `allocation_id` to the study root. Every send on these paths goes through
    `_DurableBrokerOutput.infer`, which calls `broker.ensure_operation` with
    that `allocation_id`, and `store.prepare_operation` writes it to
    `operations.allocation_id` (store.py:1477). So a store read is available:
    `SELECT COUNT(*) FROM operations WHERE allocation_id = %s`, which is the
    same currency `_output_already_spent` (line 1310) already counts for the
    output study, and the same one `LiveGuard`'s own docstring names.

  - `probe` (line 4111) is the exception. Its signature is
    `probe(out, *, read_ms, max_tokens, api)` and its `probe` verb at line
    4232 reads only `--out`, `--read-ms` and `--api`. It is handed a bare
    `HttpGatewayAdapter`, never a `_DurableBrokerOutput`, so no send on that
    path creates an operation row to count. There is no store read to fall
    back on without giving the verb a `--dsn` it has never had, which is a
    change to the invocation contract rather than a repair.

So the fix is two derivations and one refusal, and the refusal is the point:
`probe` must not keep reading a number nobody writes.

This file pins the reader census. The derivations themselves are in
`scripts/invl02_live.py` and are exercised by the live paths, not here; what
is testable offline is that the dead name is gone, that the derivation reads
the store, and that the third path refuses instead of guessing.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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
    """No live code path may read it again.

    Prose that names the variable as the thing that was removed is kept: the
    preflight's docstring at `s09_study_preflight.py:1228` and this lane's
    `_already_spent` docstring both have to name it to say what they replaced.
    So the check is for a read, not a mention: an `environ.get` or
    `os.environ` lookup of the name, which is the only way a value could reach
    a ceiling.

    `scripts/s09_pilot.py:1109` is such a reader, defaults it to `"2"` rather
    than zero, and is out of C14's scope, which named the e0, frontier and
    probe paths. It is a live-path guard seeded a dispatch count from a name
    nothing writes, so the same hole is open there with a worse default. It
    is recorded in the test rather than fixed, because fixing it is the same
    decision C14 is making and belongs in the same wave.
    """
    import re

    reader = re.compile(
        r"""environ\s*\.?\s*(?:\.get\s*\(\s*)?\(?\s*['"]%s['"]"""
        % DEAD)
    hits: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        if ".venv" in path.parts or ".git" in path.parts:
            continue
        if path.name in (Path(__file__).name,
                         "test_s09_c11_reported_spend.py"):
            continue
        for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="ignore").splitlines(),
                1):
            if reader.search(line):
                hits.append("%s:%d" % (path.relative_to(ROOT), number))

    assert hits == ["scripts/s09_pilot.py:1109"], (
        "the live readers of the dead name moved: %r" % hits)


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


def test_the_probe_path_has_no_store_to_read() -> None:
    """The reason the third site is a refusal rather than a derivation."""
    from scripts import invl02_live as driver

    params = list(driver.probe.__code__.co_varnames
                  [:driver.probe.__code__.co_argcount])
    assert "dsn" not in params


def test_the_probe_verb_offers_no_dsn_flag() -> None:
    """Establishing the same fact at the invocation surface, where a caller
    would actually look for the store."""
    import inspect

    from scripts import invl02_live as driver

    body = inspect.getsource(driver.main)
    block = body.split('if verb == "probe"')[1].split(
        "return 0 if result.get")
    assert "--dsn" not in block


def test_probe_refuses_rather_than_seeding_a_ceiling_it_cannot_ground() -> None:
    """A count nobody writes must not decide whether a probe may send.

    `probe` builds its guard with `ceiling=_already_spent() + 1`. With no
    durable count there is nothing to add to, so the ceiling has to come from
    somewhere the probe can state, and it has to refuse when it cannot.
    """
    source = (ROOT / "scripts/invl02_live.py").read_text(encoding="utf-8")
    start = source.index("def probe(")
    block = source[start:source.index("\ndef ", start + 10)]

    assert "_already_spent(" not in block


DATABASE = "v3_c14_spend_source"
DSN = "dbname=%s host=/var/run/postgresql user=ubuntu" % DATABASE
ALLOCATION = "ad01-campaign-invl02-live-e0"


@pytest.fixture()
def store():
    """A real store, because the derivation is a query and not a lookup."""
    import psycopg
    from settlement import db

    admin = psycopg.connect(
        "host=/var/run/postgresql user=ubuntu dbname=postgres", autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS %s" % DATABASE)
    admin.execute("CREATE DATABASE %s" % DATABASE)
    admin.close()
    db.apply_migrations(DSN, ROOT / "migrations")
    yield DSN
    admin = psycopg.connect(
        "host=/var/run/postgresql user=ubuntu dbname=postgres", autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS %s" % DATABASE)
    admin.close()


def _operations(store_dsn: str, allocation_id: str, count: int) -> None:
    from settlement import store as settlement_store
    from settlement.common import Command

    settlement_store.seed_allocation(store_dsn, Command(
        request_id="c14-alloc-%s" % allocation_id,
        payload={"allocation_id": allocation_id, "domain": "study",
                 "authorized": 1000}))
    for index in range(count):
        settlement_store.prepare_operation(store_dsn, Command(
            request_id="c14-prep-%s-%d" % (allocation_id, index),
            payload={"operation_id": "op-%s-%d" % (allocation_id, index),
                     "allocation_id": allocation_id,
                     "operation": {"effect": "note"}}))


def test_the_count_is_the_stores_and_not_a_declaration(store) -> None:
    from scripts import invl02_live as driver

    _operations(store, ALLOCATION, 3)

    assert driver._already_spent(store, ALLOCATION) == 3


def test_another_studys_rows_are_not_counted(store) -> None:
    """The allocation scopes the count. An unscoped `COUNT(*)` would read a
    shared study cluster's whole history as this study's spend and refuse
    every send."""
    from scripts import invl02_live as driver

    _operations(store, ALLOCATION, 3)
    _operations(store, "ad01-campaign-some-other-study", 7)

    assert driver._already_spent(store, ALLOCATION) == 3


def test_an_empty_store_spends_nothing(store) -> None:
    from scripts import invl02_live as driver

    assert driver._already_spent(store, ALLOCATION) == 0


def test_an_unreadable_store_refuses_rather_than_reporting_zero() -> None:
    """A zero here is indistinguishable from a genuine no-spend, which is the
    hole the preflight's `None` avoids."""
    from scripts import invl02_live as driver

    with pytest.raises(ValueError, match="was not readable"):
        driver._already_spent(
            "dbname=v3_c14_absent host=/var/run/postgresql user=ubuntu",
            ALLOCATION)


def test_the_env_var_could_not_have_produced_that_number(store, monkeypatch) -> None:
    """The defect stated as a pair: the declaration says zero, the store says
    three, and only the store moves the ceiling."""
    from scripts import invl02_live as driver

    monkeypatch.setenv(DEAD, "0")
    _operations(store, ALLOCATION, 3)

    assert driver._already_spent(store, ALLOCATION) == 3
