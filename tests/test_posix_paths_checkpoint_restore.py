"""A recovery-set path is a value, not a rendering of the host filesystem.

`scripts/checkpoint.py` writes `str(path.relative_to(root))` into
`manifest.json`, and `scripts/restore.py` compares a re-walk of the extracted
tar against `sorted(e["path"] for e in manifest["artifacts"])`. Both sides use
the host separator, so a Windows checkpoint describes a recovery set no Linux
host can verify, and `restore.py` records
`artifact tar contents differ from manifest` against a perfectly intact
backup. That is a recovery-path defect: the operator is told the archive is
damaged when it is not.

The tar itself is already portable. `tarfile.gettarinfo` applies
`arcname.replace(os.sep, "/")`, so the members it wrote were forward-slash on
this host. Only the manifest disagreed with them.

These call `run_restore` as an operator does, with the database stubbed at the
seams it already has. No PostgreSQL is reachable here, so the DB halves of
`run_restore` are substituted and the artifact verification, which is the part
under test, runs for real over a real tar.

Every assertion names a literal path, so each one fails if either function
goes back to the host-native form.
"""

import json
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import restore
from checkpoint import _artifact_manifest, _write_tar

NESTED = "world-0/dev/ad01-w0-dev-gr-00.json"
TOP = "world-0/top.txt"
ROW_COUNTS = {"control": 0, "operations": 0}


def _artifact_tree(root: Path) -> Path:
    (root / "world-0" / "dev").mkdir(parents=True)
    (root / "world-0" / "dev" / "ad01-w0-dev-gr-00.json").write_bytes(b'{"task": 1}\n')
    (root / "world-0" / "top.txt").write_bytes(b"top\n")
    return root


def _recovery_set(root: Path) -> tuple[Path, list[dict]]:
    """A backup dir holding what checkpoint.py writes, over a real artifact tree."""
    out = root / "backup"
    out.mkdir()
    _write_tar(_artifact_tree(root / "artifacts"), out / "artifacts.tar")
    entries = _artifact_manifest(root / "artifacts")
    manifest = {
        "source": {"database": "source_db", "commit": "0" * 40,
                   "artifacts_root": str((root / "elsewhere").resolve())},
        "migrations": [], "control": {}, "row_counts": ROW_COUNTS,
        "barrier": {}, "workflow": {"coordinated": False},
        "artifacts": entries,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    (out / "source_db.dump").write_bytes(b"not a real dump")
    return out, entries


def _restore_without_postgres(backup_dir: Path, artifacts_dir: Path) -> dict:
    """Run the real run_restore, substituting only its database calls."""
    empty = {name: 0 for name in ROW_COUNTS}
    schema = {"SELECT name FROM schema_migrations": [],
              "SELECT * FROM control WHERE id = 1": [{"id": 1}],
              "SELECT id, dispatch_state FROM operations": []}

    class _Cursor:
        def __init__(self, rows):
            self._rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, *_args):
            self._rows = schema.get(sql, [])

        def fetchone(self):
            return self._rows[0]

        def fetchall(self):
            return self._rows

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self, **_kw):
            return _Cursor([])

        def commit(self):
            pass

    class _Psycopg:
        @staticmethod
        def connect(_dsn):
            return _Conn()

    class _Store:
        @staticmethod
        def restore_fence(_dsn, _command):
            class _Result:
                code = type("C", (), {"value": "applied"})()
                data = {}
                detail = ""
            return _Result()

    originals = (restore._check_fresh, restore._restore_dump, restore._target_rows,
                 restore._extract_tar, restore._verify_restored_workflow)
    restore._check_fresh = lambda _dsn: []
    restore._restore_dump = lambda *_a, **_k: None
    restore._target_rows = lambda _dsn: dict(empty)
    restore._verify_restored_workflow = lambda m, *_a: (m, 0)
    real_extract = originals[3]
    restore._extract_tar = real_extract
    import sys as _sys
    _types = _sys.modules
    _types["psycopg"] = _Psycopg
    _types["psycopg.rows"] = type("rows", (), {"dict_row": None})
    _types["settlement"].store = _Store
    try:
        return restore.run_restore(backup_dir, "dbname=target_db", artifacts_dir)
    finally:
        (restore._check_fresh, restore._restore_dump, restore._target_rows,
         restore._extract_tar, restore._verify_restored_workflow) = originals
        del _types["psycopg"]
        del _types["psycopg.rows"]


def test_the_checkpoint_manifest_names_its_artifacts_with_forward_slashes():
    with tempfile.TemporaryDirectory() as root:
        entries = _artifact_manifest(_artifact_tree(Path(root)))
    assert [e["path"] for e in entries] == [NESTED, TOP]


def test_an_intact_recovery_set_restores_without_an_artifact_mismatch():
    with tempfile.TemporaryDirectory() as root:
        root = Path(root)
        backup, _ = _recovery_set(root)
        report = _restore_without_postgres(backup, root / "restored")
    assert "artifact tar contents differ from manifest" not in report["mismatches"]
    assert report["mismatches"] == []
    assert report["ok"] is True


def test_a_recovery_set_restored_onto_another_host_verifies():
    """The cross-host case: the manifest is the artifact that travels.

    A recovery set is copied off the machine that made it. This asserts the
    committed form, forward slashes, over a tar this host produced, which is
    the pair that fails today.
    """
    with tempfile.TemporaryDirectory() as root:
        root = Path(root)
        backup, entries = _recovery_set(root)
        manifest = json.loads((backup / "manifest.json").read_text())
        manifest["artifacts"] = [{"path": e["path"].replace("\\", "/"),
                                  "size": e["size"], "sha256": e["sha256"]}
                                 for e in entries]
        assert [e["path"] for e in manifest["artifacts"]] == [NESTED, TOP]
        (backup / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        report = _restore_without_postgres(backup, root / "restored")
    assert "artifact tar contents differ from manifest" not in report["mismatches"]
    assert report["mismatches"] == []


def test_the_restored_tree_lands_where_the_manifest_names_it():
    with tempfile.TemporaryDirectory() as root:
        root = Path(root)
        backup, entries = _recovery_set(root)
        _restore_without_postgres(backup, root / "restored")
        restored = root / "restored"
        for entry in entries:
            assert (restored / entry["path"]).is_file(), \
                f"{entry['path']} did not land as named"
        assert sorted(p.relative_to(restored).as_posix()
                      for p in restored.rglob("*") if p.is_file()) == [NESTED, TOP]


def test_the_artifact_tar_member_names_are_forward_slash_already():
    """Guards the pairing: the tar was always portable, the manifest was not.

    If this ever fails, fixing the manifest alone is not enough; both halves
    of the comparison have to name files the same way.
    """
    with tempfile.TemporaryDirectory() as root, \
            tempfile.TemporaryDirectory() as out:
        _write_tar(_artifact_tree(Path(root)), Path(out) / "artifacts.tar")
        with tarfile.open(Path(out) / "artifacts.tar", "r") as tar:
            names = sorted(m.name for m in tar.getmembers())
    assert names == [NESTED, TOP]
