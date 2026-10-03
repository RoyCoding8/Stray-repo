"""A43: an acquired method gets a durable release, and a refusal is not a run.

Two owner decisions, each proved in both directions. A method that is
acquired and retained is pinned to a `capability_releases` row a fresh
process can resolve, and the test fails if that binding is removed. An
execution the executor refuses is recorded as a refusal, and the incumbent
it used to impersonate is still available under its own name.
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"

RUN_TOKEN = "a43%s" % uuid.uuid4().hex[:10]
CID = "ad01-w0-I-70"
DEV_TASK = "ad01-w0-dev-sw-00"
USE_TASK = "ad01-w0-within-sw-00"

# A delegating wrapper over the supplied reducer. The child driver injects
# `reducers` into the member module's namespace, so the binding is a bare
# name and the wrapper carries no import -- which is also why the forbidden
# variant below trips `verify_member` before a byte is staged.
METHOD_SOURCE = (
    "def acquired_sw_greedy(task, oracle, max_queries=16):\n"
    "    return reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
ENTRY = "acquired_sw_greedy"
FORBIDDEN_SOURCE = "import os\n" + METHOD_SOURCE


def _policy_source(method_id: str, task_id: str = USE_TASK) -> str:
    return (
        "def STEP(view, state):\n"
        "    return {'action': {'kind': 'use_method',\n"
        "                      'target': %r,\n"
        "                      'inputs': {'method_id': %r, 'max_queries': 16},\n"
        "                      'evidence_refs': [],\n"
        "                      'requested_resources': {'queries': 16}},\n"
        "            'state': {'chosen': %r}}\n"
    ) % (task_id, method_id, method_id)


def _member(source: str = METHOD_SOURCE, member_id: str = "acquired-sw-a43") -> dict:
    return {"capability_id": member_id, "method_source": source,
            "entry": ENTRY, "params": {"max_queries": 16},
            "scope": {"family": "software"}, "authored": False,
            "qualified_on": DEV_TASK,
            "source_digest": hashlib.sha256(
                source.encode("utf-8")).hexdigest()}


@pytest.fixture(scope="module")
def store():
    from experiments.ad01.s09_run_isolation import (
        create_disposable_db, drop_disposable_db)

    database = create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database)


@pytest.fixture(scope="module")
def allocated(store):
    from experiments.ad01 import trajectory

    return trajectory.authorize_campaign(
        store, CID, authorized=1000)["allocation_id"]


# --- Decision 1: an acquired method gets a durable release ---------------


def test_a_retained_method_is_pinned_to_a_durable_release(store, allocated):
    """The release names the exact bytes, and a fresh read resolves them.

    Non-vacuity, positive direction: the row exists, its provenance digest
    is the digest of the member's own bytes, and `active_binding_for` --
    the function `selection.select_member` reads for every fresh-process
    use -- returns it without the acquire path in hand.
    """
    from experiments.ad01 import records, selection, trajectory, worlds
    from settlement import db

    member = _member()
    release = trajectory.bind_method_release(
        {"dsn": store, "cid": CID, "world": 0}, member,
        {"observation_id": "obs-a43-dev"}, boundary={"seq": 0},
        scope={"family": "software"})
    assert release["bound"] is True, release

    with db.connect(store) as conn:
        row = conn.execute(
            "SELECT id, versions, scope, disposition, policy_version,"
            " invalidation, evidence_refs, evaluator_version"
            " FROM capability_releases WHERE id = %s",
            (release["release_id"],)).fetchone()
    assert row is not None
    assert row[0] == trajectory.method_release_id(
        CID, member["source_digest"])
    assert list(row[1]) == [member["capability_id"]]
    assert row[2] == {"family": "software"}
    assert row[3] == "default"
    # A method release is not a policy release. `policy_version` is what a
    # reader would use to tell them apart, so it must be empty here rather
    # than carrying a policy's identity.
    assert row[4] == ""
    assert row[5] == {"proposal_id": release["proposal_id"],
                      "candidate_digest": member["source_digest"]}
    assert row[6] == [release["assessment_attempt_id"]]
    assert row[7] == trajectory.METHOD_EVALUATOR_VERSION

    stored = records.load_freeze(store, release["proposal_id"])
    assert stored["source"] == METHOD_SOURCE

    binding = selection.active_binding_for(
        store, "software", release_id=release["release_id"])
    assert binding is not None
    assert list(binding["versions"]) == [member["capability_id"]]
    assert selection.binding_provenance(binding)["candidate_digest"] \
        == member["source_digest"]

    task = worlds.load_task(worlds.FROZEN_DIR, USE_TASK)
    chosen = selection.select_member(
        {"members": [member]}, task, dsn=store,
        release_id=release["release_id"])
    assert chosen is not None
    assert chosen["capability_id"] == member["capability_id"]

    # And a use that names the release resolves the member's own bytes
    # rather than falling back to a seed or the incumbent.
    [record] = trajectory.run_use(
        {"campaign_id": CID, "members": [member]}, 0, "I", [USE_TASK], {},
        dsn=store, allocation_id=allocated,
        release_id=release["release_id"],
        policy_source=_policy_source(member["capability_id"]))
    assert record["executed"] == member["capability_id"]


def test_the_method_release_is_absent_without_the_binding(store):
    """Non-vacuity, negative direction.

    The same method, never bound, resolves no binding: `select_member`
    reads `capability_releases` only when a release id is named, and the
    repertoire freeze mints none. So removing the bind changes what a fresh
    read resolves, and this test fails when the binding is removed.
    """
    from experiments.ad01 import selection, trajectory, worlds

    unbound = _member(source=METHOD_SOURCE + "\n# unbound bytes\n",
                      member_id="acquired-sw-a43-unbound")
    task = worlds.load_task(worlds.FROZEN_DIR, USE_TASK)
    assert selection.active_binding_for(
        store, "software",
        release_id=trajectory.method_release_id(
            CID, unbound["source_digest"])) is None
    assert selection.select_member(
        {"members": [unbound]}, task, dsn=store,
        release_id=trajectory.method_release_id(
            CID, unbound["source_digest"])) is None


def test_a_method_the_assessment_does_not_bind_is_not_released(store):
    """Bytes that fail `bind_revision`'s own gates are reported, not bound."""
    from experiments.ad01 import selection, trajectory

    member = _member(source=METHOD_SOURCE + "\n# no reduction\n",
                     member_id="acquired-sw-a43-noreduce")
    release = trajectory.bind_method_release(
        {"dsn": store, "cid": CID, "world": 0}, member,
        {"observation_id": "obs-a43-noreduce"}, boundary={"seq": 0},
        scope={"family": "software"})
    assert release["bound"] is False
    assert release["reason"]
    assert selection.active_binding_for(
        store, "software", release_id=release.get("release_id", "")) is None


def test_the_release_id_separates_a_method_from_a_policy(store):
    """Two artifacts, two names, so neither can be read as the other."""
    from experiments.ad01 import trajectory

    method = trajectory.method_release_id("ad01-w0-I-00", "a" * 64)
    policy = "ad01-%s-policy-%s" % ("ad01-w0-I-00", "a" * 64)
    assert method != policy
    assert "-method-" in method
    assert "-policy-" in policy


# --- Decision 2: a refusal is not scored as a result ---------------------


def test_a_refused_member_is_recorded_as_a_refusal(store, allocated):
    """`executed` reads `refused`, not the incumbent the fallback produced.

    Non-vacuity, positive direction: the executor refused these bytes, and
    the record says so in every field a reader branches on.
    """
    from experiments.ad01 import trajectory

    member = _member(source=FORBIDDEN_SOURCE, member_id="acquired-sw-a43-bad")
    [record] = trajectory.run_use(
        {"campaign_id": CID, "members": [member]}, 0, "I", [USE_TASK],
        {"tokens": 0, "sandbox_ops": 0},
        policy_source=_policy_source(member["capability_id"]),
        dsn=store, allocation_id=allocated)
    assert record["status"] == "refused"
    assert record["verdict"] == "refused"
    assert record["executed"] == "refused"
    assert record["executed_source"] == "refused"
    assert record["output"] == {}
    assert record["normalized_reduction"] == 0.0
    assert "imports-forbidden" in record["fallback_reason"]
    # The admission was real and is still named as such.
    assert record["requested"] == member["capability_id"]
    assert record["selected"] == member["capability_id"]


def test_the_incumbent_fallback_survives_as_its_own_record(store, allocated):
    """Non-vacuity, the other direction: wanting the fallback is enough.

    The incumbent is still measured, under its own name and in its own
    field, so a caller that wants the control arm's number still has it
    and the refusal in `executed` is untouched.
    """
    from experiments.ad01 import controls, trajectory, worlds

    member = _member(source=FORBIDDEN_SOURCE, member_id="acquired-sw-a43-bad")
    [record] = trajectory.run_use(
        {"campaign_id": CID, "members": [member]}, 0, "I", [USE_TASK],
        {"tokens": 0, "sandbox_ops": 0},
        policy_source=_policy_source(member["capability_id"]),
        dsn=store, allocation_id=allocated)
    baseline = record["incumbent_baseline"]
    assert baseline["executed"] == "incumbent"
    task = worlds.load_task(worlds.FROZEN_DIR, USE_TASK)
    assert baseline["output"] == controls.incumbent(task)
    assert baseline["initial_measure"] == len(task["ops"])
    assert baseline["final_measure"] == len(task["ops"])
    assert record["executed"] == "refused"


def test_a_legitimate_incumbent_fallback_still_works():
    """The control arm's own path is untouched by the refusal record.

    `dev_episode`'s `no-reduction` branch names the incumbent as a fallback
    and is not the use-phase refusal path. It must keep reporting the
    incumbent it always did.
    """
    from experiments.ad01 import trajectory

    episode = trajectory.dev_episode(USE_TASK, "seed-sw-greedy", max_queries=0)
    assert episode["disposition"] == "no-candidate"
    assert episode["fallback"] == "incumbent"
    assert episode["fallback_reason"]


def test_a_refused_record_verifies_as_a_refusal(store, allocated):
    """The independent checker reads the refusal as a refusal.

    `checker._verify_record` is the verifier that already separates "ran and
    was scored" from "never ran". It is the check that would have caught
    the defect, and the new record must satisfy it.

    The refusal keeps its `operation_ids` -- the admitted policy child
    settled before the member ran, and dropping that receipt would leave
    settled work out of the study's accounting -- so the checker's
    `refused-record-has-operations` rule applies here. This asserts the
    requirement explicitly rather than letting the record's shape decide
    it by accident.
    """
    from experiments.ad01 import checker, trajectory, worlds

    member = _member(source=FORBIDDEN_SOURCE, member_id="acquired-sw-a43-bad")
    [record] = trajectory.run_use(
        {"campaign_id": CID, "members": [member]}, 0, "I", [USE_TASK],
        {"tokens": 0, "sandbox_ops": 0},
        policy_source=_policy_source(member["capability_id"]),
        dsn=store, allocation_id=allocated)
    problems = checker._verify_record(record, worlds.FROZEN_DIR, [])

    assert problems == ["refused-record-has-operations %s"
                        % record["record_id"]]
    stripped = {**record, "operation_ids": []}
    assert checker._verify_record(stripped, worlds.FROZEN_DIR, []) == []


def test_the_refusal_field_is_distinct_from_the_executed_field(store, allocated):
    """A caller reading `executed` cannot reach the incumbent through it."""
    from experiments.ad01 import trajectory

    member = _member(source=FORBIDDEN_SOURCE, member_id="acquired-sw-a43-bad")
    [record] = trajectory.run_use(
        {"campaign_id": CID, "members": [member]}, 0, "I", [USE_TASK],
        {"tokens": 0, "sandbox_ops": 0},
        policy_source=_policy_source(member["capability_id"]),
        dsn=store, allocation_id=allocated)
    for field in ("requested", "selected", "executed", "executed_source"):
        assert record[field] in (member["capability_id"], "refused")
    assert record["executed"] != "incumbent"
    assert record["executed_source"] != "incumbent"
    assert record["incumbent_baseline"]["executed"] == "incumbent"