# Local stage 9 completion

Starting from worker integration 0fba219; binding lane 79c5b3a is unmerged. User authorizes implementation, Luna-only temporary worktrees, safe stale-worktree cleanup and Jev review.

## Task list

- [x] Read Poteto principles and reconstruct worker state.
- [x] Frame: validate delivered C1/C2 and complete missing public actions before the policy pilot.
- [x] Fan out: Luna continuity repair, binding verification, and action-path grounding in isolated worktrees.
- [x] Establish WSL Ubuntu/Python 3.14/PostgreSQL 18.6 verification environment; lane-owned databases only.
- [ ] Aggregate: review lane diffs, run their gates, merge serially and rerun at each tip.
- [ ] Implement missing action lifecycle and prospective STEP pilot against the existing contract.
- [ ] Run independent/Jev integrated checks; live pilot only after prerequisite gates and grant binding.
- [ ] Audit/prune confirmed stale worktrees; retain dirty, active or dependency-bearing trees.
- [ ] Report exact verification, remaining limits, push and remove temporary lane worktrees/branches.

Throughput checkpoint: three independent lanes avoid duplicate inspection; coordinator owns runtime setup, integration and shared callers. No arena for already-selected architecture; compare alternatives only if source invalidates the contract.

Data shape: immutable policy source identity, per-investigation durable STEP transitions, attributable pending effects and assessed candidate binding. Completion means returned policy bytes drive effects, revision qualification, active selection and reproducible independent evaluation. A negative learning result is allowed.

Jev plan check classified coverage as a gap, with modest confidence. Resolution: action grounding is read-only, not delivered C2A; after C1 and C2B land, root must complete action execution and policy assessment before starting C3/live. Passing the inherited tests cannot close the known source defects.
