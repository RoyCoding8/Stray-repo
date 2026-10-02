# M4 offline recomputation harness

Driver: `experiments/ad01/offline_recompute.py`. Gate:
`tests/test_m4_offline_recompute.py` (13 passed). The harness reads a
single bundle file or dict. It opens no gateway, database, network or
environment handle. Its imports are `hashlib`, `json` and `pathlib`
only. A fully scrubbed environment run passes.

## What is recomputed

Quality per use record is 1.0 when the recorded observed output equals
the frozen task expected value, else 0.0. Incumbent-marked records for
unavailable arms carry no acquired quality. Arm means, the comparison
winner, model dispatches, tool queries, history input tokens, failed
attempts and unresolved exposure are all recounted from episodes,
construction records, cost fields and receipts. Runtime verdict labels
are cross-checked and never trusted.

## Measurement boundary

Resource consumption is a runtime attestation named by
`accounting[<class>].source`. The verifier recounts what is countable
and refuses unknown-as-zero billing, but cannot independently measure
tokens, child compute or billed units. Unknown stays unknown. This
limit is declared in `MEASUREMENT_BOUNDARY`.

## Tamper classes and problem names

Identity: `identity-digest-mismatch`, `constructed-policy-not-frozen`.
Content: `quality-mismatch` on altered observed outputs. Membership:
`membership-unknown-task`, `executed-source-not-frozen` for swapped or
disconnected candidates. Costs: `accounting-<class>-mismatch`,
`billed-unknown-scored-as-zero`. Results: `comparison-verdict-mismatch`
on a flipped claimed winner. Forged witnesses without legal operations
fail on `missing-operation`. Each class has a dedicated failing-first
test.

## Quota and availability proofs

`reserve_allowance` returns identical grants for reversed arm order.
Construction beyond init plus repair fails with
`construction-ceiling-exceeded`. A missing candidate produces an
unavailable arm, incumbent-marked records, and an incomplete comparison
with `missing_arms` and no winner. A candidate-executed record under an
unavailable arm fails with `substituted-baseline`.

## Commands

`PYTHONPATH=<worktree> <python> -m pytest
tests/test_m4_offline_recompute.py -q` runs the gate with no database
and no gateway variables. `verify_bundle_file` recomputes a frozen
bundle export from disk.
