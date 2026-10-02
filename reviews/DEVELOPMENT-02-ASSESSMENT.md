# Development 02: bounded acceptance and live prompt check

Reviewed source: `a1d2525a37571abf45a54de45c3dfcdad4aaaf9f`, fetched from `origin/codex/implementation-development-02`. Assessment branch: `codex/development-02-assessment`. Production code unchanged.

## Decision

Accept the deterministic mechanisms as useful prototype progress. Do not describe the complete live episode, ordinary post-release use, or CTX-01..CTX-10 as validated yet. The next assignment is one bounded live-completion slice, not another unrestricted review. Agenda design can advance independently.

There are three episode corrections below (D2A-001..003), plus two context limitations that must be closed before claiming their corresponding contracts (D2A-004..005). A fresh, single-episode, ample-context experiment can exclude the latter failure conditions explicitly; it cannot establish durable context correctness under reuse or pressure. This is a restricted experiment, not a relaxation of CTX.

## What is accepted

- Collection now precedes diagnosis; task material is stored as claims with observation-premise warrants. Harness transcript reuse avoids rerunning the same development batch in the normal entry path.
- Comparison synthesis resolves the selected binding, and an episode rejection supplies no candidate. D02-002 is closed at that seam.
- A finite panel is declared at admission and version binding follows development. The fixed entry path addresses the original first-freeze timing gap. This assessment does not qualify arbitrary policy amendments or adaptive evaluation.
- A fresh-process use entry really invokes and grades a method or incumbent. That closes the former absence of execution, but its selection source is still wrong (D2A-003).
- Packets, support alternatives, operator inspection, continuation state and a challenge panel exist. The worker reports 509 tests passed on its final tree. That suite was not rerun here.

## Episode corrections

### D2A-001 — The emitted model contract does not describe the consumed product

**Blocks the live episode; DEV-04 / CTX-03.** `development.py:633-646` declares only the filename and `--selftest`. The actual consumer, `experiment.py:260-295`, invokes a program with two path arguments and reads `fixed.py`. Nothing in the emitted invocation contract says to read the first path, transform its source, write the second path, or implement a reusable repair procedure rather than the repaired task itself. The diagnosis response shape in `context.py:204-219` also omits the intervention consumed by `development.py:510-519`.

The independent live prompt check used the requested `claude-opus-4-6-thinking`, the production 512-token response ceiling and production packet rendering over synthetic database-shaped state. Both responses ended normally (`stop`); both failed strict JSON parsing. Diagnosis returned fenced JSON. Construction returned prose plus fenced JSON containing a repaired `sum_to` function with no file interface. Its code was not executed. Production diagnosis uses `json.loads(text)`; construction treats that response as invalid output. The model did include an intervention despite the incomplete diagnosis schema; absence of intervention is not claimed as a live observation.

**Correction:** specify the complete response and executable interface from one canonical contract shared with the consumer. Handle provider output through a declared bounded policy: structured output if supported and verified, or explicit formatting instructions plus deterministic envelope handling and schema validation. Never treat arbitrary prose extraction as validated code. A valid abstention remains allowed. Verify the exact live emitted prompt and returned bytes, then apply and grade the constructed procedure on a different input in the supported execution profile. Do not handwrite the successful candidate after seeing the model fail.

### D2A-002 — Collected experience is stored but not fully delivered to diagnosis

**Blocks the intended experience-conditioned diagnosis claim; D02-001 / CTX-02.** `_collect_task` creates claims with original source and cases (`development.py:338-351`), but `collect_experience` returns their IDs without connecting them to the episode's trigger refs (`359-401`). `_claim_candidates` selects diagnosis claims only from those refs (`context.py:618-640`). The ordinary CLI refs contain task ID/family only. Diagnosis therefore gets outcome receipts and model text, but no evidence bundle resolving the newly stored original source and task cases.

The worker regression checks the source in the database and task ID in the prompt separately (`test_dev02_episode.py:172-195`), which misses this distinction. The independent probe materializes a ready diagnosis with a visible collected claim: its bundle list is empty and its original-source sentinel never appears in rendered input. It does contain the repaired model output. This is partial experience, not no experience.

**Correction:** durably connect admitted episode experience to the required decision inputs and prove the actual outgoing prompt contains original task material, attempts, outcomes and permitted feedback. For the first run, a dedicated investigation/database is an acceptable isolation condition. Investigation-wide raw receipts and globally visible candidate claims are not sufficient isolation for later multi-episode or held-out-data reuse; do not claim that broader boundary from this run.

### D2A-003 — Subsequent use bypasses comparison disposition and applicability

**Blocks ordinary post-disposition use; D02-004 / CTX-08.** `run_use.py:78-92` passes the episode's pre-comparison binding. `run_subsequent_use` checks existence, quarantine and bytes, then invokes it (`experiment.py:723-751`); it does not resolve the release/router disposition or task family. `_maybe_release` can return `ineligible` or `skipped-synthetic` while this path still uses the candidate. The default subsequent task is a transfer-family task (`run_dev_episode.py:309-325`), making scope relevant in the current CLI. Its summary can simultaneously report incumbent fallback and selected-method use.

The independent probe invokes an unreleased `off_by_one` binding for a `wrong_operator` task; routing is never consulted. Persistence, invocation and grading are doubled in that probe, so it establishes the orchestration choice, not a sandbox escape.

**Correction:** subsequent ordinary use must resolve the durable post-comparison disposition and scope through the normal selection path. No release, wrong scope, missing bytes or quarantine selects the incumbent (or a declared refusal). A deliberately unreleased experimental invocation is legitimate only as an explicitly labeled trial, not evidence of ordinary use. Persist that distinction across the fresh process.

## Context limitations, with controlled experiment exceptions

### D2A-004 — Packet linkage does not prove which input was sent

**CTX-05/06 remain incomplete.** `bind_packet_invocation` checks packet self-hash and operation existence only (`context.py:992-1027`). It does not read the operation's input, verify a model operation, or revalidate the packet. Diagnosis/construction bind after inference (`development.py:502,661`). The probe binds a valid packet to an unrelated existing operation without any payload read. The current ordinary constructor does embed the packet; this is not evidence that it omitted the packet on that path.

Before durable reuse claims, bind the actual serialized model input and its policy/source footprint to the immutable admitted request, verify it at the dispatch boundary and reject conflicting/replayed linkage. Preserve the previous delivered bytes when a packet is refreshed. For one isolated experiment, saving and comparing the complete admitted request, actual emitted messages, response and packet bytes is an acceptable explicitly manual verification; merely querying `packet_invocations` is not.

### D2A-005 — Budget fallback strips the content of known counterevidence

**CTX-04 remains incomplete under pressure.** `_bundle_view(..., False)` replaces opposition bodies with IDs/kind/status (`context.py:825-834`). `build_packet` then reports `ready` if this reduced rendering fits (`917-919`). The probe supplies a decisive negative-input counterexample; the reduced packet keeps its ID but drops the counterexample while staying ready. The maintained budget test currently expects this behavior.

Keep decision-relevant opposition content, use a justified traceable reduction, or return a staged/narrower `needs_information` outcome. Knowing a counterexample ID exists does not convey its constraint. An ample-context pilot with exact mandatory delivery and no such omissions can proceed now; it does not validate compression or omission policy. Also measure the actual final message envelope when claiming an input bound, rather than only the packet's `_wire` estimate.

## Answers to the worker's four questions

1. **Pre-candidate contract: yes.** Declare the target interface before a candidate exists; bind actual version and bytes afterward. Requiring an existing candidate to specify what should be built is circular. D2A-001 is about incomplete content, not this decision.
2. **Split settlement: yes, with explicit aggregation.** Protocols can own different phases, and reuse should reference existing operations. Report a unique-operation union for the whole episode, separating shared acquisition, candidate development, evaluation and subsequent use. The current CLI exports harness totals (`run_dev_episode.py:427-428`), which omit diagnosis/construction/check operations and the later use phase. Do not call those totals all-in development cost or use them for an efficiency claim. Budget enforcement in the allocation is a separate question.
3. **Previously exposed task: acceptable for a restart/execution smoke only.** It cannot establish unseen-task competence. The task and exposure label must be declared. A live held-out comparison requires genuinely unexposed evaluation material; subsequent use must follow scope and disposition even for a smoke.
4. **509 passing deterministic tests: useful, not sufficient for blanket closure.** D02-002 closes; freeze ordering is accepted for the fixed entry; experience delivery and post-disposition selection remain partial. Tests written around partial contracts do not prove the complete experiment, and the live formatting failure is directly observed.

## Independent evidence and stopping rule

`python -m pytest -q reviews/probes/test_development_02_acceptance.py`: **5 passed**, 1 existing unknown `asyncio_mode` configuration warning, 1.25 seconds. Passing means the current limitations were reproduced. Actual production functions ran with explicitly mocked DB/effect boundaries. No real PostgreSQL or sandbox was used here.

The two-call [live prompt pilot protocol](../reports/evidence/development-02-prompt-pilot/protocol.json) was written before either call; [results](../reports/evidence/development-02-prompt-pilot/results.json) retain exact responses. Reported tokens: diagnosis 525 input/358 output; constructor 693 input/397 output. These are provider-reported usage, not verified billing. Each request allowed 120 seconds and zero retries. The requested model was returned on both calls. The apparatus is [development_02_prompt_pilot.py](probes/development_02_prompt_pilot.py). Synthetic state and independent prompts mean this is not the full runtime's live episode or a statistical learning comparison.

Finish D2A-001..003, independently assess 004..005 and either close them or establish the narrow conditions above, then run one predeclared live episode and report the result. Negative, rejected or inconclusive competence outcomes are acceptable. A transport/parser failure is evidence about integration, not learning. Do not reopen unrelated S0-S3 hardening or require a positive learning result.
