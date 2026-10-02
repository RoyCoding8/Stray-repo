"""The effect identity is the identity of an operation that exists.

RF-02 repair, lane X4b, against `e442a02`. The independent reviewer measured,
against a real three-boundary campaign on PostgreSQL, that all three
`s09_policy_state.effect_id` values were absent from `operations` and that no
`attempt_observations` row carried an `operation_id`. Both sides of the
"admitted effect -> observation" arrow were durable rows and the binding
between them was `(investigation_id, seq)` alone.

Before this file, `trajectory._s09_effect_id(cid, seq)` returned the constant
`ad01-<cid>-b<seq>-effect`. Nothing inserted a row under that id and nothing
read it back, so the column named an identity that had never existed. The
assertions below are each the opposite of a green run, so a repaired run
cannot pass by accident, and each is a query against a real database rather
than a source-shape reading.

Nothing here fabricates an identity. Every assertion reads a row a production
path wrote, and the fabrication test plants an id and proves the production
derivation refuses it. The campaigns are entered through
`trajectory.run_campaign` with the fixture gateway only. No live model call,
no network, no credentials.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_inv_a_reviewer_source as reviewer

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "x4beffect"
CHARTER = {"objective": "reduce examples while preserving their witness",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 4, "diagnostic_queries": 16, "model_calls": 20}
TASKS = ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01", "ad01-w0-dev-sw-00"]


@pytest.fixture(scope="module")
def store():
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = iso.create_disposable_db(RUN_TOKEN, admin_dsn=admin_dsn,
                                        migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database, admin_dsn=admin_dsn)


class Constructor:
    """The offline fixture gateway. No network, no credentials."""

    def __init__(self, source=reviewer.ACQUIRED_METHOD):
        from settlement.gateway import Usage

        self.calls = []
        self.source = source
        self.usage = Usage(input_tokens=10, output_tokens=20)

    def check_discovery(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse

        self.calls.append(request)
        return ModelResponse(
            request.operation_id,
            json.dumps({"entry": self.source, "notes": "x4b reviewer"}),
            {}, self.usage, "stop")

    def cancel(self, operation_id):
        return False


def _query(dsn, sql, params=()):
    from experiments.ad01 import trajectory

    with trajectory._read_conn(dsn) as conn:
        rows = conn.execute(sql, params).fetchall()
        conn.commit()
        return [dict(row) for row in rows]


def _campaign(store, seq):
    """One campaign through the public entry, on a real disposable store."""
    from experiments.ad01 import agenda_policy, policy_step, trajectory

    cid = trajectory.campaign_id(0, "I", seq)
    gateway = Constructor()
    trajectory.authorize_campaign(store, cid, authorized=100000)
    consumer = agenda_policy.step_policy_consumer(
        policy_step.make_policy_artifact(reviewer.CHAIN_SOURCE,
                                         origin="authored-control"),
        dsn=store, cid=cid, charter=dict(CHARTER), world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid), study_root=cid,
        gateway=gateway, model="x4b-reviewer-double")
    out = trajectory.run_campaign(
        0, "I", CHARTER, CAPS, tasks=list(TASKS), campaign_seq=seq,
        dsn=store, consumer=consumer, constructor="model",
        gateway=gateway, model="x4b-reviewer-double")
    return cid, out


def _effect_rows(store, cid):
    return _query(
        store,
        "SELECT seq, attempt_id, effect_id, status, effect_record"
        " FROM s09_policy_state WHERE investigation_id = %s ORDER BY seq",
        (cid,))


def _bound_operations(store, cid):
    return _query(
        store,
        "SELECT id, allocation_id, settled, dispatch_state,"
        " payload->>'effect' AS effect FROM operations"
        " WHERE id LIKE %s ORDER BY id", ("ad01-%s%%" % cid,))


def _boundary_observations(store, cid):
    rows = _query(
        store,
        "SELECT o.id, o.content FROM attempt_observations o"
        " JOIN attempts a ON a.id = o.attempt_id"
        " WHERE a.investigation_id = %s AND o.content->>'kind' = 'boundary'"
        " ORDER BY o.content->>'seq'", (cid,))
    return {int(dict(row["content"])["seq"]): dict(row["content"])
            for row in rows}


def _admitted(store, seq):
    """The campaign plus the rows a reader would use to check the arrows."""
    cid, out = _campaign(store, seq)
    return {"cid": cid, "out": out, "effects": _effect_rows(store, cid),
            "operations": _bound_operations(store, cid),
            "observations": _boundary_observations(store, cid)}


# --- 1. the effect id names an operation that exists ---------------------


def test_an_admitted_effect_id_is_a_settled_operation_with_a_receipt(store):
    """Requirement 1. Every admitted effect id is a real `operations.id`.

    Over a campaign with at least three boundaries. This repeats the
    reviewer's own measurement rather than restating it: they found 3 of 3
    effect ids absent from `operations`, so a repaired run must find every
    admitted one present, settled, and carrying its own decided receipt. That
    is the A1 and A7 guarantee, asserted on the effect row rather than on the
    operation table in general.
    """
    run = _admitted(store, 481)
    cid, out, effects = run["cid"], run["out"], run["effects"]

    boundaries = [b["seq"] for b in out["boundaries"]]
    assert len(boundaries) >= 3, (
        "the campaign ran %d boundaries; the defect needs at least three to"
        " measure" % (len(boundaries),))
    assert [row["seq"] for row in effects] == boundaries

    admitted = [row for row in effects if row["effect_id"]]
    assert len(admitted) >= 2, (
        "only %d of %d boundaries admitted an effect identity; a repair that"
        " withdrew every identity would satisfy this vacuously"
        % (len(admitted), len(effects)))

    for row in admitted:
        effect_id = row["effect_id"]
        named = _query(
            store, "SELECT id, allocation_id, settled, dispatch_state"
            " FROM operations WHERE id = %s", (effect_id,))
        assert named, (
            "effect id %r for seq %d names no operations row"
            % (effect_id, row["seq"]))
        operation = named[0]
        assert operation["settled"] is True, (
            "effect id %r names an operation that never settled" % (effect_id,))
        assert operation["allocation_id"], (
            "effect id %r names an operation with no allocation" % (effect_id,))
        receipts = _query(
            store, "SELECT receipt_identity, outcome FROM receipts"
            " WHERE operation_id = %s", (effect_id,))
        assert receipts, (
            "effect id %r names an operation that settled with no receipt"
            % (effect_id,))
        assert all(dict(r)["outcome"] in ("success", "failure") for r in
                   receipts), "effect id %r has an undecided receipt" % (
                       effect_id,)


def test_the_old_synthesized_constant_is_no_longer_any_effect_identity(store):
    """The defect's own value must be gone from every admitted row.

    The reviewer printed `ad01-ad01-w0-I-771-b0-effect` for seq 0 and found it
    absent from `operations`. A repair that kept the constant on any admitted
    row would leave the reviewer's measurement reproducible, so the constant is
    asserted against the table rather than against a helper's return value.
    """
    run = _admitted(store, 482)
    cid, effects = run["cid"], run["effects"]

    synthesized = "ad01-%s-b%d-effect"
    for row in effects:
        expected_old = synthesized % (cid, row["seq"])
        assert row["effect_id"] != expected_old, (
            "seq %d still carries the synthesized constant %r"
            % (row["seq"], row["effect_id"]))
    in_operations = _query(
        store, "SELECT id FROM operations WHERE id = %s",
        (synthesized % (cid, 0),))
    assert not in_operations, (
        "an operations row now exists under the synthesized name; the"
        " identity would be joined only because the id was minted to match")


# --- 2. both directions of the arrow -------------------------------------


def test_an_observation_reaches_its_operation_in_both_directions(store):
    """Requirement 2. Both directions of "admitted effect -> observation".

    Forward: from the boundary's effect row to the `operations` row it names,
    and on to the `attempt_observations` row that carries that boundary's
    observation under the same id.

    Backward: from a durable `attempt_observations` row to the effect id it
    carries, and on to that `operations` row. The backward direction is what
    the reviewer measured as absent, and it is the one a reader needs to ask
    "which operation produced this observation".
    """
    run = _admitted(store, 483)
    cid, effects, observations = run["cid"], run["effects"], run["observations"]
    by_seq = {row["seq"]: row for row in effects}

    forward = 0
    for seq, content in sorted(observations.items()):
        effect = by_seq[seq]
        effect_id = content.get("operation_id")
        if not effect_id:
            continue
        assert effect_id == effect["effect_id"], (
            "the boundary observation for seq %d carries operation_id %r and"
            " the effect row carries %r; the two sides of the arrow disagree"
            % (seq, effect_id, effect["effect_id"]))
        named = _query(store, "SELECT id, settled FROM operations WHERE id = %s",
                       (effect_id,))
        assert named, (
            "the boundary observation for seq %d names %r, which is not an"
            " operations row" % (seq, effect_id))
        assert content.get("observation_id"), (
            "seq %d's boundary observation carries no observation_id" % (seq,))
        forward += 1

    assert forward >= 2, (
        "only %d of %d boundary observations reached an operation; the"
        " forward arrow is unbound for the rest"
        % (forward, len(observations)))

    # Backward: start from the observation rows themselves.
    reached = 0
    for row in _query(
            store,
            "SELECT o.id, o.content FROM attempt_observations o"
            " JOIN attempts a ON a.id = o.attempt_id"
            " WHERE a.investigation_id = %s"
            " AND o.content ? 'operation_id'", (cid,)):
        content = dict(row["content"])
        effect_id = content.get("operation_id")
        if not effect_id:
            continue
        assert by_effect(by_seq, effect_id) is not None, (
            "observation row %d names %r, which is not an admitted effect of"
            " this campaign" % (row["id"], effect_id))
        named = _query(store, "SELECT id FROM operations WHERE id = %s",
                       (effect_id,))
        assert named, (
            "observation row %d names %r and that names no operations row"
            % (row["id"], effect_id))
        reached += 1
    assert reached == forward, (
        "%d observations carry an effect id and %d were reached from a"
        " boundary; the two directions disagree" % (forward, reached))


def by_effect(by_seq, effect_id):
    for row in by_seq.values():
        if row["effect_id"] == effect_id:
            return row
    return None


# --- 3. derived, not fabricated ------------------------------------------


def test_a_fabricated_effect_id_is_refused_by_the_derivation(store):
    """Requirement 3. The effect row is derived from the admitted operation.

    A fabricated id is planted in each place the episode could carry one, and
    the production derivation is entered. It must return nothing rather than
    echo the planted value, and the fabricated string must never reach the
    table. This is the one failure that would make things worse, so it is
    asserted directly rather than argued.
    """
    from experiments.ad01 import trajectory

    run = _admitted(store, 484)
    cid = run["cid"]
    fabricated = "ad01-%s-b0-operation-that-was-never-admitted" % cid

    planted = [
        {"kind": "use_method", "operation_id": fabricated},
        {"kind": "development", "disposition": "retained",
         "executable": {"construction": {"init_operation": fabricated}}},
        {"kind": "diagnostic", "disposition": "inspected",
         "operation_id": fabricated},
    ]
    for episode in planted:
        derived = trajectory._effect_operation_id(store, cid, episode)
        assert derived == "", (
            "an episode carrying the fabricated id %r was admitted under"
            " effect identity %r; the derivation is echoing its input rather"
            " than reading an operation" % (fabricated, derived))

    stored = _query(
        store, "SELECT effect_id FROM s09_policy_state"
        " WHERE investigation_id = %s AND effect_id = %s", (cid, fabricated))
    assert stored == [], (
        "the fabricated id reached the effect table: %r" % (stored,))
    present = _query(store, "SELECT id FROM operations WHERE id = %s",
                     (fabricated,))
    assert present == [], (
        "the fabricated id names an operations row; it was minted, not"
        " admitted")


def test_no_database_means_no_identity(store):
    """An identity that cannot be verified is not an identity.

    The derivation's authority is the `operations` table, so with no store it
    has nothing to check against and produces nothing. This is the same
    property as the fabrication test, seen from the boundary rather than from
    a planted id: an unverifiable claim yields no claim.
    """
    from experiments.ad01 import trajectory

    assert trajectory._effect_operation_id(
        None, "ad01-w0-I-901", {"operation_id": "some-operation"}) == ""
    assert trajectory._effect_operation_id(store, "ad01-w0-I-901", {}) == ""


def test_a_real_operation_id_in_the_episode_is_taken_verbatim(store):
    """The other half of requirement 3. Derivation is not a refusal policy.

    A fabrication test passes just as well against a derivation that always
    returns nothing. So the same function is entered with the episode the
    production path really produced and must return that boundary's real
    operation id.
    """
    from experiments.ad01 import trajectory

    run = _admitted(store, 485)
    out, effects = run["out"], run["effects"]
    admitted = [row["effect_id"] for row in effects if row["effect_id"]]
    assert admitted, "the campaign admitted no effect identity to check"

    by_seq = {row["seq"]: row for row in effects}
    matched = 0
    for seq, row in sorted(by_seq.items()):
        if not row["effect_id"]:
            continue
        episode = out["episodes"][seq]
        derived = trajectory._effect_operation_id(store, run["cid"], episode)
        assert derived == row["effect_id"], (
            "seq %d's episode derives %r and the row carries %r"
            % (seq, derived, row["effect_id"]))
        matched += 1
    assert matched == len(admitted)


def test_a_boundary_that_admitted_no_operation_claims_no_effect(store):
    """Outcome (b), with a witness. A boundary that ran no operation.

    Entered with no policy consumer and the seed constructor, so the boundary
    runs a host-side diagnostic that never reaches the broker. Measured on the
    same table as requirement 1, the store holds no `operations` row at all,
    so there is nothing for the effect row to name. The honest outcome is that
    the effect is NOT admitted: the row says so by carrying no identity, and
    the row is not left claiming one.
    """
    from experiments.ad01 import trajectory

    cid = trajectory.campaign_id(0, "I", 486)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    out = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=2),
        tasks=["ad01-w0-dev-sw-00"], campaign_seq=486, dsn=store,
        constructor="seed")
    assert [b["seq"] for b in out["boundaries"]] == [0]

    operations = _query(
        store, "SELECT id FROM operations WHERE allocation_id = %s"
        " OR id LIKE %s", (trajectory._alloc_id(cid), "ad01-%s%%" % cid))
    assert operations == [], (
        "this witness is only a witness while the boundary admits no"
        " operation; it found %r" % (operations,))

    rows = _effect_rows(store, cid)
    assert len(rows) == 1
    assert rows[0]["effect_id"] == "", (
        "a boundary that admitted no operation claims effect identity %r"
        % (rows[0]["effect_id"],))
    assert rows[0]["status"] == "incorporated"
    assert not _query(store, "SELECT id FROM operations WHERE id = %s",
                      (rows[0]["effect_id"],))

    observation = _boundary_observations(store, cid)[0]
    assert observation.get("operation_id") == "", (
        "the boundary observation claims operation %r where none was"
        " admitted" % (observation.get("operation_id"),))


# --- 4. the third arrow, identity-joined ---------------------------------


def test_the_third_arrow_is_identity_joined_end_to_end(store):
    """Requirement 4. permitted experience -> decision -> effect -> observation.

    Each hop is joined on an identity rather than on `(investigation_id, seq)`.
    The permitted experience is named by its own operation id, the decision by
    the durable row that carries it, the effect by the operation it was
    derived from, and the observation by the effect id it carries.
    """
    run = _admitted(store, 487)
    cid, out, effects = run["cid"], run["out"], run["effects"]

    # Hop 1: permitted experience, named by its own settled operation.
    permitted = "ad01-%s-policy-s0-k0" % cid
    hop1 = _query(store, "SELECT id, settled FROM operations WHERE id = %s",
                  (permitted,))
    assert hop1 and hop1[0]["settled"] is True

    # Hop 2: the decision, on its durable row, naming the action that ran.
    # The decision row and the policy output name the same boundary in two
    # vocabularies: `accepted_action` carries the admitted action in the
    # driver's own spelling, `policy_output` carries the STEP result the
    # policy program returned. Both are asserted, because a hop joined only
    # through one of them has not proved the decision and the program agree.
    hop2 = _query(
        store,
        "SELECT seq, accepted_action, policy_output FROM s09_policy_state"
        " WHERE investigation_id = %s ORDER BY seq", (cid,))
    assert len(hop2) >= 3
    kinds = []
    for row in hop2:
        for result in dict(row["policy_output"] or {}).get("results", []):
            kinds.append(result["action"]["kind"])
    assert kinds[:3] == ["diagnose", "construct_method", "use_method"]
    admitted_kinds = [dict(dict(row["accepted_action"] or {}).get(
        "next_action") or {}).get("kind") for row in hop2]
    assert admitted_kinds[:3] == ["diagnostic", "development", "use_method"], (
        "the admitted action kinds changed shape: %r" % (admitted_kinds,))
    action = dict(dict(hop2[1]["accepted_action"] or {}).get(
        "next_action") or {})
    assert action.get("kind") == "development"

    # Hop 3: the effect, derived from the operation that admitted it.
    hop3 = {row["seq"]: row for row in effects}
    joined = [seq for seq, row in hop3.items() if row["effect_id"]]
    assert joined, "no boundary admitted an effect identity to join on"
    for seq in joined:
        named = _query(store, "SELECT id FROM operations WHERE id = %s",
                       (hop3[seq]["effect_id"],))
        assert named, (
            "hop 3 for seq %d names %r, which is not an operations id"
            % (seq, hop3[seq]["effect_id"]))

    # Hop 4: the observation, carrying the same effect id it was produced by.
    observations = run["observations"]
    for seq in joined:
        content = observations[seq]
        assert content["operation_id"] == hop3[seq]["effect_id"], (
            "hop 4 for seq %d carries %r and hop 3 carries %r"
            % (seq, content["operation_id"], hop3[seq]["effect_id"]))
        assert content["observation_id"], (
            "hop 4 for seq %d carries no observation_id" % (seq,))

    # The join is an identity, not a sequence number: the same operation id
    # reaches the effect row and the observation row from either direction.
    for seq in joined:
        effect_id = hop3[seq]["effect_id"]
        from_effect = _query(
            store, "SELECT seq FROM s09_policy_state"
            " WHERE investigation_id = %s AND effect_id = %s", (cid, effect_id))
        from_observation = _query(
            store,
            "SELECT o.content->>'seq' AS seq FROM attempt_observations o"
            " JOIN attempts a ON a.id = o.attempt_id"
            " WHERE a.investigation_id = %s"
            " AND o.content->>'operation_id' = %s", (cid, effect_id))
        assert from_effect and from_observation, (
            "effect %r is reachable from one side of the arrow only"
            % (effect_id,))
        assert str(from_effect[0]["seq"]) == str(
            from_observation[0]["seq"]), (
            "effect %r joins the effect row at seq %r and the observation row"
            " at seq %r" % (effect_id, from_effect[0]["seq"],
                            from_observation[0]["seq"]))


def test_a_second_campaign_agrees_with_the_first(store):
    """The identity is not an artefact of one campaign's ids.

    A second campaign on the same store, with a different campaign sequence,
    must reach the same verdicts. A derivation that joined only because one
    campaign's ids happened to line up would pass the first test and this one.
    """
    first = _admitted(store, 488)
    second = _admitted(store, 489)

    assert first["cid"] != second["cid"]
    for run in (first, second):
        admitted = [row["effect_id"] for row in run["effects"] if row["effect_id"]]
        assert len(admitted) >= 2
        for effect_id in admitted:
            named = _query(
                store, "SELECT id, settled FROM operations WHERE id = %s",
                (effect_id,))
            assert named and named[0]["settled"] is True, (
                "effect id %r names no settled operation in campaign %s"
                % (effect_id, run["cid"]))
    assert set(row["effect_id"] for row in first["effects"] if row["effect_id"]) \
        .isdisjoint(
            set(row["effect_id"] for row in second["effects"]
                if row["effect_id"])), (
        "two campaigns share an effect identity, so the identity is not"
        " per-campaign")