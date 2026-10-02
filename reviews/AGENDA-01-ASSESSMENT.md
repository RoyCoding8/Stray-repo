# Agenda 01 assessment: useful construction, material contract gaps

Reviewed tip: `29496a04d5f1d7754a7ea7b623e4a1d0f1b1c25e`, compared with design `c69f8cb`. Scope: durable execution/evidence integration, continuation-policy separation, experiment interpretation and reproducibility. This is a bounded acceptance assessment, not a new whole-repository audit.

## Decision and evidence

**Do not close Agenda 01 yet.** Preserve the 128-run result as a descriptive all-tie observation. It is neither evidence that Q helps nor an adequate rejection test of evidence-qualified continuation: the treatment never changes selected work in these traces, the shared admission path applies a second qualification, and significant mechanical gates are not actually checked. No positive outcome is required from the correction.

The worker built persistent option/disposition records, a pure policy module, authored worlds, a visible command path and accounting exports. Those are useful components to retain. The following findings concern missing behavior in the selected contract, not cosmetic robustness or a demand for a new architecture.

Independently performed locally:

- Fetched and pinned the exact worker revision; inspected relevant implementation, schema, tests, manifest and reports.
- Ran `python -m pytest tests/test_ag01_policy.py -q -p no:cacheprovider`: **27 passed**.
- Ran [the assessment probe](probes/agenda01_assessment.py). The existing checker accepts all 128 committed traces / 64 pairs. Independent comparisons confirm equal full grades and resource vectors, and zero selected-action/option differences.
- Counted **zero rows in `ledger.ops` across all 128 traces**. The exporter queries the actual `operations` table; this is not a formatting omission inferred from the report alone.
- The same checker accepts an empty result directory and independently altered traces marked incomplete, carrying an invented policy version, missing evaluation reservation rows, or missing per-tick decision-operation references.
- A pure-policy probe qualifies an unrelated proposition as Q1 when only the before/after decision strings differ and the proposed probe declares no outcomes.

Probe results are preserved in [AGENDA-01-assessment.json](AGENDA-01-assessment.json). These checks require no database or inference. No local PostgreSQL service was used, and the design role has not replayed live durable trajectories or rerun the full suite. The worker reports 653 passes before the final fix, plus 18 affected-file passes afterwards; that is useful qualified evidence, not a full-suite run of the final source.

## Findings

### AGR1-01 — P1: admitted work is a parallel accounting path, not the contracted execution path

AG01-02/03/07/09; implementation contract sections 2–3. `agenda.py:435` (`select_and_admit`) reserves exposure and inserts `agenda_attempt_links`, but creates no existing investigation, attempt or operation and invokes no broker dispatch. Migration `0010_agenda01.sql:38` has free-standing attempt/operation strings rather than links to those durable entities. `runner.py:467` executes a simulated world effect by updating process-local dictionaries. All exported operation tables are empty.

The admitted revision is simply the revision read now: no expected selected revision/input identity is checked. The row stores `AG01-CMD-1` instead of the actual selecting policy and leaves its input digest empty. Existing ownership, authority and protected-scope checks do not follow automatically from `store.transact`; that wrapper does not supply them. Moreover, `propose_option` calls `_agenda_ensure_root` at line 377, creating fresh spending authority from the proposal body if the named root is absent. The root-free helper also ignores child allocation commitments.

Repair by connecting probe admissions/effects to existing attempts, preparation, broker and settlement interfaces. Keep any accounting-only decision cost explicitly distinct from a probe effect. Move grant creation to trusted experiment setup; new option IDs/roots cannot authorize themselves. Prove stale selection refusal, authority revocation, protected capacity, branch/root limits and ownership with the real integrated path. These are intended-contract requirements; the design role has not dynamically exercised these database bypasses locally.

### AGR1-02 — P1: receipt/evidence identity is asserted rather than verified

AG01-04. `agenda.py:507` (`record_outcome`) accepts an arbitrary nonempty receipt string and caller-supplied observation, stores it in `agenda_outcomes`, and can settle the reservation. It does not resolve an existing runtime receipt/evidence record or validate its bytes, source attempt, evidence invalidation or actual execution outcome. Its epoch check uses the agenda tick-derived cursor, not the evidence store's validity epoch. Existing receipt IDs return `ALREADY_APPLIED` without checking the attempted new attribution/content (`531–537`).

Link the trusted simulated adapter's actual results through the existing receipt/evidence machinery. Label them simulated. Reject fabricated, wrong-operation, changed-content and invalidated support; preserve unknown scientific conclusions independently from whether execution and billing are resolved. Reusing a receipt ID for another result must not silently report success. Prove the refusal at the public command boundary, not only in an observation parser.

### AGR1-03 — P1: the treatment leaks into both arms, and Q1 accepts changed prose

AG01-05/06; experiment sections 3–4. `runner.py:195` routes both arms through `submit_continuation`; that command applies its own Q1/Q2/Q3 logic (`agenda.py:643–684`) without receiving an R/Q policy identity. Thus R's supposedly unqualified continuation still faces an additional semantic qualification. Its logic also differs from the pure policy, creating two definitions of useful continuation. A truthy replication-slot string bypasses the substantive route test without checking a durable frozen protocol or remaining sample count.

Independently, `agenda_policy.py:218–235` accepts any current decisive in-scope citation once before/after strings differ and the caller makes two question fields equal. The probe uses a citation to `unrelated`, a residual question about `p1`, and no declared outcomes: `qualified=True`, route Q1. The runner automatically manufactures a new `decision_after` string (`runner.py:372`), compounding this weakness. This violates the explicit rejection of irrelevant true observations and renamed rationales.

Use one policy definition. Keep shared admission checks mechanical; propagate and bind the actual selected policy/input so Q alone adds the experimental condition. Define a checkable relation between an observation and a changed decision condition in the limited declared language. Do not pretend arbitrary scientific usefulness is decidable. Resolve replication against its pre-existing finite protocol. Demonstrate end-to-end R admission versus Q refusal for the same mechanically valid unqualified continuation, plus qualified admission and legitimate replication in both arms.

### AGR1-04 — P1 for the experimental conclusion: no integrated treatment exposure

AG01-10 and the scenario/control requirements. The all-tie arithmetic is correct. However, the common proposal generator excludes many potential continuations before either policy sees them: it requires decisive, ungrounded, in-scope current observations, suppresses already-bound probe/slot combinations, and usually offers very little work (`runner.py:321–373`). The reported 15–22 idle ticks in most worlds and invariant tie-order outcomes are consistent with little selection pressure. The intended Q-losing control also ties.

A unit demonstration that two helper functions can disagree does not establish that the measured integrated treatment had an opportunity to matter. Preserve this panel as an inactive-treatment result, not a general negative policy finding. After repairing AGR1-03, add separate prospective diagnostic controls where the integrated pipeline demonstrably admits more work under R, where unnecessary continuation costs resources, and where over-selective stopping loses useful information. Check competition, adverse variants and tie-order effects before freezing another scored panel. Do not tune scored worlds until Q wins. A validated treatment can still fairly tie or lose on the new panel.

### AGR1-05 — P1: checker and freeze do not establish the claimed evidence boundary

AG01-10/11. The executable probes reproduce the checker omissions listed above. `checker.py:113–160` checks only pairs it happens to find, so deleting every pair can pass. It does not enforce the manifest's complete expected trajectory set or reject duplicate identities before overwriting pair entries. `check_trace` checks presence rather than truth of `complete`, ignores the declared policy version, and does not reconcile evaluation/recovery records and decision-to-effect linkage sufficiently to reject the demonstrated alterations.

The freeze path is also advisory: `manifest.load` trusts the stored hash without recomputing it; checker CLI obtains a default hash even with a supplied alternate manifest; `run_trajectory` rebuilds worlds/manifest from current code and accepts a caller-provided hash (`runner.py:644–679`). It does not execute exclusively from a verified frozen manifest. Runtime policy/store files are not included in the explicit file digest map. Git revision can anchor them, but execution must actually check the source/configuration it claims.

Commit a replay/check entry point that validates the freeze and requires exact panel completeness by default. Make any subset diagnostic mode explicit. Independently reconcile every relevant resource class, unique effect, decision, receipt, observation, horizon cut and remaining liability. Test deletion of whole pairs, duplicates, metadata drift, changed manifest/source and altered ledgers. Report validation coverage narrowly; hashes alone do not prove scientific truth.

### AGR1-06 — P1 for durability acceptance: fresh-process reading is not trajectory continuation

AG01-09/12. `tests/test_ag01_state.py:267–293` proves a new process can read a snapshot and replay a proposal. The killed-writer test proves an uncommitted SQL insert rolls back. Neither demonstrates continued decisions/effects after a killed agenda runner. `_drive` initializes samples, outstanding launches, observations, products, refused proposals and effect fingerprints in local dictionaries (`runner.py:495–502`) and starts the loop at zero. The committed runner creates a new database instead of resuming that state.

The advertised full replay command relies on `/tmp/ag01_run128.py`, which is not committed; several fresh-process tests hardcode `/tmp/asv2-agenda01`. Equivalent test snippets do not make that command reproducible from a clean checkout.

Commit the actual full-panel driver and a genuine resume entry. Reconstruct or durably store the minimum necessary execution/simulator state, including delayed effects and simulation position, under the existing mechanisms. Kill after preparation, with a pending receipt, and around dormant wake delivery; resume from another process and compare subsequent effects and accounting with an uninterrupted control. Do not substitute a restart from an empty database. Remove checkout-specific paths from the acceptance path.

## Next step and stopping rule

Issue one [bounded worker correction](../WORKER-AGENDA-01-CORRECTION.md). The worker should independently confirm or rebut each finding with integrated evidence before repairing it. Retain the useful option/policy/apparatus pieces, preserve the original panel, and avoid a broader engineering audit.

After the six contract areas have evidence, run one properly frozen, interpretable comparison and report its outcome. Positive, negative and tie outcomes are all permissible. Fixing these gaps does not advance representations, teams or learner revision; stage 8.4 remains partially implemented until this correction is assessed.
