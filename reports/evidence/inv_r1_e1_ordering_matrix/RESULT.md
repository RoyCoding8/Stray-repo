# E1 on the ordering world: three representations, all three comparable

Jev was consulted on E1's matrix, as the handoff reserves it for
representation expressivity, and it was decisive on three questions:

| question | Jev |
|---|---|
| is the ordering STEP refusal a world binding or an expressivity limit? | **0.90 binding** |
| what can E1 claim? | **one world, two of three** (0.96); *not* the general portability claim |
| next step? | **unbind STEP** (0.99) |

It also declined the claim I would have preferred: "representations are
portable, policies are not" scored **0.00**. That is a generalisation from
one second world, and the score says so.

## What the matrix now shows

Five ordering-constraints tasks, three representations, all three pairs
`compare_arms`-comparable on every task:

| task | step | ast | graph | all pairs comparable | agree |
|---|---|---|---|---|---|
| dev/4 | 0.0 | 0.0 | 0.0 | yes | yes |
| dev/7 | 0.0 | 0.0 | 0.0 | yes | yes |
| dev/11 | 0.0 | 0.0 | 0.0 | yes | yes |
| qual/2 | 0.0 | 0.0 | 0.0 | yes | yes |
| audit/5 | 0.0 | 0.0 | 0.0 | yes | yes |

**The Boolean matrix is unchanged** — all five cells identical to the
recorded evidence, verified cell by cell after the rewiring.

## Every arm scores 0.0, and that is the honest reading

The three representations agree exactly, and they agree on zero. The
typed AST's measured limit explains it: the frozen node set has no
symbolic `lt`, so an AST program can *identify* a job the world named but
cannot *order* two. It commits a fixed permutation and gets it wrong.

The graph and STEP do the same, and the reason is the same: all three
records commit a written-down order rather than deriving one. So on this
world the matrix shows the representations agreeing, and it shows them
agreeing on a decision none of them computes.

**That is a parity result and a ceiling result at once**, and reading only
the first would overstate what was shown.

## Four defects between "reachable" and "runs"

Reaching the ordering world was one commit; running a three-representation
matrix on it took four more, and they are the same class of mistake each
time — a world-typed constant where a world parameter belonged:

1. `_world_state_from_contract_view` renamed `construct` to `commit`
   unconditionally, so the ordering arms received a Boolean schema.
2. The parity check compared `n_queried` when the ordering score does not
   publish it, and reported a mismatch between two score shapes.
3. `s09_graph_budget`'s child driver hardcoded the Boolean graph executor.
4. The world was passed as a bare argv element the child could not read as
   a path; it is staged to a file instead.

The third was flagged by the graph worker as "what the integration owner
must wire" and I had left it unwired while reporting the second world as
done. That was the least defensible part of this sequence.

## What is not claimed

Five tasks, one world family, and authored records in each notation. The
matrix says the three representations behave identically on two worlds and
that they score zero here. It does not say STEP and the AST are identical
in general, and Jev's 0.00 on the portability claim is the reason not to
say it.
