"""A compact STEP policy, authored offline, as a size witness. No sends.

B17 has to answer whether the served budget can carry a REPAIRING
artifact. That is a question about size, and it is answerable without a
wire call: write a small policy, run it on the dev split through the
instrument's own scorer, and measure it.

This policy is authored bytes with zero model calls. It is never an
acquired lineage and never enters an acquired set. It exists to be
measured, and its repair rate is a lower bound on what the budget can
carry, not a claim about the model.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (REPO_ROOT, REPO_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

#: The same search the authored control runs, written without its
#: docstrings, its diagnostics, and the rewrite families this policy does
#: not need. Deliberately NOT a better policy than the control: the claim
#: is that it fits, and a fitting witness is enough.
COMPACT_POLICY = '''MAX_SUSPECTS = 4


def act(kind, target, inputs):
    return {"kind": kind, "target": target, "inputs": inputs,
            "evidence_refs": [], "requested_resources": {}}


def parses(line):
    body = line.strip()
    if not body:
        return False
    depth = 0
    quote = ""
    for char in body:
        if quote:
            if char == quote:
                quote = ""
        elif char in "'\\"":
            quote = char
        elif char in "([{":
            depth = depth + 1
        elif char in ")]}":
            depth = depth - 1
            if depth < 0:
                return False
    return depth == 0 and not quote


def lines_of(view):
    return [entry["text"] for entry in view["source"]]


def initialiser(text):
    body = text.strip()
    if not body.endswith("= 0"):
        return False
    name = body[:-3]
    return bool(name) and name.replace("_", "a").isalnum()


def risk_key(lines, number):
    text = lines[number - 1] if number <= len(lines) else ""
    body = text.strip()
    is_init = body.endswith("= 0") and body[:-3].replace("_", "a").isalnum()
    return (1 if is_init else 0, -len(text), number)


def digits(text):
    return "".join(char for char in text if char.isdigit())


def candidates(line, pool):
    out = []
    body = line.strip()
    indent = line[:len(line) - len(line.lstrip())]
    pairs = ((" < ", " > "), (" > ", " < "), (" <= ", " >= "),
             (" >= ", " <= "), (" == ", " != "), (" != ", " == "),
             (" + ", " - "), (" - ", " + "))
    for old, new in pairs:
        if old in body:
            out.append(body.replace(old, new, 1))
    if " if " in body and " else " in body:
        head, _, rest = body.partition(" if ")
        condition, _, tail = rest.partition(" else ")
        out.append(head.strip() + " = " + tail.strip() + " if "
                   + condition.strip() + " else " + head.strip())
    if "range(" in body:
        head, _, rest = body.partition("range(")
        inside, _, tail = rest.rpartition(")")
        bounds = [part.strip() for part in inside.split(",")]
        for index, bound in enumerate(bounds):
            if bound in pool or bound.replace("_", "a").isalnum():
                for shifted in (bound + " + 1", bound + " - 1"):
                    trial = list(bounds)
                    trial[index] = shifted
                    out.append(head + "range(" + ", ".join(trial) + ")" + tail)
    for name in digits(pool):
        if name not in body and len(name) == 1:
            out.append(body.replace("0", name, 1))
    fresh = []
    for candidate in out:
        dedup = candidate.strip()
        if dedup and dedup != body and parses(dedup) and dedup not in fresh:
            fresh.append(dedup)
    return [indent + item for item in fresh]


def suspects(view):
    observed = {item["test"]: item
                for item in view["symptom"]["observed"]}
    failing = [name for name, item in observed.items()
               if not (item["actual"] == item["expected"]
                       and item["kind"] == "value")]
    by_failing = []
    shared = []
    for item in view["symptom"]["coverage"]:
        bucket = by_failing if item["test"] in failing else shared
        for line in item["executed_lines"]:
            if line not in bucket:
                bucket.append(line)
    ranked = [n for n in by_failing if n not in shared] + \\
        [n for n in by_failing if n in shared]
    lines = lines_of(view)
    clean = [n for n in ranked
             if not initialiser(lines[n - 1] if n < len(lines) else "")]
    return sorted(clean, key=lambda n: risk_key(lines, n))[:MAX_SUSPECTS]


def STEP(view, state):
    symptom = view["symptom"]
    seen = [item["test"] for item in symptom["observed"]]
    pending = [case["name"] for case in view["public_tests"]
               if case["name"] not in seen]
    remaining = view["remaining"]
    if pending and remaining.get("test", 0) > 0:
        return {"action": act("observe", "test.run",
                              {"test": pending[0]}), "state": state}
    if symptom["failing_tests"] and not symptom["coverage"] \\
            and remaining.get("localize", 0) > 0:
        return {"action": act("construct", "code.localize",
                              {"test": symptom["failing_tests"][0]["test"]}),
                "state": state}
    if remaining.get("probe", 0) > 0:
        lines = lines_of(view)
        pool = "".join(lines)
        tried = state.setdefault("tried", [])
        for number in suspects(view):
            if number < 0 or number >= len(lines):
                continue
            for candidate in candidates(lines[number], pool):
                tag = str(number) + "|" + candidate
                if tag in tried:
                    continue
                tried.append(tag)
                state["pending"] = [number + 1, candidate]
                return {"action": act("construct", "code.try",
                                      {"line": number + 1,
                                       "text": candidate}),
                        "state": state}
    winner = state.get("winner")
    total = len(view["public_tests"])
    if winner and state.get("best", -1) == total \\
            and remaining.get("edit", 0) > 0:
        return {"action": act("use", "code.repair",
                              {"edits": [{"line": winner[0], "op": "replace",
                                          "text": winner[1]}]}),
                "state": state}
    return {"action": act("stop", "swe.task", {}), "state": state}
'''


def run_dev(source: str, split: str = "dev") -> list:
    """Run these bytes over a split through the instrument's own scorer.

    `world.run_episode` is used rather than a hand-rolled loop, so the
    answer is the same one every other row in the study is scored under.
    """
    from experiments.ad01 import s09_swe_experiment as experiment
    from experiments.ad01 import s09_swe_tasks as tasks
    from experiments.ad01 import s09_swe_world as world

    namespace: dict = {}
    exec(compile(source, "<b17-compact>", "exec"), namespace)
    step = namespace["STEP"]

    state: dict = {}

    def choose(view):
        experiment._absorb_bridge(state, view.get("last_effect"))
        return step(view, state)["action"]

    rows = []
    catalogue = tasks.enumerate_instances(split)
    for seed, record in enumerate(catalogue):
        state.clear()
        episode = world.run_episode(choose, split=split, seed=seed)
        final = episode["final"]
        rows.append({"seed": seed, "task_id": record["task_id"],
                     "mechanism": record["mechanism"],
                     "repaired": episode["repaired"],
                     "outcome": final.get("outcome"),
                     "public_passed": final.get("public_passed"),
                     "public_total": final.get("public_total"),
                     "turns": episode["turns"]})
    return rows
