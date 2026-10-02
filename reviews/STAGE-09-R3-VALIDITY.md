# Stage 9 R3: experimental validity and identifiability review

Read-only challenge of the source at `dd504e1` on `wt/r3-validity`. No source,
test, or evidence file was modified. The only file this commit adds is this
review.

## What the study as written is

The frozen protocol (`experiments/ad01/s09_study_protocol.py`) defines three
arms and a fixed task list. The arms are role labels, not treatments:

```
ARMS_BY_NAME = (Arm(name="P0", role="authored-control", control=True),
                Arm(name="P1", role="acquisition", dispatches=True),
                Arm(name="P2", role="improvement", dispatches=True,
                    benchmark=True))
```

`Episode.__post_init__` at `s09_study_protocol.py:161` refuses any episode
whose `arms` tuple is not exactly `ARMS`, and `_ordered_episodes` at line 1246
assigns every panel cell all three arms. Every episode therefore runs the same
three treatments on the same task, in the same order, with
`DISPATCHING_ARMS = ("P1", "P2")` fixed at line 63.

`grep -n -i 'represent' experiments/ad01/s09_study_protocol.py` returns nothing.
The representation vocabulary lives in a different module
(`s09_verdict.REPRESENTATION_BINDING` at line 365) which runs pytest files, not
study arms.

This is the central fact of the review. The handoff asks for three
representations crossed with experience treatments across worlds. The frozen
protocol has neither factor. The two questions that require them cannot be
answered by this apparatus, and no amount of budget fixes that.

## Findings

| # | Severity | Location | Claim | Status |
|---|---|---|---|---|
| 1 | Critical | `s09_study_protocol.py:59-63,130-134,1246-1261` | The frozen protocol has no representation axis and no experience axis. Representation choice is not separable from experience treatment because representation is absent from the design. | CONFIRMED |
| 2 | Critical | `s09_verdict.py:812-830` | `transfer_verdict` reads `true` on a graph task where a software-scoped policy scored 0.0 and no control was compared. It measures that bytes ran, not that behavior transferred. | CONFIRMED |
| 3 | Critical | `s09_verdict.py:735-764` | `task_utility_verdict` issues `win` from a single shared task. No minimum n, no cluster, no per-family table. Executed proof below. | CONFIRMED |
| 4 | High | `splits.py:466-467` | `generate_ad01_graph` gives `within` the same spec list as `dev`. All 9 dev/within graph pairs in the frozen panel are isomorphic. `within` carries no structural transfer. | CONFIRMED |
| 5 | High | `s09_panel_inventory.py:18,186,189` | Clustering is by `(family, template)`. Software has 4 clusters, below the 6 required at alpha 0.05. The panel cannot support a software significance claim. | CONFIRMED |
| 6 | High | `s09_panel_inventory.py:125-140` | `canonical_graph_form` enumerates all `n!` vertex permutations. A 9-vertex graph takes 52 s, a 10-vertex graph about 15 min. The inventory CLI is unusable on the frozen panel. | CONFIRMED |
| 7 | High | `offline_recompute.py:22-28,1648-1665` | The verifier hashes its own source against digests frozen in an earlier commit. Every frozen bundle fails `frozen-source-mismatch`, so no clean baseline exists. | CONFIRMED |
| 8 | High | `offline_recompute.py` (absent) | Resumed-count rollback has no detector. `grep -c 'resum'` returns 0. The module declares `external_operation_store_checked: False` at line 1451. | CONFIRMED |
| 9 | Medium | `offline_recompute.py:1735-2334` vs `1461-1601` | Hidden-answer contamination detectors exist only on the output path. The 141-line M4 path has no occurrence of `score`, `private`, `target`, or `oracle`. | CONFIRMED |
| 10 | Medium | `tests/test_m4_offline_recompute.py:516-524` | `test_disconnected_artifact_is_refused` asserts `executed-source-not-frozen`, which is repertoire membership, not connectivity. | CONFIRMED |
| 11 | Medium | `tests/test_boolean_ast_arm.py:437,447` | The AST suite fails on a loaded machine. The 1000 ms wall timeout yields a wall-timeout refusal where an `IndexError` is expected, so `mechanism_verdict` reads `unproven` for a healthy representation. | CONFIRMED |
| 12 | Medium | `packet.py:109-126` | `visible_context` is the only function that raises on a protected-use reference. It has no caller outside its own test. `trajectory.admit_investigation:1873-1879` reimplements the check separately. | CONFIRMED |
| 13 | Medium | `improve_channel.py` (absent) | Question 5 requires evaluating descendants. `grep -c 'descendant\|cohort'` returns 0. No descendant evaluation exists. | CONFIRMED |
| 14 | Medium | `rotation.py:20-33` | The R arm's investigation order is a human-authored fixed schedule. `trajectory.py:516` falls back to `scaffolding_proposer`, which pins the task id. Question 4's "if every trajectory follows the same authored schedule, call the treatment inactive" is met. | CONFIRMED |
| 15 | Low | `s09_study_protocol.py:1003-1032` | `DescriptiveOnly.is_significant` is a hardcoded `return False`. The descriptive-only posture is a constant, not a computation. | CONFIRMED |

## The finite target support

Computed with `splits.ad01_content_key`, the function the codebase already uses
for leakage checks, applied to the committed freeze.

| Panel subset | Task cells | Distinct targets | Duplication |
|---|---|---|---|
| Full panel, 3 worlds | 54 | 46 | 1.17x |
| Study worlds 1 and 2 | 36 | 33 | 1.09x |
| Claim splits, worlds 1 and 2, within + transfer | 24 | 22 | 1.09x |

Distinct targets per `(family, template)` cluster, full panel:

```
(graph, 'C5+joined-by-path')     1
(graph, 'C5+shared-edge')        1
(graph, 'C5+shared-vertex')      4
(graph, 'C5+tree')               4
(graph, 'C7+tree')               6
(graph, 'C9+tree')               3
(software, 'stale-clear-core')   6
(software, 'stale-clear-del-core') 3
(software, 'stale-read-2chain')  12
(software, 'stale-read-3chain')   6
```

Two of the ten graph clusters hold exactly one distinct target across all
three worlds. A cluster with one member is not a comparison.

Six exact-duplicate groups exist, each a set of distinct task ids sharing one
content key:

```
ad01-w0-dev-gr-00       == ad01-w1-dev-gr-00
ad01-w0-within-gr-00    == ad01-w2-dev-gr-00
ad01-w0-dev-gr-02       == ad01-w0-within-gr-02
ad01-w1-dev-gr-02       == ad01-w2-within-gr-02
ad01-w0-transfer-gr-01  == ad01-w1-transfer-gr-01 == ad01-w2-transfer-gr-01
ad01-w0-transfer-gr-02  == ad01-w1-transfer-gr-02 == ad01-w2-transfer-gr-02
```

The handoff says "more trials on identical hidden targets do not create more
independent evidence" and "do not create apparent replication by relabeling
duplicate tasks". Both describe the committed panel.

The three graph transfer clusters hold 3, 1, and 1 distinct targets. The
entire structural-transfer arm for the graph domain rests on five distinct
graphs.

### Target identity is checked in one place and not the other

The handoff names this as a requirement: the panel inventory must verify target
identity, not distinct RNG seeds. The code does both, unevenly.

`splits.generate_ad01_graph` at lines 470-481 does check. It builds an `avoid`
set of dev content keys and skips any generated task whose key is in it:

```python
avoid = set()
if kind != "dev":
    for pos in range(3):
        avoid.add(ad01_content_key(generate_ad01_graph(world, "dev", pos)))
for salt in range(64):
    task = _build_ad01_graph(seed, world, kind, index, spec, salt)
    if task is None:
        continue
    if ad01_content_key(task) in avoid:
        continue
    return task
```

This is real dedup and it is why `ad01_content_key` shows 3 intersections
rather than 27. But it only avoids the three dev tasks in the same world. It
never compares against the other two worlds, which is how the six duplicate
groups above survive.

`software` gets no dedup at all. `generate_ad01_software` at lines 377-429 has
no `avoid` set. The software rows happen to come out distinct, which is luck
of the seed derivation rather than a property anyone checked.

`s09_panel_inventory` never calls `ad01_content_key` at all. It clusters on
`(family, template)` at line 186, which is a coarser grouping that hides
duplicates inside a cluster, and its isomorphism check at lines 143-161 is
restricted to graph dev/within pairs only. Software duplication and all
cross-world duplication are invisible to it.

`s09_study_protocol._panel_cells` at lines 298-317 reads `task_id`, `family`,
`template`, `world`, and `split`. It never reads the task body.

## Per-question verdict on identifiability

**Question 1, which representations can be acquired and executed.** Not
answerable as designed. The protocol runs one representation. The three-way
comparison exists only in `s09_verdict.REPRESENTATION_BINDING`, which runs three
pytest files and reports `mechanism = true` when they are green. That measures
the harness, not the model's acquisition, and `s09_m2_rubric.py` already knows
this: its docstring at lines 11-22 states that an authored program is a
mechanism witness and that an acquisition axis read from an authored record must
refuse rather than score zero. The rubric is honest. The protocol that would
feed it has one arm.

**Question 2, does experience help, and does relevant experience beat
irrelevant.** Not answerable as designed. There is no experience treatment.
P0 is authored with no model, P1 and P2 both dispatch. The only curriculum
difference is `learner.curriculum_item` at line 263, which returns a schedule
item for arm `R` and `None` otherwise, and `R` is not an arm in this protocol.
The shuffled and irrelevant controls the handoff requires have no
representation in any module.

**Question 3, does retention help on new families after cost.** Partially, and
the transfer half is broken. There is a within and a transfer split, and
`transfer_verdict` is a real code path. But two defects make the verdict
unusable. First, `within` is not a distinct family (finding 4). Second, the
verdict measures execution, not benefit (finding 2). The cost accounting the
handoff asks for is present in `checker._verify_costs` at lines 178-188, which
preserves `"unknown"` rather than zeroing it, and that part is sound.

**Question 4, can it choose useful investigations.** Not answerable, and the
code already says so by construction. `rotation.r_schedule` at lines 20-33 is a
human-authored list of six task ids per world in fixed index order.
`scaffolding_proposer` at `agenda_policy.py:40-50` pins `next_action.task_id` to
the passed `task_id` before the proposer ever runs. The handoff instructs that
such a treatment be called inactive and the experiment repaired before any
benefit claim. It is inactive.

**Question 5, can it acquire an executable revision that improves a later
cohort.** Not answerable. `improve_channel.py` is 618 lines of construction,
adoption, and probe machinery with no descendant evaluation anywhere in it. The
handoff is explicit that "a better task solver alone does not answer this" and
that the descendants must be evaluated rather than the reviser's own score.
There is no code that produces a descendant cohort.

## Can a clean offline baseline be established

No. Three independent reasons, any one sufficient.

Every frozen bundle fails. I ran `offline_recompute.verify_bundle_file` on the
committed evidence:

```
reports/evidence/invl02-output-shape-550b-r4/output-run.json   fail  16 problems
reports/evidence/invl02-r123/e12/m4-bundle.json               fail  55 problems
```

The r4 failures include `frozen-source-mismatch` against
`experiments/ad01/offline_recompute.py`, `scripts/invl02_live.py`, and
`src/settlement/gateway_http.py`.

The cause is structural rather than evidentiary. `OUTPUT_CODE_PATHS` at line 22
lists the verifier's own file. `_check_output_digest_maps` at line 1658 hashes
the live bytes on disk against digests frozen in an earlier commit. Editing the
verifier therefore invalidates every bundle it verifies, and the check cannot
return clean until the freeze is reissued against the current tree. M4's rule
that "a baseline that already fails cannot establish a successful tamper test"
is not merely unmet here. The failing check is a property of the current tree,
so it will keep failing for any bundle produced at this commit.

One of the seven required rejecting examples has no implementation. Resumed-
count rollback is absent; the string `resum` does not appear in the file, and
the module's own `verification_scope` at line 1451 reports
`external_operation_store_checked: False`. The count checks that do exist at
lines 1854-1872 compare a bundle against itself in a single pass, which is
structurally incapable of detecting a cross-run rollback.

The synthetic fixture baseline is clean. `tests/test_m4_offline_recompute.py`
passes 45 of 45 against `demo_bundle()`, a hand-built in-memory bundle. That
qualifies the detectors. It says nothing about the frozen evidence, and M4 asks
for the frozen evidence.

## Multiple comparisons

Nothing in the pipeline makes an inferential claim. The posture is
descriptive-only and it is enforced: `Power.supports_significance` at line 383
returns whether every domain is powered, `DescriptiveOnly.is_significant` at
line 1019 returns `False`, and `build_protocol` at line 1316 wires both into the
emitted protocol. On the frozen panel software sits at 4 clusters against a
required 6, so `supports_significance` is `False` and the study correctly
declines a significance claim.

The gap is not a missing correction. It is that the descriptive reports are
themselves under-powered per family and are not clustered when they are read.
`BENEFIT_MARGIN` at line 70 is a fixed 0.1 threshold applied to a within-scope
delta with no cluster structure behind it, and `task_utility_verdict` averages
a raw mean over however many shared tasks happen to exist. The margin is a
decision rule, not a test, which is defensible. The unclustered mean behind it
is not, and `worlds.audit_tasks` already knows that dev and use must not share
content.

## What the next engineer inherits

Three separable things, in the order that unblocks the others.

The representation and experience factors have to enter the protocol as real
arm dimensions before any of questions 1, 2, 4, or 5 can move. Right now they
are documentation of an intent. `s09_arm_parity` has the machinery
(`ArmRegistry`, `compare_arms`, `REPRESENTATION_KINDS`) and it is not wired to
the study driver.

The panel needs new generation families before it can be powered. Software
needs two more clusters; the graph transfer arm needs to stop resting on five
distinct graphs. Extending `generate_ad01_graph`'s existing `avoid` set to
cover all three worlds, and giving `generate_ad01_software` the same treatment,
is a small change that makes cross-world duplicates impossible.

`within` needs to mean something. As it stands, `AD01_GRAPH_DEV_SPECS` and the
`within` branch of `generate_ad01_graph` at line 466 are the same tuple, and all
nine dev/within graph pairs are isomorphic. Until that is fixed, the within and
transfer arms measure the same thing.

Finally, `canonical_graph_form` should be replaced with a refinement-based
canonical form. At 52 s for a 9-vertex graph the inventory is not runnable, and
an instrument nobody runs is not a check.

## Notes on method

Two claims I tried to break and could not. The `ad01_content_key` dedup in
`generate_ad01_graph` is real and load-bearing; removing it would raise the
dev/use intersection from 3 to 27. And the `"unknown"` handling in
`checker._verify_quality` at lines 133-141 and `offline_recompute`'s accounting
path is correct: an unmeasured quantity is preserved and reported as
unevaluable rather than scored as zero, which is the right treatment and worth
keeping.

One claim I had to correct mid-review. My first independent isomorphism check
reported zero isomorphic pairs, which contradicted the frozen inventory's nine.
My backtracking canonical form was wrong. A direct vertex-permutation mapping
confirms all nine. `s09_panel_inventory` is right and I was not.

The AST suite failure (finding 11) is load-dependent. This machine has 2 CPUs
at load average 49. Running the single test three times gave two failures and
one pass. The underlying defect is that a 1000 ms wall timeout in an assertion
about exception text is not reproducible on shared hardware. The verdict
consequence is real regardless of which way it lands on a given run, because
`mechanism_verdict` returns `unproven` whenever any suite is not green.
