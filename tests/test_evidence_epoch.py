import io
import tarfile
import uuid

import pytest

from settlement import artifacts, store
from settlement.common import Command, MissingEvidence, ResultCode


def _archive_bytes(names):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in names:
            info = tarfile.TarInfo(name)
            info.size = 3
            tar.addfile(info, io.BytesIO(b"xyz"))
    return buf.getvalue()


def test_archive_traversal_member_rejected(migrated_db, tmp_roots):
    dsn = migrated_db
    raw = _archive_bytes(["../evil.txt"])
    import hashlib
    manifest = {"files": [{"path": "a.tgz", "kind": "archive", "unpack": True,
                           "digest": hashlib.sha256(raw).hexdigest(), "size": len(raw)}]}
    with pytest.raises(Exception):
        artifacts.stage_package(dsn, tmp_roots["staging"], manifest=manifest,
                                files={"a.tgz": raw})
