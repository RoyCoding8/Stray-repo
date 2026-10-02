from types import SimpleNamespace

from experiments.coord02 import controller
from experiments.coord02.policy_exec import probe_op_id


def test_probe_uses_admitted_step_identity(monkeypatch):
    seen = []

    def run(dsn, launcher, **kwargs):
        seen.append(probe_op_id(kwargs["run_id"], kwargs["task_id"],
                                kwargs["seq"], kwargs["idx"]))
        return {"observation": {"interface": "public", "result": "failed"}}

    monkeypatch.setattr(controller, "run_probe_call", run)
    cfg = SimpleNamespace(run_id="review", task_id="task", allocation_id="a",
                          source_interfaces={"public": b"source"}, probe_timeout_ms=10)
    result = controller._run_probes(
        "unused", cfg, {"local-process": object()}, {"steps_used": 0},
        {"invocations": [{"interface": "public", "input": {}}]})
    assert result == [{"interface": "public", "result": "failed"}]
    assert seen == ["coord:review:task:step:0000:probe:0"]


def test_child_receives_observed_contents():
    child = {"node_id": "w1", "obligation": "repair", "owned_paths": ["x"],
             "input_bindings": {}, "output_contract": {}}
    observations = [{"interface": "public", "result": {"failed": [3]}}]
    assert controller.render_child_obligation(child, observations)[
        "admitted_observations"] == observations
