# Composition rpr-C-source-v1 (authored fixture, not model output)

Scope: software-family witness-preserving reduction, sequences up to 24
ops with a designated value-disagreement observation.

Interpretation: the adapter translates a task to an anonymous atom list
(one atom per op position) and back; the shared core searches over atom
subsets with coarse feedback-driven halving. Aux carries the source
snapshot, declared and charged; the core never sees raw ops.

Applicability: supported on well-formed software tasks within cap.
Preservation is decided by the independent oracle, never by this text.

Losses: atom indices discard op semantics, order effects and fault
identity; the aux snapshot retains them, so a small encoding alone does
not suffice. Coarse chunks fail when setup spans halves.
