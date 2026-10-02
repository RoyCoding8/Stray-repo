# AG01-POLICY lane report

Owner: Nightjar. Branch `codex/ag01-policy`, worktree `/tmp/asv2-ag01-policy`.
Base `769aeef14004ad6123f6f5a142df7ce666c6bfb3` (AG01 contract baseline).
Tip `d7e4967` (pushed to `origin/codex/ag01-policy`; this report's tip-SHA
line added as a follow-up commit).
Lane brief: AG01-05 through AG01-08; no external skill installed.

## Owned paths (only files touched)

- `src/settlement/agenda_policy.py` (new)
- `tests/test_ag01_policy.py` (new; distinct from the pre-existing
  S1 `tests/test_agenda_policy.py`, which is untouched)
- `reports/workstreams/ag01-policy.md` (this file)

## What was built

Pure-function policy module, no DB, no IO, no model calls. Imports only
`settlement.agenda` (`seed_order`, `SEED_CLASSES`) and `settlement.common`
(`payload_digest`, `SettlementError`).

- Versions: grammar `AG01-OBS-1`, R `AG01-R-1`, Q `AG01-Q-1` (see CR-01).
- `parse_observations(raw, current_epoch)` validates `prop scope dep
  dep_version value source_attempt receipt epoch`; normalizes
  `True/False/"true"/"false"/"unknown"` to canonical strings; preserves
  `unknown`, conflicting pairs (reported in `conflicts`, never merged) and
  the `simulated` label; rejects malformed shapes and future-epoch items
  with per-index reasons instead of raising.
- `rotation_order(candidates, cursor)` adapts option dicts to
  `agenda.seed_order` stubs and maps the result back to the full dicts;
  cursor advancement is owned by `seed_order`. `advance_cursor` is the pure
  arithmetic for non-rotation steps.
- `eligible(option, state)` derives eligibility from disposition,
  prerequisites, root cap, remaining authority, pending-effect identities,
  current negative history and expiry, returning reasons in all cases.
  Stale negatives (dependency moved on) are reported as invalidated and do
  not block.
- `qualify_continuation(continuation, observations, state)` implements
  exactly Q1/Q2/Q3 and returns the winning route plus reasons, or every
  route's failure reason.
- `decide_R` / `decide_Q` share one code path over identical input shapes
  (`candidates observations state cursor`); the single
  `qualified_only` flag is the only treatment difference. Output records
  policy version, `select|idle`, selection summary, `input_digest` over the
  canonical snapshot via `common.payload_digest`, next cursor, per-candidate
  evaluation and parse counts. Deterministic: no clock, no randomness.
- `match_wake(condition, event)` is total over the three typed predicates
  `prerequisite-version`, `evidence-change`, `authorized-scan-due`;
  malformed shapes and unknown types return `matched: False` with a reason.

## Published Q rules with worked examples

State carries `dep_versions` (current dependency versions). An observation
is *current* when its `dep_version` equals the map entry; otherwise stale.

**Q1 decision-change.** A cited observation with the same
`prop/scope/dep/dep_version` as a parsed observation is current, decisive
(`true`/`false`), in the continuation scope, `decision_before` and
`decision_after` are non-empty and differ, and
`next_probe.question == residual_question`.
Worked: cited `{p-weak,s1,dep-a@3}=true`, before `hold`, after `go`,
probe asks the residual question -> qualified Q1. Negative variant: cited
`{p1,s1,dep-a@3}=false`, before `pursue`, after `abandon-scope` ->
qualified Q1 (abandoning on evidence counts as useful).

**Q2 discriminating-probe.** At least two probe outcomes remain live
(contradicted = a current decisive observation on the probe question pins a
different value) with different declared consequences, and no current
decisive observation already matches the probe question.
Worked: probe `{true->go, false->stop}`, no current evidence on `p1` ->
qualified Q2 with no citation at all. Settled variant: current
`{p1,s1,dep-a@3}=true` present -> `q2:settled-by-current-evidence`,
unqualified.

**Q3 frozen-replication-remainder.** `replication` declares `protocol`,
`total > 0`, `completed`, `declared_before_first_sample: True`,
`stop_reached: False`, and `0 <= completed < total`.
Worked: protocol `rep-p`, 1-of-4 done, prefrozen, no stop -> qualified Q3.
Exhausted (4-of-4), stopped, or undeclared variants -> unqualified.

**Must NOT qualify (all tested):** paraphrase (same decision, no citation,
single-consequence probe), dangling new-ID citation, irrelevant-true
observation (out-of-scope citation, non-discriminating probe), bare time
passage (later epoch, no new evidence), renamed alternatives (decisions
textually equal), stale negative (citation at `dep@2` while current is
`dep@3`, non-discriminating probe).

## Checks with results

- `uv sync --extra test` then
  `uv run --extra test pytest tests/test_ag01_policy.py -q`: **27 passed**.
- Covers: 3 version asserts; parse accept/reject/conflict/unknown/simulated;
  all 7 contract section-4 fixtures (irrelevant, settled, weak-signal,
  in-scope negative, stale negative, remaining/exhausted replication);
  5 non-qualification cases; changed-dependency invalidation in both
  `eligible` and Q1; determinism (repeat-call equality); R/Q divergence with
  shared `input_digest`; Q-selectivity-loses case (R selects on `unknown`,
  Q idles, later decisive evidence would have qualified the dropped
  continuation); import gate (`sys.modules` scoped to `settlement.*` plus
  source grep for `grader`/`latent`: 0 hits); rotation agreement with
  `agenda.seed_order` over cursors 0-3; digest stability and sensitivity;
  typed wake match/mismatch matrix; cursor wrap.
- Regression: `tests/test_agenda_policy.py` still **2 passed, 5 skipped**
  (DB-gated skips, no `SETTLEMENT_TEST_DSN` in this environment);
  full-suite `--collect-only`: **617 tests**, no import breakage.
- Not run: any PostgreSQL-backed check (no test in this lane needs a DB;
  durable seams belong to AG01-STATE/AG01-EXP).

## Limitations (honest negatives)

- Q selectivity demonstrably loses: `test_q_selectivity_loses_a_real_finding`
  shows Q idling on an `unknown` observation where R's continuation would
  have produced the decisive evidence. Selectivity is a cost, not a free win.
- Fixtures are authored and embody author assumptions per contract section 4;
  they prove the rules are implemented, not that the rules are wise.
- Citation matching is exact structured keys; semantic equivalence is never
  guessed from prose, so reworded-but-equivalent evidence will not qualify.
- Rotation agreement is proven against in-memory `seed_order` only; durable
  cursor/ordering behavior awaits the STATE integration.
- `simulated` observations are preserved as public input and can support
  qualification; the module cannot verify their provenance beyond the label.

## Change requests for the coordinator

- **CR-01 (version spelling):** this module publishes `AG01-OBS-1`,
  `AG01-R-1`, `AG01-Q-1` per the lane brief; `reports/DECISIONS.md`
  AG01-D04/D05 use the slash form (`AG01-OBS/1`, `AG01-R/1`, `AG01-Q/1`).
  Request a ruling on the canonical spelling before EXP freezes the
  manifest; the rename is one constant edit either way.
- No other contract change needed. No edits outside owned paths; no merges;
  no other branch touched.
