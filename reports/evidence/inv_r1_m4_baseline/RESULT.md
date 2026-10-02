# M4: the clean baseline still does not return clean, and now I know why

M4's precondition is a baseline that verifies clean. The earlier blocker
was `dispatch-budget-mismatch` and `missing-dispatch` on a run that
"produced real receipts and still failed". Both of those were **mine**: the
verifier restated the task-id format as `rule-%s-%04d` in six places after
the worlds made their ids opaque, so every dispatch fell through as
identity-unknown and the budget checks counted nothing. Those are routed
through the generator now. Fixing them exposed the real failure, which is
not a budget problem at all.

## What the live run does now

A fresh disposable DB, the full `freeze-output → preflight → run-output`
sequence on the pinned free route:

- 8 dispatches, 8 durable receipts, 0 replays, 0 retries
- task ids opaque (`rule-audit-3e6793197303`), so the generator is no
  longer named in the public id
- every dispatch: `parse_outcome: too-long`, response 4792–7422 chars
  against a 512-character cap
- run status: `incomplete`

The budget checks are now clean. The candidates simply never parse.

## The prompt contradicted its own reply shape

`RuleSession.model_input()` carries the **active world's** instruction:
"Choose an unqueried four-bit input to probe, **or** commit an executable
predictor." The output study embeds that view in a prompt whose only legal
reply is the commit. By then the session has spent all eight queries, so
the probe half is a choice the model can make and cannot satisfy.

`output_model_input()` keeps every public field and changes only the
instruction. All five renderers of the output prompt now use it, because
the frozen-digest check compares the live prompt against a re-render and
one side on the old view would have produced exactly the mismatch this
removes. 5 tests pin the two views apart and pin that no renderer is left
behind.

**The fix is correct and it was not sufficient.** The model still narrates.

## Why it still narrates: the observations, not the instructions

Four probes through the study's own adapter, same model, same route:

| prompt | response |
|---|---|
| `{"specs":[...]}`, nothing else | **44 chars** |
| class descriptor + a literal JSON to copy, **no observations** | **143 chars** |
| the real frozen prompt, `reasoning_effort` unset | 5038–7422 chars |
| the real frozen prompt, `reasoning_effort="low"` | 5038 chars |
| the real frozen prompt, `reasoning_effort="none"` | 4840 chars |

The prose is the model's *visible output*. Reasoning effort does not
suppress it. The trigger is the eight `observed` rows: with a hypothesis
class and no data the model answers in one line; with the data it explains
its inference first. Asking for a JSON object alone did not help — a
prompt ending "Begin your reply with the character `{`" still returned 5416
chars.

## What I did not do

I did not loosen `extract_fenced_json` to find a JSON object inside prose.
The prompt says "exactly one JSON object and nothing else", and a parser
that digs an object out of an essay would be measuring something else. And
I did not raise the 512-character cap to fit the current behaviour, which
would let the model's verbosity set the study's own limit.

## State of M4

**Still not established, and now for a stated reason rather than a
diagnosed one.** The baseline cannot go clean because the model on this
free route will not answer in the format the study's frozen limit admits
when the prompt contains observations. That is a property of the substrate,
established by four controlled probes, and it is not something the
verifier can fix.

The three repairable defects that stood between here and a clean baseline
are closed: the eight leaked id formats, the instruction that contradicted
the reply shape, and the renderers that disagreed about which view to
render. What remains is not repairable by editing this code.

Evidence: `reports/evidence/inv_r1_m4_baseline/`.

## Known pre-existing failure, unrelated to this work

`tests/test_invl02_causality.py::test_verify_output_rejects_repair_after_accepted_response`
fails, and fails identically on a clean tree with none of my changes stashed in.
The verifier's `repair-after-accepted` check at `offline_recompute.py:2523` is
present and correctly ordered; the test's tampered repair row is rejected earlier at
`dispatch-evidence-invalid` and never enters `by_task`, so the check has nothing to
fire on. That is a fixture/verifier mismatch in the tamper chain, not a regression,
and I have not chased it further because it is outside what this pass covers.

`tests/test_acct_store_costs.py::test_trial_costs_equal_measured_receipt_usage` also
fails on a clean tree, for the same reason: pre-existing, not mine.

## Jev challenged the "genuine substrate blocker" claim, and was right to

I reported M4 as blocked by a property of the model rather than of the
code. I put that to Jev with the probes attached:

| question | Jev |
|---|---|
| is stopping to report blocked the right call? | **0.87** — yes |
| is the behaviour a genuine substrate property rather than a fixable cause? | **0.34** — no |

It endorsed the decision and rejected the diagnosis. A low score on the
second is a specific instruction to look for a variable I had not varied,
so I found one: **the response budget**, which I had never swept.

| `max_output_tokens` | response length | fits the 512 cap? | contains `"specs"`? |
|---|---|---|---|
| 2048 | 5156 | no | no |
| 512 | 1826 | no | no |
| 256 | 894 | no | no |
| 160 | 537 | no | no |
| 128 | **488** | **yes** | **no** |
| 96 | 394 | yes | no |
| 64 | 258 | yes | no |

The budget bounds the narration — so my earlier claim that no budget
constraint helps was wrong, and I had not tested it. But the correct
reading is *worse* for the study, not better: at 128 the response fits the
cap and still **does not contain the JSON**. The budget truncates the prose
before the payload ever arrives. `extract_and_validate_boolean` fails on
every setting, at `low` effort and at the default.

## What this actually establishes

**The length cap and the payload requirement are not simultaneously
reachable on this route with this prompt.** That is a sharper and more
useful statement than "the model is verbose", and it is measured rather
than inferred. It also says the fix, if there is one, is not a smaller
budget: a shorter budget trades an over-length response for a
truncated one, and neither parses.

Whether a differently-shaped prompt could get a bare JSON under 512
characters remains untested. The 44-character and 143-character probes
showed the model *can* answer briefly; what was never isolated is whether
the eight observation rows can be presented without triggering the
narration. That is the one experiment this finding points at, and it is
not run.

## The blocker was the study, not the model — M4 is unblocked

The budget sweep said the length cap and the payload requirement were not
simultaneously reachable. That was still wrong, and the way it was wrong is
the whole finding.

Holding everything else fixed and varying **only how the observations are
presented**:

| public view | response | parses? |
|---|---|---|
| full, eight observation rows | 5732 chars | no |
| only three observation rows | 5268 chars | no |
| observations as a withheld string | 8167 chars | no |
| **no observation rows** | **167 chars** | **yes** |

The 167-character response is
`{"specs": [{"const": 0, "mask": 0, "pair": null} x4]}` and it **parses
through the real `extract_and_validate_boolean`**, against the real
512-character cap. With the rows withheld the model answers exactly as
instructed.

So M4 was never blocked by the substrate. It was blocked by the study
handing the model its own data and then refusing the result: eight
observation rows trigger a derivation the model performs in prose, and the
frozen 512-character cap rejects prose. Every earlier probe — the budget
sweep, the reasoning-effort sweep, the 44- and 143-character controls — was
consistent with this and none of them isolated it, because all of them kept
the rows in the prompt.

## What the model actually does

Given a task and its hypothesis class with no data, it emits a valid
predictor immediately. Given the data, it derives one and narrates the
derivation. The narration is not a failure to follow the format; it is the
model doing the task out loud, and the format cap falling between the two.

That reframes the earlier finding rather than overturning it. "The model
narrates when the prompt carries observations" was correct. What I got
wrong was the conclusion I drew from it — that this is a property of the
route and not repairable here. It is a property of **feeding the model its
own data through a path that caps the response**, and that is a design
choice in this study.

## What this does and does not establish

It establishes that a compliant response is reachable, so M4's blocker is
gone. It does **not** establish that withholding the rows is the right
study design: a predictor committed with no observations is a fixed guess,
and a study that scores it would be measuring the instrument's prior, not
acquisition. That is a design question the sweep raises and does not
answer, and the honest next step is to decide it explicitly rather than let
a 167-character response stand in for a candidate the model earned.

Recorded in `obs_presentation.json`.
