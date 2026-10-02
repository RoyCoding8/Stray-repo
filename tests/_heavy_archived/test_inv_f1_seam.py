"""INV-F1: canned constructor seam refuses unattested artifacts.

`dev_constructor` and `solved_child_factory` are importable seams whose
authored bytes carry no broker admission. The seam must refuse them with
a visible disposition instead of passing them through as success.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DSN = os.environ.get(
    "INV_F1_DSN",
    "dbname=inv_f1_seam host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"
TASK = "c02-t01"


def _fresh_db():
    assert "live" not in DSN
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(DSN, MIGRATIONS)
    E.designate_db(DSN, kind="disposable",
                   purpose="INV-F1 canned-seam refusal")
    E.prepare_disposable_db(DSN, MIGRATIONS)


def _owned():
    from experiments.coord02 import oracle
    return list(oracle.worker_files(TASK))


def test_canned_constructors_refuse_without_admission():
    from experiments.coord02 import entry as entry_mod
    from experiments.coord02 import experience as E
    owned = _owned()
    assert owned, "oracle owns no paths for %s" % TASK
    child = {"owned_paths": owned}
    assert E.dev_constructor(TASK, solved=True)(
        "w1", child, {}) is None
    assert E.dev_constructor(TASK, solved=False)(
        "w1", child, {}) is None
    assert entry_mod.solved_child_factory(TASK)(
        "w1", child, {}) is None


def test_canned_episode_has_visible_refusal(tmp_path):
    _fresh_db()
    from experiments.coord02 import entry as entry_mod
    from experiments.coord02 import experience as E
    from experiments.coord02 import oracle
    from experiments.coord02.controller import EpisodeConfig, run_episode
    from experiments.coord02.controller import seed_episode
    from settlement.launcher_local import LocalLauncher
    from settlement.representation import sha_hex
    snapshot = E.snapshot_files(TASK)
    payload = oracle.build_solver_payload(TASK)
    policy = entry_mod.arm_policy_entry("S", task_id=TASK,
                                        package_digest="inv-f1")
    requires = E._requires_for(TASK, snapshot)
    seed = seed_episode(DSN, "invf1-%s" % uuid.uuid4().hex[:8], snapshot)
    cfg = EpisodeConfig(
        run_id="run-invf1-%s" % uuid.uuid4().hex[:8], task_id=TASK,
        allocation_id=seed["allocation_id"],
        investigation_id=seed["investigation_id"],
        snapshot=dict(snapshot),
        interface_contract=E._dev_interface_contract(TASK, payload),
        join_rules=E._dev_join_rules(TASK),
        bindings=E._dev_bindings(requires, snapshot),
        source_interfaces=E._dev_source_interfaces(TASK),
        package={"version_id": "coord02-L-invf1",
                 "package_digest": sha_hex(policy),
                 "entry_bytes": policy, "requires": requires},
        snapshot_digest=seed["snapshot_digest"])
    outcome = run_episode(
        DSN, cfg, {"local-process": LocalLauncher(tmp_path)},
        E.dev_constructor(TASK, solved=True))
    assert outcome.get("status") == "submit-refused", outcome
    assert "no constructor artifact" in outcome.get("reason", ""), outcome
    liable = [l for l in outcome.get("liabilities", [])
              if l.get("party") == "constructor"]
    assert liable, outcome
