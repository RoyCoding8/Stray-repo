"""RPR-ACQ/2 held-out evaluation freeze and full decision rule (CBR-02/03)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation import splits
from experiments.representation.acquire import contexts, panel
from experiments.representation.acquire import run as panel_run
from experiments.representation.experiment import checker, freeze

EXPERIMENT = ROOT / "experiments" / "representation" / "experiment"
FIXTURES = ROOT / "experiments" / "representation" / "fixtures"
SW_EVA = ["sw-eva-%02d" % i for i in range(8)]
GR_EVA = ["gr-eva-%02d" % i for i in range(8)]


def _manifest():
    return json.loads((EXPERIMENT / "manifest.json").read_bytes())


def _sha():
    return (EXPERIMENT / "manifest.sha256").read_text().strip()


def _costs(**over):
    base = {"invocations_used": 1, "queries_used": 4, "validation_used": 1,
            "elapsed_s": 0.5, "model_calls": 0,
            "model_tokens": {"in": 0, "out": 0},
            "cpu_s": 0.4, "exposure_units": 0}
    base.update(over)
    return base


def _rec(arm, task_id, family, u, costs=None, verified=True):
    return {"arm": arm, "task_id": task_id, "family": family,
            "result": {"disposition": "improved" if u > 0
                       else "no_improvement",
                       "best_measure": 3, "improvement_u": u,
                       "verified": verified,
                       "delivered_digest": "d"},
            "initial": {"measure": 10}, "costs": costs or _costs()}


def _panel(sw_c=0.68, gr_c=0.85, costs=None, verified=True,
           controls=None):
    records = {}
    for task_id in SW_EVA[:2]:
        for arm, u in (("A", 0.7), ("B", 0.7), ("C", sw_c)):
            records[(arm, task_id)] = _rec(arm, task_id, "software", u,
                                           costs, verified)
    for task_id in GR_EVA[:2]:
        for arm, u in (("A", 0.6), ("B", 0.6), ("C", gr_c)):
            records[(arm, task_id)] = _rec(arm, task_id, "graph", u,
                                           costs, verified)
    if controls is None:
        controls = {"ctrl-%d" % i: True for i in range(4)}
    return records, controls


def test_panel_is_heldout_freeze():
    assert panel.PANEL_VERSION == "RPR-ACQ/2"
    assert panel.BENEFIT_SW == SW_EVA
    assert panel.BENEFIT_GR == GR_EVA
    assert panel.MECHANICS_SW + panel.MECHANICS_GR + panel.ACQUIRE_SW \
        + panel.ACQUIRE_GR != panel.BENEFIT_SW + panel.BENEFIT_GR
    assert not [t for t in panel.BENEFIT_SW + panel.BENEFIT_GR
                if "-dev-" in t or "-che-" in t]
    assert all(panel.trial_group(t) == "protected-eval"
               for t in SW_EVA + GR_EVA)
    assert panel.trial_group("sw-dev-00") == "development"
    assert panel.trial_group("sw-che-00") == "check"
    assert len(panel.benefit_pairs()) == 48
    assert len(panel.control_pairs()) == 12


def test_selectors_see_development_only():
    source = contexts.build_source_context(FIXTURES)
    transfer = contexts.build_transfer_context(FIXTURES)
    seen = [t["task_id"] for t in source["tasks"] + transfer["tasks"]]
    assert not [t for t in seen if "-eva-" in t]
    assert "-eva-" not in json.dumps(panel.derive_selectors(source, transfer))
    manifest = _manifest()
    assert manifest["selectors"] == panel.derive_selectors(source, transfer)
    assert "-eva-" not in json.dumps(manifest["selectors"])


def test_eval_fixtures_deterministic():
    for i in range(8):
        assert splits.generate_software("evaluation", i) == json.loads(
            (FIXTURES / "software" / "evaluation"
             / ("sw-eva-%02d.json" % i)).read_bytes())
        assert splits.generate_graph("evaluation", i) == json.loads(
            (FIXTURES / "graphs" / "evaluation"
             / ("gr-eva-%02d.json" % i)).read_bytes())
    assert splits.verify_manifest(FIXTURES) == []


def test_freeze_clean_and_rule_text():
    assert freeze.verify_committed() == []
    manifest = _manifest()
    assert manifest["version"] == "RPR-ACQ/2"
    assert manifest["panel"]["benefit_sw"] == SW_EVA
    assert manifest["panel"]["benefit_gr"] == GR_EVA
    rule = manifest["verdict_rule"]
    for phrase in ("1.25x", "efficiency", "missing CPU/exposure",
                   "cannot certify", "does not authorize"):
        assert phrase in rule, phrase


def test_resource_counterexample_fixed():
    records, controls = _panel(costs=_costs(elapsed_s=1_000_000))
    for (arm, _), record in records.items():
        if arm != "C":
            record["costs"] = _costs(elapsed_s=1.0)
    rule = checker.pilot_rule(records, controls)
    assert rule["clauses"]["transfer-gain-0.10-vs-A"] is True
    assert rule["clauses"]["resources-within-1.25x"] is False
    assert rule["promising"] is False
    assert "resources-within-1.25x" in rule["reasons"]


def test_over_budget_queries_rejected():
    records, controls = _panel()
    for (arm, _), record in records.items():
        record["costs"] = _costs(queries_used=20 if arm == "C" else 4,
                                 validation_used=0)
    rule = checker.pilot_rule(records, controls)
    assert rule["promising"] is False
    assert rule["resources"]["oracle_queries"]["within-1.25x"] is False


def test_unknown_measurement_blocks():
    records, controls = _panel(costs=_costs(elapsed_s=None))
    rule = checker.pilot_rule(records, controls)
    assert rule["promising"] is False
    assert rule["resources"]["elapsed_s"]["C"] is None
    records, _ = _panel()
    for record in records.values():
        del record["costs"]["cpu_s"]
    rule = checker.pilot_rule(records, controls)
    assert rule["promising"] is False
    assert rule["clauses"]["resources-within-1.25x"] is False


def test_zero_denominator_requires_c_zero():
    records, controls = _panel()
    for record in records.values():
        record["costs"] = _costs(queries_used=0, validation_used=0)
    assert checker.pilot_rule(records, controls)["resources"][
        "oracle_queries"]["within-1.25x"] is True
    records[("C", SW_EVA[0])]["costs"] = _costs(queries_used=1,
                                                validation_used=0)
    assert checker.pilot_rule(records, controls)["resources"][
        "oracle_queries"]["within-1.25x"] is False


def test_full_pass_promising_but_unreleased():
    records, controls = _panel()
    rule = checker.pilot_rule(records, controls)
    assert rule["promising"] is True, rule["reasons"]
    assert rule["release_eligible"] is False
    assert "release" in rule["release_note"]


def test_invalid_delivery_and_bad_controls_block():
    records, controls = _panel()
    records[("C", SW_EVA[0])]["result"]["verified"] = False
    rule = checker.pilot_rule(records, controls)
    assert rule["clauses"]["valid-delivery"] is False
    assert rule["promising"] is False
    records, _ = _panel()
    bad = dict(controls)
    bad["ctrl-0"] = False
    rule = checker.pilot_rule(records, bad)
    assert rule["clauses"]["controls-pass"] is False
    assert rule["promising"] is False
    rule = checker.pilot_rule(records, None)
    assert rule["clauses"]["controls-pass"] is False
    assert rule["promising"] is False


def test_efficiency_alternative():
    records, controls = _panel(sw_c=0.7, gr_c=0.6)
    for (arm, _), record in records.items():
        record["costs"] = _costs(queries_used=2 if arm == "C" else 4,
                                 validation_used=0)
    rule = checker.pilot_rule(records, controls)
    assert rule["promising"] is False
    assert rule["efficiency"] == {"vs-A": True, "vs-B": True,
                                  "efficient": True}


def test_checker_rejects_invalid_costs(tmp_path):
    manifest, sha = _manifest(), _sha()
    record = {"arm": "A", "task_id": SW_EVA[0], "family": "software",
              "stage": "heldout", "manifest_sha256": sha,
              "checker_version": panel.CHECKER_VERSION,
              "inputs_digest": {"context": "c", "fixture": "f",
                                "checker": "k"},
              "composition": {"native": True, "procedure": "greedy"},
              "initial": {"measure": 10},
              "result": {"disposition": "improved", "reason": "ok",
                         "best_measure": 3, "improvement_u": 0.7,
                         "verified": True, "delivered_digest": "d"},
              "oracle_queries": [{"verdict": "preserved"}],
              "invocations": [],
              "costs": {"invocations_used": 0, "queries_used": 4,
                        "validation_used": 0, "elapsed_s": float("nan"),
                        "model_calls": 0,
                        "model_tokens": {"in": 0, "out": -1},
                        "cpu_s": 0.1, "exposure_units": 0},
              "trial": [{"protocol_id": "p", "assignment_id": "a",
                         "outcome": "success", "invocation_ref": ""}]}
    root = tmp_path / "evidence"
    (root / "arm_task").mkdir(parents=True)
    (root / "arm_task" / ("A-%s.json" % SW_EVA[0])).write_text(
        json.dumps(record))
    _, problems = checker.check_evidence(root, manifest, sha)
    joined = "\n".join(problems)
    assert "invalid-cost-elapsed_s" in joined
    assert "invalid-cost-model_tokens-out" in joined


def _reference(records, controls):
    means = {}
    for arm in "ABC":
        for family in ("software", "graph"):
            values = [r["result"]["improvement_u"] for (a, _), r in
                      records.items()
                      if a == arm and r["family"] == family]
            means["%s-%s" % (arm, family)] = round(
                sum(values) / len(values), 6)
    quality = means["C-graph"] - means["A-graph"] >= 0.10 \
        and means["C-graph"] - means["B-graph"] >= 0.10 \
        and means["C-software"] - means["A-software"] >= -0.05 \
        and means["C-software"] - means["B-software"] >= -0.05
    valid = all(r["result"]["verified"] is True
                for r in records.values())
    ctrl = bool(controls) and all(controls.values())

    def total(arm, key):
        out = 0
        for (a, _), r in records.items():
            if a != arm:
                continue
            costs = r["costs"]
            tokens = costs.get("model_tokens") or {}
            try:
                out += {"cpu_s": costs["cpu_s"],
                        "elapsed_s": costs["elapsed_s"],
                        "oracle_queries": costs["queries_used"]
                        + costs["validation_used"],
                        "model_tokens": tokens["in"] + tokens["out"],
                        "exposure_units": costs["exposure_units"]}[key]
            except (KeyError, TypeError):
                return None
        return out
    resource = True
    for key in ("cpu_s", "elapsed_s", "oracle_queries", "model_tokens",
                "exposure_units"):
        for comp in "AB":
            base = total(comp, key)
            value = total("C", key)
            if base is None or value is None:
                resource = False
            elif base == 0:
                resource = resource and value == 0
            else:
                resource = resource and value <= 1.25 * base
    return {"means": means, "promising": valid and ctrl and quality
            and resource}


def test_reference_recomputation_matches():
    records, controls = _panel()
    rule = checker.pilot_rule(records, controls)
    ref = _reference(records, controls)
    assert rule["promising"] is True
    assert ref["promising"] == rule["promising"]
    key_of = {("C", "graph"): "C-transfer-mean",
              ("A", "graph"): "A-transfer-mean",
              ("B", "graph"): "B-transfer-mean",
              ("C", "software"): "C-software-mean",
              ("A", "software"): "A-software-mean",
              ("B", "software"): "B-software-mean"}
    for cell, key in key_of.items():
        assert ref["means"]["%s-%s" % cell] == rule["means"][key]


def test_heldout_gate_on_real_db(migrated_db, tmp_path):
    dsn = migrated_db
    roots = {}
    for key in ("artifacts", "staging", "runs", "evidence"):
        path = tmp_path / key
        path.mkdir(parents=True, exist_ok=True)
        roots[key] = path
    index = panel_run.run_panel(
        dsn, tag="t11", artifacts_root=roots["artifacts"],
        staging_root=roots["staging"], runs_root=roots["runs"],
        evidence_root=roots["evidence"])
    assert index["panel_version"] == "RPR-ACQ/2"
    assert index["arm_task_records"] == 48
    assert index["control_records"] == 12
    assert index["attribution_records"] == 2
    assert index["use_records"] == 4
    assert index["release"] == "none"
    assert index["unchanged_core"]["equal"] is True
    benefit = [json.loads(path.read_bytes()) for path in
               sorted((roots["evidence"] / "arm_task").glob("*.json"))]
    assert len(benefit) == 48
    assert {r["trial_group"] for r in benefit} == {"protected-eval"}
    assert all(r["manifest_sha256"] == index["manifest_sha256"]
               for r in benefit)
    assert all(r["costs"]["model_calls"] == 0
               and r["costs"]["model_tokens"] == {"in": 0, "out": 0}
               for r in benefit)
    report = checker.check_all(roots["evidence"])
    assert report["clean"], report["problems"]
    assert checker.check_all(roots["evidence"],
                             dsn=dsn)["clean"]
    records = { (r["arm"], r["task_id"]): r for r in benefit}
    controls = {stem: value for stem, value in
                report["controls"].items()}
    rule = checker.pilot_rule(records, controls)
    assert rule == report["pilot_rule"]
    ref = _reference(records, controls)
    assert ref["promising"] == rule["promising"]
    assert rule["promising"] is False
    assert rule["clauses"]["transfer-gain-0.10-vs-A"] is False
    assert rule["release_eligible"] is False
    assert index["physical_operation_union"] > 0
