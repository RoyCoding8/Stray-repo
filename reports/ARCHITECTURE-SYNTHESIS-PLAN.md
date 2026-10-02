# Architecture synthesis worklist

Design owner: Codex. Implementation baseline: `7e87d739344d30e3304bd6d96d38c955abcc4bce`.

The assignment is conceptual synthesis, formalization, mechanism selection and a reviewable implementation brief. It does not run another live study or implement the proposed runtime.

- [x] Verify relevant primary research, including the user's RSI survey.
- [x] Trace the implemented decision, execution, revision, assessment and continuation paths.
- [x] Separate established behavior, scoped evidence, open defects and untested learning hypotheses.
- [x] Compare structurally different architectures and select one with reversal conditions.
- [x] Define the state model, revision semantics, memory, agenda, replay and evaluation contracts.
- [x] Specify an informative, bounded next experiment and worker assignment.
- [x] Challenge the design with Jev; resolve concrete concerns without chasing scores.
- [x] Refresh the roadmap and check references, JSON syntax, whitespace and documentation-only scope.

Delivery branch: `codex/stage-09-architecture-synthesis`. The delivery commit and verified remote equality are reported in the final handback; this document does not predict a push result.

Standing constraints: general autonomous discovery across domains; fixed model weights for this phase; keep valid execution/evidence/authority guarantees; no claim of universal optimality or demonstrated recursive improvement; preserve historical evidence; prioritize architecture over unrelated bug sweeps.

## Delivered design

- [Research review](../docs/design/RSI-RESEARCH-2026-09-22.md): seven primary sources, read extent and limitations disclosed.
- [Architecture](../docs/design/ARCHITECTURE-SYNTHESIS-2026-09-22.md): selected alternative, formal state/transitions, common action semantics, agenda, memory, replay, inheritance, technology decisions and E0–E3 studies.
- [Worker assignment](../docs/HISTORY.md#worker-investigation-learning-02): fresh-chat M0–M6 sequence, isolation/merge discipline, independent checks, Jev use, authority reconciliation and bounded stopping rules.
- [Roadmap](../docs/design/REFINEMENT-ROADMAP.md): Stage 9A–9D design complete, 9E implementation/qualification open, Stage 10 integration still ahead. Historical assessments are labeled rather than rewritten as new evidence.

## Jev review dispositions

The [initial request](jev/s09-synthesis-plan-request.json) and [response](jev/s09-synthesis-plan-response.json) favored the persistent-investigation alternative and ranked action semantics first among missing contracts, with private-state activation next. Added the common-effect table and explicit quiescent activation with private-state reset. These are design responses, not tested implementations.

The [final request](jev/s09-synthesis-final-request.json) contains the architecture and worker draft as they stood before the last clarification. Its [response](jev/s09-synthesis-final-response.json) rated explicit shared semantics and honest closeout at 0.96 each, and matched improver evaluation at 0.84. The remaining-ambiguity choice selected recursion at 0.41 with low confidence 0.27; selection separation was 0.25 and no blocker 0.30. Treat that spread as a prompt to inspect, not a demonstrated defect.

Accepted the actionable clarity concern: the final architecture now specifies a purpose-bearing STEP view, access to frozen source, program-controlled construction inputs and a leaf constructor. It requires an independent pair of controls with identical operational behavior but different improvement behavior, traced through a restart and a descendant-producing round. Also made qualification/audit exposure retirement explicit. These additions were reviewed locally; no second Jev score is claimed for them. No aggregate-score chasing or live-study authorization occurred.

## Validation and boundaries

All relative Markdown file links in the edited/new Markdown documents resolve. The four saved Jev request/response files parse as JSON. Whitespace checks pass. The change is documentation and review evidence only; runtime source, database schema, frozen study evidence and installed dependencies are unchanged. No runtime suite was rerun for these edits, and no new discovery-model study was performed.

The source audit does not establish the cause of every empty receipt export. M0 must classify those attempts from available source evidence. Provider capability, effective learning and recursive improvement remain unproven. No new database, worktree or subagent was created for this design pass.
