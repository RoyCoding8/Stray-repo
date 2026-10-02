# M4 E1/E2 frozen prospective-comparison protocol

Study family `invl02-m4`. No live data in this directory. All values
below are the frozen rule shape. Worked examples use synthetic
test-double bytes from `tests/test_m4_offline_recompute.py`.

## Arms and treatment

P0 is the competent fixed learner plus ordinary retrieval. P1 acquires
an executable program from interface and mission information without
development history. P2 receives the same interface and mission plus
the permitted history. The history difference is the declared
treatment. P0 performs no construction.

## Quota reservation

Before either acquired arm starts, `reserve_allowance` grants P1 and
P2 equal init and repair allocations. The grant is a pure function of
the arm set, so execution order cannot starve an arm. The offline
verifier rejects any arm whose construction calls exceed init plus
repair, and rejects unequal P1/P2 allowances.

## Splits

Development, qualification (assessment) and untouched audit task sets
are pairwise disjoint. Qualification results may select among frozen
candidates and are adaptive evidence. The audit runs after selection,
cannot change the reported winner, and is retired from future
untouched claims once reused. Environment probe outputs during an
audit task are legal operational observations. Private target
identities and unqueried outputs are never in the program view.

## Candidates and configuration

The freeze pins candidate source bytes with digests, the frozen method
repertoire per arm, model and configuration, instruments, resource
ceilings and the comparison rule. Comparison is mean recomputed
quality on qualification tasks with a frozen margin. Ties resolve to
the incumbent P0. A larger benefit claim needs a pre-registered sample
size and practical effect threshold before the audit.

## Effects, lineage and resources

Every episode exports its policy actions as actual effects. Every
record carries source identity, invocation lineage through operation
identities with settled receipts, and outcome evidence as observed
outputs. All resource classes are exported: model dispatches,
input and output tokens, tool queries, child compute, billed units,
unresolved exposure and human interventions. History input tokens and
failed attempts are counted separately. Unknown billing stays unknown
and a zero claim against an unresolved source is refused.

## Unavailable arms

Incomplete acquisition yields unavailable arms with a recorded reason
and an incomplete comparison with no winner. Candidate execution by an
unavailable arm is refused as substitution. Incumbent-marked records
for unavailable arms are baseline evidence, never acquired outcomes.
