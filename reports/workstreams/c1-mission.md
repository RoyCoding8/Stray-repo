# C1 — one durable mission entry

Lane C1 of the milestone-C build. Offline, no live model calls, no network.
Gate: `tests/test_mission_entry.py`, 4 passed.

## What was wrong

No mission concept existed in `src/settlement` (zero occurrences). Three
aggregates each held a *part* of a mission, and a fourth held a file-based
copy:

- `s09_policy_state` — the accepted decisions, keyed `(investigation_id, seq)`
- `FrontierStore.pending_effects` — the unresolved work, in a JSON file
- `context.resume_package` (`src/settlement/context.py:155`) — the continuation
- `frontier._blank_doc` — a Boolean-only, digest-guarded mission projection in
  the frontier JSON

Each is keyed for a different question, so "what is this investigation for"
meant reading three places, and file-based state is a named recurring failure
for this program.

## The schema I extended, and why not a new table

`migrations/0019_mission_entry.sql` **extends `investigations`** (created in
`0001_schema.sql`), which already owns an investigation's identity and
objective. Six columns added: `frontier`, `permitted_experience`,
`active_program`, `acquired_artifacts`, `retained_use`, `improvement_mode`.

Not a new table beside `s09_policy_state`, for the reason the assignment gives
and which the schema makes concrete: `s09_policy_state` is keyed
`(investigation_id, seq)`. A mission placed there is reachable only at some
seq, which is a *second* owner answering "what is this investigation trying to
do", with a seq it does not have a meaning for. That is the duplicate
authority being removed, not created. `investigations` is already one row per
investigation, so all six are readable with no join.

`improvement_mode` is CHECK-constrained to `('operate', 'improve')` because it
decides which executor holds authority; an unrecognised value must be a
refusal rather than a typo that leaves a mission silently inert. The other
five stay opaque JSONB: they are the study's own descriptions, and a schema
here would make every new study a migration.

`mission.py` records a mission as a **partial** update. A mission is built over
its life (charter frozen, then experience/program/retained-use written as
acquired), so naming one of the six must not blank the other five. `scope` and
`obligations` merge rather than replace because they are shared with the
steward and hold keys this module does not own.

## What I deleted

`frontier._blank_doc` no longer writes a second mission authority:

- `mission_projection` — the `canonical()` digest of the mission, deleted
- `_validate_document`'s `mission_projection changed` refusal, deleted
- the document's `mission` now holds exactly `{objective, environments}`,
  which is what a STEP view names and what a reopened store is recognised by

I did **not** delete the `_blank_doc` function itself: it is how a store's
environments, grant and counters start, and none of those are the mission.
Deleting it would have meant deleting unrelated behaviour.

Callers migrated: `create_store` (`frontier.py:2154`) now takes the durable
entry's declaration; `live_construct.ensure_live_store` and
`improve_channel._improve_probe_opportunity` (`improve_channel.py:1113`) read
through the document unchanged and both are exercised by the gate.

## The trajectory.py sites A4 must wire

I did not edit `experiments/ad01/trajectory.py` (verified clean:
`git diff --stat HEAD -- experiments/ad01/trajectory.py` is empty). It is the
designated mission owner (ARCHITECTURE-SYNTHESIS §13:249-253) and lane A4 owns
the file. The mission exists without it. A4 must wire these:

1. `trajectory.ensure_campaign` (`:187`) — after `admit_commitment` succeeds,
   call `mission.record_mission` with the charter and the six. This is the
   natural seam: the investigation row is created there, so the mission is one
   row and one write.
2. `trajectory.accept_action` (`:328`) — record `active_program` from the
   accepted decision.
3. `trajectory.execute_pending` (`:344`) — append to `permitted_experience` and
   `acquired_artifacts` on incorporation.
4. `trajectory._s09_ensure_incorporated` (`:289`) / `_s09_mark_incorporated`
   (`:318`) — the two points where a boundary's effect is resolved; a decision
   whose effect was never executed must be visible as such on the entry.
5. `trajectory.resume_campaign` (`:1723`) — read the entry rather than
   re-arming from the campaign alone.

## s09_arm_parity field reconciliation

The comment at `s09_arm_parity.py:39-46` claims `_run_arm` "demands exactly
eight public-state fields and the SWE world publishes twelve of its own", and
that the SWE arm is "refused by the harness view normaliser". **That comment is
stale.** The per-world declaration landed later (`VIEW_CONTRACT_FIELDS`,
`:329-340`): the SWE world declares all twelve itself, and
`admit_world_view` returns `None` for a real SWE view. `contract_view`
projects it to the six contract fields and `admit_shared_view` admits that.
Measured, not assumed:

- `swe.public_view(...)` publishes 12 fields
- `ap.admit_world_view(pv)` → `None` (admitted)
- `ap.contract_view(pv)` → the exact six
- `ap.admit_shared_view(cv)` → `None`
- `tests/test_view_contract_swe.py` — 9 passed (pines `hypothesis_class`
  derived from `structure` + `editable_lines`, and the union-view refusal)

So SWE is no longer "registered for addressability only". The 8-vs-12 tension
is real but it is **not** a refusal; it is a per-world declaration where the
count is deliberately not the contract.

**Which fields were surplus, and why.** The contract's six consume 8 of the
SWE world's 12. The seven the contract never reads are:

- `max_budget` — **verbatim duplicate** of `action_schema.budget` (measured
  equal). Pure surplus; a second spelling of a value already present.
- `source`, `structure`, `entry`, `public_tests`, `symptom` — the task program,
  its shape, the tests, and the symptom. The contract reads these only
  *derived*: `observed` ← `symptom.observed`, `hypothesis_class` ←
  `{structure, editable_lines: len(source)}`. The raw fields exist so the SWE
  world's **own** drivers (`s09_swe_policy.py`, `s09_swe_experiment.py`) can
  work; `last_effect` is read by `s09_swe_experiment.py:1174,1229` and
  `s09_swe_policy.py:744`.
- `last_effect` — the previous action's result. Read by the SWE policy
  drivers, not by the contract.

So none of the seven is deletable without deleting the SWE world, and none is a
leak: the deliberately-removed projections named in the comment at `:360-365`
(`s09_swe_ast.swe_view`, `s09_e1_fork_probe.honest_projection`) are already
gone, which is why `VIEW_CONTRACT_READS`/`DERIVED` exist. I changed no
`arm_parity` behaviour; `s09_arm_parity.py` is **lane L3's** file and I did not
touch it. The correct fix is the comment, which is lane L3's to make.

## Verification

Exact command and summary line:

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims; \
  export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/c1.jsonl; \
  cd /mnt/d/AI/Agent-Society-v2/.worktrees/c1-mission && \
  PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/c1-mission/src \
  timeout 1200 /home/ubuntu/.venvs/as9/bin/python -m pytest \
  tests/test_mission_entry.py -q -p no:cacheprovider'

....                                                                     [100%]
4 passed in 15.04s
```

Also run, to bound blast radius. Every failure below is **identical at
baseline** — measured by stashing my four files and re-running:

- `test_m2_frontier_inherit.py`, `test_frontier_harden.py`,
  `test_frontier_atomicity.py` — 15 failed, 32 passed, both before and after.
  Cause: `method_exec.py:1413` "refused: execution needs explicit authority
  and identity". Pre-existing, not mine.
- `test_evidence_integrity.py`, `test_s09rev_acquisition.py`,
  `test_s09rev_boundary.py`, `test_s09_e4_channel.py` — 11 failed, 51 passed,
  both before and after. Same authority blocker.
- `test_s09m1_state.py`, `test_s09_durable_state.py` — 13 passed. This one
  matters: it pins `s09_policy_state`'s column list exactly, so it confirms my
  migration did not add a column there.
- `test_view_contract_swe.py` — 9 passed.

`git diff --name-only f03db5b HEAD -- reports/evidence/` is **not** empty: it
lists `reports/evidence/invr1b8-panel-census/census.json`. That file came from
commit `005a4f7` ("B8: census which panel..."), which predates this worktree's
fork at `450a988`. `git diff --name-only HEAD -- reports/evidence/` is empty,
so I edited nothing under `reports/evidence/`.

## Files

- `migrations/0019_mission_entry.sql` (new — 0019 verified unused by listing
  the directory; 0018 was taken by `receipt_provenance`)
- `experiments/ad01/mission.py` (new)
- `experiments/ad01/frontier.py` (modified — `_blank_doc`, `_validate_document`,
  `create_store`)
- `tests/test_mission_entry.py` (new, mine alone)

Trained TDD: the test was written and watched fail on a missing module, then
two real defects surfaced behind it — a partial mission update blanking the
objective, and a zero-resource opportunity refused by `frontier._resource_delta`.