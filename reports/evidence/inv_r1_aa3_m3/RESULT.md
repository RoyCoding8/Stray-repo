# M3: a competent authored control, an open menu, and what the model chose

`s09iso-m3final-root`, model `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`, tier `free`, store `s09iso_m3final_37cf4979f732`.

M3 (`WORKER-STAGE-09-CONNECTED-STUDY.md:55`) asks for construction with development experience against construction with only the public interface, plus a competent authored control at the same oracle/action/compute limits. This run has all three, paired on every task, and every send went through `authority.admit_study_call` and then `broker.dispatch_operation`.

## The arms are distinct, and by which leg

| arm | family | strategy the bytes name | source |
|---|---|---|---|
| `authored-control/graph` | graph | ddmin | `return reducers.reduce_graph(task, oracle, method='ddmin', max_queries=max_queri` |
| `authored-control/software` | software | ddmin | `return reducers.reduce_software(task, oracle, method='ddmin', max_queries=max_qu` |
| `dev-exp/graph` | | (construction failed) | |
| `dev-exp/software` | software | ddmin | `return {"candidate": result["candidate"], "queries": result["queries"]}` |
| `public-interface/graph` | graph | ddmin | `return {"candidate": result["candidate"], "queries": result["queries"]}` |
| `public-interface/software` | | (construction failed) | |

`control_distinct` **refuses** for `dev-exp`: not-scored: no constructed member for graph
`control_distinct` **refuses** for `public-interface`: not-scored: no constructed member for software

## What each arm scored

| task | family | dev-exp | public-interface | authored-control |
|---|---|---|---|---|
| `ad01-w1-within-gr-00` | graph | **not-constructed** | **execution-refused** | 0.0833 (preserved, 16 q) |
| `ad01-w1-within-sw-00` | software | 0.6250 (preserved, 16 q) | **not-constructed** | 0.6250 (preserved, 16 q) |
| `ad01-w2-within-gr-00` | graph | **not-constructed** | **execution-refused** | 0.0833 (preserved, 16 q) |
| `ad01-w2-within-sw-00` | software | 0.7692 (preserved, 9 q) | **not-constructed** | 0.7692 (preserved, 9 q) |

## Dispatches and cost, in separate currencies

- **Admitted sends**: 4.
- **Physical dispatches**: 4. A send the adapter refused before it left the process is admitted and settled but never dispatched, and it is counted here as a dispatch only if it actually left.
- **Provider-reported cost**: the route is free, so the provider reports zero. That is an absence of a price, not a measured zero cost, and it is not comparable to an unqualified baseline.
- **Internal charge units**: absent on every send. The broker records `charge_units` only when a response is billed; on this free route it is absent, which is recorded as absent and never as a zero.

The two token counts the receipt carries are the internal denominations. They are reported here and never summed with the provider's reported cost, which is on a different scale and, on this route, is not a price at all.

## What failed, and why it is not a model failure

- **dev-exp/graph lost its response**: the receipt is `gw:s09iso-m3final-w0-construct-graph-l1-dev-exp:lost-response`: the send left and no response was recovered. The spend on it is uncertain, so it is recorded as unknown and not as a zero.
- **public-interface/software lost its response**: the receipt is `gw:s09iso-m3final-w0-construct-software-l1-public-interface:lost-response`: the send left and no response was recovered. The spend on it is uncertain, so it is recorded as unknown and not as a zero.
- **public-interface failed to execute on ad01-w1-within-gr-00**: `refused: durable child operation has no successful receipt`. Bytes: `def ENTRY(task, oracle, max_queries=16):     result = reduce_graph(task, oracle, "ddmin", max_queries)     return {"candidate": result["candidate"], "`
- **public-interface failed to execute on ad01-w2-within-gr-00**: `refused: durable child operation has no successful receipt`. Bytes: `def ENTRY(task, oracle, max_queries=16):     result = reduce_graph(task, oracle, "ddmin", max_queries)     return {"candidate": result["candidate"], "`

The graph members that failed wrote `reduce_graph(task, oracle, "ddmin", max_queries)`, which is the call `child_contract` documents. The wrapper the child binds is `(task, oracle, *, max_queries=16, **kwargs)`, so `method` is keyword-only and that call is a `TypeError`. The model obeyed the contract. `verify_member` passed it because it checks the entry's arity and never the calls inside it. This is a contract that mis-documents its own binding; the fix is in `method_exec.py`, which this lane does not own.

## What M3 can claim, and what it cannot

Mechanism `true`: the child menu is open (`menu_answers_nothing` reports no defaulting strategy), every arm executes out of process through the real sandbox, and every scored number is re-derived by the study's own checker. Live acquisition `partial`: 2 of 4 constructions returned source that qualified. The failures are recorded, not dropped. Task utility `not_comparable`: `control_distinct` refuses, so the arms ran one strategy and a tie here carries no information. This is the honest reading, and it is the reading the gate exists to force. Transfer: the acquired arms are developed on the calibration world (`w0`) and scored on `w1` and `w2`, so every acquired score is a score on a world the member was not constructed on. That is a within-family, same-representation transfer. It is **not** a cross-representation or cross-family transfer diagnostic, and it is not zero-shot: the member had development experience in `w0`. Whether the capability carries to a different *representation* or a different family is untested here. Recursive improvement `ineligible`: E4's channel has no headroom from this run.

## Reproducing this

The generator is committed at `experiments/ad01/s09_m3_pilot.py`. It writes `freeze.json`, `result.json` and this file from one run, so the prose cannot drift from the numbers.

    # no provider contact, proves the pipeline and the gates
    python -m experiments.ad01.s09_m3_pilot \
        --out /tmp/m3dry --token m3dry --dry

    # the live run this directory holds
    python -m experiments.ad01.s09_m3_pilot \
        --out <dir> --token <token>

The live form needs `SETTLEMENT_GATEWAY_ENDPOINT`, the gateway key in the environment, and `M3_MODEL`. The route is read from `SETTLEMENT_EXPECTED_ROUTE` and must pin `tier: free`; the dispatch model is the route's `requested_model`, and the store is a fresh disposable database the run drops on exit.

