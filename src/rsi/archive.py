"""Genome archive and recorded DGM-style parent selection.

Every published genome stays selectable. Dev scores count missing verdicts as
unsolved, so incomplete evaluation cannot inflate a node's weight. Selection
is fixed policy; the record retains its task set, scores, draw and weights.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import secrets

from psycopg.types.json import Json

from settlement import db, store
from settlement.common import Command, ResultCode, SettlementError


@dataclass(frozen=True)
class Node:
    digest: str
    parent: str | None
    score: float
    measured: int
    children: int
    weight: float


def weight(score: float, children: int) -> float:
    if not 0 <= score <= 1 or children < 0:
        raise ValueError("archive score must be in [0, 1] and children nonnegative")
    return 1 / (1 + math.exp(-10 * (score - 0.5))) / (1 + children)


def decision(dsn: str, decision_id: str) -> dict | None:
    with db.connect(dsn) as conn:
        row = conn.execute("SELECT kind, actor, subject, data FROM rsi_decisions WHERE id = %s",
                           (decision_id,)).fetchone()
    return None if row is None else dict(kind=row[0], actor=row[1], subject=row[2], data=row[3])


def record(dsn: str, decision_id: str, *, kind: str, actor: str, subject: str, data: dict) -> dict:
    payload = dict(kind=kind, actor=actor, subject=subject, data=data)

    def save(cur, control):
        cur.execute("INSERT INTO rsi_decisions (id, kind, actor, subject, data) VALUES (%s,%s,%s,%s,%s)",
                    (decision_id, kind, actor, subject, Json(data)))
        return ResultCode.APPLIED, "decision recorded", payload, [("rsi.decision", payload)], []

    result = store.transact(dsn, Command(request_id="rsi-decision:" + decision_id, payload=payload), save)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    return result.data


def _nodes(cur, dev_tasks: tuple[str, ...]) -> list[Node]:
    if not dev_tasks or len(set(dev_tasks)) != len(dev_tasks):
        raise SettlementError("selection needs a nonempty unique dev task set")
    cur.execute("SELECT digest FROM rsi_tasks WHERE split = 'dev' AND digest = ANY(%s)", (list(dev_tasks),))
    if {r['digest'] for r in cur.fetchall()} != set(dev_tasks):
        raise SettlementError("parent selection accepts published dev tasks only")
    cur.execute("SELECT g.digest, g.parent, (SELECT count(*) FROM rsi_genomes c WHERE c.parent=g.digest) AS children,"
                " count(v.passed) AS measured, count(*) FILTER (WHERE v.passed IS TRUE) AS solved"
                " FROM rsi_genomes g CROSS JOIN rsi_tasks t"
                " LEFT JOIN LATERAL (SELECT v.passed FROM rsi_episodes e LEFT JOIN rsi_verdicts v"
                " ON v.episode=e.operation_id AND v.evaluator_version=t.evaluator_version"
                " WHERE e.genome=g.digest AND e.task=t.digest"
                " ORDER BY e.created_at DESC, e.operation_id DESC LIMIT 1) v ON true"
                " WHERE t.digest=ANY(%s) GROUP BY g.digest ORDER BY g.digest", (list(dev_tasks),))
    nodes = []
    for r in cur.fetchall():
        score = int(r['solved']) / len(dev_tasks)
        children = int(r['children'])
        nodes.append(Node(r['digest'], r['parent'], score, int(r['measured']), children,
                          weight(score, children)))
    if not nodes:
        raise SettlementError("archive has no genomes")
    return nodes


def select_parent(dsn: str, decision_id: str, dev_tasks: tuple[str, ...], *, draw: float | None = None) -> str:
    """Select once. Replays return the original parent despite later archive growth."""
    tasks = tuple(sorted(dev_tasks))
    if draw is not None and not 0 <= draw < 1:
        raise ValueError("selection draw must be in [0, 1)")
    payload = {"dev_tasks": list(tasks), "policy": "sigmoid-10-0.5/children-v1"}

    def select(cur, control):
        nodes = _nodes(cur, tasks)
        point = secrets.SystemRandom().random() if draw is None else draw
        target = point * sum(n.weight for n in nodes)
        parent = nodes[-1].digest
        for node in nodes:
            target -= node.weight
            if target < 0:
                parent = node.digest
                break
        data = dict(payload, parent=parent, draw=point, nodes=[asdict(n) for n in nodes])
        cur.execute("INSERT INTO rsi_decisions (id, kind, actor, subject, data)"
                    " VALUES (%s, 'parent-selection', 'fixed', %s, %s)", (decision_id, parent, Json(data)))
        return ResultCode.APPLIED, "parent selected", data, [("rsi.parent-selected", data)], []

    result = store.transact(dsn, Command(request_id="rsi-select:" + decision_id, payload=payload), select)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    return result.data['parent']
