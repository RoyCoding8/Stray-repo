"""Investigation 01 engineering pilot on the M1-M5 path."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
MODEL = "inv01-study-double"
CALIBRATION_WORLD = 0
COMPARISON_WORLDS = [1, 2]


def _family(task_id: str) -> str:
    return "graph" if "-gr-" in task_id else "software"


def _dev_tasks(world: int) -> list:
    from experiments.ad01 import rotation
    return [s["task_id"] for s in rotation.r_schedule(world)]


def _arm_tasks(world: int, arm: str) -> list:
    ordered = _dev_tasks(world)
    if arm == "I":
        return list(reversed(ordered))
    return list(ordered)


def _use_tasks(world: int) -> list:
    from experiments.ad01 import trajectory
    membership = trajectory.worlds.world_membership(
        trajectory.worlds.FROZEN_DIR)
    kinds = membership[str(world)]
    tasks = []
    for domain in ("software", "graph"):
        tasks.extend(kinds["within"][domain][:2])
        tasks.extend(kinds["transfer"][domain][:1])
    return tasks


def build_cap_sheet() -> dict:
    from experiments.ad01 import construct, method_exec, packet
    from experiments.ad01 import trajectory as _traj
    from settlement import broker
    from settlement.exec_profile import STOP_SETTLE_S
    learner_bounds = {"max_output_tokens": 2048,
                      "deadline_ms": 300_000}
    construction_bounds = {"max_output_tokens": 2048,
                           "deadline_ms": 300_000}
    sandbox_bounds = {"timeout_ms": method_exec.DEFAULT_TIMEOUT_MS,
                      "max_output_bytes": 1_048_576,
                      "profile": "local-process"}
    per_trajectory = {"max_boundaries": 6,
                      "max_dev_episodes": _traj.DEV_EPISODE_CAP,
                      "max_lineages": construct.MAX_LINEAGES,
                      "max_construction_calls":
                          construct.CONSTRUCTION_CALL_CEILING,
                      "max_model_calls": 60,
                      "diagnostic_queries": 96,
                      "max_witness_queries_per_development": 16}
    study = {"trajectories": 6,
             "max_construction_calls": 24,
             "max_model_calls": 360,
             "max_boundaries": 36,
             "deadline_s": 3600}
    derivation = {
        "per_trajectory_boundaries": "WORKER-INVESTIGATION-01-COMPLETION"
        " pilot ceiling, enforced in trajectory.run_campaign",
        "per_trajectory_dev_episodes": "trajectory.DEV_EPISODE_CAP",
        "per_trajectory_lineages": "construct.MAX_LINEAGES, one init"
        " plus at most one repair each",
        "per_trajectory_construction":
        "construct.CONSTRUCTION_CALL_CEILING",
        "per_trajectory_model_calls": "caps model_calls, learner plus"
        " construction through broker",
        "per_trajectory_diagnostic_queries": "6 boundaries times 16"
        " explicit max_queries per development, not a historical"
        " average",
        "study_construction": "6 trajectories times 4 construction"
        " calls",
        "study_model_calls": "6 trajectories times 60 model calls",
        "token_estimate_kind": "estimated-budget",
        "token_estimate_note": "broker model exposure sums"
        " request characters divided by 4 plus max_output_tokens as"
        " an estimate only, never an absolute token bound",
        "query_ceiling_source": "explicit max_queries budgets and"
        " diagnostic caps, never a historical average",
        "learner_request": learner_bounds,
        "construction_request": construction_bounds,
        "sandbox_operation": sandbox_bounds,
        "sandbox_exposure_note": "hard-ceiling from timeout plus"
        " %d settle seconds" % STOP_SETTLE_S,
        "model_exposure_kind": "estimated-budget",
        "sandbox_exposure_kind": "hard-ceiling",
        "deadline_note": "overall study wall clock enforced before"
        " each trajectory, per-operation deadlines from runner"
        " settings",
        "packet_version": packet.PACKET_VERSION,
    }
    return {"per_trajectory": per_trajectory, "study": study,
            "derivation": derivation,
            "accounting_kinds": ["estimate", "measured",
                                 "internal_charge",
                                 "provider_billing"],
            "kinds_note": {
                "estimate": "broker exposure_schedule before effects",
                "measured": "receipt usage input/output tokens plus"
                " witness queries plus sandbox ops",
                "internal_charge": "charge_units reserved against the"
                " study allocation",
                "provider_billing": "only usage with billed true;"
                " recording doubles report billed false"}}


def check_caps_against_runner(sheet: dict) -> dict:
    from experiments.ad01 import construct, method_exec, packet
    from experiments.ad01 import trajectory as _traj
    problems = []
    per = sheet.get("per_trajectory", {})
    study = sheet.get("study", {})
    if per.get("max_boundaries") != 6:
        problems.append("per-trajectory boundaries must be 6")
    if per.get("max_dev_episodes") != _traj.DEV_EPISODE_CAP:
        problems.append("dev episodes must match runner %s" % (
            _traj.DEV_EPISODE_CAP,))
    if per.get("max_lineages") != construct.MAX_LINEAGES:
        problems.append("lineages must match runner %s" % (
            construct.MAX_LINEAGES,))
    if per.get("max_construction_calls") != \
            construct.CONSTRUCTION_CALL_CEILING:
        problems.append("construction calls must match runner %s" % (
            construct.CONSTRUCTION_CALL_CEILING,))
    if per.get("max_model_calls") != 60:
        problems.append("per-trajectory model calls must be 60")
    if study.get("max_construction_calls") != 24:
        problems.append("study construction must be 24")
    if study.get("max_model_calls") != 360:
        problems.append("study model calls must be 360")
    if sheet.get("derivation", {}).get("packet_version") != \
            packet.PACKET_VERSION:
        problems.append("packet version drift")
    if sheet.get("derivation", {}).get(
            "token_estimate_kind") != "estimated-budget":
        problems.append("token bound must stay an estimate")
    if sheet.get("accounting_kinds") != [
            "estimate", "measured", "internal_charge",
            "provider_billing"]:
        problems.append("accounting kinds must stay split four ways")
    req = sheet.get("derivation", {}).get("learner_request", {})
    if req.get("max_output_tokens") != 2048:
        problems.append("learner output bound drift")
    if req.get("deadline_ms") != 300_000:
        problems.append("learner deadline drift")
    sandbox = sheet.get("derivation", {}).get("sandbox_operation", {})
    if sandbox.get("timeout_ms") != method_exec.DEFAULT_TIMEOUT_MS:
        problems.append("sandbox timeout drift")
    if not isinstance(study.get("deadline_s"), int) or \
            study.get("deadline_s") <= 0:
        problems.append("study needs a positive overall deadline")
    return {"problems": problems}


class StudyBudget:
    def __init__(self, sheet: dict, deadline_s: int = 3600):
        self.limits = {"model_calls": int(
            sheet["study"]["max_model_calls"]),
            "construction_calls": int(
                sheet["study"]["max_construction_calls"]),
            "boundaries": int(sheet["study"]["max_boundaries"])}
        self.counts = {"model_calls": 0, "construction_calls": 0,
                       "boundaries": 0}
        self.start = time.monotonic()
        self.deadline_s = int(deadline_s or sheet["study"][
            "deadline_s"])

    def admit(self, model_calls: int = 0, construction_calls: int = 0,
              boundaries: int = 0) -> dict:
        elapsed = time.monotonic() - self.start
        if elapsed >= self.deadline_s:
            return {"ok": False,
                    "reason": "study deadline exceeded"}
        for key, want in (("model_calls", model_calls),
                          ("construction_calls", construction_calls),
                          ("boundaries", boundaries)):
            if self.counts[key] + int(want) > self.limits[key]:
                return {"ok": False,
                        "reason": "study cap exceeded for %s" % key}
        return {"ok": True, "reason": ""}

    def spend(self, model_calls: int = 0, construction_calls: int = 0,
              boundaries: int = 0) -> None:
        self.counts["model_calls"] += int(model_calls)
        self.counts["construction_calls"] += int(construction_calls)
        self.counts["boundaries"] += int(boundaries)


def external_requirements() -> dict:
    endpoint = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT", "")
    key_env = "SETTLEMENT_GATEWAY_KEY"
    key_present = bool(os.environ.get(key_env, ""))
    try:
        from settlement.config import Settings
        settings = Settings.from_env()
        endpoint_present = bool(settings.gateway.endpoint or endpoint)
    except Exception:
        endpoint_present = bool(endpoint)
    return {"endpoint_present": "present" if endpoint_present
            else "missing",
            "key_present": "present" if key_present else "missing",
            "key_env": key_env,
            "grant": "missing: agenda authority plus construction"
            " grant required for live; recording pilot needs none",
            "live_model": "missing unless a live model label is"
            " supplied; pilot uses recording doubles"}


def _scripts_for(tasks: list) -> list:
    from experiments import doubles as D
    scripts = []
    for task_id in tasks:
        scripts.append(D.learner_development_text(
            task_id, _family(task_id)))
    return scripts


def _run_trajectory(dsn: str, world: int, arm: str, tasks: list,
                    agenda_authorized: int, budget: StudyBudget) -> dict:
    from experiments import doubles as D
    from experiments.ad01 import learner, trajectory
    gate = budget.admit(model_calls=60, construction_calls=4,
                        boundaries=len(tasks))
    if not gate["ok"]:
        raise RuntimeError("study budget refuses trajectory: %s" % (
            gate["reason"],))
    scripts = _scripts_for(tasks)
    gateway = D.InvCQualificationDouble(
        learner_scripts=list(scripts))
    cid = trajectory.campaign_id(world, arm, 0)
    trajectory.authorize_campaign(dsn, cid,
                                  authorized=agenda_authorized)
    seed = trajectory.ensure_campaign(
        dsn, cid, world, arm, dict(CHARTER),
        {"max_boundaries": 6, "diagnostic_queries": 96,
         "model_calls": 60, "construction_tokens": 2048,
         "agenda_authorized": agenda_authorized}, tasks=list(tasks))
    propose = learner.propose_from_model(
        dsn, cid=cid, gateway=gateway, model=MODEL,
        charter=dict(CHARTER), world=world, arm=arm,
        allocation_id=seed["allocation_id"])
    campaign = trajectory.run_campaign(
        world, arm, dict(CHARTER),
        {"max_boundaries": 6, "diagnostic_queries": 96,
         "model_calls": 60, "construction_tokens": 2048,
         "agenda_authorized": agenda_authorized}, tasks=list(tasks),
        propose=propose, campaign_seq=0, dsn=dsn,
        gateway=gateway, model=MODEL, constructor="model")
    budget.spend(model_calls=int(campaign.get("model_calls", 0)),
                 construction_calls=int(campaign.get(
                     "construction_calls", 0)),
                 boundaries=len(campaign.get("boundaries", [])))
    return campaign


def _fresh_use(repertoire_path: Path, world: int, arm: str,
               tasks: list, dsn: str, allocation_id: str) -> list:
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "use",
         "--repertoire", str(repertoire_path), "--world", str(world),
         "--arm", arm, "--tasks", ",".join(tasks),
         "--dsn", dsn, "--allocation-id", allocation_id],
        cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError("fresh-process use failed: %s" % (
            proc.stderr[-2000:],))
    return json.loads(proc.stdout)


def run_study(dsn: str, out: Path, agenda_authorized: int,
              deadline_s: int = 3600) -> int:
    from experiments.ad01 import records, trajectory
    if "inv_c3_" not in dsn:
        print("study refuses non-disposable dsn", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    sheet = build_cap_sheet()
    checked = check_caps_against_runner(sheet)
    if checked["problems"]:
        print("cap sheet drift: %s" % checked["problems"],
              file=sys.stderr)
        return 2
    (out / "cap_sheet.json").write_text(json.dumps(
        sheet, sort_keys=True, indent=1) + "\n")
    budget = StudyBudget(sheet, deadline_s=deadline_s)
    (out / "external_requirements.json").write_text(json.dumps(
        external_requirements(), sort_keys=True, indent=1) + "\n")
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(dsn, ROOT / "migrations")
    E.designate_db(dsn, kind="disposable",
                   purpose="INV-01 engineering pilot")
    E.prepare_disposable_db(dsn, ROOT / "migrations")
    calibration_specs = [(CALIBRATION_WORLD, "I"),
                         (CALIBRATION_WORLD, "R")]
    comparison_specs = [(w, arm) for w in COMPARISON_WORLDS
                        for arm in ("I", "R")]
    exports_dir = out / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    repertoires_dir = out / "repertoires"
    repertoires_dir.mkdir(parents=True, exist_ok=True)
    trajectories = []
    for world, arm in calibration_specs + comparison_specs:
        tasks = _arm_tasks(world, arm)
        campaign = _run_trajectory(dsn, world, arm, tasks,
                                   agenda_authorized, budget)
        frozen_path = repertoires_dir / (
            "repertoire-w%d-%s.json" % (world, arm))
        repertoire = trajectory.freeze_repertoire(campaign,
                                                  frozen_path)
        export = records.export_campaign(
            dsn, campaign, model=MODEL, charter=dict(CHARTER),
            caps={"max_boundaries": 6, "diagnostic_queries": 96,
                  "model_calls": 60, "construction_tokens": 2048,
                  "agenda_authorized": agenda_authorized})
        chain = records.verify_byte_chain(export)
        if chain["problems"]:
            print("byte chain failed: %s" % chain["problems"],
                  file=sys.stderr)
            return 2
        records.write_export(
            export, exports_dir / ("export-w%d-%s.json" % (
                world, arm)))
        trajectories.append({"world": world, "arm": arm,
                             "campaign_id": campaign["campaign_id"],
                             "dispositions": [e.get("disposition")
                                              for e in campaign.get(
                                                  "episodes", [])],
                             "model_calls": int(campaign.get(
                                 "model_calls", 0)),
                             "construction_calls": int(campaign.get(
                                 "construction_calls", 0))})
    freeze = {}
    for entry in trajectories:
        path = repertoires_dir / ("repertoire-w%d-%s.json" % (
            entry["world"], entry["arm"]))
        raw = path.read_bytes()
        freeze[path.name] = hashlib.sha256(raw).hexdigest()
    (out / "freeze.json").write_text(json.dumps(
        {"repertoires": freeze,
         "policy": {"model": MODEL,
                    "packet_version": sheet["derivation"][
                        "packet_version"]}},
        sort_keys=True, indent=1) + "\n")
    use_records: list = []
    for world, arm in comparison_specs:
        repertoire_path = repertoires_dir / (
            "repertoire-w%d-%s.json" % (world, arm))
        repertoire = trajectory.load_repertoire(repertoire_path)
        cid = trajectory.campaign_id(world, arm, 0)
        tasks = _use_tasks(world)
        records_batch = _fresh_use(
            repertoire_path, world, arm, tasks, dsn,
            trajectory._alloc_id(cid))
        chain = records.verify_byte_chain(
            records.load_export(exports_dir / (
                "export-w%d-%s.json" % (world, arm))),
            use_records=records_batch)
        if chain["problems"]:
            print("use byte chain failed: %s" % chain["problems"],
                  file=sys.stderr)
            return 2
        use_records.extend(records_batch)
    (out / "use_records.json").write_text(json.dumps(
        use_records, sort_keys=True, indent=1, default=str) + "\n")
    empty_path = repertoires_dir / "empty.json"
    empty_path.write_text(json.dumps(
        {"campaign_id": "inv01-study-empty", "members": [],
         "queries": 0}) + "\n")
    empty_tasks = _use_tasks(COMPARISON_WORLDS[0])
    empty_cid = trajectory.campaign_id(COMPARISON_WORLDS[0], "I", 0)
    empty_records = _fresh_use(
        empty_path, COMPARISON_WORLDS[0], "I", empty_tasks, dsn,
        trajectory._alloc_id(empty_cid))
    (out / "empty_use_records.json").write_text(json.dumps(
        empty_records, sort_keys=True, indent=1, default=str) + "\n")
    totals = {"model_calls": 0, "construction_calls": 0,
              "witness_queries": 0}
    for world, arm in calibration_specs + comparison_specs:
        export = records.load_export(exports_dir / (
            "export-w%d-%s.json" % (world, arm)))
        recomputed = records.recompute_accounting(export, [])
        totals["model_calls"] += int(recomputed["acquisition"][
            "model_calls"])
        totals["construction_calls"] += int(recomputed["acquisition"][
            "construction_calls"])
        totals["witness_queries"] += int(recomputed["acquisition"][
            "witness_queries"])
    use_queries = sum(int(r.get("costs", {}).get(
        "witness_queries", 0) or 0) for r in use_records)
    totals["witness_queries"] += use_queries
    totals["use_records"] = len(use_records)
    if totals["model_calls"] > 360 or totals[
            "construction_calls"] > 24:
        print("study exceeded aggregate caps: %s" % totals,
              file=sys.stderr)
        return 2
    accounting = {"total": totals, "trajectories": trajectories,
                  "measured_from": "durable operation identities"
                  " plus receipt usage; doubles billed false"}
    (out / "accounting.json").write_text(json.dumps(
        accounting, sort_keys=True, indent=1) + "\n")
    manifest = {"pilot": {"calibration_trajectories": 2,
                          "comparison_trajectories": 4,
                          "worlds": list(COMPARISON_WORLDS),
                          "protected_use_records": len(use_records)},
                "trajectories": trajectories,
                "freeze": freeze,
                "caps_digest": hashlib.sha256(json.dumps(
                    sheet, sort_keys=True).encode()).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(
        manifest, sort_keys=True, indent=1) + "\n")
    disposition = {}
    for entry in trajectories:
        for disposition_name in entry["dispositions"]:
            disposition[disposition_name] = disposition.get(
                disposition_name, 0) + 1
    (out / "disposition.json").write_text(json.dumps(
        {"per_trajectory": trajectories,
         "totals": disposition}, sort_keys=True, indent=1) + "\n")
    return 0


def recompute_study(out: Path, recomputed_out: Path) -> int:
    from experiments.ad01 import records
    exports_dir = out / "exports"
    use_records = json.loads((out / "use_records.json").read_text())
    totals = {"model_calls": 0, "construction_calls": 0,
              "witness_queries": 0}
    loaded_exports = []
    for path in sorted(exports_dir.glob("export-*.json")):
        export = records.load_export(path)
        loaded_exports.append(export)
        recomputed = records.recompute_accounting(export, [])
        totals["model_calls"] += int(recomputed["acquisition"][
            "model_calls"])
        totals["construction_calls"] += int(recomputed[
            "acquisition"]["construction_calls"])
        totals["witness_queries"] += int(recomputed["acquisition"][
            "witness_queries"])
    gate = getattr(records, "verify_study", None)
    if gate is not None:
        verdict = gate(
            loaded_exports, use_records,
            expected={
                "campaign_ids": [e.get("campaign_id")
                                 for e in loaded_exports],
                "use_record_ids": [r.get("record_id")
                                   for r in use_records]})
        if verdict.get("status") != "pass":
            print("study verify failed: %s" % verdict.get(
                "problems"), file=sys.stderr)
            return 2
    use_queries = sum(int(r.get("costs", {}).get(
        "witness_queries", 0) or 0) for r in use_records)
    totals["witness_queries"] += use_queries
    totals["use_records"] = len(use_records)
    accounting = json.loads((out / "accounting.json").read_text())
    if totals["model_calls"] != int(accounting["total"][
            "model_calls"]) or totals["construction_calls"] != int(
            accounting["total"]["construction_calls"]):
        print("recompute mismatch: %s vs %s" % (
            totals, accounting["total"]), file=sys.stderr)
        return 2
    recomputed_out.write_text(json.dumps(
        {"total": totals}, sort_keys=True, indent=1) + "\n")
    return 0


def _v1_effort(explicit: str) -> str:
    if explicit in ("low", "medium", "high"):
        return explicit
    return __import__("experiments.ad01.trajectory", fromlist=["reasoning_effort"]).reasoning_effort()


def _v1_effective_config(provider: str, model: str, effort: str,
                         deadline_s: int) -> dict:
    from experiments.ad01 import method_exec
    from settlement.exec_profile import STOP_SETTLE_S
    return {"provider": provider, "model": model,
            "reasoning_effort": effort,
            "learner": {"max_output_tokens": 2048,
                        "deadline_ms": 300_000},
            "construction": {"max_output_tokens": 2048,
                             "deadline_ms": 300_000},
            "sandbox": {"timeout_ms": method_exec.DEFAULT_TIMEOUT_MS,
                        "max_output_bytes": 1048576,
                        "profile": "local-process",
                        "settle_s": STOP_SETTLE_S},
            "gateway": {"api": "responses" if provider == "live" else "recording-double",
                        "endpoint_env": "SETTLEMENT_GATEWAY_ENDPOINT"},
            "deadline_s": int(deadline_s)}


def _v1_panel() -> dict:
    from experiments.ad01 import checker, trajectory, worlds
    return {"freeze_id": worlds.FREEZE_ID,
            "freeze_digest": checker.freeze_digest(worlds.FROZEN_DIR),
            "calibration_world": CALIBRATION_WORLD,
            "comparison_worlds": list(COMPARISON_WORLDS)}


def _v1_sheet(effective: dict) -> dict:
    sheet = build_cap_sheet()
    per = dict(sheet["per_trajectory"])
    study = dict(sheet["study"])
    study["max_witness_queries"] = 960
    study["max_execution_units"] = 5328
    study["deadline_s"] = int(effective["deadline_s"])
    derivation = dict(sheet["derivation"])
    derivation["effective_config"] = dict(effective)
    derivation["study_witness_queries"] = "6 trajectories times 96 diagnostic plus 24 use times 16"
    derivation["study_execution_units"] = "48 sandbox exposures times (30s plus 80 settle plus 1)"
    derivation["wall_deadline"] = "persisted wall_deadline_at enforced before each effect with remaining propagated"
    return {"per_trajectory": per, "study": study,
            "derivation": derivation,
            "accounting_kinds": list(sheet["accounting_kinds"]),
            "kinds_note": dict(sheet["kinds_note"])}


def _v1_load_run(dsn: str, study_root: str) -> dict | None:
    from psycopg.rows import dict_row
    from settlement import db
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("SELECT * FROM inv_r1_study_runs WHERE study_root = %s",
                            (study_root,))
                row = cur.fetchone()
            except Exception:
                conn.rollback()
                return None
            conn.commit()
    return dict(row) if row is not None else None


def _v1_remaining_ms(row: dict) -> int:
    import datetime
    deadline = row["wall_deadline_at"]
    if isinstance(deadline, str):
        deadline = datetime.datetime.fromisoformat(deadline)
    now = datetime.datetime.now(datetime.timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=datetime.timezone.utc)
    return int((deadline - now).total_seconds() * 1000)


def _v1_ensure_run(dsn: str, study_root: str, authorized: int,
                   deadline_s: int, effective: dict, panel: dict,
                   ceilings: dict) -> dict:
    from settlement import authority, db
    existing = _v1_load_run(dsn, study_root)
    if existing is not None:
        if int(existing["authorized"]) != int(authorized):
            raise ValueError("grant change refused for %s" % study_root)
        if int(existing["deadline_s"]) != int(deadline_s):
            raise ValueError("deadline change refused for %s" % study_root)
        if dict(existing["effective_config"] or {}) != dict(effective):
            raise ValueError("effective config change refused for %s" % study_root)
        return existing
    handle = authority.authorize_study(
        dsn, study_root, authorized=int(authorized),
        allocation_id=study_root,
        ceilings=dict(ceilings),
        correction_budget=2)
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    wall = now + datetime.timedelta(seconds=int(deadline_s))
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO inv_r1_study_runs (study_root, allocation_id,"
                " authorized, ceilings, model, reasoning_effort, provider,"
                " effective_config, panel, deadline_s, started_at,"
                " wall_deadline_at) VALUES (%s, %s, %s, %s, %s, %s, %s,"
                " %s, %s, %s, %s, %s)",
                (study_root, handle.allocation_id, int(authorized),
                 json.dumps(dict(ceilings)),
                 str(effective.get("model", "")),
                 str(effective.get("reasoning_effort", "low")),
                 str(effective.get("provider", "recording")),
                 json.dumps(dict(effective)), json.dumps(dict(panel)),
                 int(deadline_s), now.isoformat(), wall.isoformat()))
        conn.commit()
    created = _v1_load_run(dsn, study_root)
    if created is None:
        raise RuntimeError("study run row missing after create")
    return created


def _v1_counts(dsn: str, study_root: str) -> dict:
    from psycopg.rows import dict_row
    from settlement import authority, db
    try:
        handle = authority.bind_study(dsn, study_root)
    except Exception:
        return {"model_calls": 0, "construction_calls": 0,
                "witness_queries": 0, "execution_units": 0,
                "operations": 0}
    alloc = handle.allocation_id
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "WITH RECURSIVE study_allocs (id) AS ("
                " SELECT id FROM allocations WHERE id = %s"
                " UNION SELECT a.id FROM allocations a"
                " JOIN study_allocs s ON a.parent_id = s.id)"
                " SELECT o.id, o.payload FROM operations o"
                " WHERE o.allocation_id IN (SELECT id FROM study_allocs)",
                (alloc,))
            ops = cur.fetchall()
            conn.commit()
    model_calls = sum(1 for r in ops if dict(
        r["payload"] or {}).get("effect") == "model-inference")
    sandbox_ops = sum(1 for r in ops if dict(
        r["payload"] or {}).get("effect") == "sandbox-exec")
    construction_calls = sum(1 for r in ops if "-construct-" in str(r["id"])
                             and dict(r["payload"] or {}).get(
                                 "effect") == "model-inference")
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    "WITH RECURSIVE study_allocs (id) AS ("
                    " SELECT id FROM allocations WHERE id = %s"
                    " UNION SELECT a.id FROM allocations a"
                    " JOIN study_allocs s ON a.parent_id = s.id)"
                    " SELECT COALESCE(SUM((r.content->'usage'->>'charge_units')::int), 0) AS c"
                    " FROM receipts r JOIN operations o ON o.id = r.operation_id"
                    " WHERE o.allocation_id IN (SELECT id FROM study_allocs)"
                    " AND r.outcome IN ('success','failure')",
                    (alloc,))
                _ = cur.fetchone()
            except Exception:
                pass
            conn.commit()
    return {"model_calls": int(model_calls),
            "construction_calls": int(construction_calls),
            "witness_queries": 0, "execution_units": int(sandbox_ops),
            "operations": len(ops)}


def _v1_admit(dsn: str, row: dict, need: dict,
              allocation_id: str | None = None) -> dict:
    if _v1_remaining_ms(row) <= 0:
        return {"ok": False, "reason": "study deadline exceeded"}
    counts = _v1_counts(dsn, row["study_root"])
    limits = {"model_calls": 360, "construction_calls": 24,
              "witness_queries": 960, "execution_units": 5328}
    consumed = {"model_calls": max(counts["model_calls"], int(
                    row.get("consumed_model_calls", 0) or 0)),
                "construction_calls": max(counts["construction_calls"], int(
                    row.get("consumed_construction_calls", 0) or 0)),
                "witness_queries": int(row.get(
                    "consumed_witness_queries", 0) or 0),
                "execution_units": max(counts["execution_units"], int(
                    row.get("consumed_execution_units", 0) or 0))}
    for key in ("model_calls", "construction_calls",
                "witness_queries", "execution_units"):
        want = int(need.get(key, 0))
        if consumed.get(key, 0) + want > limits[key]:
            return {"ok": False,
                    "reason": "study cap exceeded for %s" % key}
    from settlement import store
    try:
        free = store.allocation_free(
            dsn, allocation_id or row["allocation_id"])
    except Exception as exc:
        return {"ok": False, "reason": "missing-authority: %s" % exc}
    if free <= 0:
        return {"ok": False, "reason": "insufficient-authority"}
    return {"ok": True, "reason": ""}


def _v1_update_counts(dsn: str, study_root: str) -> None:
    from settlement import db
    counts = _v1_counts(dsn, study_root)
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE inv_r1_study_runs SET consumed_model_calls = %s,"
                " consumed_construction_calls = %s,"
                " consumed_execution_units = %s, updated_at = now()"
                " WHERE study_root = %s",
                (counts["model_calls"], counts["construction_calls"],
                 counts["execution_units"], study_root))
        conn.commit()


class _GuardGateway:
    def __init__(self, dsn: str, study_root: str, inner):
        self._dsn = dsn
        self._study_root = study_root
        self._inner = inner
        self.calls: list = []

    def check_discovery(self):
        return self._inner.check_discovery()

    def check_auth(self):
        return self._inner.check_auth()

    def cancel(self, operation_id: str) -> bool:
        return self._inner.cancel(operation_id)

    def infer(self, request):
        from settlement.gateway import GatewayError, GatewayErrorKind
        row = _v1_load_run(self._dsn, self._study_root)
        if row is None:
            return GatewayError(GatewayErrorKind.TRANSPORT,
                                "missing study run", False,
                                request.operation_id)
        if _v1_remaining_ms(row) <= 0:
            return GatewayError(GatewayErrorKind.TIMEOUT,
                                "study deadline exceeded", False,
                                request.operation_id)
        counts = _v1_counts(self._dsn, self._study_root)
        if counts["model_calls"] >= 360:
            return GatewayError(GatewayErrorKind.RATE_LIMIT,
                                "study cap exceeded for model_calls",
                                False, request.operation_id)
        if "-construct-" in str(request.operation_id) and counts[
                "construction_calls"] >= 24:
            return GatewayError(GatewayErrorKind.RATE_LIMIT,
                                "study cap exceeded for construction_calls",
                                False, request.operation_id)
        remaining = _v1_remaining_ms(row)
        if int(getattr(request, "deadline_ms", 300_000)) > remaining:
            return GatewayError(GatewayErrorKind.TIMEOUT,
                                "total attempt deadline exceeded", True,
                                request.operation_id)
        self.calls.append(request)
        return self._inner.infer(request)


def _v1_select_provider(provider: str, model: str, learner_scripts: list):
    if provider == "live":
        from settlement.config import Settings
        from settlement.gateway_http import HttpGatewayAdapter
        settings = Settings.from_env()
        if not settings.gateway.endpoint:
            raise ValueError("live provider needs SETTLEMENT_GATEWAY_ENDPOINT")
        import os as _os
        if not _os.environ.get(settings.gateway.api_key_env, ""):
            raise ValueError("live provider needs %s" % (
                settings.gateway.api_key_env,))
        if not model or model == MODEL:
            raise ValueError("live provider needs an explicit --model")
        return HttpGatewayAdapter.from_settings(settings, api="responses")
    from experiments import doubles as D
    return D.InvCQualificationDouble(learner_scripts=list(learner_scripts))


def _v1_ensure_campaign_alloc(dsn: str, study_root: str, cid: str,
                              authorized: int) -> str:
    from settlement import authority, store
    from settlement.common import Command, ResultCode
    handle = authority.bind_study(dsn, study_root)
    child = "ad01-campaign-%s" % cid
    from settlement import db
    from psycopg.rows import dict_row
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT authorized FROM allocations WHERE id = %s",
                        (child,))
            found = cur.fetchone()
            conn.commit()
    if found is not None:
        return child
    result = store.subdivide_allocation(
        dsn, Command(request_id="inv-r1-subdivide-%s" % child,
                     payload={"parent_id": handle.allocation_id,
                              "child_id": child, "authorized": int(authorized),
                              "domain": "study"}))
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise RuntimeError("study subdivision refused: %s" % result.detail)
    return child


def _v1_run_one(dsn: str, world: int, arm: str, tasks: list,
                study_root: str, gateway, model: str,
                max_boundaries: int, study_authorized: int) -> dict:
    from experiments.ad01 import learner, trajectory
    cid = trajectory.campaign_id(world, arm, 0)
    _v1_ensure_campaign_alloc(dsn, study_root, cid, 100000)
    seed = trajectory.ensure_campaign(
        dsn, cid, world, arm, dict(CHARTER),
        {"max_boundaries": int(max_boundaries), "diagnostic_queries": 96,
         "model_calls": 60, "construction_tokens": 2048,
         "agenda_authorized": int(study_authorized)}, tasks=list(tasks),
        study_root=study_root)
    propose = learner.propose_from_model(
        dsn, cid=cid, gateway=gateway, model=model,
        charter=dict(CHARTER), world=world, arm=arm,
        allocation_id=seed["allocation_id"])
    return trajectory.run_campaign(
        world, arm, dict(CHARTER),
        {"max_boundaries": int(max_boundaries), "diagnostic_queries": 96,
         "model_calls": 60, "construction_tokens": 2048,
         "agenda_authorized": int(study_authorized)}, tasks=list(tasks),
        propose=propose, campaign_seq=0, dsn=dsn,
        gateway=gateway, model=model, constructor="model",
        study_root=study_root)


def run_study_v1(dsn: str, out: Path, authorized: int, *,
                 study_root: str, provider: str, model: str, effort: str,
                 deadline_s: int, prepare_disposable: bool,
                 max_trajectories: int, max_boundaries: int) -> int:
    from settlement import db
    if "inv_r1_" not in dsn:
        print("study refuses non-disposable dsn", file=sys.stderr)
        return 2
    if provider not in ("recording", "live"):
        print("study needs explicit --provider recording|live",
              file=sys.stderr)
        return 2
    if not model:
        print("study needs explicit --model", file=sys.stderr)
        return 2
    if provider == "live" and model == MODEL:
        print("live provider needs an explicit --model", file=sys.stderr)
        return 2
    if provider == "live":
        from settlement.config import Settings
        import os as _os
        try:
            settings = Settings.from_env()
        except Exception as exc:
            print("live provider misconfigured: %s" % exc,
                  file=sys.stderr)
            return 2
        if not settings.gateway.endpoint:
            print("live provider needs SETTLEMENT_GATEWAY_ENDPOINT",
                  file=sys.stderr)
            return 2
        if not _os.environ.get(settings.gateway.api_key_env, ""):
            print("live provider needs %s" % settings.gateway.api_key_env,
                  file=sys.stderr)
            return 2
    out.mkdir(parents=True, exist_ok=True)
    if prepare_disposable:
        print("refusing to clear database on the study path;"
              " use explicit test setup", file=sys.stderr)
        return 2
    db.apply_migrations(dsn, ROOT / "migrations")
    effort_resolved = _v1_effort(effort)
    if effort:
        os.environ["AD01_REASONING_EFFORT"] = effort_resolved
    effective = _v1_effective_config(provider, model, effort_resolved,
                                     deadline_s)
    panel = _v1_panel()
    sheet = _v1_sheet(effective)
    checked = check_caps_against_runner(sheet)
    if checked["problems"]:
        print("cap sheet drift: %s" % checked["problems"],
              file=sys.stderr)
        return 2
    (out / "cap_sheet.json").write_text(json.dumps(
        sheet, sort_keys=True, indent=1) + "\n")
    ceilings = {"max_model_calls": 360, "max_construction_calls": 24,
                "max_boundaries": 36, "max_witness_queries": 960,
                "max_execution_units": 5328}
    try:
        row = _v1_ensure_run(dsn, study_root, int(authorized),
                             int(deadline_s), effective, panel, ceilings)
    except ValueError as exc:
        print("study refused: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:
        print("study refused: %s" % exc, file=sys.stderr)
        return 2
    if _v1_remaining_ms(row) <= 0:
        print("study deadline exceeded", file=sys.stderr)
        return 2
    gate = _v1_admit(dsn, row, {"model_calls": 1})
    if not gate["ok"] and "deadline" not in gate["reason"] and \
            "insufficient-authority" not in gate["reason"]:
        pass
    full = not max_trajectories or int(max_trajectories) >= 6
    if full:
        specs = [(CALIBRATION_WORLD, "I"), (CALIBRATION_WORLD, "R")] + [
            (w, arm) for w in COMPARISON_WORLDS for arm in ("I", "R")]
    else:
        specs = [(CALIBRATION_WORLD, "I")][:int(max_trajectories)]
    exports_dir = out / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    repertoires_dir = out / "repertoires"
    repertoires_dir.mkdir(parents=True, exist_ok=True)
    trajectories = []
    for world, arm in specs:
        tasks = _arm_tasks(world, arm)[:int(max_boundaries)]
        need = {"model_calls": 60, "construction_calls": 4,
                "boundaries": len(tasks), "witness_queries": 96,
                "execution_units": 111}
        fresh = _v1_load_run(dsn, study_root)
        gate = _v1_admit(dsn, fresh, need)
        if not gate["ok"]:
            print("study refuses trajectory w%d-%s: %s" % (
                world, arm, gate["reason"]), file=sys.stderr)
            return 2
        scripts = _scripts_for(tasks)
        try:
            inner = _v1_select_provider(provider, model, scripts)
        except ValueError as exc:
            print("study refused: %s" % exc, file=sys.stderr)
            return 2
        gateway = _GuardGateway(dsn, study_root, inner)
        from experiments.ad01 import records, trajectory
        campaign = _v1_run_one(dsn, world, arm, tasks, study_root,
                               gateway, model, max_boundaries,
                               int(authorized))
        _v1_update_counts(dsn, study_root)
        from settlement import db as _db
        with _db.connect(dsn) as _conn:
            with _conn.cursor() as _cur:
                _cur.execute(
                    "UPDATE inv_r1_study_runs SET consumed_witness_queries ="
                    " consumed_witness_queries + %s, updated_at = now()"
                    " WHERE study_root = %s",
                    (int(campaign.get("queries", 0) or 0), study_root))
            _conn.commit()
        frozen_path = repertoires_dir / (
            "repertoire-w%d-%s.json" % (world, arm))
        trajectory.freeze_repertoire(campaign, frozen_path)
        export = records.export_campaign(
            dsn, campaign, model=model, charter=dict(CHARTER),
            caps={"max_boundaries": int(max_boundaries),
                  "diagnostic_queries": 96, "model_calls": 60,
                  "construction_tokens": 2048,
                  "agenda_authorized": int(authorized)})
        chain = records.verify_byte_chain(export)
        if chain["problems"]:
            print("byte chain failed: %s" % chain["problems"],
                  file=sys.stderr)
            return 2
        records.write_export(
            export, exports_dir / ("export-w%d-%s.json" % (world, arm)))
        trajectories.append({"world": world, "arm": arm,
                             "campaign_id": campaign["campaign_id"],
                             "model_calls": int(campaign.get(
                                 "model_calls", 0)),
                             "construction_calls": int(campaign.get(
                                 "construction_calls", 0))})
    freeze = {}
    for entry in trajectories:
        path = repertoires_dir / ("repertoire-w%d-%s.json" % (
            entry["world"], entry["arm"]))
        raw = path.read_bytes()
        freeze[path.name] = hashlib.sha256(raw).hexdigest()
    (out / "freeze.json").write_text(json.dumps(
        {"repertoires": freeze,
         "policy": {"model": model,
                    "packet_version": sheet["derivation"][
                        "packet_version"]}},
        sort_keys=True, indent=1) + "\n")
    use_records: list = []
    if full:
        from experiments.ad01 import records, trajectory
        for world, arm in [(w, a) for w in COMPARISON_WORLDS
                           for a in ("I", "R")]:
            repertoire_path = repertoires_dir / (
                "repertoire-w%d-%s.json" % (world, arm))
            cid = trajectory.campaign_id(world, arm, 0)
            tasks = _use_tasks(world)
            fresh = _v1_load_run(dsn, study_root)
            gate = _v1_admit(dsn, fresh, {"model_calls": 0,
                                          "construction_calls": 0,
                                          "boundaries": 0,
                                          "witness_queries": len(tasks) * 16,
                                          "execution_units": len(tasks) * 111},
                             allocation_id="ad01-campaign-%s" % cid)
            if not gate["ok"]:
                print("study refuses use w%d-%s: %s" % (
                    world, arm, gate["reason"]), file=sys.stderr)
                return 2
            child = "ad01-campaign-%s" % cid
            records_batch = _fresh_use(
                repertoire_path, world, arm, tasks, dsn, child)
            use_records.extend(records_batch)
            _v1_update_counts(dsn, study_root)
        (out / "use_records.json").write_text(json.dumps(
            use_records, sort_keys=True, indent=1, default=str) + "\n")
    else:
        (out / "use_records.json").write_text("[]\n")
    totals = {"model_calls": 0, "construction_calls": 0,
              "witness_queries": 0}
    if full:
        from experiments.ad01 import records
        loaded_exports = []
        for world, arm in specs:
            export = records.load_export(exports_dir / (
                "export-w%d-%s.json" % (world, arm)))
            loaded_exports.append(export)
            recomputed = records.recompute_accounting(export, [])
            totals["model_calls"] += int(recomputed["acquisition"][
                "model_calls"])
            totals["construction_calls"] += int(recomputed["acquisition"][
                "construction_calls"])
            totals["witness_queries"] += int(recomputed["acquisition"][
                "witness_queries"])
        use_queries = sum(int(r.get("costs", {}).get(
            "witness_queries", 0) or 0) for r in use_records)
        totals["witness_queries"] += use_queries
        gate = getattr(records, "verify_study", None)
        if gate is not None:
            verdict = gate(
                loaded_exports, use_records,
                expected={
                    "campaign_ids": [e.get("campaign_id")
                                     for e in loaded_exports],
                    "use_record_ids": [r.get("record_id")
                                       for r in use_records]})
            if verdict.get("status") != "pass":
                print("study verify failed: %s" % verdict.get(
                    "problems"), file=sys.stderr)
                return 2
    else:
        counts = _v1_counts(dsn, study_root)
        totals = {"model_calls": counts["model_calls"],
                  "construction_calls": counts["construction_calls"],
                  "witness_queries": counts["witness_queries"]}
    totals["use_records"] = len(use_records)
    if totals["model_calls"] > 360 or totals[
            "construction_calls"] > 24:
        print("study exceeded aggregate caps: %s" % totals,
              file=sys.stderr)
        return 2
    (out / "accounting.json").write_text(json.dumps(
        {"total": totals, "trajectories": trajectories,
         "measured_from": "durable operation identities plus receipt usage;"
                          " recording doubles billed false;"
                          " live billed from provider usage"},
        sort_keys=True, indent=1) + "\n")
    final_row = _v1_load_run(dsn, study_root)
    study_doc = {"study_root": study_root, "provider": provider,
                 "model": model,
                 "reasoning_effort": effort_resolved,
                 "effective_config": effective, "panel": panel,
                 "grant": int(authorized),
                 "allocation_id": final_row["allocation_id"] if final_row else study_root,
                 "deadline_s": int(deadline_s),
                 "wall_deadline_at": str(final_row["wall_deadline_at"]) if final_row else "",
                 "started_at": str(final_row["started_at"]) if final_row else "",
                 "caps": sheet["study"],
                 "per_trajectory_caps": sheet["per_trajectory"],
                 "accounting_kinds": sheet["accounting_kinds"],
                 "trajectories": trajectories,
                 "freeze": freeze}
    (out / "study.json").write_text(json.dumps(
        study_doc, sort_keys=True, indent=1, default=str) + "\n")
    manifest = {"pilot": {"calibration_trajectories": 2 if full else 0,
                          "comparison_trajectories": 4 if full else len(
                              trajectories),
                          "worlds": list(COMPARISON_WORLDS) if full else [],
                          "protected_use_records": len(use_records)},
                "trajectories": trajectories, "freeze": freeze,
                "study_root": study_root, "provider": provider,
                "model": model,
                "caps_digest": hashlib.sha256(json.dumps(
                    sheet, sort_keys=True).encode()).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(
        manifest, sort_keys=True, indent=1) + "\n")
    return 0


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="inv01-study")
    parser.add_argument("--dsn", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--agenda-authorized", type=int, default=0)
    parser.add_argument("--deadline-s", type=int, default=3600)
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument("--recomputed-out", default="")
    parser.add_argument("--study-root", default="")
    parser.add_argument("--provider", default="",
                        choices=["", "recording", "live"])
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="")
    parser.add_argument("--prepare-disposable", action="store_true")
    parser.add_argument("--max-trajectories", type=int, default=0)
    parser.add_argument("--max-boundaries", type=int, default=6)
    args = parser.parse_args(argv)
    if args.recompute:
        if not args.out or not args.recomputed_out:
            parser.error("--recompute needs --out and --recomputed-out")
        return recompute_study(Path(args.out),
                               Path(args.recomputed_out))
    if not args.dsn or not args.out:
        parser.error("study needs --dsn and --out")
    if not args.agenda_authorized or args.agenda_authorized <= 0:
        parser.error("study needs positive --agenda-authorized")
    if args.study_root or "inv_r1_" in args.dsn or args.provider:
        return run_study_v1(
            args.dsn, Path(args.out), args.agenda_authorized,
            study_root=args.study_root or "inv01-study",
            provider=args.provider or "recording",
            model=args.model or MODEL,
            effort=args.reasoning_effort or "",
            deadline_s=args.deadline_s,
            prepare_disposable=args.prepare_disposable,
            max_trajectories=int(args.max_trajectories or 0),
            max_boundaries=int(args.max_boundaries or 6))
    return run_study(args.dsn, Path(args.out),
                     args.agenda_authorized,
                     deadline_s=args.deadline_s)


if __name__ == "__main__":
    raise SystemExit(main())
