"""Inventory the independent units and statistical ceiling of the AD01 panel."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import permutations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from experiments.ad01 import independent_units
from experiments.ad01.worlds import FROZEN_DIR

FAMILIES = ("software", "graph")
CLUSTER_RULE = "(family, template)"
CLUSTER_RATIONALE = (
    "The generator reuses each (family, template) pair across cells and worlds, "
    "and reuses dev/within pairs across splits. A new cell in an existing pair is "
    "another draw from the same generation family, not a new independent unit."
)
TASK_ID = re.compile(
    r"ad01-w(?P<world>\d+)-(?P<kind>dev|within|transfer)-"
    r"(?:sw|gr)-(?P<index>\d+)$"
)
DEFAULT_ALPHA = 0.05


@dataclass(frozen=True)
class Cell:
    task_id: str
    family: str
    template: str
    world: int
    kind: str
    index: int


@dataclass(frozen=True)
class Cluster:
    family: str
    template: str
    task_ids: tuple[str, ...]


@dataclass(frozen=True)
class Power:
    cluster_count: int
    minimum_p: float | None
    powered: bool
    required_clusters: int | None


@dataclass(frozen=True)
class IsomorphicPair:
    dev_task_id: str
    within_task_id: str


@dataclass(frozen=True)
class Inventory:
    panel_root: str
    cell_count: int
    cells: tuple[Cell, ...]
    cluster_count: int
    clusters: tuple[Cluster, ...]
    isomorphic_pair_count: int
    isomorphic_pairs: tuple[IsomorphicPair, ...]

    def family_cluster_count(self, family: str) -> int:
        return sum(cluster.family == family for cluster in self.clusters)

    def available_family_coverage(self) -> dict[str, dict[str, Any]]:
        """Describe the generation families available in this inventory.

        A family count is coverage of the frozen panel. It does not say how
        many of those families a particular assessment actually used.
        """
        coverage: dict[str, dict[str, Any]] = {}
        for family in FAMILIES:
            templates = sorted({cluster.template for cluster in self.clusters
                                if cluster.family == family})
            coverage[family] = {
                "template_count": len(templates),
                "templates": templates,
            }
        return coverage

    def decision(self, alpha: float = DEFAULT_ALPHA) -> dict[str, Any]:
        required = minimum_clusters_for_alpha(alpha)
        family_power = {
            family: {
                "cluster_count": self.family_cluster_count(family),
                "minimum_p": minimum_sign_flip_p(
                    self.family_cluster_count(family)),
                "powered": self.family_cluster_count(family) >= required,
                "required_clusters": required,
            }
            for family in FAMILIES
        }
        family_power["additional_generation_families_required"] = {
            family: max(0, required - self.family_cluster_count(family))
            for family in FAMILIES
        }
        total = asdict(Power(
            cluster_count=self.cluster_count,
            minimum_p=minimum_sign_flip_p(self.cluster_count),
            powered=self.cluster_count >= required,
            required_clusters=required,
        ))
        resolution = {
            "all": minimum_p_resolution(self.cluster_count, alpha),
            **{
                family: minimum_p_resolution(
                    self.family_cluster_count(family), alpha)
                for family in FAMILIES
            },
        }
        return {
            "alpha": alpha,
            "cluster_rule": CLUSTER_RULE,
            "cluster_rationale": CLUSTER_RATIONALE,
            "cell_count": self.cell_count,
            "cluster_count": self.cluster_count,
            "isomorphic_dev_within_pair_count": self.isomorphic_pair_count,
            "minimum_p_resolution": resolution,
            "available_family_coverage": self.available_family_coverage(),
            "observably_distinct_units": self.observably_distinct_units(),
            "verdict": "powered" if all(
                result["powered"] for result in family_power.values()
            ) else "cannot_be_powered",
            "power": {"all": total, **family_power},
        }

    def observably_distinct_units(self) -> dict[str, Any]:
        """Cluster counts beside the behaviours those clusters exhibit.

        The cluster rule counts `(family, template)` pairs, and it counts
        them correctly. What it cannot say is whether those templates are
        different draws or different names for one draw, because nothing
        checked. Measured per family and reported beside the count rather
        than in place of it: a family whose templates share one observable
        behaviour has fewer independent units than its cluster count, and
        adding a template to it does not move that number.
        """
        measured: dict[str, Any] = {}
        for family in FAMILIES:
            if family == "software":
                observation = independent_units.software_family_observation()
                measured[family] = observation.as_dict()
            else:
                measured[family] = {
                    "family": family,
                    "template_count": self.family_cluster_count(family),
                    "signature_count": None,
                    "collapses": None,
                    "note": "no observable-behaviour measure is defined for "
                            "this family",
                }
        return measured


def minimum_sign_flip_p(cluster_count: int) -> float | None:
    if cluster_count < 0:
        raise ValueError("cluster count must be non-negative")
    if cluster_count == 0:
        return None
    return 2.0 ** (1 - cluster_count)


def minimum_p_resolution(cluster_count: int,
                         alpha: float = DEFAULT_ALPHA) -> dict[str, Any]:
    """Return the sign-flip p-value floor without calling it statistical power."""
    required = minimum_clusters_for_alpha(alpha)
    minimum_p = minimum_sign_flip_p(cluster_count)
    return {
        "cluster_count": cluster_count,
        "minimum_p": minimum_p,
        "required_clusters": required,
        "meets_alpha_resolution": (
            minimum_p is not None and minimum_p <= alpha),
    }


def minimum_clusters_for_alpha(alpha: float) -> int:
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between zero and one")
    return math.floor(math.log(alpha) / math.log(0.5)) + 2


def canonical_graph_form(task: Mapping[str, Any]) -> tuple[tuple[int, int], ...]:
    vertices = task["vertices"]
    edges = task["edges"]
    best: tuple[tuple[int, int], ...] | None = None
    for order in permutations(vertices):
        positions = {vertex: index for index, vertex in enumerate(order)}
        form = tuple(sorted(
            (min(positions[first], positions[second]),
             max(positions[first], positions[second]))
            for first, second in edges
        ))
        if best is None or form < best:
            best = form
    if best is None:
        raise ValueError("graph must have at least one edge")
    return best


def isomorphic_dev_within_pairs(cells: Iterable[Cell],
                                tasks: Mapping[str, Mapping[str, Any]],
                                ) -> tuple[IsomorphicPair, ...]:
    by_world_kind: dict[tuple[int, str], dict[int, Cell]] = defaultdict(dict)
    for cell in cells:
        if cell.family == "graph" and cell.kind in ("dev", "within"):
            key = (cell.world, cell.kind)
            by_world_kind[key][cell.index] = cell
    pairs = []
    for world in sorted({cell.world for cell in cells}):
        dev = by_world_kind.get((world, "dev"), {})
        within = by_world_kind.get((world, "within"), {})
        for index in sorted(set(dev) & set(within)):
            first = canonical_graph_form(tasks[dev[index].task_id])
            second = canonical_graph_form(tasks[within[index].task_id])
            if first == second:
                pairs.append(IsomorphicPair(
                    dev[index].task_id, within[index].task_id))
    return tuple(pairs)


def build_inventory(root: Path | str = FROZEN_DIR) -> Inventory:
    root = Path(root)
    tasks = {}
    cells = []
    for path in sorted(root.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        task = json.loads(path.read_text())
        match = TASK_ID.fullmatch(task.get("task_id", ""))
        if match is None:
            raise ValueError("bad task id: %s" % task.get("task_id"))
        cells.append(Cell(
            task_id=task["task_id"],
            family=task["family"],
            template=task["template"],
            world=int(match.group("world")),
            kind=match.group("kind"),
            index=int(match.group("index")),
        ))
        tasks[task["task_id"]] = task
    grouped = defaultdict(list)
    for cell in cells:
        grouped[(cell.family, cell.template)].append(cell.task_id)
    clusters = tuple(
        Cluster(family, template, tuple(sorted(task_ids)))
        for (family, template), task_ids in sorted(grouped.items())
    )
    pairs = isomorphic_dev_within_pairs(cells, tasks)
    return Inventory(
        panel_root=str(root.resolve()),
        cell_count=len(cells),
        cells=tuple(sorted(cells, key=lambda cell: cell.task_id)),
        cluster_count=len(clusters),
        clusters=clusters,
        isomorphic_pair_count=len(pairs),
        isomorphic_pairs=pairs,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-root", type=Path, default=FROZEN_DIR)
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    args = parser.parse_args(argv)
    inventory = build_inventory(args.panel_root)
    result = {
        "inventory": asdict(inventory),
        "decision": inventory.decision(args.alpha),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
