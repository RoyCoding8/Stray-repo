# E2, contrast five: observation substitution

The handoff's fifth E2 contrast: *"Observation substitution on a selected set
of tasks to prove that policy behavior responds to evidence, not only task
identifiers or hardcoded family labels."*

This one matters more than the others to the campaign, because the
seed-leak finding (N-01) was exactly this failure — a policy that scored
full marks from the task id alone. The apparatus
(`learner.substitution_gate`) was built and never run against a live
acquisition.

## The gate, and that it discriminates

The gate substitutes an observation's **verdict** and holds everything else
fixed, including the task id — because a policy that keyed on the identifier
and one that read its evidence would otherwise be indistinguishable. It
executes both policies' real bytes out of process and compares the
resulting action excluding the target.

Two authored controls, run through the real gate:

| policy | reads | verdict |
|---|---|---|
| `reads-verdict` — branches on `obs[0]['verdict']` | verdict | `responds-to-evidence` (x: 3 → 7) |
| `authored-id-keyed` — branches on `task_id.startswith(...)` | task id | `responds-only-to-identifier` (x: 5 → 5) |

So the gate separates a policy that reads its evidence from one that reads
its identifier. That is the discrimination the contrast needs, and it works.

## The live acquisition, and why it could not be gated

I asked the free route for a STEP policy that depends on the observations'
verdicts. It produced a 3364-byte policy that genuinely reads verdicts —
`any(obs.get('verdict') == 'policy-failed' for obs in observations[-3:])` —
and then failed the execution envelope **twice** before the evidence
question could be asked:

1. **`crashes-on-empty-state`** — it guarded `if state is None:` while the
   STEP contract hands `{}` as the initial state, so
   `state['diagnostic_attempts']` raised `KeyError` on the first step.
2. **`action-not-an-object`** — it returned `{'action': 'diagnose', ...}`,
   the action as a bare string rather than the seven-field object, refused
   with `malformed-step-envelope`.
3. **`non-json-state`** — it seeded `state['tried_diagnostics'] = set()` and
   spread it back, and the step state must be JSON.

The first is repairable in one line, and I made that repair to see past it.
The second and third are the policy's own bytes and I did not rewrite them,
because a substituted acquisition is not the acquisition.

## What this is and is not

It is **not** a result about whether the model reads its evidence. That
question is still open for this acquisition: the policy's *logic* reads the
verdict, and the gate could not execute the policy to confirm the logic
runs.

It **is** a result about the failure modes that dominate acquisition
attempts on this ABI, and it is the direct answer to the handoff's first
research question for this contrast: the model fails here for **language**
reasons (wrong return shape, non-JSON state) and **construction** reasons
(guards the wrong initial-state sentinel), not because it cannot express
the decision. It expressed the decision correctly in the source it wrote.

**Three envelope defects in one acquisition of 3364 bytes, and zero of them
were about the decision the policy was asked to make.** That is the
measurable shape of the gap between "the model can write the logic" and "the
model can write a policy this executor will run".

Evidence: `acquired_source.py` (verbatim), `result.json`.
