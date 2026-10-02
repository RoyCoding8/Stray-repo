from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKS = ROOT / "tasks"
PROTECTED = ROOT / "protected"
REFERENCE = ROOT / "reference"

EVALUATOR_ID = "team01-oracle"
EVALUATOR_VERSION = "1.0.0"

FAMILIES = ("fam-ind", "fam-cpl", "fam-seq", "fam-sng")

SPLITS = {
    "development": ["team01-t01", "team01-t05", "team01-t09", "team01-t13"],
    "evaluation": ["team01-t02", "team01-t03", "team01-t06", "team01-t07",
                   "team01-t10", "team01-t11", "team01-t14", "team01-t15"],
    "transfer": ["team01-t04", "team01-t08", "team01-t12", "team01-t16"],
}

TASK_FAMILY = {
    "team01-t01": "fam-ind", "team01-t02": "fam-ind",
    "team01-t03": "fam-ind", "team01-t04": "fam-ind",
    "team01-t05": "fam-cpl", "team01-t06": "fam-cpl",
    "team01-t07": "fam-cpl", "team01-t08": "fam-cpl",
    "team01-t09": "fam-seq", "team01-t10": "fam-seq",
    "team01-t11": "fam-seq", "team01-t12": "fam-seq",
    "team01-t13": "fam-sng", "team01-t14": "fam-sng",
    "team01-t15": "fam-sng", "team01-t16": "fam-sng",
}

DEV_TASK = {"fam-ind": "team01-t01", "fam-cpl": "team01-t05",
            "fam-seq": "team01-t09", "fam-sng": "team01-t13"}

ALL_TASKS = [t for split in ("development", "evaluation", "transfer")
             for t in SPLITS[split]]


class CandidateError(Exception):
    pass


def load_spec(task_id: str) -> dict:
    return json.loads((TASKS / task_id / "spec.json").read_text())


def public_cases(task_id: str) -> list:
    return json.loads((TASKS / task_id / "public.json").read_text())


def protected_cases(task_id: str) -> list:
    return json.loads((PROTECTED / (task_id + ".json")).read_text())


def _ind_text(op: str, texts: list) -> list:
    if op == "strip_lower":
        return [t.strip().lower() for t in texts]
    if op == "dedup_sort":
        return sorted(set(texts))
    if op == "reverse":
        return [t[::-1] for t in texts]
    if op == "upper":
        return [t.upper() for t in texts]
    raise CandidateError("unknown text op %r" % op)


def _ind_num(op: str, numbers: list):
    if op == "sum":
        return sum(numbers, 0)
    if op == "span":
        return (max(numbers) - min(numbers)) if numbers else 0
    if op == "rmean":
        return round(sum(numbers, 0) / len(numbers), 2) if numbers else 0
    if op == "count_pos":
        return sum(1 for n in numbers if n > 0)
    raise CandidateError("unknown num op %r" % op)


def _ref_ind(spec: dict, payload: dict) -> dict:
    return {"texts": _ind_text(spec["text_op"], payload["texts"]),
            "numbers": _ind_num(spec["num_op"], payload["numbers"])}


def _ref_cpl(spec: dict, payload: dict) -> dict:
    units = spec["units"]
    want = payload["want"]
    values = []
    for reading in payload["readings"]:
        canonical = reading["v"] * units[reading["u"]]
        values.append(round(canonical / units[want], 2))
    return {"values": values}


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
    raise CandidateError("unknown seq op %r" % op)


def _ref_seq(spec: dict, payload: dict) -> dict:
    mode = _detect(spec["rule"], payload)
    values = _operands(spec["rule"], spec, payload, mode)
    return {"mode": mode, "result": _apply_op(spec["ops"][mode], values)}


def _ref_sng(spec: dict, payload: dict):
    op = spec["op"]
    if op == "window_sum":
        k = payload["k"]
        nums = payload["nums"]
        return {"total": sum(nums[len(nums) - k:], 0) if k > 0 else 0}
    if op == "gt_count":
        return {"count": sum(1 for n in payload["nums"]
                             if n > payload["threshold"])}
    if op == "get_default":
        return {"value": payload["m"].get(payload["key"], spec["default"])}
    if op == "format_pair":
        return {"text": "%s%s%s" % (payload["a"], spec["sep"], payload["b"])}
    raise CandidateError("unknown single op %r" % op)


def reference(family: str, spec: dict, payload: dict):
    if family == "fam-ind":
        return _ref_ind(spec, payload)
    if family == "fam-cpl":
        return _ref_cpl(spec, payload)
    if family == "fam-seq":
        return _ref_seq(spec, payload)
    if family == "fam-sng":
        return _ref_sng(spec, payload)
    raise CandidateError("unknown family %r" % family)


def run_candidate(src_dir: Path, payload: dict, timeout_s: float = 20.0):
    with tempfile.TemporaryDirectory(prefix="team01-req-") as tmp:
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


def prepare_tree(task_id: str, kind: str, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(TASKS / task_id, dest)
    if kind in ("valid", "invalid"):
        overlay = REFERENCE / TASK_FAMILY[task_id] / kind
        for path in sorted(overlay.glob("*.py")):
            if path.name.startswith("local_"):
                continue
            shutil.copy(path, dest / "src" / path.name)
    elif kind != "broken":
        raise CandidateError("unknown tree kind %r" % kind)
    return dest / "src"


def _run_local_checks(family: str) -> dict:
    overlay = REFERENCE / family / "invalid"
    results = {}
    for path in sorted(overlay.glob("local_*.py")):
        try:
            proc = subprocess.run(
                [sys.executable, str(path)], cwd=str(overlay),
                capture_output=True, text=True, timeout=20.0)
            results[path.stem] = proc.returncode == 0
        except subprocess.TimeoutExpired:
            results[path.stem] = False
    return results


def selftest() -> dict:
    outcome = {}
    with tempfile.TemporaryDirectory(prefix="team01-self-") as tmp:
        for family in FAMILIES:
            dev = DEV_TASK[family]
            spec = load_spec(dev)
            cases = public_cases(dev) + protected_cases(dev)
            valid_src = prepare_tree(dev, "valid", Path(tmp) / family / "valid")
            invalid_src = prepare_tree(dev, "invalid",
                                       Path(tmp) / family / "invalid")
            valid = evaluate_tree(valid_src, cases)
            invalid = evaluate_tree(invalid_src, cases)
            entry = {"valid": valid, "invalid": invalid}
            local = _run_local_checks(family)
            if local:
                entry["local"] = local
            outcome[family] = entry
    return outcome
