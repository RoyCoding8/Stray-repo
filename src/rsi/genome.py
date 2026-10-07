"""Genome: the versioned bundle an agent harness reads, and nothing else.

A genome is a set of files under a fixed layout:

- ``AGENTS.md``: context and rules the task agent reads.
- ``skills/<name>/SKILL.md`` plus resources: Agent Skills (open standard).
- ``harness.toml``: harness settings the genome may choose.
- ``meta/**``: the meta agent's own instructions. The improver lives in the
  genome so it can be improved too (HyperAgents-style).

Identity is content: the digest is the settlement artifact-package digest of
the files, so ``publish`` and ``digest_of`` always agree, and the same files
reached from two parents are one genome.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from psycopg.types.json import Json

from settlement import artifacts, db, store
from settlement.common import Command, ResultCode, SettlementError

SCOPE = "rsi-genome"
HARNESSES = ("codex",)
# Settings a genome may set. The model, provider, sandbox and approval policy
# belong to the kernel: they fix the budget and the trust boundary, and a
# genome that could change them would compare unequal runs as equal.
HARNESS_KEYS = frozenset({"model_reasoning_effort", "model_reasoning_summary",
                          "model_verbosity", "hide_agent_reasoning"})


class GenomeError(SettlementError):
    pass


@dataclass(frozen=True)
class Genome:
    files: Mapping[str, bytes]
    harness: str = "codex"
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        for rel in self.files:
            _check_layout(rel)
        if self.harness not in HARNESSES:
            raise GenomeError(f"unknown harness {self.harness!r}")
        settings(self)  # parse now so a bad harness.toml never gets a digest
        object.__setattr__(self, "files", dict(sorted(self.files.items())))
        object.__setattr__(self, "digest", _package_digest(self._manifest(), self.files))

    def _manifest(self) -> dict:
        return {"kind": "rsi-genome", "harness": self.harness,
                "files": [{"path": rel, "kind": "file", "size": len(raw),
                           "digest": hashlib.sha256(raw).hexdigest()}
                          for rel, raw in self.files.items()]}

    def text(self, rel: str) -> str:
        return self.files[rel].decode("utf-8")


def _check_layout(rel: str) -> None:
    try:
        artifacts._check_relpath(rel)
    except SettlementError as exc:
        raise GenomeError(str(exc)) from exc
    top = rel.split("/", 1)[0]
    if rel in ("AGENTS.md", "harness.toml"):
        return
    if top in ("skills", "meta") and "/" in rel:
        return
    raise GenomeError(f"{rel!r} is outside the genome layout"
                      " (AGENTS.md, harness.toml, skills/**, meta/**)")


def _package_digest(manifest: dict, files: Mapping[str, bytes]) -> str:
    # Must match artifacts.stage_package byte for byte.
    payload = json.dumps({"manifest": manifest, "scope": SCOPE,
                          "files": {rel: raw.hex() for rel, raw in files.items()}},
                         sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def settings(genome: Genome) -> dict:
    raw = genome.files.get("harness.toml")
    if raw is None:
        return {}
    try:
        parsed = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise GenomeError(f"harness.toml does not parse: {exc}") from exc
    extra = set(parsed) - HARNESS_KEYS
    if extra:
        raise GenomeError(f"harness.toml sets kernel-owned keys {sorted(extra)}")
    return parsed


def workspace_path(rel: str) -> str | None:
    """Where a genome file lands in a task workspace; None if it does not."""
    if rel == "AGENTS.md":
        return "AGENTS.md"
    if rel.startswith("skills/"):
        return ".agents/" + rel
    return None  # harness.toml becomes config overrides; meta/ is for the meta agent


def materialize(genome: Genome, workspace: Path) -> list[str]:
    """Write the task-agent view of `genome` into `workspace`."""
    placed = []
    for rel, raw in genome.files.items():
        dest = workspace_path(rel)
        if dest is None:
            continue
        target = artifacts._contained(workspace, dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        placed.append(dest)
    return placed


def publish(dsn: str, genome: Genome, *, staging_root: str | Path,
            artifacts_root: str | Path, parent: str | None, origin: str) -> str:
    """Store `genome` as an artifact and record its lineage edge. Idempotent."""
    receipt = artifacts.stage_package(dsn, staging_root, manifest=genome._manifest(),
                                      files=dict(genome.files), scope=SCOPE,
                                      format="rsi-genome")
    if receipt["digest"] != genome.digest:
        raise GenomeError("artifact digest disagrees with genome digest")
    artifacts.publish_package(dsn, Command(request_id=f"rsi-genome-art-{genome.digest}",
                                           payload={"digest": genome.digest}),
                              artifacts_root, receipt)

    def _fn(cur, control):
        cur.execute("SELECT parent FROM rsi_genomes WHERE digest = %s", (genome.digest,))
        if cur.fetchone() is not None:
            return (ResultCode.ALREADY_APPLIED, "genome known", {"digest": genome.digest}, [], [])
        if parent is not None:
            cur.execute("SELECT 1 FROM rsi_genomes WHERE digest = %s", (parent,))
            if cur.fetchone() is None:
                raise GenomeError(f"unknown parent genome {parent[:12]}")
        cur.execute("INSERT INTO rsi_genomes (digest, parent, harness, origin)"
                    " VALUES (%s, %s, %s, %s)",
                    (genome.digest, parent, genome.harness, Json({"origin": origin})))
        return (ResultCode.APPLIED, "genome published", {"digest": genome.digest},
                [("rsi.genome.published", {"digest": genome.digest, "parent": parent})], [])
    result = store.transact(dsn, Command(request_id=f"rsi-genome-{genome.digest}",
                                         payload={"digest": genome.digest, "parent": parent}), _fn)
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise GenomeError(f"genome not recorded: {result.detail}")
    return genome.digest


def load(dsn: str, artifacts_root: str | Path, digest: str) -> Genome:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT harness FROM rsi_genomes WHERE digest = %s", (digest,))
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise GenomeError(f"unknown genome {digest[:12]}")
    raw = (Path(artifacts_root) / digest).read_bytes()
    package = json.loads(raw.decode())
    genome = Genome({rel: bytes.fromhex(h) for rel, h in package["files"].items()},
                    harness=row[0])
    if genome.digest != digest:
        raise GenomeError(f"stored genome {digest[:12]} does not match its digest")
    return genome


def from_dir(root: Path, harness: str = "codex") -> Genome:
    files = {p.relative_to(root).as_posix(): p.read_bytes()
             for p in sorted(root.rglob("*")) if p.is_file()}
    return Genome(files, harness=harness)
