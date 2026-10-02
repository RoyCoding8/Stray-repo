# Fresh local worker: finish Stage 9 executable policy revision

This is a fresh-chat assignment for the local Opus worker. You do not need the previous worker conversation. Read the final checkpoint report before starting; it distinguishes verified work from remaining work. Do not infer completion from older handbacks or test counts.

## Start here

- Local integration checkout: `D:\AI\Agent-Society-v2-investigation-review`.
-- Checkpoint branch: `codex/stage-09-local-completion`, backed up on `origin`. Confirm the exact SHA after fetching; do not assume an older local copy includes the 76-pass integration checkpoint.
- Verify the local branch and remote tip, inspect dirty files and running work, then create `codex/stage-09-opus-completion` from the checkpoint in this same integration checkout. Avoid another permanent coordinator worktree.
- Use Windows Git for this checkout. Its worktree metadata contains Windows paths; native WSL Git does not resolve those paths correctly.
- Read `reports/local-completion/CHECKPOINT.md`, `docs/design/STAGE-09-IMPLEMENTATION-CONTRACT.md`, and `WORKER-STAGE-09-COMPLETION.md`. The latter's C0–C5 requirements remain the governing completion contract. Read the applicable repository instructions and workflow documents too.
- Preserve `evidence_inv01_live/` and all historical frozen evidence byte-for-byte. Never reset or clean another owner's worktree, branch, database, or run directory.

The objective remains a general investigator that accumulates useful experience and improves executable investigation behavior. The two current domains are bounded instruments for testing that mechanism. Do not turn this into a permanently hand-authored benchmark solver or claim general intelligence from this panel.

## What this checkpoint contributes

The local changes make selected retained methods execute their actual bytes, refuse unavailable methods without constructing replacements, and prevent failed use from refunding unknown query expenditure. Operational feedback can now create a durable revision proposal, construct an executable `STEP` policy with parent lineage, and freeze its bytes. Those candidates deliberately remain pending assessment. They are not task-method repertoire members or released policies.

Binding work verifies actual candidate bytes, exact release selection, assessment identity and repeated request consistency. Continuity and pilot work are described with final gate outcomes in the checkpoint report. Treat that report as the authority for their integration status.

**The next architectural milestone is a complete policy revision cycle.** Reaching `assessment_status=pending` is not success for this assignment. A negative live comparison is an acceptable scientific result; disconnected execution or an incomplete lifecycle is not.

## Deliver the remaining work in order

1. **Confirm the checkpoint and pin the missing integration contract.** Run the checkpoint gates, then trace the public caller to policy proposal, construction, freeze, assessment, binding and continued execution. Map each required field and transition to the existing store. Keep one driver. Separate `learning-policy`/`STEP` artifacts from task-method artifacts; share identity, authority and journaling facilities, not an evaluator that assumes both mean the same thing.
2. **Connect sealed policy assessment.** Consume frozen candidate bytes and an immutable protocol through the trusted runtime. Assess executed decisions, resulting effects, downstream task quality and full resources. An ABI dry run, a changed source digest, or a method reducer score alone cannot qualify a learning policy. Freeze the comparison rule and held-out identities before exposure. Enforce assessment retirement and prohibit protected answers from entering construction or subsequent learner feedback. Handle unavailable or rejected candidates explicitly.
3. **Connect policy binding and continuation.** Activate only a qualifying, current assessment for the exact policy bytes, protocol, evaluator and scope. Carry the investigation's explicit binding through the public command, durable state, exports and fresh-process continuation. Rejected revisions keep the incumbent. Use the existing atomic stale-update and revocation mechanisms. Add no global-newest selection or implicit method-to-policy conversion.
4. **Prove the whole public cycle in both domains.** One public command must acquire/check/retain/use a method, incorporate permitted operational feedback, revise the policy, assess it, bind or reject it, and continue after restart. Tests may provide model responses, but must not call missing lifecycle steps on behalf of production. Include a successful binding path, a rejected policy, an unavailable constructor, a disconnect, and interruption around an accepted effect. Receipt reuse must work at exhausted allowance without a second model request.
5. **Finish and run the prospective policy comparison.** Preserve the existing C3/N5 schedule and limits: four visible development episodes; P1 and P2 each get one policy candidate plus one repair; twelve matched assessment episodes; two sealed method-use tasks per episode, including structural variation. P0 uses the frozen incumbent. P1 and P2 receive identical objective, interface, construction task and allowance; permitted experience is the intended difference. All arms execute the same trusted driver. Missing arms remain missing. Freeze actual acquired bytes and effective configuration before assessment. Prove the configured HTTP adapter is on the full path before spending live calls.
6. **Run the authorized bounded live study and close the evidence.** The user authorized free-model live work under the existing cap sheet, at most 100 total model calls and no paid fallback. First inspect local and stored usage; do not replay a spent grant or invent unused authority. Pin the actual free model, effort, endpoint configuration and unused study root without recording secrets. Enforce the aggregate and per-phase ceilings in the real dispatch path. Use recorded live bytes through construction, policy execution, method execution and held-out use. Recompute exports independently without a provider or live database. An honest negative finishes the study once the mechanism and evidence are complete.

If a configured gateway or free model is genuinely unavailable, finish all independent work and report the exact failed preflight and unrun remainder. An old report saying “needs a grant” does not override the user's existing authorization. Do not manufacture success using a recording adapter in live mode.

## Workflow and verification

Parallel subagents are authorized. Use the models available and permitted in your own local worker environment; do not assume that Codex's Luna tool exists there. Use short temporary paths, exclusive file ownership, separate `s09_` databases, and one writer per worktree. You own integration. Inspect every full lane diff and merge serially with `--no-ff`, then rerun affected gates on the merged source. A stream timeout is not proof a worker is dead: check its state before replacing it or adopting its files.

Keep a task graph and a requirement-to-public-caller-to-gate map. Finish each milestone before claiming it. Continue through the full assignment rather than stopping after the first lane or after a reviewer note. Prefer existing helpers and database invariants. No second workflow engine, generic plugin layer, new memory system, or unrelated cleanup is needed.

Use context-mode for bulk searches, logs and comparisons when its tools are available. Otherwise use bounded reads and saved log summaries; do not invent tool availability or stop useful work merely because an optional context tool is absent.

For material fixes, show a failing behavioral check before the correction and a passing check afterward. Do not invert assertions merely to match new output. A fixture migration must identify the changed contract, preserve the old test's purpose, and add any missing provenance rather than weakening the runtime. Historical names such as “full deterministic cycle” do not prove that the test actually uses the public lifecycle; inspect the call path.

Two independent reviews are useful: one follows bytes and actions through the public path; the other tries authority, leakage, identity and resume failures. Give reviewers enough context to test their own candidate bytes and retain their exact commands. Ask them to challenge the integrated source, not just trust a coordinator's summary. Fix important findings; ledger unrelated minor items without letting them displace the architectural objective.

Keep one long suite run at a time. Write output and exit status to durable logs, surface progress, and wait for the process to finish. Never declare a run green from progress dots, add counts from separate runs as one suite, or call a failure environmental without a reproducer. Do not kill a valid suite because an orchestration timeout is shorter than the suite. Rerun touched gates after integration corrections; broaden only when the changes or failures justify it.

## Use Jev deliberately

Read `C:\Users\roysh\.codex\skills\jev\SKILL.md`. The evaluator is `C:\Users\roysh\.codex\skills\jev\scripts\jev.py`; it accepts a JSON request on stdin. Use it for typed decisions, not code generation or authorization.

Use four meaningful checkpoints: plan coverage, causal/evidence separation, integrated risk triage, and final claim-versus-evidence review. Supply the relevant contract plus actual source/diff or raw evidence excerpts. Ask separate questions for separate claims. A vague “is this good?” score is not useful. Save sanitized requests and responses with the report and state what you checked or changed as a result.

Example request shape:

```json
{
  "state": {"contract": "...", "source_and_evidence": "..."},
  "questions": {
    "causal_path_complete": {
      "type": "boolean",
      "instructions": "Do the supplied source and traces establish that the returned policy bytes change actual runtime decisions and effects? A digest label alone is insufficient.",
      "criteria": {"true": "Causal path evidenced", "false": "Missing or contradicted evidence"}
    },
    "priority": {
      "type": "choice",
      "instructions": "Which supplied finding most threatens this experiment's conclusion?",
      "criteria": {"causal_disconnect": "Wrong bytes or actions execute", "authority_or_leakage": "Authority or sealed data boundary fails", "reporting_only": "Behavior is intact but reporting is inaccurate"}
    }
  }
}
```

Jev reads `VERCEL_API_KEY`, falling back to `AI_GATEWAY_API_KEY`. On this Windows machine the configured user environment can be read into the evaluator process environment programmatically. Never print key values or put them in commands, requests, reports, Git, or a model prompt. The retained Windows Python environment at `D:\AI\Agent-Society-v2-review-02\.venv\Scripts\python.exe` can run the evaluator. That checkout remains because it supplies this runtime; do not delete it while in use.

Treat probabilities as review evidence. High confidence cannot replace a real gate; low confidence calls for inspection, not repeated rephrasing until Jev agrees. Jev cannot authorize spending, promote candidates, approve deletion, or weaken a test.

## Local runtime and hygiene

Use WSL `Ubuntu`, Linux user `ubuntu`, Python `/home/ubuntu/.venvs/as9/bin/python`, and PostgreSQL 18 on `/var/run/postgresql`. These are persistent; `/tmp` is not. Local dependencies include pytest, psycopg, DBOS, httpx and the existing application dependencies. Set `PYTHONPATH` with the explicit Linux paths for your checkout and `src`/`experiments`. Windows-to-WSL quoting expanded `$PWD` incorrectly in an earlier run, so verify `settlement.__file__` before a suite.

Only create and drop databases owned by this task with the `s09_` prefix. Check active sessions before cleanup. Never touch `ec02test_*`, `inv_*`, or other owners' stores. The final checkpoint report lists any intentionally retained resources. Gate tests that create their own database names cannot be run concurrently against that same name from two worktrees.

Commit as `Nightjar <nightjar@authors.invalid>` for author and committer. Use additive commits with finding IDs; no history rewrite or force push. Push coherent checkpoints and the final branch to `origin`, then compare local and remote SHAs. Local access does not replace remote backup. Keep secrets out of Git and use `origin` rather than embedding a private repository address.

Remove your temporary worktrees only after clean/merged status and path checks. Preserve useful untracked evidence before deletion. Remove merged local task branches; do not delete unrelated remote branches. Leave one integration checkout, a clean tree, no active test processes, and a complete fresh-checkout reproduction path.

## Final handback

Give the branch and exact pushed SHA, local/remote equality, the integrated gate command and actual result, the independent offline recomputation, and dispositions for C0–C5. Separate live, doubled and externally unverified evidence. Explain what the acquired policy changed, whether any benefit survived the controls and resource rule, and what remains unproven. Include the next architectural decision supported by the results. Do not call Stage 9 complete if policy assessment, exact activation, or fresh-process continuation is still manually supplied by the tests.
