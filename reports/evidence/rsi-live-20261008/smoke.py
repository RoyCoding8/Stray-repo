"""A live tool-route smoke check, not task-bank utility or learning evidence."""
import json
from pathlib import Path
from run import DSN, ROOT, ROOTS, CODEX
from rsi import episode, genome, task, verifier
from settlement import store
from settlement.common import Command, ResultCode
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

op = 'live08-direct-tool-smoke'
plan = dict(operation=op, model='openrouter/openrouter/free', episodes_maximum=1,
            token_ceiling=1000000, timeout_ms=180000, request_retries=1, stream_retries=1,
            interpretation='Authored tiny smoke task, never a held-out learning or Exercism result')
path = ROOT / 'tool-smoke-plan.json'
if path.exists():
    assert json.loads(path.read_text()) == plan
else:
    path.write_text(json.dumps(plan, indent=2) + '\n')
subject = task.Task('live-tool-smoke-add', 'dev',
    'This is a tiny tool-route check. The workspace already contains calc.py. '
    'Read it, replace its stub with def add(a, b) returning the integer sum a + b, '
    'then finish immediately. You may write it with PowerShell Set-Content; '
    'do not search for tests, Git, skills or files outside this workspace. '
    'The kernel separately verifies the result. Do not add tests or other files.',
    {'calc.py': b'def add(a, b):\n    pass\n'},
    {'calc_test.py': b'import unittest\nfrom calc import add\nclass AddTest(unittest.TestCase):\n'
                     b'    def test_examples(self):\n        self.assertEqual(add(2, 3), 5)\n'
                     b'        self.assertEqual(add(-7, 2), -5)\n        self.assertEqual(add(0, 0), 0)\n'},
    {'calc.py': b'def add(a, b):\n    return a + b\n'}, ('calc_test.py',))
task.publish(DSN, subject, **ROOTS)
seed = genome.from_dir(Path('D:/AI/tools/rsi-t9-seed'))
route = dict(l.split('=', 1) for l in Path('D:/AI/tools/model-route.env').read_text().splitlines()
             if l and not l.startswith('#'))
for domain, amount in [('tokens', plan['token_ceiling']), ('cpu', 120)]:
    result = store.seed_allocation(DSN, Command(request_id=op + ':' + domain,
        payload=dict(allocation_id=op + ':' + domain, domain=domain, authorized=amount)))
    assert result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
agent = CodexLauncher(ROOT / 'runs', codex_cmd=[CODEX],
    provider=Provider(route['SETTLEMENT_GATEWAY_ENDPOINT'], plan['model'], route['SETTLEMENT_GATEWAY_KEY'],
                      request_retries=1, stream_retries=1), allowed_overrides=genome.HARNESS_KEYS)
print(json.dumps({'start': op}), flush=True)
ep = episode.run_episode(DSN, agent, seed, operation_id=op, task=subject,
    allocation_id=op + ':tokens', attempt_id=None, token_ceiling=plan['token_ceiling'],
    timeout_ms=plan['timeout_ms'], **ROOTS)
out = dict(operation=op, task=subject.digest, status=ep.status, tokens=ep.tokens, seconds=ep.seconds,
           trajectory=ep.trajectory, interpretation=plan['interpretation'])
if ep.status == 'completed':
    checked = verifier.verify_episode(DSN, agent, LocalLauncher(ROOT / 'verifiers'), op,
        allocation_id=op + ':cpu', attempt_id=None, **ROOTS)
    out['verifier'] = dict(operation=checked.operation_id, passed=checked.passed, status=checked.status)
(ROOT / 'tool-smoke-report.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2), flush=True)
