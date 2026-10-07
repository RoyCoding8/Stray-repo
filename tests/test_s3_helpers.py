"""Shared S3 fixtures: seeded grant/allocation/investigation/attempt and
method-artifact staging. Imported by test_s3_*.py; defines no tests itself."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


from settlement import artifacts, store
from settlement.common import Command

FIXTURES = Path(__file__).parent / "fixtures"


def seed_env(dsn, tag, authorized=100_000):
    store.seed_grant(dsn, Command(request_id=f"{tag}-grant", payload={
        "version": 1, "charter_text": "s3", "authority_grant": {}, "envelopes": {}}))
    store.seed_allocation(dsn, Command(request_id=f"{tag}-alloc", payload={
        "allocation_id": f"{tag}-alloc", "domain": "s3", "authorized": authorized,
        "max_occupancy": 64}))
    store.admit_commitment(dsn, Command(request_id=f"{tag}-inv", payload={
        "investigation_id": f"{tag}-inv", "objective": "s3",
        "scope": {}, "obligations": {}}))
    return {"allocation_id": f"{tag}-alloc", "investigation_id": f"{tag}-inv"}


def acquire(dsn, tag, attempt_id, env, allocation_id=None):
    return store.acquire_work(dsn, Command(request_id=f"{tag}-acq-{attempt_id}", payload={
        "attempt_id": attempt_id, "investigation_id": env["investigation_id"],
        "allocation_id": allocation_id or env["allocation_id"]}))


def bind_assignment(dsn, tag, assignment_id, invocation_ref, content=None,
                    evaluator_id="s3-eval", evaluator_version="v1"):
    from settlement import evaluation
    from settlement.common import payload_digest

    body = dict(content or {"code": f"{tag}-candidate"})
    evaluation.submit_candidate(
        dsn, Command(request_id=f"{tag}-sub-{assignment_id}", payload={}),
        assignment_id, body)
    return evaluation.bind_evaluation(
        dsn, Command(request_id=f"{tag}-bind-{assignment_id}", payload={}),
        assignment_id, candidate_digest=payload_digest(body),
        evaluator_id=evaluator_id, evaluator_version=evaluator_version,
        invocation_ref=invocation_ref)


def stage_method(dsn, staging_root, source_path, entry_name, access_label="public"):
    raw = Path(source_path).read_bytes()
    manifest = {"files": [{"path": entry_name, "kind": "file",
                           "digest": hashlib.sha256(raw).hexdigest(),
                           "size": len(raw)}],
                "entry": entry_name, "verify_args": ["--selftest"]}
    return artifacts.stage_package(dsn, staging_root, manifest=manifest,
                                   files={entry_name: raw}, access_label=access_label)


def publish_method(dsn, tag, artifacts_root, receipt):
    return artifacts.publish_package(dsn, Command(request_id=f"{tag}-pub"),
                                     artifacts_root, receipt)
