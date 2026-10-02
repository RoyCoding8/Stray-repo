# Lane A5 — the full chain, entered through the public entry

Base: `94efa12`. Branch: `wt/a5-chain`. Offline lane: fixture gateway only,
no live model call, no network.

## What this lane owns

Three new files, and one production line.

| Path | Role |
|---|---|
| `tests/test_inv_a_reviewer_source.py` | Reviewer-written policy source. Every STEP byte in both gates was written for this verification, so no lane's own fixture can be self-consistently green here. |
| `tests/test_inv_a_chain.py` | The seven arrows, each asserted against a durable row. |
| `tests/test_inv_a_counterexamples.py` | The seven tamper cases, each with a clean baseline first. |

Production: `experiments/ad01/trajectory.py`, one line. See "Production fix".

## The chain, and the durable row behind each arrow

Entered through `trajectory.run_campaign` (the acquisition arm) and
`trajectory.run_use` (the fresh-process arm), both with `dsn` set against a
real PostgreSQL database this run created and dropped.

| Arrow | Durable row that carries it |
|---|---|
| permitted experience | `operations` row `ad01-<cid>-policy-s0-k0`, `effect = sandbox-exec`, `settled`, plus the `receipts` row for it. The probe the reviewer program admitted ran as a real bounded child. |
| program decision | `s09_policy_state` row for `seq = 0`, `policy_output.results[0].action.kind = diagnose`, and `source_digest` equal to `sha256(CHAIN_SOURCE)`. The decision names the source that produced it. |
| admitted effect | `operations` rows for `…-construct-l1-init` (model-inference) and `…-validate-l1-init` (sandbox-exec), each `settled` with its own `receipts` row. |
| observation | `attempt_observations` row with `content->>'kind' = 'boundary'` and the nested `observation.observation_id`; the same id is read back through `_read_campaign`. |
| checked artifact | `s09_policy_state` `effect_record.episode` for `seq = 1`: `disposition = retained`, `check.verdict = preserved`, and an `executable` whose `source_digest` equals `sha256` of its own `method_source`. |
| retention/binding | The frozen repertoire member (`acquired-sw-*`, `authored: false`) whose bytes agree with their digest, and `capability_releases` empty. Method identity and policy identity are held apart and asserted unequal. |
| fresh-process use | `run_use` with `policy_source=` runs two `sandbox-exec` operations, each `settled` with its own receipt. The record's `executed_source` is the acquired member's bytes, and its `policy_source_digest` differs from the member's `source_digest`. |

Two further facts the gate pins, because they are the ones a digest alone
would pass without:

- The reviewer's private state crosses a boundary only through the row.
  `state_transition.final_state.stage` is `[1, 1, 3]` across the three
  boundaries, so the program reached its use step through persisted state.
- Re-entering the same campaign is idempotent. A second `run_campaign`
  returns the same three boundaries, every one marked `resumed`, and the
  `operations` count does not move.

Gate:

```
29 passed in 43.58s
S09ISO: dropped 13 database(s) for this run
```

## The seven tamper cases

Every row below runs its baseline first, in the same test, on the same
store. A literal reason is asserted, not a substring and not an exception
type.

| # | Case | Literal refusal | Clean-baseline proof |
|---|---|---|---|
| 1 | unrelated-route replay | `unknown operation ad01-a5-route-B-op-<tag>`, `ResultCode.INVALID_INPUT`, from `broker.admit_launcher_receipt` | A route-A member is executed first and settles `success` with exactly one receipt. The recorded receipt stays bound to the operation that earned it. |
| 2 | changed bytes | `refused: staged source digest mismatch`, and `dispatch_operation` was never reached | Baseline runs the same member through the real broker and real launcher: `source_digest` matches, `candidate` is non-empty, the operation row is `settled`. Only the substitution refuses. |
| 3 | missing authority | `refused: execution needs explicit authority and identity` (any of dsn / allocation_id / operation_id omitted); `refused: unknown allocation`; `use requires explicit execution allocation` | Each of the three runs executes `CHAIN_SOURCE` on the same view with full authority and returns `action.kind == diagnose`; `run_use` with a real allocation returns `executed == acquired-sw-a5counter`. |
| 4 | no candidate | `admitted 'a5-absent-method' is absent from the repertoire`; and separately `admitted 'seed-gr-dfs' is scoped to 'graph' and cannot answer a software task` | Baseline: the same repertoire runs the member it holds (`executed == acquired-sw-a5counter`). The scope case has its own baseline (`acquired-sw-scoped`). Both refusals set `output = {}` and `selected = executed = refused`. |
| 5 | partial response | Empty body settles `outcome = failure` under receipt identity `gw:<op>:empty-response` | Baseline: the same program with a body that arrived settles `outcome = success` under `gw:<op>`. Two different receipts for two different bodies. |
| 6 | timeout | `policy step failed: refused: durable child operation has no successful receipt`, episode `disposition = no-candidate`, no `executable` key | Baseline: the chain program run on the same store yields one episode with `disposition = inspected`. The companion case records `policy step budget exhausted (6 steps)` in `accepted_action`. |
| 7 | pending resume | `pending effect 0 already accepted` / `boundary 0 already settled` where the row is deleted and re-accepted; the durable row itself is the guard | Baseline: a boundary accepted via `trajectory.accept_action` restarts and executes exactly the accepted decision. A second decision for that seq returns the first `attempt_id` and writes nothing, so the stored `accepted_action` is still the first one. |

Every one of the seven is proved. None rests on a red baseline.

Two notes on what the tamper actually exercises, so the table is not
overread:

- Case 1's refusal is "unknown operation", because the route-B operation was
  never prepared. A prepared route-B operation was not reachable through
  this entry without a real launcher, so the case proves the receipt cannot
  be attached to an operation that does not exist, and separately that
  replaying it onto its own operation is idempotent rather than a second
  execution. The stronger claim, that a receipt from a prepared route-A
  operation is refused against a prepared route-B operation, is NOT proved
  here. `execution_version` exists on `broker.ensure_operation` and
  `learner_revision._route_execution_version` populates it, but no public
  entry I found lets a test prepare two operations differing only in route
  and then replay one receipt onto the other.
- Case 6's baseline distinguishes a hang from a refusal. Both produce one
  episode with no method, so without a clean run producing a real decision
  the assertion would not be attributable.

## Production fix

`experiments/ad01/trajectory.py:721`, in `_run_boundary`:

```python
        result=(member or {}).get("validation", {}).get("result"),
        authority=_dev_episode_authority(journal, boundary))
```

was

```python
        result=(member or {}).get("validation", {}).get("result"),
        **_dev_episode_authority(journal, boundary))
```

Lane A6 (`c3181d9`) introduced `_dev_episode_authority`, which returns a
`{dsn, allocation_id, operation_id}` dict, and spread it with `**` onto
`dev_episode`. `dev_episode` declares one keyword-only `authority`
parameter, so every boundary that constructed a development episode raised
`TypeError: dev_episode() got an unexpected keyword argument 'dsn'`.

This was a live break on the merge base, not a latent one. It is also a
second-order effect of the same shape as A2's fix: spreading a dict of
named authority onto a signature that takes it as one parameter.

`tests/test_s09c2a_actions.py` went from 2 failed / 5 passed to
7 passed. No other caller is affected: `selection.py:1045` passes no
authority, and the two executors were already checked by A2.

## Affected regression set

```
7 failed, 78 passed in 28.90s
S09ISO: dropped 13 database(s) for this run
```

All 7 failures are pre-existing on the merge base. Verified by running the
same files in a throwaway worktree at `94efa12`, which produced the
identical 7:

```
7 failed, 61 passed in 17.63s
```

All 7 share one root cause and one literal:
`MethodExecutionError: refused: execution needs explicit authority and
identity` at `method_exec.py:1413`.

The broken caller is `experiments/ad01/improve_channel.py:1013`, in
`_run_source`, which forwards only `**evidence` to
`method_exec.run_step_out_of_process` and supplies no `dsn` and no
`allocation_id`. A2 deleted the `dsn is None` branch, so that call now
refuses. `drive_improve_round` calls it with no handler for
`MethodExecutionError`, so the refusal propagates to the tests, which reach
it through `live_construct.run_live_improve_round` →
`drive_improve_round`.

A6 knew. `tests/test_inv_a6_caller_migration.py:119-125` lists
`experiments/ad01/improve_channel.py` in `OTHER_LANES`, files "owned by
another lane, not asserted on, so a change there is not a false red". That
is why A6's own gate was green while these tests stayed red. This is a
deferred obligation with a named owner gap, not an oversight.

An earlier draft of this report attributed the break to `live.py`. That was
wrong: the file is `live_construct.py`, and it never calls an executor at
all. Its only `method_exec` touchpoints are `verify_step_source` at
`:892` and `:1163`, which is not an executor entry.

That belongs to A2/A6, not to this lane, and I did not touch those files.

Whether the repair is an edit or a decision is not mine to settle. The
invl02 frontier world has no settlement store behind it: `frontier.py`
contains no `dsn` and no `allocation`, and `FrontierStore` wraps a
file-backed JSON document. So there is no authority for that world to
supply. The options are to thread real authority through, or to declare
policy-source execution out of scope for invl02 and correct the assertions.
Either way it belongs in its own commit, not in this merge.

`tests/test_final_provenance.py` and `tests/test_mission_entry.py` are
fully green.

## What I could NOT prove

1. The stronger unrelated-route replay (case 1 above). A receipt from a
   *prepared* route-A operation offered against a *prepared* route-B
   operation. The `execution_version` field exists and
   `learner_revision.py:60,416` binds it, but no public entry lets a test
   build two operations differing only in route and then offer one receipt
   to the other. The case as proved is the unprepared-operation refusal.
2. Whether the seven inherited red tests should be repaired, and by which
   of the two dispositions above. They are A2/A6's regression surface and
   `improve_channel.py` is another lane's file. Left red and reported
   rather than silently widened, and never marked `xfail` or `skip`.
3. The non-STEP representation arms. `inv-a.md` §e asked L5 to add
   reviewer-written source for the typed AST and graph arms as well as
   STEP. I wrote reviewer-written source for STEP only. The typed AST and
   graph paths (`policy_action`, `representation.py`) are not entered
   through `run_campaign`/`run_use`, so reaching them through the public
   entry was not something I could establish. The chain is proved for the
   STEP arm only, and that limit is real.
4. Every arrow across a representation boundary. §13 asks that the same
   logical action admit the same effect, observation, refusal and resource
   use across STEP, typed AST and graph. Only STEP is covered here; the
   cross-representation claim remains unproved by this lane.