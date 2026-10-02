# W1 / E1 second live construction campaign

Run id `w1-e1-boolean-r2`. Driver `experiments/ad01/w1_e1_campaign_r2.py`.
Every construction attempt recorded here was dispatched through the
shipped acquisition path (`LiveGuard` over `HttpGatewayAdapter`,
`render_output_prompt`, `output_operation_id`,
`extract_and_validate_boolean`, `RuleSession`) and none through a private
client, a private prompt or a private parser.

## What this campaign is not

It is not a rerun of `w1-e1-boolean-r1`. That campaign recorded eight
lineages and every one ended in `route-refusal` or `transport-loss`,
because the route contract had two halves that disagreed about one field.
That is a fact about the harness, not about the model, so r1 is retained
as invalid and no r1 cell is carried forward, repaired or selectively
re-run. r2 is a new study root with a new freeze.

## The route repair this campaign depends on

`3721cd6` made `gateway_http.route_matches` the one comparison of a whole
returned route, and routed the adapter, the catalog half and `LiveGuard`
through it. r1's blocking defect cannot recur through a split that no
longer exists. Every lineage here carries the evidence that it did not:
`provider: "Nvidia"` against a frozen `nvidia`, `tier: "free"`, and
`route_error: None`.

The api is `chat`, not the preflight suite's `responses`. The responses
API publishes no `provider`, so `_returned_route` yields `None` and the
frozen route refuses a correct answer after the tokens are spent. That
defect is recorded in r1 and belongs to `src/settlement/gateway_http.py`,
which this lane does not own.

## Acquisition is one cell wide, and that was verified, not assumed

The single most decision-relevant fact about E1's shape is that the
Boolean output-shape predictor is the only cell with a shipped
acquisition path. `python -m experiments.ad01.w1_e1_campaign_r2 census`
settles it offline, at no model call, and is reproducible from this
directory.

The check is a search rather than an assertion. Every `def` containing
`acqui` is read off the parsed source of `experiments/`, `scripts/` and
`src/`; every non-Boolean record builder is checked for whether it
accepts text; and every site the search finds is adjudicated. The
Boolean-only claim rests on a refusal, not on a naming convention:
`output_operation_id` raises `unknown arm or task` for a split outside
`OUTPUT_TASKS` and `unfrozen task or attempt` for a seed outside the
frozen pair. `render_output_prompt` and `extract_and_validate_boolean`
have no counterpart for another world.

The non-Boolean record builders all take no text. `make_record`,
`ordering_document`, `graph_policy_record`, `ordering_graph_record` and
`swe_graph_record` are authored literals or tables keyed on a lineage
index. Their executors are real, typed and reachable in process; nothing
asks a model to write one.

**One counter-path exists, and it is not an E1 cell.**
`construct.construct_method` (`experiments/ad01/construct.py:209`) really
does take a provider's `entry` source, gate it on a settled store receipt
and mint a STEP artifact via `policy_step.make_policy_artifact`. Its
shipped entry point is `live_construct.construct_live_method:850`, called
from `scripts/ad01_r3_compare.py:134` and `ad01_r4_compare.py:188`. It is
excluded from E1 for two recorded reasons, not for convenience: it needs
a PostgreSQL DSN at its first statement, which this host does not have
(measured: `ConnectionTimeout`), and its world is the invl01/invl02
method world rather than a Boolean, ordering or SWE policy world.
`experiments/representation/acquire/campaign.py:337` is the same shape,
broker-bound, in the representation panel's own reducer world. Both are
named in the census rather than left for a reader to find.

So E1's acquisition column is one cell wide, and that is a property of
the shipped harness. It is not a claim that the model cannot write an
ordering program, a typed AST or a graph.

## What was asked and what came back

**Zero constructions, from a model that answered.** 6 of 8 dispatches
reached the provider and returned real bytes; 2 were HTTP 502s recorded
as `transport-loss`. All 6 answered dispatches failed as
`invalid-program` of one specific kind, `over-length`: the model reasons
the task out in prose, runs to the frozen 2048-token ceiling, and never
emits the requested 512-character JSON object.

| Treatment | Lineages | Verified offline | Construction events | Unique source programs | Outcomes |
|---|---:|---:|---:|---:|---|
| P1 interface-only | 4 | 4 | 0 | 0 | 3 `invalid-program`, 1 `transport-loss` |
| P2 prior-task summary | 4 | 4 | 0 | 0 | 3 `invalid-program`, 1 `transport-loss` |

The two arms are identical cell for cell. That is a real negative result
about this pair, not a gap to be filled by hunting. The full reading is
in `RESULTS.md`, and the recomputed tables are in `campaign.json`.

## Re-verifying this offline, with no network

```bash
uv run python -m experiments.ad01.w1_e1_campaign_r2 summarize
uv run python -m experiments.ad01.w1_e1_campaign_r2 verify
uv run python -m experiments.ad01.w1_e1_campaign_r2 census
```

`verify` withdraws `LiveGuard.infer` first, so any path reaching for a
gateway raises rather than quietly succeeding, and it calls the shipped
`live_construct.verify_preflight_record` on every record that reached the
wire. A record that never reached the wire has no response to attest, so
it is reported under `no_response_to_attest` and counted as neither a
pass nor a failure.

Re-verifiability is only a real claim if a tampered record fails. Copy
the directory, swap any `raw_response`, and `verify` reports one failure
naming the digest mismatch (`preflight response does not match its own
dispatch evidence`) while every untouched record still passes. Measured
on this run; `test_verify_refuses_a_tampered_record_rather_than_reverifying_it`
holds that check.

## Three numbers that are not one number

`campaign.json` reports `construction_events`,
`unique_source_programs` and `retained_artifact_records` separately. A
construction event is a lineage whose bytes parsed and ran; a unique
source program is a distinct candidate digest among those bytes; a
retained artifact record is a file on disk. Independent calls may
legitimately converge on identical programs, and four records sharing one
digest is four events of one program, not four acquisitions.

## The taxonomy stays five ways

`route-refusal`, `transport-loss`, `empty-content`, `invalid-program` and
`poor-task-result` are distinct outcomes and are never merged. A campaign
that cannot tell a route refusal from a poor task result is reporting an
apparatus fact as a model fact. `invalid-program` additionally carries an
`invalid_program_defect` of `over-length` or `would-not-parse`, because
a reply that never stopped talking and a reply that stopped and was still
not a program are different findings with different causes.

## The authored baseline is measured, not dispatched

`campaign.json` carries one `authored-control` row, run in-process through
`boolean_graph_policy.choose_action` at zero model calls. It is never
counted as a lineage. On this task the authored arm probes once and
declines to commit, because its commit guard is keyed to a fixed constant
the observation does not match. That is a decision, not a zero, and there
is no predictor to score. The STEP and typed-AST authored arms both need
the bounded child this coordinator cannot spawn, so one of three authored
representations is measurable on this host.

## Counters

`exposure.json` is written before the first dispatch and re-written after
every attempt, so a process killed mid-campaign leaves the unfinished
exposure on disk rather than in memory. The final ledger records the
attempt count, the dispatches spent, the refunded pre-gateway
refusals, and any driver fault. A driver fault leaves its attempt
unsettled rather than settled as a result.

The cap sheet's `N = 4 x supported cells x treatments` gives
`N = 4 x 1 x 2 = 8` construction opportunities and a model-call ceiling
of `N x 2 = 16`. The run spent 8 with 0 refunded and 0 driver faults.
The repair allowance is recorded as unspent and is not spendable here:
`render_output_prompt` refuses an attempt outside `(1, 2)` and
`output_operation_id` refuses any seed outside the frozen pair, so a
repair would have to reuse the same task and the same identity.

No credential is written to this directory. The guard enforces endpoint,
model, provider and tier on every response, so a paid route is refused as
`route-refusal` before it can be mistaken for a model result.