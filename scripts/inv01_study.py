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

DISPOSIBLE_PREFIXES = ("s09iso_", "inv_r1_", "inv_c3_")

# The authored control arm's own name, and the witness budget both arms run
# at. `_v1_use_arms` is what the ceilings and the use loop read; clearing
# CONTROL_ARM returns the study to its pre-control shape without deleting
# any of it, which is the point of a switch over a deletion.
CONTROL_ARM = "C"
CONTROL_BUDGET = 4

# The two orderings the use loop walks before any control exists. The
# ceiling has to count them: sizing the use half on one ordering is what
# left the third run's control arm with nothing to spend.
ACQUIRED_ARMS = ("I", "R")


def _v1_use_arms() -> int:
    """How many arms the use phase runs in total.

    The two acquired orderings, plus the control when there is one. This is
    the number the ceiling is sized on and the number the authority is
    widened by, and both had to learn the same lesson: the control arm is
    the third, not the second.
    """
    return len(ACQUIRED_ARMS) + (1 if CONTROL_ARM else 0)


def _disposable_store(dsn: str) -> bool:
    """Accept a store a test could have created and no operator named.

    The guard used to be a single substring, so it admitted exactly the names
    a caller could not derive. The run token that `s09_run_isolation` mints is
    matched by `TOKEN_RE`, which admits no underscore, so a name carrying both
    `inv_r1_` and the library's own `s09iso_` prefix is unreachable and the
    study could only run against whatever a human had left behind. Both
    callers now admit the disposable library's names alongside the ones they
    used to, and the study still refuses every store it cannot attribute to a
    test.
    """
    from urllib.parse import urlparse

    parsed = urlparse(dsn)
    if parsed.scheme:
        name = (parsed.path or "/").lstrip("/")
    else:
        name = ""
        for field in dsn.split():
            if field.startswith("dbname="):
                name = field[7:].strip("'\"")
    return any(name.startswith(prefix) for prefix in DISPOSIBLE_PREFIXES)


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


def _v1_write_use_policy(repertoire_path: Path, task: dict) -> str:
    """Materialise the use-phase policy for a repertoire, or nothing.

    The use CLI compiles its policy as a STEP callable and refuses a phase
    without one. The repertoire holds `ENTRY` methods, which are not that, so
    the selector is built from the repertoire's own capability ids. A study
    that acquired a real use policy will pass it in instead; this is the
    path that makes the phase runnable at all, and the record says which it
    was.
    """
    from experiments.ad01 import trajectory
    repertoire = trajectory.load_repertoire(repertoire_path)
    eligible = [{"capability_id": m.get("capability_id"),
                 "family": (m.get("scope") or {}).get("family")}
                for m in (repertoire.get("members") or [])
                if m.get("capability_id")]
    source = _v1_use_policy_fallback(eligible)
    if not source:
        return ""
    out = repertoire_path.with_name(repertoire_path.stem + "-use-policy.py")
    out.write_text(source, encoding="utf-8")
    return str(out)


def _v1_control_arm(repertoires_dir: Path) -> dict:
    """Write the authored control arm's repertoire and its selector.

    One repertoire, not one per world. The control is authored rather than
    acquired, so it is not scoped to a campaign and has nothing that would
    make it world-specific; a world-scoped control would be four copies of
    the same bytes and would make the freeze's repertoire digests say
    something false about how many artifacts the study ran.

    The selector is measured here, in the host, at study-build time. That
    costs no dispatch and is not charged to the arm's budget, which is why
    the arm's own executions are the only ones its admission gate sees.
    """
    from experiments.ad01 import control_arm
    repertoire = control_arm.control_repertoire(
        "ad01-%s" % control_arm.ID_PREFIX.rstrip("-"))
    tables = control_arm.measured_tables(repertoire)
    source = control_arm.selector_source(
        repertoire, features=tables["shape"], coarse=tables["template"])
    if not source:
        raise RuntimeError("control arm built no selector source")
    path = repertoires_dir / ("repertoire-%s.json" % CONTROL_ARM)
    path.write_text(json.dumps(repertoire, sort_keys=True, indent=1) + "\n",
                    encoding="utf-8")
    selector = repertoires_dir / ("control-%s-use-policy.py" % CONTROL_ARM)
    selector.write_text(source, encoding="utf-8")
    return {"repertoire": path, "policy": selector,
            "repertoire_doc": repertoire, "source": source,
            "tables": tables}


def _fresh_use(repertoire_path: Path, world: int, arm: str,
               tasks: list, dsn: str, allocation_id: str,
               policy_path: str | Path | None = None,
               timeout_s: int = 600) -> list:
    command = [sys.executable, "-m", "experiments.ad01.cli", "use",
               "--repertoire", str(repertoire_path), "--world", str(world),
               "--arm", arm, "--tasks", ",".join(tasks),
               "--dsn", dsn, "--allocation-id", allocation_id]
    # A control arm runs through its own entry point rather than the CLI's
    # `use` branch, because that branch refuses an `--arm` outside
    # ("I", "R") at cli.py:238 and the control is neither ordering of a
    # trajectory. Widening the CLI's vocabulary would have said the control
    # is a third rotation of the same campaign, which it is not. The
    # process boundary is kept either way: it is what makes the child's
    # member bytes the bytes that run, and what turns a raising policy into
    # a refusal record instead of an exception out of the study.
    if policy_path:
        command = [sys.executable, "-m", "experiments.ad01.control_use",
                   "--repertoire", str(repertoire_path),
                   "--world", str(world), "--arm", arm,
                   "--tasks", ",".join(tasks), "--dsn", dsn,
                   "--allocation-id", allocation_id,
                   "--policy-source", str(policy_path)]
    else:
        # The acquired arm's path is unchanged: the fallback refuses the
        # two-members-per-family case, which is the acquired arm's own
        # precondition and not the control's.
        policy = _v1_write_use_policy(
            repertoire_path, {"task_id": tasks[0] if tasks else ""})
        if policy:
            command += ["--policy-source", policy]
    proc = subprocess.run(
        command,
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0:
        raise RuntimeError("fresh-process use failed: %s" % (
            proc.stderr[-2000:],))
    return json.loads(proc.stdout)


def run_study(dsn: str, out: Path, agenda_authorized: int,
              deadline_s: int = 3600) -> int:
    from experiments.ad01 import records, trajectory
    if not _disposable_store(dsn):
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


def _v1_ceilings(arms: int = 1) -> dict:
    """The study's resource ceilings, derived from the work it admits.

    These were three separate literals in three places. They sized the
    acquired arm's use phase and the acquisition loop together, and a
    control arm's use phase did not fit inside what was left.

    A ceiling has to cover every phase the study admits, so this sums two
    measured halves and then adds headroom. `_v1_acquisition_budget` is
    what the campaign loop asks `_v1_admit` for; `_v1_use_budget` is what
    every use arm asks for. Both are read from the same `need` dicts the
    loop passes, so a ceiling cannot drift from what is actually
    requested.

    The headroom is not slack for its own sake. Sized at exactly the sum,
    the ceiling was 6660 against 6660 and the run consumed it all on the
    first two phases, so the control's last world fell back on all six
    tasks with `ceiling max_execution_units=6660 reached at 6660`. A
    budget with no headroom is not a bound on the work, it is a race
    between three phases for the last unit, and the phase that loses is
    whichever the loop reaches last. One extra acquisition campaign's worth
    is enough to cover a single task overspending on any phase.

    Two sizing mistakes came before this one and neither arithmetic caught
    in advance: the first covered only the use phase and refused the
    second campaign, the second covered two arms when the loop walks three.
    Both are now covered by tests, and the third by this margin.

    `max_model_calls` and `max_construction_calls` are the aggregate caps
    the end-of-run totals check compares against, and a control arm adds no
    model call and no construction call, so those are unchanged.
    """
    acquisition = _v1_acquisition_budget()
    use = _v1_use_budget(arms)
    margin = acquisition["execution_units"]
    return {
        "max_model_calls": 360,
        "max_construction_calls": 24,
        "max_boundaries": 36,
        "max_witness_queries": acquisition["witness_queries"]
        + use["witness_queries"] + margin,
        "max_execution_units": acquisition["execution_units"]
        + use["execution_units"] + margin,
    }


def _v1_acquisition_budget(max_trajectories: int = 0) -> dict:
    """What the campaign loop asks for, summed over the campaigns it runs.

    Read from `_v1_specs` and the same per-trajectory `need` the loop
    passes, so this is the number admission will actually see rather than
    a restatement of it.
    """
    tasks = 6
    per = {"witness_queries": 96, "execution_units": 111}
    campaigns = len(_v1_specs(max_trajectories))
    return {"campaigns": campaigns, "tasks_per_campaign": tasks,
            "witness_queries": per["witness_queries"] * campaigns,
            "execution_units": per["execution_units"] * campaigns}


def _v1_use_budget(arms: int = 1) -> dict:
    """What every use arm asks for, summed over arms and worlds.

    The acquired side is not one arm. The use loop walks both orderings,
    `for world in _v1_use_worlds() for a in ("I", "R")`, so the study
    admits six use combinations before the control exists. Sizing the use
    half on one of them left the control nothing: the derived ceiling came
    to exactly 4662, which is 666 acquisition plus 3996 acquired use, and
    the third real run spent all of it on the acquired arm. Every one of
    the control's eighteen records then fell back to `incumbent` with
    `study ceiling max_execution_units=4662 reached`, and
    `control_distinct` read that as `distinct: True` — a false pass, since
    both arms named `incumbent` and an empty executed id is not a
    distinction.

    So the use half counts the arms the loop actually walks: two acquired
    orderings, plus the control. The per-task witness budget is the larger
    of the two arms', so both fit rather than only the cheaper one.
    """
    from experiments.ad01 import control_arm
    per_arm = control_arm.arm_budget(
        _v1_use_worlds(), per_task_queries=max(16, CONTROL_BUDGET))
    return {"arms": int(arms),
            "acquired_orderings": ACQUIRED_ARMS,
            "witness_queries": per_arm["witness_queries"] * int(arms),
            "execution_units": per_arm["execution_units"] * int(arms),
            "tasks_per_arm": per_arm["tasks"]}


def _v1_sheet(effective: dict) -> dict:
    sheet = build_cap_sheet()
    per = dict(sheet["per_trajectory"])
    study = dict(sheet["study"])
    ceilings = _v1_ceilings(_v1_use_arms())
    study["max_witness_queries"] = ceilings["max_witness_queries"]
    study["max_execution_units"] = ceilings["max_execution_units"]
    study["deadline_s"] = int(effective["deadline_s"])
    derivation = dict(sheet["derivation"])
    derivation["effective_config"] = dict(effective)
    acquisition = _v1_acquisition_budget()
    use = _v1_use_budget(_v1_use_arms())
    derivation["study_witness_queries"] = (
        "acquisition %d campaigns times 96 plus use %d tasks per arm times"
        " %d arms times %d witness queries, both derived from the need"
        " dicts the loops admit against"
        % (acquisition["campaigns"], use["tasks_per_arm"], use["arms"],
           max(16, CONTROL_BUDGET)))
    derivation["study_execution_units"] = (
        "acquisition %d campaigns times 111 plus use %d tasks per arm times"
        " %d arms times 111 sandbox units"
        % (acquisition["campaigns"], use["tasks_per_arm"], use["arms"]))
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
    ceilings = _v1_ceilings(_v1_use_arms())
    limits = {"model_calls": ceilings["max_model_calls"],
              "construction_calls": ceilings["max_construction_calls"],
              "witness_queries": ceilings["max_witness_queries"],
              "execution_units": ceilings["max_execution_units"]}
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


ROUTE_ENV = "SETTLEMENT_EXPECTED_ROUTE"


def _v1_expected_route(endpoint: str, requested_model: str,
                       resolved_model: str, provider: str, tier: str) -> dict:
    """The route this study is authorized to spend on, as a contract.

    `HttpGatewayAdapter` refuses every dispatch when no expected route is
    pinned and the mode is not paid, which is the correct default: nothing
    has established the route is free. The study therefore has to state it,
    and a caller that cannot supply every field gets a refusal rather than
    an adapter that will fail on the first operation.
    """
    from settlement.gateway import RouteContract
    return RouteContract(
        endpoint=endpoint, requested_model=requested_model,
        resolved_model=resolved_model, provider=provider, tier=tier
    ).as_dict()


def _v1_route_from_env(model: str) -> dict:
    """Read the pinned route, or refuse.

    A route is a fact about the provider, not something the study can infer
    from the endpoint it was handed: the same URL fronts paid and free
    routes. So the caller states it, this function checks it, and a study
    that cannot name its route never dispatches.
    """
    raw = os.environ.get(ROUTE_ENV, "").strip()
    if not raw:
        raise ValueError(
            "live study needs %s: the endpoint alone does not establish that "
            "the route is free" % ROUTE_ENV)
    import json as _json
    try:
        route = _json.loads(raw)
    except ValueError as exc:
        raise ValueError("%s is not JSON: %s" % (ROUTE_ENV, exc))
    from settlement.gateway import RouteContract
    try:
        contract = RouteContract.from_mapping(route)
    except ValueError as exc:
        raise ValueError("%s: %s" % (ROUTE_ENV, exc))
    # The requested model is what the study asked for and must match. The
    # resolved model is what the provider reports back, and it legitimately
    # differs: the router serves `openrouter/nvidia/nemotron-...` and returns
    # `nvidia/nemotron-...`. Requiring both to equal the study's model refuses
    # every real route, which is what happened here. What must hold is that
    # the resolved field is a real string, because an empty one would make the
    # adapter's response comparison vacuous.
    if contract.requested_model != model:
        raise ValueError(
            "%s pins requested=%r, the study was given %r"
            % (ROUTE_ENV, contract.requested_model, model))
    if not contract.resolved_model.strip():
        raise ValueError("%s pins an empty resolved model" % ROUTE_ENV)
    if contract.tier.lower() != "free":
        raise ValueError(
            "%s pins tier %r and this study is authorized on the free route "
            "only" % (ROUTE_ENV, contract.tier))
    return contract.as_dict()


def _v1_select_provider(provider: str, model: str, learner_scripts: list,
                        *, route: dict | None = None):
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
        # A study that dispatches with no route pinned is refused by the
        # adapter on every operation, so the run spent nothing and exited 0
        # looking like a study. Refuse here, where the reason is visible.
        if route is None:
            raise ValueError(
                "live study needs a pinned route; an unpinned adapter "
                "refuses every dispatch as an unproven free route")
        # `chat`, not `responses`: a frozen route is refused pre-send on the
        # responses surface, which publishes no provider field, and this
        # adapter pins one. Refusing would kill every live dispatch here.
        return HttpGatewayAdapter.from_settings(
            settings, api="chat", expected_route=route)
    from experiments import doubles as D
    return D.InvCQualificationDouble(learner_scripts=list(learner_scripts))


def _v1_ensure_alloc(dsn: str, study_root: str, child: str,
                     authorized: int) -> str:
    """One subdivision of the study's authority, by child name.

    The campaigns and the control arm are all children of the study's own
    allocation, and `free_of` counts a parent's children against the
    parent's balance. So the control cannot spend the study's remainder
    once six campaigns have been carved out of it: the second run refused
    it with `insufficient-authority` after the acquired arm's use phase had
    already run. It gets a subdivision of its own instead, and the study
    is authorized wide enough to hold one per arm it runs.

    `authorized` is the sheet's unit allowance, the same number a campaign
    subdivision takes, so the control is not a cheaper arm than the thing
    it is the control for.
    """
    from settlement import authority, store
    from settlement.common import Command, ResultCode
    handle = authority.bind_study(dsn, study_root)
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


def _v1_ensure_campaign_alloc(dsn: str, study_root: str, cid: str,
                              authorized: int) -> str:
    return _v1_ensure_alloc(dsn, study_root, "ad01-campaign-%s" % cid,
                            authorized)


def _v1_use_policy_prompt(eligible: list, task: dict) -> str:
    """The prompt for the artifact the use phase actually runs.

    The use phase is handed a STEP policy that chooses a `capability_id` out
    of `eligible_methods`. That is not the method itself: the methods are
    `ENTRY` functions the constructor acquired, and asking the model for one
    here would be asking for a second, different artifact under the first
    one's name. The job is selection, so the prompt says so.
    """
    import json as _json
    return "\n".join([
        "Choose which already-built capability answers this task.",
        "Interface: exactly one module-level function STEP(view, state).",
        "The view holds task_content, observations, open_questions,",
        "last_result, eligible_methods, remaining and contract_versions.",
        "Return exactly {\"action\": <action>, \"state\": <object>}.",
        "Admit kind 'use_method' with inputs {\"method_id\": <one id>,",
        "\"max_queries\": <non-negative int>}, target the task id,",
        "evidence_refs a list of strings, and requested_resources a dict of",
        "non-negative integers.",
        "Eligible capabilities: %s." % _json.dumps(list(eligible),
                                                  sort_keys=True),
        "Choose only from that list. A capability outside it is refused.",
        "The word import anywhere in the entry source fails validation,",
        "so use no imports, no dunder access, no IO.",
        "Reply with exactly one JSON object and nothing else, shaped",
        '{"entry": "<complete python source>", "notes": "<sentence>"}.',
        "Task: %s" % _json.dumps({k: task.get(k) for k in
                                  ("task_id", "family")}, sort_keys=True),
    ])


def _v1_use_policy_fallback(eligible: list) -> str:
    """A selector for the case where no model policy is available.

    The choice is a lookup of the task's own family against the families the
    repertoire's members declare, and the table it looks in is written into
    the source below, so the artifact says which member answers which family
    and not merely that the first one did. A task whose family no member
    declares, and a family two members both claim, are both refusals: the
    step ABI turns a raising policy into a refusal record, which is what an
    unanswered task should leave behind. Picking the nearest member instead
    is the substitution this must not do.

    A repertoire that declares no scope at all is a different thing, and one
    with a single member answers for itself; two unscoped members are still
    a choice this cannot make.
    """
    import json as _json
    by_family: dict = {}
    unscoped: list = []
    for entry in eligible:
        if isinstance(entry, dict):
            capability_id = str(entry.get("capability_id") or "")
            family = entry.get("family")
        else:
            capability_id = str(entry or "")
            family = None
        if not capability_id:
            continue
        if isinstance(family, str) and family:
            by_family.setdefault(family, []).append(capability_id)
        else:
            unscoped.append(capability_id)
    if not by_family and len(unscoped) != 1:
        return ""
    return "\n".join([
        "def STEP(view, state):",
        "    by_family = %s" % _json.dumps(
            {f: ids for f, ids in sorted(by_family.items())},
            sort_keys=True),
        "    unscoped = %s" % _json.dumps(sorted(unscoped)),
        "    eligible = list(view.get('eligible_methods') or [])",
        "    family = (view.get('task_content') or {}).get('family')",
        "    if by_family:",
        "        named = by_family.get(family, [])",
        "        if len(named) != 1:",
        "            raise ValueError(",
        "                'no single repertoire member is scoped to %r'"
        " ' among %s' % (family, sorted(by_family)))",
        "        picked = named[0]",
        "        why = ['family=%s' % (family,),",
        "               'scope[%s]=%s' % (picked, family)]",
        "        for other in sorted(by_family):",
        "            if other != family:",
        "                why.append(",
        "                    'not-scoped-to-task[%s]=%s'"
        " % (by_family[other][0], other))",
        "    else:",
        "        picked = unscoped[0]",
        "        why = ['family=%s' % (family,),",
        "               'scope[%s]=unscoped' % (picked,)]",
        "    if picked not in eligible:",
        "        raise ValueError(",
        "            'selected %r is not among the eligible methods'"
        " % (picked,))",
        "    return {'action': {'kind': 'use_method',",
        "                     'target': view['task_content']['task_id'],",
        "                     'inputs': {'method_id': picked,",
        "                                'max_queries': 4},",
        "                     'evidence_refs': why,",
        "                     'requested_resources': {'queries': 4}},",
        "            'state': {'picked': picked, 'why': why}}\n"])


def _v1_use_worlds() -> list:
    """The worlds the use phase runs over, which the study also acquires in.

    A policy can only be used where it was acquired, so this set is a subset
    of the worlds the campaign loop runs. The first completed run acquired in
    the calibration world alone and used only the comparison worlds, which
    made every use find an empty repertoire.
    """
    return sorted(set(COMPARISON_WORLDS) | {CALIBRATION_WORLD})


def _v1_specs(max_trajectories: int) -> list:
    """Which world/arm campaigns this study runs.

    The study's unit authority is sized from this list and the loop walks it,
    so the two cannot disagree. They did once: the authority was bound from a
    single campaign's allowance while the loop ran six, so every campaign
    after the first inherited a free balance of zero.
    """
    if not max_trajectories or int(max_trajectories) >= 6:
        return [(CALIBRATION_WORLD, "I"), (CALIBRATION_WORLD, "R")] + [
            (w, arm) for w in COMPARISON_WORLDS for arm in ("I", "R")]
    return [(CALIBRATION_WORLD, "I")][:int(max_trajectories)]


def _v1_campaign_count(max_trajectories: int) -> int:
    return max(len(_v1_specs(max_trajectories)), 1)


def _v1_study_units(campaigns: int = 1) -> int:
    """The unit authority this study binds, from the cap sheet.

    Each campaign takes a subdivision of the whole sheet allowance, so a
    study running N campaigns needs N of them. The cap sheet's 64 sends is
    the campaign's own total, not the study's, and giving the study exactly
    one of them left every campaign after the first with a free balance of
    zero and refused arm R for insufficient authority. The study's authority
    is therefore one allowance per campaign it will run, which is derived
    from the same sheet rather than typed in.

    A control arm takes a subdivision too, and `free_of` counts every
    child against the parent, so the study needs one more allowance per
    control arm. Without it the control's use phase is refused for
    insufficient authority after the campaigns have been carved out, which
    is what the second run did.
    """
    from experiments.ad01 import s09_cap_sheet
    sheet = s09_cap_sheet.load()
    children = max(int(campaigns), 1) + (_v1_use_arms() - 1)
    return int(sheet.unit_allowance.units) * children


def _v1_campaign_units() -> int:
    """Reservation units one campaign subdivision may hold.

    This was the literal 100000, which no cap sheet or runner constant
    derives. It had to exceed whatever the parent was authorized with, so a
    campaign that provisioned the sheet's real allowance was refused by its
    own child. The value is now the sheet's unit allowance, and a study that
    authorized less than one campaign's worth fails at the study, where the
    reason is visible.
    """
    from experiments.ad01 import s09_cap_sheet
    return int(s09_cap_sheet.load().unit_allowance.units)


def _v1_run_one(dsn: str, world: int, arm: str, tasks: list,
                study_root: str, gateway, model: str,
                max_boundaries: int, study_authorized: int,
                study_units: int | None = None) -> dict:
    from experiments.ad01 import learner, trajectory
    cid = trajectory.campaign_id(world, arm, 0)
    _v1_ensure_campaign_alloc(dsn, study_root, cid, _v1_campaign_units())
    seed = trajectory.ensure_campaign(
        dsn, cid, world, arm, dict(CHARTER),
        {"max_boundaries": int(max_boundaries), "diagnostic_queries": 96,
         "model_calls": 60, "construction_tokens": 2048,
         "agenda_authorized": (study_units if study_units is not None
                               else _v1_study_units(1))}, tasks=list(tasks),
        study_root=study_root)
    propose = learner.propose_from_model(
        dsn, cid=cid, gateway=gateway, model=model,
        charter=dict(CHARTER), world=world, arm=arm,
        allocation_id=seed["allocation_id"])
    return trajectory.run_campaign(
        world, arm, dict(CHARTER),
        {"max_boundaries": int(max_boundaries), "diagnostic_queries": 96,
         "model_calls": 60, "construction_tokens": 2048,
         "agenda_authorized": (study_units if study_units is not None
                               else _v1_study_units(1))}, tasks=list(tasks),
        propose=propose, campaign_seq=0, dsn=dsn,
        gateway=gateway, model=model, constructor="model",
        study_root=study_root)


def run_study_v1(dsn: str, out: Path, authorized: int, *,
                 study_root: str, provider: str, model: str, effort: str,
                 deadline_s: int, prepare_disposable: bool,
                 max_trajectories: int, max_boundaries: int) -> int:
    from settlement import db
    if not _disposable_store(dsn):
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
        try:
            _v1_route_from_env(model)
        except ValueError as exc:
            print("study refused: %s" % exc, file=sys.stderr)
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
    ceilings = _v1_ceilings(_v1_use_arms())
    try:
        # `--agenda-authorized` is a count for the agenda, and it was being
        # passed to `authorize_study` as allocation units, so a study
        # authorized 2 units and every campaign subdivision needed 100000.
        # The study's unit authority is the cap sheet's allowance, which is
        # derived from the real request bounds rather than typed in.
        row = _v1_ensure_run(dsn, study_root,
                             _v1_study_units(_v1_campaign_count(max_trajectories)),
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
    specs = _v1_specs(max_trajectories)
    full = len(specs) > 2
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
            inner = _v1_select_provider(
                provider, model, scripts,
                route=_v1_route_from_env(model)
                if provider == "live" else None)
        except ValueError as exc:
            print("study refused: %s" % exc, file=sys.stderr)
            return 2
        gateway = _GuardGateway(dsn, study_root, inner)
        from experiments.ad01 import records, trajectory
        campaign = _v1_run_one(dsn, world, arm, tasks, study_root,
                               gateway, model, max_boundaries,
                               int(authorized),
                               study_units=_v1_study_units(
                                   _v1_campaign_count(max_trajectories)))
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
    use_records: list = []
    policy_identities: dict = {}
    control = None
    if CONTROL_ARM:
        from experiments.ad01 import control_arm
        control = _v1_control_arm(repertoires_dir)
        raw = control["repertoire"].read_bytes()
        freeze[control["repertoire"].name] = hashlib.sha256(raw).hexdigest()
        policy_identities.update(control_arm.policy_identities(
            CONTROL_ARM, control["repertoire_doc"]))
    if full:
        from experiments.ad01 import control_arm, records, trajectory
        # Acquisition and use must cover the same worlds. The first
        # completed run acquired in the calibration world and used only the
        # comparison worlds, so every repertoire it went to use was empty and
        # all twenty-four use records refused. A policy can only be used
        # where it was acquired.
        for world, arm in [(w, a) for w in _v1_use_worlds()
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
        # The control arm runs over the same worlds, on the same task ids,
        # at the same witness budget. It has no campaign, so its own child
        # allocation is named for the arm rather than for a campaign, and
        # the operation ids it writes are namespaced to it so
        # `records.verify_study`'s duplicate checks cannot see the two arms
        # as one campaign.
        if control is not None:
            child = _v1_ensure_alloc(
                dsn, study_root, "ad01-control-%s" % CONTROL_ARM,
                _v1_campaign_units())
            for world in _v1_use_worlds():
                tasks = control_arm.control_tasks(world)
                fresh = _v1_load_run(dsn, study_root)
                gate = _v1_admit(
                    dsn, fresh,
                    {"model_calls": 0, "construction_calls": 0,
                     "boundaries": 0,
                     "witness_queries": len(tasks) * CONTROL_BUDGET,
                     "execution_units": len(tasks) * 111},
                    allocation_id=child)
                if not gate["ok"]:
                    print("study refuses control use w%d: %s" % (
                        world, gate["reason"]), file=sys.stderr)
                    return 2
                control_records = _fresh_use(
                    control["repertoire"], world, CONTROL_ARM, tasks, dsn,
                    child, policy_path=control["policy"])
                for record in control_records:
                    record["study_arm"] = CONTROL_ARM
                use_records.extend(control_records)
                _v1_update_counts(dsn, study_root)
        (out / "use_records.json").write_text(json.dumps(
            use_records, sort_keys=True, indent=1, default=str) + "\n")
    else:
        (out / "use_records.json").write_text("[]\n")
        if control is not None:
            policy_identities = {}
    if full:
        # The acquired arm's identity is keyed to the bytes its records
        # actually executed, not to a digest of the repertoire file.
        # `_comparability_leg` holds every arm to
        # sha256(record["executed_source"]), so a bound digest that did
        # not come from the executed source would fail the leg for the
        # one arm the study spent its dispatches on.
        from experiments.ad01 import control_arm as _arm
        for name in sorted({str(r.get("arm") or "") for r in use_records}
                           - {CONTROL_ARM, ""}):
            digests = {}
            for record in use_records:
                if str(record.get("arm")) != name:
                    continue
                source = record.get("executed_source")
                if isinstance(source, str) and source \
                        and source != "incumbent":
                    digests[record.get("executed")] = hashlib.sha256(
                        source.encode("utf-8")).hexdigest()
            if digests:
                policy_identities.update(_arm.acquisition_identity(
                    name, sorted(digests), digests))
    (out / "freeze.json").write_text(json.dumps(
        {"repertoires": freeze,
         "policy_identities": policy_identities,
         "policy": {"model": model,
                    "packet_version": sheet["derivation"][
                        "packet_version"]}},
        sort_keys=True, indent=1, default=str) + "\n")
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
