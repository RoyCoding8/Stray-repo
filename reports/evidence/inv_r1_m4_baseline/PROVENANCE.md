# PROVENANCE: `output-run.json` in this directory is not an M4 artifact

Added for B8 / N-411's sibling row, the mis-filed output-shape bundle. **No file
in this directory was moved, renamed, rewritten or deleted to write this notice.**
`output-run.json` stays exactly where it was produced, and this file says what it
is.

## The file

`output-run.json`, 276,249 B, added by `59181d7` (2026-09-26). It is the only
copy of eight raw model responses. Measured: 8 dispatches, 8 distinct
`raw_response` values, 4,792 to 7,422 characters each, and no other file in
`reports/` contains any of them. Do not relocate it and do not regenerate it.

## What it actually is

By its own fields, and by the fields of the run it is filed against:

| | this file | the r4 run it is filed near |
|---|---|---|
| `study` | `invl02-output-shape-550b-r4` | `invl02-output-shape-550b-r4` |
| `run_id` | `f9bd21ad28d847e9bd9853fed0e07853` | `8a7d3ef94f9b457eb4e09bee02e9ba89` |
| `freeze_digest` | `6b709c6365f62f0425e8fde75fed961a6be2c254b16b03ee2cf7bcf8822a67dd` | `ad4188300eaef2a39497d1b821bced8d083435665868e66322dc764f4478e823` |
| `source_identity` | `472ddedc7d29b16895d6db8806f500473351061c63d778de6ba27aef9f430186` | `954ddd7b27b78cdacbffecf666878ff66c2b5cd989f59797ba2adc074c21aab2` |
| operation namespace | `invl02-output-b21c612ec436-*` | `invl02-output-872608eb94c3-*` |
| `status` | `incomplete` | `unavailable` |
| dispatches | 8 | 0 |

`source_identity` is the deciding field. The value `954ddd7b2...` is the one r4's
own `grant-binding.json:bound_study.source_identity` records, so the m4 run is
**not** the run r4's grant authorized. The `code_digests` differ too, on
`scripts/invl02_live.py`, `gateway_http.py` and `boolean_rule.py`.

So the directory name is wrong and the artifact is right about itself. It is an
r4-protocol output-shape bundle, from a run four months of code revisions later
than r4 and one day after r4 was declared closed.

## Why "r4's 8 raw responses" is the wrong description, and it matters

The task row describes this file as r4's eight raw responses. **It is not.** r4
dispatched nothing that produced a response.

`invl02-output-shape-550b-r4/output-run.json` records `status: "unavailable"`,
`dispatch_count: 0`, `dispatches: []`, and the reason:

```
durable broker unavailable before inference: output preflight route does not match the freeze
```

The file is duplicated at `output-run.pre-dispatch-crash.json`, byte for byte,
which is the same finding stated twice.

r4 did spend one dispatch. `store-reconciliation.json` records it, and it is a
lost response with no text:

| field | value |
|---|---|
| operation | `invl02-output-872608eb94c3-P1-audit-0023-a1` |
| `dispatch_state` | `unresolved` |
| receipt | `outcome: "unknown"`, `response_class: "lost-response"` |
| `response_received` | `false` |
| `response_digest` | `null` |
| error | `gateway request timed out` (`error_kind: "timeout"`, `retryable: true`) |
| reservation | `amount: 2294`, `state: "uncertain"`, `settled: false` |
| `reconciled_at` | 2026-09-25T04:34:50+00:00 |

That is the 2294 uncertain units. A lost response has no text to keep, which is
why there is nothing to file under r4 and nothing was ever lost from r4's side.

**The consequence for the eight responses here.** They belong to the
`f9bd21ad` run. Naming them r4's would attach a 18,708-unit spend to a study
whose one dispatch is a timeout. r4's history, its freeze, its single spent
dispatch and its 2294 uncertain units are correct as committed and are not
changed by this notice.

## Why this file was not moved

Three reasons, each measured.

1. **It is the only copy.** Searched every 50-character run of all eight
   responses across `reports/`; nothing else contains any of them. `git log
   --all --diff-filter=D` on the path is empty, so no copy was withdrawn. A move
   is only safe as `git mv`, and even then the directory would be renamed out
   from under 11 documents that cite it.
2. **A move changes a liability calculation.** `_settled_study`
   (`experiments/ad01/s09_exposure_ledger.py:1013`) does
   `for path in sorted(rglob("output-run.json"))` and **returns on the first
   match**. The resolution order today is this file, then r3, then r4. A rename
   that reorders them changes which file answers first, in the module that
   produces the exposure ceiling, and nothing tests that order.
3. **Where it was produced is part of the record.** The M4 lane ran
   `freeze-output → preflight → run-output` to get a baseline bundle to hand to
   `offline_recompute.verify_bundle()`, and wrote it into the directory it was
   working in. `RESOLUTION.md:15` in this same directory says the bundle is the
   output-shape cell's and that `verify_bundle()` routes it to `_verify_output`,
   not `_verify_m4_bundle`. The mis-filing is the finding, and the wrong
   directory is the evidence that the M4 lane made the mistake. Relocating it
   would erase the mistake's only trace while leaving the mistake's consequence
   (M4 measured against the wrong verifier) in place.

## The exposure, which is a separate matter

This run spent 8 dispatches carrying **18,708 units** of recorded exposure, four
at 2294 and four at 2383, all `settled: true`, `unresolved_exposure: 0`,
`charge_units: "unknown"`. `reports/PROJECT-LEDGER.md` now records it.

Three numbers, and they are three different things:

- **2294** is r4's single uncertain reservation, a lost response.
- **18,708** is this run's settled-but-unpriced exposure. It is 4 × 2294 and
  4 × 2383, not 4 × 2294, because a later code revision prices the reservation
  differently. 2294 is not a constant.
- **18,688** is the pre-flight campaign sizing, `4 × 2294 + 4 × 2378`, settled
  at `94443a7` and not held liability. See `reviews/STAGE-09-N36-N65.md`.

## The pointer

A reader looking for r4's dispatch record should read, in this order:

- `../invl02-output-shape-550b-r4/output-run.json` — what the r4 bundle claims
  (nothing dispatched, and why)
- `../invl02-output-shape-550b-r4/store-reconciliation.json` — the one dispatch
  r4 really spent, the lost response, and the 2294
- `output-run.json` (this directory) — a different run, `f9bd21ad`, eight
  responses, filed here by accident
