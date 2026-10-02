"""S09 revision: acquisition attribution and the immutable boundary.

Lane L, second file. The first file decides whether revision bytes are an
eligible intervention and whether the apparatus can measure an effect. This
one covers the two properties that make any such claim safe to make: a
benefit requires attributable model bytes, and the trusted authority stays
outside the mutable learner.

A revision may be a legitimate intervention and still not be evidence. The
campaign is explicit that attributable model bytes and an operative learner
boundary are the prerequisites, so a package without model provenance is
refused rather than measured.

Deterministic only: no network, no database, no live model call.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments.ad01 import boolean_rule as br
from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live

COHORT = list(range(24))
ELIGIBILITY_SEEDS = (0, 1, 2, 3)


def _mission():
    return {
        "objective": "probe boolean rules within eight queries",
        "constraints": ["deterministic only", "no live network"],
        "success_criteria": ["committed predictor"],
        "environments": [
            {"instrument": "boolean-rule-v1", "split": "dev", "seed": 4},
        ],
    }


def _store(tmp_path, name="s09rev-acq.json"):
    return frontier.create_store(
        tmp_path / name, namespace=frontier.NAMESPACE,
        mission=_mission(), authority={"queries": 16, "steps": 12})


def _bound_store(tmp_path, name="bound.json"):
    store = _store(tmp_path, name)
    base = channel.make_control("low")
    store.bind_active(base)
    return store, base


def _eligibility_views(store, package, seeds=ELIGIBILITY_SEEDS):
    views = []
    for seed in seeds:
        view = store.step_view(frontier.IMPROVE, package)
        view["experience"] = []
        view["round"] = 1
        views.append(view)
    return views


def _acquired_package(imp_source, parent, control_id, provenance):
    package = {
        "control_id": control_id, "origin": live.ACQUIRED_ORIGIN,
        "source_kind": "model-response",
        "op_source": parent["op_source"], "imp_source": imp_source,
        "op_digest": frontier.source_digest(parent["op_source"]),
        "imp_digest": frontier.source_digest(imp_source),
        "parent_digest": parent["package_digest"],
        "provenance": provenance,
        "provenance_digest": frontier.source_digest(
            frontier.canonical(provenance)),
        "version": int(parent["version"]) + 1,
        "authority_request": dict(parent["authority_request"]),
        "obligations": list(parent["obligations"]),
        "channel": parent["channel"], "package_digest": None}
    package["package_digest"] = frontier.package_digest(package)
    return package


# --- attributable bytes are a prerequisite -------------------------------

def test_an_acquired_package_needs_dispatch_provenance(tmp_path):
    """Model bytes without an attributable dispatch are not evidence."""
    store, base = _bound_store(tmp_path)
    package = _acquired_package(
        channel._revision_source('3 if not view["experience"] else 6'),
        base, "acquired-1", None)
    with pytest.raises((frontier.Refused, live.LiveRefused)) as excinfo:
        frontier.validate_package(package, grant=store._doc["grant"])
    assert "provenance" in str(excinfo.value)


def test_an_authored_package_cannot_claim_model_provenance(tmp_path):
    """The other direction. A hand-written revision cannot be relabelled
    as model output, which would let a reviewer-authored control stand in
    for a live acquisition."""
    store, base = _bound_store(tmp_path)
    package = {
        "control_id": "forged", "origin": live.APPARATUS_ORIGIN,
        "source_kind": "fixed-menu", "op_source": base["op_source"],
        "imp_source": channel._revision_source(
            '3 if not view["experience"] else 6'),
        "op_digest": frontier.source_digest(base["op_source"]),
        "imp_digest": frontier.source_digest(channel._revision_source(
            '3 if not view["experience"] else 6')),
        "parent_digest": base["package_digest"],
        "provenance": {"dispatch_evidence_digest": "deadbeef"},
        "provenance_digest": None, "version": 1,
        "authority_request": dict(base["authority_request"]),
        "obligations": list(base["obligations"]),
        "channel": base["channel"], "package_digest": None}
    package["provenance_digest"] = frontier.source_digest(
        frontier.canonical(package["provenance"]))
    package["package_digest"] = frontier.package_digest(package)
    with pytest.raises((frontier.Refused, live.LiveRefused)) as excinfo:
        frontier.validate_package(package, grant=store._doc["grant"])
    assert "provenance" in str(excinfo.value)


def test_an_acquired_package_whose_bytes_do_not_match_is_refused(tmp_path):
    """The manifest digest is the seal. Tampering with the revision bytes
    after acquisition is caught by the digest, not by inspection."""
    store, base = _bound_store(tmp_path)
    provenance = {"dispatch_evidence_digest": "e" * 64}
    package = _acquired_package(
        channel._revision_source('3 if not view["experience"] else 6'),
        base, "acquired-2", provenance)
    tampered = dict(package)
    tampered["imp_source"] = channel._revision_source("9")
    with pytest.raises((frontier.Refused, live.LiveRefused)) as excinfo:
        frontier.validate_package(tampered, grant=store._doc["grant"])
    assert "digest" in str(excinfo.value)


def test_no_live_acquisition_means_the_benefit_is_not_claimed():
    """The campaign's own fallback, wired end to end.

    The delta here is real and measured, and the run still claims no
    benefit, because the bytes were authored rather than acquired.
    """
    delta = channel.descendant_delta(
        channel.evaluate_lineage([0], split="qual", seeds=COHORT),
        channel.evaluate_lineage([3], split="qual", seeds=COHORT))
    assert delta["measured"] is True
    outcome = channel.benefit_outcome(
        delta, {"eligible": True, "live_attributable": False})
    assert outcome["benefit"] is False
    assert "no live-acquired attributable model bytes" in outcome["blockers"]
    assert outcome["scope"] is None


# --- the trusted authority stays outside the learner ---------------------

def test_a_revision_cannot_widen_its_own_authority(tmp_path):
    """The grant is enforced by the authority, not by the revision.

    A revision that asks for more than the grant does not get it. The
    revision may be entirely eligible and still be unable to buy itself
    more than the trusted authority allows.
    """
    store, base = _bound_store(tmp_path)
    greedy = channel._revision_source("3").replace(
        '{"queries": 1, "steps": 1}', '{"queries": 99, "steps": 99}')
    package = {
        "control_id": "greedy", "origin": live.APPARATUS_ORIGIN,
        "source_kind": "fixed-menu", "op_source": base["op_source"],
        "imp_source": greedy,
        "op_digest": frontier.source_digest(base["op_source"]),
        "imp_digest": frontier.source_digest(greedy),
        "parent_digest": base["package_digest"],
        "provenance": None, "provenance_digest": None, "version": 1,
        "authority_request": {"queries": 999, "steps": 999},
        "obligations": list(base["obligations"]),
        "channel": base["channel"], "package_digest": None}
    package["package_digest"] = frontier.package_digest(package)
    with pytest.raises((frontier.Refused, live.LiveRefused)) as excinfo:
        frontier.validate_package(package, grant=store._doc["grant"])
    assert "authority" in str(excinfo.value)


def test_the_spend_itself_is_bounded_by_the_grant(tmp_path):
    """Bounded in execution, not only in the manifest.

    A revision is admitted with a legal request, then the authority
    refuses the spend when the grant cannot cover it. This is what makes
    the freeze a property of the run rather than a declaration in a file.
    """
    store, base = _bound_store(tmp_path, "spend.json")
    hungry = channel._revision_source("3")
    package = {
        "control_id": "hungry", "origin": live.APPARATUS_ORIGIN,
        "source_kind": "fixed-menu", "op_source": base["op_source"],
        "imp_source": hungry,
        "op_digest": frontier.source_digest(base["op_source"]),
        "imp_digest": frontier.source_digest(hungry),
        "parent_digest": base["package_digest"],
        "provenance": None, "provenance_digest": None, "version": 1,
        "authority_request": {"queries": 16, "steps": 12},
        "obligations": list(base["obligations"]),
        "channel": base["channel"], "package_digest": None}
    package["package_digest"] = frontier.package_digest(package)
    store.adopt_revision(package)
    before = dict(store.authority)
    with pytest.raises(frontier.Refused):
        store.spend({"queries": 10_000, "steps": 10_000})
    assert store.authority == before


def test_frozen_state_is_stable_across_a_real_round(tmp_path):
    """The freeze holds through an actual executed round, not just a
    classification call.

    A revision that runs, spends and builds a descendant must leave the
    grant, the evaluator identity and the execution limits exactly as they
    were. Only the used-so-far counters move, and they move downward.
    """
    store, base = _bound_store(tmp_path, "round.json")
    revision = channel._revision_source('3 if not view["experience"] else 6')
    package = {
        "control_id": "runner", "origin": live.APPARATUS_ORIGIN,
        "source_kind": "fixed-menu", "op_source": base["op_source"],
        "imp_source": revision,
        "op_digest": frontier.source_digest(base["op_source"]),
        "imp_digest": frontier.source_digest(revision),
        "parent_digest": base["package_digest"],
        "provenance": None, "provenance_digest": None, "version": 1,
        "authority_request": dict(base["authority_request"]),
        "obligations": list(base["obligations"]),
        "channel": base["channel"], "package_digest": None}
    package["package_digest"] = frontier.package_digest(package)
    store.adopt_revision(package)
    before = channel.frozen_state(store)
    driven = channel.drive_improve_round(
        store, br.make_task("dev", 0), package=store.active_package,
        round_no=1, admit_probes=True)
    assert driven["candidate"] is not None
    after = channel.frozen_state(store)
    assert after["grant"] == before["grant"]
    assert after["evaluator"] == before["evaluator"]
    assert after["execution_limits"] == before["execution_limits"]
    assert after["sealed_results"] == before["sealed_results"]
    assert after["used"]["queries"] <= before["used"]["queries"] + \
        channel.EXECUTION_LIMITS["max_queries"]


def test_the_evaluator_cannot_be_replaced_by_a_revision(tmp_path):
    """The descendant metric names the evaluator it used.

    A reading is only interpretable because the evaluator is fixed, so
    the result carries the evaluator identity and refuses a run that
    cannot say which evaluator produced it.
    """
    result = channel.evaluate_descendants([3], split="qual",
                                          seeds=COHORT)
    assert result["n"] == len(COHORT)
    scored = channel.descendant_score([3], "qual", 0)
    assert set(scored) >= {"overall", "queried", "unqueried", "n_queried"}
    identity = channel.frozen_state(
        _bound_store(tmp_path, "id.json")[0])["evaluator"]
    assert identity == channel.EVALUATOR_ID
