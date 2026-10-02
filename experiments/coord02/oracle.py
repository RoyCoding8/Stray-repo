from __future__ import annotations

import copy
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKS = ROOT / "corpus" / "tasks"
PROTECTED = ROOT / "protected"
REFERENCE = PROTECTED / "reference"

EVALUATOR_ID = "coord02-oracle"
EVALUATOR_VERSION = "1.0.0"

FAMILIES = ("sep", "cpl", "dia", "sng", "rw", "sco")

TASK_FAMILY: dict = {}
for _fam, _base in (("sep", 1), ("cpl", 6), ("dia", 11),
                    ("sng", 16), ("rw", 21), ("sco", 26)):
    for _n in range(_base, _base + 5):
        TASK_FAMILY["c02-t%02d" % _n] = _fam

SPLITS = {
    "development": ["c02-t01", "c02-t02", "c02-t06", "c02-t07",
                    "c02-t11", "c02-t12", "c02-t16", "c02-t17",
                    "c02-t21", "c02-t22", "c02-t26", "c02-t27"],
    "evaluation": ["c02-t03", "c02-t04", "c02-t08", "c02-t09",
                   "c02-t13", "c02-t14", "c02-t18", "c02-t19",
                   "c02-t23", "c02-t24", "c02-t28", "c02-t29"],
    "transfer": ["c02-t05", "c02-t10", "c02-t15",
                 "c02-t20", "c02-t25", "c02-t30"],
}

ALL_TASKS = [t for split in ("development", "evaluation", "transfer")
             for t in SPLITS[split]]

DIA_FAULT = {"c02-t11": "detect", "c02-t12": "operate",
             "c02-t13": "detect", "c02-t14": "operate",
             "c02-t15": "detect"}

PROFILES = {
    "cpl/1": {"id": "cpl/1", "keys": ["readings", "want"]},
    "cellsum/1": {"id": "cellsum/1", "keys": ["cells", "factor"]},
    "cellchain/1": {"id": "cellchain/1", "keys": ["parcels", "want"]},
}

DIA_PROBES = {
    "c02-t11": [{"xs": [1, 2], "ys": [3]},
                {"flag": 1, "xs": [1], "ys": [3, 4]}],
    "c02-t12": [{"code": 3, "vals": [2, 5]}, {"code": 9, "vals": [2, 5]}],
    "c02-t13": [{"kind": "alpha-1", "vals": [4, 7]},
                {"kind": "beta-1", "vals": [4, 7]}],
    "c02-t14": [{"items": [2, 3]}, {"items": {"p": 2, "q": 3}}],
    "c02-t15": [{"code": 2, "vals": [1, 1], "xs": [5], "zs": [7]},
                {"code": 8, "vals": [1, 1], "xs": [5], "zs": [7]}],
}

BANNED_LABELS = ("separable multi-module", "coupled semantics",
                 "diagnostic information", "single-owner", "single owner",
                 "rework dependencies", "misleading similarity",
                 "protected/", "reference/", "fault is in",
                 "faulty module", "family")


class CandidateError(Exception):
    pass


def load_spec(task_id: str) -> dict:
    return json.loads((TASKS / task_id / "spec.json").read_text())


def public_cases(task_id: str) -> list:
    return json.loads((TASKS / task_id / "public.json").read_text())


def protected_cases(task_id: str) -> list:
    return json.loads((PROTECTED / (task_id + ".json")).read_text())


def _ref_sep(spec: dict, payload: dict) -> dict:
    out = {}
    if "names" in spec["layout"]:
        out["names"] = [s.strip().lower() for s in payload["names"]]
    if "scores" in spec["layout"]:
        lo, hi = spec["bounds"]
        out["scores"] = [round(min(hi, max(lo, x)), 2)
                         for x in payload["scores"]]
    if "tags" in spec["layout"]:
        out["tags"] = sorted(set(payload["tags"]))
    if "stats" in spec["layout"]:
        vals = payload["values"]
        out["stat"] = round(sum(vals, 0) / len(vals), 2) if vals else 0
    if "pconv" in spec["layout"]:
        units = spec["units"]
        out["values"] = [round_half_up(r["v"] * units[r["u"]]
                                       / units[payload["want"]], 2)
                         for r in payload["readings"]]
    if "cconv" in spec["layout"]:
        lo2, hi2 = spec["cbounds"]
        out["flags"] = ["low" if v < lo2 else "high" if v > hi2 else "ok"
                        for v in out["values"]]
    return out


def round_half_up(x: float, nd: int = 2) -> float:
    quantum = Decimal(1).scaleb(-nd)
    return float(Decimal(str(x)).quantize(quantum, rounding=ROUND_HALF_UP))


def _ref_cpl(spec: dict, payload: dict) -> dict:
    units = spec["units"]
    lo, hi = spec["bounds"]
    rows = payload.get("readings", payload.get("parcels"))
    values = [round_half_up(r["v"] * units[r["u"]] / units[payload["want"]], 2)
              for r in rows]
    flags = ["low" if v < lo else "high" if v > hi else "ok" for v in values]
    return {"values": values, "flags": flags}


def _detect(rule: dict, payload: dict) -> str:
    kind = rule["kind"]
    if kind == "key":
        return "b" if rule["key"] in payload else "a"
    if kind == "threshold":
        return "b" if payload["code"] >= rule["at"] else "a"
    if kind == "prefix":
        return "b" if payload["kind"].startswith(rule["prefix"]) else "a"
    if kind == "shape":
        return "b" if isinstance(payload["items"], dict) else "a"
    raise CandidateError("unknown rule kind %r" % kind)


def _operands(rule: dict, spec: dict, payload: dict, mode: str) -> list:
    kind = rule["kind"]
    if kind == "key":
        return list(payload[spec["list_keys"][mode]])
    if kind in ("threshold", "prefix"):
        if "list_keys" in spec:
            return list(payload[spec["list_keys"][mode]])
        return list(payload["vals"])
    if kind == "shape":
        items = payload["items"]
        return list(items) if mode == "a" else list(items.values())
    raise CandidateError("unknown rule kind %r" % kind)


def _apply_op(op: str, values: list):
    if op == "sum":
        return sum(values, 0)
    if op == "prod":
        return math.prod(values)
    if op == "min":
        return min(values) if values else 0
    if op == "max":
        return max(values) if values else 0
    raise CandidateError("unknown op %r" % op)


def _ref_dia(spec: dict, payload: dict) -> dict:
    mode = _detect(spec["rule"], payload)
    values = _operands(spec["rule"], spec, payload, mode)
    return {"mode": mode, "result": _apply_op(spec["ops"][mode], values)}


def _ref_sng(spec: dict, payload: dict):
    op = spec["op"]
    if op == "window_sum":
        k = payload["k"]
        nums = payload["nums"]
        return {"total": sum(nums[max(0, len(nums) - k):], 0) if k > 0 else 0}
    if op == "gt_count":
        return {"count": sum(1 for n in payload["nums"]
                             if n > payload["threshold"])}
    if op == "get_default":
        return {"value": payload["m"].get(payload["key"], spec["default"])}
    if op == "format_pair":
        return {"text": "%s%s%s" % (payload["a"], spec["sep"], payload["b"])}
    raise CandidateError("unknown single op %r" % op)


def _ref_rw(spec: dict, payload: dict, conv: dict) -> dict:
    disc = spec.get("discount", 0)
    rows = payload["deliveries"]
    out = {"total": round(sum(row["n"] for row in rows) * (1 - disc), 2)}
    if spec.get("notes", False):
        out["notes"] = [row.get("note", "") for row in rows]
    return out


def _ref_cell(spec: dict, payload: dict) -> dict:
    factor = payload["factor"]
    values = [round(c["v"] * factor, 2) for c in payload["cells"]]
    return {"values": values, "total": round(sum(values, 0), 2)}


def reference(family: str, spec: dict, payload: dict, conv: dict | None = None):
    if family == "sep":
        return _ref_sep(spec, payload)
    if family == "cpl":
        return _ref_cpl(spec, payload)
    if family == "dia":
        return _ref_dia(spec, payload)
    if family == "sng":
        return _ref_sng(spec, payload)
    if family == "rw":
        if conv is None:
            raise CandidateError("rw reference needs its convention")
        return _ref_rw(spec, payload, conv)
    if family == "sco":
        if spec.get("kind", "cell") == "chain":
            return _ref_cpl(spec, payload)
        return _ref_cell(spec, payload)
    raise CandidateError("unknown task group %r" % family)


def run_candidate(src_dir: Path, payload: dict, timeout_s: float = 20.0):
    with tempfile.TemporaryDirectory(prefix="coord02-req-") as tmp:
        req = Path(tmp) / "req.json"
        resp = Path(tmp) / "resp.json"
        req.write_text(json.dumps(payload))
        try:
            proc = subprocess.run(
                [sys.executable, str(Path(src_dir) / "app.py"),
                 str(req), str(resp)],
                cwd=str(src_dir), capture_output=True, text=True,
                timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise CandidateError("candidate timed out: %s" % exc)
        if proc.returncode != 0:
            raise CandidateError("candidate exit %s: %s"
                                 % (proc.returncode, proc.stderr[-2000:]))
        try:
            return json.loads(resp.read_text())
        except (OSError, ValueError) as exc:
            raise CandidateError("candidate produced no valid output: %s; "
                                 "stderr: %s" % (exc, proc.stderr[-2000:]))


def evaluate_tree(src_dir: Path, cases: list) -> dict:
    passed = 0
    failures = []
    for case in cases:
        try:
            got = run_candidate(Path(src_dir), copy.deepcopy(case["input"]))
        except CandidateError as exc:
            failures.append({"input": case["input"],
                             "expected": case["expected"],
                             "got": None, "error": str(exc)})
            continue
        if got == case["expected"]:
            passed += 1
        else:
            failures.append({"input": case["input"],
                             "expected": case["expected"],
                             "got": got, "error": ""})
    return {"passed": passed, "failed": len(failures),
            "total": len(cases), "failures": failures}


def _ref_dir(task_id: str, kind: str) -> Path:
    fam = TASK_FAMILY[task_id]
    if fam == "sng":
        if task_id == "c02-t20" and kind == "valid":
            return REFERENCE / "sng" / "valid_split"
        op = load_spec(task_id)["op"]
        return REFERENCE / "sng" / ("%s_%s" % (kind, op))
    if fam == "dia" and kind == "invalid":
        kind = "invalid_op" if DIA_FAULT[task_id] == "detect" else "invalid_det"
    if fam == "sco":
        if task_id in ("c02-t27", "c02-t29"):
            return REFERENCE / "sco" / ("valid_renamed" if kind == "valid"
                                        else "invalid")
        if task_id == "c02-t30":
            return REFERENCE / "sco" / ("valid_chain" if kind == "valid"
                                        else "invalid")
        if kind == "invalid":
            return REFERENCE / "sco" / "invalid"
        return REFERENCE / "sco" / "valid_cell"
    return REFERENCE / fam / kind


def overlay_files(task_id: str, kind: str) -> dict:
    src = _ref_dir(task_id, kind)
    if task_id == "c02-t10" and kind in ("valid", "invalid"):
        names = ("maker.py", "shaper.py", "judge.py")
    elif task_id == "c02-t20" and kind == "valid":
        names = ("compute.py", "helper.py")
    elif TASK_FAMILY[task_id] == "sco" and task_id in ("c02-t27", "c02-t29"):
        names = ("zeta.py", "quux.py")
    elif task_id == "c02-t30":
        names = ("intake.py", "convert.py", "finalize.py")
    elif TASK_FAMILY[task_id] == "sco":
        names = ("producer.py", "consumer.py")
    elif TASK_FAMILY[task_id] == "sng":
        names = ("compute.py",)
    elif TASK_FAMILY[task_id] == "dia":
        names = ("detect.py", "operate.py")
    elif TASK_FAMILY[task_id] == "cpl":
        names = ("producer.py", "consumer.py")
    elif TASK_FAMILY[task_id] == "rw":
        names = ("emit.py", "render.py")
    else:
        names = ("names.py", "scores.py", "tags.py", "stats.py")
        if task_id == "c02-t05":
            names = ("names.py", "tags.py", "pconv.py", "cconv.py")
    return {name: (src / name).read_text() for name in names}


def task_files(task_id: str) -> dict:
    tdir = TASKS / task_id
    found = {}
    for name in ("spec.md", "spec.json", "public.json", "convention.json"):
        path = tdir / name
        if path.is_file():
            found[name] = path.read_text()
    for path in sorted((tdir / "src").glob("*.py")):
        found["src/" + path.name] = path.read_text()
    return found


def worker_files(task_id: str) -> list:
    return sorted(path for path in task_files(task_id)
                  if path.startswith("src/") and path != "src/app.py")


def prepare_tree(task_id: str, kind: str, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(TASKS / task_id, dest)
    if kind == "broken":
        return dest / "src"
    if kind in ("valid", "invalid"):
        overlays = overlay_files(task_id, kind)
    elif kind == "rework-stale":
        overlays = {"src/emit.py": (REFERENCE / "rw" / "rework"
                                    / "emit_v2.py").read_text(),
                    "src/render.py": (REFERENCE / "rw" / "valid"
                                      / "render.py").read_text(),
                    "convention.json": (REFERENCE / "rw" / "rework"
                                        / "convention_v2.json").read_text()}
    elif kind == "rework-fresh":
        overlays = {"src/emit.py": (REFERENCE / "rw" / "rework"
                                    / "emit_v2.py").read_text(),
                    "src/render.py": (REFERENCE / "rw" / "rework"
                                      / "render_v2.py").read_text(),
                    "convention.json": (REFERENCE / "rw" / "rework"
                                        / "convention_v2.json").read_text()}
    elif kind == "rework-carried":
        overlays = {"src/" + name: body
                    for name, body in overlay_files(task_id, "valid").items()}
        overlays["src/emit.py"] = (REFERENCE / "rw" / "rework"
                                   / "emit_alt.py").read_text()
    elif kind == "dia-stale":
        overlays = {"src/operate.py": (REFERENCE / "dia" / "stale_operate"
                                       / "operate.py").read_text()}
    else:
        raise CandidateError("unknown tree kind %r" % kind)
    for rel, body in overlays.items():
        if "/" in rel or rel in ("convention.json", "spec.json",
                                 "public.json", "spec.md"):
            target = dest / rel
        else:
            target = dest / "src" / rel
        target.write_text(body)
    return dest / "src"


def partial_tree(task_id: str, fixed: list, dest: Path,
                 base: str = "broken") -> Path:
    src = prepare_tree(task_id, base, dest)
    valid = overlay_files(task_id, "valid")
    for name in fixed:
        (dest / "src" / name).write_text(valid[name])
    return src


def observe(task_id: str, payload: dict, kind: str = "broken") -> dict:
    with tempfile.TemporaryDirectory(prefix="coord02-obs-") as tmp:
        src = prepare_tree(task_id, kind, Path(tmp) / "tree")
        try:
            return {"output": run_candidate(src, copy.deepcopy(payload))}
        except CandidateError as exc:
            return {"error": str(exc)}


def implicate(task_id: str) -> str:
    spec = load_spec(task_id)
    fam = TASK_FAMILY[task_id]
    for payload in DIA_PROBES[task_id]:
        seen = observe(task_id, payload)
        if "error" in seen:
            return "detect"
        want = reference(fam, spec, payload)
        if seen["output"].get("mode") != want.get("mode"):
            return "detect"
        if seen["output"] != want:
            return "operate"
    return "none"


def stale_after(task_id: str, changed, module: str) -> bool:
    deps = load_spec(task_id).get("deps", {})
    return bool(set(deps.get(module, ())) & set(changed))


def check_binding(task_id: str, profile_id: str) -> dict:
    iface = load_spec(task_id).get("interface", {})
    profile = PROFILES.get(profile_id)
    if profile is None:
        return {"eligible": False, "reason": "unknown-profile"}
    if iface.get("id") != profile["id"]:
        return {"eligible": False,
                "reason": "interface-mismatch: task declares %r, "
                          "profile requires %r" % (iface.get("id"),
                                                   profile["id"])}
    missing = [key for key in profile["keys"] if key not in iface.get("keys", [])]
    if missing:
        return {"eligible": False,
                "reason": "missing-keys: %s" % ",".join(missing)}
    return {"eligible": True, "reason": "bound"}


def _canon(value) -> bytes:
    return json.dumps(value, sort_keys=True,
                      separators=(",", ":")).encode()


def build_solver_payload(task_id: str) -> dict:
    return {"task_id": task_id, "spec": load_spec(task_id),
            "public": public_cases(task_id), "files": task_files(task_id)}


def task_input_digest(task_id: str) -> str:
    return hashlib.sha256(_canon(build_solver_payload(task_id))).hexdigest()


def participant_files(root: Path = ROOT) -> list:
    found = []
    tasks = root / "corpus" / "tasks"
    for task_dir in sorted(tasks.iterdir()):
        if not task_dir.is_dir():
            continue
        for name in ("spec.md", "spec.json", "public.json",
                     "convention.json"):
            path = task_dir / name
            if path.is_file():
                found.append(path)
        for path in sorted((task_dir / "src").glob("*.py")):
            found.append(path)
    return found


def _walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        yield value
        for item in value:
            yield from _walk(item)


def audit_barrier(root: Path = ROOT) -> list:
    problems = []
    files = participant_files(root)
    if not files:
        return ["no-participant-files"]
    texts = {}
    for path in files:
        try:
            texts[path] = path.read_text(encoding="utf-8")
        except OSError:
            problems.append("unreadable %s" % path.name)
    lowered = "\n".join(texts.values()).lower()
    for label in BANNED_LABELS:
        if label in lowered:
            problems.append("label %r visible in participant inputs" % label)
    hidden = []
    for task_id in ALL_TASKS:
        doc = PROTECTED / (task_id + ".json")
        try:
            cases = json.loads(doc.read_text())
        except (OSError, ValueError):
            problems.append("unreadable protected %s" % doc.name)
            continue
        for case in cases:
            hidden.append((task_id, _canon(case).decode()))
    for path, text in texts.items():
        if path.suffix != ".json":
            continue
        try:
            doc = json.loads(text)
        except ValueError:
            problems.append("unreadable participant %s" % path.name)
            continue
        seen = {_canon(node).decode() for node in _walk(doc)
                if isinstance(node, dict) and "input" in node
                and "expected" in node}
        for stem, needle in hidden:
            if needle in seen:
                problems.append("protected case for %s visible in %s"
                                % (stem, path.name))
    shipped = {}
    for task_id in ALL_TASKS:
        for rel, body in task_files(task_id).items():
            shipped[(task_id, rel)] = body
    for task_id in ALL_TASKS:
        try:
            valid = overlay_files(task_id, "valid")
        except (OSError, KeyError):
            problems.append("missing valid overlay for %s" % task_id)
            continue
        own = {path: text for path, text in texts.items()
               if path.suffix == ".py"
               and (TASKS / task_id) in path.parents}
        for name, body in valid.items():
            rel = "src/" + name
            if shipped.get((task_id, rel)) == body:
                continue
            needle = "".join(body.split())
            if len(needle) < 40:
                continue
            for path, text in own.items():
                if needle in "".join(text.split()):
                    problems.append("required fix for %s %s visible in %s"
                                    % (task_id, name, path.name))
    return sorted(set(problems))


def selftest() -> dict:
    outcome = {}
    with tempfile.TemporaryDirectory(prefix="coord02-self-") as tmp:
        for task_id in SPLITS["development"]:
            fam = TASK_FAMILY[task_id]
            spec = load_spec(task_id)
            cases = public_cases(task_id) + protected_cases(task_id)
            results = {}
            for kind in ("valid", "broken", "invalid"):
                src = prepare_tree(task_id, kind, Path(tmp) / task_id / kind)
                results[kind] = evaluate_tree(src, cases)
            entry = {"valid": results["valid"], "broken": results["broken"],
                     "invalid": results["invalid"]}
            if fam in ("cpl",):
                pub = public_cases(task_id)
                entry["invalid_public"] = evaluate_tree(
                    prepare_tree(task_id, "invalid",
                                 Path(tmp) / task_id / "invalid-pub"), pub)
            outcome[task_id] = entry
    return outcome
