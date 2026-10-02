"""AG01-12 operator CLI: visible agenda path without reading SQL.

Contract: reports/PLAN.md AGENDA-01 row (frozen command names), decisions
AG01-D01..D08 in reports/DECISIONS.md, design AG01-12 in
docs/design/AGENDA-01-IMPLEMENTATION.md section 3 plus the section 6 demo line.

Frozen call shapes assumed for the parallel STATE lane (change requests live
in reports/workstreams/ag01-demo.md; the coordinator verifies them at merge):
  agenda.propose_option(dsn, cmd)         request ag01-propose-<key>-r<rev>
  agenda.select_and_admit(dsn, cmd)       request ag01-admit-<option>-<probe>
  agenda.record_outcome(dsn, cmd)         request ag01-observe-<receipt>
  agenda.submit_continuation(dsn, cmd)    request ag01-cont-<option>-<probe>
  agenda.set_dormant(dsn, cmd)            expected_disposition_version
  agenda.answer_option(dsn, cmd)          expected_disposition_version
  agenda.retire_option(dsn, cmd)          expected_disposition_version
  agenda.process_wake(dsn, cmd)           request ag01-wake-<option>-<event>
  agenda.explain_eligibility(dsn, option_id)  read-only dict
  agenda.agenda_snapshot(dsn)             extended dict (eligibility reasons,
                                          continuation basis, wake condition,
                                          costs, outstanding liability)

Backend: StateBackend over the integrated settlement.agenda commands on real
PostgreSQL. A missing command is a hard failure; there is no silent
substitution and no parallel toy store.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from settlement.common import (Command, CommandResult, ConflictPayload, ResultCode,
                               SettlementError, StaleRevision, payload_digest)

TRAJECTORY = "demo-traj"
BUDGET_TOTAL = 64
PROBE_COSTS = {"small": 2, "medium": 4, "large": 8}
STATE_FUNCS = ("propose_option", "select_and_admit", "record_outcome",
               "submit_continuation", "set_dormant", "answer_option",
               "retire_option", "process_wake", "explain_eligibility")


def dsn_of(args) -> str:
    dsn = args.dsn or os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn:
        raise SystemExit("no DSN: pass --dsn or set SETTLEMENT_TEST_DSN")
    if "PGPASSWORD" in os.environ:
        raise SystemExit("refusing: PGPASSWORD is set; use peer auth")
    if "password" in dsn.lower():
        raise SystemExit("refusing: DSN must use peer auth, no passwords")
    return dsn


def _res(code: ResultCode, request_id: str, detail: str = "",
         data: dict | None = None) -> CommandResult:
    return CommandResult(code=code, request_id=request_id, detail=detail,
                         data=data or {})


def _fade(result: CommandResult) -> int:
    return 0 if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED) else 2


class StateBackend:
    name = "state-lane"

    def __init__(self, dsn: str, agenda):
        self.dsn = dsn
        self.agenda = agenda

    def _ready(self) -> None:
        from settlement import db as _db
        _db.apply_migrations(self.dsn, Path(__file__).resolve().parent.parent / "migrations")

    def _call(self, func: str, payload: dict, request_id: str,
              expected_revision: int | None = None) -> CommandResult:
        self._ready()
        cmd = Command(request_id=request_id, expected_revision=expected_revision,
                      payload=payload)
        try:
            return getattr(self.agenda, func)(self.dsn, cmd)
        except SettlementError as exc:
            return _res(exc.code, request_id, str(exc), {})

    def init_db(self) -> CommandResult:
        from pathlib import Path as _Path

        from settlement import db as _db

        _db.apply_migrations(self.dsn, _Path(__file__).resolve().parent.parent
                             / "migrations")
        return _res(ResultCode.APPLIED, "init-db",
                    f"state backend ready on {self.dsn}", {"backend": self.name})

    def reset(self) -> None:
        raise SystemExit("refusing reset on the shared state backend; use a scratch DB")

    def propose(self, option_key: str, scope: str, question: str, revision: int,
                expected_revision: int | None, allocation_root: str, body: dict,
                request_id: str | None = None) -> CommandResult:
        return self._call("propose_option",
                          {"option_key": option_key, "scope": scope, "question": question,
                           "revision": revision, "allocation_root": allocation_root,
                           "body": body},
                          request_id or f"ag01-propose-{option_key}-r{revision}",
                          expected_revision)

    def grant(self, root: str, exploration: int = BUDGET_TOTAL,
              request_id: str | None = None) -> CommandResult:
        from settlement import store as _store
        self._ready()
        tag = request_id or f"ag01-grant-{root}"
        seed = _store.seed_grant(
            self.dsn, Command(request_id=f"{tag}-charter",
                              payload={"version": 1, "charter_text": "agenda01 demo",
                                       "authority_grant": {}, "envelopes": {}}))
        if seed.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            return seed
        alloc = _store.seed_allocation(
            self.dsn, Command(request_id=f"{tag}-root",
                              payload={"allocation_id": root, "domain": "agenda01",
                                       "authorized": exploration,
                                       "max_occupancy": 8}))
        if alloc.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            return alloc
        inv = _store.admit_commitment(
            self.dsn, Command(request_id=f"{tag}-inv",
                              payload={"investigation_id": f"ag01-inv-{TRAJECTORY}",
                                       "objective": "agenda01 demo trajectory",
                                       "scope": {"trajectory": TRAJECTORY},
                                       "obligations": {"tasks": 1},
                                       "sponsor": "agenda01-demo",
                                       "origin": "demo-setup"}))
        if inv.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            return inv
        return _res(ResultCode.APPLIED, tag,
                    f"grant v1 funds {root} with {exploration} exploration",
                    {"allocation_root": root, "authorized": exploration})

    def admit(self, option_id: str, probe: str, intended_decision: str,
              trajectory: str = TRAJECTORY, replication_slot: str | None = None,
              evidence_refs: list | None = None, dep_versions: dict | None = None,
              cost: int = 4, request_id: str | None = None,
              policy_version: str = "AG01-R-1", input_digest: str = "demo-digest",
              observed: list | None = None) -> CommandResult:
        return self._call("select_and_admit",
                          {"trajectory": trajectory, "option_id": option_id,
                           "probe": probe, "intended_decision": intended_decision,
                           "replication_slot": replication_slot,
                           "policy_version": policy_version,
                           "input_digest": input_digest,
                           "evidence_refs": evidence_refs or [],
                           "dep_versions": dep_versions or {},
                           "observed_plan": observed or [], "cost": cost},
                          request_id or f"ag01-admit-{option_id}-{probe}")

    def dispatch(self, operation_id: str, values: dict,
                 request_id: str | None = None) -> CommandResult:
        from experiments.agenda01 import launcher as _launcher
        from settlement import broker as _broker
        self._ready()
        sim = _launcher.AgendaProbeLauncher(
            self.dsn,
            observe=lambda probe, sample, prop: values.get(prop, True),
            claim=lambda prop: bool(values.get(prop, False)))
        status = _broker.dispatch_operation(
            self.dsn, operation_id,
            launchers={_launcher.ADAPTER_KEY: sim})
        if not status.sent_this_call and status.dispatch_state not in ("observed",
                                                                       "unresolved"):
            return _res(ResultCode.INVALID_INPUT,
                        request_id or f"ag01-dispatch-{operation_id}",
                        f"dispatch refused: {status.next_decision}", {})
        receipts = sim.read_result(operation_id) or {}
        return _res(ResultCode.APPLIED,
                    request_id or f"ag01-dispatch-{operation_id}",
                    f"dispatched {operation_id} as {status.dispatch_state}",
                    {"operation_id": operation_id,
                     "dispatch_state": status.dispatch_state,
                     "receipts": {prop: content["receipt"]
                                  for prop, content in receipts.items()}})

    def observe(self, option_id: str, attempt_id: str, receipt: str,
                request_id: str | None = None) -> CommandResult:
        return self._call("record_outcome",
                          {"option_id": option_id, "attempt_id": attempt_id,
                           "receipt_identity": receipt},
                          request_id or f"ag01-observe-{receipt}-{attempt_id}")

    def continue_(self, option_id: str, parent_attempt: str, cites: list[str],
                  next_probe: str, residual_prop: str, consequences: dict,
                  trajectory: str = TRAJECTORY,
                  replication_slot: str | None = None, cost: int = 2,
                  request_id: str | None = None,
                  policy_version: str = "AG01-R-1",
                  input_digest: str = "demo-digest",
                  observed: list | None = None) -> CommandResult:
        return self._call("submit_continuation",
                          {"option_id": option_id, "parent_attempt": parent_attempt,
                           "observation_refs": cites, "next_probe": next_probe,
                           "intended_decision": f"probe {next_probe}",
                           "residual_question": residual_prop,
                           "consequences": consequences, "replication_slot": None
                           if replication_slot is None else replication_slot,
                           "policy_version": policy_version,
                           "input_digest": input_digest,
                           "observed_plan": observed or [], "cost": cost},
                          request_id or f"ag01-cont-{option_id}-{next_probe}")

    def decline(self, option_id: str, expected_version: int | None, reason: str,
                wake_condition: dict, request_id: str | None = None) -> CommandResult:
        return self._call("set_dormant",
                          {"option_id": option_id,
                           "expected_disposition_version": expected_version,
                           "reason": reason, "wake_condition": wake_condition},
                          request_id or f"ag01-decline-{option_id}")

    def answer(self, option_id: str, expected_version: int | None, answer: str,
               request_id: str | None = None) -> CommandResult:
        return self._call("answer_option",
                          {"option_id": option_id,
                           "expected_disposition_version": expected_version,
                           "answer": answer},
                          request_id or f"ag01-answer-{option_id}")

    def retire(self, option_id: str, expected_version: int | None, reason: str,
               request_id: str | None = None) -> CommandResult:
        return self._call("retire_option",
                          {"option_id": option_id,
                           "expected_disposition_version": expected_version,
                           "reason": reason},
                          request_id or f"ag01-retire-{option_id}")

    def wake(self, option_id: str, event: dict,
             request_id: str | None = None) -> CommandResult:
        return self._call("process_wake", {"option_id": option_id, "event": event},
                          request_id or f"ag01-wake-{option_id}-{event.get('identity')}")

    def snapshot(self) -> dict:
        self._ready()
        snap = self.agenda.agenda_snapshot(self.dsn)
        return snap if isinstance(snap, dict) else {"raw": snap}

    def explain(self, option_id: str | None = None) -> list[str]:
        snap = self.snapshot()
        lines = ["[snapshot] " + json.dumps(snap, sort_keys=True, default=str)]
        if option_id is not None:
            try:
                detail = self.agenda.explain_eligibility(self.dsn, option_id)
                lines.append("[eligibility] " + json.dumps(detail, sort_keys=True,
                                                           default=str))
            except SettlementError as exc:
                lines.append(f"[eligibility] refused: {exc}")
        return lines

    def resume(self, trajectory: str = TRAJECTORY) -> list[str]:
        snap = self.snapshot()
        tick = (snap.get("cursor") or {}).get("tick")
        lines = [f"[resume] fresh process on {self.dsn}: trajectory={trajectory} tick={tick}"]
        for opt in snap.get("options", []):
            if opt["disposition"] == "open":
                lines.append(f"[resumable] open {opt['option_id']} at r{opt['revision']}:"
                             " eligible: open revision rechecked against durable state")
            elif opt["disposition"] == "dormant":
                cond = opt["wake_condition"] or {}
                lines.append(f"[resumable] dormant {opt['option_id']}: waits on"
                             f" {cond.get('type')}:{cond.get('dep', '')};"
                             " no pending dispatch escapes dormancy")
        held = [a["operation_id"] for a in snap.get("agenda_attempts", [])
                if a["state"] == "admitted"]
        lines.append(f"[resumable] outstanding liability carries over: {held or []}")
        settled = len([a for a in snap.get("agenda_attempts", []) if a["state"] == "settled"])
        lines.append(f"[costs] decisions={snap.get('decisions')} probes_settled={settled}"
                     f" outstanding_liability={snap.get('liability')}"
                     f" budget_remaining={snap.get('remaining')}")
        return lines


def pick_backend(dsn: str):
    from settlement import agenda as _agenda
    missing = [name for name in STATE_FUNCS if not callable(getattr(_agenda, name, None))]
    if missing:
        raise SystemExit(f"refusing: agenda commands missing: {','.join(missing)}")
    return StateBackend(dsn, _agenda)


def show(result: CommandResult, tag: str) -> int:
    print(f"[{tag}] result={result.code.value} reason={result.detail}")
    if result.data:
        print(f"[{tag}] data={json.dumps(result.data, sort_keys=True, default=str)}")
    return _fade(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    grant = sub.add_parser("grant")
    grant.add_argument("--root", default="agenda-root")
    grant.add_argument("--exploration", type=int, default=BUDGET_TOTAL)
    propose = sub.add_parser("propose")
    propose.add_argument("--option", required=True)
    propose.add_argument("--scope", default="transfer")
    propose.add_argument("--question", default="which transfer route is congested")
    propose.add_argument("--revision", type=int, default=1)
    propose.add_argument("--expected-revision", type=int, default=None)
    propose.add_argument("--allocation-root", default="agenda-root")
    propose.add_argument("--body", default="{}")
    admit = sub.add_parser("admit")
    admit.add_argument("--option", required=True)
    admit.add_argument("--probe", required=True)
    admit.add_argument("--decision", required=True)
    admit.add_argument("--trajectory", default=TRAJECTORY)
    admit.add_argument("--replication-slot", default=None)
    admit.add_argument("--cost", type=int, default=4)
    admit.add_argument("--dep", default="dep-seed")
    admit.add_argument("--dep-version", type=int, default=3)
    admit.add_argument("--policy-version", default="AG01-R-1")
    admit.add_argument("--input-digest", default="demo-digest")
    admit.add_argument("--observe-prop", default=None)
    admit.add_argument("--observe-scope", default="transfer")
    admit.add_argument("--observe-dep", default="dep-seed")
    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--operation", required=True)
    dispatch.add_argument("--values", default="{}")
    observe = sub.add_parser("observe")
    observe.add_argument("--option", required=True)
    observe.add_argument("--attempt", required=True)
    observe.add_argument("--receipt", required=True)
    cont = sub.add_parser("continue")
    cont.add_argument("--option", required=True)
    cont.add_argument("--parent-attempt", required=True)
    cont.add_argument("--cite", action="append", default=[])
    cont.add_argument("--next-probe", required=True)
    cont.add_argument("--residual-prop", required=True)
    cont.add_argument("--if-true", default="")
    cont.add_argument("--if-false", default="")
    cont.add_argument("--replication-slot", default=None)
    cont.add_argument("--cost", type=int, default=2)
    cont.add_argument("--policy-version", default="AG01-R-1")
    cont.add_argument("--input-digest", default="demo-digest")
    cont.add_argument("--observe-prop", default=None)
    cont.add_argument("--observe-scope", default="transfer")
    cont.add_argument("--observe-dep", default="dep-seed")
    decline = sub.add_parser("decline")
    decline.add_argument("--option", required=True)
    decline.add_argument("--expected-version", type=int, default=None)
    decline.add_argument("--reason", required=True)
    decline.add_argument("--wake-type", required=True)
    decline.add_argument("--wake-dep", default="")
    decline.add_argument("--wake-ref", default="")
    answer = sub.add_parser("answer")
    answer.add_argument("--option", required=True)
    answer.add_argument("--expected-version", type=int, default=None)
    answer.add_argument("--answer", required=True)
    retire = sub.add_parser("retire")
    retire.add_argument("--option", required=True)
    retire.add_argument("--expected-version", type=int, default=None)
    retire.add_argument("--reason", required=True)
    wake = sub.add_parser("wake")
    wake.add_argument("--option", required=True)
    wake.add_argument("--event-identity", required=True)
    wake.add_argument("--event-kind", required=True)
    wake.add_argument("--event-dep", default="")
    wake.add_argument("--event-dep-version", type=int, default=None)
    wake.add_argument("--event-ref", default="")
    wake.add_argument("--event-version", type=int, default=None)
    wake.add_argument("--event-scan", default="")
    resume = sub.add_parser("resume")
    resume.add_argument("--trajectory", default=TRAJECTORY)
    explain = sub.add_parser("explain")
    explain.add_argument("--option", default=None)
    sub.add_parser("demo")
    return parser


def run_cli(backend, args) -> int:
    print(f"[backend] name={backend.name}"
          f" note={getattr(backend, 'banner_note', 'integrated state lane')}")
    if args.cmd == "init-db":
        return show(backend.init_db(), "init-db")
    if args.cmd == "grant":
        return show(backend.grant(args.root, args.exploration), "grant")
    if args.cmd == "propose":
        return show(backend.propose(args.option, args.scope, args.question,
                                    args.revision, args.expected_revision,
                                    args.allocation_root, json.loads(args.body)),
                    "propose")
    if args.cmd == "admit":
        observed = [] if args.observe_prop is None else [
            {"prop": args.observe_prop, "scope": args.observe_scope,
             "dep": args.observe_dep}]
        return show(backend.admit(args.option, args.probe, args.decision,
                                  args.trajectory, args.replication_slot, [],
                                  {args.dep: args.dep_version}, args.cost,
                                  None, args.policy_version, args.input_digest,
                                  observed), "admit")
    if args.cmd == "dispatch":
        return show(backend.dispatch(args.operation, json.loads(args.values)),
                    "dispatch")
    if args.cmd == "observe":
        return show(backend.observe(args.option, args.attempt, args.receipt),
                    "observe")
    if args.cmd == "continue":
        observed = [] if args.observe_prop is None else [
            {"prop": args.observe_prop, "scope": args.observe_scope,
             "dep": args.observe_dep}]
        return show(backend.continue_(args.option, args.parent_attempt, args.cite,
                                      args.next_probe, args.residual_prop,
                                      {"if_true": args.if_true,
                                       "if_false": args.if_false}, TRAJECTORY,
                                      args.replication_slot, args.cost, None,
                                      args.policy_version, args.input_digest,
                                      observed),
                    "continue")
    if args.cmd == "decline":
        cond = {"type": args.wake_type}
        if args.wake_dep:
            cond["dep"] = args.wake_dep
        if args.wake_ref:
            cond["ref"] = args.wake_ref
        return show(backend.decline(args.option, args.expected_version, args.reason,
                                    cond), "decline")
    if args.cmd == "answer":
        return show(backend.answer(args.option, args.expected_version, args.answer),
                    "answer")
    if args.cmd == "retire":
        return show(backend.retire(args.option, args.expected_version, args.reason),
                    "retire")
    if args.cmd == "wake":
        event: dict = {"identity": args.event_identity, "kind": args.event_kind}
        for key, value in (("dep", args.event_dep), ("ref", args.event_ref),
                           ("scan", args.event_scan)):
            if value:
                event[key] = value
        for key, value in (("dep_version", args.event_dep_version),
                           ("version", args.event_version)):
            if value is not None:
                event[key] = value
        result = backend.wake(args.option, event)
        print(f"[wake] result={result.code.value} reason={result.detail}")
        return 0 if result.code == ResultCode.APPLIED else _fade(result)
    if args.cmd == "resume":
        for line in backend.resume(args.trajectory):
            print(line)
        return 0
    if args.cmd == "explain":
        for line in backend.explain(args.option):
            print(line)
        return 0
    raise SystemExit(f"unknown command {args.cmd}")


OPT = "q-bottleneck"
SCOPE = "transfer"
PROBE_A = "probe-route-a"
PROBE_B = "probe-route-b"
ATT_A = f"att-{OPT}-{PROBE_A}"
ATT_B = f"att-{OPT}-{PROBE_B}"
BODY = {"hypothesis": "route A carries the overload",
        "basis": "yesterday's transfer backlog",
        "desired_observation": "per-route congestion at dep-seed v3",
        "probe": PROBE_A, "intended_decision": "shift load to route B",
        "decision_consequences": {"route-A-congested=true": "shift load",
                                 "route-A-congested=false": "hold"},
        "dependencies": ["dep-seed"], "cap": 8, "expiry": "tick-24", "exposure": 4}


def _need(ok: bool, label: str) -> None:
    print(f"[check] {label}: {'held' if ok else 'VIOLATED'}")
    if not ok:
        raise SystemExit(f"demo invariant violated: {label}")


def _scratch_dsn(dsn: str, name: str) -> str:
    from urllib.parse import urlparse, urlunparse
    parts = urlparse(dsn)
    return urlunparse((parts.scheme, parts.netloc, "/" + name, "", parts.query, ""))


def _create_db(base_dsn: str, name: str) -> str:
    import psycopg
    with psycopg.connect(base_dsn, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    return _scratch_dsn(base_dsn, name)


def _drop_db(base_dsn: str, name: str) -> None:
    import psycopg
    with psycopg.connect(base_dsn, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


def run_demo(dsn: str) -> int:
    import uuid
    base = dsn
    scratch = f"agenda01_demo_run_{uuid.uuid4().hex[:8]}"
    dsn = _create_db(base, scratch)
    try:
        backend = pick_backend(dsn)
        backend.init_db()
        print(f"[backend] name={backend.name} note=integrated state lane")
        print("[demo] scratch journey on a fresh deterministic state")
        granted = backend.grant("agenda-root", BUDGET_TOTAL)
        print(f"[grant] result={granted.code.value} reason={granted.detail}")
        _need(granted.code == ResultCode.APPLIED, "authority grant precedes proposals")
        first = backend.propose(OPT, SCOPE, "which transfer route is congested", 1, None,
                                "agenda-root", BODY)
        print(f"[propose] result={first.code.value} reason={first.detail}")
        _need(first.code == ResultCode.APPLIED and
              first.data.get("disposition") == "open", "propose opens r1")
        replay = backend.propose(OPT, SCOPE, "which transfer route is congested", 1, None,
                                 "agenda-root", BODY)
        print(f"[propose-replay] result={replay.code.value} reason={replay.detail}")
        _need(replay.code == ResultCode.ALREADY_APPLIED, "stable request replays one result")
        stale = backend.propose(OPT, SCOPE, "which transfer route is congested", 1, 0,
                                "agenda-root", BODY,
                                "ag01-propose-q-bottleneck-r1-staleprobe")
        print(f"[propose-stale] result={stale.code.value} reason={stale.detail}")
        _need(stale.code == ResultCode.STALE_REVISION, "stale expected revision refuses")
        admitted = backend.admit(OPT, PROBE_A, "shift load to route B", TRAJECTORY, None,
                                 [], {"dep-seed": 3}, PROBE_COSTS["medium"], None,
                                 "AG01-R-1", "demo-digest-a",
                                 [{"prop": "route-A-congested", "scope": SCOPE,
                                   "dep": "dep-seed"}])
        print(f"[admit] result={admitted.code.value} reason={admitted.detail}")
        _need(admitted.code == ResultCode.APPLIED and
              admitted.data.get("attempt_id") == ATT_A, "admit funds attempt A")
        dup = backend.admit(OPT, PROBE_A, "shift load to route B", TRAJECTORY, None, [],
                            {"dep-seed": 3}, PROBE_COSTS["medium"],
                            "ag01-admit-q-bottleneck-probe-route-a-retry")
        print(f"[admit-duplicate] result={dup.code.value} reason={dup.detail}")
        _need(dup.code == ResultCode.ALREADY_APPLIED and dup.data.get("dec_op"),
              "same probe slot creates no effect but the new decision is charged")
        sent_a = backend.dispatch(admitted.data["operation_id"],
                                  {"route-A-congested": True})
        print(f"[dispatch] result={sent_a.code.value} reason={sent_a.detail}")
        print(f"[dispatch] data={json.dumps(sent_a.data, sort_keys=True)}")
        _need(sent_a.code == ResultCode.APPLIED and sent_a.data.get("receipts"),
              "dispatch sends the probe and returns launcher receipts")
        rc_1 = sent_a.data["receipts"]["route-A-congested"]
        seen = backend.observe(OPT, ATT_A, rc_1)
        print(f"[observe] result={seen.code.value} reason={seen.detail}")
        _need(seen.code == ResultCode.APPLIED and seen.data.get("settled_probe") is not None,
              "decisive outcome links and settles probe exposure")
        forged = backend.observe(OPT, ATT_A, "rc-forged",
                                 "ag01-observe-rc-forged-demo")
        print(f"[observe-forged] result={forged.code.value} reason={forged.detail}")
        _need(forged.code == ResultCode.INVALID_INPUT and
              "unknown receipt" in forged.detail,
              "fabricated receipts justify no outcome")
        useful = backend.continue_(OPT, ATT_A, [rc_1], PROBE_B, "route-B-congested",
                                   {"if_true": "fix route B", "if_false": "keep route A"},
                                   TRAJECTORY, None, PROBE_COSTS["small"], None,
                                   "AG01-R-1", "demo-digest-b",
                                   [{"prop": "route-B-congested", "scope": SCOPE,
                                     "dep": "dep-seed"}])
        print(f"[continue] result={useful.code.value} reason={useful.detail}")
        _need(useful.code == ResultCode.APPLIED and
              useful.data.get("decision") == "useful-continuation",
              "useful continuation admitted with a qualification route")
        _need("useful continuation" in useful.detail,
              "continuation names its qualification route")
        sent_b = backend.dispatch(useful.data["operation_id"],
                                  {"route-B-congested": None})
        print(f"[dispatch] result={sent_b.code.value} reason={sent_b.detail}")
        _need(sent_b.code == ResultCode.APPLIED, "second probe dispatches")
        rc_2 = sent_b.data["receipts"]["route-B-congested"]
        unknown = backend.observe(OPT, ATT_B, rc_2)
        print(f"[observe] result={unknown.code.value} reason={unknown.detail}")
        _need(unknown.code == ResultCode.APPLIED and
              unknown.data.get("settled_probe") is None,
              "unknown outcome preserves uncertainty and retains exposure")
        refused = backend.continue_(OPT, ATT_B, [rc_2], "probe-route-c",
                                    "route-B-congested",
                                    {"if_true": "fix route B", "if_false": "keep route A"},
                                    TRAJECTORY, None, PROBE_COSTS["small"])
        print(f"[continue] result={refused.code.value} reason={refused.detail}")
        _need(refused.code == ResultCode.INVALID_INPUT and
              "remains unknown" in refused.detail,
              "unknown support yields a justified refusal, not a probe")
        dormant = backend.decline(OPT, 1, "waiting on fresher dependency evidence",
                                  {"type": "evidence-change", "dep": "dep-seed"})
        print(f"[decline] result={dormant.code.value} reason={dormant.detail}")
        _need(dormant.code == ResultCode.APPLIED and
              dormant.data.get("disposition") == "dormant",
              "decline parks the option dormant with a typed wake condition")
        noise = backend.wake(OPT, {"identity": "ev-noise", "kind": "message",
                                   "text": "unrelated chatter"})
        print(f"[wake] result={noise.code.value} reason={noise.detail}")
        _need(noise.code == ResultCode.APPLIED and not noise.data.get("woke"),
              "untyped events leave dormancy untouched")
        relevant = backend.wake(OPT, {"identity": "ev-dep-v4", "kind": "evidence-changed",
                                      "dep": "dep-seed", "version": 4})
        print(f"[wake] result={relevant.code.value} reason={relevant.detail}")
        _need(relevant.code == ResultCode.APPLIED and relevant.data.get("woke"),
              "a relevant event reopens the dormant question with a reason")
        redeliver = backend.wake(OPT, {"identity": "ev-dep-v4", "kind": "evidence-changed",
                                       "dep": "dep-seed", "version": 4},
                                 "ag01-wake-q-bottleneck-ev-dep-v4-redeliver")
        print(f"[wake] result={redeliver.code.value} reason={redeliver.detail}")
        _need(redeliver.code == ResultCode.ALREADY_APPLIED,
              "duplicate wake delivery creates no duplicate effect")
        script = Path(__file__).resolve()
        fresh = subprocess.run([sys.executable, str(script), "--dsn", dsn, "resume"],
                               capture_output=True, text=True, timeout=120)
        print("[resume-fresh] subprocess resume output:")
        print(fresh.stdout.strip())
        if fresh.stderr.strip():
            print("[resume-fresh] subprocess errors:")
            print(fresh.stderr.strip())
        _need(fresh.returncode == 0 and "[resumable] open q-bottleneck" in fresh.stdout,
              "fresh process resumes the reopened option from durable state")
        for line in backend.explain(OPT):
            print(line)
        snap = backend.snapshot() if hasattr(backend, "snapshot") else {}
        if snap.get("liability") is not None:
            _need(snap["liability"] == PROBE_COSTS["small"],
                  "unknown probe exposure survives as outstanding liability")
            _need(snap["remaining"] == BUDGET_TOTAL - 4 - PROBE_COSTS["medium"]
                  - PROBE_COSTS["small"], "budget reconstructs from durable cost records")
            _need(snap["cursor"]["tick"] == 4, "one cursor tick per paid decision")
            _need(any(o["option_id"] == OPT and o["disposition"] == "open"
                      for o in snap["options"]), "journey ends with the option open")
        print("[demo] journey complete: propose replayed, admit funded, outcomes linked,"
              " continuation qualified once and refused once with reasons, dormancy"
              " waited on a typed condition, wake reopened on relevant evidence only,"
              " and a fresh process resumed from durable records")
        return 0
    finally:
        _drop_db(base, scratch)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    dsn = dsn_of(args)
    if args.cmd == "demo":
        try:
            return run_demo(dsn)
        except SystemExit as exc:
            print(str(exc))
            return 1
    return run_cli(pick_backend(dsn), args)


if __name__ == "__main__":
    raise SystemExit(main())
