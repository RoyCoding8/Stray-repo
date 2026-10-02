"""Frozen acquisition context builders for Representation Lane D (RPR-03).

Two contexts over disjoint task sets, each usable by any present or future
arm: a source context over the 6 software development tasks and a transfer
context over 4 graph development tasks. Each context bundles parent
experience references (Lane B manifest identity plus per-task digests),
complete deterministic baseline transcripts (ddmin and greedy runs with
every oracle verdict) and labeled authored lessons. The source context
carries no graph vocabulary; the transfer context is never loaded by
source-stage code paths.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation import checkers, graphs, reducers, software

CONTEXT_VERSION = "RPR-CTX/1"
SOURCE_TASKS = ["sw-dev-%02d" % i for i in range(6)]
TRANSFER_TASKS = ["gr-dev-%02d" % i for i in range(4)]
BARRIER_TOKENS = ("vert", "edge", "bipart", "triangle", "cycle", "graph")

SOURCE_LESSONS = [
    "authored-fixture-lesson 1: keep the observing read and the writes that"
    " set up the stale value; prefix reads on other names usually drop away.",
    "authored-fixture-lesson 2: a halving step that spans both the setup"
    " pair and the observing read fails whole; tail-first single removals"
    " spend fewer checks.",
    "authored-fixture-lesson 3: reads that agree in both interpreters are"
    " expendable; only the designated disagreeing read must survive.",
    "authored-fixture-lesson 4: after a clear, the surviving stale value"
    " comes from the pre-clear write; prefix writes on other names drop away.",
    "authored-fixture-lesson 5: ddmin halves win early on long sequences"
    " with clustered setup; greedy tail-first wins when setup sits near"
    " the front.",
    "authored-fixture-lesson 6: never claim a smaller sequence without a"
    " preserved verdict on the exact bytes; count every check.",
]

TRANSFER_LESSONS = [
    "authored-fixture-lesson 1: the odd cycle is the witness core; attached"
    " trees and even-cycle distractors reduce first.",
    "authored-fixture-lesson 2: shared-vertex doubles keep one full odd"
    " cycle; drop the second cycle's private vertices.",
    "authored-fixture-lesson 3: doubles joined by a path usually keep one"
    " side only; the joining path itself is expendable.",
    "authored-fixture-lesson 4: isolated vertices and disconnected paths"
    " never affect the witness; remove them before touching cycle vertices.",
    "authored-fixture-lesson 5: deletions that shorten the odd cycle to an"
    " even length destroy the witness; prefer tree deletions.",
    "authored-fixture-lesson 6: check every candidate against the exact"
    " oracle; count every query including failures.",
]


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fixture_digest(fixtures_root: Path, task_id: str) -> tuple:
    for sub in ("software/development", "graphs/development", "software/check",
                "graphs/check", "software/evaluation", "graphs/evaluation",
                "controls", "use"):
        path = fixtures_root / sub / ("%s.json" % task_id)
        if path.is_file():
            raw = path.read_bytes()
            return str(path.relative_to(fixtures_root)), _digest(raw), raw
    raise KeyError("unknown fixture %s" % task_id)


def _lane_b_manifest_digest(fixtures_root: Path) -> tuple:
    manifest_raw = (fixtures_root / "manifest.json").read_bytes()
    pinned = (fixtures_root / "manifest.sha256").read_text().strip()
    if _digest(manifest_raw) != pinned:
        raise ValueError("lane B manifest hash mismatch")
    manifest = json.loads(manifest_raw)
    return manifest.get("version", ""), pinned


def _software_transcripts(task: dict) -> dict:
    out = {}
    for method in ("ddmin", "greedy"):
        oracle = checkers.SoftwareOracle(task, max_queries=16)
        result = reducers.reduce_software(task, oracle, method=method,
                                          max_queries=16)
        final = result["candidate"]
        verdict = checkers.check_software(task, final)
        out[method] = {"kept_atoms": result["kept"], "queries": result["queries"],
                       "accepted": result["accepted"], "status": result["status"],
                       "history": [{"verdict": h["verdict"], "measure": h["measure"],
                                    "reason": h["reason"]} for h in oracle.history],
                       "final_measure": verdict["measure"],
                       "final_u": round((len(task["ops"]) - verdict["measure"])
                                        / len(task["ops"]), 6)}
    return out


def _graph_transcripts(task: dict) -> dict:
    out = {}
    initial = len(task["vertices"]) + len(task["edges"])
    for method in ("ddmin", "greedy"):
        oracle = checkers.GraphOracle(task, max_queries=16)
        result = reducers.reduce_graph(task, oracle, method=method,
                                       max_queries=16)
        final = result["candidate"]
        verdict = checkers.check_graph(task, final)
        out[method] = {"kept_atoms": result["kept"], "queries": result["queries"],
                       "accepted": result["accepted"], "status": result["status"],
                       "history": [{"verdict": h["verdict"], "measure": h["measure"],
                                    "reason": h["reason"]} for h in oracle.history],
                       "final_measure": verdict["measure"],
                       "final_u": round((initial - verdict["measure"]) / initial, 6)}
    return out


def build_context(fixtures_root: Path, *, stage: str, family: str,
                  task_ids: list, lessons: list) -> dict:
    version, manifest_digest = _lane_b_manifest_digest(fixtures_root)
    tasks, transcripts = [], {}
    for task_id in task_ids:
        rel, digest, raw = _fixture_digest(fixtures_root, task_id)
        task = json.loads(raw)
        if family == "software":
            parsed = software.parse_task(task)
            measure = software.measure(parsed["ops"])
            transcripts[task_id] = _software_transcripts(task)
            extra = {"fault": parsed["fault"]}
        else:
            parsed = graphs.parse_graph(task)
            measure = graphs.measure(parsed)
            transcripts[task_id] = _graph_transcripts(task)
            extra = {"pattern": "development"}
        tasks.append({"task_id": task_id, "path": rel, "digest": digest,
                      "measure": measure, **extra})
    return {"version": CONTEXT_VERSION, "stage": stage, "family": family,
            "provenance": "authored-fixture, not model output",
            "parent_refs": {"lane_b_manifest_version": version,
                            "lane_b_manifest_digest": manifest_digest},
            "tasks": tasks, "transcripts": transcripts, "lessons": lessons,
            "instruments": {"oracle_vocabulary": ["preserved", "not_preserved",
                                                  "invalid", "unknown"],
                            "budgets": {"witness_queries": 16,
                                        "component_invocations": 64,
                                        "elapsed_s": 120,
                                        "per_invocation_ms": 2000,
                                        "message_bytes": 65536}},
            "usable_by": ["arm-A", "arm-B", "arm-C", "future-arm"]}


def build_source_context(fixtures_root: Path) -> dict:
    return build_context(fixtures_root, stage="source", family="software",
                         task_ids=list(SOURCE_TASKS), lessons=list(SOURCE_LESSONS))


def build_transfer_context(fixtures_root: Path) -> dict:
    return build_context(fixtures_root, stage="transfer", family="graph",
                         task_ids=list(TRANSFER_TASKS), lessons=list(TRANSFER_LESSONS))


def write_contexts(repo_root: Path) -> dict:
    fixtures = repo_root / "experiments" / "representation" / "fixtures"
    target = repo_root / "experiments" / "representation" / "acquire"
    built = {"source_context.json": build_source_context(fixtures),
             "transfer_context.json": build_transfer_context(fixtures)}
    for name, doc in built.items():
        raw = (json.dumps(doc, sort_keys=True, indent=2) + "\n").encode()
        (target / name).write_bytes(raw)
    return {name: _digest((json.dumps(doc, sort_keys=True, indent=2) + "\n")
                          .encode()) for name, doc in built.items()}


def main(argv):
    repo = Path(argv[0]) if argv else ROOT
    digests = write_contexts(repo)
    print(json.dumps(digests, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
