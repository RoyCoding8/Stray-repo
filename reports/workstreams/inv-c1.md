# INV-C1 lane note: M1 integrated lifecycle + M4 executable interfaces

Branch `wt/inv-c1-lifecycle`, base `692af23`. Owned paths only:
`experiments/ad01/{trajectory,construct,learner,packet,method_exec,worlds}.py`,
`experiments/ad01/agenda_policy.py` (new), `tests/test_invc1_*.py` (new),
this note. Untouched: `src/**`, `scripts/**`, `experiments/doubles.py`,
`experiments/ad01/cli.py`, `experiments/ad01/records.py`, other tests.

## M1: one public lifecycle

`experiments/ad01/agenda_policy.py` holds the versioned policy selection
(`ad01-policy-baseline-v1` fixed scaffolding proposer,
`ad01-policy-model-v1` model policy) plus `select_tasks` for experiment
entry task/treatment selection. `DecisionConsumer` is the one gate every
boundary decision passes: propose, admit, bounded correction of the same
decision, then continuation or stopping. Domain differences stay in
adapters (`controls`, `seeds`, `checkers`) and policy selection.

`trajectory._run_boundary` always delegates to the consumer. A passed
`consumer` is used directly; otherwise a default consumer adapts the
legacy `propose` callback (or scaffolding when absent). Raw callbacks are
proposers only: admission still runs inside the consumer, so no direct
callback can close the gate. Replacing the consumer (refusing) or
disconnecting it changes both domain runs.

Correction: a refused proposal journals a structured failure
(`target`, `reason`, `attempt` as `kind: correction` observations under
the boundary attempt) and re-proposes with the failure in the next actual
request (`seen["prior_failure"]`; model path renders
`PRIOR FAILURE (correct it)` into the next prompt under a fresh
`-c<n>` learner operation id so corrections never reuse the refused
settled text). Same target is pinned for content refusals; targeting
refusals (curriculum/world/protected) release the pin because the target
itself was the fault, while admission still gates the retry. Budget is
2 corrections; journaled rows make the remainder survive restart, and a
resumed exhausted boundary refuses without calling the proposer.

`study_root` threads from `run_campaign`/`resume_campaign` through
`ensure_campaign` and construction into member lineage. `ensure_campaign`
attempts C2 `src/settlement/authority.py` bind when present; the module
is absent, so the campaign allocation carries study authority and the
integration point is recorded in `ensure_campaign`'s return payload.

Construction no longer mints fresh authority: `_construction_allocation`
subdivides the episode child from the campaign (study-root) allocation
and raises `ConstructionFailed` naming the missing study authority when
the parent cannot cover. Measured: a construction call needs ~3000 units
of exposure, so studies must fund construction from the root.

Historical entries: `run_c3_qualification.py` stays untouched and keeps
working (all new parameters are optional; legacy `propose` callbacks are
adapted, not removed). `cli.py` is C3-owned and unmodified; the CLI path
is exercised as-is below.

## M4: executable interfaces

`method_exec.entry_contract` now declares `result_envelope` separately
from the outer model JSON response (`entry` plus `notes`) and the
candidate object. `packet.construction_packet` carries the envelope from
the same contract and the renderer prints its rule verbatim, so renderer,
parser and executor agree. The child driver reports a direct-candidate
return as structured `malformed-result-envelope` instead of a `KeyError`.

Proof uses independently written methods (original linear scans, no
reducers, no authored wrapper) through the actual child process: software
14 ops to 3 and graph 12 to 10, both preserved; malformed envelope;
query exhaustion (3 over-budget queries return unknown, host counts 2);
diagnostics plus repair reason reaching the repair prompt.

## Gates (real Postgres `inv_c1_lifecycle`/`inv_c1_envelope`, doubles at provider seam only)

- `pytest tests/test_invc1_lifecycle.py tests/test_invc1_method_envelope.py`: 16 passed.
- Nearby, no shared databases touched: `test_inv_b4_trajectory` 4 passed,
  `test_inv_g3_obs` 1 passed, `test_inv_b1_contracts` pure-contract 3 passed.
- `test_inv_b1_contracts` brokered 4 fail identically on base: database
  `inv_b1_contracts` does not exist here (environmental, pre-existing).
- Real CLI: `run` covers software plus graph boundaries; swapped
  off-curriculum recordings refuse both boundaries through shared admission.
- System-chosen content: consumer-decided task ids, journaled correction
  chains, retained independent-sweep bytes with digests. Authored fixtures:
  scripted provider texts and the two independent methods above, labeled
  as such; no live inference anywhere.

## Known fallout (legitimate contract change, needs coordinator/C2 routing)

`test_aled_campaign.py` (untouchable here) runs `constructor="model"`
with `agenda_authorized=1000`. Construction exposure (~3000/call) never
fit that root; those runs only passed by minting fresh per-episode
authority, which M1 removes. Measured on scratch `inv_c1_lifecycle`:
that shape now ends rejected with
`construction needs 16384 study authority from parent ... has 1000 free`
and zero model calls. Affected: `test_episode_identity_and_bytes`,
`test_failed_construction_calls_are_counted`,
`test_campaign_constructs_and_retains_acquired`,
`test_construction_failure_rejects_episode`,
`test_resume_restores_budgets_and_bytes_without_new_calls`,
`test_resume_without_plan_continues_full_schedule`,
`test_resume_after_final_construction_call_restores_member`,
`test_construction_call_cap_spans_boundaries`,
`test_lineage_limit_survives_resume`. Reconciliation (root authority
levels for legacy caps) belongs with C2/M2; behavior preserved for
adequately funded studies (100000, as in qualification).

## Remaining gaps

- C2 owns M2/M3 completion: bind/admit against `src/settlement/authority.py`
  once it exists, plus interrupted-phase recovery beyond correction rows.
- C3 owns trace/export/replay and the runnable study entry.
- No live qualification attempted; no grant in environment.
