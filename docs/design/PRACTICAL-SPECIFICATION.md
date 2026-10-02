# Settlement: practical specification and build sequence

2026-09-09. R7 of this isolated design pass. Read [TECHNOLOGY-DECISIONS.md](TECHNOLOGY-DECISIONS.md) for the selected stack and its primary sources. This is a target implementation specification, not implemented behavior. It does not authorize edits to the concurrent work or any live effects. Requirement identifiers below are for builder and reviewer traceability.

## 1. What the builder is building

Build a durable investigation system whose temporary workers can develop, evaluate, and retain executable methods and representations. The trusted application interprets versioned compositions and mediates effects. Learned code runs in isolated workers. Existing methods, context policies, team arrangements, task generators, and learning policies can become candidates under the same versioned trial machinery.

Do not start by implementing a fixed cast of personas. The first complete slice must perform work, preserve continuity, acquire a reusable behavior through development, and test its use on unseen tasks. Autonomous agenda formation and more extensive collective organization extend that slice.

The interfaces and protocols below are normative for the selected design. Concrete filenames and class hierarchies are not prescribed. Keep the semantic modules deep: callers should not reconstruct authorization, budget conservation, or evidence invalidation from low-level database operations.

## 2. Configuration and boot contract

**BOOT-1.** Startup requires a versioned charter and authority grant, database and artifact-store configuration, an admitted base execution image, gateway configuration, and finite resource envelopes. Secrets belong to trusted services. Candidate input contains references, not credentials.

**BOOT-2.** Resource configuration includes consumable quotas, concurrent occupancy limits, per-operation limits, attempt deadlines, scratch/output bounds, and protected capacity for supervision and recovery. Development and ordinary work receive allocations within these totals. No descendant creates a new root allocation.

**BOOT-3.** The scheduler and trial policy have named versioned parameters: exploration allocation, admission limits, decision horizons, sample selection, useful gain, allowed regressions, and error treatment. Numerical values are operational inputs. The builder must not infer them from incidental sample counts in old documents. Provide a bounded simulation profile for demonstrations; live execution remains unavailable until real grants are configured.

**BOOT-4.** Startup validates database migrations, available retained artifacts, sandbox runtime/profile, gateway contract, and trusted interpreter versions needed by unfinished workflows. Distinguish configured, reachable, authenticated, and successfully exercised dependencies. A failed dependency narrows available operations; model unavailability does not disable operator inspection or mechanical recovery.

**BOOT-5.** On restart, recover domain state and reconcile active operations before resuming affected work. A registry of unfinished operations, ownership generations, and execution versions is authoritative; process memory and a model-written summary are not.

## 3. Shared command and result contract

Each command carries a request identity, expected subject revision where relevant, a bounded payload, and a deadline. The trusted caller context supplies authenticated identity and authority; payload fields cannot grant either.

The result is one of: applied, already applied with the original result, accepted for asynchronous work, stale revision, unauthorized, insufficient resources, incompatible version, missing evidence, invalid input, or unavailable dependency. An execution outcome additionally distinguishes observed success/failure from unknown external outcome.

Reusing a request identity with a different payload is an error. A command journal binds identity to a payload digest and durable result. Duplicate messages cannot create additional commitments or spend. The journal and semantic update commit together.

**IF-1. Stewardship:** admit/amend/withdraw commitment; subdivide allocation; reserve/settle resources; change externally authorized policy; admit/quarantine release. Returns versioned decisions with reasons and obligations.

**IF-2. Investigations:** propose/revise objective; acquire work; submit evidence; install a continuation; complete attempt; assess/commit fulfillment; suspend/resume. Completion checks the current revision and authority, not just the existence of a final answer.

**IF-3. Evidence:** register observation; propose claim; admit warrant; register opposition or retraction; inspect current support; build an access-scoped retrieval view. Interpretive material cannot impersonate an authenticated observation receipt.

**IF-4. Capabilities:** publish candidate manifest; inspect version and dependencies; validate composition; select a released composition for a declared task scope. Selection returns the exact versions and applicable limitations.

**IF-5. Execution:** prepare operation; ensure its authorized dispatch; inspect outcome; request cancellation; reconcile receipt. Ensuring an operation twice refers to the same operation rather than two effects.

**IF-6. Evaluation:** admit protocol; obtain a scoped assignment; execute candidate/reference checks; submit authenticated results; summarize the predefined comparison. Evaluation is an actual invocation under an evaluator profile, not an arbitrary record insertion.

**IF-7. Development:** register opportunity and change hypothesis; allocate a distinguishing investigation; propose a candidate; interpret a trial; propose disposition or transfer. Development can propose its successor; it cannot manufacture a release receipt.

## 4. Minimum durable data model

These are semantic table groups. Foreign keys, unique keys, check constraints, and transition logic must enforce the named distinctions; a single JSON payload with convention-only state does not satisfy them.

| Group | Required information and constraints |
|---|---|
| Control and grants | Current admission epoch, authority version, evidence epoch, release epoch, grant scope and provenance. Only trusted control writes these. |
| Commands, journal, outbox | Request identity and payload digest; committed result; ordered domain events; dispatch intent and deterministic workflow identity. |
| Investigations and revisions | Continuing identity, revision, origin/sponsor, objective, scope, obligation structure, commitment disposition, amendment history. |
| Attempts and continuations | Investigation revision, ownership generation, exact composition/model/environment, lifecycle, deadline, continuation and context references. |
| Allocations and reservations | Resource domain/epoch, parent allocation, available/consumed/reserved amounts, occupancy, operation attribution, uncertain exposure. |
| Operations and receipts | Operation identity, authorized payload digest, dispatch state, launcher/provider identity, receipt provenance, reconciliation and cancellation state. |
| Artifact versions | Immutable bytes digest, manifest, interpretation format/version, size, dependencies, availability, protection and retention state. |
| Claims and derivations | Immutable proposition/scope, alternative derivations, grouped jointly required premises, procedure, assumptions, result and invalidations. |
| Capability versions and releases | Invocation/effect/resource contract, artifact dependencies, applicability evidence, selection scope, disposition and fallback. |
| Trials, assignments and results | Frozen protocol, candidate/reference identity, independent task groups, actual invocations, blinded assignments, outcomes and exposure history. |
| Frontier and context views | Opportunities and tested/hypothesized relations; source revisions and transformations for constructed contexts. Both remain revisable. |

Use exact integer units for discrete quotas and explicitly scaled monetary units; do not enforce ceilings using binary floating-point arithmetic. Foreign keys to immutable versions must never target a mutable default alias.

## 5. Authoritative transition protocol

**TX-1.** For this single-host design, serialize consequential domain transitions through one PostgreSQL control-row lock inside a short transaction. This gives admission, revocation, and accounting an explicit total order. External work remains concurrent. Expensive inference, execution, retrieval, and proof checking occur outside the lock.

This deliberately trades metadata throughput for a straightforward correctness boundary. Measure transaction latency and queueing before replacing it with finer-grained locks. That replacement must preserve the same invariants and is not a silent optimization.

**TX-2.** A transition checks command idempotency, current subject revision, issued authority, relevant evidence/release epochs, ownership, resource availability, and legal state change; it then records the update, journal events, and any outbox intent before commit. Retry a serialization/deadlock failure as a whole transaction with the same command identity. Bound retries by the request deadline.

**TX-3.** Assign the domain event epoch by incrementing the locked control row; use an ordinal within a transition for multiple events. Do not treat an independently allocated sequence number as commit order: a later-numbered transaction can otherwise become visible before an earlier transaction commits, causing a cursor-based UI to miss events.

**TX-4.** Check expensive support outside the transition against a recorded evidence snapshot, then validate its evidence epoch at admission. Any relevant uncertainty causes revalidation; the initial conservative rule invalidates the cache on every registered evidence change that can alter admissibility. New derivations may be computed outside the lock; their admission checks exact inputs and current assumptions. No model call is made while holding the lock.

**TX-5.** The dispatcher scans the durable outbox, starts the named DBOS workflow idempotently, then records delivery. A crash at any point leaves either an undelivered intent or a harmless duplicate. A workflow's domain mutation has its own command identity, covering a crash after domain commit but before workflow checkpoint.

**TX-6.** Fulfillment checks current completion authority/generation, unfulfilled status, matching investigation revision, and current obligations in this same transition. A second terminal fulfillment for that revision is refused. Other workers can still submit attributable observations.

## 6. Effect lifecycle and reconciliation

**EFF-1. Prepare.** Validate the operation and its concrete effects, reserve its bounded exposure, bind it to the attempt and authority, and commit an immutable intent. A descriptive label supplied by a model is not effect classification. The initial effect vocabulary consists of model inference, sandbox execution, artifact input/output, approved observation adapters, and domain commands.

**EFF-2. Dispatch admission.** The broker atomically advances a prepared operation to dispatching under the current grant and owner generation. Only that admitted dispatcher may issue the operation. `dispatching` means it may have been sent; it is recorded before sending. If the broker then disappears, recovery must not infer that no effect occurred.

**EFF-3. Execute.** No database transaction remains open during an external call. Bounded workers receive no gateway credential or database connection. All their requests arrive through a launcher-bound channel and are validated independently. Protocol framing has explicit length and output limits; untrusted serialized input is parsed as typed data, never loaded as executable host objects.

**EFF-4. Observe.** Authenticate and bind the result to the actual issued operation. Store a durable receipt and settle its reservation once. A duplicate receipt with the same content is harmless; conflicting receipts are recorded for reconciliation rather than silently replacing one another.

**EFF-5. Lost response.** Retain exposure and mark the operation unresolved. Repeating a broker request returns that state. Retry an actual external effect only when its adapter contract provides suitable idempotency or conclusive reconciliation. A negative status query is insufficient if an older dispatcher can still send or the provider can still accept delayed work. Reconcile the old dispatcher and provider semantics together.

**EFF-6. Cancellation.** Separate cancellation requested, local worker stopped, and external cancellation confirmed. Cancelling an attempt prevents new work but does not release uncertain charges or undo past effects. Record late receipts even after cancellation, using the trusted reconciliation path.

**EFF-7. Local execution.** Use an operation-derived container identity and declared runtime/profile. Recovery inspects actual launcher state before attaching, stopping, or considering a replacement. It must not launch a second container under a fresh random identity merely because the first response was lost. Account for processes still running after a worker lease expires.

The launcher installs the hard execution deadline in host supervision outside the model worker and broker process, and accounts for termination grace and runtime overhead in the admitted bound. Killing the broker must not remove the worker's stop mechanism. CPU rate limits alone do not bound total CPU consumption if a process can run forever. The actual profile must demonstrate the claimed total exposure under broker failure; otherwise only the enforceable rate/occupancy limits may be reported as hard bounds.

**EFF-8. Financial exposure.** Reserve a provider-enforceable upper bound, including possible retry costs and applicable billable dimensions. If only usage estimates are available, report an estimated budget and refuse a claim of a hard monetary ceiling. Unknown usage retains conservative exposure. A lower authorized future budget does not erase older liability.

**EFF-9. Reconciliation is work.** Give it bounded supervision capacity and an explicit next decision. An adapter that cannot establish the outcome may leave a visible unresolved liability indefinitely; the system may continue only work whose allocations and dependencies do not conflict with it.

## 7. Artifact publication and retention

**ART-1.** Worker outputs enter bounded staging outside the authoritative artifact namespace. Validate size, manifest shape, declared relative paths and content digests. Import regular files through controlled handles; reject host path traversal and unexpected links. An archive can be retained as opaque bytes; unpacking untrusted archives happens in isolation.

**ART-2.** Publish immutable content to its final location on the same filesystem with the durability operations required by the selected filesystem, then commit its availability in PostgreSQL. Never commit an available database reference before its bytes are durable. A crash before database registration can leave an orphan file; recovery may register a matching publication intent or reclaim the unreferenced file under the retention protocol.

**ART-3.** Evidence, releases, active attempts, and checkpoints can hold protection references. Retirement marks an artifact unavailable for new references under the transition lock before removal. Garbage collection checks protection and publication state again; it cannot race a new reference into a file already selected for deletion. Missing or corrupted protected bytes invalidate availability and dependent use.

**ART-4.** A model may propose a retention change but cannot bypass active preservation obligations. Store finite working sets and archives under explicit budgets. A digest is not evidence availability. Do not delete sole active evidence to make an appealing storage metric improve.

## 8. Composition and continuation protocol

**RUN-1.** Implement the R5 composition algebra as versioned typed data: sequence, conditional choice, bounded repetition, parallel alternatives, dependency join, and suspension. Each node invokes an admitted module or model operation, names expected outcome shapes, and has an enclosing attempt budget.

**RUN-2.** A continuation contains the active composition version, program position, completed node result references, unresolved operation identities, outstanding obligations, and next decision. Store observations and chosen branches before advancing. Do not reconstruct the next branch by asking a fresh model to remember what an earlier model intended.

**RUN-3.** Dynamic decomposition or a generated continuation is validated and admitted as a new revision. It inherits allocation and authority. Bounded recursion does not create a new quota. Unrecognized operations or interpreters cannot enter the trusted process as generated Python.

**RUN-4.** Version pinning preserves the program used by an attempt. It does not override quarantine or revoked authority. Subsequent dispatch and fulfillment check current eligibility; already issued effects go through EFF reconciliation. Migration records old and new continuations and their compatibility obligations.

**RUN-5.** Context construction records source versions, transformations, current constraints and retrieval limitations. Missing mandatory information leads to a smaller or staged decision. A candidate context builder cannot remove the broker's independent checks. Evaluation measures downstream outcomes and constraint preservation.

## 9. Scheduling and autonomous investigation

**AGENDA-1.** Maintain separate admitted allocations for obligations, development, and mechanical supervision. Service due recovery and reconciliation from protected capacity. Within accepted work, use explicit deadlines and fair rotation among eligible investigations; admit no guarantee of meeting a deadline solely from priority ordering.

**AGENDA-2.** Within the feasible development allocation, the seed policy rotates among bottleneck investigation, transfer, instrument/evaluator gaps, and speculative charter-compatible questions. Choose eligible proposals with finite initial bounds; use a stable fair order when evidence cannot distinguish them. This is a declared initial policy that can later be compared with another policy, not a theoretically optimal scheduler.

**AGENDA-3.** Each frontier proposal names its question or change hypothesis, known basis, desired observation, resource cap, and next continuation/stop decision. A renewal names what the preceding attempt changed in the decision. Age, novelty rhetoric, and message count are insufficient reasons for additional allocation.

**AGENDA-4.** New events, completed operations, explicit user messages, and due decision deadlines wake the relevant workflow. A periodic scan repairs missed wakeups. The heartbeat does no model inference merely to show activity. No eligible feasible work means idle or explicit suspension.

**AGENDA-5.** Start with single-worker execution. A team proposal states a benefit such as separable work, independent attempts, or distinct tools. For independence claims, track shared source/result exposure and commit initial results before revealing peers' conclusions. Different names or model aliases alone do not establish independence.

## 10. Candidate, trial, and release protocol

**LEARN-1.** A candidate record binds reference version, proposed change, causal hypothesis, scope, dependencies, trial protocol, and allocated development budget. A generated program is untrusted until run through the admitted execution profile; publication is not release.

**LEARN-2.** Freeze an explicit task selection and evaluation protocol before scoring. Separate development examples, visible regression tasks, and protected evaluation assignments. Store hidden answers outside candidate access. All task generators and evaluators have versions and access policies; a candidate cannot write its own successful receipt.

**LEARN-3.** Execute candidate and reference under matched information and resource policies. Record actual differences in model/environment conditions. Count candidate construction, failed trials, coordination, retrieval, evaluation, and selection toward development expenditure. Record subsequent use cost separately and report amortization over the declared horizon.

**LEARN-4.** Every assigned case has an outcome. The frozen protocol defines treatment of timeouts, invalid outputs, unavailable evaluators and infrastructure failures. Do not selectively discard unfavorable runs. Repeated instances from the same source problem belong to the same task group when independence is needed.

**LEARN-5.** The comparison can conclude observed gain on a declared finite panel, inferential gain under stated sampling assumptions, regression, or inconclusive. These labels are not interchangeable. A finite-panel claim does not automatically establish an expected advantage on all future tasks.

**LEARN-6.** Before inferential promotion, the protocol supplies an executable statistical procedure, estimand, task grouping, stopping rule, error budget, useful-gain threshold and protected regression bounds. Validate the procedure against simulated nulls and known effects, including the actual adaptive selection policy. No library-provided confidence interval is accepted merely because it produces two numbers.

For the first build, finite-panel comparisons are sufficient to exercise the full pipeline and admit a visibly limited experimental release. Broad competence labels remain unavailable until the stronger protocol is supplied. This is an explicit evidence limit, not a builder's permission to invent statistical certainty.

**LEARN-7.** A release transaction binds exact candidate versions, evidence, applicable scope, disposition, fallback, selection policy and invalidation conditions. A candidate need not beat every incumbent everywhere. Preserve incumbents outside supported scope, and test the router's actual choices. A quarantine takes effect for pinned attempts under RUN-4.

**LEARN-8.** Learning-policy changes are evaluated over complete bounded learning trajectories from equivalent initial information and capabilities. Do not credit a learner for generating more candidates without downstream gains. Candidate evaluation access is accounted for; repeated holdout feedback can leak information even if raw answers stay hidden.

**LEARN-9.** Retain a failed hypothesis when it changes a future decision or meets a preservation obligation. Do not turn every incident into a new active abstraction. Consolidation proposes reuse or retirement with costs and affected dependencies; it never rewrites the historical result to look successful.

## 11. First experiment: does durable executable competence help?

Use bounded diagnostic tasks with checkable outcomes. A suitable first family is software failure reduction; a later transfer family is reduction of finite mathematical counterexamples under independently defined predicates. The particular task and generator packages are experiment artifacts, not permanent domain restrictions.

Compare these arms under the same starting model, tools, task exposure, and total development envelope:

| Arm | What can persist between tasks | Purpose |
|---|---|---|
| A | Strong fixed baseline instructions and declared ordinary task history; no new retained method library | Establish the contribution of development beyond ordinary inference and recall. |
| B | Retrieved textual lessons and method descriptions | Test the strongest relevant document-memory baseline. |
| C | Invocable versioned methods/compositions, with the same permitted experience | Test the selected carrier of competence. |

All arms may construct tools inside an individual task. Do not cripple the baseline's within-task reasoning or tool use. Between-task retention is the experimental difference; its construction and retrieval costs remain in the total budget. Include a whole-agent retention arm later when directly testing E1's compositional-versus-whole-system claim.

The sequence is development examples, fresh-worker continuation, independent same-family tasks, and a separately declared cross-family transfer test. Split by underlying problem source or structure rather than near-duplicate examples. Record model drift and randomization conditions. Freeze the final evaluation access policy before development exposes results.

A successful limited demonstration shows that C retains and invokes a method after the original worker is gone, satisfies the task predicate, and improves a declared outcome on the independent panel under comparable resources. The cross-family claim also requires the new interpretation and witness predicate to be valid. A reducer's local irreducibility is not global minimality.

If C produces more packages but no use benefit over B, the central carrier hypothesis is unsupported at this scope. If it helps only after receiving more tools, hidden task information, or uncounted compute, rerun the fair comparison. If it helps only on previously seen examples, report reuse or memorization, not general transfer.

This experiment does not establish that the method is novel to science or absent from the base model's training. It tests whether this persistent architecture makes retained behavior more useful across fresh invocations. Representation invention, autonomous curricula and learner revision each require their corresponding additional experiments.

## 12. Operator contract

**UI-1.** The overview shows accepted obligations, running/suspended attempts, next decisions, capacity, and unresolved operations. Its status comes from durable records even when model endpoints fail.

**UI-2.** An investigation view shows its conditional dependency diagram, attempted branches, actual operations, evidence, selected versions, and why work is waiting. A capability view shows invocation contract, lineage, scope, trials, counterexamples and release disposition.

**UI-3.** A learning view places candidate and reference outcomes beside resource expenditure, task exposure, exclusions and uncertainty. Separate demonstrated gains, experimental alternatives and unsupported hypotheses. Do not use growing artifact counts as the primary progress chart.

**UI-4.** Commands are versioned and idempotent: admit, pause, resume, cancel, quarantine, amend allocation and inspect reconciliation. Display the exact accepted/refused outcome and pending effects. A cancel button cannot claim an external action was undone.

**UI-5.** A control request needs authenticated operator context and request protection. Bind the initial interface to the operator's local/tunneled access; remote exposure is a deployment change. Generated text and artifacts remain inert in the management origin. A UI refresh cannot activate generated code.

## 13. Checkpoint and restoration protocol

**REC-1.** Stop new admissions, establish a domain barrier, and persist every known operation state. Running work must reach a recorded suspension or remain explicitly represented as in flight. Complete domain-to-DBOS outbox reconciliation, stop old executors from further checkpoint mutation, and then create a consistent database backup plus a manifest of all protected artifact bytes.

**REC-2.** Verify and copy that recovery set to the designated backup destination. Record its recovery epoch and completeness. An artifact upload in progress cannot appear as available in the checkpoint. Backups are tested by restoration, not by successful file copying alone.

**REC-3.** Restore into a fenced environment with external writes disabled. Validate artifact closure, domain journal, DBOS version availability and old operation identities. Establish new ownership generations. Discover or fence old launchers before resuming effects; an old dispatcher may outlive the lost connection.

**REC-4.** Reconcile external actions that may have happened after the backup. If the restored system cannot establish their state, record the uncertainty and obtain the required resolution before conflicting actions resume. Never replay the operation journal as external commands. RPO/RTO are measured deployment properties, not architectural constants.

## 14. Sequenced build and acceptance gates

Each slice includes an operator-visible path and relevant real integration checks. This is a sequence for implementing the full design, not permission to label an earlier slice complete architecture.

| Slice | Deliverable | Acceptance gate |
|---|---|---|
| S0 Contracts and compatibility | Lock manifest, seeded grants, database schema/constraints, admitted runtime image and gateway probe | Explicit failure for unavailable inference or incompatible sandbox; no unrestricted fallback. |
| S1 Durable bounded work | One investigation, one worker, transition protocol, operation broker, resources, UI and recovery | Kill/restart at every effect boundary; preserve uncertain exposure and refuse duplicate fulfillment/spend. |
| S2 Evidence and continuity | Grouped derivations, invalidation, artifact publication, context views, fresh-worker resumption | Retract one support route, preserve a valid alternative, detect missing protected bytes, and resume with pending effects intact. |
| S3 Executable learning | Candidate packages, frozen trial, comparison, limited release and actual reuse | Run the first A/B/C experiment; a fresh worker invokes the retained method on independent tasks. An inconclusive result stays inconclusive. |
| S4 Representation and transfer | Operational language package, translation, interpretation and cross-family evaluation | Check soundness and coverage separately; reject vacuous/non-output reductions and invalid witness transfer. |
| S5 Autonomous agenda and teams | Frontier policy, bounded exploration, adaptive worker compositions | No user task needed to originate an allocated investigation; no unbounded renewal; compare selected teams with a strong single worker. |
| S6 Learner revision and consolidation | Whole-trajectory comparison, protected evaluator revision, retirement and migration | A self-modified judge cannot certify itself; quarantine affects pinned work; old capabilities and evidence remain correctly scoped. |
| S7 Operational qualification | Restorable checkpoints, exposure reconciliation, host capacity profiles, UI completeness | Restore on a clean runtime, fence old execution, and demonstrate the declared failure model under real components. |

## 15. Required adversarial checks

Map the 24 conceptual scenarios and the R5 representation cases to concrete integration tests. At minimum include:

- Concurrent workers reserve the same last units; only feasible reservations commit.
- Broker dies before send, after send, after receipt, and after domain commit before workflow checkpoint.
- A stale worker submits a valid-looking completion after its lease expires.
- An event cursor advances while an earlier transaction is still trying to commit; no committed event is permanently skipped.
- A support retraction races release or fulfillment; stale admissibility cannot win after the retraction's admission order.
- A candidate bypasses the pipe, reaches for credentials, exceeds scratch/output quotas, or requires an unsupported runtime operation.
- An artifact publication or retirement crashes while another command tries to reference its bytes.
- An evaluator is replaced with an always-pass implementation, or hidden answers enter ordinary retrieval.
- A budget reduction, quarantine, or cancellation occurs while an operation is already dispatched.
- The first new release improves one family but damages another, and the router selects the wrong version.
- A restored database predates an external effect; the system enters reconciliation instead of repeating it.

Use real subsystem boundaries for these checks. A property test against a simplified model helps find sequences; it does not verify that the real executor enforces the model.

## 16. Completion criteria and remaining empirical work

The implementation is structurally conforming when the specified transitions, interfaces, scoped evidence behavior, isolation, recovery, and operator contracts pass their acceptance gates under the declared failure model. It demonstrates limited learning only when the corresponding experiment supports that narrower claim. Broad autonomous improvement remains subject to E1-E8.

The builder must report separately: static/unit checks, real database tests, real sandbox tests, live gateway tests, restoration tests, finite-panel learning results, and any inferential claims. Missing host access or insufficient experimental resources produce an explicit unverified gate, not a fabricated pass.

This specification completes the design handoff through R7. Exact deployment credentials and budgets are runtime inputs; package compatibility, statistical calibration and empirical learning remain work to execute and measure. No code or experiments have been implemented by this document.
