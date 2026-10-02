# EC02 G2 live acquisition — no-acquisition fallback report

Prescribed fallback per design §11/G2: construction exhausted its
finite attempts with no usable candidate; freeze none selected.

## Count reconciliation (reviewer ECR2-04 question)

24 ledger-admitted construction attempts across 6 rounds (each
round: 2 lineages x init+repair, ACCOUNTING calls_used=4 in all
six round logs in `/tmp/ec02-live/`). Explained calls: 20 = 4
(round 1, full per-call detail in `g2-acquire-summary.json`) + 0
(round 3, broker-refused pre-dispatch on operation-id reuse —
zero provider sends, no receipts can exist) + 12 (rounds 4–6, all
empty/timeout; round 6 receipted in `ec02test_live`). The
remaining 4 are round 2: ledger-admitted (ACCOUNTING calls_used=4
in `acquire-l2.log`) but provider-side receipt rows lost in the
TRUNCATE incident; per-call outcomes survive as summary lines
(all empty-response, zero usage). Nothing was double-counted:
each round used a fresh in-memory ledger, and rounds 3+ used
fresh operation-id prefixes (rounds 1–2 shared the unprefixed
stem; the surviving DB holds no unprefixed construction rows,
confirming round 2's rows were lost rather than duplicated).

Surviving machine records: `ec02test_live` holds 16 receipt rows
(4 construction + 12 acquisition-episode receipts, exported to
scratch `live-db-export.json` in `/tmp/ec02-live/` pending commit
under `evidence-live/`); round-1 full per-call detail
(`g2-acquire-summary.json`, usage in=6566 out=9622, all
billed=false); all six round stdout logs with per-call
usable/reason/parse/usage lines.

## Spend (all receipted, all provider-reported unbilled)

24 live construction calls in 6 rounds (2 lineages x init+repair,
per-round unique operation prefix), 2 dev acquisition tasks per
round, isolated evidence DB. 0 usable `entry` payloads.

- Rounds 1–2: 8 calls; 1 text-bearing reply (a `probe` action, no
  `entry` field — the prompt never asked for one), 3 timeouts,
  4 empties. Receipt rows lost to a test-fixture TRUNCATE of the
  shared DB (coordinator procedural error, see below); round
  summaries survive in scratch logs with operation ids and usage.
- Round 3: aborted pre-dispatch (broker refused payload-changed
  operation-id reuse — fixed: per-campaign attempt prefix).
- Rounds 4–6: 12 calls; all timeouts/empties.

Provider discrimination (direct probes, receipted where applicable):
trivial prose prompts answer in ~3s; ANY JSON-object prompt —
including `{"a":{"b":{"c":"deep"}}}` — returns no text in ~3–7s;
the 2.4KB construction prompt times out at every deadline up to
600s. The provider answers small prose but never completes a
construction-scale generation on this endpoint.

## Root causes fixed (doubled-gated, committed)

1. `construction_request` never specified the `entry` response
   contract the parser demands → added `required_response` +
   `response_example` (the 1 text reply proved the gap).
2. `acquire()` reused the fixed `coord02-L-construct` operation
   prefix per call → broker refused round 3 → per-campaign prefix
   (new `attempt_prefix` param, campaign uuid default).
3. Ledger sent raw canonical JSON as the message → provider
   no-text on JSON shapes → `render_construction_prompt` renders
   labeled plain prose; canonical digest stays on the call record
   for identity.

Gate: `tests/test_coord02_learning.py` 10 passed (incl. new
`test_construction_prompt_plain_text_with_response_contract`).

## Procedural incident

Doubled gate runs of `test_coord02_learning.py` TRUNCATE
`ec02test_l` per its fixture — the same DB the live rounds used.
Rounds 1–4 live receipt rows were wiped; round summaries survive
in scratch logs. Remaining live work moved to isolated
`ec02test_live` (migrated, never used by any test fixture).
Rule learned: live-evidence DBs must never equal a test default.

## Disposition

- G2 acquisition: FAILED (provider-side) → no-acquisition
  fallback. No authored bytes inserted into any live arm.
- G3 frozen panels: BLOCKED on G2 (no package to freeze; running
  144 episodes with a known-empty arm would spend the grant for
  zero information).
- Episode grant untouched (0/204). Construction spend: 24 calls,
  0 billed units.
