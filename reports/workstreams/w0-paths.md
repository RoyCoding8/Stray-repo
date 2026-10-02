# W0 — reusable production paths: connected-ness crosswalk

Branch: `wt/w0-paths`, revision `dfbd557`. Read-only investigation; no source modified.
Purpose: let W1–W4 lanes be assigned without re-deriving the system. This is a
crosswalk, not an architecture. Every claim below carries a citation; an uncited
claim is marked `(guess)`.

## Public entry path

`pyproject.toml` declares no `[project.scripts]`, so "entry" means a module run
directly. The repo names its own public entry verbatim:
`reports/local-completion/action-grounding.md:16` — "The current public entry is
`experiments.ad01.cli`." Corroborated by `reports/STAGE-09-CONSOLIDATION.md:29`.

```
experiments/ad01/cli.py:323   __main__ guard
experiments/ad01/cli.py:111   main() -> argparse subcommand dispatch
experiments/ad01/cli.py:278   run|cycle branch
experiments/ad01/cli.py:285   trajectory.run_campaign(...)
experiments/ad01/trajectory.py:1077  run_campaign
experiments/ad01/trajectory.py:1206  execute_pending(...)  per boundary
```

Three further independent entries exist and do NOT route through it:
`experiments/coord02/entry.py:828`, `experiments/representation/acquire/run.py:1408`,
`scripts/scheduler.py:57`. `src/settlement/api.py:520 main()` is an operator
dashboard, not a campaign entry.

## Crosswalk

| Capability | Module(s) | Connected? | Entry-reachable? | Measurable | Cannot express | Must change |
|---|---|---|---|---|---|---|
| **1. STEP** | `experiments/ad01/policy_step.py:181` `compile_step`; ABI `:38`; validator `:137` | Yes, but ABI vs production step are different shapes | Yes — `cli.py:278` -> `trajectory.run_campaign`; also `scripts/s09_pilot.py:388` | Receipt carries value: `response`, `verdict` at `src/settlement/representation.py:691-692`; costs `loop.py:171` | Nothing — it is real Python (`exec(compile(...))` at `policy_step.py:190`) | None for W1. Note `src/settlement/representation.py:367` `step_op_id` is an identity string, not a step type |
| **2. Typed AST** | `experiments/ad01/boolean_ast_policy.py:27` `_EXPR_FIELDS`, `:38` `_STMT_FIELDS`; evaluator `:409`; load `:370` | **Experiment-only. Not connected to any entry** | **NO.** Zero importers in `scripts/`; zero in `cli.py` | Node/depth/state/byte budgets; `expressivity_limits()` `:773`; refusals | No I/O, no call, no loop, no string concat, no return-value node. See limits below | A SWE arm needs new view fields + new nodes, or the cell stays missing by design |
| **3. Action graph** | Policy: `experiments/ad01/boolean_graph_policy.py:58`, `ordering_graph_policy.py:95`. Control-flow: `src/settlement/run.py:97` `Composition` | Policy graph: experiment-only. **Control-flow graph: production-connected** | Policy graph: **NO**. Control-flow: **YES** — `scripts/scheduler.py:29` -> `broker.sweep` `:1278` -> `_wake_waiting_workflows` `:1341` -> `runmod.*`; `broker.py:1384` starts the DBOS workflow | Policy: refusal text per node. Control-flow: `Continuation` position, retry counts, `operation_outcome` `run.py:437` | Policy graph: a guard value cannot reach an action input (see limits). Control-flow: not a policy, it executes a fixed plan | None for W1 on the control-flow side. Do not confuse the two graphs |
| **4. Experience** | `src/settlement/loop.py:303` `ExperienceTransition`; journal `:322`, `read_journal` `:335`, `resume_state` `:373`. Also `src/settlement/context.py`, `experiments/coord02/experience.py:239` | Yes. `loop.py` is the production journal | Yes — `trajectory.py:403,409`; `e3_ladder.py:364`; `s09_m3_pilot.py:379`. No `src/` importer | `costs_measured`/`costs_unknown` `loop.py:310-311`; `witness_acquisition` vs `witness_use` `experiments/ad01/records.py:897-903` | **No decay/retention anywhere.** Append-only. `src/settlement/context.py` is TEST-ONLY (zero non-test importers) | A transfer claim needs a lesson->later-decision link. Only aggregate use counts exist today |
| **5. Autonomous selection** | Production: `src/settlement/agenda.py:421` `select_and_admit`, policy `src/settlement/agenda_policy.py:334` `_decide`. Experiment: `experiments/ad01/agenda_policy.py:92`, `selection.py:255` | Yes | **Yes** — `scripts/scheduler.py:21`, `scripts/agenda01.py:287`, and `api.py:26` | `agenda_policy.py:389-395`: `decision`, `selection{option_id,kind,cost,route}`, `reasons`, `evaluated[]` with per-candidate `skipped` | Production is **rotation, not scoring** — `rotation_order` `:99` -> `seed_order` `agenda.py:68`; first-eligible wins. No utility score. `ad01/agenda_policy.py:88` emits `rationale` but no rejected list and no score | Production criterion is fairness. W3 needs a stated criterion change, not a wiring fix |
| **6. Learner revision** | `experiments/ad01/learner_revision.py:1176` `run_campaign`; `improve_channel.py:387` `classify_revision`, `:811` `admit_revision_under_freeze`; incumbent `rule_learner.py:18`; production `src/settlement/development.py:700` `construct`, `:982` `select` | Yes | **Partly.** `improve_channel` reachable via `live_construct.py:1057`, `invl02_live.py:1869`. `learner_revision.run_campaign`: only `reports/evidence/inv_r1_e4/make_result.py:40`. `settlement/development.py`: reachable from `run_dev_episode.py:47`, `run_live_abc.py:168`, **not from `ad01.cli`** | `acquisition` verdict `:221`; `incumbent_x` vs `revised_x` `:1073`; `delta` `:880`; 3-control `qualify` `:1010`; `descendant_built` `:1035` | No command completes revision through assessment and bind (recorded at `reports/local-completion/action-grounding.md:16`) | Wire the run harness onto a real entry; keep acquisition and benefit separate (`learner_revision.py:14-22`) |

## Call chain per capability, or the exact break

| Capability | Status | Chain or break point |
|---|---|---|
| 1. STEP | connected | `cli.py:285` -> `trajectory.py:1077` -> `execute_pending` `:1206` -> `policy_step.run_policy_step` `:424` -> `method_exec.run_step_out_of_process` `:1334` -> `broker.ensure_operation` / `dispatch_operation` |
| 2. Typed AST | **disconnected** | Break at `experiments/ad01/s09_arm_parity.py:575` `_typed_ast_factory`. It is wired into the s09 parity harness only. No `scripts/` importer, and `s09_swe_experiment.py:1840` `main()` is itself unimported |
| 3. Action graph | control-flow connected; policy disconnected | Control-flow: `scheduler.py:29` -> `broker.sweep` `:1278` -> `broker.py:1384` `DBOS.start_workflow(attempt_workflow)` -> `run.py:1577` `advance`. Policy: break at `s09_arm_parity.py:618`, same as AST |
| 4. Experience | connected | `trajectory.py:403` imports `loop`; `loop.py:322` `journal`, `:373` `resume_state` |
| 5. Selection | connected | `scheduler.py:21` -> `agenda.collect_wakeups`; `agenda.py:421` `select_and_admit`. `agenda_policy.decide_R/decide_Q` `:405/:409` are called from `experiments/agenda01/runner.py:456-457` only |
| 6. Learner revision | partly connected | `improve_channel` via `live_construct.py:1057`. `learner_revision.run_campaign` has one non-test importer, an evidence script |

## AST/graph expressiveness limits, verified in code

The design contract holds on both halves. The grammar omits data access and
value flow, and it does **not** hide a Python interpreter.

- The node set is 9 expression ops and 4 statement ops total
  (`boolean_ast_policy.py:27`, `:38`). There is no call, loop, function-def,
  import, I/O, string-concat or arithmetic-minus op.
- `_run_expression` (`:409`) reads only from the in-memory `env` built at `:474`
  from `{"view", "state"}`. **No node performs I/O.**
- `_VIEW_TYPES` (`:47`) is a closed 6-name whitelist: `instrument, task_id,
  observed, remaining, public_world, action_schema`. `_expr` refuses anything
  else at `:225`. **No view field carries a program, a diff or a repository.**
- `_execute` (`:448`) ends at `return {"action", "state"}` (`:471`), forced
  through `policy_action.parse_step_result` (`:478`). The return type is an
  action, not a value. **A value cannot flow back out through the AST**; it
  returns only via the STEP receipt.

The repository records these as measured refusals, not claims:
`boolean_ast_policy.py:773` `expressivity_limits()` — "every entry here is a
measured refusal", driven back through the loader by
`tests/test_s09ast_expressivity.py:365`. For the SWE world specifically,
`s09_swe_ast.py:309` `missing_cells()` states, for typed-ast, "no view field
carrying the program under repair, and no node that builds replacement source
text ... its repair rate is 0 and that 0 is about the node set" (`:316-323`).
For action-graph, "a guard value cannot reach an action input" (`:325-335`),
rooted at `ordering_graph_policy.py:261` `_parse_action`, which deep-copies the
literal record node and discards what the guard just read. Both are wired into a
real driver: `s09_swe_experiment.py:1013, 1096, 1266`.

The hidden-interpreter risk lands elsewhere, and is real: the STEP arm runs real
Python at `policy_step.py:190` and `method_exec.py:547`. That is a deliberate
separate representation, not the AST.

## The `resource` dependency

Three sites, all deferred function-local imports. There is no fourth.

| Site | Enclosing fn | Gates | Windows behaviour |
|---|---|---|---|
| `src/settlement/exec_profile.py:117` | `_limit_resources` `:116`, via `_child_session` `:125` | `RLIMIT_CPU` `:120`, `RLIMIT_AS` `:122` | `ModuleNotFoundError`, no guard |
| `src/settlement/launcher_local.py:796` | `_child_setup(payload)._setup` `:795` | `RLIMIT_CPU` `:801`, `RLIMIT_AS` `:803`, then `_landlock_restrict` `:809`, then `os.setsid()` `:810` | `ModuleNotFoundError`, no guard |
| `experiments/ad01/boolean_ast_policy.py:483` | `_child_main` `:482` | `RLIMIT_CPU` `:490`, `RLIMIT_AS` `:496` | `ModuleNotFoundError`, no guard |

Measured on this host, not inferred:

```
import resource                      -> ModuleNotFoundError
hasattr(os,'setsid')                -> False
exec_profile._limit_resources(10,1M) -> ModuleNotFoundError
launcher_local.landlock_available()  -> False
boot.check_sandbox('local-process')  -> reachable=False,
   'local spawn failed: preexec_fn is not supported on Windows platforms'
boolean_ast_policy._child_main()     -> ModuleNotFoundError
```

What is gated, and what a portable replacement must cover:

- CPU survives only under the gVisor profile, which maps it to a container flag
  at `exec_profile.py:261` (`--ulimit cpu=N:N`). That is the existing portable
  equivalent.
- Address-space memory (`RLIMIT_AS`) has **no** mapping on any profile.
- The launcher already has the correct refusal pattern for the Landlock half:
  it checks `landlock_available()` **before** spawning and returns
  `read-boundary-unavailable` (`launcher_local.py:713-726`). The `resource`
  limits have no equivalent pre-spawn check. That asymmetry is the defect.
- `boolean_ast_policy.py:773` records that the AST CPU rlimit "no legal program
  reaches: ... the load-time node budget is the limit that actually binds CPU."
  So the AST child loses a limit that was never the binding one.

`README.md:22-24` states the rule: "disabling execution limits is not a valid
portability fix." `WORKER-PROMPT.md:52` repeats it. The fix belongs in a
Windows job-object path from the parent, plus a pre-spawn refusal mirroring
`launcher_local.py:713-726`. Not in removing the limits.

## Blocking gaps — the minimum W1–W4 depend on

1. **`src/settlement/exec_profile.py:117` and `src/settlement/launcher_local.py:796`** — no Windows branch for the child resource limits. Add a parent-side job-object limit and a pre-spawn refusal. Nothing dispatches on this host until then.
2. **`src/settlement/launcher_local.py:713`** — extend the existing `landlock_available()` pre-spawn refusal to cover the resource limits, so a limit that cannot be enforced refuses rather than raising inside `preexec_fn`.
3. **`src/settlement/run.py:97` reachability** — resolved, not a gap. The control-flow graph is production-connected through `broker.py:1341`. Recorded here so a lane does not re-investigate it.
4. **`src/settlement/loop.py:322`** — no lesson-to-later-decision record. A W2 transfer claim is not derivable; only aggregate `witness_use` counts exist (`records.py:897-903`).
5. **`experiments/ad01/learner_revision.py:1176`** — the revision run harness has one non-test importer, an evidence script. W3 needs it on a real entry.
6. **`experiments/ad01/s09_arm_parity.py:318`** — `admit_world_view` demands an exact 8-field set; the SWE world publishes 12 (`s09_swe_world.py:154` `POLICY_VIEW_FIELDS`). This is the N-58 fork. W1 cannot run a 3-representation SWE matrix until it is resolved. Both options are costed at `s09_swe_experiment.py:1635-1649`.

## Does not need to change

- **`experiments/ad01/policy_step.py`** — the STEP path is real, connected, and works. It is the only arm that can express SWE repair. Do not touch it for W1.
- **`src/settlement/run.py`** — production-connected via `broker.py:1341` and `broker.py:1384`. No re-wiring needed.
- **`src/settlement/agenda.py:421` / `scripts/scheduler.py`** — the production selection path is connected and emits chosen plus rejected alternatives with rationale (`agenda_policy.py:389-395`). W3 changes the criterion, not the wiring.
- **`src/settlement/loop.py:322`** journal mechanics — the digest-keyed identity (`:325-328`) and resume fold are sound. Only the missing transfer record matters.
- **The typed AST's expressivity limits** — these are correct, test-backed, and must be left missing. `WORKER-PROMPT.md:62` requires exactly this: "leave the cell missing and continue supported cells."
- **`src/settlement/api.py`** — operator dashboard. Out of scope for W1–W4.
- **`experiments/coord02/**` and `experiments/representation/acquire/**`** — independent lanes with their own entries. Not part of the ad01 campaign path.

## Verification boundary

Static reading plus six executed probes listed above. No candidate code was
executed, no child spawned by me, no database or gateway contacted. The
`preexec_fn` failure mode is derived from the measured `boot.check_sandbox`
string and from the `except OSError` clauses at `exec_profile.py:167` and
`launcher_local.py:750`, which do not catch `ImportError`; that specific
propagation path is `(guess)` until a live probe confirms it.
