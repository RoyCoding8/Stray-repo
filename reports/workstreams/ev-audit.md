# EV-AUDIT: did any lane in this batch touch `reports/evidence/`?

Lane EV-AUDIT. Read-only audit of the 62-lane consolidation batch.
Branch `wt/ev-audit`, audited at `6d7558c062b0da2540bca6d61a59760934621322`.

## Verdict

**No pre-existing evidence was modified.** Every one of the 390 evidence files that
existed at the batch base is byte-identical at the tip. Zero content changes, zero
deletions, zero mode changes. The batch added 10 new files to
`reports/evidence/`, every one added by exactly one commit and never touched again.

The premise of the audit brief was wrong in one respect, and it matters. Five of the
seven paths the brief listed as "known-immutable archived directories" **did not exist
at the batch base**. They were created by this batch. They are not archived artifacts
this batch edited. Details in "Correction to the brief's premise" below.

## Base-commit derivation

Base is **`915b029f8c52214f2bddf84a4c682c3154d807a1`**,
"Record the claim-ledger ownership defect in the lane table", authored
2026-10-01 01:46:44 -0400.

Derived by walking the first-parent chain of `codex/stage09-consolidation-2026-10-01`
oldest to newest (136 commits) and finding where the batch's merges begin. The
chain reaches index 85 with `f03db5b` ("Add milestone inventory and lane
decompositions for the connected build", 00:16:18), then four plain commits that
prepare the batch (86-89), and at index 90 the first lane merge
`5d8bb4e` ("Merge lane B8", 01:57:41). The commit immediately before that run is
`915b029`, so `915b029` is the base.

Three independent checks confirm it.

1. `git rev-parse 5d8bb4e^1` returns `915b029f8c52214f2bddf84a4c682c3154d807a1`.
   The first lane merge's own first parent is the base.
2. `git merge-base --is-ancestor 915b029 6d7558c` exits 0.
3. `915b029` appears in the first-parent chain of the tip at position 46 from
   the tip.

One earlier derivation attempt is recorded because it was wrong. Scanning backward
from the tip for a contiguous run of `Merge lane *` subjects yields only three
merges (`17a4ff9`, `6afd724`, `6d7558c`) and a "base" of `e442a02`. That is
wrong because the batch interleaved its lane merges with commits whose subjects do
not match the pattern (`Merge delivery`, `Merge final acceptance`,
`Merge independent review`, `Merge search pass`, and several direct commits such as
`Revert lane B13` and `Close the documentary defects the acceptance pass found`).
A subject-prefix rule cannot see the real boundary.

Commit composition of `915b029..6d7558c`: 94 commits total, of which 35 are
`Merge lane *`, 2 are `Merge search pass`, 3 are delivery/acceptance/review merges,
1 is a revert, and 53 are direct commits (lane work merged non-fast-forward plus
reconciliation commits on the branch itself).

## Headline evidence: `reports/evidence/` is not modified

```
$ git diff --stat 915b029..6d7558c -- reports/evidence/
 reports/evidence/invr1b11-budget/budget-probe.json |  725 ++++++++++++
 reports/evidence/invr1b11-budget/store-rows.json   |  520 ++++++++
 reports/evidence/invr1b12-swe/campaign.json        |  791 +++++++++++++
 reports/evidence/invr1b12-swe/construction.json    |  693 +++++++++++
 reports/evidence/invr1b12-swe/store-rows.json      |  420 +++++++
 reports/evidence/invr1b12-swe/use.json             |   42 +
 reports/evidence/invr1b14-retention/retention.json | 1249 ++++++++++++++++++++
 .../evidence/invr1b17-budgetfit/budget-fit.json    |  420 +++++++
 .../evidence/invr1b17-budgetfit/store-rows.json    |  351 ++++++
 .../evidence/invr1b8-panel-census/census.json      |  475 ++++++++
 10 files changed, 5686 insertions(+)
```

Every one of those 10 lines is a pure addition. There is no deletion line and no
modification line anywhere in the diff.

```
$ git log --format=%h %s 915b029..6d7558c -- reports/evidence/
78e1808 Merge lane B17: the budget was not the reason, and 7000 was never the cap
1a56662 B14: a new freeze, and the retention leg is closed behind it
30b9eac B17: the budget was not the reason, and 7000 was never the cap
9cfe7aa B12: the SWE matrix constructed live, and 2048 tokens is the binding constraint
bb62fe5 Measure the served output budget, and find 2048 serves
005a4f7 B8: census which panel can carry the E2 contrast, and report the panel that can
```

Per-commit `--name-status` confirms all 10 entries carry status `A` and nothing else.

### Stronger check than the diff

A pathspec diff proves what git recorded between two commits. The decisive check
compares blob identity for every tracked file under `reports/evidence/` at both
commits, via `git ls-tree -r`.

| Measure | At base `915b029` | At tip `6d7558c` |
|---|---|---|
| Files under `reports/evidence/` | 390 | 400 |
| Pre-existing files whose blob SHA changed | — | **0** |
| Pre-existing files deleted | — | **0** |
| Pre-existing files with a changed mode | — | **0** |
| New files | — | 10 |

All 390 pre-existing files are byte-identical at both commits. This holds for the
hardcoded archived generators too. `reports/evidence/inv_r1_e2_offline/make_evidence.py`
is blob `9fa3ca1c9b427f670d725b8079f9dcc921194639` at both base and tip. Its last
touching commit is `d17b5a7` (2026-09-30), before the batch.
`reports/evidence/inv_r1_e4/make_evidence.py` is blob
`d20ae3d23b0d66c79358563332578629d43e14c0` at both commits, last touched by
`c4ed09b` (2026-09-30), also before the batch.

The deliberately hardcoded `seed-%s-%s` identifier in
`inv_r1_e2_offline/make_evidence.py` is still present at line 242, unchanged:

```python
capability_id = "seed-%s-%s" % (prefix, method)
```

That is recorded as immutable, and it is still immutable.

## Correction to the brief's premise

The brief listed seven paths as "known-immutable archived directories to check
individually". Existence at the batch base, checked per path with
`git cat-file -e <base>:<path>`:

| Path | At base | At tip |
|---|---|---|
| `reports/evidence/invr1b8-panel-census/census.json` | **absent** | present |
| `reports/evidence/invr1b11-budget/` | **absent** | present |
| `reports/evidence/invr1b12-swe/` | **absent** | present |
| `reports/evidence/invr1b14-retention/retention.json` | **absent** | present |
| `reports/evidence/invr1b17-budgetfit/` | **absent** | present |
| `reports/evidence/inv_r1_e2_offline/make_evidence.py` | present | present (identical blob) |
| `reports/evidence/inv_r1_e4/make_evidence.py` | present | present (identical blob) |

The first five did not exist when the batch began. They were created inside the
batch, so they cannot be "amendments to someone else's archived artifact" by
construction. The immutability rule does bind them going forward: they are now
archived evidence, and a future lane must not edit them.

The brief also flags that `invr1b14-retention/retention.json` records `"billed": null`.
Confirmed at the tip: line 3 is `"billed": null`, and it is the only line in the
file matching `/billed/`. Consistent with `b-live-cap.md` line 181, which states
that `billed` and `charge_units` are null on every receipt from this route.

## Every new file, with its lane and a judgement

Ten new files. Each was added by exactly one commit, and no later commit in the
batch modified it. Judge each as a new artifact for its own experiment, not an
amendment to another lane's.

| File | Added by | Lane | Judgement |
|---|---|---|---|
| `invr1b8-panel-census/census.json` | `005a4f7` 01:57:13 | B8 | New artifact. Lane B8's own panel census. |
| `invr1b11-budget/budget-probe.json` | `bb62fe5` 04:28:09 | B11 | New artifact. The served output budget ladder probe. |
| `invr1b11-budget/store-rows.json` | `bb62fe5` 04:28:09 | B11 | New artifact. Store rows of the same B11 run. |
| `invr1b12-swe/campaign.json` | `9cfe7aa` 05:36:29 | B12 | New artifact. The SWE campaign result. |
| `invr1b12-swe/construction.json` | `9cfe7aa` 05:36:29 | B12 | New artifact. Construction phase of the same B12 run. |
| `invr1b12-swe/store-rows.json` | `9cfe7aa` 05:36:29 | B12 | New artifact. Store rows of the same B12 run. |
| `invr1b12-swe/use.json` | `9cfe7aa` 05:36:29 | B12 | New artifact. Use phase of the same B12 run. |
| `invr1b14-retention/retention.json` | `1a56662` 06:29:07 | B14 | New artifact. The retention leg closed behind a zero ceiling. |
| `invr1b17-budgetfit/budget-fit.json` | `30b9eac` 06:18:46 | B17 | New artifact. The budget-fit result. |
| `invr1b17-budgetfit/store-rows.json` | `30b9eac` 06:18:46 | B17 | New artifact. Store rows of the same B17 run. |

Note on `invr1b11-budget`. The brief's directory list implies it was archived
pre-batch. It was not. Its adding commit `bb62fe5` carries the subject
"Measure the served output budget, and find 2048 serves" and is reached through
the B11 merge `e7d0e3f`. The lane that produced it is B11 even though the commit
subject does not name the lane, which is why the attribution came from the file
path and the merge rather than the subject line.

Amend detection, per file, over the whole batch: each of the 10 files shows
exactly one blob-touching commit. No file was added and then rewritten inside the
batch. There is no candidate for a silent amendment.

## `reports/cap-sheets/`

Three commits touched this tree, and the whole diff is 596 insertions across
2 files with 0 deletions:

```
$ git log --format='%h %ad %s' --date=short 915b029..6d7558c -- reports/cap-sheets/
15335bd 2026-10-01 Close the documentary defects the acceptance pass found
1a56662 2026-10-01 B14: a new freeze, and the retention leg is closed behind it
e25b25c 2026-10-01 Write the B cap sheet from the complete matrix, before any effect

$ git log --format='COMMIT %h' --name-status 915b029..6d7558c -- reports/cap-sheets/
COMMIT 15335bd    M  reports/cap-sheets/b-live-cap.md
COMMIT 1a56662    A  reports/cap-sheets/b14-retention-freeze.md
COMMIT e25b25c    A  reports/cap-sheets/b-live-cap.md
```

Two of the three are additions of new sheets. Neither sheet existed at the base,
so neither has a pre-batch spend to reduce.

`b-live-cap.md` is the one file edited after creation, by `15335bd`. The entire
diff is a five-line prose replacement. No table cell, no number, no total changes:

```diff
-The three `graph` rows are the only powered panels; the ten `software` rows are the
-unpowered remainder, and the four unpowered graph panels are omitted from this table
-because this sheet allocates nothing to them. `powered_but_blind` is empty, because
-every panel that reaches six clusters also has a non-zero ceiling. A powered-but-blind
+**Three** panels are powered, and all three are the `graph` rows above.
+`graph:dev+transfer` is the smallest of the three, not the only one. The seven
+`software` rows are unpowered, and the four unpowered graph panels are omitted
+from this table because this sheet allocates nothing to them.
+`powered_but_blind` is empty, because every panel that reaches six clusters
+also has a non-zero ceiling. A powered-but-blind
```

The edit corrects a prose overstatement ("the only powered panels", "ten
`software` rows") and adds the word **Three**. It changes the claim about how many
panels are powered from one to three, in the direction of describing the table
below it more accurately. It does not touch an allocation.

### Spend-reduction and zero-movement flags: none

The brief asked me to flag any edit that reduces a recorded spend or moves a
recorded zero to a nonzero value. I checked each recorded field directly at the tip.

`b-live-cap.md` at tip records `total_dispatch_cap: 75` (line 139),
`total_retry_allowance: 3` (140), `total_physical_send_ceiling: 78` (141),
`per_request_units: 2492` (143), `total_units: 194376` (146), and
`carried_in_uncertain_units: 5563` (147). The brief's figures of 75 dispatches,
78 physical sends and 194376 units all match. Line 131 is the table total row
`| **total** | **75** | **3** | **78** | |`.

`b14-retention-freeze.md` at tip records `total_dispatch_cap: 0` (line 32),
`total_physical_send_ceiling: 0` (34), `total_units: 0` (39), `dispatches_used: 0`
(49), `per_request_units: 2492` (206). The zero stayed zero.

The B14 and B15 legs are excluded from the B total and say so at
`b-live-cap.md` line 156: "`B14` and `B15` are **not allocated and not in this
total.**"

No spend was reduced. No recorded zero was moved to nonzero. No cap was lowered,
raised, or removed. The single edit to an existing cap sheet is prose only.

## Credential scan

Scanned all 39663 added lines of `git diff 915b029..6d7558c`, across 151 changed
files. Nine pattern families, in two passes.

Anchored pass, requiring the pattern at a token boundary so that a substring
inside a longer word cannot match:

| Pattern | Hits |
|---|---|
| `sk-` key at token boundary (16+ chars) | 0 |
| `nvapi-` key | 0 |
| `github token` (`ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_`) | 0 |
| AWS access key id (`AKIA` + 16) | 0 |
| PEM private key block | 0 |
| JWT | 0 |
| `Bearer` + 12+ chars | 0 |

Unanchored pass produced two hit classes, both of which I then triaged and both of
which are false positives.

**The 16 `sk-` substring hits are all the word "task-".** The first pass's regex had
no left boundary, so it matched inside `task-id`, `task-scope`,
`poor-task-graph`, and similar. The anchored pass finds zero.

**The 94 long literals are all lowercase-hex digests.** Every one matched
`^[0-9a-f]+$`, 59 distinct values across 14 files, concentrated in the new
evidence JSON (which records content digests) and in 5 test files that assert on
digests. Not one contains a character outside `[0-9a-f]`, which rules out base64
and rules out any key with mixed-case or punctuation.

**The single `api_key=` hit is a variable read, not a key.** It is in
`scripts/invl02_live.py` at line 4231:

```python
api_key=settings.gateway.api_key_env and __import__(
    "os").environ.get(settings.gateway.api_key_env, ""),
```

The "value" my first regex captured was the expression
`settings.gateway.api_key_env`, 28 characters starting `sett`. It is a lookup of
an environment-variable name from config, then an `os.environ.get`. No literal.

### The local route key is pre-existing, and this batch did not add it

The route key in use is a short local development key for the gateway at
`http://127.0.0.1:4000/v1`. A literal form of that key does appear in the tree at
the tip, in 5 files:

```
reviews/STAGE-09-R4-REPRODUCTION.md
scripts/w2_e2_contrast_run.sh
scripts/w2_retention_run.sh
tests/test_ad01_e2_contrast.py
tests/test_ad01_w2_retention.py
```

**None of the 5 was touched by this batch.** `git diff --name-only 915b029..6d7558c`
returns empty for each. The literal was introduced by `48d535c` (2026-09-30,
"Stage 9 experiments: all four negative, each with a located cause"), which predates
the base, and the same lines are present in the base tree. So this batch neither
introduced the key nor moved it.

The pattern by which this batch handles the credential is the correct one. It reads
`SETTLEMENT_GATEWAY_KEY` from the environment at runtime
(`scripts/invl02_live.py:187`, `scripts/invl02_route_discovery.py:34`,
`src/settlement/config.py:10` names the env var). The added code contains
**0 lines that assign a literal to `SETTLEMENT_GATEWAY_KEY`**.
`scripts/b11_route_preflight.py:38` prints only the length of the loaded credential,
never its value. `config/.env.example:7` ships
`SETTLEMENT_GATEWAY_KEY=` with an empty value.

The endpoint `http://127.0.0.1:4000/v1` appears on 54 added lines. That is a
loopback address, not a credential, and it is expected: the brief states the route
in use is this local gateway.

## Scope, skips and failures

Everything the brief asked for completed. No command timed out and no scope was
skipped. Three items to record for the next reader.

1. **My worktree was created on the wrong commit.** It started at `c4ac2ff`
   (`codex/architecture-handoff`), not at the consolidation tip. Had I run the
   diff as briefed without noticing, the audit would have compared two unrelated
   histories and reported a meaningless result. I confirmed the worktree held only
   the 3 pre-existing architecture-handoff commits, that those are preserved on
   `codex/architecture-handoff` and `origin/HEAD`, and that the working tree was
   clean before moving to a new branch `wt/ev-audit` at `6d7558c`. No commit was
   rewritten and nothing was lost.
2. **One earlier base derivation was wrong and is documented above.** The
   subject-prefix rule produced `e442a02`. It is superseded by `915b029`, which
   three independent checks confirm.
3. **The brief's archived-directory premise was wrong for 5 of 7 paths**, as
   documented above. This changed the interpretation of the evidence diff from
   "an archived artifact was modified" to "a new artifact was created". I flag it
   because the distinction is the whole question this lane existed to answer, and
   the answer is the benign half of it.

## What this does and does not prove

This audit proves file-level integrity of the tracked tree. Every archived evidence
file present at the batch base is byte-identical at the tip, and the 10 files under
`reports/evidence/` that the batch did add are each attributable to one lane and one
commit.

It does not prove the recorded numbers inside those 10 new evidence files are
correct. A byte-identical archived file can still record a figure that was wrong when
first written, and no lane in this batch had standing to re-derive one it did not
produce. Per this project's standing rule, an artifact hash proves provenance, not
the research claim the artifact carries.

## Report of skips and errors by scope

| Scope | Result |
|---|---|
| Base-commit derivation | Complete, three independent checks |
| `reports/evidence/` diff and log | Complete |
| Blob-identity check over 390 pre-existing files | Complete |
| Per-path existence check, 7 brief paths | Complete |
| Per-file lane attribution and amend detection, 10 files | Complete |
| `reports/cap-sheets/` history and diff review | Complete |
| Direct read of recorded spend fields at tip | Complete |
| Credential scan, 39663 added lines, 151 files, 9 pattern families | Complete |
| Working-tree mutation | None outside creating this report |

## Files

- This report: `reports/workstreams/ev-audit.md`
- Audited branch tip: `6d7558c062b0da2540bca6d61a59760934621322`
- Audit branch: `wt/ev-audit` (not pushed, not merged)