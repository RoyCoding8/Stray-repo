# Stage 9 completion report

Branch `codex/stage-09-opus-completion`, cut from checkpoint `8e05c14`.

**Stage 9 does not close.** The mechanism is demonstrated. The empirical question is not
answered, and one defect the live run exposed is open. An independent typed review put stage
closure at 0.16 and support for any learning claim at 0.10, which matches this report.

## What a reader should take away

The policy revision cycle used to be a cycle only because test bodies called the missing
steps. Production now owns it. One public command proposes a revision, constructs and
freezes `learning-policy` `STEP` bytes, freezes a held-out panel and a finite comparison
rule before exposure, assesses the incumbent and the candidate by executing both as
policies, then binds the exact assessed bytes or records an explicit rejection that leaves
the incumbent active. A second operating-system process given only a release id resolves the
same bytes from durable state.

The live study then ran that machinery against a real provider and the free model could not
produce a valid executable policy. Both treatment arms are missing, so the study reports
incomplete and issues no comparison verdict.

## Verified, with command and observed result

| Check | Observed |
|---|---|
| Pre-change baseline, 15 original Stage 9 files | 84 passed, exit 0, 648.34s |
| Integrated gate, 22 files, before the live run | 133 passed, exit 0, 391.33s |
| Causal discrimination suites | 30 passed, exit 0, 144.90s |
| Export and offline verification suite | 13 passed, including 10 export mutations |
| Pre-launch hardening suite | red 8 failed, then 8 passed |
| Live study | exit 0, 16 episodes, 24 use records, 15 model calls |
| Offline recomputation, no provider, unreachable database | produced a verdict, status fail on 7 problems |

All deterministic runs used WSL Ubuntu, Python 3.14.4, real PostgreSQL 18.6, real child
processes. `settlement.__file__` was printed inside this checkout on every run. The rerunnable
scripts are committed beside this report. Logs are in `D:/AI/s09o/logs/`.

## The live study

Configuration frozen before the first effect, recorded in `FROZEN-LIVE-CONFIG.md`. Endpoint
`https://ai-gateway.vercel.sh/v1`, responses API shape, model
`inclusionai/ling-3.0-flash-vl-free`, real `HttpGatewayAdapter`, study root
`s09o_live_01`, freeze digest `ba94d81a`. The key was read from the environment at run time
and never written to a file, a report, a prompt or a commit; a scan of the committed evidence
for the key and for credential-shaped strings returns zero matches.

No gateway was preconfigured on this machine. Every `SETTLEMENT_*` variable was unset in the
Windows user, Windows machine and WSL environments, there was no `.env`, and no shell init
referenced a gateway. The configuration was therefore resolved from the reachable catalogue:
386 models, 78 at zero price, of which only 10 can emit text. Two were smoke tested.
`poolside/laguna-s-2.1-free` returned HTTP 503. `inclusionai/ling-3.0-flash-vl-free`
returned HTTP 200, emitted valid `def STEP(view, state):` source, and reported `cost 0`,
`market_cost 0`, `is_byok false`, `fallbacksAvailable []`, on system credentials. Zero cost
is therefore a measured billed figure, not a catalogue claim.

Spend: 19 dispatches against a ceiling of 100, comprising 4 discovery calls and 15 study
calls. The guard's `refusal_reason` is empty, so neither the ceiling nor the zero-cost abort
fired.

### Result, per arm

| Arm | Status | Construction calls | Preserved | Reduction | Changed decisions |
|---|---|---|---|---|---|
| P0 frozen incumbent | authored, available | 0 | 8 of 8 | 2.8215 | 4 |
| P1 no experience | unavailable | 1 | 0 of 8 | 0 | 0 |
| P2 with experience | unavailable | 2 | 0 of 8 | 0 | 0 |

P1 failed because its construction call `...policy-l1-init` left no settled response. P2
then failed because the construction call cap was reached. The study reports
`status: incomplete`, `missing_arms: ["P1","P2"]`, and no verdict on either `P2-vs-P0` or
`P2-vs-P1`.

This is a negative result about free-tier provider capability. It is not evidence for or
against the hypothesis that experience improves executable policy revision. That hypothesis
remains untested.

## The defect the live run exposed

Offline verification returns `status: fail` with exactly 7 problems, all of the form
`missing-receipt for-operation <id>`, and every cited id is a construction or
policy-construction model-inference operation. The contract requires that a settled receipt
remain attributable even when decoding fails. These operations were dispatched and left no
receipt, so their spend is not attributable.

This is a real defect, not verifier strictness; an independent typed review agreed at 0.86.
The verifier catching it is the verification working as intended. It is the first thing the
next batch should fix, chosen at 0.85 with 0.80 confidence over stronger model access and
construction robustness.

## Four defects found and fixed, each with a red check first

Two independent reviews ran against the integrated source, one attacking authority, leakage,
identity and resume, the other following bytes and actions through the public path.

`selection.select_member` substituted the release fallback member when the pinned bytes were
absent. Every disposition that reaches selection is a promoting one, so that branch could
only ever execute unassessed bytes while `run_use` still recorded the requested capability as
executed with an empty `fallback_reason`. Removed; absent pinned bytes now refuse.

`policy_step.materialize_view` copied observations verbatim, so an untrusted policy could
lift a sealed answer into a `request_model` prompt and the journal. A probe captured the
secret. Observations are now projected. The task itself was stripped later, before the live
run, once a real provider was on the other end.

The sealed assessment credited a policy-supplied `inputs["candidate"]` as a task outcome, so
a policy that copied the task witness and dropped one operation bound with zero queries.
A learning policy directs method execution and does not answer the panel task; that input is
now refused.

The comparison rule priced only queries and model calls, so policy compute was free and a
candidate could buy quality with unbounded steps. `step_calls` now counts. Child wall time is
deliberately excluded because it is not deterministic and would break the finite rule.

## C0 to C5 dispositions

| Requirement | Disposition | Evidence |
|---|---|---|
| C0 baseline confirmed | Met | 84 passed before any change |
| C1 STEP state and every action real | Met for the tested paths, with one gap | 133-pass gate; the 7 unattributable receipts are a C1 gap |
| C2 revision, qualification, exact subsequent selection | Met | production owns assess and bind; 11 public cycle tests; exact-byte activation |
| C3 prospective comparison with controlled providers | Mechanism met, comparison incomplete | pilot drives the cycle; doubled study green; live arms missing |
| C4 authorized live study | Executed within the cap, honest negative | exit 0, 19 of 100 calls, measured zero cost |
| C5 offline recomputation | Met, and it fails on a real defect | recomputed counts match; 7 problems named |

## Evidence classes, kept separate

Deterministic machinery and controlled HTTP: the 133-pass gate, the causal discrimination
suite, the export mutation suite, the doubled three-arm study. Provider doubles only.

Real inference: the live study alone. 15 study model calls plus 4 discovery calls against
`inclusionai/ling-3.0-flash-vl-free`. Committed under `evidence_s09_live_opus/`.

Externally unverified: the per-arm resource measurements are runtime attestations. Step
calls, model calls, queries and child wall time cannot be recomputed from static data. Byte
identity, artifact conformance, downstream quality and leakage are independently
recomputable, and the verifier says so rather than overstating its reach.

Not established at all: that a revised learning policy improves investigation outcomes.
No treatment arm produced a policy, so nothing was measured.

## Next bottlenecks, at most three, each evidence-supported

Make every dispatched model operation leave an attributable settled receipt, including empty
and failed provider responses. Seven operations in a single live run lacked one.

Obtain model access capable of emitting a valid executable STEP policy. The free tier failed
on both arms within the authorized construction budget, so the experiment cannot run at all
until this changes.

Decide whether policy construction should tolerate weak model output through more repair
attempts or a stricter output contract. P1 spent its allowance on one unsettled call and P2
was then starved, which is a schedule fragility worth naming even though the schedule itself
behaved correctly.

## Retained resources

`s09_local_c3_diag` and `s09_local_control` were created by a previous worker and are left
untouched. My own `s09o_*` databases are dropped. `evidence_inv01_live/` is unchanged.

## Generality campaign update (M0–M2), 2026-09-25

Branch `codex/implementation-investigation-learning-02`. This section supersedes nothing
above; it records what the generality campaign changed and what it did not.

**The empirical question is still unanswered, and one more thing is now known about why.**
The earlier report attributed the failure to the free model's inability to emit a valid
executable policy. The campaign found a second, independent cause that would have produced
the same result: no policy artifact could reach any world's decision point. The world could
be driven only by a Python callback, so a model-authored arm had no execution path into the
study at all. That is now fixed — a bounded bridge runs exact verified policy bytes through
the existing launcher and driver, and a hand-written policy chooses its own probe, its own
commit, or an immediate stop with all eight queries unspent. It is a mechanism result about
authored bytes, and it is the first time an executable policy has governed admitted actions
in this repository.

**Four recorded defects are fixed and merged**, each with a failing-before test and
verification by driving production code: a trusted `initial_measure` in the AD01 checker, the
r4 preflight zero-overwrite, replay returning before the immutable body was bound, and a
control gate that trusted `control_pass` without executing anything. Two of them were
verified against disposable migrated databases so the coverage is real rather than skipped.

**Three findings that change how any future Stage 9 result must be read.**

1. The task inventory cannot support a family-level claim. The three worlds contain the same
   ten structural clusters, so the study resolves ten independent units rather than 54 cells
   or 30 world-cells. The software half is 4 clusters, where a *perfect* sweep is p=0.125 and
   significance is unreachable at any effect size. Reaching roughly 24 independent clusters
   needs 14 new generation families, family-disjoint across development, qualification and
   audit, not 14 new cells.
2. Contamination is structural, not nominal. Nine `dev`/`within` graph pairs in the same
   world are isomorphic up to vertex relabeling, which a template-level audit cannot see. The
   duplicate guard compares literal labels and therefore reports clean.
3. The control gate, once it actually executes, reports a real control failure:
   `C-ctrl-sw-invalid` is `unsupported`, so the checker cannot be clean. Any earlier
   "checker clean" statement for the representation pilot was clean under a gate that read a
   file, and must be bounded accordingly.

**Inherited liability is 5563 units, not r4's 2294.** Enumerating every row of `reservations`
in `invl02_live` -- not just the current study's root, and never an evidence export -- finds a
second uncertain reservation of **3269 units** belonging to the older AD01 campaign of
2026-09-23, alongside r4's 2294. Its operation is `unresolved/unresolved` with a
lost-response-shaped receipt, so it is a real terminal state and not an empty row. Any new
freeze must carry both; computing liability from r4 alone understates prior unresolved
exposure by 3269. This generality campaign added no exposure of its own, having spent zero.

**Bottlenecks, revised.** Model access remains the binding constraint on the empirical
question, and it is unchanged. Ahead of it sit three items that must land before a live round
is worth running: a panel with family-disjoint splits and no isomorphic overlap; a shared
execution entry in `policy_step.py`, since the bridge duplicates an executor and carries no
durable DSN operation provenance; and a bound or a fix for the failing C control. The
incumbent `STEP` source verifier is a denylist and accepts `f = open; f(...)`; executing
model-authored bytes through it is bounded execution, not safe execution, and a positive AST
allowlist plus a real OS boundary is required before any arm's bytes run.
