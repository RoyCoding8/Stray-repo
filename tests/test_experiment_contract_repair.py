"""Regression checks for experimental-unit reporting contracts."""

import hashlib
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from experiments.ad01 import s09_panel_inventory as panel
from experiments.ad01 import s09_swe_experiment as swe
from experiments.ad01 import twodomain


WORLD_ROOT = Path(__file__).parents[1] / "experiments" / "ad01" / "worlds"


def test_panel_reports_resolution_separately_from_family_coverage():
    inventory = panel.build_inventory(WORLD_ROOT)
    decision = inventory.decision()

    assert decision["minimum_p_resolution"]["all"] == {
        "cluster_count": 10,
        "minimum_p": 0.001953125,
        "required_clusters": 6,
        "meets_alpha_resolution": True,
    }
    assert decision["available_family_coverage"] == {
        "software": {
            "template_count": 4,
            "templates": [
                "stale-clear-core", "stale-clear-del-core",
                "stale-read-2chain", "stale-read-3chain",
            ],
        },
        "graph": {
            "template_count": 6,
            "templates": [
                "C5+joined-by-path", "C5+shared-edge", "C5+shared-vertex",
                "C5+tree", "C7+tree", "C9+tree",
            ],
        },
    }


def test_crossing_does_not_call_union_resolution_assessment_power():
    census = twodomain.cluster_census()
    software = census[twodomain.SWE]

    assert software["minimum_p_resolution"]["meets_alpha_resolution"] is True
    assert software["available_family_coverage"] == {
        "dev": 3, "held_out": 6}
    assert software["actual_assessment_counts"] == {
        "episodes": 3, "by_split": {"dev": 2, "held_out": 1}}
    assert software["assessment_family_coverage"]["dev"][
        "assessed_families"] == 1
    assert software["assessment_family_coverage"]["held_out"][
        "assessed_families"] == 1
    assert software["assessment_family_coverage"]["dev"][
        "meets_required_resolution"] is False
    assert software["assessment_family_coverage"]["held_out"][
        "meets_required_resolution"] is False
    assert census["crossing_coverage_sufficient"] is False
    assert "powered" not in software


def test_active_program_source_digest_is_driver_source():
    crossing = {"boolean-rule-v1": {"episodes": []},
                "software-fault-repair-v1": {"episodes": []}}
    program = twodomain._active_program(crossing)

    expected_source = hashlib.sha256(
        Path(twodomain.__file__).read_bytes()).hexdigest()
    assert program["source_digest"] == expected_source
    assert program["transcript_digest"] == twodomain._digest(crossing)
    assert program["source_digest"] != program["transcript_digest"]


def test_lineage_summary_separates_attempt_slots_from_record_diversity():
    lineage = swe.LINEAGES[0]
    result = swe.MatrixResult(
        scheduled_lineages=[{
            "identity": "%s:%s" % (lineage.representation_kind,
                                     lineage.name),
            "record_digest": lineage.digest,
        }])
    summary = swe.lineage_summary(result)

    assert summary["scheduled"]["attempt_count"] == 1
    assert summary["observed"]["attempt_count"] == 0
    assert "statistical independence" in summary["model_construction"]


def test_payload_lineage_summary_uses_executed_subset():
    lineage = replace(swe.LINEAGES[0], built_ok=False,
                      build_error="contract-test refusal")
    result = swe.run_matrix(splits=("dev",), lineages=[lineage])
    with patch.object(swe, "probe_reach", return_value={}), \
            patch.object(swe, "search_span", return_value={}):
        payload = swe.result_payload(result)
        empty = swe.result_payload(swe.MatrixResult())

    summary = payload["lineage_summary"]
    assert summary["scheduled"]["attempt_count"] == 1
    assert summary["observed"]["attempt_count"] == 1
    assert empty["lineage_summary"]["scheduled"]["attempt_count"] == 0
    assert empty["lineage_summary"]["observed"]["attempt_count"] == 0
