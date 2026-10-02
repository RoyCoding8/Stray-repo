# Development 02 live campaign: acceptance and interpretation

Reviewed remote source: `3857ec44c66d572048114f80c9ee5aae988daef9` on `codex/implementation-development-02`, fetched 2026-09-11. The supplied message named `f495c60`; that object was not available in fetched history. This assessment applies to the available commit with the matching live-campaign report and four episode files. Production code unchanged by the reviewer.

## Decision

**Accept live integration and fallback-path exercise as prototype progress, based on the worker's report and committed summaries.** The old blanket statement that no runtime inference has occurred is obsolete. Do not reopen all foundation hardening. The reported 530-test deterministic suite is useful evidence; it was not independently reproduced here.

**Do not accept “0 scores is a model-on-tasks finding, not a pipeline defect.”** The campaign does not isolate task-solving ability from output formatting. Nor does it demonstrate successful acquisition/use of a retained method. A negative learning result would be acceptable, but these observations need a narrower interpretation.

## What the four saved records establish

All four files in `reports/evidence/d02live/` identify `muse-spark-1.3-contributor-free`, `simulated: false`, and `local-process`. They are not results for the earlier requested Claude model. Each contains 15 failed arm-task outputs (5 tasks × A/B/C): **60 across the campaign**, or 20 per arm. All 16 pairwise/group verdicts are inconclusive. Every episode rejects its constructed candidate; `development.methods` and `ablation_noop` are empty. Subsequent use selects the incumbent with an explicit no-release reason and also grades as failure.

This is evidence of live orchestration, candidate rejection and fallback execution. C receives no acquired method in these comparisons, so these are not four demonstrations of acquired-procedure transfer. “0/0” in the prose denotes zero candidate and reference successes, not zero evaluated tasks.

The summaries identify 46 unique operations per episode and report zero unresolved exposure. They omit exact model prompts/responses, candidate bytes, per-case grader errors, and the DB settlement rows. Those cannot be reconstructed from IDs after the worker deletes the databases/artifact scratch. Treat the worker's detailed live diagnosis/staging claims as reported, not independently replayed from these summaries.

## EVID-01: distinguish formatting failure from semantic task failure

`experiment._arm_prompt` (`src/settlement/experiment.py:634-648`) supplies task source and a tool envelope but no explicit Python-source response contract. The A/B/C path then passes the entire model text to `_prepare_grade` (`989-996`), which writes it directly as `candidate.py` (`149-157`). Collection and incumbent use also consume text as source. The diagnosis/constructor JSON fix does not cover these distinct solver outputs.

The worker's own `reports/workstreams/d02live-live.md` records a live diagnosis of correct fixes trapped in prose with syntax errors. That is evidence against excluding a harness/model-interface explanation. Exact causes of all 60 failures remain unknown because the raw traces were not preserved.

Independent real-subprocess control, using trusted repository fixture bytes: `panel-triangular`'s correct reference code scored **3/3** with the production grader; identical source inside a Python Markdown fence scored **0/3**, each failure a `SyntaxError`. The grader can score this correct code; the control demonstrates the format confound, not retrospective proof that every live answer was correct.

Before another comparison, declare a consistent solver response format and deterministic validation policy for collection, all arms and incumbent use. Preserve raw text separately from accepted source and classify transport, truncation, format, import/execution, timeout and wrong-answer failures. Use a positive grader control and one live baseline task before buying another campaign. Do not salvage arbitrary prose differently for different arms or edit a candidate after evaluation exposure.

## EVID-02: unknown billing is not zero cost

The Responses decoder (`gateway_http.py`, `_decode_responses_body`) sets `charge_units=0, billed=False` without decoding monetary fields. That establishes **billing unavailable in this adapter**, not a verified free price. The broker correctly passes `actual_cost=None` for unbilled usage (`broker.py:458`), invoking conservative settlement. However, `_op_accounting` (`experiment.py:356-386`) reports `usage.charge_units` whenever present, ignoring `billed=False` and the actual settled debit.

An independent doubled-DB probe supplies a settled 1000-unit reservation and the broker-shaped unbilled receipt. The reporting function returns settled=0, unresolved=0. This demonstrates a reporting defect, not a bypass of allocation enforcement. Accordingly, the campaign's identical 2664-unit totals cannot be accepted as verified all-in settled cost or provider billing. Provider-reported token counts, external price and conservative internal debit need separate fields. Reconcile reports to the actual durable settlement and allocation changes.

## Provenance and bounded limitations

- Each episode file records revision `976cee1`, before the committed Responses changes, while the narrative says those changes were needed to run. These were evidently working-tree runs; the summaries do not pin their full source. Preserve this history and record immutable source/dirty-tree fingerprints next time rather than relabeling old runs as executed at the new commit.
- The narrative says 8192 response tokens; saved `budgets.*.matched_caps.tokens` still says 512. Freeze and export the effective configuration, including API, token/packet bounds and timeouts. Fixed defaults are not evidence of effective runtime caps.
- The campaign used explicitly uncontained local execution. It does not qualify runsc containment or justify running arbitrary generated code on a sensitive host. Future execution must have an appropriate profile or an explicitly authorized disposable environment.
- The single-slot-per-family observation is a seed-policy limitation, not a blocker. An admitted ceiling of two is not an obligation to consume both. Defer adaptive revision policy to its intended design stage.
- Packet input hashing remains partial CTX-05/06 assurance: the binder hashes stored payloads but does not establish inclusion of rendered evidence or revalidate before dispatch. Keep the earlier fresh-run/exact-input verification restriction; no broad memory closure is inferred from the six probes.

## Independent checks and next step

`python -m pytest -q reviews/probes/test_live_evidence_controls.py reviews/probes/test_development_02_acceptance.py`: **9 passed**, one existing unknown `asyncio_mode` warning, 4.86 seconds. This includes two real-subprocess grader controls, one reporting-defect characterization with explicit DB doubles, and six existing mock-level acceptance probes. No new live calls, real DB suite or generated-code execution were performed for this campaign assessment.

Next worker work is [a small evidence repair and solver smoke](../WORKER-LIVE-EVIDENCE-PROMPT.md). Close live access/integration as exercised; keep competence, retained-method transfer, accurate accounting and operational qualification separate. Agenda policy design at stage 8.4 can continue without waiting for a positive learning result.
