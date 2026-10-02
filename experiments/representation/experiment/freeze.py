"""Freeze script for the Representation Lane D pilot (RPR-04).

Builds the trusted single-file checker bundles deterministically from Lane B
instruments, verifies the committed acquisition contexts are byte-stable,
derives the frozen selectors from development transcripts only, and writes
the content-verified manifest (manifest.json + manifest.sha256). The runner
regenerates everything and refuses to work on any mismatch; the strict
checker rejects altered manifests, missing or duplicate records and
unbound invocations.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation import splits
from experiments.representation.acquire import contexts, panel

REP = Path(__file__).resolve().parent
ACQUIRE = REP.parent / "acquire"
FIXTURES = REP.parent / "fixtures"

COMPOSITIONS = [
    {"composition_id": "rpr-C-source-v1", "role": "source",
     "core": "core", "adapter": "sw_adapter",
     "description": "acquire/descriptions/source.md"},
    {"composition_id": "rpr-C-transfer-v1", "role": "transfer",
     "core": "core", "adapter": "gr_adapter",
     "description": "acquire/descriptions/transfer.md"},
    {"composition_id": "rpr-CTRL-nullsw-v1", "role": "source",
     "core": "null_core", "adapter": "sw_adapter",
     "description": "acquire/descriptions/nullsw.md"},
    {"composition_id": "rpr-CTRL-nullgr-v1", "role": "transfer",
     "core": "null_core", "adapter": "gr_adapter",
     "description": "acquire/descriptions/nullgr.md"},
]

VERDICT_RULE = (
    "promising-pilot: no invalid delivered result or incorrect control"
    " handling; C transfer mean improvement exceeds both A and B by at least"
    " 0.10; C software mean trails neither by more than 0.05; measured"
    " execution CPU, elapsed time, oracle queries, model tokens and accounted"
    " exposure each at most 1.25x each comparator total over the same benefit"
    " tasks (zero denominator requires C also zero). A secondary efficiency"
    " outcome requires identical per-task improvements with no greater"
    " resource component and at least one strict reduction against both"
    " comparators. Unknown or missing measurements cannot certify a resource"
    " win: missing CPU/exposure values block a resource-based favorable"
    " claim. A promising pilot warrants a broader frozen trial; it does not"
    " authorize a general learned-capability release."
)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_module(name: str) -> str:
    return (REP.parent / ("%s.py" % name)).read_text(encoding="utf-8")


def _strip_future(source: str) -> str:
    return "\n".join(line for line in source.splitlines()
                     if line.strip() != "from __future__ import annotations")


def build_checker_bundle(family: str) -> bytes:
    lines = ["from __future__ import annotations", "", "import sys", ""]
    if family == "software":
        lines.append(_strip_future(_read_module("software")))
    else:
        lines.append(_strip_future(_read_module("graphs")))
    checker = _read_module("checkers")
    dropped = [line for line in checker.splitlines()
               if line.strip() in ("from __future__ import annotations",
                                   "from . import graphs, software")]
    if len(dropped) != 2:
        raise ValueError("checker import shape changed; refusing bundle")
    body = "\n".join(line for line in checker.splitlines()
                     if line.strip() not in (
                         "from __future__ import annotations",
                         "from . import graphs, software"))
    lines.append(body)
    lines.append("")
    alias = "software" if family == "software" else "graphs"
    lines.append("%s = sys.modules[__name__]" % alias)
    check_fn = ("check_software" if family == "software" else "check_graph")
    lines.append("")
    lines.append("def _wrapper_main(argv):")
    lines.append("    import json as _json")
    lines.append("    if argv == ['--selftest']:")
    lines.append("        print(_json.dumps({'status': 'ok',"
                 " 'data': {'checker_bundle': True}}))")
    lines.append("        return 0")
    lines.append("    doc = _json.load(open(argv[0], encoding='utf-8'))")
    lines.append("    report = %s(doc['source_task'], doc['candidate'])"
                 % check_fn)
    lines.append("    _json.dump({'verdict': report['verdict'],"
                 " 'measure': report['measure'],"
                 " 'reason': report['reason']},"
                 " open(argv[1], 'w', encoding='utf-8'))")
    lines.append("    return 0")
    lines.append("")
    lines.append("if __name__ == '__main__':")
    lines.append("    raise SystemExit(_wrapper_main(sys.argv[1:]))")
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def _fixture_rel(task_id: str) -> str:
    for sub in ("software/development", "graphs/development", "software/check",
                "graphs/check", "software/evaluation", "graphs/evaluation",
                "controls", "use"):
        if (FIXTURES / sub / ("%s.json" % task_id)).is_file():
            return "%s/%s.json" % (sub, task_id)
    raise KeyError("unknown fixture %s" % task_id)


def build_manifest() -> dict:
    problems = splits.verify_manifest(FIXTURES)
    if problems:
        raise ValueError("lane B manifest invalid: %s" % problems)
    lane_b_raw = (FIXTURES / "manifest.json").read_bytes()
    lane_b = json.loads(lane_b_raw)
    bundles = {"sw_checker": build_checker_bundle("software"),
               "gr_checker": build_checker_bundle("graph")}
    for name, raw in bundles.items():
        committed = REP / ("bundle_%s_checker.py" % name.split("_")[0])
        if not committed.is_file() or committed.read_bytes() != raw:
            raise ValueError("committed %s drifted from its generator"
                             % committed.name)
    for name in ("source_context.json", "transfer_context.json"):
        committed = (ACQUIRE / name).read_bytes()
        rebuilt = (json.dumps(
            contexts.build_source_context(FIXTURES)
            if name.startswith("source")
            else contexts.build_transfer_context(FIXTURES),
            sort_keys=True, indent=2) + "\n").encode()
        if _digest(committed) != _digest(rebuilt):
            raise ValueError("committed %s drifted from its generator" % name)
    source_ctx = json.loads((ACQUIRE / "source_context.json").read_bytes())
    transfer_ctx = json.loads((ACQUIRE / "transfer_context.json").read_bytes())
    selectors = panel.derive_selectors(source_ctx, transfer_ctx)
    files = []
    seen_tasks = (panel.BENEFIT_SW + panel.BENEFIT_GR + panel.CONTROLS
                  + panel.USE + [t for t, _ in panel.ATTRIBUTION])
    for task_id in seen_tasks:
        rel = _fixture_rel(task_id)
        raw = (FIXTURES / rel).read_bytes()
        files.append({"path": "experiments/representation/fixtures/%s" % rel,
                      "task_id": task_id, "digest": _digest(raw),
                      "bytes": len(raw)})
    components = dict(panel.COMPONENTS)
    components.update({"source_context": "acquire/source_context.json",
                       "transfer_context": "acquire/transfer_context.json"})
    for key, rel in components.items():
        raw = (REP.parent / rel).read_bytes()
        files.append({"path": "experiments/representation/%s" % rel,
                      "component": key, "digest": _digest(raw),
                      "bytes": len(raw)})
    compositions = []
    for comp in COMPOSITIONS:
        core_raw = (ACQUIRE / ("%s.py" % ("atom_core" if comp["core"] == "core"
                                          else comp["core"]))).read_bytes()
        adapter_raw = (ACQUIRE / ("%s.py" % comp["adapter"])).read_bytes()
        desc_raw = (REP.parent / comp["description"]).read_bytes()
        files.append({"path": "experiments/representation/%s" % comp["description"],
                      "description_for": comp["composition_id"],
                      "digest": _digest(desc_raw), "bytes": len(desc_raw)})
        compositions.append({**comp, "core_digest": _digest(core_raw),
                             "adapter_digest": _digest(adapter_raw)})
    files.sort(key=lambda entry: entry["path"])
    return {"version": panel.PANEL_VERSION,
            "checker_version": panel.CHECKER_VERSION,
            "lane_b": {"version": lane_b.get("version", ""),
                       "manifest_digest": _digest(lane_b_raw)},
            "files": files, "compositions": compositions,
            "selectors": selectors,
            "panel": {"benefit_sw": panel.BENEFIT_SW,
                      "benefit_gr": panel.BENEFIT_GR,
                      "controls": panel.CONTROLS, "use": panel.USE,
                      "attribution": [{"task_id": t, "family": f}
                                      for t, f in panel.ATTRIBUTION]},
            "budgets": panel.BUDGETS,
            "protocols": [panel.PROTOCOL_B, panel.PROTOCOL_C],
            "verdict_rule": VERDICT_RULE}


def write_manifest() -> dict:
    manifest = build_manifest()
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    (REP / "manifest.json").write_bytes(raw)
    (REP / "manifest.sha256").write_text(_digest(raw) + "\n")
    return manifest


def verify_committed(name: str = "manifest.json",
                     regenerate: bool = True) -> list:
    problems = []
    try:
        manifest_raw = (REP / name).read_bytes()
    except OSError:
        return ["missing-manifest"]
    try:
        pinned = (REP / (Path(name).stem + ".sha256")).read_text().strip()
    except OSError:
        return ["missing-manifest-hash"]
    if _digest(manifest_raw) != pinned:
        return ["manifest-hash-mismatch"]
    if regenerate:
        try:
            fresh = build_manifest()
        except (ValueError, KeyError) as exc:
            return ["regeneration-failed %s" % exc]
        if json.loads(manifest_raw) != fresh:
            problems.append("manifest-content-mismatch")
    manifest = json.loads(manifest_raw)
    seen = set()
    for entry in manifest.get("files", []):
        path = entry.get("path", "")
        if path in seen:
            problems.append("duplicate-file %s" % path)
        seen.add(path)
        target = ROOT / path
        if not target.is_file():
            problems.append("missing-file %s" % path)
            continue
        if _digest(target.read_bytes()) != entry.get("digest"):
            problems.append("digest-mismatch %s" % path)
    return problems


def write_bundles() -> dict:
    out = {}
    for family, stem in (("software", "sw"), ("graph", "gr")):
        raw = build_checker_bundle(family)
        (REP / ("bundle_%s_checker.py" % stem)).write_bytes(raw)
        out[stem] = _digest(raw)
    return out


def main(argv):
    if "--write-bundles" in argv:
        print(json.dumps(write_bundles(), indent=2))
        return 0
    if "--check" in argv:
        problems = {"manifest.json": verify_committed(),
                    "manifest_acq1.json":
                        verify_committed("manifest_acq1.json",
                                         regenerate=False)}
        print(json.dumps({"problems": problems}, indent=2))
        return 1 if any(problems.values()) else 0
    manifest = write_manifest()
    print(json.dumps({"wrote": "manifest.json",
                      "files": len(manifest["files"]),
                      "compositions": len(manifest["compositions"])},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
