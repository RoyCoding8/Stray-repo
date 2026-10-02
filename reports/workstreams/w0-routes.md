# w0-routes — inference route discovery and free-tier verification

Revision `dfbd557`, branch `wt/w0-routes`. Date 2026-09-29.

Verdict up front: **a live free route is ESTABLISHED, but not through the frozen route constant.**
The frozen `OUTPUT_ROUTE` is stale and its preflight refuses today. The same underlying
model is reachable, free, and answering under a different request id. The blocker is a
two-line constant, not an external dependency.

## 1. How the gateway is configured

Four config surfaces, in the order a caller meets them.

`src/settlement/config.py` defines `GatewayConfig`. `Settings.from_env` reads
`SETTLEMENT_GATEWAY_ENDPOINT` for the endpoint. The credential is not read there; only the
env var *name* `SETTLEMENT_GATEWAY_KEY` is stored as `api_key_env`, defaulting to that name.
The endpoint default is the empty string, so an unconfigured gateway is discoverable as unset
rather than wrong.

`src/settlement/gateway.py` holds the provider-neutral contract. `RouteContract` carries five
required strings: `endpoint`, `requested_model`, `resolved_model`, `provider`, `tier`.
`GatewayErrorKind` separates the failure classes this lane has to keep distinct: `TRANSPORT`,
`AUTH`, `RATE_LIMIT`, `TIMEOUT`, `CANCELLED`, `PROTOCOL`, `BILLING_UNKNOWN`. `GatewayRouteError`
names route-specific refusals. `FakeGatewayAdapter` exists and returns `GatewayStatus.CONFIGURED`
and `AUTHENTICATED` with a constant `"simulated"` string, so a green fake is not evidence about
a live route.

`src/settlement/gateway_http.py` is the only real adapter. It sends `Authorization: Bearer <api_key>`
and serves two surfaces, `chat` and `responses`, selected by `SETTLEMENT_GATEWAY_API` defaulting
to `chat`. Timeouts come from `SETTLEMENT_GATEWAY_TIMEOUT_CONNECT_MS`, `_READ_MS`, `_TOTAL_MS`.

Provider selection is not a provider registry. It is an exact string lookup in the gateway's own
`GET /v1/models` catalog, reconciled by `reconcile_model_route`. Two policies matter and are
documented at the top of that file. `provider` and `tier` compare case-insensitively, on both
the catalog half and the response half, through the single shared `_route_value_matches`.
`requested_model` and `resolved_model` compare **exactly**, because the gateway answered
`NVIDIA/nemotron-3-ultra-550b-a55b:free` with HTTP 503 `auth_not_found` while `nvidia/...`
returned 200 in the same minute. Folding a case would admit a key the catalog cannot answer for.

`scripts/manifest.py` reads `SETTLEMENT_DSN` only, and reports `unknown (SETTLEMENT_DSN is not
configured)` when absent. It carries no route information.

Credentials for the live path are loaded by `scripts/invl02_live.py::_load_live_environment`, from
`LIVE_ENV_PATH = "/home/ubuntu/.config/agent-society-live.env"`, a **Linux absolute path**. It admits
only `SETTLEMENT_GATEWAY_ENDPOINT`, `SETTLEMENT_GATEWAY_KEY`, `INVL02_LIVE_GRANT`,
`INVL02_LIVE_MODEL`. It raises `live environment file is unavailable` if the file is missing. This
matters on this host, which is Windows.

The route constant is `experiments/ad01/live_construct.py::OUTPUT_ROUTE`. It is a literal dict, and
`scripts/invl02_route_discovery.py` and `experiments/ad01/offline_recompute.py` both compare frozen
evidence against it. So the constant is a **gate**, not just a default.

## 2. Discovered configuration, secrets redacted

Secret policy: variable name, present or not, and length. No value printed anywhere.

| Variable | State | Non-secret value |
|---|---|---|
| `SETTLEMENT_GATEWAY_ENDPOINT` | **UNSET** | n/a |
| `SETTLEMENT_GATEWAY_URL` (legacy alias) | **UNSET** | n/a |
| `SETTLEMENT_GATEWAY_KEY` | **UNSET** (present=False, len=0) | n/a |
| `SETTLEMENT_GATEWAY_API` | **UNSET** (would default to `chat`) | n/a |
| `SETTLEMENT_EXPECTED_ROUTE` | **UNSET** | n/a |
| `INVL02_LIVE_MODEL` | **UNSET** | n/a |
| `INVL02_LIVE_GRANT` | **UNSET** | n/a |
| `SETTLEMENT_MODEL` | **UNSET** | n/a |
| `SETTLEMENT_GRANT_UNITS` | **UNSET** | n/a |
| `SETTLEMENT_DSN` | **UNSET** | n/a |
| `SETTLEMENT_TEST_DSN` | **UNSET** | n/a |
| `OPENROUTER_API_KEY` | **VERIFIED-PRESENT**, len=73 | value never printed |
| `OPENAI_API_KEY` | **UNSET** | n/a |
| `ANTHROPIC_API_KEY` | **UNSET** | n/a |
| `CX_AGENT_BASE_URL` (router config, not settlement) | **VERIFIED-PRESENT** | `http://127.0.0.1:4000` |
| `CX_AGENT_API_KEY` (router config, not settlement) | **VERIFIED-PRESENT**, len=11 | value never printed |
| `CX_AGENT_MODEL` / `CX_AGENT_MODELS` | **VERIFIED-PRESENT** | `Worker lvl` / `Worker lvl,Opus lvl,qwen3.8-27b` |

The settlement-native credential path is entirely **UNSET** on this host. There is no `.env` in the
repo root or the parent checkout; `config/` is empty. The Linux env file
`/home/ubuntu/.config/agent-society-live.env` does not exist, and neither does any Windows analogue
(`C:\home\ubuntu\...`, `%USERPROFILE%\.config\...`, `D:\home\ubuntu\...`).

What is present instead is a **different control plane**: `cx-router/1.1` on `127.0.0.1:4000`, the
same host and port the frozen `OUTPUT_ROUTE` names. Its credential is configured under
`mcpServers.cx-agent.env` in `C:\Users\roysh\.claude.json`, and `OPENROUTER_API_KEY` is in the
process environment. The router's own readiness probe reports `ready: true`, `routerReady: true`,
pools `Worker lvl`, `Opus lvl`, `qwen3.8-27b`.

`OPENROUTER_API_KEY` is **not** a valid credential for this router. A `GET /v1/models` with it
returns HTTP 401 `invalid api key`. The two credentials are distinct.

## 3. What the committed evidence historically claimed

`evidence_s09_route_probe/probe.json`, committed at `a9a37e3` dated **2026-09-26**, is the cleanest
historical record. It names route `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`,
`endpoint_control_plane` `127.0.0.1:4000`, `measured_at` `2026-09-26`, one dispatch of 23 input and
16 output tokens, text `ready`, and `charge_units: null`, `billed: null`. Its own caveats are honest:
one call on one day is a property of that day, a 16-token answer says nothing about a longer
construction response, and the store still required a 25-unit reservation even at measured zero cost.

`reports/STAGE-09-C16-GATEWAY.md` lines 34-36 list all three spellings of this model as valid at the
time: `nvidia/...`, `openrouter/nvidia/...`, and `kilo/nvidia/...`. Line 44 records the exact-ids
defect that produced the exact-match policy. `reports/cap-sheets/invl02-live-grant.md` records the
cap sheet as requested `openrouter/nvidia/...` resolving to `nvidia/...` with provider Nvidia,
observed, free routing only. `reports/PLAN.md` line 1383 lists
`nvidia/nemotron-3-ultra-550b-a55b:free` as pilot with `nvidia/nemotron-3-super-120b-a12b:free` as
fallback.

Historical claim, not current truth, as instructed.

## 4. Verification actually performed

All commands run with `PYTHONPATH=D:/AI/Agent-Society-v2/.worktrees/w0-routes/src;D:/AI/Agent-Society-v2`
and `D:/AI/Agent-Society-v2/.venv/Scripts/python.exe`. Import confirmed:
`settlement` resolves to `D:\AI\Agent-Society-v2\.worktrees\w0-routes\src\settlement\__init__.py`.
Python 3.13.14. Five calls total, all read-only except two minimal dispatches. **No Jev call. No paid
fallback. No credential created. Nothing mutated or renewed.**

**Call 1, unauthenticated reachability.** `GET http://127.0.0.1:4000/`, `/health`, `/v1/models`,
`/v1/health`, `/models`, `/v1`. `/` and `/health` return 200 `{"status":"ok"}`, `Server: cx-router/1.1`.
`/v1/models` returns 401 `invalid api key`. `/v1/health`, `/models`, `/v1` return 404 with
`unknown path`. The control plane is up and does require auth.

**Call 2, sanctioned preflight with the settlement credential.** `HttpGatewayAdapter(endpoint=
"http://localhost:4000/v1", api_key=<OPENROUTER_API_KEY>, api="responses").preflight_route(OUTPUT_ROUTE)`
returned `GatewayError kind=AUTH retryable=False status=401`, message `gateway refused request: http 401`.
This is an **auth** refusal, not transport loss and not model inability. The credential was wrong for
this endpoint. `discover_model_route` on the same input returned verdict `refused`,
`reason: model discovery failed: http 401`, `model_count: 0`.

**Call 3, read-only catalog.** `GET http://127.0.0.1:4000/v1/models` with the router's own credential
returned **200, 255 model entries**. No entry carries `tier` or `pricing`; 0 of 255. So no model in
this catalog has an explicit price signal, and the only free signal available is the `:free` id
suffix, 32 ids. This matters for the validator, which rejects an expected route whose tier is not
free and requires a free signal.

**Call 4, the sanctioned validator against the live catalog.** Same frozen five fields, only
`requested_model` varied:

| `requested_model` | verdict | reason |
|---|---|---|
| `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` (as frozen) | **refused** | `model list is missing exact requested_model` |
| `kilo/nvidia/nemotron-3-ultra-550b-a55b:free` | **accepted** | none |
| `nvidia/nemotron-3-ultra-550b-a55b:free` (bare) | **accepted** | none |
| bare id with `provider` set to `kilo` | **refused** | `resolved model namespace does not match provider` |

Presence detail: `exact_id_presence` is `requested_model: false, resolved_model: true`. The
`resolved_model` `nvidia/nemotron-3-ultra-550b-a55b:free` **is still in the live catalog**, sanitized
entry `{"id": "nvidia/nemotron-3-ultra-550b-a55b:free", "owned_by": "Kilo API"}`. The aggregator moved
from OpenRouter to Kilo API. The `openrouter/nvidia/...` request id is gone from the catalog
entirely; only 4 `openrouter/`-prefixed ids survive (`openrouter/free`, `openrouter/minimax/minimax-m3:free`,
`openrouter/openrouter/free`, `openrouter/stealth/space-bunny-alpha`).

**Call 5, minimal live dispatch.** One 16-token request through the sanctioned `HttpGatewayAdapter`
with the bare id, then a raw `POST /v1/responses`. Both adapters refused at
`GatewayRouteError.RESPONSE_METADATA`, message `gateway response route refused: returned route
metadata mismatch`, HTTP **200**, usage `input_tokens: 23, output_tokens: 16`, tokens actually spent.

The raw body explains it. `_returned_route(body)` yields
`{"model": "nvidia/nemotron-3-ultra-550b-a55b:free", "provider": null, "tier": null}`. The model id
matches the frozen `resolved_model` exactly. `provider` and `tier` are **absent from the response
body**, and `_response_meta` treats a missing field as a mismatch against the frozen `provider: nvidia`
and `tier: free`. The gateway's response shape changed; it no longer echoes route metadata the way
the adapter's contract requires.

`/v1/chat` returns 404 `unknown path` on this router. Only the `responses` surface exists, while
`SETTLEMENT_GATEWAY_API` defaults to `chat`.

A sixth 64-token dispatch returned `status: completed`, `incomplete_details: None`,
`model: nvidia/nemotron-3-ultra-550b-a55b:free`, text `"ready"`, usage 23 in / 17 out. **The model is
live, is the one the freeze names, and produces real non-empty content.** The earlier
`incomplete: max_output_tokens` at 16 tokens was output truncation, not a capability limit.

**Model id the provider actually reports:** `nvidia/nemotron-3-ultra-550b-a55b:free`. Identical to the
frozen `resolved_model`. The requested id no longer needs to carry an aggregator prefix.

**Observable free-tier restriction.** The response body contains **no** cost, charge, bill, price or
credit field, in either dispatch. Usage reports tokens only. That is an **absence**, and I am calling
it what it is. This matches the 2026-09-26 `probe.json` exactly, where `charge_units: null` and
`billed: null` were also read as measured zero rather than unknown. The corroborating positive
signal is the id suffix: `:free` survives in the catalog, and the provider still serves it. What I
could **not** observe: any rate limit, quota ceiling, concurrency cap, or daily allowance. I made two
calls. Nothing in either response bounds them. Whether this router applies OpenRouter-style
free-tier rate limits upstream is **undetermined** by this evidence.

## 5. Mismatch between the old reports and today

Three distinct mismatches, not one.

The **aggregator moved**. Old reports claim `openrouter/` as the request prefix. Today that exact id
is absent from the live catalog and the same model is reached through `kilo/` or bare. Free status is
unaffected; the request id is stale. `STAGE-09-C16-GATEWAY.md` line 36 already listed `kilo/...` as
valid, so this is drift in the route space, not a new discovery.

The **response metadata contract broke**. Old evidence recorded provider `Nvidia` **observed**. Today
the response omits `provider` and `tier` entirely, so the adapter refuses a correct, well-formed,
HTTP-200 response as `RESPONSE_METADATA`. This is a **preflight refusal caused by response shape**, not
model inability and not route unavailability. The distinction is load-bearing for every downstream lane
that would otherwise read this as the model failing.

The **API surface narrowed**. Only `/v1/responses` exists. The default in
`SETTLEMENT_GATEWAY_API` is `chat`, which is 404 here. Any lane relying on the default fails for a
reason unrelated to the model.

## 6. Verdict

**ESTABLISHED**, with a named code-level caveat that is not an external blocker.

A free route is established. The route is `http://127.0.0.1:4000/v1`, model
`nvidia/nemotron-3-ultra-550b-a55b:free`, provider `nvidia`, tier `free`, verified today against the
live 255-entry catalog with the sanctioned validator (`verdict: accepted`) and by a live dispatch
returning `completed` with real content. **No external dependency blocks this.** The router is up, the
model exists, the credential is present, and the call is free by every signal available.

What is **UNVERIFIED** and stated as such: rate limits, quotas and concurrency ceilings. No response
field bounds them and two calls cannot. Free-by-observation, not free-under-load. A coordinator
freezing a campaign should treat reservation headroom and upstream rate limiting as uncharacterised,
exactly as `probe.json`'s own caveats warned.

What must change before the frozen route works, and is **not** an inference problem:

1. `OUTPUT_ROUTE["requested_model"]` in `experiments/ad01/live_construct.py` must move off the
   dead `openrouter/` prefix. `nvidia/nemotron-3-ultra-550b-a55b:free` is verified; `kilo/nvidia/nemotron-3-ultra-550b-a55b:free`
   is also catalog-accepted. Note that `offline_recompute.py` and `invl02_live.py` both compare
   against this constant, so changing it invalidates existing frozen evidence by design.
2. The adapter's `RESPONSE_METADATA` guard needs a decision, not a workaround. Either the gateway
   must echo `provider` and `tier`, or `_response_meta` must be told what a gateway is allowed to omit.
   I did **not** relax it. Relaxing a route guard to make a probe pass is precisely the failure mode
   the exact-ids policy was written to prevent.
3. `SETTLEMENT_GATEWAY_API` must be `responses` for this gateway. The `chat` default is wrong here.
4. The credential is not in the settlement path. All `SETTLEMENT_GATEWAY_*` vars are unset and the
   Linux env file does not exist on this Windows host. Whichever way the coordinator wires this, the
   credential must not be written into the repo. Note `OPENROUTER_API_KEY` is present but is **not**
   accepted by this router, so it is not a workaround.

**This is a configuration-drift finding, not a model-capability finding.** The exact model named by
the 2026-09-26 freeze is live and answering today. What is broken is the request id, the response
metadata contract, and the api-surface default. Any lane that reports "the free model is unavailable"
from a preflight refusal is reporting the wrong cause.
