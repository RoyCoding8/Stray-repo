"""Finite-support audit and qualified panels for the two S09 pilot worlds.

Both pilot worlds are finite, and their finiteness is small enough to
exhaust. `second_active` draws a strict total order on four named jobs, so
the world admits exactly 4! = 24 hidden targets. `boolean_rule` draws four
distinct members of a 224-member hypothesis class, so it admits
P(224, 4) = 2450745024. A seed is a coordinate in that support, not an
instance: drawing 12 seeds from 24 targets returns 11 distinct targets
with probability high enough that a panel built by seed enumeration is
reporting replication where none exists.

This module is the lever. It makes the support, the target identity, the
split overlap, the difficulty and the view separation computable from the
code rather than asserted in prose, and it emits a panel only when every
check passes, so an unqualified panel cannot be constructed by accident.
Lanes I and G consume `build_panel` and `audit_panel` rather than
enumerating seeds themselves.

`target_digest` is a host-side summary of the hidden target. It never
enters a policy-visible view; it exists so two cells can be compared for
identity without either target being disclosed.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from itertools import permutations
from typing import Any, Callable, Sequence

from . import boolean_rule
from . import second_active

ORDERING = "ordering"
BOOLEAN = "boolean"

DEV = "dev"
QUAL = "qual"
AUDIT = "audit"
SPLITS = (DEV, QUAL, AUDIT)

# The Boolean world is scored per state, so no probe set is canonical. A
# difficulty number is only comparable across instances when every arm is
# charged the same reference schedule, and nothing in the instrument pins
# one. This is the schedule the panel reports difficulty under, named so a
# reader can see the number is conditional on it.
REFERENCE_PROBES = (0, 1, 2, 3, 4, 5, 6, 7)

REFERENCE_ORDERING_POLICY = "balance-survivor-set"

# Seeds per split a panel builder will scan before it declares the world
# unable to supply the panel. A world whose first few hundred seeds cover
# its whole support and still cannot fill the request cannot fill it, and
# the bound keeps a defective generator from spinning here.
SCAN_LIMIT = 4096

DIGEST_CHARS = 16


class PanelRefused(Exception):
    def __init__(self, reason: str, detail: Any = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=list).encode()
    ).hexdigest()[:DIGEST_CHARS]


@dataclass(frozen=True)
class WorldSpec:
    """Everything the audit needs about one world, in one row.

    `signature` reduces a task to its hidden target. `support_size` is the
    exact number of distinct targets the generator can draw. `difficulty`
    returns a comparable per-instance cost, or None when the world admits
    none.
    """

    name: str
    instrument: str
    module: Any
    splits: tuple[str, ...]
    signature: Callable[[dict], Any]
    support_size: int
    support_formula: str
    enumerable: bool
    view_keys: tuple[str, ...]
    difficulty: Callable[[dict], int | None]
    difficulty_basis: str


def _ordering_signature(task: dict) -> tuple:
    return tuple(task["order"])


def _boolean_signature(task: dict) -> tuple:
    return tuple(task["tables"])


def _ordering_difficulty(task: dict) -> int:
    return ordering_reference_cost(task["order"])


def _boolean_difficulty(task: dict) -> int | None:
    return boolean_residual_bits(task["tables"], REFERENCE_PROBES)


_ORDERING_PAIRS = tuple((first, second)
                        for index, first in enumerate(second_active.JOB_IDS)
                        for second in second_active.JOB_IDS[index + 1:])
_ALL_ORDERS = tuple(sorted(permutations(second_active.JOB_IDS)))
_MINIMAX_CACHE: dict[tuple, int] = {}


def _ordering_minimax(candidates: tuple) -> int:
    """Fewest comparisons that pin one of `candidates`, worst case.

    A comparison is the only query `ScheduleSession.compare` accepts, and
    it partitions the candidate set by the relative order of one pair of
    jobs. The recursion is exact, not heuristic, so the number it returns
    is a property of the world rather than of a policy.
    """
    if len(candidates) <= 1:
        return 0
    cached = _MINIMAX_CACHE.get(candidates)
    if cached is not None:
        return cached
    best = None
    for left, right in _ORDERING_PAIRS:
        first = tuple(order for order in candidates
                      if order.index(left) < order.index(right))
        second = tuple(order for order in candidates
                       if order.index(left) > order.index(right))
        if not first or not second:
            continue
        worst = 1 + max(_ordering_minimax(first), _ordering_minimax(second))
        if best is None or worst < best:
            best = worst
    _MINIMAX_CACHE[candidates] = best
    return best


def ordering_minimax_queries() -> int:
    """Comparisons needed to identify the target from the start state."""
    return _ordering_minimax(_ALL_ORDERS)


def ordering_reference_cost(order: Sequence[str]) -> int:
    """Queries a fixed comparison policy spends before it can act.

    The policy compares the pair that most evenly splits the survivors, so
    its cost depends on which comparisons the target happens to make
    informative. This is the per-target number a panel can balance on, and
    it is a policy's cost, not the instance's: the instance's own cost is
    `ordering_minimax_queries()` and is the same for all 24 targets.
    """
    candidates = list(_ALL_ORDERS)
    target = tuple(order)
    queries = 0
    while len(candidates) > 1:
        chosen = None
        for left, right in _ORDERING_PAIRS:
            first = tuple(item for item in candidates
                          if item.index(left) < item.index(right))
            second = tuple(item for item in candidates
                           if item.index(left) > item.index(right))
            if not first or not second:
                continue
            width = max(len(first), len(second))
            if chosen is None or width < chosen[0]:
                chosen = (width, left, right, first, second)
        _, left, right, first, second = chosen
        candidates = list(first if target.index(left) < target.index(right)
                          else second)
        queries += 1
    return queries


def ordering_difficulty_spread() -> dict[int, int]:
    """How many of the 24 targets cost the reference policy each amount."""
    spread: dict[int, int] = {}
    for order in _ALL_ORDERS:
        cost = ordering_reference_cost(order)
        spread[cost] = spread.get(cost, 0) + 1
    return dict(sorted(spread.items()))


def boolean_residual_bits(tables: Sequence[int],
                          probes: Sequence[int]) -> int:
    """Bits of class uncertainty left after a learner sees `probes`.

    Each output bit is an independent draw from the hypothesis class, so
    the number of predictors consistent with the observations is the
    product over output bits of the class members matching that bit at
    every probed input. The result is the log2 of that product, which is
    the same scale for every instance and is therefore comparable across
    arms charged the same probe schedule.
    """
    observed = {x: tuple((table >> x) & 1 for table in tables)
                for x in probes}
    consistent = 1
    for bit in range(boolean_rule.N_OUTPUTS):
        allowed = sum(
            1 for table in boolean_rule.CLASS_TABLES
            if all(((table >> x) & 1) == observed[x][bit] for x in probes))
        if allowed == 0:
            raise PanelRefused("no-class-member-matches-observation",
                               {"probes": tuple(probes)})
        consistent *= allowed
    return int(math.log2(consistent))


WORLD_SPECS: dict[str, WorldSpec] = {
    ORDERING: WorldSpec(
        name=ORDERING,
        instrument=second_active.INSTRUMENT_ID,
        module=second_active,
        splits=second_active.SPLITS,
        signature=_ordering_signature,
        support_size=math.factorial(len(second_active.JOB_IDS)),
        support_formula="4! strict total orders on four named jobs",
        enumerable=True,
        view_keys=("action_schema", "hypothesis_class", "instrument",
                   "max_queries", "observed", "remaining", "split",
                   "task_id"),
        difficulty=_ordering_difficulty,
        difficulty_basis=(
            "queries spent by the %s comparison policy; the instance's own "
            "minimax cost is %d for every target"
            % (REFERENCE_ORDERING_POLICY, ordering_minimax_queries()))),
    BOOLEAN: WorldSpec(
        name=BOOLEAN,
        instrument=boolean_rule.INSTRUMENT_ID,
        module=boolean_rule,
        splits=boolean_rule.SPLITS,
        signature=_boolean_signature,
        support_size=math.perm(len(boolean_rule.CLASS_TABLES),
                               boolean_rule.N_OUTPUTS),
        support_formula="P(224, 4) ordered quadruples of distinct class members",
        enumerable=False,
        view_keys=("action_schema", "hypothesis_class", "instrument",
                   "max_queries", "observed", "remaining", "split",
                   "task_id"),
        difficulty=_boolean_difficulty,
        difficulty_basis=(
            "log2 of the predictors consistent with the observations at "
            "inputs %s; conditional on that probe schedule, which the "
            "instrument does not otherwise pin" % (list(REFERENCE_PROBES),))),
}


def spec_for(world: str) -> WorldSpec:
    spec = WORLD_SPECS.get(world)
    if spec is None:
        raise PanelRefused("unknown-world", {"world": world})
    return spec


def make_task(world: str, split: str, seed: int) -> dict:
    return spec_for(world).module.make_task(split, seed)


def target_signature(world: str, task: dict) -> Any:
    return spec_for(world).signature(task)


def target_digest(world: str, task: dict) -> str:
    return _digest(spec_for(world).signature(task))


def enumerate_support(world: str) -> tuple:
    """Every hidden target the world admits, or refuse if too many to hold.

    The ordering world has 24 and returns them. The Boolean world has
    2450745024 and refuses rather than materialising a tuple of targets
    nobody will read.
    """
    spec = spec_for(world)
    if not spec.enumerable:
        raise PanelRefused("support-not-enumerable",
                           {"support_size": spec.support_size,
                            "support_formula": spec.support_formula})
    return _ALL_ORDERS


def collision_probability(world: str, instances: int) -> float:
    """Chance a naive seed panel of `instances` draws is all-distinct.

    Reported so a panel built by enumerating seeds is read with the right
    prior. The probability is over random draws, not over this
    generator's actual output, which is why the panel is verified by
    signature rather than by this number.
    """
    support = spec_for(world).support_size
    if instances > support:
        return 0.0
    product = 1.0
    for index in range(instances):
        product *= (support - index) / support
    return product


@dataclass(frozen=True)
class Cell:
    world: str
    split: str
    seed: int
    task_id: str
    target_digest: str
    difficulty: int | None


@dataclass(frozen=True)
class Panel:
    world: str
    cells: tuple[Cell, ...]
    support_size: int
    support_formula: str
    difficulty_basis: str
    reference_probes: tuple[int, ...] | None

    def by_split(self, split: str) -> tuple[Cell, ...]:
        return tuple(cell for cell in self.cells if cell.split == split)

    def as_dict(self) -> dict:
        return asdict(self)


def build_panel(world: str, *, dev: int, held: int,
                held_splits: Sequence[str] = (QUAL, AUDIT)) -> Panel:
    """A panel whose cells are distinct by target, not by seed.

    Seeds are scanned in order and a seed is taken only when its target
    signature has not already been used, so the panel is qualified by
    construction rather than by inspection afterwards. It refuses rather
    than return a panel the world cannot support: asking for more held-out
    targets than the support permits is the defect the handoff asked to be
    caught, and it is caught here.
    """
    spec = spec_for(world)
    requested = dev + held
    if requested > spec.support_size:
        raise PanelRefused("panel-exceeds-finite-support", {
            "requested": requested,
            "support_size": spec.support_size,
            "support_formula": spec.support_formula})
    unknown = [split for split in held_splits if split not in spec.splits]
    if unknown:
        raise PanelRefused("unknown-split", {"splits": unknown})
    if len(set(held_splits)) != len(held_splits):
        raise PanelRefused("repeated-held-split", {"splits": list(held_splits)})
    if held % len(held_splits):
        raise PanelRefused("held-not-divisible-across-splits", {
            "held": held, "held_splits": list(held_splits)})

    used: dict[Any, str] = {}
    cells: list[Cell] = []
    for split, wanted in [(DEV, dev)] + [
            (name, held // len(held_splits)) for name in held_splits]:
        taken = 0
        for seed in range(SCAN_LIMIT):
            if taken == wanted:
                break
            task = spec.module.make_task(split, seed)
            signature = spec.signature(task)
            if signature in used:
                continue
            used[signature] = task["task_id"]
            cells.append(Cell(
                world=world,
                split=split,
                seed=seed,
                task_id=task["task_id"],
                target_digest=_digest(signature),
                difficulty=spec.difficulty(task)))
            taken += 1
        if taken < wanted:
            raise PanelRefused("panel-exceeds-finite-support", {
                "split": split,
                "requested_here": wanted,
                "found_here": taken,
                "support_size": spec.support_size,
                "support_formula": spec.support_formula})
    return Panel(
        world=world,
        cells=tuple(cells),
        support_size=spec.support_size,
        support_formula=spec.support_formula,
        difficulty_basis=spec.difficulty_basis,
        reference_probes=(REFERENCE_PROBES if world == BOOLEAN else None))


def overlapping_targets(panel: Panel) -> dict[str, list[str]]:
    """Targets appearing in more than one split, by the split pair."""
    owners: dict[str, dict[str, str]] = {}
    for cell in panel.cells:
        owners.setdefault(cell.target_digest, {})[cell.split] = cell.task_id
    overlaps: dict[str, list[str]] = {}
    for digest, split_owners in owners.items():
        if len(split_owners) < 2:
            continue
        names = sorted(split_owners)
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                overlaps.setdefault("%s/%s" % (first, second), []).append(digest)
    return overlaps


def duplicate_targets(panel: Panel) -> dict[str, list[str]]:
    """Digests claimed by more than one cell in the same split."""
    owners: dict[str, list[str]] = {}
    for cell in panel.cells:
        owners.setdefault("%s/%s" % (cell.target_digest, cell.split),
                          []).append(cell.task_id)
    return {key: names for key, names in owners.items() if len(names) > 1}


def seed_from_view(view: dict) -> int:
    """The generator seed a public view names.

    Both worlds stamp the seed into `task_id` as its last hyphen-separated
    field, and neither view carries a separate `seed` key. This is the
    fact the leak turns on, so it is one function a test can pin.
    """
    task_id = view.get("task_id")
    split = view.get("split")
    if not isinstance(task_id, str) or not isinstance(split, str):
        raise PanelRefused("view-does-not-name-an-instance", sorted(view))
    try:
        suffix = task_id.rsplit("-", 1)[1]
    except IndexError as exc:
        raise PanelRefused("unexpected-task-id", {"task_id": task_id}) from exc
    if _rejects_as_digest(suffix):
        raise PanelRefused("unexpected-task-id", {"task_id": task_id})
    try:
        return int(suffix)
    except ValueError as exc:
        raise PanelRefused("unexpected-task-id", {"task_id": task_id}) from exc


# A keyed id is 12 hex characters, so it comes out all-decimal about 0.5%
# of the time - `order-qual-895074405257` is one. `seed_from_view` cannot
# tell that from a genuine seed by shape alone, so it returned the wrong
# seed silently and `derive_target_from_view` then computed a wrong
# target, which made `view_leaks_target` answer False for the wrong
# reason. A 12-character decimal cannot be one of our hex digests and
# cannot be a seed either, so the suffix length is the discriminator.
_ID_SUFFIX_LENGTH = 12


def _rejects_as_digest(suffix: str) -> bool:
    """True when the trailing field is too long to be a generator seed.

    Seeds in this study are small integers - the frozen bundles name 3, 7,
    11, 23 - so a 12-character decimal is not one. Refusing it keeps
    `view_leaks_target` meaningful: a leak is reported only when a
    published id really does hand back the seed, not when a digest happens
    to look numeric.
    """
    return suffix.isdigit() and len(suffix) >= _ID_SUFFIX_LENGTH


def derive_target_from_view(world: str, view: dict) -> Any:
    """The hidden target a policy holding only the public view computes.

    Both generators are pure functions of `(split, seed)` and the view
    names both, so the target is recoverable without a single query. This
    returns it, so `view_leaks_target` can compare it against the real
    target and report the leak as a measured fact.
    """
    spec = spec_for(world)
    return spec.signature(
        spec.module.make_task(view["split"], seed_from_view(view)))


def view_leaks_target(world: str, view: dict, task: dict) -> bool:
    """Whether the view alone determines the target, in the real world.

    A view whose `task_id` does not reduce to a generator seed cannot
    reach the target, so it does not leak. That case is the world after
    the fix rather than a corner case, and it is why the check reads as a
    predicate over a view rather than a fact about a world.
    """
    try:
        recovered = derive_target_from_view(world, view)
    except PanelRefused:
        return False
    return recovered == target_signature(world, task)


def difficulty_report(panel: Panel) -> dict:
    """Per-split difficulty, and the spread the panel can balance on."""
    by_split: dict[str, dict[str, Any]] = {}
    for split in SPLITS:
        cells = panel.by_split(split)
        if not cells:
            continue
        values = [cell.difficulty for cell in cells
                  if cell.difficulty is not None]
        by_split[split] = {
            "cells": len(cells),
            "difficulty": sorted(values),
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }
    pooled = [cell.difficulty for cell in panel.cells
              if cell.difficulty is not None]
    return {
        "basis": panel.difficulty_basis,
        "reference_probes": (list(panel.reference_probes)
                             if panel.reference_probes else None),
        "by_split": by_split,
        "pooled_min": min(pooled) if pooled else None,
        "pooled_max": max(pooled) if pooled else None,
    }


def audit_panel(panel: Panel) -> dict:
    """Run every check the handoff names and report each one by name.

    A check that passes says what was verified. A check that fails says
    what is wrong and returns `qualified: false`, so a panel that claims
    eight held-out targets over a four-target world cannot be mistaken for
    one that has eight.
    """
    overlaps = overlapping_targets(panel)
    duplicates = duplicate_targets(panel)
    difficulties = difficulty_report(panel)
    total = len(panel.cells)
    return {
        "world": panel.world,
        "support_size": panel.support_size,
        "support_formula": panel.support_formula,
        "cell_count": total,
        "distinct_targets": len({cell.target_digest for cell in panel.cells}),
        "distinct_targets_per_split": {
            split: len({cell.target_digest for cell in panel.by_split(split)})
            for split in SPLITS if panel.by_split(split)},
        "overlapping_targets": overlaps,
        "overlapping_target_count": sum(len(v) for v in overlaps.values()),
        "duplicate_targets": duplicates,
        "difficulty": difficulties,
        "difficulty_reported": any(
            entry["difficulty"] for entry in difficulties["by_split"].values()),
        "difficulty_spread": (
            difficulties["pooled_max"] - difficulties["pooled_min"]
            if difficulties["pooled_min"] is not None else None),
        "checks": {
            "targets_distinct": not duplicates and len(
                {cell.target_digest for cell in panel.cells}) == total,
            "splits_disjoint": not overlaps,
            "panel_within_support": total <= panel.support_size,
            "difficulty_reported": any(
                entry["difficulty"]
                for entry in difficulties["by_split"].values()),
        },
        "qualified": (not duplicates and not overlaps
                      and total <= panel.support_size),
    }


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", choices=sorted(WORLD_SPECS))
    parser.add_argument("--dev", type=int, default=4)
    parser.add_argument("--held", type=int, default=8)
    args = parser.parse_args(argv)

    if args.world:
        report = audit_panel(
            build_panel(args.world, dev=args.dev, held=args.held))
    else:
        report = {"worlds": {
            name: {
                "support_size": spec.support_size,
                "support_formula": spec.support_formula,
                "enumerable": spec.enumerable,
                "requested_panel": args.dev + args.held,
                "panel_fits_support":
                    args.dev + args.held <= spec.support_size,
                "naive_seed_panel_all_distinct_probability":
                    collision_probability(name, args.dev + args.held),
                "difficulty_basis": spec.difficulty_basis,
            }
            for name, spec in sorted(WORLD_SPECS.items())}}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
