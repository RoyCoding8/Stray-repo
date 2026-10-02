# Inv-Learning-02 M0: failure boundary and implementation contract

Base: `beb4c29` on `wt/m0-baseline`. Live bundle: `evidence_s09_live_opus`
(freeze digest `ba94d81a`). No live spend in this lane. Live store
`s09o_live_01` is dropped; classification below uses surviving export only
and reports limits where the export cannot decide.

## 1. Failing repro (red, preserved)

`PYTHONPATH=. .venv/bin/python scripts/s09_verify.py evidence_s09_live_opus`
exits 1 with `status fail` and exactly 7 problems, all
`missing-receipt for-operation <id>`. Recomputed counts: claimed 36,
construction calls 3, model calls 15, use records 24, witness 89/52,
worst case 100. The verifier counts only settled (`success`/`failure`)
receipts. All 7 operations were exported with one `unknown` receipt each,
so the red is real attribution debt, not verifier strictness.

## 2. Classification of the seven

Lever: `scripts/reconcile_empty_receipts.py`. Supplement:
`reports/evidence/s09-empty-receipts/reconciliation.json` (new file,
original bundle bytes untouched, per-file SHA-256 recorded inside).

| Operation (suffix) | Claimed by | Bucket | Surviving evidence |
|---|---|---|---|
| `dev-gr-01-construct-l1-init` | development dev-gr-1 | unknown response | 1 unknown receipt; disposition rejected, status complete |
| `dev-sw-00-policy-policy-l1-init` | construction P1 | unknown response | 1 unknown receipt; P1 unavailable, left no settled response |
| `dev-sw-00-construct-l1-repair` | assessment P0-w1-software | unknown response | 1 unknown receipt; l1-init settled, repair not |
| `dev-sw-00-construct-l2-init` | assessment P0-w1-software | unknown response | 1 unknown receipt; second lineage init not |
| `dev-gr-00-construct-l1-init` | assessment P0-w1-graph | unknown response | 1 unknown receipt; single attempt |
| `dev-sw-00-construct-l1-init` | assessment P0-w2-software | unknown response | 1 unknown receipt; single attempt |
| `dev-gr-00-construct-l1-init` | assessment P0-w2-graph | unknown response | 1 unknown receipt; single attempt |

Counts: unknown response 7, never-sent preparation 0, observed provider
failure 0, receipt-admission refusal 0, export omission 0. Every cited id
is a construction or policy-construction model-inference operation. All 7
were dispatched (an `unknown` receipt proves a send was attempted and a
gateway outcome was admitted). None is a never-sent preparation, none is
an export omission (all keys present), and none carries a settled failure
receipt. Receipt-admission refusal leaves no export trace, so its 0 means
none observed, not none occurred. The export slim usage carries no error
text, so timeout, empty completion and transport failure cannot be split
further. That split is reported as a limit, not invented.

## 3. Root causes fixed (3, minimal)

R1. Failed decoder erased received usage. Both HTTP decoders checked
response text before parsing usage, so a 200 response with usage and an
empty body returned a bare error. Old contract: text-first, usage lost.
New contract: usage parsed first and attached to the error; a failed
decode preserves measured tokens and charge fields.

R2. Broker dropped error usage on the unknown path. `_send_model`
admitted `{"error": message}` with no usage, so the durable unknown
receipt could not feed accounting tokens or exposure review. Old
contract: unknown receipts carry only an error string. New contract:
unknown receipts carry the gateway error usage object; settlement still
parks the reservation as uncertain and settles nothing.

R3. Study guard ignored captured cost on the error path. `infer`
returned `GatewayError` before inspecting `_s09_costs`, so a nonzero
charge behind a failed call stayed invisible. Old contract: cost checked
on success only. New contract: cost checked on errors too, from both the
captured raw body and the usage object now carried by the error; a
nonzero field records `refusal_reason` as an already-incurred charge and
blocks later dispatches, while the original error is returned unchanged
so the broker still attributes it. A post-response check stops later
calls but cannot prevent the incurred charge.

Deliberately unchanged: the success-path nonzero-cost raise (pinned by
existing guard tests), guard-ceiling refusal flowing through the broker
unknown path (no evidence it touched the 7; ledgered below), and the P2
`KeyError: slice` executor failure (separate subsystem, ledgered below).

## 4. Files changed

- `src/settlement/gateway.py`: `GatewayError` gains optional
  `usage: Usage | None = None`. Backward compatible.
- `src/settlement/gateway_http.py`: both decoders parse usage before the
  text check and attach it to empty-text errors.
- `src/settlement/broker.py`: `_send_model` embeds gateway error usage
  in the admitted unknown receipt.
- `scripts/s09_pilot.py`: guard records incurred cost on errors and
  blocks later dispatches; original error still returned.
- New: `scripts/reconcile_empty_receipts.py`,
  `tests/test_m0_empty_receipts.py` (9 tests),
  `reports/evidence/s09-empty-receipts/reconciliation.json`,
  this report.

## 5. Architecture state map S=(G,I,E,C,A,V,P,B) onto existing records

| Element | Existing type and storage |
|---|---|
| G mission and constraints | `CHARTER`, `CAPS` in `scripts/s09_pilot.py`; `freeze.json` caps, metric and resource rules; `grants` and `allocations` tables |
| I investigations | `investigations` and `attempts` tables; `trajectory` campaigns and boundaries; `s09_policy_state` |
| E observations and attempted effects | `receipts` table all outcomes; `receipt_conflicts`; operation dispatch states; export transitions with receipts, raw responses, costs-unknown; `unknown_exposure` |
| C revisable claims | No dedicated table. Claims live as observations, episode reports and policy refusal records. Gap: projection only, no invalidation owner yet |
| A artifact archive | `capability_releases`; freeze method repertoires; artifact store path; `make_policy_artifact` bytes |
| V versions and private state | Release binding plus `s09_policy_state` policy outputs; attempt `continuation_ref`; operation `execution_version` |
| P unfinished pinned actions | Operations in prepared, dispatching, sent or unresolved; outbox `dispatch:` intents; continuation `unresolved_ops` |
| B authority and exposure | `allocations` and `reservations` (reserved, consumed, uncertain); `trials.record_expenditure`; accounting categories; `unknown_exposure` |

## 6. Trusted dispatcher per effect

| Effect | Owner path |
|---|---|
| model-inference | `broker.dispatch_operation` through the configured gateway adapter (`HttpGatewayAdapter` live, `RecordingGatewayAdapter` controlled, fakes in tests); study runs wrap it in `StudyGatewayGuard` |
| sandbox-exec | Profile launchers (`local-process`) as child processes out of the host; broker owns identity and receipts |
| artifact-io | Artifact store path; broker defers without a store binding |
| observation-adapter | `clock` inline in the broker; `agenda-probe` through its registered launcher |
| domain-command | Broker inline (`note`) |

## 7. Schema changes and restart behavior

No database migration. Receipt `content` is JSONB and already carries
usage objects. Reservation settlement already handles the `unknown`
outcome by marking exposure uncertain. `restart_reconciliation` is a
read-only scan; allocations and reservations persist untouched, and
`test_restart_keeps_consumed_authority` proves consumed and reserved
survive a restart while settled operations stay terminal. Parallel lanes
may start from this contract with no pending migration.

## 8. Executable phase and cap plan, no new live spend

Deterministic, runnable now:

- `PYTHONPATH=. .venv/bin/python scripts/s09_verify.py evidence_s09_live_opus`
- `PYTHONPATH=. .venv/bin/python scripts/reconcile_empty_receipts.py evidence_s09_live_opus reports/evidence/s09-empty-receipts/reconciliation.json`
- `SETTLEMENT_TEST_DSN='dbname=invl02_m0 host=/var/run/postgresql user=ubuntu' .venv/bin/python -m pytest tests/test_m0_empty_receipts.py -q`

Live E0 preflight, blocked until the surviving grant and model scope are
re-verified (19 historical dispatches against a ceiling of 100 prove
nothing about remaining authority):

- `PYTHONPATH=. .venv/bin/python scripts/s09_pilot.py run --dsn <disposable-dsn> --out <dir> --mode live --model <verified-model>`

Frozen caps for that run: study model calls 100, construction ceiling 4,
per-episode model calls 6, policy steps 6, diagnostic queries 16. Status:
blocked on authority verification. No live call was made in this lane.

## 9. Gates

| Gate | Result |
|---|---|
| `s09_verify.py` on live bundle | exit 1, 7 missing-receipt, counts 36/3/15/24/89/52/100 |
| `test_m0_empty_receipts.py` | 9 passed |
| broker dispatch, prepare, review, adversarial | 51 + 19 passed |
| gateway unit and engine suites | all passed |
| guard prelive suite | all passed |
| decoder charge and protocol subset | 5 passed |
| `test_s09m5_pilot.py` | 3 passed, 5 collection errors from missing third-party `fault_tasks` package in this worktree venv (`experiments/doubles.py:12`, file untouched by this lane; pre-existing environment gap, not a code regression) |

## 10. Remaining gaps

- Unknown billing on the error path without captured cost relies on
  reservation uncertainty, not the guard. No silent zero is written.
- Guard-ceiling refusal converts to a broker unknown receipt, which
  conflates never-sent with sent-but-lost. Untouched for lack of live
  evidence; needs a refused-before-send marker.
- P2 init text decoded but failed validation with an executor
  `KeyError`, then the arm starved on the call cap. Executor defect and
  schedule fragility belong to later lanes.
- Claim invalidation (C) has no owner; claims are projections of
  observations and episode reports.
