# Investigation 01 semantic causality review

Verdict. Accept with findings.

Scope. Investigation 01 batch at tip 5ff0f1e. Method. Derive expectations from docs/design/INVESTIGATION-01.md first, then trace bytes through code. Principle applied. principle-prove-it-works. It changed the work from reading lane notes to running the paths in disposable databases. No lane note is cited as evidence below. Every numbered claim carries its own run output or file lines.

## Expectations

The design asks for one loop with these properties. The contract renderer, parser and executor agree on entry selection, arguments, output shape and profile limits. Prompt rendering derives from the same contract. A malformed action is an attributed result with bounded correction, not silent advance. Retention and rejection both continue durably across restart. The public entry is qualified with doubles only at provider seams. The learner is called and its costs are included. No direct proposal callback substitutes for integrated qualification. The acquired program is substantive. Replay refuses hidden future, version mismatch and new code bytes. Live comparison is a separate authorization.

## Valid output trace

I traced test_entry_drives_learner_and_construction_through_broker in tests/test_inv_c_qualification.py:106. I ran it with my own disposable database inv_rsem_trace. The campaign returned dispositions inspected, retained, retained with model calls 5 and construction calls 2.

Byte path, each hop confirmed by equality check in my run.

- Double emits bytes. experiments/doubles.py:281 in InvCQualificationDouble.infer records response text per operation id. The stream choice lives at experiments/doubles.py:268. Construction default bytes come from experiments/doubles.py:201.
- Learner travels through the broker. experiments/ad01/learner.py:155 ensures the model inference operation. experiments/ad01/learner.py:167 dispatches it through the gateway. experiments/ad01/learner.py:169 reads the settled receipt text. My run showed 3 learner operations. Each receipt text equaled gateway.records text. Each receipt carried simulated true and billed false.
- Construction travels through the broker. experiments/ad01/construct.py:84 ensures the operation. experiments/ad01/construct.py:97 dispatches it. experiments/ad01/construct.py:58 reads the settled text. experiments/ad01/construct.py:80 reuses settled bytes on resume. My run showed 2 construct init operations. Each receipt text equaled the double response with sha prefix 99819c48c39c.
- Validation parses and executes the settled bytes. experiments/ad01/construct.py:145 evaluates the text through experiments/ad01/packet.py:221. experiments/ad01/construct.py:106 gates the source through method_exec.verify_member and executes it out of process through method_exec.run_member_out_of_process. The check runs through trajectory._check at experiments/ad01/trajectory.py:56. My retained episodes verified preserved with reductions 16 to 3 and 12 to 10.
- Retention keeps the exact bytes. experiments/ad01/trajectory.py:585 writes members to repertoire.json. experiments/ad01/trajectory.py:599 reloads the file and rejects digest mismatch. My run showed digest ok for both members with entry acquired_order and authored false.
- Fresh process use executes the frozen bytes. experiments/ad01/cli.py:use loads the repertoire and calls trajectory.run_use. experiments/ad01/trajectory.py:649 selects the member by family and executes it out of process. My subprocess run returned 2 records. Each executed_source equaled the retained method_source. Each digest matched. Each verdict read preserved.

Resume durability held in the same run. I called trajectory.resume_campaign with a fresh double. Fresh calls equaled empty list. Operation and receipt counts stayed at 9 and 9. Cost union totals matched. This confirms settled byte reuse, not re inference.

## Failure reproduction

I reproduced two failures with my own operation ids and bytes in disposable database inv_rsem_fail. Neither failure used the author scripts.

- Zero budget probe refusal. I bound envelope rsem-probe with 1000 and a probe allowance of 50. I called admit_probe with amount 0. src/settlement/loop.py:128 returned reason zero-budget-probe. Consumed and reserved stayed at 0 and 0 before and after. A later amount 5 grant succeeded. I also called trajectory.dev_episode with max_queries 0. It returned disposition no-candidate with fallback incumbent and lineage empty. The reason carried zero-budget-probe.
- Malformed construction rejection. I passed text not python triple brace through construct.construct_method under campaign rsem-malformed-01. It raised ConstructionFailed with calls made 4. Four operations existed under the construct prefix. Each operation had a broker row and a success receipt. I also passed invented basis references through trajectory.run_campaign with campaign seq 91. It returned disposition no-candidate with fallback incumbent and reason invented basis references. Queries equaled 0.

Both failures have visible effects and lineage accounting. Malformed bytes leave operations and receipts. Refusals leave episodes with reasons. Zero budget leaves the study ledger untouched.

## Rulings

INV-R-S01. Contract rendering agrees with execution and validation. Accepted. I rendered construction packets for software and graph. The prompt contained the entry params, every forbidden call, the import rule, all candidate keys, all verdicts, all reason codes and all public operations. experiments/ad01/packet.py:172 renders the prompt. experiments/ad01/method_exec.py:37 defines the entry contract. The parser at experiments/ad01/packet.py:221 accepts the double bytes. The verifier accepts acquired_order and rejects import and dunder sources. Learner instruction and validator agree on kind values. Full B1 gate passed 11 of 11 on inv_rsem_b1. Full B3 gate passed 8 of 8 on inv_rsem_b3.

INV-R-S02. Malformed actions have visible effects. Accepted. My malformed run left 4 construct operations with broker rows and receipts. The rejected episode path in trajectory._run_boundary at experiments/ad01/trajectory.py:379 returns disposition rejected with construction calls counted. The invented basis path at experiments/ad01/trajectory.py:269 returns disposition no-candidate with the invented reason. Nothing advances silently.

INV-R-S03. Retention continues durably with byte identity. Accepted. Freeze, load digest check and subprocess use matched exactly in my trace. The use record executed_source equaled the retained method_source for both families. Full C gate passed 9 of 9 on inv_rsem_trace and inv_rsem_c2.

INV-R-S04. Rejection and kill resume continue durably. Accepted. My resume left counts and cost totals unchanged with zero new gateway calls. Cross database rerun in the C gate asserts ALREADY_APPLIED and equal acquisition, use and total dicts. The empty repertoire use path executes incumbent with preserved verdict.

INV-R-S05. Zero budget probes never consume study lineage. Accepted. My envelope ledger check and dev episode probe both confirm it. Full B2 gate passed 8 of 8 on inv_rsem_b2. Full B4 gate passed 4 of 4 without a database.

INV-R-S06. Replay boundaries hold. Accepted. I ran test_replay_boundary_refusals with PYTHONPATH set. It passed. Supported probes return recorded results with unknown costs. Hidden future, version mismatch, reordered dependents, new code bytes and malformed probes return unsupported or refused with empty results. Stale packets materialize as stale.

INV-R-S07. No gate was closed with a monkeypatched controller. Accepted with a note. The C success paths use no monkeypatch. Grep over tests/test_inv_c_qualification.py finds none. The B4 zero allowance test patches construct_method to fail the test if construction is called. That patch is a guard, not a success simulator. My unpatched dev episode probe confirms the same refusal without any patch.

INV-R-S08. No success gate was closed with a direct proposal callback. Accepted for the current tip. Rejected for the historical C3 corpus. All C success paths build propose through learner.propose_from_model at tests/test_inv_c_qualification.py:70. That function calls model_propose through broker admission. Only the explicit no-candidate test passes a refusing function at tests/test_inv_c_qualification.py:215. That test claims no candidate, not acquisition. The historical C3 corpus used a recording learner passed directly as propose. The E lane records this at the bfe1006 driver. That historical gate is not valid acquisition evidence. The current driver routes through broker admission instead.

INV-R-S09. The acquired program is substantive. Accepted for the INV-C double. Rejected for the historical C3 wrappers as acquisition. The INV-C source at experiments/doubles.py:74 contains no reducers import and no import at all. It implements its own shrink with bulk drops, degree order for graphs and witness last order for software. It reduced 16 to 3 and 12 to 10 with preserved verdicts in my run. The B1 CARRIED_SW wrapper calls reducers.reduce_software with method greedy. The E lane shows the committed C3 bytes equal those wrappers. Those bytes are fixtures, not acquired behavior.

INV-R-S10. Fixture success was not relabeled as acquisition on this tip. Accepted with a correction on record. The C tests label every double response simulated true and billed false. Cost union reports tokens none for simulated calls. The B3 canned seam test asserts model operations equal empty list. The historical authored false flags on wrapper bytes are rejected as acquisition labels. The E lane correction to 45 of 72 retained byte execution with 72 of 72 checker clean is the honest reading. Tip 5ff0f1e carries that correction.

## Rework

None for semantic causality. The remainder is the live comparison in design item 6. It needs separate authorization and is outside this review. Do not claim live benefit from doubles. Do not reuse the historical C3 corpus as acquisition evidence.

## Verification boundary

Doubles prove the integrated path, not live inference or containment. All runs used disposable databases named inv_rsem_trace, inv_rsem_fail, inv_rsem_c2, inv_rsem_b1, inv_rsem_b2 and inv_rsem_b3. I dropped them after exporting the outputs quoted above.

Reproduction.

- PYTHONPATH=src:experiments:. INV_C_DSN and INV_C_DSN2 pointing at two disposable databases. pytest tests/test_inv_c_qualification.py. Result here was 9 passed.
- INV_B1_DSN, INV_B3_DSN and INV_B2_DSN pointing at disposable databases. pytest on test_inv_b1_contracts.py, test_inv_b3_coord02_contracts.py and test_inv_b2_loop.py. Results here were 11, 8 and 8 passed.
- pytest tests/test_inv_b4_trajectory.py with no database. Result here was 4 passed.
