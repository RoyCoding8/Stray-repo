# W1 / E1 r2 results

Recomputed from the written run directory with no network. Every number
here is in `campaign.json` and is reproducible with
`uv run python -m experiments.ad01.w1_e1_campaign_r2 verify`.

## The result

**Zero constructions, and this time the zero is about the model.**

r1 recorded zero constructions and said so as a harness fact: its eight
lineages all died in `route-refusal` or `transport-loss` because the
route contract had two halves disagreeing about `provider`. r2 ran on
the repaired contract and reached a provider on 6 of 8 dispatches. Those
6 returned real bytes, and every one of them failed as an
`invalid-program` of the same specific kind. The 2 remaining dispatches
were HTTP 502s from the free route, recorded as `transport-loss` and
kept distinct.

| Treatment | Lineages | Verified offline | Construction events | Unique source programs | Outcomes |
|---|---:|---:|---:|---:|---|
| P1 interface-only | 4 | 4 | 0 | 0 | 3 `invalid-program` (over-length), 1 `transport-loss` |
| P2 prior-task summary | 4 | 4 | 0 | 0 | 3 `invalid-program` (over-length), 1 `transport-loss` |

The two arms are identical cell for cell. That is a real result about
this pair, and it is a negative one.

## The three counts

| Count | Value |
|---|---:|
| Construction events | 0 |
| Unique source programs | 0 |
| Retained artifact records | 8 |

A construction event is a lineage whose bytes parsed, committed and were
scored. None did. The 8 retained records are the 8 dispatch records
themselves, and 8 records with 0 programs behind them is exactly the
distinction the prior evidence got wrong. Nothing here is an
acquisition.

## What the model actually did

Every one of the 6 answered dispatches behaved the same way. It
reasoned the Boolean task out in prose, enumerating the observed points
and their pairwise products, and never emitted the requested JSON
object.

| Lineage | Outcome | Defect | Characters | Stop reason | Provider | Tier |
|---|---|---|---:|---|---|---|
| L01-P1 | `invalid-program` | over-length | 5211 | `length` | Nvidia | free |
| L02-P1 | `invalid-program` | over-length | 5092 | `length` | Nvidia | free |
| L03-P1 | `transport-loss` | — | — | — | — | — |
| L04-P1 | `invalid-program` | over-length | 6590 | `length` | Nvidia | free |
| L01-P2 | `invalid-program` | over-length | 5185 | `length` | Nvidia | free |
| L02-P2 | `invalid-program` | over-length | 7314 | `length` | Nvidia | free |
| L03-P2 | `transport-loss` | — | — | — | — | — |
| L04-P2 | `invalid-program` | over-length | 5323 | `length` | Nvidia | free |

All 6 carry `stop_reason: length` and `output_tokens: 2048`, the frozen
ceiling, against a frozen response limit of 512 characters. The replies
run 10 to 14 times over the limit, from 5092 to 7314 characters, and are
cut mid-sentence. The single occurrence of the string `specs` in a
reply is the model echoing the schema out of the prompt, not producing a
program.

The finding is a budget-behaviour finding, not a competence finding.
The frozen protocol asks for a 512-character object and gives the model
2048 output tokens, and this free model spends all of them reasoning.
Nothing here shows it cannot state the rule; it shows that under this
protocol it does not.

## The route repair held

Every answered dispatch carries `provider: "Nvidia"` against a frozen
`nvidia`, `tier: "free"` and `route_error: None`. That is the exact
contradiction that made r1 refuse a correct answer, and it is now
accepted. The repair works.

## Reference points

| Predictor | Score |
|---|---:|
| Do nothing | 0.0625 |
| Oracle (the rule) | 1.0 |
| **Frozen floor** | **1.0** |
| Acquired, best of 6 answered | no score exists |

The floor is the oracle, so nothing could have cleared it without
recovering the rule exactly. No program was scored, so the score
distribution is empty for both cells. `min`, `median` and `max` are
`null`, not zero.

## The authored baseline, measured not dispatched

One `authored-control` row, run in-process at 0 model calls through
`boolean_graph_policy.choose_action`. It probes once and then stops
without committing, because its commit guard is keyed to a fixed constant
this observation does not match. Recorded as a decision, not a zero:
there is no predictor to score. It is never counted as a lineage.

The STEP and typed-AST authored arms both need the bounded child this
coordinator cannot spawn, so one of three authored representations is
measurable on this host. That is a deployment limit, recorded as data.

## Calls against the cap

| Item | Value |
|---|---:|
| Cap sheet line | `N = 4 x supported cells x treatments` |
| Supported cells | 1 (Boolean / output-shape predictor) |
| Treatments | 2 |
| `N` | 8 construction opportunities |
| Model-call ceiling `N x 2` | 16 |
| **Dispatched** | **8** |
| Refunded pre-gateway | 0 |
| Driver faults | 0 |

8 dispatches against a ceiling of 16, with the repair allowance
unspent. It is unspent and unspendable: `render_output_prompt` refuses
an attempt outside `(1, 2)` and `output_operation_id` refuses any seed
outside the frozen pair, so a repair would have to reuse the same task
and the same identity. The deadline was the shipped preflight's own
300s, not a number chosen to make the campaign finish; r1 measured 55s
on this prompt and 110s with no response at a 110s deadline, and
shortening it would have manufactured transport loss and called it a
result.

## One process note

`campaign.json` was re-derived once after the run. The running process
had imported `summarize()` before the `invalid-program` defect split was
added, so the first `campaign.json` left `invalid_program_defect` and
`response_characters` as `None`. The re-derivation read the same
written lineage records with the fixed summarizer, at 0 model calls. No
lineage record, no `exposure.json` and no `campaign-manifest.json` was
touched, and the exposure ledger is byte-identical. The reason is
recorded in `campaign.json` under `campaign_json_rederived`.
