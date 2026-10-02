"""M2 durable frontier of admissible investigation work.

The study freezes mission plus environments. It never dictates the next
investigation. The executable program chooses its own next work from this
frontier through its STEP bytes, inside explicit authority. The frontier,
observations, pending effects, outcomes and obligations persist in one
JSON store so an investigation survives a restart. Storage exists only
for restart survival.

Replay reveals a recorded outcome only where the stored identity matches
exactly. Anything unseen returns unsupported. Prediction is a separate
evidence class and never counts as a replay result. Readiness is
event-driven through ready_events. This module starts no loops, timers
or schedulers.
"""

from __future__ import annotations

import hashlib
import json
import os

FRONTIER_VERSION = "invl02-frontier-v1"
NAMESPACE = "invl02_m2"

OPERATE = "operate"
IMPROVE = "improve"
PURPOSES = (OPERATE, IMPROVE)

OPERATE_KINDS = (
    "investigate",
    "probe",
    "construct",
    "reuse",
    "revise",
    "wait",
    "stop",
)

PACKAGE_ORIGINS = ("authored-control", "acquired")

INSTRUMENTS = ("boolean-rule-v1", "deliberation")


class Refused(Exception):
    pass


def canonical(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def package_digest(op_source: str, imp_source: str, parent_digest,
                   version: int, control_id: str) -> str:
    return _digest_text(canonical(
        {"op_source": op_source, "imp_source": imp_source,
         "parent_digest": parent_digest, "version": version,
         "control_id": control_id}))


def source_digest(source: str) -> str:
    return _digest_text(source)


def environment_digest(environments: list) -> str:
    return _digest_text(canonical(list(environments)))


def _is_count(value) -> bool:
    return type(value) is int and value >= 0


def validate_package(package: dict, *, grant: dict) -> dict:
    if not isinstance(package, dict):
        raise Refused("revision candidate is not an object")
    for key in ("control_id", "origin", "op_source", "imp_source",
                "op_digest", "imp_digest", "package_digest",
                "parent_digest", "version", "authority_request"):
        if key not in package:
            raise Refused("revision candidate misses %s" % key)
    if package["origin"] not in PACKAGE_ORIGINS:
        raise Refused("unknown package origin %r" % (
            package.get("origin"),))
    for key in ("op_source", "imp_source"):
        if not isinstance(package[key], str) or not package[key].strip():
            raise Refused("revision candidate holds no %s bytes" % key)
    if package["op_digest"] != source_digest(package["op_source"]):
        raise Refused("operational bytes do not match their digest")
    if package["imp_digest"] != source_digest(package["imp_source"]):
        raise Refused("improvement bytes do not match their digest")
    if package["package_digest"] != package_digest(
            package["op_source"], package["imp_source"],
            package.get("parent_digest"),
            package["version"], package["control_id"]):
        raise Refused("package bytes do not match their digest")
    if type(package["version"]) is not int or package["version"] < 0:
        raise Refused("revision version is not a nonnegative integer")
    request = package["authority_request"]
    if not isinstance(request, dict):
        raise Refused("revision candidate holds no authority request")
    for key in ("queries", "steps"):
        if not _is_count(request.get(key)):
            raise Refused("revision authority request is malformed")
        if request[key] > int(grant.get(key, 0)):
            raise Refused("revision expands authority beyond the grant")
    return package


def validate_operate_action(action: dict) -> dict:
    if not isinstance(action, dict):
        raise Refused("operate action must be an object")
    kind = action.get("kind")
    if kind not in OPERATE_KINDS:
        raise Refused("unknown operate action kind %r" % (kind,))
    inputs = action.get("inputs")
    if not isinstance(inputs, dict):
        raise Refused("operate action inputs must be an object")
    if kind == "investigate" and not isinstance(
            inputs.get("opportunity_id"), str):
        raise Refused("investigate needs an opportunity_id")
    if kind == "probe" and (not isinstance(inputs.get("x"), int)
                            or not 0 <= inputs["x"] < 16):
        raise Refused("probe needs an input x in 0..15")
    resources = action.get("requested_resources")
    if not isinstance(resources, dict) or any(
            not _is_count(v) for v in resources.values()):
        raise Refused("operate action requested_resources must hold"
                      " nonnegative integers")
    return action


def validate_view(view: dict) -> dict:
    if not isinstance(view, dict):
        raise Refused("STEP view must be an object")
    if view.get("purpose") not in PURPOSES:
        raise Refused("STEP view names no operate/improve purpose")
    for key in ("mission", "frontier", "experience", "obligations",
                "authority_remaining", "instruments", "environments",
                "environment_digest", "target_digest",
                "contract_versions"):
        if key not in view:
            raise Refused("STEP view misses %s" % key)
    if view["purpose"] == IMPROVE and "frozen_source" not in view:
        raise Refused("improve view holds no frozen source")
    if view["purpose"] == OPERATE and "frozen_source" in view:
        raise Refused("operate view must not carry program source")
    return view


def _check_opportunity(opportunity: dict) -> dict:
    if not isinstance(opportunity, dict):
        raise Refused("opportunity must be an object")
    for key in ("opportunity_id", "mission_link", "question",
                "intervention", "resources"):
        if key not in opportunity:
            raise Refused("opportunity misses %s" % key)
    intervention = opportunity["intervention"]
    if not isinstance(intervention, dict) or intervention.get(
            "instrument") not in INSTRUMENTS:
        raise Refused("opportunity names an inadmissible instrument")
    resources = opportunity["resources"]
    if not isinstance(resources, dict) or not _is_count(
            resources.get("queries")) or not _is_count(
            resources.get("steps")):
        raise Refused("opportunity needs finite query/step resources")
    if not isinstance(opportunity["opportunity_id"], str) or not \
            opportunity["opportunity_id"]:
        raise Refused("opportunity needs an id")
    return opportunity


def _blank_doc(namespace: str, mission: dict, authority: dict) -> dict:
    return {
        "namespace": namespace,
        "frontier_version": FRONTIER_VERSION,
        "mission": dict(mission),
        "environments": list(mission["environments"]),
        "environment_digest": environment_digest(
            mission["environments"]),
        "grant": {"queries": int(authority["queries"]),
                  "steps": int(authority["steps"])},
        "used": {"queries": 0, "steps": 0},
        "opportunities": {},
        "observations": [],
        "outcomes": {},
        "predictions": [],
        "obligations": [],
        "pending_effects": [],
        "active_package": None,
        "lineage": [],
        "retained": {"evidence_ids": [], "obligations": []},
        "private_state": {},
        "staged_candidate": None,
        "rounds": [],
        "improvement_log": [],
        "treatment_arms": {"acquired": []},
    }


class FrontierStore:
    def __init__(self, path) -> None:
        self.path = str(path)
        with open(self.path, encoding="utf-8") as handle:
            doc = json.load(handle)
        if not isinstance(doc, dict) or doc.get("namespace") != \
                NAMESPACE:
            raise Refused("store %s is outside namespace %s" % (
                self.path, NAMESPACE))
        if doc.get("frontier_version") != FRONTIER_VERSION:
            raise Refused("store %s uses an unknown frontier version"
                          % self.path)
        self._doc = doc

    @property
    def authority(self) -> dict:
        grant = dict(self._doc["grant"])
        used = dict(self._doc["used"])
        return {"queries_total": grant["queries"],
                "steps_total": grant["steps"],
                "queries_used": used["queries"],
                "steps_used": used["steps"],
                "queries_remaining": grant["queries"] - used["queries"],
                "steps_remaining": grant["steps"] - used["steps"]}

    @property
    def observations(self) -> list:
        return [dict(o) for o in self._doc["observations"]]

    @property
    def retained(self) -> dict:
        return {"evidence_ids": list(
            self._doc["retained"]["evidence_ids"]),
            "obligations": list(
                self._doc["retained"]["obligations"])}

    @property
    def private_state(self) -> dict:
        return dict(self._doc["private_state"])

    @private_state.setter
    def private_state(self, state: dict) -> None:
        if not isinstance(state, dict):
            raise Refused("private state must be an object")
        self._doc["private_state"] = dict(state)
        self.save()

    @property
    def active_package(self):
        package = self._doc["active_package"]
        return dict(package) if package is not None else None

    @property
    def active_digest(self):
        package = self._doc["active_package"]
        return package["package_digest"] if package else None

    @property
    def environment_digest(self) -> str:
        return self._doc["environment_digest"]

    @property
    def pending_effects(self) -> list:
        return [dict(e) for e in self._doc["pending_effects"]
                if e["status"] == "pending"]

    @property
    def settled_effects(self) -> list:
        return [dict(e) for e in self._doc["pending_effects"]
                if e["status"] == "settled"]

    @property
    def treatment_arms(self) -> dict:
        return {"acquired": [dict(c) for c in
                             self._doc["treatment_arms"]["acquired"]]}

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(canonical(self._doc) + "\n")
        os.replace(tmp, self.path)

    def propose(self, opportunity: dict) -> dict:
        admitted = _check_opportunity(opportunity)
        oid = admitted["opportunity_id"]
        if oid in self._doc["opportunities"]:
            raise Refused("opportunity %r already exists" % oid)
        record = {**admitted, "status": "admissible"}
        self._doc["opportunities"][oid] = record
        self.save()
        return dict(record)

    def admissible(self) -> list:
        listed = [dict(o) for o in
                  self._doc["opportunities"].values()
                  if o["status"] == "admissible"]
        return sorted(listed, key=lambda o: (
            o["resources"]["queries"] + o["resources"]["steps"],
            o["opportunity_id"]))

    def step_view(self, purpose: str, package: dict) -> dict:
        if purpose not in PURPOSES:
            raise Refused("unknown STEP purpose %r" % (purpose,))
        if not isinstance(package, dict) or not package.get(
                "package_digest"):
            raise Refused("STEP view needs the active package digest")
        remaining = {"queries": self.authority["queries_remaining"],
                     "steps": self.authority["steps_remaining"]}
        view = {
            "purpose": purpose,
            "mission": self._doc["mission"]["objective"],
            "frontier": [
                {"opportunity_id": o["opportunity_id"],
                 "task": o["intervention"]["target"],
                 "question": o["question"],
                 "cost": dict(o["resources"])}
                for o in self.admissible()
            ],
            "experience": [
                {"observation_id": o.get("observation_id"),
                 "task": o.get("task"),
                 "verdict": o.get("verdict"),
                 "detail": o.get("detail")}
                for o in self._doc["observations"]
            ],
            "obligations": list(self._doc["obligations"]),
            "retained": self.retained,
            "authority_remaining": remaining,
            "instruments": list(INSTRUMENTS),
            "environments": list(self._doc["environments"]),
            "environment_digest": self._doc["environment_digest"],
            "target_digest": package["package_digest"],
            "contract_versions": self._contracts(),
        }
        if purpose == IMPROVE:
            view["frozen_source"] = {
                "op_source": package["op_source"],
                "imp_source": package["imp_source"],
                "op_digest": package["op_digest"],
                "imp_digest": package["imp_digest"],
            }
            view["improvement_budget"] = {
                "queries": min(4, remaining["queries"]),
                "steps": min(4, remaining["steps"]),
            }
        return validate_view(view)

    def _contracts(self) -> dict:
        from . import method_exec
        from . import packet
        from . import policy_step
        return {
            "frontier": FRONTIER_VERSION,
            "packet": packet.PACKET_VERSION,
            "policy_step": policy_step.POLICY_STEP_VERSION,
            "child": method_exec.CHILD_CONTRACT_VERSION,
        }

    def spend(self, requested: dict) -> dict:
        if not isinstance(requested, dict) or any(
                not _is_count(v) for v in requested.values()):
            raise Refused("requested resources are malformed")
        remaining = {"queries": self.authority["queries_remaining"],
                     "steps": self.authority["steps_remaining"]}
        for key in ("queries", "steps"):
            if int(requested.get(key, 0)) > remaining[key]:
                raise Refused("%s budget exhausted" % key)
        for key in ("queries", "steps"):
            self._doc["used"][key] += int(requested.get(key, 0))
        self.save()
        return {"queries_remaining": self.authority[
            "queries_remaining"],
            "steps_remaining": self.authority["steps_remaining"]}

    def accept(self, opportunity_id: str, program_digest: str) -> dict:
        record = self._doc["opportunities"].get(opportunity_id)
        if record is None or record["status"] != "admissible":
            raise Refused("opportunity %r is not admissible" % (
                opportunity_id,))
        if not program_digest:
            raise Refused("acceptance needs the proposing program digest")
        effect = {
            "effect_id": "eff-%s-%d" % (
                opportunity_id, len(self._doc["pending_effects"])),
            "opportunity_id": opportunity_id,
            "program_digest": program_digest,
            "status": "pending",
        }
        record["status"] = "accepted"
        self._doc["pending_effects"].append(effect)
        self.save()
        return dict(effect)

    def observe(self, observation: dict) -> dict:
        if not isinstance(observation, dict) or not observation.get(
                "observation_id"):
            raise Refused("observation needs an observation_id")
        self._doc["observations"].append(dict(observation))
        self.save()
        return dict(observation)

    def settle(self, effect_id: str, observation: dict) -> dict:
        effect = next((e for e in self._doc["pending_effects"]
                       if e["effect_id"] == effect_id), None)
        if effect is None or effect["status"] != "pending":
            raise Refused("effect %r is not pending" % (effect_id,))
        known = {o.get("observation_id") for o in
                 self._doc["observations"]}
        stored = dict(observation) if observation.get(
            "observation_id") in known else self.observe(observation)
        effect["status"] = "settled"
        effect["observation_id"] = stored["observation_id"]
        record = self._doc["opportunities"].get(
            effect["opportunity_id"])
        if record is not None:
            record["status"] = "done"
        self.save()
        return dict(effect)

    def record_outcome(self, action_key: dict, outcome: dict) -> None:
        self._doc["outcomes"][canonical(action_key)] = dict(outcome)
        self.save()

    def replay(self, action_key: dict) -> dict:
        outcome = self._doc["outcomes"].get(canonical(action_key))
        if outcome is None:
            return {"class": "unsupported",
                    "reason": "no compatible recorded outcome"}
        return {"class": "recorded-replay", "outcome": dict(outcome)}

    def predict(self, action_key: dict, hypothesis: dict) -> dict:
        entry = {"key": dict(action_key), "hypothesis": dict(
            hypothesis)}
        self._doc["predictions"].append(entry)
        self.save()
        return {"class": "prediction", "hypothesis": dict(hypothesis)}

    def ready_events(self) -> list:
        events = [{"type": "opportunity-available",
                   "opportunity_id": o["opportunity_id"]}
                  for o in self.admissible()]
        events.extend({"type": "effect-pending",
                       "effect_id": e["effect_id"]}
                      for e in self.pending_effects)
        return events

    def is_quiescent(self) -> bool:
        return len(self.pending_effects) == 0

    def bind_active(self, package: dict) -> dict:
        bound = validate_package(package, grant=self._doc["grant"])
        if self._doc["active_package"] is not None:
            raise Refused("an active program already exists; adopt a"
                          " revision instead")
        self._doc["active_package"] = dict(bound)
        self._doc["lineage"].append(
            {"version": 0, "package_digest": bound["package_digest"],
             "parent_digest": None})
        self._doc["private_state"] = {}
        self._doc["retained"] = {"evidence_ids": [], "obligations": []}
        self.save()
        return dict(bound)

    def adopt_revision(self, candidate: dict) -> dict:
        active = self._doc["active_package"]
        if active is None:
            raise Refused("no active program to revise")
        if not self.is_quiescent():
            raise Refused("adoption needs a quiescent boundary")
        bound = validate_package(candidate, grant=self._doc["grant"])
        if bound["parent_digest"] != active["package_digest"]:
            raise Refused("revision parent is not the active program")
        self._doc["active_package"] = dict(bound)
        self._doc["lineage"].append(
            {"version": len(self._doc["lineage"]),
             "package_digest": bound["package_digest"],
             "parent_digest": bound["parent_digest"]})
        self._doc["private_state"] = {}
        self._doc["retained"] = {
            "evidence_ids": [o.get("observation_id")
                             for o in self._doc["observations"]
                             if o.get("observation_id")],
            "obligations": list(bound.get("obligations") or []),
        }
        if bound["package_digest"] not in {
                c["package_digest"] for c in
                self._doc["treatment_arms"]["acquired"]}:
            self._doc["treatment_arms"]["acquired"].append(dict(bound))
        self._doc["staged_candidate"] = None
        self.save()
        return dict(bound)


def create_store(path, *, namespace: str, mission: dict,
                 authority: dict) -> FrontierStore:
    if namespace != NAMESPACE:
        raise Refused("lane stores live in namespace %s" % NAMESPACE)
    if not isinstance(mission, dict) or not mission.get("objective") \
            or not isinstance(mission.get("environments"), list) \
            or not mission["environments"]:
        raise Refused("mission needs an objective plus frozen"
                      " environments")
    if not isinstance(authority, dict) or not _is_count(
            authority.get("queries")) or not _is_count(
            authority.get("steps")):
        raise Refused("authority needs nonnegative query/step totals")
    store = FrontierStore.__new__(FrontierStore)
    store.path = str(path)
    store._doc = _blank_doc(namespace, mission, authority)
    store.save()
    return store
