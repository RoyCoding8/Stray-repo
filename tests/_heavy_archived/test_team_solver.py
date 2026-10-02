"""Doubled gates for the live solver loop (solver.py).

These tests use a scripted gateway and the real broker/store/team stack on
real Postgres. They prove the mechanism (constructor bytes flow to scored
bytes; substitution/disconnect/incompatible controls behave); liveness
itself is proven by the vertical-path live run, not by these doubles.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from settlement import broker, store
from settlement.common import Command
from settlement.gateway import (GatewayError, GatewayErrorKind,
                                ModelResponse, Usage)
from settlement.launcher_local import LocalLauncher

from experiments.team01 import oracle, solver


@pytest.fixture()
def live_db():
    from settlement import db

    dsn = os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn:
        pytest.skip("SETTLEMENT_TEST_DSN is not configured")
    db.apply_migrations(dsn, ROOT / "migrations")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                " AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{row[0]}" CASCADE')
        conn.commit()
    yield dsn


class ScriptedGateway:
    """One queued reply per inference call, in order."""

    def __init__(self, texts: list, usage=None) -> None:
        self.texts = list(texts)
        self.usage = usage or Usage(input_tokens=150, output_tokens=400)
        self.requests: list = []

    def check_discovery(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.requests.append(request)
        if not self.texts:
            return GatewayError(GatewayErrorKind.TRANSPORT,
                                "script exhausted", False,
                                request.operation_id)
        return ModelResponse(request.operation_id, self.texts.pop(0),
                             {"scripted": True}, self.usage, "stop")

    def cancel(self, operation_id):
        return True


def _snapshot_task(task_id: str = "team01-t01") -> dict:
    tdir = oracle.TASKS / task_id
    snap = {"spec.json": (tdir / "spec.json").read_text()}
    for mod in sorted((tdir / "src").glob("*.py")):
        snap["src/" + mod.name] = mod.read_text()
    return snap


GOOD_T01 = {
    "src/app.py": None,  # filled from snapshot in each test
    "src/numops.py": (
        "def summarize(op, numbers):\n"
        "    if op == \"sum\":\n"
        "        return sum(numbers)\n"
        "    if op == \"span\":\n"
        "        return round(sum(numbers, 0) / len(numbers), 2) if numbers else 0\n"
        "    if op == \"rmean\":\n"
        "        return sum(1 for n in numbers if n > 0)\n"
        "    if op == \"count_pos\":\n"
        "        return sum(numbers, 0)\n"
        "    raise ValueError(op)\n"),
    "src/textops.py": (
        "def transform(op, texts):\n"
        "    if op == \"strip_lower\":\n"
        "        return [t.strip().lower() for t in texts]\n"
        "    if op == \"dedup_sort\":\n"
        "        return [t[::-1] for t in texts]\n"
        "    if op == \"reverse\":\n"
        "        return [t.strip().lower() for t in texts]\n"
        "    if op == \"upper\":\n"
        "        return sorted(set(texts))\n"
        "    raise ValueError(op)\n"),
}

WRONG_T01 = {
    "src/numops.py": (
        "def summarize(op, numbers):\n"
        "    if op == \"sum\":\n"
        "        return len(numbers)\n"
        "    raise ValueError(op)\n"),
    "src/textops.py": (
        "def transform(op, texts):\n"
        "    if op == \"strip_lower\":\n"
        "        return [t.strip().lower() for t in texts]\n"
        "    raise ValueError(op)\n"),
}


def _envelope(files: dict) -> str:
    return json.dumps({"files": files, "notes": "scripted repair"})


def _good_files():
    snap = _snapshot_task()
    files = dict(GOOD_T01)
    files["src/app.py"] = snap["src/app.py"]
    return files


def _wrong_files():
    snap = _snapshot_task()
    files = dict(WRONG_T01)
    files["src/app.py"] = snap["src/app.py"]
    return files


def _launchers(runs_root: Path) -> dict:
    return {"local-process": LocalLauncher(str(runs_root))}


def _tag(prefix: str) -> str:
    # Unique per invocation: reruns must not share the fixed 100k
    # per-episode allocation, whose retained reservations accumulate
    # across runs and eventually refuse new operations.
    import uuid

    return "%s-%s" % (prefix, uuid.uuid4().hex[:6])


# --- envelope parsing (no DB) --------------------------------------------

def test_parse_accepts_exact_owned_set():
    owned = ["src/a.py", "src/b.py"]
    out = solver.parse_ctor_envelope(
        _envelope({"src/a.py": "x=1\n", "src/b.py": "y=2\n"}), owned)
    assert out["error"] == "" and set(out["files"]) == set(owned)


def test_parse_rejects_empty_notjson_badshape_paths():
    owned = ["src/a.py"]
    assert solver.parse_ctor_envelope("", owned)["files"] is None
    assert solver.parse_ctor_envelope("not json{{", owned)["files"] is None
    assert solver.parse_ctor_envelope(json.dumps({"nope": 1}),
                                      owned)["files"] is None
    assert solver.parse_ctor_envelope(_envelope({"src/b.py": "x"}),
                                      owned)["error"].startswith(
                                          "path-mismatch")


def test_parse_accepts_fenced_envelope():
    owned = ["src/a.py"]
    out = solver.parse_ctor_envelope(
        "```json\n%s\n```" % _envelope({"src/a.py": "x=1\n"}), owned)
    assert out["error"] == ""


# --- live-path mechanism on real PG --------------------------------------

def test_S_repairs_t01_with_constructor_bytes(live_db, tmp_path):
    gw = ScriptedGateway([_envelope(_good_files()),
                          json.dumps({"verdict": "keep",
                                      "notes": "checked edges"})])
    record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-s"), task_id="team01-t01", arm="S")
    assert gw.requests, "constructor never invoked the gateway"
    assert record["outcome"] == "success", json.dumps(
        {k: record[k] for k in ("public", "protected", "join")})[:800]
    assert record["protected"]["failed"] == 0
    assert record["simulated"] is False
    digest = solver.team.output_digest(_good_files())
    assert record["submitted_digests"]["w1"] == digest
    prompts = [t.get("prompt", "") for t in record["constructor_ops"]
               if t.get("kind") == "ctor"]
    assert prompts and all("fam-" not in p for p in prompts)
    assert all("apparatus-overlay" not in p for p in prompts)


def test_substitution_flows_to_scored_tree(live_db, tmp_path):
    gw = ScriptedGateway([_envelope(_good_files()),
                          json.dumps({"verdict": "keep",
                                      "notes": "checked"})])
    record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-sub"), task_id="team01-t01", arm="S",
        probe="substitution", substitute={"w1": _wrong_files()})
    assert record["outcome"] == "failure"
    assert record["protected"]["failed"] > 0
    sub = record["controls"]["substituted"]["w1"]
    assert sub["constructor_digest"] != sub["substitute_digest"]
    assert sub["substitute_digest"] == solver.team.output_digest(
        _wrong_files())
    assert record["submitted_digests"]["w1"] == sub["substitute_digest"]


def test_disconnect_refuses_without_artifact(live_db, tmp_path):
    gw = ScriptedGateway([_envelope(_good_files())])
    record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-disc"), task_id="team01-t01", arm="S",
        probe="disconnect", disconnect=["w1"])
    assert record["outcome"] == "refused"
    assert record["frozen_digest"] is None
    assert "w1" in record["reason"]
    assert record["usage"] == {"in": 150, "out": 400}
    assert record["costs"]["model_tokens"] == {"in": 150, "out": 400}
    assert record["costs"]["model_invocations"] == record["model_calls"]


def _node_envelope(path: str, content: str) -> str:
    return json.dumps({"files": {path: content}, "notes": "scripted node"})


def test_incompatible_pair_repaired_or_refused(live_db, tmp_path):
    snap = _snapshot_task()
    renamed = snap["src/textops.py"].replace("def transform(",
                                             "def xform(", 1)
    fixed_numops = GOOD_T01["src/numops.py"]
    fixed_textops = GOOD_T01["src/textops.py"]
    gw = ScriptedGateway([
        json.dumps({"shape": "decompose",
                    "rationale": "two modules, split the work"}),
        _node_envelope("src/numops.py", fixed_numops),
        _node_envelope("src/textops.py", fixed_textops),
        _node_envelope("src/numops.py", fixed_numops),
        _node_envelope("src/textops.py", fixed_textops),
    ])
    record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-inc"), task_id="team01-t01", arm="T",
        probe="incompatible",
        authored_nodes={"w2": {"files": {"src/textops.py": renamed},
                               "label": "diagnostic: renamed entry point"}},
        repair_rounds=1)
    assert "w2" in record["controls"]["authored"]
    assert record["shape"] == "decompose"
    assert record["outcome"] == "success"
    assert record["repairs"] >= 1
    assert record["protected"]["failed"] == 0


def test_P_selects_passing_attempt(live_db, tmp_path):
    snap = _snapshot_task()
    whole_good = dict(snap)
    whole_good.update({k: v for k, v in _good_files().items()
                       if k.startswith("src/")})
    whole_wrong = dict(snap)
    whole_wrong.update({k: v for k, v in _wrong_files().items()
                        if k.startswith("src/")})
    gw = ScriptedGateway([_envelope(whole_good), _envelope(whole_wrong)])
    record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-p"), task_id="team01-t01", arm="P")
    assert record["shape"] == "alternatives"
    assert record["outcome"] == "success", json.dumps(
        record["join"])[:500]
    assert record["join"]["passed"] is True
    assert record["protected"]["failed"] == 0
    assert record["submitted_digests"]["w1"] == \
        solver.team.output_digest(whole_good)
    assert record["join"]["assembly_note"] == "selected-w1"


def test_P_rejects_rewritten_spec(live_db, tmp_path):
    snap = _snapshot_task()
    rewritten = dict(snap)
    rewritten["spec.json"] = json.dumps({"num_op": "span",
                                         "text_op": "upper"})
    gw = ScriptedGateway([_envelope(rewritten), _envelope(rewritten)])
    record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-spec"), task_id="team01-t01", arm="P")
    assert record["outcome"] == "refused"
    assert "w1,w2" in record["reason"]


@pytest.mark.xfail(
    strict=True,
    reason="acquire2.py was never committed; executed source is unrecoverable "
           "(reports/workstreams/ec02-D.md). Recovery provenance: only orphaned "
           "bytecode survives. This test preserves the surviving API contract "
           "(build_template returning directive/error/digest) so recovered "
           "source lands against it.")
def test_build_returns_none_on_empty_replies(live_db, tmp_path):
    from experiments.team01 import acquire2
    gw = ScriptedGateway(["", "   "])
    nonce = _tag("tspec-acquire")
    store.seed_allocation(live_db, Command(
        request_id="%s-seed" % nonce,
        payload={"allocation_id": nonce, "domain": "cpu",
                 "authorized": 50000, "max_occupancy": 4}))
    record = {"task_id": "team01-t01", "arm": "S", "shape": "single",
              "outcome": "success", "probe": None, "repairs": 0,
              "public": {"passed": 4, "total": 4},
              "constructor_ops": [], "tool_ops": []}
    build = acquire2.build_template(
        live_db, gateway=gw, allocation_id=nonce, tag="tspec",
        dev_records=[record], evidence_root=tmp_path / "ev", attempt=1)
    assert build["directive"] is None
    assert build["error"] == "empty-output"
    assert "digest" not in build


def test_warm_T_without_directive_refuses(live_db, tmp_path):
    gw = ScriptedGateway([_envelope(_good_files())])
    record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-warm"), task_id="team01-t01", arm="warm-T",
        panel="dev", directive=None)
    assert record["outcome"] == "refused"
    assert "directive" in record["reason"]
    assert gw.requests == []


def test_directive_conditions_plan_and_nodes(live_db, tmp_path):
    snap = _snapshot_task()
    node_textops = {"src/textops.py": GOOD_T01["src/textops.py"]}
    node_numops = {"src/numops.py": GOOD_T01["src/numops.py"]}
    gw = ScriptedGateway([
        json.dumps({"shape": "decompose", "rationale": "split modules"}),
        _node_envelope("src/numops.py", node_numops["src/numops.py"]),
        _node_envelope("src/textops.py", node_textops["src/textops.py"]),
    ])
    directive = "Repair each module on its own; keep entry points."
    record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-dir"), task_id="team01-t01", arm="warm-T",
        panel="dev", directive=directive)
    assert record["outcome"] == "success"
    assert record["template_digest"] == solver.hashlib.sha256(
        directive.encode()).hexdigest()
    plans = [t for t in record["constructor_ops"]
             if t.get("kind") == "plan"]
    assert plans and plans[0]["directive_digest"] == \
        record["template_digest"]


def test_exhausted_gateway_refuses_without_scoring(live_db, tmp_path):
    gw = ScriptedGateway([])
    record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-exh"), task_id="team01-t01", arm="S")
    assert record["outcome"] == "refused"
    assert record["frozen_digest"] is None
    assert record["protected"] is None


def test_checker_rejects_empty_evidence_root(tmp_path):
    from experiments.team01 import checker
    report = checker.check_all(tmp_path / "empty")
    assert report["clean"] is False
    assert report["problems"]


def test_scored_tree_uses_only_submitted_bytes(live_db, tmp_path):
    gw = ScriptedGateway([_envelope(_good_files()),
                          json.dumps({"verdict": "keep", "notes": "ok"})])
    record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-flow"), task_id="team01-t01", arm="S")
    assert record["outcome"] == "success"
    allowed = {solver.team.output_digest(_good_files())}
    assert record["submitted_digests"]["w1"] in allowed
    ctor_digests = {t.get("files_digest") for t in record["constructor_ops"]
                    if t.get("files_digest")}
    assert record["submitted_digests"]["w1"] in ctor_digests


def test_replay_accepts_live_record_shapes(live_db, tmp_path):
    from experiments.team01 import checker
    gw = ScriptedGateway([_envelope(_good_files()),
                          json.dumps({"verdict": "keep", "notes": "ok"})])
    ok_record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-replay"), task_id="team01-t01", arm="S")
    assert ok_record["outcome"] == "success"
    assert isinstance(ok_record["receipts"], list)
    gw = ScriptedGateway([_envelope(_good_files())])
    ref_record = solver.run_live_repair_episode(
        live_db, gateway=gw, launchers=_launchers(tmp_path / "runs"),
        runs_root=tmp_path / "runs", evidence_root=tmp_path / "ev",
        tag=_tag("tsolv-replay"), task_id="team01-t01", arm="S",
        probe="disconnect", disconnect=["w1"])
    assert ref_record["outcome"] == "refused"
    replayed = checker.replay_panel(live_db, tmp_path / "ev")
    assert replayed["replayed"] == 2
    ok_where = "dev-S-team01-t01-1"
    assert not [m for m in replayed["mismatches"]
                if m.startswith(("rebound", "effect-without-receipt"))
                and ok_where in m]
    assert any("unbound-revision" in m and "dev-S-team01-t01-1" in m
               for m in replayed["mismatches"])
