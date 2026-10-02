# Live study evidence (Investigation 01 study readiness)

Full live study on `nvidia/nemotron-3-ultra-550b-a55b:free` at high
effort, study-root `inv01-live`, grant 600000, deadline 3600s.
Study rc 0, recompute rc 0. Contents: 6 campaign exports, 6 frozen
repertoires, `study.json`, `accounting.json`, `cap_sheet.json`,
`freeze.json`, `manifest.json`, 24 `use_records.json` entries.

Transform note: the only redaction from the raw runner output is the
local gateway endpoint string, replaced with
`LOCAL-GATEWAY-REDACTED` (36 occurrences across the 6 exports). All
other bytes, including model ids, token counts, digests, verdicts and
method sources, are byte-identical to the verified run. No keys were
ever written here.

## What the system learned and retained

Nothing retainable. All 6 repertoires hold zero members, and all 24
use records selected the incumbent with `no eligible repertoire
member` fallbacks (12 software, 12 graph). Totals: 43 model calls, 10
construction calls, 548 witness queries, 0 charge units.

Per trajectory (model calls / construction calls): w0-I 10/4, w0-R
5/1, w1-I 13/4, w1-R 5/1, w2-I 6/0, w2-R 4/0. Construction attempted
on 4 of 6 trajectories but no candidate passed the check gate, so no
lineage was retained. Observation verdicts across 28 transitions: seed
preserved while the novel candidate was not in 10 cases, mutual
not-preserved in 6,exact ties in the remaining 12. The I arms explored harder
than the R arms and still retained nothing, which bounds the live
model's transfer on this panel to diagnosis without acquisition.
