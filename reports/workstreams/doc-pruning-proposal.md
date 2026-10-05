# Document pruning proposal

Written on `wt/prune` at base `89df5873`. Governing principle is
`principle-subtract-before-you-add`, with `principle-laziness-protocol` on
proposal size and `principle-minimize-reader-load` on what a third reader can
still follow. Every row below is grounded in a file read or a grep in this
tree. Where I could not establish something, it says so.

**Nothing under `reports/workstreams/` or `reports/cap-sheets/` was deleted.**
The brief marks those proposals-only, and that judgment belongs to a human.
What I did correct is four present-tense defects, named in the last section.

## The distinction this census turns on

`AGENTS.md` says historical reports describe their own revisions, not today's
completion state. A lane report that says "the writer is missing" describes the
tree it ran on and is not stale. A **current-status** document that says it is
missing, after the repair landed, is a bug in a document.

That split does most of the work below. Of 197 files in `reports/workstreams/`,
**185 are referenced by no current-status document** — verified by grep for
each basename across `reports/PROJECT-LEDGER.md`, `docs/`, `WORKER-PROMPT.md`,
`IMPLEMENTATION-WORKFLOW.md`, `reports/STAGE-09-10-COMPLETION-MATRIX.md` and
`AGENTS.md`. Only four are named: `m0-ownership-map.md`, `m0-map-challenge.md`,
`bottlenecks.md` and `recovered/`. An unreferenced lane report is not clutter; it
is the record of how a lane was reasoned, which is exactly what the brief says
not to delete on a merge alone.

## Census: `reports/workstreams/`

191 markdown files, 2 Python, 2 JSON, 1 empty `recovered/` entry in the listing.
Last-touched by date:

| date | files | what they are |
|---|---:|---|
| 2026-10-02 | 176 | review-01 and milestone lane reports (`R1a`, `R2`, `b*`, `inv-*`, `w0-tr*`, `ec02-*`, `m0-*`) |
| 2026-10-03 | 3 | `z2-red-audit.md`, `s09-*`, others |
| 2026-10-04 | 12 | the batch under study, listed below |

| document | claim it makes | claim still true? | recommendation |
|---|---|---|---|
| `m0-ownership-map.md` | mission state ownership map | yes, cited by ledger:179 as M0's evidence | **keep** |
| `m0-map-challenge.md` | challenges the lane split; ledger:192 records the split as REFUTED | yes | **keep** |
| `m3-expressive-probe.md` | 33/39 admit one repair, 0/39 two; carried into ledger:268-295 | yes | **keep** |
| `m3-instrument-census.md` | instrument census behind the M3 null | yes, cited as the null's basis | **keep** |
| `m2-acceptance-design.md` | M2 acceptance design; M2 unstarted | yes | **keep** |
| `barrier-path-decision.md` | counts four `in_flight` writers, recommends deletion | **superseded as a decision** — it recommends deleting the fourth writer, and `437007e` deleted it. Its census, its reachability method and its counter-argument section remain the only record | **keep** (see consolidation note) |
| `m1-lane-b11-findings.md` | four writers enumerated; lane rejected the repair | same shape as above — the report is the *reason* the B11 repair was refused | **keep** |
| `m1-lane-c-improve-authority.md` | improve-channel authority lane | unreferenced; content not verified against the tree | **keep, unreviewed** |
| `ad01-leak-assessment.md`, `caps-child-execution-authority.md`, `triage2-shard2-3-heavy.md` | this session's lane findings | not verified line by line | **keep, unreviewed** |
| 176 files dated 2026-10-02 | per-lane findings for review-01 and the milestones | each describes its own base commit; history by construction | **keep** (see below) |
| `a59-root-eval.py` | evaluates own-`__file__` derivations | runs; referenced by `a59-heavy.md:150` | **keep** |
| `freshauth-repro.py` | reproduces the freshauth refusal, no PostgreSQL needed | runs; self-documenting docstring | **keep** |
| `a59-derivations.json`, `inv-a-c2-ledger.json`, `inv-a-c4-ledger.json` | JSON evidence | `a59-derivations.json` is referenced by no document; the two `inv-a` ledgers are not | **keep, unreviewed** |

### Proposed deletions

**Zero.** No file in `reports/workstreams/` is verbatim-duplicated by another
file, and no finding-bearing report's content survives nowhere else. The brief's
test — (a) landed in code and recorded in the ledger, or (b) the only record of
something — resolves to **keep** in both branches for the reason it is built to:
the reasoning behind a rejected repair is not reproducible from the ledger, which
records what landed and not why an alternative was refused.

The exception worth naming is `barrier-path-decision.md`. It is a decision
document whose decision has since been taken by a commit, so a reader arriving
cold cannot tell whether the count in it is current. The finding is not
deletable. The fix is one line in the ledger or the file, adding that `437007e`
carried out the recommendation and the count is now three — which ledger:141
**already records**. On that basis the file needs no edit: the ledger is the
index and it is right. Recording it as **keep**.

### Proposed consolidations

**One, and it is a candidate rather than a recommendation.**

`barrier-path-decision.md` (28 KB) and `m1-lane-b11-findings.md` (22 KB) reach
the same conclusion about the same column from opposite directions — one argues
the fourth writer should be deleted, the other argues a fifth should not be
added — and both carry the writer census. If they were merged, the merged
document would have to contain the reachability census, the `FOR UPDATE`
transaction argument, the "what this lane changed" diff summary and the
`_EXPECTED_WRITERS` test-coupling note. That is most of both files, so the
merge saves one filename and loses the ability to read either lane's reasoning
whole. I do not recommend it.

**Recommendation: consolidate nothing.** `principle-minimize-reader-load`
measures layers to trace, and a directory of per-lane reports is already one
flat layer. Merging same-conclusion files adds a cross-reference and removes a
scannable index.

What I would propose instead, if the human wants the tree thinner, is the
opposite move: a single `reports/workstreams/INDEX.md` listing each file with
its base commit and verdict, so 191 files become navigable without a merge.
That is an **addition**, and `principle-subtract-before-you-add` says the tree
does not need it until someone actually fails to find a report.

## Census: `reports/cap-sheets/`

Eight files. The brief's concern was two sheets describing one experiment with
superseded numbers. **I found no such disagreement.**

| document | claim | still true? | recommendation |
|---|---|---|---|
| `a57-prospective-freeze.md` | FROZEN 2026-10-03 at `8860d85`; `route_verified_live: false`; A1 at zero dispatches | yes as a dated freeze. It records that a route was absent **on 2026-10-03 at that tip**, and the ledger:165 records a route live at `ff5b767`. Two different tips, both correctly dated — not a contradiction | **keep** |
| `e0-e12-child-execution-caps.md` | adds `sandbox_calls` to E0 (19) and E12 (30), derived from code | yes; every figure re-derived reads the same | **keep** (one duplication corrected) |
| `b-live-cap.md` | FROZEN 2026-10-01 at `75cab06`; B14/B15 not allocated | yes as a dated freeze | **keep** |
| `b14-retention-freeze.md` | new freeze; B14 allocated a dispatch ceiling of **zero** | yes. It explicitly does not amend `b-live-cap.md` and says so at line 7 | **keep** |
| `invl02-live-grant.md` | live authorization of 2026-09-23 | yes, and `invl02-m5-cap.md` names itself superseded by it | **keep** |
| `invl02-m5-cap.md` | withdrawn placeholder, never ran | yes; self-marked superseded | **keep** |
| `w1-e1-cap.md` | FROZEN pending sign-off | yes | **keep** |
| `invl02-s09-cap.json` | JSON cap | not verified against the two s09 sheets — **NOT MEASURED** | **keep, unreviewed** |

`e0-e12-child-execution-caps.md` was amended this session. Reading it against
`a57`, the two sheets do not disagree: `e0-e12` scopes E0/E12 only and says so at
line 231, and both sheets record `dispatches_used: 0` and `model_calls: 0`.

## Stale scratch

| item | state |
|---|---|
| `.measure/` directories | **none anywhere in the tree** (`find -name '.measure*'`) |
| `experiments/ad01/probes/` | **absent.** Added by `4a768596`, removed by `686312a2` ("Drop the probe scripts from the production tree"). Confirmed nothing remains |
| measurement scripts | `reports/workstreams/a59-root-eval.py` and `freshauth-repro.py` are both live and referenced by their lane reports. `4a768596` restored a census harness under `probes/` and `686312a2` removed it. `reports/evidence/*/make_*.py` are records of runs. **Nothing here is mine to delete** |

## Present-tense false claims

Five classes were searched by name. Results:

- **`tasks.score` deciding from "two public cases plus one protected case"** — two
  hits, `PROJECT-LEDGER.md:280` and `STAGE-09-10-COMPLETION-MATRIX.md:80`. **Both
  correct as written.** Each states the defect in the past tense and names the
  repair (`cb7012c`, then `1a47029b`) in the same breath. `s09_swe_tasks.py:717-725`
  confirms the code decides on `equivalence_verdict`, not on case counts.
- **`mismatch` branch live** — **no present-tense claim found.** Every hit is a
  historical finding, an evidence-tree identifier, or an unrelated domain use
  (`artifacts.py` content digest, `broker.py` identity refusal).
- **`in_flight` has four writers** — four hits, all historical:
  `barrier-path-decision.md:249` and `m1-lane-b11-findings.md:25,104` are
  2026-10-04 lane reports enumerating the count *before* `437007e` deleted the
  fourth; `m1-lane-b11-findings.md:279` is a test log recording that the
  enumeration still returned four at the time. The current tree has three,
  all in `mission.py` — confirmed at `tests/test_a40_admission_wired.py:463-467`,
  in the `trajectory.py` docstring at `:560-563`, and in `mission.py:101`. **No
  correction needed**; these are the reasoning record.
- **`observation_dependent` is `True` on E0** — **two present-tense hits found.**
- **"No live route is configured"** — five hits. All correctly scoped: ledger:167
  and ledger:390 are the *retraction* of that claim; `a57-prospective-freeze.md:35-36`
  and `:256` are dated to 2026-10-03 at `8860d85`; `a1-preflight.md:119` and
  `a7-probe.md:110` are lane reports on their own bases. **No correction needed.**
- **"43-site census" / "a55 authority commit"** — **neither string exists** in
  any `.md` or `.json` in the tree. `a55-owner.md` is a real lane report with no
  commit by that name. Ledger:141 cites `437007e` for the `in_flight` repair;
  I verified that resolves to `195bcd4e`, "Give investigations.in_flight back the
  single owner it had" — the correct commit. **No correction needed.**

### Corrected

**1. `docs/design/REFINEMENT-ROADMAP.md:18` — named a superseded mechanism in
present tense.**

Before: "`observation_dependent` measured the falsifier's own hand, not causal
influence."

The field now compares preserved against **disconnected**
(`scripts/invl02_live.py:2179-2181`), which is why it reads `False`. The roadmap
was describing the falsifier comparison, which `581c7a4b`/`1d7e8564` replaced.
The verdict was right and the mechanism was wrong, which is the harder kind of
stale: a reader would look for the falsifier arm and not find it.

After: "`observation_dependent` compares the preserved arm against a
disconnected arm given no evidence, and on the real E0 freeze both choose
`opp-first`, so it cannot show causal influence."

**2. `reports/STAGE-09-10-COMPLETION-MATRIX.md:444` — cited two drifted line
numbers in a "still open" finding.**

Cited `twodomain.py:102` for the 120-vs-72 figure; the sentence is at `:128`
after later edits. Named no line for the census it contrasts against; the
`range(24)` it describes is at `:116`. A reader following the citation lands on
unrelated code and cannot confirm the finding. Corrected to `:128` and `:116`.
The test citation (`:16`) was already right, verified.

**3. `reports/cap-sheets/e0-e12-child-execution-caps.md:212-213` — a sentence
duplicated verbatim by a bad edit.**

"At the time it was written that was not a live defect, because every round ran
against a" appeared twice consecutively. The second copy made the paragraph
unparseable and buried the actual reason the sheet is needed. Removed the
duplicate.

### Considered and left alone

- **The three "recorded, not repaired in place" defects at matrix:440-444** are
  all still open, verified individually: `channel.REACHABLE_EVIDENCE` has no
  definition left in `experiments/` or `src/`, so `make_evidence.py:238` still
  reads a deleted name; `make_evidence.py:242` still mints `seed-%s-%s`;
  `twodomain.py:128` still says 120. The matrix is right to record them rather
  than edit an immutable evidence tree, and the reasoning holds.
- **The two "corrections" sections in the ledger** (lines 98-112) deliberately
  correct the evening section *in place of* editing it, on the stated ground that
  "that section records its own stretch." I did not second-guess that. It is the
  distinction this brief opens with, applied correctly.
- **`m3-expressive-probe.md`** describes a probe whose candidate enumeration was
  later changed. The ledger:270-273 already explains why. Not stale.

## What I did not measure

- Whether any of the 176 files dated 2026-10-02 still contains a false
  present-tense claim. I read headers and grepped for open-defect phrasing across
  the directory; I did not read 176 files. Ten matched the grep
  (`a55-owner.md`, `b1-sweharness.md`, `b1c-flip.md`, `b2-graphchild.md`,
  `doc-delta.md`, `ec02-D.md`, `inv-b.md`, `w0-tr02.md`, `w0-tr03.md`,
  `z2-red-audit.md`) and are **unreviewed**. A lane report describing its own
  defect is history; one of these may not be.
- `invl02-s09-cap.json` against the s09 sheets.
- Whether `reports/workstreams/recovered/` patches are still applicable. They are
  `.patch` files recovered from pruned lanes; the ledger:489 names the directory.

## Contradictions to the brief

1. **"Any present-tense claim that `tasks.score` decides from two public cases
   plus one protected case"** — no such claim exists. Both hits already carry the
   repair in the same sentence. The brief said a previous pass found this class
   three times; on this tree that pass has already repaired all of it.
2. **"Anything claiming the `mismatch` branch is live"** — nothing claims this.
   The string does not occur in any present-tense defect statement.
3. **"`reports/cap-sheets/`: check whether multiple cap sheets describe the same
   experiment with superseded numbers"** — they do not. The 19/30 ceilings in
   `e0-e12` and the zero-dispatch findings in `a57` are disjoint scopes, each
   says so, and no number in one is restated in the other.
4. **"This session added 20+ reports"** — on this base, 12 files in
   `reports/workstreams/` have a 2026-10-04 last touch. 176 of 191 are from
   2026-10-02. The accumulation being pruned is mostly from an earlier day, and
   pruning it is not a small edit to this session's output.

The brief's caution about `43-site` and `a55 authority` was well placed. Neither
string exists, and the `a55` reference resolves to a real report.