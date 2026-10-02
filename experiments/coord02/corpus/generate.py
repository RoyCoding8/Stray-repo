from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

COORD02 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COORD02.parent.parent))

from experiments.coord02 import oracle

CONV_V1 = {"scale": 10, "in_key": "qty", "version": 1}
CONV_V2 = {"scale": 100, "in_key": "amount", "version": 2}

CORRECT = {
    "names": 'def transform(items):\n    return [s.strip().lower() for s in items]\n',
    "scores": 'def adjust(items, lo, hi):\n    return [round(min(hi, max(lo, x)), 2) for x in items]\n',
    "tags": 'def tidy(items):\n    return sorted(set(items))\n',
    "stats": 'def describe(values):\n    return round(sum(values, 0) / len(values), 2) if values else 0\n',
    "pconv": 'from decimal import Decimal, ROUND_HALF_UP\n\n\ndef convert(readings, units, want):\n    out = []\n    for r in readings:\n        x = r["v"] * units[r["u"]] / units[want]\n        q = Decimal(str(x)).quantize(Decimal("0.01"),\n                                     rounding=ROUND_HALF_UP)\n        out.append(float(q))\n    return out\n',
    "cconv": 'def label(values, lo, hi):\n    return ["low" if v < lo else "high" if v > hi else "ok"\n            for v in values]\n',
    "producer": 'def to_base(v, u, units):\n    return v * units[u]\n',
    "consumer": 'from decimal import Decimal, ROUND_HALF_UP\n\n\ndef from_base(x, want, units):\n    q = Decimal(str(x / units[want])).quantize(\n        Decimal("0.01"), rounding=ROUND_HALF_UP)\n    return float(q)\n\n\ndef flag(v, lo, hi):\n    return "low" if v < lo else "high" if v > hi else "ok"\n',
    "maker": 'def to_base(v, u, units):\n    return v * units[u]\n',
    "shaper": 'from decimal import Decimal, ROUND_HALF_UP\n\n\ndef from_base(x, want, units):\n    q = Decimal(str(x / units[want])).quantize(\n        Decimal("0.01"), rounding=ROUND_HALF_UP)\n    return float(q)\n',
    "judge": 'def flag(v, lo, hi):\n    return "low" if v < lo else "high" if v > hi else "ok"\n',
    "detect": 'def classify(rule, payload):\n    kind = rule["kind"]\n    if kind == "key":\n        return "b" if rule["key"] in payload else "a"\n    if kind == "threshold":\n        return "b" if payload["code"] >= rule["at"] else "a"\n    if kind == "prefix":\n        return "b" if payload["kind"].startswith(rule["prefix"]) else "a"\n    if kind == "shape":\n        return "b" if isinstance(payload["items"], dict) else "a"\n    raise ValueError("unknown rule kind")\n',
    "operate": 'import math\n\n\ndef _operands(rule, spec, payload, mode):\n    kind = rule["kind"]\n    if kind == "key":\n        return list(payload[spec["list_keys"][mode]])\n    if kind in ("threshold", "prefix"):\n        if "list_keys" in spec:\n            return list(payload[spec["list_keys"][mode]])\n        return list(payload["vals"])\n    items = payload["items"]\n    return list(items) if mode == "a" else list(items.values())\n\n\ndef compute(rule, spec, payload, mode):\n    values = _operands(rule, spec, payload, mode)\n    op = spec["ops"][mode]\n    if op == "sum":\n        return sum(values, 0)\n    if op == "prod":\n        return math.prod(values)\n    if op == "min":\n        return min(values) if values else 0\n    if op == "max":\n        return max(values) if values else 0\n    raise ValueError("unknown op")\n',
    "emit": 'def packet(row, conv):\n    return {conv["in_key"]: row["n"] * conv["scale"]}\n',
    "render": 'def total(packets, conv, discount=0):\n    return round(sum(p["qty"] for p in packets)\n                 / conv["scale"] * (1 - discount), 2)\n',
    "cell_producer": 'def scale(cells, factor):\n    return [round(c["v"] * factor, 2) for c in cells]\n',
    "cell_consumer": 'def summarize(values):\n    return round(sum(values, 0), 2)\n',
    "intake": 'def extract(parcels):\n    return [(p["v"], p["u"]) for p in parcels]\n',
    "convert": 'from decimal import Decimal, ROUND_HALF_UP\n\n\ndef to_want(pairs, units, want):\n    out = []\n    for v, u in pairs:\n        x = v * units[u] / units[want]\n        q = Decimal(str(x)).quantize(Decimal("0.01"),\n                                     rounding=ROUND_HALF_UP)\n        out.append(float(q))\n    return out\n',
    "finalize": 'def check(values, lo, hi):\n    return ["low" if v < lo else "high" if v > hi else "ok"\n            for v in values]\n',
}

SNG_CORRECT = {
    "window_sum": 'def evaluate(payload, spec):\n    k = payload["k"]\n    nums = payload["nums"]\n    if k <= 0:\n        return {"total": 0}\n    return {"total": sum(nums[max(0, len(nums) - k):], 0)}\n',
    "gt_count": 'def evaluate(payload, spec):\n    return {"count": sum(1 for n in payload["nums"]\n                         if n > payload["threshold"])}\n',
    "get_default": 'def evaluate(payload, spec):\n    return {"value": payload["m"].get(payload["key"], spec["default"])}\n',
    "format_pair": 'def evaluate(payload, spec):\n    return {"text": "%s%s%s" % (payload["a"], spec["sep"], payload["b"])}\n',
}

SNG_BROKEN = {
    "window_sum": 'def evaluate(payload, spec):\n    k = payload["k"]\n    nums = payload["nums"]\n    if k <= 0:\n        return {"total": 0}\n    return {"total": sum(nums[:k], 0)}\n',
    "gt_count": 'def evaluate(payload, spec):\n    return {"count": sum(1 for n in payload["nums"]\n                         if n >= payload["threshold"])}\n',
    "get_default": 'def evaluate(payload, spec):\n    return {"value": payload["m"].get(payload["key"])}\n',
    "format_pair": 'def evaluate(payload, spec):\n    return {"text": "%s%s%s" % (payload["b"], spec["sep"], payload["a"])}\n',
}

SNG_INVALID = {
    "window_sum": 'def evaluate(payload, spec):\n    k = payload["k"]\n    nums = payload["nums"]\n    if k <= 0:\n        return {"total": 0}\n    return {"total": sum(nums[len(nums) - k + 1:], 0) if k > 1\n            else sum(nums[len(nums) - k:], 0)}\n',
    "gt_count": 'def evaluate(payload, spec):\n    return {"count": sum(1 for n in payload["nums"]\n                         if n > payload["threshold"] + 1)}\n',
    "get_default": 'def evaluate(payload, spec):\n    return {"value": payload["m"][payload["key"]]\n            if payload["m"].get(payload["key"]) else spec["default"]}\n',
    "format_pair": 'def evaluate(payload, spec):\n    return {"text": "%s %s" % (payload["a"], payload["b"])}\n',
}

BROKEN = {
    "names": 'def transform(items):\n    return [s.lower() for s in items]\n',
    "scores": 'def adjust(items, lo, hi):\n    return [round(x, 2) for x in items]\n',
    "tags": 'def tidy(items):\n    return sorted(items)\n',
    "stats": 'def describe(values):\n    return round(sum(values, 0), 2)\n',
    "pconv": 'def convert(readings, units, want):\n    return [r["v"] for r in readings]\n',
    "cconv": 'def label(values, lo, hi):\n    return ["ok" for _ in values]\n',
    "producer": 'def to_base(v, u, units):\n    return v\n',
    "consumer": 'def from_base(x, want, units):\n    return round(x * units[want], 2)\n\n\ndef flag(v, lo, hi):\n    return "ok"\n',
    "maker": 'def to_base(v, u, units):\n    return v\n',
    "shaper": 'def from_base(x, want, units):\n    return round(x * units[want], 2)\n',
    "judge": 'def flag(v, lo, hi):\n    return "ok"\n',
    "detect": 'def classify(rule, payload):\n    return "a"\n',
    "operate": 'import math\n\n\ndef _operands(rule, spec, payload, mode):\n    kind = rule["kind"]\n    if kind == "key":\n        return list(payload[spec["list_keys"][mode]])\n    if kind in ("threshold", "prefix"):\n        if "list_keys" in spec:\n            return list(payload[spec["list_keys"][mode]])\n        return list(payload["vals"])\n    items = payload["items"]\n    return list(items) if mode == "a" else list(items.values())\n\n\ndef compute(rule, spec, payload, mode):\n    values = _operands(rule, spec, payload, mode)\n    op = spec["ops"]["a"]\n    if op == "sum":\n        return sum(values, 0)\n    if op == "prod":\n        return math.prod(values)\n    if op == "min":\n        return min(values) if values else 0\n    if op == "max":\n        return max(values) if values else 0\n    raise ValueError("unknown op")\n',
    "operate_v1keys": 'import math\n\nV1_KEYS = {"a": "xs", "b": "ys"}\n\n\ndef compute(rule, spec, payload, mode):\n    values = list(payload[V1_KEYS[mode]])\n    op = spec["ops"][mode]\n    if op == "sum":\n        return sum(values, 0)\n    if op == "prod":\n        return math.prod(values)\n    if op == "min":\n        return min(values) if values else 0\n    if op == "max":\n        return max(values) if values else 0\n    raise ValueError("unknown op")\n',
    "emit": 'def packet(row, conv):\n    return {"qty": row["n"]}\n',
    "render": 'def total(packets, conv, discount=0):\n    return round(sum(p["qty"] for p in packets) * conv["scale"], 2)\n',
    "cell_producer": 'def scale(cells, factor):\n    return [c["v"] for c in cells]\n',
    "cell_consumer": 'def summarize(values):\n    return sum(values, 0)\n',
    "intake": 'def extract(parcels):\n    return [(p["v"], p["u"]) for p in parcels]\n',
    "convert": 'def to_want(pairs, units, want):\n    return [v * units[want] for v, u in pairs]\n',
    "finalize": 'def check(values, lo, hi):\n    return ["ok" for _ in values]\n',
}

INVALID = {
    "consumer": 'def from_base(x, want, units):\n    return round(x / units[want], 2)\n\n\ndef flag(v, lo, hi):\n    return "low" if v < lo else "ok" if v < hi else "high"\n',
    "shaper": 'def from_base(x, want, units):\n    return round(x / units[want], 2)\n',
    "judge": 'def flag(v, lo, hi):\n    return "low" if v < lo else "ok" if v < hi else "high"\n',
    "pconv_halfeven": 'def convert(readings, units, want):\n    return [round(r["v"] * units[r["u"]] / units[want], 2)\n            for r in readings]\n',
    "cconv_exclusive": 'def label(values, lo, hi):\n    return ["low" if v < lo else "ok" if v < hi else "high"\n            for v in values]\n',
    "cell_consumer": 'def summarize(values):\n    return round(sum(values, 0), 1)\n',
    "chain_convert": 'def to_want(pairs, units, want):\n    return [round(v * units[u] / units[want], 2) for v, u in pairs]\n',
    "chain_finalize": 'def check(values, lo, hi):\n    return ["low" if v < lo else "ok" if v < hi else "high"\n            for v in values]\n',
}

REWORK = {
    "emit_v2": 'def packet(row, conv):\n    return {conv["in_key"]: row["n"] * conv["scale"]}\n',
    "render_v2": 'def total(packets, conv, discount=0):\n    key = conv["in_key"]\n    return round(sum(p[key] for p in packets)\n                 / conv["scale"] * (1 - discount), 2)\n',
    "emit_alt": 'def packet(row, conv):\n    total = 0\n    for _ in range(1):\n        total = row["n"] * conv["scale"]\n    return {"qty": total}\n',
}

HELPER = {
    "broken": 'def last_k(nums, k):\n    if k <= 0:\n        return []\n    return nums[:k]\n',
    "valid": 'def last_k(nums, k):\n    if k <= 0:\n        return []\n    return nums[max(0, len(nums) - k):]\n',
}

SNG_COMPUTE_HELPER = {
    "broken": 'from helper import last_k\n\n\ndef evaluate(payload, spec):\n    if payload["k"] <= 0:\n        return {"total": 0}\n    return {"total": sum(last_k(payload["nums"], payload["k"]), 0)}\n',
    "valid": 'from helper import last_k\n\n\ndef evaluate(payload, spec):\n    if payload["k"] <= 0:\n        return {"total": 0}\n    return {"total": sum(last_k(payload["nums"], payload["k"]), 0)}\n',
}

APP = {
    "sep": 'import json\nimport sys\nfrom pathlib import Path\n\nimport names\nimport scores\nimport tags\nimport stats\n\n\ndef main(argv):\n    here = Path(__file__).resolve().parent\n    spec = json.loads((here.parent / "spec.json").read_text())\n    payload = json.loads(Path(argv[1]).read_text())\n    lo, hi = spec["bounds"]\n    out = {"names": names.transform(payload["names"]),\n           "scores": scores.adjust(payload["scores"], lo, hi),\n           "tags": tags.tidy(payload["tags"]),\n           "stat": stats.describe(payload["values"])}\n    Path(argv[2]).write_text(json.dumps(out))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main(sys.argv))\n',
    "sep_mixed": 'import json\nimport sys\nfrom pathlib import Path\n\nimport names\nimport tags\nimport pconv\nimport cconv\n\n\ndef main(argv):\n    here = Path(__file__).resolve().parent\n    spec = json.loads((here.parent / "spec.json").read_text())\n    payload = json.loads(Path(argv[1]).read_text())\n    values = pconv.convert(payload["readings"], spec["units"],\n                           payload["want"])\n    lo, hi = spec["cbounds"]\n    out = {"names": names.transform(payload["names"]),\n           "tags": tags.tidy(payload["tags"]),\n           "values": values,\n           "flags": cconv.label(values, lo, hi)}\n    Path(argv[2]).write_text(json.dumps(out))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main(sys.argv))\n',
    "cpl": 'import json\nimport sys\nfrom pathlib import Path\n\nimport producer\nimport consumer\n\n\ndef main(argv):\n    here = Path(__file__).resolve().parent\n    spec = json.loads((here.parent / "spec.json").read_text())\n    payload = json.loads(Path(argv[1]).read_text())\n    units = spec["units"]\n    base = [producer.to_base(r["v"], r["u"], units)\n            for r in payload["readings"]]\n    lo, hi = spec["bounds"]\n    out = {"values": [consumer.from_base(x, payload["want"], units)\n                      for x in base],\n           "flags": []}\n    out["flags"] = [consumer.flag(v, lo, hi) for v in out["values"]]\n    Path(argv[2]).write_text(json.dumps(out))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main(sys.argv))\n',
    "cpl_chain": 'import json\nimport sys\nfrom pathlib import Path\n\nimport maker\nimport shaper\nimport judge\n\n\ndef main(argv):\n    here = Path(__file__).resolve().parent\n    spec = json.loads((here.parent / "spec.json").read_text())\n    payload = json.loads(Path(argv[1]).read_text())\n    units = spec["units"]\n    base = [maker.to_base(r["v"], r["u"], units)\n            for r in payload["readings"]]\n    values = [shaper.from_base(x, payload["want"], units) for x in base]\n    lo, hi = spec["bounds"]\n    out = {"values": values,\n           "flags": [judge.flag(v, lo, hi) for v in values]}\n    Path(argv[2]).write_text(json.dumps(out))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main(sys.argv))\n',
    "dia": 'import json\nimport sys\nfrom pathlib import Path\n\nimport detect\nimport operate\n\n\ndef main(argv):\n    here = Path(__file__).resolve().parent\n    spec = json.loads((here.parent / "spec.json").read_text())\n    payload = json.loads(Path(argv[1]).read_text())\n    mode = detect.classify(spec["rule"], payload)\n    out = {"mode": mode,\n           "result": operate.compute(spec["rule"], spec, payload, mode)}\n    Path(argv[2]).write_text(json.dumps(out))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main(sys.argv))\n',
    "sng": 'import json\nimport sys\nfrom pathlib import Path\n\nimport compute\n\n\ndef main(argv):\n    here = Path(__file__).resolve().parent\n    spec = json.loads((here.parent / "spec.json").read_text())\n    payload = json.loads(Path(argv[1]).read_text())\n    Path(argv[2]).write_text(json.dumps(compute.evaluate(payload, spec)))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main(sys.argv))\n',
    "rw": 'import json\nimport sys\nfrom pathlib import Path\n\nimport emit\nimport render\n\n\ndef main(argv):\n    here = Path(__file__).resolve().parent\n    spec = json.loads((here.parent / "spec.json").read_text())\n    conv = json.loads((here.parent / "convention.json").read_text())\n    payload = json.loads(Path(argv[1]).read_text())\n    packets = [emit.packet(row, conv) for row in payload["deliveries"]]\n    out = {"total": render.total(packets, conv, spec.get("discount", 0))}\n    if spec.get("notes", False):\n        out["notes"] = [row.get("note", "")\n                        for row in payload["deliveries"]]\n    Path(argv[2]).write_text(json.dumps(out))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main(sys.argv))\n',
    "cell": 'import json\nimport sys\nfrom pathlib import Path\n\nimport producer\nimport consumer\n\n\ndef main(argv):\n    here = Path(__file__).resolve().parent\n    spec = json.loads((here.parent / "spec.json").read_text())\n    payload = json.loads(Path(argv[1]).read_text())\n    values = producer.scale(payload["cells"], payload["factor"])\n    out = {"values": values, "total": consumer.summarize(values)}\n    Path(argv[2]).write_text(json.dumps(out))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main(sys.argv))\n',
    "renamed": 'import json\nimport sys\nfrom pathlib import Path\n\nimport zeta\nimport quux\n\n\ndef main(argv):\n    here = Path(__file__).resolve().parent\n    spec = json.loads((here.parent / "spec.json").read_text())\n    payload = json.loads(Path(argv[1]).read_text())\n    values = zeta.scale(payload["cells"], payload["factor"])\n    out = {"values": values, "total": quux.summarize(values)}\n    Path(argv[2]).write_text(json.dumps(out))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main(sys.argv))\n',
    "chain": 'import json\nimport sys\nfrom pathlib import Path\n\nimport intake\nimport convert\nimport finalize\n\n\ndef main(argv):\n    here = Path(__file__).resolve().parent\n    spec = json.loads((here.parent / "spec.json").read_text())\n    payload = json.loads(Path(argv[1]).read_text())\n    pairs = intake.extract(payload["parcels"])\n    values = convert.to_want(pairs, spec["units"], payload["want"])\n    lo, hi = spec["bounds"]\n    out = {"values": values,\n           "flags": finalize.check(values, lo, hi)}\n    Path(argv[2]).write_text(json.dumps(out))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main(sys.argv))\n',
}


def spec_for(task_id: str) -> dict:
    if task_id in ("c02-t01", "c02-t04"):
        return {"layout": ["names", "scores", "tags", "stats"],
                "bounds": [0, 100]}
    if task_id == "c02-t02":
        return {"layout": ["names", "scores", "tags", "stats"],
                "bounds": [-50, 50]}
    if task_id == "c02-t03":
        return {"layout": ["names", "scores", "tags", "stats"],
                "bounds": [0, 10]}
    if task_id == "c02-t05":
        return {"layout": ["names", "tags", "pconv", "cconv"],
                "units": {"s": 1, "m": 200}, "cbounds": [0, 5],
                "rounding": "half-up", "boundary": "inclusive",
                "topology": "mixed-groups"}
    if task_id in ("c02-t06", "c02-t08"):
        return {"units": {"cm": 10, "m": 1000, "mm": 1},
                "bounds": [0, 50] if task_id == "c02-t06" else [1, 20],
                "rounding": "half-up", "boundary": "inclusive"}
    if task_id in ("c02-t07", "c02-t09"):
        return {"units": {"g": 1, "kg": 1000},
                "bounds": [0, 10] if task_id == "c02-t07" else [0, 5],
                "rounding": "half-up", "boundary": "inclusive"}
    if task_id == "c02-t10":
        return {"units": {"A": 200, "B": 1}, "bounds": [0, 2],
                "rounding": "half-up", "boundary": "inclusive",
                "topology": "chain3"}
    if task_id == "c02-t11":
        return {"rule": {"kind": "key", "key": "flag"},
                "list_keys": {"a": "xs", "b": "ys"},
                "ops": {"a": "sum", "b": "prod"}}
    if task_id == "c02-t12":
        return {"rule": {"kind": "threshold", "at": 5},
                "ops": {"a": "sum", "b": "prod"}}
    if task_id == "c02-t13":
        return {"rule": {"kind": "prefix", "prefix": "beta"},
                "ops": {"a": "min", "b": "max"}}
    if task_id == "c02-t14":
        return {"rule": {"kind": "shape"},
                "ops": {"a": "sum", "b": "prod"}}
    if task_id == "c02-t15":
        return {"rule": {"kind": "threshold", "at": 5},
                "list_keys": {"a": "xs", "b": "zs"},
                "ops": {"a": "prod", "b": "sum"}, "convention": "v2",
                "deps": {"detect.py": ["spec:rule"],
                         "operate.py": ["spec:rule", "spec:list_keys"]}}
    if task_id in ("c02-t16", "c02-t20"):
        return {"op": "window_sum",
                "topology": "delegated" if task_id == "c02-t20"
                            else "single"}
    if task_id == "c02-t17":
        return {"op": "gt_count"}
    if task_id == "c02-t18":
        return {"op": "get_default", "default": "n/a"}
    if task_id == "c02-t19":
        return {"op": "format_pair", "sep": "-"}
    if task_id in ("c02-t21", "c02-t22", "c02-t23", "c02-t24"):
        return {"deps": {"emit.py": ["convention.json"],
                         "render.py": ["convention.json", "emit.py"]}}
    if task_id == "c02-t25":
        return {"deps": {"emit.py": ["convention.json"],
                         "render.py": ["convention.json", "emit.py"]},
                "discount": 0.1, "notes": True, "semantics": "discounted"}
    if task_id in ("c02-t26", "c02-t27", "c02-t28", "c02-t29"):
        return {"interface": {"id": "cellsum/1", "version": 1,
                              "keys": ["cells", "factor"]}}
    if task_id == "c02-t30":
        return {"interface": {"id": "cellchain/1", "version": 1,
                              "keys": ["parcels", "want"]},
                "kind": "chain", "units": {"p": 40, "q": 1},
                "bounds": [0, 2], "rounding": "half-up",
                "boundary": "inclusive", "topology": "renamed-chain"}
    raise ValueError("unknown task %s" % task_id)


def _sep_payloads(i: int, lo: int, hi: int):
    names = [["  ALPHA ", "bravo  "], ["  CHARLIE", "  delta "],
             ["Echo", "  FOXTROT  "], ["  golf ", "HOTEL"],
             ["  india", "Juliet  "], ["KILO  ", "  lima"],
             ["  MIKE", "november "], ["  oscar  ", "PAPA"],
             ["quebec", "  ROMEO "]]
    scores = [[10, 20 + 5 * i], [30 + i, 40], [50, 60 + i], [70, 80 - i]]
    tags = [["b", "a"], ["x"], ["m", "n", "m"], ["z", "y"]]
    values = [[1, 2, 3], [4.5, 5.5], [10], [7, 8, 9]]
    pub = [{"names": names[(i + k) % 9], "scores": list(scores[k]),
            "tags": list(tags[k]), "values": list(values[k])}
           for k in range(4)]
    pub[1]["scores"] = [hi + 25, lo - 5, 50]
    pub[2]["tags"] = ["m", "n", "m"]
    prot = [
        {"names": [], "scores": [], "tags": [], "values": []},
        {"names": names[(i + 5) % 9], "scores": [lo, hi, lo - 1, hi + 1],
         "tags": ["solo"], "values": [1, 2, 2]},
        {"names": ["  DUP "], "scores": [5], "tags": ["b", "a", "b", "A"],
         "values": [9]},
        {"names": names[(i + 7) % 9], "scores": [lo + 1],
         "tags": [], "values": [2, 2, 2, 2]},
        {"names": [" x "], "scores": [hi], "tags": ["q", "q"],
         "values": [0.5, 1.5]},
    ]
    return pub, prot


def _mixed_payloads():
    pub = [
        {"names": ["  ALPHA "], "tags": ["b", "a"],
         "readings": [{"v": 400, "u": "s"}], "want": "m"},
        {"names": ["bravo"], "tags": ["x"],
         "readings": [{"v": 200, "u": "s"}, {"v": 1, "u": "m"}],
         "want": "m"},
        {"names": ["  C "], "tags": ["m", "m"],
         "readings": [{"v": 0, "u": "s"}], "want": "m"},
        {"names": ["d"], "tags": [],
         "readings": [{"v": 600, "u": "s"}, {"v": 200, "u": "s"}],
         "want": "m"},
    ]
    prot = [
        {"names": [], "tags": [],
         "readings": [{"v": 535, "u": "s"}], "want": "m"},
        {"names": ["  HI "], "tags": ["t"],
         "readings": [{"v": 1000, "u": "s"}], "want": "m"},
        {"names": ["e"], "tags": ["a", "b", "a"],
         "readings": [{"v": 400, "u": "s"}, {"v": 1, "u": "s"}],
         "want": "m"},
        {"names": ["  F", "g  "], "tags": ["z"],
         "readings": [], "want": "m"},
        {"names": ["h"], "tags": ["q", "q"],
         "readings": [{"v": 3, "u": "m"}], "want": "m"},
    ]
    return pub, prot


CPL_PAYLOADS = {
    "c02-t06": (
        [{"readings": [{"v": 1500, "u": "cm"}], "want": "m"},
         {"readings": [{"v": 250, "u": "cm"}, {"v": 2, "u": "m"}],
          "want": "m"},
         {"readings": [{"v": 0, "u": "mm"}], "want": "m"},
         {"readings": [{"v": 3200, "u": "mm"}], "want": "m"}],
        [{"readings": [{"v": 2675, "u": "mm"}], "want": "m"},
         {"readings": [{"v": 50000, "u": "mm"}], "want": "m"},
         {"readings": [{"v": 500, "u": "mm"}], "want": "m"},
         {"readings": [], "want": "m"},
         {"readings": [{"v": 3, "u": "m"}, {"v": 13, "u": "mm"}],
          "want": "m"}]),
    "c02-t07": (
        [{"readings": [{"v": 1500, "u": "g"}], "want": "kg"},
         {"readings": [{"v": 250, "u": "g"}, {"v": 2, "u": "kg"}],
          "want": "kg"},
         {"readings": [{"v": 0, "u": "g"}], "want": "kg"},
         {"readings": [{"v": 3100, "u": "g"}], "want": "kg"}],
        [{"readings": [{"v": 2675, "u": "g"}], "want": "kg"},
         {"readings": [{"v": 10000, "u": "g"}], "want": "kg"},
         {"readings": [{"v": 500, "u": "g"}], "want": "kg"},
         {"readings": [], "want": "kg"},
         {"readings": [{"v": 3, "u": "kg"}, {"v": 13, "u": "g"}],
          "want": "kg"}]),
    "c02-t08": (
        [{"readings": [{"v": 1600, "u": "cm"}], "want": "m"},
         {"readings": [{"v": 260, "u": "cm"}, {"v": 2, "u": "m"}],
          "want": "m"},
         {"readings": [{"v": 1000, "u": "mm"}], "want": "m"},
         {"readings": [{"v": 3300, "u": "mm"}], "want": "m"}],
        [{"readings": [{"v": 2675, "u": "mm"}], "want": "m"},
         {"readings": [{"v": 20000, "u": "mm"}], "want": "m"},
         {"readings": [{"v": 1500, "u": "mm"}], "want": "m"},
         {"readings": [], "want": "m"},
         {"readings": [{"v": 3, "u": "m"}, {"v": 17, "u": "mm"}],
          "want": "m"}]),
    "c02-t09": (
        [{"readings": [{"v": 1600, "u": "g"}], "want": "kg"},
         {"readings": [{"v": 260, "u": "g"}, {"v": 1, "u": "kg"}],
          "want": "kg"},
         {"readings": [{"v": 0, "u": "g"}], "want": "kg"},
         {"readings": [{"v": 3300, "u": "g"}], "want": "kg"}],
        [{"readings": [{"v": 2675, "u": "g"}], "want": "kg"},
         {"readings": [{"v": 5000, "u": "g"}], "want": "kg"},
         {"readings": [{"v": 500, "u": "g"}], "want": "kg"},
         {"readings": [], "want": "kg"},
         {"readings": [{"v": 2, "u": "kg"}, {"v": 17, "u": "g"}],
          "want": "kg"}]),
    "c02-t10": (
        [{"readings": [{"v": 300, "u": "B"}], "want": "A"},
         {"readings": [{"v": 250, "u": "B"}, {"v": 1, "u": "A"}],
          "want": "A"},
         {"readings": [{"v": 0, "u": "B"}], "want": "A"},
         {"readings": [{"v": 3400, "u": "B"}], "want": "A"}],
        [{"readings": [{"v": 535, "u": "B"}], "want": "A"},
         {"readings": [{"v": 400, "u": "B"}], "want": "A"},
         {"readings": [{"v": 100, "u": "B"}], "want": "A"},
         {"readings": [], "want": "A"},
         {"readings": [{"v": 1, "u": "A"}, {"v": 25, "u": "B"}],
          "want": "A"}]),
}


DIA_PAYLOADS = {
    "c02-t11": (
        [{"xs": [1, 2], "ys": [9]}, {"flag": 0, "xs": [3], "ys": [2, 5]},
         {"xs": [], "ys": [4]}, {"flag": "x", "xs": [1], "ys": [6, 7]}],
        [{"xs": [5], "ys": [5, 5]}, {"flag": None, "xs": [2, 2], "ys": [3]},
         {"xs": [10, 20], "ys": []}, {"flag": False, "xs": [], "ys": []},
         {"xs": [-1, 1], "ys": [-2, 3]}]),
    "c02-t12": (
        [{"code": 3, "vals": [2, 5]}, {"code": 9, "vals": [2, 5]},
         {"code": 0, "vals": []}, {"code": 5, "vals": [1, 1, 1]}],
        [{"code": 4, "vals": [7]}, {"code": 6, "vals": [7]},
         {"code": 5, "vals": []}, {"code": 100, "vals": [-1, 2]},
         {"code": -3, "vals": [0]}]),
    "c02-t13": (
        [{"kind": "alpha", "vals": [4, 7]}, {"kind": "beta", "vals": [4, 7]},
         {"kind": "alpha-x", "vals": [1]}, {"kind": "beta-x", "vals": [9, 2]}],
        [{"kind": "bet", "vals": [3, 3]}, {"kind": "beta", "vals": []},
         {"kind": "", "vals": [5]}, {"kind": "Beta", "vals": [2, 8]},
         {"kind": "beta!", "vals": [-4, -1]}]),
    "c02-t14": (
        [{"items": [2, 3]}, {"items": {"p": 2, "q": 3}},
         {"items": []}, {"items": {"z": 5}}],
        [{"items": {}}, {"items": [0]}, {"items": {"a": 1, "b": 1}},
         {"items": [-2, 4]}, {"items": {"m": -3, "n": -3}}]),
    "c02-t15": (
        [{"code": 2, "xs": [2, 3], "zs": [9]},
         {"code": 8, "xs": [2], "zs": [4, 5]},
         {"code": 5, "xs": [1], "zs": []},
         {"code": 0, "xs": [6], "zs": [2]}],
        [{"code": 4, "xs": [3, 3], "zs": [1]},
         {"code": 6, "xs": [1], "zs": [8, 8]},
         {"code": 5, "xs": [], "zs": [2, 2]},
         {"code": 9, "xs": [7], "zs": []},
         {"code": 1, "xs": [4, 4], "zs": [3, 3, 3]}]),
}

SNG_PAYLOADS = {
    "window_sum": (
        [{"nums": [1, 2, 3, 4], "k": 2}, {"nums": [5], "k": 1},
         {"nums": [1, 2, 3], "k": 3}, {"nums": [9, 8], "k": 0}],
        [{"nums": [], "k": 2}, {"nums": [1, 2], "k": 5},
         {"nums": [7], "k": 0}, {"nums": [3, 1, 4, 1, 5], "k": 4},
         {"nums": [-2, 5], "k": 1}]),
    "gt_count": (
        [{"nums": [1, 6, 3, 7], "threshold": 5}, {"nums": [], "threshold": 0},
         {"nums": [5, 5], "threshold": 5},
         {"nums": [-1, -6], "threshold": -5}],
        [{"nums": [6], "threshold": 5}, {"nums": [4, 5, 6], "threshold": 5},
         {"nums": [0], "threshold": 0}, {"nums": [10, 10, 10], "threshold": 9},
         {"nums": [2, 3], "threshold": 3}]),
    "get_default": (
        [{"m": {"a": 1}, "key": "b"}, {"m": {"a": 1}, "key": "a"},
         {"m": {}, "key": "x"}, {"m": {"k": 0}, "key": "k"}],
        [{"m": {"k": ""}, "key": "k"}, {"m": {"k": 0}, "key": "missing"},
         {"m": {"z": None}, "key": "z"}, {"m": {"a": []}, "key": "a"},
         {"m": {"n": 5}, "key": "n"}]),
    "format_pair": (
        [{"a": "x", "b": "y"}, {"a": "", "b": "q"},
         {"a": "m", "b": ""}, {"a": "a b", "b": "c"}],
        [{"a": "1", "b": "2"}, {"a": "-", "b": "-"},
         {"a": "", "b": ""}, {"a": "X", "b": "Y"},
         {"a": "p", "b": "p"}]),
}

SNG20_PAYLOADS = (
    [{"nums": [4, 3, 2, 1], "k": 2}, {"nums": [8], "k": 1},
     {"nums": [5, 5, 5], "k": 3}, {"nums": [1, 9], "k": 0}],
    [{"nums": [], "k": 1}, {"nums": [6, 7], "k": 9},
     {"nums": [2], "k": 0}, {"nums": [9, 8, 7, 6, 5], "k": 3},
     {"nums": [0, 4], "k": 2}])


def _rw_payloads(i: int, notes: bool = False):
    def row(n, note=None):
        d = {"n": n + 50 * i}
        if notes and note is not None:
            d["note"] = note
        return d
    pub = [
        {"deliveries": [row(2, "a"), row(3)]},
        {"deliveries": [row(5, "b")]},
        {"deliveries": [row(1), row(4, "c"), row(6)]},
        {"deliveries": []},
    ]
    prot = [
        {"deliveries": [row(7, "d")]},
        {"deliveries": [row(0)]},
        {"deliveries": [row(2), row(2, "e")]},
        {"deliveries": [row(10), row(20), row(30, "f")]},
        {"deliveries": [row(4)]},
    ]
    return pub, prot


def _cell_payloads(i: int):
    pub = [
        {"cells": [{"v": 2}, {"v": 3}], "factor": 2},
        {"cells": [{"v": 1.5}], "factor": 3},
        {"cells": [], "factor": 5},
        {"cells": [{"v": 10 + i}], "factor": 0},
    ]
    prot = [
        {"cells": [{"v": 0.1}], "factor": 0.2},
        {"cells": [{"v": 1}, {"v": 2}, {"v": 3}], "factor": 1.5},
        {"cells": [{"v": 7 + i}], "factor": 1},
        {"cells": [{"v": 2.5}, {"v": 2.5}], "factor": 2},
        {"cells": [{"v": 100}], "factor": 0.05},
    ]
    return pub, prot


def _chain_payloads():
    pub = [
        {"parcels": [{"v": 60, "u": "q"}], "want": "p"},
        {"parcels": [{"v": 1, "u": "p"}, {"v": 20, "u": "q"}],
         "want": "p"},
        {"parcels": [{"v": 0, "u": "q"}], "want": "p"},
        {"parcels": [{"v": 120, "u": "q"}], "want": "p"},
    ]
    prot = [
        {"parcels": [{"v": 107, "u": "q"}], "want": "p"},
        {"parcels": [{"v": 80, "u": "q"}], "want": "p"},
        {"parcels": [{"v": 0, "u": "p"}], "want": "p"},
        {"parcels": [], "want": "p"},
        {"parcels": [{"v": 2, "u": "p"}, {"v": 1, "u": "q"}],
         "want": "p"},
    ]
    return pub, prot


def payloads_for(task_id: str):
    fam = oracle.TASK_FAMILY[task_id]
    idx = oracle.ALL_TASKS.index(task_id)
    if fam == "sep":
        if task_id == "c02-t05":
            return _mixed_payloads()
        spec = spec_for(task_id)
        return _sep_payloads(idx, spec["bounds"][0], spec["bounds"][1])
    if fam == "cpl":
        return CPL_PAYLOADS[task_id]
    if fam == "dia":
        return DIA_PAYLOADS[task_id]
    if fam == "sng":
        if task_id == "c02-t20":
            return SNG20_PAYLOADS
        return SNG_PAYLOADS[spec_for(task_id)["op"]]
    if fam == "rw":
        return _rw_payloads(idx, notes=(task_id == "c02-t25"))
    if fam == "sco":
        if task_id == "c02-t30":
            return _chain_payloads()
        return _cell_payloads(idx)
    raise ValueError("unknown task %s" % task_id)


def broken_src_for(task_id: str) -> dict:
    fam = oracle.TASK_FAMILY[task_id]
    if fam == "sep":
        if task_id == "c02-t05":
            return {"app.py": APP["sep_mixed"], "names.py": BROKEN["names"],
                    "tags.py": BROKEN["tags"], "pconv.py": BROKEN["pconv"],
                    "cconv.py": BROKEN["cconv"]}
        return {"app.py": APP["sep"], "names.py": BROKEN["names"],
                "scores.py": BROKEN["scores"], "tags.py": BROKEN["tags"],
                "stats.py": BROKEN["stats"]}
    if fam == "cpl":
        if task_id == "c02-t10":
            return {"app.py": APP["cpl_chain"], "maker.py": BROKEN["maker"],
                    "shaper.py": BROKEN["shaper"],
                    "judge.py": BROKEN["judge"]}
        return {"app.py": APP["cpl"], "producer.py": BROKEN["producer"],
                "consumer.py": BROKEN["consumer"]}
    if fam == "dia":
        files = {"app.py": APP["dia"]}
        fault = oracle.DIA_FAULT[task_id]
        if task_id == "c02-t15":
            files["detect.py"] = BROKEN["detect"]
            files["operate.py"] = BROKEN["operate_v1keys"]
        elif fault == "detect":
            files["detect.py"] = BROKEN["detect"]
            files["operate.py"] = CORRECT["operate"]
        else:
            files["detect.py"] = CORRECT["detect"]
            files["operate.py"] = BROKEN["operate"]
        return files
    if fam == "sng":
        if task_id == "c02-t20":
            return {"app.py": APP["sng"],
                    "compute.py": SNG_COMPUTE_HELPER["broken"],
                    "helper.py": HELPER["broken"]}
        return {"app.py": APP["sng"],
                "compute.py": SNG_BROKEN[spec_for(task_id)["op"]]}
    if fam == "rw":
        return {"app.py": APP["rw"], "emit.py": BROKEN["emit"],
                "render.py": BROKEN["render"]}
    if fam == "sco":
        if task_id in ("c02-t27", "c02-t29"):
            return {"app.py": APP["renamed"],
                    "zeta.py": BROKEN["cell_producer"],
                    "quux.py": BROKEN["cell_consumer"]}
        if task_id == "c02-t30":
            return {"app.py": APP["chain"], "intake.py": CORRECT["intake"],
                    "convert.py": BROKEN["convert"],
                    "finalize.py": BROKEN["finalize"]}
        return {"app.py": APP["cell"],
                "producer.py": BROKEN["cell_producer"],
                "consumer.py": BROKEN["cell_consumer"]}
    raise ValueError("unknown task %s" % task_id)


def reference_overlays() -> dict:
    ref = {}
    ref["sep/valid"] = {"names.py": CORRECT["names"],
                        "scores.py": CORRECT["scores"],
                        "tags.py": CORRECT["tags"],
                        "stats.py": CORRECT["stats"],
                        "pconv.py": CORRECT["pconv"],
                        "cconv.py": CORRECT["cconv"]}
    ref["sep/invalid"] = {"names.py": CORRECT["names"],
                          "scores.py": CORRECT["scores"],
                          "tags.py": BROKEN["tags"],
                          "stats.py": BROKEN["stats"],
                          "pconv.py": INVALID["pconv_halfeven"],
                          "cconv.py": INVALID["cconv_exclusive"]}
    ref["cpl/valid"] = {"producer.py": CORRECT["producer"],
                        "consumer.py": CORRECT["consumer"],
                        "maker.py": CORRECT["maker"],
                        "shaper.py": CORRECT["shaper"],
                        "judge.py": CORRECT["judge"]}
    ref["cpl/invalid"] = {"producer.py": CORRECT["producer"],
                          "consumer.py": INVALID["consumer"],
                          "maker.py": CORRECT["maker"],
                          "shaper.py": INVALID["shaper"],
                          "judge.py": INVALID["judge"]}
    ref["dia/valid"] = {"detect.py": CORRECT["detect"],
                        "operate.py": CORRECT["operate"]}
    ref["dia/invalid_det"] = {"detect.py": BROKEN["detect"],
                              "operate.py": CORRECT["operate"]}
    ref["dia/invalid_op"] = {"detect.py": CORRECT["detect"],
                             "operate.py": BROKEN["operate"]}
    ref["dia/stale_operate"] = {"operate.py": BROKEN["operate_v1keys"]}
    for op in ("window_sum", "gt_count", "get_default", "format_pair"):
        ref["sng/valid_%s" % op] = {"compute.py": SNG_CORRECT[op]}
        ref["sng/invalid_%s" % op] = {"compute.py": SNG_INVALID[op]}
    ref["sng/valid_split"] = {"compute.py": SNG_COMPUTE_HELPER["valid"],
                              "helper.py": HELPER["valid"]}
    ref["rw/valid"] = {"emit.py": CORRECT["emit"],
                       "render.py": CORRECT["render"]}
    ref["rw/invalid"] = {"emit.py": CORRECT["emit"],
                         "render.py": BROKEN["render"]}
    ref["rw/rework"] = {"emit_v2.py": REWORK["emit_v2"],
                        "render_v2.py": REWORK["render_v2"],
                        "emit_alt.py": REWORK["emit_alt"],
                        "convention_v2.json": json.dumps(CONV_V2, indent=2)
                        + "\n"}
    ref["sco/valid_cell"] = {"producer.py": CORRECT["cell_producer"],
                             "consumer.py": CORRECT["cell_consumer"]}
    ref["sco/valid_renamed"] = {"zeta.py": CORRECT["cell_producer"],
                                "quux.py": CORRECT["cell_consumer"]}
    ref["sco/valid_chain"] = {"intake.py": CORRECT["intake"],
                              "convert.py": CORRECT["convert"],
                              "finalize.py": CORRECT["finalize"]}
    ref["sco/invalid"] = {"producer.py": CORRECT["cell_producer"],
                          "consumer.py": INVALID["cell_consumer"],
                          "zeta.py": CORRECT["cell_producer"],
                          "quux.py": INVALID["cell_consumer"],
                          "intake.py": CORRECT["intake"],
                          "convert.py": INVALID["chain_convert"],
                          "finalize.py": INVALID["chain_finalize"]}
    return ref


ABI = ("Program ABI: read one JSON object from the request file named by "
       "the first command-line argument, write one JSON object to the "
       "response file named by the second. Use only the Python standard "
       "library.")

EDGE = ("Edge cases are graded: empty lists, zero and missing values, "
        "exact boundary values, and repeated entries must all be handled.")


def spec_md_for(task_id: str, spec: dict) -> str:
    fam = oracle.TASK_FAMILY[task_id]
    head = "# Task %s\n\n%s\n\n" % (task_id, ABI)
    if fam == "sep" and task_id != "c02-t05":
        lo, hi = spec["bounds"]
        return head + (
            "Four record fields arrive together and leave together. "
            "Input object: names holds a list of strings, scores a list of "
            "numbers, tags a list of strings, values a list of numbers.\n\n"
            "Each field has its own module and every module has a defect: "
            "names.py must strip surrounding whitespace then lowercase each "
            "string in order; scores.py must clamp each number into [%s, %s] "
            "then round to two decimals; tags.py must remove duplicates and "
            "sort what remains; stats.py must report the mean of values "
            "rounded to two decimals, or 0 when values is empty. "
            "app.py assembles the four outputs under names, scores, tags "
            "and stat. Fixing only some modules cannot satisfy the graded "
            "outputs. %s\n" % (lo, hi, EDGE))
    if task_id == "c02-t05":
        return head + (
            "Names and tags travel with instrument readings that must be "
            "converted and flagged. Input object: names holds a list of "
            "strings, tags a list of strings, readings a list of "
            "{\"v\", \"u\"} records with unit s or m, want names the "
            "target unit.\n\n"
            "names.py must strip surrounding whitespace then lowercase each "
            "string in order; tags.py must remove duplicates and sort what "
            "remains; pconv.py must convert each reading into the wanted "
            "unit and round half-up to two decimals; cconv.py must flag "
            "each converted value against [0, 5] with both ends inclusive "
            "(low below, high above, ok otherwise). app.py assembles "
            "names, tags, values and flags. The conversion pair shares one "
            "rounding and boundary convention: both halves must agree. %s\n"
            % EDGE)
    if fam == "cpl":
        units = ", ".join("%s=%s" % kv for kv in sorted(spec["units"].items()))
        lo, hi = spec["bounds"]
        if task_id == "c02-t10":
            stages = ("Three stages collaborate: maker.py converts each "
                      "reading to base units, shaper.py converts base units "
                      "to the wanted unit rounded half-up to two decimals, "
                      "judge.py flags each value.")
        else:
            stages = ("Two stages collaborate: producer.py converts each "
                      "reading to base units, consumer.py converts base "
                      "units to the wanted unit rounded half-up to two "
                      "decimals and flags each value.")
        return head + (
            "Input object: readings holds a list of {\"v\", \"u\"} "
            "records, want names the target unit. Unit table: %s.\n\n"
            "%s Flags use [%s, %s] with both ends inclusive (low below, "
            "high above, ok otherwise). Output object: values then flags. "
            "A conversion that looks right on round numbers but rounds "
            "half-cases the other way, or that excludes the upper bound, "
            "fails the graded outputs. %s\n"
            % (units, stages, lo, hi, EDGE))
    if fam == "dia":
        rule = spec["rule"]
        if rule["kind"] == "key":
            how = ("mode \"b\" when the payload carries the key %r, "
                   "else mode \"a\"" % rule["key"])
            operands = "the list under the per-mode key of list_keys"
        elif rule["kind"] == "threshold":
            how = ("mode \"b\" when payload code is at least %s, else "
                   "mode \"a\"" % rule["at"])
            if "list_keys" in spec:
                operands = ("the list under the per-mode key of list_keys "
                            "(convention v2)")
            else:
                operands = "payload vals"
        elif rule["kind"] == "prefix":
            how = ("mode \"b\" when payload kind starts with %r, else "
                   "mode \"a\"" % rule["prefix"])
            operands = "payload vals"
        else:
            how = ("mode \"b\" when payload items is an object mapping "
                   "names to numbers, mode \"a\" when it is a list")
            operands = ("the list itself in mode \"a\", the object values "
                        "in mode \"b\"")
        ops = ", ".join("%s=%s" % kv for kv in sorted(spec["ops"].items()))
        return head + (
            "Two stages collaborate and either stage may be at fault, so "
            "probe before repairing. detect.py must classify the payload: "
            "%s. operate.py must aggregate %s with the per-mode operation "
            "from {%s}. Output object: mode then result. Run the program "
            "on small crafted inputs first: an input whose mode flips the "
            "expected aggregate tells you which stage to fix. %s\n"
            % (how, operands, ops, EDGE))
    if fam == "sng":
        op = spec["op"]
        if op == "window_sum":
            body = ("Input object: nums holds a list of numbers, k "
                    "a non-negative window. Output object: total, "
                    "the sum of the last k entries of nums (all of "
                    "them when k exceeds the length, 0 when k is 0).")
        elif op == "gt_count":
            body = ("Input object: nums holds a list of numbers, "
                    "threshold a number. Output object: count, the "
                    "number of entries strictly greater than "
                    "threshold.")
        elif op == "get_default":
            body = ("Input object: m holds an object, key a "
                    "string. Output object: value, the stored entry "
                    "when the key is present (even when it is "
                    "empty, zero or null), otherwise the configured "
                    "default %r from spec.json." % spec["default"])
        else:
            body = ("Input object: a and b hold strings. Output "
                    "object: text, a then the configured separator "
                    "%r then b, in that order." % spec["sep"])
        extra = ""
        if task_id == "c02-t20":
            extra = (" The window selection lives in helper.py behind "
                     "last_k; compute.py only sums what it returns.")
        return head + body + extra + " compute.py holds the defect. %s\n" % EDGE
    if fam == "rw":
        extra = ""
        if task_id == "c02-t25":
            extra = (" Each delivery may carry a note string; notes pass "
                     "through unchanged under the notes key, defaulting to "
                     "empty string. Totals first scale then apply the "
                     "spec.json discount of 0.1.")
        return head + (
            "Input object: deliveries holds a list of {\"n\"} records. "
            "emit.py must pack each record with convention.json (scale and "
            "entry key); render.py must unpack with the same convention "
            "and report the scaled total rounded to two decimals. "
            "convention.json carries scale, in_key and version. render.py "
            "depends on both the convention file and the packet layout "
            "emit.py writes: when the convention changes, packed work from "
            "the old layout is stale and must be redone, while work "
            "packed under an unchanged convention stays valid.%s\n"
            % extra)
    if fam == "sco":
        if task_id == "c02-t30":
            units = ", ".join("%s=%s" % kv
                              for kv in sorted(spec["units"].items()))
            return head + (
                "Input object: parcels holds a list of {\"v\", \"u\"} "
                "records, want names the target unit. Unit table: %s. "
                "Three unfamiliar stages collaborate: intake.py reads each "
                "parcel, convert.py converts to the wanted unit rounded "
                "half-up to two decimals, finalize.py flags each value "
                "against [0, 2] with both ends inclusive. This chain "
                "answers to interface cellchain/1 only: bindings written "
                "for other interfaces must be refused, even though the "
                "arithmetic resembles them. %s\n" % (units, EDGE))
        return head + (
            "Input object: cells holds a list of {\"v\"} records, factor "
            "a number. The first stage scales each cell by factor rounded "
            "to two decimals; the second stage reports the rounded sum as "
            "total. Output object: values then total. This task answers "
            "to interface cellsum/1 only: similarly named stages from "
            "other interfaces do not apply here, while the same interface "
            "under unfamiliar stage names binds normally. %s\n" % EDGE)
    raise ValueError("unknown task %s" % task_id)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: Path, content: str, files: list, rel: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = content.encode()
    path.write_bytes(raw)
    files.append({"path": rel, "digest": _digest(raw), "bytes": len(raw)})


def build_all() -> dict:
    root = COORD02
    tasks_root = root / "corpus" / "tasks"
    if tasks_root.exists():
        for child in sorted(tasks_root.iterdir()):
            if child.is_dir():
                for sub in sorted(child.rglob("*")):
                    if sub.is_file():
                        sub.unlink()
            elif child.is_file():
                child.unlink()
    if oracle.REFERENCE.exists():
        for child in sorted(oracle.REFERENCE.iterdir()):
            if child.is_dir():
                for sub in sorted(child.rglob("*")):
                    if sub.is_file():
                        sub.unlink()
    for stale in sorted(oracle.PROTECTED.glob("c02-*.json")):
        stale.unlink()
    files = []
    for task_id in oracle.ALL_TASKS:
        spec = spec_for(task_id)
        fam = oracle.TASK_FAMILY[task_id]
        pub_inputs, prot_inputs = payloads_for(task_id)
        conv = CONV_V1 if fam == "rw" else None
        public = [{"input": payload,
                   "expected": oracle.reference(fam, spec, payload, conv)}
                  for payload in pub_inputs]
        protected = [{"input": payload,
                      "expected": oracle.reference(fam, spec, payload, conv)}
                     for payload in prot_inputs]
        tdir = tasks_root / task_id
        _write(tdir / "spec.json",
               json.dumps(spec, sort_keys=True, indent=2) + "\n",
               files, "experiments/coord02/corpus/tasks/%s/spec.json"
               % task_id)
        _write(tdir / "spec.md", spec_md_for(task_id, spec), files,
               "experiments/coord02/corpus/tasks/%s/spec.md" % task_id)
        _write(tdir / "public.json",
               json.dumps(public, indent=2) + "\n", files,
               "experiments/coord02/corpus/tasks/%s/public.json" % task_id)
        for name, body in broken_src_for(task_id).items():
            _write(tdir / "src" / name, body, files,
                   "experiments/coord02/corpus/tasks/%s/src/%s"
                   % (task_id, name))
        if fam == "rw":
            _write(tdir / "convention.json",
                   json.dumps(CONV_V1, indent=2) + "\n", files,
                   "experiments/coord02/corpus/tasks/%s/convention.json"
                   % task_id)
        _write(oracle.PROTECTED / (task_id + ".json"),
               json.dumps(protected, indent=2) + "\n", files,
               "experiments/coord02/protected/%s.json" % task_id)
    for dirname, members in reference_overlays().items():
        for name, body in members.items():
            _write(oracle.REFERENCE / dirname / name, body, files,
                   "experiments/coord02/protected/reference/%s/%s"
                   % (dirname, name))
    oracle_raw = (oracle.ROOT / "oracle.py").read_bytes()
    _write(oracle.ROOT / "oracle.py", oracle_raw.decode(), files,
           "experiments/coord02/oracle.py")
    files.sort(key=lambda entry: entry["path"])
    manifest = {"version": "coord02-corpus/1",
                "splits": {key: list(val)
                           for key, val in oracle.SPLITS.items()},
                "membership": dict(oracle.TASK_FAMILY),
                "seeds": {"c02-t%02d" % n: 2000 + n for n in range(1, 31)},
                "sampling_offset": 30,
                "evaluator": {"id": oracle.EVALUATOR_ID,
                              "version": oracle.EVALUATOR_VERSION,
                              "code_digest": _digest(oracle_raw)},
                "files": files}
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    (root / "corpus" / "manifest.json").write_bytes(raw)
    (root / "corpus" / "manifest.sha256").write_text(_digest(raw) + "\n")
    return manifest


def main() -> None:
    manifest = build_all()
    print(json.dumps({"tasks": len(oracle.ALL_TASKS),
                      "files": len(manifest["files"]),
                      "version": manifest["version"]}))


if __name__ == "__main__":
    main()

