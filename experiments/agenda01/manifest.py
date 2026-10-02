"""AG01-EXP frozen manifest: identities, budgets, rules and digests."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from . import worlds

PACKAGE = Path(__file__).parent
MANIFEST_PATH = PACKAGE / "manifest.json"
HASH_PATH = PACKAGE / "manifest.sha256"

EXPERIMENT_VERSION = "AG01-EXP/3"
SRC_FILES = ("src/settlement/agenda.py", "src/settlement/agenda_policy.py",
             "src/settlement/broker.py", "src/settlement/store.py")
POLICY_VERSIONS = {"R": "AG01-R-1", "Q": "AG01-Q-2"}
POLICY_SOURCES = {"R": "settlement.agenda_policy.decide_R",
                  "Q": "settlement.agenda_policy.decide_Q"}
GRAMMAR = "AG01-OBS-1"
BUDGETS = {"ticks": 24, "exploration": 64, "eval_per_trajectory": 8,
           "recovery_cap": 16, "decision_cost": 1}
TRAJECTORIES_PER_WORLD = 4

PUBLIC_FIELDS = ["measurement specs", "probe costs {2,4,8}", "noise rates",
                 "prerequisites", "delays", "replication plans",
                 "decision consequences (hypotheses)", "event schedules",
                 "initial option seeds", "end-use task specs",
                 "trajectory observations", "budget state"]
PRIVILEGED_FIELDS = ["latent prop facts", "grader seed", "per-task answers"]

PROPOSAL_RULE = (
    "t0 seeds from world.seeds as agenda options. From durable scored outcomes "
    "(decisive, current dep version, ungrounded, in-scope) maintain one "
    "continuation descriptor per (option, next probe, slot) citing all matching "
    "receipts: the declared probe followup when present, else a frozen "
    "replication slot repl:<probe>:<k>-of-<N> while samples_taken < N, else a "
    "same-probe re-sample while samples_taken < 2. Continuations reuse the "
    "parent option (no new option keys). Admission goes through the "
    "submit_continuation fence; already-bound effects and fence-refused "
    "receipt sets are not re-proposed. No other options are ever generated.")

EVENT_ORDERING = (
    "deterministic tick order: due exogenous events and available receipts, "
    "then wake/eligibility processing, then at most one paid policy decision "
    "and its possible discretionary admission. Zero-delay receipts apply the "
    "same tick; delayed receipts apply at launch_tick + delay. Read-only "
    "eligibility explanation never advances the cursor.")

GRADING_RULE = (
    "equal solver for both arms: per task, majority vote over scored "
    "observations at the horizon dep version plus labeled simulated product "
    "claims; ties and absence give unknown, which scores incorrect. Attempt "
    "cost is 1 eval unit per task. Drain information is reported, never scored.")

ANALYSIS_RULE = (
    "primary outcome: paired difference in correct end-use tasks under the "
    "equal exploration cap; report every pair, family totals and both tie "
    "orders with regressions. Resource vector: exploration, end-use, "
    "recovery, waiting/idle, liabilities. No universal score. Q merits a "
    "broader trial on aggregate primary improvement with no family-total "
    "regression, or all-primary-tied with lower total resources, with all "
    "mechanical gates passing.")


def source_revision() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=PACKAGE,
                              capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except Exception:
        return "unrecorded"


def file_digest(name: str) -> str:
    return hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest()


def repo_digest(rel: str) -> str:
    return hashlib.sha256((PACKAGE / ".." / ".." / rel).read_bytes()).hexdigest()


def tie_orders(world: dict) -> dict:
    forward = [s["option_key"] for s in world["seeds"]]
    return {"t0": forward, "t1": list(reversed(forward))}


def canonical_bytes(doc: dict) -> bytes:
    trimmed = {k: v for k, v in doc.items() if k != "source_revision"}
    return json.dumps(trimmed, sort_keys=True, indent=2).encode()


def canonical_digest(doc: dict) -> str:
    return hashlib.sha256(canonical_bytes(doc)).hexdigest()


def build() -> tuple[dict, str]:
    frozen_worlds = worlds.all_worlds()
    manifest = {
        "experiment": EXPERIMENT_VERSION,
        "source_revision": source_revision(),
        "files": {n: file_digest(n) for n in
                  ("worlds.py", "grader.py", "observations.py", "runner.py",
                   "checker.py", "manifest.py", "launcher.py", "replay.py",
                   "panel.py")},
        "sources": {n: repo_digest(n) for n in SRC_FILES},
        "worlds": frozen_worlds,
        "tie_orders": {w["world_id"]: tie_orders(w) for w in frozen_worlds},
        "public_fields": PUBLIC_FIELDS,
        "privileged_fields": PRIVILEGED_FIELDS,
        "proposal_rule": PROPOSAL_RULE,
        "event_ordering": EVENT_ORDERING,
        "policy_versions": POLICY_VERSIONS,
        "policy_sources": POLICY_SOURCES,
        "grammar": GRAMMAR,
        "grading_rule": GRADING_RULE,
        "solver_cost_per_task": 1,
        "budgets": BUDGETS,
        "trajectories_per_world": TRAJECTORIES_PER_WORLD,
        "controls": {"positive": list(worlds.CONTROL_WORLDS),
                     "wrong_answer": "all-worlds",
                     "q_losing": worlds.Q_LOSING_WORLD},
        "analysis_rule": ANALYSIS_RULE,
    }
    return manifest, canonical_digest(manifest)


def write() -> tuple[Path, Path, str]:
    manifest, digest = build()
    blob = json.dumps(manifest, sort_keys=True, indent=2).encode()
    MANIFEST_PATH.write_bytes(blob)
    HASH_PATH.write_text(canonical_digest(manifest) + "\n")
    return MANIFEST_PATH, HASH_PATH, digest


def load() -> tuple[dict, str]:
    blob = MANIFEST_PATH.read_bytes()
    return json.loads(blob), HASH_PATH.read_text().strip()


def load_verified(manifest_path: str | Path, hash_path: str | Path,
                  *, run_unverified: bool = False) -> tuple[dict, str]:
    manifest_path, hash_path = Path(manifest_path), Path(hash_path)
    doc = json.loads(manifest_path.read_bytes())
    digest = canonical_digest(doc)
    frozen = hash_path.read_text().strip()
    if digest != frozen and not run_unverified:
        raise ValueError(f"manifest drift: {manifest_path} digests to {digest},"
                         f" frozen {frozen}; pass --run-unverified for diagnostics only")
    for name, want in dict(doc.get("files") or {}).items():
        got = file_digest(name)
        if got != want and not run_unverified:
            raise ValueError(f"frozen file drifted: {name} {got} != {want};"
                             " pass --run-unverified for diagnostics only")
    for rel, want in dict(doc.get("sources") or {}).items():
        got = repo_digest(rel)
        if got != want and not run_unverified:
            raise ValueError(f"frozen source drifted: {rel} {got} != {want};"
                             " pass --run-unverified for diagnostics only")
    return doc, frozen
