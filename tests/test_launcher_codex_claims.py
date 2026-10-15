from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from settlement.broker import AGENT_RUN, BrokerOp
from settlement.launcher_codex import CodexLauncher, Provider


def _launcher(root):
    return CodexLauncher(root, codex_cmd=["unused"],
                         provider=Provider("http://fixture.invalid", "fixture", "fixture"),
                         allowed_overrides=frozenset())


def _operation(generation=1):
    return BrokerOp(operation_id="claim-test", effect=AGENT_RUN,
                    dispatch_generation=generation,
                    payload={"token_ceiling": 100})


@pytest.mark.parametrize("claim", [None, b"{", b'{"generation":1}'])
def test_missing_or_incomplete_claim_cannot_prove_no_dispatch(tmp_path, claim):
    launcher = _launcher(tmp_path)
    operation_dir = tmp_path / "claim-test"
    operation_dir.mkdir()
    if claim is not None:
        (operation_dir / "claim").write_bytes(claim)
    assert launcher.prove_never_sent("claim-test", 1) is False


def test_preflight_owns_dispatch_across_launcher_instances(tmp_path, monkeypatch):
    first, second = _launcher(tmp_path), _launcher(tmp_path)
    entered, release = Event(), Event()
    calls = []

    def preflight(*_):
        entered.set()
        assert release.wait(10)

    def run(*_):
        calls.append("child")
        return {"status": "completed", "tokens": {"input_tokens": 2, "output_tokens": 3},
                "trajectory_digest": "fixture"}

    for launcher in (first, second):
        monkeypatch.setattr(launcher, "model_catalog", lambda: b"{}")
        monkeypatch.setattr(launcher, "_run", run)
    monkeypatch.setattr(first, "isolation_problem", preflight)
    monkeypatch.setattr(second, "isolation_problem", lambda *_: None)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(first.dispatch, _operation())
        try:
            assert entered.wait(10)
            duplicate = second.dispatch(_operation(2))
        finally:
            release.set()
        original = pending.result(timeout=10)

    assert original.sent is True
    assert duplicate.sent is False
    assert calls == ["child"]
    assert first.prove_never_sent("claim-test", 1) is False


def test_explicit_preflight_refusal_proves_only_its_generation(tmp_path, monkeypatch):
    launcher = _launcher(tmp_path)
    monkeypatch.setattr(launcher, "model_catalog", lambda: b"{}")
    monkeypatch.setattr(launcher, "isolation_problem", lambda *_: "fixture refusal")
    result = launcher.dispatch(_operation(4))
    assert result.sent is False
    assert result.refused_reason == "isolation: fixture refusal"
    assert launcher.prove_never_sent("claim-test", 4) is True
    assert launcher.prove_never_sent("claim-test", 3) is False
