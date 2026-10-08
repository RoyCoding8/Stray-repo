"""Two prospectively bounded text probes, separate from task/learning evidence."""
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
models = ['kilo/cohere/north-mini-code:free', 'nvidia/nemotron-3-super-120b-a12b:free']
plan = {'models': models, 'calls_maximum': 2, 'max_output_tokens': 2048, 'timeout_seconds': 45,
        'purpose': 'Inspect free-route HTTP failures and response pricing, not task or learning evidence'}
path = ROOT / 'transport-plan.json'
if path.exists():
    assert json.loads(path.read_text()) == plan
else:
    path.write_text(json.dumps(plan, indent=2) + '\n')
route = dict(l.split('=', 1) for l in Path('D:/AI/tools/model-route.env').read_text().splitlines()
             if l and not l.startswith('#'))
for index, model in enumerate(models):
    out = ROOT / f'transport-{index}.json'
    assert not out.exists(), 'Do not redispatch a recorded probe'
    request = dict(model=model, input='Reply with exactly READY.', max_output_tokens=2048, stream=False)
    raw = json.dumps(request).encode()
    record = {'model': model, 'request_digest': hashlib.sha256(raw).hexdigest(),
              'dispatched': True, 'outcome': 'unknown', 'usage': None}
    out.write_text(json.dumps(record, indent=2) + '\n')
    started = time.monotonic()
    q = urllib.request.Request(route['SETTLEMENT_GATEWAY_ENDPOINT'] + '/responses', data=raw,
        headers={'Authorization': 'Bearer ' + route['SETTLEMENT_GATEWAY_KEY'], 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(q, timeout=45) as response:
            record['http_status'] = response.status
            body = response.read(200000)
        record['response'] = json.loads(body)
        record['usage'] = record['response'].get('usage')
        record['outcome'] = 'response_received'
    except urllib.error.HTTPError as exc:
        body = exc.read(10000)
        record.update(http_status=exc.code, outcome='http_error', error=body.decode('utf-8', 'replace'))
    except Exception as exc:
        record['error'] = str(exc)
    record['seconds'] = round(time.monotonic() - started, 1)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record), flush=True)
