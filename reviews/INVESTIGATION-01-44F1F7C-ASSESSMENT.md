# Investigation 01 review at 44f1f7c

Reviewed implementation: `44f1f7c7d6340890f9028de8ef4f3f61e344e4c1`, fetched and checked against the handoff at `123c211`. Review date: 2026-09-20. This review changes no production code and makes no study model calls or database changes.

**Disposition: partial implementation, completion required before live qualification.** Missing live authorization is real, but it is not the only remaining prerequisite. Keep the working broker, contracts and diagnostic fixes. Finish the connected investigation path already specified, without another whole-repository audit or new architecture project. The continuation is [the completion assignment](../docs/HISTORY.md#worker-investigation-01-completion).

## Accepted progress and limits

Construction prompts now include concrete tasks, candidate shapes, helper signatures and oracle meaning. The current diagnostic reaches construction. Query sequencing subtracts diagnostic spend before granting construction queries. Model-backed proposals and construction are exercised through brokered gateway doubles in the new tests. Historical reports now distinguish missing evidence and incomplete comparisons. These are useful improvements.

The worker reports 46 lane checks passing. Its delivery report records a broader run of 727 passed, 591 skipped and 16 provisioning errors subsequently rerun, not a clean complete PostgreSQL suite on the final tip. This review does not dispute the lane runs or independently reproduce them.

The delivery's “system-chosen” packet shapes, envelope sequencing and sweep design are implementation-worker engineering decisions. Scripted methods prove acquisition plumbing only. Attribute runtime choices to traced policy outputs, engineering choices to their implementer, and fixture content to its author. No live acquisition, learning benefit or transfer is established here.

## Material findings

### INV-R1: the proposed shared cognitive path is not the public path, P1

`src/settlement/loop.py:401` defines `run_boundary`, but all eight direct calls are in tests. AD01 still runs `trajectory.run_campaign -> trajectory._run_boundary`; coordination retains its own controller. Sharing `broker.sweep` consolidates effect recovery, not the learner/action/result lifecycle. Production uses a sequencing helper from the new module, which does not connect that module's journal, correction and resume semantics. The replay helper in `experiments/doubles.py:333` is likewise exercised only by tests; public campaigns do not emit its transition format.

Software and graph already share AD01's older trajectory. The required fix is not to call a particular function name or force coordination into a graph task. Choose one actual public lifecycle, implement the specified semantics there, and remove unused alternative orchestration. Domain adapters and experimental policy selection can differ. Public CLI runs, transition exports and offline replay must follow the same implementation.

### INV-R2: construction still creates independent authority, P1

`experiments/ad01/construct.py:31` seeds a fresh allocation from a per-call estimate and a four-call ceiling. `construct_method` calls it at line 192 using the episode identity. There is no parent study allocation in that command. The review spy observed two separate 16,384-unit seed requests for the same episode on two database identifiers. This is a command-boundary observation, not a real database overspend demonstration.

The committed database-backed `test_cross_database_no_renewal` at `tests/test_inv_c_qualification.py:450` explicitly runs the campaign again in DSN2, expects the same new authorization and repeats the gateway calls. That checks reproducibility, not conservation of one study's authority. `ResourceEnvelope.bind` is not connected to the public campaign either. New database or campaign names must not authorize fresh study work. Use a designated authoritative store and refuse an unbound database, or an equally explicit existing authority mechanism; a distributed ledger is unnecessary.

### INV-R3: correction and interrupted-phase recovery are not qualified, P1

The public boundary catches learner refusal or admission failure, returns a no-candidate episode, and advances the outer task loop. The review invoked the public campaign with a diagnostic callback: rejection at boundary 0 advanced to boundary 1, and the unique refusal reason was absent from the next decision packet. The episode retained the failure, so this is missing corrective feedback, not missing reporting. The worker's “rejected then corrected” test switches from a software task to a graph task; it does not correct the rejected decision.

`test_kill_resume_reuses_settled_results:313` completes `_run` before starting a resume subprocess. It proves fresh-process reuse of completed boundaries, not interruption after a diagnostic or candidate validation. In the production path, the accepted decision is persisted before `run_diagnostic`, but the diagnostic observation is not checkpointed before construction. Resuming an accepted pending decision calls the diagnostic again. The test does not expose that window. Preserve actual intermediate results, bounded correction state and pending actions. Interrupt the real process at both required phase boundaries and resume with unchanged identities and budget.

### INV-R4: the generated method's return contract is still implicit, P2

The prompt declares task/candidate shapes and helper return values, but `method_exec.entry_contract` does not declare the generated method's own return envelope. The actual child driver indexes `out['candidate']`. Two trusted fixture programs both pass `verify_member`: returning the candidate task directly fails in the real driver with `KeyError: 'candidate'`; returning `{'candidate': task}` succeeds. This does not show that every live model will fail. It shows a remaining undocumented interface that can consume acquisition attempts without testing learning.

Specify the method result separately from the outer model JSON response and the candidate object. Render it from the executor-owned contract and check an independently written example through the actual child process. Complete semantic agreement, including failures and query accounting, matters more than matching keywords in the prompt.

### INV-R5: the proposed live caps and exports are not executable bounds, P1

Lane D is explicitly reports-only. Its absolute 1.475M “token” ceiling assumes each request is at most 4097 estimated units from 8192 characters and 2048 output tokens. The renderer does not enforce that character bound. A 12,000-character observation produced a 15,981-character prompt and an estimated broker exposure of 6044 in the review probe. Character division is also an estimate, not measured input-token authority. The 192-query total extrapolates expected use queries; it is not a derived worst-case or a shown study-wide admission limit. The wall ceiling counts model deadlines alone. No public six-trajectory runner enforcing the aggregate cap sheet was delivered.

Produce a runnable study entry with one concrete, enforced manifest covering calibration, comparison, protected use, retries and exports. Derive ceilings from actual request and operation bounds, distinguish estimates from measured/unknown usage, and enforce an overall deadline. The requested raw-response/receipt/configuration exports must be generated by that entry. Do not ask the human to approve this report's estimates as if they were implemented guarantees.

## Independent verification

- [Review probe](probes/investigation_01_delivery.py), [observed results](evidence/investigation-01-review/observed.json): static caller scan, allocation-command spy, public callback diagnostic, real trusted-fixture child driver, and prompt/exposure measurement. No database or model effects. Callback/spies establish the named failure boundaries only; they are not substitutes for integrated qualification.
- Focused pytest run: 12 passed and one environment failure in 5.63 seconds. Passed: all four `test_inv_b4_trajectory` tests, `test_inv_g3_obs`, three parser/contract tests each from B1 and B3, and `test_c3_ir_lists_share_tasks_selection_differs`. `test_two_domain_packets` failed during setup because its Linux PostgreSQL socket was unavailable on Windows. No test logic failed after successful database setup, and no full-suite pass is claimed.
- Jev evaluated evidence-to-claim judgments and prioritization twice. [Initial input](evidence/investigation-01-review/jev-input.json), [response](evidence/investigation-01-review/jev-output.json), [corrected follow-up input](evidence/investigation-01-review/jev-followup-input.json), [response](evidence/investigation-01-review/jev-followup-output.json). The first input incorrectly described the 8192-character assumption as truncation; the follow-up explicitly corrects that reviewer mistake using the probe. Jev judged integration incomplete and recommended finishing the actual path before live work. It received reviewer-selected evidence, not independent repository access; probabilities are not acceptance proofs.

## Review task list and next decision

- [x] Inspect delivered path, tests, reports and live request.
- [x] Reproduce consequential discrepancies and acknowledge accepted progress.
- [x] Challenge interpretation with Jev and correct its input when evidence changed.
- [ ] Worker completes the integrated lifecycle, authority, recovery, contracts and study entry.
- [ ] Run bounded live qualification under a valid grant, or report the exact remaining external dependency after all technical preparation is complete.

Remain in stage 8. The general product direction is unchanged: persistent investigations, executable capability acquisition and reuse across task types. This is completion of the chosen architecture, not another expansion of scope or a demand for a positive result.
