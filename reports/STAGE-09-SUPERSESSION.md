# Stage 09 — supersession markers: what they are, and what they cannot do

Rows B6 and B7 of `TASKS.md` §B. A prior pass named the gap correctly — the
repo has both halves of a supersession convention and neither is discoverable
from the artifact it describes — and stopped at "do not build it; this is what
the four cases require, stated as shape."

**I built it.** The shape it specified was small enough to check, and a marker
that cannot be checked is prose with a filename. Four markers, five shapes, one
checker, thirty tests.

**No file under `reports/evidence/` was modified, moved, renamed or deleted.**
Every one of the six files this pass added is new. `git status` on the tree is
empty at the pre-existing paths and lists only the four markers as additions.

---

## 1. Where reachability came from, and why not from the artifact

**A sibling, named to sort beside the file it describes.** The marker is
`<stem>.supersession.json` in the artifact's own directory:
`e3-postfix-ladder.json` → `e3-postfix-ladder.supersession.json`.

**Why not from the artifact.** The tree's rule forbids editing, regenerating or
deleting anything committed, and the prior pass verified that neither route into
the JSON is available. A `supersedes` field is written by the artifact's own
generator (`e2_gate_report.py:242`, `e2_reason_probe.py:160`), so adding one to
`e3-postfix-ladder.json` means re-running `regen_e3_ladder.py` and overwriting
the committed file — the prohibited act. I confirmed the broader form of the
obstruction too: `_output_shape_problems` (`offline_recompute.py:1940`) does
not reject unknown top-level keys, so a field added post-hoc would pass
verification **unverified** — anyone could add one and no later run would
check it. That is worse than no field.

So reachability is a sibling, and the sibling's whole value rests on being
*findable* and being *checkable*. Findable is a naming rule; checkable is a
digest.

**A correction to the measurement this builds on.** The prior pass reported
"zero of the five `RETRACTED.md` directories have a sibling artifact mentioning
the retraction." Counted over the committed tree at `HEAD`, counting **all**
sibling files, that is **2 of 5** — `inv_r1_e3_ladder` and `inv_r1_e3_selection`
each carry a prose sibling (`ANNOTATION-B6-REACHABILITY.md`, `ANNOTATION-B1-B5.md`)
that uses the words. The figure holds only when the census is restricted to
JSON artifacts, which is what the prior pass did. Both numbers are defensible
about different things; the gap is the same, so this changes no conclusion. It is
recorded because the difference between "zero" and "two" is exactly the kind of
confident number this stage has been burned by.

Counted the way the task row states it — *a reader who opens the artifact* — the
gap is unchanged and total. `e3-postfix-ladder.json` contains none of `retract`,
`withdrawn`, `invalid` or `superseded` across 165,045 bytes, and that is what
this pass fixes.

---

## 2. The marker

```json
{
  "artifact": "reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json",
  "artifact_sha256": "2d59e0c9…",
  "shape": "SCOPE",
  "verdict": "PARTIALLY_VOID",
  "finding": "B6 / N-80",
  "annotation": "reports/evidence/inv_r1_e3_ladder/ANNOTATION-B6-REACHABILITY.md",
  "void_scope": [{"pointer": "$.committed_ladder", "reason": "…", "finding": "…"}],
  "surviving_claim": "…",
  "superseded_by": null,
  "intact_at_ref": null,
  "container_mislabelled": false,
  "note": "…"
}
```

**`artifact_sha256` is the load-bearing field.** It is what makes the marker
checkable rather than decorative: a marker whose digest does not match the file
beside it is stale, and `check_evidence_tree` fails. A marker with no digest is
an opinion that cannot expire.

### Five shapes, because there are five relations

| shape | void_scope | backward edge | rows |
|---|---|---|---|
| `SCOPE` | JSON pointer | no | B1, B6 |
| `DATA` | `$` or subtrees | no | the three older `RETRACTED.md` dirs |
| `EDITS` | `$` | **yes** | B2 |
| `VESSEL` | **must be empty** | no | B8 |
| `NAME` | must be empty | no | — |

The prior pass's requirement that a marker express scope, direction, the
surviving positive claim, a non-path referent, and reachability is met, with one
change: I split `SCOPE` and `DATA` rather than letting `void_scope: ["$"]`
serve both, because a whole-file void and a pointer-scoped void are different
claims and a reader should not have to inspect the pointer to learn which.

### All four cases, and which field carries each

| row | shape | carried by |
|---|---|---|
| B6 `inv_r1_e3_ladder` | `SCOPE` | `void_scope: ["$.committed_ladder"]` + a `surviving_claim` that says the file and the key both stand, for the pre-fix/post-fix comparison |
| B2 `inv_r1_e1_swe_ceiling` | `EDITS` | `verdict: VOID` + `intact_at_ref: "d422c93"`, the backward edge to the pre-edit bytes |
| B1 `inv_r1_e3_selection` | `SCOPE` | `void_scope: ["$.severed"]` + `superseded_by` the regen-v2 witness |
| B8 `inv_r1_m4_baseline` | `VESSEL` | `container_mislabelled: true` and an **empty** `void_scope` |

All four are expressed. The design fails none of the four, and the limit is
below rather than a case it cannot carry.

**B8 drove the one field with no precedent.** `container_mislabelled` has no
precedent in the repo, as the prior pass said. The schema makes it
load-bearing: a `VESSEL` marker that carries a non-empty `void_scope` is
**refused**, because on that shape voiding would destroy the only copy of eight
raw responses. The rule is the finding, encoded as a refusal.

**`intact_at_ref` is the backward edge, and it is checkable.** The checker
resolves it with `git cat-file -e <ref>^{commit}`. Reachability is the wrong
question — `d422c93` is an ancestor of HEAD and names no branch — so the check
asks git for the commit directly. I measured that ref's blob: 5,167,881 bytes,
against 5,163,201 at HEAD.

---

## 3. What the check actually verifies

`scripts/evidence_supersession.py`. `python3 scripts/evidence_supersession.py`
exits 0 on the committed tree: **4 markers checked, 0 problems.** Six falsifiable
claims, none of which needs a run:

1. the schema, including per-shape obligations
2. `artifact_sha256` equals the sha256 of the file beside the marker
3. every `void_scope` pointer resolves in that artifact
4. the named `annotation` exists
5. `intact_at_ref` names a commit this repository can read
6. an unknown key is **refused, not ignored** — a typo in a field name is not an
   unrecorded claim

**Thirty tests in `tests/test_evidence_supersession.py`, all passing.** I
mutation-tested the suite rather than trusting a green run — three deliberate
defects, each caught:

| mutation | caught by |
|---|---|
| digest check → no-op | `test_a_marker_whose_digest_does_not_match_the_artifact_is_reported_stale` |
| pointer resolution → swallow `MarkerError` | `test_a_pointer_that_no_longer_resolves_is_reported` |
| allow `VESSEL` to carry a `void_scope` | `test_a_mislabelled_container_is_not_allowed_to_void_anything` (+1) |

Six of the thirty failed on the first run. Five were bugs in my tests and one
was a real defect in the checker: `check_marker` re-read and re-parsed the
artifact once per pointer, so a 5.16 MB matrix was parsed 60 times for B2.

### The predicate the prior pass proposed, and why I did not build it

It suggested enforcing *"every JSON artifact whose `measure_digest` or `run_id`
matches another file in its directory has a sidecar naming the other."*
Measured over 218 parsed objects, that predicate fires on **3 legitimate run
bundles** — `invl02-output-shape-550b-r2/r3/r4`, where 2, 4 and 7 files
respectively share a `run_id`, because a freeze bundle is *designed* to stamp one
`run_id` across `freeze.json`, `preflight.json`, `output-run.json` and
`scorer-private.json`. It would have demanded 13 false sidecars.

The real N-79 shape is the **cross-directory `measure_digest` collision**, and
there is exactly one in the tree: `ce5a140aff83bccc…` shared by
`e3-postfix-ladder.json` and `e3-crossover.json`. That is B6 itself, and the
B6 marker now records it. So the predicate is right about the danger and wrong
about the key; I did not build it, and say so rather than shipping a check that
would fail for the right reason on the wrong evidence.

---

## 4. The limit, named plainly

**A reader who opens only the JSON and parses no sibling still does not learn
anything.** This mechanism cannot change that, and no amount of schema will. The
only thing that reaches a reader who parses the JSON alone is a field in the
JSON, and a field in the JSON can only be written by the writer, and re-running
the writer means overwriting the artifact. For these four artifacts that is the
prohibited act. This is a property of the case, not a gap in the design.

What the mechanism does buy, concretely: a reader or a machine that *lists* the
directory or globs `*.supersession.json` now reaches the verdict starting from
the artifact, and a check fails if the artifact later changes underneath the
marker. That is a real improvement on zero, and it is not the same thing as
"visible in the artifact."

Two further limits, both inherited rather than introduced:

- **The convention is run by hand.** Four markers exist because I wrote four.
  Nothing creates the fifth. A future retraction still needs someone to decide
  to write a marker, exactly as it needs someone to decide to write
  `RETRACTED.md` today. The checker can only police markers that exist.
- **`intact_at_ref` is only as good as the ref surviving.** `d422c93` is
  reachable today; a repository that garbage-collects it would turn every
  `EDITS` marker into a red check rather than a silently wrong one, which is the
  right failure direction but is still a failure.

### One thing I corrected in an annotation I did not write

`ANNOTATION-B2-EDIT-INTENT.md` states the rule as *"strip the trailing `stop`
from every row whose trace contains a `use code.repair`."* Measured against
`d422c93`, that rule selects **128** rows. Only **60** were edited. The gap is
exact and structural: **68 rows already end in a repair**, so there was no
trailing `stop` to strip. The rule that reproduces the edit with no residue is

> strip the trailing `stop` from every row whose trace contains a
> `use code.repair` **and which does not already end in one**

128 contain a repair, 68 already end in one, 60 were editable, and all 60 were
edited — 56 `repaired` and 4 `unrepaired`, matching the annotation's census. The
annotation's counts and its conclusion are right; its stated rule is
over-broad by 68 rows. I did not edit the file (it is one of the four findings
B2 is about, and the error is in the rule's phrasing, not its finding). The
corrected rule is recorded in the marker's `note`, where a checker can see it.

---

## 5. The evidence tree's history

Checked before making any claim about it, because the prior pass nearly wrote
that nothing was ever deleted here and that would have been false.

```
git log --all --diff-filter=D --name-status -- reports/evidence/
```

Over **all refs**, exactly one deletion:

```
4b365ed  2026-09-29  live_acquisition: true, with no demotion
D  reports/evidence/invl02_liveacq_r2/arm_sw00_r1_refused.json
```

One file, one commit, not this pass. `git log --all --diff-filter=R` over the
same path is **empty**: nothing in the evidence tree was ever renamed or moved.
So the tree's history is one deletion and zero renames — not "nothing", and not
"nothing by me".

---

## Constraint confirmation

- **No committed evidence file was modified, regenerated, moved or deleted.**
  Six files added: four `*.supersession.json` markers,
  `scripts/evidence_supersession.py`, `tests/test_evidence_supersession.py`,
  and this document. `git status --porcelain reports/evidence/` lists only the
  four new markers, all as additions (`A`/untracked); no other path under the
  tree appears.
- Nothing was deleted, by this pass or any other on this branch. The one
  deletion in the tree's history is `4b365ed`, named above.
- **Collision surface measured before adding files.** The only code that
  enumerates the evidence tree is `s09_exposure_ledger.py:1127`,
  `rglob("output-run.json")`. The two `rglob("*.json")` sites
  (`s09_panel_inventory.py:168`, `s09_study_protocol.py:308`) both read
  `worlds.FROZEN_DIR` (`experiments/ad01/worlds/`, not `reports/evidence`), so
  no marker can be picked up as a task cell. No new file matches any glob
  pattern the tree is scanned with, which is the class of breakage B8 warns
  about.
- `ec02test_live` was never contacted. No database was created or dropped by
  this pass. The test run is reported as `S09ISO: dropped 38 database(s) for
  this run` by the pre-existing isolation fixture, which allocates and drops its
  own per-run `ec02test_*` names; none is an `r03flow_*` and no test was killed.
- Targeted verification only: the one new test file, thirty tests, three
  mutation runs. No full suite.
- **No cross-lane edits.** `store.py`, `broker.py`, `authority.py`,
  `construct.py`, `control_arm.py`, `live_construct.py`,
  `s09_exposure_ledger.py` and `conftest_isolation.py` were read only, never
  written. `scripts/` and `tests/test_evidence_supersession.py` are new paths,
  disjoint from every live lane.
