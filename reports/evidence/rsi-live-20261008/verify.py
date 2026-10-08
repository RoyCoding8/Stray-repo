"""Check archived byte identities and recorded outcomes. No DB, model calls or candidate execution."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2] / 'src'))
from rsi import genome

def read(name):
    return json.loads((ROOT / name).read_text())

manifest = read('manifest.json')
for name, spec in manifest.items():
    raw = (ROOT / name).read_bytes()
    assert len(raw) == spec['bytes'] and hashlib.sha256(raw).hexdigest() == spec['sha256'], name
outcomes, records, receipts = read('outcomes.json'), read('store.json'), read('receipts.json')
proposal = outcomes['direct-acquisition-report']['proposal']
child_id = proposal['child']
retained = read('retained-genomes.json')
objects = {digest: genome.Genome({p: bytes.fromhex(raw) for p, raw in row['files'].items()}, row['harness'])
           for digest, row in retained.items()}
assert all(g.digest == digest for digest, g in objects.items())
assert child_id != proposal['parent'] and proposal['status'] == 'completed'
assert read('construction-files.json') == retained[child_id]['files']
expected_view = {p: raw.hex() for p, raw in genome.workspace_view(objects[child_id]).items()}
for op, files in read('child-staged-files.json').items():
    assert files == expected_view, op
for op in ['live08-direct-acquire-01', 'live08-direct-tool-smoke',
           'live08-direct-child-grade-school', 'live08-direct-child-smoke']:
    raw = gzip.decompress((ROOT / (op + '.jsonl.gz')).read_bytes())
    result = read(op + '-result.json')
    digest = hashlib.sha256(raw).hexdigest()
    assert result['trajectory_digest'] == digest
    assert any(r['content'].get('response_digest') == digest and r['content'].get('operation_id') == op
               for r in receipts[op]), op
for key in ['tool-smoke-report', 'child-smoke-use-report']:
    outcome = outcomes[key]
    assert outcome['status'] == 'completed' and outcome['verifier']['passed'] is True
    verdict = next(v for v in records['rsi_verdicts'] if v['episode'] == outcome['operation'])
    assert verdict['passed'] is True and verdict['status'] == 'passed'
    assert receipts[verdict['operation_id']]
assert outcomes['child-smoke-use-report']['genome'] == child_id
assert outcomes['child-use-report']['status'] == 'timeout'
assert not records['rsi_anchor_uses']
assert all(op['dispatch_state'] == 'observed' and receipts[op['id']] for op in records['operations'])
print(json.dumps(dict(check='pass', live_operations=len(records['operations']),
    acquired_child=child_id, authored_smoke_passes=2, anchor_exposures=0,
    learning_advantage='unproved', limitation='Checks recorded results and bytes, not provider attestation'), indent=2))
