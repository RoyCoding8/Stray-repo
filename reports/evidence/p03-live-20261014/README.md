# P03 bounded live context comparison

The nine-cell comparison ran once under prospective freeze `543a0956`.
The runtime source was frozen at `13619719`; its application code was independently
accepted by GPT-6.1 Sol High at `0800a14c`. Source hashes bind the cells to the
prospective manifest. Freezing and report commits changed no runtime code.

Each cell used a separate fresh database, the same public maximum task, genome,
and condition-specific corpus. Two labeled fixture workers supplied prior checked
experience. The lesson and all three context policies were authored. The live
task asked the worker to infer the empty-list convention from that experience.
The misleading condition substituted a wrong challenged lesson while preserving
its original opposition. The source-removal condition removed the required
opposition artifact before context construction.

| Policy | Complete evidence | Misleading lesson | Required source removed |
|---|---|---|---|
| `structured/1` | Passed | Failed pristine tests | No dispatch; information needed |
| `raw-history/1` | Stream failure; no grade | Passed | No dispatch; information needed |
| `adaptive/1` | Passed | Worker timeout; no grade | No dispatch; information needed |

Six live worker invocations produced three passes, one failed task and two
unavailable grades. The recomputed quality rate is 3/4 among graded cells,
not 3/6 successful dispatches. The structured misleading worker retained the
initial `sorted(xs)[-1]` implementation, which fails the empty-input test.
Delivering opposition does not guarantee correct model behavior. The raw complete
worker's stream closed without a terminal event. Its usage is unknown. The adaptive
misleading worker timed out with recorded partial usage and no graded solution.
No failed or unavailable cell was retried.

Five worker receipts report 859,547 input-plus-output tokens in total. That is a
known subtotal; the complete token total remains `null`. Cached input and reasoning
output subsets are not added again. All ten target worker/verifier operations have
receipts and are settled; exported unresolved-effect lists are empty. A terminal
launcher failure receipt does not establish provider completion or its invoice.
Per-operation costs remain in the archive, without summing CPU and token units.

The route was `openrouter/openrouter/free`. The underlying provider model was not
pinned. Limits were six worker invocations, one decision per cell, a 180-second
worker timeout, a 500,000-token internal allowance per live worker and zero request
or stream retries. The longest decision step took 192.001 seconds, including
timeout handling and cleanup. These are worker limits, not six HTTP requests or
an independently enforced provider invoice ceiling. Each context used the default
48,000-byte continuation allocation. Construction counts measure bounded logical
inspections over P02-resolved text, not all physical reads or crash-complete CPU.

The passing fixture comparison and independent controls qualify packet selection,
opposition retention, actual instruction binding, adaptive feedback and refusal.
This small live panel qualifies live use and exposes failures. Missing grades,
route variation and the small corpus prevent a context-advantage conclusion.
No learned policy, capability acquisition, transfer, learner improvement,
hostile-code containment or deployment is established.

## Offline reproduction

```powershell
python -I -S reports/evidence/p03-live-20261014/check.py
```

`bundle.zip` contains 88 raw cell records, freezes and content-addressed artifact
packages, compressed from 660,733 bytes. `archive-index.json` checks its exact
membership and bytes. The frozen standard-library checker recomputes `result.json`
without PostgreSQL, gateway access or candidate execution. It checks internal
consistency, not response authenticity or independently metered usage. Literal
credential-value scanning passed before publication.

`run.py` preserves the coordinator. The runtime implementation lives at the
recorded Git revision. The existing freeze and databases must not be reused for
another experiment. Receipt anchors are the nine `p03_live_20261014_*` databases
and `D:/AI/tools/p03-live-20261014`. Reviewer fixture records and small diagnostic
logs remain at `D:/AI/tools/p03`. Existing older live anchors were untouched.
