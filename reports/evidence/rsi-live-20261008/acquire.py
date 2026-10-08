"""Acquire one child from pinned development failures using an explicitly free router."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REPO = Path('D:/AI/Agent-Society-v2')
sys.path.insert(0, str(REPO / 'src'))
from rsi import genome, improve
from settlement import store
from settlement.common import Command, ResultCode
from settlement.launcher_codex import CodexLauncher, Provider

DSN = 'dbname=rsi_live_20261008 host=127.0.0.1 port=55432 user=postgres'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--model', default='kilo-auto/free', choices=['kilo-auto/free', 'openrouter/openrouter/free'])
parser.add_argument('--operation', default='live08-kilo-acquire-01')
args = parser.parse_args()
OP = args.operation
MODEL = args.model
plan = dict(operation=OP, model=MODEL, proposals_maximum=1, token_ceiling=1000000,
            timeout_ms=300000, request_retries=1, stream_retries=1,
            source='Only pinned development episodes of the existing seed in this study',
            purpose='Acquire an attributable changed genome; no learning advantage presumed',
            routing_limit='The free router can change its underlying model between calls')
path = ROOT / ('acquisition-plan.json' if MODEL == 'kilo-auto/free' else 'direct-acquisition-plan.json')
if path.exists():
    assert json.loads(path.read_text()) == plan
else:
    path.write_text(json.dumps(plan, indent=2) + '\n')
route = dict(l.split('=', 1) for l in Path('D:/AI/tools/model-route.env').read_text().splitlines()
             if l and not l.startswith('#'))
allocation = OP + ':tokens'
result = store.seed_allocation(DSN, Command(request_id=allocation,
    payload=dict(allocation_id=allocation, domain='tokens', authorized=plan['token_ceiling'])))
assert result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED), result
seed = genome.from_dir(Path('D:/AI/tools/rsi-t9-seed'))
agent = CodexLauncher(ROOT / 'runs', codex_cmd=[
    'C:/Users/roysh/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe'],
    provider=Provider(route['SETTLEMENT_GATEWAY_ENDPOINT'], MODEL, route['SETTLEMENT_GATEWAY_KEY'],
                      request_retries=1, stream_retries=1), allowed_overrides=genome.HARNESS_KEYS)
print(json.dumps({'start': OP, 'model': MODEL}), flush=True)
proposal = improve.propose(DSN, agent, seed.digest, operation_id=OP, allocation_id=allocation,
    token_ceiling=plan['token_ceiling'], timeout_ms=plan['timeout_ms'],
    staging_root=ROOT / 'stage', artifacts_root=ROOT / 'art')
status = store.allocation_status(DSN, allocation)
out = dict(proposal=proposal.__dict__, accounting={k: status[k] for k in ['authorized', 'reserved', 'consumed']})
(ROOT / ('acquisition-report.json' if MODEL == 'kilo-auto/free' else 'direct-acquisition-report.json')).write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2), flush=True)
