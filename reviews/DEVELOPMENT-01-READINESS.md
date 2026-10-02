# Development 01: bounded experiment readiness

Inspected implementation: `e1b95a6119e0c5a3f0c8f67732c2cec8c3e937b0`. Scope: the causal path from experience to construction, selected candidate, comparison and subsequent use. This is not another general infrastructure or style review.

## Disposition

The worker delivered useful durable episode machinery and a scripted integration path. Preserve that work. Its report records 484 passing tests; this review did not independently reproduce that PostgreSQL/subprocess suite.

Four gaps prevent treating the current CLI as the complete live experiment specified by Development 01. They concern what the experiment measures, not production hardening. Close them in the next bounded slice while implementing the selected [decision-context design](../docs/design/MEMORY-AND-CONTEXT.md). Do not reopen unrelated S0-S3 findings.

## D02-001: the constructor has references but no resolved experience

**Blocks an experience-conditioned learning claim.** DEV-01/02, LEARN-1/3.

`experiments/run_dev_episode.py:227-254` supplies triggers containing only task ID and family, then diagnoses and constructs. `development.py:277-281` sends those references to diagnosis. `_allowed_experience` at `development.py:355-359` and the construction prompt at `429-431` never resolve them into task content, attempted behavior, observations or costs. The ordinary development batch runs later, inside `run_abcs`, called at entry-point lines `445-458`.

Consequently the live constructor cannot condition on the claimed development experiences through this interface. A model may infer a generic method from a family name, but that is a different experiment. The fixture hides the missing input by returning a prewritten fixer.

The prompt also says only “candidate bytes honoring the access policy”; it does not state the JSON response shape and executable invocation contract that downstream code expects, including `--selftest`. These must be ordinary explicit task inputs, not knowledge embedded in the fixture.

**Required result:** admit the evaluation policy, obtain or resolve actual development experiences, materialize an authorized versioned context containing them and the output/invocation contract, then construct. Use the same allowed experience for retention controls. A pre-existing completed batch is acceptable; executing the same batch twice is unnecessary.

**Probe:** `test_constructor_prompt_has_unresolved_ids_not_experience` invokes the production constructor with a doubled store/inference seam and captures its actual request. Source inspection establishes the CLI's ordering and absence of reference resolution.

## D02-002: rejected candidate bytes still enter the comparison

**Blocks selected-version and rejection semantics.** DEV-04/08, LEARN-7.

The closure in `experiments/run_dev_episode.py:264-273` reads the `built` map. It does not consult `selected` or `bindings`. When development checks reject a built candidate, `development.bind` legitimately returns no selected version. Nevertheless the closure returns that candidate's bytes, and the CLI supplies a fallback version stem to `run_abcs` at `295-299,448-458`. The harness can publish/use it as the retained method despite rejection.

**Required result:** the selected immutable binding is the sole source for comparison candidate resolution. A reject/no-candidate outcome means no promoted or implicitly republished C candidate. Use the declared incumbent/control behavior, retain the rejection and its cost, and do not pretend that a new version stem changes eligibility.

**Probe:** `test_rejected_candidate_still_returned_to_comparison` runs the production `_run_episode` with explicit lifecycle doubles returning a valid rejection, then invokes the actual returned synthesis closure. It returns the rejected bytes. This checks the integration seam, not database release enforcement.

## D02-003: the first evaluation-policy freeze is missing

**Blocks the predeclared-comparison interpretation.** DEV-04/07, LEARN-2/4/6.

Admission at `development.py:222-228` freezes a development protocol with generic groups and empty budgets/stopping/uncertainty. The CLI records its comparison task groups only after construction and development checks, at `run_dev_episode.py:285-289`. That policy contains task IDs only. `freeze_comparison` at `development.py:627-639` accepts it in the checked state; it is not the required pre-development freeze of selection/grouping, access, outcomes, thresholds, stopping and release rules.

The stock fixture's hardcoded task lists reduce one avenue of adaptation, but the durable contract does not establish the required ordering or complete policy. This does not mean observed cheating occurred; it means the promised experiment is not yet bound as specified.

**Required result:** before constructor-visible development feedback, persist the actual finite-panel policy and its immutable identity. Later bind the selected candidate/lesson/reference/evaluator versions to that policy. Do not require statistical inference: explicit finite-panel thresholds and complete outcomes are sufficient. An amendment creates a declared new protocol and preserves exposure history.

**Probe:** `test_cli_freezes_task_policy_after_construction` records production entry-point call order with lifecycle doubles. The admission source establishes what its earlier protocol contains.

## D02-004: the reported subsequent-use phase stops at routing/pinning

**Blocks the claim that the released method was used on a later task.** DEV-08/12.

`experiment._maybe_release` at `592-650` releases, creates a fresh attempt, routes and pins versions. It has no subsequent task input and performs no method invocation or outcome check. `run_dev_episode._summarize` at `326-366` nevertheless marks “use” complete from that metadata, or from a textual fallback selection. Earlier panel/transfer invocations occurred before release; they cannot establish post-release use on a new task.

The separate fresh-process test in `tests/test_dev01_compare.py:105-165` demonstrates artifact reuse, using a supplied version and a previously evaluated task. Preserve that useful evidence, but distinguish it from the CLI's complete post-release continuation claim.

**Required result:** run a separate subsequent-use assignment after disposition. A fresh process obtains the release or incumbent through ordinary selection, invokes the selected behavior, consumes its output, grades the new task and records costs. A rejected candidate must follow the same visible incumbent path. Phase completion derives from that execution's receipts and outcome, not the existence of a pinned attempt.

**Probe:** `test_release_reuse_path_only_routes_and_pins` invokes the production release orchestrator with explicit release/store doubles. It observes routing/pinning without inference or method invocation. Source inspection connects that return value to the completed phase label.

## Independent checks and limits

Committed apparatus: [four characterization probes](probes/test_development_01_readiness.py). These deliberately assert the observed gaps; **4 passed means four gaps reproduced**, not four acceptance tests passed. The worker should migrate them to intended contracts or replace them with stronger real-DB regressions and record correspondence.

Reproduce from the repository with its test dependencies:

```sh
uv run --extra test python -m pytest reviews/probes/test_development_01_readiness.py -q -o addopts=''
```

Locally executed with Python 3.12.13 and an existing test environment against this checkout's production modules: 4 passed in 2.85 seconds. One existing pytest configuration warning concerned unavailable `asyncio_mode` support in that environment. No PostgreSQL transactions, containment, live inference or provider billing were exercised by these probes. Source links and the behavior under explicit doubles are the evidence; the worker must independently assess production reachability and its proposed remedy.

A local gateway was subsequently supplied by the human, along with model `claude-opus-4-6-thinking`. The first address returned HTTP 401; after the human corrected the port, discovery succeeded and eight live requests completed. No credential or private endpoint is stored here. The [standalone context pilot](../reports/CONTEXT-PILOT-01.md) is separate evidence from runtime qualification and does not close the four semantic gaps.

## Next action

Implement [Development 02](../WORKER-DEVELOPMENT-02-PROMPT.md): resolve these four seams and make decision context operational for diagnosis, construction and fresh-worker continuation. Preserve the fixture, keep live evidence separate, and carry controlled prototype limitations forward. Broader recovery, scheduler, deployment and statistical-calibration work stays on the roadmap.
