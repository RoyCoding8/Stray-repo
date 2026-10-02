# EV-RECHECK: evidence and cap-sheet immutability at the new tip

Lane EV-RECHECK, branch `wt/ev-recheck`. Re-establishes the immutability proof that lane
EV-AUDIT recorded at base `915b029` versus tip `6d7558c`, and deltas it against the
current tip `4887515` after seven further lane merges.

Read-only audit. Nothing under `reports/evidence/` or `reports/cap-sheets/` was edited.
This file is the only file this lane created. No history was rewritten, nothing was
pushed, no test was run.

## Refs under audit

| Ref | SHA |
|---|---|
| base | `915b029` |
| earlier audit tip | `6d7558c` |
| current tip | `4887515` |

The base was not re-derived. It was verified to sit in HEAD's first-parent chain:

```
$ git merge-base --is-ancestor 915b029 HEAD   ->  YES
$ git rev-list --first-parent 915b029..HEAD | wc -l   ->  53
$ git rev-list --count 915b029..HEAD          ->  107
```

53 first-parent commits and 107 total commits in the range, which is the interleaving
the method note warned about. Subject-prefix scanning would not have found this boundary.

## 1. Blob identity of pre-existing evidence files

**Zero changed.** 390 files at base, 400 at HEAD.

The check joined two sorted path-to-blob maps rather than trusting a diff summary:

```
$ comm -23 base_by_path.tsv head_by_path.tsv | wc -l   ->  0
```

Zero base path-and-blob pairs are absent at HEAD. A second pass compared mode, blob and
path as a triple:

```
$ comm -23 base_mode.tsv head_mode.tsv | wc -l          ->  0
```

Zero mode changes, zero blob changes, zero deletions. The only structural change is
10 pure additions, matching the earlier audit exactly.

## 2. Files added under reports/evidence/ since 6d7558c

**None.** Zero files were added since the earlier audit's tip.

```
$ git diff --name-status 6d7558c HEAD -- reports/evidence/   ->  (no output)
$ git diff --raw 6d7558c HEAD -- reports/evidence/ | wc -l   ->  0
```

The 10 additions the earlier audit saw are the same 10 present now, each attributed to
the same lane, each added by exactly one commit and never touched again. All five
adding commits are ancestors of `6d7558c`, so the earlier audit already had them.

| Evidence file | Adding commit | Lane merge | Touching commits |
|---|---|---|---|
| `invr1b8-panel-census/census.json` | `005a4f7` | `5d8bb4e` Merge lane B8 | 1 |
| `invr1b11-budget/budget-probe.json` | `bb62fe5` | `e7d0e3f` Merge lane B11 | 1 |
| `invr1b11-budget/store-rows.json` | `bb62fe5` | `e7d0e3f` Merge lane B11 | 1 |
| `invr1b12-swe/campaign.json` | `9cfe7aa` | `7cc4df7` Merge lane B12 | 1 |
| `invr1b12-swe/construction.json` | `9cfe7aa` | `7cc4df7` Merge lane B12 | 1 |
| `invr1b12-swe/store-rows.json` | `9cfe7aa` | `7cc4df7` Merge lane B12 | 1 |
| `invr1b12-swe/use.json` | `9cfe7aa` | `7cc4df7` Merge lane B12 | 1 |
| `invr1b14-retention/retention.json` | `1a56662` | `9cc7249` Merge lane B14 | 1 |
| `invr1b17-budgetfit/budget-fit.json` | `30b9eac` | `78e1808` Merge lane B17 | 1 |
| `invr1b17-budgetfit/store-rows.json` | `30b9eac` | `78e1808` Merge lane B17 | 1 |

No file was added by one lane and modified by another. The serious finding this item
guards against did not occur.

Batch-wide structural confirmation:

```
$ git log --format='%h|%s' --name-status --diff-filter=MDRT 915b029..HEAD -- reports/evidence/
(empty)
```

No commit in the entire batch modified, deleted, renamed or type-changed any evidence file.

## 3. reports/cap-sheets/

**No commit since the earlier audit touched this directory**, and no recorded spend or
zero moved.

```
$ git log --oneline 6d7558c..HEAD -- reports/cap-sheets/   ->  (no output)
$ git diff --shortstat 915b029 HEAD -- reports/cap-sheets/  ->  2 files changed, 596 insertions(+)
```

596 insertions, 0 deletions, unchanged from the earlier audit. Three commits in the batch
touch cap-sheets at all, and all three predate the earlier audit.

The three known values in `b-live-cap.md` are byte-identical to how they were first
written in `e25b25c`:

| Field | Value |
|---|---|
| `total_dispatch_cap` | 75 |
| `total_physical_send_ceiling` | 78 |
| `total_units` | 194376 |

`b14-retention-freeze.md` is untouched since its introducing commit `1a56662`
(`git diff 1a56662 HEAD` on it is empty). All six recorded zeros hold at the same lines:

```
total_dispatch_cap: 0          total_physical_send_ceiling: 0
total_retry_allowance: 0       campaign_wall_ceiling_ms: 0
requests: 0                    total_units: 0
```

### One disclosure about the 0-deletions figure

`15335bd` (Close the documentary defects the acceptance pass found) shows numstat
`6 insertions, 4 deletions` on `b-live-cap.md`. The batch-level `0 deletions` counts
deletions against base, where the file did not exist, so those 4 removed lines are
invisible in the range total. This commit is an ancestor of `6d7558c`, so the earlier
audit saw it too.

I inspected every deleted line. All four are prose from a single sentence, and none
contains a digit:

```
-The three `graph` rows are the only powered panels; the ten `software` rows are the
-unpowered remainder, and the four unpowered graph panels are omitted from this table
-because this sheet allocates nothing to them. `powered_but_blind` is empty, because
-every panel that reaches six clusters also has a non-zero ceiling. A powered-but-blind
```

```
$ git show 15335bd -- reports/cap-sheets/b-live-cap.md | grep -E '^-[^-]' | grep -cE '[0-9]'   ->  0
```

The commit corrects a factual claim (three powered panels, not one). It corrects no
ceiling, no spend and no zero. The three numeric cap lines are unchanged from `e25b25c`
to HEAD by direct comparison.

## 4. Credential scan over lines added since 6d7558c

**No credential-shaped string in any added line.** No value is reproduced here.

Scope: 21 files changed since the earlier tip, 2,906 insertions by numstat. Scanned for
nine pattern families with a word-boundary anchored match:

- zero added lines matching an OpenAI, Stripe, GitHub, AWS, Slack or JWT key shape
- zero added lines containing a `PRIVATE KEY` header
- zero added lines containing a `Bearer` token

The batch's convention holds. Three added lines mention `SETTLEMENT_GATEWAY_KEY` and all
three are prose in `reports/workstreams/ev-audit.md` describing the convention itself,
including the line `**0 lines that assign a literal to SETTLEMENT_GATEWAY_KEY**`. Added
lines matching a literal key assignment scan return exactly one variable name:

```
RUN_TOKEN   (1 occurrence since 6d7558c, 10 since base)
```

`RUN_TOKEN` is a 7-character test fixture assigned in test files. It was already present
at base in 23 test files and HEAD has 34. This is test-fixture text, not credential
material.

### The pre-existing literal

Confirmed pre-existing and untouched by this batch, as the brief stated. Two files
carry a literal default:

- `scripts/w2_e2_contrast_run.sh:28`
- `scripts/w2_retention_run.sh:36`

Both use a shell `export VAR="${VAR:-sk-cx-local}"` fallback. `sk-cx-local` is a local
route fixture label, not a live key. Provenance and immutability:

```
$ git log --oneline --reverse -S 'sk-cx-local' -- scripts/w2_e2_contrast_run.sh | head -1
48d535c  Stage 9 experiments: all four negative, each with a located cause

$ git merge-base --is-ancestor 48d535c 915b029   ->  YES (predates the batch)

$ git diff --stat 915b029 HEAD -- scripts/w2_e2_contrast_run.sh scripts/w2_retention_run.sh
(empty — the batch did not touch either file)

scripts/w2_e2_contrast_run.sh  base=e3c334b3  earlier=e3c334b3  head=e3c334b3
scripts/w2_retention_run.sh    base=0347cdc9  earlier=0347cdc9  head=0347cdc9
```

Identical blobs at base, earlier tip and HEAD. No new literal of the local route key was
added by this batch.

### A detector correction worth recording

My first whole-tree scan reported zero literal assignments at HEAD. That was wrong. The
regex I used required 8 or more characters from `[A-Za-z0-9_-]`, and `sk-cx-local`
contains two hyphens splitting short segments, so it did not match. The corrected scan
finds the two occurrences. An earlier broad `sk-` scan also produced ~80 apparent hits
that were ordinary words such as `task-` and `risk-`; anchoring the pattern to a word
boundary cleared all of them. Both the false negative and the false positives were found
by running a synthetic known-positive control through the detector and by characterising
hits rather than trusting a raw count.

## Verdict

The immutability proof holds at the new tip. Nothing in this batch modified, deleted or
rewrote any pre-existing evidence file, and no lane has touched a recorded cap or a
recorded zero.

| Item | Result |
|---|---|
| 1. Blob identity, 390 pre-existing files | 0 changed, 0 mode changes, 0 deletions |
| 2. Evidence added since `6d7558c` | none; the same 10 files, each from one lane, each single-commit |
| 3. Cap-sheets | no commit since earlier tip; 596 ins / 0 del; three known values and six B14 zeros intact |
| 4. Credential scan on added lines | no credential-shaped string; convention intact; the one literal is pre-existing and byte-identical |

### What changed since the earlier audit

Seven lanes merged: BOTTLENECK, X4b, DOC-APPLY, MIG-MIGRATE, SIB-FIX, C14-FIX, plus the
documentary-defect commit they carried. None touched `reports/evidence/` or
`reports/cap-sheets/`. Range grew from 39,663 to 42,449 insertions and from 151 to 164
changed files, all in code, tests and governance documents.

### Scope limit

This proves file-level integrity. It does not prove that the numbers inside a
byte-identical archived evidence file were correct when first written. The 390 files are
unchanged from before the batch, and their contents were outside this lane's
verification. A separate review would be needed for that claim.

### What I could not determine

Whether the branch tip moves again before push. This audit holds at `4887515`. If more
lanes merge, the delta is cheap to re-run since the base is verified, but the proof does
not transfer forward on its own.