# Stage 09 C2/C3 action grounding

## Scope

This is a read-only grounding report for `codex/local-s09-actions`. It covers the C2/C3 gaps around executable STEP policy revision, method use, trajectories, records, assessment, and the smallest public full-cycle gate. No production files were changed.

## Facts from the current source

- The contract defines `STEP(view, state) -> {action, state}`. The view contains task content, observations, unresolved questions, last result, eligible methods, remaining resources, and contract versions. Policy state is bounded JSON and is persisted by the trusted driver (`docs/design/STAGE-09-IMPLEMENTATION-CONTRACT.md:25-39`, `experiments/ad01/policy_step.py:115-145`).
- `StepPolicyConsumer` currently maps `diagnose`, `construct_method`, and `use_method` through `_STEP_TO_LEGACY`; `use_method` therefore becomes a development proposal. `propose_revision` creates an in-memory investigation containing revision metadata, persists the STEP transition, then returns a terminal `stop` action. It does not call `open_revision_proposal`, construct candidate policy bytes, freeze, assess, or bind (`experiments/ad01/agenda_policy.py:277-323`, `:581-631`).
- The trajectory boundary admits the investigation, executes the selected action, records the episode, and returns observations. It already has durable accepted-action/effect identity and resume handling through `s09_policy_state`, so C2 should extend that path instead of adding a second loop (`experiments/ad01/trajectory.py:222-325`, `:431-525`).
- Policy construction already emits `kind=learning-policy`, `entry=STEP`, ABI, source digest, origin, parent digest, applicability, and model-call lineage. It validates returned STEP bytes in a child before returning them (`experiments/ad01/construct.py:398-490`, `experiments/ad01/policy_step.py:148-201`).
- Revision proposal and freeze are durable and deterministic. `open_revision_proposal` pins investigation, parent digest, operational failure, scope, protocol, and allocation. `freeze_candidate` stores exact source bytes and refuses a second byte set for the same proposal (`experiments/ad01/records.py:830-954`).
- `records.assess_frozen` is currently a task-method assessor. It loads a freeze, calls `method_exec.verify_member`, executes `run_member_out_of_process`, checks each result with `_check`, counts reductions, and returns `bind` only when at least one task improves (`experiments/ad01/records.py:969-1033`). That is not a STEP-policy assessment rule.
- Binding is already atomic and version-checked, and selection can use an active binding. The selection fallback still supports legacy first-match behavior without binding context. Policy binding must carry policy identity and scope into the public caller and fresh-process selection (`experiments/ad01/selection.py:17-111`).
- The current public entry is `experiments.ad01.cli`. It exposes `run`, `resume`, `use`, `export`, `replay`, and `recompute`; no command completes revision through assessment and bind (`experiments/ad01/cli.py:85-255`).

## Two viable integration shapes

### A. Typed assessment dispatch in `records`

Keep one lifecycle entry such as `assess_frozen`, add an explicit artifact kind/protocol, and dispatch to either a method assessor or a STEP-policy assessor. The shared envelope owns proposal identity, frozen digest, attempt identity, source/configuration, resource accounting, and immutable result persistence. The handlers remain separate. A method handler calls `verify_member` and `run_member_out_of_process`; a policy handler calls `verify_step_source` and `run_step_out_of_process`, then drives bounded policy decisions and the sealed method-use tasks through the same trusted trajectory admission.

This keeps exports, replay, and verifier plumbing on one record shape. The dispatch must reject missing or contradictory artifact kind rather than infer it from `entry` or caller labels. The policy handler must record returned source bytes, executed digest, admitted action, actual effect, sealed-task outcome, and complete costs. A changed digest without changed execution remains insufficient.

### B. Dedicated policy assessment entry beside method assessment

Leave `assess_frozen` method-only and add `assess_frozen_policy` plus a public revision driver. The new entry owns policy-specific freeze validation, child STEP execution, policy episode transitions, sealed method-use tasks, quality/resource judgment, and the call to atomic bind. Shared helpers can still cover proposal/freeze loading, deterministic attempt IDs, and immutable result persistence.

This makes the semantic split obvious and reduces accidental reuse of `_check` or method execution. It adds another public path and requires the exporter/verifier to understand two assessment result families. The shared helpers must remain small, otherwise the code becomes two disconnected lifecycle implementations.

## Recommendation

Use the hybrid of A and B. Share only the durable lifecycle envelope and identity/accounting helpers. Keep `assess_frozen` as the method assessor and add a policy-specific assessor or handler selected by an explicit `artifact_kind=learning-policy` and protocol. Route both through one trusted revision command that performs proposal, construction, freeze, assessment, and atomic bind or rejection. This follows Jev's strong preference for a hybrid separation decision while avoiding a second disconnected public lifecycle. Jev's reuse result was low-confidence and split between dispatch and lifecycle-only reuse, so the source evidence should decide the narrower choice: reuse records mechanics, not method semantics.

## Smallest real public full-cycle gate

Add one public command or callable that runs this exact bounded path in one study root and can resume by identity:

1. `run` or `resume` executes an independently supplied STEP policy until a visible operational method-use failure is recorded.
2. The policy's `propose_revision` action creates a durable proposal pinned to that failure and the active parent policy digest.
3. The trusted revision command constructs returned `kind=learning-policy`, `entry=STEP` bytes through the broker, validates them in a child, freezes the exact bytes, and records no-candidate on constructor disconnect or invalid output.
4. A fresh assessment state runs the frozen candidate and incumbent under the same declared protocol. Assessment inputs include only declared development/operational data; sealed answers and judgments stay evaluator-owned.
5. The independent rule returns reject, inconclusive, or bind. Bind uses expected current versions and exact candidate/protocol/evaluator/scope identity. Rejection preserves the incumbent.
6. A fresh process selects the active binding and executes at least one policy step through `STEP -> admitted action -> actual child/effect`, with a different policy source producing a different admitted operation under the same starting fixture. Export and offline verification must prove the source digest, action, effect, receipt, accounting, and verdict.

The honest no-candidate branch must be part of the same gate. A recorded proposal or accepted row alone is not a pass. This is the smallest gate that satisfies the contract's required evidence without adding a workflow engine or broad rewrite (`WORKER-STAGE-09-COMPLETION.md:37-53`, `docs/design/STAGE-09-IMPLEMENTATION-CONTRACT.md:55-65`, `:83-95`).

## Causal and hidden-assessment constraints

The C3 pilot must keep P0 as the frozen incumbent, P1 as equally budgeted construction without experience, and P2 as equally budgeted construction with permitted experience. Candidate source bytes must be the constructor result. The assessment panel must be frozen before exposure, use fresh worlds, and remain absent from construction/development inputs. Report construction cost separately from execution cost. Missing candidates remain unavailable arms and cannot become authored incumbents (`WORKER-STAGE-09-COMPLETION.md:45-53`, `docs/design/STAGE-09-IMPLEMENTATION-CONTRACT.md:67-81`).

Jev judged the causal claim only 0.52 true. Treat that as a warning, not approval. The gate above needs explicit matched starting conditions, an independently different returned policy source, changed admitted action/effect evidence, and downstream task utility/resource records. A source digest change or accepted proposal is not causal evidence.

## Unresolved design questions for implementation

- Which exact policy quality/resource rule is frozen before assessment, and which fields make unknown cost block promotion rather than become zero?
- Does a policy assessment episode reuse the existing trajectory boundary with a policy artifact argument, or does it need a small policy-specific episode adapter around that boundary?
- What public identity names the active policy release so `run`, `resume`, and `use` cannot select an unrelated same-family release after restart?
- Which sealed method-use result fields are persisted for independent verification while keeping answers out of policy construction and revision prompts?
- Does the existing capability release schema need an explicit artifact kind/protocol column, or can the policy artifact identity and protocol be encoded in existing version/evidence fields without ambiguity?

## Jev evidence

The sanitized request and response are in `reports/local-completion/action-grounding-jev.json`. Jev used `typesafe-ai/jev` through the local typed-evaluation skill. It returned `hybrid` for policy/method integration with probability `0.99`, `dispatch` for reuse of `assess_frozen` with probability `0.60` and confidence `0.40`, and causal sufficiency probability `0.52`. These are evidence for review, not authorization or proof.
