"""Baseline reducers any arm may use.

``ddmin_reduce`` is a deletion-only ddmin over abstract atoms; ``greedy_reduce``
removes one atom at a time in a domain-aware priority order. Both use only
legal operations: every trial goes through oracle feedback and only
``preserved`` trials are accepted. Family adapters supply atomization,
candidate building and priority.
"""

from __future__ import annotations

from .checkers import PRESERVED


def _chunks(count: int, parts: int):
    size, extra = divmod(count, parts)
    out, start = [], 0
    for piece in range(parts):
        stop = start + size + (1 if piece < extra else 0)
        out.append(list(range(start, stop)))
        start = stop
    return out


def ddmin_reduce(count: int, build, probe, *, max_queries: int = 16) -> dict:
    keep = list(range(count))
    if probe(build(keep))["verdict"] != PRESERVED:
        return {"kept": keep, "queries": 1, "accepted": 0,
                "status": "initial-not-preserved"}
    queries, accepted, parts = 1, 0, 2
    while len(keep) >= 2:
        parts = min(parts, len(keep))
        improved = False
        for chunk in _chunks(len(keep), parts):
            if queries >= max_queries:
                return {"kept": keep, "queries": queries,
                        "accepted": accepted, "status": "budget-exhausted"}
            doomed = set(chunk)
            trial_keep = [atom for pos, atom in enumerate(keep) if pos not in doomed]
            if not trial_keep:
                continue
            trial = build(trial_keep)
            if trial is None:
                continue
            queries += 1
            if probe(trial)["verdict"] == PRESERVED:
                keep = trial_keep
                accepted += 1
                parts = max(parts - 1, 2)
                improved = True
                break
        if improved:
            continue
        if parts >= len(keep):
            break
        parts = min(parts * 2, len(keep))
    return {"kept": keep, "queries": queries, "accepted": accepted,
            "status": "locally-irreducible"}


def greedy_reduce(count: int, build, probe, *, priority=None,
                  max_queries: int = 16) -> dict:
    keep = list(range(count))
    order = list(priority) if priority is not None else list(range(count))
    if probe(build(keep))["verdict"] != PRESERVED:
        return {"kept": keep, "queries": 1, "accepted": 0,
                "status": "initial-not-preserved"}
    queries, accepted = 1, 0
    changed = True
    while changed and len(keep) > 1:
        changed = False
        for atom in [a for a in order if a in keep]:
            if queries >= max_queries:
                return {"kept": keep, "queries": queries,
                        "accepted": accepted, "status": "budget-exhausted"}
            trial_keep = [a for a in keep if a != atom]
            trial = build(trial_keep)
            if trial is None:
                continue
            queries += 1
            if probe(trial)["verdict"] == PRESERVED:
                keep = trial_keep
                accepted += 1
                changed = True
    return {"kept": keep, "queries": queries, "accepted": accepted,
            "status": "locally-irreducible"}


def software_atoms(task: dict):
    ops = task["ops"]
    witness_id = task["witness"]["observation"]
    witness_pos = next(i for i, entry in enumerate(ops)
                       if entry.get("id") == witness_id)

    def build(keep):
        kept = [ops[i] for i in sorted(keep)]
        # The candidate is a proposal to the grader, not a copy of the
        # task. It carries the identity the grader matches on and the
        # atoms it will read; it does not carry the fault, the witness
        # values or the seed, which the grader already holds and a member
        # must not be able to read off its own output.
        return {"family": "software", "task_id": task["task_id"],
                "ops": kept}

    order = ([i for i in range(len(ops) - 1, -1, -1) if i != witness_pos]
             + [witness_pos])
    return build, order


def graph_atoms(task: dict):
    from .graphs import adjacency
    vertices = list(task["vertices"])
    edges = [list(e) for e in task["edges"]]
    table = adjacency(vertices, edges)
    units = [("v", v) for v in vertices] + [("e", i) for i in range(len(edges))]

    def build(keep):
        kept = set(keep)
        gone = {units[i][1] for i in range(len(units))
                if i not in kept and units[i][0] == "v"}
        drop_e = {units[i][1] for i in range(len(units))
                  if i not in kept and units[i][0] == "e"}
        keep_v = [v for v in vertices if v not in gone]
        if not keep_v:
            return None
        kept_v = set(keep_v)
        keep_e = [e for i, e in enumerate(edges)
                  if i not in drop_e and e[0] in kept_v and e[1] in kept_v]
        return {"family": "graph", "task_id": task["task_id"],
                "vertices": keep_v, "edges": keep_e}

    def priority():
        scores = []
        for i, (kind, ref) in enumerate(units):
            if kind == "v":
                scores.append((len(table.get(ref, ())), 0, i))
            else:
                first, second = edges[ref]
                scores.append((len(table.get(first, ()))
                               + len(table.get(second, ())), 1, i))
        scores.sort()
        return [i for _, _, i in scores]

    return build, priority()


def reduce_software(task, oracle, *, method: str,
                    max_queries: int = 16) -> dict:
    """`method` has no default on purpose.

    It had one, `ddmin`, and every acquisition observed chose it while
    matching the authored control exactly. A default that is the answer
    makes the choice untestable: a caller that never chooses looks identical
    to one that chose correctly. Every caller already passed a method, so
    making it required cost nothing and removed the excuse.
    """
    build, order = software_atoms(task)
    probe = lambda cand: oracle.query(cand)  # noqa: E731
    if method == "greedy":
        result = greedy_reduce(len(task["ops"]), build, probe,
                               priority=order, max_queries=max_queries)
    elif method == "ddmin":
        result = ddmin_reduce(len(task["ops"]), build, probe,
                              max_queries=max_queries)
    else:
        raise ValueError("unknown-method")
    result["candidate"] = build(result["kept"])
    return result


def reduce_graph(task, oracle, *, method: str,
                 max_queries: int = 16) -> dict:
    """`method` is required here for the same reason as in `reduce_software`."""
    build, order = graph_atoms(task)
    count = len(task["vertices"]) + len(task["edges"])
    probe = lambda cand: oracle.query(cand)  # noqa: E731
    if method == "greedy":
        result = greedy_reduce(count, build, probe,
                               priority=order, max_queries=max_queries)
    elif method == "ddmin":
        result = ddmin_reduce(count, build, probe, max_queries=max_queries)
    else:
        raise ValueError("unknown-method")
    result["candidate"] = build(result["kept"])
    return result
