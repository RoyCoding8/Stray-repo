# M4 resolved: the block was the wrong artifact, not a missing route

`reports/STAGE-09-COMPLETION-MATRIX.md:32` records M4 as BLOCKED and gives the
reason as *"no clean baseline and therefore no tamper test"*, citing
`inv_r1_m4_baseline/summary.json` (`status: "incomplete"`, 8/8
`parse_outcome: "too-long"`). That is a true statement about that artifact and
a false statement about M4.

**M4's seven required rejecting examples all execute, each on a baseline that
verifies clean first.** Established on tip `4a931a9`, no gateway, no database,
no dispatch.

## The cause, precisely

`inv_r1_m4_baseline/output-run.json` is a bundle for the **output-shape
experiment cell**, and `verify_bundle()` routes it to `_verify_output`
(`offline_recompute.py:1688-1693`). It is not the M4 verifier. M4's required
checks live in `_verify_m4_bundle`, which the same artifact cannot reach.

The routing is not a technicality — it is a near-total partition. Reachability
from each path, measured by AST call graph at this tip:

| | `_verify_output` | `_verify_m4_bundle` |
|---|---|---|
| functions reachable | 16 | 48 |
| `foreign-study-identity` | **not reachable** | reachable |
| `hidden-answer-contamination` | **not reachable** | reachable |
| `substituted-baseline` | **not reachable** | reachable |
| `resume-count-rollback` | **not reachable** | reachable |

A clean output-shape baseline would not have produced a single M4 rejecting
example, and it would not have satisfied the handoff. The milestone was blocked
because the lane was measuring the wrong cell, not because the route was
unavailable and not because the model refused to comply.

## The clean baseline, and the seven tamper results

`tests/test_s09an_evidence.py` holds the seven. Each runs through `baseline()`,
which asserts `verify_bundle() == "pass"` **before** the mutation is applied —
so "a baseline that already fails cannot establish a tamper test" is satisfied
by construction, not by assertion after the fact. `rejected()` asserts the
example's *own* problem string, so a verifier tripping on something unrelated
cannot pay for the example.

Reproduced independently at `4a931a9`, each from a fresh clean baseline:

| required example | expected problem | fired |
|---|---|---|
| doubled receipt inserted into live lineage | `duplicate-receipt-identity` | yes |
| foreign study identity | `foreign-study-identity` | yes |
| source substitution | `source-shared-between-arms` | yes |
| disconnected policy | `policy-digest-frozen-mismatch` | yes |
| hidden-answer contamination | `hidden-answer-contamination` | yes |
| absent usage treated as zero | `billed-unknown-scored-as-zero` | yes |
| resumed-count rollback | `resume-count-rollback` | yes |

Baseline `status: "pass"`, `problems: []`, byte-identical across two
constructions. The seven mutations are transcribed from the committed tests,
not invented. Results: `tamper-results.json`. Committed suite, 109 passed, 0
failed, 0 skipped, 8.25s: `gate-results.json`.

## What the earlier artifacts were measuring

The 512-character cap is not a property of M4. `max_response_characters` and
`OUTPUT_PROMPT_TEMPLATE` appear at `live_construct.py:33` and `:50` and nowhere
else in that file — the cap belongs to the output-shape cell alone. The
narration finding in `inv_r1_m4_baseline/RESULT.md`, the budget sweep, and the
1-in-5 compliance rate in `OPTION-THREE.md` are all measurements *of that
cell*. They were sound measurements of the wrong thing. N-23 and N-24 remain
exactly as valid as they were: the output-shape study still has no defensible
way to prompt a committed predictor. They were never M4's blocker.

## The finding against the matrix

`STAGE-09-COMPLETION-MATRIX.md:32` and `:281` both assert that **"no committed
artifact shows any of them executing."** That is false at the matrix's own tip.
`tests/test_s09an_evidence.py` was added at `d83ecc0` on 2026-09-26 15:29,
`d83ecc0` is an ancestor of `4a931a9`, and the matrix was written on 2026-09-28
01:10 — ten hours later. No `.md` in the tree references that file; the
executor was never looked up.

## The residual, and it is not M4's blocker

Two things remain unmet, and neither is the reason the milestone was blocked.

**1. No *live-derived* main-path baseline is committed.**
`invl02-r123/e12/m4-bundle.json` was recorded `pass` on 2026-09-25 and **fails
at this tip** with 52 problems — the verifier gained checks the bundle predates.
`export_m4_bundle()` on that same directory is refused outright
(`live protocol does not match the study root`). So the clean baseline
established here is synthetic, built by `demo_bundle()`. The tamper test is
real; the baseline behind it is a fixture, not a recorded run.

**2. A live main-path run is reachable but was not performed.**
`freeze_e12()` succeeds offline right now and pins
`nvidia/nemotron-3-ultra-550b-a55b:free` at the same endpoint. I did not
dispatch: the coordinator's brief puts the campaign freeze and the durable
reservation owner ahead of any send, and M4's requirement is met without one.
Recorded as a decision, not a blocker.

## Exposure

Zero dispatches. No gateway call, no gateway credential read at runtime, no
reservation drawn. This lane is entirely offline recomputation, which is what
M4 asks for. Every artifact here was written by a fresh export at `4a931a9`; no
existing artifact in this directory was modified or deleted.
