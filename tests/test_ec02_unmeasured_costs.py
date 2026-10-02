from experiments.coord02 import entry, schemas_evidence as SE
from settlement import broker


def test_unmeasured_costs_preserve_unknown_and_exact_liability(monkeypatch):
    def usage(dsn, ids):
        if "unknown" in ids:
            raise SE.TrialError("no measured usage")
        return {"in": 7, "out": 11, "calls": 1}

    monkeypatch.setattr(SE, "costs_for_operations", usage)
    costs, liability = entry._cell_costs("unused", {
        name: {"effect": broker.MODEL_INFERENCE}
        for name in ("known", "unknown")}, {})
    assert costs["model_tokens_in"] == SE.UNKNOWN
    assert costs["model_tokens_out"] == SE.UNKNOWN
    assert costs["model_calls"] == SE.UNKNOWN
    assert liability == ["unknown"]


def test_measured_costs_are_preserved(monkeypatch):
    monkeypatch.setattr(SE, "costs_for_operations",
                        lambda dsn, ids: {"in": 7, "out": 11, "calls": 1})
    costs, liability = entry._cell_costs("unused", {
        "known": {"effect": broker.MODEL_INFERENCE}}, {})
    assert costs["model_tokens_in"] == 7
    assert costs["model_tokens_out"] == 11
    assert costs["model_calls"] == 1
    assert liability == []


def test_unknown_model_usage_does_not_hide_known_resource_breaches():
    costs = {"model_calls": SE.UNKNOWN,
             "model_tokens_in": SE.UNKNOWN, "model_tokens_out": SE.UNKNOWN,
             "tool_invocations": 4, "sandbox_ops": 3}
    ceilings = {"model_calls": 1, "input_tokens": 1, "output_tokens": 1,
                "tool_invocations": 2, "sandbox_ops": 2}
    assert entry.check_ceilings(costs, ceilings) == [
        "ceiling-breach-tool_invocations", "ceiling-breach-sandbox_ops"]


def test_measured_zero_is_not_unknown(monkeypatch):
    monkeypatch.setattr(SE, "costs_for_operations",
                        lambda dsn, ids: {"in": 0, "out": 0, "calls": 0})
    costs, liability = entry._cell_costs("unused", {
        "zero": {"effect": broker.MODEL_INFERENCE}}, {})
    assert [costs[key] for key in (
        "model_tokens_in", "model_tokens_out", "model_calls")] == [0, 0, 0]
    assert liability == []
