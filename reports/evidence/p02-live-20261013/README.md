# P02 live memory probe

Run on 2026-10-14 from source `ae1dca44`. The directory identifier was reserved
on 2026-10-13. `freeze.json` was written before database creation and effects.
The first setup attempt could not connect to the stopped PostgreSQL cluster;
it created no database and dispatched nothing. After the cluster restarted,
the driver ran once to completion.

Two labeled fixture workers established original experience: a nonempty maximum
implementation passed, and the same procedure failed a task specifying zero for
empty input. An authored lesson was first supported, then challenged with the
original failure. These are fixture observations and an authored interpretation,
not model-acquired knowledge.

Two actual Codex workers used the approved `openrouter/openrouter/free` route.
The later public instruction asked them to infer the empty-input convention from
memory without stating the answer. Both implementations passed pristine checks.
The raw-history worker explicitly cited the earlier failed case and returned zero
for empty input. The structured worker received the challenged lesson with its
support and opposition and also returned zero for empty input. The alias is a
free router; no particular underlying model identity is established here.

| Cell | Memory revision | Original observation IDs | Result |
|---|---|---|---|
| Raw history | 4 | 2, 1 | Passed |
| Structured | 5 | 1, 2, 3 | Passed |

The structured cell also saw the preceding live raw-history result. This was a
sequential conditioning probe, not a matched comparison of memory quality.
There is no structured-memory advantage, transfer or autonomous-learning claim.
Behavioral disconnect and wrong-evidence controls belong to the deterministic
integration gates, not to this two-cell live run.

All eight worker/verifier operations settled with eight attributable receipts.
The two live workers reported 341,911 input tokens and 2,347 output tokens in
total. These are recorded usage values, not independently metered provider usage.
Provider billing is not verified. Limits were two live worker actions, one action
per investigation, 180 seconds per worker and 500,000 authorized tokens per live
worker. The token allowance is enforced by internal accounting, not a hard
upstream invoice limit. Request and stream retries were disabled.

The frozen tasks, genome, solution snapshots and trajectories are preserved in
13 packages under `artifacts/`, totaling 70,922 bytes. Package and inner-file
hashes can be checked without the gateway, repository imports or PostgreSQL:

```powershell
python reports/evidence/p02-live-20261013/verify.py
```

That command checks archived bytes, identity links, recorded outcomes and usage
agreement. It does not rerun candidate code, authenticate provider responses or
independently prove their truth. `run.py` preserves the original driver; rerunning
it requires its external local paths and route file and must not reuse the
existing database identity. The live database and private run area are retained
outside Git as receipt anchors. Credentials and gateway configuration are absent
from this bundle.

Execution used native cooperative child processes. These results do not qualify
hostile-code containment or deployment. Subsequent P02 review fixes are qualified
by their own gates; this live evidence remains bound to its original source.

## Subsequent source qualification

GPT-6.1 Sol High independently reviewed repaired source `84385f7b`. The
[component gate](review-gate.log) passed 18 tests without skips. The
[independent counterexamples](review-probes.log) passed four tests; the slow
original-source 257-candidate case was deselected in that final run. Those logs
qualify the repaired source and do not relabel the earlier live evidence.

The coordinator's [broader regression gate](regression-gate.log) on `84385f7b`
passed 120 tests with one Windows symlink-permission skip in 835.20 seconds.
It covers all RSI tests and the real checkpoint migration test on PostgreSQL 18;
it is not a whole-repository or CI result.
