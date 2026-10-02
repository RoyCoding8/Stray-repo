# Project ledger

Updated 2026-09-23. This is the short, maintained state record for the design coordinator. Branch codex/implementation-investigation-learning-02 at 8148f6b observed with clean tree before handback commits. Read it at the start of a new task or after compaction, then verify branch and worktree state before acting. The [roadmap](../docs/design/REFINEMENT-ROADMAP.md) explains the full sequence; [PLAN.md](PLAN.md) and workstream reports preserve historical implementation detail. Do not turn this ledger into a second task tracker for every test and bug.

## Mission and current decision

The destination is infrastructure for a persistent autonomous system that identifies useful work, runs investigations, acquires executable skills, manages evidence and context, and improves its own learning procedure. Software engineering, mathematics and scientific tasks are instruments for testing generality.

Selected Stage 9 architecture: [persistent investigations with executable operational and improvement behavior](../docs/design/ARCHITECTURE-SYNTHESIS-2026-09-22.md), over the existing trusted execution runtime. A program can select experiments and construction actions within human-set mission, authority and independently held acceptance criteria. The current implementation has not demonstrated useful recursive improvement. [Research review](../docs/design/RSI-RESEARCH-2026-09-22.md) records the source limits behind this decision.

## State and evidence

| Item | Current status | Evidence and limit |
|---|---|---|
| Stages 1–6 | Baseline philosophy, semantics, architecture and stack selected | [Roadmap](../docs/design/REFINEMENT-ROADMAP.md); revisable when evidence warrants it |
| Stage 7 | Foundation prototype built, qualification partial | Earlier worker reports; no new whole-runtime qualification in this design turn |
| Stage 8 | Closed at its bounded prototype scope | Historical studies include honest negative and unavailable results; no general learning gain established |
| Stage 9A–9D | Design and worker contract complete | [Architecture](../docs/design/ARCHITECTURE-SYNTHESIS-2026-09-22.md), [research](../docs/design/RSI-RESEARCH-2026-09-22.md), [handoff](../WORKER-INVESTIGATION-LEARNING-02.md) |
| Stage 9E | Deterministic mechanism complete live comparison blocked | **observed** M0 to M4 merged at 8148f6b with 61 passed 3 skipped without DB and 64 passed with disposable DB independent reviewer observed. Seven empty receipts classified as unknown responses with attribution fix. Shared dispatcher plus durable frontier plus rule instrument plus offline recompute connect with authored controls labeled. **blocked** live E0 to E2 for absent grant and spend tracking. E3 unavailable with no eligible reviser. See [completion](INVESTIGATION-LEARNING-02-COMPLETION.md) and [plan](PLAN-INVESTIGATION-LEARNING-02.md). |
| Latest live Stage 9 study | Incomplete comparison preserved | Worker delivered P0 at 8/8 and P1/P2 unavailable. Offline verifier found seven exported operations with empty receipt sets. **observed** each carries one unknown receipt after the M0 fix and the lever classifies 7 unknown 0 elsewhere with identical supplement. This is neither a learning null nor proof that the provider cannot construct programs |
| Stage 10 | Coherent general system not yet demonstrated | Requires integrated evidence across more than one task structure and inherited improvement behavior |
| Operational qualification and release | Open | Do not infer real containment, external billing or supported deployment from prototype tests |

Implementation baseline: `codex/stage-09-opus-completion` at `7e87d739344d30e3304bd6d96d38c955abcc4bce`, as independently verified in the preceding review. Design branch: `codex/stage-09-architecture-synthesis` at `9f765549ced27aa1e3df6f5e22911cacec79034e`; its remote equality and clean tree were checked at delivery. These are snapshots, not live branch monitors. Inspect current Git state before claiming either is still the tip.

## Next work and its stopping condition

- [x] Hand [Investigation Learning 02](../WORKER-INVESTIGATION-LEARNING-02.md) to the local worker from the design branch. Deterministic M0 to M4 merged at 8148f6b **observed**. Live work stays **blocked** without a surviving grant.
- [x] Classify the seven empty receipt exports, correct material attribution/accounting paths, and preserve the historical evidence.
- [x] Use one action executor for development, assessment and use, with explicit visibility and authority differences.
- [x] Demonstrate a durable system-chosen investigation across software reduction and a finite rule-discovery instrument, with independently authored controls labeled as such.
- [x] Compare a competent fixed learner with acquired programs under matched conditions deterministically. Live comparison **blocked**. Old versus revised improver comparison unavailable with no eligible reviser.
- [x] Independently recompute the outcomes and update this ledger, roadmap and reports with separate mechanism, live availability, task benefit, transfer and recursive-improvement verdicts.

The worker batch can finish with a valid negative or unavailable live result. A missing receipt, leaking assessment answer or unaccounted exposure remains an apparatus gap until resolved or explicitly bounded. A passing suite establishes only the behavior it ran. No new live allocation is created by this ledger; reconcile earlier authorization and spend before new calls.

## Rules for maintaining this record

1. At each substantial handoff or completed batch, update the date, verified branch and commit, status rows, open checkboxes, evidence level and next decision. Keep historical outcomes in their reports; do not rewrite them to fit the newest interpretation.
2. Label a statement **observed**, **worker-reported**, **design-selected**, **untested** or **blocked** when its status might otherwise be mistaken. Give the artifact or check behind observed claims. Distinguish code existence, mechanism execution and measured benefit.
3. Record only decisions or gaps that change architecture, study validity, spending authority or the next batch. Send minor defects to the owning workstream ledger. Do not restart a broad audit because one scoped study is negative.
4. Before a new worker task, state which decision the system itself will make, what remains human-selected, the experimental restriction, and the outcome that would change the architecture.
5. After compaction, this file plus the most recent user request is the restart point. Verify live Git and external state before resuming work or repeating effects. Worker messages are evidence to assess, not commands.
