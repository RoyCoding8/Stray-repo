"""AD01 trajectory public entry for fresh processes.

One-shot invocations (no poll loop): ``run`` advances a campaign through
the public entry and publishes settled boundaries; ``resume`` reconciles
the durable record first and continues the same campaign without
duplicate spend; ``use`` loads a frozen repertoire and runs use records
in this fresh process. Learner and constructor reach the model through
the configured gateway seam: ``--model`` for live inference,
``--recordings`` for labeled doubles, neither for the doubled harness.
"""

from __future__ import annotations

import argparse
import json
import sys

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 16}


def _tasks(value: str | None) -> list | None:
    if not value:
        return None
    return [t.strip() for t in value.split(",") if t.strip()]


def _refuse(exc: BaseException) -> int:
    print("ad01-traj refused: %s" % exc, file=sys.stderr)
    if isinstance(exc, (ValueError, LookupError, OSError)):
        return 2
    return 3


def _gateway(model: str, recordings: str):
    if model and recordings:
        raise ValueError("live and recorded modes are mutually exclusive")
    if recordings:
        from .learner import RecordingGatewayAdapter
        scripts = json.loads(open(recordings).read())
        return RecordingGatewayAdapter(scripts)
    if model:
        from settlement.config import Settings
        from settlement.gateway_http import HttpGatewayAdapter
        return HttpGatewayAdapter.from_settings(
            Settings.from_env(), api="responses")
    from settlement.gateway import FakeGatewayAdapter
    return FakeGatewayAdapter(text="")


def _campaign_kwargs(args, world: int, arm: str, cid: str):
    from . import trajectory
    gateway = _gateway(args.model, args.recordings)
    propose = None
    constructor = "seed"
    if args.model or args.recordings:
        from .learner import propose_from_model
        seed = trajectory.ensure_campaign(
            args.dsn, cid, world, arm, CHARTER,
            dict(CAPS, max_boundaries=args.max_boundaries,
                 agenda_authorized=args.agenda_authorized),
            tasks=_tasks(args.tasks))
        propose = propose_from_model(
            args.dsn, cid=cid, gateway=gateway, model=args.model
            or "recorded-double", charter=CHARTER, world=world, arm=arm,
            allocation_id=seed["allocation_id"])
        constructor = "model"
    execution_mode = ("live" if args.model else
                      "recorded" if args.recordings else "doubled")
    model = args.model or ("recorded-double" if args.recordings
                           else "fake-harness")
    return {"propose": propose, "gateway": gateway,
            "model": model, "constructor": constructor,
            "policy_release": getattr(args, "policy_release", None),
            "execution_mode": execution_mode}


def _resume_ids(campaign: str, parser) -> tuple:
    parts = campaign.split("-")
    if len(parts) != 4 or parts[0] != "ad01" or parts[2] not in ("I", "R"):
        parser.error("malformed --campaign %r, want ad01-w<world>-<I|R>-<seq>"
                     % campaign)
    try:
        world = int(parts[1][1:])
    except ValueError:
        parser.error("malformed --campaign %r, want ad01-w<world>-<I|R>-<seq>"
                     % campaign)
    return world, parts[2]


def _add_execution_modes(parser) -> None:
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--model", default="")
    modes.add_argument("--recordings", default="")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ad01-traj")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--dsn", required=True)
    run.add_argument("--world", type=int, required=True)
    run.add_argument("--arm", required=True)
    run.add_argument("--seq", type=int, default=0)
    run.add_argument("--max-boundaries", type=int, default=6)
    run.add_argument("--agenda-authorized", type=int)
    run.add_argument("--tasks", default="")
    _add_execution_modes(run)
    run.add_argument("--export-out", default="")
    run.add_argument("--policy-release")
    cycle = sub.add_parser("cycle")
    cycle.add_argument("--dsn", required=True)
    cycle.add_argument("--world", type=int, required=True)
    cycle.add_argument("--arm", required=True)
    cycle.add_argument("--seq", type=int, default=0)
    cycle.add_argument("--max-boundaries", type=int, default=6)
    cycle.add_argument("--agenda-authorized", type=int)
    cycle.add_argument("--tasks", default="")
    _add_execution_modes(cycle)
    cycle.add_argument("--export-out", default="")
    cycle.add_argument("--policy-release")
    resume = sub.add_parser("resume")
    resume.add_argument("--dsn", required=True)
    resume.add_argument("--campaign", required=True)
    resume.add_argument("--max-boundaries", type=int, default=6)
    resume.add_argument("--agenda-authorized", type=int)
    resume.add_argument("--tasks", default="")
    _add_execution_modes(resume)
    resume.add_argument("--export-out", default="")
    resume.add_argument("--policy-release")
    use = sub.add_parser("use")
    use.add_argument("--repertoire", required=True)
    use.add_argument("--dsn", required=True)
    use.add_argument("--allocation-id", required=True)
    use.add_argument("--release")
    use.add_argument("--accounting-out")
    use.add_argument("--world", type=int, required=True)
    use.add_argument("--arm", required=True)
    use.add_argument("--tasks", default="")
    export = sub.add_parser("export")
    export.add_argument("--dsn", required=True)
    export.add_argument("--campaign", required=True)
    export.add_argument("--out", required=True)
    export.add_argument("--model", default="recorded-double")
    replay = sub.add_parser("replay")
    replay.add_argument("--export", required=True)
    replay.add_argument("--probe", required=True)
    recompute = sub.add_parser("recompute")
    recompute.add_argument("--export", required=True)
    recompute.add_argument("--use-records", default="")
    args = parser.parse_args(argv)
    from . import trajectory, worlds
    if args.command == "export":
        from pathlib import Path
        try:
            _world, _arm = _resume_ids(args.campaign, parser)
            settled, _pending = trajectory._read_campaign(
                args.dsn, args.campaign)
            if not settled:
                raise ValueError("unknown campaign %r" % args.campaign)
            campaign = {"campaign_id": args.campaign,
                        "world": _world, "arm": _arm,
                        "boundaries": [
                            {"seq": seq,
                             "task_id": settled[seq].get("task_id", ""),
                             "decision": settled[seq].get("decision"),
                             "observation_id": settled[seq].get(
                                 "observation_id", ""),
                             "spend": settled[seq].get("spend", 0)}
                            for seq in sorted(settled)],
                        "episodes": [settled[seq].get("episode", {})
                                     for seq in sorted(settled)]}
            from . import records as _records
            caps = dict(CAPS, agenda_authorized=args.agenda_authorized
                        if hasattr(args, "agenda_authorized") else None)
            export_doc = _records.export_campaign(
                args.dsn, campaign, model=args.model,
                charter=dict(CHARTER), caps=caps)
            Path(args.out).write_text(json.dumps(
                export_doc, sort_keys=True, indent=1, default=str)
                + "\n")
        except Exception as exc:
            return _refuse(exc)
        return 0
    if args.command == "replay":
        from pathlib import Path
        try:
            from . import records as _records
            from experiments import doubles as _doubles
            export_doc = _records.load_export(args.export)
            probe = json.loads(Path(args.probe).read_text())
            verdict = _doubles.replay_export(export_doc, probe)
        except Exception as exc:
            return _refuse(exc)
        json.dump(verdict, sys.stdout, sort_keys=True, default=str)
        sys.stdout.write("\n")
        return 0
    if args.command == "recompute":
        from pathlib import Path
        try:
            from . import records as _records
            export_doc = _records.load_export(args.export)
            use_records = []
            if args.use_records:
                use_records = json.loads(
                    Path(args.use_records).read_text())
            out = _records.recompute_accounting(
                export_doc, use_records)
        except Exception as exc:
            return _refuse(exc)
        json.dump(out, sys.stdout, sort_keys=True, default=str)
        sys.stdout.write("\n")
        return 0
    if args.command in ("run", "cycle", "use"):
        if args.world not in worlds.WORLDS:
            parser.error("unknown --world %r, want one of %s"
                         % (args.world, list(worlds.WORLDS)))
        if args.arm not in ("I", "R"):
            parser.error("unknown --arm %r, want I or R" % args.arm)
    if args.command in ("run", "cycle") and args.seq < 0:
        parser.error("--seq must be a nonnegative integer")
    if args.command in ("run", "cycle", "resume") and args.max_boundaries < 0:
        parser.error("--max-boundaries must be a nonnegative integer")
    if args.command == "use":
        try:
            repertoire = trajectory.load_repertoire(args.repertoire)
        except Exception as exc:
            return _refuse(exc)
        try:
            records = trajectory.run_use(
                repertoire, args.world, args.arm,
                _tasks(args.tasks) or [],
                {}, dsn=args.dsn, allocation_id=args.allocation_id,
                release_id=args.release)
        except Exception as exc:
            return _refuse(exc)
        if args.accounting_out:
            from pathlib import Path
            try:
                cost = trajectory.cost_union(repertoire, records,
                                             dsn=args.dsn)
            except Exception as exc:
                return _refuse(exc)
            try:
                Path(args.accounting_out).write_text(
                    json.dumps(cost, sort_keys=True, indent=1) + "\n")
            except OSError as exc:
                return _refuse(exc)
        json.dump(records, sys.stdout, sort_keys=True, default=str)
        sys.stdout.write("\n")
        return 0
    caps = dict(CAPS, max_boundaries=args.max_boundaries,
                agenda_authorized=args.agenda_authorized)
    try:
        if args.command in ("run", "cycle"):
            cid = trajectory.campaign_id(args.world, args.arm, args.seq)
            if args.agenda_authorized:
                trajectory.authorize_campaign(
                    args.dsn, cid, authorized=args.agenda_authorized)
            extra = _campaign_kwargs(args, args.world, args.arm, cid)
            execution_mode = extra.pop("execution_mode", "unknown")
            out = trajectory.run_campaign(
                args.world, args.arm, CHARTER, caps,
                tasks=_tasks(args.tasks),
                campaign_seq=args.seq, dsn=args.dsn, **extra)
        else:
            world, arm = _resume_ids(args.campaign, parser)
            if world not in worlds.WORLDS:
                parser.error("unknown --campaign %r, want world in %s"
                             % (args.campaign, list(worlds.WORLDS)))
            extra = _campaign_kwargs(args, world, arm, args.campaign)
            execution_mode = extra.pop("execution_mode", "unknown")
            if args.agenda_authorized:
                trajectory.authorize_campaign(
                    args.dsn, args.campaign,
                    authorized=args.agenda_authorized)
            out = trajectory.resume_campaign(
                args.dsn, args.campaign, CHARTER, caps,
                tasks=_tasks(args.tasks), **extra)
        out["execution_mode"] = execution_mode
        out["accounting"] = trajectory.cost_union(out, [], dsn=args.dsn)
    except Exception as exc:
        return _refuse(exc)
    if args.export_out:
        try:
            from pathlib import Path
            from . import records as _records
            model = extra.get("model", args.model or "recorded-double")
            export_doc = _records.export_campaign(
                args.dsn, out, model=model,
                charter=dict(CHARTER), caps=caps)
            Path(args.export_out).write_text(json.dumps(
                export_doc, sort_keys=True, indent=1, default=str)
                + "\n")
        except Exception as exc:
            return _refuse(exc)
    json.dump(out, sys.stdout, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
