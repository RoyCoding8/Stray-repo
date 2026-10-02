Authorization and cap sheet, verbatim from the assignment.
"The human explicitly authorized free-model live spending on 2026-09-21. This section is the written grant for one new study after C1-C3 pass, not a request to ask again for the same permission. Use the worker's configured free model and gateway. Resolve the exact model ID and effort level from that working configuration and freeze them before the first call. If several free models are available, choose a capable one with functioning structured/source output. Paid fallback, changing provider/model mid-study or increasing these ceilings is not authorized."
Ceilings: study model calls 100 including discovery inference/smoke, empties, errors and repairs; development 4 episodes 2 per domain; policy construction 4 calls total, 1 initial plus 1 repair per P1/P2; assessment 12 episodes and 24 scheduled sealed method-use slots; episode model calls and STEP decisions 6 each cumulative.
"Use one new root s09-completion-live-01. If that identity already exists, inspect its grants, operations, receipts and exported evidence and resume it; do not mint a replacement to reset exposure. Persist the resolved model, effort, protocol, root, this authorization reference and cap sheet in the durable grant before effects. Keep the endpoint and key in local configuration, outside committed evidence. Do not reuse a historical spent grant."
"Do not manufacture success using a recording adapter in live mode."

Measured preflight facts. Every item below was observed, not assumed.
1. No study gateway was preconfigured anywhere. SETTLEMENT_GATEWAY_ENDPOINT, SETTLEMENT_GATEWAY_URL, SETTLEMENT_GATEWAY_KEY, SETTLEMENT_GATEWAY_API and SETTLEMENT_DSN are all unset in the Windows user environment, the Windows machine environment, and the WSL login environment. There is no .env file in the repository root. Neither /home/ubuntu/.bashrc nor /home/ubuntu/.profile contains any line matching SETTLEMENT, GATEWAY or API_KEY.
2. The only gateway credential present on the machine is VERCEL_API_KEY in the Windows user environment. It is the same key the Jev evaluator uses. AI_GATEWAY_API_KEY and OPENAI_API_KEY are unset.
3. A read-only GET to https://ai-gateway.vercel.sh/v1/models with that key returned 386 models, of which 78 have pricing.input == 0 and pricing.output == 0. Of those 78, by declared type: 35 video, 26 image, 10 language, 3 reranking, 3 realtime, 1 transcription. So only 10 zero-cost models can emit text at all.
4. The 10 zero-cost language model ids are inclusionai/ling-3.0-flash-fin, -fin-free, -sante, -sante-free, -vl, -vl-free, perplexity/sonar, perplexity/sonar-pro, perplexity/sonar-reasoning-pro, poolside/laguna-s-2.1-free.
5. Two candidates were smoke tested with one real chat completion each, asking for Python source with no prose. poolside/laguna-s-2.1-free returned HTTP 503 service_unavailable_error and is unusable. inclusionai/ling-3.0-flash-vl-free returned HTTP 200 and emitted valid Python whose first line is "def STEP(view, state):", 183 characters, and a regex for "def STEP(" matched.
6. The successful call's own usage block reported cost 0, market_cost 0, upstream_inference_prompt_cost 0, upstream_inference_completions_cost 0, is_byok false, prompt_tokens 85, completion_tokens 177. So zero cost is a measured billed figure from the response, not only a price listed in the catalogue.
7. Two model calls have therefore been spent on discovery, one failing and one succeeding. The cap sheet counts both. 98 of the 100 authorized calls remain.
8. No prior study state exists to resume. The reachable PostgreSQL databases are s09_local_c3_diag and s09_local_control, both created by a previous worker and not by me, and neither contains a s09-completion-live-01 root. No grant has been spent under that root.

Configuration proposed to be frozen in the durable grant before the first study effect.
endpoint: https://ai-gateway.vercel.sh/v1
api shape: chat, via POST /v1/chat/completions, which is the shape that returned HTTP 200 in the smoke test
model: inclusionai/ling-3.0-flash-vl-free
reasoning effort: the model exposed no effort parameter in the smoke test, so effort is recorded as "unset-by-provider" rather than invented
key: read at run time from the VERCEL_API_KEY environment variable, never written to any file, evidence bundle, report, prompt or commit
study root: s09-completion-live-01, newly minted because no such root exists
adapter: settlement.gateway_http.HttpGatewayAdapter.from_settings, the same real adapter the controlled HTTP test exercises
paid fallback: none permitted; the study aborts rather than substituting another model or provider
aggregate ceiling: 100 study model calls, 2 already spent on discovery, enforced in the real dispatch path
abort condition: if any response reports a nonzero cost, the study stops immediately rather than continuing