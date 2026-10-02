"""M3 authored baseline: version-space Boolean-rule learner.

Maintains, per output bit, the surviving hypothesis set consistent with
every observed query. Chooses the unqueried input with the largest total
disagreement across the four version spaces, smallest index on ties.
Predicts the version-space member nearest the majority vote, so the
committed predictor is always legal and consistent with all queries.
Deterministic in the seed. Tuned on development instances only.
"""

from __future__ import annotations

import random

from . import boolean_rule as br


class VersionSpaceLearner:
    def __init__(self, class_tables: tuple, seed: int):
        self._tables = tuple(class_tables)
        self._rng = random.Random(seed)
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
        scored = [(self._disagreement(x), x) for x in open_inputs]
        best = max(s for s, _ in scored)
        cands = sorted(x for s, x in scored if s == best)
        return cands[self._rng.randrange(len(cands))]

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
