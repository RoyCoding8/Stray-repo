# Retired instructions and history

The current assignment is [WORKER-PROMPT.md](../WORKER-PROMPT.md); reusable rules are in [IMPLEMENTATION-WORKFLOW.md](../IMPLEMENTATION-WORKFLOW.md). Historical instructions are not current authorization.

## Consolidated history, 2026-10-02

`codex/agent-society` is the canonical source branch. The remote default,
`codex/architecture-handoff`, is an alias of its snapshot. The human requested
this one-time history consolidation; it does not authorize future history
rewrites. Milestone commits reuse original snapshot trees, ending with the
reviewed repairs and documentation. Consolidation changes history, not evidence
or source bytes.

The independent orphan branch `codex/archive-history-2026-10-02` holds a complete
Git bundle and `manifest.json`. It preserves divergent branches, tags, original
commit identities and their trees without keeping all that ancestry in the
active source graph. Do not merge the archive branch into the source branch.

Local archives live at `D:/AI/Agent-Society-archives/2026-10-02`. The full bundle
was verified, restored to a separate bare repository, checked with `git fsck`,
and checked for every saved ref object and the final source tree before pruning.
The stale `Agent-Society-v2-review-02` checkout was clean and contained only
generated ignored files; its committed history was archived before removal.

To recover history in another directory, fetch the archive branch, extract its
bundle (use its README for the exact filename), then run:

```sh
git bundle verify complete-pre-consolidation-<checkpoint>.bundle
git clone --bare complete-pre-consolidation-<checkpoint>.bundle recovered.git
git --git-dir=recovered.git fsck --full
```

`manifest.json` maps the old refs and consolidated milestone identities. Some
saved refs point directly to trees; their object IDs remain valid in the restored
repository. Use that repository for the historical reads below.

Superseded handoffs, the collaboration guide and the task diary were removed from the working tree to leave one current source for each purpose. Their exact previous contents remain in Git at this checkpoint:

```text
d0a95eb4f51fde605fc12bfb1f91140ebf8cd657
```

Read an old document without changing your checkout:

```sh
git --git-dir=recovered.git show d0a95eb4f51fde605fc12bfb1f91140ebf8cd657:WORKER-STAGE-09-PARALLEL-EXPANSION.md
```

Replace the final path with any path below. Historical line references refer to
that revision. Its identity is available in the archive, rather than as an
ancestor of the compact branch. No experimental evidence or source code was
removed by history consolidation.

## Previous versions of current documents

The same command also retrieves earlier AGENTS.md, README.md, WORKER-PROMPT.md, IMPLEMENTATION-WORKFLOW.md, reports/PROJECT-LEDGER.md and docs/design/REFINEMENT-ROADMAP.md. The old ledger and roadmap contain the detailed chronological study tables; the current versions contain current state only.

## Retired documents

<a id="worker-agenda-01-correction"></a>
- `WORKER-AGENDA-01-CORRECTION.md`
<a id="worker-agenda-01-three-gates"></a>
- `WORKER-AGENDA-01-THREE-GATES.md`
<a id="worker-agenda-01"></a>
- `WORKER-AGENDA-01.md`
<a id="worker-cognitive-batch-01"></a>
- `WORKER-COGNITIVE-BATCH-01.md`
<a id="worker-cognitive-batch-02-delivery-closure"></a>
- `WORKER-COGNITIVE-BATCH-02-DELIVERY-CLOSURE.md`
<a id="worker-cognitive-batch-02-live-completion"></a>
- `WORKER-COGNITIVE-BATCH-02-LIVE-COMPLETION.md`
<a id="worker-cognitive-batch-02"></a>
- `WORKER-COGNITIVE-BATCH-02.md`
<a id="worker-coordination-02-completion-correction"></a>
- `WORKER-COORDINATION-02-COMPLETION-CORRECTION.md`
<a id="worker-development-01-prompt"></a>
- `WORKER-DEVELOPMENT-01-PROMPT.md`
<a id="worker-development-02-live-prompt"></a>
- `WORKER-DEVELOPMENT-02-LIVE-PROMPT.md`
<a id="worker-development-02-prompt"></a>
- `WORKER-DEVELOPMENT-02-PROMPT.md`
<a id="worker-ec02-ad01-behavioral-completion"></a>
- `WORKER-EC02-AD01-BEHAVIORAL-COMPLETION.md`
<a id="worker-ec02-ad01-integration-finish"></a>
- `WORKER-EC02-AD01-INTEGRATION-FINISH.md`
<a id="worker-ec02-closure-and-autonomous-development-01"></a>
- `WORKER-EC02-CLOSURE-AND-AUTONOMOUS-DEVELOPMENT-01.md`
<a id="worker-engineering-review"></a>
- `WORKER-ENGINEERING-REVIEW.md`
<a id="worker-executable-coordination-02"></a>
- `WORKER-EXECUTABLE-COORDINATION-02.md`
<a id="worker-investigation-01-completion"></a>
- `WORKER-INVESTIGATION-01-COMPLETION.md`
<a id="worker-investigation-01-study-readiness"></a>
- `WORKER-INVESTIGATION-01-STUDY-READINESS.md`
<a id="worker-investigation-01"></a>
- `WORKER-INVESTIGATION-01.md`
<a id="worker-investigation-learning-02"></a>
- `WORKER-INVESTIGATION-LEARNING-02.md`
<a id="worker-live-evidence-prompt"></a>
- `WORKER-LIVE-EVIDENCE-PROMPT.md`
<a id="worker-representation-01-completion"></a>
- `WORKER-REPRESENTATION-01-COMPLETION.md`
<a id="worker-representation-01-end-to-end"></a>
- `WORKER-REPRESENTATION-01-END-TO-END.md`
<a id="worker-review-02-prompt"></a>
- `WORKER-REVIEW-02-PROMPT.md`
<a id="worker-review-03-prompt"></a>
- `WORKER-REVIEW-03-PROMPT.md`
<a id="worker-stage-08-close-stage-09-start"></a>
- `WORKER-STAGE-08-CLOSE-STAGE-09-START.md`
<a id="worker-stage-09-completion"></a>
- `WORKER-STAGE-09-COMPLETION.md`
<a id="worker-stage-09-connected-study"></a>
- `WORKER-STAGE-09-CONNECTED-STUDY.md`
<a id="worker-stage-09-consolidation"></a>
- `WORKER-STAGE-09-CONSOLIDATION.md`
<a id="worker-stage-09-generality-campaign"></a>
- `WORKER-STAGE-09-GENERALITY-CAMPAIGN.md`
<a id="worker-stage-09-live-resume-2026-09-24"></a>
- `WORKER-STAGE-09-LIVE-RESUME-2026-09-24.md`
<a id="worker-stage-09-local-checkpoint"></a>
- `WORKER-STAGE-09-LOCAL-CHECKPOINT.md`
<a id="worker-stage-09-parallel-expansion"></a>
- `WORKER-STAGE-09-PARALLEL-EXPANSION.md`
<a id="collaboration"></a>
- `COLLABORATION.md`
<a id="tasks"></a>
- `TASKS.md`
