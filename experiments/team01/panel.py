from __future__ import annotations

import hashlib
import json
import tempfile
import time
import uuid
from pathlib import Path

from settlement import broker, store, team
from settlement.common import Command, ResultCode, SettlementError
from settlement.launcher_local import LocalLauncher

from . import oracle, register

ROOT = Path(__file__).resolve().parent

ARMS = ("S", "P", "T")
REPEATS = (1, 2)
TRANSFER_MODES = ("S", "cold-T", "warm-T")
PANEL_VERSION = "team01-panel/1"
GRANT_UNITS = 100000

FAMILY_MODULES = {
    "fam-ind": ("src/numops.py", "src/textops.py"),
    "fam-cpl": ("src/producer.py", "src/consumer.py"),
    "fam-seq": ("src/detect.py", "src/operate.py"),
    "fam-sng": ("src/compute.py", "src/validate.py"),
}

ARM_COSTS = {
    "S": {"in": 1000, "out": 250, "tools": 4, "calls": 2},
    "P": {"in": 2000, "out": 500, "tools": 8, "calls": 4},
    "T": {"in": 1200, "out": 300, "tools": 5, "calls": 3},
    "cold-T": {"in": 1200, "out": 300, "tools": 5, "calls": 3},
    "warm-T": {"in": 700, "out": 200, "tools": 4, "calls": 2},
}


def _cmd(payload=None) -> Command:
    return Command(request_id="team01-%s" % uuid.uuid4().hex, payload=payload or {})


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _snapshot(task_id: str) -> dict:
    tdir = oracle.TASKS / task_id
    snap = {"spec.json": (tdir / "spec.json").read_text()}
    for mod in sorted((tdir / "src").glob("*.py")):
        snap["src/" + mod.name] = mod.read_text()
    return snap


def _check_src(task_id: str, shape: str) -> str:
    cases = oracle.public_cases(task_id)
    embedded = json.dumps(cases)
    if shape == "alternatives":
        body = (
            "import importlib.util,json,subprocess,sys,tempfile\n"
            "from pathlib import Path\n"
            "root=sys.argv[1];order=sys.argv[2].split(',');cases=%s\n"
            "def run(tree,payload):\n"
            " with tempfile.TemporaryDirectory() as tmp:\n"
            "  req=Path(tmp)/'req.json';resp=Path(tmp)/'resp.json'\n"
            "  req.write_text(json.dumps(payload))\n"
            "  p=subprocess.run([sys.executable,str(Path(tree)/'src'/'app.py'),str(req),str(resp)],capture_output=True,text=True,timeout=20)\n"
            "  return json.loads(resp.read_text()) if p.returncode==0 else None\n"
            "picked=None\n"
            "for node in order:\n"
            " try:\n"
            "  if all(run(str(Path(root)/node),dict(c['input']))==c['expected'] for c in cases):picked=node;break\n"
            " except Exception:continue\n"
            "print(json.dumps({'status':'ok','data':{'selected':picked}} if picked else {'status':'error','data':{'message':'no passing candidate'}}))\n"
        ) % embedded
    else:
        body = (
            "import json,subprocess,sys,tempfile\n"
            "from pathlib import Path\n"
            "root=sys.argv[1];cases=%s\n"
            "fails=[]\n"
            "for c in cases:\n"
            " with tempfile.TemporaryDirectory() as tmp:\n"
            "  req=Path(tmp)/'req.json';resp=Path(tmp)/'resp.json'\n"
            "  req.write_text(json.dumps(dict(c['input'])))\n"
            "  p=subprocess.run([sys.executable,str(Path(root)/'src'/'app.py'),str(req),str(resp)],capture_output=True,text=True,timeout=20)\n"
            "  try:got=json.loads(resp.read_text()) if p.returncode==0 else None\n"
            "  except Exception:got=None\n"
            "  if got!=c['expected']:fails.append(c['input'])\n"
            "print(json.dumps({'status':'ok','data':{'passed':len(cases)-len(fails)}} if not fails else {'status':'error','data':{'message':'public check failed','fails':fails}}))\n"
        ) % embedded
    return body


def _children(shape: str, snapshot: dict, family: str) -> list:
    whole = sorted(snapshot)
    mods = list(FAMILY_MODULES[family])
    bindings = {"base_%d" % pos: path for pos, path in enumerate(whole)}
    if shape == "single":
        return [{"node_id": "w1", "obligation": "repair the whole task tree",
                 "owned_paths": whole,
                 "output_contract": {"entry": "whole-tree", "checks": ["public"]},
                 "input_bindings": dict(bindings)}]
    if shape == "alternatives":
        return [{"node_id": node, "obligation": "independent whole-task attempt",
                 "owned_paths": whole,
                 "output_contract": {"entry": "whole-tree", "checks": ["public"]},
                 "input_bindings": dict(bindings)} for node in ("w1", "w2")]
    first, second = mods
    return [{"node_id": "w1", "obligation": "repair %s" % first,
             "owned_paths": [first],
             "output_contract": {"entry": first, "checks": ["public"]},
             "input_bindings": {"base": first}},
            {"node_id": "w2", "obligation": "repair %s" % second,
             "owned_paths": [second],
             "output_contract": {"entry": second, "checks": ["public"]},
             "input_bindings": {"base": second}}]


def _join_rules(shape: str, task_id: str) -> dict:
    join = {"single": "accept", "alternatives": "select-one",
            "decompose": "conjunctive"}[shape]
    return {"join": join, "integration_owner": "w1",
            "check_entry": "check.py",
            "checks": {"check.py": _check_src(task_id, shape)}}


def _visible_info(task_id: str) -> dict:
    family = oracle.TASK_FAMILY[task_id]
    return {"task_id": task_id, "defect_count": 1 if family == "fam-sng" else 2,
            "modules": list(FAMILY_MODULES[family]),
            "interface_stable": family in ("fam-ind", "fam-sng"),
            "unclear_diagnosis": family == "fam-seq"}


class FakePlanner:
    def __init__(self, template=None) -> None:
        self.template = template
        self.calls: list = []

    def propose(self, arm: str, task_id: str, repeat: int,
                probe: str | None = None) -> dict:
        family = oracle.TASK_FAMILY[task_id]
        base = team.select_plan(_visible_info(task_id))
        shape = {"S": "single", "P": "alternatives"}.get(arm, base["shape"])
        changed = False
        if arm == "warm-T" and self.template is not None:
            from . import template as _tm
            applied = _tm.apply_template(self.template, task_id)
            if applied["applicable"]:
                shape = applied["directive"]["shape"]
                changed = applied["changed_decision"]
        key = arm.split("-")[-1]
        if probe == "incompatible":
            kinds = {"w1": "valid", "w2": "invalid"}
        elif key == "S":
            kind = "invalid" if family == "fam-seq" else "valid"
            kinds = {"w1": kind, "w2": kind}
        elif key == "P":
            kinds = {"w1": "invalid", "w2": "invalid"} \
                if family == "fam-cpl" else {"w1": "invalid", "w2": "valid"}
        else:
            kinds = {"w1": "valid", "w2": "valid"}
        if shape == "single":
            kinds = {"w1": kinds["w1"]}
        costs = dict(ARM_COSTS[arm if arm in ARM_COSTS else key])
        costs["in"] += repeat * 10
        decision = {"shape": shape, "kinds": kinds, "costs": costs,
                    "template_used": arm == "warm-T" and self.template is not None,
                    "template_changed_decision": changed, "simulated": True}
        self.calls.append({"arm": arm, "task_id": task_id, "repeat": repeat,
                           "probe": probe, "decision": decision})
        return decision


def _seed(dsn: str, tag: str) -> dict:
    store.seed_allocation(dsn, _cmd({"allocation_id": "%s-root" % tag,
                                    "domain": "cpu", "authorized": GRANT_UNITS,
                                    "max_occupancy": 16}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "%s-inv" % tag,
                                     "objective": "team01 %s" % tag,
                                     "obligations": {"repair": True}}))
    return {"allocation_id": "%s-root" % tag,
            "investigation_id": "%s-inv" % tag}


def _dispatch(dsn: str, plan_id: str, launchers: dict) -> dict:
    receipts = {}
    for node in team.child_nodes(dsn, plan_id):
        op_id = team.child_operation(dsn, plan_id, node)
        gen = team.child_attempt(dsn, plan_id, node)["ownership_generation"]
        status = broker.dispatch_operation(dsn, op_id, launchers=launchers,
                                           ownership_generation=gen)
        if not (status.sent_this_call or status.dispatch_state == "observed"):
            raise SettlementError("child %s never observed" % node)
        receipts[node] = [r["receipt_identity"]
                          for r in store.operation_receipts(dsn, op_id)]
        if not receipts[node]:
            raise SettlementError("child %s left no receipt" % node)
    return receipts


def _tree_files(task_id: str, kind: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="team01-kind-") as tmp:
        src = oracle.prepare_tree(task_id, kind, Path(tmp) / kind)
        files = {"src/" + p.name: p.read_text()
                 for p in sorted(src.glob("*.py"))}
    files["spec.json"] = (oracle.TASKS / task_id / "spec.json").read_text()
    return files


def _materialize(tree: dict, dest: Path) -> Path:
    for relpath, body in tree.items():
        target = dest / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return dest / "src"


def run_episode(dsn: str, *, task_id: str, arm: str, repeat: int,
                runs_root, panel_name: str, evidence_root=None,
                tag: str = "team01", template=None,
                probe: str | None = None,
                planner: FakePlanner | None = None) -> dict:
    started = time.monotonic()
    register.ensure_foundation(dsn)
    planner = planner or FakePlanner(template)
    family = oracle.TASK_FAMILY[task_id]
    decision = planner.propose(arm, task_id, repeat, probe)
    shape, kinds = decision["shape"], decision["kinds"]
    epid = "%s-%s-%s-r%d" % (panel_name, arm, task_id, repeat)
    if probe:
        epid = "%s-%s" % (epid, probe)
    seed = _seed(dsn, "%s-%s" % (tag, epid))
    snapshot = _snapshot(task_id)
    snap = team.register_snapshot(dsn, _cmd(), dict(snapshot))
    if snap.code != ResultCode.APPLIED:
        raise SettlementError("snapshot refused: %s" % snap.detail)
    launchers = {"local-process": LocalLauncher(str(runs_root))}
    proposed = team.propose_team_plan(
        dsn, _cmd(), parent_obligation="%s:repair %s" % (
            seed["investigation_id"], task_id),
        snapshot_digest=snap.data["snapshot_digest"], shape=shape,
        children=_children(shape, snapshot, family),
        interface_contract={"shapes": [shape], "new_paths": []},
        join_rules=_join_rules(shape, task_id),
        allocation_id=seed["allocation_id"],
        policy_response={"shape": shape,
                         "rationale": "doubled planner for %s" % arm})
    if proposed.code != ResultCode.APPLIED:
        raise SettlementError("plan refused: %s" % proposed.detail)
    plan_id = proposed.data["plan_id"]
    receipts = _dispatch(dsn, plan_id, launchers)
    _submit_real(dsn, plan_id, task_id, snapshot, shape, kinds, receipts)
    joined = team.assemble_and_join(dsn, _cmd(), plan_id=plan_id,
                                    launchers=launchers)
    join = team.join_record(dsn, plan_id, 1) if joined.data.get(
        "candidate_digest") else {"passed": False,
                                  "candidate_digest": "",
                                  "join_receipt": "",
                                  "check_operation": joined.data.get(
                                      "check_operation", "")}
    frozen_digest = None
    if joined.code == ResultCode.APPLIED:
        frozen = team.freeze_candidate(
            dsn, _cmd(), plan_id=plan_id,
            candidate_digest=joined.data["candidate_digest"])
        if frozen.code == ResultCode.APPLIED:
            frozen_digest = frozen.data["frozen_candidate"]
    final = _final_tree_real(dsn, plan_id, task_id, snapshot, shape,
                             kinds, joined.data.get("candidate_digest", ""))
    with tempfile.TemporaryDirectory(prefix="team01-eval-") as tmp:
        src = _materialize(final, Path(tmp) / "tree")
        public = oracle.evaluate_tree(src, oracle.public_cases(task_id))
        protected = oracle.evaluate_tree(src, oracle.protected_cases(task_id))
    solved = bool(frozen_digest) and protected["failed"] == 0
    costs = decision["costs"]
    record = {"episode_id": epid, "panel": panel_name, "arm": arm,
              "task_id": task_id, "repeat": repeat, "family": family,
              "probe": probe, "panel_version": PANEL_VERSION,
              "plan_id": plan_id, "revision": 1, "shape": shape,
              "snapshot_digest": snap.data["snapshot_digest"],
              "manifest_sha256": _manifest_sha(),
              "template_digest": (template or {}).get("digest")
              if decision["template_used"] else None,
              "template_changed_decision": decision["template_changed_decision"],
              "outcome": "success" if solved else "failure",
              "public": public, "protected": protected,
              "join": {"passed": bool(join.get("passed")),
                       "join_receipt": join.get("join_receipt", ""),
                       "check_operation": join.get("check_operation", ""),
                       "candidate_digest": join.get("candidate_digest", "")},
              "frozen_digest": frozen_digest,
              "receipts": receipts, "simulated": True,
              "costs": {"model_tokens": {"in": costs["in"], "out": costs["out"]},
                        "tool_executions": costs["tools"],
                        "model_invocations": costs["calls"],
                        "wall_s": round(time.monotonic() - started, 3)}}
    if evidence_root is not None:
        dest = Path(evidence_root) / "episodes"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / ("%s.json" % epid)).write_text(json.dumps(record, indent=2))
    return record


def _submit_real(dsn, plan_id, task_id, snapshot, shape, kinds, receipts):
    staged = {}
    for node, kind in kinds.items():
        if kind == "broken":
            files = dict(snapshot)
        else:
            files = _tree_files(task_id, kind)
        staged[node] = files
    for node, files in staged.items():
        if shape == "decompose":
            owned = next(c["owned_paths"] for c in
                         team.plan_summary(dsn, plan_id)["children"]
                         if c["node_id"] == node)
            files = {path: files[path] for path in owned}
        reg = team.register_output(dsn, _cmd(), dict(files))
        if reg.code != ResultCode.APPLIED:
            raise SettlementError("output refused: %s" % reg.detail)
        attempt = team.child_attempt(dsn, plan_id, node)
        result = team.submit_child(
            dsn, _cmd({"plan_id": plan_id}), plan_revision=1, node_id=node,
            input_digests=team.expected_inputs(dsn, plan_id, node),
            ownership_generation=attempt["ownership_generation"],
            output_digest=reg.data["output_digest"],
            receipt_refs=receipts[node])
        if result.code != ResultCode.APPLIED:
            raise SettlementError("submit refused: %s" % result.detail)


def _final_tree_real(dsn, plan_id, task_id, snapshot, shape, kinds,
                     candidate_digest):
    staged = {}
    for node, kind in kinds.items():
        files = dict(snapshot) if kind == "broken" else _tree_files(task_id, kind)
        if shape == "decompose":
            owned = next(c["owned_paths"] for c in
                         team.plan_summary(dsn, plan_id)["children"]
                         if c["node_id"] == node)
            files = {path: files[path] for path in owned}
        staged[node] = files
    if shape == "alternatives":
        for node, files in staged.items():
            if team.output_digest(files) == candidate_digest:
                return files
        return dict(snapshot)
    tree = dict(snapshot)
    for files in staged.values():
        tree.update(files)
    return tree


def _manifest_sha() -> str:
    try:
        return (ROOT / "manifest.sha256").read_text().strip()
    except OSError:
        return ""


def _write_index(evidence_root, records: list) -> Path:
    root = Path(evidence_root)
    (root / "episodes").mkdir(parents=True, exist_ok=True)
    index = {"panel_version": PANEL_VERSION,
             "manifest_sha256": _manifest_sha(),
             "records": len(records),
             "episodes": [r["episode_id"] for r in records]}
    target = root / "index.json"
    target.write_text(json.dumps(index, sort_keys=True, indent=2))
    return target


def run_development(dsn: str, *, evidence_root, runs_root,
                    tag: str = "team01") -> list:
    planner = FakePlanner()
    records = []
    for task_id in oracle.SPLITS["development"]:
        for probe in ("template-use", "diagnostic", "incompatible"):
            records.append(run_episode(
                dsn, task_id=task_id, arm="T", repeat=1, runs_root=runs_root,
                panel_name="dev", evidence_root=evidence_root, tag=tag,
                probe=probe, planner=planner))
    _write_index(evidence_root, records)
    return records


def run_comparison(dsn: str, *, evidence_root, runs_root,
                   tag: str = "team01", template=None) -> dict:
    planner = FakePlanner(template)
    records = [run_episode(
        dsn, task_id=task_id, arm=arm, repeat=repeat, runs_root=runs_root,
        panel_name="eval", evidence_root=evidence_root, tag=tag,
        template=template, planner=planner)
        for arm in ARMS for task_id in oracle.SPLITS["evaluation"]
        for repeat in REPEATS]
    if len(records) != 48:
        raise SettlementError("eval panel needs 48 episodes, have %d"
                              % len(records))
    return {"records": records, "index": str(_write_index(evidence_root, records))}


def run_transfer(dsn: str, *, evidence_root, runs_root,
                 tag: str = "team01", template=None) -> dict:
    planner = FakePlanner(template)
    records = [run_episode(
        dsn, task_id=task_id, arm=arm, repeat=repeat, runs_root=runs_root,
        panel_name="transfer", evidence_root=evidence_root, tag=tag,
        template=template, planner=planner)
        for arm in TRANSFER_MODES for task_id in oracle.SPLITS["transfer"]
        for repeat in REPEATS]
    if len(records) != 24:
        raise SettlementError("transfer panel needs 24 episodes, have %d"
                              % len(records))
    return {"records": records, "index": str(_write_index(evidence_root, records))}
