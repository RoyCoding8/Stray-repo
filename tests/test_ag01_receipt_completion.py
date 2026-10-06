import copy

import pytest

from experiments.agenda01.launcher import AgendaProbeLauncher
from settlement import agenda, broker
from settlement.common import CommandResult, ResultCode, SettlementError


def _launch(monkeypatch, code=ResultCode.APPLIED, conflict=False):
    admitted = []

    def accept(dsn, operation_id, receipt):
        admitted.append(receipt)
        return CommandResult(code=code, request_id="receipt", detail="refused",
                             data={"conflict": conflict})

    monkeypatch.setattr(broker, "admit_launcher_receipt", accept)
    launcher = AgendaProbeLauncher("unused", lambda probe, sample, prop:
                                   True if prop == "p0" else None, lambda prop: True)
    operation = broker.BrokerOp(operation_id="op", effect=broker.SANDBOX_EXEC,
        payload={"adapter": "agenda-probe", "input": {
            "attempt_id": "attempt", "probe": "probe", "sample": 0,
            "epoch": 0, "receipt_base": "base", "dep_versions": {"dep": 1},
            "observed": [{"prop": prop, "scope": "scope", "dep": "dep"}
                         for prop in ("p0", "p1")], "product": [], "dud": False}})
    return launcher, operation, admitted


def test_one_final_receipt_completes_multiple_measurements(monkeypatch):
    launcher, operation, admitted = _launch(monkeypatch)
    result = launcher.dispatch(operation)
    assert result.sent is True
    assert [receipt.outcome for receipt in admitted] == ["unknown", "unknown"]
    assert result.receipt.outcome == "success"
    assert result.receipt.receipt_identity == "agenda-final:op"
    assert result.receipt.content["adapter"] == "agenda-probe"
    assert result.receipt.content["resolves_unknowns"] == ["base:p0", "base:p1"]
    assert result.receipt.content["results"] == {
        receipt.receipt_identity: receipt.content for receipt in admitted}
    assert [receipt.content["value"] for receipt in admitted] == ["true", "unknown"]


@pytest.mark.parametrize("code,conflict", [
    (ResultCode.INVALID_INPUT, False), (ResultCode.APPLIED, True)])
def test_rejected_measurement_never_reports_completion(monkeypatch, code, conflict):
    launcher, operation, admitted = _launch(monkeypatch, code, conflict)
    with pytest.raises(SettlementError, match="refused"):
        launcher.dispatch(operation)
    assert len(admitted) == 1
    assert not launcher.prior_send("op")


@pytest.mark.parametrize("tamper", [None, "missing", "operation", "content", "conflict"])
def test_measurement_requires_its_own_intact_completion(monkeypatch, tamper):
    launcher, operation, admitted = _launch(monkeypatch)
    result = launcher.dispatch(operation)
    row = {"operation_id": "op", "content": admitted[0].content}
    final = {"operation_id": "op", "outcome": "success",
             "content": copy.deepcopy(result.receipt.content)}
    if tamper == "operation":
        final["operation_id"] = "other"
    if tamper == "content":
        final["content"]["results"]["base:p0"]["value"] = "false"
    replies = iter([row, None, None if tamper == "missing" else final,
                    {"conflict": True} if tamper == "conflict" else None])

    class Cursor:
        def execute(self, *args):
            pass

        def fetchone(self):
            return next(replies)

    resolve = lambda: agenda._agenda_resolve_receipt(
        Cursor(), {"operation_id": "op", "attempt_id": "attempt"}, "base:p0")
    if tamper is None:
        assert resolve() == (row, row["content"])
    else:
        with pytest.raises(SettlementError, match="completion"):
            resolve()
