# Context policy pilot 01

Executed 2026-09-10 through the human-supplied local gateway. Requested and returned model ID: `claude-opus-4-6-thinking`. Eight live requests completed, with no retry or output truncation. This is an independent read-only research apparatus, not the Settlement runtime's end-to-end learning experiment.

## Question and frozen protocol

Can a simple context policy following explicit required references and their dependencies preserve decisions on a small structured panel while delivering less input than the complete authorized context?

The [protocol](evidence/context-pilot-01/protocol.json) was written before the first inference request. It fixes four hand-authored cases, expected decisions, decisive source IDs, arm order, instructions, model, eight-request limit, 2,048 output-token request cap, 32,768 input-character cap per request, 120-second timeout and zero retries. Protocol digest: `7a81ee94008d995420039ad5b98daabb3ad5f05a49ed3ce4492d6b5defd4004a`.

The full-context control receives every authorized record, including irrelevant archived records. The dependency-context arm starts from required references and follows explicit links. Both receive the same decision instructions and complete decisive evidence. Expected answers remain in the apparatus and are not sent to the model. Neither arm is permitted external actions. The candidate policy is deterministic and uses hand-authored links; it is not learned retrieval.

The four cases concern an unresolved external operation, alternative evidence after a premise retraction, a known counterexample outside a method's supported scope, and missing bytes for a pinned artifact. These are closed-world synthetic operational questions. Their rubric follows declared rules, not another model's judgment.

## Result

| Measure | Full context | Dependency context |
|---|---:|---:|
| Correct next decisions | 4/4 | 4/4 |
| Correct decisive evidence references | 4/4 | 4/4 |
| Delivered input characters, including common instruction | 24,075 | 5,019 |
| Gateway-reported prompt tokens | 5,213 | 1,181 |
| Gateway-reported completion tokens | 554 | 490 |
| Total observed request time | 25.218 s | 20.843 s |

Dependency context used 77.35% fewer reported prompt tokens and 79.15% fewer input characters. Correctness was tied. Individual request latency was not consistently lower, and four observations per arm do not establish a latency advantage. Gateway usage is recorded as reported usage, not independently verified monetary billing or a guarantee about hidden reasoning computation.

All requests returned `finish_reason: stop`. All eight responses used JSON code fences; the frozen parser explicitly tolerates that wrapper. Correct decision scores therefore do not imply strict unwrapped-JSON format compliance. The [results](evidence/context-pilot-01/results.json) preserve exact delivered packets, model response text, response model ID, reported usage, timings and per-case scoring. Credentials and private endpoint identifiers are excluded.

## What follows, and what does not

This supports a narrow feasibility statement: for these four explicitly linked cases, the reduced packets preserved the correct decision and decisive evidence at substantially smaller input size. It also shows the supplied gateway can complete inference using the selected model ID.

It does not demonstrate improved correctness, learned memory, discovery of missing dependency links, robust semantic summarization, generalization to open-ended work, or superiority over a strong fixed retrieval baseline. Much of the size reduction follows directly from excluding records explicitly unrelated to the task. The experiment is small, manually constructed and sampled once per condition. No inferential promotion is warranted.

It does not exercise PostgreSQL state, source invalidation, continuation recovery, real containment, runtime budget settlement or paid billing. It does not discharge DEV-01 through DEV-12, CTX-01 through CTX-10, or E4. Their integration and stronger empirical obligations remain in the roadmap.

## Design consequence

Implement the deterministic decision-context resolver first. Its job is to deliver existing experience and current obligations with explicit dependencies; no learned retrieval engine or new storage platform is justified by this result. Test it inside the actual development/continuation path, then compare against a strong fixed retrieval policy on independent groups with realistic distractions and missing links.

The separate [readiness assessment](../reviews/DEVELOPMENT-01-READINESS.md) identifies four episode seams that must be corrected before claiming the full runtime has performed the intended learning experiment. Those corrections and context materialization form one bounded Development-02 assignment.

## Reproduction and apparatus checks

[Apparatus source](../reviews/probes/context_policy_pilot.py), using only the Python standard library. Supply `PILOT_GATEWAY_URL` and `PILOT_GATEWAY_KEY` through the process environment and select a new output directory:

```sh
python reviews/probes/context_policy_pilot.py reports/evidence/context-pilot-new-run
```

The model is pinned in the apparatus. Prior output directories are refused to preserve evidence. The preflight checked eight requests, payload bounds and preservation of each case's decisive evidence. The source digest in the frozen protocol identifies the exact apparatus run. Post-run checks verified the protocol digest, call order, every packet digest and decisions parsed from raw responses under the frozen fence tolerance. No generated code was executed.
