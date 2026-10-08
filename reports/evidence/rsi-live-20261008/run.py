"""Bounded live qualification through the existing RSI runtime. No credentials in output."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path('D:/AI/Agent-Society-v2')
sys.path.insert(0, str(REPO / 'src'))
from rsi import episode, genome, task, verifier
from settlement import db, store
from settlement.common import Command, ResultCode
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

ROOT = Path(__file__).resolve().parent
DSN = 'dbname=rsi_live_20261008 host=127.0.0.1 port=55432 user=postgres'
SOURCE_DSN = 'dbname=rsi_t5 host=127.0.0.1 port=55432 user=postgres'
SOURCE_ROOT = Path('D:/AI/tools/rsi-t5')
CODEX = 'C:/Users/roysh/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe'
ROOTS = dict(staging_root=ROOT / 'stage', artifacts_root=ROOT / 'art')


def bootstrap():
    import psycopg
    from psycopg import sql
    with psycopg.connect('dbname=postgres host=127.0.0.1 port=55432 user=postgres', autocommit=True) as conn:
        exists = conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', ('rsi_live_20261008',)).fetchone()
        if not exists:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier('rsi_live_20261008')))
    db.apply_migrations(DSN, REPO / 'migrations')
    bank = json.loads((SOURCE_ROOT / 'bank-report.json').read_text())
    for row in bank['sanity']:
        value = task.load(SOURCE_DSN, SOURCE_ROOT / 'art', row['task'])
        assert task.publish(DSN, value, **ROOTS) == row['task']
    (ROOT / 'bank-report.json').write_text(json.dumps(bank, indent=2) + '\n')
    plan = dict(source_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
                purpose='Qualify free tool routes, task competence and retained revision; no presumed learning gain',
                model_candidates=['nvidia/nemotron-3-ultra-550b-a55b:free', 'stepfun/step-3.7-flash:free', 'deepseek/deepseek-v4-pro-free'],
                probe_task='proverb', route_probes_maximum=3, tokens_per_probe=300000, timeout_ms=480000,
                dev=['proverb', 'grade-school', 'phone-number'], validation=['transpose'],
                anchor=['affine-cipher', 'bottle-song', 'bowling', 'list-ops', 'poker', 'tree-building'],
                generations_maximum=1, trusted_promotion=False,
                authorization='Human authorized only free gateway routes in this chat',
                price_evidence='Exact gateway catalogue IDs explicitly label these routes free; no paid fallback',
                containment='Cooperative benchmark with native process bounds; filesystem/network confinement unqualified')
    path = ROOT / 'plan.json'
    if path.exists():
        assert json.loads(path.read_text()) == plan, 'Existing plan differs; use a new study root'
    else:
        path.write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps(dict(bootstrap='complete', database='rsi_live_20261008', tasks=len(bank['sanity']))), flush=True)


def probe(model, op, name, plan_name='plan.json'):
    plan = json.loads((ROOT / plan_name).read_text())
    assert model in plan['model_candidates'] and name == plan['probe_task']
    assert model.endswith((':free', '-free')) or model in ('openrouter/free', 'kilo-auto/free', 'openrouter/openrouter/free')
    route = dict(line.split('=', 1) for line in Path('D:/AI/tools/model-route.env').read_text().splitlines()
                 if line and not line.startswith('#'))
    bank = json.loads((ROOT / 'bank-report.json').read_text())
    row = next(row for row in bank['sanity'] if row['name'] == name)
    assert row['split'] == 'dev'
    subject = task.load(DSN, ROOT / 'art', row['task'])
    seed = genome.from_dir(Path('D:/AI/tools/rsi-t9-seed'))
    genome.publish(DSN, seed, parent=None, origin='live-20261008-seed', **ROOTS)
    for domain, amount in [('tokens', plan['tokens_per_probe']), ('cpu', 120)]:
        result = store.seed_allocation(DSN, Command(request_id=op + ':' + domain,
            payload=dict(allocation_id=op + ':' + domain, domain=domain, authorized=amount)))
        assert result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED), result
    agent = CodexLauncher(ROOT / 'runs', codex_cmd=[CODEX],
        provider=Provider(route['SETTLEMENT_GATEWAY_ENDPOINT'], model, route['SETTLEMENT_GATEWAY_KEY'],
                          request_retries=plan.get('request_retries', 10),
                          stream_retries=plan.get('stream_retries', 10)),
        allowed_overrides=genome.HARNESS_KEYS)
    print(json.dumps(dict(start=op, model=model, task=name)), flush=True)
    value = episode.run_episode(DSN, agent, seed, operation_id=op, task=subject,
        allocation_id=op + ':tokens', attempt_id=None, timeout_ms=plan['timeout_ms'],
        token_ceiling=plan['tokens_per_probe'], **ROOTS)
    report = dict(operation_id=op, model=model, genome=seed.digest, task=subject.digest,
        status=value.status, tokens=value.tokens, seconds=value.seconds, trajectory=value.trajectory,
        infra_reason=value.infra_reason)
    if value.status == 'completed':
        checked = verifier.verify_episode(DSN, agent, LocalLauncher(ROOT / 'verifiers'), op,
            allocation_id=op + ':cpu', attempt_id=None, **ROOTS)
        report['verifier'] = dict(operation_id=checked.operation_id, status=checked.status, passed=checked.passed)
    report['accounting'] = {}
    for domain in ['tokens', 'cpu']:
        current = store.allocation_status(DSN, op + ':' + domain)
        report['accounting'][domain] = {key: current[key] for key in ['authorized', 'reserved', 'consumed']}
    (ROOT / (op + '-report.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['bootstrap', 'probe', 'probe2', 'probe3', 'direct'])
    parser.add_argument('--model')
    parser.add_argument('--operation')
    args = parser.parse_args()
    if args.mode == 'bootstrap':
        bootstrap()
    else:
        if not args.model or not args.operation:
            parser.error('probe requires --model and --operation')
        plans = {'probe': 'plan.json', 'probe2': 'route-round2-plan.json', 'probe3': 'route-round3-plan.json',
                 'direct': 'direct-openrouter-plan.json'}
        name = json.loads((ROOT / plans[args.mode]).read_text())['probe_task']
        probe(args.model, args.operation, name, plans[args.mode])
