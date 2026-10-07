> Historical task graph and ownership plan, issued against `dd504e1` on a
> branch whose commits do not resolve in the current repository. It is a plan
> for a campaign that has since been superseded. Current scoped status is
> reconciled in [PROJECT-LEDGER.md](PROJECT-LEDGER.md) and
> [STAGE-09-10-COMPLETION-MATRIX.md](STAGE-09-10-COMPLETION-MATRIX.md).

# Stage 9 connected study: task graph and file ownership

Issued against `dd504e1` on `codex/implementation-investigation-learning-02`. Supplements
`WORKER-STAGE-09-CONNECTED-STUDY.md` (`293a120`) and `WORKER-STAGE-09-PARALLEL-EXPANSION.md`
(`dd504e1`). The narrow study recorded at `b0c010c` is an integration checkpoint, not the
stopping point.

## M0 inventory, verified at the source

State read at `dd504e1`, not from a lane checkout.

| Fact | Value | How it was read |
|---|---|---|
| Local tip | `dd504e1`, ahead of `b0c010c` by the two mandate commits | `git log` |
| Origin tip | `293a120` on my branch, plus `codex/stage09-expanded-study-handoff` | `git fetch --all --prune` |
| Worktrees | main checkout only, plus two foreign checkouts not on my branch | `git worktree list` |
| Stale `wt/*` branches | 0 | `git branch --list 'wt/*'` |
| Orphan `worktree-agent-*` branches | 5, all identical, each 3 commits deleting 2612 files from a scratch base | `git diff --stat` per branch |
| Router | live on 127.0.0.1:4000, `{"status":"ok"}` | `curl /health` |
| Campaign suite at `b0c010c` | 691 passed, 1 skipped, 1 xfailed | committed run output |

The five orphan branches were scratch bases aborted mid-run, not worker output. All five
carry the same three commits and the same 2612-file deletion. Nothing was salvageable, and
all five are deleted. No active lane existed to disrupt.

### The three findings, reproduced here rather than accepted

**CS-01, the dimensional error, reproduced exactly.**

```
measurement_status       measured
provider_charge_units    null
provider_billed          null
provider_charge_scale    null
reads_as                 "the provider charges nothing for this call"
route_capacity_from_freeze  {max_dispatches: 8, units_per_dispatch: 0,
                             authorized_ceiling_units: 0}
study_ceiling()          0
```

The chain that produces it. `s09_route_cost.measurement` reads `charge_units: null` and its
`reads_as` renders that as "the provider charges nothing for this call". `route_capacity`
converts the null to `int(charge or 0)` and marks the zero `VERIFIED`, on the strength of a
committed settled receipt. `route_capacity_from_freeze` then multiplied that zero
by `max_dispatches` to mint an `authorized_ceiling_units` of 0, and the
preflight's `Budget` subtracted 5563 carried *reservation units* from that 0 to
describe the result as `-5563 dispatches`. Repaired at `f3af21a`:
`route_capacity_from_freeze` now returns a `DispatchAllowance` from
`limits["max_dispatches"]` at `experiments/ad01/s09_exposure_ledger.py:544-508`
and multiplies nothing.

Three quantities are being called one thing. A provider's reported charge is null, which is
unknown. An internal reservation estimate is 5563 units held against two prior campaigns, and
is not a dispatch count. A dispatch allowance is 8 sends. Null is folded to zero, zero is
certified verified, zero is scaled into a unit ceiling, and reservation units are subtracted
from it.

**CS-02, the circular launch check, reproduced at the call site.** `collect` calls
`probe_policy_execution(read_bundle(config.bundle))` on the same bundle the study is about to
write. The probe passes on a bundle carrying a nonempty `executed_digest_list` on some
records, a nonempty admitted action, and two or more distinct digest tuples. None of those
is a causal claim. A single valid retained policy may legitimately produce one digest
everywhere, which the probe scores as `unproven`. Two unrelated records can satisfy the
list and the action independently. The check qualifies the apparatus using the study's own
future output.

**CS-03, representation components, as reproduced at `85181b7`.**
`REAL_REPRESENTATION_KINDS` was `frozenset({PYTHON_STEP})` with one registration
helper. It is now `frozenset({PYTHON_STEP, TYPED_AST, ACTION_GRAPH})` at
`experiments/ad01/s09_arm_parity.py:29`, with `register_typed_ast` at `:737` and
`register_action_graph` at `:811`, built at `0fa7971` and `136e792`. Arms now
branch per kind through the registered `driver_factory` at `:688` rather than
calling `boolean_active.run_episode` for every kind.

### The call chain the assignment asks me to trace

Traced by reading call sites, not module names. Each edge records the existing
implementation, so the repair reuses what is there.

| Edge | Existing implementation | State |
|---|---|---|
| construction response to acquired artifact | `experiments/ad01/live_construct.py:874`, `construct.py:427` | **HOLDS** — source checked at `82a8fd10` |
| acquired artifact to selected policy | `learner.py.visible_prompt`, `policy_assess.py` | **FALSE** — the named path does not carry an acquired artifact to a selected policy |
| selected policy to child/interpreter | `policy_step.py:457` driver → `method_exec.run_step_out_of_process:1633` | **FALSE, worst row** — the plan names `exec_profile` as bound; it is imported by `src/settlement/artifacts.py:21` and `boot.py:102` and by nothing under `experiments/ad01/`. `git log --all -S 'exec_profile'` on both files is empty, so it was never bound on any branch |
| proposed action to admission | `policy_action.parse_action:80`, `ACTION_KINDS:32`, called by `admit_action` (`s09_arm_parity.py:615`) | **FALSE citation, right idea** — `policy_action.admit` does not exist; `grep admit` in that file returns nothing. The row's "one schema" qualifier survives |
| oracle effect to scored result | `boolean_active.run_episode:114`, `checker.py:138` | **HOLDS, and undercounts** — `_WORLDS` (`s09_arm_parity.py:47`) names three worlds, not two. `checker.py:138` grades the `("initial","final")` pair and refuses `unknown` rather than zeroing it |
| receipt to evidence boundary | `s09_receipt_diagnosability`, `offline_recompute` | **FALSE, two files presented as one edge** — `s09_receipt_diagnosability` is 574 lines with no production importer (two test files only), and `offline_recompute` re-derives ids from a freeze rather than receiving a receipt |
| durable resume to remaining count | `agenda_policy._step_remaining:784` | **FALSE citation, right idea** — the plan names `s09_durable_state.resume_or_step:251`, which has only test callers. The live path is `agenda_policy`, and `DurableStep:75` carries no count field at all |
| budget units to dispatch count | `study_ceiling` (`s09_study_preflight.py:1294`) returns only a dispatch count | **STALE — BUILT** (`85181b7`) |
| representation kind to real executor | all three registered at `s09_arm_parity.py:708`/`:737`/`:811` | **STALE — BUILT** (`0fa7971`, `136e792`) |
| causal policy decision to admitted effect | `s09_causal_proof.qualify_pre_launch:574` replaced the circular check; `launch_governance` docstring at `:1193` names CS-02 | **STALE — BUILT** (`f3af21a`, `14f5733`) |

> **Historical review at `2b7050a`. The current source citations were re-read at `82a8fd10`.**
> Row-by-row evidence, every `file:line` opened and checked:
> `reviews/STAGE-09-M0-TASKGRAPH.md`.
>
> **Two distinct failure classes, and a reviewer reading this table would
> catch neither.** Rows 2, 4, 6 and 7 were wrong about code that *already
> existed* when the plan was written. Rows 8, 9 and 10 were overtaken: the
> repairs converged on a parallel line — `85181b7` is an ancestor of `0fa7971`
> but not of `f3af21a` or `14f5733` — and this plan was never re-read against
> them.
>
> **Row 9 would have sent a lane to re-wire a comparison two commits had
> already run.** Do not dispatch work from this table without checking the
> source first.
>
> No reviewer had ever challenged any of these edges. Four R-lane reviews
> exist and none touches this table. M1-M4, the ownership table and the
> standing constraints below are unaffected.

Rows 8, 9 and 10 were the assignment when this table was written at `85181b7`. All
three are now built and the cells above say so. Dispatch nothing from them.

The repair they asked for landed on a parallel line of work and this table was not
re-read against it. The last verification is `2b7050a`, which is not an ancestor
of `f3af21a` or `14f5733`. Any commit that touches an owned path below and is not
a descendant of `2b7050a` needs this table re-read before it is used for dispatch.

## Ownership

Disjoint before dispatch. The integration owner is lane I, and no other lane edits a shared
driver or a shared contract.

| Lane | Owned paths | Must not touch |
|---|---|---|
| A budget and authority | `src/settlement/store.py`, `src/settlement/authority.py`, `experiments/ad01/s09_exposure_ledger.py` | gateway, preflight, arm_parity |
| B execution and provenance | `experiments/ad01/policy_action.py`, `experiments/ad01/policy_step.py`, `experiments/ad01/s09_bound_use_proof.py` | exposure ledger, arm_parity |
| C STEP qualification | `experiments/ad01/boolean_policy.py`, `tests/test_s09c3_policy_pilot.py` | arm_parity, ledger |
| D typed AST | `experiments/ad01/boolean_ast_policy.py`, `tests/test_s09m2_policy.py` | arm_parity, ledger |
| E action graph | `experiments/ad01/boolean_graph_policy.py`, `tests/test_s09m2_construct.py` | arm_parity, ledger |
| F instruments | `experiments/ad01/s09_m2_rubric.py`, `experiments/ad01/s09_panel_inventory.py`, `experiments/ad01/second_active.py` | arm_parity, ledger, policy modules |
| G SWE instrument | `experiments/ad01/worlds/`, `experiments/ad01/s09_swe_*.py` new only | everything above |
| H construction and experience | `experiments/ad01/learner.py`, `experiments/ad01/packet.py`, `experiments/ad01/live_construct.py` | arm_parity, ledger |
| I integration owner | `experiments/ad01/s09_arm_parity.py`, `experiments/ad01/s09_study_preflight.py`, `experiments/ad01/s09_study_protocol.py`, `scripts/inv01_study.py` | lanes A through H source |
| J evidence and analysis | `experiments/ad01/offline_recompute.py`, `experiments/ad01/s09_verdict.py` | every lane's source |
| K autonomous selection | `experiments/ad01/agenda_policy.py`, `experiments/ad01/improve_channel.py` | arm_parity, ledger, preflight |
| L executable learner revision | `experiments/ad01/improve_channel.py` split with K, see note | arm_parity, ledger |
| R1 authority and recovery | read-only, writes `reviews/STAGE-09-R1-*.md` | all source |
| R2 execution and visibility | read-only, writes `reviews/STAGE-09-R2-*.md` | all source |
| R3 experimental validity | read-only, writes `reviews/STAGE-09-R3-*.md` | all source |
| R4 reproduction | read-only, writes `reviews/STAGE-09-R4-*.md` | all source |
| I document | `reports/PLAN-STAGE-09-CONNECTED.md`, this call-chain table | any other plan or report |

Lane K and lane L both want `improve_channel.py`. K owns the agenda-to-investigation wiring
and L owns the executable revision boundary. K takes the first 320 lines, L the rest, and
each states its split in its brief. If either finds it needs the other's half, it reports
the conflict rather than editing across it.

Lane I also owns this document. Every row of the call-chain table points into lane
I's owned paths, so the lane that can turn the table stale is the one that owns it.
The R lanes are one-shot challenges and are not a substitute: all four were grepped
for this table and none touches it. When lane I commits a change to any path in the
table above, re-read rows 1 through 10 before the table is used to dispatch.

## Order

M1 and M2 can run concurrently; they touch different subsystems and neither reads the other's
output. M3 needs both. M4 needs M3. The E-lane work from the expansion document needs the M2
interfaces pinned, so lanes F through H and K through L start at M2 and are held at their
live-effect boundary until M3 freezes.

## Standing constraints, carried forward

- Never put the key in Git, reports, or evidence. The historical exposure in pushed history
  is accepted by the user and stays; no new occurrence.
- Never rewrite shared history. Commit and push normally.
- The router at 127.0.0.1:4000 is live. Never stop it.
- r4 stays closed. Its freeze, its one spent dispatch and its 2294 uncertain units are
  historical and unchanged.
- Keep the 5563 historical held units. Do not release them to make room.
- A confirmed free route is authorized. A new paid route is not.
