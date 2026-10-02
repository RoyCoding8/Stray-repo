# Worker: connect acquired behavior to evaluation and subsequent use

Reviewed base: `646e154094d85cf79fb9950b7b418c9e47c37a8d`. Fetch `origin/codex/representation-completion-assessment` and integrate additively into your owned `codex/implementation-cognitive-batch-01` branch. Use the configured remote and private author/committer `Nightjar <nightjar@authors.invalid>`. Preserve historical evidence and other tasks' work. This prompt is the current assignment; the original [Representation 01 contract](docs/design/REPRESENTATION-01-IMPLEMENTATION.md) still defines the experiment.

## Priority and architectural outcome

**Complete one connected learning experiment: constructor output → selected retained behavior → frozen held-out comparison → disposition → fresh-process use or fallback.** This is the only foreground objective. The user explicitly prioritizes important functional work over minor polishing. Note incidental small defects and portability/report cleanup for later; do not turn them into another prerequisite list or broad audit. Fix issues that prevent this path, falsify its evidence, or violate its execution/authority boundaries.

Agenda remains an accepted scoped prototype. The representation acquisition, held-out fixture runner and full decision rule are useful delivered components. We are at stage 8.5; no new architecture or stack is needed to connect them. A negative or no-candidate result is acceptable. An authored-fixture comparison is evidence about that fixture, not about what the model acquired.

## The important gap at the reviewed revision

The configured `live_campaign.py` now calls `campaign.run_campaign`. That function constructs/stages candidates, executes C on the source/transfer selection tasks, records retention, and returns `disposition: complete`. It does not invoke held-out evaluation or subsequent use. Separately, `run.run_panel` calls `ensure_compositions`, which stages the repository's authored packages from `freeze.COMPOSITIONS`; it accepts no campaign selection as input. Searching the experiment's callers shows no consumer connecting campaign retention to the held-out runner.

The same gap affects the arms: `campaign._stage_and_execute` publishes A lessons and B's `procedure.py` through `stage_text`, then invokes only slots having a `composition_id`. B's acquired procedure is therefore stored but not executed there. Its selection is first-parseable text. The current held-out A/B results instead come from the authored native reducer selectors. These facts prevent the claimed complete acquisition experiment even when credentials become available.

There is also an essential input to supply while completing this connection: transfer construction currently receives the frozen core's digest but not its implementation or a sufficient operational interface. A digest identifies the core; it does not teach a constructor how to write a compatible adapter. Candidate prompts currently specify file names and parseable Python, but must also supply the actual invocation contract needed to produce working code. Provide the necessary versioned interface/meaning and frozen-core content or a controlled way to retrieve it, within the existing context and exposure caps. Do not expose held-out tasks.

## Finish the connection using existing components

1. **Carry one selected acquisition result forward.** Freeze the actual A/B/C retained artifact and selector identities, source/transfer lineage, applicability, dependencies and budget policy after development/check selection. Let the evaluation entry consume that result. Preserve an explicit authored-fixture mode for historical reproduction; do not silently use it when acquired artifacts are absent or invalid.
2. **Make each arm's retained material operational.** Give A's lessons the declared effect on its development-selected behavior; execute B's selected task-specific procedure through a bounded, independently checked path; run C's selected core/adapter composition. Missing or rejected candidates follow the declared incumbent/fallback policy with a recorded reason and honest cost. Stored text or code alone is not executed learning.
3. **Evaluate those exact identities.** Bind the 16 held-out benefit inputs plus four controls across A/B/C to the selected campaign artifacts before executing them. Derive results and the full decision rule from their actual outputs and costs. Selection and transfer adaptation must already be frozen. Keep the same C core bytes across source and graph interpretation, or label adaptation rather than unchanged-core transfer.
4. **Carry disposition into a new process.** Load the retained result and its trial/release status from durable state/artifacts. Demonstrate actual selected use where authorized or persistent rejection/incumbent fallback. A promising pilot is not a general release. Do not force a positive result or bypass existing eligibility to exercise a path.

Do not introduce another registry, evaluator framework or controller to accomplish this. Choose the smallest explicit interface between the existing campaign and panel code. Version the run-specific freeze and evidence as needed without relabeling or overwriting RPR-ACQ/1 or RPR-ACQ/2 history. Record whether a public entry completed acquisition only or the entire experiment; its status must name the phase actually completed.

## Acceptance centered on the complete behavior

Use parallel workers where their owned paths are independent: one owns campaign retention and usable constructor contracts; one owns consumption by evaluation/disposition/use. Set the shared interface first, then integrate serially. An independent reviewer must follow the acquired artifact through the combined path. Apply the existing worktree, ownership and non-author verification discipline; do not repeat five broad subsystem reviews of unchanged components solely to satisfy a pass count. This narrows the earlier workflow to the remaining outcome.

The decisive deterministic check must use the real public orchestration with a controlled model seam returning behavioral bytes different from the authored fixtures. Follow their digests into held-out invocations and fresh-process disposition/use. Exercise B as executable behavior as well as C. Demonstrate that changing a returned candidate to one with different known behavior changes the observed output/verified failure on an appropriate fixed diagnostic task; a cosmetic digest change is insufficient. The diagnostic task need not reveal a held-out answer to the constructor.

In an isolated reviewer copy, disconnect acquisition consumption or force the authored package back in. The end-to-end acceptance check must fail. Also cover explicit no-candidate handling through the same public entry. These checks are the completion evidence: separate green acquisition tests and green fixture-panel tests cannot substitute for them. Fix confirmed defects that defeat this proof and recheck affected paths; ledger unrelated issues.

Use a real available gateway and durable finite grant for the bounded campaign when prerequisites are present. The original 12 construction-call ceiling and phase/token/exposure limits remain; extra reviewer tokens do not authorize extra experimental campaigns. If access is absent, finish the connected deterministic path and report **implemented, live externally unverified**. Do not report a model-acquired held-out result when the executed bytes were authored. No new reviewer approval round trip is required within the previously authorized valid grant/profile.

## Evidence already accepted; do not redo it for appearance

At `646e154`, the architectural reviewer independently checked the committed held-out manifest/evidence and recomputed 48 benefit records plus 12 controls: C graph mean `0.153019`, A/B `0.299312`; C elapsed `52.309 s`, A/B `0.021 s`; the full rule returns promising false and release ineligible. Missing CPU/exposure measurements block the resource clause. Preserve this authored-fixture negative result.

Local focused check: `tests/test_rpr10_campaign.py` and `tests/test_rpr11_heldout.py` produced 14 passed, 10 skipped, one Windows regeneration failure. The failure is the previously noted source-context path spelling difference, not evidence that the Linux campaign failed. Stored manifest/record checks passed using exact committed bytes. Full real-PostgreSQL verification remains worker-reported. Windows regeneration, prose inconsistencies and similar minor cleanup are notes, not new foreground gates.

## Handback and stop

Keep a short task/coverage list in PLAN for the four steps above. Update the current experiment report, verification/status entries and roadmap with the connected-run evidence and precise live boundary; extensive historical prose cleanup can wait. Include exact candidate identities, invocation evidence, per-phase cost boundaries, panel counts and subsequent-use disposition.

Run the affected checks and configured end-to-end acceptance on the merged source, with appropriate final integration verification. Stop after this outcome is established or its genuine external live blocker is recorded. Push normally, verify remote equality, and return the SHA and the exact command/evidence for the complete path. Do not start teams, learner revision, a new benchmark campaign, another agenda run or unrelated deep cleanup.
