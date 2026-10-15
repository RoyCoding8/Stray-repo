"""Freeze the P05 campaign inputs and the source that will consume them."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SOURCE_PATHS = (
    "AGENTS.md",
    "WORKER-PROMPT.md",
    "docs/plans/05-AGENDA.md",
    "src/rsi/agenda.py",
    "src/rsi/agenda_policy.py",
    "src/rsi/investigate.py",
    "src/rsi/investigation.py",
    "src/rsi/experience.py",
    "src/rsi/memory.py",
    "src/rsi/capability.py",
    "src/rsi/task.py",
    "src/rsi/genome.py",
    "src/rsi/context.py",
    "src/rsi/verifier.py",
    "src/rsi/episode.py",
    "src/rsi/_method_runner.py",
    "src/settlement/db.py",
    "src/settlement/store.py",
    "src/settlement/common.py",
    "src/settlement/broker.py",
    "src/settlement/artifacts.py",
    "src/settlement/launcher_codex.py",
    "src/settlement/launcher_local.py",
    "migrations/0031_agendas.sql",
    "experiments/agenda05/freeze.py",
    "experiments/agenda05/check.py",
    "experiments/agenda05/driver.py",
    "experiments/agenda05/fixture_worker.py",
    "tests/test_rsi_agenda_campaign.py",
)
MANIFEST = "manifest.json"
SCENARIO = "scenario.json"
SCHEMA = "p05-agenda-freeze/1"
_SECRET_KEYS = {"api_key", "authorization", "credential", "credentials",
                "route_envfile", "secret"}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _reject_credentials(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.casefold() in _SECRET_KEYS:
                raise ValueError(f"scenario contains forbidden credential field {key!r}")
            _reject_credentials(item)
    elif isinstance(value, list):
        for item in value:
            _reject_credentials(item)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def _source_state(repo: Path) -> dict:
    sources = {}
    for rel in SOURCE_PATHS:
        path = repo / rel
        if not path.is_file():
            raise ValueError(f"frozen source is missing: {rel}")
        sources[rel] = _sha(path.read_bytes())
    dirty = _git(repo, "status", "--porcelain", "--", *SOURCE_PATHS)
    if dirty:
        raise ValueError("freeze requires committed, clean pinned source files")
    return {"commit": _git(repo, "rev-parse", "HEAD"), "sources": sources}


def freeze(repo: Path, bundle: Path, scenario_path: Path) -> dict:
    manifest_path = bundle / MANIFEST
    if manifest_path.exists():
        raise ValueError(f"refusing to replace existing freeze {manifest_path}")
    scenario_raw = scenario_path.read_bytes()
    try:
        scenario = json.loads(scenario_raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"scenario must be UTF-8 JSON: {exc}") from exc
    if not isinstance(scenario, dict):
        raise TypeError("scenario must be a JSON object")
    _reject_credentials(scenario)
    state = _source_state(repo.resolve())
    canonical_scenario = _canonical(scenario)
    manifest = {
        "schema": SCHEMA,
        **state,
        "python": sys.version,
        "scenario_sha256": _sha(canonical_scenario),
        "scenario": base64.b64encode(canonical_scenario).decode("ascii"),
    }
    bundle.mkdir(parents=True, exist_ok=True)
    _write_json(bundle / SCENARIO, scenario)
    _write_json(manifest_path, manifest)
    return manifest


def verify_freeze(repo: Path, bundle: Path) -> dict:
    manifest = _read_json(bundle / MANIFEST)
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ValueError("unsupported P05 freeze manifest")
    if manifest.get("sources") != _source_state(repo.resolve())["sources"]:
        raise ValueError("frozen source differs from the current committed source")
    try:
        scenario_raw = base64.b64decode(manifest["scenario"], validate=True)
        scenario = json.loads(scenario_raw)
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("frozen scenario is missing or malformed") from exc
    if (not isinstance(scenario, dict)
            or _sha(_canonical(scenario)) != manifest.get("scenario_sha256")
            or scenario != _read_json(bundle / SCENARIO)):
        raise ValueError("frozen scenario copy or digest does not match")
    _reject_credentials(scenario)
    return manifest


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> None:
    raw = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                      allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(raw, encoding="utf-8", newline="\n")
    temp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--repo", type=Path,
                        default=Path(__file__).resolve().parents[2])
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--scenario", type=Path)
    args = parser.parse_args()
    if args.freeze:
        if args.scenario is None:
            parser.error("--freeze requires --scenario")
        result = freeze(args.repo, args.bundle, args.scenario)
    else:
        result = verify_freeze(args.repo, args.bundle)
    print(json.dumps({"schema": result["schema"],
                      "commit": result["commit"],
                      "scenario_sha256": result["scenario_sha256"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
