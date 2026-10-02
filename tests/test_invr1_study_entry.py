from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

DISTINCTIVE = "INV-R1-DISTINCTIVE-7f3a9c"


def _dsn_for(name: str) -> str:
    return f"dbname={name} host=/var/run/postgresql user=ubuntu"


def _ensure_db(name: str) -> str:
    subprocess.run(["createdb", "-h", "/var/run/postgresql", name],
                   capture_output=True)
    dsn = _dsn_for(name)
    from settlement import db
    db.apply_migrations(dsn, ROOT / "migrations")
    return dsn


def _drop_db(name: str) -> None:
    subprocess.run(["dropdb", "-h", "/var/run/postgresql", name],
                   capture_output=True)


def _prepare_disposable(dsn: str) -> None:
    assert "inv_r1_" in dsn
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(dsn, ROOT / "migrations")
    E.designate_db(dsn, kind="disposable",
                   purpose="INV-R1 test setup")
    E.prepare_disposable_db(dsn, ROOT / "migrations")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps({"data": []}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {}
        if self.path.endswith("/responses"):
            inp = payload.get("input", "")
            text_blob = inp if isinstance(inp, str) else json.dumps(inp)
            if "Reply with ONLY one JSON object" in text_blob or \
                    "diagnose" in text_blob or "develop" in text_blob:
                task_id = "ad01-w0-dev-sw-00"
                try:
                    import re
                    found = re.findall(r"ad01-[\w\-]+", text_blob)
                    if found:
                        task_id = found[0]
                except Exception:
                    pass
                inner = json.dumps({
                    "basis_references": [f"obs-{task_id}-seed"],
                    "question": f"develop {task_id} {DISTINCTIVE}",
                    "next_action": {"kind": "development",
                                    "diagnostic": "software",
                                    "task_id": task_id,
                                    "max_queries": 1},
                    "requested_resources": {"diagnostic_queries": 1}})
            else:
                from experiments.doubles import construction_text
                inner = construction_text()
            body = json.dumps({
                "status": "completed",
                "output": [{"type": "message",
                            "content": [{"type": "output_text",
                                         "text": inner}]}],
                "usage": {"input_tokens": 13, "output_tokens": 9},
                "model": payload.get("model", "")}).encode()
        else:
            messages = payload.get("messages", [])
            text_blob = json.dumps(messages)
            if "Reply with ONLY one JSON object" in text_blob:
                import re
                task_id = "ad01-w0-dev-sw-00"
                try:
                    found = re.findall(r"ad01-[\w\-]+", text_blob)
                    if found:
                        task_id = found[0]
                except Exception:
                    pass
                inner = json.dumps({
                    "basis_references": [f"obs-{task_id}-seed"],
                    "question": f"develop {task_id} {DISTINCTIVE}",
                    "next_action": {"kind": "development",
                                    "diagnostic": "software",
                                    "task_id": task_id,
                                    "max_queries": 1},
                    "requested_resources": {"diagnostic_queries": 1}})
            else:
                from experiments.doubles import construction_text
                inner = construction_text()
            body = json.dumps({
                "choices": [{"message": {"content": inner},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 13, "completion_tokens": 9,
                          "charge_units": 5, "charge_scale": 1000},
                "model": payload.get("model", "")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(server: HTTPServer) -> None:
    server.serve_forever(poll_interval=0.05)


def test_live_provider_distinctive_response_traces_to_effect(tmp_path):
    import scripts.inv01_study as S
    name = f"inv_r1_live_{os.getpid()}_01"
    dsn = _ensure_db(name)
    try:
        _prepare_disposable(dsn)
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=_serve, args=(server,),
                                  daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{port}"
        env = dict(os.environ)
        env["SETTLEMENT_GATEWAY_ENDPOINT"] = endpoint
        env["SETTLEMENT_GATEWAY_KEY"] = "test-key-not-secret"
        env["AD01_REASONING_EFFORT"] = "low"
        old_endpoint = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT")
        old_key = os.environ.get("SETTLEMENT_GATEWAY_KEY")
        old_effort = os.environ.get("AD01_REASONING_EFFORT")
        os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = endpoint
        os.environ["SETTLEMENT_GATEWAY_KEY"] = "test-key-not-secret"
        os.environ["AD01_REASONING_EFFORT"] = "low"
        try:
            out = tmp_path / "study"
            rc = S.main(["--dsn", dsn, "--out", str(out),
                         "--agenda-authorized", "2000000",
                         "--study-root", "inv-r1-live",
                         "--provider", "live",
                         "--model", "review-live-model",
                         "--deadline-s", "600",
                         "--max-trajectories", "1",
                         "--max-boundaries", "1"])
        finally:
            if old_endpoint is None:
                os.environ.pop("SETTLEMENT_GATEWAY_ENDPOINT", None)
            else:
                os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = old_endpoint
            if old_key is None:
                os.environ.pop("SETTLEMENT_GATEWAY_KEY", None)
            else:
                os.environ["SETTLEMENT_GATEWAY_KEY"] = old_key
            if old_effort is None:
                os.environ.pop("AD01_REASONING_EFFORT", None)
            else:
                os.environ["AD01_REASONING_EFFORT"] = old_effort
            server.shutdown()
            thread.join(timeout=5)
        assert rc == 0
        from settlement import db
        with db.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT content FROM receipts"
                            " WHERE content->>'text' LIKE %s",
                            (f"%{DISTINCTIVE}%",))
                rows = cur.fetchall()
                conn.commit()
        assert len(rows) >= 1
        study_doc = json.loads((out / "study.json").read_text())
        assert study_doc["provider"] == "live"
        assert study_doc["model"] == "review-live-model"
        assert study_doc["study_root"] == "inv-r1-live"
        assert study_doc["effective_config"]["reasoning_effort"] == "low"
        assert "sk-" not in json.dumps(study_doc)
    finally:
        _drop_db(name)


def _op_count(dsn: str) -> int:
    from settlement import db
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM operations")
            count = cur.fetchone()[0]
            conn.commit()
    return int(count)


def _authority_count(dsn: str) -> int:
    from settlement import db
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM study_authority")
            count = cur.fetchone()[0]
            conn.commit()
    return int(count)


def test_missing_live_requirements_refuse_without_recording(tmp_path):
    import scripts.inv01_study as S
    name = f"inv_r1_refuse_{os.getpid()}_02"
    dsn = _ensure_db(name)
    try:
        _prepare_disposable(dsn)
        old_endpoint = os.environ.pop("SETTLEMENT_GATEWAY_ENDPOINT", None)
        old_key = os.environ.pop("SETTLEMENT_GATEWAY_KEY", None)
        old_effort = os.environ.get("AD01_REASONING_EFFORT")
        os.environ["AD01_REASONING_EFFORT"] = "low"
        try:
            out = tmp_path / "refuse-no-endpoint"
            rc = S.main(["--dsn", dsn, "--out", str(out),
                         "--agenda-authorized", "2000000",
                         "--study-root", "inv-r1-refuse",
                         "--provider", "live",
                         "--model", "review-live-model",
                         "--deadline-s", "600",
                         "--max-trajectories", "1",
                         "--max-boundaries", "1"])
            assert rc == 2
            assert _op_count(dsn) == 0
            os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = "http://127.0.0.1:9"
            rc = S.main(["--dsn", dsn, "--out", str(out),
                         "--agenda-authorized", "2000000",
                         "--study-root", "inv-r1-refuse",
                         "--provider", "live",
                         "--model", "inv01-study-double",
                         "--deadline-s", "600",
                         "--max-trajectories", "1",
                         "--max-boundaries", "1"])
            assert rc == 2
            assert _op_count(dsn) == 0
        finally:
            if old_endpoint is None:
                os.environ.pop("SETTLEMENT_GATEWAY_ENDPOINT", None)
            else:
                os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = old_endpoint
            if old_key is None:
                os.environ.pop("SETTLEMENT_GATEWAY_KEY", None)
            else:
                os.environ["SETTLEMENT_GATEWAY_KEY"] = old_key
            if old_effort is None:
                os.environ.pop("AD01_REASONING_EFFORT", None)
            else:
                os.environ["AD01_REASONING_EFFORT"] = old_effort
        from settlement import db
        with db.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM receipts"
                            " WHERE content->'model_meta'->>'simulated' = 'true'")
                simulated = cur.fetchone()[0]
                conn.commit()
        assert simulated == 0
    finally:
        _drop_db(name)


def test_restart_keeps_single_root_and_consumption(tmp_path):
    import scripts.inv01_study as S
    name = f"inv_r1_restart_{os.getpid()}_03"
    dsn = _ensure_db(name)
    try:
        _prepare_disposable(dsn)
        old_effort = os.environ.get("AD01_REASONING_EFFORT")
        os.environ["AD01_REASONING_EFFORT"] = "low"
        try:
            out = tmp_path / "restart"
            rc = S.main(["--dsn", dsn, "--out", str(out),
                         "--agenda-authorized", "2000000",
                         "--study-root", "inv-r1-restart",
                         "--provider", "recording",
                         "--model", "inv01-study-double",
                         "--deadline-s", "600",
                         "--max-trajectories", "1",
                         "--max-boundaries", "1"])
            assert rc == 0
            assert _authority_count(dsn) == 1
            first_ops = _op_count(dsn)
            assert first_ops > 0
            from settlement import db
            with db.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT wall_deadline_at, consumed_model_calls,"
                                " consumed_construction_calls, authorized,"
                                " deadline_s FROM inv_r1_study_runs"
                                " WHERE study_root = %s",
                                ("inv-r1-restart",))
                    before = cur.fetchone()
                    conn.commit()
            out2 = tmp_path / "restart2"
            rc = S.main(["--dsn", dsn, "--out", str(out2),
                         "--agenda-authorized", "2000000",
                         "--study-root", "inv-r1-restart",
                         "--provider", "recording",
                         "--model", "inv01-study-double",
                         "--deadline-s", "600",
                         "--max-trajectories", "1",
                         "--max-boundaries", "1"])
            assert rc == 0
            assert _authority_count(dsn) == 1
            assert _op_count(dsn) == first_ops
            with db.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT wall_deadline_at, consumed_model_calls,"
                                " consumed_construction_calls, authorized,"
                                " deadline_s FROM inv_r1_study_runs"
                                " WHERE study_root = %s",
                                ("inv-r1-restart",))
                    after = cur.fetchone()
                    conn.commit()
            assert before == after
            study_doc = json.loads((out2 / "study.json").read_text())
            assert study_doc["study_root"] == "inv-r1-restart"
            assert study_doc["grant"] == 2000000
        finally:
            if old_effort is None:
                os.environ.pop("AD01_REASONING_EFFORT", None)
            else:
                os.environ["AD01_REASONING_EFFORT"] = old_effort
    finally:
        _drop_db(name)


def test_expired_deadline_and_exhausted_caps_do_zero_effects(tmp_path):
    import scripts.inv01_study as S
    name = f"inv_r1_zero_{os.getpid()}_04"
    dsn = _ensure_db(name)
    try:
        _prepare_disposable(dsn)
        old_effort = os.environ.get("AD01_REASONING_EFFORT")
        os.environ["AD01_REASONING_EFFORT"] = "low"
        try:
            out = tmp_path / "zero"
            rc = S.main(["--dsn", dsn, "--out", str(out),
                         "--agenda-authorized", "2000000",
                         "--study-root", "inv-r1-zero",
                         "--provider", "recording",
                         "--model", "inv01-study-double",
                         "--deadline-s", "600",
                         "--max-trajectories", "1",
                         "--max-boundaries", "1"])
            assert rc == 0
            before_ops = _op_count(dsn)
            assert before_ops > 0
            from settlement import db
            with db.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE inv_r1_study_runs"
                                " SET wall_deadline_at = now() - interval '1 hour'"
                                " WHERE study_root = %s",
                                ("inv-r1-zero",))
                conn.commit()
            out_expired = tmp_path / "zero-expired"
            rc = S.main(["--dsn", dsn, "--out", str(out_expired),
                         "--agenda-authorized", "2000000",
                         "--study-root", "inv-r1-zero",
                         "--provider", "recording",
                         "--model", "inv01-study-double",
                         "--deadline-s", "600",
                         "--max-trajectories", "1",
                         "--max-boundaries", "1"])
            assert rc == 2
            assert _op_count(dsn) == before_ops
            with db.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE inv_r1_study_runs"
                                " SET wall_deadline_at = now() + interval '1 hour',"
                                " consumed_model_calls = 360,"
                                " consumed_construction_calls = 24"
                                " WHERE study_root = %s",
                                ("inv-r1-zero",))
                conn.commit()
            out_exhausted = tmp_path / "zero-exhausted"
            rc = S.main(["--dsn", dsn, "--out", str(out_exhausted),
                         "--agenda-authorized", "2000000",
                         "--study-root", "inv-r1-zero",
                         "--provider", "recording",
                         "--model", "inv01-study-double",
                         "--deadline-s", "600",
                         "--max-trajectories", "1",
                         "--max-boundaries", "1"])
            assert rc == 2
            assert _op_count(dsn) == before_ops
        finally:
            if old_effort is None:
                os.environ.pop("AD01_REASONING_EFFORT", None)
            else:
                os.environ["AD01_REASONING_EFFORT"] = old_effort
    finally:
        _drop_db(name)


def test_cap_sheet_derived_and_billing_split_and_no_replenish(tmp_path):
    import scripts.inv01_study as S
    name = f"inv_r1_caps_{os.getpid()}_05"
    dsn = _ensure_db(name)
    try:
        _prepare_disposable(dsn)
        old_effort = os.environ.get("AD01_REASONING_EFFORT")
        os.environ["AD01_REASONING_EFFORT"] = "low"
        try:
            out = tmp_path / "caps"
            rc = S.main(["--dsn", dsn, "--out", str(out),
                         "--agenda-authorized", "2000000",
                         "--study-root", "inv-r1-caps",
                         "--provider", "recording",
                         "--model", "inv01-study-double",
                         "--deadline-s", "600",
                         "--max-trajectories", "1",
                         "--max-boundaries", "1"])
            assert rc == 0
            sheet = json.loads((out / "cap_sheet.json").read_text())
            assert sheet["study"]["max_model_calls"] == 360
            assert sheet["study"]["max_construction_calls"] == 24
            assert sheet["per_trajectory"]["max_model_calls"] == 60
            assert sheet["per_trajectory"]["max_construction_calls"] == 4
            assert sheet["per_trajectory"]["max_boundaries"] == 6
            assert sheet["accounting_kinds"] == [
                "estimate", "measured", "internal_charge",
                "provider_billing"]
            assert sheet["derivation"]["effective_config"]["model"] == \
                "inv01-study-double"
            assert sheet["derivation"]["effective_config"]["provider"] == \
                "recording"
            assert sheet["study"]["max_witness_queries"] == 960
            assert sheet["study"]["max_execution_units"] == 5328
            checked = S.check_caps_against_runner(sheet)
            assert checked["problems"] == []
            study_doc = json.loads((out / "study.json").read_text())
            assert study_doc["panel"]["freeze_id"] == "ad01"
            assert study_doc["panel"]["freeze_digest"]
            assert study_doc["grant"] == 2000000
            accounting = json.loads((out / "accounting.json").read_text())
            assert accounting["total"]["model_calls"] <= 360
            assert accounting["total"]["construction_calls"] <= 24
            assert "measured_from" in accounting
            from settlement import db
            with db.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COALESCE(SUM((r.content->'usage'->>'input_tokens')::int),0),"
                        " COALESCE(SUM((r.content->'usage'->>'output_tokens')::int),0),"
                        " COALESCE(SUM((r.content->'usage'->>'charge_units')::int) FILTER"
                        " (WHERE r.content->'usage'->>'billed'='true'),0)"
                        " FROM receipts r JOIN operations o ON o.id=r.operation_id"
                        " WHERE o.allocation_id LIKE 'ad01-campaign-%'")
                    measured_in, measured_out, billed = cur.fetchone()
                    conn.commit()
            assert int(measured_in) + int(measured_out) > 0
            assert int(billed) == 0
            before_ops = _op_count(dsn)
            with db.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT wall_deadline_at FROM inv_r1_study_runs"
                                " WHERE study_root=%s", ("inv-r1-caps",))
                    wall_before = cur.fetchone()[0]
                    conn.commit()
            out_grant = tmp_path / "caps-grant-change"
            rc = S.main(["--dsn", dsn, "--out", str(out_grant),
                         "--agenda-authorized", "3000000",
                         "--study-root", "inv-r1-caps",
                         "--provider", "recording",
                         "--model", "inv01-study-double",
                         "--deadline-s", "600",
                         "--max-trajectories", "1",
                         "--max-boundaries", "1"])
            assert rc == 2
            assert _op_count(dsn) == before_ops
            out_deadline = tmp_path / "caps-deadline-change"
            rc = S.main(["--dsn", dsn, "--out", str(out_deadline),
                         "--agenda-authorized", "2000000",
                         "--study-root", "inv-r1-caps",
                         "--provider", "recording",
                         "--model", "inv01-study-double",
                         "--deadline-s", "900",
                         "--max-trajectories", "1",
                         "--max-boundaries", "1"])
            assert rc == 2
            assert _op_count(dsn) == before_ops
            with db.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT wall_deadline_at FROM inv_r1_study_runs"
                                " WHERE study_root=%s", ("inv-r1-caps",))
                    wall_after = cur.fetchone()[0]
                    conn.commit()
            assert wall_before == wall_after
        finally:
            if old_effort is None:
                os.environ.pop("AD01_REASONING_EFFORT", None)
            else:
                os.environ["AD01_REASONING_EFFORT"] = old_effort
    finally:
        _drop_db(name)
