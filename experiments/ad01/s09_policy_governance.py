"""Operational governance of a bound STEP policy, or its absence.

Finding S09R-02 (`reviews/STAGE-09-GENERALITY-LIVE-REVIEW.md`) holds that a
bound `STEP` digest was copied onto use records whose executed bytes were an
authored `ENTRY` constant. This module keeps the two artifact columns apart
and attacks the question with a substitution and a disconnect.

    operational policy  the STEP program, its construction response, its
                        release, the actions a fresh interpreter admitted
                        from its bytes
    task method         the ENTRY repertoire member, its provenance, the
                        child invocation that ran it

Substitution holds the repertoire fixed and swaps the policy. Disconnect
withholds the policy and watches the repertoire. Both run in a fresh
interpreter, because a reused one can carry a warm module or a copied field
into the answer.

The two action vocabularies in this codebase do not meet. `policy_action`
admits `probe, observe, construct, use, check, stop`; the operational
dispatcher admits `diagnose, construct_method, use_method, request_model,
propose_revision, stop`. Only `stop` is common, so a policy conforming to one
is refused by the other unless it stops. Any future claim that a policy and a
shared-contract representation are interchangeable has to survive that.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import assessment_profile
from . import method_exec
from . import policy_action
from . import policy_step
from . import seeds
from . import worlds

ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = ROOT / "evidence_s09_m3_live"
PILOT = ROOT / "scripts" / "s09_pilot.py"

OPERATIONAL_POLICY = "operational-policy"
TASK_METHOD = "task-method"

EPISODE_CPU_SECONDS = 30
EPISODE_TIMEOUT_MS = 60_000
EPISODE_MAX_OUTPUT_BYTES = 1_048_576

REFUSAL_NO_DISPATCHER = "no-policy-dispatcher"
REFUSAL_NO_STEP = "policy-step-refused"
REFUSAL_EFFECT_REFUSED = "admitted-action-refused"


class GovernanceRefused(Exception):
    """A bound policy refused at a boundary."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__("%s: %s" % (stage, reason))
        self.stage = stage
        self.reason = reason


def _digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


@dataclass(frozen=True)
class BoundPolicy:
    """Operational-policy column: bytes, the digest they hash to, and the
    release disposition the construction response claims for them."""

    arm: str
    source: str
    digest: str
    recorded_digest: str
    entry: str
    origin: str
    source_path: str
    disposition: str
    release_id: str

    @property
    def column(self) -> str:
        return OPERATIONAL_POLICY

    @property
    def released(self) -> bool:
        return bool(self.release_id) and self.disposition == "released"

    def as_dict(self) -> dict:
        return {"column": self.column, "arm": self.arm, "digest": self.digest,
                "recorded_digest": self.recorded_digest,
                "entry": self.entry, "origin": self.origin,
                "source_path": self.source_path,
                "disposition": self.disposition,
                "release_id": self.release_id, "released": self.released,
                "digest_matches_record": self.digest == self.recorded_digest}


def bind(source: str, *, arm: str, recorded_digest: str, entry: str,
         origin: str, source_path: str, disposition: str,
         release_id: str = "") -> BoundPolicy:
    """Bind durable bytes against the digest claimed for them.

    The digest is recomputed from the bytes in hand. A recorded digest the
    bytes do not reproduce is a refusal, never a warning.
    """
    if not isinstance(source, str) or not source.strip():
        raise GovernanceRefused(REFUSAL_NO_STEP, "policy source bytes are empty")
    method_exec.verify_step_source(source, entry)
    actual = _digest(source)
    if actual != recorded_digest:
        raise GovernanceRefused(
            REFUSAL_NO_STEP,
            "policy bytes hash to %s, record claims %s" % (actual, recorded_digest))
    if origin not in policy_step.POLICY_ORIGINS:
        raise GovernanceRefused(REFUSAL_NO_STEP,
                                "unknown policy origin %r" % (origin,))
    return BoundPolicy(arm=arm, source=source, digest=actual,
                       recorded_digest=recorded_digest, entry=entry,
                       origin=origin, source_path=source_path,
                       disposition=disposition, release_id=release_id)


def load_bundle_policy(arm: str, *, bundle: Path = BUNDLE_DIR) -> BoundPolicy:
    """Load one arm's bound policy out of a persisted construction response.

    A missing `origin` is read as authored rather than refused, because a
    construction response predating the field is authored by construction. An
    origin that is present but unrecognized still refuses, in `bind`.
    """
    path = Path(bundle) / "construction.json"
    if not path.is_file():
        raise GovernanceRefused(REFUSAL_NO_STEP,
                                "no construction response at %s" % path)
    entry = json.loads(path.read_text(encoding="utf-8")).get(arm)
    if not isinstance(entry, dict):
        raise GovernanceRefused(REFUSAL_NO_STEP,
                                "construction response has no arm %r" % arm)
    recorded = entry.get("bound_digest") or (
        entry.get("policy_artifact") or {}).get("source_digest")
    return bind(entry["policy_source"], arm=arm, recorded_digest=recorded,
                entry=policy_step.STEP_ENTRY,
                origin=(entry.get("policy_artifact") or {}).get(
                    "origin", "authored-control"),
                source_path="%s:%s.policy_source" % (path, arm),
                disposition=str(entry.get("disposition", "unknown")),
                release_id=str(entry.get("release_id") or ""))


@dataclass(frozen=True)
class MethodColumn:
    """Task-method column: which repertoire member ran, and the digest of the
    outcome it produced.

    `outcome_digest` and `policy_digest` hash different things, so they are not
    comparable and this column never claims the policy ran. The comparable
    pair lives in `bundle_method_governs`, where both sides are program bytes.
    """

    identity: str
    owner: str
    outcome: dict
    outcome_digest: str
    policy_digest: str
    queries: int

    @property
    def column(self) -> str:
        return TASK_METHOD

    def as_dict(self) -> dict:
        return {"column": self.column, "identity": self.identity,
                "owner": self.owner, "outcome": self.outcome,
                "outcome_digest": self.outcome_digest,
                "policy_digest": self.policy_digest, "queries": self.queries}


@dataclass(frozen=True)
class Decision:
    seq: int
    action: dict
    state: dict
    executed_digest: str
    wall_ms: int
    launcher: str
    argv: list

    def as_dict(self) -> dict:
        return {"seq": self.seq, "action": self.action, "state": self.state,
                "executed_digest": self.executed_digest,
                "wall_ms": self.wall_ms, "launcher": self.launcher,
                "argv": self.argv}


@dataclass(frozen=True)
class Episode:
    arm: str
    policy_digest: str
    view_digest: str
    admitted: tuple
    methods: tuple
    episode_pid: int
    driver_pid: int

    @property
    def admitted_sequence(self) -> tuple:
        return tuple(_canonical(decision.action) for decision in self.admitted)

    @property
    def fresh_process(self) -> bool:
        return self.episode_pid != self.driver_pid

    def as_dict(self) -> dict:
        return {"arm": self.arm, "policy_digest": self.policy_digest,
                "view_digest": self.view_digest,
                "admitted_sequence": list(self.admitted_sequence),
                "admitted": [d.as_dict() for d in self.admitted],
                "methods": [m.as_dict() for m in self.methods],
                "episode_pid": self.episode_pid,
                "driver_pid": self.driver_pid,
                "fresh_process": self.fresh_process}


def method_source_digest(source: str) -> str:
    """Public because the child process re-hashes its own staged bytes."""
    return _digest(source)


def pilot_method_source() -> str:
    """The authored `ENTRY` the live pilot ran during the use phase."""
    from scripts import s09_pilot
    return s09_pilot.METHOD_SOURCE


def _view_for(task_id: str, *, remaining: dict) -> dict:
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    return policy_step.materialize_view(
        task=task, observations=[], open_questions=[], last_result=None,
        eligible_methods=[item["capability_id"] for item
                          in seeds.SEED_CAPABILITIES
                          if item["family"] == task["family"]],
        remaining=dict(remaining))


def _context(policy: BoundPolicy, task_id: str, step_index: int,
             remaining: dict) -> dict:
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    return assessment_profile.make_ctx(
        candidate_digest=policy.digest,
        scope={"family": task["family"], "task_ids": [task_id]},
        session="s09-governance/%s" % policy.arm, step_index=step_index,
        remaining=dict(remaining))


def _step(policy: BoundPolicy, view: dict, state: dict, seq: int) -> Decision:
    record = policy_step.make_policy_artifact(
        policy.source, origin=policy.origin)
    stepped = policy_step.run_policy_step(record, view, state)
    launcher_receipt = stepped["receipt"]["details"]["raw_payload"][
        "launcher_receipt"]
    return Decision(
        seq=seq, action=dict(stepped["action"]), state=dict(stepped["state"]),
        executed_digest=stepped["source_digest"],
        wall_ms=int(launcher_receipt["data"].get("wall_ms") or 0),
        launcher=str(launcher_receipt.get("profile", "")),
        argv=[str(item) for item in launcher_receipt.get("argv", [])])


def _episode_body(policy: BoundPolicy, task_id: str, *, remaining: dict,
                  dispatcher: Callable | None,
                  max_steps: int, driver_pid: int) -> Episode:
    if dispatcher is None:
        raise GovernanceRefused(REFUSAL_NO_DISPATCHER,
                                "use was attempted with no policy dispatcher")
    view = _view_for(task_id, remaining=remaining)
    view_digest = _digest(_canonical(view))
    state: dict = {}
    decisions: list[Decision] = []
    methods: list[MethodColumn] = []
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    for step_index in range(max_steps):
        try:
            decision = _step(policy, view, state, len(decisions))
        except Exception as exc:
            raise GovernanceRefused(REFUSAL_NO_STEP, str(exc)) from exc
        if decision.executed_digest != policy.digest:
            raise GovernanceRefused(
                REFUSAL_NO_STEP,
                "child executed %s, policy bound %s"
                % (decision.executed_digest, policy.digest))
        decisions.append(decision)
        state = decision.state
        effect = dispatcher(policy, task, decision.action,
                            _context(policy, task_id, step_index, remaining))
        if not isinstance(effect, dict) or not effect.get("accepted"):
            raise GovernanceRefused(
                REFUSAL_EFFECT_REFUSED,
                "admitted %s action was refused: %s"
                % (decision.action["kind"], (effect or {}).get("reason", "")))
        methods.append(MethodColumn(
            identity=str(effect.get("selected_identity")),
            owner=str(effect.get("owner")),
            outcome=effect.get("candidate") or {},
            outcome_digest=_digest(_canonical(effect.get("candidate") or {})),
            policy_digest=policy.digest, queries=int(effect.get("queries", 0))))
        if effect.get("candidate") is not None or decision.action["kind"] == "stop":
            break
    return Episode(arm=policy.arm, policy_digest=policy.digest,
                   view_digest=view_digest, admitted=tuple(decisions),
                   methods=tuple(methods),
                   episode_pid=os.getpid(), driver_pid=driver_pid)


def _default_dispatcher(policy: BoundPolicy, task: dict, action: dict,
                        context: dict) -> dict:
    return assessment_profile.dispatch(
        profile_name=assessment_profile.ASSESSMENT,
        record=policy_step.make_policy_artifact(policy.source,
                                               origin=policy.origin),
        task=task, action=action, ctx=context)


_EPISODE_CHILD = '''
import json, os, sys
work, root, policy_path, arm, task_id, remaining, max_steps, driver_pid, mode = sys.argv[1:]
sys.path.insert(0, root)
sys.path.insert(0, root + "/src")
from experiments.ad01 import s09_policy_governance as gov
from experiments.ad01 import policy_step
from pathlib import Path

def emit(status, data, error=""):
    # WorkerOutput sets extra="forbid", so a structured refusal stage cannot be
    # its own envelope field; it rides inside `error` and is re-split by the
    # driver on ": ".
    print(json.dumps({"status": status, "data": data, "error": error}))

staged = Path(policy_path).read_bytes()
recorded = Path(policy_path).with_suffix(".digest").read_text().strip()
if gov.method_source_digest(staged.decode("utf-8")) != recorded:
    emit("error", {}, "policy-digest-mismatch: staged policy bytes do not"
                       " match the bound digest")
else:
    policy = gov.bind(staged.decode("utf-8"), arm=arm, recorded_digest=recorded,
                      entry=policy_step.STEP_ENTRY, origin="authored-control",
                      source_path=policy_path, disposition="staged")
    dispatcher = None if mode == "disconnected" else gov._default_dispatcher
    try:
        episode = gov._episode_body(
            policy, task_id, remaining=json.loads(remaining),
            dispatcher=dispatcher, max_steps=int(max_steps),
            driver_pid=int(driver_pid))
        emit("ok", episode.as_dict())
    except gov.GovernanceRefused as exc:
        emit("error", {}, exc.stage + ": " + exc.reason)
'''


def run_episode(policy: BoundPolicy, task_id: str, *, remaining: dict | None = None,
                dispatcher: Callable | None = _default_dispatcher,
                max_steps: int = policy_step.POLICY_MAX_STEPS) -> Episode:
    """Run one bound policy over one task inside a fresh interpreter.

    The bytes are staged to disk, read back, and re-hashed by the child before
    it executes anything, so a digest cannot travel with the request instead of
    the source. A refusal inside the child is raised here as a typed
    `GovernanceRefused`; it is never downgraded to a fallback.
    """
    from settlement import broker
    from settlement.launcher_local import PROFILE, LocalLauncher

    budget = dict(remaining or {"queries": 16, "model_calls": 2})
    mode = "disconnected" if dispatcher is None else "connected"
    with tempfile.TemporaryDirectory(prefix="s09-governance-") as raw:
        work = Path(raw)
        staged = work / "policy.py"
        staged.write_bytes(policy.source.encode("utf-8"))
        (work / "policy.digest").write_text(policy.digest, encoding="utf-8")
        child = work / "episode.py"
        child.write_text(_EPISODE_CHILD, encoding="utf-8")
        launcher = LocalLauncher(work / "launcher")
        payload = {
            "profile": PROFILE,
            "argv": [sys.executable, str(child), str(work), str(ROOT),
                     str(staged), policy.arm, task_id, _canonical(budget),
                     str(max_steps), str(os.getpid()), mode],
            "timeout_ms": EPISODE_TIMEOUT_MS,
            "max_output_bytes": EPISODE_MAX_OUTPUT_BYTES,
            "cpu_seconds": EPISODE_CPU_SECONDS,
        }
        # one id per invocation: the launcher refuses a second send under a
        # recorded id and would hand back the first run's receipt
        operation_id = "s09-governance-%s" % os.urandom(6).hex()
        launched = launcher.dispatch(broker.BrokerOp(
            operation_id=operation_id, effect=broker.SANDBOX_EXEC,
            payload=payload))
        if not launched.sent:
            raise GovernanceRefused(
                REFUSAL_NO_STEP,
                "episode was not launched: %s" % launched.refused_reason)
        receipt = launcher.read_result(operation_id)
    worker = (receipt.get("data") or {}).get("worker") or {}
    if worker.get("status") != "ok":
        stage, _, reason = str(worker.get("error", "")).partition(": ")
        if not stage:
            raise GovernanceRefused(
                REFUSAL_NO_STEP, _receipt_detail(receipt))
        raise GovernanceRefused(stage, reason or str(worker["error"]))
    data = worker["data"]
    return Episode(
        arm=data["arm"], policy_digest=data["policy_digest"],
        view_digest=data["view_digest"],
        admitted=tuple(Decision(
            seq=item["seq"], action=item["action"], state=item["state"],
            executed_digest=item["executed_digest"], wall_ms=item["wall_ms"],
            launcher=item["launcher"], argv=item["argv"])
            for item in data["admitted"]),
        methods=tuple(MethodColumn(
            identity=item["identity"], owner=item["owner"],
            outcome=item["outcome"],
            outcome_digest=item["outcome_digest"],
            policy_digest=item["policy_digest"], queries=item["queries"])
            for item in data["methods"]),
        episode_pid=data["episode_pid"], driver_pid=data["driver_pid"])


def _receipt_detail(receipt: dict) -> str:
    worker = (receipt.get("data") or {}).get("worker") or {}
    if worker.get("error"):
        return str(worker["error"])
    return "child exited %s: %s" % (
        (receipt.get("data") or {}).get("returncode"),
        ((receipt.get("data") or {}).get("stderr") or "")[-300:])


def substitution_verdict(first: BoundPolicy, second: BoundPolicy,
                         task_id: str, *, remaining: dict | None = None) -> dict:
    """Swap the policy with the method repertoire held fixed."""
    left = run_episode(first, task_id, remaining=remaining)
    right = run_episode(second, task_id, remaining=remaining)
    identities = ([m.identity for m in left.methods],
                  [m.identity for m in right.methods])
    owners = ([m.owner for m in left.methods], [m.owner for m in right.methods])
    return {
        "task_id": task_id,
        "repertoire_held_fixed": list(assessment_profile.default_repertoire()),
        "policies": {"first": first.as_dict(), "second": second.as_dict()},
        "admitted_sequences": {"first": list(left.admitted_sequence),
                               "second": list(right.admitted_sequence)},
        "executed_identities": {"first": identities[0], "second": identities[1]},
        "executed_owners": {"first": owners[0], "second": owners[1]},
        "view_digests": {"first": left.view_digest, "second": right.view_digest},
        "views_identical": left.view_digest == right.view_digest,
        "admitted_sequence_differs":
            left.admitted_sequence != right.admitted_sequence,
        "executed_identity_differs": identities[0] != identities[1],
        "policy_governs": (left.admitted_sequence != right.admitted_sequence
                           and identities[0] != identities[1]),
    }


def disconnect_verdict(policy: BoundPolicy, task_id: str, *,
                       remaining: dict | None = None) -> dict:
    """Cut the policy's reach to the method repertoire and demand a refusal.

    Two disconnects are measured. The first withholds this module's policy
    dispatcher from the episode. The second withholds the method identity from
    an admitted `use_method` action and hands it to the pipeline's own
    dispatcher, `assessment_profile.dispatch`, which is the code the live study
    used.
    """
    without_dispatcher = _refusal_of(
        lambda: run_episode(policy, task_id, remaining=remaining,
                            dispatcher=None))
    record = policy_step.make_policy_artifact(policy.source,
                                              origin=policy.origin)
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    unnamed = {"kind": "use_method", "target": task_id, "inputs": {},
               "evidence_refs": [], "requested_resources": {"queries": 16}}
    policy_step.validate_action(unnamed)
    effect = assessment_profile.dispatch(
        profile_name=assessment_profile.ASSESSMENT, record=record, task=task,
        action=unnamed,
        ctx=assessment_profile.make_ctx(
            candidate_digest=policy.digest,
            scope={"family": task["family"], "task_ids": [task_id]},
            session="s09-governance/%s" % policy.arm,
            remaining=dict(remaining or {"queries": 16, "model_calls": 2})))
    return {
        "task_id": task_id,
        "no_dispatcher": without_dispatcher,
        "unnamed_method_action": {
            "kind": unnamed["kind"], "inputs": unnamed["inputs"]},
        "unnamed_method_effect": {
            "accepted": effect["accepted"], "reason": effect["reason"],
            "owner": effect["owner"],
            "selected_identity": effect["selected_identity"],
            "queries": effect["queries"]},
        "refused_without_dispatcher": without_dispatcher is not None,
        "refused_on_unnamed_method": effect["accepted"] is False,
        "reached_repertoire_without_policy": bool(effect["selected_identity"]),
    }


def _refusal_of(thunk: Callable) -> dict | None:
    try:
        thunk()
    except GovernanceRefused as exc:
        return {"stage": exc.stage, "reason": exc.reason}
    return None


def bundle_method_governs(arm: str, *, bundle: Path = BUNDLE_DIR) -> dict:
    """Ask which column governed the committed bundle's use phase.

    No digest below is copied from a record. Each is re-hashed from bytes: the
    construction response, the pilot's authored `ENTRY`, and each use record's
    own `executed_source`.
    """
    policy = load_bundle_policy(arm, bundle=bundle)
    authored = pilot_method_source()
    authored_digest = _digest(authored)
    records = json.loads(
        (Path(bundle) / "use_records.json").read_text(encoding="utf-8"))
    matching = [record for record in records
                if record.get("arm") == arm
                and record.get("executed_source") == authored]
    recomputed = [_digest(record["executed_source"])
                  for record in matching
                  if isinstance(record.get("executed_source"), str)]
    return {
        "arm": arm,
        "bundle": str(Path(bundle)),
        "policy_digest": policy.digest,
        "policy_digest_matches_bound_record": policy.as_dict()[
            "digest_matches_record"],
        "policy_released": policy.released,
        "authored_method_digest": authored_digest,
        "authored_method_source_path": str(PILOT),
        "use_records_executing_authored_method": len(matching),
        "record_digests_match_recomputed": all(
            value == record["executed_source_digest"]
            for value, record in zip(recomputed, matching)),
        "policy_digest_equals_executed_digest":
            policy.digest == authored_digest,
        "governing_column": (OPERATIONAL_POLICY
                             if policy.digest == authored_digest
                             else TASK_METHOD),
    }


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    arm = argv[0] if argv else "P1"
    task_id = argv[1] if len(argv) > 1 else "ad01-w1-within-sw-00"
    report = {
        "module": "s09_policy_governance",
        "contract_versions": {
            "policy_step": policy_step.POLICY_STEP_VERSION,
            "policy_action": policy_action.CONTRACT_VERSION,
            "child": method_exec.CHILD_CONTRACT_VERSION},
        "action_vocabularies": {
            "policy_action": list(policy_action.ACTION_KINDS),
            "policy_step": list(policy_step.ACTION_KINDS),
            "shared": sorted(set(policy_action.ACTION_KINDS)
                             & set(policy_step.ACTION_KINDS))},
        "bundle": bundle_method_governs(arm),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
