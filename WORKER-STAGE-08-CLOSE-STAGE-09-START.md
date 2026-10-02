# Worker: close stage 8 fixes, then start stage 9

This is self-contained for a fresh worker chat. Fetch `origin/codex/stage-09-handoff`, inspect local status and ownership, and create `codex/implementation-stage-08-close-stage-09-start` from that fetched tip. It includes implementation `f3d20ac`, committed live evidence `a26408f` and this assignment. Preserve uncommitted work and other owners' resources. Reuse a suitable clean owned worktree or create one isolated task worktree. Do not reset or force-push.

The human explicitly asks you to fix stage 8 first, test and report, and then start stage 9 with no further nudge. Complete both phases in this assignment. Stage 9 here means a concrete architecture consolidation package and feasibility checks, not the final system rewrite. The external architectural reviewer will assess that package before assigning the larger migration. Do not stop after the first bug fix or substitute a roadmap paragraph for stage 9.

Read `AGENTS.md`, `docs/design/STAGE-09-CONSOLIDATION-01.md`, `docs/design/ARCHITECTURAL-DIRECTION-2026-09-17.md`, `docs/design/INVESTIGATION-01.md`, `IMPLEMENTATION-WORKFLOW.md` and `COLLABORATION.md`. Then read the evidence README, live report and actual records relevant to your checks. Earlier worker assignments explain history; they do not restart old campaigns. No private conversation or machine-local memory is needed to understand the work.

## Phase A: bounded stage 8 fixes, tests and report

### A1. Make the advertised method operations executable

The reviewer found a concrete contract mismatch. `experiments/ad01/packet.py` advertises bare `reduce_graph(...)` and `reduce_software(...)`. The child in `method_exec.py` supplies `reducers`, not those names. The archived run contains ten construction calls: four completed responses, three output-limit responses, three timeout/unknown receipts. All four recorded validation executions failed with `NameError: name 'reduce_graph' is not defined`.

Confirm this independently. Reuse the existing reducer functions. Put the versioned callable contract under the executor's ownership and derive prompt exposure and runtime bindings from it. Preserve the offered functionality unless evidence demonstrates a required contract change. Do not merely remove the advertised helpers, rewrite every generated candidate, add instructions telling the model to guess a namespace, or run candidate code in the trusted parent.

Inspect every caller and both domains. Verify signatures, result envelope, legal candidate shapes, oracle semantics, actual shared query accounting and bounds. Do not expose the whole trusted host as a convenience. Keep authored helper behavior labeled; a generated wrapper that delegates to an authored reducer is not by itself a novel learned algorithm.

Acceptance: a candidate independently written from the rendered contract calls each advertised operation through the actual child path. Include graph and software helper use, direct oracle use, a substantive candidate that does not delegate its whole strategy to a helper, malformed output and query exhaustion. Assert behavior and measured resources, not only string equality. A fake executor cannot prove the namespace fix. Record at least one failing-before case and its fixed result. Reuse existing tests and helpers where possible.

### A2. Diagnose the archived construction failures honestly

Re-execute the four archived candidates that reached validation through the corrected public execution path, without editing their source bytes. Use separate owned resources and label this as a post-fix diagnostic intervention. Record source digest, old failure, new outcome and any next failure. Do not overwrite the six original repertoires, the 24 original use records, their verdicts or their freeze. These candidates have already seen those development tasks; this exercise is not held-out transfer.

Classify the other construction attempts from their receipts and actual response content. Preserve timeout/unknown exposure, output truncation, parse failure, execution failure and no useful improvement as separate outcomes. Determine whether current timeout/output settings are faithfully applied and whether bounded repair gets the actual failure. Fix confirmed wiring/decoding errors on this path; do not increase every limit, switch models, append retries or treat free billing as unlimited authority.

Inspect actual remaining grants before any new inference. If the human has separately authorized a suitable bounded live continuation, run only the smallest relevant confirmation within its remaining limits, pinning changed configuration as a new run. Otherwise finish the executable diagnostics and controlled-provider tests without model calls and give one concrete optional live request. A spent historical grant or a fresh database is not new authorization. Lack of new live authority must not stop Phase B.

### A3. Verify and report before Phase B

Run affected contract, constructor, packet, public trajectory, recovery and evidence checks on the integrated source. Prove at least one full public acquisition/check/retention/use path with provider doubles only at the model boundary, and one honest rejection/fallback path. Label authored test candidates and actual model bytes separately. Gate usefulness according to the existing criteria; do not relax the judge to manufacture retention.

Run the applicable full suite with the required database setup once the final production changes are integrated. Fix relevant failures; classify skips/setup errors exactly. Record source identity and commands. If a later change touches production, rerun the affected integrated checks and state precisely which tree the full suite covered. Do not turn a single passing file rerun into an all-green claim for a suite with skips/errors.

Commit `reports/STAGE-08-CLOSEOUT.md` with the defect, fixes, archived-candidate diagnostic table, verification boundaries, and stage disposition. The original live study remains no-retention. Distinguish closure of this engineering slice from unproven learning efficacy, hostile containment and other operational qualification. Ledger unrelated minor findings. Continue directly to Phase B.

## Phase B: start stage 9 architecture consolidation

Implement the design work specified in `docs/design/STAGE-09-CONSOLIDATION-01.md`. The intended center is a persistent investigation with accumulated experience and revisable executable learning procedures. Agents are temporary participants. This is broader than fixing helper names and broader than a SWE agent. Preserve the current broker, authority and evidence guarantees while evaluating substantial changes in cognitive ownership.

### B1. Ground and compare

Trace the actual public paths for both domains. Map authoritative state, effect admission, model-visible context, construction, diagnostics, revision, retention, later use, crash recovery and export. Distinguish implemented callers from unused helpers. Include `DecisionConsumer`, `trajectory`, `packet`, `construct`, `method_exec`, `records` and the relevant settlement facilities. Inspect existing replay and context implementations before proposing replacements.

Compare the two structurally distinct alternatives in the design brief: consolidation in the current consumer/driver, and extraction of an action-level persistent investigation core. Give each a concrete usage example, ownership model and migration cost. Evaluate branching, context loss, policy replacement, domain dependence, state duplication and interface depth. Pick one with source-backed reasons. Do not pick solely by diff size or invent a platform because implementation is cheap.

### B2. Specify the full learning cycle

Define the investigation, instrument, experience, learning-procedure, branch/replay and assessment/retention contracts. Show their state transitions, data identities, ownership and failure outcomes. Use existing representations when adequate; proposed types/signatures can live in the design document.

Walk a complete example: encounter a limitation, choose an investigation, acquire or reject a method, use retained bytes in another setting, observe a scope failure, propose a revision to the method or learning procedure, assess it independently, and retain or reject the revision. Explain what the system chooses without a new human-written controller between steps. Distinguish task-solving methods from procedures that select how to learn.

Keep replayed observations, predictions and new execution distinct. State when a changed policy can be evaluated from the corpus and when its branch becomes unsupported. Preserve visibility, artifact and dependency versions; a shared task ID is insufficient. A policy may not revise its own evaluation authority or claim that unseen outcomes are facts. Do not add a world model or replay optimization campaign in this batch.

### B3. Check feasibility and choose the next empirical question

Use existing code and small runnable probes to test the architecture's risky assumptions: a policy substitution changes actual admitted/executed behavior, pending work survives context/process loss, both domain contracts are usable, and replay accepts a supported continuation while refusing a genuinely unsupported alternative. Label a hand-authored substituted policy as an engineering control, not autonomous improvement. Do not add unused production classes or a second runtime to illustrate pseudocode.

Analyze the supplied corpus and Phase A diagnostics for supported replay coverage and the remaining bottleneck. Separate delivery/format, executable validity, development usefulness, retention and transfer. Rank at most three hypotheses. Select one next experiment, with contrasting predictions, controls, honest cost/unknown handling, a finite resource envelope and a stopping rule that accepts an informative negative. Do not use protected outcomes to tune a future method or claim that zero acquisition measures the benefit of its subsequent use.

### B4. Deliver an implementation-ready consolidation package

Write `docs/design/STAGE-09-ARCHITECTURE.md` containing the selected semantics, alternatives, public usage sketch, module ownership, keep/change/remove/migrate table and next experiment. Write `reports/STAGE-09-FEASIBILITY.md` with actual checks and limitations. Include a sequenced migration plan with owned paths, dependencies, state/receipt preservation, legacy reproduction and integrated gates. Explicitly mark which larger migration is proposed rather than implemented.

Update the maintained roadmap: stage 8 engineering closeout at its actual scope; stage 9 active with its first design package delivered; learning advantage and final implementation remain unproven/uncompleted. Do not mark all of stage 8 done because one mechanism now runs. Do not remain trapped in stage 8 because every possible learning experiment has not been exhausted.

## Workflow and delivery

Maintain A1–A3 and B1–B4 in `reports/PLAN.md`. Use capable parallel specialists where work is independent. Give each exact requirements, skills to load, owned paths, baseline, worktree, database ownership and acceptance commands. No specialist writes the coordinator's integration tree. Workers may read broadly but should edit only their assigned paths. The coordinator alone merges serially and resolves shared contract changes. Your model choices are unrestricted by the external reviewer's Luna preference.

Useful roles are contract/execution, evidence/failure analysis and architecture alternatives, followed by an independent integrated review. Phase B grounding may be prepared in parallel, but finalize its recommendation from Phase A's fixed source and findings. Do not duplicate the same audit across several agents or spawn a replacement writer merely because a stream is quiet; inspect status, branch and process ownership first.

An independent reviewer must try the public command and an independently constructed valid response, inspect both domain paths, and check that the proposed architecture has actual owners rather than disconnected helpers. Give it requirements and source before your verdict. Review changes to tests against the original behavior contract. Jev may challenge structured claims or prioritization; its score cannot replace running the feature or inspecting the evidence. If a local skill is missing, follow these explicit requirements without pretending the skill ran.

Complete meaningful integrated slices, communicate during long tests, and make additive commits with author and committer `Nightjar <nightjar@authors.invalid>`. Use `origin` without committing credentials or private endpoint/remote details. Preserve original evidence and other owners' databases/worktrees. Clean up your disposable resources after their evidence is exported; retain a required receipt anchor with its reason recorded. Never use broad database-prefix deletion or reset an anchor to rerun a test.

Push `codex/implementation-stage-08-close-stage-09-start`, verify remote equality, and return the tip, stage 8 outcome, stage 9 selected design, exact checks, unresolved limits and the proposed next batch. Do not stop after A1, after lane handbacks, or because live authority is absent. Deliver both phases; no positive scientific result is required.
