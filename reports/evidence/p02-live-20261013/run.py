"""One bounded comparison of raw experience and structured lessons on a free route."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import psycopg

from rsi import genome, investigate, memory, task
from settlement import db, store
from settlement.common import Command
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

REPO = Path('D:/AI/Agent-Society-v2')
ROOT = Path('D:/AI/tools/p02-live-20261013')
EVIDENCE = REPO / 'reports/evidence/p02-live-20261013'
DSN = 'host=127.0.0.1 port=55432 dbname=p02_live_20261013 user=postgres'
ADMIN = 'host=127.0.0.1 port=55432 dbname=postgres user=postgres'
ROUTE = Path('D:/AI/tools/rsi-openrouter-route.env')
CODEX = 'C:/Users/roysh/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe'
roots = dict(staging_root=ROOT / 'stage', artifacts_root=ROOT / 'art')


def save(name, value):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, default=str) + '\n', encoding='utf8')


def make_task(name, instruction, empty):
    tests = (b'import unittest\nfrom solution import maximum\n'
             b'class MaximumTests(unittest.TestCase):\n'
             b'    def test_nonempty(self):\n'
             b'        self.assertEqual(maximum([-8,2,5]),5)\n'
             b'        self.assertEqual(maximum([-8,-2,-5]),-2)\n')
    if empty:
        tests += b'    def test_empty(self):\n        self.assertEqual(maximum([]),0)\n'
    return task.Task(name, 'dev', instruction,
                     {'solution.py': b'def maximum(xs):\n    return sorted(xs)[-1]\n'},
                     {'test_maximum.py': tests},
                     {'solution.py': b'def maximum(xs):\n    return max(xs) if xs else 0\n'},
                     ('test_maximum.py',))


def create_and_run(agent, item, identity, view, token_ceiling):
    task.publish(DSN, item, **roots)
    for domain, cap in [('tokens', token_ceiling), ('cpu', 1000)]:
        store.seed_allocation(DSN, Command(payload=dict(
            allocation_id=identity + '-' + domain, domain=domain, authorized=cap)))
    investigate.create(DSN, agent, seed, investigation_id=identity, task=item,
                       token_allocation=identity + '-tokens', cpu_allocation=identity + '-cpu',
                       max_steps=1, timeout_ms=180000, token_ceiling=token_ceiling,
                       memory={'scope': {'domain': 'task'}, 'view': view, 'limit': 5}, **roots)
    result = investigate.run(DSN, agent, LocalLauncher(ROOT / 'verifiers'), identity, **roots)
    exported = investigate.export(DSN, identity)
    save(identity + '.json', exported)
    print(json.dumps({'investigation': identity, 'status': result['status'],
                      'observation': result['last_observation']}), flush=True)
    return exported


if __name__ == '__main__':
    route = dict(line.split('=', 1) for line in ROUTE.read_text().splitlines()
                 if line and not line.startswith('#'))
    if route['SETTLEMENT_GATEWAY_MODEL'] != 'openrouter/openrouter/free':
        raise SystemExit('Only the human-approved free alias is allowed.')
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    save('freeze.json', dict(source=source, driver_sha256=hashlib.sha256(
        Path(__file__).read_bytes()).hexdigest(), model=route['SETTLEMENT_GATEWAY_MODEL'],
        live_worker_actions=2, fixture_worker_actions=2, max_actions_per_investigation=1,
        token_allowance_per_live_worker=500000, total_live_token_authorization=1000000,
        cpu_authorization_per_investigation=1000, timeout_ms_per_worker=180000,
        views=['raw-history', 'structured'], request_retries=0, stream_retries=0,
        origin='authored task/genome/lesson; earlier observations from labeled fixture children',
        ordering='raw-history then structured; sequential evidence, not a matched superiority comparison',
        claim='conditioning probe only; no learned ranking, utility advantage or transfer test'))
    with psycopg.connect(ADMIN, autocommit=True) as conn:
        conn.execute('CREATE DATABASE p02_live_20261013')
    db.apply_migrations(DSN, REPO / 'migrations')
    seed = genome.Genome({'AGENTS.md': (
        b'Work only on the public task. Consult the continuation memory. '
        b'Treat lessons as scoped interpretations and inspect contrary checked evidence. '
        b'Do not seek hidden tests.\n')})
    genome.publish(DSN, seed, parent=None, origin='authored-p02-smoke', **roots)
    fixture = CodexLauncher(ROOT / 'fixture-runs', codex_cmd=[sys.executable,
        str(REPO / 'tests/fixtures/p02_worker.py'), str(ROOT / 'fixture-inputs.jsonl'), 'source'],
        provider=Provider('http://fixture/v1', 'fixture:free', 'fixture'),
        allowed_overrides=genome.HARNESS_KEYS)
    nonempty = create_and_run(fixture, make_task('p02-nonempty',
        'Implement maximum(xs) for nonempty lists and return their largest value.', False),
        'p02-prior-nonempty', 'structured', 5000)
    empty = create_and_run(fixture, make_task('p02-empty',
        'Implement maximum(xs); when the list is empty return 0, otherwise its largest value.', True),
        'p02-prior-empty', 'structured', 5000)
    assert nonempty['state']['last_observation']['passed'] is True
    assert empty['state']['last_observation']['passed'] is False
    support = nonempty['observations'][0]['id']
    opposition = empty['observations'][0]['id']
    memory.revise(DSN, claim_id='maximum-rule', expected_version=0,
        text='sorted(xs)[-1] computes maximum for nonempty lists.', scope={'domain': 'task'},
        status='supported', support=[support], artifacts_root=roots['artifacts_root'])
    lesson = memory.revise(DSN, claim_id='maximum-rule', expected_version=1,
        text='sorted(xs)[-1] works for nonempty lists but fails on empty lists. '
             'The checked empty-input task specifies a zero default.', scope={'domain': 'task'},
        status='challenged', support=[support], opposition=[opposition],
        artifacts_root=roots['artifacts_root'])
    save('lesson.json', lesson)
    live = CodexLauncher(ROOT / 'live-runs', codex_cmd=[CODEX], provider=Provider(
        route['SETTLEMENT_GATEWAY_ENDPOINT'], route['SETTLEMENT_GATEWAY_MODEL'],
        route['SETTLEMENT_GATEWAY_KEY'], catalog_template='gpt-6.1-sol',
        request_retries=0, stream_retries=0), allowed_overrides=genome.HARNESS_KEYS)
    for view in ('raw-history', 'structured'):
        create_and_run(live, make_task('p02-later-' + view,
            'Implement maximum(xs), including the empty-input convention. '
            'Determine that convention from earlier checked maximum experience in memory.', True),
            'p02-live-' + view, view, 500000)
    with db.connect(DSN) as conn:
        save('operations.json', dict(operations=conn.execute(
            'SELECT id,payload_digest,dispatch_state,reconcile_state,settled FROM operations '
            'ORDER BY created_at,id').fetchall(), episodes=conn.execute(
            'SELECT operation_id,status,tokens,trajectory FROM rsi_episodes ORDER BY created_at').fetchall(),
            receipts=conn.execute('SELECT operation_id,receipt_identity,content_digest,outcome,content FROM receipts '
                                  'ORDER BY created_at').fetchall()))
