"""A frozen send ceiling must bind the path a live dispatch actually takes.

`study_authority.ceilings` is written at authorization and read by
`store.admit_study_operation`, whose only caller is
`authority.admit_study_call`. No live dispatch reaches that. Every send goes
through `broker.ensure_operation` into `store.prepare_operation`, which binds
the study root and then never consults a ceiling. A study that authorizes one
send and dispatches two is refused nowhere, which is the r4 overrun with the
checking machinery in place and pointed at the wrong layer.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from settlement import authority, store
from settlement.common import Command, ResultCode


STUDY_ROOT = "ceiling-live-path"
CEILING = 2


@pytest.fixture()
def authorized(migrated_db):
    authority.authorize_study(migrated_db, STUDY_ROOT, authorized=10_000_000,
                              ceilings={"model_calls": CEILING})
    return migrated_db


def _send(dsn, index: int) -> Command:
    return store.prepare_operation(dsn, Command(
        request_id="ceiling-%d" % index,
        payload={"operation_id": "ceil-op-%d" % index,
                 "attempt_id": None,
                 "allocation_id": STUDY_ROOT,
                 "reservation_id": None,
                 "exposure": 0,
                 "operation": {"effect": "model-inference",
                               "study_root": STUDY_ROOT,
                               "payload": {"model": "m"}}}))


def test_a_send_over_the_study_ceiling_is_refused(authorized):
    """The live admission path must honour the ceiling the study froze."""
    results = [_send(authorized, index) for index in range(1, CEILING + 2)]

    assert all(r.code is ResultCode.APPLIED for r in results[:CEILING]), (
        "the first %d sends were not admitted: %r"
        % (CEILING, [str(r) for r in results[:CEILING]]))

    over = results[CEILING]
    assert over.code is not ResultCode.APPLIED, (
        "a send past a ceiling of %d was admitted: %s"
        % (CEILING, over.detail or over.code))
    assert "ceiling" in str(over.detail or "").lower()


def test_the_ceiling_is_refused_before_the_reservation_is_taken(authorized):
    """An over-ceiling send must not also spend its exposure."""
    for index in range(1, CEILING + 1):
        assert _send(authorized, index).code is ResultCode.APPLIED

    over = _send(authorized, CEILING + 1)

    assert over.code is not ResultCode.APPLIED


def test_a_declared_only_ceiling_does_not_refuse_a_send(authorized):
    """`authorize_study` accepts ceilings this layer does not count.

    A wall deadline or a witness-query budget is recorded and not enforced by
    design. The live check must skip those rather than raise, because a study
    that declares one is legally authorized and raising here would break every
    such study at its first dispatch.
    """
    from settlement import authority

    authority.authorize_study(
        authorized, "ceiling-declared-only", authorized=1_000_000,
        ceilings={"max_boundaries": 4, "max_witness_queries": 960,
                  "max_model_calls": 10})

    result = store.prepare_operation(authorized, Command(
        request_id="declared-only-1",
        payload={"operation_id": "decl-op-1", "attempt_id": None,
                 "allocation_id": "ceiling-declared-only",
                 "reservation_id": None, "exposure": 0,
                 "operation": {"effect": "model-inference",
                               "study_root": "ceiling-declared-only",
                               "payload": {"model": "m"}}}))

    assert result.code is ResultCode.APPLIED, (
        "a declared-only ceiling refused a legal send: %s" % result.detail)
