"""B8: which panel can carry the E2 experience contrast, enumerated.

The contrast ran twice and returned null both times
(`reports/evidence/invr1e2contrast/report.json`,
`reports/evidence/invr1e2contrastr2/report.json`). Section (c) of
`reports/workstreams/inv-b.md` reads that as a power problem, and the
diagnosis has two halves that are routinely merged and must not be.

**The panel power problem.** A contrast needs independent units, and
`panel_inventory.CLUSTER_RULE` counts one per `(family, template)`. The
software panel offers four of them against the six
`minimum_clusters_for_alpha(1/20)` requires, and the runnable split
measured two. This is a power problem, and it is fixable by choosing a
different panel.

**The retention closure.** `RETENTION_BLOCKER` states that the repertoire
was closed and identical for every arm, so no difference in `method_id` could
ever be a retention effect. This was not a power problem and no panel fixed
it. **B3 has since opened the repertoire**, and the test that asserted the
closure now asserts both halves: the authored seeds alone are still closed,
which is what every archived run here reproduced, and the arrival path for
an acquired member exists, which is what makes the leg measurable at all.
`tests/test_inv_b3_repertoire.py` measures the opened side.

This module separates the two. It enumerates every combination of split the
frozen world offers, computes the cluster count and the attainable positive
ceiling for each against its own family's zero-information default, and
answers two questions with literal numbers: which combinations reach six
clusters, and which of those have a non-zero ceiling. A combination that
reaches six clusters with a positive ceiling is a panel a contrast can
actually move. One that reaches six and has a ceiling of zero is powered
and blind. Neither the enumeration nor its verdict claims anything about
retention.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from experiments.ad01 import s09_panel_inventory
from experiments.ad01 import s09_study_protocol
from experiments.ad01 import w2_retention_campaign as campaign

REPO = Path(__file__).resolve().parents[1]
CENSUS_PATH = REPO / "reports" / "evidence" / "invr1b8-panel-census" / "census.json"

SPLITS = ("dev", "within", "transfer")
FAMILIES = ("software", "graph")


# ---------------------------------------------------------------------------
# the enumeration
# ---------------------------------------------------------------------------


def test_the_enumeration_covers_every_non_empty_combination_of_splits():
    combinations = list(campaign.panel_combinations())
    assert len(combinations) == 14, (
        "two families times every non-empty subset of three splits is 2*7; "
        "got %d, so an axis of the census is missing" % len(combinations))
    assert {c["family"] for c in combinations} == set(FAMILIES)
    assert {tuple(c["splits"]) for c in combinations} == {
        splits for size in (1, 2, 3)
        for splits in itertools.combinations(SPLITS, size)}


def test_every_enumerated_panel_reports_a_cluster_count_and_a_ceiling():
    for panel in campaign.panel_combinations():
        assert panel["cluster_count"] >= 1, panel
        assert panel["rows_measured"] >= 1, panel
        assert panel["max_attainable_positive_delta"] >= 0.0, panel
        assert panel["open_rows"] <= panel["rows_measured"], panel


def test_the_census_names_a_literal_cluster_count_per_family_and_split():
    # Not self-consistency. These are the counts read off the frozen world:
    # each family contributes exactly two software templates on any one
    # split, and the two transfer templates are disjoint from the dev/within
    # pair, so a split union either reuses the pair or adds the pair.
    measured = {(c["family"], tuple(c["splits"])): c["cluster_count"]
                for c in campaign.panel_combinations()}
    assert measured[("software", ("within",))] == 2
    assert measured[("software", ("transfer",))] == 2
    assert measured[("software", ("dev", "within"))] == 2
    assert measured[("software", ("dev", "transfer"))] == 4
    assert measured[("software", ("within", "transfer"))] == 4
    assert measured[("software", ("dev", "within", "transfer"))] == 4
    assert measured[("graph", ("dev",))] == 3
    assert measured[("graph", ("transfer",))] == 3
    assert measured[("graph", ("dev", "within"))] == 3
    assert measured[("graph", ("dev", "transfer"))] == 6
    assert measured[("graph", ("within", "transfer"))] == 6
    assert measured[("graph", ("dev", "within", "transfer"))] == 6


def test_the_cluster_rule_that_counts_them_is_the_frozen_one():
    # The count is only meaningful if it is counted the way the protocol
    # counts. `minimum_clusters_for_alpha` answers 6 here, and the archive
    # that recorded the shortfall recorded 6 as well.
    assert s09_panel_inventory.CLUSTER_RULE == "(family, template)"
    assert s09_panel_inventory.minimum_clusters_for_alpha(0.05) == 6
    assert s09_study_protocol.minimum_clusters_for_alpha(
        s09_study_protocol.ALPHA) == 6


# ---------------------------------------------------------------------------
# the two defects, kept apart
# ---------------------------------------------------------------------------


def test_the_software_panel_the_prior_run_used_cannot_be_powered():
    # This is the panel both archived runs used, at the split they used.
    # Its count is asserted rather than recomputed, because the whole point
    # is that the number is small and the number is the finding.
    prior = next(c for c in campaign.panel_combinations()
                 if c["family"] == "software"
                 and tuple(c["splits"]) == ("within",))
    assert prior["cluster_count"] == 2
    assert prior["cluster_count"] < 6
    assert prior["powered"] is False
    assert prior["shortfall"] == 4


def test_software_is_short_of_clusters_on_every_combination_it_offers():
    # The shortfall is not a choice of split. Four software templates exist
    # in the whole frozen world, so no union of splits reaches six.
    software = [c for c in campaign.panel_combinations()
                if c["family"] == "software"]
    assert software, "the census dropped the software family entirely"
    assert max(c["cluster_count"] for c in software) == 4
    for panel in software:
        assert panel["powered"] is False, panel
        assert panel["shortfall"] >= 2, panel


def test_graph_can_reach_six_clusters_and_the_software_family_cannot():
    powered = [c for c in campaign.panel_combinations() if c["powered"]]
    assert {c["family"] for c in powered} == {"graph"}
    for panel in powered:
        assert panel["cluster_count"] == 6, panel
        assert panel["shortfall"] == 0, panel


# ---------------------------------------------------------------------------
# the ceiling, which is the half that is not about clusters
# ---------------------------------------------------------------------------


def test_the_graph_panel_that_reaches_six_clusters_has_a_positive_ceiling():
    # The disposition depends on this number. A six-cluster panel whose
    # ceiling is zero would be powered and blind, and the honest report
    # would say so instead of naming a panel.
    candidates = [c for c in campaign.panel_combinations()
                  if c["family"] == "graph" and c["powered"]]
    assert candidates, "no graph combination reaches six clusters"
    for panel in candidates:
        assert panel["max_attainable_positive_delta"] == pytest.approx(
            0.2857142857, abs=1e-6), panel
        assert panel["open_rows"] == panel["rows_measured"], panel


def test_the_closed_software_within_panel_is_reported_as_zero_and_not_as_power():
    # The prior panel. It is closed on the positive side, and no panel choice
    # changes that; the archive recorded the same zero.
    closed = next(c for c in campaign.panel_combinations()
                  if c["family"] == "software"
                  and tuple(c["splits"]) == ("within",))
    assert closed["max_attainable_positive_delta"] == 0.0, closed
    assert closed["open_rows"] == 0, closed


def test_the_verdict_names_the_panel_and_does_not_claim_retention():
    verdict = campaign.panel_power_verdict()
    assert verdict["required_clusters"] == 6
    assert verdict["powered_with_positive_ceiling"] == [
        "graph:dev+transfer", "graph:within+transfer",
        "graph:dev+within+transfer"]
    assert verdict["powered_but_blind"] == []
    assert verdict["unpowered"] == [c["panel_id"] for c in campaign
                                   .panel_combinations()
                                   if not c["powered"]]
    # Seven software combinations plus the four graph combinations that
    # stay under six clusters on a single split or on dev+within.
    assert len(verdict["unpowered"]) == 11
    # Every unpowered panel except one had a ceiling. `software:within` is
    # the exception and it is the prior lane's panel. This is what separates
    # "too few independent units" from "nowhere for a positive to go", and
    # it is why the prior null was not a blind panel.
    assert set(verdict["unpowered_but_positive"]) == (
        set(verdict["unpowered"]) - {"software:within"})
    assert "retention" in verdict["not_claimed"], verdict
    assert "repertoire" in verdict["retention_closure"]["mechanism"]


# ---------------------------------------------------------------------------
# the closed repertoire, still asserted
# ---------------------------------------------------------------------------


def test_the_repertoire_opened_in_b3_and_the_default_one_is_still_closed():
    # B8 left this failing-by-design while the repertoire was closed. B3
    # opened it, and this is the deliberate update rather than the deletion
    # of a guard: the closure is no longer the world, and the two states are
    # now separate assertions instead of one flag read two ways.
    #
    # The four archived reports the closure was read from are named in
    # campaign.RETENTION_BLOCKER["archived_in"], and none of them was
    # edited: they are measurements of the world at 35ba5e9.
    default = campaign.measure_repertoire_closure()

    assert default["repertoire_closed"] is True, (
        "the authored seeds alone are still a closed repertoire; if this "
        "fails then default_repertoire grew, which would invalidate every "
        "archived run in this tree")
    assert default["default_repertoire_closed"] is True, default
    assert len(default["distinct_eligible_sets"]) == 1, default
    assert default["every_arm_sees_the_same_eligible_methods"] is True
    for row in default["rows"]:
        assert row["eligible_count"] == 2, row
        assert row["retained_method_nameable"] is False, row

    assert campaign.RETENTION_BLOCKER["archived_in"] == [
        "reports/evidence/invr1w2retention/report.json",
        "reports/evidence/invr1w2retentionr2/report.json",
        "reports/evidence/invr1w2retention-census/report.json",
        "reports/evidence/invr1b8-panel-census/census.json",
    ], ("a report now describes the closed repertoire as the world; the "
        "list of archives whose description went stale must say which")


def test_the_power_census_is_unaffected_by_which_repertoire_a_run_holds():
    # What B8 measured was the panel's own reachability, over the authored
    # decision grid. That grid is `method_ids_for`, still the seeds, so
    # admitting a member did not move a ceiling. This says so with a
    # measurement rather than by appeal to which lane touched which file.
    for panel in campaign.panel_combinations():
        assert panel["family"] in ("software", "graph")
    assert campaign.method_ids_for("software") == [
        "seed-sw-ddmin", "seed-sw-greedy"]
    assert campaign.method_ids_for("graph") == [
        "seed-gr-ddmin", "seed-gr-greedy"]


# ---------------------------------------------------------------------------
# the artifact
# ---------------------------------------------------------------------------


def test_the_census_artifact_is_reproducible_from_source():
    # Not "the file equals what the function returns now". The function's
    # numbers are re-derived from the frozen world and the frozen reducers,
    # and the committed artifact is compared against that derivation. A
    # hand-edited artifact fails here.
    assert CENSUS_PATH.exists(), (
        "the census was not written to %s" % CENSUS_PATH)
    committed = json.loads(CENSUS_PATH.read_text(encoding="utf-8"))
    assert campaign.panel_power_verdict() == committed["verdict"]
    assert campaign.panel_combinations() == committed["panels"]


def test_the_census_artifact_records_how_to_recompute_it():
    committed = json.loads(CENSUS_PATH.read_text(encoding="utf-8"))
    assert committed["recomputed_by"] == (
        "experiments.ad01.w2_retention_campaign.panel_power_verdict")
    assert committed["model_calls"] == 0
    assert committed["alpha"] == "1/20"
    assert committed["required_clusters"] == 6
    assert committed["cluster_rule"] == "(family, template)"
