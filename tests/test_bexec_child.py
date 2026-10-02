"""B-EXEC slice 1: shared admitted child path (acceptance A1).

The stamp channel (snapshot bytes plus a hash comment) must be gone:
unexpected-but-valid model bytes supplied at the configured adapter seam
reach the staged tree verbatim. DB ec02test_bexec only, never ec02test_live.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from experiments.coord02 import entry
from experiments.coord02 import oracle
from experiments.coord02.controller import seed_episode
from experiments.coord02.experience import snapshot_files
from settlement import db
from settlement.gateway import (
    GatewayAdapter,
    GatewayStatus,
    ModelResponse,
    Usage,
)

DSN = os.environ.get(
    "EC02_BEXEC_DSN",
    "dbname=ec02test_bexec host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"

TASK = oracle.SPLITS["development"][0]


class RecordingChildAdapter(GatewayAdapter):
    """Model-seam double: replays one unexpected-but-valid repair."""

    label = "BEXEC-RECORDING-CHILD"

    def __init__(self, files: dict):
        self._files = dict(files)
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        return ModelResponse(
            request.operation_id,
            json.dumps({"files": self._files,
                        "notes": "bexec unexpected repair"}),
            {"bexec-recording-child": True},
            Usage(input_tokens=7, output_tokens=11), "stop")

    def cancel(self, operation_id):
        return False


def _child_repair_double(task, repair_files):
    from experiments.coord02 import entry as _entry
    import json as _json
    from settlement.gateway import (GatewayAdapter as _GA,
                                    GatewayStatus as _GS,
                                    ModelResponse as _MR, Usage as _U)

    class _Repair(_GA):
        label = "BEXEC-REPAIR-DOUBLE"

        def __init__(self):
            self.calls = []

        def check_discovery(self):
            return _GS.CONFIGURED

        def check_auth(self):
            return _GS.AUTHENTICATED

        def infer(self, request):
            self.calls.append(request)
            if "a-decision" in request.operation_id:
                proposal = {"action": "plan", "shape": "single",
                            "children": _entry.plan_children(
                                task, "single")}
                return _MR(request.operation_id, _json.dumps(proposal),
                           {}, _U(input_tokens=1, output_tokens=1), "stop")
            return _MR(request.operation_id, _json.dumps(
                {"files": repair_files, "notes": "bexec repair"}),
                {}, _U(input_tokens=1, output_tokens=1), "stop")

        def cancel(self, operation_id):
            return False

    return _Repair()


def test_run_cell_records_child_repair_bytes_through_submit():
    import tempfile
    from experiments.coord02 import entry as _entry
    from experiments.coord02 import freeze as _freeze
    from experiments.coord02 import oracle as _oracle
    from settlement import db as _db
    from settlement.launcher_local import LocalLauncher
    task = _oracle.SPLITS["development"][0]
    snap = snapshot_files(task)
    owned = sorted(_oracle.worker_files(task))
    repair = {pp: snap[pp] + "\n\nBEXEC_CELL_REPAIR = 1\n"
              for pp in owned}
    _db.apply_migrations(DSN, MIGRATIONS)
    gw = _child_repair_double(task, repair)
    freeze = _freeze.build_freeze("coord02-bexec-cell",
                                  source_sha="bexec-base")

    def launcher_factory(tag):
        return {"local-process": LocalLauncher(
            Path(tempfile.mkdtemp(prefix="bexec-cell-")) / tag)}

    cell = _entry.run_cell(
        DSN, freeze=freeze, task_id=task, panel="development",
        repeat=1, arm="A", launcher_factory=launcher_factory,
        package_digest="none", package_text="doubled-dev",
        source_sha="bexec-base", config_digest="entry-cell",
        gateway=gw, model="bexec-cell-double")
    assert cell.outcome.get("status") in ("success", "join-failed-terminal"), cell.outcome
    tree = _entry.restage_tree(DSN, cell.outcome)
    assert tree is not None
    assert all("coord02-admitted" not in body
               for body in tree.values())
    assert any(tree[pp] != snap[pp] for pp in owned)


def test_shared_child_path_stages_model_bytes_verbatim():
    assert "live" not in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute('TRUNCATE TABLE "%s" CASCADE' % row[0])
        conn.commit()
    snap = snapshot_files(TASK)
    assert snap, "no snapshot files for %s" % TASK
    owned = sorted(snap)
    repair = {p: snap[p] + "\n\nBEXEC_REPAIR = 1\n" for p in owned}
    gw = RecordingChildAdapter(repair)
    seed = seed_episode(DSN, "bexec-child-%s" % uuid.uuid4().hex[:8],
                        dict(snap))
    child = {"node_id": "w1", "obligation": "repair whole tree",
             "owned_paths": list(owned),
             "output_contract": {"entry": "whole-tree",
                                 "checks": ["public"]},
             "input_bindings": {"base_%d" % i: p
                                for i, p in enumerate(owned)}}
    staged = entry.dispatch_admitted_child(
        DSN, gateway=gw, model="bexec-recording", task_id=TASK,
        node="w1", child=child, rendered={},
        allocation_id=seed["allocation_id"],
        operation_id="bexec-child-%s" % uuid.uuid4().hex[:8])
    assert gw.calls, "child dispatch never reached the gateway"
    assert staged == repair, \
        "model bytes did not reach the staged tree verbatim"
    assert all("coord02-admitted" not in body
               for body in staged.values()), \
        "stamp channel still present in staged bytes"
    assert any(staged[p] != snap[p] for p in owned), \
        "staged tree is the unchanged snapshot"
    from settlement import team
    op_id = gw.calls[0].operation_id
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT receipt_identity, outcome FROM receipts"
                " WHERE operation_id = %s AND receipt_identity = %s",
                (op_id, "gw:%s" % op_id))
            row = cur.fetchone()
        conn.commit()
    assert row is not None and row[1] == "success", \
        "child model call left no settled success receipt"
    assert team.output_digest(dict(staged)) == team.output_digest(
        dict(repair)), "staged bytes were not durably registered"
