# M5 cap sheet Investigation Learning 02

Status: blocked. No surviving grant verified in this worker environment. Do not launch.

Observed authority:
VERCEL_API_KEY present. AI_GATEWAY_API_KEY absent. S09_M5_LIVE_GRANT absent. S09_STUDY_CALLS_ALREADY_SPENT absent. Historical 19 of 100 worker-reported in reports/STAGE-09-COMPLETION.md. Historical count is not remaining balance proof.

Required grant to unblock:
Explicit human grant naming model scope, call ceiling, study root, and spend tracking vars. Example vars to set: S09_M5_LIVE_GRANT, S09_STUDY_CALLS_ALREADY_SPENT, SETTLEMENT_DSN.

Exact runnable next step when grant exists:
S09_M5_LIVE_GRANT=<grant-id> S09_STUDY_CALLS_ALREADY_SPENT=<n> uv run python scripts/s09_pilot.py --config FROZEN-LIVE-CONFIG.md --study-root s09o_live_02 --cap 100 --endpoint https://ai-gateway.vercel.sh/v1 --model inclusionai/ling-3.0-flash-vl-free --no-paid-fallback
Then: uv run python scripts/s09_verify.py --study-root s09o_live_02

Routing constraints:
Configured endpoint and model only. No silent paid fallback. Discovery and price metadata are not billing proof. Preserve failed attempts and uncertainty. Empty responses trigger frozen repair or stop, not endless retries or unreported switch.

Stop rule:
E0 preflight first with independently authored apparatus control. Proceed to E1 E2 only if preflight permits. E3 only with eligible revised improver from identical start. Otherwise record unavailable.
