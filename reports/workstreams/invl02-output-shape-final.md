# Output-shape final preflight

**Status.** Unavailable before inference.

The final integrity tip was `9e6c922`. The independent review passed after the durable dispatch-root, E3 dependency, M4 receipt, gateway endpoint, and mandatory child-receipt fixes merged.

## Route preflight

The authorized command performed `GET /models` only:

```bash
set -a
. /home/ubuntu/.config/agent-society-live.env
set +a
export PYTHONPATH=.:src:experiments
uv run python scripts/invl02_live.py preflight \
  --out reports/evidence/invl02-output-shape-final
```

The first shell attempt used `python`, which was not installed. It made no request. The corrected `uv run python` attempt reached the route preflight and failed closed with:

```text
model list does not contain the exact route
```

The expected route was:

- Endpoint: `http://localhost:4000/v1`
- Requested model: `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`
- Resolved model: `nvidia/nemotron-3-ultra-550b-a55b:free`
- Provider: `nvidia`
- Tier: `free`

The preflight wrote no `preflight.json` because it failed before serialization. The sanitized failure record is `reports/evidence/invl02-output-shape-final/preflight-failure.json`.

## Effect boundary

- Model dispatches: `0`
- Repairs: `0`
- E1 or E2 execution: not started
- E3 execution: not started
- Candidate bytes: none
- Receipts: none
- Scorer-private artifact: none
- Live route inference: none

The P1/P2 output-shaping study remains unrun. The route-specific unavailability is not a model-capability result and not a learning null. The next decision requires restoring exact route discovery or recording a new authorization and protocol before any further live attempt. No retry of this frozen study directory is permitted.
