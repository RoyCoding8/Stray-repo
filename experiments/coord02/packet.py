"""coord02 materialized packets: one typed shape per decision.

The construction envelope converges on the shared shape owned by
experiments.ad01.packet: one JSON object carrying the entry source,
parsed fence-tolerant through the shared parse_construction_response,
so renderer, parser and executor agree by construction instead of by
paraphrase. Family-specific content stays limited to candidate_shape
(owned tree files per task) and witness_rule (protected-case
preservation meaning); both render into the prompt from these
builders, never from paraphrase.
"""

from __future__ import annotations

import json
from typing import Any

from settlement.common import SettlementError
from settlement.representation import canonical_bytes, sha_hex

from experiments.ad01.packet import parse_construction_response as _shared_parse

from . import oracle
from . import schemas as wire

PACKET_VERSION = "coord02-packet-v1"


def candidate_shape(task_id: str) -> dict:
    return {
        "owned_paths": list(oracle.worker_files(task_id)),
        "family": oracle.TASK_FAMILY.get(task_id, ""),
        "output_contract": {
            "entry": "one complete file content per owned path",
            "checks": ["public"],
        },
    }


def witness_rule(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "meaning": ("the restaged candidate tree must pass every "
                    "protected case for the task"),
        "evaluator": {"id": oracle.EVALUATOR_ID,
                      "version": oracle.EVALUATOR_VERSION},
        "secrecy": ("protected reference bytes never appear in any "
                    "packet, prompt, or response"),
    }


def render_task_input(cfg: Any, *, observations: list,
                      accepted_plan: dict | None,
                      residual: dict, remaining: dict) -> dict:
    return {"task_snapshot": dict(cfg.snapshot),
            "public_contract": dict(cfg.interface_contract),
            "interface_bindings": [dict(b) for b in cfg.bindings],
            "accepted_plan": accepted_plan,
            "observations": list(observations),
            "residual_obligations": dict(residual),
            "remaining_allocation": dict(remaining),
            "dependency_versions": {b["name"]: b.get("version", "")
                                    for b in cfg.bindings}}


def render_child_obligation(child: dict, observations: list) -> dict:
    return {"node_id": child["node_id"],
            "owned_paths": list(child["owned_paths"]),
            "input_bindings": dict(child["input_bindings"]),
            "output_contract": dict(child["output_contract"]),
            "admitted_observations": [dict(o) for o in observations
                                      if isinstance(o, dict)]}


def render_child_prompt(task_id: str, node: str, rendered: dict) -> str:
    return "\n".join([
        "Repair owned paths for task %s node %s." % (task_id, node),
        "Work packet: %s" % json.dumps(rendered, sort_keys=True),
        "Reply with exactly one JSON object and nothing else, shaped "
        '{"files": { "<owned relpath>": "<complete file content>" }, '
        '"notes": "<one or two sentences>"}. '
        "Include an entry for every owned path, even if unchanged."])


def parse_child_response(child: dict, text: str) -> tuple:
    owned = list(child.get("owned_paths", []))
    body = (text or "").strip()
    if body.startswith("```"):
        lines = body.split("\n")[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines)
    try:
        data = json.loads(body) if body else None
    except ValueError:
        return None, "parse-failure: child response is not JSON"
    files = None
    if isinstance(data, dict):
        files = data.get("files")
        if files is None and isinstance(data.get("children"), list):
            plan = [c for c in data["children"]
                    if isinstance(c, dict)
                    and c.get("node_id") == child.get("node_id")]
            if plan and isinstance(plan[0].get("files"), dict):
                files = plan[0]["files"]
    if not isinstance(files, dict) or set(files) != set(owned):
        return None, "parse-failure: files must cover exactly the owned paths"
    if any(not isinstance(v, str) or not v.strip()
           for v in files.values()):
        return None, "parse-failure: every owned path needs file content"
    return {p: files[p] for p in owned}, ""


def construction_call_spec(packet: dict, budget: dict) -> dict:
    return {"abi": {"argv": ["python", "<entry>", "<request.json>",
                             "<response.json>"],
                    "request_fields": ["profile", "profile_version",
                                       "decision_id", "package_digest",
                                       "source_digest", "plan_revision",
                                       "phase", "allowed_actions", "state",
                                       "task"],
                    "response_fields": ["profile", "profile_version",
                                        "decision_id", "package_digest",
                                        "source_digest", "plan_revision",
                                        "phase", "proposal", "state"],
                    "actions": list(wire.ACTIONS),
                    "state_limit_bytes": wire.MAX_STATE_BYTES},
            "action_semantics": {
                "probe": ("up to %d bounded JSON calls of bound "
                          "interfaces" % wire.MAX_PROBE_CALLS),
                "plan": "one single|alternatives|decompose team for admission",
                "rework": "name failed-join children for fresh attempts",
                "stop": "end intervention preserving residual obligation",
                "unsupported": "decline for a missing binding or scope"},
            "transport_examples": {
                "probe": {"action": "probe",
                          "invocations": [{"interface": "<bound-name>",
                                           "input": {}}]},
                "plan": {"action": "plan", "shape": "single", "children": []},
                "rework": {"action": "rework", "rework": ["<node>"]}},
            "development_observations": packet.get("probe_observations", []),
            "budget": dict(budget)}


def snapshot_digest_of(snapshot: dict) -> str:
    from settlement import team as _team
    try:
        return _team.snapshot_digest(
            {k: v for k, v in snapshot.items() if isinstance(v, str)})
    except Exception:
        return sha_hex(canonical_bytes(snapshot))


def _wire_schema() -> dict:
    return {"profile": wire.PROFILE,
            "profile_version": wire.PROFILE_VERSION,
            "phases": dict(wire.ALLOWED),
            "actions": list(wire.ACTIONS),
            "request_fields": ["profile", "profile_version", "decision_id",
                               "package_digest", "source_digest",
                               "plan_revision", "phase", "allowed_actions",
                               "state", "task"],
            "response_fields": ["profile", "profile_version", "decision_id",
                                "package_digest", "source_digest",
                                "plan_revision", "phase", "proposal",
                                "state"],
            "limits": {"max_state_bytes": wire.MAX_STATE_BYTES,
                       "max_message_bytes": wire.MAX_MESSAGE_BYTES,
                       "max_probe_calls": wire.MAX_PROBE_CALLS,
                       "max_reason_chars": wire.MAX_REASON_CHARS,
                       "max_policy_steps": wire.MAX_POLICY_STEPS}}


def _transport_specimen() -> dict:
    decision_id = "specimen-decision"
    package_digest = "specimen-package"
    source_digest = "specimen-source"
    plan_revision = 0
    phase = wire.PHASE_PRE_PLAN
    allowed = list(wire.ALLOWED[phase])
    request = wire.build_request(
        decision_id=decision_id, package_digest=package_digest,
        source_digest=source_digest, plan_revision=plan_revision,
        phase=phase, allowed=allowed, state={},
        task={"specimen": True})
    response = {"profile": wire.PROFILE,
                "profile_version": wire.PROFILE_VERSION,
                "decision_id": decision_id,
                "package_digest": package_digest,
                "source_digest": source_digest,
                "plan_revision": plan_revision, "phase": phase,
                "proposal": {"action": "stop",
                             "reason": "specimen decline carries no policy"},
                "state": {}}
    wire.validate_response(
        dict(response), decision_id=decision_id,
        package_digest=package_digest, source_digest=source_digest,
        plan_revision=plan_revision, phase=phase, allowed=allowed)
    return {"decision_id": decision_id, "package_digest": package_digest,
            "source_digest": source_digest, "plan_revision": plan_revision,
            "phase": phase, "allowed": allowed, "request": request,
            "response": response}


def _episode_contents(episode: dict) -> dict:
    packet = episode.get("packet", episode)
    inputs = packet.get("versioned_inputs", {}) or {}
    return {"task_id": episode.get("task_id", packet.get("task_id", "")),
            "run_id": episode.get("episode", {}).get("run_id",
                                                     packet.get("run_id",
                                                                "")),
            "source": inputs.get("task_snapshot", {}),
            "contracts": inputs.get("interface_contract", {}),
            "initial_state": {
                "snapshot_digest": inputs.get("snapshot_digest", "")},
            "proposals": list(packet.get("decisions", [])),
            "admissions": list(packet.get("plans", [])),
            "observed_outputs": list(packet.get("probe_observations", [])),
            "child_artifacts": packet.get("actual_artifacts", {}),
            "failed_joins": list(packet.get("failed_joins",
                                            [j for j in packet.get(
                                                "joins", [])
                                             if not j.get("passed",
                                                          True)])),
            "revisions": list(packet.get("revisions", [])),
            "costs": packet.get("cost", {})}


def _as_episode_list(episodes: Any) -> list[dict]:
    if isinstance(episodes, dict):
        return [episodes]
    return list(episodes)


def _task_ids_of(contents: list) -> list:
    seen = []
    for item in contents:
        task_id = item.get("task_id", "")
        if task_id and task_id not in seen:
            seen.append(task_id)
    return seen


def construction_packet(episodes: Any, budget: dict, *,
                        lineage: int, attempt: str,
                        prior_failure: dict | None = None,
                        content_budget_bytes: int) -> dict:
    listed = _as_episode_list(episodes)
    contents = [_episode_contents(e) for e in listed]
    wire_schema = _wire_schema()
    specimen = _transport_specimen()
    sized = canonical_bytes({"contents": contents, "wire": wire_schema,
                             "specimen": specimen})
    if len(sized) > content_budget_bytes:
        raise SettlementError(
            "construction request exceeds content budget: "
            "%d bytes over %d for %d episodes: narrow the selection"
            % (len(sized), content_budget_bytes, len(contents)))
    packet = listed[0].get("packet", listed[0]) if listed else {}
    spec = construction_call_spec(
        {"probe_observations": packet.get("probe_observations", [])},
        dict(budget))
    tasks = _task_ids_of(contents)
    return {"lineage": int(lineage), "attempt": attempt,
            "abi": spec["abi"],
            "action_semantics": spec["action_semantics"],
            "wire_schema": wire_schema,
            "transport_specimen": specimen,
            "episode_contents": contents,
            "candidate_shapes": {t: candidate_shape(t) for t in tasks},
            "witness_rules": {t: witness_rule(t) for t in tasks},
            "content_bytes": len(sized),
            "content_budget_bytes": content_budget_bytes,
            "required_response": {
                "format": "one JSON object with a single string field",
                "field": "entry",
                "entry": "complete python policy source honoring the "
                         "abi above (argv/request/response, proposal "
                         "actions, 16 KiB state limit); the entry must "
                         "exit 0 when invoked as `python <entry> "
                         "--selftest` with no request file; no other "
                         "top-level fields"},
            "response_example": {"entry": (
                "import json, sys\n"
                "if len(sys.argv) == 2 and sys.argv[1] == '--selftest':\n"
                "    raise SystemExit(0)\n"
                "req = json.load(open(sys.argv[1]))\n"
                "proposal = {'action': 'probe', 'invocations': []}\n"
                "json.dump({'profile': req['profile'], "
                "'profile_version': req['profile_version'], "
                "'decision_id': req['decision_id'], "
                "'package_digest': req['package_digest'], "
                "'source_digest': req['source_digest'], "
                "'plan_revision': req['plan_revision'], "
                "'phase': req['phase'], 'proposal': proposal, "
                "'state': {}}, open(sys.argv[2], 'w'))\n")},
            "budget": spec["budget"], "prior_failure": prior_failure,
            "packet_digest": sha_hex(canonical_bytes(
                [e.get("packet", e) for e in listed]))}


def render_construction_prompt(request: dict) -> str:
    sections = {
        "ABI": request.get("abi", {}),
        "ACTION SEMANTICS": request.get("action_semantics", {}),
        "WIRE SCHEMA": request.get("wire_schema", {}),
        "TRANSPORT SPECIMEN": request.get("transport_specimen", {}),
        "DEVELOPMENT EPISODES": request.get("episode_contents", []),
        "CANDIDATE SHAPES": request.get("candidate_shapes", {}),
        "WITNESS RULES": request.get("witness_rules", {}),
        "REQUIRED RESPONSE": request.get("required_response", {}),
        "RESPONSE EXAMPLE": request.get("response_example", {}),
    }
    lines = ["Build a python policy program for the coordinator ABI below.",
             "Reply with ONLY one JSON object of the form "
             '{"entry": "<complete python source>"}; no other text.',
             ""]
    for title, body in sections.items():
        if body:
            lines += ["", title + ": " + canonical_bytes(body).decode()]
    prior = request.get("prior_failure")
    if prior:
        lines += ["", "PRIOR FAILURE (repair it): " +
                  canonical_bytes(prior).decode()]
    return "\n".join(lines)


def parse_construction_entry(text: str) -> tuple:
    source, problem = _shared_parse(text)
    if problem == "":
        return source, ""
    if problem.startswith("parse-failure: missing entry"):
        return None, "missing-entry"
    if problem.endswith("response is not an object"):
        return None, "missing-entry"
    return None, problem.replace("parse-failure: ", "unparsable-response: ",
                                 1)
