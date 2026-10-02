"""E1 with a model-acquired arm against the authored control, on the live route.

The measurement the whole thread has been clearing toward. Every prior
comparison in this stage put `ACQUIRED_ORDER_SOURCE` on the acquired side, so
`control_distinct` was one constant against two authored controls and
`s09_verdict.task_utility_verdict` demoted the result to `not_comparable`. The
`reports/evidence/invl02_liveacq_r2/` bundle carries two arms a provider
actually wrote, so this runs the study that produces the other half of the
comparison against them and reports the gate whichever way it falls.

Three properties the run holds, each of which cost a dispatch in a prior run.

**One campaign per acquisition.** `construct.construct_method` counts prior
lineages across the whole campaign (`_campaign_operations(dsn, campaign_id)`,
every `ad01-<cid>-construct-l*-init`), so one campaign acquires for at most
`MAX_LINEAGES` tasks and then refuses with `lineage cap reached (2/trajectory)`
having dispatched nothing. Two timeouts in the r2 run ate all four slots that
way. `acquisition_tasks` therefore hands each task its own campaign id, which
is the same thing the study's own per-(world, arm) campaign does, made
explicit.

**The read timeout is raised, tasks are never dropped.** The free-tier
reasoning model runs past 60s on a construction prompt, and 60s is both the
adapter default and the router's upstream header timeout, so the default is a
measurement of the timeout rather than of the model. A task that times out is
recorded as a lost response and the campaign's next task proceeds; it is never
removed from the panel.

**The acquired arm's identity is derived from the store.** The verdict layer
reads `origin: model-acquired` only when the arm's own construction record
carries `acquisition_evidence.earned is true`, and that evidence is
`live_construct.read_acquisition_evidence` over the operation's committed
prompt and its settled success receipt. This driver reads it back out of the
store after the run and writes the freeze from it, so an arm that cannot show
a receipt cannot reach the freeze as a model's.

Run: python -m scripts.ad01_r3_compare <out-dir>
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

TOKEN_RE = "r3cmp"

# The acquisition panel. One software and one graph task per world, taken
# from the study's own use tasks so the acquired arm and the control run the
# same task ids and the comparison is paired by construction rather than by a
# second list that could drift. Six tasks, six campaigns, six acquisition
# slots -- which is what keeps every task inside the lineage cap.
ACQUISITION_TASKS = ["ad01-w0-within-sw-00", "ad01-w0-within-gr-00",
                     "ad01-w1-within-sw-00", "ad01-w1-within-gr-00",
                     "ad01-w2-within-sw-00", "ad01-w2-within-gr-00"]

# Past 60s, which is both the adapter's read default and the router's
# upstream header timeout. A reasoning model that needs more than the
# transport's own header budget is a timeout, not a capability finding.
READ_TIMEOUT_MS = 240_000
TOTAL_TIMEOUT_MS = READ_TIMEOUT_MS + 60_000

# Six tasks, one construction call each on the init attempt. A repair is a
# second call on the same slot, so the ceiling is the task count and not a
# number chosen to look generous.
DISPATCH_CEILING = len(ACQUISITION_TASKS) * 2

STUDY_DEADLINE_S = 3000


def _arms_run() -> int:
    """The children this run subdivides, counted three ways.

    One child per acquisition campaign, one for the control's use phase, and
    one per *acquired* arm's own use phase. The third is the one that was
    missed. `use_acquired_arms` calls `study_child` per arm, so the use
    phases are five separate subdivisions and not a share of the control's.

    Getting this wrong is not a small shortfall. `_v1_study_units` is the
    sheet's allowance times `n + 2`, so under-counting by the use phases
    leaves the last subdivisions with a free balance of zero and
    `store.subdivide_allocation` refuses with `parent ... has 0 free`. The
    arms that lose are the ones the loop reaches last, and a use phase that
    never ran is not a fallback the gate can read: it contributes no record
    at all, so the comparison is paired on the two tasks that happened to
    be reached first and `unpaired_tasks` names the other sixteen.
    """
    return len(ACQUISITION_TASKS) * 2 + 1


def study_units() -> int:
    """The study's own authority, derived from the children this run creates.

    `_v1_study_units` counts one allowance per campaign plus one per
    non-acquired arm, and the study's default is sized for its own six
    campaigns plus two extra arms. This run subdivides a different number,
    and the two runs have collided before: a study authorized for fewer
    children than it creates leaves the last one with a free balance of
    zero, and the arm that loses is whichever the loop reaches last.
    Derived rather than typed for that reason.
    """
    from scripts import inv01_study as study
    return study._v1_study_units(_arms_run())


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
    return "r3acq-t%d-%s" % (index, task_id)


def acquire(dsn: str, study_root: str, model: str, route: dict) -> list:
    """The model-acquired arm: one campaign per task, live, with evidence.

    Every refusal is recorded rather than raised. A task whose construction
    timed out is a lost response, and a panel that silently drops its hardest
    task is the defect this whole thread is about, so a refusal is a row in
    the artifact with the stage and the reason the store holds.
    """
    from experiments.ad01 import live_construct
    from experiments.ad01 import worlds
    from scripts import inv01_study as study

    gateway = study._v1_select_provider("live", model, [], route=route)
    guard = live_construct.LiveGuard(
        gateway, pinned_model=model, ceiling=DISPATCH_CEILING,
        expected_route=route)
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
            from experiments.ad01 import trajectory
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
    guard_status = guard.guard_status()
    return arms, guard_status


def run_control_use(dsn: str, study_root: str, out: Path) -> list:
    """The authored control arm, on the same task ids, at the same budget.

    `experiments.ad01.control_use` is the study's own entry point for an arm
    outside the `("I", "R")` vocabulary, in a fresh process, which is what
    makes the member bytes the bytes that run. The selector is measured in
    the host by `control_arm.measured_tables`, so building it spends no
    dispatch.
    """
    from experiments.ad01 import control_arm, trajectory
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
        tasks = control_arm.control_tasks(world)
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
            record["use_policy_source_digest"] = hashlib.sha256(
                source.encode("utf-8")).hexdigest()
            records.append(record)
        print("CONTROL_USE world=%d records=%d" % (world, len(
            json.loads(proc.stdout))), flush=True)
    (out / "use_records_control.json").write_text(
        json.dumps(records, sort_keys=True, indent=1, default=str) + "\n",
        encoding="utf-8")
    return records


def use_acquired(dsn: str, arm: dict, world: int, allocation: str,
                 scratch: Path) -> list:
    """The acquired arm's own use phase, on the task it acquired for.

    A policy can only be used where it was acquired, so the repertoire is
    the one this arm produced and it holds one member. The selector is
    generated from that repertoire rather than shared, because
    `_v1_use_policy_fallback` is keyed on which families the members claim: a
    selector built from a software-only repertoire refuses a graph task
    outright, which would report a missing family as a missing policy. The
    member id is `acquired-<fam>-<digest8>`, which is not in
    `seeds.SEED_CAPABILITIES`, so the bytes are staged and run rather than
    short-circuited to the host's dispatch table.
    """
    from experiments.ad01 import trajectory
    from scripts import inv01_study as study
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
               "--repertoire", str(path), "--world", str(world),
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
    """The acquired arm's use records, one per arm that earned a member.

    An arm whose acquisition did not earn a member contributes no record
    rather than a refusal record. A refusal would be read by
    `control_distinct` as a fallback, and a fallback names no executed
    policy, which is a different claim from "this task was never acquired".
    The panel is unchanged either way; what changes is that an unacquired
    task cannot masquerade as an unmeasured pairing.
    """
    from scripts import inv01_study as study
    scratch.mkdir(parents=True, exist_ok=True)
    records: list = []
    for arm in arms:
        if not arm.get("acquired"):
            continue
        try:
            records.extend(use_acquired(
                dsn, arm, _world_of(arm["task_id"]),
                study_child(dsn, study_root, arm["arm"]), scratch))
        except Exception as exc:
            arm["use_error"] = str(exc)[:400]
            print("ACQUIRED_USE_FAILED arm=%s error=%s"
                  % (arm["arm"], str(exc)[:200]), flush=True)
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

    `load_bundle` reads six files: `freeze`, `construction`, `operations`,
    `use_records`, `accounting`, `assessment`. Every one of them is written
    here from what the run did, not from what the run intended:

    `freeze.config.model`      what was dispatched
    `freeze.metric_rule`       the rule the deltas are normalized by
    `freeze.route`             the pinned route the receipts name
    `construction.<arm>`       the member's own bytes, its digests, and the
                               acquisition evidence read back out of the
                               store by `read_acquisition_evidence`
    `operations.<id>`          every operation under the study's allocation
                               with its receipts, so `_dispatch_leg` can
                               find a live provider rather than take the
                               construction record's word for it
    `use_records`              the control and acquired records
    `accounting`               the four currencies, read before the drop
    `assessment`               one row per executed record

    The origin in the freeze is written only for an arm whose evidence
    reads `earned: true`. `Bundle.earned_origin` re-derives it from the
    construction record rather than trusting the freeze, so a wrong label
    here is caught rather than believed -- but a missing one is not, and an
    arm that cannot show a receipt should not carry the label at all.
    """
    from experiments.ad01 import control_arm, s09_verdict
    from experiments.ad01 import live_construct

    identities: dict = {}
    construction: dict = {}
    for arm in arms:
        if not arm.get("acquired"):
            continue
        # The evidence the acquisition itself recorded, not a re-read.
        # `construct.acquisition_origin` calls
        # `read_acquisition_evidence(dsn, operation_id, response_text)` with
        # the whole settled response, and that call is the one that compares
        # the receipt's `content["text"]` digest against the response the
        # member was parsed from. Re-reading here with the member's
        # `policy_source` compares the receipt against the *extracted
        # `entry` field* instead, which is a substring of the response and
        # hashes differently, so every arm reads `member bytes are not the
        # settled response` and no arm reaches the freeze as acquired. It
        # cost this run a `live_acquisition: unproven` and a
        # `not_comparable` that the receipts do not support.
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
        identities["C"]["source_digest"] = hashlib.sha256(
            "".join(m["method_source"] for m in repertoire["members"]
                    ).encode("utf-8")).hexdigest()

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
    (out / "operations.json").write_text(
        json.dumps(read_operations(dsn, study_root), sort_keys=True, indent=1,
                   default=str) + "\n", encoding="utf-8")
    (out / "use_records.json").write_text(
        json.dumps(control + acquired, sort_keys=True, indent=1,
                   default=str) + "\n", encoding="utf-8")
    (out / "assessment.json").write_text(
        json.dumps({"records": len(control) + len(acquired)}, sort_keys=True,
                   indent=1) + "\n", encoding="utf-8")

    bundle = s09_verdict.Bundle(
        root=out, freeze=freeze, construction=construction,
        operations=read_operations(dsn, study_root),
        use_records=tuple(control + acquired), accounting={},
        assessment=())
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
    """The construction operation id this arm's bytes came from.

    It is the same string `construct_method` builds, reconstructed rather
    than read, and `read_acquisition_evidence` re-reads the operation's own
    committed prompt and its settled receipt, so a mismatch here surfaces as
    a refusal to earn rather than as a silent pass.
    """
    return "ad01-%s-b0-%s-construct-l1-init" % (arm["campaign_id"],
                                                arm["task_id"])


def read_operations(dsn: str, study_root: str) -> dict:
    """Every operation under the study's allocation, with its receipts.

    `_dispatch_leg` requires a receipt for each construction request and
    fails when one is missing, so the bundle has to carry the operations
    rather than a count of them. Only `outcome`, `receipt_identity` and the
    `usage` block are exported; the response text is not, because the
    evidence that a provider answered is the receipt's own metadata and not
    its payload.
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
                " SELECT o.id, o.payload, r.receipt_identity, r.outcome,"
                " r.content FROM operations o"
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
    `ad01-w0-within-...` as the split and raises, which is why this matches
    the `w<N>` prefix rather than counting.
    """
    for token in task_id.split("-"):
        if len(token) > 1 and token[0] == "w" and token[1:].isdigit():
            return int(token[1:])
    raise ValueError("task id %r names no world" % task_id)


def study_child(dsn: str, study_root: str, name: str) -> str:
    """The control arm's own allocation, subdivided from the study's.

    It has to be its own subdivision rather than the study's remainder: the
    six acquisition campaigns are children too, and `free_of` counts a
    parent's children against the parent's balance, so the control would
    arrive to nothing and every one of its records would fall back to
    `incumbent`. A fallback names no policy, and `control_distinct` reads
    that as a refusal rather than a result.
    """
    from scripts import inv01_study as study
    child = "r3-control-%s" % name
    study._v1_ensure_alloc(dsn, study_root, child, study._v1_campaign_units())
    return child


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = Path(argv[0]) if argv else (
        ROOT / "reports" / "evidence" / "invl02_liveacq_r3")
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

    admin = isolation.admin_dsn()
    token = "%s%s" % (TOKEN_RE, uuid.uuid4().hex[:8])
    database = isolation.create_disposable_db(token, admin_dsn=admin)
    print("DISPOSABLE_DB=%s" % database.name, flush=True)
    study_root = isolation.study_root_for(token)
    dsn = database.dsn
    scratch = ROOT / ".ad01-r3-runs" / token
    try:
        study._v1_ensure_run(
            dsn, study_root, study_units(),
            STUDY_DEADLINE_S,
            study._v1_effective_config("live", model, "", STUDY_DEADLINE_S),
            study._v1_panel(),
            study._v1_ceilings(study._v1_use_arms()))

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

        cost = result.cost_currencies(dsn=dsn, study_root=study_root)
        (out / "cost.json").write_text(
            json.dumps(cost, sort_keys=True, indent=1, default=str) + "\n",
            encoding="utf-8")
        print("COST=%s" % json.dumps(
            {k: v.get("status", "REPORTED") for k, v in cost.items()},
            sort_keys=True), flush=True)
        summary = {
            "acquired_arms": len(arms),
            "acquired": sum(1 for a in arms if a["acquired"]),
            "earned": sum(1 for a in arms
                          if (a.get("evidence") or {}).get("earned") is True),
            "control_records": len(control),
            "acquired_use_records": len(acquired_use),
            "control_distinct": gate.get("distinct"),
            "control_distinct_refusal": gate.get("refusal", ""),
            "gate_split": gate_split(gate),
            "utility": rows["value"],
            "mean_acquired_minus_control": rows[
                "mean_acquired_minus_control"],
            "verdicts": verdicts,
            "guard": guard_status,
            "cost": {k: v.get("status", "REPORTED") for k, v in cost.items()},
        }
        (out / "summary.json").write_text(
            json.dumps(summary, sort_keys=True, indent=1, default=str) + "\n",
            encoding="utf-8")
        return 0
    finally:
        isolation.drop_disposable_db(database, admin_dsn=admin)
        print("DROPPED=%s" % database.name, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
