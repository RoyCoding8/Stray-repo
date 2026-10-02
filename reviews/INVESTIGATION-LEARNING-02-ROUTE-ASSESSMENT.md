# Investigation Learning 02 route assessment

Reviewed pushed implementation tip `552a616` and its claimed preflight source commit `9e6c922`. This is a read-only source/evidence comparison; no provider request or test suite was run.

The committed `experiments/ad01/live_construct.py::OUTPUT_ROUTE` at `9e6c922` requests `openrouter/nvidia/nemotron-3-ultra-a55b:free` and resolves to `nvidia/nemotron-3-ultra-a55b:free`. The committed `reports/evidence/invl02-output-shape-final/preflight-failure.json` instead records both IDs with `ultra-550b-a55b`. `scripts/invl02_live.py::preflight_route` passes the imported `OUTPUT_ROUTE` to the gateway. The failure record therefore does not establish which route that source actually checked. It may be a record error, a different imported module, or an uncommitted source state; the committed evidence does not distinguish these explanations.

`validate_model_route` also requires **both** requested and resolved IDs to appear as separate entries in `/models`. Without the sanitized catalog identities from the request, the recorded refusal cannot distinguish a genuinely unavailable route from an alias/catalog-shape mismatch. Do not interpret the failed preflight as provider incapability or a completed P1/P2 experiment.

The worker reports 151 focused passes and 9 skips; the full suite timed out and is not green. The preflight report records zero inference calls, so no new model-acquired candidate, comparison, or E3 result is claimed.

Next, reproduce only the read-only route preflight in a fresh evidence directory. Record the loaded module path and source commit, the exact route object passed to the adapter, a digest and sanitized matching entries from `/models`, and the refusal or acceptance. Compare those bytes with the frozen protocol before any inference. Preserve the earlier failure record unchanged. If the route is genuinely absent, keep the study unavailable; if the problem is alias validation or source drift, correct its cause and freeze a new prospective study rather than reusing the failed directory.
