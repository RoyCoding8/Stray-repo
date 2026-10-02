"""E1 at full panel: a model-acquired arm against the authored control, live.

The r3 run in `reports/evidence/invl02_liveacq_r3/` reached a real result on
two of six tasks and two of its own defects kept it from reporting it. Both
are fixed there and carried in; a third was found while checking, by
`scripts/ad01_r4_dryrun_verdict.py`, and is fixed in `s09_verdict`. This run
exists to answer the question r3 could not: does the two-of-five result
hold on the whole panel, and is the control distinct from a real policy more
or less widely than one task in two.

**Retries are zero, and the wall clock is the budget.**
`LiveGuard.automatic_retries` defaults to `MAX_RETRIES = 3`, so one task can
burn four times the read timeout. At 240s that is sixteen minutes for a
single task, and r3 lost one arm to exactly that. The ceiling below is the
send count, and a repair is a second send on the same slot, so it is twice
the task count.

**The panel is the study's, and both arms run all of it.**
`control_distinct` pairs on the intersection of the two arms' task ids and
refuses when the symmetric difference is non-empty. The control runs
`control_tasks(world)` -- six per world, eighteen in all -- and the acquired
arms each ran one task in r3, so `unpaired_tasks` was 16 and the gate could
not have returned `distinct: True` however the two arms behaved. An arm
acquired for one task cannot answer another, so the panel is the six
acquisition tasks and the control runs those six, over all three worlds.

**Headroom is derived, not typed.** Two runs lost their last world to a
fallback at an exactly-sized ceiling, and the arm that loses is the one the
loop reaches last. `ceilings()` below sums what each phase can actually draw
and adds a full campaign's margin on top.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

TOKEN_RE = "r4cmp"

# One software and one graph task per world, drawn from the study's own use
# tasks so the control and the acquired arm run the same ids and the pairing
# is by construction rather than by a second list that could drift. Six
# tasks, six campaigns, six construction slots -- one campaign per task is
# what keeps every task inside the two-per-campaign lineage cap.
ACQUISITION_TASKS = ["ad01-w0-within-sw-00", "ad01-w0-within-gr-00",
                     "ad01-w1-within-sw-00", "ad01-w1-within-gr-00",
                     "ad01-w2-within-sw-00", "ad01-w2-within-gr-00"]

# Past 60s, which is both the adapter's read default and the router's
# upstream header timeout. Measured on this route at 44-112s per
# construction call, and 98s in a probe this morning.
READ_TIMEOUT_MS = 240_000
TOTAL_TIMEOUT_MS = READ_TIMEOUT_MS + 60_000

# Six tasks, one construction call each on the init attempt, one repair slot
# each. Two sends per task, no retries.
DISPATCH_CEILING = len(ACQUISITION_TASKS) * 2

STUDY_DEADLINE_S = 3600


def _arms_run() -> int:
    """The children this run subdivides, counted three ways.

    One child per acquisition campaign, one for the control's use phase, and
    one per acquired arm's own use phase. `use_acquired_arms` calls
    `study_child` per arm, so the use phases are six more subdivisions and
    not a share of the control's.

    Under-counting by the use phases is not a small shortfall. `_v1_study_units`
    is the sheet's allowance times `n + 2`, so it leaves the last
    subdivisions with a free balance of zero and `subdivide_allocation`
    refuses them with `parent ... has 0 free`. A use phase that never ran is
    not a fallback the gate can read: it contributes no record at all, so the
    comparison pairs on whichever tasks were reached first.
    """
    return len(ACQUISITION_TASKS) * 2 + 1


def study_units() -> int:
    """The study's own authority, derived from the children it creates."""
    from scripts import inv01_study as study
    return study._v1_study_units(_arms_run())


def ceilings() -> dict:
    """Ceilings derived from what each phase draws, with a margin.

    The study's own `_v1_ceilings` is sized for six acquisition campaigns
    plus three use arms over eighteen tasks each, which is a different
    shape from this run: six single-task use phases rather than three
    eighteen-task arms. Deriving from the study's functions would size for
    work this run does not do.

    What each phase actually spends, per the store's own counters:
      - one model-inference construction call per task, plus at most one
        repair, so `max_model_calls` is the ceiling and
        `max_construction_calls` matches it.
      - one sandbox-exec validate per acquisition and one per use record.
        `_sandbox_exposure` is `timeout_ms // 1000 + STOP_SETTLE_S + 1` and
        `DEFAULT_TIMEOUT_MS` is 30000, so 30 + 80 + 1 = 111 units each --
        which is where the study's own per-task figure of 111 comes from.
      - the control runs six tasks and each acquired arm one, so 6 + 6 + 6
        sandbox execs on the use side.

    The margin is one extra acquisition campaign's worth, because a ceiling
    sized at exactly the sum is a race between phases for the last unit and
    the phase that loses is whichever the loop reaches last.
    """
    from settlement import exec_profile
    from experiments.ad01 import construct, method_exec

    per_exec = (method_exec.DEFAULT_TIMEOUT_MS // 1000
                + exec_profile.STOP_SETTLE_S + 1)
    acquisitions = len(ACQUISITION_TASKS)
    acquired_arms = acquisitions
    control_tasks = acquisitions
    validate_execs = acquisitions
    use_execs = acquired_arms + control_tasks
    margin = acquisitions * per_exec

    model_calls = DISPATCH_CEILING
    return {
        "max_model_calls": model_calls * 2,
        "max_construction_calls": model_calls,
        "max_execution_units": (validate_execs + use_execs) * per_exec
        + margin,
        "max_witness_queries": 0,
    }


def ceiling_derivation() -> dict:
    """The arithmetic behind `ceilings()`, written beside the numbers.

    `authorize_study` refuses a ceiling name it does not recognise, so this
    cannot ride inside the ceilings dict; it is the reader's answer to "why
    these numbers" and it is written into the evidence rather than left in
    a function body.
    """
    from settlement import exec_profile
    from experiments.ad01 import construct, method_exec

    per_exec = (method_exec.DEFAULT_TIMEOUT_MS // 1000
                + exec_profile.STOP_SETTLE_S + 1)
    return {
        "per_sandbox_exec_units": per_exec,
        "timeout_ms": method_exec.DEFAULT_TIMEOUT_MS,
        "stop_settle_s": exec_profile.STOP_SETTLE_S,
        "validation_execs": len(ACQUISITION_TASKS),
        "use_execs": 2 * len(ACQUISITION_TASKS),
        "margin_execs": len(ACQUISITION_TASKS),
        "dispatch_ceiling": DISPATCH_CEILING,
        "construction_call_ceiling": construct.CONSTRUCTION_CALL_CEILING,
        "note": "one model call per task plus one repair slot per task, and"
                " retries are zero, so the ceiling is twice the task count",
    }


def _load_live_environment() -> None:
    """The documented variables, from the file, without printing any of them."""
    for line in Path("/home/ubuntu/.config/agent-society-live.env").read_text(
            encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
    os.environ["SETTLEMENT_GATEWAY_TIMEOUT_READ_MS"] = str(READ_TIMEOUT_MS)
    os.environ["SETTLEMENT_GATEWAY_TIMEOUT_TOTAL_MS"] = str(TOTAL_TIMEOUT_MS)


def _campaign_id(index: int, task_id: str) -> str:
    """One campaign per task, named so the lineage cap cannot cross tasks."""
    return "r4acq-t%d-%s" % (index, task_id)


def acquire(dsn: str, study_root: str, model: str, route: dict) -> tuple:
    """The model-acquired arm: one campaign per task, live, with evidence.

    Every refusal is recorded rather than raised. A task whose construction
    timed out is a lost response, and a panel that silently drops its hardest
    task is the defect this whole thread is about.

    `route` is the pinned route the guard holds every dispatch to. Passing
    `None` turns that check off, which is only for
    `scripts/ad01_r4_rehearse.py`: a recording double cannot attest the four
    route fields, so a rehearsal that kept the check would measure nothing
    but the refusal.
    """
    from experiments.ad01 import live_construct
    from experiments.ad01 import trajectory, worlds
    from scripts import inv01_study as study

    gateway = study._v1_select_provider("live", model, [], route=route)
    guard = live_construct.LiveGuard(
        gateway, pinned_model=model, ceiling=DISPATCH_CEILING,
        expected_route=route, automatic_retries=0)
    arms: list = []
    for index, task_id in enumerate(ACQUISITION_TASKS):
        cid = _campaign_id(index, task_id)
        arm = "arm_%s%s" % (study._family(task_id)[:2], "%02d" % index)
        row: dict = {"arm": arm, "task_id": task_id,
                     "family": study._family(task_id),
                     "campaign_id": cid, "acquired": False}
        started = time.monotonic()
        try:
            study._v1_ensure_campaign_alloc(
                dsn, study_root, cid, study._v1_campaign_units())
            trajectory.ensure_campaign(
                dsn, cid, index, "I", dict(study.CHARTER),
                {"max_boundaries": 1, "diagnostic_queries": 16,
                 "model_calls": 60, "construction_tokens": 2048,
                 "agenda_authorized": study_units()},
                tasks=[task_id], study_root=study_root)
            member = live_construct.construct_live_method(
                dsn, campaign_id=cid,
                task=worlds.load_task(worlds.FROZEN_DIR, task_id),
                experience={"observations": [], "retained": [],
                            "remaining": {"queries": 16, "steps": 12,
                                          "model_calls": 60}},
                budget={"max_output_tokens": 2048,
                        "deadline_ms": READ_TIMEOUT_MS,
                        "max_queries": 4, "model_calls": 4},
                gateway=guard, model=model, study_root=study_root)
        except Exception as exc:
            row["reason"] = str(exc)[:600]
            row["stage"] = live_construct.diagnose_construction(
                exc, guard.spent_dispatches).get("stage")
            row["elapsed_s"] = round(time.monotonic() - started, 1)
            arms.append(row)
            print("ACQUIRE_REFUSED arm=%s task=%s reason=%s"
                  % (arm, task_id, row["reason"][:200]), flush=True)
            continue
        source = str(member.get("method_source") or "")
        evidence = dict(member.get("acquisition_evidence") or {})
        row.update({
            "acquired": True,
            "capability_id": member.get("capability_id"),
            "entry": member.get("entry"),
            "policy_source": source,
            "source_digest": hashlib.sha256(
                source.encode("utf-8")).hexdigest(),
            "origin": member.get("origin"),
            "evidence": evidence,
            "elapsed_s": round(time.monotonic() - started, 1),
        })
        arms.append(row)
        print("ACQUIRED arm=%s task=%s id=%s earned=%s elapsed=%ss"
              % (arm, task_id, member.get("capability_id"),
                 evidence.get("earned"), row["elapsed_s"]), flush=True)
    return arms, guard.guard_status()


def run_control_use(dsn: str, study_root: str, out: Path) -> list:
    """The authored control arm, on the acquisition panel, at the same budget.

    `experiments.ad01.control_use` is the study's own entry point for an arm
    outside the `("I", "R")` vocabulary, in a fresh process, which is what
    makes the member bytes the bytes that run. The selector is measured in
    the host by `control_arm.measured_tables`, so building it spends no
    dispatch.
    """
    from experiments.ad01 import control_arm
    repertoire = control_arm.control_repertoire("ad01-ctl")
    tables = control_arm.measured_tables(repertoire)
    source = control_arm.selector_source(
        repertoire, features=tables["shape"], coarse=tables["template"])
    if not source:
        raise RuntimeError("control arm built no selector source")
    out.mkdir(parents=True, exist_ok=True)
    (out / "repertoire-C.json").write_text(
        json.dumps(repertoire, sort_keys=True, indent=1) + "\n",
        encoding="utf-8")
    (out / "control-C-use-policy.py").write_text(source, encoding="utf-8")
    child = study_child(dsn, study_root, "C")
    records: list = []
    for world in (0, 1, 2):
        tasks = [task_id for task_id in ACQUISITION_TASKS
                 if _world_of(task_id) == world]
        if not tasks:
            continue
        command = [sys.executable, "-m", "experiments.ad01.control_use",
                   "--repertoire", str(out / "repertoire-C.json"),
                   "--world", str(world), "--arm", "C",
                   "--tasks", ",".join(tasks), "--dsn", dsn,
                   "--allocation-id", child,
                   "--policy-source", str(out / "control-C-use-policy.py")]
        proc = subprocess.run(command, cwd=str(ROOT), capture_output=True,
                              text=True, timeout=900)
        if proc.returncode != 0:
            raise RuntimeError("control use w%d failed: %s"
                               % (world, proc.stderr[-1500:]))
        for record in json.loads(proc.stdout):
            record["study_arm"] = "C"
            records.append(record)
        print("CONTROL_USE world=%d records=%d"
              % (world, len(json.loads(proc.stdout))), flush=True)
    (out / "use_records_control.json").write_text(
        json.dumps(records, sort_keys=True, indent=1, default=str) + "\n",
        encoding="utf-8")
    return records


def use_acquired(dsn: str, arm: dict, allocation: str, scratch: Path) -> list:
    """The acquired arm's own use phase, on the task it acquired for.

    A policy can only be used where it was acquired, so the repertoire is the
    one this arm produced and it holds one member. The selector is generated
    from that repertoire rather than shared, because a selector built from a
    software-only repertoire refuses a graph task outright, which would
    report a missing family as a missing policy. The member id is
    `acquired-<fam>-<digest8>`, which is not in `seeds.SEED_CAPABILITIES`, so
    the bytes are staged and run rather than short-circuited to the host's
    dispatch table.
    """
    repertoire = {"campaign_id": arm["campaign_id"],
                  "members": [{"capability_id": arm["capability_id"],
                               "entry": arm["entry"],
                               "authored": False,
                               "origin": "model-acquired",
                               "method_source": arm["policy_source"],
                               "source_digest": arm["source_digest"],
                               "scope": {"family": arm["family"]}}],
                  "queries": 0}
    path = scratch / ("repertoire-%s.json" % arm["arm"])
    path.write_text(json.dumps(repertoire, sort_keys=True, indent=1) + "\n",
                    encoding="utf-8")
    from scripts import inv01_study as study
    policy = study._v1_use_policy_fallback([
        {"capability_id": arm["capability_id"], "family": arm["family"]}])
    if not policy:
        raise RuntimeError("no selector for the single-member repertoire %r"
                           % arm["arm"])
    policy_path = scratch / ("single-member-policy-%s.py" % arm["arm"])
    policy_path.write_text(policy, encoding="utf-8")
    arm["use_policy_source_digest"] = hashlib.sha256(
        policy.encode("utf-8")).hexdigest()
    command = [sys.executable, "-m", "experiments.ad01.control_use",
               "--repertoire", str(path), "--world",
               str(_world_of(arm["task_id"])),
               "--arm", arm["arm"], "--tasks", arm["task_id"],
               "--dsn", dsn, "--allocation-id", allocation,
               "--policy-source", str(policy_path)]
    proc = subprocess.run(command, cwd=str(ROOT), capture_output=True,
                          text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError("acquired use failed: %s" % proc.stderr[-1500:])
    return [dict(r, study_arm=arm["arm"]) for r in json.loads(proc.stdout)]


def use_acquired_arms(dsn: str, study_root: str, arms: list,
                      scratch: Path) -> list:
    """The acquired arms' use records, one per arm that earned a member.

    An arm whose acquisition did not earn a member contributes no record
    rather than a refusal record. A refusal would be read by
    `control_distinct` as a fallback, and a fallback names no executed
    policy, which is a different claim from "this task was never acquired".
    """
    from scripts import inv01_study as study
    scratch.mkdir(parents=True, exist_ok=True)
    records: list = []
    for arm in arms:
        if not arm.get("acquired"):
            continue
        try:
            records.extend(use_acquired(
                dsn, arm, study_child(dsn, study_root, arm["arm"]), scratch))
        except Exception as exc:
            arm["use_error"] = str(exc)[:400]
            print("ACQUIRED_USE_FAILED arm=%s error=%s"
                  % (arm["arm"], str(exc)[:200]), flush=True)
    del study
    return records


def gate_split(gate: dict) -> dict:
    """The counts a reader needs to see where a refusal comes from.

    `control_distinct` returns one boolean and up to nine named lists. A
    refusal that does not say which list fired is a refusal a reader has to
    re-derive, so the split is written beside the verdict.
    """
    verdict = gate.get("verdict") or {}
    if not isinstance(verdict, dict):
        return {"raised": bool(gate.get("raised")),
                "refusal": gate.get("refusal", "")}
    return {name: len(value) for name, value in sorted(verdict.items())
            if isinstance(value, list)}


def write_verdict_bundle(dsn: str, study_root: str, arms: list,
                         control: list, acquired: list, out: Path,
                         model: str, route: dict) -> dict:
    """The bundle `s09_verdict` reads, assembled from the store.

    The origin in the freeze is written only for an arm whose evidence reads
    `earned: true`, and that evidence is the one the acquisition recorded.
    `Bundle.earned_origin` re-derives the origin from the construction
    record rather than trusting the freeze, so a wrong label is caught
    rather than believed -- but a missing one is not, and an arm that cannot
    show a receipt should not carry the label at all.

    The control's construction entry is written too. The verdict layer reads
    `construction[arm].bound_digest` first, and `member_digests` off the
    freeze identity; the r3 bundle had neither for `C`, so the leg fell back
    to the concatenation digest and refused all eighteen control records.
    """
    from experiments.ad01 import control_arm, s09_verdict

    identities: dict = {}
    construction: dict = {}
    for arm in arms:
        if not arm.get("acquired"):
            continue
        evidence = dict(arm.get("evidence") or {})
        bound = arm["source_digest"]
        construction[arm["arm"]] = {
            "arm": arm["arm"], "task_id": arm["task_id"],
            "family": arm["family"], "campaign_id": arm["campaign_id"],
            "policy_source": arm["policy_source"],
            "candidate_digest": bound, "bound_digest": bound,
            "source_digest": bound,
            "acquisition_evidence": evidence,
            "construction_requests": [{
                "effect": "model-inference", "model": model,
                "operation_id": _construct_operation_id(arm)}],
        }
        if evidence.get("earned") is True:
            identities.update(control_arm.acquisition_identity(
                arm["arm"], [arm["capability_id"]],
                {arm["capability_id"]: bound},
                acquisition_evidence=evidence))

    repertoire = control_arm.control_repertoire("ad01-ctl")
    tables = control_arm.measured_tables(repertoire)
    identities.update(control_arm.policy_identities("C", repertoire))
    control_rows = [r for r in control if r.get("study_arm") == "C"]
    if control_rows:
        construction["C"] = {
            "arm": "C", "origin": "authored-control",
            "policy_source": repertoire["members"][0]["method_source"],
            "acquisition_evidence": None,
            "construction_requests": [],
            "executed_member_digests": sorted({
                hashlib.sha256(str(r.get("executed_source") or "").encode(
                    "utf-8")).hexdigest()
                for r in control_rows
                if isinstance(r.get("executed_source"), str)
                and r.get("executed_source") not in (None, "", "incumbent")}),
        }

    freeze = {
        "config": {"model": model},
        "route": route,
        "metric_rule": {"quality": "normalized_reduction"},
        "policy_identities": identities,
        "study_root": study_root,
        "selector_tables_measured": bool(tables["shape"]),
    }
    (out / "freeze.json").write_text(
        json.dumps(freeze, sort_keys=True, indent=1, default=str) + "\n",
        encoding="utf-8")
    (out / "construction.json").write_text(
        json.dumps(construction, sort_keys=True, indent=1, default=str) + "\n",
        encoding="utf-8")
    operations = read_operations(dsn, study_root)
    (out / "operations.json").write_text(
        json.dumps(operations, sort_keys=True, indent=1, default=str) + "\n",
        encoding="utf-8")
    (out / "use_records.json").write_text(
        json.dumps(control + acquired, sort_keys=True, indent=1,
                   default=str) + "\n", encoding="utf-8")
    (out / "assessment.json").write_text(
        json.dumps({"records": len(control) + len(acquired)}, sort_keys=True,
                   indent=1) + "\n", encoding="utf-8")

    bundle = s09_verdict.Bundle(
        root=out, freeze=freeze, construction=construction,
        operations=operations, use_records=tuple(control + acquired),
        accounting={}, assessment=())
    acquisition = s09_verdict.live_acquisition_verdict(bundle)
    utility = s09_verdict.task_utility_verdict(bundle)
    verdicts = {"live_acquisition": acquisition.value,
                "task_utility": utility.value,
                "live_acquisition_legs": [
                    {"name": leg.name, "status": leg.status,
                     "evidence": leg.evidence} for leg in acquisition.legs],
                "task_utility_legs": [
                    {"name": leg.name, "status": leg.status,
                     "evidence": leg.evidence} for leg in utility.legs],
                "task_utility_basis": utility.basis.detail,
                "acquisition_basis": acquisition.basis.detail}
    (out / "verdicts.json").write_text(
        json.dumps(verdicts, sort_keys=True, indent=1, default=str) + "\n",
        encoding="utf-8")
    (out / "verdict.txt").write_text(
        "live_acquisition verdict: %s\n\n"
        "task_utility verdict: %s\n\n%s"
        % (acquisition.value, utility.value,
           "\n".join("  %-42s %s\n      %s"
                     % (leg.name, leg.status, leg.evidence)
                     for leg in list(acquisition.legs) + list(utility.legs))),
        encoding="utf-8")
    return {"bundle": bundle, "verdicts": verdicts}


def _construct_operation_id(arm: dict) -> str:
    """The construction operation id this arm's bytes came from."""
    return "ad01-%s-b0-%s-construct-l1-init" % (arm["campaign_id"],
                                                arm["task_id"])


def read_operations(dsn: str, study_root: str) -> dict:
    """Every operation under the study's allocation, with its receipts.

    `_dispatch_leg` requires a receipt for each construction request, so the
    bundle has to carry the operations rather than a count of them. Only
    `outcome`, `receipt_identity` and the `usage` block are exported; the
    response text is not, because the evidence that a provider answered is
    the receipt's own metadata and not its payload.
    """
    from psycopg.rows import dict_row
    from settlement import authority, db
    handle = authority.bind_study(dsn, study_root)
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "WITH RECURSIVE kids (id) AS ("
                " SELECT id FROM allocations WHERE id = %s"
                " UNION SELECT a.id FROM allocations a"
                " JOIN kids k ON a.parent_id = k.id)"
                " SELECT o.id, o.payload, o.settled, r.receipt_identity,"
                " r.outcome, r.content FROM operations o"
                " LEFT JOIN receipts r ON r.operation_id = o.id"
                " WHERE o.allocation_id IN (SELECT id FROM kids)"
                " ORDER BY o.id, r.receipt_identity",
                (handle.allocation_id,))
            rows = cur.fetchall()
        conn.commit()
    out: dict = {}
    for row in rows:
        entry = out.setdefault(row["id"], {
            "operation_id": row["id"],
            "effect": (row["payload"] or {}).get("effect"),
            "settled": bool(row["settled"]),
            "receipts": []})
        if row["receipt_identity"] is None:
            continue
        content = dict(row["content"] or {})
        entry["receipts"].append({
            "receipt_identity": row["receipt_identity"],
            "outcome": row["outcome"],
            "usage": content.get("usage"),
            "model_meta_present": bool(content.get("model_meta")),
        })
    return out


def _world_of(task_id: str) -> int:
    """The world a frozen task id belongs to, read off the id itself.

    A frozen id is `ad01-w<N>-<split>-<family>-<nn>`, so the world is the
    token after `w`. A positional index over `-`-separated tokens reads
    `ad01-w0-within-...` as the split and raises.
    """
    for token in task_id.split("-"):
        if len(token) > 1 and token[0] == "w" and token[1:].isdigit():
            return int(token[1:])
    raise ValueError("task id %r names no world" % task_id)


def study_child(dsn: str, study_root: str, name: str) -> str:
    """One arm's own allocation, subdivided from the study's.

    It has to be its own subdivision rather than the study's remainder: the
    six acquisition campaigns are children too, and `free_of` counts a
    parent's children against the parent's balance, so the control would
    arrive to nothing and every one of its records would fall back to
    `incumbent`. A fallback names no policy, and `control_distinct` reads
    that as a refusal rather than a result.
    """
    from scripts import inv01_study as study
    child = "r4-control-%s" % name
    study._v1_ensure_alloc(dsn, study_root, child, study._v1_campaign_units())
    return child


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = Path(argv[0]) if argv else (
        ROOT / "reports" / "evidence" / "invl02_liveacq_r4")
    if out.exists():
        print("refusing to write over an existing %s" % out, file=sys.stderr)
        return 2
    _load_live_environment()

    from experiments.ad01 import control_arm_result as result
    from experiments.ad01 import s09_run_isolation as isolation
    from scripts import inv01_study as study

    model = os.environ.get("INVL02_LIVE_MODEL", "").strip()
    if not model:
        print("refusing: INVL02_LIVE_MODEL names no model")
        return 2
    route = study._v1_route_from_env(model)
    print("ROUTE_OK requested=%s provider=%s tier=%s read_ms=%d"
          % (route["requested_model"], route["provider"], route["tier"],
             READ_TIMEOUT_MS), flush=True)
    print("CEILINGS=%s" % json.dumps(ceilings(), sort_keys=True), flush=True)

    admin = isolation.admin_dsn()
    token = "%s%s" % (TOKEN_RE, uuid.uuid4().hex[:8])
    database = isolation.create_disposable_db(token, admin_dsn=admin)
    print("DISPOSABLE_DB=%s" % database.name, flush=True)
    study_root = isolation.study_root_for(token)
    dsn = database.dsn
    scratch = ROOT / ".ad01-r4-runs" / token
    try:
        study._v1_ensure_run(
            dsn, study_root, study_units(),
            STUDY_DEADLINE_S,
            study._v1_effective_config("live", model, "", STUDY_DEADLINE_S),
            study._v1_panel(), ceilings())

        arms, guard_status = acquire(dsn, study_root, model, route)
        out.mkdir(parents=True)
        (out / "acquired_arms.json").write_text(
            json.dumps({"arms": arms, "guard": guard_status},
                       sort_keys=True, indent=1, default=str) + "\n",
            encoding="utf-8")
        print("GUARD=%s" % json.dumps(guard_status, sort_keys=True,
                                      default=str), flush=True)

        control = run_control_use(dsn, study_root, scratch)
        acquired_use = use_acquired_arms(dsn, study_root, arms, scratch)

        gate = result.gate_control_distinct(control, acquired_use)
        paired = result.per_task(result.arm_rows(control),
                                 result.arm_rows(acquired_use))
        rows = result.utility(paired)
        (out / "control_distinct.json").write_text(
            json.dumps(gate, sort_keys=True, indent=1, default=str) + "\n",
            encoding="utf-8")
        (out / "arms.json").write_text(json.dumps(
            {"control": result.arm_rows(control),
             "acquired": result.arm_rows(acquired_use),
             "per_task": paired}, sort_keys=True, indent=1,
            default=str) + "\n", encoding="utf-8")
        (out / "use_records.json").write_text(
            json.dumps(control + acquired_use, sort_keys=True, indent=1,
                       default=str) + "\n", encoding="utf-8")

        bundle_out = write_verdict_bundle(dsn, study_root, arms, control,
                                          acquired_use, out, model, route)
        verdicts = bundle_out["verdicts"]
        print("VERDICT live_acquisition=%s task_utility=%s"
              % (verdicts["live_acquisition"], verdicts["task_utility"]),
              flush=True)

        write_cost(dsn, study_root, guard_status, out)
        summary = {
            "acquired_arms": len(arms),
            "acquired": sum(1 for a in arms if a["acquired"]),
            "earned": sum(1 for a in arms
                          if (a.get("evidence") or {}).get("earned") is True),
            "panel": ACQUISITION_TASKS,
            "control_records": len(control),
            "acquired_use_records": len(acquired_use),
            "control_distinct": gate.get("distinct"),
            "control_distinct_refusal": gate.get("refusal", ""),
            "gate_split": gate_split(gate),
            "utility": rows["value"],
            "mean_acquired_minus_control": rows[
                "mean_acquired_minus_control"],
            "per_task_deltas": rows["per_task_deltas"],
            "verdicts": verdicts,
            "guard": guard_status,
            "ceilings": ceilings(),
            "ceiling_derivation": ceiling_derivation(),
            "arms": [{"arm": a["arm"], "task_id": a["task_id"],
                      "acquired": a["acquired"],
                      "capability_id": a.get("capability_id"),
                      "earned": (a.get("evidence") or {}).get("earned"),
                      "elapsed_s": a.get("elapsed_s"),
                      "reason": a.get("reason"),
                      "use_error": a.get("use_error")} for a in arms],
        }
        (out / "summary.json").write_text(
            json.dumps(summary, sort_keys=True, indent=1, default=str) + "\n",
            encoding="utf-8")
        return 0
    finally:
        isolation.drop_disposable_db(database, admin_dsn=admin)
        print("DROPPED=%s" % database.name, flush=True)


def write_cost(dsn: str, study_root: str, guard_status: dict,
               out: Path) -> dict:
    """The run's spend, in all four currencies, measured not asserted.

    The four are separate and none is derived from another: the dispatch
    allowance the guard spent, the internal reservation authority the study
    was granted and what is left of it, the provider's billing, and the
    units still held.

    Provider billing is read from the gateway receipts, not from a
    reason string. `cost_currencies` labels it NOT_REPORTED with the reason
    "recording doubles bill false; the run made no provider call to bill",
    which is a true statement about a double and a false one about a live
    run. A settled receipt that reports token counts and a null charge is
    UNMEASURED: the tokens are known and the charge is not, which is not
    zero. A dispatch that produced no settled response is UNCERTAIN, because
    the provider may or may not have answered and billed.

    The reservation figures are this run's, not `cost_currencies`'s. That
    function reports `_v1_study_units(_v1_campaign_count(6))`, which is the
    study's own shape of six campaigns plus two extra arms. This run
    subdivides a different number of children, so reading the study's
    number here reported 1673728 against a grant of 3138240 -- a fifth of
    the authority, and an authority a reader would take at face value.
    """
    from experiments.ad01 import control_arm_result as result
    from scripts import inv01_study as study
    from settlement import authority, store

    measured = result.cost_currencies(dsn=dsn, study_root=study_root)
    operations = read_operations(dsn, study_root)
    settled_success = []
    lost = []
    tokens_in = tokens_out = 0
    for operation_id, entry in sorted(operations.items()):
        for receipt in entry["receipts"]:
            if receipt["outcome"] != "success":
                lost.append(operation_id)
                continue
            if entry["effect"] != "model-inference":
                continue
            usage = dict(receipt.get("usage") or {})
            if usage.get("input_tokens") is None:
                lost.append(operation_id)
                continue
            settled_success.append(operation_id)
            tokens_in += int(usage["input_tokens"])
            tokens_out += int(usage["output_tokens"])

    handle = authority.bind_study(dsn, study_root)
    authorized = study_units()
    cost = {
        "dispatch_allowance": {
            "status": "REPORTED",
            "guard_ceiling": guard_status.get("ceiling"),
            "guard_spent_dispatches": guard_status.get("spent_dispatch_count"),
            "refunded_pre_gateway": guard_status.get(
                "refunded_dispatch_count"),
            "note": "a lost response is still a send; the guard counts it and"
                    " so does this",
        },
        "reservation_allowance": {
            "status": "REPORTED",
            "study_units_authorized": authorized,
            "campaign_units": study._v1_campaign_units(),
            "children_subdivided": _arms_run(),
            "authorized_derivation": study._v1_study_units(_arms_run()),
            "source": "s09_cap_sheet unit allowance times (_arms_run() +"
                      " _v1_use_arms() - 1). _arms_run() is the count of"
                      " children this run creates: one campaign and one use"
                      " phase per acquisition, and one for the control.",
            "cost_currencies_reports": measured["reservation_allowance"][
                "study_units_authorized"],
            "cost_currencies_note":
                "cost_currencies sizes the study's own shape of six campaigns"
                " plus two extra arms, which is not the shape this run"
                " subdivides; its number is carried beside this one rather"
                " than in place of it",
        },
        "internal_held_units": {
            "status": "REPORTED",
            "free_units": int(store.allocation_free(dsn, handle.allocation_id)),
            "note": "free = authorized minus consumed minus children's"
                    " authorization",
        },
        "provider_billing": {
            "status": "UNMEASURED" if settled_success else "NOT_REPORTED",
            "settled_success_receipts": len(settled_success),
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "billed_reported_null": len(settled_success),
            "note": "every settled gateway receipt carries billed=null and"
                    " charge_units=null, so the token counts are known and the"
                    " charge is not. This is not zero.",
        },
        "lost_responses": {
            "status": "UNCERTAIN" if lost else "REPORTED",
            "count": len(lost),
            "operation_ids": sorted(set(lost)),
            "note": "receipts with no success and no token usage; the"
                    " provider may or may not have answered and billed.",
        },
    }
    cost["supersedes"] = (
        "cost_currencies reports provider_billing as NOT_REPORTED with the"
        " recording-double reason, which is the wrong label for a live run."
        " The four measured numbers are here.")
    (out / "cost.json").write_text(
        json.dumps(cost, sort_keys=True, indent=1, default=str) + "\n",
        encoding="utf-8")
    return cost


if __name__ == "__main__":
    raise SystemExit(main())
