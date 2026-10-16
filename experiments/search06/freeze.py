"""Prospective freeze for the P06 experiment's code and collected corpus."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

try:
    from .driver import CODEX, MODEL, ROUTE_FILE, SOURCE_PATHS, _scenario, canonical, read_json
except ImportError:
    from driver import CODEX, MODEL, ROUTE_FILE, SOURCE_PATHS, _scenario, canonical, read_json


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sources(root: Path) -> dict[str, str]:
    result = {}
    for relative in SOURCE_PATHS:
        path = root / relative
        if not path.is_file():
            raise ValueError(f"frozen source is missing: {relative}")
        result[relative] = _sha(path.read_bytes())
    return result


def _route(path: Path, mode: str) -> dict:
    if mode == "fixture":
        endpoint = "fixture://native"
    else:
        values = {}
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                key, sep, value = line.partition("=")
                if not sep:
                    raise ValueError("route file contains a malformed assignment")
                values[key.strip()] = value.strip().strip("\"'")
        required = {"SETTLEMENT_GATEWAY_ENDPOINT", "SETTLEMENT_GATEWAY_MODEL",
                    "SETTLEMENT_GATEWAY_KEY"}
        if required - values.keys() or values["SETTLEMENT_GATEWAY_MODEL"] != MODEL:
            raise ValueError("live route must identify the approved free OpenRouter model")
        endpoint = values["SETTLEMENT_GATEWAY_ENDPOINT"].rstrip("/")
        if not endpoint.startswith(("https://", "http://")):
            raise ValueError("live route endpoint must be HTTP(S)")
    return {"model": MODEL if mode == "live" else "fixture:free",
            "endpoint_sha256": _sha(endpoint.encode("utf-8")),
            "mode": mode}


def _software(root: Path, mode: str) -> dict:
    result = {}
    if mode == "live":
        if not CODEX.is_file():
            raise ValueError(f"Codex CLI is missing: {CODEX}")
        result["codex"] = {"path": str(CODEX.resolve()),
                           "sha256": _sha(CODEX.read_bytes())}
    return result


def _live_plan(run_id: str, freeze_path: Path) -> dict:
    def allocation(stage: str) -> dict[str, str]:
        return {domain: f"p06-{run_id}-{stage}-{domain}"
                for domain in ("tokens", "cpu")}

    return {
        "run_id": run_id,
        "run_output": str((freeze_path.parent / "live").resolve()),
        "allocations": {
            "construction": allocation("construct"),
            "candidate_screen": allocation("candidate-screen"),
            "incumbent_screen": allocation("incumbent-screen"),
            "diagnostic_screen": allocation("diagnostic-screen"),
            "agenda": allocation("agenda"),
        },
        "operations": {
            "construction": [run_id + "-construct-0", run_id + "-construct-1"],
            "candidate_screen": run_id + "-candidate",
            "incumbent_screen": run_id + "-incumbent",
            "diagnostic_screen": run_id + "-candidate-diagnostic",
            "agenda": run_id + "-agenda",
        },
        "agenda_deadline": (datetime.now(UTC) + timedelta(seconds=180)).isoformat(),
        "screening_cpu_ceiling": 2_400_000,
    }


def freeze(root: Path, path: Path, collection_path: Path, *, mode: str,
           route_file: Path = ROUTE_FILE, scenario_path: Path) -> dict:
    if path.exists():
        raise FileExistsError(f"refusing to replace existing freeze {path}")
    if mode not in {"fixture", "live"}:
        raise ValueError("freeze mode must be fixture or live")
    scenario = _scenario(scenario_path)
    collection = read_json(collection_path)
    if (collection.get("schema") != "p06-collection/1"
            or collection.get("scenario_sha256") != _sha(canonical(scenario))
            or len(collection.get("frames", [])) != 3
            or len(collection.get("branches", [])) != 6
            or set(collection.get("policies", {})) != {"authored-restricted", "authored-general"}):
        raise ValueError("freeze requires the complete three-frame authored collection")
    sources = _sources(root)
    run_id = "p06-live-" + uuid.uuid4().hex[:10]
    document = {
        "schema": "p06-search-freeze/1", "mode": mode,
        "scenario_sha256": _sha(canonical(scenario)),
        "scenario": scenario, "source_manifest": sources,
        "source_sha256": _sha(canonical(sources)),
        "collection_sha256": _sha(canonical(collection)),
        "collection": {"run_id": collection["run_id"],
                       "frames": collection["frames"], "branches": collection["branches"],
                       "policies": collection["policies"]},
        "route": _route(route_file, mode), "caps": scenario["caps"],
        "software": _software(root, mode),
        "live_plan": _live_plan(run_id, path),
    }
    document["freeze_sha256"] = _sha(canonical(document))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True, indent=2,
                               ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return document


def verify_freeze(root: Path, path: Path, collection_path: Path, *,
                  route_file: Path = ROUTE_FILE, scenario_path: Path | None = None) -> dict:
    frozen = read_json(path)
    if frozen.get("schema") != "p06-search-freeze/1":
        raise ValueError("unsupported P06 freeze")
    scenario_path = scenario_path or root / "experiments/search06/scenario.json"
    scenario = _scenario(scenario_path)
    collection = read_json(collection_path)
    route = _route(route_file, frozen.get("mode"))
    source_manifest = _sources(root)
    software = _software(root, frozen.get("mode"))
    checks = {
        "scenario_sha256": _sha(canonical(scenario)),
        "source_sha256": _sha(canonical(source_manifest)),
        "collection_sha256": _sha(canonical(collection)),
        "route": route, "caps": scenario["caps"], "software": software,
        "live_plan": frozen.get("live_plan"),
        "collection": {"run_id": collection.get("run_id"),
                       "frames": collection.get("frames"),
                       "branches": collection.get("branches"),
                       "policies": collection.get("policies")},
    }
    for key, value in checks.items():
        if frozen.get(key) != value:
            raise ValueError(f"P06 freeze changed: {key}")
    if frozen.get("scenario") != scenario or frozen.get("source_manifest") != source_manifest:
        raise ValueError("P06 frozen scenario or source manifest changed")
    if not isinstance(frozen.get("live_plan"), dict):
        raise TypeError("P06 freeze has no prospective run plan")
    unsigned = {key: value for key, value in frozen.items() if key != "freeze_sha256"}
    if frozen.get("freeze_sha256") != _sha(canonical(unsigned)):
        raise ValueError("P06 freeze digest is invalid")
    return frozen
