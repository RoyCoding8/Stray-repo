"""coord02 learning path tests (lane L, EC02 design sections 6-7).

Real PostgreSQL (ec02test_l) + real subprocesses throughout. No live model
calls exist in this environment (no TEAM01_LIVE_API_KEY; unauthenticated
inference is rejected), so construction is routed through the broker against
the FakeGatewayAdapter and every such run is labeled DOUBLED. The 4 live
construction calls + G2 acquisition await the grant.

Authored stand-in packages below are labeled construction-path tests only
(DOUBLED_* names + doubled labels); they are never acquisition evidence.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

from experiments.coord02 import experience as E
from experiments.coord02 import freeze as F
from experiments.coord02 import oracle
from experiments.coord02.controller import (
    load_frozen_package,
    seed_episode,
)
from settlement import broker, capabilities, db
from settlement.common import Command, ResultCode
from settlement.gateway import FakeGatewayAdapter
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get("EC02_L_DSN",
                     "dbname=ec02test_l host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"

DOUBLED_SINGLE_TEST = ("\n".join([
    "import json",
    "import sys",
    "if len(sys.argv) == 2 and sys.argv[1] == '--selftest':",
    "    raise SystemExit(0)",
    "req = json.load(open(sys.argv[1]))",
    "paths = sorted(req['task']['task_snapshot'].keys())",
    "plan = {'action': 'plan', 'shape': 'single', 'children': [{",
    "  'node_id': 'w1',",
    "  'obligation': 'DOUBLED stand-in: apply valid reference tree',",
    "  'owned_paths': paths,",
    "  'output_contract': {'entry': 'whole-tree', 'checks': ['public']},",
    "  'input_bindings': {'base_%d' % i: p",
    "                     for i, p in enumerate(paths)}}]}",
    "resp = {'profile': req['profile'],",
    "        'profile_version': req['profile_version'],",
    "        'decision_id': req['decision_id'],",
    "        'package_digest': req['package_digest'],",
    "        'source_digest': req['source_digest'],",
    "        'plan_revision': req['plan_revision'],",
    "        'phase': req['phase'], 'proposal': plan, 'state': {}}",
    "json.dump(resp, open(sys.argv[2], 'w'))",
    ""]) + "\n").encode()

DOUBLED_STOP_TEST = ("\n".join([
    "import json",
    "import sys",
    "if len(sys.argv) == 2 and sys.argv[1] == '--selftest':",
    "    raise SystemExit(0)",
    "req = json.load(open(sys.argv[1]))",
    "resp = {'profile': req['profile'],",
    "        'profile_version': req['profile_version'],",
    "        'decision_id': req['decision_id'],",
    "        'package_digest': req['package_digest'],",
    "        'source_digest': req['source_digest'],",
    "        'plan_revision': req['plan_revision'],",
    "        'phase': req['phase'],",
    "        'proposal': {'action': 'stop',",
    "                   'reason': 'DOUBLED stand-in: decline'},",
    "        'state': {}}",
    "json.dump(resp, open(sys.argv[2], 'w'))",
    ""]) + "\n").encode()


@pytest.fixture()
def dsn():
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{row[0]}" CASCADE')
        conn.commit()
    for stale in Path("/tmp").glob("coord02-L-test-*"):
        shutil.rmtree(stale, ignore_errors=True)
    return DSN


def _tag(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _factory(root: Path):
    def _make(tag: str) -> dict:
        return {"local-process": LocalLauncher(root / tag)}
    return _make


def _fresh_dirs(root: Path, name: str) -> dict:
    out = {"runs": root / f"coord02-L-test-{name}-runs",
           "staging": root / f"coord02-L-test-{name}-staging",
           "artifacts": root / f"coord02-L-test-{name}-art"}
    for path in out.values():
        path.mkdir(parents=True, exist_ok=True)
    return out


def _requires(task_id: str) -> dict:
    return E._requires_for(task_id, E.snapshot_files(task_id))


def test_no_live_grant_in_env():
    assert "TEAM01_LIVE_API_KEY" not in os.environ
    assert E.preflight_live() == {
        "live_grant": False,
        "reason": "no TEAM01_LIVE_API_KEY: 4 live construction calls + "
                  "G2 acquisition blocked; doubled path only"}
    assert E.construction_budget()["label"] == "DOUBLED"
    assert E.construction_budget()["live_calls_used"] == 0
    assert E.construction_budget()["live_calls_authorized"] == 4


def test_experience_packet_from_real_episodes(dsn, tmp_path):
    episodes = E.acquire_episodes(
        dsn, tmp_path, task_ids=["c02-t16", "c02-t01"],
        launcher_factory=_factory(tmp_path),
        constructor=E.dev_constructor("c02-t16", solved=True))
    assert len(episodes) == 2
    for made in episodes:
        packet = made["packet"]
        assert packet["packet_version"] == "coord02-experience/1"
        assert packet["task_id"] == made["task_id"]
        assert packet["run_id"] == made["episode"]["run_id"]
        assert set(("task_snapshot", "interface_contract",
                    "snapshot_digest")) <= set(
            packet["versioned_inputs"])
        assert len(packet["decisions"]) >= 1
        assert len(packet["probe_observations"]) >= 1
        assert len(packet["executed_operations"]) >= 1
        assert set(("model_calls", "source_invocations",
                    "sandbox_operations")) <= set(packet["cost"])
        assert packet["cost"]["unknown"]
        transport = packet["probe_observations"][0]
        assert transport["interface"] == "observe-broken"
        assert "reference" not in json.dumps(
            packet["development_observations"] if
            "development_observations" in packet else []).lower()


def test_construction_call_ceiling(dsn, tmp_path):
    budget = E.construction_budget()
    seed = E.seed_construction_campaign(dsn, _tag("ledger"), budget)
    ledger = E.ConstructionLedger(dsn, seed["allocation_id"])
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    gateway = FakeGatewayAdapter(text=json.dumps({"entry": "x = 1\n"}))
    init_ops = []
    for lineage in (1, 2):
        rec = ledger.request_call(
            E.construction_request(packet, budget, lineage=lineage,
                                   attempt="init"), gateway=gateway)
        init_ops.append(rec["operation_id"])
    for lineage, op_id in zip((1, 2), init_ops):
        prior = {"kind": "empty", "reason": "empty-response",
                 "operation_id": op_id}
        ledger.repair_call(packet, budget, lineage=lineage,
                           prior_failure=prior, gateway=gateway)
    assert ledger.calls_used() == 4
    assert ledger.remaining() == 0
    with pytest.raises(E.ConstructionBudgetExhausted):
        ledger.request_call(
            E.construction_request(packet, budget, lineage=1,
                                   attempt="init"), gateway=gateway)
    assert ledger.refused == 1
    assert ledger.accounting()["live_calls_used"] == 0
    assert ledger.accounting()["live_calls_authorized"] == 4
    assert all(c["label"] == "DOUBLED" and c["doubled"]
               and not c["live"] for c in ledger.calls)
    assert len({c["operation_id"] for c in ledger.calls}) == 4
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM operations WHERE id LIKE %s",
                        (f"{ledger.attempt_prefix}%",))
            assert int(cur.fetchone()[0]) == 4
            conn.commit()


def test_empty_response_kept_and_counted(dsn, tmp_path):
    budget = E.construction_budget()
    seed = E.seed_construction_campaign(dsn, _tag("ledger"), budget)
    ledger = E.ConstructionLedger(dsn, seed["allocation_id"])
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    empty = ledger.request_call(
        E.construction_request(packet, budget, lineage=1, attempt="init"),
        gateway=FakeGatewayAdapter(text=""))
    kept = E.keep_response(empty)
    assert kept["kept"] is True
    assert kept["usable"] is False
    assert kept["reason"] == "empty-response"
    assert kept["entry_bytes"] == b""
    assert kept["label"] == "DOUBLED" and kept["doubled"]
    assert not kept["live"]
    assert ledger.calls_used() == 1
    assert E.parse_candidate(kept["entry_bytes"]) == {
        "ok": False, "reason": "empty-response"}
    bad = ledger.request_call(
        E.construction_request(packet, budget, lineage=2, attempt="init"),
        gateway=FakeGatewayAdapter(text="not json at all"))
    kept_bad = E.keep_response(bad)
    assert kept_bad["kept"] is True and not kept_bad["usable"]
    assert kept_bad["response_bytes"] == b"not json at all"


def test_repair_after_protected_feedback_impossible(dsn, tmp_path):
    seed = E.seed_construction_campaign(dsn, _tag("ledger"),
                                        E.construction_budget())
    ledger = E.ConstructionLedger(dsn, seed["allocation_id"])
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    budget = E.construction_budget()
    ledger.request_call(
        E.construction_request(packet, budget, lineage=1, attempt="init"),
        gateway=FakeGatewayAdapter(text=""))
    with pytest.raises(Exception, match="protected-feedback"):
        ledger.repair_call(
            packet, budget, lineage=1,
            prior_failure={"kind": "parse", "reason": "see protected_cases",
                           "operation_id": "op"},
            gateway=FakeGatewayAdapter(text="x"))
    assert ledger.calls_used() == 1
    with pytest.raises(Exception, match="protected-feedback"):
        E.construction_request(packet, budget, lineage=1, attempt="repair",
                               prior_failure={"detail": "oracle.py says"})
    with pytest.raises(Exception, match="prior failure"):
        E.construction_request(packet, budget, lineage=1,
                               attempt="repair", prior_failure=None)


def test_stage_gate_strict_parse_stage_check(dsn, tmp_path):
    dirs = _fresh_dirs(tmp_path, "gate")
    launcher = LocalLauncher(dirs["runs"])
    seed = seed_episode(dsn, _tag("gate"), {"m": "1"})
    parsed = E.stage_gate(
        dsn, dirs["staging"], dirs["artifacts"],
        entry_bytes=b"def broken(((", requires={},
        version_id=f"coord02-L-gate-{_tag('v')}", launcher=launcher,
        allocation_id=seed["allocation_id"])
    assert parsed == {"stage": "parse", "ok": False,
                      "reason": parsed["reason"]}
    assert parsed["reason"]
    good = E.stage_gate(
        dsn, dirs["staging"], dirs["artifacts"],
        entry_bytes=DOUBLED_SINGLE_TEST, requires={},
        version_id=f"coord02-L-gate-{_tag('v')}", launcher=launcher,
        allocation_id=seed["allocation_id"],
        description="DOUBLED construction-path test stand-in")
    assert good["stage"] == "select" and good["ok"] is True
    loaded = load_frozen_package(dsn, dirs["artifacts"],
                                 good["version_id"])
    assert loaded["entry_bytes"] == DOUBLED_SINGLE_TEST
    assert good["receipt"]["construction_label"] == "DOUBLED"


def test_selection_ordering_and_none_path(dsn, tmp_path):
    factory = _factory(tmp_path)
    entry_good = DOUBLED_SINGLE_TEST
    entry_bad = DOUBLED_STOP_TEST
    requires = _requires("c02-t16")
    tasks = ["c02-t16", "c02-t01"]
    good = E.validate_on_development(
        dsn, entry_bytes=entry_good, requires=requires, task_ids=tasks,
        launcher_factory=factory,
        constructor=E.dev_constructor("c02-t16", solved=True))
    assert good["valid_execution"] is True
    assert good["solved_count"] >= 1
    assert good["solved_tasks"] and good["executed"] == tasks
    bad = E.validate_on_development(
        dsn, entry_bytes=entry_bad, requires=requires, task_ids=tasks,
        launcher_factory=factory,
        constructor=E.dev_constructor("c02-t16", solved=True))
    assert bad["valid_execution"] is False
    assert bad["solved_count"] == 0
    assert bad["fallback_tasks"] == []
    picked = E.select_candidate(
        [{"lineage": 1, "validation": bad, "entry_bytes": entry_bad},
         {"lineage": 2, "validation": good, "entry_bytes": entry_good}])
    assert picked["selection"] == 2
    assert picked["ordering"] == list(E.ORDERING)
    assert picked["ranking"] == [2, 1]
    cheaper = dict(good, model_tokens=1, sandbox_operations=1,
                   canonical_bytes=10)
    dearer = dict(good, model_tokens=99, sandbox_operations=99,
                  canonical_bytes=9999)
    tie = E.select_candidate(
        [{"lineage": 1, "validation": dearer},
         {"lineage": 2, "validation": cheaper}])
    assert tie["selection"] == 2
    none = E.select_candidate(
        [{"lineage": 1, "validation": bad, "entry_bytes": entry_bad},
         {"lineage": 2, "validation": dict(bad), "entry_bytes": entry_bad}])
    assert none["selection"] == "none"
    assert "neither candidate executable" in none["reason"]
    frozen_none = E.freeze_selection(
        f"coord02-L-none-{_tag('f')}", {"status": "declared-by-lane-E"},
        source_sha="0" * 40, selection=none,
        dev_results=[{"lineage": 1, "validation": bad},
                     {"lineage": 2, "validation": dict(bad)}],
        lineages=[{"lineage": 1,
                   "exposure_manifest": E.exposure_manifest(1, [])},
                  {"lineage": 2,
                   "exposure_manifest": E.exposure_manifest(2, [])}],
        accounting={"calls_used": 0, "live_calls_used": 0})
    assert frozen_none["package"]["kind"] == "none"
    assert F.verify_freeze(F.write_freeze(
        tmp_path / "none-freeze.json", frozen_none)) == []


def test_lineage_two_exposure_manifest(dsn, tmp_path):
    out = E.acquire(
        dsn, tmp_path, task_ids=["c02-t16"],
        launcher_factory=_factory(tmp_path),
        constructor=E.dev_constructor("c02-t16", solved=True),
        construction_gateway=FakeGatewayAdapter(text=""),
        budget=E.construction_budget())
    assert len(out["lineages"]) == 2
    assert out["lineages"][0]["exposure_manifest"] == {
        "lineage": 1, "development_access": "same-policy",
        "prior_lineage_results": [], "recorded": True}
    assert out["lineages"][1]["exposure_manifest"] == {
        "lineage": 2, "development_access": "same-policy",
        "prior_lineage_results": [1], "recorded": True}
    assert out["accounting"]["calls_used"] == 4
    assert out["accounting"]["live_calls_used"] == 0
    assert len(out["episodes"]) == 1
    assert out["packet"]["packet_version"] == "coord02-experience/1"


def test_frozen_package_use_and_retention(dsn, tmp_path):
    dirs = _fresh_dirs(tmp_path, "fro")
    launcher = LocalLauncher(dirs["runs"])
    seed = seed_episode(dsn, _tag("fro"), {"m": "1"})
    gated = E.stage_gate(
        dsn, dirs["staging"], dirs["artifacts"],
        entry_bytes=DOUBLED_SINGLE_TEST, requires={},
        version_id=f"coord02-L-fro-{_tag('v')}", launcher=launcher,
        allocation_id=seed["allocation_id"],
        description="DOUBLED construction-path test stand-in")
    assert gated["ok"] is True
    retained = E.publish_retained(
        dsn, dirs["artifacts"], receipt=gated["receipt"], launcher=launcher,
        allocation_id=seed["allocation_id"], version_id=gated["version_id"],
        requires={}, applicability={"requires": {}},
        evidence_refs=[{"episode": "dev", "outcome": "solved"}],
        scope={"study": "coord02"}, dependencies=[],
        budget={"units": 1})
    assert retained.code in (ResultCode.APPLIED,
                             ResultCode.ALREADY_APPLIED)
    assert retained.data["hooks"]["scope"] == {"study": "coord02"}
    assert retained.data["hooks"]["evidence_refs"] == [
        {"episode": "dev", "outcome": "solved"}]
    assert retained.data["hooks"]["dependencies"] == [
        gated["package_digest"]]
    revoked = E.revoke_binding_eligibility(
        dsn, version_id=gated["version_id"], reason="probe control")
    assert revoked["quarantine"] == ResultCode.APPLIED.value
    assert capabilities.quarantine_status(
        dsn, gated["version_id"]) is not None
    with pytest.raises(Exception, match="[Qq]uarantined"):
        load_frozen_package(dsn, dirs["artifacts"], gated["version_id"])
    scoped = E.scoped_loss_evidence({"binding": "role-x", "loss": "0/2"})
    assert scoped == {"scope": "binding", "binding": "role-x",
                      "loss": "0/2", "global_quarantine": False}


def test_construction_prompt_plain_text_with_response_contract():
    packet = {"probe_observations": []}
    budget = E.construction_budget()
    req = E.construction_request(packet, budget, lineage=1,
                                 attempt="init")
    assert "required_response" in req
    assert req["required_response"]["field"] == "entry"
    assert "response_example" in req
    text = E.render_construction_prompt(req)
    assert not text.lstrip().startswith("{")
    assert '"entry"' in text
    assert "single" in text or "probe" in text


SENTINEL_DSN = os.environ.get(
    "EC02_SENTINEL_DSN",
    "dbname=ec02test_sentinel host=/var/run/postgresql user=ubuntu")


def _sentinel_episode(dsn, tmp_path, marker: str) -> dict:
    episodes = E.acquire_episodes(
        dsn, tmp_path, task_ids=["c02-t16"],
        launcher_factory=_factory(tmp_path),
        constructor=E.dev_constructor("c02-t16", solved=True))
    made = episodes[0]
    packet = dict(made["packet"])
    inputs = dict(packet["versioned_inputs"])
    snapshot = dict(inputs["task_snapshot"])
    snapshot["sentinel_module"] = marker
    inputs["task_snapshot"] = snapshot
    packet["versioned_inputs"] = inputs
    return {"task_id": made["task_id"], "episode": made["episode"],
            "packet": packet}


def test_construction_request_carries_bounded_actual_contents(dsn,
                                                             tmp_path):
    from experiments.coord02 import schemas as S
    marker = f"SENTINEL-SOURCE-{uuid.uuid4().hex[:8]}"
    episode = _sentinel_episode(dsn, tmp_path, marker)
    req = E.construction_request([episode], E.construction_budget(),
                                 lineage=1, attempt="init")
    contents = req["episode_contents"]
    assert len(contents) == 1
    first = contents[0]
    for key in ("task_id", "source", "contracts", "initial_state",
                "proposals", "admissions", "observed_outputs",
                "child_artifacts", "failed_joins", "revisions", "costs"):
        assert key in first, key
    assert first["source"]["sentinel_module"] == marker
    assert first["proposals"], "decisions must be delivered, not digested"
    assert first["observed_outputs"], "observations must be delivered"
    assert first["costs"]["unknown"], "unknown costs stay unknown"
    wire = req["wire_schema"]
    assert wire["profile"] == S.PROFILE
    assert wire["profile_version"] == S.PROFILE_VERSION
    assert wire["phases"] == dict(S.ALLOWED)
    assert wire["actions"] == list(S.ACTIONS)
    specimen = req["transport_specimen"]
    S.validate_response(
        dict(specimen["response"]), decision_id=specimen["decision_id"],
        package_digest=specimen["package_digest"],
        source_digest=specimen["source_digest"],
        plan_revision=specimen["plan_revision"],
        phase=specimen["phase"], allowed=list(specimen["allowed"]))
    text = E.render_construction_prompt(req)
    assert marker in text, "actual source must reach the prompt"
    assert "doubled-fake-gateway" not in text
    assert "TEAM01" not in text


def test_construction_request_refuses_oversize_without_truncation(dsn,
                                                                  tmp_path):
    episode = _sentinel_episode(dsn, tmp_path, "oversize-probe")
    packet = dict(episode["packet"])
    inputs = dict(packet["versioned_inputs"])
    snapshot = dict(inputs["task_snapshot"])
    snapshot["blob"] = "x" * (E.CONSTRUCTION_CONTENT_BUDGET_BYTES + 1)
    inputs["task_snapshot"] = snapshot
    packet["versioned_inputs"] = inputs
    episode["packet"] = packet
    with pytest.raises(E.ConstructionRequestTooLarge):
        E.construction_request([episode], E.construction_budget(),
                               lineage=1, attempt="init")


def test_construction_budget_defaults_large_cap_low_effort():
    budget = E.construction_budget()
    assert budget["max_output_tokens"] >= 65536
    assert budget["reasoning_effort"] == "low"


def test_request_call_threads_reasoning_effort(dsn):
    seed = E.seed_construction_campaign(dsn, _tag("effort"),
                                        E.construction_budget())
    ledger = E.ConstructionLedger(dsn, seed["allocation_id"])
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    rec = ledger.request_call(
        E.construction_request(packet, E.construction_budget(),
                               lineage=1, attempt="init"),
        gateway=FakeGatewayAdapter(text=json.dumps({"entry": "x = 1\n"})))
    stored = broker.read_operation(dsn, rec["operation_id"])
    inner = stored["payload"]["payload"]
    assert inner["reasoning_effort"] == "low"
    assert inner["max_output_tokens"] >= 65536


def test_ledger_survives_process_replacement(dsn):
    seed = E.seed_construction_campaign(dsn, _tag("durable"),
                                        E.construction_budget())
    prefix = f"coord02-L-durable-{uuid.uuid4().hex[:6]}"
    first = E.ConstructionLedger(dsn, seed["allocation_id"],
                                 attempt_prefix=prefix)
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    gateway = FakeGatewayAdapter(text=json.dumps({"entry": "x = 1\n"}))
    rec = first.request_call(
        E.construction_request(packet, E.construction_budget(),
                               lineage=1, attempt="init"),
        gateway=gateway)
    pending_id = f"{prefix}-l2-init-pending"
    ensured = broker.ensure_operation(
        dsn, operation_id=pending_id, effect=broker.MODEL_INFERENCE,
        payload={"model": "doubled-fake-gateway",
                 "messages": [{"role": "user", "content": "held"}],
                 "max_output_tokens": 8, "deadline_ms": 300_000},
        allocation_id=seed["allocation_id"], attempt_id=None)
    assert ensured.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    fresh = E.ConstructionLedger(dsn, seed["allocation_id"],
                                 attempt_prefix=prefix)
    assert fresh.calls_used() == 2
    assert fresh.remaining() == E.MAX_CONSTRUCTION_CALLS - 2
    assert {c["operation_id"] for c in fresh.calls} >= {
        rec["operation_id"], pending_id}
    assert pending_id in fresh.unresolved_effects()
    assert rec["operation_id"] not in fresh.unresolved_effects()


def test_invalid_requests_consume_defined_budget(dsn):
    seed = seed_episode(dsn, _tag("invalid"), {"m": "1"})
    prefix = f"coord02-L-invalid-{uuid.uuid4().hex[:6]}"
    ledger = E.ConstructionLedger(dsn, seed["allocation_id"],
                                  attempt_prefix=prefix)
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    budget = E.construction_budget()
    gateway = FakeGatewayAdapter(text=json.dumps({"entry": "x = 1\n"}))
    with pytest.raises(Exception, match="lineage"):
        ledger.request_call(
            E.construction_request(packet, budget, lineage=99,
                                   attempt="init"),
            gateway=gateway)
    assert ledger.calls_used() == 1
    assert ledger.remaining() == E.MAX_CONSTRUCTION_CALLS - 1
    fresh = E.ConstructionLedger(dsn, seed["allocation_id"],
                                 attempt_prefix=prefix)
    assert fresh.calls_used() == 1
    assert fresh.remaining() == E.MAX_CONSTRUCTION_CALLS - 1


def test_repair_carries_lineage_and_concrete_failure(dsn, tmp_path):
    out = E.acquire(
        dsn, tmp_path, task_ids=["c02-t16"],
        launcher_factory=_factory(tmp_path),
        constructor=E.dev_constructor("c02-t16", solved=True),
        construction_gateway=FakeGatewayAdapter(text=""),
        budget=E.construction_budget())
    for rec in out["lineages"]:
        assert rec["repair"] is not None
        assert rec["repair"]["lineage"] == rec["lineage"]
        assert rec["repair"]["operation_id"] != rec["init"]["operation_id"]
        failure = rec["repair_failure"]
        assert failure["lineage"] == rec["lineage"]
        assert failure["reason"]
        assert failure["operation_id"] == rec["init"]["operation_id"]
        assert rec["rejections"], "failed keeps/parses must be preserved"
        assert rec["init"]["text"] == "", "raw response must be preserved"


def test_sentinel_destructive_setup_refused():
    from psycopg.types.json import Json
    db.apply_migrations(SENTINEL_DSN, MIGRATIONS)
    E.designate_db(SENTINEL_DSN, kind="evidence",
                     purpose="sentinel proof contents")
    seed = seed_episode(SENTINEL_DSN, f"sentinel-{uuid.uuid4().hex[:8]}",
                        {"m": "1"})
    sentinel_op = f"sentinel-op-{uuid.uuid4().hex[:8]}"
    ensured = broker.ensure_operation(
        SENTINEL_DSN, operation_id=sentinel_op,
        effect=broker.MODEL_INFERENCE,
        payload={"model": "doubled-fake-gateway",
                 "messages": [{"role": "user", "content": "sentinel"}],
                 "max_output_tokens": 8, "deadline_ms": 300_000},
        allocation_id=seed["allocation_id"], attempt_id=None)
    assert ensured.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    marker = f"sentinel-proof-{uuid.uuid4().hex[:8]}"
    with db.connect(SENTINEL_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO receipts (receipt_identity,"
                        " operation_id, content_digest, content, outcome)"
                        " VALUES (%s, %s, 'sentinel', %s, 'success')"
                        " ON CONFLICT DO NOTHING",
                        (marker, sentinel_op, Json({})))
            conn.commit()
    with pytest.raises(E.EvidenceDBProtected):
        E.prepare_disposable_db(SENTINEL_DSN, MIGRATIONS)
    with db.connect(SENTINEL_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipts WHERE"
                        " receipt_identity = %s", (marker,))
            assert int(cur.fetchone()[0]) == 1
            conn.commit()


def test_disposable_designation_permits_setup(dsn):
    E.designate_db(dsn, kind="disposable", purpose="lane test database")
    E.prepare_disposable_db(dsn, MIGRATIONS)
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM operations")
            assert int(cur.fetchone()[0]) == 0
            conn.commit()
