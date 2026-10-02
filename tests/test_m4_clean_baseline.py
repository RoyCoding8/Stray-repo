"""M4's precondition: a tamper test needs a baseline that passes.

`verify_bundle` reported twenty-nine problems on an untampered bundle, because
the M4 fixtures run the driver with a gateway double that creates no durable
store, so no operation has a durable receipt to join. A baseline that cannot
pass cannot establish that a tamper was detected, which is the precondition the
handoff states. The tamper tests were passing for the wrong reason: each
asserted one problem appeared in a list that was already full of others.

This builds the baseline against a real disposable store, so the receipts exist
because dispatches happened rather than because a fixture wrote them.

The store is real; the transport is a double. `run_output_live` is the live
path's receipt, freeze-validation, settlement and join logic, and all of that
runs against the store, the frozen prompts and the frozen operation ids. What
the double replaces is the one step no test may perform for real: the send. The
rows below were left red because loading `~/.config/agent-society-live.env`
would have made them dispatch against a live model, and that spends real
budget. `run_output_live` now takes the same injected gateway `run_output`
already took, so the properties under test - that dispatches produce receipts,
and that a receipt joins to the operation that produced it - can be exercised
with zero provider spend.

The limit this buys, stated rather than implied: nothing here proves the
provider honours the frozen route or returns what the freeze asked for. The
double supplies that, so a regression in route validation at the provider
boundary, or in `_live_gateway`'s own construction, is outside what these two
rows can see. They prove the live path's bookkeeping; they do not prove the
transport.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest


def _reply_text(prompt: str) -> str:
    """The one legal commit the public view of a task determines.

    The output prompt carries the public task view: the eight observed
    (input, output-vector) pairs and nothing else. For each output bit, the
    class member consistent with all eight is picked here, so the reply is
    derived from what the prompt actually says rather than from the hidden
    tables. Nothing else in the test needs to know the task's answers.
    """
    from experiments.ad01 import boolean_rule as rules
    from experiments.ad01 import live_construct

    task = json.loads(prompt.split("Public task input: ", 1)[1].split(
        ". Permitted history: ", 1)[0])
    rows = task["observed"]

    def pair_index(pair):
        return -1 if pair is None else rules.PAIRS.index(tuple(pair))

    def spec_of(table):
        spec = rules._TABLE_TO_SPEC[table]
        return (spec["const"], spec["mask"], pair_index(spec["pair"]))

    specs = []
    for bit in range(rules.N_OUTPUTS):
        consistent = [
            table for table in rules.CLASS_TABLES
            if all(rules.eval_spec(*spec_of(table), row["x"]) == row["y"][bit]
                   for row in rows)]
        assert consistent, "the public view does not pin output bit %d" % bit
        const, mask, pair = spec_of(consistent[0])
        specs.append({"const": const, "mask": mask,
                      "pair": None if pair == -1 else list(rules.PAIRS[pair])})

    return json.dumps({"specs": specs}, separators=(",", ":"))


class _RecordingGateway:
    """A gateway that records what it was asked and answers from the prompt.

    It is injected, never defaulted: `run_output_live` builds a real
    `HttpGatewayAdapter` when no gateway is passed, so a production caller
    cannot pick this up by accident and no live run can be faked by omitting
    an argument.
    """

    def __init__(self, route: dict):
        self.route = dict(route)
        self.endpoint = self.route["endpoint"]
        self.requests = []
        self.preflights = []

    def preflight_route(self, expected_route):
        """Answer a route preflight by echoing the frozen route back.

        This is the only place a double could hide a route mismatch, so it does
        the strict thing: anything that is not exactly the frozen route comes
        back as the error `preflight_route` already knows how to refuse on.
        """
        from settlement.gateway import GatewayError, GatewayErrorKind

        self.preflights.append(dict(expected_route))
        if expected_route != self.route:
            return GatewayError(
                GatewayErrorKind.PROTOCOL, "recorded route mismatch", False,
                "preflight")
        return dict(expected_route)

    def infer(self, request):
        from settlement.gateway import ModelResponse, Usage

        self.requests.append(request)
        prompt = "".join(
            str(message.get("content", ""))
            for message in request.messages if message.get("role") == "user")
        metadata = {"adapter": "recording-double",
                    "contract": "not-a-provider"}
        for key, value in (("endpoint", self.route["endpoint"]),
                           ("model", self.route["resolved_model"]),
                           ("provider", self.route["provider"]),
                           ("tier", self.route["tier"])):
            metadata[key] = value
        return ModelResponse(
            request.operation_id, _reply_text(prompt), metadata,
            Usage(input_tokens=0, output_tokens=0, charge_units=0,
                  billed=False),
            "stop")

    def check_discovery(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.AUTHENTICATED

    def cancel(self, operation_id):
        return True


def _live_baseline(migrated_db, tmp_path, monkeypatch) -> tuple[dict, dict]:
    """An untampered bundle built by the real live path, so receipts exist."""
    import scripts.invl02_live as driver

    freeze = driver.freeze_output(tmp_path)
    gateway = _RecordingGateway(freeze["route"])
    monkeypatch.setenv("INVL02_LIVE_GRANT", "test")
    monkeypatch.setenv("INVL02_LIVE_MODEL", freeze["route"]["requested_model"])
    driver.preflight_route(tmp_path, gateway=gateway)
    bundle = driver.run_output_live(migrated_db, tmp_path, gateway=gateway)
    private = json.loads((tmp_path / "scorer-private.json").read_text())
    return bundle, private


@pytest.fixture()
def live_store(migrated_db):
    """A store with the r4 study root, provisioned once per test.

    The output study root is fixed, so a second run in the same store sees
    the first run's spent budget and refuses. Each test gets its own.
    """
    return migrated_db


def test_the_live_path_now_dispatches_and_settles(
        live_store, tmp_path, monkeypatch):
    """The output study authorized zero constructions and never dispatched.

    It bound `construction_calls: 0`, which went unenforced, so nothing
    noticed. The ceiling is enforced on the live path now, and it refused the
    first construction. With at least one authorized, the same path settles
    eight receipts.
    """
    bundle, _ = _live_baseline(live_store, tmp_path, monkeypatch)
    receipts = (bundle.get("candidate_view") or {}).get("durable_receipts") or []

    import sys as _s
    v = bundle.get("candidate_view") or {}

    assert bundle.get("status") == "available", (
        "the live path did not complete both arms on both tasks: %s"
        % str(bundle.get("reason") or bundle.get("status"))[:200])
    assert receipts, (
        "the live path produced no durable receipts, so every M4 check that "
        "joins an operation to a receipt is vacuous: %s"
        % str(bundle.get("reason"))[:200])
    assert all(r.get("receipt_outcome") == "success" for r in receipts), (
        "expected settled receipts, got %s"
        % sorted({str(r.get("receipt_outcome")) for r in receipts}))


def test_a_settled_receipt_is_joined_to_its_operation(
        live_store, tmp_path, monkeypatch):
    """The join the verifier performs must find its receipts."""
    from experiments.ad01 import offline_recompute as M4

    bundle, private = _live_baseline(live_store, tmp_path, monkeypatch)
    view = bundle["candidate_view"]
    receipt_ops = {r.get("operation_id") for r in view.get("durable_receipts") or []}

    assert receipt_ops, "no receipts to join"
    verified = M4.verify_bundle(bundle, private)
    durable_problems = [p for p in verified["problems"] if "durable" in p]

    assert not durable_problems or all(
        "unsettled" in p or "unresolved" in p for p in durable_problems), (
        "receipts exist but the join still reports them missing: %s"
        % durable_problems[:4])


def test_the_default_still_builds_a_real_gateway(live_store, tmp_path,
                                                monkeypatch):
    """The seam is opt-in. Omitting the gateway must not yield a double.

    A default that fell back to a recording double would make every production
    caller a fake and leave the whole live path as dead code. This reads the
    default out of the signature rather than calling it, because calling it
    builds a real adapter against a live endpoint and this lane spends nothing.
    """
    import inspect

    import scripts.invl02_live as driver

    parameter = inspect.signature(driver.run_output_live).parameters["gateway"]

    assert parameter.default is None, (
        "run_output_live defaults its gateway to %r; a caller that omits it "
        "would not reach the provider" % (parameter.default,))


def test_the_seam_does_not_bypass_the_route_check(live_store, tmp_path,
                                                  monkeypatch):
    """An injected gateway still has to match the frozen endpoint.

    `run_output_live` reads `gateway.endpoint` and refuses a transport pointing
    somewhere other than the freeze. A double that pointed elsewhere is refused
    for the same reason a live adapter would be, which is what makes this a
    seam in the transport rather than a way around the check.
    """
    import scripts.invl02_live as driver

    freeze = driver.freeze_output(tmp_path)
    gateway = _RecordingGateway(freeze["route"])
    gateway.endpoint = "http://elsewhere.invalid/v1"
    monkeypatch.setenv("INVL02_LIVE_GRANT", "test")
    monkeypatch.setenv("INVL02_LIVE_MODEL", freeze["route"]["requested_model"])
    driver.preflight_route(tmp_path, gateway=_RecordingGateway(freeze["route"]))

    bundle = driver.run_output_live(live_store, tmp_path, gateway=gateway)

    assert bundle["status"] == "unavailable"
    assert "route does not match the freeze" in bundle["reason"], (
        "the mismatched endpoint was not refused by the freeze check, so the "
        "run continued: %s" % bundle["reason"][:200])
    assert "before inference" in bundle["reason"], (
        "the refusal came from a later stage than the endpoint check: %s"
        % bundle["reason"][:200])
    assert gateway.requests == [], "a refused transport was still sent on"


def test_the_seam_does_not_bypass_the_grant(live_store, tmp_path, monkeypatch):
    """`_require_grant` runs before the gateway is ever looked at.

    The seam replaces a transport, not an authority. A caller with no live
    grant must be refused whether it injected a gateway or not, and must be
    refused before the double can record a request.
    """
    import pytest

    import scripts.invl02_live as driver

    freeze = driver.freeze_output(tmp_path)
    gateway = _RecordingGateway(freeze["route"])
    monkeypatch.setenv("INVL02_LIVE_MODEL", freeze["route"]["requested_model"])
    monkeypatch.delenv("INVL02_LIVE_GRANT", raising=False)
    monkeypatch.delenv("S09_M5_LIVE_GRANT", raising=False)
    driver.preflight_route(tmp_path, gateway=_RecordingGateway(freeze["route"]))

    with pytest.raises(ValueError, match="fresh human grant"):
        driver.run_output_live(live_store, tmp_path, gateway=gateway)

    assert gateway.requests == []


def test_the_seam_does_not_bypass_freeze_validation(live_store, tmp_path,
                                                    monkeypatch):
    """The frozen route and the frozen prompts are still the live path's.

    `run_output_live` validates the freeze before it looks at the transport, and
    the requested model must equal the frozen one. Both refusals are properties
    of the run's authority over its own protocol, and neither is the gateway's
    to grant.
    """
    import scripts.invl02_live as driver

    freeze = driver.freeze_output(tmp_path)
    gateway = _RecordingGateway(freeze["route"])
    monkeypatch.setenv("INVL02_LIVE_GRANT", "test")
    monkeypatch.setenv("INVL02_LIVE_MODEL", "a-model-the-freeze-never-asked-for")
    driver.preflight_route(tmp_path, gateway=_RecordingGateway(freeze["route"]))

    with pytest.raises(ValueError, match="does not match the frozen request"):
        driver.run_output_live(live_store, tmp_path, gateway=gateway)

    assert gateway.requests == []


def test_a_route_mismatched_preflight_still_refuses(live_store, tmp_path,
                                                    monkeypatch):
    """The double does not get to vouch for a route it was not asked about.

    `_RecordingGateway.preflight_route` answers with the frozen route only when
    it is asked about exactly that route. Handed a different one it returns the
    error `preflight_route` already knows how to refuse on, so a test cannot
    pass by handing the double a loose route and having it agree.
    """
    import scripts.invl02_live as driver
    from settlement.gateway import GatewayError

    freeze = driver.freeze_output(tmp_path)
    gateway = _RecordingGateway(freeze["route"])
    other = dict(freeze["route"], resolved_model="some/other-model:free")

    answer = gateway.preflight_route(other)

    assert isinstance(answer, GatewayError), answer
    assert driver.preflight_route(tmp_path, gateway=_RecordingGateway(
        freeze["route"]))["route"] == freeze["route"]

