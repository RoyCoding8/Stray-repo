"""Which artifact column governs a fresh-process use episode.

Finding S09R-02 alleges that the S09 pilot's four P1 software use records
execute an authored `ENTRY` method while carrying a bound STEP policy
digest copied from the investigation phase. The allegation is measured
here rather than narrated, by keeping two columns apart and asking the
same question of both.

The operational policy column is the STEP program: its construction
response, its bound digest, its release, and the action it admits when
replayed after a restart. The task method column is the ENTRY repertoire
member: its provenance, its entry name, and the bytes that actually ran.

Both columns are measured by running them. The policy column loads its
source from durable persisted state, recomputes `sha256(source)`, refuses
on any mismatch, and only then executes the bytes through
`method_exec.run_step_out_of_process`, which stages the source in a fresh
interpreter with a scrubbed environment. The method column runs
`trajectory.run_use`, the function `scripts/s09_pilot.run_study` calls at
`scripts/s09_pilot.py:1133`.

That executor refuses an execution that names no store, allocation and
operation id, so every entry point here takes that authority as an argument
and `proof_authority` mints a disposable one. This module has no refusal to
show and no reading to take: `fresh_process_evidence` reports a worker
status and a launcher receipt that exist only once a child has run, so a
proof that could not execute would report nothing about which column
governs. The authority is a disposable store created for these executions
and dropped after them, never a study or live store.

A negative result here is a finding. `governing_column` names the column
that governs, and the evidence for the other column's non-governance is
carried in the same report.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from . import method_exec
from . import policy_action
from . import policy_step
from . import s09_durable_state
from . import trajectory
from . import worlds

ROOT = Path(__file__).resolve().parents[2]

EVIDENCE = ROOT / "evidence_s09_m3_live"

PILOT_RUN_USE_CALL_SITE = "scripts/s09_pilot.py:1133"
PILOT_METHOD_SOURCE_SITE = "scripts/s09_pilot.py:299"
# The digest lands on a use record the policy never produced.
PILOT_DIGEST_COPY_SITE = "scripts/s09_pilot.py:1142"

PROVING = "operational-policy"
NOT_PROVING = "task-method"

TASK_ID = "ad01-w1-within-sw-00"
FAMILY = "software"
CAMPAIGN_ID = "ad01-w1-I-90"
BASELINE_METHOD = "seed-sw-greedy"
SUBSTITUTE_METHOD = "seed-sw-ddmin"

P1_SOFTWARE_USE_TASKS = (
    "ad01-w1-within-sw-00",
    "ad01-w1-transfer-sw-00",
    "ad01-w2-within-sw-00",
    "ad01-w2-transfer-sw-00",
)

SEED_METHOD_SOURCE = (
    "def ENTRY(task, oracle, max_queries=16):\n"
    "    if task['family'] == 'software':\n"
    "        return reducers.reduce_software(task, oracle, method='greedy', "
    "max_queries=max_queries)\n"
    "    return reducers.reduce_graph(task, oracle, method='greedy', "
    "max_queries=max_queries)\n"
)

SEED_POLICY_SOURCE = (
    "def STEP(view, state):\n"
    "    task = view['task_content']\n"
    "    if state.get('used'):\n"
    "        action = {'kind': 'stop', 'target': task['task_id'],\n"
    "                  'inputs': {'reason': 'episode complete'},\n"
    "                  'evidence_refs': [], 'requested_resources': {}}\n"
    "    else:\n"
    "        action = {'kind': 'use_method', 'target': task['task_id'],\n"
    "                  'inputs': {'method_id': %r,\n"
    "                             'max_queries': 4},\n"
    "                  'evidence_refs': [],\n"
    "                  'requested_resources': {'queries': 4}}\n"
    "    return {'action': action, 'state': {'used': True}}\n"
)

# The kinds `policy_step.validate_action` enforces.
STEP_ABI_ACTION_KINDS = policy_step.ACTION_KINDS
SHARED_ACTION_KINDS = policy_action.ACTION_KINDS


class PolicyNotProved(RuntimeError):
    """A countercheck the current code cannot pass."""


def sha256_of(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def seed_policy_source(method_id: str) -> str:
    return SEED_POLICY_SOURCE % (method_id,)


def use_repertoire(method_source: str = SEED_METHOD_SOURCE,
                   capability_id: str = BASELINE_METHOD) -> dict:
    """A repertoire dict shaped the way `run_use` reads one."""
    return {
        "campaign_id": CAMPAIGN_ID,
        "queries": 0,
        "members": [{
            "capability_id": capability_id,
            "family": FAMILY,
            "scope": {"family": FAMILY},
            "entry": "ENTRY",
            "method_source": method_source,
            "source_digest": sha256_of(method_source),
            "disposition": "retained",
        }],
    }


def use_view(methods: Sequence[str] = (BASELINE_METHOD, SUBSTITUTE_METHOD),
             task_id: str = TASK_ID) -> dict:
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    return policy_step.materialize_view(
        task=task, observations=[], open_questions=[], last_result=None,
        eligible_methods=list(methods), remaining={"steps": 6, "queries": 8})


@dataclass(frozen=True)
class PolicyBinding_:
    """A durable binding, checked without a store.

    `s09_durable_state.load_step` is the database-backed reader. It cannot
    run without a migrated disposable database, and the digest question
    here is answerable from persisted bytes alone, so this reads the same
    committed `construction.json` shape and applies the same equality rule
    the durable reader applies at
    `experiments/ad01/s09_durable_state.py:159`.
    """

    source: str
    recorded_digest: str
    origin: str
    durable: bool = True

    @property
    def digest(self) -> str:
        return sha256_of(self.source)

    def verified(self) -> "PolicyBinding_":
        if self.digest != self.recorded_digest:
            raise PolicyNotProved(
                "recomputed sha256(%d bytes) = %s does not equal the recorded"
                " bound digest %s" % (len(self.source), self.digest,
                                      self.recorded_digest))
        if self.durable and self.source not in _committed_policy_bytes(
                self.recorded_digest):
            raise PolicyNotProved(
                "recomputed source is not the bytes persisted at digest %s"
                % self.recorded_digest)
        return self

    def as_policy_record(self) -> dict:
        artifact = policy_step.make_policy_artifact(
            self.source, origin=self.origin)["artifact"]
        if artifact["source_digest"] != self.recorded_digest:
            raise PolicyNotProved(
                "make_policy_artifact produced %s, not the bound digest %s"
                % (artifact["source_digest"], self.recorded_digest))
        return {"artifact": artifact, "policy_source": self.source}

    def as_durable_binding(self) -> s09_durable_state.PolicyBinding:
        return s09_durable_state.PolicyBinding(
            policy_id="s09-p1-bound", digest=self.recorded_digest,
            digest_kind="source", origin=self.origin)


def _committed_policy_bytes(digest: str) -> list:
    out = []
    for name in ("construction.json",):
        path = EVIDENCE / name
        if not path.exists():
            continue
        entry = json.loads(path.read_text()).get("P1", {})
        for key in ("policy_source",):
            value = entry.get(key)
            if isinstance(value, str) and sha256_of(value) == digest:
                out.append(value)
        candidate = entry.get("policy_candidate", {})
        value = candidate.get("policy_source")
        if isinstance(value, str) and sha256_of(value) == digest:
            out.append(value)
    return out


def make_record(source: str, *, origin: str = "fixture-stand-in") -> dict:
    return policy_step.make_policy_artifact(source, origin=origin)


def load_bound_policy() -> PolicyBinding_:
    """Read the P1 policy from durable persisted state, not from source."""
    path = EVIDENCE / "construction.json"
    if not path.exists():
        raise PolicyNotProved("committed construction evidence is absent at %s"
                              % path)
    entry = json.loads(path.read_text()).get("P1", {})
    source = entry.get("policy_source")
    recorded = entry.get("bound_digest")
    if not isinstance(source, str) or not isinstance(recorded, str):
        raise PolicyNotProved(
            "committed construction evidence carries no P1 policy source"
            " plus bound digest")
    return PolicyBinding_(source=source, recorded_digest=recorded,
                          origin="authored-control")


def use_phase_names_policy() -> dict:
    """Whether the use phase the pilot calls can reach a policy at all.

    `trajectory.run_use` is the function the pilot's use phase runs. This
    reads its source and reports which policy surfaces it mentions, so the
    answer is the code's, not this module's assumption.
    """
    import inspect
    source = inspect.getsource(trajectory.run_use)
    return {
        "call_site": PILOT_RUN_USE_CALL_SITE,
        "mentions": tuple(token for token in
                          ("policy", "STEP", "policy_digest",
                           "run_step_out_of_process", "run_policy_step")
                          if token in source),
        "accepts_policy_argument": "policy" in
        trajectory.run_use.__code__.co_varnames[
            :trajectory.run_use.__code__.co_argcount],
        "signature": str(inspect.signature(trajectory.run_use)),
    }


@dataclass(frozen=True)
class FreshProcess:
    child_argv: tuple
    receipt_identity: str
    launcher_profile: str
    executed_digest: str
    worker_status: str
    policy_digest: str


def execute_bound_policy(binding: PolicyBinding_, view: dict, state: dict, *,
                         entry: str = "STEP",
                         authority: Mapping[str, Any] | None = None,
                         operation_id: str | None = None) -> dict:
    """The one execution this module makes, under an authority it names.

    This module proves that the bound policy runs in a fresh interpreter and
    that its admitted action governs, so it has to execute rather than read
    the refusal: `fresh_process_evidence` reports a worker status and a
    launcher receipt that only exist once a child has run. The executor
    refuses an execution with no `dsn`, allocation and operation id, so the
    authority is named here rather than inferred, and its absence is a
    refusal rather than a run against whatever store happens to be visible.
    """
    binding.verified()
    record = binding.as_policy_record()
    policy_step.verify_policy_record(record)
    if not isinstance(authority, Mapping) or not authority.get("dsn") \
            or not authority.get("allocation_id") or not operation_id:
        raise PolicyNotProved(
            "this proof executes the bound policy, so it needs a store, an "
            "allocation and an operation identity: it has no refusal to show "
            "and no result without them")
    return method_exec.run_step_out_of_process(
        binding.source, view, state, entry=entry,
        dsn=str(authority["dsn"]),
        allocation_id=str(authority["allocation_id"]),
        operation_id=str(operation_id))


@contextlib.contextmanager
def proof_authority() -> Iterator[dict]:
    """A disposable store and allocation for this proof's executions.

    Created here, for these executions, and dropped when the proof ends, so
    the receipts it reads back are attributable while they run and leave
    nothing behind afterwards. It is separate from any live or study store
    by construction rather than by convention.
    """
    from . import s09_run_isolation as isolation
    from settlement import authority as _authority

    token = "bound-use-proof-%s" % uuid.uuid4().hex[:8]
    admin = isolation.admin_dsn()
    database = isolation.create_disposable_db(token, admin_dsn=admin)
    try:
        handle = _authority.authorize_study(
            database.dsn, isolation.study_root_for(token),
            authorized=1_000_000, allocation_id="%s-alloc" % token,
            ceilings={"sandbox_calls": 10_000})
        yield {"dsn": database.dsn, "allocation_id": handle.allocation_id}
    finally:
        isolation.drop_disposable_db(database, admin_dsn=admin)


def _operation_id(binding: PolicyBinding_, view: dict, suffix: str = "") -> str:
    """One execution's identity, derived from the bytes and the view.

    The step suffix is part of it because a sequence of steps is not one
    execution: under a single identity the second step would read back the
    first step's settled receipt and report the first step's action, which
    would read as "the policy stopped advancing" when nothing ran twice.
    """
    view_key = sha256_of(json.dumps(dict(view), sort_keys=True,
                                     default=str))[:16]
    parts = ["bound-use-proof", binding.recorded_digest[:16], view_key]
    if suffix:
        parts.append(suffix)
    return "-".join(parts)


def fresh_process_evidence(result: Mapping[str, Any]) -> FreshProcess:
    receipt = result["receipt"]
    launcher = receipt["details"]["raw_payload"]["launcher_receipt"]
    return FreshProcess(
        child_argv=tuple(launcher["argv"]),
        receipt_identity=str(receipt["receipt_identity"]),
        launcher_profile=str(launcher["profile"]),
        executed_digest=str(result["source_digest"]),
        worker_status=str(launcher["data"]["worker"]["status"]),
        policy_digest=str(receipt["source_digest"]),
    )


def admitted_actions(binding: PolicyBinding_, view: dict, *,
                     steps: int = 2,
                     authority: Mapping[str, Any] | None = None) -> list:
    state: dict = {}
    admitted = []
    for index in range(steps):
        result = execute_bound_policy(
            binding, view, state, authority=authority,
            operation_id=_operation_id(binding, view, "step%d" % index))
        action = policy_step.validate_step_result(
            {"action": result["action"], "state": result["state"]})
        admitted.append(action["action"])
        state = action["state"]
    return admitted


def use_episode(policy: Any = None, *,
                repertoire: dict | None = None,
                use_tasks: Sequence[str] = (TASK_ID,),
                world: int = 1) -> list:
    """Run the use phase the pilot runs, optionally through a policy.

    `policy` is a decision consumer with the shape
    `agenda_policy.step_policy_consumer` returns. It is consulted once
    per use task, the way the investigation phase consults it, and a
    refusal from it stops the episode before any method runs. When it is
    None the phase behaves exactly as the pilot ships it. The return
    value is the saved use records.
    """
    records = []
    for task_id in use_tasks:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        if policy is not None:
            decision = policy.decide(
                {"observations": [{"task_id": task_id}]},
                {}, boundary={"seq": 0}, experience={})
            if decision.get("status") == "refused":
                records.append({
                    "record_id": "%s-%s" % (CAMPAIGN_ID, task_id),
                    "world": world, "arm": "I", "task_id": task_id,
                    "domain": task["family"],
                    "status": "refused",
                    "selected": "refused", "requested": "refused",
                    "executed": "refused", "executed_source": "refused",
                    "verdict": "refused",
                    "initial_measure": 0, "final_measure": 0,
                    "normalized_reduction": 0.0,
                    "costs": {"witness_queries": 0}, "output": {},
                    "operation_ids": [],
                    "fallback_reason": str(decision.get("reason", "")),
                })
                continue
        records.extend(trajectory.run_use(
            repertoire if repertoire is not None else use_repertoire(),
            world, "I", [task_id], {}))
    return records


def column_report(*, binding: PolicyBinding_ | None = None,
                  use_records: Sequence[Mapping[str, Any]] | None = None,
                  view: dict | None = None,
                  authority: Mapping[str, Any] | None = None) -> dict:
    binding = binding if binding is not None else load_bound_policy()
    view = view if view is not None else use_view()
    use_records = list(use_records if use_records is not None
                       else use_episode(None))

    policy_result = execute_bound_policy(
        binding, view, {}, authority=authority,
        operation_id=_operation_id(binding, view, "report"))
    policy_actions = admitted_actions(binding, view, authority=authority)
    policy_fresh = fresh_process_evidence(policy_result)
    policy_verdict = (
        PROVING if (policy_fresh.executed_digest == binding.recorded_digest
                    and policy_fresh.worker_status == "ok"
                    and _execute_admitted(
                        policy_actions[0], binding)["accepted"]) else
        NOT_PROVING)

    method_digests = sorted({sha256_of(str(record["executed_source"]))
                             for record in use_records})
    method_verdict = (PROVING if binding.recorded_digest in method_digests
                      else NOT_PROVING)

    reach = use_phase_names_policy()
    governing = (PROVING if policy_verdict == PROVING
                 and method_verdict == NOT_PROVING
                 and reach["mentions"] else NOT_PROVING)
    return {
        "governing_column": governing,
        "operational_policy": {
            "role": "the STEP program, its construction response, its bound"
                    " digest, and the actions it admits after a restart",
            "verdict": policy_verdict,
            "recorded_digest": binding.recorded_digest,
            "recomputed_digest": binding.digest,
            "digest_recomputed": True,
            "source_bytes": len(binding.source),
            "admitted_actions": policy_actions,
            "fresh_process": {
                "child_argv0": policy_fresh.child_argv[0],
                "child_argv1": policy_fresh.child_argv[1].rsplit("/", 1)[-1],
                "receipt_identity": policy_fresh.receipt_identity,
                "launcher_profile": policy_fresh.launcher_profile,
                "worker_status": policy_fresh.worker_status,
                "executed_digest": policy_fresh.executed_digest,
                "receipt_policy_digest": policy_fresh.policy_digest,
            },
            "reaches_use_phase": bool(reach["mentions"]),
            "use_phase_signature": reach["signature"],
        },
        "task_method": {
            "role": "the ENTRY repertoire member, its provenance, and the"
                    " bytes that ran in the use phase",
            "verdict": method_verdict,
            "executed_source_digests": method_digests,
            "executed_capability_ids": sorted(
                {str(record["selected"]) for record in use_records}),
            "call_site": PILOT_RUN_USE_CALL_SITE,
            "authored_method_site": PILOT_METHOD_SOURCE_SITE,
        },
        "digest_copy_site": PILOT_DIGEST_COPY_SITE,
    }


def _execute_admitted(action: Mapping[str, Any],
                      binding: PolicyBinding_) -> dict:
    """Send one admitted action through the shipped action dispatcher."""
    from . import assessment_profile
    task = worlds.load_task(worlds.FROZEN_DIR, action["target"])
    ctx = assessment_profile.make_ctx(
        candidate_digest=binding.recorded_digest,
        scope={"family": FAMILY, "task_ids": [TASK_ID]},
        session="s09-bound-use-proof", qualify_depth=0,
        remaining={"queries": 8, "model_calls": 0},
        visible_observation_ids=(), trusted=False)
    return assessment_profile.dispatch(
        profile_name=assessment_profile.DEVELOPMENT,
        record=binding.as_policy_record(), task=task, action=dict(action),
        ctx=ctx)


@dataclass(frozen=True)
class Substitution:
    """The same use episode under two policies, method repertoire fixed."""

    repertoire_digest: str
    method_digests: tuple
    actions: tuple
    outcomes: tuple
    differs: bool

    @property
    def changes_the_episode(self) -> bool:
        return self.differing_action is not None

    @property
    def differing_action(self) -> tuple | None:
        for left, right in zip(self.actions[0], self.actions[1]):
            if left != right:
                return right
        return None


def substitute_policy(baseline: PolicyBinding_,
                      substitute: PolicyBinding_,
                      view: dict | None = None,
                      repertoire: dict | None = None,
                      authority: Mapping[str, Any] | None = None) -> Substitution:
    view = view if view is not None else use_view()
    repertoire = repertoire if repertoire is not None else use_repertoire()
    method_digest = sha256_of(str(repertoire["members"][0]["method_source"]))

    actions, outcomes = [], []
    for binding in (baseline, substitute):
        admitted = admitted_actions(binding, view, authority=authority)
        actions.append(tuple(_action_key(action) for action in admitted))
        outcomes.append(tuple(
            _candidate_digest(_execute_admitted(action, binding))
            for action in admitted))

    return Substitution(
        repertoire_digest=method_digest,
        method_digests=(method_digest, method_digest),
        actions=actions,
        outcomes=outcomes,
        differs=actions[0] != actions[1] or outcomes[0] != outcomes[1])


def _action_key(action: Mapping[str, Any]) -> tuple:
    return (str(action["kind"]), str(action["target"]),
            json.dumps(dict(action["inputs"]), sort_keys=True))


def _candidate_digest(effect: Mapping[str, Any]) -> str:
    if not effect.get("accepted"):
        return "refused: %s" % effect.get("reason", "")
    return sha256_of(json.dumps(effect.get("candidate"), sort_keys=True))


def substitute(baseline_source: str, substitute_source: str,
               authority: Mapping[str, Any] | None = None) -> Substitution:
    """Substitution over two policy sources, repertoire held fixed.

    Neither source is required to be persisted. The substitution question
    is whether swapping the policy changes the episode, which the
    durable-persistence check would only constrain.
    """
    view = use_view()
    baseline = PolicyBinding_(
        source=baseline_source, recorded_digest=sha256_of(baseline_source),
        origin="fixture-stand-in", durable=False)
    substitute_binding = PolicyBinding_(
        source=substitute_source, recorded_digest=sha256_of(substitute_source),
        origin="fixture-stand-in", durable=False)
    return substitute_policy(baseline, substitute_binding, view,
                             authority=authority)


@dataclass(frozen=True)
class Disconnect:
    """The run's outcome when the policy dispatcher was unavailable.

    `fell_back_to_method` is the opposite outcome to `refused`: a method
    result despite that refusal. The run carries no subprocess of its
    own, so it has no exit code to report and this does not invent one.
    """

    decision: dict
    refused: bool
    fell_back_to_method: bool
    executed: str
    records: tuple

    @property
    def refusal_recorded(self) -> bool:
        return self.refused


def disconnect(step_policy: Any, view: dict) -> Disconnect:
    """Refuse loudly, or record the failure that lets us say so."""
    step_policy._disconnected = "policy dispatcher unavailable"
    decision = step_policy.decide(
        {"observations": [{"task_id": TASK_ID}]}, {},
        boundary={"seq": 0}, experience={})
    refused = (decision.get("status") == "refused"
               and "disconnected" in str(decision.get("reason", "")))
    records = use_episode(step_policy)
    return Disconnect(
        decision=dict(decision),
        refused=bool(refused),
        fell_back_to_method=any(
            record.get("selected") not in (None, "", "refused")
            for record in records),
        executed=str(records[0]["executed"]) if records else "",
        records=tuple(records))


def disconnect_probe() -> Disconnect:
    """Disconnect a real STEP consumer and record what the run did."""
    from . import agenda_policy
    binding = load_bound_policy()
    policy = {
        "artifact": binding.as_policy_record()["artifact"],
        "source_digest": binding.recorded_digest,
        "entry": policy_step.STEP_ENTRY,
        "policy_source": binding.source,
    }
    consumer = agenda_policy.step_policy_consumer(
        policy, dsn=None, cid=CAMPAIGN_ID)
    return disconnect(consumer, use_view())


def shipped_path_fallback() -> dict:
    """What the pilot's own use phase does when the policy is gone.

    The shipped `run_use` never consults a policy, so removing one
    cannot change it. This measures that rather than asserting it: the
    episode runs with a disconnected consumer present and with none, and
    the two must be identical for the fallback to be silent.
    """
    from . import agenda_policy
    binding = load_bound_policy()
    policy = {
        "artifact": binding.as_policy_record()["artifact"],
        "source_digest": binding.recorded_digest,
        "entry": policy_step.STEP_ENTRY,
        "policy_source": binding.source,
    }
    consumer = agenda_policy.step_policy_consumer(
        policy, dsn=None, cid=CAMPAIGN_ID)
    consumer._disconnected = "policy dispatcher unavailable"
    with_policy = use_episode(None, repertoire=use_repertoire())
    without_policy = trajectory.run_use(
        use_repertoire(), 1, "I", [TASK_ID], {})
    return {
        "consumer_refused": consumer.decide(
            {"observations": [{"task_id": TASK_ID}]}, {},
            boundary={"seq": 0}, experience={}),
        "shipped_executed": str(without_policy[0]["executed"]),
        "shipped_selected": str(without_policy[0]["selected"]),
        "shipped_reduction": float(
            without_policy[0]["normalized_reduction"]),
        "consults_policy": bool(use_phase_names_policy()["mentions"]),
        "identical_to_policy_run": (
            [r["output"] for r in with_policy]
            == [r["output"] for r in without_policy]),
    }


def vocabulary_columns() -> dict:
    """Which action kinds each column can actually express.

    The two vocabularies are the reason the substitution test needs the
    STEP ABI's kinds: `policy_action` names six kinds and
    `policy_step` names six others, and only `stop` is common. A policy
    that satisfies the shared contract's `use` cannot be dispatched by
    the use path, which is why the STEP fixture below is checked against
    both.
    """
    step = set(STEP_ABI_ACTION_KINDS)
    shared = set(SHARED_ACTION_KINDS)
    return {
        "step_abi": tuple(sorted(step)),
        "shared_contract": tuple(sorted(shared)),
        "shared_between": tuple(sorted(step & shared)),
        "step_only": tuple(sorted(step - shared)),
        "shared_only": tuple(sorted(shared - step)),
    }


def recorded_p1_use_census() -> dict:
    """Recompute the two digest columns from the committed use records."""
    path = EVIDENCE / "use_records.json"
    if not path.exists():
        raise PolicyNotProved("committed use evidence is absent at %s" % path)
    records = json.loads(path.read_text())
    rows = [record for record in records
            if str(record.get("arm")) == "P1"
            and str(record.get("task_id")) in P1_SOFTWARE_USE_TASKS]
    recomputed = []
    for record in rows:
        source = record.get("executed_source")
        recomputed.append({
            "task_id": record["task_id"],
            "recorded_policy_digest": str(record.get("policy_digest", "")),
            "recorded_executed_source_digest": str(
                record.get("executed_source_digest", "")),
            "recomputed_executed_source_digest": (
                sha256_of(source) if isinstance(source, str) else ""),
            "selected": str(record.get("selected", "")),
        })
    agree = all(row["recorded_executed_source_digest"]
                == row["recomputed_executed_source_digest"]
                for row in recomputed)
    columns_agree = all(
        row["recorded_policy_digest"] == row["recomputed_executed_source_digest"]
        for row in recomputed)
    return {
        "rows": recomputed,
        "recomputation_agrees": agree,
        "policy_column_equals_method_column": columns_agree,
        "use_records_site": PILOT_DIGEST_COPY_SITE,
    }


__all__ = [
    "BASELINE_METHOD",
    "Disconnect",
    "EVIDENCE",
    "FreshProcess",
    "NOT_PROVING",
    "P1_SOFTWARE_USE_TASKS",
    "PROVING",
    "PolicyBinding_",
    "PolicyNotProved",
    "SUBSTITUTE_METHOD",
    "Substitution",
    "TASK_ID",
    "admitted_actions",
    "column_report",
    "disconnect",
    "disconnect_probe",
    "execute_bound_policy",
    "fresh_process_evidence",
    "load_bound_policy",
    "make_record",
    "proof_authority",
    "recorded_p1_use_census",
    "seed_policy_source",
    "sha256_of",
    "shipped_path_fallback",
    "substitute",
    "substitute_policy",
    "use_episode",
    "use_phase_names_policy",
    "use_repertoire",
    "use_view",
    "vocabulary_columns",
]
