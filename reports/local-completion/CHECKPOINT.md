# Stage 9 local checkpoint

Branch: `codex/stage-09-local-completion`

This checkpoint integrates the verified local C1, C2A, C2B and C3 slices. It does not close Stage 9.

## Verified mechanisms

- A durable STEP transition is recorded before a model effect. Public fresh-process resume reuses a settled receipt without a gateway and reuses a prepared effect at exhausted allowance without rerunning STEP k0 or drawing a second model call.
- A STEP policy can construct a task method, then select and execute that retained method's exact source through the bounded child. An unavailable method refuses; it does not silently construct another.
- Operational feedback can create a durable policy revision request, construct model-returned `learning-policy` STEP bytes, and freeze the exact candidate with parent lineage. It remains pending; no release is created.
- Method binding now validates exact frozen source bytes, assessment currentness, canonical requests and explicit release scope. Repertoire-only use remains available when a release is intentionally absent.
- The C3 controlled-provider pilot executes returned STEP bytes, model method construction, frozen repertoire and sealed use; it independently verifies exported evidence. It is a controlled test, not live model evidence.

## Merged checks

| Gate | Result |

|---|---|

| C1 continuity and failure path | Included in the integrated 76-pass gate, PostgreSQL 18.6 and fresh child processes |

| C2A/C2B merged action and binding path | 22 passed |

| C2B neighboring bind and visibility path | 13 passed |

| C3 controlled policy pilot and legacy pilot | 15 passed |

| Policy constructor and STEP neighbors | Included in the integrated 76-pass gate |

| Integrated checkpoint gate | 76 passed in 113.30s |


All gates used WSL Ubuntu, Python 3.14, PostgreSQL 18.6 and real subprocesses. Model providers were doubles or a controlled local HTTP server. No live model call occurred in this checkpoint.

## What remains

The system still lacks a policy-specific sealed assessment that measures an acquired STEP policy's decisions, effects, downstream utility and resource use, followed by exact policy binding and fresh-process policy continuation. Existing method assessment cannot stand in for it. That full public policy-revision cycle must be completed before the authorized capped live comparison. The fresh local worker assignment describes the required order, counterchecks, Jev use, runtime, cleanup and final evidence boundary.

The worker must not describe a policy source digest, ABI dry run, or a task-method binding as proof that a revised learning policy improved behavior.
