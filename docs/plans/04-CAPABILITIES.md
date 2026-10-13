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
