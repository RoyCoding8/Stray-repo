"""AG01-EXP durable trajectory runner: tick order, budgets, isolation, traces.

Every scored trajectory runs through the implemented agenda commands
(settlement.agenda) on a per-trajectory isolated PostgreSQL database, with
policy decisions from settlement.agenda_policy (decide_R / decide_Q). The
runner never imports grader-latent facts into the policy path: simulation
reads latent bits only to mint world observations, exactly as a physical
probe would mint readouts. Manifest hash in every trace.
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from settlement import agenda, agenda_policy, broker, db, store
from settlement.common import (Command, ResultCode, SettlementError,
                               payload_digest)

from . import grader, launcher, manifest, observations, worlds
from .worlds import draw


def traj_ids(world_index: int, variant: int, arm: str, tie: int) -> str:
    assert arm in ("R", "Q") and tie in (0, 1)
    return f"w{world_index:02d}v{variant}_{arm.lower()}_t{tie}"


def swap_dbname(dsn: str, name: str) -> str:
    return make_conninfo(dsn, dbname=name)


def create_db(base_dsn: str, name: str) -> str:
    with psycopg.connect(base_dsn, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    return swap_dbname(base_dsn, name)


def drop_db(base_dsn: str, name: str) -> None:
    with psycopg.connect(base_dsn, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


def _ok(result, what: str):
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(f"{what} refused: {result.code.value} {result.detail}")
    return result


class AgendaBackend:
    def __init__(self, dsn: str, traj: str, sim: launcher.AgendaProbeLauncher) -> None:
        self.dsn = dsn
        self.traj = traj
        self.root = f"ag01:{traj}"
        self.explore = f"{self.root}:explore"
        self.eval = f"{self.root}:eval"
        self.recovery = f"{self.root}:recovery"
        self.inv = f"ag01-inv-{traj}"
        self.sim = sim

    def setup(self, budgets: dict) -> None:
        total = budgets["exploration"] + budgets["eval_per_trajectory"] + budgets["recovery_cap"]
        _ok(store.seed_grant(
            self.dsn, Command(request_id=f"ag01-setup-{self.traj}-grant",
                              payload={"version": 1, "charter_text": "agenda01 experiment",
                                       "authority_grant": {}, "envelopes": {}})), "seed grant")
        _ok(store.seed_allocation(
            self.dsn, Command(request_id=f"ag01-seed-{self.traj}-root",
                              payload={"allocation_id": self.root, "domain": "agenda01",
                                       "authorized": total, "max_occupancy": 1024})), "seed root")
        for key, child in (("exploration", self.explore),
                           ("eval_per_trajectory", self.eval),
                           ("recovery_cap", self.recovery)):
            _ok(store.subdivide_allocation(
                self.dsn, Command(request_id=f"ag01-seed-{self.traj}-{key}",
                                  payload={"parent_id": self.root, "child_id": child,
                                           "authorized": budgets[key],
                                           "domain": "agenda01"})), f"subdivide {key}")
        _ok(store.admit_commitment(
            self.dsn, Command(request_id=f"ag01-setup-{self.traj}-inv",
                              payload={"investigation_id": self.inv,
                                       "objective": f"agenda01 trajectory {self.traj}",
                                       "scope": {"trajectory": self.traj},
                                       "obligations": {"tasks": 8},
                                       "sponsor": "agenda01-experiment",
                                       "origin": "experiment-setup"})), "admit investigation")

    def explore_free(self) -> int:
        row = store.allocation_status(self.dsn, self.explore)
        return int(row["authorized"]) - int(row["consumed"]) - int(row["reserved"])

    def explore_consumed(self) -> int:
        return int(store.allocation_status(self.dsn, self.explore)["consumed"])

    def propose_seed(self, key: str, seed: dict, scope: str) -> None:
        _ok(agenda.propose_option(
            self.dsn, Command(request_id=f"ag01-propose-{self.traj}-{key}-r1",
                              payload={"option_key": key, "scope": scope,
                                       "question": seed["question"], "revision": 1,
                                       "allocation_root": self.explore,
                                       "body": {"seed_class": seed["seed_class"],
                                                "probe": seed["probe"], "cap": seed["cap"],
                                                "expiry": seed["expiry"]}})), f"propose {key}")

    def options(self) -> list:
        with db.read_connect(self.dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT o.option_id, o.scope, o.revision, o.disposition,"
                            " o.disposition_version, r.body FROM agenda_options o"
                            " JOIN agenda_option_revisions r ON r.option_id = o.option_id"
                            " AND r.revision = o.revision ORDER BY o.option_id")
                rows = [dict(r) for r in cur.fetchall()]
                conn.commit()
        return rows

    def links(self) -> list:
        with db.read_connect(self.dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT attempt_id, trajectory, option_id, option_revision,"
                            " probe, intended_decision, replication_slot, effect_identity,"
                            " operation_id, reservation_id, state"
                            " FROM agenda_attempt_links ORDER BY attempt_id")
                rows = [dict(r) for r in cur.fetchall()]
                conn.commit()
        return rows

    def outcomes(self, scored: bool | None = None) -> list:
        with db.read_connect(self.dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if scored is None:
                    cur.execute("SELECT receipt_identity, option_id, attempt_id, observation,"
                                " epoch, grounded, scored FROM agenda_outcomes"
                                " ORDER BY receipt_identity")
                else:
                    cur.execute("SELECT receipt_identity, option_id, attempt_id, observation,"
                                " epoch, grounded, scored FROM agenda_outcomes"
                                " WHERE scored = %s ORDER BY receipt_identity", (scored,))
                rows = [{"receipt": r["receipt_identity"], "option_id": r["option_id"],
                         "attempt_id": r["attempt_id"], "observation": dict(r["observation"]),
                         "epoch": int(r["epoch"]), "grounded": bool(r["grounded"]),
                         "scored": bool(r["scored"])}
                        for r in cur.fetchall()]
                conn.commit()
        return rows

    def launches_for(self, probe: str) -> int:
        with db.read_connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM agenda_attempt_links"
                            " WHERE trajectory = %s AND probe = %s",
                            (self.traj, probe))
                n = int(cur.fetchone()[0])
                conn.commit()
        return n

    def option_spend(self, option_id: str) -> int:
        with db.read_connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(SUM(r.amount), 0) FROM reservations r"
                            " JOIN agenda_attempt_links l ON l.reservation_id = r.id"
                            " WHERE l.option_id = %s AND r.state IN ('held', 'settled')",
                            (option_id,))
                n = int(cur.fetchone()[0])
                conn.commit()
        return n

    def receipts_for(self, operation_id: str) -> list:
        with db.read_connect(self.dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT receipt_identity, operation_id, content_digest, outcome"
                            " FROM receipts WHERE operation_id = %s ORDER BY receipt_identity",
                            (operation_id,))
                rows = [{"receipt": r["receipt_identity"],
                         "operation": r["operation_id"],
                         "digest": r["content_digest"],
                         "outcome": r["outcome"]} for r in cur.fetchall()]
                conn.commit()
        return rows

    def operation(self, operation_id: str) -> dict | None:
        with db.read_connect(self.dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT id, attempt_id, dispatch_state, payload"
                            " FROM operations WHERE id = %s", (operation_id,))
                row = cur.fetchone()
                conn.commit()
        return dict(row) if row is not None else None

    def cursor(self) -> dict:
        with db.read_connect(self.dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT tick, rotation, epoch, dep_versions FROM agenda_cursors"
                            " WHERE trajectory = %s", (self.traj,))
                row = cur.fetchone()
                conn.commit()
        if row is None:
            return {"tick": 0, "rotation": 0, "epoch": 0, "dep_versions": {}}
        return {"tick": int(row["tick"]), "rotation": int(row["rotation"]),
                "epoch": int(row["epoch"]),
                "dep_versions": dict(row["dep_versions"] or {})}

    def load_state(self) -> dict:
        with db.read_connect(self.dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT refused, admitted_fx, tick, ticks, idle,"
                            " feasible_wait, liabilities FROM agenda_traj_state"
                            " WHERE trajectory = %s", (self.traj,))
                row = cur.fetchone()
                conn.commit()
        if row is None:
            return {"refused": [], "admitted_fx": {}, "tick": 0, "ticks": [],
                    "idle": 0, "feasible_wait": 0, "liabilities": []}
        return {"refused": list(row["refused"] or []),
                "admitted_fx": dict(row["admitted_fx"] or {}),
                "tick": int(row["tick"] or 0),
                "ticks": list(row["ticks"] or []),
                "idle": int(row["idle"] or 0),
                "feasible_wait": int(row["feasible_wait"] or 0),
                "liabilities": list(row["liabilities"] or [])}

    def save_state(self, refused: list, admitted_fx: dict, tick: int,
                   progress: dict | None = None) -> None:
        progress = progress or {}
        with db.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO agenda_traj_state (trajectory, refused, admitted_fx,"
                            " tick, ticks, idle, feasible_wait, liabilities)"
                            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                            " ON CONFLICT (trajectory) DO UPDATE SET refused = EXCLUDED.refused,"
                            " admitted_fx = EXCLUDED.admitted_fx, tick = EXCLUDED.tick,"
                            " ticks = EXCLUDED.ticks, idle = EXCLUDED.idle,"
                            " feasible_wait = EXCLUDED.feasible_wait,"
                            " liabilities = EXCLUDED.liabilities, updated_at = now()",
                            (self.traj, store._j(refused), store._j(admitted_fx), tick,
                             store._j(list(progress.get("ticks") or [])),
                             int(progress.get("idle") or 0),
                             int(progress.get("feasible_wait") or 0),
                             store._j(list(progress.get("liabilities") or []))))
                conn.commit()

    def apply_dep_bump(self, dep: str, version: int) -> None:
        _ok(agenda.note_dep_version(
            self.dsn, Command(request_id=f"ag01-dep-{self.traj}-{dep}-{version}",
                              payload={"trajectory": self.traj, "dep": dep,
                                       "version": int(version)})), f"dep bump {dep}")

    def admit_initial(self, tick: int, key: str, probe: str, intended: str,
                      deps: dict, cost: int, revision: int, policy: str,
                      digest: str, plan: dict, due: int):
        return agenda.select_and_admit(
            self.dsn, Command(request_id=f"ag01-admit-{self.traj}-t{tick}-{key}-{probe}",
                              payload={"trajectory": self.traj, "option_id": key,
                                       "expected_option_revision": revision,
                                       "probe": probe, "intended_decision": intended,
                                       "replication_slot": None,
                                       "policy_version": policy, "input_digest": digest,
                                       "dep_versions": dict(deps), "cost": cost,
                                       "observed_plan": plan["observed"],
                                       "product_plan": plan["product"],
                                       "dud_plan": plan["dud"], "due_epoch": due}))

    def admit_continuation(self, tick: int, key: str, parent_attempt: str,
                           receipts: list, next_probe: str, residual: dict,
                           slot: str | None, cost: int, revision: int,
                           policy: str, digest: str, intended: str, plan: dict,
                           due: int, decl: dict, rep: dict | None,
                           before: str, after: str, stop: dict):
        return agenda.submit_continuation(
            self.dsn, Command(
                request_id=f"ag01-cont-{self.traj}-t{tick}-{key}-{next_probe}",
                payload={"option_id": key, "parent_attempt": parent_attempt,
                         "observation_refs": list(receipts), "next_probe": next_probe,
                         "intended_decision": intended,
                         "residual_question": dict(residual),
                         "policy_version": policy, "input_digest": digest,
                         "expected_option_revision": revision,
                         "next_probe_decl": decl, "replication": rep,
                         "decision_before": before, "decision_after": after,
                         "stop_condition": stop,
                         "replication_slot": slot, "cost": cost,
                         "observed_plan": plan["observed"],
                         "product_plan": plan["product"],
                         "dud_plan": plan["dud"], "due_epoch": due}))

    def dispatch_probe(self, operation_id: str):
        return broker.dispatch_operation(
            self.dsn, operation_id,
            launchers={launcher.ADAPTER_KEY: self.sim})

    def idle(self, tick: int, policy_version: str, reason: str):
        return agenda.note_idle(
            self.dsn, Command(request_id=f"ag01-idle-{self.traj}-t{tick}",
                              payload={"trajectory": self.traj,
                                       "policy_version": policy_version, "reason": reason}))

    def record(self, key: str, attempt: str, receipt: str, scored: bool = True):
        return agenda.record_outcome(
            self.dsn, Command(request_id=f"ag01-observe-{self.traj}-{receipt}",
                              payload={"option_id": key, "attempt_id": attempt,
                                       "receipt_identity": receipt, "scored": scored}))

    def charge_aux(self, label: str, amount: int, allocation_id: str) -> str:
        """Book a non-probe charge: the eval close-out and each recovery drain.

        This is a charge, not an operation. Nothing is dispatched, no adapter
        runs and no receipt is ever written, so there is no operations row
        behind it and there must not be one: the checker requires every
        operations row in the ledger to carry a receipt
        (`checker.check_trace`, effect-without-receipt), and eval-final
        produces none.

        The charge therefore reserves and settles on its own identity in one
        transaction, the shape `agenda._agenda_charge_decision` uses for the
        per-tick decision cost. `store.reserve` is not usable here because it
        refuses an operation_id that is not already a row, and this charge
        never becomes one. Its identity is the returned string, which callers
        record in their own ledgers and liabilities.
        """
        charge_id = f"ag01:{self.traj}:{label}"
        res_id = f"{charge_id}:res"

        def _fn(cur, control):
            store._take_reservation(cur, allocation_id, res_id, int(amount), charge_id)
            store._settle_amount(cur, res_id, "success", int(amount))
            return (ResultCode.APPLIED, f"charged {amount}",
                    {"charge_id": charge_id, "amount": int(amount)}, [], [])

        _ok(store.transact(
            self.dsn,
            Command(request_id=f"{charge_id}:charge", payload={
                "allocation_id": allocation_id, "reservation_id": res_id,
                "amount": int(amount), "charge_id": charge_id}), _fn),
            f"charge {label}")
        return charge_id

    def export_ledger(self) -> dict:
        with db.read_connect(self.dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT id, attempt_id, dispatch_state, execution_version"
                            " FROM operations WHERE id LIKE %s ORDER BY id",
                            (f"ag01:{self.traj}:%",))
                ops = [{"id": r["id"], "attempt_id": r["attempt_id"],
                        "dispatch_state": r["dispatch_state"],
                        "execution_version": r["execution_version"]}
                       for r in cur.fetchall()]
                cur.execute("SELECT id, allocation_id, operation_id, amount, state"
                            " FROM reservations WHERE id LIKE %s ORDER BY id",
                            (f"ag01:{self.traj}:%",))
                reservations = [{"id": r["id"], "allocation_id": r["allocation_id"],
                                 "operation_id": r["operation_id"],
                                 "amount": int(r["amount"]), "state": r["state"]}
                                for r in cur.fetchall()]
                cur.execute("SELECT id, parent_id, authorized, consumed, reserved"
                            " FROM allocations WHERE id LIKE %s ORDER BY id",
                            (f"{self.root}%",))
                allocations = [{"id": r["id"], "parent_id": r["parent_id"],
                                "authorized": int(r["authorized"]),
                                "consumed": int(r["consumed"]),
                                "reserved": int(r["reserved"])} for r in cur.fetchall()]
                cur.execute("SELECT receipt_identity, operation_id, content_digest, outcome"
                            " FROM receipts WHERE receipt_identity LIKE %s ORDER BY 1",
                            (f"{self.traj}:rc:%",))
                receipts = [{"receipt": r["receipt_identity"],
                             "operation_id": r["operation_id"],
                             "content_digest": r["content_digest"],
                             "outcome": r["outcome"]} for r in cur.fetchall()]
                cur.execute("SELECT attempt_id, trajectory, option_id, probe,"
                            " intended_decision, replication_slot, effect_identity,"
                            " operation_id, reservation_id, state"
                            " FROM agenda_attempt_links WHERE trajectory = %s"
                            " ORDER BY attempt_id", (self.traj,))
                links = [dict(r) for r in cur.fetchall()]
                cur.execute("SELECT trajectory, tick, policy_version, selection, reasons"
                            " FROM agenda_decisions WHERE trajectory = %s ORDER BY tick",
                            (self.traj,))
                decisions = [{"tick": int(r["tick"]), "policy": r["policy_version"],
                              "selection": dict(r["selection"]),
                              "reasons": list(r["reasons"])} for r in cur.fetchall()]
                cur.execute("SELECT o.receipt_identity, o.option_id, o.attempt_id,"
                            " o.observation, o.epoch, o.scored FROM agenda_outcomes o"
                            " JOIN agenda_attempt_links l"
                            " ON l.attempt_id = o.attempt_id WHERE l.trajectory = %s"
                            " ORDER BY o.receipt_identity", (self.traj,))
                outcomes = [{"receipt": r["receipt_identity"], "option_id": r["option_id"],
                             "observation": dict(r["observation"]),
                             "epoch": int(r["epoch"]), "scored": bool(r["scored"])}
                            for r in cur.fetchall()]
                cur.execute("SELECT COUNT(*) AS n FROM receipt_conflicts"
                            " WHERE receipt_identity LIKE %s", (f"{self.traj}:rc:%",))
                conflicts = int(cur.fetchone()["n"])
                cursor = self.cursor()
                conn.commit()
        return {"ops": ops, "reservations": reservations, "allocations": allocations,
                "receipts": receipts, "links": links, "decisions": decisions,
                "outcomes": outcomes, "conflicts": conflicts, "cursor": cursor}


def _option_scope(world: dict, probe_key: str) -> str:
    observes = world["probes"][probe_key]["observes"]
    if observes:
        return world["props"][observes[0]]["scope"]
    return "s0"


def _prereq_met(probe: dict, avail: set, deps: dict) -> bool:
    pre = probe.get("prereq")
    if pre is None:
        return True
    if "instrument" in pre:
        return pre["instrument"] in avail
    if "dep_version" in pre:
        dep, want = pre["dep_version"]
        return deps.get(dep, 1) >= want
    return False


def _translate_prereqs(probe: dict) -> list:
    pre = probe.get("prereq")
    if pre is None:
        return []
    if "instrument" in pre:
        return [{"dep": f"instrument:{pre['instrument']}", "min_version": 1}]
    if "dep_version" in pre:
        dep, want = pre["dep_version"]
        return [{"dep": dep, "min_version": int(want)}]
    return []


def _deps_fingerprint(deps: dict) -> str:
    return "|".join(f"{k}={deps[k]}" for k in sorted(deps))


def _avail_at(world: dict, tick: int) -> set:
    return {k for k, v in world["instruments"].items()
            if v["available_at"] is not None and v["available_at"] <= tick}


def _base_deps(world: dict) -> dict:
    return {spec["dep"]: 1 for spec in world["props"].values()}


def simulate_value(world: dict, probe_key: str, sample_index: int, prop: str):
    probe = world["probes"][probe_key]
    truth = grader.latent_bit(world["world_id"], prop)
    if draw(world["rng_seed"], probe_key, sample_index, prop) < probe["noise"]:
        return not truth
    return truth


def resolve_policy(arm: str):
    import importlib
    mod = importlib.import_module("settlement.agenda_policy")
    return getattr(mod, f"decide_{arm}")


def _plan_for(world: dict, probe_key: str) -> dict:
    spec = world["probes"][probe_key]
    observed = [{"prop": prop, "scope": world["props"][prop]["scope"],
                 "dep": world["props"][prop]["dep"]}
                for prop in spec["observes"]]
    return {"observed": observed, "product": list(spec.get("product") or []),
            "dud": not observed and not spec.get("product")}


def _expected_receipts(base: str, plan: dict) -> list:
    out = [f"{base}:{prop['prop']}" for prop in plan["observed"]]
    if plan["product"]:
        out.append(f"{base}:product")
    if plan["dud"]:
        out.append(f"{base}:dud")
    return out


def _public_from_content(content: dict, scored: bool) -> dict | None:
    if content.get("kind") != "observation":
        return None
    value = content.get("value")
    return observations.public_observation(
        content["prop"], {"scope": content.get("scope"), "dep": content.get("dep"),
                          "dep_version": content.get("dep_version")},
        True if value == "true" else (False if value == "false" else "unknown"),
        content.get("source_attempt", ""), content.get("receipt", ""),
        int(content.get("epoch", 0)), scored)


def _tick_evaluated(decision: dict, candidates: list) -> list:
    kinds = {c["id"]: c.get("kind") for c in candidates if isinstance(c, dict)}
    return [{"id": entry.get("id"), "kind": kinds.get(entry.get("id")),
             "skipped": entry.get("skipped")}
            for entry in (decision.get("evaluated") or [])
            if isinstance(entry, dict)]


def _progress(st: dict) -> dict:
    return {"ticks": list(st["ticks"]), "idle": int(st["idle"]),
            "feasible_wait": int(st["feasible_wait"]),
            "liabilities": list(st["liabilities"])}


def _sort_public(st: dict) -> None:
    st["scored"].sort(key=lambda o: (o.get("receipt", ""), o.get("prop", "")))
    st["drained"].sort(key=lambda o: (o.get("receipt", ""), o.get("prop", "")))
    st["drained_products"].sort(key=lambda o: str(o.get("operation_id", "")))


def _ingest_due(backend: AgendaBackend, world: dict, st: dict, tick: int,
                scored: bool) -> list:
    now = int(backend.cursor()["epoch"])
    fresh = []
    for attempt, info in sorted(st["launched"].items()):
        if info["due"] > now:
            continue
        fresh.extend(_ingest_due_single(backend, world, st, attempt, scored))
    return fresh


def _dispatch_launch(backend: AgendaBackend, operation_id: str,
                     expected: list) -> None:
    have = {r["receipt"] for r in backend.receipts_for(operation_id)}
    if all(rc in have for rc in expected):
        return
    status = backend.dispatch_probe(operation_id)
    if status.dispatch_state == "prepared":
        raise RuntimeError(f"dispatch {operation_id} refused: {status}")
    have = {r["receipt"] for r in backend.receipts_for(operation_id)}
    missing = [rc for rc in expected if rc not in have]
    if missing:
        raise RuntimeError(f"dispatch {operation_id} left receipts missing: {missing}")


def _launch(backend: AgendaBackend, world: dict, st: dict, tick: int, key: str,
            probe_key: str, attempt: str, op: str, res: str, cost: int,
            plan: dict, due: int) -> None:
    base = f"{backend.traj}:rc:{attempt}"
    expected = _expected_receipts(base, plan)
    _dispatch_launch(backend, op, expected)
    st["launched"][attempt] = {"probe": probe_key, "option": key, "op": op,
                               "res": res, "amount": cost, "due": due,
                               "receipts": expected, "recorded": []}
    st["admitted_fx"][f"{key}|{probe_key}"] = _deps_fingerprint(st["deps"])
    if due <= int(backend.cursor()["epoch"]):
        _ingest_due_single(backend, world, st, attempt, True)


def _ingest_due_single(backend: AgendaBackend, world: dict, st: dict,
                       attempt: str, scored: bool) -> list:
    info = st["launched"][attempt]
    fresh = []
    for receipt in info["receipts"]:
        if receipt in info["recorded"]:
            continue
        result = backend.record(info["option"], attempt, receipt, scored)
        if result.code.value == "already_applied":
            info["recorded"].append(receipt)
            continue
        _ok(result, f"record {receipt}")
        info["recorded"].append(receipt)
        obs = (result.data or {}).get("observation") or {}
        if obs.get("kind") == "product-claims":
            if scored:
                st["products"].update(dict(obs.get("claims") or {}))
            else:
                st["drained_products"].append(
                    {"operation_id": info["op"],
                     "claims": dict(obs.get("claims") or {})})
            continue
        public = _public_from_content(obs, scored)
        if public is None:
            continue
        if scored:
            st["scored"].append(public)
        else:
            st["drained"].append(public)
        fresh.append(public)
    _sort_public(st)
    return fresh


def _descriptors(backend: AgendaBackend, world: dict, st: dict) -> list:
    links = {l["attempt_id"]: l for l in backend.links()}
    bound = {(l["option_id"], l["probe"], l["replication_slot"]) for l in backend.links()}
    groups: dict = {}
    for row in backend.outcomes(scored=True):
        obs = row["observation"]
        if obs.get("kind") != "observation":
            continue
        if obs.get("value") not in ("true", "false") or row["grounded"]:
            continue
        if obs.get("dep_version") != st["deps"].get(obs.get("dep"), 1):
            continue
        link = links.get(row["attempt_id"])
        if link is None:
            continue
        opt = st["options"].get(row["option_id"])
        if opt is None or obs.get("scope") != opt["scope"]:
            continue
        groups.setdefault((row["option_id"], link["probe"]), []).append(row["receipt"])
    out = []
    for (key, parent_probe), receipts in sorted(groups.items()):
        spec = world["probes"][parent_probe]
        taken = backend.launches_for(parent_probe)
        slot = None
        if spec.get("followup") is not None:
            nxt = spec["followup"]
        elif spec.get("replication") is not None and taken < spec["replication"]:
            nxt = parent_probe
            slot = f"repl:{parent_probe}:{taken}-of-{spec['replication']}"
        elif taken < 2:
            nxt = parent_probe
        else:
            continue
        if (key, nxt, slot) in bound:
            continue
        sig = [key, nxt, slot, sorted(receipts)]
        if sig in st["refused"]:
            continue
        scored_rows = {r["receipt"]: r for r in backend.outcomes(scored=True)}
        first = scored_rows[receipts[0]]
        first_obs = first["observation"]
        residual = {"prop": first_obs["prop"], "scope": st["options"][key]["scope"],
                    "dep": first_obs["dep"]}
        cons = world["probes"][nxt]["consequences"]
        parent_link = next(l for l in backend.links() if l["attempt_id"] == first["attempt_id"])
        rep = None
        if slot is not None:
            rep = {"protocol": slot, "total": spec["replication"], "completed": taken,
                   "declared_before_first_sample": True,
                   "stop_reached": taken >= spec["replication"]}
        out.append({"option_id": key, "next_probe": nxt, "slot": slot, "receipts": receipts,
                    "sig": sig, "parent_attempt": first["attempt_id"], "residual": residual,
                    "consequences": cons, "replication": rep,
                    "decision_before": parent_link["intended_decision"],
                    "decision_after": f"continue-{nxt}:{cons.get(first_obs['value'], '?')}"})
    return out


def _candidates(backend: AgendaBackend, world: dict, st: dict, tick: int) -> list:
    out = []
    for opt in backend.options():
        if opt["disposition"] != "open":
            continue
        body = dict(opt["body"]) if isinstance(opt["body"], dict) else {}
        probe_key, cap = body["probe"], body["cap"]
        spec = world["probes"][probe_key]
        if tick > body["expiry"] or not _prereq_met(spec, st["avail"], st["deps"]):
            continue
        if backend.option_spend(opt["option_id"]) + spec["cost"] > cap:
            continue
        if st["admitted_fx"].get(f"{opt['option_id']}|{probe_key}") == _deps_fingerprint(st["deps"]):
            continue
        out.append({"id": opt["option_id"], "tie_key": opt["option_id"],
                    "seed_class": body["seed_class"], "kind": "initial",
                    "probe_id": probe_key, "cost": spec["cost"], "cap": cap,
                    "scope": opt["scope"], "disposition": "open",
                    "expiry_epoch": body["expiry"],
                    "prerequisites": _translate_prereqs(spec),
                    "allocation_root": backend.explore,
                    "spent": backend.option_spend(opt["option_id"]),
                    "effect_identity": None, "revision": int(opt["revision"])})
    for desc in _descriptors(backend, world, st):
        opt = next(o for o in backend.options() if o["option_id"] == desc["option_id"])
        body = dict(opt["body"])
        spec = world["probes"][desc["next_probe"]]
        if tick > body["expiry"] or not _prereq_met(spec, st["avail"], st["deps"]):
            continue
        if backend.option_spend(opt["option_id"]) + spec["cost"] > body["cap"]:
            continue
        question = dict(desc["residual"])
        out.append({"id": opt["option_id"], "tie_key": opt["option_id"],
                    "seed_class": body["seed_class"], "kind": "continuation",
                    "probe_id": desc["next_probe"], "cost": spec["cost"], "cap": body["cap"],
                    "scope": opt["scope"], "disposition": "open",
                    "expiry_epoch": body["expiry"],
                    "prerequisites": _translate_prereqs(spec),
                    "allocation_root": backend.explore,
                    "spent": backend.option_spend(opt["option_id"]),
                    "effect_identity": None, "revision": int(opt["revision"]),
                    "continuation": {
                        "parent_attempt": desc["parent_attempt"],
                        "cited": [{"prop": r["observation"]["prop"],
                                   "scope": r["observation"]["scope"],
                                   "dep": r["observation"]["dep"],
                                   "dep_version": r["observation"]["dep_version"]}
                                  for r in backend.outcomes(scored=True)
                                  if r["receipt"] in desc["receipts"]],
                        "residual_question": question,
                        "next_probe": {
                            "id": desc["next_probe"], "question": question,
                            "outcomes": [{"value": "true",
                                          "consequence": spec["consequences"]["true"]},
                                         {"value": "false",
                                          "consequence": spec["consequences"]["false"]}]},
                        "scope": opt["scope"],
                        "decision_before": desc["decision_before"],
                        "decision_after": desc["decision_after"],
                        "replication": desc["replication"],
                        "stop_condition": {"kind": "max-samples",
                                           "samples": (world["probes"][desc["next_probe"]]
                                                       .get("replication") or 2)}}})
    return out


def _negatives(backend: AgendaBackend) -> list:
    probes = {l["attempt_id"]: l["probe"] for l in backend.links()}
    out = []
    for row in backend.outcomes(scored=True):
        obs = row["observation"]
        if obs.get("value") != "false":
            continue
        out.append({"probe": probes.get(row["attempt_id"], ""),
                    "scope": obs.get("scope"), "dep": obs.get("dep"),
                    "dep_version": obs.get("dep_version")})
    return out


def _policy_state(backend: AgendaBackend, st: dict, tick: int) -> dict:
    instruments = {k: {"available": k in st["avail"]} for k in st["instruments"]}
    dep_versions = dict(st["deps"])
    for key, info in instruments.items():
        dep_versions[f"instrument:{key}"] = 1 if info["available"] else 0
    consumed = backend.explore_consumed()
    return {"epoch": tick + 1, "dep_versions": dep_versions,
            "spent": {backend.explore: consumed}, "caps": {backend.explore: 64},
            "remaining": backend.explore_free(), "pending": [],
            "negatives": _negatives(backend), "instruments": instruments}


def _rebuild_state(backend: AgendaBackend, world: dict) -> dict:
    saved = backend.load_state()
    st: dict = {"instruments": dict(world["instruments"]),
                "deps": dict(_base_deps(world)),
                "scored": [], "products": {}, "drained_products": [],
                "launched": {}, "refused": list(saved["refused"]),
                "admitted_fx": dict(saved["admitted_fx"]),
                "options": {}, "ticks": list(saved.get("ticks") or []),
                "idle": int(saved.get("idle") or 0),
                "feasible_wait": int(saved.get("feasible_wait") or 0),
                "drained": [], "liabilities": list(saved.get("liabilities") or [])}
    for opt in backend.options():
        st["options"][opt["option_id"]] = {"scope": opt["scope"]}
    attempt_op = {l["attempt_id"]: l["operation_id"] for l in backend.links()}
    recorded: dict = {}
    for row in backend.outcomes():
        obs = row["observation"]
        recorded.setdefault(row["attempt_id"], []).append(row["receipt"])
        if not row["scored"]:
            if obs.get("kind") == "product-claims":
                st["drained_products"].append(
                    {"operation_id": attempt_op.get(row["attempt_id"], ""),
                     "claims": dict(obs.get("claims") or {})})
                continue
            public = _public_from_content(obs, False)
            if public is not None:
                st["drained"].append(public)
            continue
        if obs.get("kind") == "product-claims":
            st["products"].update(dict(obs.get("claims") or {}))
            continue
        public = _public_from_content(obs, True)
        if public is None:
            continue
        if obs.get("value") in ("true", "false"):
            st["scored"].append(public)
    _sort_public(st)
    for link in backend.links():
        receipts = [r["receipt"] for r in backend.receipts_for(link["operation_id"])]
        if not receipts:
            continue
        op = backend.operation(link["operation_id"]) or {}
        payload = dict(op.get("payload") or {})
        epoch = int(((payload.get("payload") or {}).get("input") or {}).get("epoch", 0))
        st["launched"][link["attempt_id"]] = {
            "probe": link["probe"], "option": link["option_id"],
            "op": link["operation_id"], "res": link["reservation_id"],
            "due": epoch, "receipts": receipts,
            "recorded": list(recorded.get(link["attempt_id"], []))}
    return st


def _resume_incomplete(backend: AgendaBackend, world: dict, st: dict) -> None:
    for link in backend.links():
        attempt = link["attempt_id"]
        expected = _expected_receipts(f"{backend.traj}:rc:{attempt}",
                                      _plan_for(world, link["probe"]))
        if attempt not in st["launched"]:
            op = backend.operation(link["operation_id"]) or {}
            payload = dict(op.get("payload") or {})
            epoch = int(((payload.get("payload") or {}).get("input") or {})
                        .get("epoch", 0))
            st["launched"][attempt] = {
                "probe": link["probe"], "option": link["option_id"],
                "op": link["operation_id"], "res": link["reservation_id"],
                "due": epoch, "receipts": expected, "recorded": []}
        _dispatch_launch(backend, link["operation_id"], expected)


def _attribute_open_exposure(ledger: dict, liabilities: list) -> None:
    have = {entry.get("operation_id") for entry in liabilities}
    ops = {op["id"]: op for op in ledger.get("ops", [])}
    by_op: dict = {}
    for receipt in ledger.get("receipts", []):
        by_op.setdefault(receipt["operation_id"], []).append(receipt["outcome"])
    for res in ledger.get("reservations", []):
        if res.get("state") == "settled" or res.get("operation_id") in have:
            continue
        outcomes = sorted(set(by_op.get(res.get("operation_id"), [])))
        if outcomes:
            reason = f"unresolved {'/'.join(outcomes)} receipt retains exposure"
        else:
            state = ops.get(res.get("operation_id"), {}).get("dispatch_state",
                                                              "unknown")
            reason = f"undispatched {state} operation retains exposure"
        liabilities.append({"operation_id": res.get("operation_id"), "reason": reason})


def _drive(world: dict, arm: str, tie: int, policy_fn, policy_version: str,
           manifest_doc: dict, manifest_hash: str, budgets: dict,
           backend: AgendaBackend, tick_start: int = 0,
           max_ticks: int | None = None) -> dict:
    traj = backend.traj
    horizon = world["ticks"]
    orders = manifest_doc["tie_orders"].get(world["world_id"])
    if orders is None:
        seeds = [s["option_key"] for s in world["seeds"]]
        orders = {"t0": seeds, "t1": list(reversed(seeds))}
    tie_order = orders[f"t{tie}"]
    if tick_start == 0:
        backend.setup(budgets)
        st = _rebuild_state(backend, world)
        for seed in world["seeds"]:
            scope = _option_scope(world, seed["probe"])
            backend.propose_seed(seed["option_key"], seed, scope)
            st["options"][seed["option_key"]] = {"scope": scope}
    else:
        st = _rebuild_state(backend, world)
        _resume_incomplete(backend, world, st)
    st["deps"] = dict(backend.cursor().get("dep_versions") or st["deps"])
    end_reason = "horizon"
    stop_at = horizon if max_ticks is None else min(horizon, tick_start + max_ticks)
    for tick in range(tick_start, stop_at):
        if backend.explore_free() < budgets["decision_cost"]:
            end_reason = "unfundable"
            break
        st["avail"] = _avail_at(world, tick)
        applied = []
        for event in world["events"]:
            if event["tick"] == tick and event["kind"] == "dep-bump":
                backend.apply_dep_bump(event["dep"], int(event["to"]))
                applied.append({"kind": "dep-bump", "dep": event["dep"],
                                "to": int(event["to"])})
        cursor = backend.cursor()
        st["deps"] = dict(cursor.get("dep_versions") or st["deps"])
        _ingest_due(backend, world, st, tick, True)
        candidates = agenda_policy.rotation_order(
            _candidates(backend, world, st, tick),
            cursor["rotation"], list(tie_order))["ordered"]
        descs = {}
        for candidate in candidates:
            if candidate["kind"] == "continuation":
                descs[(candidate["id"], candidate["probe_id"])] = candidate["continuation"]
        state = _policy_state(backend, st, tick)
        packet = {"candidates": candidates, "observations": st["scored"],
                  "state": state, "cursor": cursor["rotation"],
                  "tie_order": list(tie_order)}
        digest = payload_digest(packet)
        decision = dict(policy_fn(packet) or {"decision": "idle"})
        action, entry = "idle", None
        key = (decision.get("selection") or {}).get("option_id")
        reason = ";".join(decision.get("reasons", ["idle"]))
        dec_op, probe_op, idle_reason = None, None, None
        if decision.get("decision") == "select" and key is not None:
            entry = next((c for c in candidates if c["id"] == key), None)
        if entry is None:
            idle_reason = reason if decision.get("decision") != "select" else "ineligible-pick"
            result = backend.idle(tick, policy_version,
                                  idle_reason or "no selectable candidate")
            _ok(result, "idle")
            dec_op = result.data["dec_op"]
            action = "idle"
            st["idle"] += 1
            if candidates:
                st["feasible_wait"] += 1
        elif entry["kind"] == "initial":
            spec = world["probes"][entry["probe_id"]]
            plan = _plan_for(world, entry["probe_id"])
            due = int(cursor["epoch"]) + int(spec.get("delay", 0))
            result = backend.admit_initial(
                tick, key, entry["probe_id"], f"execute-{entry['probe_id']}",
                state["dep_versions"], entry["cost"], entry["revision"],
                policy_version, digest, plan, due)
            if result.code == ResultCode.INSUFFICIENT_RESOURCES:
                end_reason = "unfundable"
                st["ticks"].append({"tick": tick, "events": [], "wakes": [],
                                    "eligible": [c["id"] for c in candidates],
                                    "decision": {"action": "idle", "option_key": key,
                                               "reason": f"unfundable: {result.detail}",
                                               "idle_reason": None,
                                               "evaluated": _tick_evaluated(
                                                   decision, candidates)},
                                    "dec_op": None, "probe_op": None})
                break
            if result.code == ResultCode.ALREADY_APPLIED:
                action, idle_reason = "idle", f"duplicate-effect:{key}"
                dec_op = (result.data or {}).get("dec_op")
                st["idle"] += 1
            else:
                _ok(result, f"admit {key}")
                dec_op, probe_op = result.data["dec_op"], result.data["probe_op"]
                _launch(backend, world, st, tick, key, entry["probe_id"],
                        result.data["attempt_id"], probe_op, probe_op + ":r",
                        entry["cost"], plan, due)
                action = "probe"
        else:
            cont = descs[(entry["id"], entry["probe_id"])]
            desc = next(d for d in _descriptors(backend, world, st)
                        if d["option_id"] == entry["id"]
                        and d["next_probe"] == entry["probe_id"])
            spec = world["probes"][entry["probe_id"]]
            plan = _plan_for(world, entry["probe_id"])
            due = int(cursor["epoch"]) + int(spec.get("delay", 0))
            rep = cont.get("replication")
            decl = {"id": entry["probe_id"], "question": dict(cont["residual_question"]),
                    "outcomes": [{"value": "true",
                                  "consequence": spec["consequences"]["true"]},
                                 {"value": "false",
                                  "consequence": spec["consequences"]["false"]}]}
            result = backend.admit_continuation(
                tick, key, cont["parent_attempt"], desc["receipts"],
                entry["probe_id"], cont.get("residual_question", {}),
                (cont.get("replication") or {}).get("protocol"), entry["cost"],
                entry["revision"], policy_version, digest,
                f"continue-{entry['probe_id']}", plan, due, decl, rep,
                str(cont.get("decision_before", "")),
                str(cont.get("decision_after", "")),
                {"kind": "max-samples",
                 "samples": int(spec.get("replication") or 2)})
            if result.code == ResultCode.INSUFFICIENT_RESOURCES:
                end_reason = "unfundable"
                st["ticks"].append({"tick": tick, "events": [], "wakes": [],
                                    "eligible": [c["id"] for c in candidates],
                                    "decision": {"action": "idle", "option_key": key,
                                               "reason": f"unfundable: {result.detail}",
                                               "idle_reason": None,
                                               "evaluated": _tick_evaluated(
                                                   decision, candidates)},
                                    "dec_op": None, "probe_op": None})
                break
            if result.code == ResultCode.ALREADY_APPLIED:
                action, idle_reason = "idle", f"duplicate-effect:{key}"
                dec_op = (result.data or {}).get("dec_op")
                st["idle"] += 1
            elif result.code == ResultCode.INVALID_INPUT:
                refused = list(st["refused"]) + [desc["sig"]]
                st["refused"] = refused
                backend.save_state(refused, st["admitted_fx"], tick, _progress(st))
                dec_op = result.data["dec_op"]
                action, idle_reason = "idle", f"fence-refused:{result.detail}"
                st["idle"] += 1
                if candidates:
                    st["feasible_wait"] += 1
            else:
                _ok(result, f"continue {key}")
                dec_op, probe_op = result.data["dec_op"], result.data["probe_op"]
                _launch(backend, world, st, tick, key, entry["probe_id"],
                        result.data["attempt_id"], probe_op, probe_op + ":r",
                        entry["cost"], plan, due)
                action = "probe"
        st["ticks"].append({"tick": tick, "events": applied, "wakes": [],
                            "eligible": [c["id"] for c in candidates],
                            "decision": {"action": action, "option_key": key,
                                       "reason": reason, "idle_reason": idle_reason,
                                       "evaluated": _tick_evaluated(decision,
                                                                    candidates)},
                            "dec_op": dec_op, "probe_op": probe_op})
        backend.save_state(st["refused"], st["admitted_fx"], tick + 1, _progress(st))
    finished = stop_at >= horizon and end_reason == "horizon"
    if not finished:
        return {"complete": False, "end_reason": end_reason, "traj_id": traj,
                "world_id": world["world_id"], "arm": arm, "tie": tie}
    rec_n = 0
    for attempt, info in sorted(st["launched"].items()):
        if all(rc in info["recorded"] for rc in info["receipts"]):
            continue
        try:
            backend.charge_aux(f"rec-{attempt}", 1, backend.recovery)
        except SettlementError:
            st["liabilities"].append({"operation_id": info["op"],
                                      "reason": "recovery-cap-exhausted"})
            continue
        rec_n += 1
        _ingest_due_single(backend, world, st, attempt, False)
    backend.charge_aux("eval-final", len(world["tasks"]), backend.eval)
    grade = grader.grade(st["scored"], st["products"], world)
    ledger = backend.export_ledger()
    _attribute_open_exposure(ledger, st["liabilities"])
    consumed = {a["id"]: a["consumed"] for a in ledger["allocations"]}
    trace = {
        "manifest_sha256": manifest_hash, "traj_id": traj,
        "sources": dict(manifest_doc.get("sources") or {}),
        "files": dict(manifest_doc.get("files") or {}),
        "world_id": world["world_id"], "family": world["family"],
        "variant": world["variant"], "arm": arm, "tie": tie,
        "policy_version": policy_version, "backend": type(backend).__name__,
        "rng_seed": world["rng_seed"], "end_reason": end_reason,
        "ticks": st["ticks"], "observations": st["scored"],
        "products": st["products"], "pending_drained": st["drained"],
        "drained_products": st["drained_products"], "ledger": ledger,
        "option_spend": {l["option_id"]: backend.option_spend(l["option_id"])
                         for l in backend.links()},
        "totals": {
            "explore_spent": consumed.get(backend.explore, 0),
            "eval_spent": consumed.get(backend.eval, 0),
            "recovery_spent": consumed.get(backend.recovery, 0),
            "idle_ticks": st["idle"], "feasible_waiting": st["feasible_wait"],
            "liabilities": st["liabilities"]},
        "grade": grade, "complete": True}
    return trace


def _resolve_world(world):
    if isinstance(world, dict):
        return world
    try:
        return worlds.get_world(world)
    except KeyError:
        for dev in worlds.dev_worlds():
            if dev["world_id"] == world:
                return dev
        raise


def _traj_for(world: dict, arm: str, tie: int) -> str:
    if world["world_id"].startswith("dev"):
        return f"dev{world['variant']:02d}_{arm.lower()}_t{tie}"
    return traj_ids(world["family"] * 4 + world["variant"], world["variant"], arm, tie)


def run_trajectory(base_dsn: str, world, arm: str, tie: int, policy_fn,
                   policy_version: str, manifest_doc: dict, manifest_hash: str,
                   out_dir, budgets: dict | None = None, keep_db: bool = False,
                   migrations_dir=None, max_ticks: int | None = None,
                   resume: bool = False) -> dict:
    world = _resolve_world(world)
    budgets = budgets or manifest.BUDGETS
    traj = _traj_for(world, arm, tie)
    db_name = f"agenda01_{traj}"
    fresh = not resume
    if fresh:
        try:
            drop_db(base_dsn, db_name)
        except Exception:
            pass
        dsn = create_db(base_dsn, db_name)
    else:
        dsn = swap_dbname(base_dsn, db_name)
        try:
            saved = AgendaBackend(dsn, traj, None).load_state()
        except Exception as exc:
            raise SettlementError(
                f"resume refused: trajectory database {db_name} holds no"
                f" saved progress ({type(exc).__name__})") from exc
        if not saved["ticks"] and saved["tick"] == 0:
            raise SettlementError(
                f"resume refused: trajectory database {db_name} holds no"
                " saved progress")
    try:
        if migrations_dir is None:
            migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
        if fresh:
            db.apply_migrations(dsn, migrations_dir)
        sim = launcher.AgendaProbeLauncher(
            dsn,
            observe=lambda probe, sample, prop: simulate_value(world, probe, sample, prop),
            claim=lambda prop: grader.latent_bit(world["world_id"], prop))
        backend = AgendaBackend(dsn, traj, sim)
        start = 0 if fresh else backend.load_state()["tick"]
        trace = _drive(world, arm, tie, policy_fn, policy_version, manifest_doc,
                       manifest_hash, budgets, backend, tick_start=start,
                       max_ticks=max_ticks)
        trace["db"] = db_name
        if trace.get("complete"):
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            (Path(out_dir) / f"{traj}.json").write_text(json.dumps(trace, indent=2,
                                                                  sort_keys=True))
        return trace
    finally:
        if not keep_db:
            drop_db(base_dsn, db_name)
