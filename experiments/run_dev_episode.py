"""Development-01 deterministic episode entry point (DEV-12).

Runs one full development episode end to end through the committed
experiment contract: admit -> diagnose -> construct -> development check ->
select -> freeze -> compare -> dispose -> use/fallback. Each phase is
reported with revision/environment/result detail, and the episode record
keeps A/B/C arms plus the no-op control visible.

Two sources back the run, selected by --gateway:

  fixture (default)  deterministic ScriptedDouble over
      experiments/fault_tasks.py; the report is labeled simulated and is
      never a live result.
  live               broker-routed model inference through the configured
      gateway. Live mode requires supplied access, allocation and profile
      and refuses otherwise (exit 2) naming the exact missing inputs:
        SETTLEMENT_GATEWAY_ENDPOINT (SETTLEMENT_GATEWAY_URL legacy alias)
        SETTLEMENT_GATEWAY_KEY
        SETTLEMENT_GRANT_UNITS (positive integer monetary grant cap)
        --model (or SETTLEMENT_MODEL)
      plus an admitted containment profile: --launcher runsc with a pinned
      --runsc-image, or --launcher local with --allow-uncontained.

Command:
  uv run python experiments/run_dev_episode.py --dsn postgresql://... \\
      --allocation dev01ep --artifacts-root /path/artifacts
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
EXPERIMENTS = HERE.parent
WORKTREE = EXPERIMENTS.parent
for _anchor in (str(EXPERIMENTS), str(WORKTREE / "src")):
    if _anchor not in sys.path:
        sys.path.insert(0, _anchor)

from settlement import development, experiment, store
from settlement.common import Command, SettlementError
from settlement.gateway import GatewayAdapter, GatewayError, ModelResponse, Usage
from settlement.gateway_http import HttpGatewayAdapter
from settlement.launcher_local import LocalLauncher

from run_live_abc import (_bind_grant_cap, _bundle_manifest, _effective_config,
                            _parse_ids, _select_launcher, _source_fingerprint)

LIVE_MISSING = ("live dev episode blocked: set SETTLEMENT_GATEWAY_ENDPOINT, "
                "SETTLEMENT_GATEWAY_KEY, and SETTLEMENT_GRANT_UNITS "
                "(monetary grant cap)")
LIVE_COMMAND = ("uv run python experiments/run_dev_episode.py --dsn $SETTLEMENT_DSN"
                " --allocation <allocation> --artifacts-root $ARTIFACT_ROOT"
                " --gateway live --model <model> --launcher runsc"
                " --runsc-image sha256:<pinned>")
EPISODE_PHASES = ("admit", "diagnose", "construct", "check", "select",
                  "freeze", "compare", "dispose", "use")


def _fixture_double():
    from doubles import ScriptedDouble
    from fault_tasks import DEV_IDS, PANEL_IDS, TASKS, TRANSFER_IDS

    fixes = {t["id"]: t["fixed"] for t in TASKS}
    broken = {t["id"]: t["broken"] for t in TASKS}
    competence = {("B", "panel-triangular"): True, ("B", "panel-batcher"): True}
    for dev_id in DEV_IDS:
        competence[("DEV", dev_id)] = True
    return ScriptedDouble(competence, fixes, broken), DEV_IDS, PANEL_IDS, TRANSFER_IDS


class _EpisodeFixtureAdapter(GatewayAdapter):
    """Deterministic composite for `--gateway fixture`: answers the episode
    diagnose/construct prompts with the worked fixer bytes and delegates the
    run_abcs-internal prompts to ScriptedDouble. Labeled fixture only."""

    def __init__(self, scripted, candidate_code: str):
        self._scripted = scripted
        self._candidate_code = candidate_code
        self.calls: list[dict] = []

    def check_discovery(self):
        return self._scripted.check_discovery()

    def check_auth(self):
        return self._scripted.check_auth()

    def cancel(self, operation_id):
        return self._scripted.cancel(operation_id)

    def infer(self, request):
        try:
            body = json.loads(request.messages[-1]["content"])
        except (ValueError, IndexError, TypeError):
            return GatewayError("protocol", "fixture needs a JSON body",
                                False, request.operation_id)
        if isinstance(body, dict) and body.get("phase") in ("diagnose",
                                                            "construct"):
            self.calls.append(body)
            if body["phase"] == "diagnose":
                payload = {
                    "explanations": [
                        {"id": "e1",
                         "text": "loop bound excludes the endpoint"},
                        {"id": "e2",
                         "text": "spec states inclusive range"}],
                    "intervention": {
                        "action": "inclusive-bound repair procedure"}}
            else:
                payload = {"code": self._candidate_code}
            return ModelResponse(
                request.operation_id, json.dumps(payload),
                {"simulated": True},
                Usage(input_tokens=40, output_tokens=200, charge_units=240),
                "stop")
        return self._scripted.infer(request)


def _live_adapter(args: argparse.Namespace):
    missing = [name for name, present in
               (("SETTLEMENT_GATEWAY_ENDPOINT",
                 os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT",
                                os.environ.get("SETTLEMENT_GATEWAY_URL", ""))),
                ("SETTLEMENT_GATEWAY_KEY",
                 os.environ.get("SETTLEMENT_GATEWAY_KEY", "")),
                ("SETTLEMENT_GRANT_UNITS",
                 os.environ.get("SETTLEMENT_GRANT_UNITS", "")))
               if not present]
    if missing:
        return None, (f"live dev episode blocked: missing {', '.join(missing)};"
                      f" {LIVE_MISSING}"), 2
    grant = os.environ.get("SETTLEMENT_GRANT_UNITS", "")
    try:
        grant_units = int(grant)
    except ValueError:
        return None, (f"live dev episode blocked: SETTLEMENT_GRANT_UNITS={grant!r}"
                       " is not an integer"), 2
    if grant_units <= 0 or not args.model:
        return None, ("live dev episode blocked: grant must be positive and --model"
                      " (or SETTLEMENT_MODEL) must select the episode model"), 2
    try:
        experiment.model_token_budget()
        development.packet_budget()
    except SettlementError as exc:
        return None, f"live dev episode blocked: {exc}", 2
    try:
        launcher = _select_launcher(args)
    except SettlementError as exc:
        return None, str(exc), 3
    try:
        from settlement.gateway_http import gateway_timeout_overrides

        adapter = HttpGatewayAdapter(
            endpoint=os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT",
                                    os.environ.get("SETTLEMENT_GATEWAY_URL", "")),
            api_key=os.environ.get("SETTLEMENT_GATEWAY_KEY", ""),
            api=os.environ.get("SETTLEMENT_GATEWAY_API", "chat"),
            **gateway_timeout_overrides())
    except ValueError as exc:
        return None, f"live dev episode blocked: {exc}", 2
    status = adapter.check_discovery()
    if isinstance(status, GatewayError):
        return None, f"live dev episode blocked: discovery failed: {status}", 3
    auth = adapter.check_auth()
    if isinstance(auth, GatewayError):
        return None, f"live dev episode blocked: auth failed: {auth}", 3
    return {"adapter": adapter, "launcher": launcher, "grant_units": grant_units,
            "discovery": str(status), "auth": str(auth)}, "", 0


def _admit(dsn: str, args: argparse.Namespace, grant_units: int,
           prefix: str) -> tuple[str, dict]:
    if int(store.get_control(dsn).get("authority_version", 0)) < 1:
        raise SettlementError("dev episode blocked: no installed grant")
    if grant_units > 0:
        run_allocation = _bind_grant_cap(dsn, args.allocation, grant_units,
                                         prefix)
    else:
        status = store.allocation_status(dsn, args.allocation)
        available = (int(status["authorized"]) - int(status["consumed"])
                     - int(status["reserved"]))
        if available <= 0:
            raise SettlementError(
                f"dev episode blocked: allocation {args.allocation}"
                " has no available units")
        run_allocation = args.allocation
    try:
        store.admit_commitment(
            dsn, Command(request_id=f"{prefix}-ep-inv",
                         payload={"investigation_id": args.investigation,
                                  "objective": "dev01-episode",
                                  "scope": {}, "obligations": {}}))
    except SettlementError as exc:
        if "already exists" not in str(exc):
            raise
    return run_allocation, {"allocation": run_allocation,
                            "grant_units": grant_units}


def _phase(name: str, status: str, detail: dict) -> dict:
    return {"phase": name, "status": status, "detail": detail}


def _req(prefix: str, *parts: str) -> Command:
    return Command(request_id="-".join((prefix, *parts)), payload={})


def _episode_code(artifacts_root: str, artifact_digest: str) -> str:
    raw = (Path(artifacts_root) / artifact_digest).read_bytes()
    package = json.loads(raw.decode())
    files, manifest = package["files"], package["manifest"]
    name = manifest.get("entry", "")
    if name not in files:
        name = next(iter(files))
    return bytes.fromhex(files[name]).decode()


def _run_episode(dsn: str, args: argparse.Namespace, adapter: Any,
                 launcher: Any, model: str, run_allocation: str, prefix: str,
                 dev_ids: list[str], tasks: list[dict], by_id: dict,
                 panel_ids: list[str], transfer_ids: list[str]) -> dict:
    episode_id = args.episode
    families = sorted({by_id[i]["family"] for i in dev_ids})
    development.observe(
        dsn, _req(prefix, "ep", "observe"), episode_id=episode_id,
        investigation_id=args.investigation,
        trigger_refs=[{"task_id": i, "family": by_id[i]["family"]}
                      for i in dev_ids],
        bottleneck=f"dev batch faults in {','.join(families)}")
    development.propose(
        dsn, _req(prefix, "ep", "propose"), episode_id=episode_id,
        uncertainty=("fixture-driven construction; no live hypothesis"
                     if model == "scripted" else "model-proposed intervention"))
    panel_policy = development.panel_policy_for(
        dev_ids, panel_ids, transfer_ids, families=families,
        evaluator_version=args.evaluator_version)
    development.admit(
        dsn, _req(prefix, "ep", "admit"), episode_id=episode_id,
        reference_version=args.reference_version,
        access_policy={"families": families}, allocation_id=run_allocation,
        panel_policy=panel_policy)
    dev_tasks = [{"id": i, "family": by_id[i]["family"],
                  "broken": by_id[i]["broken"], "cases": by_id[i]["cases"]}
                 for i in dev_ids]
    gathered = development.collect_experience(
        dsn, _req(prefix, "ep", "gather"), adapter, launcher,
        episode_id=episode_id, model=model, dev_tasks=dev_tasks,
        grader_path=str(EXPERIMENTS / "run_tests.py"))
    diagnosed = development.diagnose(
        dsn, _req(prefix, "ep", "diagnose"), adapter, episode_id=episode_id,
        model=model)
    staging_root = tempfile.mkdtemp(prefix="devep-stage-")
    version_stem = f"{prefix}-cand"
    built: dict[str, dict] = {}
    for family in families:
        try:
            made = development.construct(
                dsn, _req(prefix, "ep", "construct", family), adapter,
                launcher, episode_id=episode_id, model=model,
                artifacts_root=args.artifacts_root, staging_root=staging_root,
                version_stem=version_stem, entry=f"{family}_method.py",
                family=family)
        except SettlementError as exc:
            if "candidate slots exhausted" not in str(exc):
                raise
            made = {"status": "slots-exhausted", "detail": str(exc)}
        if made["status"] == "constructed":
            built[family] = made
    def synthesize(transcripts: list[dict]) -> str | None:
        vid = bindings.get("version_id")
        digest = bindings.get("artifact_digest", "")
        if not vid or not digest:
            return None
        return _episode_code(args.artifacts_root, digest)

    checked: dict = {"status": "skipped", "reason": "no constructed candidate"}
    selected: dict = {"status": "skipped", "reason": "no constructed candidate"}
    bindings: dict = {}
    if built:
        checked = development.check(
            dsn, _req(prefix, "ep", "check"), launcher, episode_id=episode_id,
            artifacts_root=args.artifacts_root,
            grader_path=str(EXPERIMENTS / "run_tests.py"), tasks=dev_tasks)
        development.freeze_comparison(
            dsn, _req(prefix, "ep", "freeze"), episode_id=episode_id,
            policy={**panel_policy,
                    "evaluator_version": args.evaluator_version})
        selected = development.select(dsn, _req(prefix, "ep", "select"),
                                      episode_id=episode_id)
        bound = development.bind(dsn, _req(prefix, "ep", "bind"),
                                 episode_id=episode_id)
        bindings = bound["bindings"]
    return {"episode_id": episode_id, "version_stem": version_stem,
            "fixer_version": bindings.get("version_id") or "",
            "panel_eval_protocol": development.eval_protocol_id(episode_id),
            "panel_groups": panel_policy["task_groups"],
            "diagnosed": diagnosed, "built": built, "checked": checked,
            "selected": selected, "bindings": bindings,
            "gathered": gathered, "synthesize": synthesize}


def _use_disposition(releases: dict) -> dict:
    released, policies = {}, {}
    for rel in (releases or {}).values():
        if not isinstance(rel, dict) or rel.get("status") != "released":
            continue
        policy = rel.get("router_policy", "")
        for family, route in (rel.get("routed") or {}).items():
            vid = (route or {}).get("version_id")
            if vid and policy:
                released[family] = vid
                policies[family] = policy
    return {"released": released, "router_policies": policies, "trial": False}


def _episode_phase_ops(ep: dict, report: dict, use: dict) -> dict:
    transcripts = ((ep.get("gathered") or {}).get("transcripts") or {})
    collection = [op for item in transcripts.values()
                  for op in (item.get("model_op"), item.get("grade_op")) if op]
    diagnosed = ep.get("diagnosed") or {}
    diagnosis = [((diagnosed.get("provenance") or {}).get("op")) or ""]
    if diagnosed.get("probes_used"):
        diagnosis.append(f"{ep['episode_id']}-probe")
    construction = []
    for rec in (ep.get("built") or {}).values():
        if not isinstance(rec, dict):
            continue
        prov = rec.get("provenance") or {}
        if prov.get("op"):
            construction.append(prov["op"])
        if rec.get("stage_op"):
            construction.append(rec["stage_op"])
        if rec.get("version_id"):
            construction.append(f"cap-verify-{rec['version_id']}")
    checked = ep.get("checked") or {}
    checks = [op for app in (checked.get("applied") or [])
              for op in (app.get("invoke_op"), app.get("grade_op")) if op]
    repair_op = (checked.get("repair") or {}).get("invoke_op")
    if repair_op:
        checks.append(repair_op)
    acct = (report.get("accounting") or {}).get("ops") or {}
    phases = {"collection": [op for op in collection if op],
              "diagnosis": [op for op in diagnosis if op],
              "construction": construction, "checks": checks,
              "comparison-shared": [op for op, entry in acct.items()
                                    if entry.get("arm") == "dev"]}
    for arm in ("A", "B", "C"):
        phases[f"comparison-{arm}"] = [
            op for op, entry in acct.items() if entry.get("arm") == arm]
    phases["subsequent-use"] = [op for op in
                                (use.get("ops") or {}).values() if op]
    return phases


def _run_subsequent_use(args: argparse.Namespace,
                        run_allocation: str, report: dict) -> dict:
    from fault_tasks import BY_ID

    transfer = [i for i in BY_ID if i.startswith("transfer")]
    panel = [i for i in BY_ID if i.startswith("panel")]
    dev = [i for i in BY_ID if i.startswith("dev-")]
    if args.use_task:
        use_task_id = args.use_task
    elif transfer:
        use_task_id = transfer[0]
    elif panel:
        use_task_id = panel[0]
    else:
        use_task_id = dev[0]
    if use_task_id in transfer:
        prior = "transfer-comparison"
    elif use_task_id in panel:
        prior = "panel-comparison"
    elif use_task_id in dev:
        prior = "development-batch"
    else:
        prior = "none"
    disposition = _use_disposition(report.get("releases") or {})
    cmd = [sys.executable, str(EXPERIMENTS / "run_use.py"),
           "--dsn", args.dsn, "--artifacts-root", args.artifacts_root,
           "--allocation", run_allocation,
           "--investigation", args.investigation, "--episode", args.episode,
           "--use-task", use_task_id, "--prior-exposure", prior,
           "--protocol-prefix", args.protocol_prefix,
           "--disposition-json", json.dumps(disposition),
           "--gateway", args.gateway, "--launcher", args.launcher]
    if args.allow_uncontained:
        cmd.append("--allow-uncontained")
    for flag in ("--runsc-image", "--runsc-python", "--model"):
        value = getattr(args, flag.strip("-").replace("-", "_"), "")
        if value:
            cmd.extend([flag, value])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SettlementError(f"subsequent use did not run: {exc}")
    if proc.returncode != 0:
        raise SettlementError(
            f"subsequent use refused: {proc.stdout.strip()}"
            f" {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def _summarize(report: dict, run_allocation: str, revision: str,
               environment: dict, ep: dict, use: dict, dsn: str) -> dict:
    development = report["development"]
    selection = report["selection"]
    protocols = sorted({v["protocol_id"] for v in
                        report["verdicts"].values() if v.get("protocol_id")}
                       | {f"{environment['protocol_prefix']}-dev"})
    arms = {arm: {task: cell["outcome"]
                  for task, cell in sorted(tasks.items())}
            for arm, tasks in sorted(report["arms"].items())}
    releases = report["releases"]
    released = sorted(name for name, rel in releases.items()
                      if rel.get("status") == "released")
    if released:
        disposition = {"decision": "released-limited", "groups": released,
                       "fallback": "baseline-v0"}
    elif report["simulated"]:
        disposition = {"decision": "fixture-only",
                       "reason": "synthetic evidence stays non-promotable",
                       "selected": "baseline-v0 (incumbent fallback)"}
    else:
        disposition = {"decision": "fallback",
                       "reason": "no observed gain eligible for release",
                       "selected": "baseline-v0 (incumbent fallback)"}
    reuse = {name: {k: rel.get(k) for k in
                    ("release_id", "candidate", "router_policy", "routed",
                     "reuse_attempt") if k in rel}
             for name, rel in releases.items() if rel.get("status") == "released"}
    use_outcome = use.get("outcome", "")
    use_status = "complete" if use_outcome in ("success", "failure") else "blocked"
    use_detail = {"task_id": use.get("task_id", ""),
                  "method": use.get("method", ""),
                  "version_id": use.get("version_id", ""),
                  "outcome": use_outcome, "ops": use.get("ops", {}),
                  "protocol_id": use.get("protocol_id", ""),
                  "prior_exposure": use.get("prior_exposure", ""),
                  "launcher": use.get("launcher", ""),
                  "reason": use.get("reason", ""),
                  "trial": use.get("trial", False),
                  "use_disposition": use.get("disposition", {}),
                  "releases": reuse, "disposition": disposition,
                  "source": use.get("source", {}),
                  "effective_config": use.get("effective_config", {})}
    phases = [
        _phase("admit", "complete",
               {"allocation": run_allocation,
                "grant_units": environment.get("grant_units", 0),
                "episode_id": ep["episode_id"],
                "bindings": ep["bindings"]}),
        _phase("diagnose", "complete",
               {"explanations": len(ep["diagnosed"].get("explanations", [])),
                "probes_used": ep["diagnosed"].get("probes_used", 0),
                "lesson_provenance": development["lesson_provenance"],
                "lesson_digest": development["lesson_digest"]}),
        _phase("construct", "complete",
               {"built": {fam: rec.get("version_id", rec.get("status"))
                          for fam, rec in ep["built"].items()},
                "acquisition": development["acquisition"]}),
        _phase("check", "complete",
               {"grade_outcome": ep["checked"].get("grade_outcome",
                                                  ep["checked"].get("status")),
                "outcomes": {k: v["outcome"] for k, v in
                             sorted(development["outcomes"].items())}}),
        _phase("select", "complete",
               {"episode_selection": (ep["selected"].get("selection")
                                      if isinstance(ep["selected"], dict)
                                      else ep["selected"]),
                "group_candidate": selection["group_candidate"],
                "method_set": selection["method_set"]}),
        _phase("freeze", "complete", {"protocols": protocols}),
        _phase("compare", "complete",
               {"verdicts": report["verdicts"], "arms": arms,
                "ablation_noop": report["ablation_noop"]}),
        _phase("dispose", "complete",
               {"releases": releases, "disposition": disposition}),
        _phase("use", use_status, use_detail),
    ]
    return {"episode": environment["episode"], "revision": revision,
            "environment": environment, "phases": phases,
            "arms": arms, "ablation_noop": report["ablation_noop"],
            "verdicts": report["verdicts"], "budgets": report["budgets"],
            "accounting": report["accounting"]["totals"],
            "accounting_scope": "harness-only: comparison-harness operations;"
                                " excludes collection, diagnosis,"
                                " construction, checks and subsequent use;"
                                " simulated flag applies",
            "episode_costs": experiment.episode_cost_union(
                dsn, _episode_phase_ops(ep, report, use)),
            "development": {"outcomes": {k: v["outcome"] for k, v in
                                         development["outcomes"].items()},
                            "lesson_provenance":
                                development["lesson_provenance"],
                            "methods": development["methods"],
                            "acquisition": development["acquisition"]},
            "disposition": disposition, "simulated": report["simulated"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--allocation", required=True)
    parser.add_argument("--artifacts-root", required=True)
    parser.add_argument("--episode", default="dev01-episode-01")
    parser.add_argument("--investigation", default="dev01-ep-inv")
    parser.add_argument("--protocol-prefix", default="dev01ep")
    parser.add_argument("--evaluator-id", default="s3-eval")
    parser.add_argument("--evaluator-version", default="v1")
    parser.add_argument("--model", default=os.environ.get("SETTLEMENT_MODEL", ""))
    parser.add_argument("--gateway", default="fixture",
                        choices=("fixture", "live"))
    parser.add_argument("--launcher", default="runsc",
                        choices=("runsc", "local"))
    parser.add_argument("--allow-uncontained", action="store_true")
    parser.add_argument("--runsc-image",
                        default=os.environ.get("SETTLEMENT_RUNSC_IMAGE", ""))
    parser.add_argument("--runsc-python",
                        default=os.environ.get("SETTLEMENT_RUNSC_PYTHON", ""))
    parser.add_argument("--dev", default="")
    parser.add_argument("--panel", default="")
    parser.add_argument("--transfer", default="")
    parser.add_argument("--use-task", default="")
    parser.add_argument("--reference-version", default="baseline-v0")
    args = parser.parse_args(argv)
    grant_units = 0
    if args.gateway == "fixture":
        adapter, dev_ids, panel_ids, transfer_ids = _fixture_double()
        launcher = LocalLauncher(tempfile.mkdtemp(prefix="devep-runs-"))
        model, simulated = "scripted", True
    else:
        live, blocker, code = _live_adapter(args)
        if live is None:
            print(blocker)
            return code
        adapter, launcher = live["adapter"], live["launcher"]
        grant_units, model, simulated = (live["grant_units"], args.model,
                                        False)
        endpoint = os.environ.get(
            "SETTLEMENT_GATEWAY_ENDPOINT",
            os.environ.get("SETTLEMENT_GATEWAY_URL", ""))
        print(f"grant cap: {grant_units} units; gateway: {endpoint}",
              file=sys.stderr)
        print(f"discovery: {live['discovery']}; auth: {live['auth']}",
              file=sys.stderr)
        from fault_tasks import DEV_IDS, PANEL_IDS, TRANSFER_IDS

        dev_ids, panel_ids, transfer_ids = DEV_IDS, PANEL_IDS, TRANSFER_IDS
    dev_ids = _parse_ids(args.dev) or dev_ids
    panel_ids = _parse_ids(args.panel) or panel_ids
    transfer_ids = _parse_ids(args.transfer) or transfer_ids
    try:
        run_allocation, admit = _admit(args.dsn, args, grant_units,
                                       args.protocol_prefix)
        if grant_units:
            print(f"grant cap: {grant_units} units;"
                  f" sub-allocation: {run_allocation}", file=sys.stderr)
        from fault_tasks import BY_ID

        tasks = [BY_ID[i] for i in (dev_ids + panel_ids + transfer_ids)]
        if simulated:
            adapter = _EpisodeFixtureAdapter(
                adapter, (EXPERIMENTS / "offbyone_fixer.py").read_text())
        ep = _run_episode(args.dsn, args, adapter, launcher, model,
                          run_allocation, args.protocol_prefix, dev_ids,
                          tasks, BY_ID, panel_ids, transfer_ids)
        report = experiment.run_abcs(
            args.dsn, launcher=launcher, artifacts_root=args.artifacts_root,
            allocation_id=run_allocation, investigation_id=args.investigation,
            tasks=tasks, dev_ids=dev_ids, panel_ids=panel_ids,
            transfer_ids=transfer_ids, lessons=None, gateway=adapter,
            grader_path=str(EXPERIMENTS / "run_tests.py"),
            protocol_prefix=args.protocol_prefix,
            fixer_version=ep["fixer_version"],
            evaluator_id=args.evaluator_id,
            evaluator_version=args.evaluator_version, simulated=simulated,
            model=model, synthesize=ep["synthesize"],
            dev_transcripts=ep["gathered"]["transcripts"],
            panel_protocol={"eval_protocol": ep["panel_eval_protocol"],
                            "groups": ep["panel_groups"],
                            "evaluator_version": args.evaluator_version})
        use = _run_subsequent_use(args, run_allocation, report)
        fingerprint = _source_fingerprint()
        effective = _effective_config(
            adapter=adapter, launcher=launcher, model=model,
            grant_units=grant_units, run_allocation=run_allocation, args=args)
    except SettlementError as exc:
        print(f"dev episode refused: {exc}")
        return 3
    environment = {"episode": args.episode,
                   "protocol_prefix": args.protocol_prefix,
                   "launcher": launcher.profile, "model": model,
                   "grant_units": grant_units,
                   "evaluator": f"{args.evaluator_id}@{args.evaluator_version}",
                   "allocation": run_allocation,
                   "investigation": args.investigation,
                   "entry_point": "experiments/run_dev_episode.py",
                   "episode_bindings": ep["bindings"],
                   "episode_built": {fam: {"version_id": rec["version_id"],
                                           "status": rec["status"]}
                                     for fam, rec in ep["built"].items()},
                   "fixer_version": ep["fixer_version"]}
    record = _summarize(report, run_allocation, fingerprint["revision"],
                        environment, ep, use, args.dsn)
    record["source"] = fingerprint
    record["effective_config"] = effective
    roots = Path(args.artifacts_root)
    roots.mkdir(parents=True, exist_ok=True)
    record_name = f"{args.protocol_prefix}-episode.json"
    record_text = json.dumps(record, indent=2, sort_keys=True)
    (roots / record_name).write_text(record_text)
    manifest = _bundle_manifest(
        entry_point="experiments/run_dev_episode.py", record_name=record_name,
        record_text=record_text, artifacts_root=args.artifacts_root,
        protocol_prefix=args.protocol_prefix, effective_config=effective)
    (roots / f"{args.protocol_prefix}-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True))
    print(record_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
