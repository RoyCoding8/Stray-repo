"""INV-C1 M4: the generated method's return envelope is an explicit contract.

The adapter/executor owns three separate shapes: the outer model JSON
response (entry source plus notes), the generated method's own return
envelope (candidate plus queries used), and the candidate object. The
renderer, parser and executor agree because they read the same contract.
An independently written method (no authored greedy/ddmin wrapper, no
reducers) exercises the actual child process: return envelopes, malformed
results, query exhaustion, current diagnostics and repair feedback.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DSN = os.environ.get(
    "INV_C1_ENV_DSN",
    "dbname=inv_c1_envelope host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

MODEL = "inv-c1-double"
SW0 = "ad01-w0-dev-sw-00"
GR0 = "ad01-w0-dev-gr-00"

ENVELOPE_SW_SOURCE = (
    "def independent_sweep(task, oracle, max_queries=16):\n"
    "    ops = list(task.get(\"ops\", []))\n"
    "    keep = list(range(len(ops)))\n"
    "    first = dict(task)\n"
    "    first[\"ops\"] = [ops[i] for i in keep]\n"
    "    report = oracle.query(first)\n"
    "    if not isinstance(report, dict) or report.get(\"verdict\") "
    "!= \"preserved\":\n"
    "        return {\"candidate\": first, \"queries\": 1}\n"
    "    used = 1\n"
    "    for pos in range(len(keep) - 1, -1, -1):\n"
    "        if used >= max_queries:\n"
    "            break\n"
    "        trial = [i for i in keep if i != pos]\n"
    "        cand = dict(task)\n"
    "        cand[\"ops\"] = [ops[i] for i in trial]\n"
    "        rep = oracle.query(cand)\n"
    "        used = used + 1\n"
    "        if isinstance(rep, dict) and rep.get(\"verdict\") "
    "== \"preserved\":\n"
    "            keep = trial\n"
    "    best = dict(task)\n"
    "    best[\"ops\"] = [ops[i] for i in keep]\n"
    "    return {\"candidate\": best, \"queries\": used}\n"
)

ENVELOPE_GR_SOURCE = (
    "def independent_graph_sweep(task, oracle, max_queries=16):\n"
    "    vertices = list(task.get(\"vertices\", []))\n"
    "    edges = [list(e) for e in task.get(\"edges\", [])]\n"
    "    drop_v = []\n"
    "    drop_e = []\n"
    "    def build():\n"
    "        kept_v = [v for v in vertices if v not in drop_v]\n"
    "        kept = set(kept_v)\n"
    "        kept_e = [e for i, e in enumerate(edges) if i not in "
    "drop_e and e[0] in kept and e[1] in kept]\n"
    "        return {\"family\": \"graph\", \"task_id\": "
    "task.get(\"task_id\"), \"vertices\": kept_v, \"edges\": "
    "kept_e, \"seed\": task.get(\"seed\")}\n"
    "    report = oracle.query(build())\n"
    "    if not isinstance(report, dict) or report.get(\"verdict\") "
    "!= \"preserved\":\n"
    "        return {\"candidate\": build(), \"queries\": 1}\n"
    "    used = 1\n"
    "    for index in range(len(edges)):\n"
    "        if used >= max_queries:\n"
    "            break\n"
    "        drop_e = drop_e + [index]\n"
    "        rep = oracle.query(build())\n"
    "        used = used + 1\n"
    "        if not (isinstance(rep, dict) and rep.get(\"verdict\") "
    "== \"preserved\"):\n"
    "            drop_e = drop_e[:-1]\n"
    "    for vertex in vertices:\n"
    "        if used >= max_queries:\n"
    "            break\n"
    "        drop_v = drop_v + [vertex]\n"
    "        rep = oracle.query(build())\n"
    "        used = used + 1\n"
    "        if not (isinstance(rep, dict) and rep.get(\"verdict\") "
    "== \"preserved\"):\n"
    "            drop_v = drop_v[:-1]\n"
    "    return {\"candidate\": build(), \"queries\": used}\n"
)

MALFORMED_DIRECT_SOURCE = (
    "def malformed_direct(task, oracle, max_queries=16):\n"
    "    return task\n"
)

EXHAUSTING_SOURCE = (
    "def exhausting_probe(task, oracle, max_queries=16):\n"
    "    unknowns = 0\n"
    "    total = max_queries + 3\n"
    "    for pos in range(total):\n"
    "        rep = oracle.query(task)\n"
    "        if isinstance(rep, dict) and rep.get(\"verdict\") "
    "== \"unknown\":\n"
    "            unknowns = unknowns + 1\n"
    "    out = dict(task)\n"
    "    out[\"unknowns_seen\"] = unknowns\n"
    "    return {\"candidate\": out, \"queries\": total}\n"
)


def _fresh_db():
    assert "live" not in DSN
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(DSN, MIGRATIONS)
    E.designate_db(DSN, kind="disposable",
                   purpose="INV-C1 executable interfaces gate")
    E.prepare_disposable_db(DSN, MIGRATIONS)


@pytest.fixture(scope="module")
def authority():
    """Real store, real allocation, one fresh operation id per execution.

    The envelope is a property of what the child does with the bytes, so the
    bytes have to reach a child. Under the durable mandate that takes a
    store, an allocation and an operation id; the fixture holds all three and
    mints a new operation id per call so no test replays another's receipt.
    """
    from experiments.ad01 import method_exec, trajectory
    from experiments.ad01.s09_run_isolation import create_disposable_db, \
        drop_disposable_db

    database = create_disposable_db("invc1-authority",
                                    migrations_dir=MIGRATIONS)
    try:
        trajectory.set_namespace_token("")
        campaign = "invc1-%s" % uuid.uuid4().hex[:8]
        allocation = trajectory.authorize_campaign(
            database.dsn, campaign, authorized=100000)
        counter = {"n": 0}
        last = {"operation_id": ""}

        def run(member: dict, task: dict, **kwargs) -> dict:
            counter["n"] += 1
            last["operation_id"] = "%s-op%d" % (campaign, counter["n"])
            return method_exec.run_member_out_of_process(
                member, task, dsn=database.dsn,
                allocation_id=allocation["allocation_id"],
                operation_id=last["operation_id"], **kwargs)

        yield {"run": run, "dsn": database.dsn,
               "last_operation_id": last}
    finally:
        drop_disposable_db(database)


def _member(source: str, entry: str, family: str) -> dict:
    return {"capability_id": "independent-probe",
            "method_source": source, "entry": entry,
            "params": {"max_queries": 16},
            "scope": {"family": family}, "authored": False}


def test_entry_contract_declares_result_envelope():
    from experiments.ad01 import method_exec
    contract = method_exec.entry_contract()
    envelope = contract["result_envelope"]
    assert envelope["shape"] == {"candidate": "candidate-shaped object",
                                 "queries": "nonnegative integer"}
    assert "candidate-shaped object" in envelope["rule"]
    assert contract["result_envelope"] is not contract["params"]


def test_prompt_renders_envelope_rule_from_contract():
    from experiments.ad01 import method_exec, packet, worlds
    contract = method_exec.entry_contract()
    task = worlds.load_task(worlds.FROZEN_DIR, SW0)
    prompt = packet.render_construction_prompt(
        packet.construction_packet(
            task=task, experience={"observations": []},
            budget={"max_output_tokens": 512}, prior_failure=None))
    assert contract["result_envelope"]["rule"] in prompt
    assert '{"candidate"' in prompt


def test_independent_software_method_through_child_process(authority):
    from experiments.ad01 import method_exec, trajectory
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       SW0)
    result = authority["run"](
        _member(ENVELOPE_SW_SOURCE, "independent_sweep", "software"),
        task, max_queries=16)
    report = trajectory._check(task, result["candidate"])
    assert report["verdict"] == "preserved"
    assert len(result["candidate"]["ops"]) < len(task["ops"])
    assert result["queries"] >= 1


def test_independent_graph_method_through_child_process(authority):
    from experiments.ad01 import method_exec, trajectory
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       GR0)
    result = authority["run"](
        _member(ENVELOPE_GR_SOURCE, "independent_graph_sweep",
                "graph"),
        task, max_queries=16)
    report = trajectory._check(task, result["candidate"])
    assert report["verdict"] == "preserved"
    total = lambda c: len(c["vertices"]) + len(c["edges"])
    assert total(result["candidate"]) < total(task)
    assert result["queries"] >= 1


def test_malformed_envelope_reports_structured_reason(authority):
    """The structured reason now lives in the settled receipt, not the raise.

    Under the durable mandate a member returning the bare task does not fail
    at the parse step. It runs, records a typed child error and settles on
    it, so the executor's own refusal is the generic "no successful
    receipt". The structured reason is therefore read from the receipt the
    operation actually left behind.
    """
    from experiments.ad01 import method_exec, trajectory
    from settlement import store
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       SW0)

    with pytest.raises(method_exec.MethodExecutionError) as excinfo:
        authority["run"](
            _member(MALFORMED_DIRECT_SOURCE, "malformed_direct",
                    "software"),
            task, max_queries=16)

    assert str(excinfo.value) == (
        "refused: durable child operation has no successful receipt")
    receipts = store.operation_receipts(
        authority["dsn"], authority["last_operation_id"]["operation_id"])
    assert len(receipts) == 1
    error = receipts[0]["content"]["data"]["worker"]["error"]
    assert error.startswith("malformed-result-envelope"), error


def test_query_exhaustion_returns_unknown(authority):
    from experiments.ad01 import method_exec, trajectory
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       SW0)
    result = authority["run"](
        _member(EXHAUSTING_SOURCE, "exhausting_probe", "software"),
        task, max_queries=2)
    assert result["candidate"]["unknowns_seen"] == 3
    assert result["queries"] == 2


def test_construction_prompt_carries_diagnostics_and_repair():
    from experiments.ad01 import construct, trajectory
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       SW0)
    diagnostic = {"observation_id": "obs-c4-diagnostic-%s" % SW0,
                  "task_id": SW0, "capability_id": "seed-sw-greedy",
                  "verdict": "diagnostic-vs-nondiagnostic",
                  "detail": {"diagnostic_verdict": "preserved"}}
    failure = {"stage": "parse",
               "reason": "parse-failure: eutactic snippet",
               "operation_id": "op-1"}
    prompt = construct._prompt(
        task, {"observations": [diagnostic]}, {"max_output_tokens": 64},
        failure)
    assert SW0 in prompt
    assert "diagnostic-vs-nondiagnostic" in prompt
    assert "parse-failure: eutactic snippet" in prompt


def test_repair_prompt_reaches_model_request():
    from experiments.ad01 import construct, trajectory
    from test_invc1_lifecycle import ScriptedGateway
    _fresh_db()
    cid = trajectory.campaign_id(0, "I", 61)
    trajectory.authorize_campaign(DSN, trajectory.campaign_id(0, "I", 61),
    authorized=100000)
    trajectory.ensure_campaign(
        DSN, cid, 0, "I", {"objective": "x", "freeze_id": "ad01"},
        {"agenda_authorized": 100000, "max_boundaries": 6,
         "diagnostic_queries": 96},
        tasks=[SW0])
    gateway = ScriptedGateway(
        [], [{"text": "not python {{{"},
             {"text": json.dumps({"entry": ENVELOPE_SW_SOURCE,
                                  "notes": "repaired sweep."})}])
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       SW0)
    diagnostic = {"observation_id": "obs-c4-diagnostic-%s" % SW0,
                  "task_id": SW0, "capability_id": "seed-sw-greedy",
                  "verdict": "diagnostic-vs-nondiagnostic",
                  "detail": {"diagnostic_verdict": "preserved"}}
    member = construct.construct_method(
        DSN, campaign_id=cid, task=task,
        experience={"observations": [diagnostic],
                    "boundary": {"seq": 0}},
        budget={"max_output_tokens": 512, "max_queries": 16,
                "model_calls": 4},
        gateway=gateway, model=MODEL)
    assert member["lineage"]["repair_operation"] is not None
    repair_prompt = gateway.prompts[member["lineage"]["repair_operation"]]
    assert "parse-failure" in repair_prompt
    assert "diagnostic-vs-nondiagnostic" in repair_prompt
    assert member["method_source"] == ENVELOPE_SW_SOURCE
