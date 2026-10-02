# Investigation 01 completion

Integration branch: `codex/implementation-investigation-01-completion`.
Review handoff: `cd7e156` (baseline `44f1f7c`).
Reviewed tip: `a41d4b3`.

## Milestones

M1, integrated lifecycle: `experiments/ad01/agenda_policy.py` holds one
`DecisionConsumer` gating propose, admit, bounded correction, continuation
and stopping for software and graph. `trajectory._run_boundary` delegates
to it. Swapping or disconnecting the consumer changes or refuses both
domain runs (`tests/test_invc1_lifecycle.py`).

M2, one authority: `src/settlement/authority.py` holds authorize, bind,
admit, ledger verify and correction budgets. `authorize_campaign` is the
explicit grant. `ensure_campaign` binds only and refuses unbound stores
with zero writes. Construction subdivides from remaining parent authority.
A rerun on a fresh database refuses (`test_cross_database_no_renewal`).

M3, feedback and recovery: same-target bounded correction carries the
refusal reason into the next prompt (`test_rejected_then_corrected_proposal`).
Receipt-less `dispatching` operations relaunch exactly once on resume;
receipted operations never relaunch (`tests/test_invd1_dispatch.py`).
Kill during validation and kill after validation both resume identical to
control with zero new model calls.

M4, executable interfaces: the executor-owned return envelope is declared
in `method_exec.entry_contract`, rendered verbatim into the construction
prompt, and proven through the real child process for legal methods,
malformed results and query exhaustion (`tests/test_invc1_method_envelope.py`,
`tests/test_invd3_envelope.py`).

M5, trace, export, replay: public runs export decisions, packets,
operations, receipts, identities and byte digests (`records.py`). Offline
replay refuses hidden-future information, mismatches and unsupported
choices. Fresh-process recompute exits 0 on matching totals
(`tests/test_invc3_export.py`).

M6, runnable study: `scripts/inv01_study.py` runs calibration, freeze,
matched I/R worlds, disposition and fresh-process use including empty
repertoire incumbent use. The cap sheet is generated and mechanically
checked against runner settings with a study deadline. Recording pilot:
6 trajectories, 12 retained, 3 rejected, 12 no-candidate; 24 protected
use records plus 6 empty-use records; recompute matches 39 model calls
and 12 construction calls. External requirements expose endpoint, key
and grant as missing by presence only.

## Complete path

```
PYTHONPATH=<root>:<root>/src:<root>/experiments uv run --frozen python \
  scripts/inv01_study.py --dsn 'dbname=<disposable> host=/var/run/postgresql user=ubuntu' \
  --out <dir> --agenda-authorized 100000
PYTHONPATH=<same> uv run --frozen python scripts/inv01_study.py \
  --recompute --out <dir> --recomputed-out <file>
```

## Verification boundaries

Recording doubles sit at the provider seam only. No live inference ran.
Hostile containment is unvalidated. Post-spawn kill claims park for
reconciliation. Cross-store double grants are detectable by fingerprint
but not prevented. The 44f1f7c review probe's allocation section targets
the removed minting API and is superseded by the refusal gate above.

## Final verification

Full suite at the reviewed tip: 828 passed, 0 failed, 592 skipped (pre-existing DSN gates). Two `test_broker_dbos.py` setup errors need `SETTLEMENT_TEST_DSN` in URL form; with it set the file gives 3 passed. Recording pilot at the tip plus fresh-process recompute both exit 0 with matching totals.

## Live qualification request

No grant covers the study in this environment. To run live: provide
`SETTLEMENT_GATEWAY_ENDPOINT`, the key behind `SETTLEMENT_GATEWAY_KEY`,
and a written grant naming the study root, model id, effort level and
the enforced cap sheet in `cap_sheet.json`. Then run the entry above
with a live model label.

## Next research bottlenecks

1. Post-spawn interruption accounting: reconcile launcher-side claims
   after kills that land past spawn.
2. Single pilot-wide study root: per-trajectory roots conserve correctly;
   one root across all six trajectories would bind the aggregate directly.
3. Replay-supported policy comparison: the trace format now exists;
   use it to test whether recorded choice coverage justifies a
   replay-assisted learner study.
