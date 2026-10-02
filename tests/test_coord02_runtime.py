"""coord02 runtime path tests (lane R, EC-01/02/03/04/06/07/08).

Real PostgreSQL (ec02test_r) and real subprocesses throughout. Child
repair bytes here are labeled rejecting controls or fake-gateway
simulated bytes: there is no live grant in this environment
(no TEAM01_LIVE_API_KEY; unauthenticated inference is rejected), so the
FakeGatewayAdapter stands in for model generation and every authored
tree is labeled as such.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest

from psycopg.rows import dict_row

from experiments.coord02 import controller as C
from experiments.coord02 import policy_exec as P
from experiments.coord02 import schemas as S
from settlement import broker, capabilities, db, store, team
from settlement.common import Command, ResultCode
from settlement.gateway import FakeGatewayAdapter
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get("EC02_R_DSN",
                     "dbname=ec02test_r host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"
FAKE_LABEL = "fake-gateway-simulated (FakeGatewayAdapter; no live grant)"

BASE = {
    "pkg/__init__.py": "",
    "pkg/a.py": "MODE = 'X'\nVALUE = 1\n",
    "pkg/b.py": "MODE = 'X'\nVALUE = 2\n",
}
GOOD_A = {"pkg/a.py": "MODE = 'C'\nVALUE = 10\n"}
GOOD_B = {"pkg/b.py": "MODE = 'C'\nVALUE = 20\n"}
GOOD_WHOLE = {"pkg/__init__.py": "", **GOOD_A, **GOOD_B}
BAD_B = {"pkg/b.py": "MODE = 'X'\nVALUE = 20\n"}

CHECK_SRC = """import importlib.util
import json
import sys

asm = sys.argv[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, asm + "/pkg/" + name + ".py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

try:
    a = load("a")
    b = load("b")
    assert a.MODE == b.MODE, "mode mismatch %r vs %r" % (a.MODE, b.MODE)
    assert (a.VALUE, b.VALUE) == (10, 20), "values %r" % ((a.VALUE, b.VALUE),)
    print(json.dumps({"status": "ok", "data": {"mode": a.MODE}}))
except Exception as exc:
    print(json.dumps({"status": "error", "data": {"message": str(exc)}}))
"""

IFACE_TMPL = """import json
import sys
SNAP = __SNAP__
req = json.load(open(sys.argv[1]))
want = (req.get("input") or {}).get("path", "")
json.dump({"path": want, "content": SNAP.get(want)}, open(sys.argv[2], "w"))
"""

POLICY_TMPL = """import json
import sys
if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
    raise SystemExit(0)
req = json.load(open(sys.argv[1]))
STEPS = __STEPS__
n = (req.get("state") or {}).get("step", 0)
if n >= len(STEPS):
    n = len(STEPS) - 1
chosen = STEPS[n]
resp = {"profile": req["profile"], "profile_version": req["profile_version"],
        "decision_id": req["decision_id"],
        "package_digest": req["package_digest"],
        "source_digest": req["source_digest"],
        "plan_revision": req["plan_revision"], "phase": req["phase"],
        "proposal": chosen["proposal"], "state": {"step": n + 1}}
json.dump(resp, open(sys.argv[2], "w"))
"""


class KillSim(Exception):
    pass


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
    return DSN


def _tag(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _digest_str(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _requires(snapshot: dict) -> dict:
    inherits = dict(snapshot)
    out = {}
    for role, path in (("mod-a", "pkg/a.py"), ("mod-b", "pkg/b.py")):
        body = inherits.get(path)
        if body is None and path == "pkg/a.py":
            body = inherits.get("pkg/alpha.py")
        if body is not None:
            out[role] = {"digest": _digest_str(body), "abi": "py-module",
                         "version": "1"}
    return out


def _requires_pinned() -> dict:
    return _requires(dict(BASE))


def _bindings(snapshot: dict, renames: dict | None = None) -> list:
    renames = renames or {}
    return [{"name": role, "path": renames.get(path, path),
             "abi": "py-module", "version": "1"}
            for role, path in (("mod-a", "pkg/a.py"), ("mod-b", "pkg/b.py"))]


def _decompose_children() -> list:
    return [
        {"node_id": "w1", "obligation": "fix module a",
         "owned_paths": ["pkg/a.py"],
         "output_contract": {"entry": "pkg.a", "checks": ["public"]},
         "input_bindings": {"base_a": "pkg/a.py"}},
        {"node_id": "w2", "obligation": "fix module b",
         "owned_paths": ["pkg/b.py"],
         "output_contract": {"entry": "pkg.b", "checks": ["public"]},
         "input_bindings": {"base_b": "pkg/b.py"}},
    ]


def _single_children(snapshot: dict) -> list:
    whole = sorted(snapshot)
    return [{"node_id": "w1", "obligation": "repair the whole tree",
             "owned_paths": whole,
             "output_contract": {"entry": "whole-tree", "checks": ["public"]},
             "input_bindings": {f"base_{i}": p
                                for i, p in enumerate(whole)}}]


def _iface() -> dict:
    return {"modes": ["C"], "new_paths": []}


def _join_rules() -> dict:
    return {"join": "conjunctive", "integration_owner": "w1",
            "check_entry": "check.py", "checks": {"check.py": CHECK_SRC}}


def _entry(steps: list) -> bytes:
    return POLICY_TMPL.replace("__STEPS__", json.dumps(steps)).encode()


def _plan_step(children: list, shape: str = "decompose") -> dict:
    return {"proposal": {"action": "plan", "shape": shape,
                         "children": children}}


def _probe_step(interface: str = "describe",
                call_input: dict | None = None) -> dict:
    return {"proposal": {"action": "probe", "invocations": [
        {"interface": interface,
         "input": call_input or {"path": "pkg/a.py"}}]}}


def _rework_step(nodes: list) -> dict:
    return {"proposal": {"action": "rework", "rework": list(nodes)}}


def _stop_step(reason: str = "done observing") -> dict:
    return {"proposal": {"action": "stop", "reason": reason}}


class Constructor:
    def __init__(self, outputs: dict, gateway: FakeGatewayAdapter | None = None):
        self.outputs = dict(outputs)
        self.calls: list = []
        self.gateway = gateway or FakeGatewayAdapter()

    def __call__(self, node: str, child: dict, rendered: dict):
        assert self.gateway.check_auth() is not None
        self.calls.append(node)
        value = self.outputs.get(node, "missing")
        if callable(value):
            return value(node, self.calls.count(node))
        return dict(value) if value is not None else None


def _package(entry: bytes) -> dict:
    return {"version_id": f"coord02-test-{uuid.uuid4().hex[:8]}",
            "package_digest": hashlib.sha256(entry).hexdigest(),
            "entry_bytes": entry, "requires": _requires_pinned()}


def _cfg(dsn: str, tag: str, entry: bytes, snapshot: dict | None = None,
         renames: dict | None = None, **over) -> C.EpisodeConfig:
    snap = dict(snapshot or BASE)
    seed = C.seed_episode(dsn, tag, snap)
    package = _package(entry)
    package["requires"] = _requires_pinned()
    cfg = C.EpisodeConfig(
        run_id=f"run-{tag}", task_id=f"task-{tag}",
        allocation_id=seed["allocation_id"],
        investigation_id=seed["investigation_id"], snapshot=snap,
        interface_contract=_iface(), join_rules=_join_rules(),
        bindings=_bindings(snap, renames),
        source_interfaces={"describe": IFACE_TMPL.replace(
            "__SNAP__", json.dumps(snap)).encode()},
        package=package, snapshot_digest=seed["snapshot_digest"])
    for key, value in over.items():
        setattr(cfg, key, value)
    return cfg


def _launchers(tmp_path) -> dict:
    return {"local-process": LocalLauncher(tmp_path / "runs")}


def _op_count(dsn: str, like: str) -> int:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM operations WHERE id LIKE %s",
                        (like,))
            count = cur.fetchone()[0]
            conn.commit()
            return int(count)


def test_no_live_grant_in_env():
    assert "TEAM01_LIVE_API_KEY" not in os.environ
    gw = FakeGatewayAdapter()
    assert gw.check_discovery() is not None


def test_probe_then_plan_success(dsn, tmp_path):
    tag = _tag("probeplan")
    entry = _entry([_probe_step(), _plan_step(_decompose_children())])
    cfg = _cfg(dsn, tag, entry)
    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "success", out
    assert out["candidate_digest"]
    assert ctor.calls == ["w1", "w2"]
    assert len(out["liabilities"]) == 0
    status = C.derive_status(dsn, cfg)
    assert status["sentinel"]
    assert [d["action"] for d in status["decisions"]] == ["probe", "plan"]
    assert status["observations"][0]["interface"] == "describe"
    plan = team.plan_summary(dsn, out["plan_id"])
    assert plan["shape"] == "decompose"
    assert out["live_source"].startswith("simulated")


def test_ec01_branch_change_moves_work_description_does_not(dsn, tmp_path):
    entry_split = _entry([_plan_step(_decompose_children())])
    entry_single = _entry([_plan_step(_single_children(BASE), "single")])

    def _run(tag, entry, outputs):
        cfg = _cfg(dsn, tag, entry)
        ctor = Constructor(outputs)
        out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
        assert out["status"] == "success", out
        plan = team.plan_summary(dsn, out["plan_id"])
        return out, plan

    split_outputs = {"w1": GOOD_A, "w2": GOOD_B}
    out_a, plan_a = _run(_tag("ec01a"), entry_split, split_outputs)
    out_b, plan_b = _run(_tag("ec01b"), entry_split, split_outputs)
    assert plan_a["shape"] == plan_b["shape"] == "decompose"
    assert [c["node_id"] for c in plan_a["children"]] == \
        [c["node_id"] for c in plan_b["children"]]
    assert out_a["candidate_digest"] == out_b["candidate_digest"]
    out_c, plan_c = _run(_tag("ec01c"), entry_single, {"w1": GOOD_WHOLE})
    assert plan_c["shape"] == "single"
    assert [c["owned_paths"] for c in plan_c["children"]] != \
        [c["owned_paths"] for c in plan_a["children"]]
    assert team.child_nodes(dsn, out_c["plan_id"]) != \
        team.child_nodes(dsn, out_a["plan_id"])
    assert team.child_operation(dsn, out_c["plan_id"], "w1") != \
        team.child_operation(dsn, out_a["plan_id"], "w1")


def test_ec02_disconnect_and_substitution_fail_visibly(dsn, tmp_path):
    tag = _tag("ec02d")
    cfg = _cfg(dsn, tag, _entry([_plan_step(_decompose_children())]))
    ctor = Constructor({"w1": GOOD_A, "w2": None}, )
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "submit-refused", out
    assert "w2" in out["reason"]
    assert out["candidate_digest"] is None
    assert any(l["party"] == "constructor" for l in out["liabilities"])

    tag = _tag("ec02s")
    cfg = _cfg(dsn, tag, _entry([_plan_step(_decompose_children()),
                                 _stop_step("accepting the failure")]))
    ctor = Constructor({"w1": GOOD_A, "w2": dict(BAD_B)})
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "stopped", out
    assert out["candidate_digest"] is None
    join = team.join_record(dsn, out["plan_id"], 1)
    assert join["passed"] is False

    refused = team.submit_child(
        dsn, Command(request_id=f"req_{uuid.uuid4().hex[:12]}",
                     payload={"plan_id": out["plan_id"]}),
        plan_revision=1, node_id="w1",
        input_digests=team.expected_inputs(dsn, out["plan_id"], "w1"),
        ownership_generation=team.child_attempt(
            dsn, out["plan_id"], "w1")["ownership_generation"],
        output_digest="0" * 64, receipt_refs=["rc:phantom"])
    assert refused.code != ResultCode.APPLIED


def test_ec03_refused_plan_dispatches_no_child_inference(dsn, tmp_path):
    tag = _tag("ec03")
    bad = _decompose_children()
    bad[0] = dict(bad[0], owned_paths=["pkg/ghost.py"])
    cfg = _cfg(dsn, tag, _entry([_plan_step(bad)]))
    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    before = _op_count(dsn, "%.work")
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "plan-refused", out
    assert ctor.calls == []
    assert _op_count(dsn, "%.work") == before
    assert out["plan_id"] is None


def test_ec04_renamed_binds_incompatible_missing_version_decline(dsn, tmp_path):
    moved = dict(BASE)
    moved["pkg/alpha.py"] = moved.pop("pkg/a.py")
    renames = {"pkg/a.py": "pkg/alpha.py"}
    assert C.check_bindings(moved, _bindings(moved, renames),
                            _requires_pinned(), dsn, "unpublished") == \
        {"ok": True}
    tag = _tag("ec04r")
    ren_children = _decompose_children()
    ren_children[0] = dict(ren_children[0], owned_paths=["pkg/alpha.py"],
                           input_bindings={"base_a": "pkg/alpha.py"})
    cfg = _cfg(dsn, tag, _entry([_plan_step(ren_children),
                                 _stop_step("join failed as expected")]),
               snapshot=moved, renames=renames)
    ctor = Constructor({"w1": {"pkg/alpha.py": GOOD_A["pkg/a.py"]},
                        "w2": GOOD_B})
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "stopped", out
    assert out["plan_id"] is not None
    assert team.join_record(dsn, out["plan_id"], 1)["passed"] is False

    changed = dict(BASE, **{"pkg/a.py": "MODE = 'Q'\nVALUE = 1\n"})
    tag = _tag("ec04i")
    cfg = _cfg(dsn, tag, _entry([_plan_step(_decompose_children())]),
               snapshot=changed)
    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "unsupported", out
    assert "incompatible" in out["reason"]
    assert ctor.calls == []

    tag = _tag("ec04m")
    cfg = _cfg(dsn, tag, _entry([_plan_step(_decompose_children())]))
    cfg.bindings = [b for b in cfg.bindings if b["name"] != "mod-b"]
    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "unsupported", out
    assert "no bound input" in out["reason"]
    assert ctor.calls == []

    tag = _tag("ec04v")
    cfg = _cfg(dsn, tag, _entry([_plan_step(_decompose_children())]))
    cfg.bindings[1] = dict(cfg.bindings[1], version="2")
    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "unsupported", out
    assert "version" in out["reason"]
    assert ctor.calls == []


def test_ec04_quarantine_blocks_new_use(dsn, tmp_path):
    tag = _tag("ec04q")
    entry = _entry([_plan_step(_decompose_children())])
    seed = C.seed_episode(dsn, tag, dict(BASE))
    launchers = _launchers(tmp_path)
    launcher = launchers["local-process"]
    receipt = C.stage_package(tmp_path / "staging", entry_bytes=entry,
                              description=b"quarantine-me",
                              requires=_requires(BASE))
    staged = C.publish_package_version(
        dsn, tmp_path / "artifacts", receipt, launcher,
        seed["allocation_id"], version_id=f"coord02-q-{tag}",
        requires=_requires(BASE))
    assert staged.code == ResultCode.APPLIED, staged.detail
    quarantined = capabilities.quarantine(
        dsn, Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload={}),
        f"coord02-q-{tag}", "lane-R rejecting control")
    assert quarantined.code == ResultCode.APPLIED, quarantined.detail
    cfg = C.EpisodeConfig(
        run_id=f"run-{tag}", task_id=f"task-{tag}",
        allocation_id=seed["allocation_id"],
        investigation_id=seed["investigation_id"], snapshot=dict(BASE),
        interface_contract=_iface(), join_rules=_join_rules(),
        bindings=_bindings(BASE),
        source_interfaces={"describe": IFACE_TMPL.replace(
            "__SNAP__", json.dumps(dict(BASE))).encode()},
        package={"version_id": f"coord02-q-{tag}",
                 "package_digest": hashlib.sha256(entry).hexdigest(),
                 "entry_bytes": entry, "requires": _requires(BASE)},
        snapshot_digest=seed["snapshot_digest"])
    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    out = C.run_episode(dsn, cfg, launchers, ctor)
    assert out["status"] == "unsupported", out
    assert "quarantined" in out["reason"]
    assert ctor.calls == []


def _flaky_b(node: str, calls: int):
    if node == "w2" and calls == 1:
        return dict(BAD_B)
    return {"w1": GOOD_A, "w2": GOOD_B}[node]


def test_ec06_selective_rework_carries_valid_work(dsn, tmp_path):
    tag = _tag("ec06")
    cfg = _cfg(dsn, tag, _entry([_plan_step(_decompose_children()),
                                 _rework_step(["w2"])]))
    ctor = Constructor({"w1": GOOD_A, "w2": _flaky_b})
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "success", out
    assert out["carried"] == ["w1"]
    assert out["invalidated"] == ["w2"]
    assert ctor.calls.count("w1") == 1
    assert ctor.calls.count("w2") == 2
    assert team.join_record(dsn, out["plan_id"], 1)["passed"] is False
    assert team.join_record(dsn, out["plan_id"], 2)["passed"] is True
    first = team.child_attempt(dsn, out["plan_id"], "w2", revision=1)
    second = team.child_attempt(dsn, out["plan_id"], "w2")
    assert first["attempt_id"] != second["attempt_id"]


def test_ec06_changed_deps_invalidate_carried_work(dsn, tmp_path):
    tag = _tag("ec06c")
    cfg = _cfg(dsn, tag, _entry([_plan_step(_decompose_children()),
                                 _rework_step(["w2"])]))
    launchers = _launchers(tmp_path)
    ctor = Constructor({"w1": GOOD_A, "w2": _flaky_b})
    mutated = {"done": False}

    def _progress(status):
        join = status.get("join")
        if join is not None and not status.get("join_passed") \
                and status.get("revision") == 1 and not mutated["done"]:
            mutated["done"] = True
            cfg.interface_contract = dict(cfg.interface_contract,
                                          convention="v2-breaks-deps")

    out = C.run_episode(dsn, cfg, launchers, ctor, _progress)
    assert mutated["done"]
    assert out["status"] == "success", out
    assert out["carried"] == []
    assert sorted(out["invalidated"]) == ["w1", "w2"]
    assert ctor.calls.count("w1") == 2


def test_ec07_kill_after_probe_resumes(dsn, tmp_path):
    tag = _tag("ec07p")
    cfg = _cfg(dsn, tag, _entry([_probe_step(), _plan_step(_decompose_children())]))
    launchers = _launchers(tmp_path)

    def _progress(status):
        if status["observations"] and status["plan_id"] is None:
            raise KillSim("kill after probe")

    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    with pytest.raises(KillSim):
        C.run_episode(dsn, cfg, launchers, ctor, _progress)
    before = C.derive_status(dsn, cfg)
    assert before["sentinel"]
    steps_before = [(d.get("decision_id"), d.get("request_digest"))
                    for d in before["decisions"]]
    probe_ops_before = _op_count(dsn, f"coord:{cfg.run_id}:%probe%")
    out = C.resume_episode(dsn, cfg, launchers, ctor)
    assert out["status"] == "success", out
    after = C.derive_status(dsn, cfg)
    assert after["sentinel"] == before["sentinel"]
    assert [(d.get("decision_id"), d.get("request_digest"))
            for d in after["decisions"][:len(steps_before)]] == steps_before
    assert _op_count(dsn, f"coord:{cfg.run_id}:%probe%") == probe_ops_before


def test_ec07_kill_after_one_child_resumes(dsn, tmp_path):
    tag = _tag("ec07c")
    cfg = _cfg(dsn, tag, _entry([_plan_step(_decompose_children())]))
    launchers = _launchers(tmp_path)
    inner = Constructor({"w1": GOOD_A, "w2": GOOD_B})

    def _killer(node, child, rendered):
        if node == "w2":
            raise KillSim("kill after one accepted child")
        return inner(node, child, rendered)

    with pytest.raises(KillSim):
        C.run_episode(dsn, cfg, launchers, _killer)
    plan_id = C.derive_status(dsn, cfg)["plan_id"]
    assert plan_id is not None
    attempt_before = team.child_attempt(dsn, plan_id, "w1")
    out = C.resume_episode(dsn, cfg, launchers, inner)
    assert out["status"] == "success", out
    assert team.child_attempt(dsn, plan_id, "w1")["attempt_id"] == \
        attempt_before["attempt_id"]
    assert inner.calls.count("w1") == 1
    assert C.derive_status(dsn, cfg)["sentinel"] is not None


INFINITE_ENTRY = b"""import sys
if len(sys.argv) == 2 and sys.argv[1] == "--selftest__":
    raise SystemExit(0)
while True:
    pass
"""

OVERSIZE_ENTRY = """import json
import sys
req = json.load(open(sys.argv[1]))
resp = {"profile": req["profile"], "profile_version": req["profile_version"],
        "decision_id": req["decision_id"],
        "package_digest": req["package_digest"],
        "source_digest": req["source_digest"],
        "plan_revision": req["plan_revision"], "phase": req["phase"],
        "proposal": {"action": "stop", "reason": "too big"},
        "state": {"blob": "x" * 20000}}
json.dump(resp, open(sys.argv[2], "w"))
""".encode()

MALFORMED_ENTRY = b"""import sys
open(sys.argv[2], "w").write("{not json")
"""

UNKNOWN_ACTION_ENTRY = """import json
import sys
req = json.load(open(sys.argv[1]))
resp = {"profile": req["profile"], "profile_version": req["profile_version"],
        "decision_id": req["decision_id"],
        "package_digest": req["package_digest"],
        "source_digest": req["source_digest"],
        "plan_revision": req["plan_revision"], "phase": req["phase"],
        "proposal": {"action": "teleport", "reason": "nowhere"},
        "state": {}}
json.dump(resp, open(sys.argv[2], "w"))
""".encode()

EXTRA_FIELD_ENTRY = """import json
import sys
req = json.load(open(sys.argv[1]))
resp = {"profile": req["profile"], "profile_version": req["profile_version"],
        "decision_id": req["decision_id"],
        "package_digest": req["package_digest"],
        "source_digest": req["source_digest"],
        "plan_revision": req["plan_revision"], "phase": req["phase"],
        "proposal": {"action": "stop", "reason": "sneaky",
                     "passed": True},
        "state": {}}
json.dump(resp, open(sys.argv[2], "w"))
""".encode()

EMPTY_ENTRY = b"""import sys
raise SystemExit(0)
"""


def _failure_outcome(dsn, tmp_path, tag, entry, **over):
    cfg = _cfg(dsn, tag, entry, **over)
    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] != "success", out
    assert "s-fallback-success" != out["status"]
    assert out["liabilities"], out
    assert all(l["party"] and l["reason"] for l in out["liabilities"])
    return out


def test_ec08_bounded_failures(dsn, tmp_path):
    out = _failure_outcome(dsn, tmp_path, _tag("ec08inf"), INFINITE_ENTRY)
    assert out["status"] == "policy-timeout", out
    assert out["liabilities"][0]["party"] == "policy"

    out = _failure_outcome(dsn, tmp_path, _tag("ec08ovr"), OVERSIZE_ENTRY)
    assert out["status"] == "policy-oversize", out

    out = _failure_outcome(dsn, tmp_path, _tag("ec08inv"), MALFORMED_ENTRY)
    assert out["status"] == "policy-invalid", out

    out = _failure_outcome(dsn, tmp_path, _tag("ec08unk"),
                           UNKNOWN_ACTION_ENTRY)
    assert out["status"] == "policy-invalid", out
    assert "teleport" in out["reason"]

    out = _failure_outcome(dsn, tmp_path, _tag("ec08ext"), EXTRA_FIELD_ENTRY)
    assert out["status"] == "policy-invalid", out

    out = _failure_outcome(dsn, tmp_path, _tag("ec08empty"), EMPTY_ENTRY)
    assert out["status"] == "policy-empty", out

    tag = _tag("ec08bud")
    cfg = _cfg(dsn, tag, _entry([_probe_step(),
                                 _plan_step(_decompose_children())]),
               max_steps=1)
    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "budget-exhausted", out
    assert out["plan_id"] is None

    tag = _tag("ec08can")
    cfg = _cfg(dsn, tag, _entry([_plan_step(_decompose_children())]))
    launchers = _launchers(tmp_path)
    cancelled = {"done": False}

    def _progress(status):
        if status["plan_id"] is not None and not cancelled["done"]:
            cancelled["done"] = True
            op_id = team.child_operation(dsn, status["plan_id"], "w1")
            broker.request_cancel(dsn, op_id)

    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    out = C.run_episode(dsn, cfg, launchers, ctor, _progress)
    assert cancelled["done"]
    assert out["status"] == "cancelled", out
    assert any(l["party"] == "external" for l in out["liabilities"])


def test_revalidation_on_input_change(dsn, tmp_path):
    tag = _tag("stale")
    cfg = _cfg(dsn, tag, _entry([_plan_step(_decompose_children())]))
    launchers = _launchers(tmp_path)
    mutated = {"done": False}

    def _progress(status):
        if status["plan_id"] is not None and status["join"] is None \
                and not mutated["done"]:
            mutated["done"] = True
            cfg.snapshot = dict(cfg.snapshot,
                                **{"pkg/a.py": "MODE = 'Z'\nVALUE = 1\n"})

    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    out = C.run_episode(dsn, cfg, launchers, ctor, _progress)
    assert mutated["done"]
    assert out["status"] == "stale-inputs", out
    assert "inputs changed" in out["reason"]


def test_s_fallback_only_preplan(dsn, tmp_path):
    tag = _tag("sfb")
    cfg = _cfg(dsn, tag, _entry([{"proposal": {"action": "unsupported",
                                               "reason": "out of scope"}}]),
               s_fallback_outputs=dict(GOOD_WHOLE))
    ctor = Constructor({"w1": GOOD_A, "w2": GOOD_B})
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "s-fallback-success", out
    assert ctor.calls == []

    tag = _tag("sfbpost")
    cfg = _cfg(dsn, tag, _entry([_plan_step(_decompose_children()),
                                 _stop_step("give up")]),
               s_fallback_outputs=dict(GOOD_WHOLE))
    ctor = Constructor({"w1": GOOD_A, "w2": dict(BAD_B)})
    out = C.run_episode(dsn, cfg, _launchers(tmp_path), ctor)
    assert out["status"] == "stopped", out
    plan = team.plan_summary(dsn, out["plan_id"])
    assert plan["shape"] == "decompose"
    assert not team.team_state(
        dsn, cfg.investigation_id)["plans"][0]["frozen_candidate"]


def _echo_fixture(**over):
    base = {"profile": S.PROFILE, "profile_version": S.PROFILE_VERSION,
            "decision_id": "d1", "package_digest": "p",
            "source_digest": "s", "plan_revision": 1, "phase": "pre-plan",
            "proposal": {"action": "stop", "reason": "r"}, "state": {}}
    base.update(over)
    return base


def test_schema_strictness():
    echo = {"decision_id": "d1", "package_digest": "p", "source_digest": "s",
            "plan_revision": 1, "phase": "pre-plan",
            "allowed": list(S.ALLOWED["pre-plan"])}
    parsed = S.validate_response(_echo_fixture(), **echo)
    assert parsed["action"] == "stop"
    with pytest.raises(S.PolicyError):
        S.validate_response(_echo_fixture(
            proposal={"action": "teleport", "reason": "x"}), **echo)
    with pytest.raises(S.PolicyError):
        S.validate_response(_echo_fixture(
            proposal={"action": "stop", "reason": "r", "passed": True}),
            **echo)
    with pytest.raises(S.PolicyError):
        S.validate_response(_echo_fixture(decision_id="other"), **echo)
    with pytest.raises(S.PolicyError):
        S.validate_response(_echo_fixture(
            proposal={"action": "rework", "rework": ["w1"]}), **echo)
    with pytest.raises(S.PolicyError):
        S.validate_response(_echo_fixture(state={"blob": "x" * 20000}),
                            **echo)
    with pytest.raises(S.PolicyError):
        S.build_request(decision_id="d", package_digest="p",
                        source_digest="s", plan_revision=1, phase="pre-plan",
                        allowed=["plan"], state={}, task={})
    assert S.ALLOWED["pre-plan"] == ("probe", "plan", "unsupported", "stop")
    assert S.ALLOWED["post-probe"] == ("plan", "unsupported", "stop")
    assert S.ALLOWED["post-fail-join"] == ("probe", "rework", "stop")
