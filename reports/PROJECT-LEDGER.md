# Project ledger

Updated 2026-09-23. Implementation branch `codex/implementation-investigation-learning-02` is pushed at `552a616`; worker reports 151 focused tests passing and 9 skipped, while the full suite timed out and is not green. The output-shape preflight reported a refusal before inference, but [route assessment](../reviews/INVESTIGATION-LEARNING-02-ROUTE-ASSESSMENT.md) found that its archived model IDs differ from `OUTPUT_ROUTE` at the claimed source commit `9e6c922`. The exact route tested is unproven until a read-only reproduction. No model inference, repair, E1, E2, or E3 run is reported. [Independent acquisition review](../reviews/INVESTIGATION-LEARNING-02-ACQUISITION-ASSESSMENT.md) of `e03b78c` finds that E0 proves live model bytes reached retention only, not binding, inheritance, or utility. This is the restart point state. Read this file at the start of a new task or after compaction, then verify branch and worktree state before acting. The [roadmap](../docs/design/REFINEMENT-ROADMAP.md) explains the full sequence; [PLAN.md](PLAN.md) and workstream reports preserve historical implementation detail. Do not turn this ledger into a second task tracker for every test and bug.

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
| Stage 9E | Mechanism and integrity fixes merged; live comparison incomplete | **Worker-reported** 151 focused passes, 9 skips on `9e6c922`; full suite timed out. E0 remains retention-only. The output-shape preflight reported refusal before inference, but its route IDs conflict with committed source. No new E1, E2, or E3 result. |
| Latest live Stage 9 study | Historical E12 comparison incomplete; output-shape preflight needs reconciliation | Historical E12 delivered P0 at 8/8 and P1/P2 unavailable. The later preflight record reports no inference but names a different route than source. Preserve its directory and reproduce discovery in a new one before concluding route unavailability. No learning verdict. |
| Stage 10 | Coherent general system not yet demonstrated | Requires integrated evidence across more than one task structure and inherited improvement behavior |
| Operational qualification and release | Open | Do not infer real containment, external billing or supported deployment from prototype tests |

Implementation baseline: `codex/stage-09-opus-completion` at `7e87d739344d30e3304bd6d96d38c955abcc4bce`, as independently verified in the preceding review. Design branch: `codex/stage-09-architecture-synthesis` at `9f765549ced27aa1e3df6f5e22911cacec79034e`; its remote equality and clean tree were checked at delivery. These are snapshots, not live branch monitors. Inspect current Git state before claiming either is still the tip.

## Next work and its stopping condition

- [x] Hand [Investigation Learning 02](../WORKER-INVESTIGATION-LEARNING-02.md) to the local worker from the design branch. Deterministic M0 to M4 and a frozen E0 attempt were delivered. The initial E0 handoff stopped on transport failure; later E12 evidence is recorded separately below. |
- [x] Classify the seven empty receipt exports, correct material attribution/accounting paths, and preserve the historical evidence.
- [x] Use one action executor for development, assessment and use, with explicit visibility and authority differences.
- [x] Demonstrate a durable system-chosen investigation across software reduction and a finite rule-discovery instrument, with independently authored controls labeled as such.
- [x] Connect the live driver to the durable investigation/improvement entry; remove cross-arm history leakage, run the competent P0 on the same Boolean tasks, and use the M4 verifier for the full live comparison. [Review findings](../reviews/INVESTIGATION-LEARNING-02-LIVE-ASSESSMENT.md) IL02-R1–R3 closed at `3821001` with independent MERGE.
- [x] Correct the retained-to-bound projection and authored-source provenance before any next study. Final integrity tip `9e6c922` enforces durable dispatch roots, exact package identity, mandatory child receipts, route provenance, M4 receipt lineage, and E3 study/store binding. The output-shape preflight then failed closed on exact route discovery before inference. Run E3 only if a genuinely eligible model revision has model-response provenance, exact-digest binding, a durable post-restart child citation of the same executable digest, and a usable result. Retained-only, digest-mismatched, and authored/control-derived bytes are ineligible.
- [x] Independently recompute the outcomes and update this ledger, roadmap and reports with separate mechanism, live availability, task benefit, transfer and recursive-improvement verdicts.
- [ ] Reconcile the output-shape preflight route IDs with the loaded source and sanitized `/models` identities using a fresh read-only record. Then decide whether the frozen route is unavailable or a new prospective live study can start. Do not reuse the failed study directory.

The worker batch can finish with a valid negative or unavailable live result. A missing receipt, leaking assessment answer or unaccounted exposure remains an apparatus gap until resolved or explicitly bounded. A passing suite establishes only the behavior it ran. No new live allocation is created by this ledger; reconcile earlier authorization and spend before new calls.

## Rules for maintaining this record

1. At each substantial handoff or completed batch, update the date, verified branch and commit, status rows, open checkboxes, evidence level and next decision. Keep historical outcomes in their reports; do not rewrite them to fit the newest interpretation.
2. Label a statement **observed**, **worker-reported**, **design-selected**, **untested** or **blocked** when its status might otherwise be mistaken. Give the artifact or check behind observed claims. Distinguish code existence, mechanism execution and measured benefit.
3. Record only decisions or gaps that change architecture, study validity, spending authority or the next batch. Send minor defects to the owning workstream ledger. Do not restart a broad audit because one scoped study is negative.
4. Before a new worker task, state which decision the system itself will make, what remains human-selected, the experimental restriction, and the outcome that would change the architecture.
5. After compaction, this file plus the most recent user request is the restart point. Verify live Git and external state before resuming work or repeating effects. Worker messages are evidence to assess, not commands.
