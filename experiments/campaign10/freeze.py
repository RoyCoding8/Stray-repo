"""Freeze and verify the public P10 pilot inputs before any model effects."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "scenario.json"
SOURCE_FILES = tuple(
    path.relative_to(ROOT).as_posix()
    for path in sorted((ROOT / "src/rsi").glob("*.py"))
) + (
    "src/settlement/broker.py",
    "src/settlement/launcher_codex.py",
    "src/settlement/launcher_local.py",
    "experiments/campaign10/scenario.json",
    "experiments/campaign10/freeze.py",
    "experiments/campaign10/driver.py",
    "experiments/campaign10/fixture_worker.py",
)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source_manifest(root: Path = ROOT) -> dict[str, str]:
    manifest = {}
    for relative in SOURCE_FILES:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"frozen source is missing: {relative}")
        manifest[relative] = sha256(path.read_bytes())
    return manifest


def scenario_digest(path: Path = SCENARIO) -> str:
    return sha256(canonical_bytes(json.loads(path.read_text(encoding="utf-8"))))


def freeze_document(*, mode: str, protocol: dict, identities: dict,
                    scenario_path: Path = SCENARIO, root: Path = ROOT) -> dict:
    if mode not in {"fixture", "live"}:
        raise ValueError("mode must be fixture or live")
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    sources = source_manifest(root)
    source_sha = sha256(canonical_bytes(sources))
    protocol_sha = sha256(canonical_bytes(protocol))
    caps_sha = sha256(canonical_bytes(scenario["caps"]))
    prepared_at_epoch = time.time()
    return {
        "schema": "p10-campaign-pilot-freeze/1",
        "mode": mode,
        "mode_sha256": sha256(mode.encode("utf-8")),
        "prepared_at_epoch": prepared_at_epoch,
        "prepared_at_epoch_sha256": sha256(canonical_bytes(prepared_at_epoch)),
        "source_manifest": sources,
        "source_sha256": source_sha,
        "scenario_sha256": scenario_digest(scenario_path),
        "protocol_sha256": protocol_sha,
        "caps_sha256": caps_sha,
        "identities_sha256": sha256(canonical_bytes(identities)),
        "identities": identities,
        "protocol": protocol,
        "caps": scenario["caps"],
    }


def verify_freeze(path: Path, *, scenario_path: Path = SCENARIO,
                  root: Path = ROOT) -> dict:
    frozen = json.loads(path.read_text(encoding="utf-8"))
    if frozen.get("schema") != "p10-campaign-pilot-freeze/1":
        raise ValueError("unsupported pilot freeze")
    current_sources = source_manifest(root)
    current = {
        "mode_sha256": sha256(str(frozen.get("mode", "")).encode("utf-8")),
        "prepared_at_epoch_sha256": sha256(canonical_bytes(
            frozen.get("prepared_at_epoch"))),
        "source_sha256": sha256(canonical_bytes(current_sources)),
        "scenario_sha256": scenario_digest(scenario_path),
        "protocol_sha256": sha256(canonical_bytes(frozen.get("protocol"))),
        "caps_sha256": sha256(canonical_bytes(json.loads(
            scenario_path.read_text(encoding="utf-8"))["caps"])),
        "identities_sha256": sha256(canonical_bytes(frozen.get("identities"))),
    }
    for key, value in current.items():
        if frozen.get(key) != value:
            raise ValueError(f"pilot freeze changed: {key}")
    if frozen.get("source_manifest") != current_sources:
        raise ValueError("pilot freeze changed: source_manifest")
    if frozen.get("caps") != json.loads(scenario_path.read_text(encoding="utf-8"))["caps"]:
        raise ValueError("pilot freeze changed: caps")
    scenario_copy = json.loads((path.parent / "scenario.json").read_text(encoding="utf-8"))
    static_scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    if canonical_bytes(scenario_copy) != canonical_bytes(static_scenario):
        raise ValueError("pilot freeze changed: run scenario")
    identities_copy = json.loads((path.parent / "identities.json").read_text(encoding="utf-8"))
    if identities_copy != frozen.get("identities"):
        raise ValueError("pilot freeze changed: identities")
    protocol_path = path.parent / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if (protocol != frozen.get("protocol")
            or sha256(canonical_bytes(protocol)) != frozen.get("protocol_sha256")):
        raise ValueError("pilot freeze changed: protocol")
    return frozen
