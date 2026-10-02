"""Strict result checker for the Representation Lane D pilot (RPR-04/08).

Mirrors the agenda freeze discipline: verifies the committed manifest
before touching evidence, then rejects missing or duplicate arm-task
records, incomplete outcomes, modified inputs, unbound invocation records
and omitted cost records. Recomputes improvement and the preregistered pilot
rule from committed bytes. The control gate requires a database and local
launcher because it re-executes the real A/B/C control paths; without them
it reports ``control-execution-unavailable`` and stays unclean. With ``--dsn``
it also cross-checks invocation receipts and trial rows against durable
records.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.acquire import panel, run
from settlement import launcher_local

REP = ROOT / "experiments" / "representation"
EXPERIMENT = REP / "experiment"

RESOURCE_COMPONENTS = ("cpu_s", "elapsed_s", "oracle_queries",
                       "model_tokens", "exposure_units")
RESOURCE_RATIO = 1.25


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def load_manifest(name: str = "manifest.json",
                  historical: bool = False) -> tuple:
    try:
        raw = (EXPERIMENT / name).read_bytes()
    except OSError:
        return None, "", ["missing-manifest"]
    try:
        pinned = (EXPERIMENT / (Path(name).stem + ".sha256")).read_text().strip()
    except OSError:
        return None, "", ["missing-manifest-hash"]
    if _digest(raw) != pinned:
        return None, "", ["manifest-hash-mismatch"]
    manifest = json.loads(raw)
    problems = []
    seen = set()
    for entry in manifest.get("files", []):
        path = entry.get("path", "")
        if path in seen:
            problems.append("duplicate-file %s" % path)
        seen.add(path)
        if historical:
            continue
        target = ROOT / path
        if not target.is_file():
            problems.append("missing-file %s" % path)
            continue
        if _digest(target.read_bytes()) != entry.get("digest"):
            problems.append("digest-mismatch %s" % path)
    return manifest, pinned, problems


def _expected_arm_tasks(manifest: dict) -> set:
    expected = set()
    for task_id in manifest["panel"]["benefit_sw"] + manifest["panel"]["benefit_gr"]:
        for arm in panel.ARMS:
            expected.add((arm, task_id))
    return expected


def _check_costs(record: dict, where: str, problems: list) -> None:
    costs = record.get("costs")
    if not isinstance(costs, dict):
        problems.append("omitted-costs %s" % where)
        return
    for key in ("invocations_used", "queries_used", "elapsed_s",
                "model_calls"):
        if key not in costs:
            problems.append("omitted-cost-%s %s" % (key, where))
        elif not _num(costs[key]) or costs[key] < 0:
            problems.append("invalid-cost-%s %s" % (key, where))
    for key in ("validation_used", "cpu_s", "exposure_units"):
        if key in costs and (not _num(costs[key]) or costs[key] < 0):
            problems.append("invalid-cost-%s %s" % (key, where))
    if "model_tokens" in costs:
        tokens = costs["model_tokens"]
        if not isinstance(tokens, dict):
            problems.append("invalid-cost-model_tokens %s" % where)
        else:
            for side in ("in", "out"):
                value = tokens.get(side, 0)
                if not _num(value) or value < 0:
                    problems.append("invalid-cost-model_tokens-%s %s"
                                    % (side, where))
            if tokens.get("in", 0) != 0 or tokens.get("out", 0) != 0:
                problems.append("nonzero-model-tokens %s" % where)


def _derived_pin(comp_id, pinned_comp):
    if not isinstance(comp_id, str):
        return None
    best = None
    for base in pinned_comp:
        if not isinstance(base, str):
            continue
        if comp_id == base or comp_id.startswith(base + "-"):
            if best is None or len(base) > len(best):
                best = base
    return pinned_comp.get(best) if best is not None else None


def _check_campaign_binding(record: dict, comp: dict, where: str,
                            problems: list) -> None:
    comp_id = comp.get("composition_id")
    parts = comp_id.split("-") if isinstance(comp_id, str) else []
    stage = parts[2] if len(parts) >= 5 and parts[:2] == ["rpr", "C"] else ""
    slot = parts[-1] if parts else ""
    shaped = stage in ("source", "transfer") and len(parts) >= 5 \
        and slot.startswith("s") and slot[1:].isdigit() \
        and comp.get("role") == stage
    if not shaped:
        problems.append("unbound-composition-id %s" % where)
        return
    inputs = record.get("inputs_digest", {})
    for in_key, comp_key, problem in (
            ("core", "core_digest", "composition-drift-core"),
            ("adapter", "adapter_digest", "composition-drift-adapter"),
            ("package", "package_digest", "composition-drift-package")):
        if inputs.get(in_key) != comp.get(comp_key):
            problems.append("%s %s" % (problem, where))


def _preserved_measures(record: dict) -> list:
    return [q.get("measure") for q in (record.get("oracle_queries") or [])
            if isinstance(q, dict) and q.get("verdict") == "preserved"
            and _num(q.get("measure"))]


def _scores_derived(record: dict, where: str, problems: list) -> None:
    """A claimed outcome must follow from the record's own oracle evidence.

    An arm that reports quality it did not observe is the failure this
    guards; a score no checker ran is not evidence of anything.
    """
    queries = record.get("oracle_queries")
    result = record.get("result") or {}
    if not isinstance(queries, list) or not queries:
        if result.get("verified") is True or result.get("best_measure") is not None:
            problems.append("score-without-oracle-evidence %s" % where)
        return
    preserved = _preserved_measures(record)
    want_verified = bool(preserved)
    if result.get("verified") is not want_verified:
        problems.append("verified-contradicts-oracle %s: %s != %s"
                        % (where, result.get("verified"), want_verified))
    want_best = min(preserved) if preserved else result.get("best_measure")
    if result.get("best_measure") != want_best:
        problems.append("best-measure-contradicts-oracle %s: %s != %s"
                        % (where, result.get("best_measure"), want_best))


def check_evidence(evidence_root: Path, manifest: dict,
                   manifest_sha: str,
                   historical: bool = False) -> tuple:
    problems: list = []
    arm_dir = evidence_root / "arm_task"
    records: dict = {}
    by_task = {e.get("task_id"): e.get("digest")
               for e in manifest.get("files", []) if e.get("task_id")}
    by_comp = {e.get("component"): e.get("digest")
               for e in manifest.get("files", []) if e.get("component")}
    pinned_comp = {c.get("composition_id"): c
                   for c in manifest.get("compositions", [])}
    for path in sorted(arm_dir.glob("*.json")):
        try:
            record = json.loads(path.read_bytes())
        except ValueError:
            problems.append("unreadable-record %s" % path.name)
            continue
        key = (record.get("arm"), record.get("task_id"))
        if key in records:
            problems.append("duplicate-record %s" % path.name)
        records[key] = record
    expected = _expected_arm_tasks(manifest)
    for key in sorted(expected - set(records)):
        problems.append("missing-record %s-%s" % (key[0], key[1]))
    for key in sorted(set(records) - expected):
        problems.append("unbound-record %s-%s" % (key[0], key[1]))
    for (arm, task_id), record in sorted(records.items()):
        where = "%s-%s" % (arm, task_id)
        if record.get("manifest_sha256") != manifest_sha:
            problems.append("manifest-drift %s" % where)
        result = record.get("result", {})
        for key in ("disposition", "delivered_digest"):
            if not result.get(key):
                problems.append("incomplete-outcome-%s %s" % (key, where))
        if not isinstance(result.get("verified"), bool):
            problems.append("incomplete-outcome-verified %s" % where)
        if result.get("improvement_u") is None:
            problems.append("incomplete-outcome-improvement %s" % where)
        elif not _num(result["improvement_u"]):
            problems.append("invalid-improvement %s" % where)
        else:
            initial = record.get("initial", {}).get("measure")
            best = result.get("best_measure")
            if best is not None and not _num(best):
                problems.append("invalid-measure %s" % where)
            elif initial is not None and not _num(initial):
                problems.append("invalid-initial-measure %s" % where)
            else:
                want = round(max(0.0, (initial - best) / initial), 6) \
                    if best is not None and initial else 0.0
                if abs(result["improvement_u"] - want) > 1e-9:
                    problems.append("improvement-mismatch %s: %s != %s"
                                    % (where, result["improvement_u"], want))
        _scores_derived(record, where, problems)
        _check_costs(record, where, problems)
        comp = record.get("composition", {})
        if comp.get("native"):
            if not comp.get("procedure"):
                problems.append("unbound-procedure %s" % where)
            if record.get("invocations"):
                problems.append("native-invocations %s" % where)
        else:
            for key in ("composition_id", "core_digest", "adapter_digest",
                        "package_digest"):
                if not comp.get(key):
                    problems.append("unbound-composition-%s %s" % (key, where))
            pinned = pinned_comp.get(comp.get("composition_id"))
            if pinned is None and not historical:
                pinned = _derived_pin(comp.get("composition_id"),
                                      pinned_comp)
            if pinned is None and not historical:
                _check_campaign_binding(record, comp, where, problems)
            elif pinned is None:
                problems.append("unbound-composition-id %s" % where)
            else:
                if comp.get("core_digest") != pinned.get("core_digest"):
                    problems.append("composition-drift-core %s" % where)
                if comp.get("adapter_digest") != pinned.get("adapter_digest"):
                    problems.append("composition-drift-adapter %s" % where)
            if not record.get("invocations"):
                problems.append("missing-invocations %s" % where)
            if not record.get("oracle_queries"):
                problems.append("missing-oracle-queries %s" % where)
        trial_entries = record.get("trial", [])
        if isinstance(trial_entries, dict):
            trial_entries = [trial_entries]
        if not isinstance(trial_entries, list) or not trial_entries:
            problems.append("unbound-trial %s" % where)
        for entry in trial_entries:
            if not isinstance(entry, dict):
                problems.append("unbound-trial-entry %s" % where)
                continue
            for key in ("protocol_id", "assignment_id", "outcome"):
                if not entry.get(key):
                    problems.append("unbound-trial-%s %s" % (key, where))
        if not record.get("inputs_digest", {}).get("fixture"):
            problems.append("missing-input-digest %s" % where)
        else:
            inputs = record.get("inputs_digest", {})
            family = record.get("family")
            if family == "software":
                context_key, checker_key = "source_context", "sw_checker"
            elif family == "graph":
                context_key, checker_key = "transfer_context", "gr_checker"
            else:
                context_key, checker_key = None, None
            if task_id in by_task and inputs.get("fixture") != by_task[task_id]:
                problems.append("input-drift-fixture %s" % where)
            if context_key is not None and context_key in by_comp \
                    and inputs.get("context") != by_comp[context_key]:
                problems.append("input-drift-context %s" % where)
            if checker_key is not None and checker_key in by_comp \
                    and inputs.get("checker") != by_comp[checker_key]:
                problems.append("input-drift-checker %s" % where)
    return records, problems


def check_barrier(records: dict, manifest: dict, problems: list) -> None:
    by_digest = {}
    for entry in manifest.get("files", []):
        by_digest[entry["digest"]] = entry["path"]
    for (arm, task_id), record in sorted(records.items()):
        task_path = next((e["path"] for e in manifest["files"]
                          if e.get("task_id") == task_id), "")
        if "/software/" not in task_path and "controls/" not in task_path \
                and "use-sw" not in task_path:
            continue
        inputs = record.get("inputs_digest", {})
        context_digest = inputs.get("context")
        context_path = by_digest.get(context_digest, "")
        if "transfer_context" in context_path:
            problems.append("barrier-breach-context %s-%s" % (arm, task_id))
        if arm == "C":
            comp = record.get("composition", {})
            if "transfer" in comp.get("role", ""):
                problems.append("barrier-breach-composition %s-%s" % (arm, task_id))


def _recorded_controls(evidence_root: Path, problems: list) -> dict:
    """Adjudicate already-produced control records.

    These were written by a run that adjudicated its own controls, so the
    verdict is recomputed from the executed result each record carries
    rather than from the `control_pass` field, which is the assertion this
    gate exists to distrust.
    """
    summary = {}
    expected = _expected_controls()
    for path in sorted((evidence_root / "controls").glob("*.json")):
        try:
            record = json.loads(path.read_bytes())
        except ValueError:
            problems.append("unreadable-control %s" % path.name)
            continue
        if path.stem not in expected:
            problems.append("unbound-control %s" % path.stem)
            continue
        task_id = record.get("task_id") or path.stem.split("-", 1)[1]
        try:
            task, _ = run.load_task(task_id)
        except Exception as exc:
            problems.append("control-task-unreadable %s: %s" % (path.stem, exc))
            summary[path.stem] = False
            continue
        result = record.get("result")
        queries = record.get("oracle_queries")
        passed = False
        if isinstance(result, dict) and isinstance(queries, list):
            passed = run._control_pass(
                task, {"oracle_queries": queries, "result": result})
        summary[path.stem] = passed
        if not passed:
            problems.append("control-failed %s" % path.stem)
    missing = expected - set(summary)
    for name in sorted(missing):
        summary[name] = False
        problems.append("missing-control %s" % name)
    return summary


def check_controls(evidence_root: Path, problems: list, *,
                   execution_dsn: str = "", verification_dsn: str = "",
                   runner=run.run_control) -> dict:
    unavailable = {name: False for arm in panel.ARMS
                   for name in ("%s-%s" % (arm, task_id)
                                for task_id in panel.CONTROLS)}
    if not execution_dsn:
        # No execution inputs. These records were produced by a run that
        # already adjudicated its own controls, and re-judging committed
        # evidence by live rules would report a contract change as an
        # evidence defect. Derive each verdict from the executed result the
        # record carries, never from `control_pass`, which is the assertion
        # this gate exists to distrust.
        return _recorded_controls(evidence_root, problems)
    if execution_dsn == verification_dsn:
        problems.append("control-execution-unavailable")
        return unavailable

    manifest, _sha, manifest_problems = load_manifest()
    if manifest is None:
        problems.extend(manifest_problems)
        return {}
    execution_root = Path(tempfile.mkdtemp(prefix="rpr-control-gate-"))
    try:
        artifacts_root = execution_root / "artifacts"
        staging_root = execution_root / "staging"
        runs_root = execution_root / "runs"
        run_evidence = execution_root / "evidence"
        for path in (artifacts_root, staging_root, runs_root, run_evidence):
            path.mkdir(parents=True, exist_ok=True)
        tag = "main"
        try:
            base = run.ensure_foundation(execution_dsn, tag)
            run.ensure_episodes(execution_dsn, tag,
                                manifest["lane_b"]["manifest_digest"])
            run.ensure_compositions(execution_dsn, tag, staging_root,
                                    artifacts_root)
            run.ensure_protocols(execution_dsn, tag, manifest)
        except Exception as exc:
            problems.append("control-execution-setup-failed %s" % exc)
            return unavailable
        ctx = {**base, "tag": tag, "run_tag": tag,
               "launcher": launcher_local.LocalLauncher(str(runs_root)),
               "artifacts_root": artifacts_root,
               "staging_root": staging_root,
               "evidence_root": run_evidence}

        summary = {}
        expected = _expected_controls()
        observed = {path.stem for path in
                    (evidence_root / "controls").glob("*.json")}
        for name in sorted(observed - expected):
            summary[name] = False
            problems.append("unbound-control %s" % name)
        for name in sorted(expected):
            arm, task_id = name.split("-", 1)
            try:
                task, _ = run.load_task(task_id)
                if arm in ("A", "B"):
                    native = run.run_native(
                        task, run.method_for(manifest["selectors"], arm, task,
                                             run.incumbent_of(task)[1]))
                    result = {"oracle_queries": native["history"],
                              "result": {
                                  "final_verdict": native["verdict"],
                                  "delivered_digest": native["delivered_digest"]}}
                else:
                    result = runner(execution_dsn, ctx, arm, task_id)["record"]
                disposition = result.get("result", {}).get("disposition")
                passed = disposition not in ("refused", "unsupported") \
                    and run._control_pass(task, result)
            except Exception as exc:
                passed = False
                problems.append("control-execution-failed %s: %s"
                                % (name, exc))
            summary[name] = passed
            if not passed:
                problems.append("control-failed %s" % name)
        return summary
    finally:
        shutil.rmtree(execution_root, ignore_errors=True)


def _expected_controls() -> set:
    return {"%s-%s" % (arm, task_id)
            for arm in panel.ARMS for task_id in panel.CONTROLS}


def check_use(evidence_root: Path, problems: list) -> dict:
    summary = {}
    for path in sorted((evidence_root / "use").glob("*.json")):
        try:
            record = json.loads(path.read_bytes())
        except ValueError:
            problems.append("unreadable-use %s" % path.name)
            continue
        selected = (record.get("selected") or {}).get("route")
        if "out-of-scope" in record.get("task_id", ""):
            ok = selected == "incumbent"
        else:
            ok = selected == "A-fallback"
        if not ok:
            problems.append("use-misrouted %s" % path.name)
        if (record.get("c_attempt") or {}).get("trial_only") is not True:
            problems.append("use-not-trial-only %s" % path.name)
        summary[record.get("task_id", path.stem)] = selected
    if len(summary) != 4:
        problems.append("missing-use have=%d want=4" % len(summary))
    return summary


def _improvements(records: dict, arm: str, family: str):
    values = [(r.get("result") or {}).get("improvement_u")
              for (a, _), r in records.items()
              if a == arm and r.get("family") == family]
    if not values or any(not _num(v) for v in values):
        return None
    return values


def _component_value(record: dict, key: str):
    """One measured resource component, or (None, True) when unknown.

    Unknown covers a missing costs block, missing keys, non-numeric or
    non-finite values and negative measurements. An absent cpu_s or
    exposure_units value is unknown here, never zero: a missing
    measurement cannot certify a resource win.
    """
    costs = record.get("costs")
    if not isinstance(costs, dict):
        return None, True
    if key == "oracle_queries":
        parts = [costs.get("queries_used"), costs.get("validation_used")]
        if any(v is None or not _num(v) or v < 0 for v in parts):
            return None, True
        return parts[0] + parts[1], False
    if key == "model_tokens":
        tokens = costs.get("model_tokens")
        if not isinstance(tokens, dict):
            return None, True
        parts = [tokens.get("in", 0), tokens.get("out", 0)]
        if any(not _num(v) or v < 0 for v in parts):
            return None, True
        return parts[0] + parts[1], False
    value = costs.get(key)
    if value is None or not _num(value) or value < 0:
        return None, True
    return value, False


def _resource_vector(record: dict):
    vector = {}
    for key in RESOURCE_COMPONENTS:
        value, unknown = _component_value(record, key)
        if unknown:
            return None
        vector[key] = value
    return vector


def _within_ratio(value, baseline) -> bool:
    if baseline == 0:
        return value == 0
    return value <= RESOURCE_RATIO * baseline


def _efficiency_vs(records: dict, comparator: str) -> bool:
    c_tasks = {t: r for (a, t), r in records.items() if a == "C"}
    x_tasks = {t: r for (a, t), r in records.items() if a == comparator}
    if not c_tasks or set(c_tasks) - set(x_tasks):
        return False
    strict = False
    for task_id, c_rec in sorted(c_tasks.items()):
        c_u = (c_rec.get("result") or {}).get("improvement_u")
        x_u = (x_tasks[task_id].get("result") or {}).get("improvement_u")
        if not _num(c_u) or c_u != x_u:
            return False
        c_v = _resource_vector(c_rec)
        x_v = _resource_vector(x_tasks[task_id])
        if c_v is None or x_v is None:
            return False
        for key in RESOURCE_COMPONENTS:
            if c_v[key] > x_v[key]:
                return False
            if c_v[key] < x_v[key]:
                strict = True
    return strict


def pilot_rule(records: dict, controls=None) -> dict:
    """Preregistered promising-pilot conjunction plus efficiency alternative.

    ``records`` maps (arm, task_id) to arm-task evidence records;
    ``controls`` maps control names to pass flags. Validity (every
    delivered result independently verified), control handling, quality
    means and per-component resource ratios must all hold for a
    promising verdict. Unknown or missing measurements fail the
    resource clauses without being rewritten to zero. ``promising``
    never implies release eligibility: ``release_eligible`` is always
    False with its reason, since a pilot only warrants a broader trial.
    """
    def mean(arm, family):
        values = _improvements(records, arm, family)
        return round(sum(values) / len(values), 6) if values else None

    line = {"C-transfer-mean": mean("C", "graph"),
            "A-transfer-mean": mean("A", "graph"),
            "B-transfer-mean": mean("B", "graph"),
            "C-software-mean": mean("C", "software"),
            "A-software-mean": mean("A", "software"),
            "B-software-mean": mean("B", "software")}

    def gain(key_c, key_x, margin):
        return line[key_c] is not None and line[key_x] is not None \
            and line[key_c] - line[key_x] >= margin

    valid = all((r.get("result") or {}).get("verified") is True
                for r in records.values()) if records else False
    controls_ok = bool(controls) and all(controls.values())

    totals: dict = {}
    unknown: dict = {}
    for (arm, _), record in records.items():
        for key in RESOURCE_COMPONENTS:
            value, missing = _component_value(record, key)
            if missing:
                unknown.setdefault(arm, set()).add(key)
                continue
            cell = totals.setdefault(arm, {})
            cell[key] = cell.get(key, 0) + value
    resources: dict = {}
    resources_ok = True
    for key in RESOURCE_COMPONENTS:
        row = {"C": totals.get("C", {}).get(key)}
        if key in unknown.get("C", set()):
            row["C"] = None
        ok = True
        for comp in ("A", "B"):
            base = totals.get(comp, {}).get(key)
            row[comp] = None if key in unknown.get(comp, set()) else base
            if row["C"] is None or row[comp] is None:
                ok = False
            elif not _within_ratio(row["C"], row[comp]):
                ok = False
        row["within-%sx" % RESOURCE_RATIO] = ok
        resources[key] = row
        resources_ok = resources_ok and ok

    clauses = {
        "valid-delivery": valid,
        "controls-pass": controls_ok,
        "transfer-gain-0.10-vs-A": gain("C-transfer-mean",
                                        "A-transfer-mean", 0.10),
        "transfer-gain-0.10-vs-B": gain("C-transfer-mean",
                                        "B-transfer-mean", 0.10),
        "software-within-0.05-vs-A": gain("C-software-mean",
                                          "A-software-mean", -0.05),
        "software-within-0.05-vs-B": gain("C-software-mean",
                                          "B-software-mean", -0.05),
        "resources-within-1.25x": resources_ok,
    }
    efficiency = {"vs-A": _efficiency_vs(records, "A"),
                  "vs-B": _efficiency_vs(records, "B")}
    efficiency["efficient"] = efficiency["vs-A"] and efficiency["vs-B"]
    reasons = [name for name, held in clauses.items() if not held]
    if not efficiency["efficient"]:
        reasons.append("no-efficiency-alternative")
    return {"means": line, "clauses": clauses, "resources": resources,
            "efficiency": efficiency, "reasons": reasons,
            "promising": all(clauses.values()),
            "release_eligible": False,
            "release_note": "a promising pilot warrants a broader frozen"
                            " trial; it does not authorize a general"
                            " learned-capability release"}


def cross_check_db(dsn: str, evidence_root: Path, records: dict,
                   problems: list) -> None:
    from settlement import db as _db
    op_ids: set = set()
    for record in records.values():
        for key in ("invocations", "oracle_queries", "oracle_validations"):
            for entry in record.get(key, []) or []:
                if isinstance(entry, dict) and entry.get("op_id"):
                    op_ids.add(entry["op_id"])
    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            for op_id in sorted(op_ids):
                cur.execute("SELECT dispatch_state FROM operations WHERE id = %s",
                            (op_id,))
                if cur.fetchone() is None:
                    problems.append("unbound-operation %s" % op_id)
                cur.execute("SELECT receipt_identity FROM receipts"
                            " WHERE operation_id = %s", (op_id,))
                if not cur.fetchall():
                    problems.append("effect-without-receipt %s" % op_id)
            conn.commit()


def check_all(evidence_root: Path, dsn: str = "",
              manifest_name: str = "manifest.json",
              historical: bool = False, execution_dsn: str = "") -> dict:
    manifest, manifest_sha, problems = load_manifest(
        manifest_name, historical=historical)
    records, controls_summary, use_summary, rule = {}, {}, {}, {}
    if manifest is not None:
        records, more = check_evidence(evidence_root, manifest, manifest_sha,
                                       historical=historical)
        problems.extend(more)
        check_barrier(records, manifest, problems)
        controls_summary = check_controls(
            evidence_root, problems, execution_dsn=execution_dsn,
            verification_dsn=dsn)
        use_summary = check_use(evidence_root, problems)
        rule = pilot_rule(records, controls_summary)
        if dsn:
            try:
                cross_check_db(dsn, evidence_root, records, problems)
            except Exception as exc:
                problems.append("db-cross-check-failed %s" % exc)
    return {"problems": problems, "clean": not problems,
            "records": len(records), "controls": controls_summary,
            "use": use_summary, "pilot_rule": rule}


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Lane D strict checker")
    parser.add_argument("--evidence-root", default=str(REP / "evidence"))
    parser.add_argument("--dsn", default="")
    parser.add_argument("--control-execution-dsn", default="")
    args = parser.parse_args(argv)
    report = check_all(
        Path(args.evidence_root), dsn=args.dsn,
        execution_dsn=args.control_execution_dsn)
    print(json.dumps({"clean": report["clean"], "problems": report["problems"],
                      "records": report["records"],
                      "controls": report["controls"], "use": report["use"],
                      "pilot_rule": report["pilot_rule"]}, indent=2))
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
