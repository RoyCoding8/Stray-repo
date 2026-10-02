# Stage 9 implementation contract: persistent executable learning procedures

Selected 2026-09-21 after the [delivery review](../../reviews/STAGE-08-09-1D90C2E-ASSESSMENT.md). This supersedes the unresolved revision and replay proposals in `STAGE-09-ARCHITECTURE.md`. The bounded stage 8 helper fix remains accepted. The original live study remains unchanged and shows no retained method. This contract authorizes the next engineering batch, not a new live spending grant.

## Decision and scope

Consolidate the existing consumer/driver into one persistent investigation loop over the current broker, authority and evidence facilities. Choose the in-place migration, but change semantics where required rather than preserving benchmark assumptions. No new workflow engine, database technology or permanent agent hierarchy is needed. Experiments supply task opportunities, splits and judges; they do not own a second cognitive loop.

The next deliverable is a complete bounded cycle: observe a limitation, execute a policy that chooses how to investigate, construct/check a method, retain or reject it, use it after restart, incorporate permitted operational feedback, propose a revised learning policy, independently assess it, and bind or reject the revision. It must work through the public entry in both current domains. It proves mechanisms; a positive learning result is not required.

The system chooses admissible targets, diagnostics, method construction/use and stopping. It can acquire arbitrary bounded policy source under the declared interface, not only select an authored strategy name. The outer effect vocabulary, budget, evaluation protocol and initial domain instruments are supplied by us. Open-ended agenda expansion, weight training, predictive world models and hostile containment qualification are outside this batch.

## N1. Durable ownership and identity

Use an investigation identity independent of world, arm and schedule. Those remain experiment labels. A durable state or projection must identify the objective, visible evidence, open questions, active policy artifact, scoped method bindings, pending accepted action, policy-private state, revision lineage and remaining authority. Map every field to an existing row/artifact or a justified schema addition before implementation. A name in a design document is not persistent state.

One trusted driver owns this transition:

`materialize visible view -> execute policy step -> validate/admit or refuse -> persist transition -> execute/reconcile effect -> incorporate result -> next step or stop`.

Persist the exact policy input, output, state transition and accepted action identity before external effects. Resume reconciles the pending action and then continues. Repeating a request reuses its logical identity; intentionally revised execution gets a new attempt identity. A context reset, process restart, different database or new policy cannot replenish the study root.

Initial revision is serial: one active policy and at most one assessment candidate per lineage. Keep parent snapshot and artifact identities so future branches can be represented without renaming benchmark campaigns. Parallel policy assessment arms have isolated investigation state and explicit allocations under the same study authority. General branch merging is not required or claimed.

## N2. Executable policy ABI and trusted admission

Use a versioned JSON-in/JSON-out step interface, with semantics equivalent to:

```
STEP(view, state) -> {action, state}
```

The view contains actual permitted task/instrument content, visible observations and unresolved questions, the last action result/refusal, eligible method identities, remaining resources and contract versions. Policy state is bounded JSON, opaque to the driver except for validation and persistence. It is never the authoritative source of budgets, claims, visibility or accepted operations.

A policy artifact includes kind, source digest, entry/ABI, dependency and instrument contract identities, origin, parent policy digest and applicability. Keep task-method artifacts distinct from policies that choose how to learn. Origins distinguish authored controls, model-acquired bytes and fixture-generated stand-ins.

Execute acquired policy source outside the trusted host with CPU/wall/output/state limits. Reuse the established child execution/profile machinery where appropriate. Do not pass generated code as an unrestricted Python proposer or admission callback. The driver validates every returned action. Admission, evaluation rules and budgets remain trusted and cannot be replaced by the learned policy.

The initial permitted action set covers diagnose, construct/check a method, use a scoped method, request model reasoning, propose a method or policy revision, and stop. Concrete names can reuse existing actions. Every action carries target/instrument, inputs, evidence references and requested resources. A model request is a yielded effect, routed through the broker; its actual response is an observation for the next step. Policy code has no direct provider credentials or unaccounted tool access. Limit steps as well as model calls so a policy cannot loop without cost forever.

Do not hardcode the whole sequence in a new driver while labeling a model's decorative question as the policy. Prove that two valid policy artifacts cause different actual operations under the same starting conditions. A routine action may omit a hypothesis; an investigation may keep competing explanations and choose a diagnostic with distinguishing outcomes.

Both public orchestration and direct effect admission must apply visibility, target, artifact and budget constraints. The audit found that reference-free exploratory proposals can pass `admit_investigation`, while `_run_boundary` supplies the later protected-target fence. Preserve the complete protection when moving ownership. Test a proposal with no references, unknown target, protected target, stale support and incompatible policy/artifact version. An intermediate 'admitted' value is not proof that execution is permitted.

## N3. Operational feedback and sealed assessment

Use three explicit evidence roles: development, operational feedback and sealed assessment. Public operational failure is legitimate learning input. Sealed assessment is held by the evaluator and cannot enter policy construction, revision prompts or development context.

If assessment evidence is deliberately revealed later, record its exposure and retire it from independent assessment for every descendant that could have consumed it. Retire the relevant assessment batch when its outcomes inform another adaptive revision. Copying, summarizing or renaming the data does not restore independence. Historical frozen tasks and verdicts remain unchanged; use new identities for future protocols.

Prefer a visible operational-use failure to trigger the first revision cycle. Pin the failed method/policy digest and failure record. The current historical AD01 protocol must keep refusing protected feedback; implement new operational feedback through the new versioned protocol instead of weakening the old guard globally.

An assessment episode may expose its declared working inputs and intermediate instrument observations to the frozen policy, but evaluation judgments and sealed use answers cannot escape to its constructor. Give each matched arm isolated state and identical declared information access. A hidden-output perturbation must not alter pre-assessment construction inputs.

## N4. Revision, assessment and promotion

Persist a revision proposal with parent artifact, motivating visible evidence, scope, construction allocation and protocol identity. Build candidate bytes through the broker and the same returned-bytes validation discipline as task methods. Permit one bounded repair per candidate in the initial study. No authored candidate may silently replace a failed model construction.

A candidate policy is frozen before independent assessment. Compare it with the current policy under a fixed protocol, matched fresh opportunities and finite resource limits. Include proposal/construction/repair costs in study accounting and report their amortization separately from execution costs. Unknown usage or unresolved effects cannot become zero cost or support a promotion requiring known costs.

Improving the motivating task is a development result. It does not automatically authorize family-wide replacement. Qualification and promotion are separate. Promotion requires the predeclared independent quality/resource rule and relevant regression checks. Outcomes are reject, inconclusive, retain as a scoped alternative, or bind as active for a declared scope. If this first implementation supports only reject/inconclusive/bind, explicitly defer portfolio selection rather than faking it with list order.

Bind a successful revision atomically against the expected current artifact/version. Preserve the parent and rejection evidence. Losing a concurrent comparison or resuming after a crash cannot bind twice or silently replace a newer policy. Fallback has an explicit reason and preserves the old binding.

Method selection must consult the active eligible binding, not whichever family match occurs first in a list. New execution identities must bind investigation, logical action, active policy and invoked method version. Retrying one action reuses its identity; intentionally testing a different revision on the same target does not reuse the old settled operation. Historical IDs remain usable for historical reproduction.

## N5. Replay and the selected empirical question

Keep exact recorded replay for integrity, recovery and supported continuations. The existing checker rejects a changed instrument by construction. Its 28 identity successes and 28 changed-instrument refusals close that conformance question; do not run it again as a study of policy improvement. Unsupported alternatives remain unknown. Predictive dreams are not observations and are not introduced by this batch.

The next empirical question is prospective: **can a policy revision constructed from visible investigation experience improve subsequent independent outcomes over the incumbent and over an equally budgeted revision without that experience?** This tests the use of experience in executable policy revision. It does not claim general intelligence or replicate every claim of Dream-RSI.

Use a small engineering pilot with three arms: P0 frozen incumbent policy, P1 directly constructed policy with interface/objective but no experience corpus, P2 policy constructed with permitted experience. Give P1/P2 the same interface, candidate count and construction allowance. Do not supply P2 with an authored answer or a menu of successful strategies. Track whether each constructed policy actually changes execution.

First collect at most four visible development/operational-feedback episodes, two per domain. Permit one policy candidate plus one repair for each of P1/P2, four construction calls maximum in total. Freeze candidates and the protocol before exposing fresh assessment inputs. The assessment panel has two fresh worlds per domain and all three arms, twelve policy episodes. Each episode has bounded investigation opportunities and two sealed method-use tasks, one within the declared scope and one structural variation. Freeze exact task identities, source/configuration, arm order and evaluation rule in the implementation plan before running the panel.

Each development or assessment episode permits at most six policy steps and six model calls total, including method construction/repair and model-request actions. At most one method lineage with one repair per episode. Thus four development episodes plus twelve assessment episodes plus four policy-construction calls permit at most 100 new model calls. A stop/unknown/no-candidate outcome does not authorize a replacement episode. Fault injection should reuse existing operations where testing recovery; extra inference needs a separately itemized allowance. These are design ceilings, not a grant. Derive concrete token, query, child-runtime, pending-exposure and wall ceilings from the selected profiles, and reconcile every phase under one study root.

Choose and freeze a transparent quality/resource rule using the existing domain judgments before looking at assessment results. Include preservation failures, method usefulness on sealed use tasks and the complete resource vector. Avoid zero-denominator ratios. A pilot may justify a scoped next study, not a statistically established general benefit. Compare P2 separately against P0 and P1; partial coverage or missing candidates cannot yield a full comparison claim.

If policy acquisition produces no valid candidate, archive that exact construction outcome and do not populate its arm with an authored substitute. If all arms tie, report the tie and whether policies made different decisions. If execution differs but quality does not, that is a different result from an inactive mechanism. If provider failures dominate, separate delivery from executable validity and utility. No success hunting or expansion after seeing protected outcomes.

## N6. Migration and public acceptance

Keep one current investigation driver. Existing CLI/study callers become clients of it. Reuse broker, journal, artifacts, context and capability facilities where their real contracts fit; do not claim reuse merely because similarly named modules exist. A domain instrument adapter supplies content, operations and result interpretation. The shared driver must not decode world/task-name conventions to decide scientific meaning.

The implementation plan must map old campaign state, pending decisions, diagnostic checkpoints, method selection and use IDs to the new semantics. Preserve completed historical reproduction. For pending legacy work, either demonstrate a lossless versioned resume or refuse migration with a precise drain instruction. Never reset, relabel or guess a pending effect. Once active callers migrate, delete the duplicate current loop; retain only an explicit historical reproduction path when necessary.

The public acceptance battery must include both domains and prove: policy bytes to admitted action to actual effect; one acquired-method path and honest no-candidate fallback; operational feedback to a revision request; hidden assessment data exclusion; independent promotion/rejection and fresh-process active selection; unchanged pending-action identity across process loss; distinct identity for a new revision; unknown-cost preservation; exact replay support/refusal. Persist all probe sources and bounded outputs. Readable rows and accepted proposals alone do not prove resumed or executed behavior.

## Completion

The batch delivers updated design, implementation, deterministic qualification through the real public path, and the small live pilot only if valid authority/configuration are available. Missing live authority does not block the engineering work, evidence analysis or a concrete final request. A live negative can finish the pilot. Stage 9 consolidation can be complete for this contract while broad learning efficacy and operational qualification remain open.

Do not implement unrelated management UI, new model training, general branch merging, production deployment or a universal simulator. Do implement the complete accepted cycle before calling the batch done.
