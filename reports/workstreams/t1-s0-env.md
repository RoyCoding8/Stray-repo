# T1 S0-env task report

Owner: implementation specialist T1. Branch: `codex/task-s0-env`.
Worktree: `/home/ubuntu/AI/Agent-Society-v2-s0-env` (only directory touched).

## Revisions

- Base: `783dc9f` (exact starting point, verified `git rev-parse HEAD` before work).
- Code tip: `366c924` (4 commits, one per vertical slice).
- Report commit: recorded below after committing this file; `git log` is authoritative.

## Modified paths

- `src/settlement/gateway_http.py` (new): `HttpGatewayAdapter(GatewayAdapter)` for a
  user-supplied generic HTTP endpoint (OpenAI-compatible chat-completions shape).
  `from_settings()` resolves endpoint + bearer key via `GatewayConfig.api_key_env`.
  `check_discovery` (configured/reachable via `GET /models`), `check_auth` (200 vs
  401/403/429 typed), `infer` (single attempt, connect/read/write httpx timeouts plus
  total attempt deadline capping the read phase and a post-response elapsed check).
  Errors: transport/auth/rate-limit/timeout/cancel/protocol with a `retryable` flag;
  retry authority stays with the caller. `Usage.provider_enforced_ceiling` is always
  `False` (EFF-8: estimates never establish a hard ceiling). `cancel()` records intent
  and returns True; `cancel_status()` reports `requested` vs `confirmed` (confirmed only
  when `infer` observed the cancellation). `CONTRACT =
  "settlement-gateway/http-chat-completions-v1"`.
- `src/settlement/exec_profile.py` (new): `probe_gvisor()` (runsc binary + docker runsc
  runtime; unavailable yields `INCOMPATIBLE_VERSION`, never a fallback);
  `dispatch("gvisor", ...)` raises `IncompatibleVersion`; `dispatch("local-process",
  ...)` runs a bounded subprocess (wall-time kill, RLIMIT_CPU/RLIMIT_AS, output cap,
  secret-scrubbed minimal env, `containment=False` on every result);
  `dispatch("simulated", ...)` returns a canned result labeled `simulated=True`.
- `src/settlement/boot.py` (new): `validate()` checks database (configured / reachable /
  authenticated / `schema_migrations` exercised), artifact roots (round-trip probe),
  sandbox profile, gateway (discovery/auth, optional live probe inference), interpreters
  (>=3.12 + spawn check). Returns `BootReport(ok, entries, available_operations,
  models_available)`; `inspect`/`mechanical-recovery`/`simulated-demonstration` survive
  gateway failure, `model-inference` and `sandbox-exec:<profile>` are added only when
  the dependency proves out.
- `scripts/manifest.py` (new): prints deterministic sorted JSON with python version,
  `uv.lock` name->version map, postgres server version, runsc/docker presence + gvisor
  reason, kernel, configured limits, gateway contract name. Never prints secrets (only
  an endpoint-configured boolean).
- `scripts/probe_sandbox.py` (new, optional): prints the gvisor probe as JSON.
- `scripts/__init__.py` (new, empty): makes `scripts` importable for tests.
- `tests/test_s0_gateway.py`, `tests/test_s0_profile.py`, `tests/test_s0_boot.py`,
  `tests/test_s0_manifest.py` (new): 36 tests at public seams against an in-process stub
  HTTP server, real Postgres, and real subprocesses; expected values are literals.
- `config/.env.example`: documentation lines only, no new variables.

## Checks

- `uv sync --extra test` then `SETTLEMENT_TEST_DSN=postgresql://ubuntu@/settlement_t0env?host=/var/run/postgresql uv run pytest -q`: **36 passed**.
- `uv run python scripts/manifest.py`: valid JSON manifest (python 3.12.3, postgres
  16.15, kernel 7.0.0-1012-aws, `runsc_present: false`).
- `uv run python scripts/probe_sandbox.py`: `available: false`, code
  `incompatible_version`, reason names missing runsc/docker.
- TDD loop followed per slice (red observed before each green: missing module, then a
  stub-server bug and a `_status` arity bug fixed during green).

## Limitations (explicit unverified gates)

- Live-gateway gate unverified: no user endpoint exists. The adapter is verified only
  against an in-process stub; `exercise_gateway=True` against a real endpoint, usage
  attribution, and billing behavior remain for the live gate.
- gVisor gate unverified on this host: no runsc/docker present. The explicit
  incompatible path is demonstrated; containment, image/tool compatibility, and
  performance measurement need the target Linux VM.
- Postgres here is 16.15 (host-provided); TECHNOLOGY-DECISIONS selects 18 for the
  isolated deployment. Manifest records the actual version; no upgrade attempted.

## Shared-contract requests (not edited)

- `GatewayConfig` has no `timeout_write_ms`; the adapter defaults write timeout to the
  connect timeout. Add the field if the coordinator wants it explicit.
- `GatewayAdapter.cancel()` returns `bool`, so confirmed-vs-requested is exposed via the
  additional `cancel_status()` method rather than the ABC signature.
- Note: `pyproject.toml` sets `asyncio_mode = "strict"` which pytest warns is unknown
  (pytest-asyncio not installed). Pre-existing, untouched (shared file).
- Note: `migrations/` and `reports/workstreams/` referenced in PLAN did not exist in
  this worktree at 783dc9f; boot treats missing `schema_migrations` as "not exercised"
  rather than an error, pending T2's store slice.
