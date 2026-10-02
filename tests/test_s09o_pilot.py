from __future__ import annotations

import hashlib
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
METHOD = (
    "def ENTRY(task, oracle, max_queries=16):\n"
    "    if task['family'] == 'software':\n"
    "        return reducers.reduce_software(task, oracle, method='greedy', max_queries=max_queries)\n"
    "    return reducers.reduce_graph(task, oracle, method='greedy', max_queries=max_queries)\n"
)
REJECTED_POLICY = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    action = {'kind': 'diagnose', 'target': target,\n"
    "              'inputs': {'diagnostic': view['task_content']['family']},\n"
    "              'evidence_refs': [], 'requested_resources': {'queries': 1}}\n"
    "    return {'action': action, 'state': state}\n"
)


def _dsn(name: str) -> str:
    return "dbname=%s host=/var/run/postgresql user=ubuntu" % name


def _make_db(name: str) -> str:
    subprocess.run(["createdb", "-h", "/var/run/postgresql", "-U", "ubuntu", name],
                   check=True, capture_output=True, text=True, timeout=60)
    from settlement import db
    dsn = _dsn(name)
    db.apply_migrations(dsn, MIGRATIONS)
    return dsn


def _drop_db(name: str) -> None:
    subprocess.run(["dropdb", "-h", "/var/run/postgresql", "-U", "ubuntu", name],
                   capture_output=True, text=True, timeout=60)


class RoutingProvider:
    label = "S09O-PILOT-PROVIDER"

    def __init__(self, policy_source: str):
        from settlement.gateway import Usage
        self.policy_source = policy_source
        self.calls = []
        self.usage = Usage(input_tokens=11, output_tokens=7)

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse
        self.calls.append(request)
        prompt = " ".join(str(m.get("content", ""))
                            for m in request.messages)
        source = self.policy_source if "Write one python policy" in prompt else METHOD
        return ModelResponse(request.operation_id,
                             json.dumps({"entry": source, "notes": "pilot"}),
                             {}, self.usage, "stop")

    def cancel(self, operation_id):
        return False


@pytest.fixture(scope="module")
def full_bundle(tmp_path_factory):
    from scripts import s09_pilot
    name = "s09o_pilot_full"
    dsn = _make_db(name)
    try:
        out = tmp_path_factory.mktemp("full")
        yield s09_pilot.run_study(
            dsn, out, gateway=RoutingProvider(s09_pilot.P1_POLICY_SOURCE)), out
    finally:
        _drop_db(name)


def test_bound_policy_releases_drive_the_covered_domain(full_bundle):
    bundle, _out = full_bundle
    for arm in ("P1", "P2"):
        entry = bundle["construction"][arm]
        assert entry["status"] == "available"
        assert entry["disposition"] == "bound"
        assert entry["release_id"]
        assert entry["calls"] == 1
        for row in bundle["assessment"]:
            if row["arm"] != arm:
                continue
            assert row["policy_release"] == entry["release_id"]
            assert row["release_id"] == entry["release_id"]
            if row["domain"] == "software":
                assert row["coverage_status"] == "covered"
                assert row["executed_policy_digest"] == entry["bound_digest"]
                assert row["executed_policy_digests"] == [entry["bound_digest"]]
            else:
                assert row["coverage_status"] == \
                    "not-covered-by-revised-policy"
                assert row["executed_policy_digest"] != entry["bound_digest"]
                assert row["fallback_reason"].startswith(
                    "arm-domain-uncovered:")


def test_p0_has_no_release_and_uncovered_domains_use_incumbent(full_bundle):
    bundle, _out = full_bundle
    assert all(row["policy_release"] is None and row["release_id"] is None
               for row in bundle["assessment"] if row["arm"] == "P0")
    for arm in ("P1", "P2"):
        graph = [row for row in bundle["use_records"]
                 if row["study_arm"] == arm and row["domain"] == "graph"]
        assert len(graph) == 4
        assert {row["executed"] for row in graph} == {"incumbent"}
        assert all(row["fallback_reason"].startswith(
            "arm-domain-uncovered:") for row in graph)
    assert set(bundle["report"]["comparisons"]) == {"P2-vs-P0", "P2-vs-P1"}
    assert bundle["report"]["comparisons"]["P2-vs-P0"][
        "not_covered_domains"] == ["graph"]


def test_one_candidate_per_arm_and_experience_is_the_only_request_difference(
        full_bundle):
    bundle, _out = full_bundle
    assert sum(bundle["construction"][arm]["calls"]
               for arm in ("P1", "P2")) == 2
    assert bundle["construction_request_comparison"] == {
        "software": {"same_non_experience": True,
                      "experience_differs": True}}
    assert bundle["construction"]["P1"]["experience_digest"] != \
        bundle["construction"]["P2"]["experience_digest"]
    assert len(bundle["construction_requests"]["P1"]) == 1
    assert len(bundle["construction_requests"]["P2"]) == 1


def test_schedule_and_assessment_counts_are_observed(full_bundle):
    bundle, _out = full_bundle
    assert len(bundle["development"]) == 4
    assert len(bundle["assessment"]) == 12
    assert len(bundle["use_records"]) == 24
    assert all(len(entry["use_tasks"]) == 2
               for entry in bundle["freeze"]["assessment"])
    assert sum(entry["calls"] for entry in bundle["construction"].values()) <= 4
    assert all(sum(row["arm"] == arm for row in bundle["assessment"]) == 4
               for arm in ("P0", "P1", "P2"))


def test_rejected_arm_is_incomplete_and_not_relabelled(tmp_path):
    from scripts import s09_pilot, s09_verify
    name = "s09o_pilot_rejected"
    dsn = _make_db(name)
    try:
        bundle = s09_pilot.run_study(
            dsn, tmp_path, gateway=RoutingProvider(REJECTED_POLICY))
        assert bundle["construction"]["P1"]["status"] == "rejected"
        assert bundle["construction"]["P1"]["disposition"] == "rejected"
        assert bundle["construction"]["P1"]["release_id"] is None
        assert bundle["report"]["complete"] is False
        assert "P1" in bundle["report"]["incomplete_arms"]
        assert {record["executed"] for record in bundle["use_records"]
                if record["study_arm"] == "P1"} == {"unavailable"}
        assert s09_verify.verify_bundle(bundle)["status"] == "fail"
    finally:
        _drop_db(name)


def test_controlled_http_adapter_carries_bound_policy_bytes(tmp_path, monkeypatch):
    from scripts import s09_pilot
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(
                int(self.headers["Content-Length"])))
            seen.append(payload)
            prompt = str(payload.get("input", ""))
            source = (s09_pilot.P1_POLICY_SOURCE
                      if "Write one python policy" in prompt else METHOD)
            body = json.dumps({"output": [{"type": "message", "content": [{
                "type": "output_text",
                "text": json.dumps({"entry": source, "notes": "http"})}]}],
                "usage": {"input_tokens": 1, "output_tokens": 1}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            return

    name = "s09o_pilot_http"
    dsn = _make_db(name)
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("S09_CONTROLLED_GATEWAY_ENDPOINT",
                           "http://127.0.0.1:%d" % server.server_port)
        bundle = s09_pilot.run_study(
            dsn, tmp_path, gateway_mode="controlled", model="pilot-http")
        assert bundle["freeze"]["config"]["adapter"].endswith(
            "HttpGatewayAdapter")
        assert sum("Write one python policy" in str(item.get("input", ""))
                   for item in seen) == 2
        for arm in ("P1", "P2"):
            entry = bundle["construction"][arm]
            assert entry["freeze"]["candidate_digest"] == entry["bound_digest"]
            assert entry["assessment"]["candidate_digest"] == entry[
                "bound_digest"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        _drop_db(name)


def test_export_verifies_offline_without_database_or_provider(full_bundle):
    bundle, out = full_bundle
    from scripts import s09_verify
    assert s09_verify.verify_bundle_dir(out)["status"] == "pass"
    proc = subprocess.run(
        [os.fspath(Path(os.sys.executable)),
         os.fspath(ROOT / "scripts" / "s09_verify.py"), os.fspath(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["status"] == "pass"
    assert hashlib.sha256(bundle["construction"]["P1"][
        "policy_source"].encode()).hexdigest() == \
        bundle["construction"]["P1"]["candidate_digest"]


def test_same_doubles_produce_same_report(tmp_path_factory):
    from scripts import s09_pilot
    names = ("s09o_pilot_rerun_a", "s09o_pilot_rerun_b")
    bundles = []
    try:
        for index, name in enumerate(names):
            dsn = _make_db(name)
            out = tmp_path_factory.mktemp("rerun-%d" % index)
            bundles.append(s09_pilot.run_study(
                dsn, out, gateway=RoutingProvider(
                    s09_pilot.P1_POLICY_SOURCE)))
    finally:
        for name in names:
            _drop_db(name)
    assert bundles[0]["report"] == bundles[1]["report"]
