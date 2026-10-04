# AD01 software and graph: what the leak actually is

Source `9b12277`, branch `codex/agent-society`, worktree `.worktrees/instr-ad01`.
One file changed: `experiments/ad01/packet.py`. Nothing else. No test suite was
run and no WSL was started, so every claim below is either measured by a plain
Python probe against the frozen world or cited to a line.

The census at `reports/workstreams/m3-instrument-census.md` is right that the AD01
software and graph worlds leak their answer. Its account of *how* does not hold,
and its recommendation ("state which threat model a study uses") is wrong for the
reason that matters. The leak is not a matter of a policy being able to import
the generator. It is a matter of the answer being a field on the task.

## What the threat model actually is

**An in-child policy does reach these worlds, and it never needs the generator.**

The census says the leak "is fatal for the in-child model and irrelevant for the
wire model, so the fix is to state which model a study uses". That premise is
wrong, because `verify_member` refuses every route a member would use to import
anything:

- `method_exec.verify_member` rejects `ast.Import` and `ast.ImportFrom` at
  `experiments/ad01/method_exec.py:738` with `refused: imports-forbidden`.
- It rejects attribute access on any name starting with `_` at `:732` and `:740`,
  which covers `__class__`, `__globals__` and every other reflection escape.
- `__import__` is in `_FORBIDDEN_CALLS` at `:37-40`, alongside `open`, `eval`,
  `exec`, `compile`, `getattr`, `globals` and `vars`.
- 0 of the 4421 member sources under `.ad01-runs/*/member.py` contain the string
  `import`, measured by grep.

So the generator is not reachable from a child. Nothing is. The census inferred
reachability from `method_exec` running children "against the repo", which is
true of the *driver* and false of the *member*.

The actual exposure is the task dict itself, and it splits three ways.

| Call site | What the child receives | The answer |
|---|---|---|
| `trajectory.py:1839`, `records.py:1617`, `s09_m3_pilot.py:229,494`, `s09_m2_reload_proof.py:67`, `construct.py:129` | the raw task | `fault` and `witness` **verbatim** |
| `invr1b14_retention.py:177`, `w2_retention_campaign.py:840` | `packet.method_task_view` | `fault` and `witness` **verbatim** |
| `control_arm.py:368`, `experience_axis_run.py:260`, `policy_step.py:263`, `learner.py:398` | `packet.public_task_view` | `template` names the fault |

Six call sites hand the child a dict containing the key `fault` with the answer
in it. Measured on `ad01-w0-dev-sw-00`: the raw task's keys are
`['family', 'fault', 'ops', 'seed', 'task_id', 'template', 'witness']`. No import,
no inversion and no source read is required. This is the worst of the three and
the census did not find it.

`method_task_view` is not a defence either. Its docstring at `packet.py:121-129`
says it drops "sealed generic keys, but only the policy view is an allowlist".
It is a denylist, so `fault` and `witness` pass straight through. Measured:
`method_task_view` on the same task returns `['family', 'fault', 'ops', 'seed',
'task_id', 'template', 'witness']`.

The public view is the only allowlist, and it still leaks. `template` is
`"stale-read-2chain"` or `"stale-clear-core"` (`splits.py:402,415-416`), which
contains the fault name as a substring. Measured: on all 27 frozen software
tasks, `task["fault"] in public_task_view(task)["template"]` is **true, 27 of
27**. A member that cannot import and cannot see `fault` can read the fault off
the template with a substring test. `packet.py:137-143` already says so and
explains that this is why `held_out_values` treats the fault as not held out,
which is why the existing leak checks are blind to it.

`tests/test_s09exp_freeze.py:75-79` asserts the same thing as intended
behaviour, and `tests/test_s09_e2_scored.py:243-245` uses `template` as a
deliberate discriminator. `control_arm.py:163` describes `template` as "a public
field the freeze publishes". Three places treat the leak as load-bearing.

## The task is a pure function of a public id, and that is fixable

`generate_ad01_software` is a pure function of `(world, kind, index)`
(`splits.py:377-429`), all three recoverable from `task_id`. Measured:

```
ad01-w1-within-sw-00 -> seed 5401  fault stale-read
ad01-w0-dev-sw-01    -> seed 5102  fault stale-clear
ad01-w2-transfer-sw-02 -> seed 5503 fault stale-read
```

The seed is `AD01_SW_BASE["use"|"dev"] + world * 100 + index` (`splits.py:372-374`)
and the fault is `FAULTS[index % 2]` (`splits.py:383`). Both are arithmetic on
digits already in the public id. **No key closes this**, because there is nothing
to hide behind: the task is fully determined by three small integers that the id
must publish for the study to be addressable. Any keyed digest over
`(world, kind, index)` is reversible by enumeration over 3 worlds x 3 kinds x 3
indices = 27 candidates.

This is why the census's option (c), copying `boolean_rule.key_id`, does not work
here even granting that the key is committed at `worlds.py:50`. That key protects
an identifier over a 0..9999 seed space. This id is not opaque material; it is a
label. Keying it makes the arithmetic harder to *read*, not impossible to
*perform*, because the fault is not derived from the digest. It is
`FAULTS[index % 2]`, computed from the trailing digits the id publishes in
plaintext either way. **I did not adopt option (c).** It would add a second
identity mechanism and a source of drift for no security gain.

## What changed

`experiments/ad01/packet.py`, `PUBLIC_TASK_FIELDS`, +7/-1. `seed` removed from
the allowlist.

The field was a second copy of a value `task_id` already gives away, so this is
subtraction rather than a new mechanism. Verified on the frozen world after the
edit: `seed in PUBLIC_TASK_FIELDS` is False, and no task's public view carries
it.

`held_out_values` is unchanged on all 54 frozen tasks, measured before and after.
Nine tasks return `['missing']` both on `main` at `9b12277` and in the worktree;
that value comes from a witness whose `ref.type` is `"missing"`, not from this
edit.

`method_task_view` is untouched and still carries `seed`. That is correct: the
method view is the task's own oracle and the seed is the recipe the grader needs.
A child that receives the method view still receives the seed. See below.

**This does not fix the leak.** `template` still names the fault on 27 of 27
tasks, and the six raw call sites still hand over `fault` verbatim. Removing
`seed` deletes a redundant authority and nothing else. I am not shipping it as a
repair.

## What is deliberately not changed, and why

**The raw-task call sites** (`trajectory.py:1839`, `records.py:1617`,
`s09_m3_pilot.py:229,494`, `s09_m2_reload_proof.py:67`, `construct.py:129`).
These pass the unfiltered task. That is the more serious half of the defect and
it is in files another lane owns. Fixing it is not a subtraction here; it is a
boundary decision about which of two views each call site owes the child, and
`trajectory.py` is explicitly named in my constraints as off-limits.

**`template` in the public view.** Removing it is the single highest-value
change available and I cannot make it. Three consumers treat it as load-bearing
and I cannot run the suite to see what else moves:
- `control_arm.py:163-183` keys its STEP selector on `template` plus atom counts.
  Removing the field collapses its shape table onto `unshaped`.
- `experience_axis_run.py:263` mirrors that table.
- `tests/test_s09_e2_scored.py:243-245` branches on it inside a policy fixture.

It is also frozen evidence: `template` is a key in all 54 committed task JSONs,
pinned by `manifest.json` digests. Changing the view without regenerating the
worlds leaves the field present on disk and in every frozen bundle, so the edit
would fix the live view while historical evidence keeps leaking. That asymmetry
is worse than doing nothing.

**The fault-from-parity rule** (`splits.py:383`). Re-deriving the fault from
something other than `index % 2` cannot be done inside the frozen world.
Measured: all 27 frozen software tasks satisfy
`generate_ad01_software(w,k,i)["fault"] == FAULTS[i % 2]` exactly. Change the rule
and every op list changes, so all 27 manifest digests change with it. That is a
freeze regeneration, which is committed evidence and out of scope here.

## What remains broken

1. Six call sites hand the child the key `fault`, with the answer in it. Fatal
   for any claim that a member inferred anything. Owner: the mission-migration
   lane.
2. `method_task_view` is a denylist, so `fault` and `witness` survive it at both
   of its call sites. `packet.py` is mine and I did not convert it to an
   allowlist, because the method is scored against the witness by design and
   `packet.py:121-129` states the intent. Converting it is a semantics change
   that needs the tests I cannot run.
3. `template` names the fault in the public view, 27 of 27. Blocker is the
   frozen JSONs and the three load-bearing consumers, not the idea.
4. The task remains a pure function of three public integers, so a keyed id
   cannot help. Fixing this means the fault stops being a function of `index`,
   which means regenerating the freeze.
5. No test suite was run. I cannot say whether `test_s09exp_freeze.py`,
   `test_s09_e2_scored.py`, `test_s09_scoring_integrity.py` or
   `test_ad01_live_acquired_ddmin.py` pass after the `seed` removal. The
   measured blast radius is one key in one allowlist and no change to
   `held_out_values`, but that is a static argument, not a green run.

## The conclusion the human needs

**The AD01 software and graph worlds cannot carry a discovery claim until the
frozen world JSONs are regenerated.** The census reached REMOVE for four
reasons; this lane confirms reason one is real and finds it is worse than
described, and that the census's proposed fix does not apply.

Not one of the three leaks is a keyed-hash problem, and not one is fixed by
declaring a threat model. A policy that cannot import anything and cannot read
the source still reads the answer off `template`, or reads the key `fault`
outright at six call sites. Declaring the wire model would change the
instructions to the study; it would not change one line of what any member
observes.

The cheapest real repair, in order. First, route all six raw call sites through
one named view, and make that view an allowlist like the policy view already is.
That is a boundary fix and it invalidates no frozen bytes. Second, drop
`template` from the public allowlist and regenerate the world JSONs so the field
is not on disk either. Third, re-derive the fault from the seeded rng rather than
from `index % 2`, which requires a freeze regeneration and a digest rewrite in
the same commit.

I did steps that were mine to take. Steps one and two need files I was told not
to touch or evidence I was told not to edit. Step three needs a human decision
about rewriting a freeze.
