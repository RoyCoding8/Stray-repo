# T6 S1 operator interface + stewardship + agenda — task report

- Base: `16ce0ad` (branch `codex/task-s1-operator` start, per assignment).
- Tip: this commit (see `git log` on the branch).
- Worktree: `/home/ubuntu/AI/Agent-Society-v2-s1-operator` only. No other checkout touched.

## Modified paths (owned only)

- `migrations/0004_leases.sql` (new; leases only) — `worker_leases` table.
- `src/settlement/steward.py` (new) — IF-1 wrappers, allocation amend, leases, deadlines, quarantine delegation.
- `src/settlement/agenda.py` (new) — AGENDA-1..5 policy over durable records, no new tables.
- `src/settlement/api.py` (new) — FastAPI operator console (UI-1..5, BOOT-4 narrowing).
- `templates/` (new, 9 files) — server-rendered views, Jinja2 autoescape on.
- `static/htmx.min.js` (vendored) + `static/operator.css` (new, plain ops styling).
- `tests/test_steward_leases.py`, `tests/test_agenda_policy.py`, `tests/test_ui_views.py`,
  `tests/test_ui_commands.py` (new).
- This report.

No shared contracts touched. `pyproject.toml`/`uv.lock` untouched (no new dependencies;
form bodies are parsed with stdlib `urllib.parse` because `python-multipart` is not
installed and the manifest is outside owned paths).

## Outcomes

- `uv run pytest`: **171 passed** against real PostgreSQL
  (`SETTLEMENT_TEST_DSN=postgresql://ubuntu@/settlement_t1operator?host=/var/run/postgresql`),
  plus `tests/test_broker_dbos.py` **3 passed** under its own
  `settlement_t1broker` DSN (that file derives its DBOS system DSN from the DSN name and
  errors on any other name — pre-existing, unrelated to this change).
- One full run showed a single unidentified failure that never reappeared in two subsequent
  full runs; the failing name was cut from the captured output, so this is reported as an
  unreproduced flake, not a verified pass.
- Live smoke on dev port 8101 (started, checked, stopped; no running server committed):
  unauthenticated `/` → 401; tokened `/` → 200 with the models-unavailable banner;
  `/static/htmx.min.js` → 200 (50917 bytes); `/trials` → pending state.
- Requirement map: stewardship IF-1 (admit/amend/withdraw, subdivide, reserve/settle/release
  delegate to the store envelope; `amend_allocation` enforces consumed+reserved and child-sum
  ceilings plus parent cover for growth); T2-R04 (issue/expire/revoke/reacquire leases in
  `store.transact`; expiry bumps `ownership_generation` so stale dispatch/fulfill are refused
  as `stale_revision` while `submit_observation` stays open; deadlines swept via
  `due_attempts`/`expire_attempt`); AGENDA-1 (obligations/development/supervision allocations,
  task admission refused on supervision scope, recovery kind exempt); AGENDA-2 (four-class
  round-robin with finite caps, stable id order); AGENDA-3 (frontier fields validated,
  renewal must name what changed); AGENDA-4 (event/completed-op/deadline/message wakeups;
  `repair_scan` calls `broker.heartbeat(..., repair_due=True)` with `gateway=None`);
  AGENDA-5 (single-worker default, benefit-stating teams, commit-before-reveal);
  UI-1/BOOT-4 (overview from durable rows, gateway-absent banner, repair stays enabled);
  UI-2 (escaped server-rendered SVG diagram, branches, operations, evidence, versions, wait
  reasons); UI-3 (pending learning state; gains/alternatives/hypotheses kept distinct);
  UI-4 (versioned idempotent commands, accepted/refused/outcome-unknown display, cancel shows
  external-unknown); UI-5 (127.0.0.1 bind, `OPERATOR_TOKEN` auth, inert escaped rendering,
  no shell endpoint, GETs verified mutation-free, `/static` exempt from auth).

## htmx vendoring evidence

Sandbox network was available: `htmx.min.js` 2.0.4 downloaded from
`https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js` (contains `version:"2.0.4"`),
vendored to `static/htmx.min.js`, served locally with
`integrity="sha384-HGfztofotfshcF7+8n44JQL2oJmowVChPTg48S+jvZoztPfvwD79OC/LTtG6dMp+"`.
No CDN dependency at view time; the UI works fully offline against the local server.
Styling follows the coordinator constraint: plain system font stack, tables for tabular
state, labeled green/amber/red/gray status, no decorative gradients or glass effects.

## T5 integration points the coordinator must wire (both pending, recorded as dependencies)

1. Quarantine/release control: `steward.quarantine_subject` / `steward.release_subject`
   duck-type import `settlement.capabilities` and call `quarantine(dsn, cmd)` /
   `release(dsn, cmd)`, expecting a `CommandResult` back. `ImportError`/`AttributeError`
   or `UndefinedTable` from the absent migration becomes a journaled
   `unavailable_dependency` refusal. No quarantine tables were created here.
2. Trial/release views: `api.t5_state` probes `information_schema` for `trials`,
   `trial_assignments`, `trial_results`, `candidates`, `releases`, `quarantine`,
   `capability_versions`, `capability_releases`. With none present the capability/trial/
   learning views render an honest "learning slice pending" state and never crash.
   If T5 names differ, update `api.T5_PROBES`.

## Limitations

- Generation enforcement rides the store's in-transaction ownership checks; steward's
  `dispatch_guarded`/`fulfill_investigation` are the named T2-R04 seams delegating to them.
- `owner_scope` is immutable after seeding, so the supervision-capacity guard is a
  read-then-transact check; no function mutates scopes.
- Agenda ordering cursors and team commitments are in-memory caller-held values, not
  durable rows (migrations were restricted to leases); durable inputs are re-derived
  from events/attempts/operations on each call.
- No live gateway or runsc host was exercised here; model ops stay deferred and the
  gVisor path is T3's explicit `IncompatibleVersion`.
