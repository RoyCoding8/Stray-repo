# P04. Executable capabilities

Acquire a procedure that later work actually invokes. Depends on [P01](01-INVESTIGATIONS.md), [P02](02-MEMORY.md) and [P03](03-CONTEXT.md). The [master plan](MASTER-PLAN.md) owns shared rules.

## Capability contract

A capability has content identity, construction lineage, an invocation interface, applicability conditions, observable postconditions, effects, dependencies, resource limits and evidence. Documentation helps select it. The executable artifact performs the procedure.

Begin with ordinary Python packages and a narrow versioned structured input/output interface. Define the permitted invocation environment before model construction. Do not demand that the model guess file paths or hidden runtime conventions. A wrapper or interface adapter must be declared and versioned, not silently repair candidate semantics.

Use the existing genome and artifact publication paths where appropriate. Identify reusable methods within a genome without copying them into an independently authoritative skill database. Pin the dependency closure needed for execution. Record requested and executed capability identities separately when they differ.

A candidate moves through construction, local checking, experimental retention and later use. A failed candidate remains a failed candidate. Experimental retention does not imply trusted promotion. Selection uses applicability evidence rather than the model's own claim that a method is general.

## Delivery slices

1. **P04-1. Execute an independently authored method.** Pin the interface and run a package through the actual bounded worker path. Prove that returned values and produced artifacts reach the investigation.
2. **P04-2. Construct and check.** Use development evidence and the real constructor to generate candidate bytes. Check them unchanged, record refusals and retain an eligible experimental method.
3. **P04-3. Reuse after restart.** Load the retained package in a fresh process. Select it for a changed eligible task and record whether its invocation affects the result.

## Acceptance scenarios

- **P04-A.** An independent constructor produces a method without access to a hidden authored solution. Construction bytes, retained bytes and executed bytes agree.
- **P04-B.** Substitute a no-op or disconnect invocation. The use check distinguishes the lost behavior rather than passing on provenance labels.
- **P04-C.** Invoke outside declared applicability. The selector declines or explicitly conducts an experimental applicability test. It cannot relabel an incumbent result as method use.
- **P04-D.** Preserve a useful method across restart and execute it on changed inputs. A stored answer or replayed output cannot satisfy the scenario.
- **P04-E.** Reject an invalid method without publishing it as usable or losing its construction cost and evidence.

Run a live construction and later-use path on a verified free route. An honest no-acquisition result closes that experiment, but the component's execution and selection mechanics still need independent qualification. Utility and broader transfer remain separate measurements.

## Working checkpoint

The investigator can acquire, reject, retain, select and execute methods through one path. Publish a small usable catalogue and inspectable use records. Do not build a universal DSL or rewrite the entire agent executor. P09 later investigates representation transfer; P07 later makes development decisions executable and revisable.

## Selected implementation shape (2026-10-14)

The Architect comparison selected genome-embedded methods. A second design kept
standalone method artifacts behind task-declared operations. Its explicit input
contract is retained, but belongs in the investigation request rather than a new
Task schema. The independent Luna cross-judge agreed. Existing genome packages
remain the byte authority; the catalogue is derived from their descriptors and
checked retention decisions. No capability table or lifecycle service is added.

The traced path is `Genome.publish/load` to package bytes, P01 decision to durable
operation identity, broker `sandbox-exec` to bounded child, then `rsi_verdicts` to
independent task outcome. Existing agent episodes and method episodes share the
episode record and pristine verifier. Their operation effects and usage remain
distinct. A native method episode has CPU exposure, not model token usage.

### Caller's view and data shape

An investigation optionally pins a method request alongside its task and genome.
The request names the method, an interface version and a finite JSON input value.
`investigate.step` selects a checked method or reports why none is eligible. A
declined request does not silently run the model and call that method use.
The admitted decision stores requested and executed method identities and the
exact invocation input. Resume uses that decision rather than selecting again.

Methods live under `skills/<name>/`, with `SKILL.md`, `capability.json` and ordinary
Python source. The descriptor contains exactly:

```json
{
  "schema": "rsi-capability/1",
  "interface": "example-interface/1",
  "entrypoint": "method.py:invoke",
  "dependencies": ["python-stdlib"],
  "effects": ["return", "solution-files"],
  "limits": {"timeout_ms": 5000, "max_output_bytes": 65536}
}
```

All files under that skill directory form its dependency closure and method
digest. The genome digest identifies their containing package. No installation
or network dependency resolution is assigned. The fixed runner and exact Python
runtime also belong to the invocation identity. Descriptor effects state the
permitted interface; native execution does not enforce hostile filesystem or
network isolation.

The trusted runner passes `invoke(request)` one JSON object with `interface`,
`value`, public task `files` and the admitted `context` continuation. The return
object has exactly `value` and `files`. Returned files map declared solution
slots to UTF-8 text. The adapter never repairs candidate semantics.
Arbitrary JSON values support non-SWE
procedures; the initial task verifier consumes returned solution files.

Task episodes wrap `context` as `{"continuation": original_context,
"task_digest": canonical_task.digest}` before invocation. This binds the task
and evaluator identity even if a crash occurs before the episode row is saved.
The trusted runner returns one structured result; the episode consumer
materializes its immutable returned files into the verifier workspace.

The domain interface is sketched as follows. Implementation may simplify these
names, but must preserve the ownership and evidence boundaries.

```python
catalogue(genome) -> tuple[Capability, ...]
invoke(dsn, launcher, genome, name, request, *, operation_id,
       allocation_id, attempt_id, staging_root, artifacts_root) -> Invocation
retain(dsn, retention_id, *, genome, name, episode_id, artifacts_root) -> Retention
select(dsn, selection_id, *, genome, name, interface, artifacts_root) -> Selection
construct(dsn, agent, parent, *, name, interface, context_packet,
          operation_id, allocation_id, token_ceiling, timeout_ms,
          staging_root, artifacts_root) -> Construction
```

`invoke` owns closure verification, staging, fixed adapter invocation, result
publication and use records. `retain` requires a genuine method use with a
passing development-task verdict. `select` accepts only that checked interface
and current matching bytes. This establishes experimental scope, not general
applicability. It records requested and executed identities separately.
`construct` reuses the broker-routed meta worker and P03-selected development
evidence. It gives the model the full ABI before construction, never a hidden
reference implementation. Invalid outputs retain their trajectory and cost.
Before lineage publication, construction records a durable capture decision
that pins the candidate's existing genome artifact and constructor evidence.
Recovery uses that snapshot even if the workspace changes or the same genome
was published earlier by another operation. The initial workspace capture
remains a cooperative execution boundary, not hostile-code containment.

### Implementation and falsification order

1. Implement the descriptor, closure and child invocation. Independently authored
   methods must return literal changed-input values and files through real broker
   dispatch. Identity substitution, malformed output and timeout must be visible.
2. Add method episodes and checked retention/selection. Reuse existing episode,
   verifier, decision and investigation ownership. No synthetic agent receipt is
   substituted for a method operation.
3. Connect construction and the public investigation consumer. Qualify A–E on the
   integrated path, including a fresh-process use and a working baseline before
   no-op or disconnection controls.
4. Run Sol High independent verification after integration. Freeze one bounded
   free-route construction/use experiment only after its apparatus is qualified.
5. Consolidate and complete CI before closing P04. P05–P10 stay paused.

The deployment boundary remains separate. Bounded native child execution is
permitted for cooperative experiments. It does not establish hostile containment,
trusted promotion, broad transfer or improvement of the learner.
