# Composition rpr-C-transfer-v1 (authored fixture, not model output)

Scope: graph-family witness-preserving reduction, up to 10 vertices and
18 edges, witness triangle-free and non-bipartite.

Interpretation: byte-identical shared core as rpr-C-source-v1, paired with
a graph adapter translating tasks to anonymous atom lists (vertex units
then edge units) and back to id-preserving subgraphs. Only the adapter
differs; the core is unchanged.

Applicability: supported on well-formed graph tasks within cap.
Preservation is decided by the independent oracle, never by this text.

Losses: atom indices discard adjacency and cycle structure; the aux
snapshot retains them. Coarse vertex chunks often destroy the odd cycle,
which the oracle rejects; the incumbent is then retained.
