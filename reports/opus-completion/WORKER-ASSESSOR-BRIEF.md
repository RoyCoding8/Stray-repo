# Worker A brief: policy-specific sealed assessment

You own exactly two new files. Do not edit any other file in the repository.

- `experiments/ad01/policy_assess.py` (new)
- `tests/test_s09o_policy_assess.py` (new)

Repository: `D:\AI\Agent-Society-v2-investigation-review`, branch `codex/stage-09-opus-completion`.
Work in place in that checkout. Another writer owns `trajectory.py`, `records.py`,
`selection.py` and `cli.py`, so a change there will be discarded and will waste your work.

## Why this exists

`records._execute_assessment` (`records.py:1048-1108`) is a task-method evaluator. It calls
`method_exec.verify_member`, which requires an `ENTRY(task, oracle, max_queries)` arity
(`method_exec.py:94-154`), so a `STEP(view, state)` policy source is rejected on arity
before it can be scored. It then scores with `_check` and `_size` and binds when
`wins > 0`. A reducer win count is not evidence that a learning policy improved anything.

The governing assignment states: an ABI dry run, a changed source digest, or a method
reducer score alone cannot qualify a learning policy. Learning-policy artifacts must be
separate from task-method artifacts, sharing identity, authority and journaling, but not an
evaluator that assumes both mean the same thing.

Your module is that separate evaluator.

## Facilities that already exist. Use them, do not reimplement them

- `policy_step.run_policy_step(record, view, state, ...)` (`policy_step.py:316-337`) verifies
  the artifact, validates view and state, and runs the policy in a bounded child.
- `policy_step.materialize_view(...)` (`policy_step.py:115-134`) builds a conforming view.
- `policy_step.verify_policy_record(...)` (`policy_step.py:175-201`) checks artifact, ABI,
  entry, origin, parent digest and exact SHA-256 bytes.
- `method_exec.verify_step_source` (`method_exec.py:364-394`) and
  `method_exec.run_step_out_of_process` (`method_exec.py:437-507`) are the child boundary.
- `settlement.store.transact` with a `Command(request_id=..., payload=...)` is the journal.
  Read `records.open_revision_proposal` (`records.py:860-898`) for the exact idiom.

Read those before writing anything.

## Required public interface

```python
PANEL_PROTOCOL = "s09-policy-assess-01"
EVALUATOR_VERSION = "s09-policy-eval-01"

def panel_for(*, scope: dict, world: int, seed: str, size: int = 2) -> dict:
    """Held-out panel. Returns {panel_id, task_ids, panel_digest, scope}.
    task_ids must be real frozen task ids of the scope's family, chosen
    deterministically from seed, and must exclude every development task id
    (see trajectory._dev_task_ids) so the panel is genuinely unseen."""

def rule_for(*, margin: int = 1, min_preserved: int = 1,
             resource_ceiling: int = 0) -> dict:
    """Frozen finite comparison rule. Returns {rule_id, margin, min_preserved,
    resource_ceiling, tie}. tie is always "reject". The rule must never divide
    by zero: compare absolute counts and absolute resource totals only."""

def freeze_protocol(dsn: str, *, proposal_id: str, panel: dict,
                    rule: dict) -> dict:
    """Journal the panel identities and the comparison rule BEFORE any candidate
    is executed against them. Idempotent under the same bytes. Raise ValueError
    if a different panel or rule was already frozen for this proposal.
    Returns {proposal_id, panel_digest, rule_id, protocol_digest}."""

def assess_policy(dsn: str, *, proposal_id: str, candidate_source: str,
                  candidate_digest: str, candidate_artifact: dict,
                  incumbent_source: str, incumbent_digest: str,
                  incumbent_artifact: dict, panel: dict, rule: dict,
                  scope: dict, protocol_id: str,
                  evaluator_version: str = EVALUATOR_VERSION) -> dict:
    """Execute BOTH arms as policies over the sealed panel and decide."""
```

## What assess_policy must actually do

1. Refuse before executing anything if `freeze_protocol` was not already journaled for this
   proposal with this exact `panel_digest` and `rule_id`. Exposure after the freeze only.
2. Refuse if `candidate_digest` is not the SHA-256 of `candidate_source`. Same for the
   incumbent. Verify both artifacts with `policy_step.verify_policy_record`.
3. If the candidate source fails `method_exec.verify_step_source`, return outcome
   `"unavailable"` with a reason. Do not return `reject`, and do not fall through to any
   task-method path. An unavailable candidate is a distinct, explicit case.
4. For each arm, for each panel task, run the policy through
   `policy_step.run_policy_step` in a bounded loop of at most `rule["max_steps"]`
   (default 6) STEP calls, threading the returned state into the next call. Record, per
   arm:
   - `decisions`: one entry per executed STEP call with `seq`, `task_id`, action `kind`,
     action `target`, and the SHA-256 digest of the returned state.
   - `effects`: one entry per action the driver would accept, with its `kind` and whether
     it was accepted. A refused or malformed step is an entry with `accepted: false` and
     its reason, not a silent skip.
   - `quality`: `{tasks: n, preserved: n, reduced: n, failed: n}` computed from the task
     outcome the policy's actions produced, using `trajectory._check` and
     `trajectory._size`.
   - `resources`: `{step_calls, model_calls, queries, child_wall_ms}`. Every number is a
     real measured count, never an estimate. A failed child still charges its step call.
5. Decide with the frozen rule and nothing else:
   - `candidate.quality.preserved < rule["min_preserved"]` gives `reject`.
   - `candidate.quality.reduced - incumbent.quality.reduced < rule["margin"]` gives
     `reject`. An exact tie rejects.
   - `candidate.resources.queries + candidate.resources.model_calls` exceeding the
     incumbent's total by more than `rule["resource_ceiling"]` gives `reject`, even when
     quality improved. State that overrun in the reason.
   - Otherwise `bind`.
6. Return a record whose keys are a superset of what `selection.bind_revision`
   (`selection.py:62-214`) reads, because that function is already gated by 84 passing
   tests and must keep working unchanged. It reads `attempt_id`, `outcome`, `protocol_id`,
   `evaluator_version`, `scope`, and `candidate_digest`. Set `attempt_id` from
   `records.assessment_attempt_id(proposal_id, candidate_digest)` so identity is shared
   with the method path. Also return `panel`, `rule`, `arms` and `reason`.
7. Never put a panel task's expected answer, solution or `candidate` content into the
   returned record, into any journal payload, or into anything a later constructor prompt
   could read. Return digests and counts. This is the leakage boundary.

## Tests you must write

`tests/test_s09o_policy_assess.py`. Follow the fixture style of
`tests/test_s09c2a_actions.py` for database setup. Own only the database name
`s09o_assess`; create and drop exactly that.

Each test asserts a literal expected value, calls the module the way production will, and
would fail if the function under test returned `None`. Required cases:

1. A candidate that genuinely reduces more than the incumbent binds, and the returned
   record carries per-arm `decisions`, `effects`, `quality` and `resources` with non-zero
   measured `step_calls` on both arms.
2. A candidate whose bytes are not a valid STEP source returns `outcome == "unavailable"`,
   with no execution charged to the candidate arm.
3. A candidate that matches the incumbent exactly is rejected on the tie.
4. A candidate that improves quality but exceeds the resource ceiling is rejected, and the
   reason names the resource overrun.
5. Exposing a candidate before `freeze_protocol` raises `ValueError`.
6. Re-freezing a different panel or rule for the same proposal raises `ValueError`.
7. A returned record contains no panel task solution bytes. Assert on the serialized
   record, searching for a string that only appears in a panel task's answer.
8. `assess_policy` called twice with identical inputs produces the identical record,
   including `attempt_id`.

## Verification you must perform and report

Run in WSL Ubuntu as user `ubuntu`:

```
cd /mnt/d/AI/Agent-Society-v2-investigation-review
export PYTHONPATH=$PWD:$PWD/src:$PWD/experiments
/home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_s09o_policy_assess.py -q -p no:cacheprovider
```

Report the exact command, the exact pass and fail counts, and the wall time. Show a red
result from before your implementation existed for at least the first three cases, then the
green result. Do not report a pass you did not observe. Do not invert an assertion to match
output.

## Style

No inline comments. A module docstring stating what the module decides is fine. Compact
functions, data-driven repeated structure, no abstraction layer that has one caller. Match
the surrounding code's formatting.
