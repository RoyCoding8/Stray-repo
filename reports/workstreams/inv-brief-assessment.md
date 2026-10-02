# Brief: assessment + workflow (surveyor ses_f437b5fe2ffeVrWFTSgrWa7AOi)

Assessment reviewed `84d2094` on 2026-09-19.
Accepted: progress over bdf12d5 in child identities, costs, inference, construction, separated execution, fresh use.
Independent check: 15 local tests in 1.17s. C3 corpus of 72 records with zero problems accepted at that scope.
Not accepted: full C1-C5 closure, claimed C4 comparison completion, model capability attribution for failure.

Findings:
- IR-01: construction prompt without executable contract, stale seen packet (`experiments/ad01/construct.py`, `trajectory.py`).
- IR-02: C3 bypass of broker learner path, unequal I/R lists, authored wrappers.
- IR-03: query allowance reallocation after diagnostic spend (`trajectory.py` lines 284-333).
- IR-04: 11 pairs not 12, world 0 only, no retained method, no use phase.
- IR-05: EC02 lineage 2 repair feedback duplicated, raw responses unexported.

Workflow: coordinator alone writes `codex/implementation-investigation-01`.
Specialists get unique branch plus separate worktree from recorded base.
Delegations name worktree, owned paths, requirement IDs, skills, design sections.
Shared files, locks, integration belong to coordinator.
Merge one task at a time in dependency order, rerun checks on merged revision.
Coordinator keeps `reports/PLAN.md`. Specialists use `reports/workstreams/<task-id>.md`.

Limits: no candidate code in trusted host process. No silent fallback. No mock as verified gate.
No force push, no history rewrite, no overwrite of another owner branch.
No fixture execution relabeled as live. No authored answers on solver path.
No secrets in Git.
