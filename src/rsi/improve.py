"""Meta-agent proposals from pinned genomes and development evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from psycopg.rows import dict_row

from settlement import artifacts, broker, db, store
from settlement.common import Command, ResultCode, SettlementError

from . import archive, episode, genome


@dataclass(frozen=True)
class Proposal:
    operation_id: str
    parent: str
    evidence: str
    status: str
    child: str | None
    trajectory: str
    detail: str


def read(dsn: str, operation_id: str) -> Proposal | None:
    with db.connect(dsn) as conn:
        row = conn.execute("SELECT operation_id, parent, evidence, status, child, trajectory, detail"
                           " FROM rsi_proposals WHERE operation_id = %s", (operation_id,)).fetchone()
    return Proposal(*row) if row else None


def evidence_bundle(dsn: str, artifacts_root: Path, parent: str) -> bytes:
    """Only dev episodes of this parent and its quarantined children can cross this boundary."""
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT g.digest FROM rsi_genomes g WHERE g.parent=%s AND EXISTS"
                        " (SELECT 1 FROM rsi_decisions d WHERE d.subject=g.digest"
                        " AND d.kind='gate' AND d.data->>'disposition'='quarantine') ORDER BY g.digest LIMIT 8", (parent,))
            siblings = [r['digest'] for r in cur.fetchall()]
            cur.execute("SELECT e.operation_id, e.genome, e.task, e.status, e.trajectory, t.name,"
                        " v.status AS verdict, v.detail FROM rsi_episodes e"
                        " JOIN rsi_tasks t ON t.digest=e.task AND t.split='dev'"
                        " LEFT JOIN rsi_verdicts v ON v.episode=e.operation_id AND v.evaluator_version=t.evaluator_version"
                        " WHERE e.genome=ANY(%s) ORDER BY e.created_at DESC, e.operation_id DESC LIMIT 16", ([parent, *siblings],))
            rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        raw = (artifacts_root / row.pop('trajectory')).read_bytes()
        package = json.loads(raw)
        trace = bytes.fromhex(package['files']['events.jsonl']).decode('utf-8', 'replace')
        row['trajectory_tail'] = trace[-32_768:]
        if row['detail'] is not None:
            row['detail'] = json.dumps(row['detail'], sort_keys=True)[-16_384:]
    return json.dumps(dict(parent=parent, failed_siblings=siblings, dev_episodes=rows),
                      sort_keys=True, separators=(',', ':')).encode()


def propose(dsn: str, launcher, parent_digest: str, *, operation_id: str,
            allocation_id: str, token_ceiling: int, timeout_ms: int,
            staging_root: Path, artifacts_root: Path) -> Proposal:
    known = read(dsn, operation_id)
    if known:
        if known.parent != parent_digest:
            raise SettlementError("proposal identity belongs to another parent")
        archive.record(dsn, 'proposal:'+operation_id, kind='proposal', actor='ai',
                       subject=known.child or parent_digest,
                       data={'operation_id':operation_id, 'status':known.status, 'rationale':known.detail})
        return known
    parent = genome.load(dsn, artifacts_root, parent_digest)
    instructions = parent.files.get('meta/IMPROVE.md')
    if instructions is None:
        raise SettlementError("parent genome needs meta/IMPROVE.md")
    existing = broker.read_operation(dsn, operation_id)
    if existing is None:
        raw = evidence_bundle(dsn, artifacts_root, parent_digest)
        manifest = {'kind': 'rsi-dev-evidence', 'files': [{'path': 'evidence.json', 'kind': 'file',
                    'size': len(raw), 'digest': hashlib.sha256(raw).hexdigest()}]}
        staged = artifacts.stage_package(dsn, staging_root, manifest=manifest,
                                         files={'evidence.json': raw}, scope='rsi-dev-evidence',
                                         access_label='candidate', format='json')
        published = artifacts.publish_package(dsn, Command(request_id='rsi-evidence:'+staged['digest'],
                                               payload={'digest':staged['digest']}), artifacts_root, staged)
        if published.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            raise SettlementError(published.detail)
        evidence = staged['digest']
        for rel, data in parent.files.items():
            launcher.stage_input(operation_id, '', 'genome/'+rel, data)
        launcher.stage_input(operation_id, '', 'evidence.json', raw)
        launcher.stage_input(operation_id, '', 'AGENTS.md', instructions)
    else:
        if existing['payload'].get('genome') != parent_digest:
            raise SettlementError("proposal operation belongs to another parent")
        evidence = existing['payload']['task']
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.AGENT_RUN, allocation_id=allocation_id,
        payload={'harness':parent.harness, 'genome':parent_digest, 'task':evidence,
                 'instruction': 'Improve the agent in genome/ using evidence.json and your AGENTS.md. '
                                'Edit only genome/. Preserve its file layout. Improve meta/IMPROVE.md when useful. '
                                'Do not claim evaluation results. Explain your change in the final message.',
                 'config':genome.settings(parent), 'timeout_ms':timeout_ms, 'token_ceiling':token_ceiling})
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(ensured.detail)
    settled = broker.dispatch_operation(dsn, operation_id, launchers={launcher.profile:launcher})
    if settled.dispatch_state not in episode.TERMINAL:
        raise SettlementError('proposal needs dispatch recovery: '+settled.next_decision)
    result = launcher.read_result(operation_id)
    if result is None:
        raise SettlementError('settled proposal has no result')
    raw = launcher.read_output(operation_id, '', 'events.jsonl')
    if hashlib.sha256(raw).hexdigest() != result['trajectory_digest']:
        raise SettlementError('proposal trajectory changed')
    trajectory = episode._publish_trajectory(dsn, raw, staging_root, artifacts_root, 'candidate')
    status, child, detail = result['status'], None, result.get('final_message','')
    if status == 'completed':
        with db.connect(dsn) as conn:
            prior = conn.execute("SELECT digest FROM rsi_genomes WHERE origin->>'origin'=%s",
                                 ('proposal:'+operation_id,)).fetchone()
        if prior:
            child = prior[0]
        else:
            workspace, _ = launcher.exec_dirs(operation_id, '')
            try:
                output = genome.from_dir(Path(workspace)/'genome', parent.harness)
                if output.digest == parent_digest:
                    raise genome.GenomeError('proposal made no genome change')
                if not output.files.get('meta/IMPROVE.md'):
                    raise genome.GenomeError('child must retain meta/IMPROVE.md')
                child = genome.publish(dsn, output, staging_root=staging_root, artifacts_root=artifacts_root,
                                       parent=parent_digest, origin='proposal:'+operation_id)
            except genome.GenomeError as exc:
                status, detail = 'invalid', str(exc)
    proposal = Proposal(operation_id, parent_digest, evidence, status, child, trajectory, detail)

    def save(cur, control):
        artifacts._add_reference(cur, evidence, 'evidence', 'rsi-proposal:'+operation_id)
        artifacts._add_reference(cur, trajectory, 'attempt', 'rsi-proposal:'+operation_id)
        cur.execute("INSERT INTO rsi_proposals (operation_id,parent,evidence,status,child,trajectory,detail)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (operation_id, parent_digest, evidence, status, child, trajectory, detail))
        return ResultCode.APPLIED, 'proposal recorded', {'operation_id':operation_id}, [], []

    saved = store.transact(dsn, Command(request_id='rsi-proposal:'+operation_id, payload=proposal.__dict__), save)
    if saved.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(saved.detail)
    archive.record(dsn, 'proposal:'+operation_id, kind='proposal', actor='ai',
                   subject=child or parent_digest, data={'operation_id':operation_id, 'status':status, 'rationale':detail})
    return proposal
