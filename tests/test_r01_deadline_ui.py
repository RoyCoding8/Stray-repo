from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from settlement.gateway import GatewayErrorKind, ModelRequest


def _request(**overrides):
    args = {
        "model": "stub-model",
        "messages": ({"role": "user", "content": "hi"},),
        "max_output_tokens": 16,
        "deadline_ms": 1_000,
    }
    args.update(overrides)
    return ModelRequest(**args)


_OK_BODY = json.dumps(
    {
        "choices": [{"message": {"content": "trickle-answer"}, "finish_reason": "stop"}],
        "model": "stub-model",
        "usage": {"prompt_tokens": 7, "completion_tokens": 5},
    }
).encode()


class TrickleHandler(BaseHTTPRequestHandler):
    mode = "trickle"
    sleep_s = 6.0
    chunk_s = 0.06

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)
        if type(self).mode == "sleep":
            time.sleep(type(self).sleep_s)
            raw = _OK_BODY
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        raw = _OK_BODY
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        for i in range(0, len(raw), 1):
            time.sleep(type(self).chunk_s)
            try:
                self.wfile.write(raw[i : i + 1])
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return


def _trickle_server():
    from settlement import gateway_http

    server = ThreadingHTTPServer(("127.0.0.1", 0), TrickleHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    adapter = gateway_http.HttpGatewayAdapter(endpoint=endpoint, api_key="test-key")
    return adapter, server, thread


def test_trickle_response_hits_deadline_promptly():
    adapter, server, thread = _trickle_server()
    try:
        TrickleHandler.mode = "trickle"
        started = time.monotonic()
        result = adapter.infer(_request(deadline_ms=1_000))
        elapsed = time.monotonic() - started
        assert result.kind == GatewayErrorKind.TIMEOUT
        assert result.retryable is True
        assert elapsed < 5.0
    finally:
        server.shutdown()
        thread.join()


def test_injected_client_receives_per_request_timeout():
    adapter, server, thread = _trickle_server()
    try:
        TrickleHandler.mode = "sleep"
        TrickleHandler.sleep_s = 6.0
        adapter._client = httpx.Client(timeout=30.0)
        try:
            started = time.monotonic()
            result = adapter.infer(_request(deadline_ms=1_000))
            elapsed = time.monotonic() - started
        finally:
            adapter._client.close()
            adapter._client = None
        assert result.kind == GatewayErrorKind.TIMEOUT
        assert elapsed < 4.0
    finally:
        server.shutdown()
        thread.join()


def test_cancel_during_trickle_reports_unknown_outcome():
    adapter, server, thread = _trickle_server()
    try:
        TrickleHandler.mode = "trickle"
        request = _request(deadline_ms=30_000)
        outcome: list = []

        def run():
            outcome.append(adapter.infer(request))

        worker = threading.Thread(target=run, daemon=True)
        started = time.monotonic()
        worker.start()
        time.sleep(0.5)
        assert adapter.cancel(request.operation_id) is True
        worker.join(timeout=10.0)
        elapsed = time.monotonic() - started
        assert outcome, "infer did not return after cancellation"
        assert outcome[0].kind == GatewayErrorKind.CANCELLED
        assert outcome[0].retryable is False
        assert "unknown" in outcome[0].message
        assert adapter.cancel_status(request.operation_id) == "confirmed"
        assert elapsed < 5.0
    finally:
        server.shutdown()
        thread.join()


def _ui_client(migrated_db):
    import uuid

    from fastapi.testclient import TestClient

    from settlement import api, store
    from settlement.common import Command

    def cmd(payload: dict) -> Command:
        return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)

    dsn = migrated_db
    store.seed_allocation(dsn, cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    for iid in ("i1", "i2"):
        store.admit_commitment(dsn, cmd({"investigation_id": iid, "objective": f"objective-{iid}"}))
    store.acquire_work(dsn, cmd({"attempt_id": "w1", "investigation_id": "i1",
                                 "allocation_id": "a1"}))
    store.acquire_work(dsn, cmd({"attempt_id": "w2", "investigation_id": "i2",
                                 "allocation_id": "a1"}))
    from psycopg.types.json import Json

    with store.db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO observations (receipt_id, attempt_id, content)"
                        " VALUES ('o1', 'w1', %s), ('o2', 'w2', %s)",
                        (Json({"note": "evidence-i1"}), Json({"note": "evidence-i2"})))
            cur.execute("INSERT INTO claims (id, proposition) VALUES ('c1', %s), ('c2', %s)",
                        (Json({}), Json({})))
            cur.execute("INSERT INTO derivations (id, claim_id, procedure, result)"
                        " VALUES ('d1', 'c1', 'proc', %s), ('d2', 'c2', 'proc', %s)",
                        (Json({"verdict": "holds-i1"}), Json({"verdict": "holds-i2"})))
            cur.execute("INSERT INTO derivation_premises (derivation_id, group_id, premise_ref,"
                        " premise_kind) VALUES ('d1', 0, 'o1', 'observation'),"
                        " ('d2', 0, 'o2', 'observation')")
            cur.execute("INSERT INTO evidence_relations (src_ref, dst_ref, kind)"
                        " VALUES ('w1', 'c1', 'required-support'),"
                        " ('w2', 'c2', 'required-support')")
            cur.execute("INSERT INTO trial_protocols (id, candidate_version, reference_version,"
                        " evaluator_version, exclusions, uncertainty)"
                        " VALUES ('p1', 'cand-7', 'ref-3', 'eval-2', %s, %s)",
                        (Json(["bad-task"]), Json({"note": "n=4"})))
            cur.execute("INSERT INTO trial_assignments (id, protocol_id, task_id, task_group,"
                        " arm, blind_key) VALUES ('a-c1', 'p1', 't1', 'g', 'candidate', 'b1'),"
                        " ('a-c2', 'p1', 't2', 'g', 'candidate', 'b2'),"
                        " ('a-r1', 'p1', 't1', 'g', 'reference', 'b3'),"
                        " ('a-r2', 'p1', 't2', 'g', 'reference', 'b4')")
            cur.execute("INSERT INTO trial_results (assignment_id, outcome)"
                        " VALUES ('a-c1', 'success'), ('a-c2', 'failure'),"
                        " ('a-r1', 'success'), ('a-r2', 'success')")
            cur.execute("INSERT INTO expenditure_ledger (protocol_id, category, amount)"
                        " VALUES ('p1', 'evaluation', 42), ('p1', 'construction', 8)")
        conn.commit()
    app = api.create_app(dsn, gateway=None, token="test-token")
    return TestClient(app, headers={"x-operator-token": "test-token"})


def test_detail_poll_targets_current_view(migrated_db):
    client = _ui_client(migrated_db)
    for path, poll in (("/investigations/i1", "/investigations/i1"),
                       ("/learning", "/learning"),
                       ("/evidence", "/evidence"),
                       ("/capabilities", "/capabilities"),
                       ("/trials", "/trials")):
        body = client.get(path).text
        assert f'hx-get="{poll}"' in body, path
        assert 'hx-get="/"' not in body, path
    first = client.get("/investigations/i1").text
    assert "investigation i1" in first
    second = client.get("/investigations/i1").text
    assert "investigation i1" in second
    assert "objective-i1" in second


def test_investigations_show_distinct_evidence(migrated_db):
    client = _ui_client(migrated_db)
    one = client.get("/investigations/i1").text
    two = client.get("/investigations/i2").text
    for marker in ("evidence-i1", "holds-i1", "o1"):
        assert marker in one, marker
    for marker in ("evidence-i2", "holds-i2", "o2"):
        assert marker in two, marker
    for marker in ("evidence-i2", "holds-i2"):
        assert marker not in one, marker
    for marker in ("evidence-i1", "holds-i1"):
        assert marker not in two, marker


def test_learning_serves_stored_comparisons(migrated_db):
    from settlement import api as _api

    client = _ui_client(migrated_db)
    data = _api.learning_data(migrated_db)
    assert data["comparisons"], "learning must serve stored comparison results"
    comp = data["comparisons"][0]
    assert comp["candidate_version"] == "cand-7"
    assert comp["reference_version"] == "ref-3"
    body = client.get("/learning").text
    for marker in ("cand-7", "ref-3", "bad-task", "42"):
        assert marker in body, marker


def _seed_many_attempts(dsn, n=200, per_inv=50, tag="bulk"):
    import uuid

    from settlement import store
    from settlement.common import Command

    def cmd(payload: dict) -> Command:
        return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)

    store.seed_allocation(dsn, cmd({"allocation_id": f"{tag}-a1", "domain": "cpu",
                                    "authorized": 10_000_000, "max_occupancy": 10_000}))
    iids = []
    for i in range(n // per_inv):
        iid = f"{tag}-i{i}"
        store.admit_commitment(dsn, cmd({"investigation_id": iid, "objective": f"bulk-{i}"}))
        iids.append(iid)
    k = 0
    for iid in iids:
        for _ in range(per_inv):
            store.acquire_work(dsn, cmd({"attempt_id": f"{tag}-w{k}",
                                         "investigation_id": iid,
                                         "allocation_id": f"{tag}-a1"}))
            k += 1
    return iids


def _counted_dsn(monkeypatch):
    from settlement import db as _db

    counts = {"connects": 0, "executes": 0}
    real_connect = _db.connect

    class Cursor:
        def __init__(self, cur):
            self._cur = cur

        def execute(self, *args, **kwargs):
            counts["executes"] += 1
            return self._cur.execute(*args, **kwargs)

        def __enter__(self):
            self._cur.__enter__()
            return self

        def __exit__(self, *exc):
            return self._cur.__exit__(*exc)

        def __getattr__(self, name):
            return getattr(self._cur, name)

    class Conn:
        def __init__(self, conn):
            self._conn = conn

        def cursor(self, *args, **kwargs):
            return Cursor(self._conn.cursor(*args, **kwargs))

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, *exc):
            return self._conn.__exit__(*exc)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    def counting_connect(*args, **kwargs):
        counts["connects"] += 1
        return Conn(real_connect(*args, **kwargs))

    monkeypatch.setattr(_db, "connect", counting_connect)
    return counts


def test_overview_uses_bounded_projection(migrated_db, monkeypatch):
    from settlement import api as _api

    dsn = migrated_db
    _seed_many_attempts(dsn)
    counts = _counted_dsn(monkeypatch)
    view = _api.overview_data(dsn)
    assert view["attempt_total"] == 200
    assert len(view["attempts"]) <= 50
    assert set(view["next_decisions"]) == {a["id"] for a in view["attempts"]}
    assert counts["connects"] <= 6
    assert counts["executes"] <= 12


def test_overview_query_cost_independent_of_history(migrated_db, monkeypatch):
    from settlement import api as _api

    dsn = migrated_db
    _seed_many_attempts(dsn, n=20, per_inv=10, tag="small")
    counts = _counted_dsn(monkeypatch)
    small = _api.overview_data(dsn)
    assert len(small["attempts"]) == 20
    small_cost = (counts["connects"], counts["executes"])
    _seed_many_attempts(dsn, n=200, per_inv=50, tag="big")
    counts["connects"] = 0
    counts["executes"] = 0
    big = _api.overview_data(dsn)
    assert len(big["attempts"]) <= 50
    assert (counts["connects"], counts["executes"]) == small_cost


def test_shared_next_decision_matches_single_path(migrated_db):
    import uuid

    from settlement import agenda, store
    from settlement.common import Command

    dsn = migrated_db
    _seed_many_attempts(dsn, n=4, per_inv=2)
    store.prepare_operation(dsn, Command(request_id=f"req_{uuid.uuid4().hex[:12]}",
                                         payload={"operation_id": "bulk-op1",
                                                  "attempt_id": "bulk-w0",
                                                  "operation": {"effect": "note"}}))
    batch = agenda.next_decisions_for(dsn, ["bulk-w0", "bulk-w1", "bulk-missing"])
    assert batch["bulk-w0"] == agenda.next_decision_for(dsn, "bulk-w0") == "dispatch-bulk-op1"
    assert batch["bulk-w1"] == agenda.next_decision_for(dsn, "bulk-w1")
    assert batch["bulk-missing"] == "unknown-attempt"


def test_precancelled_operation_reports_unknown_outcome():
    adapter, server, thread = _trickle_server()
    try:
        request = _request(deadline_ms=30_000)
        adapter.cancel(request.operation_id)
        result = adapter.infer(request)
        assert result.kind == GatewayErrorKind.CANCELLED
        assert result.retryable is False
        assert "unknown" in result.message
        assert adapter.cancel_status(request.operation_id) == "confirmed"
    finally:
        server.shutdown()
        thread.join()
