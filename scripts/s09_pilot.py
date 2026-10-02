"""S09-C3 prospective P0/P1/P2 executable policy pilot (N5).

Freezes the study spec before exposing assessment, runs four
development episodes, one candidate plus one repair per constructed
arm, and twelve assessment episodes with two sealed use tasks each
through the public trajectory entry. Doubles only at the gateway
seam. Live runs need a fresh human grant and refuse without one.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

STUDY_ID = "s09-pilot-n5"
STUDY_ROOT = "s09-m5-pilot"
ARMS = ["P0", "P1", "P2"]
PER_EPISODE_STEPS = 6
PER_EPISODE_CALLS = 6
STUDY_MODEL_CALLS = 100
CONSTRUCTION_CALLS = 4
N_DEV = 4
N_ASSESS = 12

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 16,
        "model_calls": 6}
AUTHORIZED = 30000
ROOT_AUTHORIZED = 2000000


def _root_allocation() -> str:
    return "ad01-campaign-s09-m5-root"


def _authorize_root(dsn: str) -> None:
    from experiments.ad01 import trajectory
    trajectory.authorize_campaign(
        dsn, "s09-m5-root", authorized=ROOT_AUTHORIZED,
        study_root=STUDY_ROOT,
        ceilings={"model_calls": STUDY_MODEL_CALLS,
                  "construction_calls": CONSTRUCTION_CALLS})


def _authorize(dsn: str, cid: str) -> str:
    from settlement import store
    from settlement.common import Command, ResultCode
    made = store.subdivide_allocation(
        dsn, Command(
            request_id="subdivide-ad01-campaign-%s" % cid,
            payload={"parent_id": _root_allocation(),
                     "child_id": "ad01-campaign-%s" % cid,
                     "domain": "study", "authorized": AUTHORIZED,
                     "max_occupancy": 8}))
    if made.code not in (ResultCode.APPLIED,
                         ResultCode.ALREADY_APPLIED):
        raise ValueError("campaign allocation refused: %s" %
                         made.detail)
    return "ad01-campaign-%s" % cid

class StudyGuardRefusal(RuntimeError):
    pass


class _BufferedResponse:
    def __init__(self, response, raw):
        self.status_code = response.status_code
        self.headers = response.headers
        self.extensions = response.extensions
        self.request = response.request
        self._raw = raw

    def iter_raw(self):
        yield self._raw


class _CostCapturingClient:
    def __init__(self, costs):
        import httpx
        self._client = httpx.Client()
        self._costs = costs

    def stream(self, method, url, *args, **kwargs):
        import contextlib
        import json as _json
        client = self

        @contextlib.contextmanager
        def opened():
            with client._client.stream(method, url, *args, **kwargs) as response:
                if str(method).upper() == "POST":
                    raw = response.read()
                    try:
                        client._costs.append(_json.loads(raw))
                    except ValueError:
                        client._costs.append(None)
                    response = _BufferedResponse(response, raw)
                yield response

        return opened()

    def __getattr__(self, name):
        return getattr(self._client, name)

    def close(self):
        self._client.close()


def _field(value, name):
    if isinstance(value, dict):
        return (name in value, value.get(name))
    if hasattr(value, name):
        return True, getattr(value, name)
    return False, None


def _cost_fields(*values):
    found = []
    pending = list(values)
    while pending:
        value = pending.pop()
        if value is None:
            continue
        for name in ("cost", "market_cost", "marketCost", "gatewayCost",
                     "surchargeCost", "upstream_inference_cost"):
            present, cost = _field(value, name)
            if present:
                found.append((name, cost))
        for name in ("usage", "providerMetadata", "provider_metadata", "model_meta"):
            present, nested = _field(value, name)
            if present and nested is not None:
                pending.append(nested)
        present, nested = _field(value, "gateway")
        if present and nested is not None:
            pending.append(nested)
    return found


def _cost_is_zero(value):
    if isinstance(value, bool):
        return False
    try:
        return float(value) == 0.0
    except (TypeError, ValueError, OverflowError):
        return False


class StudyGatewayGuard:
    def __init__(self, delegate, *, pinned_model: str,
                 ceiling: int = STUDY_MODEL_CALLS,
                 already_spent: int = 2) -> None:
        if not pinned_model:
            raise ValueError("pinned model is required")
        if ceiling < 0 or already_spent < 0:
            raise ValueError("model-call ceiling and spent count must be nonnegative")
        self.delegate = delegate
        self.pinned_model = pinned_model
        self.ceiling = ceiling
        self.dispatch_count = already_spent
        self.refusal_reason = ""
        self._cost_blocked: str | None = None

    def _refuse(self, reason: str):
        self.refusal_reason = reason
        raise StudyGuardRefusal(reason)

    def _captured(self):
        costs = getattr(self.delegate, "_s09_costs", None)
        if costs:
            return costs.pop(0)
        return None

    def _block_on_incurred_cost(self, reason: str):
        self.refusal_reason = reason
        self._cost_blocked = reason

    def _check_incurred_cost(self, response, captured):
        seen = list(_cost_fields(response, captured))
        usage = getattr(response, "usage", None)
        if usage is not None:
            seen.append(("usage.charge_units",
                         getattr(usage, "charge_units", 0)))
        for name, value in seen:
            if not _cost_is_zero(value):
                self._block_on_incurred_cost(
                    "response reports nonzero cost in %s: %r;"
                    " charge already incurred, later calls blocked"
                    % (name, value))
                return

    def infer(self, request):
        checks = (
            (self._cost_blocked is not None,
             self._cost_blocked or "prior response cost blocked later calls"),
            (request.model != self.pinned_model,
             "request model is not the pinned model %r" % self.pinned_model),
            (self.dispatch_count >= self.ceiling,
             "study model-call ceiling %d reached" % self.ceiling),
        )
        for refused, reason in checks:
            if refused:
                self._refuse(reason)
        self.dispatch_count += 1
        response = self.delegate.infer(request)
        captured = self._captured()
        from settlement.gateway import GatewayError
        if isinstance(response, GatewayError):
            self._check_incurred_cost(response, captured)
            return response
        fields = _cost_fields(response, captured)
        if not fields:
            self._refuse("response cost is unverified: every cost field is absent")
        for name, value in fields:
            if not _cost_is_zero(value):
                self._refuse("response reports nonzero cost in %s: %r" %
                             (name, value))
        return response

    def check_discovery(self):
        return self.delegate.check_discovery()

    def check_auth(self):
        return self.delegate.check_auth()

    def cancel(self, operation_id):
        return self.delegate.cancel(operation_id)

    def guard_status(self):
        return {"pinned_model": self.pinned_model,
                "ceiling": self.ceiling,
                "dispatch_count": self.dispatch_count,
                "refusal_reason": self.refusal_reason}


DEV_SPECS = [
    {"episode_id": "dev-sw-0", "domain": "software", "world": 0,
     "task_id": "ad01-w0-dev-sw-00"},
    {"episode_id": "dev-sw-1", "domain": "software", "world": 0,
     "task_id": "ad01-w0-dev-sw-01"},
    {"episode_id": "dev-gr-0", "domain": "graph", "world": 0,
     "task_id": "ad01-w0-dev-gr-00"},
    {"episode_id": "dev-gr-1", "domain": "graph", "world": 0,
     "task_id": "ad01-w0-dev-gr-01"},
]

P1_TASK = "ad01-w0-dev-sw-00"
P2_TASK = P1_TASK

REVISION_DRIVER_P1_SOURCE = (
    "def STEP(view, state):\n"
    "    task = view['task_content']\n"
    "    feedback = [o for o in view['observations']\n"
    "                if o.get('verdict') not in (None, 'unmeasured')]\n"
    "    if len(feedback) < 1:\n"
    "        action = {'kind': 'diagnose', 'target': task['task_id'],\n"
    "                  'inputs': {'diagnostic': task['family']},\n"
    "                  'evidence_refs': [], 'requested_resources': {'queries': 1}}\n"
    "    else:\n"
    "        action = {'kind': 'propose_revision', 'target': task['task_id'],\n"
    "                  'inputs': {'motivation': 'improve',\n"
    "                             'scope': {'family': task['family']}},\n"
    "                  'evidence_refs': [feedback[-1]['observation_id']],\n"
    "                  'requested_resources': {}}\n"
    "    return {'action': action, 'state': state}\n"
)
REVISION_DRIVER_P2_SOURCE = REVISION_DRIVER_P1_SOURCE.replace(
    "if len(feedback) < 1:", "if len(feedback) < 2:")

P0_POLICY_SOURCE = (
    "def STEP(view, state):\n"
    "    task = view['task_content']\n"
    "    if state.get('used'):\n"
    "        return {'action': {'kind': 'stop', 'target': task['task_id'], "
    "'inputs': {'reason': 'policy complete'}, 'evidence_refs': [], "
    "'requested_resources': {}}, 'state': state}\n"
    "    return {'action': {'kind': 'construct_method', "
    "'target': task['task_id'], 'inputs': {'diagnostic': task['family'], "
    "'max_queries': 16}, 'evidence_refs': [], "
    "'requested_resources': {'queries': 16}}, 'state': {'used': True}}\n"
)
P1_POLICY_SOURCE = (
    "def STEP(view, state):\n"
    "    task = view['task_content']\n"
    "    if state.get('done'):\n"
    "        action = {'kind': 'stop', 'target': task['task_id'],\n"
    "                  'inputs': {'reason': 'candidate complete'},\n"
    "                  'evidence_refs': [], 'requested_resources': {}}\n"
    "    else:\n"
    "        action = {'kind': 'construct_method', 'target': task['task_id'],\n"
    "                  'inputs': {'max_queries': 4}, 'evidence_refs': [],\n"
    "                  'requested_resources': {'queries': 4}}\n"
    "    return {'action': action, 'state': {'done': True}}\n"
)
P2_POLICY_SOURCE = P1_POLICY_SOURCE
BROKEN_POLICY_SOURCE = "not-json{{{"
METHOD_SOURCE = (
    "def ENTRY(task, oracle, max_queries=16):\n"
    "    if task['family'] == 'software':\n"
    "        return reducers.reduce_software(task, oracle, method='greedy', "
    "max_queries=max_queries)\n"
    "    return reducers.reduce_graph(task, oracle, method='greedy', "
    "max_queries=max_queries)\n"
)


def _assess_specs() -> list:
    specs = []
    for arm in ARMS:
        for world in (1, 2):
            for domain in ("software", "graph"):
                tag = "sw" if domain == "software" else "gr"
                specs.append({
                    "episode_id": "assess-%s-w%d-%s" % (arm, world,
                                                       domain),
                    "arm": arm, "world": world, "domain": domain,
                    "investigation_task": "ad01-w%d-dev-%s-00" % (
                        world, tag),
                    "use_tasks": ["ad01-w%d-within-%s-00" % (world,
                                                             tag),
                                  "ad01-w%d-transfer-%s-00" % (
                                      world, tag)]})
    return specs


def _digest_json(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _gateway_identity(mode: str, gateway, model: str) -> dict:
    endpoint = str(getattr(gateway, "endpoint", "") or "")
    return {"mode": mode, "model": model,
            "adapter": "%s.%s" % (type(gateway).__module__,
                                    type(gateway).__name__),
            "api": getattr(gateway, "api", ""),
            "endpoint_digest": (hashlib.sha256(endpoint.encode()).hexdigest()
                                 if endpoint else "")}


def _policy_identity(entry: dict, *, task_id: str = "",
                     experience_digest: str = "") -> dict:
    status = entry.get("status", "available")
    identity = {"status": status, "task_id": task_id,
                "experience_digest": experience_digest,
                "calls": int(entry.get("calls", 0))}
    if status == "available":
        artifact = entry.get("policy_artifact") or entry.get("artifact")
        identity.update({"source": entry["policy_source"],
                         "source_digest": entry.get("source_digest") or
                         artifact["source_digest"],
                         "artifact": dict(artifact)})
    else:
        identity["reason"] = entry.get("reason", "")
    return identity


def _method_repertoire(campaigns: list) -> dict:
    members = [episode["executable"] for campaign in campaigns
               for episode in campaign.get("episodes", [])
               if episode.get("disposition") == "retained"
               and isinstance(episode.get("executable"), dict)]
    return {"members": members,
            "member_digests": sorted(member["source_digest"]
                                      for member in members
                                      if member.get("source_digest"))}


def build_freeze(*, gateway_mode: str = "doubles", gateway=None,
                 model: str = "recorded-double") -> dict:
    from experiments.ad01 import checker
    from experiments.ad01 import packet as _packet
    from experiments.ad01 import trajectory as _traj
    from experiments.ad01 import worlds
    assess = _assess_specs()
    try:
        effort = _traj.reasoning_effort()
    except Exception:
        effort = "unknown"
    freeze = {
        "study_id": STUDY_ID,
        "study_root": STUDY_ROOT,
            "policy_abi": "ad01-policy-step-v1",
            "artifact_kind": "learning-policy",
        "arms": list(ARMS),
        "order": [e["episode_id"] for e in DEV_SPECS] + [
            e["episode_id"] for e in assess],
        "development": [dict(e) for e in DEV_SPECS],
        "construction_allowance": {
            "P1": {"init": 1, "repair": 1},
            "P2": {"init": 1, "repair": 1}},
        "construction_experience": {
            "P1": "interface-and-objective-only",
            "P2": "permitted-development-observations"},
        "assessment": assess,
        "caps": {
            "per_episode": {"policy_steps": PER_EPISODE_STEPS,
                            "model_calls": PER_EPISODE_CALLS},
            "diagnostic_queries_per_episode": 16,
            "study_model_calls": STUDY_MODEL_CALLS,
            "construction_calls": CONSTRUCTION_CALLS,
            "dev_episodes": N_DEV,
            "assessment_episodes": N_ASSESS},
        "metric_rule": {
            "quality": "preserved-verdict-plus-normalized-reduction",
            "compare": ["P2-vs-P0", "P2-vs-P1"],
            "scope": "sealed-use-tasks-only"},
        "resource_rule": {
            "unknown_blocks_claims": True,
            "missing_arm_narrows_result": True,
            "no_replacement_episodes": True},
        "config": {
            **_gateway_identity(gateway_mode, gateway, model),
            "reasoning_effort": effort,
            "packet_version": _packet.PACKET_VERSION,
            "freeze_id": worlds.FREEZE_ID,
            "freeze_digest": checker.freeze_digest(
                worlds.FROZEN_DIR),
            "protocol": "broker-v1",
            "profile": "local-process"},
        "policy_identities": {},
        "method_repertoires": {},
        "phase": "initial",
    }
    from scripts.s09_verify import freeze_digest
    freeze["freeze_digest"] = freeze_digest(freeze)
    return freeze



def _campaign_ops(dsn: str, cid: str) -> list:
    from experiments.ad01 import trajectory
    return sorted(op["id"] for op in
                  trajectory._campaign_operations(dsn, cid))


def _policy_record(source: str, *, parent_digest: str | None = None,
                   origin: str = "authored-control") -> dict:
    from experiments.ad01 import policy_step
    artifact = policy_step.make_policy_artifact(
        source, origin=origin, parent_digest=parent_digest,
        applicability={"study_id": STUDY_ID})
    return {"artifact": artifact["artifact"],
            "policy_source": artifact["policy_source"]}


def _policy_digests(dsn: str, cid: str) -> list:
    from experiments.ad01 import trajectory
    digests = []
    with trajectory._read_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT policy_output FROM s09_policy_state"
            " WHERE investigation_id = %s ORDER BY seq", (cid,)).fetchall()
    for row in rows:
        digest = dict(row["policy_output"] or {}).get("source_digest")
        if isinstance(digest, str) and digest not in digests:
            digests.append(digest)
    return digests


def _operation_requests(dsn: str, op_ids: list) -> list:
    from experiments.ad01 import trajectory
    requests = []
    with trajectory._read_conn(dsn) as conn:
        for op_id in op_ids:
            row = conn.execute(
                "SELECT payload FROM operations WHERE id = %s", (op_id,)
                ).fetchone()
            if row is None:
                continue
            payload = dict(row["payload"] or {})
            if payload.get("effect") != "model-inference" or "-policy-l" not in op_id:
                continue
            request = dict(payload.get("payload") or {})
            requests.append({"operation_id": op_id, "model": request.get("model", ""),
                             "messages": list(request.get("messages") or []),
                             "max_output_tokens": request.get("max_output_tokens"),
                             "reasoning_effort": request.get("reasoning_effort")})
    return requests


def _request_core(request: dict) -> dict:
    messages = list(request.get("messages") or [])
    prompt = messages[0].get("content", "") if messages else ""
    lines = [line for line in str(prompt).splitlines()
             if not line.startswith("Prior observations:")]
    core = dict(request)
    core.pop("operation_id", None)
    core.pop("experience", None)
    core["messages"] = [{"role": messages[0].get("role", "user"),
                          "content": "\n".join(lines)}] if messages else []
    return core


def _stable_cycle_value(value):
    if isinstance(value, dict):
        return {key: _stable_cycle_value(item)
                for key, item in value.items() if key != "child_wall_ms"}
    if isinstance(value, list):
        return [_stable_cycle_value(item) for item in value]
    return value


def _run_episode(dsn: str, world: int, seq: int, task: str,
                 policy: dict | None, gateway=None,
                 model: str = "recorded-double", tasks: list | None = None,
                 release_id: str | None = None,
                 bound_digest: str = "") -> tuple:
    from experiments.ad01 import agenda_policy, trajectory
    cid = trajectory.campaign_id(world, "I", seq)
    allocation = _authorize(dsn, cid)
    consumer = None
    constructor = "seed" if release_id is not None else "model"
    if release_id is None:
        if policy is None:
            raise ValueError("policy is required without a release")
        consumer = agenda_policy.step_policy_consumer(
            policy, dsn=dsn, cid=cid, charter=dict(CHARTER), world=world,
            arm="I", allocation_id=allocation, study_root=STUDY_ROOT,
            gateway=gateway, model=model, max_policy_steps=PER_EPISODE_STEPS)
    campaign = trajectory.run_campaign(
        world, "I", dict(CHARTER), dict(CAPS), tasks=list(tasks or [task]),
        campaign_seq=seq, dsn=dsn, study_root=STUDY_ROOT,
        gateway=gateway, model=model, constructor=constructor,
        consumer=consumer, policy_release=release_id)
    actions = []
    for boundary in campaign["boundaries"]:
        decision = boundary.get("decision") or {}
        actions.append(decision.get("next_action") or
                       dict(decision.get("investigation") or {}).get(
                           "next_action") or decision)
    try:
        digests = _policy_digests(dsn, cid)
    except Exception:
        digests = []
    expected = bound_digest
    if not expected and policy is not None:
        expected = policy["artifact"]["source_digest"]
    executed = digests[0] if len(digests) == 1 else ""
    record = {"campaign_id": cid, "task_id": task,
              "policy_steps": len(campaign["boundaries"]),
              "model_calls": int(campaign["model_calls"]),
              "witness_queries": int(campaign["queries"]),
              "construction_calls": int(campaign["construction_calls"]),
              "policy_digest": expected or executed,
              "executed_policy_digests": digests,
              "executed_policy_digest": executed or expected,
              "policy_release": release_id,
              "release_id": release_id,
              "bound_digest": bound_digest,
              "policy_actions": actions,
              "dispositions": [e.get("disposition") for e in
                             campaign["episodes"]],
              "operations": _campaign_ops(dsn, cid),
              "status": "complete" if campaign["boundaries"] else "unavailable"}
    return record, campaign


def _recording_gateway(scripts: list):
    from experiments.ad01.learner import RecordingGatewayAdapter
    return RecordingGatewayAdapter(scripts)


def _http_gateway(endpoint: str):
    from settlement.gateway_http import HttpGatewayAdapter
    if not endpoint:
        raise ValueError("controlled gateway endpoint is required")
    costs = []
    adapter = HttpGatewayAdapter(
        endpoint=endpoint, api="responses", client=_CostCapturingClient(costs))
    adapter._s09_costs = costs
    return adapter


def _guard_http_gateway(adapter):
    costs = []
    adapter._client = _CostCapturingClient(costs)
    adapter._s09_costs = costs
    return adapter


def _script(text: str) -> dict:
    return {"text": text}


def _construct_arm(dsn: str, arm: str, task_id: str,
                   driver_source: str, candidate_gateway=None,
                   seq: int = 54, model: str = "recorded-double") -> dict:
    from experiments.ad01 import trajectory
    driver = _policy_record(driver_source)
    tasks = [task_id] * (2 if arm == "P1" else 3)
    record, campaign = _run_episode(
        dsn, 0, seq, task_id, driver, gateway=candidate_gateway,
        model=model, tasks=tasks)
    revision = next((entry for entry in campaign.get("episodes", [])
                     if entry.get("kind") == "policy_revision"), None)
    operations = _campaign_ops(dsn, record["campaign_id"])
    requests = _policy_requests(dsn, operations)
    observations = _dev_observations(dsn, record["campaign_id"])
    experience_digest = _digest_json({
        "observations": observations if arm == "P2" else observations[:1]})
    base = {"arm": arm, "task_id": task_id,
            "experience_digest": experience_digest,
            "status": "unavailable", "disposition": "unavailable",
            "reason": "revision episode was not reached", "calls": 0,
            "operations": operations, "campaign_id": record["campaign_id"],
            "construction_requests": requests,
            "requests": requests, "policy_candidate": None,
            "policy_source": "", "policy_artifact": {},
            "source_digest": "", "candidate_digest": "",
            "release_id": None, "bound_digest": "", "scope": {}}
    if revision is None:
        return base
    candidate = dict(revision.get("policy_candidate") or {})
    freeze = dict(revision.get("freeze") or {})
    source = candidate.get("policy_source") or freeze.get("source", "")
    digest = freeze.get("candidate_digest") or candidate.get(
        "source_digest", "")
    disposition = revision.get("disposition", "unavailable")
    base.update({
        "status": "available" if disposition == "bound" else disposition,
        "disposition": disposition,
        "reason": revision.get("reason", ""),
        "calls": int(revision.get("construction_calls", 0)),
        "policy_candidate": candidate or None,
        "policy_source": source, "policy_artifact": dict(
            candidate.get("policy_artifact") or {}),
        "source_digest": digest, "candidate_digest": digest,
        "release_id": revision.get("release_id"),
        "bound_digest": revision.get("bound_digest", ""),
        "scope": dict(candidate.get("scope") or
                       revision.get("scope") or {}),
        "freeze": _stable_cycle_value(freeze),
        "assessment": _stable_cycle_value(revision.get("assessment")),
        "revision_episode": _stable_cycle_value(revision),
        "init_operation": (candidate.get("lineage") or {}).get(
            "init_operation"),
        "repair_operation": (candidate.get("lineage") or {}).get(
            "repair_operation"),
    })
    if base["status"] == "available" and not base["release_id"]:
        raise ValueError("bound arm %s has no release id" % arm)
    return base


def _policy_requests(dsn: str, op_ids: list) -> list:
    from experiments.ad01 import trajectory
    requests = []
    with trajectory._read_conn(dsn) as conn:
        for op_id in op_ids:
            row = conn.execute(
                "SELECT payload FROM operations WHERE id = %s", (op_id,)
            ).fetchone()
            if row is None:
                continue
            payload = dict(row["payload"] or {})
            if payload.get("effect") != "model-inference" or "-policy-l" not in op_id:
                continue
            request = dict(payload.get("payload") or {})
            messages = list(request.get("messages") or [])
            prompt = str(messages[0].get("content", "")) if messages else ""
            prefix, marker, experience = prompt.partition(
                "\nPrior observations: ")
            requests.append({"operation_id": op_id,
                             "model": request.get("model", ""),
                             "max_output_tokens": request.get(
                                 "max_output_tokens"),
                             "deadline_ms": request.get("deadline_ms"),
                             "reasoning_effort": request.get(
                                 "reasoning_effort", ""),
                             "prompt_without_experience": prefix,
                             "experience": experience if marker else ""})
        conn.commit()
    return requests


def _embed_operations(dsn: str, op_ids: set) -> dict:
    from experiments.ad01 import trajectory
    embedded = {}
    with trajectory._read_conn(dsn) as conn:
        for op_id in sorted(op_ids):
            row = conn.execute(
                "SELECT payload FROM operations WHERE id = %s",
                (op_id,)).fetchone()
            if row is None:
                continue
            receipts = conn.execute(
                "SELECT receipt_identity, operation_id, content,"
                " outcome FROM receipts WHERE operation_id = %s"
                " ORDER BY receipt_identity",
                (op_id,)).fetchall()
            slim = []
            for receipt in receipts:
                content = dict(receipt["content"] or {})
                usage = dict(content.get("usage") or {})
                slim.append({
                    "receipt_identity": receipt["receipt_identity"],
                    "operation_id": receipt["operation_id"],
                    "outcome": receipt["outcome"],
                    "usage": {key: usage.get(key) for key in
                              ("input_tokens", "output_tokens",
                               "charge_units", "billed")}})
            embedded[op_id] = {
                "effect": dict(row["payload"] or {}).get("effect",
                                                         ""),
                "receipts": slim}
        conn.commit()
    return embedded


def _refusal_probes(dsn: str) -> list:
    from experiments.ad01 import construct, trajectory, worlds
    probes = []
    cid = trajectory.campaign_id(0, "I", 98)
    _authorize(dsn, cid)
    trajectory.ensure_campaign(
        dsn, cid, 0, "I", dict(CHARTER), dict(CAPS),
        tasks=[P1_TASK], study_root=STUDY_ROOT)
    before = set(_campaign_ops(dsn, cid))
    refused = False
    detail = ""
    try:
        construct.construct_policy(
            dsn, campaign_id=cid,
            task=worlds.load_task(worlds.FROZEN_DIR, P1_TASK),
            experience={"observations": [],
                        "boundary": {"seq": 0}},
            budget={"max_output_tokens": 512, "max_queries": 4,
                    "model_calls": 0},
            gateway=_recording_gateway([]), model="recorded-double",
            study_root=STUDY_ROOT)
    except construct.ConstructionFailed as exc:
        refused = True
        detail = str(exc)
    after = set(_campaign_ops(dsn, cid))
    probes.append({"probe_id": "model-cap-zero-refuses",
                   "refused": refused, "detail": detail,
                   "observed_new_ops": sorted(after - before)})
    cid2 = trajectory.campaign_id(0, "I", 99)
    _authorize(dsn, cid2)
    before2 = set(_campaign_ops(dsn, cid2))
    campaign = trajectory.run_campaign(
        0, "I", dict(CHARTER),
        dict(CAPS, max_boundaries=0), tasks=[P1_TASK],
        campaign_seq=99, dsn=dsn, study_root=STUDY_ROOT)
    after2 = set(_campaign_ops(dsn, cid2))
    probes.append({
        "probe_id": "boundary-cap-zero-refuses",
        "refused": campaign["boundaries"] == [] and campaign[
            "stop"] == {"reason": "boundary cap reached"},
        "detail": str(campaign["stop"]),
        "observed_new_ops": sorted(after2 - before2)})
    return probes


def _conformance_replay(dsn: str, campaign: dict) -> dict:
    from experiments import doubles
    from experiments.ad01 import records
    export = records.export_campaign(
        dsn, campaign, model="recorded-double", charter=dict(CHARTER),
        caps=dict(CAPS))
    recorded = doubles.recorded_from_export(export)
    if not recorded:
        raise ValueError("conformance export holds no transitions")
    rec = recorded[0]
    proposal = dict(rec.get("proposal") or {})
    inputs = dict(proposal.get("inputs") or {})
    versions = {key: inputs.get(key) for key in doubles.VERSION_FIELDS}
    code = {key: value for key, value in inputs.items()
            if key not in doubles.VERSION_FIELDS}
    action = {"target": proposal.get("target"),
              "instrument": proposal.get("instrument"),
              "inputs": code,
              "dependencies": list(proposal.get("dependencies") or []),
              "requested": dict(proposal.get("requested") or {})}
    pool: set = set()
    for prior in recorded[:0]:
        pool.update(prior.get("operations") or [])
        pool.update(prior.get("results") or [])
    base = {"index": 0, "packet_digest": rec.get("packet_digest"),
            "action": action, "versions": versions,
            "observations": sorted(pool)}
    identity = doubles.check_replay_prefix(recorded, dict(base))
    changed = dict(base)
    changed["action"] = dict(action, instrument="changed-instrument")
    changed_verdict = doubles.check_replay_prefix(recorded, changed)
    return {"status": "conformance",
            "export_campaign": str(campaign.get("campaign_id", "")),
            "identity": identity.get("verdict", ""),
            "changed": changed_verdict.get("verdict", "")}


def _assert_gateway_preflight(gateway_mode: str, gateway) -> None:
    if gateway_mode not in ("controlled", "live"):
        return
    from settlement.gateway_http import HttpGatewayAdapter
    if not isinstance(gateway, HttpGatewayAdapter) or gateway.api != "responses":
        raise ValueError("configured gateway is not the responses HTTP adapter")
    if not gateway.endpoint:
        raise ValueError("configured HTTP adapter has no endpoint")


def _verify_http_policy_path(dsn: str, gateway, construction: dict) -> None:
    from experiments.ad01 import packet, records, selection
    from settlement.gateway_http import HttpGatewayAdapter
    if isinstance(gateway, StudyGatewayGuard):
        gateway = gateway.delegate
    if not isinstance(gateway, HttpGatewayAdapter):
        return
    for arm, entry in construction.items():
        if entry.get("status") != "available":
            continue
        source = entry.get("policy_source", "")
        candidate = entry.get("policy_candidate") or {}
        lineage = candidate.get("lineage") or {}
        carried = False
        with __import__("psycopg").connect(dsn) as conn:
            for operation_id in (lineage.get("init_operation"),
                                 lineage.get("repair_operation")):
                if not operation_id:
                    continue
                row = conn.execute(
                    "SELECT content FROM receipts WHERE operation_id = %s"
                    " AND receipt_identity = %s AND outcome = 'success'",
                    (operation_id, "gw:%s" % operation_id)).fetchone()
                if row is None:
                    continue
                text = dict(row[0] or {}).get("text", "")
                returned, problem = packet.parse_construction_response(text)
                if not problem and returned == source:
                    carried = True
                    break
        if not carried:
            raise ValueError("HTTP adapter did not carry bound policy bytes for %s" % arm)
        digest = hashlib.sha256(source.encode()).hexdigest()
        if entry.get("freeze", {}).get("candidate_digest") != digest:
            raise ValueError("HTTP policy bytes lost their freeze digest for %s" % arm)
        if entry.get("bound_digest") != digest:
            raise ValueError("HTTP policy bytes lost their bind digest for %s" % arm)
        assessment = entry.get("assessment") or {}
        if assessment.get("candidate_digest") != digest:
            raise ValueError("HTTP policy bytes lost their assessment digest for %s" % arm)
        binding = selection.active_binding_for(
            dsn, (entry.get("scope") or {}).get("family", "software"),
            release_id=entry.get("release_id"))
        provenance = selection.binding_provenance(binding or {})
        if not binding or provenance.get("candidate_digest") != digest:
            raise ValueError("HTTP policy bytes were not durably bound for %s" % arm)
        loaded = records.load_freeze(dsn, (entry.get("freeze") or {}).get(
            "proposal_id", ""))
        if not loaded or loaded.get("source") != source:
            raise ValueError("HTTP policy bytes were not durably frozen for %s" % arm)


def _study_report(construction: dict, assessment: list,
                  use_records: list) -> dict:
    by_arm = {arm: [row for row in assessment if row.get("arm") == arm]
              for arm in ARMS}
    reports = {}
    for arm in ARMS:
        entry = construction.get(arm, {})
        rows = by_arm[arm]
        uses = [row for row in use_records if row.get("study_arm") == arm]
        reports[arm] = {
            "construction_delivery": {
                "status": entry.get("disposition", "authored"),
                "calls": int(entry.get("calls", 0)),
                "release_id": entry.get("release_id"),
                "candidate_digest": entry.get("bound_digest", "") or
                (hashlib.sha256(P0_POLICY_SOURCE.encode()).hexdigest()
                 if arm == "P0" else ""),
            },
            "executable_validity": {
                "available": arm == "P0" or entry.get("status") == "available",
                "executed_digests": sorted({row.get("executed_policy_digest", "")
                                             for row in rows
                                             if row.get("executed_policy_digest")}),
            },
            "coverage": {domain: {
                "status": "covered" if arm == "P0" or
                (entry.get("status") == "available" and
                 (entry.get("scope") or {}).get("family") == domain)
                else ("not-covered-by-revised-policy" if entry.get(
                    "status") == "available" else "arm-unavailable")
            } for domain in ("software", "graph")},
            "changed_decisions": sum(len(row.get("policy_actions", []))
                                     for row in rows),
            "effects": {"dispositions": {
                kind: sum(value == kind for row in rows
                          for value in row.get("dispositions", []))
                for kind in ("retained", "inspected", "rejected",
                             "no-candidate")}},
            "downstream_task_quality": {
                "tasks": len(uses),
                "preserved": sum(row.get("verdict") == "preserved"
                                  for row in uses),
                "normalized_reduction": sum(
                    float(row.get("normalized_reduction", 0.0) or 0.0)
                    for row in uses),
            },
            "resource_cost": {
                "policy_steps": sum(int(row.get("policy_steps", 0))
                                     for row in rows),
                "model_calls": sum(int(row.get("model_calls", 0))
                                    for row in rows),
                "witness_queries": sum(int(row.get("witness_queries", 0))
                                        for row in rows),
                "construction_calls": int(entry.get("calls", 0)),
                "sealed_use_tasks": len(uses),
            },
        }
    missing = [arm for arm in ("P1", "P2")
               if construction.get(arm, {}).get("status") != "available"]
    comparisons = {}
    for baseline in ("P0", "P1"):
        candidate = reports["P2"]
        base = reports[baseline]
        comparisons["P2-vs-%s" % baseline] = {
            "status": "complete" if not missing and base[
                "executable_validity"]["available"] else "incomplete",
            "candidate": "P2", "baseline": baseline,
            "candidate_metrics": candidate,
            "baseline_metrics": base,
            "not_covered_domains": [domain for domain in ("software", "graph")
                                    if candidate["coverage"][domain]["status"] !=
                                    "covered" or base["coverage"][domain][
                                    "status"] != "covered"],
        }
    return {"status": "complete" if not missing else "incomplete",
            "complete": not missing,
            "comparison_complete": not missing,
            "incomplete_arms": missing,
            "missing_arms": missing,
            "arms": reports, "comparisons": comparisons}



def run_study(dsn: str, out_dir, *,
              gateway_mode: str = "doubles", gateway=None,
              model: str = "recorded-double") -> dict:
    provided_gateway = gateway is not None
    if gateway_mode == "live":
        import os
        if not os.environ.get("S09_M5_LIVE_GRANT"):
            raise ValueError("live runs require a fresh human grant")
    if gateway is None and gateway_mode == "controlled":
        import os
        gateway = _http_gateway(os.environ.get(
            "S09_CONTROLLED_GATEWAY_ENDPOINT", ""))
    if gateway is None and gateway_mode == "live":
        from settlement.config import Settings
        from settlement.gateway_http import HttpGatewayAdapter
        gateway = HttpGatewayAdapter.from_settings(
            Settings.from_env(), api="responses")
        _guard_http_gateway(gateway)
    if gateway is None:
        gateway = _recording_gateway([_script(json.dumps(
            {"entry": METHOD_SOURCE, "notes": "doubled method"}))])
    _assert_gateway_preflight(gateway_mode, gateway)
    from experiments.ad01 import trajectory
    from scripts import s09_verify as _verify
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    freeze = build_freeze(gateway_mode=gateway_mode, gateway=gateway,
                          model=model)
    if gateway_mode == "live":
        import os as _os
        spent = int(_os.environ.get("S09_STUDY_CALLS_ALREADY_SPENT", "2"))
        gateway = StudyGatewayGuard(
            gateway, pinned_model=model, ceiling=STUDY_MODEL_CALLS,
            already_spent=spent)
    authored = _policy_record(P0_POLICY_SOURCE)
    _authorize_root(dsn)

    development = []
    dev_campaigns = []
    for index, spec in enumerate(DEV_SPECS):
        record, campaign = _run_episode(
            dsn, spec["world"], 50 + index, spec["task_id"], authored,
            gateway=gateway, model=model)
        development.append({**spec, **record})
        dev_campaigns.append(campaign)

    if gateway_mode == "doubles" and not provided_gateway:
        p1_gateway = _recording_gateway([_script(json.dumps({
            "entry": P1_POLICY_SOURCE, "notes": "doubled candidate"}))])
        p2_gateway = _recording_gateway([_script("not-json{{{"),
                                         _script(BROKEN_POLICY_SOURCE)])
    else:
        p1_gateway = gateway
        p2_gateway = gateway
    construction = {
        "P1": _construct_arm(
            dsn, "P1", P1_TASK, REVISION_DRIVER_P1_SOURCE,
            candidate_gateway=p1_gateway, seq=54, model=model),
        "P2": _construct_arm(
            dsn, "P2", P2_TASK, REVISION_DRIVER_P2_SOURCE,
            candidate_gateway=p2_gateway, seq=55, model=model),
    }

    freeze["policy_identities"] = {
        "P0": _policy_identity(authored),
        "P1": _policy_identity(construction["P1"], task_id=P1_TASK,
                               experience_digest=construction["P1"][
                                   "experience_digest"]),
        "P2": _policy_identity(construction["P2"], task_id=P2_TASK,
                               experience_digest=construction["P2"][
                                   "experience_digest"]),
    }
    repertoire = _method_repertoire(dev_campaigns)
    freeze["method_repertoires"] = {
        arm: {"members": [dict(member) for member in repertoire["members"]],
              "member_digests": list(repertoire["member_digests"])}
        for arm in ARMS}
    freeze["phase"] = "preassessment"
    freeze["freeze_digest"] = _verify.freeze_digest(freeze)
    (out / "freeze.json").write_text(
        json.dumps(freeze, sort_keys=True, indent=1) + "\n")
    _verify_http_policy_path(dsn, gateway, construction)

    frozen_digest = freeze["freeze_digest"]
    assessment = []
    use_records = []
    for index, spec in enumerate(_assess_specs()):
        arm = spec["arm"]
        entry = construction.get(arm, {})
        release = entry.get("release_id")
        available = arm == "P0" or entry.get("status") == "available"
        family = (entry.get("scope") or {}).get("family")
        covered = arm == "P0" or (available and family == spec["domain"])
        if arm == "P0":
            record, campaign = _run_episode(
                dsn, spec["world"], 60 + index,
                spec["investigation_task"], authored,
                gateway=gateway, model=model)
            record["coverage_status"] = "covered"
        elif available and covered:
            record, campaign = _run_episode(
                dsn, spec["world"], 60 + index,
                spec["investigation_task"], None,
                gateway=gateway, model=model, release_id=release,
                bound_digest=entry.get("bound_digest", ""))
            record["coverage_status"] = "covered"
        elif available:
            release_attempt, _release_campaign = _run_episode(
                dsn, spec["world"], 60 + index,
                spec["investigation_task"], None,
                gateway=gateway, model=model, release_id=release,
                bound_digest=entry.get("bound_digest", ""))
            if _release_campaign["boundaries"]:
                raise ValueError("uncovered domain unexpectedly executed revised policy")
            record, campaign = _run_episode(
                dsn, spec["world"], 60 + index,
                spec["investigation_task"], authored,
                gateway=gateway, model=model)
            record.update({"policy_release": release, "release_id": release,
                           "bound_digest": entry.get("bound_digest", ""),
                           "policy_digest": entry.get("bound_digest", ""),
                           "coverage_status": "not-covered-by-revised-policy",
                           "fallback_reason": "arm-domain-uncovered: candidate"
                           " scope %s does not cover %s" % (family,
                                                               spec["domain"]),
                           "requested_policy_release": release,
                           "release_resolution": release_attempt})
        else:
            record = {"campaign_id": "unavailable-%s" % spec["episode_id"],
                      "task_id": spec["investigation_task"],
                      "policy_steps": 0, "model_calls": 0,
                      "witness_queries": 0, "construction_calls": 0,
                      "dispositions": [entry.get("disposition",
                                                  "unavailable")],
                      "operations": [], "status": "unavailable",
                      "policy_digest": "", "executed_policy_digests": [],
                      "executed_policy_digest": "", "policy_release": None,
                      "release_id": None, "bound_digest": "",
                      "policy_actions": [], "coverage_status":
                      "arm-unavailable: %s" % entry.get("disposition",
                                                          "unavailable"),
                      "fallback_reason": "arm-unavailable: %s" % entry.get(
                          "reason", "candidate unavailable")}
            campaign = None
        record = {**spec, **record, "freeze_digest": frozen_digest,
                  "policy_artifact_kind": ("learning-policy" if arm == "P0"
                                            or available else None),
                  "arm_disposition": ("authored" if arm == "P0" else
                                      entry.get("disposition", "unavailable")),
                  "comparison_status": ("complete" if covered else
                                         record.get("coverage_status",
                                                    "incomplete"))}
        assessment.append(record)

        if arm != "P0" and not available:
            absent_kind = entry.get("disposition", "unavailable")
            executed = "incumbent" if absent_kind == "unavailable" else "unavailable"
            prefix = "arm-unavailable:" if absent_kind == "unavailable" else "arm-rejected:"
            for task_id in spec["use_tasks"]:
                use_records.append({
                    "record_id": "%s-%s" % (spec["episode_id"], task_id),
                    "episode_id": spec["episode_id"], "study_arm": arm,
                    "arm": arm, "world": spec["world"], "task_id": task_id,
                    "status": "unavailable", "executed": executed,
                    "selected": executed, "requested": executed,
                    "release_id": None, "verdict": "unavailable",
                    "initial_measure": 0, "final_measure": 0,
                    "normalized_reduction": 0.0, "costs": {
                        "witness_queries": 0}, "output": {},
                    "operation_ids": [], "executed_source": executed,
                    "executed_source_digest": "", "policy_digest": "",
                    "policy_artifact_kind": None,
                    "fallback_reason": "%s %s" % (prefix, entry.get(
                        "reason", "candidate unavailable"))})
            continue

        use_cid = trajectory.campaign_id(spec["world"], "I", 90 + index)
        allocation = _authorize(dsn, use_cid)
        trajectory.ensure_campaign(
            dsn, use_cid, spec["world"], "I", dict(CHARTER),
            dict(CAPS), tasks=list(spec["use_tasks"]), study_root=STUDY_ROOT)
        use_repertoire = freeze["method_repertoires"].get(
            "P0" if arm == "P0" or not covered else arm,
            {"members": []})
        if arm != "P0" and not covered:
            use_repertoire = {"campaign_id": use_cid, "queries": 0,
                              "members": []}
        else:
            use_repertoire = {"campaign_id": use_cid,
                              "queries": use_repertoire.get("queries", 0),
                              "members": [dict(member) for member in
                                          use_repertoire.get("members", [])]}
        saved_records = trajectory.run_use(
            use_repertoire, spec["world"], "I", list(spec["use_tasks"]), {},
            dsn=dsn, allocation_id=allocation)
        for task_id, saved in zip(spec["use_tasks"], saved_records):
            saved["record_id"] = "%s-%s" % (spec["episode_id"], task_id)
            saved["episode_id"] = spec["episode_id"]
            saved["study_arm"] = arm
            saved["arm"] = arm
            saved["release_id"] = release if arm != "P0" else None
            saved["policy_digest"] = record.get("policy_digest", "")
            saved["executed_policy_digest"] = record.get(
                "executed_policy_digest", "")
            saved["policy_artifact_kind"] = record.get(
                "policy_artifact_kind")
            source = saved.get("executed_source")
            saved["executed_source_digest"] = (
                hashlib.sha256(source.encode()).hexdigest()
                if isinstance(source, str) else "")
            if arm != "P0" and not covered:
                saved["fallback_reason"] = (
                    "arm-domain-uncovered: bound policy scope %s does not"
                    " cover %s; incumbent executed" % (family, spec["domain"]))
                saved["arm_status"] = "available-incumbent-fallback"
            else:
                saved["arm_status"] = "available"
            use_records.append(saved)

    probes = _refusal_probes(dsn)
    claimed = set()
    for episode in development + assessment:
        claimed.update(episode.get("operations", []))
    for entry in construction.values():
        claimed.update(entry.get("operations", []))
    for saved in use_records:
        claimed.update(saved.get("operation_ids", []))
    operations = _embed_operations(dsn, claimed)
    rejected = sum(1 for episode in development + assessment
                   for disposition in episode.get("dispositions", [])
                   if disposition in ("rejected", "no-candidate"))
    executed = sum(episode.get("policy_steps", 0)
                   for episode in development + assessment)
    model_total = sum(episode.get("model_calls", 0)
                      for episode in development + assessment) + sum(
                          entry.get("calls", 0)
                          for entry in construction.values())
    repairs = sum(1 for entry in construction.values()
                  for operation in entry.get("operations", [])
                  if "-repair" in operation)
    guard_status = gateway.guard_status() if isinstance(
        gateway, StudyGatewayGuard) else None
    accounting = {
        "construction": {"measured": sum(entry.get("calls", 0)
                                           for entry in construction.values()),
                          "source": "durable-model-inference-operations"},
        "rejected_actions": {"measured": rejected,
                              "source": "episode-dispositions"},
        "policy_execution": {"measured": executed,
                              "source": "settled-boundaries"},
        "model_requests": {"measured": model_total,
                            "source": "episode-plus-construction-census"},
        "use": {"measured": len(use_records),
                "source": "sealed-use-records"},
        "repair": {"measured": repairs,
                    "source": "repair-attempt-operations"},
        "charge_units": {"measured": "unknown",
                          "source": "doubles-carry-no-priced-charge"},
        "dispatch_guard": guard_status,
    }
    report = _study_report(construction, assessment, use_records)
    comparison = {domain: {
        "same_non_experience": bool(
            construction["P1"].get("requests") and
            construction["P2"].get("requests") and
            _request_core(construction["P1"]["requests"][0]) ==
            _request_core(construction["P2"]["requests"][0])),
        "experience_differs": construction["P1"].get(
            "experience_digest") != construction["P2"].get(
                "experience_digest"),
    } for domain in ("software",)}
    bundle = {"freeze": freeze, "development": development,
              "construction": construction, "assessment": assessment,
              "use_records": use_records, "operations": operations,
              "accounting": accounting, "refusal_probes": probes,
              "conformance_replay": _conformance_replay(
                  dsn, dev_campaigns[0]), "report": report,
              "construction_request_comparison": comparison,
              "construction_requests": {
                  arm: construction[arm].get("requests", [])
                  for arm in ("P1", "P2")}}
    for name in ("development", "construction", "assessment", "use_records",
                 "operations", "accounting", "refusal_probes",
                 "conformance_replay", "report"):
        (out / ("%s.json" % name)).write_text(
            json.dumps(bundle[name], sort_keys=True, indent=1,
                       default=str) + "\n")
    verdict = _verify.verify_bundle(bundle)
    (out / "verify.json").write_text(
        json.dumps(verdict, sort_keys=True, indent=1) + "\n")
    if verdict["status"] != "pass" and report["complete"]:
        raise ValueError("pilot bundle fails verification: %s" %
                         verdict["problems"])
    return bundle



def _dev_observations(dsn: str, cid: str) -> list:
    from experiments.ad01 import trajectory
    settled, _pending = trajectory._read_campaign(dsn, cid)
    observations = []
    for seq in sorted(settled):
        observation = settled[seq].get("observation") or {}
        if observation.get("observation_id"):
            observations.append(observation)
    return observations


def main(argv: list | None = None) -> int:
    args = list(argv or [])
    if len(args) == 3 and args[0] == "freeze":
        out = Path(args[2] if args[1] == "--out" else args[1])
        out.mkdir(parents=True, exist_ok=True)
        freeze = build_freeze()
        (out / "freeze.json").write_text(
            json.dumps(freeze, sort_keys=True, indent=1) + "\n")
        print(freeze["freeze_digest"])
        return 0
    if len(args) >= 4 and args[0] == "run":
        dsn = ""
        dest = ""
        mode = "doubles"
        model = "recorded-double"
        index = 1
        while index < len(args):
            if args[index] == "--dsn":
                dsn = args[index + 1]
                index += 2
            elif args[index] == "--out":
                dest = args[index + 1]
                index += 2
            elif args[index] == "--mode":
                mode = args[index + 1]
                index += 2
            elif args[index] == "--model":
                model = args[index + 1]
                index += 2
            else:
                index += 1
        if not dsn or not dest:
            print("usage: s09_pilot.py run --dsn DSN --out DIR"
                  " [--mode doubles|live] [--model ID]", file=sys.stderr)
            return 2
        if mode == "live" and model == "recorded-double":
            print("live runs require an explicit --model", file=sys.stderr)
            return 2
        try:
            bundle = run_study(dsn, dest, gateway_mode=mode, model=model)
        except Exception as exc:
            print("s09-pilot refused: %s" % exc, file=sys.stderr)
            return 3
        print("s09-pilot %s episodes=%d use=%d model=%d" % (
            bundle["freeze"]["freeze_digest"][:8],
            len(bundle["development"]) + len(bundle["assessment"]),
            len(bundle["use_records"]),
            bundle["accounting"]["model_requests"]["measured"]))
        return 0
    print("usage: s09_pilot.py freeze --out DIR | run --dsn DSN"
          " --out DIR [--mode doubles|live]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
