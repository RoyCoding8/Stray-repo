"""M3 authored baseline: version-space Boolean-rule learner.

Maintains, per output bit, the surviving hypothesis set consistent with
every observed query. Chooses the unqueried input with the largest total
disagreement across the four version spaces, smallest index on ties.
Predicts the version-space member nearest the majority vote, so the
committed predictor is always legal and consistent with all queries.
Tuned on development instances only.

**Query selection is a total order on (state, budget).** The rule is
"largest total disagreement, smallest index on ties", and nothing else
enters it: not a seed, not the order inputs happen to be presented in.
So the next query is a pure function of the observed answers and the
remaining budget, and the same task replays the same query sequence for
every caller. That is what makes a learning decision inheritable: a
decision taken at some budget can be handed to another owner and
replayed to the same state.

`seed` is still accepted because every call site passes one, but it no
longer enters selection. An earlier version broke ties with
`random.Random(seed)`, which made the query sequence depend on a seed
that was never frozen: two call sites passed different values (`0` and
`int(seed)`), and 22 of 40 dev tasks then scored differently depending
on which one the caller used.

**The version space is a singleton once the budget is spent.**
`MAX_QUERIES` is `ceil(log2(len(CLASS_TABLES))) == 8`, and the policy
below attains that information-theoretic bound: over all 224 members of
the class, every one is identified within eight probes, and the worst
case needs exactly eight. Collapse at the budget is therefore the
instrument working as designed, not a defect, and a policy that has
*not* collapsed by eight has spent its budget badly.

The guarantee is "by" the budget rather than "only at" it: 32 of the
224 members are already pinned after seven probes and the other 192 at
eight. So the budget is a tight worst-case bound, not a modal outcome,
and no downstream study may read a collapse at seven as a bug.
`tests/test_m3_rule_instrument.py` holds both halves as invariants over
the whole class rather than as figures over sampled tasks.
"""

from __future__ import annotations

from . import boolean_rule as br


class VersionSpaceLearner:
    def __init__(self, class_tables: tuple, seed: int):
        # `seed` is accepted for call-site compatibility only. See the
        # module docstring: selection is a total order, so there is
        # nothing left for a seed to decide.
        self._tables = tuple(class_tables)
        self._candidates = [set(self._tables) for _ in range(br.N_OUTPUTS)]

    def observe(self, x: int, y: tuple) -> None:
        for bit in range(br.N_OUTPUTS):
            self._candidates[bit] = {
                table for table in self._candidates[bit]
                if ((table >> x) & 1) == y[bit]}

    def version_space_sizes(self) -> list:
        return [len(cand) for cand in self._candidates]

    def _disagreement(self, x: int) -> int:
        total = 0
        for cand in self._candidates:
            ones = sum((table >> x) & 1 for table in cand)
            total += min(ones, len(cand) - ones)
        return total

    def choose_query(self, queried: dict,
                     budget: int = br.MAX_QUERIES) -> int | None:
        if len(queried) >= budget:
            return None
        open_inputs = [x for x in range(br.N_STATES) if x not in queried]
        if not open_inputs:
            return None
        best = max(self._disagreement(x) for x in open_inputs)
        return min(x for x in open_inputs if self._disagreement(x) == best)

    def predict(self, queried: dict) -> dict:
        specs = []
        for bit in range(br.N_OUTPUTS):
            vote = 0
            for x in range(br.N_STATES):
                ones = sum((table >> x) & 1
                           for table in self._candidates[bit])
                if ones * 2 >= len(self._candidates[bit]):
                    vote |= 1 << x
            ranked = sorted(
                self._candidates[bit],
                key=lambda table: (bin(table ^ vote).count("1"), table))
            specs.append(br.spec_for_table(ranked[0]))
        return {"specs": tuple(specs)}
