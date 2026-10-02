from __future__ import annotations

import contextlib
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
TOKEN = "o-pilot"
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


def _database_name(dsn):
    from urllib.parse import urlparse
    parsed = urlparse(dsn)
    if parsed.scheme:
        return (parsed.path or "/").lstrip("/")
    fields = dict(field.split("=", 1) for field in dsn.split() if "=" in field)
    return fields.get("dbname", "").strip("'\"")


@contextlib.contextmanager
def _store(token: str):
    """One store this run owns, on whichever cluster the operator named.

    A fixed name is shared state on the cluster, so a sibling run's teardown
    destroys the store this one is still writing to. The name carries a
    per-run token, so only the name this run minted is ever dropped.
    """
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = iso.create_disposable_db(token, admin_dsn=admin_dsn,
                                        migrations_dir=MIGRATIONS)
    try:
        yield database
    finally:
        iso.drop_disposable_db(database, admin_dsn=admin_dsn)


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
    with _store(TOKEN) as database:
        out = tmp_path_factory.mktemp("full")
        yield s09_pilot.run_study(
            database.dsn, out, namespace_token="o1",
            gateway=RoutingProvider(s09_pilot.P1_POLICY_SOURCE)), out


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


def test_p0_has_no_release_and_uncovered_domains_refuse(full_bundle):
    """A software-scoped policy cannot answer graph, and now says so.

    This used to assert `incumbent`, the silent fallback this campaign
    removed. The graph records are refused instead, which is the honest
    answer: a method scoped to software is not a method for graph.
    """
    bundle, _out = full_bundle
    assert all(row["policy_release"] is None and row["release_id"] is None
               for row in bundle["assessment"] if row["arm"] == "P0")
    for arm in ("P1", "P2"):
        graph = [row for row in bundle["use_records"]
                 if row["study_arm"] == arm and row["domain"] == "graph"]
        assert len(graph) == 4
        assert {row["executed"] for row in graph} == {"refused"}
        assert all(row["status"] == "refused" for row in graph)
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
    with _store(TOKEN) as database:
        bundle = s09_pilot.run_study(
            database.dsn, tmp_path, namespace_token="o2",
            gateway=RoutingProvider(REJECTED_POLICY))
    assert bundle["construction"]["P1"]["status"] == "rejected"
    assert bundle["construction"]["P1"]["disposition"] == "rejected"
    assert bundle["construction"]["P1"]["release_id"] is None
    assert bundle["report"]["complete"] is False
    assert "P1" in bundle["report"]["incomplete_arms"]
    assert {record["executed"] for record in bundle["use_records"]
            if record["study_arm"] == "P1"} == {"unavailable"}
    assert s09_verify.verify_bundle(bundle)["status"] == "fail"


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

    with _store(TOKEN) as database:
        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                monkeypatch.setenv(
                    "S09_CONTROLLED_GATEWAY_ENDPOINT",
                    "http://127.0.0.1:%d" % server.server_port)
                bundle = s09_pilot.run_study(
                    database.dsn, tmp_path, namespace_token="o2",
                    gateway_mode="controlled", model="pilot-http")
            finally:
                server.shutdown()
                thread.join(timeout=5)
    assert bundle["freeze"]["config"]["adapter"].endswith(
        "HttpGatewayAdapter")
    assert sum("Write one python policy" in str(item.get("input", ""))
               for item in seen) == 2
    for arm in ("P1", "P2"):
        entry = bundle["construction"][arm]
        assert entry["freeze"]["candidate_digest"] == entry["bound_digest"]
        assert entry["assessment"]["candidate_digest"] == entry[
            "bound_digest"]


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
    bundles = []
    for index in range(2):
        with _store(TOKEN) as database:
            out = tmp_path_factory.mktemp("rerun-%d" % index)
            bundles.append(s09_pilot.run_study(
                database.dsn, out, namespace_token="o3",
                gateway=RoutingProvider(s09_pilot.P1_POLICY_SOURCE)))
    assert bundles[0]["report"] == bundles[1]["report"]


def test_a_second_study_never_reuses_this_files_store(full_bundle):
    """This file runs a full study per store, so its store must be its own.

    A fixed name is shared state on the cluster: a sibling run of this file
    destroys the store this one is still writing to, and the failure reads
    as a product defect in the study rather than as the collision it is.
    The name carries a per-run token, so only a name this run minted is ever
    dropped, and a second fixture can never observe the first one's database.
    """
    from experiments.ad01 import s09_run_isolation as iso

    with _store(TOKEN) as database:
        name = database.name
        assert name.startswith(iso.DB_PREFIX + "_"), name
        assert TOKEN in name, name
        assert _database_name(database.dsn) == name, name

    again = iso.create_disposable_db(TOKEN, migrations_dir=MIGRATIONS)
    try:
        assert again.name != name
        assert TOKEN in again.name, again.name
    finally:
        iso.drop_disposable_db(again)
