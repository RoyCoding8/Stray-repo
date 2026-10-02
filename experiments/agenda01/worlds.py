"""AG01-EXP public world fixtures: 32 scored worlds in 8 families x 4 variants.

Policy-visible fields only: measurement specs as shared domain knowledge,
probe costs from {2, 4, 8}, exogenous event schedules, initial option seeds
and end-use task specs. Latent world facts live exclusively in grader.py.
"""

from __future__ import annotations

import hashlib

PROBE_COSTS = (2, 4, 8)
SEED_CLASSES = ("bottleneck", "transfer", "instrument-gaps", "speculative")
TICKS = 24

FAMILY_NAMES = (
    "repeated-expensive-success",
    "appealing-uninformative",
    "missing-instrument",
    "duplicate-branched",
    "counterexample-negative-history",
    "replication-noisy",
    "unresolved-wakeup",
    "sparse-stopping",
)

ADVERSE = {
    0: "construction-exceeds-reuse",
    1: "weak-signal-opens-probe",
    2: "instrument-never-arrives",
    3: "near-dupes-stay-separate",
    4: "dep-change-voids-negative",
    5: "premature-stopping-loses-finding",
    6: "dup-outoforder-single-effect",
    7: "late-event-opens-opportunity",
}

Q_LOSING_WORLD = "w23"
CONTROL_WORLDS = ("w28", "w29")

WORLD_SEEDS = {
    "w23": 1003,
}


def draw(seed: int, *parts: str) -> float:
    blob = "|".join([str(seed)] + [str(p) for p in parts]).encode()
    return int.from_bytes(hashlib.sha256(blob).digest()[:8], "big") / 2**64


def _props() -> dict:
    return {
        f"p{i}": {"scope": f"s{i % 2}", "dep": f"d{i % 2}", "dep_version": 1}
        for i in range(8)
    }


def _tasks(world_id: str) -> list:
    return [{"task_id": f"{world_id}-t{i}", "prop": f"p{i}"} for i in range(8)]


def _probe(key: str, cost: int, observes: list, noise: float = 0.0,
           prereq: dict | None = None, delay: int = 0,
           replication: int | None = None, followup: str | None = None,
           consequences: dict | None = None, product: list | None = None) -> dict:
    assert cost in PROBE_COSTS
    assert 0.0 <= noise < 1.0
    return {"cost": cost, "observes": list(observes), "noise": noise,
            "prereq": prereq, "delay": delay, "replication": replication,
            "followup": followup, "product": product,
            "consequences": consequences or {"true": "adopt-A", "false": "retain-incumbent"}}


def _seed(key: str, cls: str, probe: str, question: str, cap: int = 8) -> dict:
    assert cls in SEED_CLASSES
    return {"option_key": key, "seed_class": cls, "question": question,
            "probe": probe, "cap": cap, "expiry": TICKS}


def _world(family: int, variant: int, probes: dict, seeds: list,
           events: list | None = None, instruments: dict | None = None) -> dict:
    index = family * 4 + variant
    world_id = f"w{index:02d}"
    return {"world_id": world_id, "family": family, "variant": variant,
            "family_name": FAMILY_NAMES[family],
            "adverse": ADVERSE[family] if variant == 3 else None,
            "rng_seed": WORLD_SEEDS.get(world_id, 1000 + index),
            "ticks": TICKS, "props": _props(), "probes": probes,
            "instruments": instruments or {}, "events": events or [],
            "seeds": seeds, "tasks": _tasks(world_id), "scored": True}


def _singles(cost: int, props: list, noise: float = 0.0) -> dict:
    return {f"m{p[1:]}": _probe(f"m{p[1:]}", cost, [p], noise) for p in props}


def _fam0(v: int) -> dict:
    probes = _singles(2, ["p2", "p3", "p4", "p5", "p6", "p7"])
    reach = ["p0", "p1"] if v == 3 else ["p0", "p1", "p2", "p3"]
    probes["build"] = _probe("build", 8, [], product=reach)
    seeds = [_seed("s-build", "bottleneck", "build", "construct shared rig"),
             _seed("s-m2", "transfer", "m2", "measure p2"),
             _seed("s-m4", "instrument-gaps", "m4", "measure p4"),
             _seed("s-m6", "speculative", "m6", "measure p6")]
    return probes, seeds, [], {}


def _fam1(v: int) -> dict:
    probes = {
        "a": _probe("a", 2, ["p0"], followup="a2"),
        "a2": _probe("a2", 2, ["p0"],
                     consequences={"true": "adopt-A", "false": "adopt-A"}),
        "b": _probe("b", 4, ["p1"], followup="b2"),
        "b2": _probe("b2", 2, ["p2"]),
        "c": _probe("c", 2, ["p3"], followup="c2" if v == 3 else None),
        "c2": _probe("c2", 2, ["p4", "p5"]),
    }
    probes.update(_singles(2, ["p6", "p7"]))
    seeds = [_seed("s-a", "speculative", "a", "fluent hypothesis A"),
             _seed("s-b", "bottleneck", "b", "bearing probe B"),
             _seed("s-c", "transfer", "c", "weak signal C"),
             _seed("s-m6", "instrument-gaps", "m6", "measure p6")]
    return probes, seeds, [], {}


def _fam2(v: int) -> dict:
    probes = _singles(2, ["p0", "p1", "p4", "p5", "p6", "p7"])
    probes["deep"] = _probe("deep", 4, ["p2", "p3"],
                            prereq={"instrument": "scope2"})
    arrival = {0: 6, 1: 12, 2: 6, 3: None}[v]
    instruments = {"scope2": {"available_at": arrival}}
    events = [] if arrival is None else [{"tick": arrival, "kind": "instrument",
                                          "key": "scope2"}]
    if v == 3:
        probes["acquire"] = _probe("acquire", 8, [],
                                   consequences={"true": "adopt-A",
                                                 "false": "adopt-A"})
    seeds = [_seed("s-deep", "instrument-gaps", "deep", "await instrument"),
             _seed("s-m0", "bottleneck", "m0", "measure p0"),
             _seed("s-m4", "transfer", "m4", "measure p4"),
             _seed("s-m6", "speculative", "m6", "measure p6")]
    if v == 3:
        seeds.append(_seed("s-acq", "speculative", "acquire", "buy instrument"))
    return probes, seeds, events, instruments


def _fam3(v: int) -> dict:
    probes = _singles(2, ["p0", "p1", "p2", "p3", "p4", "p5", "p6", "p7"])
    probes["m1b"] = _probe("m1b", 4, ["p1"])
    seeds = [_seed("s-dup1", "bottleneck", "m0", "probe p0 quickly"),
             _seed("s-dup2", "transfer", "m0", "p0 probe restated"),
             _seed("s-near1", "instrument-gaps", "m1", "p1 narrow scope"),
             _seed("s-near2", "speculative", "m1b", "p1 wide scope"),
             _seed("s-m4", "bottleneck", "m4", "measure p4")]
    return probes, seeds, [], {}


def _fam4(v: int) -> dict:
    probes = _singles(2, ["p0", "p1", "p2", "p3", "p6", "p7"])
    noise = 0.35 if v == 3 else 0.0
    probes["n1"] = _probe("n1", 2, ["p4"], noise=noise)
    events, prereq = [], None
    if v >= 2:
        events = [{"tick": 8, "kind": "dep-bump", "dep": "d0", "to": 2}]
    if v == 3:
        prereq = {"dep_version": ["d0", 2]}
        probes["n2"] = _probe("n2", 4, ["p5"], prereq=prereq)
    seeds = [_seed("s-n1", "bottleneck", "n1", "scope-limited check"),
             _seed("s-m0", "transfer", "m0", "measure p0"),
             _seed("s-m2", "instrument-gaps", "m2", "measure p2"),
             _seed("s-m6", "speculative", "m6", "measure p6")]
    if v == 3:
        seeds.append(_seed("s-n2", "transfer", "n2", "recheck after change"))
    return probes, seeds, events, {}


def _fam5(v: int) -> dict:
    probes = _singles(2, ["p0", "p1", "p2", "p3", "p4", "p6", "p7"])
    cap = 16
    if v == 0:
        probes["r"] = _probe("r", 4, ["p5"])
    elif v == 1:
        probes["r"] = _probe("r", 4, ["p5"], noise=0.35, replication=3)
    elif v == 2:
        probes["r"] = _probe("r", 2, ["p5"], replication=5)
    else:
        probes["r"] = _probe("r", 4, ["p5"], noise=0.35,
                             consequences={"true": "retain-incumbent",
                                           "false": "retain-incumbent"})
    seeds = [_seed("s-r", "bottleneck", "r", "noisy readout", cap=cap),
             _seed("s-m0", "transfer", "m0", "measure p0"),
             _seed("s-m2", "instrument-gaps", "m2", "measure p2"),
             _seed("s-m6", "speculative", "m6", "measure p6")]
    return probes, seeds, [], {}


def _fam6(v: int) -> dict:
    probes = _singles(2, ["p0", "p1", "p2", "p3", "p4", "p5", "p7"])
    delay = 2 if v in (1, 3) else 1
    probes["slow"] = _probe("slow", 4, ["p6"], delay=delay)
    seeds = [_seed("s-slow", "instrument-gaps", "slow", "delayed readout"),
             _seed("s-m0", "bottleneck", "m0", "measure p0"),
             _seed("s-m2", "transfer", "m2", "measure p2"),
             _seed("s-m4", "speculative", "m4", "measure p4")]
    return probes, seeds, [], {}


def _fam7(v: int) -> dict:
    probes = _singles(2, ["p0", "p1", "p2", "p3", "p4", "p5", "p6", "p7"])
    events, instruments = [], {}
    classes = ("bottleneck", "transfer", "instrument-gaps", "speculative")
    seeds = [_seed(f"s-m{i}", classes[i % 4], f"m{i}", f"measure p{i}")
             for i in range(8)]
    if v == 3:
        probes["late"] = _probe("late", 4, ["p7"],
                                prereq={"instrument": "late-window"})
        instruments = {"late-window": {"available_at": 18}}
        events = [{"tick": 18, "kind": "instrument", "key": "late-window"}]
        seeds = [_seed("s-m0", "bottleneck", "m0", "measure p0"),
                 _seed("s-m2", "transfer", "m2", "measure p2"),
                 _seed("s-late", "instrument-gaps", "late", "await opening")]
    if v == 2:
        seeds = seeds[:2]
    return probes, seeds, events, instruments


_FAMS = (_fam0, _fam1, _fam2, _fam3, _fam4, _fam5, _fam6, _fam7)


def build_world(family: int, variant: int) -> dict:
    probes, seeds, events, instruments = _FAMS[family](variant)
    return _world(family, variant, probes, seeds, events, instruments)


def all_worlds() -> list:
    return [build_world(f, v) for f in range(8) for v in range(4)]


def get_world(world_id: str) -> dict:
    for world in all_worlds():
        if world["world_id"] == world_id:
            return world
    raise KeyError(f"unknown world {world_id}")


def dev_worlds() -> list:
    tiny = {"scope": "s0", "dep": "d0", "dep_version": 1}
    out = []
    for i in range(2):
        wid = f"dev0{i}"
        out.append({
            "world_id": wid, "family": -1, "variant": i,
            "family_name": "diagnostic-dev", "adverse": None,
            "rng_seed": 9000 + i, "ticks": 6,
            "props": {"p0": dict(tiny), "p1": dict(tiny)},
            "probes": {"m0": _probe("m0", 2, ["p0"]),
                       "m1": _probe("m1", 4, ["p1"])},
            "instruments": {}, "events": [],
            "seeds": [_seed("s-m0", "bottleneck", "m0", "dev probe")],
            "tasks": [{"task_id": f"{wid}-t{j}", "prop": f"p{j}"}
                      for j in range(2)],
            "scored": False,
        })
    out.append({
        "world_id": "dev02", "family": -1, "variant": 2,
        "family_name": "diagnostic-dev", "adverse": None,
        "rng_seed": 9002, "ticks": 6,
        "props": {"p0": dict(tiny), "p1": dict(tiny)},
        "probes": {"m0": _probe("m0", 2, ["p0"], followup="m1"),
                   "m1": _probe("m1", 2, ["p1"],
                                consequences={"true": "act", "false": "hold"})},
        "instruments": {}, "events": [],
        "seeds": [_seed("s-m0", "bottleneck", "m0", "dev useful probe", cap=4)],
        "tasks": [{"task_id": "dev02-t0", "prop": "p0"},
                  {"task_id": "dev02-t1", "prop": "p1"}],
        "scored": False,
    })
    out.append({
        "world_id": "dev03", "family": -1, "variant": 3,
        "family_name": "diagnostic-dev", "adverse": None,
        "rng_seed": 9003, "ticks": 6,
        "props": {"p0": dict(tiny), "p1": dict(tiny)},
        "probes": {"m0": _probe("m0", 2, ["p0"], followup="m1"),
                   "m1": _probe("m1", 2, ["p1"],
                                consequences={"true": "hold", "false": "hold"})},
        "instruments": {}, "events": [],
        "seeds": [_seed("s-m0", "bottleneck", "m0", "dev wasteful probe", cap=4)],
        "tasks": [{"task_id": "dev03-t0", "prop": "p0"}],
        "scored": False,
    })
    return out
