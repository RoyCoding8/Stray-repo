"""S09-M5 prospective pilot: failing repro plus deterministic gates.

The first two tests are the red-first repro: the offline verifier must
name a missing sealed use record and a claimed operation with no settled
receipt. They stay red until scripts/s09_verify.py names both.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts import s09_verify as V


def _freeze():
    return {
        "study_id": "s09-pilot-n5",
        "study_root": "s09-m5-repro",
        "arms": ["P0", "P1", "P2"],
        "order": ["assess-P0-w1-sw"],
        "development": [],
        "construction_allowance": {
            "P1": {"init": 1, "repair": 1},
            "P2": {"init": 1, "repair": 1}},
        "assessment": [{
            "episode_id": "assess-P0-w1-sw",
            "arm": "P0",
            "world": 1,
            "domain": "software",
            "use_tasks": ["ad01-w1-within-sw-00",
                          "ad01-w1-transfer-sw-00"]}],
        "caps": {
            "per_episode": {"policy_steps": 6, "model_calls": 6},
            "study_model_calls": 100,
            "construction_calls": 4,
            "dev_episodes": 4,
            "assessment_episodes": 12},
        "metric_rule": {"quality": "preserved-plus-reduction",
                        "compare": ["P2-vs-P0", "P2-vs-P1"]},
        "resource_rule": {"unknown_blocks_claims": True},
        "freeze_digest": "repro-digest",
    }


def _episode():
    return {"episode_id": "assess-P0-w1-sw", "arm": "P0",
            "campaign_id": "ad01-w1-I-00", "policy_steps": 1,
            "model_calls": 0, "witness_queries": 1,
            "status": "complete", "operations": []}


def _record(task):
    return {"record_id": "assess-P0-w1-sw-%s" % task,
            "episode_id": "assess-P0-w1-sw", "arm": "P0",
            "task_id": task, "executed": "incumbent",
            "executed_source": "incumbent",
            "fallback_reason": "no eligible repertoire member",
            "costs": {"witness_queries": 0}, "operation_ids": []}


def _bundle(records, operations):
    return {"freeze": _freeze(),
            "development": [],
            "construction": {},
            "assessment": [_episode()],
            "use_records": records,
            "operations": operations,
            "accounting": V.empty_accounting(),
            "refusal_probes": [],
            "conformance_replay": {"status": "conformance",
                                   "verdict": "repro-bypass"}}


def test_verifier_names_missing_use_record():
    bundle = _bundle([_record("ad01-w1-within-sw-00")],
                     {})
    out = V.verify_bundle(bundle)
    assert out["status"] == "fail"
    assert ("missing-use-record "
            "assess-P0-w1-sw-ad01-w1-transfer-sw-00") in out["problems"]


def test_verifier_names_missing_receipt():
    episode = _episode()
    episode["operations"] = ["op-claimed-1"]
    bundle = _bundle([_record("ad01-w1-within-sw-00"),
                      _record("ad01-w1-transfer-sw-00")],
                     {})
    bundle["assessment"] = [episode]
    out = V.verify_bundle(bundle)
    assert out["status"] == "fail"
    assert "missing-receipt for-operation op-claimed-1" in out["problems"]


TOKEN = "m5"


@contextlib.contextmanager
def _store():
    """One store this run owns, on whichever cluster the operator named.

    A fixed name is shared state on the cluster, so a sibling run's teardown
    destroys the store this one is still writing to.
    """
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = iso.create_disposable_db(TOKEN, admin_dsn=admin_dsn,
                                        migrations_dir=ROOT / "migrations")
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database, admin_dsn=admin_dsn)


@pytest.fixture(scope="module")
def pilot_bundle(tmp_path_factory):
    from scripts import s09_pilot as P
    with _store() as dsn:
        dest = tmp_path_factory.mktemp("r1")
        bundle = P.run_study(dsn, dest, namespace_token="m5a")
        yield bundle, dest


def test_doubled_pilot_verifies_green(pilot_bundle):
    bundle, _dest = pilot_bundle
    out = V.verify_bundle(bundle)
    assert out["problems"] == []
    assert out["status"] == "pass"
    assert len(bundle["development"]) == 4
    assert len(bundle["assessment"]) == 12
    assert len(bundle["use_records"]) == 24
    assert bundle["construction"]["P1"]["status"] == "available"
    assert bundle["construction"]["P1"]["calls"] == 1
    assert bundle["construction"]["P2"]["status"] == "unavailable"
    assert bundle["construction"]["P2"]["calls"] == 2
    assert out["recomputed"]["worst_case"] == 100
    assert out["recomputed"]["model_calls"] <= 100


def test_worst_case_ceiling_derived_from_code():
    from experiments.ad01 import construct
    from scripts import s09_pilot as P
    freeze = P.build_freeze()
    worst = (len(freeze["development"]) + len(freeze["assessment"])) \
        * freeze["caps"]["per_episode"]["model_calls"] \
        + construct.CONSTRUCTION_CALL_CEILING
    assert worst == 100
    assert freeze["caps"]["study_model_calls"] == worst


def test_unavailable_arm_uses_incumbent_only(pilot_bundle):
    bundle, _dest = pilot_bundle
    p2 = [r for r in bundle["use_records"] if r["study_arm"] == "P2"]
    assert len(p2) == 8
    assert {r["executed"] for r in p2} == {"incumbent"}
    assert all(r["fallback_reason"].startswith("arm-unavailable:")
               for r in p2)


def test_refusal_probes_spent_nothing(pilot_bundle):
    bundle, _dest = pilot_bundle
    assert len(bundle["refusal_probes"]) == 2
    for probe in bundle["refusal_probes"]:
        assert probe["refused"] is True
        assert probe["observed_new_ops"] == []


def test_conformance_replay_recorded(pilot_bundle):
    bundle, _dest = pilot_bundle
    conformance = bundle["conformance_replay"]
    assert conformance["status"] == "conformance"
    assert conformance["identity"] == "supported"
    assert conformance["changed"] != "supported"


def _drop_timings(value):
    """Strip measured durations, which are properties of the host."""
    if isinstance(value, dict):
        return {k: _drop_timings(v) for k, v in value.items()
                if k != "wall_ms"}
    if isinstance(value, list):
        return [_drop_timings(v) for v in value]
    return value


def test_doubled_pilot_is_deterministic(pilot_bundle):
    from scripts import s09_pilot as P
    _bundle_a, dest_a = pilot_bundle
    with _store() as dsn_b:
        dest_b = dest_a.parent / "r2"
        # The same token as run A on purpose. A namespace token is now
        # mandatory and it changes the study root, the freeze and every
        # operation id, so two runs under different tokens differ for a
        # reason that has nothing to do with determinism. Determinism means
        # the same study twice, which is the same token on two databases.
        bundle_b = P.run_study(dsn_b, dest_b, namespace_token="m5a")
    names = ("freeze", "development", "construction", "assessment",
             "use_records", "operations", "accounting",
             "refusal_probes", "conformance_replay")
    for name in names:
        text_a = (dest_a / ("%s.json" % name)).read_text()
        text_b = (dest_b / ("%s.json" % name)).read_text()
        left, right = json.loads(text_a), json.loads(text_b)
        if name == "freeze":
            # `frozen_at` is a wall clock, so two runs of the same study
            # differ on it by design. What must be reproducible is the
            # freeze's identity, which is what `freeze_digest` covers, and
            # the digest deliberately excludes the timestamp.
            assert left["freeze_digest"] == right["freeze_digest"]
            left = {k: v for k, v in left.items() if k != "frozen_at"}
            right = {k: v for k, v in right.items() if k != "frozen_at"}
        if name == "construction":
            # `wall_ms` is a duration measured on the machine, not a
            # property of the study. Two runs of the same frozen study
            # differ on it and always did; comparing it measures the host,
            # not the pipeline. Everything else in the construction record
            # is still compared exactly.
            left = _drop_timings(left)
            right = _drop_timings(right)
        assert left == right, name
    assert V.verify_bundle(bundle_b)["status"] == "pass"


def test_the_store_is_named_for_this_run_not_for_the_file():
    """A fixed name is shared state; a sibling run's teardown destroys it.

    Two runs of this file on one cluster collided on one name, and the first
    teardown dropped the store the second was still writing to. The name
    carries a per-run token, so only a name this run minted is ever dropped
    and a second fixture can never reuse the first one's database.
    """
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    first = iso.create_disposable_db(TOKEN, admin_dsn=admin_dsn,
                                     migrations_dir=ROOT / "migrations")
    try:
        assert first.name.startswith(iso.DB_PREFIX + "_"), first.name
        assert TOKEN in first.name, first.name
        again = iso.create_disposable_db(TOKEN, admin_dsn=admin_dsn,
                                         migrations_dir=ROOT / "migrations")
        try:
            assert again.name != first.name
        finally:
            iso.drop_disposable_db(again, admin_dsn=admin_dsn)
    finally:
        iso.drop_disposable_db(first, admin_dsn=admin_dsn)
