# Stage 09: the evidence tree's structure, and where r4's raw responses are filed

Lane R5, analysis only. Every file cited below was opened at `07fb0d5` unless
labelled otherwise. Nothing under `reports/evidence/` was moved, renamed,
edited, or deleted by this pass.

## What is in the tree

46 top-level directories, 201 files, 11 MB. 146 JSON, 34 Markdown, 11 Python.
Two naming families carry 39 of the 46 directories: `inv_r1_*` (25) and
`invl02-*` (14). Seven more use a third convention (`ag01-demo`, `d02live`,
`eng-solv`, `eng-close2`, `s09-empty-receipts`, `context-pilot-01`,
`development-02-prompt-pilot`), so no single prefix identifies a study family.

---

## B7. Supersession

### The mechanism that exists, and how far it reaches

Four directories carry a `RETRACTED.md`: `inv_r1_e2_noexp`, `inv_r1_e2_relevance`,
`inv_r1_e2_transfer`, `inv_r1_e3_selection`. The first three landed in one commit,
`567efae` (2026-09-26); the fourth in `4df45b2` (2026-09-28). `grep -rn RETRACTED
--include='*.py'` over the whole repository returns nothing, so no code reads or
writes any of them. The convention is human-operated, and it is run by hand each
time a retraction is written up.

What a reader gets from one is good. `inv_r1_e3_selection/RETRACTED.md` names the
refuting artifact, names three independent causes, states what survives, and
separates the repaired figure from the retracted one.

What a reader does not get is which artifact replaced it. All four say what is
wrong; none names a successor. That is exactly the N-79 case: two artifacts in
one namespace sharing `measure_digest ce5a140aff83bccc`, reporting opposite
facts, with nothing marking the older one dead.

### The three candidates, priced here

**Marker file convention (a `SUPERSEDED.md` sibling).** Smallest change. Breaks
nothing: it is prose, no reader parses it, and the 9 path-constant sites below
are all names, not shapes. Its cost is entirely that nothing enforces it, so
whether it appears is a matter of who remembers.

**A `supersedes` field in the artifact JSON.** This is where the cost is.
`_output_shape_problems` (`offline_recompute.py:1940`) does not reject unknown
top-level keys, so a field added post-hoc to a committed bundle would pass
verification, which means the field is unverified: anyone could add one, and a
later run would not check it. Worse for a regenerated artifact.
`_write_output_bundle` (`scripts/invl02_live.py:1486-1504`) builds the bundle from
a fixed 10-key dict; a `supersedes` key would have to be added to the writer, and
the writer's own output is digest-covered, so the field becomes load-bearing on
the next freeze. It cannot be added to the existing files at all without editing
evidence. That is the disqualifier: the mechanism cannot annotate the artifacts
that most need annotating.

**A generated index.** Nothing reads one. `find reports/evidence -iname 'INDEX*'
-o -iname 'MANIFEST*'` returns two hits, `inv_r1_m3/manifest.json` and
`inv_r1_m3b/manifest.json`, both per-study. The index would be a document a
reader must already know to open, which is the same failure as B7 restated.

### The 9 path-constant readers, verified

The brief's count of 9 is right, and here they are with what each does. Six read
or write a file, three are strings carried into a frozen digest.

Reading, or reading-and-writing:
1. `experiments/ad01/s09_exposure_ledger.py:38` `R4_EVIDENCE`, read at `:1161-1172`
2. `experiments/ad01/s09_exposure_ledger.py:43` `OLDER_BUNDLE`, read at `:895-907`
3. `experiments/ad01/s09_exposure_ledger.py:44` `OLDER_RECONCILIATION`, read at `:946-1007`
4. `experiments/ad01/s09_cap_sheet.py:54` `CONSTRUCTION_SOURCE`, read at `:410`
5. `experiments/ad01/e3_ladder.py:802-804` (`Path / "reports" / "evidence" / "inv_r1_e3_selection" / "e3-crossover.json"`), read at `:802` and re-emitted as a `path` field at `:846`
6. `experiments/ad01/e2_replication.py:813` `read_first_namespace` default, read at `:820`; the same file's `:1287` `--out` default writes `reports/evidence/` + `NAMESPACE`

Carried into a signed structure, so moving the target changes a frozen value:
7. `experiments/ad01/s09_study_protocol.py:46` `STUDY_ROOT_PREFIX`, used at `:468` in `Freeze.__post_init__` to refuse a mismatched study root, and at `:1285`/`:1304` to build `study_root`
8. `experiments/ad01/s09_swe_experiment.py:1882` `--out` default `reports/evidence/inv_r1_e1_swe`, the writer's default destination
9. `tests/test_s09_matrix_size.py:48` `COMMITTED`, opened at `:322`

Two more that name the tree but are not path constants, recorded so the count is
not double-counted: `experiments/ad01/s09_e2_scored.py:3` and
`tests/test_s09_e4_evidence.py:6` reference the path only in a module docstring,
and `tests/test_s09_e4_evidence.py:31` rebuilds it with `Path` parts rather than a
literal. `tests/test_s09_exposure_ledger.py:286` asserts a warning string that
embeds `OLDER_BUNDLE` and would follow any change to it.

One reader is layout-coupled in a way a rename would break silently, which is the
real reason to leave the layout alone. `_settled_study`
(`s09_exposure_ledger.py:1013`) does
`for path in sorted((repo_root / EVIDENCE_ROOT).rglob("output-run.json"))` and
returns on the first file whose `durable_receipts` carry the reservation it is
looking for. Sorted, that scan visits, in order:

```
reports/evidence/inv_r1_m4_baseline/output-run.json     <- first
reports/evidence/invl02-output-shape-550b-r3/output-run.json
reports/evidence/invl02-output-shape-550b-r4/output-run.json
```

It resolves `res-invl02-output-P1-audit-0023-a1` from the r3 file, and reports
`study_root: invl02-output-shape-550b-r1` while naming the r3 directory, which is
why the ledger emits its third conflict line. Renaming or reordering directories
changes which file answers first, and nothing tests that.

**Measured cost of changing the layout: 9 sites to edit, 4 of them test
assertions or frozen digests, 1 rglob whose resolution order is untested and
would change.**

### Recommendation: record that git history is the mechanism

Not because git is good enough in the abstract, but because it is the only option
that annotates the existing artifacts without editing them. `RETRACTED.md` is
already the working form of this and it has the same property: the retraction
lives in a commit, and the commit names the refuting artifact.

Git history is sufficient here, and this is why:

1. Every artifact is committed and none has ever been deleted. `git log
   --diff-filter=D` on the m4 bundle returns empty, so a withdrawn artifact is
   still reachable at the ref that introduced it.
2. The evidence tree is a linear sequence of immutable bundles whose identities
   are content digests, not names. A reader who wants to know whether a file is
   current compares its `run_id`, `source_identity`, and `code_digests` against
   the code it would verify against. That comparison is mechanical, and it
   requires no marker file. The m4 bundle demonstrates it: its
   `source_identity 472ddedc...` differs from r4's `954ddd7b2...` and its
   `code_digests` for `scripts/invl02_live.py` is `86d26f28...` against r4's
   `8b412fa9...`, which is what identifies the two as different runs rather than
   as one superseded by the other.
3. A generated index would have to be regenerated on every run to stay true, and
   the runs that produce these bundles are the ones the tree exists to record. An
   index that needs a dispatch to maintain is not a free-standing mechanism.

**What a receiving agent must do to discover supersession, concretely.** Four
steps, in this order:

```
git log --format='%h %ad %s' --date=short -- <the evidence file>
git log --format='%h' --all --diff-filter=D -- <path>          # was it withdrawn
git log --format='%s' --all --grep='<artifact or study id>'    # who said so
python3 -c "import json;print(json.load(open(PATH))['run_id'])"
```

Then compare that `run_id` and `source_identity` against the code's current digests.
If they differ, the file is a record of a past state, not a current measurement, and
that is the whole answer. The one case where this fails is a directory holding two
live artifacts from the same repair, which is N-79, and there the git log is the
only record too.

**If a mechanism is wanted later, the smallest correct one is a prose
`SUPERSEDED.md` naming the successor by path and by commit.** It costs one file per
retraction, breaks nothing, and is enforceable by a single check in a test that
asserts no directory contains two artifacts claiming the same `measure_digest`
without a `SUPERSEDED.md`. That check is worth more than the marker, because the
marker is what the check reads. Do not add a `supersedes` field to the JSON.

---

## B8. `inv_r1_m4_baseline/output-run.json`

### Which study it belongs to

Its own `study`, `study_root`, and `protocol_id` all read
`invl02-output-shape-550b-r4` (`invl02-output-shape-550b-r4-v1`, `round: 4`). It is
filed under `inv_r1_m4_baseline`, a directory named for M4, a milestone of the
INV-01 study series, not for the INVL02 output-shape rounds. The directory name and
the artifact's self-declared study disagree, and the artifact is right about itself.

**But it is not r4 either, and this is the finding.** It is a *second, later* r4.

- `run_id f9bd21ad28d847e9bd9853fed0e07853` against r4's committed
  `8a7d3ef94f9b457eb4e09bee02e9ba89`. Different runs.
- `freeze_digest 6b709c6365f62f0425e8fde75fed961a6be2c254b16b03ee2cf7bcf8822a67dd`
  against r4's `ad4188300eaef2a39497d1b821bced8d083435665868e66322dc764f4478e823`.
  Different freezes.
- `source_identity 472ddedc7d29b16895d6db8806f500473351061c63d778de6ba27aef9f430186`
  against r4's `954ddd7b27b78cdacbffecf666878ff66c2b5cd989f59797ba2adc074c21aab2`,
  which is the value r4's own `grant-binding.json:bound_study.source_identity`
  records. The m4 run is not the run the grant authorized.
- Its operation namespace is `invl02-output-b21c612ec436-*` against r4's
  `invl02-output-872608eb94c3-*`. A different run token.
- Its `code_digests` differ from r4's on `scripts/invl02_live.py`, `gateway_http.py`,
  and `boolean_rule.py`, and it drops `offline_recompute.py` from the digest map
  entirely. It also carries a different `prompt.rendered_digests` for every cell.

So the eight responses are not a copy of the r4 run that the store recorded. They
are a re-dispatch of the r4 study on 2026-09-26, one day after r4 was frozen and
declared closed, at a different code revision, under a different run token.

### Why it landed there

`reports/evidence/inv_r1_m4_baseline/RESULT.md:14-18` says it: "A fresh disposable
DB, the full `freeze-output → preflight → run-output` sequence on the pinned free
route: 8 dispatches, 8 durable receipts, 0 replays, 0 retries." The M4 lane ran
`scripts/invl02_live.py`'s output path to obtain a baseline bundle to hand to
`offline_recompute.verify_bundle()`, and wrote it to the directory it was working in.
`RESOLUTION.md:15` in the same directory confirms the bundle was the output-shape
cell's, not M4's, and that `verify_bundle()` routes it to `_verify_output`, not to
`_verify_m4_bundle`. I confirmed that routing by reading `offline_recompute.py:1684-1700`:
`"candidate_view" in bundle` sends it to `_verify_output` regardless of where the
file sits.

### What the correct filing is, and why moving it is unsafe

The correct home is a directory named for the run that produced it. By content that
is an r4-protocol output-shape bundle with `run_id f9bd21ad...` and freeze
`6b709c63...`, so something like
`reports/evidence/invl02-output-shape-550b-r4-replay-2026-09-26/`. Note it is not
"r4's responses"; it is a distinct run, and naming it as r4's would repeat the
confusion the finding is about.

**A move is unsafe in three specific ways, all measurable.**

1. It would change what the exposure ledger reports. `_settled_study` scans
   `sorted(rglob("output-run.json"))` and returns on the first match. Today that
   order puts `inv_r1_m4_baseline/output-run.json` first, then r3, then r4. The
   ledger's settled row resolves `res-invl02-output-P1-audit-0023-a1` from r3 and
   prints `study_root: invl02-output-shape-550b-r1` from inside a file under
   `...550b-r3/`. Moving the m4 file changes nothing for that reservation, because
   it does not hold it, but a rename that alters sort order is a silent behaviour
   change in a module whose output is a liability ceiling.
2. The file has no duplicate anywhere. I searched every 50-character run of each of
   eight `raw_response` values across the whole repository; no file other than this
   one contains any of them. `git log --all` shows one commit touching it, `59181d7`
   (2026-09-26), and it has never been deleted. It is the only copy, as the brief
   says, and `git mv` is the only way to move it that keeps that true.
3. Its evidence directory is cited by 11 other documents (matrix, roadmap,
   milestone audit, findings, resolution, both design docs). Moving the file moves
   the meaning of the directory, not just a path. Every one of those citations would
   need re-reading to confirm it still says what it says.

**The safe alternative, in order.**

1. Do not move it. Add one file, `reports/evidence/inv_r1_m4_baseline/PROVENANCE.md`,
   stating the run's true identity: `run_id f9bd21ad...`, freeze
   `6b709c63...`, `source_identity 472ddedc...`, namespace `b21c612ec436`,
   dispatched 2026-09-26 on a fresh disposable DB, distinct from r4's
   `8a7d3ef9...` / `ad41883...` / `872608eb94c3`, and that the directory name does
   not describe the run. This annotates without touching evidence and without
   moving a byte. It is also the recommendation of the B7 section above, applied to
   the case at hand.
2. Separately, and this is a real liability finding rather than a filing problem:
   the run spent **8 dispatches carrying 18,708 units of recorded exposure**
   (four at 2294 and four at 2383, all `settled: true`, `unresolved_exposure: 0`,
   `charge_units: "unknown"`), against a `reports/PROJECT-LEDGER.md` that lists
   only 5563 units of prior unsettled exposure and does not mention them. The
   operations are not in the store. `SELECT count(*) FROM operations WHERE id LIKE
   '%b21c612ec436%'` returns 0 on `invl02_live` and on every `ec02test_*` database
   on this cluster; the disposable DB is gone. The ledger's own rule
   (`PROJECT-LEDGER.md:361`) is that any new freeze must read the durable store, and
   this run's store is unrecoverable, so its 18,708 units can only be carried
   forward, never reconciled. That is a decision for the coordinator, not a
   bookkeeping line.
3. A move, if one is still wanted, is `git mv` plus a `PROVENANCE.md` at the old
   path pointing to the new one, in the same commit, with the old path kept as a
   one-line stub file rather than deleted.

**On the 18688 figure — SETTLED 2026-09-29 at `94443a7`, see
`reviews/STAGE-09-N36-N65.md`.** The superseded text follows.

**On the 18688 figure.** `grep -rn 18688 --include='*.md'` returns hits in 15
documents, 9 files by the `-l` count, and none of them is a data artifact. It does
not come from this bundle: the bundle's exposures sum to 18,708, and
`reports/STAGE-09-ROADMAP.md:650` already records that `18688 = 8 x 2336` exactly,
the shape of a pre-flight sizing at 2336 per dispatch rather than a settled
exposure. This pass neither sources nor retracts it. It is unchanged and still
OPEN. **[Superseded: 18688 is sourced. It is `4 × 2294 + 4 × 2378`, a pre-flight
sizing, and 2336 is the mean of those two prices rather than a per-dispatch
price. It is not held exposure, so nothing was overstated and nothing was
missing.]** The 18,708 measured here is a third number, from a third run, and the
coordinator should not conflate it with either.

---

## Index and cold-reader navigation

**There is no top-level index or manifest for `reports/evidence/`.** Verified:
`find reports/evidence -iname 'README*' -o -iname 'MANIFEST*' -o -iname 'INDEX*'`
returns only `inv_r1_m3/manifest.json` and `inv_r1_m3b/manifest.json`, both
per-study. The only README in the repository for an evidence tree is
`evidence_inv01_live/README.md`, which documents a different, older tree at the
repository root, not `reports/evidence/`. There is no `reports/evidence/README.md`
and no `reports/evidence/INDEX.md`.

**A cold reader cannot navigate this tree today.** The concrete instance the audit
found is E4. `reports/STAGE-09-COMPLETION-MATRIX.md:36` reads:

> `inv_r1_e4/headroom.json` (9056 bytes), `inv_r1_e4/make_evidence.py` (10722
> bytes) — **two files, no other artifact** ... **The live campaign was not run.**

That row was written on 2026-09-28 and reads only the two files that existed when
it was drafted. `reports/evidence/inv_r1_e4/result.json` (24,403 bytes,
`acquisition_summary.acquired: 6`, `verdict: "no-eligible-revision-acquired"`, a
150-seed cohort, and six `diagnosis-invl02-e4-revision-*` directories under `run/`)
was committed 8 hours later in `111ec3a` at 01:44:57. `TASKS.md` G1 records the
correction. So a reader arriving cold and trusting the layout rather than
`git log` gets a stale answer, and there is no index whose staleness would have
been visible.

The deeper problem is that the tree has three naming conventions, and 21 of 46
directories carry a `RESULT.md` while 25 do not. A reader has to know, before
starting, that `inv_r1_e4` is an INVL02-run experiment cell, that `invl02-*` is the
output-shape series, and that neither prefix sorts the other. Directory names are
not a map.

**The smallest fix, and it is a file, not a mechanism.** A hand-written
`reports/evidence/README.md` listing all 46 directories in one table with, per
directory, the study it belongs to, whether it holds a live result, and whether it
is retracted. It is 46 lines, it needs no regeneration, and it does not touch a
single evidence byte. It would have caught the E4 case, because the table would have
to be edited when `result.json` lands, and an entry that is not edited is visible in
a diff.

---

## Unread, with reasons

- `reports/evidence/inv_r1_m4_baseline/tamper-results.json` and `gate-results.json`
  were listed and sized but not parsed. They concern M4's seven tamper examples, not
  the supersession or the exposure question, and B8's identity facts come from
  `output-run.json`, `RESULT.md`, and `RESOLUTION.md`.
- `inv_r1_e4/run/` contents were listed, not read. Only the directory's existence
  and the acquisition summary from `result.json` bear on the cold-reader claim.
- `reviews/STAGE-09-FINDINGS.md` was read by grep and by targeted line ranges
  (611 lines total), not end to end. The N-79, N-80, and N-65 rows were read in
  full.
- `tests/` was not run, per the brief. The ledger was run read-only
  (`python3 -m experiments.ad01.s09_exposure_ledger`, rc 0) because its output is
  the measurable consequence of any move.
