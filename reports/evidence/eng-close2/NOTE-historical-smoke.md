# NOTE: historical eng-solv smoke is earlier-lane-state evidence

This note annotates `reports/evidence/eng-solv/smoke_result.json` and
`reports/workstreams/eng-solv.md`. Those files are preserved byte for
byte; nothing here rewrites them.

## Status

The historical smoke is evidence from the earlier eng-solv lane state,
not confirmation of the integrated accounting correction. Its recorded
provenance is base revision `f478143c520977da179cef3da309824a996a42cb`
plus a dirty-path list (`M src/settlement/development.py`,
`M src/settlement/experiment.py`, untracked evidence and contract-test
paths) — a base plus dirty list, not a recoverable exact source
snapshot. The missing bytes are not retrospectively certified here.

## The recorded discrepancy, as observed

- model reservation: 8,344 units (reservation, later released)
- grade reservation/settlement: 111 units
- sum of reported per-operation settlement: 111 units
- recorded allocation consumed increase: 8,455 units (== 8344 + 111)

The per-operation record for the model operation reads reserved 8344,
settled 0, unresolved 0, while allocation consumed rose by the full
reserved amount. That shape does not satisfy the integrated invariant
(settled + unresolved == reserved per operation; consumed delta ==
settled sum over unique operations). The earlier lane state debited
the released model reservation to consumed without a settled charge.

## How it reads under the integrated accounting

Under the integrated `_op_accounting` semantics on the repaired tree
(conservative settlement: an unbilled terminal success settles its
full reserved amount; a released reservation debits nothing from
consumed), the recorded run is expected to reread as two unique
operations whose settled amounts sum exactly to the allocation
consumed delta, with per-operation reservation rows attached. The
CLOSE-2 recorded smoke (`reports/evidence/eng-close2/`) performs that
reread on a clean recorded revision; its `reconciliation.json`
carries the verdict. A mismatch there is a finding, not a reason to
edit the historical artifact.
