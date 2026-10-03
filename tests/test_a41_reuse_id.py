"""A non-campaign id in `investigations` is admitted, and the lifecycle names it anyway.

Lane A40 named this while wiring admission into production: `scripts/invl02_live.py`
calls `ensure_campaign` with `invl02-live-reuse-...`, which is not the
`ad01-w0-I-NN-token` shape `_parse_campaign_id` accepts, so a row the boundary
parser refuses sits in `investigations`. A40 declined to fix it because the
path is not its own, and left the question open.

Measured here, the row is real and the predicted consequence is not.

The predicted mechanism was that `release_operation` derives its attempt id
from a campaign id, so a row admitted under a shape `_parse_campaign_id`
refuses could never be released, resumed, or read by the restorer. It does not
derive it. `release_operation(dsn, investigation_id, attempt_id)` takes both
ids as parameters, `_attempt_id` is `"att-%s-%d" % (cid, seq)`, and neither
`release_operation` nor `resume_operation` nor `held_operation` nor
`read_in_flight` parses anything. Every one of the 33 queries against the
`investigations` table keys on a bound parameter except one count-by-
disposition in `agenda.py`, which does not read ids at all.

What actually makes the row inert is the signature of the boundary, not the
shape of the id. `run_campaign` mints its own id with `campaign_id(world, arm,
campaign_seq)` and takes no cid, so no id of any shape can enter it.
`mission.admit_operation` is the only writer of `investigations.in_flight` and
is reachable only through `accept_action` from `admit_boundary` from
`_run_boundary`, all of which live inside `run_campaign`. `run_use` -- the arm
the reuse panel actually runs -- never calls it, and `method_exec.py`, which
runs the member, names no attempt or investigation at all.

So the reuse panels admit a commitment that holds nothing. That is a reuse
panel, not a half-built campaign: there is no admitted operation to restore,
which is why the row is never restored and never wanted.

Three panels do this, not one. `scripts/ad01_r3_compare.py` and
`scripts/ad01_r4_compare.py` mint `r3acq-t%d-%s` and `r4acq-t%d-%s` and call
the same `ensure_campaign` for the same acquisition purpose. Any guard at
`ensure_campaign` would refuse three live acquisition panels, which is the
"may break a working path" case stated plainly, and it would refuse them for
the reason that matters least: a study root is already supplied explicitly at
every one of the three call sites, so the id is a label and not the authority.

Both directions are pinned, because "the id is refused" alone would hold for
any shape including a campaign's. The parser is checked against the shapes it
accepts and the shape it refuses, and a row held under the reuse id is
released through the same call a campaign's is -- which passes if the shape
ever does start deciding the release, and fails if the predicted leak is real.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "a41cid"

CHARTER = {"objective": "reuse a retained member under its own identity",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20}
DEV_TASK = "ad01-w0-dev-sw-01"
PROGRAM_DIGEST = "21bc17cde3811fd4d3fa0289278f63c3afe0108f0ef4438915040219cf390093"

STUDY_ROOT = "invl02-live-e0"
REUSE_CID = "invl02-live-reuse-ad01w0devsw01"


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


def _decision(question: str) -> dict:
    return {"basis_references": [], "question": question,
            "next_action": {"kind": "diagnostic", "task_id": DEV_TASK,
                            "diagnostic": "software",
                            "capability_id": "seed-sw-greedy"}}


def test_a_reuse_id_is_admitted_and_the_parser_refuses_it(store):
    """The defect is real: the row exists, and the one parser refuses it.

    Admitted through `ensure_campaign` exactly as `restart_use` does, with the
    id built from the same expression the production minting uses, so this
    measures the production call and not a hand-built row.
    """
    from experiments.ad01 import mission, trajectory

    trajectory.set_namespace_token("")
    trajectory.authorize_campaign(store, REUSE_CID, authorized=100000,
                                  study_root=STUDY_ROOT)
    made = trajectory.ensure_campaign(
        store, REUSE_CID, 1, "I", dict(CHARTER), dict(CAPS),
        tasks=[DEV_TASK], study_root=STUDY_ROOT)
    assert made["admitted"] is True, "the reuse id admitted nothing"
    assert made["campaign_id"] == REUSE_CID

    with mission.connect(store) as conn:
        row = conn.execute(
            "SELECT id, in_flight FROM investigations WHERE id = %s",
            (REUSE_CID,)).fetchone()
        conn.commit()
    assert row is not None, (
        "no investigations row under the reuse id, so the defect under test "
        "is absent and this test measures nothing")

    assert mission.read_in_flight(store, REUSE_CID) == []
    assert mission.is_quiescent(store, REUSE_CID), (
        "the reuse entry reports held work. A reuse panel admits a commitment "
        "and holds nothing, so a non-empty in_flight means the use arm has "
        "started writing operations under an id the boundary cannot name -- "
        "which is the change that would make this defect real.")

    with pytest.raises(ValueError):
        trajectory._parse_campaign_id(REUSE_CID)


def test_the_parser_still_names_every_campaign_id_shape(store):
    """Non-vacuity: the refusal above is about the shape, not about the row.

    Both live campaign forms are accepted, and a campaign-shaped id is still
    admitted end to end. A parser that refused everything would satisfy the
    first test and fail this one, and the refusal would cost the resume path
    every id the system itself mints.
    """
    from experiments.ad01 import trajectory

    assert trajectory._parse_campaign_id("ad01-w0-I-51") == (0, "I", 51, "")
    assert trajectory._parse_campaign_id("ad01-w0-I-51-pe") == (0, "I", 51, "pe")

    namespaced = trajectory.campaign_id(0, "I", 51, "a41token")
    world, arm, seq, token = trajectory._parse_campaign_id(namespaced)
    assert (world, arm, seq) == (0, "I", 51)
    assert token == "a41token", (
        "the token did not survive the round trip, so a namespaced resume "
        "would rebuild a different id")

    trajectory.set_namespace_token("")
    campaign_cid = trajectory.campaign_id(0, "I", 52)
    trajectory.authorize_campaign(store, campaign_cid, authorized=100000,
                                  study_root=STUDY_ROOT)
    made = trajectory.ensure_campaign(
        store, campaign_cid, 0, "I", dict(CHARTER), dict(CAPS),
        tasks=[DEV_TASK], study_root=STUDY_ROOT)
    assert made["admitted"] is True, (
        "a campaign-shaped id stopped being admitted, so the reuse panel is "
        "the only shape this can admit and the boundary owns no id")

    assert trajectory._parse_campaign_id(campaign_cid) == (0, "I", 52, "")


def test_a_held_operation_under_a_reuse_id_releases_like_a_campaigns(store):
    """The predicted leak, measured in both directions.

    A row held under the reuse id is released by the same call that releases a
    campaign's, keyed on the attempt id the caller was handed. If the shape of
    the investigation id did decide the release -- which is what the brief
    predicted -- this could not happen and the entry would keep the operation
    forever.
    """
    from experiments.ad01 import mission, trajectory

    reuse_attempt = trajectory._attempt_id(REUSE_CID, 0)
    campaign_cid = trajectory.campaign_id(0, "I", 53)
    campaign_attempt = trajectory._attempt_id(campaign_cid, 0)

    assert reuse_attempt == "att-%s-0" % REUSE_CID
    assert reuse_attempt != campaign_attempt, (
        "the reuse and campaign ids produced one attempt id, so this test is "
        "measuring a single row under two names")

    for cid, attempt in ((REUSE_CID, reuse_attempt),
                         (campaign_cid, campaign_attempt)):
        held = mission.admit_operation(
            store, cid, seq=0, attempt_id=attempt, decision=_decision(cid),
            program_digest=PROGRAM_DIGEST, task_id=DEV_TASK,
            capability_id="seed-sw-greedy")
        assert held.attempt_id == attempt
        assert mission.is_quiescent(store, cid) is False, (
            "%s recorded nothing, so the release below would pass having "
            "removed nothing" % cid)

        mission.release_operation(store, cid, attempt)
        assert mission.read_in_flight(store, cid) == [], (
            "%s could not be released. The lifecycle keys on the attempt id "
            "it is handed, so this would mean the shape of the investigation "
            "id decides the release after all." % cid)

    assert mission.resume_operation(store, REUSE_CID) == [], (
        "the resume restored something from an entry that holds nothing")


def test_the_boundary_mints_its_own_id_so_no_shape_can_enter_it():
    """Why the row is inert: the decision boundary never accepts an id.

    `run_campaign` builds its id from three scalars and takes no `cid`, so the
    only route to `admit_operation` can never carry a foreign shape. Asserted
    on the signature because that is what makes the claim: a change letting a
    caller pass a cid in would make the reuse id reachable, and this is what
    would notice.
    """
    import inspect

    from experiments.ad01 import trajectory

    params = list(inspect.signature(trajectory.run_campaign).parameters)
    assert "cid" not in params, (
        "run_campaign now accepts a campaign id, so a non-campaign shape can "
        "enter the boundary and this file's central claim is void: %s"
        % (params,))

    boundary_cid = trajectory.campaign_id(1, "I", 0)
    assert boundary_cid != REUSE_CID
    assert trajectory._parse_campaign_id(boundary_cid) == (1, "I", 0, "")

    assert trajectory._attempt_id(REUSE_CID, 0) != trajectory._attempt_id(
        boundary_cid, 0), (
        "the two ids produced one attempt id, so they are the same row")
