# Stage 9 Generality Campaign — M0 to M5 Report

> **WITHDRAWN. The M3 live-acquisition claim in this report is withdrawn.** An independent
> review, [S09R-01 to S09R-03](../reviews/STAGE-09-GENERALITY-LIVE-REVIEW.md) at `96dfa18`,
> found two defects in `evidence_s09_m3_live/` that together make the acquisition
> evidence unusable. Acquisition is **UNPROVEN**. It is not disproven. The run was
> contaminated, so this bundle supports no conclusion about the model's capability in either
> direction.
>
> **S09R-01. The purported live P1 construction carries a double identity.**
> `evidence_s09_m3_live/freeze.json` declares `mode: "live"` and the model
> `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`, while
> `evidence_s09_m3_live/construction.json` persists
> `construction_requests[0]["model"] == "recorded-double"` for P1. The doubles dry run and the
> live run shared one database, and deterministic operation ids let the live run reuse
> already-settled double receipts. The claim that one live call acquired P1 is withheld.
> This finding is confirmed by recomputation and stands.
>
> **S09R-02 as the review stated it is INCORRECT, and is corrected here.** The review inferred
> that the bound policy did not govern use because the four P1 use records carry
> `executed_source_digest == 3834317f66d4fb086d9e4cc93c36c0b08e4a108478dd26b776de66ea04c58685`,
> the authored `METHOD_SOURCE` constant at `scripts/s09_pilot.py:299`. That inference is a
> category error. `executed_source_digest` records the **task method**; a policy that selects a
> method is expected to leave a method digest in the record. Across all 24 records that field
> takes only three values, the authored method, the incumbent fallback, and empty. **No record's
> `executed_source_digest` equals any policy source.** Requiring it to equal the bound digest
> fails every clean bundle.
>
> **The real defect is worse, and it is a different one.** A use record carries two policy
> fields, `policy_digest` and `executed_policy_digest`, and both hold the bound digest
> `b71a7f8f...` on the P1 software records. But `scripts/s09_pilot.py:547` and `:549` write them
> as `expected or executed` and `executed or expected`, where `expected` is the bound digest. The
> field is therefore backfilled from the freeze whenever the store read yields nothing, and
> **cannot distinguish a real execution from a copy.** The disambiguating list
> `executed_policy_digests`, which a populated value would have proved a store read, is never
> persisted and is `None` on all 24 records. No use record carries `policy_actions` or
> `dispositions`, so the policy's admitted decision is absent from the use evidence entirely.
>
> **The "acquired" method member is an authored constant.** The frozen `method_repertoires` are
> byte-identical across P0, P1 and P2. Their member is labelled
> `capability_id: "acquired-sw-3834317f"` with `authored: False`, and its `source_digest` is
> `3834317f...`, the authored `METHOD_SOURCE`. The label is false. This is true of every arm
> including the P0 control, so it is a property of the shared development repertoire design
> rather than contamination specific to the live bundle.
>
> **The corrected finding.** S09R-01 stands: the acquisition provenance is contaminated. On the
> use phase the evidence is **unproven rather than proven** on the original charge, and the
> supportable claim is that the bundle cannot show the bound policy governed use, while the one
> member presented as acquired is an authored constant. Requalification must persist the
> executed digest list, persist the admitted action, and stop backfilling the policy digest from
> the freeze.
>
> **S09R-03. The offline verifier passed the bundle despite both facts.**
> `scripts.s09_verify.verify_bundle_dir('evidence_s09_m3_live')` returned `pass` with zero
> problems. It confirms that a use-method digest belongs to a frozen repertoire and that a
> policy digest is present. It does not require the two to be equal.
>
> **What still stands.** The three mandated representations are integrated and tested at their
> reported scope. Nothing in this withdrawal touches the shared action contract in
> `policy_action.py`, the second world, the frozen M2 selection rubric, the scoring-integrity
> gate, or the two new software generation families. The representation work and its tests are
> unaffected by the live run's contamination.
>
> **What is suspended.** All five M5 verdicts. Each was issued against the contaminated run and
> each is reissued from a clean run or not at all. The `keep/simplify/replace` decision at the end
> of this report was issued against the withdrawn evidence and has no current standing.
>
> **Correction path.** A requalification run needs its own database, with no doubles dry run
> against it, so a settled double receipt cannot be replayed. The construction record must persist
> the live model id for every construction request. The use phase must execute the bound policy's
> own bytes after a fresh-process restart rather than copying a digest onto an authored method.
> The verifier must require `executed_source_digest == bound_digest`, and must fail on a
> `recorded-double` request inside a freeze that declares `mode: "live"`.
>
> The prior report text and `evidence_s09_m3_live/` are preserved unchanged. The withdrawn
> sections below are marked superseded in place rather than deleted, so a reader can see what was
> claimed and when it was withdrawn.

Scope: three mandated policy representations (Python `STEP`, compact typed AST, small
action/decision graph) driven through one shared action contract across more than one world,
with a frozen selection rubric, a powered panel, an improvement study, and independent
falsification.

Evidence levels used throughout: **observed** (I ran it, command and output given),
**worker-reported** (an agent claimed it, not yet independently re-run), **design-selected**
(chosen before results, frozen), **untested**, **blocked**.

---

## Headline

**All three mandated representations are integrated, merged, and independently verified on the
merged tip**, together with a second world, a frozen selection rubric, and a scoring-integrity
gate. **113 tests pass across all three arms, both worlds, the shared contract and the rubric.**

**M2 is complete: all three mandated representations are integrated and verified, with a frozen
rubric that refuses to name a winner among authored programs.** Every blocker the campaign
identified outside M2 itself is now closed. **M3 has not run and M4 is not eligible**, so no
capability claim is made in either direction.

Final state: **195 tests pass** across three arms, two worlds, the shared contract, the frozen
rubric, the parity harness, the panel census, the scoring-integrity gate, the gateway route
gate, the sibling-import gate, the family generator and the acquisition audit. The 40-file
regression intersection is **450 passed / 101 skipped / 0 failed**, against **446 / 4** at the
pre-campaign baseline: **all three pre-existing failures are closed** and the campaign
introduced none.

The governing findings are both negative, and the second undercuts the first.

1. **The power shortfall was 2 software generation families, and is now closed.** 54 tasks
   reduce to 10 independent clusters by `(family, template)`, of which software had 4, where a
   perfect two-sided sign sweep is p = 0.125 against a required 0.05. My earlier figure of "roughly
   14" was wrong because it treated the three worlds as independent replications; they contain
   the same 10 clusters. Two new families are now generated and merged, both a different class of
   fault from the four existing caching families, taking software to 6 clusters. A relabelled
   copy of an existing family is proven not to count as new.

2. **The live-acquisition negative is void, and the committed evidence cannot say why.** The
   gateway defect is fixed and confirmed: the pilot built its adapter without `expected_route`
   while `route_mode` defaulted to `"free"`, so every request was refused before dispatch, and
   all three arms are available under the fix. Recomputing the recorded run from the committed
   bytes shows **0 of 24 records show a model producing a policy**, so the negative cannot be a
   capability result. It also cannot be attributed to the route defect from those bytes, because
   the only trace of the missing responses is `outcome: unknown` with entirely null usage, and
   the receipts record **neither `response_received` nor `response_digest`**. A pre-dispatch
   refusal and a response lost in flight are indistinguishable in this evidence. The audit's
   verdict is **undecidable**, which is reported rather than resolved toward the convenient
   cause.

> **This paragraph is unaffected by the withdrawal and still stands.** It concerns the *original*
> recorded study, not the re-run in `evidence_s09_m3_live/`. The withdrawal removes the re-run's
> positive acquisition claim. It does not rehabilitate the original negative, which was already
> reported as undecidable rather than as a capability result. The project currently holds **no
> live-acquisition result in either direction**, and the one gap between the two is now the
> requalification run.

---

## What is integrated and verified

### Action/decision graph arm — merged, `af86f3d`

`experiments/ad01/boolean_graph_policy.py` (348 lines), `tests/test_boolean_graph_arm.py`
(308 lines).

The third mandated form, expressed over the existing Boolean world through the existing
shared contract. No new world, no new dispatcher, no second action vocabulary.

The distinguishing property is **local failure**. Running the loader, each of these is
rejected at load time naming the offending node rather than the whole document: an
unreachable node, a cycle that cannot reach a terminal, a guard referencing an unknown
field, a bad fallback, and a policy-id mismatch. The Python `STEP` arm cannot do this. A
one-character Python syntax error costs a whole model call; a typed node costs one edit.

**Observed, by running the real view builder on a real task, not by reading the test.** The
view handed to a policy is a strict subset of `boolean_active.public_state`. The task seed
`5201`, the template name `C5+tree`, and the edge structure are all absent from the
serialized view. The view is 573 bytes.

Gates, run by me on the merged tip: graph arm 12 passed; graph arm plus bridge, world and
contract 57 passed; with the second world added, 67 passed.

The module contains no `eval` or `exec`, and the test proves it does not call
`run_policy_step` by monkeypatching that name to a tripwire.

### Second world — merged, `665a2ec`

`experiments/ad01/second_active.py` (204 lines), `tests/test_second_active_world.py` (169
lines).

Until this commit, every transfer claim in Stage 9 rested on a single world, where a
memorized policy and a general one are indistinguishable. This world is
constraint-satisfaction **ordering**: it hides a total order over four named jobs, a `probe`
compares two jobs, and `construct` commits one permutation. The Boolean world queries
independent integer indices and commits four truth tables, so a predictor cannot be reused
as a schedule.

**Observed.** Both worlds expose the same five-function driver surface, and `public_state`
emits the identical eight-key set with the budget present both at top level and inside the
action schema, so one driver serves both. Neither `tables` nor `seed` appears in the view. A
Boolean-shaped policy probed into this world is refused, and the episode ends uncommitted
with `final` `None`. That refusal is the property that makes this a transfer test rather
than a re-skin.

Gates: second world 10 passed; boolean world plus shared contract 35 passed.

### Frozen M2 selection rubric — merged, `be7f7ef`

`experiments/ad01/s09_m2_rubric.py` (723 lines), `tests/test_s09_m2_rubric.py` (355 lines,
27 tests).

Stage 9 requires an independent panel to select a representation for scale-up, to record
reasons for rejected forms, and to **not retrofit the rubric after results**. This freezes it
before any arm's numbers exist. A SHA-256 over the canonical axis table is re-verified on
every `select()` call, so a post-hoc edit to the axes, weights, margin or rule **raises**
instead of scoring silently.

**The load-bearing decision is the evidence class carried per axis.** Model construction
success and search efficiency are `model-acquired`. Executable coverage, intervention cost and
behavior sensitivity are `mechanism-witness`. The guard keys on **provenance, not on an
attempt count an arm could inflate**, so a witness arm cannot manufacture a numerator out of
authored bytes.

**Observed, by running it.** Scoring the current panel of three authored programs returns
`Insufficient`, and `Insufficient` has **no `selected` attribute at all**. The rubric cannot
report a winner for a panel that has only demonstrated mechanism. That refusal is exactly
what the M4 authored-program constraint requires, enforced in code rather than in a note.

`search_efficiency` is the single axis that may go unmeasured, and only when
`constructed_attempts` is zero, through a field the axis itself declares. It carries weight
zero, so it is reported without being a lever. There is no default score and no rescue path.

The selection weights (construction 1/5, coverage 2/5, cost 1/5, sensitivity 1/5, search 0/5,
margin 0.05, ties refused) are a frozen judgment made before results. They are now unchangeable
without a new freeze, which is the point of freezing them early.

### Typed AST arm — merged, `fac6cc5`

`experiments/ad01/boolean_ast_policy.py` (615 lines), `tests/test_boolean_ast_arm.py`
(519 lines).

The second mandated form, and the one that makes the comparison meaningful. A closed typed
interpreter over JSON node types, with no `eval`, no `exec`, and no import of any
document-derived value. Load enforces 256 nodes, depth 32, 64-bit integers and 64 statements per
block, so the interpreter is **bounded**. It is **not** *total*, and the distinction is a
retraction: an earlier draft of this report called it total, which the loader does not enforce.
It accepts a `block` whose only statement is an `assign`, an `assign` at the root, and an `if`
that returns in one branch and assigns in the other. Severity is low, because driving such a
program produces a legal terminal `stop` carrying
`bridge_refusal: "$.policy_ast.entry: statement did not return an action"`, with no exception
escaping `run_episode`. But the gap is real: a model would learn that a well-formed,
non-terminating program is admitted at load and fails only later, which is precisely the early
local failure the arm exists to provide. A load-time `NO_RETURN` check is the right fix and is
**not yet implemented**.

**The grammar required two corrections to my brief, both found by the unit and neither by me.**
The first had no sequencing construct, so `assign` could never be followed by `return_action`.
The second had no list or map constructor, so the program could only commit a **fixed**
predictor, which would have satisfied "commits an outcome" while proving nothing about
derivation. The defect was in the *acceptance criterion* as much as in the grammar. The added
`block`, `list` and `obj` forms are closed, enumerated and capped, not a general escape hatch.

**Derivation verified by running the same program on four tasks.** The program probes `x=3`,
reads the returned `y`, and builds four `specs` through `list`, `obj` and `index`:

| task observation | derived consts | committed |
|---|---|---|
| `(0, 1, 0, 0)` | `[0, 1, 0, 0]` | yes, 1 query |
| `(1, 0, 0, 1)` | `[1, 0, 0, 1]` | yes, 1 query |
| `(1, 0, 0, 0)` | `[1, 0, 0, 0]` | yes, 1 query |
| `(0, 1, 1, 0)` | `[0, 1, 1, 0]` | yes, 1 query |

A hardcoded predictor cannot produce that correspondence. This is the check that distinguishes
the two, and it is why criterion 1 was treated as unmet until it existed.

**Local failure is the arm's distinguishing property.** A program valid except for one deep node
is refused naming that node's path: `$.policy_ast.entry.else.inputs.key: add requires two
numeric operands`. The Python `STEP` arm cannot reject at node granularity, where a
one-character syntax error costs a whole model call.

The artifact digest is over canonical JSON AST bytes, not Python source, so the record names the
bytes that actually ran. Policy identity is checked through `load_policy(record,
expected_policy_id=...)` rather than by widening `choose_action`, which would have broken arm
parity with the other two representations.

**Bounded honestly.** Execution is a private bounded child process. That is mechanism-witness
execution, **not** a durable broker or `LocalLauncher` operation receipt.

### Scoring integrity — merged, `1b86979`

`tests/test_s09_scoring_integrity.py`. A policy cannot state its own result, and the mechanism
is structural rather than incidental: `parse_action` refuses any action carrying a field outside
the declared vocabulary, so a score cannot be smuggled through the boundary at all.

**Mutation-tested rather than trusted.** Disabling the contract's exact-field rule turns the
assertion red with `an action carrying 'score' parsed, so a policy could claim a score of its
own`; restoring it turns the file green. A green test that cannot go red proves nothing.

This clause was originally assigned to a delegated unit that wrote nothing in 23 minutes. The
work was done directly and is recorded as such rather than attributed to the worker.

---

## The binding constraint: the panel cannot be powered

**Observed.** The frozen inventory in `experiments/ad01/worlds/manifest.json` contains
exactly 54 tasks: 3 worlds × 3 splits (`dev`, `within`, `transfer`) × 2 families
(`sw`, `gr`) × 3 tasks, each with its own digest under `freeze_id: ad01`, `version: AD01/1`,
and a `benefit_rule_digest`.

The uniformity is the problem. The three worlds are not independent replications; each
contains the *same* ten clusters. Software contributes **four** clusters. A perfect sweep
across four clusters is a two-sided sign test with a minimum attainable **p = 0.125**.
Significance at alpha 0.05 is unreachable **at any effect size**, so no amount of additional
data within these families can fix it.

**What would fix it is families, not cells.** M3 requires at least two generation families
per world. Reaching 24 clusters needs on the order of 14 new family-disjoint generation
families, not 14 more cells. Each new family is a generator, not a row.

A prior measurement in this campaign reproduced 9 isomorphic `dev`/`within` graph pairs
within the same world, by brute-force canonical form. They are isomorphic up to vertex
relabeling, which a template-level audit cannot see, and the duplicate guard compares
literal labels so it reports clean.

**Consequence.** If the generator work does not produce enough independent families in
budget, M3 reports as **inventory-limited**. It will not manufacture a p-value, and it will
not pool across the three worlds to manufacture clusters, because those worlds are not
independent.

An independent unit is re-deriving this census from source right now. Its numbers will
either confirm these or refute them, and the report will be corrected either way.

---

## Test accounting, corrected

**Observed.** The earlier ledger entry recorded `518 passed, 12 failed, 132 skipped` on tip
against `499 passed, 14 failed, 120 skipped` on baseline `67c4429`, and declined to call
that zero regressions because one difference was unexplained. The difference is now
explained and it was a **denominator mismatch, not a regression**: reconstructing the
bounded selection from its own stated keyword rule gives 44 files on tip, of which **4 do
not exist at baseline** — `test_boolean_policy_bridge.py`, `test_checker_measure_provenance.py`,
`test_control_execution_gate.py`, `test_wf_replay_immutable.py`. Different file sets are
different denominators.

On the **40-file intersection**, the same selection on both commits:

| commit | passed | failed | skipped |
|---|---|---|---|
| baseline `67c4429` | 446 | 4 | 101 |
| tip | 447 | 3 | 101 |

The one difference is `test_broker_route_recovery.py::test_workflow_replay_never_calls_dispatch_again`,
which **fails at baseline and passes at tip**. One fixed, zero introduced.

The three failures common to both are `test_ad01_traj.py::test_kill_after_publication_resumes_without_duplicate_spend`
and two `test_s09c3_policy_pilot.py` cases, the latter both dying on
`ModuleNotFoundError: No module named 'fault_tasks'` from `experiments/doubles.py`. That
missing module is a real, still-unfixed defect.

`518/12/132` could not be reproduced by re-running the selection it describes and is
superseded by the table above.

---

## The honesty constraint that governs M2 and M4

Stage 9 states verbatim:

> Use authored programs only as explicit controls and mechanism witnesses. Avoid presenting
> typed-DSL success with a handwritten AST as model learning.

**Both new arms are hand-authored programs.** The graph arm and the AST arm demonstrate that
a representation can *express and execute* the strategy. They are **not** evidence that a
model can acquire that strategy, and no such claim is made here. The frozen rubric carries
evidence class as a first-class field per axis so an authored result cannot be silently
scored on the same scale as an acquired one.

M4 is consequently **not yet eligible**: an eligible candidate must be an *acquired*
operational policy. If none exists, the campaign records why and performs a bounded
deterministic mechanism study **without** a recursive-improvement claim.

---

## A control that genuinely fails

**Observed.** Once the control gate was made to actually execute rather than read a
committed file, it reported a real failure. Of 12 controls executed against a scratch
database, 11 were `True` and `C-ctrl-sw-invalid` was `unsupported`. **The representation
pilot is not currently clean.** Any earlier "checker clean" statement for it was clean under
a gate that read a file rather than running the control, and is bounded accordingly.

---

## Inherited liability

**Observed.** Enumerating every row of `reservations` in `invl02_live` finds **5563 units**
unsettled across two studies: r4's **2294** and an older AD01 reservation of **3269** dated
2026-09-23, whose operation is `unresolved/unresolved` with a lost-response-shaped receipt,
so it is a real terminal state rather than an empty row. Computing liability from r4 alone
understates prior exposure by 3269. This campaign has spent **zero** and added no exposure.

r4 must not be replayed.

---

## Corrections the orchestrator made against itself

Recorded because a ledger that only accumulates its own conclusions is not an audit trail.

1. **An overstated contamination claim was retracted.** Seeds are genuinely shared across
   `within` and `transfer`, because `AD01_KINDS` has three kinds while the seed bases carry
   only `dev` and `use`, and `_ad01_seed` maps every non-`dev` kind to `use`. But both
   generators salt their RNG by kind, so a shared numeric seed does **not** produce shared
   hidden content. The correct description is bookkeeping fragility, not hidden-answer
   leakage.
2. **A reviewer's finding was passed on without checking it.** I cited `run.py:1154` as
   binding the null controls without establishing its enclosing function; it is inside
   `run_attribution`, not `run_control`. The lane pushed back with the correct function and
   source lines, I verified by resolving the enclosing definition, and withdrew the finding.
3. **A briefed constant was wrong and I had to correct three running units.** The briefs
   stated `MAX_QUERIES` is an attribute of `boolean_active`. Running it raises
   `AttributeError`; the constant is `boolean_rule.MAX_QUERIES = 8`. The value was right and
   the module was wrong, which is the most dangerous shape of briefing error, because an
   agent that trusted it and never ran it would have written code against a fiction.
4. **The regression "delta" was a denominator mismatch**, explained above.
5. **I ran `git rebase -i --root` to remove a duplicated commit subject.** It replayed the
   entire history and stopped on a conflict in `tests/test_broker_dbos.py`, leaving `HEAD`
   at an unrelated R02 commit. Recovered with `git rebase --abort`, which restored the exact
   tip with no loss. The duplicated subject remains, deliberately. A cosmetic rewrite of
   published history is not worth the blast radius, and `--root` on a shared branch is never
   the right tool for tidying a message. **No history rewriting on this branch from here.**

---

## Status against the milestone definitions

| Milestone | Status | Note |
|---|---|---|
| M0 baseline and plan | complete | — |
| M1 shared action and world semantics | complete | one contract, two worlds, verified |
| M2 three representation pilots | **complete** | three arms integrated, 47 AST tests, rubric frozen and live-verified |
| M3 large prospective study | **run, claim withdrawn** | the re-run against the fixed gateway exists in `evidence_s09_m3_live/`, but [S09R-01 to S09R-03](../reviews/STAGE-09-GENERALITY-LIVE-REVIEW.md) found it contaminated. Acquisition is unproven. The **recorded** study is void and superseded |
| M4 improvement study | **ineligible, recorded** | the acquired policy is a task solver, which M4 excludes by name. The acquisition premise of this row is itself withdrawn |
| M5 falsification and decision | **issued, then suspended** | five verdicts issued against the contaminated run, all five now suspended pending reissue. The decision has no current standing |

**RETRACTED. What M3's run did and did not establish.** This paragraph originally read that
M3 "established that **live acquisition works**: a model call produced a policy, it bound, and the
executed bytes are its own, verified by recomputing the digest chain," and that the acquired
policy and the authored reducer tie on all four shared tasks.

**Correction, from `reviews/STAGE-09-GENERALITY-LIVE-REVIEW.md` (S09R-01, S09R-02,
S09R-03).** None of the three claims is supported by the bundle. The construction request
persists `recorded-double` under a live freeze, so no evidence shows a live model produced the
policy. The use records execute the authored `METHOD_SOURCE` at `scripts/s09_pilot.py:299`, not
the bound policy, so the digest chain was recomputed over two different objects. The four-task
tie is a comparison between an authored reducer and an authored method, so it is not an
acquisition result at all. What M3's run establishes is a mechanism result. It establishes that
the pilot completes 16 episodes and 24 use records against a live route. Acquisition is
**unproven, not disproven**: the run was contaminated, so the evidence supports no claim about
the model in either direction. The panel also remains at the frozen 4-cluster software study; the
two new generation families bring it to 6 clusters for the *next* study.

**The single most important structural finding.** The campaign's original negative was produced by
a **broken harness**, and every component was behaving correctly while the system reported a
confident wrong answer. A gateway that refuses every request before dispatch is
indistinguishable, in the recorded evidence, from a model that cannot do the task. The only trace
of the missing responses is `outcome: unknown` with null usage, with no `response_received` and no
`response_digest`. **Making a refusal distinguishable from a capability failure is the top
architectural change this campaign implies.**

---

## M5: five separate verdicts

> **SUPERSEDED. All five verdicts below are suspended.** They were issued against the
> contaminated M3 run described in the withdrawal notice at the top of this report. Verdict 1
> rests on the representation work, which is untouched by the contamination, but it was issued in
> the same pass and stands reissued only on that narrower basis. Verdicts 2 through 5 all
> depend on the live-acquisition claim and have no evidentiary basis while it is withdrawn.
> The text is preserved unchanged so the reasoning that was applied stays auditable. None of it
> may be cited as a current result. The five verdicts must be reissued from a requalification
> run whose construction request persists the live model id and whose use phase executes the
> bound policy's own bytes.

Stage 9 M5 requires five verdicts reported separately: mechanism, live acquisition, task
utility, transfer, recursive improvement. All five are now issuable on gathered evidence. Two are
positive, one is a tie, one is negative and ineligible, and one is narrow.

> **Reading the "all five are now issuable" sentence below: it is false as written.** Five
> verdicts were issued, but two of them rest on evidence that a later review found unusable.

### 1. Mechanism

**POSITIVE, narrow. Stands on the representation work alone.**

All three mandated representations execute through one shared contract, in two worlds.
Verified by running, not by reading tests: the graph arm commits in one query and can stop with
all 8 unspent; the AST arm derives a predictor that tracks its observation exactly across four
tasks; the ordering world refuses a Boolean-shaped policy and ends uncommitted; the frozen rubric
refuses to score an all-witness panel at all.

Bounded by two things I found by testing my own claims. The interpreter is **bounded, not total**:
I called it total in a commit and a report, and running it showed the loader accepted programs that
return nothing. That is now refused at load. And the AST arm reuses the graph arm's private
helpers, which three arms importing another arm's internals will not survive a fourth time.

### 2. Live acquisition

**WITHDRAWN. Was issued as POSITIVE, "first time demonstrated". Now UNPROVEN.**

> **RETRACTED IN FULL, including the two byte-identity claims quoted in bold below.** The review
> at `96dfa18` names the specific facts. S09R-01: `freeze.json` declares `mode: "live"` and the
> model `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`, while `construction.json` persists
> `construction_requests[0]["model"] == "recorded-double"`, and the doubles dry run and the live
> run shared one database with deterministic operation ids. S09R-02 is corrected above: its
> original charge was a category error, because `executed_source_digest` records the task method
> rather than the policy. The supportable finding is that the bundle cannot show the bound policy
> governed use, since the policy digest field is backfilled from the freeze, and the member
> labelled `acquired` is the authored `METHOD_SOURCE` at `scripts/s09_pilot.py:299`. The correct
> disposition is that acquisition is **unproven**. The bundle does not establish that the model
> cannot produce a policy, and it does not establish that it did. Both are open.

The sealed study's negative was void, caused by a gateway that refused every request before
dispatch. Re-run live against the fixed harness, **P1 constructed a policy in one call with
`disposition: bound`, and `bound_digest == candidate_digest`**, so the executed bytes are the
model's own. Four records execute that acquired policy, all preserved. The chain verifies by
recomputation from model bytes through bound policy to executed bytes.

Bounded by a **disclosed deviation**: the pinned model differs from the sealed study's, so this is
a new freeze and the two runs are not comparable. P2 still fails after two calls, four graph
records are `arm-domain-uncovered`, and eight hit the call cap.

**A second, independent disclosure survives and is not withdrawn.** The disclosed deviation is
real and remains on the record. The pinned model differs from the sealed study's, so
`evidence_s09_m3_live/freeze.json` is a new freeze and the two runs are not comparable. P2's
failure, the four `arm-domain-uncovered` graph records and the eight calls that hit the cap are
readings of the bundle's own record and are unaffected by the provenance defects.

### 3. Task utility

**SUSPENDED. Was issued as TIE. Now UNPROVEN.**

> **RETRACTED.** A tie between the "acquired policy" and the authored reducer is a comparison
> between two authored programs. S09R-02 shows the executed bytes were the authored
> `METHOD_SOURCE` at `scripts/s09_pilot.py:299`, so the treatment arm is not a model artifact and
> the tie measures nothing about acquisition. The four normalized reduction figures remain the
> bundle's own record; what they compare is now withdrawn.

The acquired policy and the authored reducer produce **identical** normalized reductions on all
four shared software tasks: 0.625, 0.7273, 0.7692, 0.7. Acquisition is demonstrated; improvement
is not. Since P0 is an authored program this is a mechanism-witness comparison, **not** a
representation result, and no claim about which representation is better is supported.

### 4. Transfer

**SUSPENDED. Was issued as POSITIVE on the narrow question. Now UNPROVEN.**

> **RETRACTED.** The narrow positive rested on an acquired program whose branching on
> `task['family']` was read as evidence of cross-domain coverage. S09R-02 identifies that
> branching `ENTRY` as the authored `METHOD_SOURCE` at `scripts/s09_pilot.py:299`. The branching
> was ours, not the model's, so it is not evidence of what an acquired program could cover. The
> review's own disposition table records cross-domain transfer as unproven. The second world's
> ability to discriminate a memorized policy is a property of the world and stands.

The second world discriminates: a memorized policy does not port, verified by running it. The
acquired policy was evaluated in worlds 1 and 2 but its bound scope is software, so the four
**graph** records are `arm-domain-uncovered` rather than a transfer result.

**No policy has been run in both worlds and scored in both**, so transfer is still untested at the
level the milestone means. ~~The acquired program's own branching on `task['family']` is evidence it
*could* cover both, and the world declining to evaluate it there is evidence nothing more.~~
**RETRACTED.** That branching is the authored `METHOD_SOURCE` at `scripts/s09_pilot.py:299`, so it
is not evidence about any acquired program. The retraction is against the model's credit, not
against the world. The world declining to evaluate the program there remains evidence nothing more.

### 5. Recursive improvement

**SUSPENDED. Was issued as NEGATIVE and ineligible. The negative no longer follows.**

> **CORRECTED, in the conservative direction.** The verdict was negative because the acquired
> policy was a fixed-reducer task solver, and M4 excludes that by name. The premise is withdrawn:
> the bytes executed were the authored `METHOD_SOURCE` at `scripts/s09_pilot.py:299`, so the
> "acquired policy" was never an acquired policy. The correct status is **unproven and not
> eligible**, which is the review's disposition. M4's ineligibility condition still stands on its
> own terms, because M4 requires a genuinely acquired operational policy and none has been
> demonstrated. The rubric result quoted below also comes from the contaminated run and is
> suspended with the rest.

M4 requires an acquired policy that chooses what evidence to gather, what parent inputs to use,
when to stop, and which successor to submit. P1 is now genuinely acquired, so the first clause is
satisfied for the first time. But it calls a **fixed reducer**: it is a task solver. M4 states
verbatim that "a revised task solver alone is not an improved improver", and this is precisely
that case. M4 records why it is ineligible, and **no recursive-improvement claim is made**.

**The frozen rubric now does exactly what it was built for, verified by running it.** Fed the
real acquisition record from the live run, `model_construction_success` scores the acquired arm
**1.0, measured, not blocking** — the first time in this campaign that axis has been satisfiable
at all. The authored arm on the same axis is still refused with `arm is a mechanism witness: its
program is a mechanism-witness artifact, not a model acquisition record`. So the evidence-class
mechanism works in both directions on live data, not just in a test.

> **SUSPENDED, and this is the most consequential consequence in the section.** The rubric scored
> a record `1.0` on `model_construction_success` while the record's own construction request names
> `recorded-double` under a live freeze (S09R-01) and its executed bytes are an authored method
> (S09R-02). The evidence-class gate did not catch either defect. That is a defect in the rubric's
> evidence-class test, and it is why S09R-03 matters beyond this bundle: the same gate would pass
> a future contaminated run. The gate's behavior on the authored arm is a real result and stands.
> The `1.0` on the acquired arm does not, and must not be cited.

`select()` still returns `Insufficient`, and the reasons are now precise rather than blanket:
P0 is incomplete on `model_construction_success`, `executable_coverage` and
`behavior_sensitivity`; P1 is incomplete on **`behavior_sensitivity`** alone, with
`unknown-substitution-case-verdict`. **The binding constraint has moved.** It is no longer
acquisition, which is now demonstrated. It is the sensitivity axis, which needs
byte-substitution cases that no arm in this run was given.

> **RETRACTED. The "binding constraint has moved" conclusion does not follow.** The move was
> inferred from P1's `behavior_sensitivity` being the single remaining gap, which requires P1 to
> be a genuinely acquired arm. S09R-01 and S09R-02 withdraw that. With acquisition unproven, the
> acquisition axis is a gap again, and sensitivity is no longer shown to be the sole binding
> constraint. The correct reading of the committee's output is that it returns `Insufficient`
> and that the reasons for returning it are themselves unreliable, because the evidence-class
> gate misclassified a contaminated record as a live acquisition.

---

## Decision: keep, simplify, or replace

> **SUPERSEDED. This decision was issued against the withdrawn acquisition claim and has no
> current standing.** It is preserved below unchanged so the reasoning stays auditable, and each
> item is annotated with what survives. The disposition is `withdrawn pending reissue`. The
> keep/simplify/replace ruling cannot be issued at all until a requalification run exists, because
> the rubric's own `Insufficient` return and its per-axis reasons both depend on the contaminated
> evidence, and the rubric's evidence-class gate is now known to pass such evidence. The four
> structural observations below are the parts that do not depend on the live run and are recorded
> as the only items carried forward.

**The frozen rubric returns `Insufficient`, so no representation can be named a winner, and that
is the correct answer rather than a deferral.** Issued against live evidence, the reasons are
precise: the authored arm is incomplete on three axes including the acquisition one it can never
satisfy, and the acquired arm is incomplete on `behavior_sensitivity` alone because no
byte-substitution cases were run. Naming a winner from a tie on utility with an unmeasured axis
would be the retrofitting the rubric exists to prevent.

> The `Insufficient` return itself is unverified now, for the reason above. The direction of the
> answer is unchanged and so is its motivation. No representation may be named a winner on this
> evidence, which was true before the withdrawal and is true after it.

What the evidence now supports, and what it does not:

- **Keep** the shared contract in `policy_action.py`. It is the one thing all three arms and the
  live study demonstrably agree on, and its exact-field refusal is now the mechanism that makes
  scoring integrity structural rather than a convention. **Stands.** A contract does not depend on
  the live run.
- **Keep** the second world. It discriminated a memorized policy when the Boolean world could not.
  **Stands.** The discrimination was against an authored policy in the original reading, which
  makes it a weaker demonstration than claimed but a real property of the world.
- **Keep** the staged JSON child boundary in the AST arm. It survived contact with the campaign
  and it is what lets a policy be bounded without trusting the host. **Stands.**
- **Simplify**: the AST arm reaches into the graph arm's private helpers, and the Boolean bridge
  duplicates an executor while carrying no durable DSN provenance. Three arms importing one
  another's internals will not survive a fourth, and the shared durable-state substrate now
  exists to replace the duplicate executor. **Stands.** This is a code-structure observation and
  does not touch the live evidence.
- **Replace**: nothing. No representation has earned replacement, and none has earned selection.
  **Stands as a statement that nothing is being replaced.** The selection half is suspended.
  The rubric says so in code.

**The one thing this campaign changed about the architecture.** The negative was a broken
harness. Every arm, every guard, and the frozen rubric were behaving correctly, and the system
still produced a confident wrong answer, because a gateway that refuses every request looks
exactly like a model that cannot do the task. **The architecture lesson is that a refusal and a
capability failure must be distinguishable in the evidence, and today they are not** — the only
trace of a missing response is `outcome: unknown` with null usage, with no `response_received` and
no `response_digest`. That is the highest-value change this campaign implies, and it is now the
top item in the roadmap rather than a footnote.

> **A second provenance gap is now on the roadmap above this one, per S09R-01 to S09R-03.** A
> fixture-contaminated record and a live record were indistinguishable to the frozen rubric, and
> to `scripts/s09_verify.py`, which returned `pass` on `evidence_s09_m3_live/`. The lesson is
> narrower than the one above and it is now the first gate on any requalification: an evidence
> bundle must bind the identity of the thing that produced the bytes, not merely record a digest
> of a result. A digest of a result says what ran, never who or what supplied it.

**The power position.** Software had 4 clusters where alpha 0.05 needs 6, and two genuinely new
generation families are now generated, merged and proven not to be relabelled copies. The panel is
at 6 clusters. **This does not retroactively power the study that just ran**, which used the frozen
4-cluster software panel, and I am not claiming significance it cannot support.

---

## Requalification: what was rebuilt, and why no new study ran

The correction pass added eleven modules and one gate, all of which now refuse the evidence they
were built to refuse. **No new live study was run, and the preflight gate is the reason.** This
section states what is now mechanically settled and what still blocks a run.

### The contamination is confirmed three independent ways

| Route | Evidence |
|---|---|
| Persisted request | `construction.json` P1 `construction_requests[0]["model"] == "recorded-double"` under a `mode: "live"` freeze |
| Token sentinel | All 13 model-inference receipts carry `input_tokens=5, output_tokens=5`, verbatim `_fallback_usage` at `learner.py:56`, the recorded-doubles adapter. A clean bundle's receipts show varying counts (1538/1702, 1607/2048, and so on) |
| Code mechanism | `construct.py:81` reads a settled receipt before `ensure_operation`; the operation id derives from campaign, seq, task, lineage and attempt only, so model, mode and study root enter no id |

**No live model call is recorded anywhere in that bundle.** The mechanism is proven by execution.
The antecedent, that a doubles run populated that id on that database, is **INFERRED**: no local
store predating the bundle holds this campaign's call, so it is not recoverable.

### The use phase cannot reach the policy, and this is not a digest problem

`trajectory.run_use` accepts no policy parameter and its source names no policy symbol, so the
use phase cannot reach the policy even in principle. The bound P1 policy's own action sequence is
`construct_method` then `stop`, never a use action. `scripts/s09_pilot.py:1135-1149` calls
`run_use` and **then** stamps `executed_policy_digest` onto the record; a digest written after
execution is a label.

Substitution passes with the repertoire held fixed, so a policy **can** change what an episode
does. The shipped use path simply never invokes one.

### Two silent fallbacks, both pinned red

- `run_use` answers `seed-sw-greedy` while the policy consumer refuses in the same process.
- `assessment_profile._resolve_method` at lines 200-204 defaults a missing `method_id` to
  `seed-<family>-greedy`, so a `use_method` naming no method is accepted with an empty reason.

The red tests were merged on purpose. A green test asserting today's fallback would encode the bug
as desired behaviour. Both name a repair in a file no lane owned, and both are satisfiable.

### The structural blocker beneath both

`policy_action` admits `probe, observe, construct, use, check, stop`. `policy_step` admits
`diagnose, construct_method, use_method, request_model, propose_revision, stop`. **They share only
`stop`, verified per kind.** A policy written to one contract is refused by the other. The use-phase
repair cannot be written until one vocabulary is chosen. This is a design decision, not a bug fix.

### Reissued verdicts, computed from bytes

`experiments/ad01/s09_verdict.py` issues all five with a stated basis. On the real bundle:

| Verdict | Value |
|---|---|
| live acquisition | `unproven` |
| task utility | `not_comparable` |
| transfer | `unproven` |
| recursive improvement | `ineligible` |
| decision | `prior-state` |

Utility is `not_comparable` because P1 and P0 executed the **same** method bytes, so the recorded
tie was never a comparison of two policies. A synthetic clean bundle reads acquisition `true` and
decision `keep`, so the module discriminates rather than defaulting to suspicion.

### The power position is now structural

The frozen panel gives software 4 clusters at minimum sign-flip p of `1/8`, against the 6 required
for alpha 0.05. `supports_significance` is `False` and the verdict type's `is_significant` is a
constant `False`, so **no code path constructs a significant claim from this study.** A
requalification can return `unproven` or `tie` honestly; it cannot return a false positive.

### Why no new study ran

`experiments/ad01/s09_study_preflight.py` evaluated the contaminated bundle and returned
`may_start: false` with four independent unknowns: the freeze names no moment so nothing can be
shown not to predate it; the verifier lacked the authority to judge the study; no use record
persists `executed_policy_digests`, so a backfilled digest and a digest of the bytes that ran are
indistinguishable; and a count of model calls is not a unit ceiling. It also demands a fresh human
grant before it will evaluate. Route liveness passed with real evidence.

**Four fixes block a run**, all outside every lane's scope:

1. `scripts/s09_pilot.py:1100-1116` must persist `executed_policy_digests` and `policy_actions`.
2. `build_freeze` must emit `frozen_at`, so the namespace-age check becomes measurable.
3. `trajectory.run_use` must accept a policy and refuse when it is absent.
4. The `policy_action` / `policy_step` vocabulary must be unified.

Until all four land, a new run would produce another bundle that cannot answer the question. The
honest disposition is that the campaign ends with the acquisition claim withdrawn, the mechanism
established, and the requalification path specified but not executed.
