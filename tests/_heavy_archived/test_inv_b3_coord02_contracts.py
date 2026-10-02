"""INV-B3 gate: coord02 on the shared packet shape, admitted model path.

Real Postgres (`inv_b3_contracts` via INV_B3_DSN, never live) in every
brokered test. Recording doubles sit at the gateway seam only: every
coord02 model call travels through broker ensure, dispatch, settled
receipts and measured costs.
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

DSN = os.environ.get(
    "INV_B3_DSN",
    "dbname=inv_b3_contracts host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

SEP_TASK = "c02-t01"
DIA_TASK = "c02-t11"


def _fresh_db():
    assert "live" not in DSN
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(DSN, MIGRATIONS)
    E.designate_db(DSN, kind="disposable",
                   purpose="INV-B3 contracts gate")
    E.prepare_disposable_db(DSN, MIGRATIONS)


def _packet(task_id: str):
    from experiments.coord02 import experience as E
    made = E.construction_request(
        {"packet_version": "coord02-experience/1",
         "probe_observations": [], "task_id": task_id},
        E.construction_budget(), lineage=1, attempt="init")
    return made, E.render_construction_prompt(made)


def test_rendered_construction_contract_matches_enforcement():
    from experiments.coord02 import oracle
    from experiments.coord02 import packet as P
    from experiments.coord02 import schemas as S
    rendered = {}
    for task_id in (SEP_TASK, DIA_TASK):
        made, prompt = _packet(task_id)
        assert made["lineage"] == 1 and made["attempt"] == "init"
        assert made["episode_contents"][0]["task_id"] == task_id
        shape = made["candidate_shapes"][task_id]
        assert shape["family"] == oracle.TASK_FAMILY[task_id]
        assert shape["owned_paths"] == oracle.worker_files(task_id)
        for path in shape["owned_paths"]:
            assert path in prompt, (task_id, path)
        rule = made["witness_rules"][task_id]
        assert rule["evaluator"]["id"] in prompt
        assert "protected" in prompt
        for action in S.ACTIONS:
            assert action in prompt, action
        for phase in S.ALLOWED:
            assert phase in prompt, phase
        for token in ("max_state_bytes", "max_probe_calls",
                      "allowed_actions", "request_fields"):
            assert token in prompt, token
        assert "doubled-fake-gateway" not in prompt
        assert "TEAM01" not in prompt
        rendered[task_id] = (made, prompt)
    assert rendered[SEP_TASK][0]["wire_schema"] == \
        rendered[DIA_TASK][0]["wire_schema"]
    assert rendered[SEP_TASK][0]["candidate_shapes"] != \
        rendered[DIA_TASK][0]["candidate_shapes"]
    assert P.PACKET_VERSION


def test_entry_rule_acceptance_matches_validator():
    from experiments.coord02 import packet as P
    from experiments.coord02 import schemas as S
    ident = {"decision_id": "gate-decision", "package_digest": "gate-pkg",
             "source_digest": "gate-src", "plan_revision": 0,
             "phase": S.PHASE_PRE_PLAN,
             "allowed": list(S.ALLOWED[S.PHASE_PRE_PLAN])}
    good_probe = {"profile": S.PROFILE, "profile_version": S.PROFILE_VERSION,
                  "decision_id": "gate-decision", "package_digest": "gate-pkg",
                  "source_digest": "gate-src", "plan_revision": 0,
                  "phase": S.PHASE_PRE_PLAN,
                  "proposal": {"action": "probe",
                               "invocations": [{"interface": "observe-broken",
                                                "input": {}}]},
                  "state": {}}
    assert S.validate_response(dict(good_probe), **ident)["action"] == "probe"
    bad = [
        dict(good_probe, proposal={"action": "bogus", "reason": "x"}),
        dict(good_probe, proposal={"action": "stop"}),
        dict(good_probe, extra="field"),
        dict(good_probe, profile="other"),
        dict(good_probe, decision_id="stale"),
        dict(good_probe, proposal={"action": "stop", "reason": "",
                                   "extra": 1}),
        dict(good_probe, state={"big": "x" * (S.MAX_STATE_BYTES + 1)}),
    ]
    for response in bad:
        with pytest.raises(S.PolicyError):
            S.validate_response(dict(response), **ident)
    _, prompt = _packet(SEP_TASK)
    for token in ("probe", "plan", "rework", "stop", "unsupported",
                  "allowed_actions", "max_state_bytes"):
        assert token in prompt, token
    assert P.candidate_shape(SEP_TASK)["owned_paths"]


def test_parse_entry_agrees_with_renderer():
    from experiments.coord02 import experience as E
    from experiments.coord02 import packet as P
    entry_source = E._acquire_probe_plan_entry().decode("utf-8")
    body = json.dumps({"entry": entry_source})
    for text in (body, "```json\n%s\n```" % body):
        kept = E.keep_response({"text": text, "usage": {},
                                "label": E.CONSTRUCTION_LABEL,
                                "doubled": True, "live": False,
                                "operation_id": "gate-parse"})
        assert kept["usable"] is True, kept["reason"]
        assert kept["entry_bytes"].decode("utf-8") == entry_source
        source, problem = P.parse_construction_entry(text)
        assert problem == "" and source == entry_source
    for text, reason in (("not json at all", "unparsable-response"),
                         (json.dumps({"notes": "no entry"}), "missing-entry"),
                         (json.dumps([1, 2]), "missing-entry")):
        kept = E.keep_response({"text": text, "usage": {},
                                "label": E.CONSTRUCTION_LABEL,
                                "doubled": True, "live": False,
                                "operation_id": "gate-parse-bad"})
        assert kept["usable"] is False
        assert kept["reason"].startswith(reason), kept["reason"]
        assert kept["response_bytes"] == text.encode("utf-8")


class RecordingGateway:
    label = "INV-B3-RECORDING"

    def __init__(self, texts: list):
        from settlement.gateway import Usage
        self._texts = list(texts)
        self._usage = Usage(input_tokens=11, output_tokens=7)
        self.calls: list = []

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse
        self.calls.append(request)
        return ModelResponse(
            request.operation_id,
            self._texts[min(len(self.calls) - 1, len(self._texts) - 1)],
            {}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


def _ledger(campaign: str):
    from experiments.coord02 import experience as E
    seed = E.seed_construction_campaign(
        DSN, campaign, E.construction_budget())
    return E.ConstructionLedger(
        DSN, seed["allocation_id"],
        attempt_prefix="invb3-%s" % campaign)


def _operation_ids(prefix: str) -> list:
    from settlement import db
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, payload->>'effect' AS effect"
                        " FROM operations WHERE starts_with(id, %s)"
                        " ORDER BY id", (prefix,))
            rows = cur.fetchall()
            conn.commit()
            return rows


def _success_receipt(operation_id: str):
    from settlement import db
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content FROM receipts"
                        " WHERE operation_id = %s"
                        " AND receipt_identity = %s"
                        " AND outcome = 'success'",
                        (operation_id, "gw:%s" % operation_id))
            row = cur.fetchone()
            conn.commit()
            return row


def _round_trip(task_id: str, lineage: int):
    from experiments.coord02 import experience as E
    from settlement.launcher_local import LocalLauncher
    import tempfile
    ledger = _ledger("roundtrip-%s" % uuid.uuid4().hex[:8])
    gateway = RecordingGateway(
        [json.dumps({"entry": E._acquire_probe_plan_entry().decode()})])
    record = ledger.request_call(
        E.construction_request(
            {"packet_version": "coord02-experience/1",
             "probe_observations": [], "task_id": task_id},
            E.construction_budget(), lineage=lineage, attempt="init"),
        gateway=gateway)
    kept = E.keep_response(record)
    assert kept["usable"] is True, kept["reason"]
    parsed = E.parse_candidate(kept["entry_bytes"])
    assert parsed == {"ok": True, "reason": ""}
    with tempfile.TemporaryDirectory(prefix="invb3-gate-") as tmp:
        root = Path(tmp)
        seed = E.seed_episode(DSN, "gate-%s" % uuid.uuid4().hex[:8],
                              {"m": "1"})
        gated = E.stage_gate(
            DSN, root / "staging", root / "artifacts",
            entry_bytes=kept["entry_bytes"], requires={},
            version_id="invb3-gate-%s" % uuid.uuid4().hex[:8],
            launcher=LocalLauncher(root / "runs"),
            allocation_id=seed["allocation_id"])
    assert gated["ok"] is True and gated["stage"] == "select", gated
    return ledger


def test_transport_round_trip_two_families():
    _fresh_db()
    ledgers = []
    for task_id, lineage in ((SEP_TASK, 1), (DIA_TASK, 2)):
        ledger = _round_trip(task_id, lineage)
        assert ledger.calls_used() == 1
        ledgers.append(ledger)
    assert len(ledgers) == 2
    for operation_id, effect in _operation_ids("invb3-roundtrip-"):
        assert effect == "model-inference", (operation_id, effect)
        assert _success_receipt(operation_id) is not None, operation_id


def test_malformed_construction_has_visible_effects():
    _fresh_db()
    from experiments.coord02 import experience as E
    ledger = _ledger("malformed-%s" % uuid.uuid4().hex[:8])
    gateway = RecordingGateway(["not json at all"])
    record = ledger.request_call(
        E.construction_request(
            {"packet_version": "coord02-experience/1",
             "probe_observations": []},
            E.construction_budget(), lineage=1, attempt="init"),
        gateway=gateway)
    kept = E.keep_response(record)
    assert kept["usable"] is False and kept["kept"] is True
    assert kept["reason"].startswith("unparsable-response"), kept["reason"]
    assert kept["response_bytes"] == b"not json at all"
    assert ledger.calls_used() == 1
    assert len(gateway.calls) == 1
    operation_id = gateway.calls[0].operation_id
    assert _success_receipt(operation_id) is not None
    repair = ledger.repair_call(
        {"packet_version": "coord02-experience/1",
         "probe_observations": []},
        E.construction_budget(), lineage=1,
        prior_failure={"kind": "parse", "reason": kept["reason"],
                       "operation_id": operation_id},
        gateway=gateway)
    assert ledger.calls_used() == 2
    assert repair["operation_id"] != operation_id
    assert _success_receipt(repair["operation_id"]) is not None


def _demux_gateway(task_id: str, marker: str):
    from experiments.coord02 import entry
    from experiments.coord02 import experience as E
    snap = E.snapshot_files(task_id)

    class Demux(RecordingGateway):
        def infer(self, request):
            from settlement.gateway import ModelResponse
            if "a-decision" in request.operation_id:
                self.calls.append(request)
                return ModelResponse(
                    request.operation_id,
                    json.dumps({"action": "plan", "shape": "single",
                                "children": entry.plan_children(
                                    task_id, "single")}),
                    {}, self._usage, "stop")
            owned = entry.oracle.worker_files(task_id)
            self.calls.append(request)
            return ModelResponse(
                request.operation_id,
                json.dumps({"files": {p: snap[p] + "\n" + marker
                                      for p in owned},
                            "notes": "gate double"}),
                {}, self._usage, "stop")

    return Demux([""])


def test_admitted_every_model_call(tmp_path):
    _fresh_db()
    from experiments.coord02 import entry
    from experiments.coord02 import freeze as freeze_mod
    from settlement.launcher_local import LocalLauncher
    marker = "INVB3_ADMITTED = 1\n"
    gateway = _demux_gateway(SEP_TASK, marker)

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(tmp_path / tag)}

    cell = entry.run_cell(
        DSN, freeze=freeze_mod.build_freeze("invb3-admitted",
                                            source_sha="invb3-base"),
        task_id=SEP_TASK, panel="development", repeat=1, arm="A",
        launcher_factory=launcher_factory,
        package_digest="none", package_text="gate-dev",
        source_sha="invb3-base", config_digest="invb3-gate",
        gateway=gateway, model="invb3-double")
    assert cell.outcome.get("plan_id"), cell.outcome
    assert gateway.calls, "recording gateway never consulted"
    from settlement import broker
    from settlement import db
    called = [c.operation_id for c in gateway.calls]
    assert len(set(called)) == len(called), called
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            for operation_id in called:
                cur.execute("SELECT payload->>'effect' AS effect"
                            " FROM operations WHERE id = %s",
                            (operation_id,))
                row = cur.fetchone()
                assert row is not None, operation_id
                assert row[0] == broker.MODEL_INFERENCE, \
                    (operation_id, row[0])
            conn.commit()
    for operation_id in called:
        assert _success_receipt(operation_id) is not None, operation_id
    tree = entry.restage_tree(DSN, cell.outcome)
    assert tree is not None
    assert any(marker.strip() in body for body in tree.values())


def test_malformed_child_action_visibly_rejected(tmp_path):
    _fresh_db()
    from experiments.coord02 import entry
    from experiments.coord02 import freeze as freeze_mod
    from settlement.launcher_local import LocalLauncher
    gateway = _demux_gateway(SEP_TASK, "UNUSED")
    wrong = {"files": {"no/such/path.py": "x"}, "notes": "bad"}

    real_infer = gateway.infer

    def spoiled(request):
        response = real_infer(request)
        if "a-decision" in request.operation_id:
            return response
        from settlement.gateway import ModelResponse
        from settlement.gateway import Usage
        return ModelResponse(request.operation_id, json.dumps(wrong), {},
                             Usage(input_tokens=1, output_tokens=1), "stop")

    gateway.infer = spoiled

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(tmp_path / tag)}

    cell = entry.run_cell(
        DSN, freeze=freeze_mod.build_freeze("invb3-rejected",
                                            source_sha="invb3-base"),
        task_id=SEP_TASK, panel="development", repeat=1, arm="A",
        launcher_factory=launcher_factory,
        package_digest="none", package_text="gate-dev",
        source_sha="invb3-base", config_digest="invb3-gate",
        gateway=gateway, model="invb3-double")
    assert cell.outcome.get("status") == "submit-refused", cell.outcome
    assert "no constructor artifact" in cell.outcome.get("reason", ""), \
        cell.outcome
    assert gateway.calls, "model path never ran"
    from settlement import broker
    from settlement import db
    called = [c.operation_id for c in gateway.calls]
    assert called, "malformed run left no admission rows"
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            for operation_id in called:
                cur.execute("SELECT payload->>'effect' AS effect"
                            " FROM operations WHERE id = %s",
                            (operation_id,))
                row = cur.fetchone()
                assert row is not None, operation_id
                assert row[0] == broker.MODEL_INFERENCE, \
                    (operation_id, row[0])
            conn.commit()
    for operation_id in called:
        assert _success_receipt(operation_id) is not None, operation_id


def test_canned_seam_carries_no_admission(tmp_path):
    _fresh_db()
    from experiments.coord02 import entry as entry_mod
    from experiments.coord02 import experience as E
    from experiments.coord02 import oracle
    from experiments.coord02.controller import EpisodeConfig, run_episode
    from experiments.coord02.controller import seed_episode
    from settlement.launcher_local import LocalLauncher
    from settlement.representation import sha_hex
    snapshot = E.snapshot_files(SEP_TASK)
    payload = oracle.build_solver_payload(SEP_TASK)
    policy = entry_mod.arm_policy_entry("S", task_id=SEP_TASK,
                                        package_digest="gate")
    requires = E._requires_for(SEP_TASK, snapshot)
    seed = seed_episode(DSN, "gate-canned-%s" % uuid.uuid4().hex[:8],
                        snapshot)
    cfg = EpisodeConfig(
        run_id="run-gate-canned-%s" % uuid.uuid4().hex[:8], task_id=SEP_TASK,
        allocation_id=seed["allocation_id"],
        investigation_id=seed["investigation_id"],
        snapshot=dict(snapshot),
        interface_contract=E._dev_interface_contract(SEP_TASK, payload),
        join_rules=E._dev_join_rules(SEP_TASK),
        bindings=E._dev_bindings(requires, snapshot),
        source_interfaces=E._dev_source_interfaces(SEP_TASK),
        package={"version_id": "coord02-L-gate",
                 "package_digest": sha_hex(policy),
                 "entry_bytes": policy, "requires": requires},
        snapshot_digest=seed["snapshot_digest"])
    outcome = run_episode(
        DSN, cfg, {"local-process": LocalLauncher(tmp_path)},
        E.dev_constructor(SEP_TASK, solved=True))
    assert outcome.get("status") == "submit-refused", outcome
    assert "no constructor artifact" in outcome.get("reason", ""), outcome
    model_ops = [(oid, effect) for oid, effect in
                 _operation_ids("coord:run-gate-canned-")
                 if effect == "model-inference"]
    assert model_ops == [], model_ops
