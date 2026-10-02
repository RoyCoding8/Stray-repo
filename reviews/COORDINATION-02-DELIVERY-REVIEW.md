# Coordination 02 delivery review

Reviewed `0b47dcf` on `codex/implementation-executable-coordination-02`, 2026-09-13. Inspected the complete reported delta `7e3dadc..0b47dcf` and followed its runtime, construction, schema and freeze dependencies at that tip. The worker calls `7e3dadc` last reviewed; this report does not infer that every earlier lane was independently accepted by this reviewer.

**Disposition: useful fixture apparatus, incomplete live implementation.** Do not start the large held-out panels. The provider problem may be real, but it is not the sole blocker. The new entry still implements authored stand-ins and synthetic accounting. A reported absence of usable construction outputs is not evidence against the architecture, and the delivered evidence is insufficient to certify a fully reconciled, prescribed no-acquisition study.

This review is deliberately limited to execution, experimental validity and evidence preservation. It does not request a style cleanup or whole-repository audit. The completion assignment is [here](../docs/HISTORY.md#worker-coordination-02-completion-correction).

## Verification and boundaries

- Fetched and pinned the complete delivered tip in an isolated review worktree; no edits to the worker's checkout or source implementation.
- Ran [the independent semantic probes](probes/coord02_delivery_review.py), with [observed output](probes/coord02-delivery-observed.json). They use actual repository functions, controlled mocks at external seams and subprocess execution of the authored baseline programs. No database or gateway was contacted.
- Ran seven existing focused tests: trial-record round trip; refusal/timeout cost preservation; operation-union deduplication; unknown union handling; joint promising rule; entry arm distinctions; construction-prompt response contract. **7 passed in 4.81 seconds.** Their success does not reject the failures below.
- Did not rerun the worker-reported 41 PostgreSQL tests, access its live DB, reconstruct deleted receipts or verify its provider observations. The fixtures explicitly truncate configured databases, so they were not invoked against any live evidence store.
- Current observations and source were checked directly. Earlier project memory supplied the intended causal order and recovery constraints only.

## Required corrections

### ECR2-01 — Blocking: the public entry has no genuine four-arm live solver

`experiments/coord02/entry.py:71–117` generates fixed programs for S/A/F. S and A both choose the same single-worker plan; A's retained text is only asserted nonempty. F always chooses an authored split of the file list, not the specified conditional baseline. Every arm's child factory returns `dev_constructor(..., solved=True)`, which reaches `experience.py:511–533` and reads `oracle.overlay_files(task, "valid")`.

The probe intercepted this protected reference-overlay access for **all four arms** and executed S/A programs to confirm identical proposals. `main` at lines 408–427 always constructs `FakeGatewayAdapter`, never wires a real gateway into the solver, and treats a model argument as a labeling choice. There is no live policy-model path for A or live child-construction path for any arm. `run_cell` also installs authored S code when L has no package, without the required explicit acquisition/fallback lineage.

These are legitimate stand-ins inside labeled mechanism tests. They cannot be the implementation of the live experiment waiting only for a provider. Restrict fixture behavior to explicit test mode and implement real S, model-interpreted A, competent fixed F and directly executed L through the shared admitted execution path. A none selection must remain none with an explicit fallback and observed remaining allocation. Live records must bind actual model response bytes to the admitted child's submitted artifact.

### ECR2-02 — Blocking: cost and execution evidence are manufactured at the entry

`entry.py:150–159` returns exactly 100 input tokens, 20 output tokens and one model call, independent of actual operations; CPU/wall/elapsed are zero. At lines 162–172, absent step-operation IDs can become the run ID as a receipt placeholder. At lines 367–370, the writer attaches the entire cell cost to each operation reference, multiplying cell totals when several references exist rather than summing each operation's own cost once.

The probe showed unchanged model usage for one versus fifty policy steps. The numeric values are fixture constants, not measured zero/nonzero usage. `check_ceilings` additionally reads nested `model_tokens` while the trial stores flat `model_tokens_in/out`; the probe supplied one million input tokens and received no violation. This check happens after the episode anyway, so it cannot provide admission control.

Derive episode and campaign records from actual operation/receipt unions, preserving unknowns, failed calls, checks and liabilities. Enforce available capacity before each effect through durable root allocation; reporting must not invent receipts or call itself pre-admission afterward. Validate the integrated writer/reconciler, not only the arithmetic helper against synthetic examples.

### ECR2-03 — High: acquisition still omits the experience and usable contract it is meant to learn from

`experience_packet` records versioned inputs, decisions, plans, joins, artifacts and costs. `construction_request` at lines 236–268 reduces that to probe observations plus a digest; `render_construction_prompt` does not deliver the omitted contents. The probe confirmed that plan, join, source and failure sentinels disappear from the actual rendered prompt while the probe observation remains.

`controller.construction_call_spec` supplies field-name lists and illustrative actions, but no concrete nested task/child-plan schema sufficient to construct valid ownership/input/output bindings. Its plan example has no children. The newly added `entry` response requirement fixes one transport omission; it does not make the complete executable interface or episode experience available. A digest of unavailable content is not learning context.

Materialize bounded, linked development examples including the current public task/ABI, attempted organization, observations, actual outcome, residual and cost, plus the complete invocation/action contracts. Validate with a semantic fake constructor that inspects these fields and emits input-dependent behavior. Keep authored repair experience labeled until genuinely live repair episodes exist. This missing information does not prove why a provider returned empty text; it is a separate implementation gap to close before interpreting acquisition quality.

### ECR2-04 — High: construction bounds and surviving evidence do not support the handback's claims

The design grants four construction calls per defined study. `ConstructionLedger` guards `len(self.calls)` in one in-memory instance; `acquire` creates a fresh seed/allocation and operation prefix on every call. Unique IDs solve collisions but do not preserve the study-level counter across recovery/restarts. The handback reports six rounds and 24 calls; any separately authorized later grants or new study boundaries must be identified rather than inferred from a new prefix.

The only committed file under `experiments/coord02/evidence-live/` is the prose report. It simultaneously says all spend is receipted and that rounds 1–4 were wiped by test-fixture TRUNCATE. Its listed dispatched counts are eight in rounds 1–2, no dispatch in round 3, and twelve in rounds 4–6: twenty explained calls, not the asserted twenty-four. Raw responses, operation exports, round manifests, selected-none artifact and essential live driver are not delivered there. This reviewer cannot independently establish the count, usage, provider cause, billing or completed fallback from that material.

The production ledger also hardcodes `doubled=True`, `live=False` and `live_calls_used=0` even when given a real gateway (`experience.py:372–401`). Actual backend provenance must determine those labels. Missing receipt text currently falls back to zero tokens; unavailable evidence must remain unknown.

Recover and publish surviving records first. Preserve the incident, report irrecoverable gaps explicitly, and identify any available authorization for extra rounds. Do not invent deleted receipts or erase the history by starting a fresh DB. Enforce campaign limits durably and prevent test cleanup from targeting evidence databases using mechanically checked database purpose/ownership, not just a memory reminder. Further provider work needs an identified finite remaining or newly authorized diagnostic allocation.

### ECR2-05 — High: the executable entry does not preserve the frozen experiment

`run_panel` at lines 306–325 extracts task IDs and loops its own S/A/F/L order instead of executing frozen schedule entries. The probe supplied frozen order L/F/A/S and observed S/A/F/L. `main` at lines 412–415 removes other panels from the schedule, while `verify_freeze` rejects anything differing from `build_schedule`. Thus the CLI mutates the very object its checker requires to stay whole.

`run_cell` computes the executed entry digest for the controller but writes the separately supplied `package_digest` into trial evidence. It does not verify the supplied package against the frozen selection. Defaults such as `entry-base` and unconfigured model/baseline metadata are permitted into the CLI-generated freeze. Main has no interface for loading the selected frozen package or resuming acquisition-to-use from that artifact.

Make the CLI load and verify one committed freeze/selection, execute its scheduled cells with stable identities and explicit resume, and bind observed records to the actual pinned package/configuration and input bytes. A requested panel filters execution, not the frozen manifest. Fresh-process transfer must load retained bytes; a fake gateway or authored fallback cannot silently stand in for those bytes. A real fresh-checkout run/replay is required; successful import of `ARMS` proves only importability.

## What stands and what does not

The shared controller and authored probes provide useful development evidence for admission, submission and join mechanics. The source now offers a seam where a real model constructor can be connected. The decision not to spend 144 held-out episodes on a known-empty learned arm was sensible.

However, G1 is not accepted as complete against all intended behavioral obligations merely because a fixture panel is green. G2 is a worker-reported unsuccessful provider/construction attempt with incomplete retained evidence; clean no-acquisition disposition and fallback remain to be established. G3 has additional implementation blockers beyond the provider. G4 remains incomplete.

Do not redesign executable memory on this evidence. We have not yet measured the proposed live policies. The next work is to connect and verify the intended implementation, restore honest evidence boundaries and then use a bounded transport/constructor check to determine whether the configured model can emit a usable program.

## Task list

- [x] Inspect the whole delivered tip and relevant call paths.
- [x] Reproduce entry, context, cost and frozen-order failures without touching live evidence.
- [x] Check selected existing tests; distinguish their passing scope from the missing behavior.
- [x] Specify corrections, concrete integration contracts and the full completion sequence for the worker in [the current assignment](../docs/HISTORY.md#worker-coordination-02-completion-correction).
- [ ] Worker closes ECR2-01–05 or provides a concrete source/behavior rebuttal.
- [ ] Establish a genuine live vertical path and candidate selection, then continue through the already commissioned frozen study after internal review; alternatively complete an auditable bounded no-acquisition outcome.
- [ ] Independently reconstruct the final evidence and deliver mechanism, benefit, transfer and next-design conclusions in the same worker handback.
