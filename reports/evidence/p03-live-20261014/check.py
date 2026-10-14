"""Recompute the archived P03 comparison using only the Python standard library."""
from __future__ import annotations

import hashlib
import json
import runpy
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
index = json.loads((root / "archive-index.json").read_text(encoding="utf-8"))
snapshot = root / "recompute_snapshot.py"
expected = manifest["source_sha256"]["experiments/context03/recompute.py"]
assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == expected, "Frozen checker differs"
with zipfile.ZipFile(root / "bundle.zip") as archive:
    assert len(archive.namelist()) == len(index), "Archive membership count differs"
    assert set(archive.namelist()) == set(index), "Archive membership differs"
    for name, digest in index.items():
        actual = hashlib.sha256(archive.read(name)).hexdigest()
        assert actual == digest, f"Archived bytes differ: {name}"
        if name.startswith("artifacts/"):
            assert actual == name.rsplit("/", 1)[-1], "Artifact identity differs"
    records = []
    for policy, condition in manifest["matrix"]:
        cell = f"p03-context03-{policy.replace('/', '-')}-{condition}"
        record = json.loads(archive.read(f"records/{cell}/cell.json"))
        freeze = json.loads(archive.read(f"records/{cell}/freeze.json"))
        assert record["freeze"] == freeze, "Cell freeze differs from archived freeze"
        records.append(record)
result = runpy.run_path(str(snapshot))["recompute"](manifest, records)
assert result == json.loads((root / "result.json").read_text(encoding="utf-8")), "Recomputed result differs"
print(json.dumps({"status": "pass", "archived_files": len(index),
                  "matrix_cells": result["matrix_cells"],
                  "dispatched_workers": result["dispatched_workers"],
                  "recorded_token_total": result["recorded_token_total"]}, sort_keys=True))
