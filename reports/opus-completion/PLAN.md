# Stage 9 policy revision cycle: framing and designed playbook

Branch `codex/stage-09-opus-completion`, cut from checkpoint `8e05c14`.
Baseline measured before any change: 84 passed in 648.34s, exit 0 (`D:/AI/s09o/logs/baseline.log`).

## Phase A: frame

### Done as a falsifiable predicate

One public command, run twice against a real PostgreSQL database with a fresh second
process, satisfies all of the following on the software domain and on the graph domain:

1. The command acquires a task method, checks it, retains it, and executes that retained
   method's exact frozen bytes. An unavailable method is refused without constructing a
   replacement.
2. The command incorporates permitted operational feedback, opens a durable revision
   proposal, constructs `kind=learning-policy, entry=STEP` bytes with parent lineage, and
   freezes those exact bytes.
3. Production, not the test, then runs a policy-specific sealed assessment over a panel
   whose identities and comparison rule were frozen before exposure. The assessment
   executes the candidate STEP bytes as a policy through the trusted child boundary and
   records executed decisions, resulting effects, downstream task quality and full
   resource cost for both the incumbent and the candidate.
4. Production binds the exact assessed bytes when the frozen rule qualifies them, or
   records an explicit rejection that leaves the incumbent active.
5. A second, fresh OS process resumes the same investigation and decides through the bound
   policy bytes, resolved by production from durable state, with no caller-supplied
   consumer and no second model request.
6. `scripts/s09_verify.py` recomputes the outcome from the exported evidence with no
   provider and no live database, and its recomputed verdict equals the recorded verdict.

The predicate is false if any of assessment, activation or continuation is supplied by a
test fixture. It is false if the policy verdict is derived from a task-method reducer
score, a source digest comparison, or an ABI dry run alone.

### Scope, quantified

Eight units of production change, located by an independent source trace:

| Unit | Location | Rough size |
|---|---|---|
| U1 policy assessment panel and frozen rule | new `experiments/ad01/policy_assess.py` | ~220 lines |
| U2 policy-specific sealed assessor | same module, called from `records` | ~180 lines |
| U3 continue past freeze into assess then bind-or-reject | `trajectory._construct_policy_revision` | ~70 lines |
| U4 production resolves the bound policy | `trajectory.run_campaign`, `resume_campaign` | ~90 lines |
| U5 policy release binding kept distinct from method releases | `selection.py` | ~60 lines |
| U6 export and offline verification of policy assessment and binding | `records.export_campaign`, `verify_campaign` | ~140 lines |
| U7 one public lifecycle command | `experiments/ad01/cli.py` | ~80 lines |
| U8 prospective comparison wiring for the new cycle | `scripts/s09_pilot.py` | ~120 lines |

Blockers surfaced by grounding:

- `records._execute_assessment` calls `method_exec.verify_member` and
  `run_member_out_of_process`, so it rejects a `STEP(view, state)` source on arity before
  it can score anything. It is the wrong evaluator, not a broken one. It must keep serving
  task methods.
- `run_campaign` builds the legacy `DecisionConsumer` when no consumer is passed. Every
  existing STEP test therefore injects its own consumer, which is exactly the
  test-supplied lifecycle the assignment forbids.
- `test_s09m34_cycle.py::test_full_deterministic_cycle_with_provider_double_only` is named
  for a full cycle but calls `open_revision_proposal`, `freeze_candidate`, `assess_frozen`
  and `bind_revision` from the test body, with a task method as the candidate. The name
  does not prove the call path.
- The gate set takes 10m48s. One long run at a time.

### Rigor level: high

Two one-way doors justify it. Journaled `request_id` values are permanent once written, so
a wrong identity scheme cannot be edited away later. The live study spends a real grant
capped at 100 model calls with no paid fallback, and a replayed or mis-scoped grant cannot
be un-spent. Rigor is spent on gates and frozen artifacts: a red behavioural check before
each production repair, the comparison rule and panel frozen and digested before exposure,
offline recomputation with no provider, and four typed Jev checkpoints.

## Phase B: designed workflow

### The data shape, named first

A policy assessment is a distinct artifact from a method assessment. It shares identity,
authority and journaling with the method path and shares no evaluator.

```
PolicyPanel     = {panel_id, task_ids[], panel_digest, sealed_answers_excluded: true}
PolicyRule      = {rule_id, margin, min_preserved, resource_ceiling, tie: "reject"}
PolicyArmRun    = {policy_digest, decisions[], effects[], quality{}, resources{}}
PolicyAssessment= {attempt_id, proposal_id, candidate_digest, entry: "STEP",
                   protocol_id, evaluator_version, panel, rule,
                   arms: {incumbent: PolicyArmRun, candidate: PolicyArmRun},
                   outcome: "bind" | "reject" | "unavailable", reason}
```

`decisions[]` holds one row per executed STEP call with its action kind, target and state
digest. `effects[]` holds one row per accepted effect with its operation id.
`quality{}` holds the downstream task outcome. `resources{}` holds step calls, model
calls, queries and child wall time, so cost is complete rather than partial.

The comparison rule is finite and never divides by zero: the candidate qualifies only when
preserved count is at least `min_preserved`, its quality exceeds the incumbent's by at
least `margin` in absolute terms, and its resource total does not exceed the incumbent's by
more than `resource_ceiling`. A tie rejects.

### Unit sequence, riskiest unknown first

U1 and U2 come first because "can a frozen STEP policy be executed and scored as a policy
at all" is the unknown that invalidates everything downstream. U6 comes before U7 so the
public command is provable the moment it exists. U8 is last because the comparison is a
consumer of the finished cycle, not a part of it.

Order: U2 and U1 together, then U3, then U4, then U5, then U6, then U7, then U8.
Each unit ends in a red check before the repair and a green check after.

### Fan-out seams

Three seams are genuinely disjoint and get parallel workers with their own worktrees and
their own `s09_` databases: the assessor module (U1, U2), the export and offline
verification path (U6), and the adversarial review lane. U3, U4, U5 and U7 all edit the
same driver and stay with one writer, me. U8 waits for a merged tip.

## Phase C, D, E

Phase C runs each unit as an experiment against the real artifact. Phase D appends a row to
`D:/AI/s09o/decisions.tsv` as each unit lands. Phase E rechecks the whole predicate on the
real product and then the live study.
