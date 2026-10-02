# EC02/AD01 delivery assessment at 84d2094

Reviewed 2026-09-19 in an isolated checkout of `84d20948ddbef8efea38a5728edd3fddc6b3a936`. This is a source/evidence review with offline checks, not a rerun of the worker's PostgreSQL or live campaigns.

## Decision

Accept substantial implementation progress and preserve the unsuccessful live attempts. Do not accept unconditional C1–C5 closure, the claim that C4 completed its comparison, or the attribution of failure primarily to model capability. End repeated retries of this historical campaign. Carry the material obligations into [Investigation 01](../docs/design/INVESTIGATION-01.md), following the [accepted architectural direction](../docs/design/ARCHITECTURAL-DIRECTION-2026-09-17.md). This changes future work, not the original experiment's verdict.

The current implementations now connect child identities, store-derived costs, learner inference, construction, process-separated method execution and fresh-process use more substantially than bdf12d5. Fifteen selected local tests passed. The committed C3 use corpus independently checks: 72 records, zero reported problems or unevaluable records. These are useful gains. Neither result proves the complete learning path or containment.

## Material findings

### IR-01: construction lacks the information needed to interpret the result

`experiments/ad01/construct.py:50` supplies a family name, entry signature, brief API names and selected observation labels. It omits the task's concrete structure, candidate/return schema, oracle verdict schema, reducer signatures and observation `detail`. The method executor at `method_exec.py:106` requires a mapping containing `candidate`; that contract is absent from the prompt. `_entry_name` also selects the first defined function, another relevant interface condition.

At `trajectory.py:295` a diagnostic runs, but line 331 passes the earlier `seen` packet to construction. The just-produced observation is not included. The offline probe shows that changing task contract content and prior diagnostic detail leaves the construction prompt identical; a boundary capture receives only the seed observation after a distinguishing diagnostic has executed.

This is a causal information gap, not evidence that a larger model is required. Repair it through one model-visible executable contract and faithful result delivery, not more prohibitions appended to prompts. Do not infer that this explains every failed live call: raw failed construction responses were not exported here for independent attribution.

### IR-02: C3 qualifies construction/use more than the claimed learner path

`run_c3_qualification.py:90` passes `_recording_learner(...)` directly as `propose`; it bypasses the broker/model learner path. I and R receive different preselected task lists, and I has an extra task-specific zero-query budget. `ACQUIRED_SW` and `ACQUIRED_GR` are authored wrappers around existing greedy reducers. Recording them as test vectors is legitimate, but this battery does not demonstrate the full common learner path or outside-menu search behavior.

Its public fresh-process use and checked 72 records remain accepted at that scope. Next qualification must substitute only at actual provider seams, charge learner calls, give I/R equivalent initial opportunities/resources apart from the declared curriculum treatment, and include a behavior-changing program beyond seed selection. Other isolated tests do not make this particular integrated corpus prove what it bypasses.

### IR-03: a boundary can allocate already-consumed query allowance again

`trajectory.py:284` sets construction queries before running the diagnostic. Lines 295–297 then spend diagnostic queries; line 333 forwards the earlier allowance. In the isolated boundary probe, an initial allowance of 16 and a diagnostic using 10 leave 5 after the boundary charge, yet construction receives 15. The probe captures allowance propagation and stops before executing candidate/model work; it does not claim a measured live overspend.

The architecture needs one authoritative remaining allowance at every admitted effect, including failure and restart. Repeating arithmetic in stage-specific loops has not held that invariant.

### IR-04: C4's claimed completion and live attribution exceed the archive

The checkout contains **11 JSON/log pairs**, not twelve: nine readable traces and two zero-byte JSON stubs. All readable traces are world 0, with one I and eight R records including a resume. Six readable traces have unknown aggregate tokens. None retained a method; none contains a use phase. These are diagnostic attempts, not the assigned three paired worlds and 72 protected-use records.

AD01 section 7 explicitly permits no-candidate trajectories and requires incumbent use. `trajectory.run_use` supports that behavior; the reviewer reproduced incumbent fallback from an empty repertoire without a DB. Therefore zero retention is not itself a reason that AD01 use is blocked. EC02's no-learned-arm rule does not apply to AD01.

`trace-w0-R-live11.log` records an assertion in `controls.diagnostic_resolves` on a mismatched family, not evidence of an external infrastructure outage. That older defect may now be repaired; preserve the original classification as an implementation failure. Live14/15 record no settled responses and unknown usage. Without transport/provider evidence they cannot be independently classified as provider-side empty-response flakes.

The report describes fresh databases for retries, while JSON records reuse campaign/operation names and omit a per-attempt DB/export identity, effective configuration and source revision. Construction also seeds separate allocations in `construct._construction_allocation`. A 260000-unit agenda declaration alone does not establish an aggregate cross-database grant or whole-campaign reconciliation. This review cannot determine a breach or total external spend; export attributable operations and distinguish known consumption, reservations and unknown exposure before any new live campaign.

### IR-05: EC02's retained negative needs accurate lineage evidence

The init export records lineage 1 stopping with `acquisition probe only`; lineage 2 fails with `plan carries only action+shape+children`. The report says both stopped without proposing a plan. The committed repair script gives both lineages the first failure description. Thus it did not deliver lineage 2's actual schema failure as its specific repair feedback.

The final export reports four construction calls and no selection. Preserve that no-selection observation; do not imply a learned-policy comparison occurred. The committed exports contain accounting summaries, not the raw four construction responses and their complete receipt/input linkage. Full receipt reconciliation remains worker-reported. Further old-study calls are not requested.

## Verification and disposition

- Independent: `15 passed in 1.17s` across target admission, experience controls and three DB-free learner tests. Exact command below.
- Independent: `reviews/probes/closure_84d2094.py` checks the prompt/boundary defects, archive inventory, 72 C3 use records and empty-repertoire fallback. Output is committed alongside it. Boundary doubles are explicitly labeled; no DB/provider/candidate process calls occur.
- Source comparison: changes after worker-tested `ccbe25f` consist of reports, evidence and the C2 repair driver. The worker's 1329-pass/1-xfail suite is reported, not independently rerun. The final evidence driver is outside that earlier gate.
- Not verified here: remote databases, retained 16-receipt anchor, actual grants, provider billing, live containment or the provenance of unexported model responses.

```
python -m pytest tests/test_bdr03_target_admission.py tests/test_alea_experience.py tests/test_alee_learner.py::test_r_first_boundary_packet_matches_admission tests/test_alee_learner.py::test_diagnostic_detail_changes_packet tests/test_alee_learner.py::test_invalid_action_refuses_before_dependent_work -q -p no:cacheprovider
python reviews/probes/closure_84d2094.py
```

C1: substantial integrated implementation, with material information/resource gaps. C2: reported no acquisition after four calls, no benefit comparison; provenance and repair-feedback qualifications above. C3: construction/use controls accepted, full common-learner qualification incomplete. C4: diagnostic live attempts, comparison incomplete. C5: delivery exists but unconditional closure is unsupported. Archive these dispositions and move to the new architectural batch; do not spend another campaign chasing a positive result or restart a whole-repository audit.
