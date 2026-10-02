from __future__ import annotations

import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01.s09_run_isolation import create_disposable_db, \
    disposable_db, drop_disposable_db
from scripts import s09_pilot as pilot
from scripts import s09_verify as verify

from execution_authority import execution_authority

RUN_TOKEN = "c3pilot"


def test_freeze_pins_policy_abi_and_n5_panel():
    freeze = pilot.build_freeze()
    assert freeze["artifact_kind"] == "learning-policy"
    assert freeze["policy_abi"] == "ad01-policy-step-v1"
    assert len(freeze["development"]) == 4
    assert len(freeze["assessment"]) == 12
    assert all(len(entry["use_tasks"]) == 2
               for entry in freeze["assessment"])
    assert freeze["freeze_digest"] == verify.freeze_digest(freeze)


def test_policy_record_preserves_step_bytes_and_digest():
    record = pilot._policy_record(pilot.P0_POLICY_SOURCE)
    assert record["artifact"]["kind"] == "learning-policy"
    assert record["artifact"]["entry"] == "STEP"
    assert record["artifact"]["source_digest"] == hashlib.sha256(
        pilot.P0_POLICY_SOURCE.encode()).hexdigest()
    assert record["policy_source"] == pilot.P0_POLICY_SOURCE


def test_run_episode_passes_model_constructor_to_public_campaign(monkeypatch):
    from experiments.ad01 import agenda_policy, trajectory

    seen = {}
    monkeypatch.setattr(pilot, "_authorize", lambda *_: "allocation")
    monkeypatch.setattr(pilot, "_campaign_ops", lambda *_: [])
    monkeypatch.setattr(
        agenda_policy, "step_policy_consumer",
        lambda _policy, **kwargs: seen.setdefault("consumer", kwargs))

    def run(*args, **kwargs):
        seen["campaign"] = kwargs
        return {"boundaries": [], "episodes": [], "model_calls": 0,
                "queries": 0, "construction_calls": 0}

    monkeypatch.setattr(trajectory, "run_campaign", run)
    pilot._run_episode("dsn", 0, 1, pilot.P1_TASK,
                       pilot._policy_record(pilot.P0_POLICY_SOURCE),
                       gateway=object(), model="controlled")
    assert seen["campaign"]["constructor"] == "model"
    assert seen["campaign"]["gateway"] is seen["consumer"]["gateway"]
    assert seen["campaign"]["model"] == "controlled"


def test_incumbent_step_does_real_method_work_and_arms_share_input_task():
    from experiments.ad01 import policy_step

    record = pilot._policy_record(pilot.P0_POLICY_SOURCE)
    view = policy_step.materialize_view(
        task={"task_id": pilot.P1_TASK, "family": "software"},
        observations=[], open_questions=[], last_result=None,
        eligible_methods=[], remaining={"steps": 6, "model_calls": 6,
                                        "queries": 16})
    with execution_authority("c3incumbent") as auth:
        result = policy_step.run_policy_step(
            record, view, {},
            dsn=auth["dsn"], allocation_id=auth["allocation_id"],
            operation_id=auth["operation_id"])
    assert result["action"]["kind"] == "construct_method"
    assert result["action"]["inputs"]["max_queries"] == 16
    assert pilot.P1_TASK == pilot.P2_TASK


def test_controlled_gateway_uses_real_responses_adapter():
    class Handler(BaseHTTPRequestHandler):
        seen = []

        def do_POST(self):
            Handler.seen.append(json.loads(self.rfile.read(
                int(self.headers["Content-Length"]))))
            body = json.dumps({"output": [{"type": "message",
                                             "content": [{
                                                 "type": "output_text",
                                                 "text": "ok"}]}],
                               "usage": {"input_tokens": 1,
                                         "output_tokens": 1}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        adapter = pilot._http_gateway(
            "http://127.0.0.1:%d" % server.server_port)
        from settlement.gateway import ModelRequest
        response = adapter.infer(ModelRequest(
            model="controlled", messages=({"role": "user",
                                             "content": "probe"},),
            max_output_tokens=8, deadline_ms=5000,
            operation_id="c3-http-probe"))
        assert response.text == "ok"
        assert Handler.seen[0]["model"] == "controlled"
        assert Handler.seen[0]["input"] == "probe"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_controlled_http_full_study_freezes_and_verifies_public_path(
        monkeypatch, tmp_path):
    class Handler(BaseHTTPRequestHandler):
        seen = []

        def do_POST(self):
            payload = json.loads(self.rfile.read(
                int(self.headers["Content-Length"])))
            Handler.seen.append(payload)
            prompt = str(payload.get("input", ""))
            source = (pilot.METHOD_SOURCE
                      if "Write one python method" in prompt
                      else pilot.P1_POLICY_SOURCE)
            text = json.dumps({"entry": source, "notes": "controlled"})
            body = json.dumps({"output": [{"type": "message",
                                             "content": [{
                                                 "type": "output_text",
                                                 "text": text}]}],
                               "usage": {"input_tokens": 1,
                                         "output_tokens": 1}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            return

    database = create_disposable_db(RUN_TOKEN,
                                    migrations_dir=ROOT / "migrations")
    dsn = database.dsn
    assert dsn.count(database.name) == 1, database.name
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv(
            "S09_CONTROLLED_GATEWAY_ENDPOINT",
            "http://127.0.0.1:%d" % server.server_port)
        bundle = pilot.run_study(dsn, tmp_path, gateway_mode="controlled",
                                namespace_token="c3",
                                 model="controlled")
        freeze = bundle["freeze"]
        assert freeze["config"]["api"] == "responses"
        assert freeze["config"]["adapter"].endswith("HttpGatewayAdapter")
        assert freeze["phase"] == "preassessment"
        assert all(freeze["policy_identities"][arm]["status"] == "available"
                   for arm in ("P0", "P1", "P2"))
        assert freeze["policy_identities"]["P1"]["task_id"] == \
            freeze["policy_identities"]["P2"]["task_id"]
        assert freeze["policy_identities"]["P1"]["experience_digest"] != \
            freeze["policy_identities"]["P2"]["experience_digest"]
        assert freeze["method_repertoires"]["P0"]["member_digests"]
        assert any(any(action.get("kind") == "development" and
                       action.get("max_queries", 0) > 0
                       for action in episode["policy_actions"])
                   and episode["construction_calls"] > 0
                   for episode in bundle["development"])
        members = set(freeze["method_repertoires"]["P0"]["member_digests"])
        assert any(record["executed"] != "incumbent" and
                   record["executed_source_digest"] in members
                   for record in bundle["use_records"]
                   if record["study_arm"] == "P0")
        assert verify.verify_bundle(bundle)["status"] == "pass"
        prompts = [str(payload.get("input", "")) for payload in Handler.seen]
        assert any("Write one python policy" in prompt for prompt in prompts)
        assert any("Write one python method" in prompt for prompt in prompts)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        drop_disposable_db(database)


def test_verifier_rejects_policy_execution_without_digest_or_action():
    freeze = pilot.build_freeze()
    freeze["development"] = []
    freeze["assessment"] = [{"episode_id": "assess-P0-w1-sw",
                             "arm": "P0", "world": 1,
                             "domain": "software",
                             "use_tasks": ["a", "b"]}]
    freeze["order"] = ["assess-P0-w1-sw"]
    freeze["freeze_digest"] = verify.freeze_digest(freeze)
    bundle = {"freeze": freeze, "development": [],
              "construction": {},
              "assessment": [{"episode_id": "assess-P0-w1-sw",
                              "arm": "P0", "policy_steps": 1,
                              "model_calls": 0, "witness_queries": 0,
                              "operations": []}],
              "use_records": [], "operations": {},
              "accounting": verify.empty_accounting(),
              "refusal_probes": [],
              "conformance_replay": {"status": "conformance",
                                      "identity": "supported",
                                      "changed": "refused"}}
    out = verify.verify_bundle(bundle)
    assert "policy-digest-missing assess-P0-w1-sw" in out["problems"]
    assert "policy-actions-missing assess-P0-w1-sw" in out["problems"]


def test_the_store_is_one_this_run_created():
    """A dropped store must never be a store somebody else still runs on.

    This file used to drop `s09_m5_c3_http` before creating it, so a sibling
    run of the same file lost the store mid-study and the verifier then read
    a torn study as a product defect. The name carries a per-run token, and
    the run asserts the name appears exactly once in the DSN it hands the
    study, so a truncated DSN cannot quietly point at another store.
    """
    database = create_disposable_db(RUN_TOKEN)

    assert database.name.startswith("s09iso_c3pilot_"), database.name
    assert database.dsn.count(database.name) == 1, database.dsn
    drop_disposable_db(database)


def test_the_store_survives_a_second_module_scope():
    """Re-deriving the store must not reuse this module's database.

    The collision that produced the original failures was two runs of this
    file at once. Each run's fixture mints its own name, so a second fixture
    can never observe or destroy the first one's database.
    """
    with disposable_db(RUN_TOKEN) as other:
        assert other.name.startswith("s09iso_c3pilot_"), other.name
