"""B-VERIF slice 1: public-path lock (acceptance A1/A5).

Proves the PUBLIC panel path (run_cell on coordinates taken from the real
freeze schedule, exported via write_evidence) stages model repair bytes
verbatim: a recording adapter double at the configured gateway seam serves
unexpected-but-valid repair bytes, and the exported evidence record must
carry those non-snapshot bytes with no stamp comment. DB ec02test_bverif
only, never ec02test_live.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from experiments.coord02 import entry
from experiments.coord02 import freeze as freeze_mod
from experiments.coord02 import oracle
from experiments.coord02.experience import snapshot_files
from settlement import db
from settlement.gateway import (
    GatewayAdapter,
    GatewayStatus,
    ModelResponse,
    Usage,
)
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get(
    "EC02_BVERIF_DSN",
    "dbname=ec02test_bverif host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"

MARKER = 'BVERIF_PUBLIC_REPAIR = "public-path-lock"\n'


class RecordingPublicAdapter(GatewayAdapter):
    """Model-seam double: valid A proposal, then unexpected repair bytes."""

    label = "BVERIF-RECORDING-PUBLIC"

    def __init__(self, task: str, repair: dict):
        self._task = task
        self._repair = dict(repair)
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        if "a-decision" in request.operation_id:
            proposal = {"action": "plan", "shape": "single",
                        "children": entry.plan_children(self._task,
                                                        "single")}
            return ModelResponse(request.operation_id, json.dumps(proposal),
                                 {}, Usage(input_tokens=1, output_tokens=1),
                                 "stop")
        return ModelResponse(
            request.operation_id,
            json.dumps({"files": self._repair,
                        "notes": "bverif public unexpected repair"}),
            {}, Usage(input_tokens=1, output_tokens=1), "stop")

    def cancel(self, operation_id):
        return False


def test_public_panel_path_exports_model_repair_bytes_verbatim(tmp_path):
    assert "live" not in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute('TRUNCATE TABLE "%s" CASCADE' % row[0])
        conn.commit()
    freeze = freeze_mod.build_freeze("coord02-bverif-public",
                                     source_sha="bverif-base")
    coord = next(c for c in freeze["schedule"]
                 if c["panel"] == "development" and c["arm"] == "A"
                 and c["repeat"] == 1)
    task = coord["task"]
    snap = snapshot_files(task)
    owned = sorted(oracle.worker_files(task))
    assert owned and all(p in snap for p in owned)
    repair = {p: snap[p] + "\n" + MARKER for p in owned}
    gw = RecordingPublicAdapter(task, repair)

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(tmp_path / "launch" / tag)}

    cell = entry.run_cell(
        DSN, freeze=freeze, task_id=task, panel=coord["panel"],
        repeat=coord["repeat"], arm=coord["arm"],
        launcher_factory=launcher_factory,
        package_digest="none", package_text="doubled-dev",
        source_sha="bverif-base", config_digest="entry-bverif",
        gateway=gw, model="bverif-public-double")
    assert cell.outcome.get("plan_id"), "no admitted plan on the outcome"
    assert any(c.operation_id.startswith(cell.outcome["plan_id"])
               and c.operation_id.endswith(":work:model") for c in gw.calls), \
        "public path never reached the admitted child dispatch"
    summary = entry.write_evidence([cell], freeze=freeze,
                                    evidence_root=tmp_path / "evidence",
                                    dsn=DSN)
    assert summary["records"] == 1
    pairs = list((tmp_path / "evidence" / "episodes").glob("*.json"))
    assert len(pairs) == 1
    record = json.loads(pairs[0].read_text())
    assert record["candidate_digest"], \
        "public path staged no candidate tree (dispatch bypassed?)"
    staged: dict = {}
    for path in (tmp_path / "evidence" / "candidates"
                 / record["candidate_digest"]).rglob("*"):
        if path.is_file() and path.suffix == ".py":
            staged[path.name] = path.read_text()
    assert staged, "exported candidate tree carries no python files"
    assert any(MARKER.strip() in body for body in staged.values()), \
        "model repair bytes did not reach the exported evidence record"
    assert all("coord02-admitted" not in body
               for body in staged.values()), \
        "stamp channel still present in exported bytes"
    assert any(staged[name] != snap[p] for p in owned
               for name in [Path(p).name] if name in staged), \
        "exported tree is the unchanged snapshot"
