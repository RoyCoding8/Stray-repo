"""The public use path never turns source bytes into a host callable."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from execution_authority import execution_authority

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def _view():
    from experiments.ad01 import policy_step

    return policy_step.materialize_view(
        task={"task_id": "s09c-policy", "family": "software",
              "template": "line", "ops": []},
        observations=[], open_questions=[], last_result=None,
        eligible_methods=["seed-sw-greedy"], remaining={})


def _source():
    return (
        "def STEP(view, state):\n"
        "    return {'action': {'kind': 'stop',\n"
        "                      'target': view['task_content']['task_id'],\n"
        "                      'inputs': {'reason': 'done'},\n"
        "                      'evidence_refs': [],\n"
        "                      'requested_resources': {}},\n"
        "            'state': state}\n")


def test_compile_step_does_not_execute_module_top_level():
    """The compatibility callable defers source execution to the child."""
    from experiments.ad01 import policy_step

    source = "raise RuntimeError('host execution')\n" + _source()
    policy = policy_step.compile_step(source, origin="<s09c-top-level>")

    assert isinstance(policy, policy_step.BoundedPolicy)
    with pytest.raises(ValueError):
        policy(_view(), {})


def _child_receipt(dsn: str, operation_id: str) -> dict:
    """The launcher's own record of one execution, read back from the store.

    An execution that fails settles a receipt and the executor refuses with one
    message every failure produces, so the refusal says only that the execution
    failed. Whether it was a wall timeout is in the receipt the child settled,
    and asserting on that is an assertion about the bound rather than about the
    executor's wording. `test_s89a1_contract.py` established the idiom.
    """
    from settlement import store

    receipts = store.operation_receipts(dsn, operation_id)
    assert len(receipts) == 1, receipts
    return dict(receipts[0]["content"]["data"])


def test_real_child_timeout_is_a_refusal():
    """A policy that will not return is killed, and the step is refused.

    A 100ms wall limit against a policy that spins forever. The child is
    killed and the receipt says so with its timeout flag set, which is what
    distinguishes this from the CPU bound: a wall timeout is elapsed time, so
    it fires on a child that is not spending the budget.
    """
    from experiments.ad01 import method_exec, policy_step

    source = (
        "def STEP(view, state):\n"
        "    while True:\n"
        "        pass\n")
    record = policy_step.make_policy_artifact(
        source, origin="fixture-stand-in")
    with execution_authority("s09ctimeout") as auth:
        with pytest.raises(method_exec.MethodExecutionError):
            policy_step.run_policy_step(
                record, _view(), {}, timeout_ms=100, cpu_seconds=1,
                dsn=auth["dsn"], allocation_id=auth["allocation_id"],
                operation_id=auth["operation_id"])
        settled = _child_receipt(auth["dsn"], auth["operation_id"])

    assert settled["timed_out"] is True, settled


def test_source_use_requires_allocation_before_policy_child(monkeypatch):
    from experiments.ad01 import policy_step, trajectory

    called = []

    def forbidden(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("policy child must not run without allocation")

    monkeypatch.setattr(policy_step, "run_policy_step", forbidden)
    repertoire = {
        "campaign_id": "s09c-missing-allocation",
        "members": [{"capability_id": "seed-sw-greedy",
                     "scope": {"family": "software"}, "authored": True}],
    }
    with pytest.raises(ValueError, match="explicit execution allocation"):
        trajectory.run_use(
            repertoire, 0, "I", ["ad01-w0-within-sw-00"], {},
            policy_source=_source(), dsn="unused-dsn")
    assert called == []


def test_fresh_process_rehydrates_source_digest_and_receipt(tmp_path):
    source_path = tmp_path / "policy.py"
    source_path.write_text(_source(), encoding="utf-8")
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import hashlib, json, sys\n"
        "from experiments.ad01 import policy_step\n"
        "source = open(sys.argv[1], encoding='utf-8').read()\n"
        "record = policy_step.make_policy_artifact(source, "
        "origin='authored-control')\n"
        "view = policy_step.materialize_view("
        "task={'task_id':'s09c-policy','family':'software',"
        "'template':'line','ops':[]}, observations=[], "
        "open_questions=[], last_result=None, "
        "eligible_methods=['seed-sw-greedy'], remaining={})\n"
        "stepped = policy_step.run_policy_step(record, view, {}, "
        "dsn=sys.argv[2], allocation_id=sys.argv[3], "
        "operation_id=sys.argv[4])\n"
        "print(json.dumps({'digest': stepped['source_digest'], "
        "'receipt': stepped['receipt']['receipt_identity'], "
        "'kind': stepped['action']['kind']}))\n",
        encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(ROOT / "src"), env.get("PYTHONPATH", "")])
    with execution_authority("s09cprobe") as auth:
        result = subprocess.run(
            [sys.executable, str(probe), str(source_path), auth["dsn"],
             auth["allocation_id"], auth["operation_id"]],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
            env=env)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["digest"] == hashlib.sha256(
        _source().encode("utf-8")).hexdigest()
    assert payload["kind"] == "stop"
    assert payload["receipt"]
