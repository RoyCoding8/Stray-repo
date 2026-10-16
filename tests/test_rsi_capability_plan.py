from __future__ import annotations

from test_rsi_capability_integration import _genome

from rsi import capability
from settlement import broker, store
from settlement.common import Command
from settlement.launcher_local import LocalLauncher


def _request(value=None):
    return {"interface": "sequence-maximum/1", "value": value or [1, 3, 2],
            "files": {"answer.json": "null"}, "context": {}}


def test_prepared_native_identity_is_effect_free_and_input_bound(tmp_path):
    launcher = LocalLauncher(tmp_path / "native")
    candidate = _genome()
    before = tuple((tmp_path / "native").rglob("*"))
    first = capability.plan_invocation(launcher, candidate, "maximum", _request())
    repeated = capability.plan_invocation(launcher, candidate, "maximum", _request())
    changed = capability.plan_invocation(launcher, candidate, "maximum", _request([4]))
    bounded = capability.plan_invocation(
        launcher, candidate, "maximum", _request(), timeout_ms=1000)

    assert first == repeated
    assert first.execution_version.startswith("cap1-")
    assert len({first.execution_version, changed.execution_version,
                bounded.execution_version}) == 3
    assert first.runtime["python_executable"] == launcher.staged_python()
    assert tuple((tmp_path / "native").rglob("*")) == before


def test_prepared_identity_is_the_actual_native_execution(migrated_db, tmp_path):
    launcher = LocalLauncher(tmp_path / "native")
    candidate = _genome()
    request = _request()
    planned = capability.plan_invocation(launcher, candidate, "maximum", request)
    store.seed_allocation(migrated_db, Command(
        request_id="p06-plan-cpu", payload={"allocation_id": "cpu", "domain": "cpu",
                                          "authorized": 100_000}))

    result = capability.invoke(
        migrated_db, launcher, candidate, "maximum", request,
        operation_id="p06-planned-native", allocation_id="cpu", attempt_id=None,
        staging_root=tmp_path / "stage", artifacts_root=tmp_path / "art")

    assert result.status == "completed"
    assert result.value == 3
    assert result.execution_version == planned.execution_version
    assert broker.read_operation(migrated_db, result.operation_id)[
        "execution_version"] == planned.execution_version
