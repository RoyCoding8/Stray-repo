"""AD01 pressure controls: authored, labeled opportunities (§5).

Each control exercises a required opportunity of the workload through the
real checker/reducer seams and returns a record with observable
distinguishing output. Controls validate the machinery; they never
masquerade as acquired behavior.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.representation import checkers, reducers

from . import seeds, worlds

ORIGIN = "ad01-controls"


def _record(control_id: str, **fields) -> dict:
    return {"control_id": control_id, "authored": True,
            "origin": ORIGIN, **fields}


def load(task_id: str) -> dict:
    return worlds.load_task(worlds.FROZEN_DIR, task_id)


def _check(task: dict, candidate: dict) -> dict:
    if task["family"] == "software":
        return checkers.check_software(task, candidate)
    return checkers.check_graph(task, candidate)


def incumbent(task: dict) -> dict:
    return json.loads(json.dumps(task))


def break_candidate(task: dict) -> dict:
    broken = incumbent(task)
    if task["family"] == "software":
        wid = task["witness"]["observation"]
        wpos = next(i for i, o in enumerate(task["ops"])
                    if o.get("id") == wid)
        hero = task["ops"][wpos]["key"]
        broken["ops"] = [o for i, o in enumerate(task["ops"])
                         if not (o["op"] == "set" and o.get("key") == hero
                                 and i < wpos)]
    else:
        broken["edges"] = []
    return broken


def contaminate(task: dict, label: str) -> dict:
    dirty = incumbent(task)
    if task["family"] == "software":
        for entry in dirty["ops"]:
            if entry["op"] == "get":
                entry["id"] = "%s@%s" % (entry["id"], label)
    else:
        fresh = max(dirty["vertices"]) + 1
        dirty["vertices"] = sorted(dirty["vertices"] + [fresh])
    return dirty


def ledger_query(oracle, candidate: dict, label: str, ledger: list) -> dict:
    report = oracle.query(candidate)
    ledger.append({"label": label, "verdict": report["verdict"],
                   "reason": report.get("reason")})
    return report


def evidence_path(task: dict, candidate_a: dict, candidate_b: dict,
                  labels=("run-1", "run-2")) -> dict:
    oracle = (checkers.SoftwareOracle(task)
              if task["family"] == "software"
              else checkers.GraphOracle(task))
    ledger: list = []
    verdict_a = ledger_query(oracle, candidate_a, labels[0], ledger)
    verdict_b = ledger_query(oracle, candidate_b, labels[1], ledger)
    relabeled = ledger_query(oracle, candidate_a, labels[1], ledger)
    return _record("c0-evidence-path", task_id=task["task_id"],
                   verdict_a=verdict_a["verdict"],
                   verdict_b=verdict_b["verdict"],
                   changed=(verdict_a["verdict"] != verdict_b["verdict"]),
                   label_stable=(relabeled["verdict"]
                                 == verdict_a["verdict"]),
                   ledger=ledger)


def cheap_suffices(task_id: str, capability_id: str,
                   max_queries: int = 16) -> dict:
    task = load(task_id)
    capability = next(c for c in seeds.SEED_CAPABILITIES
                      if c["capability_id"] == capability_id)
    initial = (len(task["ops"]) if task["family"] == "software"
               else len(task["vertices"]) + len(task["edges"]))
    result = seeds.run_seed(capability, task, max_queries=max_queries)
    candidate = result["candidate"]
    size = (len(candidate["ops"]) if task["family"] == "software"
            else len(candidate["vertices"]) + len(candidate["edges"]))
    return _record("c1-cheap-suffices", task_id=task_id,
                   capability_id=capability_id,
                   accepted=result["accepted"], status=result["status"],
                   queries=result["queries"], initial=initial, final=size,
                   reduced=_check(task, candidate)["verdict"] == "preserved"
                   and size < initial)


def _software_chain(task: dict) -> tuple:
    wid = task["witness"]["observation"]
    wpos = next(i for i, o in enumerate(task["ops"]) if o.get("id") == wid)
    hero = task["ops"][wpos]["key"]
    chain = [i for i, o in enumerate(task["ops"])
             if o["op"] == "set" and o.get("key") == hero and i < wpos]
    others = [i for i in range(len(task["ops"]))
              if i != wpos and i not in chain]
    return chain, wpos, others


def _drop(task: dict, doomed) -> dict:
    doomed = set(doomed)
    candidate = incumbent(task)
    candidate["ops"] = [o for i, o in enumerate(task["ops"])
                        if i not in doomed]
    return candidate


def dependency_invalidates(task_id: str) -> dict:
    task = load(task_id)
    assert task["family"] == "software"
    chain, _, others = _software_chain(task)
    bulk = _check(task, _drop(task, chain[:2]))
    surgical = _check(task, _drop(task, others[:1]))
    two = _check(task, _drop(task, others[:2]))
    return _record("c2-dependency", task_id=task_id,
                   bulk_verdict=bulk["verdict"], bulk_reason=bulk["reason"],
                   surgical_verdict=surgical["verdict"],
                   surgical_reason=surgical["reason"],
                   two_distractors_verdict=two["verdict"])


def compare(seed_result: dict, novel_result: dict) -> dict:
    if novel_result["final"] < seed_result["final"]:
        winner = "novel"
    elif novel_result["final"] > seed_result["final"]:
        winner = "seed"
    elif novel_result["queries"] < seed_result["queries"]:
        winner = "novel"
    elif novel_result["queries"] > seed_result["queries"]:
        winner = "seed"
    else:
        winner = "tie"
    return {"winner": winner, "seed_final": seed_result["final"],
            "novel_final": novel_result["final"]}


def novel_order_unproductive(task_id: str, budget: int = 8) -> dict:
    task = load(task_id)
    assert task["family"] == "graph"
    build, order = reducers.graph_atoms(task)
    count = len(task["vertices"]) + len(task["edges"])
    runs = {}
    for name, priority in (("seed", order),
                           ("novel", list(reversed(order)))):
        oracle = checkers.GraphOracle(task, max_queries=budget)
        result = reducers.greedy_reduce(
            count, build, lambda c, o=oracle: o.query(c),
            priority=priority, max_queries=budget)
        candidate = build(result["kept"])
        verdict = checkers.check_graph(task, candidate)["verdict"]
        runs[name] = {"final": len(candidate["vertices"])
                      + len(candidate["edges"]),
                      "queries": result["queries"], "verdict": verdict,
                      "status": result["status"]}
    decision = compare(runs["seed"], runs["novel"])
    decision.update(task_id=task_id, budget=budget,
                    seed_verdict=runs["seed"]["verdict"],
                    novel_verdict=runs["novel"]["verdict"])
    return _record("c3-novel-unproductive", **decision)


def diagnostic_resolves(task_id: str) -> dict:
    task = load(task_id)
    assert task["family"] == "software"
    chain, wpos, others = _software_chain(task)
    diagnostic = _check(task, _drop(task, [i for i in range(len(task["ops"]))
                                           if i not in set(chain + [wpos])]))
    nondiagnostic = _check(task, _drop(task, chain + [wpos]))
    return _record("c4-diagnostic", task_id=task_id,
                   diagnostic_verdict=diagnostic["verdict"],
                   diagnostic_reason=diagnostic["reason"],
                   nondiagnostic_verdict=nondiagnostic["verdict"],
                   nondiagnostic_reason=nondiagnostic["reason"])


def _digest(task_id: str, candidate: dict) -> str:
    raw = (json.dumps({"task_id": task_id, "candidate": candidate},
                      sort_keys=True) + "\n").encode()
    return hashlib.sha256(raw).hexdigest()


class NegativeLedger:
    def __init__(self, path) -> None:
        self.path = Path(path)
        try:
            self.entries = json.loads(self.path.read_text())
        except OSError:
            self.entries = {}

    def is_repeat(self, task_id: str, candidate: dict) -> bool:
        return _digest(task_id, candidate) in self.entries.get(task_id, [])

    def record(self, task_id: str, candidate: dict, verdict: str) -> None:
        self.entries.setdefault(task_id, []).append(
            _digest(task_id, candidate))
        self.entries.setdefault("verdicts", []).append(
            {"task_id": task_id, "verdict": verdict})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, sort_keys=True,
                                        indent=2) + "\n")


def prior_negative(ledger: NegativeLedger, task_id: str) -> dict:
    task = load(task_id)
    candidate = break_candidate(task)
    if ledger.is_repeat(task_id, candidate):
        return _record("c5-prior-negative", task_id=task_id,
                       refused=True, consumed=0)
    oracle = (checkers.SoftwareOracle(task, max_queries=16)
              if task["family"] == "software"
              else checkers.GraphOracle(task, max_queries=16))
    report = oracle.query(candidate)
    ledger.record(task_id, candidate, report["verdict"])
    return _record("c5-prior-negative", task_id=task_id,
                   refused=False, consumed=1, verdict=report["verdict"])
