"""Deterministic scripted model double backing the §11 arms.

Implements the gateway adapter interface with fixed per-arm competence, so
the harness runs end to end with no live inference. Every response carries
``simulated: True`` metadata; nothing here may be reported as live.
"""

from __future__ import annotations

import json

from experiments.fault_tasks import LESSON_OFF_BY_ONE as LESSON_TEXT
from settlement.gateway import (GatewayAdapter, GatewayError, GatewayErrorKind, GatewayStatus,
                                ModelRequest, ModelResponse, Usage)


class ScriptedDouble(GatewayAdapter):
    def __init__(self, competence: dict, fixes: dict, broken: dict) -> None:
        self.competence = dict(competence)
        self.fixes = dict(fixes)
        self.broken = dict(broken)
        self.calls: list[dict] = []
        self.cancelled: set[str] = set()

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request: ModelRequest):
        if request.operation_id in self.cancelled:
            return GatewayError(GatewayErrorKind.CANCELLED, "cancelled",
                                False, request.operation_id)
        try:
            body = json.loads(request.messages[-1]["content"])
        except (ValueError, IndexError, TypeError):
            return GatewayError("protocol", "scripted double needs a JSON body",
                                False, request.operation_id)
        if body.get("author_lesson"):
            summary = body.get("dev_transcripts", [])
            wins = sum(1 for row in summary if row.get("outcome") == "success")
            text = (f"{LESSON_TEXT} Authored from {wins}/{len(summary)}"
                    " successful development repairs.")
            self.calls.append({"author_lesson": True})
            return ModelResponse(request.operation_id, text,
                                 {"simulated": True, "author_lesson": True},
                                 Usage(input_tokens=60, output_tokens=150,
                                       charge_units=210), "stop")
        try:
            arm, task_id = body["arm"], body["task_id"]
        except (KeyError, TypeError):
            return GatewayError("protocol", "scripted double needs JSON arm/task_id",
                                False, request.operation_id)
        self.calls.append({"arm": arm, "task_id": task_id})
        table = self.fixes if self.competence.get((arm, task_id)) else self.broken
        if task_id not in table:
            return GatewayError("protocol",
                                f"scripted double has no fixture for {arm}/{task_id}",
                                False, request.operation_id)
        code = table[task_id]
        return ModelResponse(request.operation_id, code,
                             {"simulated": True, "arm": arm, "task_id": task_id},
                             Usage(input_tokens=50, output_tokens=120,
                                   charge_units=170), "stop")

    def cancel(self, operation_id: str) -> bool:
        self.cancelled.add(operation_id)
        return True


INV_C_MODEL = "inv-c-double"

ACQUIRED_ORDER_SOURCE = (
"def acquired_order(task, oracle, max_queries=16):\n"
"    family = task.get(\"family\", \"software\")\n"
"    if isinstance(max_queries, int) and max_queries >= 0:\n"
"        budget = max_queries\n"
"    else:\n"
"        budget = 16\n"
"    used = [0]\n"
"    def ask(candidate):\n"
"        used[0] = used[0] + 1\n"
"        return oracle.query(candidate)\n"
"    def shrink(build, count, order, bulk):\n"
"        full = list(range(count))\n"
"        if budget <= 0:\n"
"            return build(full)\n"
"        first = build(full)\n"
"        if first is None:\n"
"            return build(full)\n"
"        report = ask(first)\n"
"        if not isinstance(report, dict) or report.get(\"verdict\") != \"preserved\":\n"
"            return build(full)\n"
"        keep = full\n"
"        if bulk is not None and used[0] < budget:\n"
"            trial = [i for i in keep if i not in bulk]\n"
"            if trial:\n"
"                cand = build(trial)\n"
"                if cand is not None:\n"
"                    rep = ask(cand)\n"
"                    if isinstance(rep, dict) and rep.get(\"verdict\") == \"preserved\":\n"
"                        keep = trial\n"
"        changed = True\n"
"        while changed and len(keep) > 1:\n"
"            changed = False\n"
"            for atom in [a for a in order if a in keep]:\n"
"                if used[0] >= budget:\n"
"                    return build(keep)\n"
"                trial_keep = [a for a in keep if a != atom]\n"
"                cand = build(trial_keep)\n"
"                if cand is None:\n"
"                    continue\n"
"                rep = ask(cand)\n"
"                if isinstance(rep, dict) and rep.get(\"verdict\") == \"preserved\":\n"
"                    keep = trial_keep\n"
"                    changed = True\n"
"        return build(keep)\n"
"    if family == \"graph\":\n"
"        vertices = list(task.get(\"vertices\", []))\n"
"        edges = [list(e) for e in task.get(\"edges\", [])]\n"
"        units = []\n"
"        for v in vertices:\n"
"            units.append((\"v\", v))\n"
"        for i in range(len(edges)):\n"
"            units.append((\"e\", i))\n"
"        degree = {}\n"
"        for v in vertices:\n"
"            degree[v] = 0\n"
"        for e in edges:\n"
"            degree[e[0]] = degree.get(e[0], 0) + 1\n"
"            degree[e[1]] = degree.get(e[1], 0) + 1\n"
"        def build_graph(keep):\n"
"            kept = set(keep)\n"
"            gone = set()\n"
"            dropped_edges = set()\n"
"            for pos in range(len(units)):\n"
"                if pos not in kept:\n"
"                    if units[pos][0] == \"v\":\n"
"                        gone.add(units[pos][1])\n"
"                    else:\n"
"                        dropped_edges.add(units[pos][1])\n"
"            keep_v = [v for v in vertices if v not in gone]\n"
"            if not keep_v:\n"
"                return None\n"
"            kept_v = set(keep_v)\n"
"            keep_e = [e for i, e in enumerate(edges) if i not in dropped_edges and e[0] in kept_v and e[1] in kept_v]\n"
"            return {\"family\": \"graph\", \"task_id\": task.get(\"task_id\"), \"vertices\": keep_v, \"edges\": keep_e, \"seed\": task.get(\"seed\")}\n"
"        v_first = [i for i in range(len(units)) if units[i][0] == \"v\"]\n"
"        v_first = sorted(v_first, key=lambda i: (degree.get(units[i][1], 0), i))\n"
"        e_rest = [i for i in range(len(units)) if units[i][0] != \"v\"]\n"
"        candidate = shrink(build_graph, len(units), v_first + e_rest, None)\n"
"        return {\"candidate\": candidate, \"queries\": used[0]}\n"
"    ops = list(task.get(\"ops\", []))\n"
"    wid = task.get(\"witness\", {}).get(\"observation\")\n"
"    wpos = -1\n"
"    for i, entry in enumerate(ops):\n"
"        if entry.get(\"id\") == wid:\n"
"            wpos = i\n"
"            break\n"
"    hero = ops[wpos].get(\"key\") if wpos >= 0 else None\n"
"    chain = [i for i, o in enumerate(ops) if wpos >= 0 and o.get(\"op\") == \"set\" and o.get(\"key\") == hero and i < wpos]\n"
"    rest = [i for i in range(len(ops)) if i != wpos and i not in chain]\n"
"    def build_sw(keep):\n"
"        kept = [ops[i] for i in sorted(keep)]\n"
"        return {\"family\": \"software\", \"task_id\": task.get(\"task_id\"), \"fault\": task.get(\"fault\"), \"ops\": kept, \"witness\": task.get(\"witness\"), \"seed\": task.get(\"seed\")}\n"
"    if wpos >= 0:\n"
"        order = rest + chain + [wpos]\n"
"        bulk = set(rest)\n"
"    else:\n"
"        order = list(range(len(ops)))\n"
"        bulk = None\n"
"    candidate = shrink(build_sw, len(ops), order, bulk)\n"
"    return {\"candidate\": candidate, \"queries\": used[0]}\n"
)


def learner_text(proposal: dict) -> str:
    return json.dumps(proposal, sort_keys=True)


def learner_diagnostic_text(task_id: str, family: str) -> str:
    return learner_text({
        "basis_references": ["obs-%s-seed" % task_id],
        "question": "diagnose %s" % task_id,
        "next_action": {"kind": "diagnostic", "diagnostic": family,
                        "task_id": task_id},
        "requested_resources": {"diagnostic_queries": 1}})


def learner_development_text(task_id: str, family: str,
                             max_queries: int = 16) -> str:
    return learner_text({
        "basis_references": ["obs-%s-seed" % task_id],
        "question": "develop %s" % task_id,
        "next_action": {"kind": "development", "diagnostic": family,
                        "task_id": task_id, "max_queries": max_queries},
        "requested_resources": {"diagnostic_queries": 1}})


def construction_text(source: str | None = None, notes: str = "") -> str:
    return json.dumps({
        "entry": source if source is not None else ACQUIRED_ORDER_SOURCE,
        "notes": notes or ("diagnostic-aware two-phase reduction:"
                           " surgical bulk drops of non-chain atoms,"
                           " then greedy polish in witness-last order.")},
        sort_keys=True)


class InvCQualificationDouble(GatewayAdapter):
    """Recording demux double for the INV-C qualification gate.

    Learner operations draw from the learner stream in call order.
    Construction init attempts draw the init stream (defaulting to the
    family stream matching the task named in the operation id), repair
    attempts draw the repair stream (defaulting the same way), and any
    other operation id draws the default stream. Every call travels
    through broker ensure and dispatch with settled receipts; only the
    provider answers are recorded. Every response carries simulated
    metadata and non-billable usage; nothing here may read as live.
    """

    label = "INV-C-QUALIFICATION-DOUBLE"

    @staticmethod
    def _script(entry):
        return entry if isinstance(entry, dict) else {"text": entry}

    def __init__(self, learner_scripts: list,
                 software_scripts: list | None = None,
                 graph_scripts: list | None = None,
                 init_scripts: list | None = None,
                 repair_scripts: list | None = None,
                 default_scripts: list | None = None) -> None:
        normalized = [self._script(s) for s in learner_scripts]
        self._streams = {
            "learner": [dict(s) for s in normalized],
            "software": [dict(self._script(s)) for s in (
                software_scripts if software_scripts is not None
                else [{"text": construction_text()},
                      {"text": construction_text()},
                      {"text": construction_text()},
                      {"text": construction_text()}])],
            "graph": [dict(self._script(s)) for s in (
                graph_scripts if graph_scripts is not None
                else [{"text": construction_text()},
                      {"text": construction_text()},
                      {"text": construction_text()},
                      {"text": construction_text()}])],
            "init": None if init_scripts is None
            else [dict(self._script(s)) for s in init_scripts],
            "repair": None if repair_scripts is None
            else [dict(self._script(s)) for s in repair_scripts],
            "default": [dict(self._script(s))
                        for s in (default_scripts if default_scripts
                                  is not None else normalized)],
        }
        self._used = {name: 0 for name in self._streams}
        self.calls: list = []
        self.records: dict = {}

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def _stream(self, operation_id: str) -> str:
        if "-learner-" in operation_id:
            return "learner"
        if operation_id.endswith("-init") and self._streams["init"]:
            return "init"
        if operation_id.endswith("-repair") and self._streams["repair"]:
            return "repair"
        if "-construct-" in operation_id:
            if "-gr-" in operation_id:
                return "graph"
            return "software"
        return "default"

    def infer(self, request: ModelRequest):
        self.calls.append(request)
        name = self._stream(request.operation_id)
        stream = self._streams[name]
        if not stream:
            return GatewayError(GatewayErrorKind.CANCELLED,
                                "inv-c double has no %s script" % name,
                                False, request.operation_id)
        position = self._used[name]
        self._used[name] += 1
        script = stream[min(position, len(stream) - 1)]
        try:
            prompt = request.messages[-1]["content"]
        except (IndexError, TypeError, KeyError):
            prompt = ""
        text = script.get("text", "")
        custom = dict(script.get("usage") or {})
        usage = Usage(input_tokens=int(custom.get("input_tokens", 11)),
                      output_tokens=int(custom.get("output_tokens", 7)),
                      charge_units=int(custom.get("charge_units", 0)),
                      billed=False)
        meta = {"simulated": True, "stream": name}
        meta.update(dict(script.get("meta") or {}))
        meta["simulated"] = True
        self.records[request.operation_id] = {
            "operation_id": request.operation_id, "prompt": prompt,
            "response": text, "stream": name,
            "usage": {"input_tokens": usage.input_tokens,
                      "output_tokens": usage.output_tokens,
                      "charge_units": usage.charge_units,
                      "billed": usage.billed}}
        return ModelResponse(request.operation_id, text, meta, usage,
                             "stop")

    def cancel(self, operation_id: str) -> bool:
        return False


VERSION_FIELDS = ("model", "packet_version", "protocol", "profile",
                  "freeze_digest")


def recorded_from_export(export: dict) -> list:
    transitions = list(export.get("transitions", []))
    recorded = []
    for transition in transitions:
        recorded.append({
            "packet_digest": transition.get("packet_digest"),
            "proposal": dict(transition.get("proposal") or {}),
            "operations": list(transition.get("operations") or []),
            "results": list(transition.get("results") or []),
            "costs_measured": dict(
                transition.get("costs_measured") or {}),
            "costs_unknown": list(
                transition.get("costs_unknown") or [])})
    return recorded


def replay_export(export: dict, probe: dict) -> dict:
    return check_replay_prefix(recorded_from_export(export), probe)


def _replay_refused(reason: str) -> dict:
    return {"verdict": "refused", "reason": reason, "results": [],
            "costs_unknown": []}


def _replay_unsupported(reason: str) -> dict:
    return {"verdict": "unsupported", "reason": reason, "results": [],
            "costs_unknown": []}


def check_replay_prefix(recorded: list, probe: dict) -> dict:
    """Decide whether a probe replays a recorded transition prefix.

    Compares the probe against one recorded ExperienceTransition row:
    packet digest, version fields, action target/instrument, code-carrying
    inputs, exact dependency order, requested resources, and observation
    availability within the recorded prefix. A matching task id alone is
    insufficient. Supported probes return the recorded results verbatim,
    unknown costs included; every other probe returns no results, so a
    stopped branch never borrows an unrelated outcome.
    """
    from settlement.common import payload_digest
    if not isinstance(probe, dict):
        return _replay_refused("malformed-probe: probe is not an object")
    for key in ("index", "packet_digest", "action", "versions",
                "observations"):
        if key not in probe:
            return _replay_refused("malformed-probe: missing %s" % key)
    index = probe["index"]
    if isinstance(index, bool) or not isinstance(index, int) \
            or not 0 <= index < len(recorded):
        return _replay_refused("malformed-probe: index out of range")
    rec = recorded[index]
    if not isinstance(rec, dict):
        return _replay_refused(
            "malformed-probe: recorded transition is not an object")
    if probe["packet_digest"] != rec.get("packet_digest"):
        return _replay_unsupported(
            "artifact-mismatch: packet digest %r is not the recorded %r"
            % (probe["packet_digest"], rec.get("packet_digest")))
    action = probe["action"]
    if not isinstance(action, dict):
        return _replay_refused("malformed-probe: action is not an object")
    proposal = rec.get("proposal") or {}
    if action.get("target") != proposal.get("target") \
            or action.get("instrument") != proposal.get("instrument"):
        return _replay_unsupported(
            "unsupported-decision: target/instrument %r/%r is not the"
            " recorded %r/%r" % (action.get("target"),
                                 action.get("instrument"),
                                 proposal.get("target"),
                                 proposal.get("instrument")))
    versions = probe["versions"]
    if not isinstance(versions, dict):
        return _replay_refused("malformed-probe: versions is not an object")
    inputs = dict(proposal.get("inputs") or {})
    for field in VERSION_FIELDS:
        if versions.get(field) != inputs.get(field):
            return _replay_unsupported(
                "version-mismatch: %s %r is not the recorded %r"
                % (field, versions.get(field), inputs.get(field)))
    recorded_code = {k: v for k, v in inputs.items()
                     if k not in VERSION_FIELDS}
    probed_code = {k: v for k, v in dict(action.get("inputs") or {}).items()
                   if k not in VERSION_FIELDS}
    if payload_digest(recorded_code) != payload_digest(probed_code):
        return _replay_unsupported(
            "new-code-bytes: action inputs differ from the recorded inputs")
    recorded_deps = list(proposal.get("dependencies") or [])
    probed_deps = action.get("dependencies")
    if not isinstance(probed_deps, list) or probed_deps != recorded_deps:
        if isinstance(probed_deps, list) and sorted(
                str(d) for d in probed_deps) == sorted(
                str(d) for d in recorded_deps):
            return _replay_unsupported(
                "reordered-dependents: %r reorders the recorded %r"
                % (probed_deps, recorded_deps))
        return _replay_unsupported(
            "dependency-mismatch: %r is not the recorded %r"
            % (probed_deps, recorded_deps))
    if dict(action.get("requested") or {}) != dict(
            proposal.get("requested") or {}):
        return _replay_unsupported(
            "changed-context: requested resources differ from recorded")
    pool: set = set()
    for prior in recorded[:index]:
        pool.update(prior.get("operations") or [])
        pool.update(prior.get("results") or [])
    observations = probe["observations"]
    if not isinstance(observations, list) or any(
            not isinstance(o, str) for o in observations):
        return _replay_refused(
            "malformed-probe: observations must be a list of strings")
    future = [o for o in observations if o not in pool]
    if future:
        return _replay_unsupported(
            "hidden-future: %r is not observable at this prefix" % future)
    return {"verdict": "supported", "reason": "",
            "results": list(rec.get("results") or []),
            "costs_unknown": list(rec.get("costs_unknown") or []),
            "costs_measured": dict(rec.get("costs_measured") or {})}
