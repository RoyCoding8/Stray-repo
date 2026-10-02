"""Fixed-seed development/check/evaluation split generators.

Benefit panel per contract section 7: 6 development, 4 candidate-check and
8 frozen-evaluation tasks per family. Plus 4 frozen scope/validity controls
and a mixed subsequent-use panel (1 supported source, 1 supported transfer,
2 outside-scope) from distinct fixed seeds. Templates/structural patterns
as well as seeds are held out of development: C9 cycles and shared-edge
double cycles appear only in evaluation; see INVENTORY.md.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from . import graphs, software

SOFTWARE_SEEDS = {"development": 1101, "check": 1201, "evaluation": 1301}
GRAPH_SEEDS = {"development": 2101, "check": 2201, "evaluation": 2301}
CONTROL_SEED = 3101
USE_SEED = 4101
SPLIT_COUNTS = {"development": 6, "check": 4, "evaluation": 8}

MANIFEST_VERSION = "RPR-01/1"

SOFTWARE_TEMPLATES = {
    "development": ("stale-read core + prefix/suffix distractors",
                    "stale-clear core + prefix/suffix distractors"),
    "check": ("stale-read core, denser distractors",
              "stale-clear core, denser distractors"),
    "evaluation": ("held-out seeds: new key/value alphabets per index, "
                   "longer suffix runs, both faults"),
}

GRAPH_TEMPLATES = {
    "development": ("C5+tree", "C7+tree", "C5+shared-vertex",
                    "C5+disconnected-path", "C7+2-trees",
                    "C5+even-cycle-distractor+isolated"),
    "check": ("C7+tree", "C5+shared-vertex",
              "C5+star-distractor", "C7+path-distractor"),
    "evaluation": ("C9+tree", "C9+isolated", "C5+shared-edge",
                   "C5+shared-vertex", "C5+joined-by-path", "C7+tree",
                   "C5+even-cycle-distractor", "C7+path-distractor"),
}

GRAPH_TEMPLATE_NOTES = {
    "development": "odd lengths C5/C7 only; single and shared-vertex doubles",
    "check": "same patterns as development, held-out seeds",
    "evaluation": ("held-out odd length C9, held-out shared-edge and "
                   "joined-by-path patterns; single-cycle+tree and "
                   "distractor patterns recur with held-out seeds"),
}


def _rng(*parts) -> random.Random:
    key = "-".join(str(part) for part in parts)
    seed = int(hashlib.sha256(key.encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def _distractor_ops(rng: random.Random, keys, n: int, ids, avoid=()) -> list:
    usable = [k for k in keys if k not in avoid]
    ops = []
    for _ in range(n):
        roll = rng.random()
        if roll < 0.45:
            ops.append({"op": "set", "key": rng.choice(usable),
                        "value": "v%d" % rng.randint(1, 4)})
        elif roll < 0.75:
            ops.append({"op": "get", "key": rng.choice(usable),
                        "id": "o%d" % next(ids)})
        elif roll < 0.85:
            ops.append({"op": "clear"})
        else:
            ops.append({"op": "del", "key": rng.choice(usable)})
    return ops


def generate_software(split: str, index: int) -> dict:
    rng = _rng("software", SOFTWARE_SEEDS[split], index)
    fault = software.FAULTS[(index + (1 if split == "check" else 0)) % 2]
    keys = list(software.KEYS)
    rng.shuffle(keys)
    hero, others = keys[0], keys[1:]
    val1, val2 = "v%d" % (index % 4 + 1), "v%d" % ((index + 2) % 4 + 1)
    ids = iter(range(1000))
    prefix = _distractor_ops(rng, keys, rng.randint(2, 5), ids, avoid=(hero,))
    ops = list(prefix)
    if fault == "stale-read":
        ops.append({"op": "set", "key": hero, "value": val1})
        ops.append({"op": "set", "key": hero, "value": val2})
        witness_id = "o%d" % next(ids)
        ops.append({"op": "get", "key": hero, "id": witness_id})
    else:
        for other in others:
            ops.append({"op": "set", "key": other,
                        "value": "v%d" % rng.randint(1, 4)})
        ops.append({"op": "set", "key": hero, "value": val1})
        ops.append({"op": "clear"})
        witness_id = "o%d" % next(ids)
        ops.append({"op": "get", "key": hero, "id": witness_id})
    suffix = _distractor_ops(rng, keys, rng.randint(2, 7), ids)
    ops.extend(suffix)
    ops = ops[:software.MAX_OPS]
    ref = software.reference_run(ops)[witness_id]
    bad = software.faulty_run(ops, fault)[witness_id]
    assert ref != bad, (split, index, fault)
    task_id = "sw-%s-%02d" % (split[:3], index)
    task = {"family": "software", "task_id": task_id, "fault": fault,
            "ops": ops,
            "witness": {"observation": witness_id, "ref": ref, "faulty": bad},
            "seed": SOFTWARE_SEEDS[split] + index}
    assert software.task_is_valid(task)
    assert len({k for op in ops for k in [op.get("key")] if k}) >= 2
    return task


def _cycle_vertices(length: int, start: int):
    vertices = list(range(start, start + length))
    edges = [[vertices[i], vertices[(i + 1) % length]] for i in range(length)]
    return vertices, edges


def _attach_path(vertices: list, edges: list, root: int, length: int,
                 rng: random.Random) -> None:
    current = root
    for _ in range(length):
        fresh = max(vertices) + 1
        vertices.append(fresh)
        edges.append([current, fresh])
        current = fresh


def _add_component(vertices: list, edges: list, kind: str, rng: random.Random) -> None:
    start = max(vertices) + 1 if vertices else 0
    if kind == "isolated":
        vertices.append(start)
    elif kind == "path":
        fresh = [start, start + 1, start + 2][:rng.randint(2, 3)]
        vertices.extend(fresh)
        edges.extend([[fresh[i], fresh[i + 1]] for i in range(len(fresh) - 1)])
    elif kind == "even-cycle":
        size = rng.choice((4, 6))
        cycle_v, cycle_e = _cycle_vertices(size, start)
        vertices.extend(cycle_v)
        edges.extend(cycle_e)
    elif kind == "star":
        vertices.append(start)
        for offset in range(1, rng.randint(2, 4)):
            vertices.append(start + offset)
            edges.append([start, start + offset])


def _assemble(spec: str, rng: random.Random) -> tuple:
    vertices: list = []
    edges: list = []
    if spec.startswith("C"):
        length = int(spec[1])
        cycle_v, cycle_e = _cycle_vertices(length, 0)
        vertices.extend(cycle_v)
        edges.extend(cycle_e)
        rest = spec[2:]
    else:
        rest = spec
    for token in rest.split("+"):
        if not token:
            continue
        if token == "tree":
            _attach_path(vertices, edges, rng.choice(vertices), 1, rng)
        elif token == "2-trees":
            for _ in range(2):
                _attach_path(vertices, edges, rng.choice(vertices),
                             rng.randint(1, 2), rng)
        elif token == "shared-vertex":
            shared = rng.choice(vertices[:5])
            anchor = max(vertices) + 1
            ring = [shared] + list(range(anchor, anchor + 4))
            vertices.extend(range(anchor, anchor + 4))
            edges.extend([[ring[i], ring[(i + 1) % 5]] for i in range(5)])
        elif token == "shared-edge":
            anchor = max(vertices) + 1
            extra = list(range(anchor, anchor + 3))
            vertices.extend(extra)
            ring = [0, extra[0], extra[1], extra[2], 1]
            edges.extend([[ring[i], ring[(i + 1) % 5]] for i in range(5)
                          if {ring[i], ring[(i + 1) % 5]} != {0, 1}])
        elif token == "joined-by-path":
            anchor = max(vertices) + 1
            ring = list(range(anchor, anchor + 5))
            vertices.extend(ring)
            edges.extend([[ring[i], ring[(i + 1) % 5]] for i in range(5)])
            edges.append([vertices[0], ring[0]])
        elif token in ("disconnected-path", "path-distractor"):
            _add_component(vertices, edges, "path", rng)
        elif token == "even-cycle-distractor":
            _add_component(vertices, edges, "even-cycle", rng)
        elif token == "star-distractor":
            _add_component(vertices, edges, "star", rng)
        elif token == "isolated":
            _add_component(vertices, edges, "isolated", rng)
        else:
            raise ValueError("unknown-template-token %r" % token)
    return vertices, edges


def generate_graph(split: str, index: int) -> dict:
    templates = GRAPH_TEMPLATES[split]
    spec = templates[index % len(templates)]
    for attempt in range(25):
        rng = _rng("graph", GRAPH_SEEDS[split], index, attempt)
        vertices, edges = _assemble(spec, rng)
        task_id = "gr-%s-%02d" % (split[:3], index)
        task = {"family": "graph", "task_id": task_id,
                "vertices": sorted(vertices),
                "edges": [sorted(e) for e in edges],
                "seed": GRAPH_SEEDS[split] + index}
        try:
            parsed = graphs.parse_graph(task)
        except graphs.GraphInvalid:
            continue
        if graphs.witness_holds(parsed):
            return task
    raise AssertionError("no valid graph for %s %d" % (split, index))


def _agreeing_observation(task: dict) -> str:
    ref = software.reference_run(task["ops"])
    bad = software.faulty_run(task["ops"], task["fault"])
    for oid, seen in ref.items():
        if bad.get(oid) == seen and oid != task["witness"]["observation"]:
            return oid
    raise AssertionError("no agreeing observation")


def generate_controls() -> list:
    rng = _rng("controls", CONTROL_SEED)
    _ = rng
    base = generate_software("development", 0)
    agreeing = _agreeing_observation(base)
    ref = software.reference_run(base["ops"])
    wrong = dict(base)
    wrong["task_id"] = "ctrl-sw-wrong-obs"
    wrong["witness"] = {"observation": agreeing, "ref": ref[agreeing],
                        "faulty": ref[agreeing]}
    broken = dict(base)
    broken["task_id"] = "ctrl-sw-invalid"
    broken["ops"] = list(base["ops"]) + [{"op": "explode", "key": "a"}]
    triangle = {"family": "graph", "task_id": "ctrl-gr-triangle",
                "vertices": [0, 1, 2, 3],
                "edges": [[0, 1], [1, 2], [2, 0], [2, 3]], "seed": CONTROL_SEED}
    assert not graphs.witness_holds(triangle)
    assert graphs.has_triangle([0, 1, 2, 3], triangle["edges"])
    bipartite = {"family": "graph", "task_id": "ctrl-gr-bipartite",
                 "vertices": [0, 1, 2, 3, 4, 5],
                 "edges": [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 0]],
                 "seed": CONTROL_SEED}
    assert not graphs.witness_holds(bipartite)
    assert graphs.is_bipartite(bipartite["vertices"], bipartite["edges"])
    assert not software.task_is_valid(wrong)
    return [wrong, broken, triangle, bipartite]


def generate_use_panel() -> list:
    rng = _rng("use", USE_SEED)
    _ = rng
    supported_sw = generate_software("evaluation", 0)
    supported_sw = dict(supported_sw, task_id="use-sw-supported")
    supported_gr = generate_graph("evaluation", 0)
    supported_gr = dict(supported_gr, task_id="use-gr-supported")
    big_sw = generate_software("evaluation", 1)
    inflated = list(big_sw["ops"])
    while len(inflated) <= software.MAX_OPS:
        inflated.append({"op": "set", "key": "a", "value": "v9"})
    oos_sw = dict(big_sw, task_id="use-sw-out-of-scope", ops=inflated)
    assert len(oos_sw["ops"]) > software.MAX_OPS
    big_gr = generate_graph("evaluation", 1)
    extra = max(big_gr["vertices"]) + 1
    oos_gr = dict(big_gr, task_id="use-gr-out-of-scope",
                  vertices=sorted(big_gr["vertices"] + [extra, extra + 1]))
    assert len(oos_gr["vertices"]) > graphs.MAX_VERTICES
    return [supported_sw, supported_gr, oos_sw, oos_gr]


def build_panel() -> dict:
    panel: dict = {"software": {}, "graph": {}}
    for split, count in SPLIT_COUNTS.items():
        panel["software"][split] = [generate_software(split, i) for i in range(count)]
        panel["graph"][split] = [generate_graph(split, i) for i in range(count)]
    panel["controls"] = generate_controls()
    panel["use"] = generate_use_panel()
    return panel


def _digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_fixtures(root) -> dict:
    root = Path(root)
    panel = build_panel()
    manifest = {"version": MANIFEST_VERSION, "files": []}
    layout = []
    for split in SPLIT_COUNTS:
        for task in panel["software"][split]:
            layout.append(("software/%s" % split, task))
        for task in panel["graph"][split]:
            layout.append(("graphs/%s" % split, task))
    for task in panel["controls"]:
        layout.append(("controls", task))
    for task in panel["use"]:
        layout.append(("use", task))
    for directory, task in layout:
        target = root / directory / ("%s.json" % task["task_id"])
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(task, sort_keys=True, indent=2) + "\n").encode()
        target.write_bytes(raw)
        manifest["files"].append({"path": str(target.relative_to(root)),
                                  "task_id": task["task_id"],
                                  "digest": _digest_bytes(raw),
                                  "bytes": len(raw)})
    manifest["files"].sort(key=lambda entry: entry["path"])
    manifest_raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    (root / "manifest.json").write_bytes(manifest_raw)
    (root / "manifest.sha256").write_text(_digest_bytes(manifest_raw) + "\n")
    return manifest


def verify_manifest(root) -> list:
    root = Path(root)
    manifest_raw = (root / "manifest.json").read_bytes()
    pinned = (root / "manifest.sha256").read_text().strip()
    problems = []
    if _digest_bytes(manifest_raw) != pinned:
        problems.append("manifest-hash-mismatch")
        return problems
    manifest = json.loads(manifest_raw)
    seen = set()
    for entry in manifest.get("files", []):
        path = entry.get("path", "")
        if path in seen:
            problems.append("duplicate-file %s" % path)
        seen.add(path)
        target = root / path
        if not target.is_file():
            problems.append("missing-file %s" % path)
            continue
        if _digest_bytes(target.read_bytes()) != entry.get("digest"):
            problems.append("digest-mismatch %s" % path)
    return problems


def load_task(path) -> dict:
    raw = json.loads(Path(path).read_text())
    if raw.get("family") == "software":
        return software.parse_task(raw)
    return graphs.parse_graph(raw)
