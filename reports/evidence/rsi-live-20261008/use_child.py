"""Fresh-process use of the exact live-acquired child; development diagnostic only."""
import argparse
import json
from pathlib import Path
from run import DSN, ROOT, ROOTS, CODEX
from rsi import episode, genome, task, verifier
from settlement import store
from settlement.common import Command, ResultCode
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--smoke', action='store_true')
args = parser.parse_args()
proposal = json.loads((ROOT / 'direct-acquisition-report.json').read_text())['proposal']
assert proposal['status'] == 'completed' and proposal['child']
subject = genome.load(DSN, ROOT / 'art', proposal['child'])
assert subject.digest == proposal['child'] and subject.digest != proposal['parent']
op = 'live08-direct-child-smoke' if args.smoke else 'live08-direct-child-grade-school'
plan = dict(operation=op, model='openrouter/openrouter/free', genome=subject.digest,
            parent=proposal['parent'], constructor=proposal['operation_id'], episodes_maximum=1,
            task='live-tool-smoke-add' if args.smoke else 'grade-school', token_ceiling=1000000, timeout_ms=180000,
            request_retries=1, stream_retries=1, interpretation='Development use, not independent transfer or gain')
path = ROOT / ('child-smoke-use-plan.json' if args.smoke else 'child-use-plan.json')
if path.exists():
    assert json.loads(path.read_text()) == plan
else:
    path.write_text(json.dumps(plan, indent=2) + '\n')
if args.smoke:
    task_digest = json.loads((ROOT / 'tool-smoke-report.json').read_text())['task']
else:
    bank = json.loads((ROOT / 'bank-report.json').read_text())
    task_digest = next(r for r in bank['sanity'] if r['name'] == plan['task'])['task']
item = task.load(DSN, ROOT / 'art', task_digest)
assert item.split == 'dev'
route = dict(l.split('=', 1) for l in Path('D:/AI/tools/model-route.env').read_text().splitlines()
             if l and not l.startswith('#'))
for domain, amount in [('tokens', plan['token_ceiling']), ('cpu', 120)]:
    result = store.seed_allocation(DSN, Command(request_id=op + ':' + domain,
        payload=dict(allocation_id=op + ':' + domain, domain=domain, authorized=amount)))
    assert result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
agent = CodexLauncher(ROOT / 'runs', codex_cmd=[CODEX],
    provider=Provider(route['SETTLEMENT_GATEWAY_ENDPOINT'], plan['model'], route['SETTLEMENT_GATEWAY_KEY'],
                      request_retries=1, stream_retries=1), allowed_overrides=genome.HARNESS_KEYS)
print(json.dumps({'start': op, 'genome': subject.digest}), flush=True)
ep = episode.run_episode(DSN, agent, subject, operation_id=op, task=item,
    allocation_id=op + ':tokens', attempt_id=None, token_ceiling=plan['token_ceiling'],
    timeout_ms=plan['timeout_ms'], **ROOTS)
workspace, _ = agent.exec_dirs(op, '')
for rel, raw in genome.workspace_view(subject).items():
    assert (Path(workspace) / rel).read_bytes() == raw, 'Staged genome changed during execution'
out = dict(operation=op, model=plan['model'], genome=subject.digest, task=item.digest, status=ep.status,
           tokens=ep.tokens, seconds=ep.seconds, trajectory=ep.trajectory,
           staged_genome_verified=True, constructor=proposal['operation_id'], interpretation=plan['interpretation'])
if ep.status == 'completed':
    checked = verifier.verify_episode(DSN, agent, LocalLauncher(ROOT / 'verifiers'), op,
        allocation_id=op + ':cpu', attempt_id=None, **ROOTS)
    out['verifier'] = dict(operation=checked.operation_id, passed=checked.passed, status=checked.status)
(ROOT / ('child-smoke-use-report.json' if args.smoke else 'child-use-report.json')).write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2), flush=True)
