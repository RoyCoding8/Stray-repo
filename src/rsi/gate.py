"""Frozen, staged comparisons with conservative anchor exposure accounting.

Validation precedes solved-task regression, which precedes the anchor. Anchor
content may be exposed to one comparison only, including interrupted or failed
runs. This is reuse accounting, not an implementation of REUSE's reusable
holdout algorithm. The paired sign test and alpha spending are recorded; their
scope is this task sample, not a claim of general autonomous improvement.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

from psycopg.types.json import Json

from settlement import db, store
from settlement.common import Command, ResultCode, SettlementError

from . import archive, episode, genome, task, verifier

POLICY = 'val-regression-fresh-anchor-sign-v1'


@dataclass(frozen=True)
class Budget:
    model: str
    token_ceiling: int
    timeout_ms: int

    def __post_init__(self):
        if not self.model.endswith((':free', '-free')):
            raise ValueError('gate requires an approved free model')
        if self.token_ceiling <= 0 or self.timeout_ms <= 0:
            raise ValueError('gate budgets must be positive')


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def freeze(dsn: str, tasks: tuple[task.Task, ...], budget: Budget, *, execution: str = 'contained') -> str:
    if execution not in ('contained', 'benchmark'):
        raise ValueError('execution must be contained or benchmark')
    specs = {t.digest: {'split': t.split, 'evaluator': t.evaluator_version} for t in tasks}
    if len(specs) != len(tasks) or {t.split for t in tasks} != {'dev', 'val', 'anchor'}:
        raise ValueError('epoch needs unique tasks in all three splits')
    data = dict(tasks=specs, budget=asdict(budget), policy=POLICY, execution=execution)
    digest = _digest(data)

    def save(cur, control):
        cur.execute('SELECT digest, split, evaluator_version FROM rsi_tasks WHERE digest=ANY(%s)', (list(specs),))
        actual = {r['digest']: {'split':r['split'], 'evaluator':r['evaluator_version']} for r in cur.fetchall()}
        if actual != specs:
            raise SettlementError('epoch tasks must match the published bank')
        cur.execute('INSERT INTO rsi_gate_epochs (digest,tasks,budget,policy,execution) VALUES (%s,%s,%s,%s,%s)',
                    (digest,Json(specs),Json(asdict(budget)),POLICY,execution))
        return ResultCode.APPLIED, 'gate epoch frozen', {'digest':digest}, [], []

    result = store.transact(dsn,Command(request_id='rsi-epoch:'+digest,payload=data),save)
    if result.code not in (ResultCode.APPLIED,ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    return digest


def anchor_identity(item: task.Task) -> str:
    # A name, split, driver or runtime change does not make ground truth fresh.
    return _digest({'instruction':item.instruction,
                    **{kind:{p:raw.hex() for p,raw in getattr(item,kind).items()}
                       for kind in ('workspace','verifier','reference')}})


def reserve_anchor(dsn: str, gate_id: str, anchors: tuple[task.Task, ...]) -> float:
    ids = {anchor_identity(t): t.digest for t in anchors}
    if not ids or len(ids) != len(anchors) or any(t.split != 'anchor' for t in anchors):
        raise ValueError('anchor exposure needs unique anchor content')

    def reserve(cur, control):
        cur.execute('SELECT identity, gate FROM rsi_anchor_uses WHERE identity=ANY(%s)',(list(ids),))
        if any(r['gate'] != gate_id for r in cur.fetchall()):
            raise SettlementError('anchor content already exposed to another comparison')
        cur.execute('SELECT count(DISTINCT gate) AS n FROM rsi_anchor_uses')
        index = int(cur.fetchone()['n'])+1
        for identity,digest in ids.items():
            cur.execute('INSERT INTO rsi_anchor_uses (identity,task,gate) VALUES (%s,%s,%s)',
                        (identity,digest,gate_id))
        alpha = 0.05/(index*(index+1))
        return ResultCode.APPLIED, 'anchor exposure reserved', {'index':index,'alpha':alpha}, [], []

    result=store.transact(dsn,Command(request_id='rsi-anchor:'+gate_id,payload={'anchors':ids}),reserve)
    if result.code not in (ResultCode.APPLIED,ResultCode.ALREADY_APPLIED):
        raise SettlementError(result.detail)
    return float(result.data['alpha'])


def paired_verdict(parent: tuple[bool, ...], candidate: tuple[bool, ...], alpha: float) -> dict:
    if not parent or len(parent) != len(candidate) or not 0 < alpha < 1:
        raise ValueError('paired anchor outcomes and alpha required')
    if any(type(x) is not bool for x in (*parent,*candidate)):
        raise ValueError('unknown outcomes cannot receive a score')
    wins=sum(not p and c for p,c in zip(parent,candidate))
    losses=sum(p and not c for p,c in zip(parent,candidate))
    discordant=wins+losses
    p_value=sum(math.comb(discordant,k) for k in range(wins,discordant+1))/2**discordant
    return dict(wins=wins,losses=losses,p_value=p_value,alpha=alpha,
                promote=wins>0 and losses==0 and p_value<=alpha)


def run(dsn: str, agent_launcher, verifier_launcher, *, gate_id: str, epoch: str,
        parent: str, candidate: str, token_allocation: str, cpu_allocation: str,
        staging_root: Path, artifacts_root: Path) -> dict:
    payload=dict(epoch=epoch,parent=parent,candidate=candidate)

    def admit(cur, control):
        if parent == candidate:
            raise SettlementError('gate needs a changed candidate')
        cur.execute('INSERT INTO rsi_gate_runs (id,epoch,parent,candidate) VALUES (%s,%s,%s,%s)',
                    (gate_id,epoch,parent,candidate))
        return ResultCode.APPLIED,'comparison admitted',payload,[],[]

    admitted=store.transact(dsn,Command(request_id='rsi-gate:'+gate_id,payload=payload),admit)
    if admitted.code not in (ResultCode.APPLIED,ResultCode.ALREADY_APPLIED):
        raise SettlementError(admitted.detail)
    known=archive.decision(dsn,'gate:'+gate_id)
    if known:
        return known['data']
    with db.connect(dsn) as conn:
        row=conn.execute('SELECT tasks,budget,policy,execution FROM rsi_gate_epochs WHERE digest=%s',(epoch,)).fetchone()
    specs,budget_raw,policy,execution=row
    if policy != POLICY:
        raise SettlementError('gate policy version changed')
    budget=Budget(**budget_raw)
    report={'epoch':epoch,'parent':parent,'candidate':candidate,'phases':{},'scope':execution}

    def finish(disposition,reason):
        report.update(disposition=disposition,reason=reason)
        archive.record(dsn,'gate:'+gate_id,kind='gate',actor='fixed',subject=candidate,data=report)
        return report

    # Launcher declarations belong to the controller, never to a genome.
    declarations=[]
    for launcher in (agent_launcher,verifier_launcher):
        describe=getattr(launcher,'declaration',None)
        declaration=describe() if callable(describe) else {}
        declarations.append(declaration)
    report['execution']=declarations
    if execution == 'contained' and any(
            d.get('containment') is not True or d.get('network') != 'none' for d in declarations):
        return finish('blocked','execution containment is unproved')
    if agent_launcher.provider.model != budget.model:
        return finish('blocked','model differs from frozen budget')
    items={digest:task.load(dsn,artifacts_root,digest) for digest in specs}
    if any(specs[d] != {'split':t.split,'evaluator':t.evaluator_version} for d,t in items.items()):
        return finish('blocked','frozen evaluator mismatch')
    genomes={d:genome.load(dsn,artifacts_root,d) for d in (parent,candidate)}

    def measure(label,digests,subjects):
        outcomes={d:[] for d in subjects}
        rows=[]
        report['phases'][label]=rows
        for digest in sorted(digests):
            for subject in subjects:
                op='rsi-gate-'+_digest(dict(gate=gate_id,phase=label,task=digest,genome=subject))
                ep=episode.run_episode(dsn,agent_launcher,genomes[subject],operation_id=op,
                    task=items[digest],allocation_id=token_allocation,attempt_id=None,
                    token_ceiling=budget.token_ceiling,timeout_ms=budget.timeout_ms,
                    staging_root=staging_root,artifacts_root=artifacts_root)
                if ep.status != 'completed':
                    rows.append(dict(genome=subject,task=digest,episode=op,status=ep.status,passed=None))
                    raise SettlementError('agent execution did not complete: '+ep.status)
                verdict=verifier.verify_episode(dsn,agent_launcher,verifier_launcher,op,
                    allocation_id=cpu_allocation,attempt_id=None,staging_root=staging_root,artifacts_root=artifacts_root)
                rows.append(dict(genome=subject,task=digest,episode=op,verdict=verdict.operation_id,
                                 status=verdict.status,passed=verdict.passed,tokens=ep.tokens,seconds=ep.seconds))
                if verdict.passed is None:
                    raise SettlementError('verifier has no task outcome: '+verdict.status)
                outcomes[subject].append(verdict.passed)
        return outcomes

    try:
        validation=[d for d,t in items.items() if t.split=='val']
        values=measure('val',validation,(parent,candidate))
        if sum(values[candidate]) < sum(values[parent]):
            return finish('quarantine','validation score decreased')
        with db.connect(dsn) as conn:
            rows=conn.execute('SELECT DISTINCT e.task FROM rsi_episodes e JOIN rsi_verdicts v ON v.episode=e.operation_id'
                              ' WHERE e.genome=%s AND e.task=ANY(%s) AND v.passed IS TRUE',
                              (parent,[d for d,t in items.items() if t.split!='anchor'])).fetchall()
        solved=[r[0] for r in rows]
        regressions=measure('regression',solved,(candidate,))
        if not all(regressions[candidate]):
            return finish('quarantine','previously solved task regressed')
        anchors=tuple(t for t in items.values() if t.split=='anchor')
        alpha=reserve_anchor(dsn,gate_id,anchors)
        values=measure('anchor',[t.digest for t in anchors],(parent,candidate))
        verdict=paired_verdict(tuple(values[parent]),tuple(values[candidate]),alpha)
        report['anchor_comparison']=verdict
        accepted = 'promote' if execution == 'contained' else 'experimental_gain'
        return finish(accepted if verdict['promote'] else 'quarantine',
                      'paired anchor gain' if verdict['promote'] else 'anchor evidence does not support promotion')
    except SettlementError as exc:
        return finish('blocked',str(exc))
