# INV-C prep: independent qualification design

Scope: lane C prep. Base `5f75ef6`. Branch `wt/inv-c-qualify`. Worktree `.worktrees/inv-c`.
Owned paths: `reports/workstreams/inv-c.md` plus scratch files under `reports/workstreams/`.
No changes to `src/**`, `experiments/**`, `tests/**`, `scripts/**`, `reports/PLAN.md`, `evidence*/**`.
Requires: B1 merged packet shape (`experiments/ad01/packet.py`), B2 phase 1 loop seam (`reports/workstreams/inv-b2.md`).
Build phase starts the moment B2 phase 2 merges. This note is design only. No implementation code lands here.
Principles applied: foundational-thinking (data shapes first, sections 1, 2, 5), test-behavior-not-implementation (gate asserts observable behavior with literal values, section 7).

## 1. Public entry the doubles will drive

The entry is `experiments/ad01/trajectory.py::run_campaign` with `propose=learner.propose_from_model(...)` and `constructor="model"`, on an explicit disposable DSN with an explicit gateway adapter and model label.

Concrete call shape:

```
tasks = [rotation.r_schedule(world)[i]["task_id"] for i in range(3)]
seed = trajectory.ensure_campaign(dsn, cid, world, arm, dict(CHARTER), dict(CAPS, agenda_authorized=N), tasks=tasks)
propose = learner.propose_from_model(dsn, cid=cid, gateway=gateway, model="inv-c-double",
    charter=dict(CHARTER), world=world, arm=arm, allocation_id=seed["allocation_id"])
campaign = trajectory.run_campaign(world, arm, dict(CHARTER), dict(CAPS, agenda_authorized=N),
    tasks=tasks, propose=propose, campaign_seq=0, dsn=dsn,
    gateway=gateway, model="inv-c-double", constructor="model")
```

After B2 phase 2 merges, each boundary inside `run_campaign` routes through the B2 shared loop:

```
run_boundary(packet, propose, adapters) -> (ExperienceTransition, LoopState)
```

`run_campaign` keeps its frozen signature as the compatibility entry. The loop owns materialize, admit, execute, incorporate, continue. If B2 names the module or fields differently, only the materialize step adapts. Packet field names come from merged `packet.decision_packet` and `packet.construction_packet`.

This is the same entry live inference uses. Live swaps only the gateway adapter instance from the recording double to the live adapter. Everything else is identical. Operation identities, broker paths, receipt reads, validation, retention, and use stay fixed.

Operation identity vocabulary the gate asserts:

- Learner: `ad01-<cid>-learner-<seq>` via `learner.model_propose` plus `broker.ensure_operation` plus `broker.dispatch_operation`.
- Construction: `ad01-<episode>-construct-l<lineage>-<init|repair>` via `construct._call`, where episode is `<campaign_id>-b<seq>-<task_id>`.
- Validation sandbox: `<construct-op-id with -construct-l replaced by -validate-l>` via `method_exec.run_member_out_of_process`.
- Use: `ad01-<campaign_id>-use-<task_id>` via `trajectory.run_use`.

Charter and caps for the gate:

- `CHARTER = {"objective": "smaller valid explanatory examples", "freeze_id": "ad01"}`.
- `CAPS = {"max_boundaries": 6, "diagnostic_queries": 96, "model_calls": 60, "construction_tokens": 2048}`.
- World 0 R schedule tasks: `ad01-w0-dev-sw-00`, `ad01-w0-dev-gr-00`, `ad01-w0-dev-sw-01`.

Qualification item 1 requires the learner to be called with costs included and forbids a direct proposal callback substitute. This entry satisfies it because every learner call travels through broker admission with settled receipts and measured `Usage`.

## 2. Recording-double design

The double implements `settlement.gateway.GatewayAdapter` at the `infer` seam only. It demultiplexes by operation id. Learner operations draw from the learner script stream. Construction operations draw from the family stream matching the task in the operation id. Repair attempts draw from the repair stream.

Each script holds exact response text bytes plus a `Usage` triple. The gateway records request operation id plus prompt bytes plus response bytes plus usage in order. The settled receipt text must equal the recorded script bytes before any validation runs.

Response bytes are followed independently into validation, retention, and fresh-process use:

- Validation reads the settled bytes through `packet.parse_construction_response` plus `method_exec.verify_member` plus `construct._evaluate`, and learner bytes through `learner.validate_proposal` plus `trajectory.admit_investigation`.
- Retention reads the same bytes through `trajectory.dev_episode` plus `trajectory.freeze_repertoire`, with `source_digest = sha256(method_source)` checked on `load_repertoire`.
- Fresh-process use reads the frozen repertoire file in a subprocess (`python3 -m experiments.ad01.cli use`) and executes the same bytes through `method_exec.run_member_out_of_process`. The use record field `executed_source` must equal the retained `method_source`.

Digest chain asserted by the gate: script bytes equal settled receipt text equal retained `method_source` equal use `executed_source`. Every response carries `simulated: True` metadata. Nothing doubled is reported as live. `trajectory.cost_union` counts doubled `model_calls` from operation identities but treats simulated usage as non-billable.

## 3. Acquired-program sketch beyond a greedy or ddmin wrapper

Current C3 fixtures `ACQUIRED_SW` and `ACQUIRED_GR` are single-line passthroughs to `reducers.reduce_software` and `reducers.reduce_graph` with fixed `method="greedy"`. The qualification needs a substantive acquired method, not another wrapper with a different method string.

Target entry: `acquired_order(task, oracle, max_queries=16)` satisfying `method_exec.entry_contract`. Params are exactly `task`, `oracle`, optional `max_queries`. No imports. No dunder access. No calls to the forbidden set. Exactly one module-level function carries the entry name.

Behavior sketch:

- Phase one is diagnostic aware. It reads the witness pointer from the task plus the prior diagnostic observation in the construction packet. For software it attempts surgical drops of non-chain ops first. For graph it trials atoms in degree order first. Each trial goes through `oracle.query` and records verdict plus queries used.
- Phase two falls back to greedy reduction with reversed priority over the remaining atoms. It keeps the smallest candidate whose verdict report is `preserved`.
- It stops at `max_queries` and returns the envelope `{"candidate": candidate, "queries": oracle.queries_used}`.

This earns its place because it branches on diagnostic content, issues a different query ledger order than fixed greedy, and can reach a smaller preserved candidate on at least one probe task while staying valid on both families. The gate asserts behavioral difference, never source text similarity. Assertion targets: `verify_member` passes, `run_member_out_of_process` plus `trajectory._check` report `preserved` on both `ad01-w0-dev-sw-00` and `ad01-w0-dev-gr-00`, final measure is strictly below incumbent measure, and the oracle query ledger order differs from the fixed-greedy ledger on the same task.

No canned source is committed as evidence of acquisition. The sketch above is a target. The gate passes only on measured behavior of bytes that traveled through construction receipts.

## 4. Diagnostic-sensitive decision cases

Rejected proposal then valid correction. The first learner script returns invented `basis_references`. `admit_investigation` refuses with reason `invented basis references`. The boundary records a `no-candidate` episode with that reason. The second script for the same seq returns an evidence-grounded development proposal for the same task. The campaign proceeds to diagnostics plus construction. The gate asserts two learner operations with success receipts, first episode `fallback_reason` containing `invented basis references`, second episode disposition `retained` or `rejected` with a construction reason.

No-candidate incumbent use. A zero `max_queries` script or a `LearnerRefused` path yields disposition `no-candidate` with fallback `incumbent`. `run_use` with an empty repertoire selects `controls.incumbent`. `checker.verify_use_records` accepts the record. The gate asserts `requested == selected == executed == incumbent`, verdict `preserved`, `normalized_reduction == 0.0`, `witness_queries == 0`, and empty `problems`.

Two domains. World 0 R schedule visits software then graph then software. The software construction packet requires candidate keys `family`, `task_id`, `ops`, `witness`. The graph packet requires `family`, `task_id`, `vertices`, `edges`. Diagnostics differ: software runs `diagnostic_resolves`, graph runs `novel_order_unproductive`. Public operations expose `reduce_software`, `reduce_graph`, and `oracle.query`. The gate runs one boundary per family and asserts per-family `candidate_shape.required_keys`, `preservation_objective.reason_codes`, rendered prompt contents, and `check_software` versus `check_graph` verdict paths.

Kill and resume. Kill point one is after diagnostic completion with the boundary seq settled via `_publish_boundary` and no construction op yet. Kill point two is after candidate validation with the construct op settled and a retained episode. A fresh process calls `trajectory.resume_campaign` with the same cid plus DSN. It reuses settled receipt text with zero new gateway `infer` calls. It restores the same observations, policy versions, envelope remaining, and pending action identities. An empty repertoire still executes the declared incumbent-use phase through `run_use`. The gate asserts gateway call counts unchanged across resume, `_read_campaign` settled rows identical, `cost_union` totals identical, and use records present for the empty-repertoire arm.

## 5. Single resource envelope asserted across stages plus repair plus databases

After B2 phase 2 merges, one `ResourceEnvelope` object admits every effect against one study root. `store.reserve` and `store.settle` stay the durable mechanism. Trajectory `remaining` dicts are reads, not authority.

Shapes (from inv-b2 section 3):

```
Allowance: allowance_id, kind, amount, spent_measured, spent_unknown
ResourceEnvelope: study_root, authorized, allowances, ceilings
ProposedAction: target, instrument, inputs, dependencies, requested, hypothesis
ExperienceTransition: packet_id, packet_digest, proposal, admission, operations, results, costs_measured, costs_unknown, continuation
LoopState: objective, opportunities, observations, questions, repertoire, actions, policy_versions, envelope
```

Sequence per boundary. Admit a diagnostic allowance from remaining. Read post-effect spend from receipts plus measured counters. Admit the construction allowance from remaining minus measured diagnostic spend. Admit the repair allowance from the same remainder. Admit validation sandbox exec and use under the same root. Failed validations still settle spend. Unknown exposure stays visible as reserved or refused. Caller-supplied totals never advance an allowance.

IR-03 regression target. Graph task `ad01-w0-dev-gr-00` with remaining queries 6 and diagnostic spend 4 grants construction at most 1. Boundary total never exceeds 6. The gate captures `envelope.remaining("queries")` before and after each effect and asserts `construction_granted <= 6 - 4 - repair_reserved`.

Cross-database rule. Changing a database, task tag, or policy version cannot renew authority. The same study root plus the same campaign id reuses settled operation ids with `ALREADY_APPLIED` and reuses receipts. `cost_union` totals derive from operation identities plus measured counters only. The gate runs the same campaign id against a second disposable database with copied operation ids, asserts no new authorization, and asserts acquisition plus use plus total dicts equal the first run.

Assertion targets: `ResourceEnvelope.remaining` before and after diagnostic, construction init, repair, validation, and use. `broker.ensure_operation` result codes. `operations` table rows by operation id prefix. `receipts` usage rows. `cost_union` acquisition, use, and total dicts.

## 6. Replay-boundary check list

Replay reads recorded `ExperienceTransition` rows. Each row carries packet id, packet digest, exact proposal, admission or refusal with reason, operation identities, receipt identities plus outcomes including unknown, measured costs plus unknown costs, and continuation with pending action identities.

Supported replay requires an exact prefix match on all of the following. A matching task id alone is insufficient.

- Dependencies plus action arguments.
- Artifact, model, and environment versions.
- Relevant prior observations.
- Packet digest plus freeze digest.

Checks:

- Hidden-future refusal. Replay at prefix N cannot read observations from prefix N plus 1. A probe feeding a later diagnostic into an earlier decision must stop as unsupported.
- Artifact and version mismatch. A changed freeze manifest, `packet_version`, model id, protocol version, or execution profile stops the branch as unsupported.
- Unsupported alternative decisions. Reordered dependent actions, new code bytes, or changed available context stops the branch as unsupported.
- No borrowing. A stopped branch never borrows an unrelated outcome, never charges it as live, and never scores unknown as failure or zero. `checker` unknown markers stay unevaluable.

Each replay verdict is one of `supported`, `unsupported`, or `refused` with a reason string. This slice proves replay boundaries only. No predictive worlds. No replay-optimization campaign.

## 7. Failing-first gate and green criteria

Gate file: `tests/test_inv_c_qualification.py`. Disposable database `inv_c_qual`. Recording doubles only at the gateway seam. Live calibration under Qualification item 6 stays separately authorized and out of this gate.

Order: write the gate red on the B2-merged base, then build the loop, envelope, double, and acquired program to green. The gate covers Qualification items 1 through 5 behavior.

Tests and exact green criteria:

- `test_entry_drives_learner_and_construction_through_broker`. Three-boundary world 0 I campaign through `run_campaign` plus `propose_from_model` plus `constructor="model"`. Green when learner operation count equals 3, every learner and construction operation has a success receipt, `entry["model_calls"]` equals learner count plus construction count, and at least one episode is `retained`.
- `test_rejected_then_corrected_proposal`. Scripted invented-basis first proposal plus valid correction at the same seq. Green when first episode is `no-candidate` with `fallback_reason` containing `invented basis references`, second episode proceeds to `retained` or `rejected` with a construction reason, and both learner operations carry success receipts.
- `test_no_candidate_incumbent_use`. Zero-budget boundary plus empty-repertoire `run_use`. Green when the episode is `no-candidate` with fallback `incumbent`, the use record shows `requested == selected == executed == incumbent`, verdict `preserved`, `normalized_reduction == 0.0`, and `checker.verify_use_records` returns empty `problems`.
- `test_two_domain_packets`. One software boundary on `ad01-w0-dev-sw-00` plus one graph boundary on `ad01-w0-dev-gr-00`. Green when each rendered prompt contains its family candidate keys, reducer name, and reason codes, and each evaluated candidate reports `preserved` through its own checker path.
- `test_kill_resume_reuses_settled_results`. Kill after diagnostic plus kill after validation, each followed by `resume_campaign` in a fresh process handle. Green when gateway `infer` call counts are identical before and after each resume, `_read_campaign` settled rows are identical, `cost_union` totals are identical, and the empty-repertoire arm still produces use records.
- `test_envelope_sequences_diagnostic_construction_repair`. Graph boundary with remaining 6 and scripted diagnostic spend 4. Green when construction granted is at most 1, repair draws from the same remainder, boundary total spend is at most 6, and every allowance advance cites a receipt identity plus a measured counter.
- `test_cross_database_no_renewal`. Same campaign id replayed against a second disposable database. Green when the second run reuses settled operation ids with `ALREADY_APPLIED`, authorized totals do not increase, and `cost_union` acquisition plus use plus total dicts equal the first run exactly.
- `test_replay_boundary_refusals`. Four replay probes: hidden future, artifact mismatch, reordered dependents, new code bytes. Green when each probe verdict is `unsupported` or `refused` with a reason string, no probe borrows another outcome, and unknown costs stay marked unknown rather than zero.

Full green means all eight tests pass on `inv_c_qual` plus the B1 contract file still passes unmodified. The gate report lists per-test operation counts, receipt counts, episode dispositions, digest equalities, remaining-authority before and after each effect, and replay verdicts with reasons.

## 8. Build-phase entry

On B2 phase 2 merge, rebase this branch, read the merged loop module name plus envelope API, adapt only the materialize step to merged packet field names, then implement the double, the acquired program target, and the gate in that order. Drop the `inv_c_qual` database on completion. Report verification boundaries exactly. Doubled runs never validate live inference or containment.

## 9. Build record (merged tip `b671d58`, gate green 2026-09-20)

Entry reconciliation: the loop entry did not move under B2. `trajectory.run_campaign`
plus `learner.propose_from_model` plus `constructor="model"` is still the entry live
inference uses. `settlement/loop.py::run_boundary` exists as a separate module and
`trajectory` was deliberately not migrated (inv-b2 section 7). The gate drives the
real current entry throughout. No wrapper preserves the old design. The loop module
is exercised directly only where it owns behavior: envelope admission, measured
costs, journaled transitions, replay probes.

Reconciliations against the prep design, each recorded not wrapped:

- Correction lands on the next boundary, not the same seq. A learner operation id
  is `ad01-<cid>-learner-<seq>`, so a second proposal at the same seq reuses the
  settled first script by design. The gate scripts invented basis at seq 0
  (`no-candidate`, reason `invented basis references`) and the valid correction at
  seq 1 (proceeds to construction). Same invariant, real mechanism.
- Campaign order is arm I with tasks `[sw-00, sw-01, gr-00]`, the R first-three set
  reordered. A graph diagnostic consumes `remaining - 1` witness queries, so a
  mid-campaign graph development would starve later construction under the
  trajectory budgeting B2 left unmigrated (visible instance of the IR-03 double
  promise, out of scope here). Graph development goes last, where its gorge is
  harmless because the construction allowance was admitted beforehand.
- Cross-store dedup is impossible by design: durable operations live per store.
  The gate asserts the real invariant instead. Same store: re-`ensure_operation`
  on a settled learner op returns `ALREADY_APPLIED`, and `resume_campaign` with a
  fresh double makes zero gateway calls with identical settled rows and totals.
  Second store: the same campaign id re-executes fully (equal call counts), takes
  an equal-sized grant, and reproduces `cost_union` acquisition, use and total
  dicts exactly.
- Kill granularity is the settled boundary, the resume unit of the public entry.
  There is no mid-boundary kill point: diagnostics run synchronously inside
  `_run_boundary`. Kill one settles a diagnostic-only boundary (no construction
  op). Kill two settles a retained development boundary. Each resumes in a fresh
  process through `cli resume` with zero new operations or receipts.
- The CLI resume path caps `diagnostic_queries` at 16, so the kill-two campaign
  is `[sw-00 diagnostic, sw-02 development]` (settled spends 1 and 6). The main
  three-boundary campaign stays `[sw-00 diagnostic, sw-01 development, gr-00
  development]` with spends well inside the harness caps.
- The acquired entry keeps the fixed `method_exec` signature, so packet
  diagnostics reach it through family-stream selection plus the task-embedded
  witness pointer, not as a parameter. The method branches on family, on the
  witness pointer and chain derived from task content, and on observed oracle
  verdict reports (initial verdict gates the search, bulk-trial verdict picks
  the phase-two path). Per-family packet diagnostics are asserted at the packet
  level in `test_two_domain_packets`.
- Ledger difference is proved by outcome divergence, never source text. Same
  task, same budget 4, both `preserved`: fixed greedy ends at 11 ops, the
  acquired method at 3. Fixed greedy removes at most one atom per accepted
  trial, so 14 to 3 in 4 queries requires multi-atom trials greedy never
  issues. The ledgers necessarily differ.
- Coord02: gated what exists (every test designates its database disposable
  through `coord02.experience`). `trajectory` carries no coord02 port, so no
  coord02 experience assertions exist to gate. That is the marked remainder.

Acquired program (`ACQUIRED_ORDER_SOURCE` in `experiments/doubles.py`): one
module-level `acquired_order(task, oracle, max_queries=16)`, no imports, no
dunder, no forbidden calls. Software phase one drops all non-chain non-witness
atoms in a single surgical trial, phase two polishes greedily witness-last.
Graph trials vertices first in ascending degree, then edges. Measured through
`run_member_out_of_process`: 14 to 3 in 5 queries on sw-00, 10 to 3 in 5 on
sw-02, valid reductions on all six world-0 dev tasks at budget 16.

Gate evidence (disposable `inv_c_qual`, `inv_c_qual2`, since dropped):
`tests/test_inv_c_qualification.py` 9 passed. Main campaign: 3 learner
operations with success receipts, 2 construction inits plus 2 validation
sandbox ops, `model_calls` 5, episodes `inspected/retained/retained`,
`sha256(script) == sha256(settled) == sha256(retained method_source) ==
sha256(fresh-process executed_source)` per family, simulated non-billable
(`cost_union` total tokens `None`). Kill/resume: operation and receipt counts
identical across both fresh-process resumes, settled rows identical,
`cost_union` totals identical. Envelope: diagnostic/construction/repair all
admitted against one study root, consumed equals the three exposures,
`sequence_construction_allowance(6, 4) == 1` with `1 + 4 + 1 == 6`, every
advance citing receipt identities plus measured counters. Replay: six probes,
one `supported` with verbatim results and unknown costs preserved, four
`unsupported` (hidden-future, version-mismatch, reordered-dependents,
new-code-bytes) with empty results, one `refused` malformed, plus a stale
packet-version refusal from the real materializer. Regressions unmodified:
`tests/test_inv_b1_contracts.py` plus `tests/test_inv_b2_loop.py`, 19 passed.

Verification boundary: every doubled run proves doubled behavior only. No
double carries live metadata, no canned source stands as acquisition evidence,
no fixture execution is relabeled. Live inference and containment remain
unvalidated by this gate.
