"""Equality-of-treatment checks for Stage 9 policy arms.

The harness owns one representation registry, one world-to-contract schema
map, and one canonical view serializer. A failed check is data in a parity
result rather than an exception from an arm.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from . import boolean_active
from . import boolean_ast_policy
from . import boolean_graph_policy
from . import boolean_policy
from . import policy_action
from . import policy_step


PYTHON_STEP = "python-step"
TYPED_AST = "typed-ast"
ACTION_GRAPH = "action-graph"
REPRESENTATION_KINDS = (PYTHON_STEP, TYPED_AST, ACTION_GRAPH)
REAL_REPRESENTATION_KINDS = frozenset({PYTHON_STEP, TYPED_AST, ACTION_GRAPH})
WORLD_ACTION_RENAMES = {boolean_active.COMMIT: policy_action.CONSTRUCT}

# The worlds the harness can drive, by name. `_run_arm` used to call
# `boolean_active.run_episode` directly, so a comparison could not be
# pointed at any other instrument and "does this representation work on a
# second world" was unaskable rather than answered. An unrecognised name
# raises: a silent fallback to the Boolean world would hand a study a clean
# comparison against the first instrument and read it as evidence about
# the second.
# `swe` used to be described here as "registered for addressability, not
# because the harness can normalise its view", on the grounds that
# `contract_view` demands exactly eight public-state fields and the SWE world
# publishes twelve of its own. That was true when it was written and it is
# false now, so it is removed rather than softened. The contract publishes six
# fields, and each world declares its OWN public-state field set against
# `VIEW_CONTRACT_FIELDS` below: the Boolean and ordering worlds declare eight,
# the SWE world twelve. The count is deliberately not the contract, so 8
# against 12 is a per-world declaration rather than a refusal.
#
# Measured end to end on real views, which is what replaced the claim:
#
#   boolean_rule session -> `public_state`          -> 8 fields
#                        -> `admit_world_view`       -> None (admitted)
#                        -> `contract_view`          -> the six contract fields
#                        -> `admit_shared_view`      -> None
#   swe_tasks instance   -> `SweSession.policy_view` -> 12 fields
#                        -> `admit_world_view`       -> None (admitted)
#                        -> `contract_view`          -> the same six fields
#                        -> `admit_shared_view`      -> None
#
# The test the old comment cited,
# `test_a_swe_arm_is_refused_by_the_harness_view_normaliser`, no longer exists
# on this tree. `tests/test_view_contract_swe.py` pins the admission, and
# `tests/test_inv_c7_two_domain.py` pins that both structures normalise to one
# contract at the field count read from the contract itself.
#
# Registering the world is still load-bearing, for a different reason and it
# is a driver reason rather than a view reason: an arm emitting a
# `boolean.task` stop target is refused by the SWE world. B18 measured
# `compare_arms` still `incomparable` with `graph issues: []`, so the view is
# no longer the blocker and the two driver factories are.
_WORLDS = {
    "boolean": "boolean_active",
    "ordering": "second_active",
    "swe": "s09_swe_world",
}


def episode_runner(world: str):
    """The `run_episode` for a named world, or a refusal.

    Both worlds expose the same `(choose, split=, seed=)` shape and return
    the same trace and final score, which is what lets one harness compare
    arms across them.
    """
    if not isinstance(world, str) or world not in _WORLDS:
        raise ValueError("unknown world: %r" % (world,))
    import importlib
    return getattr(importlib.import_module(
        "experiments.ad01." + _WORLDS[world]), "run_episode")


class IncomparabilityReason(StrEnum):
    UNDECLARED_REPRESENTATION_KIND = "undeclared-representation-kind"
    UNKNOWN_REPRESENTATION_KIND = "unknown-representation-kind"
    INVALID_DRIVER_FACTORY = "invalid-driver-factory"
    INVALID_POLICY_RECORD = "invalid-policy-record"
    DUPLICATE_ARM_NAME = "duplicate-arm-name"
    UNREGISTERED_ARM = "unregistered-arm"
    DUPLICATE_REPRESENTATION_KIND = "duplicate-representation-kind"
    INSUFFICIENT_ARMS = "insufficient-arms"
    INVALID_CONDITIONS = "invalid-conditions"
    DRIVER_FACTORY_FAILED = "driver-factory-failed"
    EPISODE_FAILED = "episode-failed"
    VIEW_MUTATED = "view-mutated"
    NON_CONTRACT_ACTION_KIND = "non-contract-action-kind"
    SCHEMA_RENAME_COLLISION = "schema-rename-collision"
    BUDGET_MISMATCH = "budget-mismatch"
    PRIVATE_ACTION_KIND = "private-action-kind"
    INVALID_SHARED_ACTION = "invalid-shared-action"
    ACTION_KIND_NOT_ADVERTISED = "action-kind-not-advertised"
    WORLD_ACTION_REFUSED = "world-action-refused"
    VIEW_DIGEST_MISMATCH = "view-digest-mismatch"
    INITIAL_STATE_MISMATCH = "initial-state-mismatch"
    CONDITION_MISMATCH = "condition-mismatch"
    SCORE_QUERY_MISMATCH = "score-query-mismatch"


@dataclass(frozen=True)
class Incomparability:
    reason: IncomparabilityReason
    arm_names: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "reason": str(self.reason),
            "arm_names": list(self.arm_names),
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class StepBudget:
    timeout_ms: int = policy_step.STEP_TIMEOUT_MS
    cpu_seconds: int = policy_step.STEP_CPU_SECONDS
    max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES
    memory_bytes: int | None = None

    def as_driver_kwargs(self) -> dict:
        return {
            "timeout_ms": self.timeout_ms,
            "cpu_seconds": self.cpu_seconds,
            "max_output_bytes": self.max_output_bytes,
            "memory_bytes": self.memory_bytes,
        }

    def as_dict(self) -> dict:
        return self.as_driver_kwargs()


@dataclass(frozen=True)
class ComparisonConditions:
    split: str
    seed: int
    max_queries: int
    step_budget: StepBudget = field(default_factory=StepBudget)
    world: str = "boolean"


@dataclass(frozen=True)
class ArmRegistration:
    name: str
    representation_kind: str
    driver_factory: Any
    policy_record: dict
    is_test_double: bool = False

    @property
    def policy_record_digest(self) -> str:
        return hashlib.sha256(
            canonical_json_bytes(self.policy_record)).hexdigest()


@dataclass(frozen=True)
class ArmRecord:
    arm_name: str
    representation_kind: str
    policy_record_digest: str
    task_id: str
    split: str
    seed: int
    query_budget: int
    queries_spent: int
    turns_taken: int
    step_budget: StepBudget
    initial_state_digest: str
    view_digest: str
    score: dict | None
    is_test_double: bool

    def as_dict(self) -> dict:
        return {
            "arm_name": self.arm_name,
            "representation_kind": self.representation_kind,
            "policy_record_digest": self.policy_record_digest,
            "task_id": self.task_id,
            "split": self.split,
            "seed": self.seed,
            "query_budget": self.query_budget,
            "queries_spent": self.queries_spent,
            "turns_taken": self.turns_taken,
            "step_budget": self.step_budget.as_dict(),
            "initial_state_digest": self.initial_state_digest,
            "view_digest": self.view_digest,
            "score": deepcopy(self.score),
            "is_test_double": self.is_test_double,
        }


@dataclass(frozen=True)
class ParityResult:
    status: str
    conditions: ComparisonConditions
    records: tuple[ArmRecord, ...] = ()
    incompatibilities: tuple[Incomparability, ...] = ()

    @property
    def comparable(self) -> bool:
        return self.status == "comparable"

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "conditions": {
                "split": self.conditions.split,
                "seed": self.conditions.seed,
                "max_queries": self.conditions.max_queries,
                "step_budget": self.conditions.step_budget.as_dict(),
            },
            "records": [record.as_dict() for record in self.records],
            "incompatibilities": [
                issue.as_dict() for issue in self.incompatibilities
            ],
        }


class SchemaRefused(Exception):
    def __init__(self, issue: Incomparability):
        super().__init__(str(issue.reason))
        self.issue = issue


class _ArmRunFailed(Exception):
    def __init__(self, issue: Incomparability):
        super().__init__(str(issue.reason))
        self.issue = issue


class ArmRegistry:
    def __init__(self) -> None:
        self._arms: dict[str, ArmRegistration] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._arms)

    def real_arm_names(self) -> tuple[str, ...]:
        """The arms backed by a real executor, not a registered double.

        The kind alone is not enough. A test double is registered under a
        real kind so it can exercise the same admission path, and before
        this checked the flag a double would have counted as real the moment
        its kind joined the set. It only did not show while the set held one
        kind, because the parity tests registered their doubles under kinds
        that were not real yet.
        """
        return tuple(
            name for name, arm in self._arms.items()
            if arm.representation_kind in REAL_REPRESENTATION_KINDS
            and not arm.is_test_double
        )

    def register(self, *, name: str, representation_kind: Any,
                 driver_factory: Any, policy_record: Any,
                 is_test_double: bool = False
                 ) -> ArmRegistration | Incomparability:
        if not isinstance(name, str) or not name:
            return Incomparability(
                IncomparabilityReason.INVALID_DRIVER_FACTORY,
                details={"field": "name", "value": repr(name)})
        if representation_kind is None:
            return Incomparability(
                IncomparabilityReason.UNDECLARED_REPRESENTATION_KIND,
                (name,), {"arm_name": name})
        if representation_kind not in REPRESENTATION_KINDS:
            return Incomparability(
                IncomparabilityReason.UNKNOWN_REPRESENTATION_KIND,
                (name,), {"representation_kind": repr(representation_kind)})
        if not callable(driver_factory):
            return Incomparability(
                IncomparabilityReason.INVALID_DRIVER_FACTORY,
                (name,), {"arm_name": name})
        if not isinstance(policy_record, dict):
            return Incomparability(
                IncomparabilityReason.INVALID_POLICY_RECORD,
                (name,), {"arm_name": name})
        if name in self._arms:
            return Incomparability(
                IncomparabilityReason.DUPLICATE_ARM_NAME,
                (name,), {"arm_name": name})
        arm = ArmRegistration(
            name=name,
            representation_kind=representation_kind,
            driver_factory=driver_factory,
            policy_record=deepcopy(policy_record),
            is_test_double=is_test_double,
        )
        self._arms[name] = arm
        return arm


def serialize_view(view: dict) -> bytes:
    return canonical_json_bytes(view)


def view_digest(view: dict) -> str:
    return hashlib.sha256(serialize_view(view)).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _json_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


# The policy view contract, declared once here and read by every world.
#
# The guard's job is to refuse a view an arm must not hold, and the field
# *count* was never what it was refusing. It compared for equality against
# one eight-field set, so the SWE world's twelve were refused for carrying
# more information rather than for carrying something protected, which
# defeats the guard's own purpose: an arm handed an eight-field view has no
# program, and one with no program passes by being unable to attempt the
# task.
#
# So each world declares its own public state, and the check stays exact
# rather than becoming a subset test. Exactness is what keeps a union of
# two vocabularies a refusal instead of a widened view, and it is the
# property `test_a_view_is_admitted_only_for_the_world_that_declared_it`
# pins.
#
# A world is matched by two things its own view publishes, and both have
# to agree: the instrument id and the action-schema `format`. Either alone
# is a string a caller can set, and a view that named a declared format
# under an undeclared instrument would be admitted by the format and
# would then be projected with the wrong world's read paths. A view is
# refused when the two disagree, rather than one being preferred.
VIEW_CONTRACT_FIELDS = {
    "boolean-rule-v1": frozenset({
        "instrument", "task_id", "split", "max_queries", "remaining",
        "observed", "hypothesis_class", "action_schema"}),
    "ordering-constraints-v1": frozenset({
        "instrument", "task_id", "split", "max_queries", "remaining",
        "observed", "hypothesis_class", "action_schema"}),
    "software-fault-repair-v1": frozenset({
        "action_schema", "entry", "instrument", "last_effect", "max_budget",
        "public_tests", "remaining", "source", "split", "structure",
        "symptom", "task_id"}),
}

VIEW_CONTRACT_FORMATS = {
    "boolean-rule-v1": "s09-boolean-action-v1",
    "ordering-constraints-v1": "s09-ordering-action-v1",
    "software-fault-repair-v1": "s09-swe-action-v1",
}

# The contract's six fields are not what every world publishes. This says,
# per world, where each contract field lives when the world nests it rather
# than publishing it flat, and for the one field whose value describes two
# published fields instead of being one of them.
#
# `max_queries` and `remaining` read the `test` budget, not the sum of the
# five. The contract requires `0 <= remaining <= max_queries` and the
# schema to agree, and a world with a per-dimension budget has exactly one
# dimension an observation spends: `observe` and `check` both spend it, and
# `PUBLIC_CASES` public tests is the ceiling a task can reach. So the pair
# is read together and is consistent by construction.
#
# Two projections of this view already existed and each answered these
# questions differently. `s09_swe_ast.swe_view` reported the probe budget
# and `{"structure": ...}`; `s09_e1_fork_probe.honest_projection` reported
# the sum of all five budgets and a list of fault-mechanism names, which is
# the injected answer and the leak the contamination tests forbid. Both are
# deleted. This is the one answer.
VIEW_CONTRACT_READS = {
    "software-fault-repair-v1": {
        "observed": ("symptom", "observed"),
        "max_queries": ("action_schema", "budget", "test"),
        "remaining": ("remaining", "test"),
    },
}


def _hypothesis_class(public_state: dict) -> dict:
    """The SWE world's hypothesis class, from two fields it publishes.

    A description rather than a fiction: `structure` is the program's shape
    and `editable_lines` is how many lines `apply_edits` will accept an
    edit to. Both are in the policy view already. It deliberately names no
    mechanism, because the mechanism is the injected fault and publishing
    it would hand every arm the answer.
    """
    return {"structure": public_state["structure"],
            "editable_lines": len(public_state["source"])}


VIEW_CONTRACT_DERIVED = {
    "software-fault-repair-v1": {"hypothesis_class": _hypothesis_class},
}


def _world_key(public_state: dict) -> str | None:
    """The world that published this view, by its own two declarations
    agreeing, or `None` when they do not."""
    if not isinstance(public_state, dict):
        return None
    key = public_state.get("instrument")
    if key not in VIEW_CONTRACT_FIELDS:
        return None
    schema = public_state.get("action_schema")
    if not isinstance(schema, dict) \
            or schema.get("format") != VIEW_CONTRACT_FORMATS[key]:
        return None
    return key


def _read(public_state: dict, path: tuple):
    value = public_state
    for key in path:
        value = value[key]
    return value


def _contract_field(public_state: dict, key: str, name: str):
    """One contract field, read from where this world actually put it.

    A declared read path wins over a flat key of the same name, because a
    world that publishes `remaining` as a per-dimension mapping still owes
    the contract the one integer that dimension is. The reads are
    lookups, so a world that moved a field is refused rather than served a
    substitute invented here. A world with no declaration for a field
    publishes it flat and it passes through.
    """
    reads = VIEW_CONTRACT_READS.get(key, {})
    if name in reads:
        return _read(public_state, reads[name])
    derived = VIEW_CONTRACT_DERIVED.get(key, {}).get(name)
    if derived is not None:
        return derived(public_state)
    return public_state.get(name)


def admit_world_view(public_state: Any, *, arm_name: str = ""
                     ) -> Incomparability | None:
    if not isinstance(public_state, dict):
        return Incomparability(
            IncomparabilityReason.NON_CONTRACT_ACTION_KIND,
            (arm_name,) if arm_name else (),
            {"field": "public_state", "value": repr(public_state)})
    key = _world_key(public_state)
    declared = VIEW_CONTRACT_FIELDS.get(key)
    if declared is None:
        return Incomparability(
            IncomparabilityReason.NON_CONTRACT_ACTION_KIND,
            (arm_name,) if arm_name else (),
            {"public_state_fields": "unrecognised world"})
    if set(public_state) != declared or "tables" in public_state:
        return Incomparability(
            IncomparabilityReason.NON_CONTRACT_ACTION_KIND,
            (arm_name,) if arm_name else (),
            {"public_state_fields": sorted(public_state)})
    schema = public_state["action_schema"]
    max_queries = _contract_field(public_state, key, "max_queries")
    if type(max_queries) is not int or max_queries <= 0:
        return Incomparability(
            IncomparabilityReason.BUDGET_MISMATCH,
            (arm_name,) if arm_name else (),
            {"max_queries": repr(max_queries)})
    if not isinstance(schema, dict) or not isinstance(schema.get("actions"), dict):
        return Incomparability(
            IncomparabilityReason.NON_CONTRACT_ACTION_KIND,
            (arm_name,) if arm_name else (),
            {"field": "action_schema"})
    schema_budget = schema.get("budget")
    if not isinstance(schema_budget, dict) \
            or schema_budget.get("max_queries", schema_budget.get("test")) \
            != max_queries:
        return Incomparability(
            IncomparabilityReason.BUDGET_MISMATCH,
            (arm_name,) if arm_name else (),
            {
                "view_max_queries": max_queries,
                "schema_max_queries": (
                    schema_budget.get("max_queries",
                                      schema_budget.get("test"))
                    if isinstance(schema_budget, dict) else None),
            })
    actions = schema["actions"]
    renames_by_target: dict[str, list[str]] = {}
    for advertised, contract_kind in WORLD_ACTION_RENAMES.items():
        renames_by_target.setdefault(contract_kind, []).append(advertised)
    for contract_kind, advertised_names in renames_by_target.items():
        collisions = set(advertised_names) & set(actions)
        if contract_kind in actions:
            collisions.add(contract_kind)
        if len(collisions) > 1:
            return Incomparability(
                IncomparabilityReason.SCHEMA_RENAME_COLLISION,
                (arm_name,) if arm_name else (),
                {
                    "contract_kind": contract_kind,
                    "world_kinds": sorted(collisions),
                })
    unknown = (set(actions) - set(policy_action.ACTION_KINDS)
               - set(WORLD_ACTION_RENAMES))
    if unknown:
        kind = sorted(unknown)[0]
        return Incomparability(
            IncomparabilityReason.NON_CONTRACT_ACTION_KIND,
            (arm_name,) if arm_name else (),
            {
                "action_kind": kind,
                "documented_renames": dict(WORLD_ACTION_RENAMES),
            })
    return None


def contract_view(public_state: dict, *, arm_name: str = "") -> dict:
    issue = admit_world_view(public_state, arm_name=arm_name)
    if issue is not None:
        raise SchemaRefused(issue)
    schema = deepcopy(public_state["action_schema"])
    schema["actions"] = {
        WORLD_ACTION_RENAMES.get(kind, kind): spec
        for kind, spec in schema["actions"].items()
    }
    # The contract cross-checks `public_world.max_queries` against
    # `schema.budget.max_queries`, so a world that publishes a
    # per-dimension budget has the contract's scalar published under the
    # key the check reads. The world's own per-dimension budgets stay, and
    # nothing else about the schema changes.
    key = _world_key(public_state)
    budget = schema.get("budget")
    if isinstance(budget, dict) and "max_queries" not in budget:
        budget["max_queries"] = budget["test"]
    return {
        "instrument": public_state["instrument"],
        "task_id": public_state["task_id"],
        "observed": deepcopy(_contract_field(public_state, key, "observed")),
        "remaining": _contract_field(public_state, key, "remaining"),
        "public_world": {
            "split": public_state["split"],
            "max_queries": _contract_field(public_state, key, "max_queries"),
            "hypothesis_class": deepcopy(
                _contract_field(public_state, key, "hypothesis_class")),
        },
        "action_schema": schema,
    }


def admit_shared_view(view: Any, *, arm_name: str = ""
                      ) -> Incomparability | None:
    expected_fields = set(policy_action.view_contract()["fields"])
    if not isinstance(view, dict) or set(view) != expected_fields:
        return Incomparability(
            IncomparabilityReason.NON_CONTRACT_ACTION_KIND,
            (arm_name,) if arm_name else (),
            {"view_fields": sorted(view) if isinstance(view, dict) else repr(view)})
    public_world = view["public_world"]
    schema = view["action_schema"]
    if not isinstance(public_world, dict) \
            or set(public_world) != {"split", "max_queries", "hypothesis_class"}:
        return Incomparability(
            IncomparabilityReason.NON_CONTRACT_ACTION_KIND,
            (arm_name,) if arm_name else (),
            {"public_world": repr(public_world)})
    if not isinstance(schema, dict) or not isinstance(schema.get("actions"), dict):
        return Incomparability(
            IncomparabilityReason.NON_CONTRACT_ACTION_KIND,
            (arm_name,) if arm_name else (),
            {"action_schema": repr(schema)})
    unknown = set(schema["actions"]) - set(policy_action.ACTION_KINDS)
    if unknown:
        return Incomparability(
            IncomparabilityReason.NON_CONTRACT_ACTION_KIND,
            (arm_name,) if arm_name else (),
            {"action_kind": sorted(unknown)[0]})
    max_queries = public_world["max_queries"]
    schema_budget = schema.get("budget")
    if type(max_queries) is not int or not isinstance(schema_budget, dict) \
            or schema_budget.get("max_queries") != max_queries:
        return Incomparability(
            IncomparabilityReason.BUDGET_MISMATCH,
            (arm_name,) if arm_name else (),
            {
                "view_max_queries": max_queries,
                "schema_max_queries": (
                    schema_budget.get("max_queries")
                    if isinstance(schema_budget, dict) else None),
            })
    remaining = view["remaining"]
    if type(remaining) is not int or not 0 <= remaining <= max_queries:
        return Incomparability(
            IncomparabilityReason.BUDGET_MISMATCH,
            (arm_name,) if arm_name else (),
            {"remaining": repr(remaining), "max_queries": max_queries})
    return None


def admit_action(view: dict, action: Any, *, arm_name: str = ""
                 ) -> Incomparability | None:
    view_issue = admit_shared_view(view, arm_name=arm_name)
    if view_issue is not None:
        details = dict(view_issue.details)
        details["arm_name"] = arm_name
        details["emitted_kind"] = (
            action.get("kind") if isinstance(action, dict) else None)
        return Incomparability(view_issue.reason, view_issue.arm_names,
                               details)
    kind = action.get("kind") if isinstance(action, dict) else None
    if kind not in policy_action.ACTION_KINDS:
        return Incomparability(
            IncomparabilityReason.PRIVATE_ACTION_KIND,
            (arm_name,) if arm_name else (),
            {"action_kind": repr(kind)})
    try:
        policy_action.parse_action(action)
    except policy_action.ActionRefused as exc:
        return Incomparability(
            IncomparabilityReason.INVALID_SHARED_ACTION,
            (arm_name,) if arm_name else (),
            {"reason": str(exc)})
    if kind not in view["action_schema"]["actions"]:
        return Incomparability(
            IncomparabilityReason.ACTION_KIND_NOT_ADVERTISED,
            (arm_name,) if arm_name else (),
            {"action_kind": kind})
    return None


def _python_step_factory(record: dict, *,
                         timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
                         cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
                         max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
                         memory_bytes: int | None = None,
                         world: str = "boolean"):
    """The shared STEP executor behind the common contract.

    `boolean_policy.choose_action` is used rather than its internals
    called directly, because it converts a failure inside the step into a
    recorded refusal action instead of an exception. That is observable:
    `test_registration_does_not_validate_the_record_it_is_given` asserts a
    malformed record still yields a `comparable` arm with a trace, and an
    earlier refactor that inlined the step made it `episode-failed`. The
    contract a policy must satisfy is not the harness's to restate.

    `world` is accepted and only `boolean` is served here. The ordering
    world's action rules need a `ScheduleSession` rather than a view, and
    that world drives its own arms; refusing beats half-supporting a second
    source of truth for its rules.
    """
    if world != "boolean":
        raise ValueError(
            "the ordering world's action rules need a session, so a STEP "
            "arm there is driven by the world, not by this adapter")
    legacy_decide = boolean_policy.choose_action(
        record, timeout_ms=timeout_ms, cpu_seconds=cpu_seconds,
        max_output_bytes=max_output_bytes, memory_bytes=memory_bytes,
    )

    def decide(view: dict) -> dict:
        return legacy_decide(_world_state_from_contract_view(view))
    return decide


def _world_state_from_contract_view(view: dict, world: str = "boolean") -> dict:
    """A contract view back into the world state the executors want.

    The rename is the world's, not the harness's. It was `construct` to the
    Boolean world's `commit`, applied unconditionally, so an ordering arm
    received a schema advertising `commit` where its own executor wanted
    `construct`. Only the Boolean world renames; the ordering executors
    take the shared contract as published.
    """
    schema = deepcopy(view["action_schema"])
    actions = schema["actions"]
    if policy_action.CONSTRUCT not in actions:
        raise ValueError("%s schema does not advertise construct" % world)
    if world == "boolean":
        actions[boolean_active.COMMIT] = actions.pop(policy_action.CONSTRUCT)
    return {
        "instrument": view["instrument"],
        "task_id": view["task_id"],
        "split": view["public_world"]["split"],
        "max_queries": view["public_world"]["max_queries"],
        "remaining": view["remaining"],
        "observed": deepcopy(view["observed"]),
        "hypothesis_class": deepcopy(view["public_world"]["hypothesis_class"]),
        "action_schema": schema,
    }


def register_python_step(registry: ArmRegistry, *, name: str,
                         policy_record: dict) -> ArmRegistration | Incomparability:
    return registry.register(
        name=name,
        representation_kind=PYTHON_STEP,
        driver_factory=_python_step_factory,
        policy_record=policy_record,
    )


def _typed_ast_factory(record: dict, *,
                       timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
                       cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
                       max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
                       memory_bytes: int | None = None):
    """The typed AST executor behind the common contract.

    Its own `choose_action` already honours every budget argument, so unlike
    the graph this adapter does more than accept and ignore them.
    """
    ast_decide = boolean_ast_policy.choose_action(
        record, timeout_ms=timeout_ms, cpu_seconds=cpu_seconds,
        max_output_bytes=max_output_bytes, memory_bytes=memory_bytes)

    def decide(view: dict) -> dict:
        return ast_decide(_world_state_from_contract_view(view))
    return decide


def register_typed_ast(registry: ArmRegistry, *, name: str,
                       policy_record: dict) -> ArmRegistration | Incomparability:
    return registry.register(
        name=name,
        representation_kind=TYPED_AST,
        driver_factory=_typed_ast_factory,
        policy_record=policy_record,
    )


def _action_graph_factory(record: dict, *,
                          timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
                          cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
                          max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
                          memory_bytes: int | None = None,
                          world: str = "boolean"):
    """The action-graph executor behind the common contract.

    The graph's load-time limits — 64 nodes, 16 arms per node, a 4096-byte
    state cap, a nine-field guard vocabulary — bound the *shape* of a graph,
    not the time it takes to evaluate one, so the four budget arguments used
    to be accepted and discarded here. An arm that could hang was reported
    as `comparable` beside two that could not, which made the parity result
    a comparison between representations under different compute limits.

    The step now runs in a child under the same `LocalLauncher` bounds the
    STEP and AST paths use. The cost is a process per turn, which is why
    this is the only change and the load-time limits are left alone.
    """
    from . import s09_graph_budget
    del timeout_ms, cpu_seconds, max_output_bytes, memory_bytes
    # The cursor is held here, not in the child, because each turn is a
    # separate process. `boolean_graph_policy.choose_action` owns a cursor
    # in its closure; an in-process arm kept it for the episode, and an arm
    # that did not would restart at its start node every turn.
    cursor: dict = {}

    def decide(delivered: dict) -> dict:
        # The contract view carries split, max_queries and hypothesis_class
        # under `public_world`; the world executors read them at the top
        # level. So the ordering graph is handed the world state and the
        # Boolean graph the renamed one, because the rename is the Boolean
        # world's own and the ordering executors take the contract as
        # published.
        state = (_world_state_from_contract_view(delivered, world)
                 if world == "boolean" else _ordering_state_from_view(
                     delivered))
        return s09_graph_budget.run_graph_step(
            record, state, cursor, world=world,
            timeout_ms=policy_step.STEP_TIMEOUT_MS,
            cpu_seconds=policy_step.STEP_CPU_SECONDS,
            max_output_bytes=policy_step.STEP_MAX_OUTPUT_BYTES)
    return decide


def _ordering_state_from_view(view: dict) -> dict:
    """A contract view into a world state, with the Boolean rename undone.

    The same projection as the Boolean one, minus the `construct` to `commit`
    rename: the ordering executors take the shared contract as published and
    re-deriving their own state from it is the world's business.
    """
    return {
        "instrument": view["instrument"],
        "task_id": view["task_id"],
        "split": view["public_world"]["split"],
        "max_queries": view["public_world"]["max_queries"],
        "remaining": view["remaining"],
        "observed": deepcopy(view["observed"]),
        "hypothesis_class": deepcopy(view["public_world"]["hypothesis_class"]),
        "action_schema": deepcopy(view["action_schema"]),
    }


def register_action_graph(registry: ArmRegistry, *, name: str,
                          policy_record: dict, world: str = "boolean"
                          ) -> ArmRegistration | Incomparability:
    return registry.register(
        name=name,
        representation_kind=ACTION_GRAPH,
        driver_factory=lambda record, **kw: _action_graph_factory(
            record, world=world, **kw),
        policy_record=policy_record,
    )


def _validate_conditions(conditions: Any) -> Incomparability | None:
    if not isinstance(conditions, ComparisonConditions) \
            or not isinstance(conditions.split, str) \
            or type(conditions.seed) is not int \
            or type(conditions.max_queries) is not int \
            or conditions.max_queries <= 0 \
            or not isinstance(conditions.step_budget, StepBudget):
        return Incomparability(
            IncomparabilityReason.INVALID_CONDITIONS,
            details={"conditions": repr(conditions)})
    budget = conditions.step_budget
    numeric = (budget.timeout_ms, budget.cpu_seconds,
               budget.max_output_bytes)
    if any(type(value) is not int or value <= 0 for value in numeric) \
            or (budget.memory_bytes is not None
                and (type(budget.memory_bytes) is not int
                     or budget.memory_bytes <= 0)):
        return Incomparability(
            IncomparabilityReason.INVALID_CONDITIONS,
            details={"step_budget": repr(budget)})
    return None


def _run_arm(arm: ArmRegistration, conditions: ComparisonConditions
             ) -> tuple[ArmRecord, tuple[Incomparability, ...]]:
    initial_state: dict | None = None
    initial_view: dict | None = None
    views: list[dict] = []
    issues: list[Incomparability] = []

    try:
        decide = arm.driver_factory(
            deepcopy(arm.policy_record), **conditions.step_budget.as_driver_kwargs())
    except Exception as exc:
        raise _ArmRunFailed(Incomparability(
            IncomparabilityReason.DRIVER_FACTORY_FAILED,
            (arm.name,), {"error": f"{type(exc).__name__}: {exc}"})) from exc

    def choose(public_state: dict) -> dict:
        nonlocal initial_state, initial_view
        try:
            view = contract_view(public_state, arm_name=arm.name)
            delivered = deepcopy(view)
            digest = view_digest(delivered)
            views.append(deepcopy(delivered))
            if initial_state is None:
                initial_state = deepcopy(public_state)
                initial_view = deepcopy(delivered)
            action = decide(delivered)
            if view_digest(delivered) != digest:
                issues.append(Incomparability(
                    IncomparabilityReason.VIEW_MUTATED, (arm.name,),
                    {"view_digest": digest}))
            action_issue = admit_action(
                view, action, arm_name=arm.name)
            if action_issue is not None:
                issues.append(action_issue)
            return deepcopy(action)
        except SchemaRefused as exc:
            raise _ArmRunFailed(exc.issue) from exc
        except _ArmRunFailed:
            raise
        except Exception as exc:
            raise _ArmRunFailed(Incomparability(
                IncomparabilityReason.EPISODE_FAILED, (arm.name,),
                {"stage": "decide", "error": f"{type(exc).__name__}: {exc}"})) from exc

    try:
        world_result = episode_runner(conditions.world)(
            choose, split=conditions.split, seed=conditions.seed)
    except _ArmRunFailed as exc:
        raise _ArmRunFailed(exc.issue) from exc
    except Exception as exc:
        raise _ArmRunFailed(Incomparability(
            IncomparabilityReason.EPISODE_FAILED, (arm.name,),
            {"error": f"{type(exc).__name__}: {exc}"})) from exc

    for turn_index, turn in enumerate(world_result["trace"]):
        turn_action_issue = None
        if turn_index < len(views):
            # The per-turn world check re-derives a world state from the
            # contract view, which only means anything for a world that
            # publishes the eight flat fields: `_world_state_from_contract_
            # view` un-nests `public_world` into them. A declared world
            # publishes its own shape, so its contract view is the
            # artefact and `admit_shared_view` is the check. Running the
            # un-nesting one anyway reported every SWE turn as a
            # non-contract action kind against a view it had itself just
            # produced.
            if conditions.world in ("boolean", "ordering"):
                world_issue = admit_world_view(
                    _world_state_from_contract_view(views[turn_index]),
                    arm_name=arm.name)
                if world_issue is not None:
                    issues.append(world_issue)
            turn_action_issue = admit_action(
                views[turn_index], turn["action"], arm_name=arm.name)
            if turn_action_issue is not None and turn_action_issue not in issues:
                issues.append(turn_action_issue)
        if "refused" in turn and turn_action_issue is None:
            issues.append(Incomparability(
                IncomparabilityReason.WORLD_ACTION_REFUSED, (arm.name,),
                {"turn": turn_index, "reason": turn["refused"]}))

    if initial_state is None or initial_view is None:
        raise _ArmRunFailed(Incomparability(
            IncomparabilityReason.EPISODE_FAILED, (arm.name,),
            {"reason": "arm received no initial view"}))
    # The budget cross-check reads the contract view rather than the raw
    # world state, because the two are not the same shape: a world that
    # publishes a per-dimension budget has no flat `max_queries` to read,
    # and the contract view is the single projection every arm was
    # handed, so it is the one place the two arms can be compared.
    view_max_queries = initial_view["public_world"]["max_queries"]
    if world_result["split"] != conditions.split \
            or world_result["seed"] != conditions.seed \
            or view_max_queries != conditions.max_queries:
        issues.append(Incomparability(
            IncomparabilityReason.CONDITION_MISMATCH, (arm.name,),
            {
                "requested_split": conditions.split,
                "result_split": world_result["split"],
                "requested_seed": conditions.seed,
                "result_seed": world_result["seed"],
                "requested_max_queries": conditions.max_queries,
                "view_max_queries": view_max_queries,
            }))
    # The Boolean world reports `queried` and the ordering world reports
    # `comparisons`; both count the arm's diagnostic spends. Reading the
    # Boolean key unconditionally is what made a second world raise rather
    # than run, so the key is resolved per world and an unrecognised shape
    # is a refusal instead of a zero.
    spent_keys = [k for k in ("queried", "comparisons") if k in world_result]
    if not spent_keys:
        raise _ArmRunFailed(Incomparability(
            IncomparabilityReason.EPISODE_FAILED, (arm.name,),
            {"reason": "world result carries no spend record",
             "keys": sorted(world_result)}))
    queries_spent = len(world_result[spent_keys[0]])
    score = world_result["final"]
    # The Boolean world's score reports `n_queried`; the ordering world's
    # does not. Comparing against `None` reported a mismatch for a world
    # that simply does not publish the field, which is a disagreement
    # about the two score shapes rather than about the arms. So the check
    # is against the field when the world publishes one.
    if isinstance(score, dict) and "n_queried" in score \
            and score.get("n_queried") != queries_spent:
        issues.append(Incomparability(
            IncomparabilityReason.SCORE_QUERY_MISMATCH, (arm.name,),
            {"score_n_queried": score.get("n_queried"),
             "queries_spent": queries_spent}))
    record = ArmRecord(
        arm_name=arm.name,
        representation_kind=arm.representation_kind,
        policy_record_digest=arm.policy_record_digest,
        task_id=world_result["task_id"],
        split=world_result["split"],
        seed=world_result["seed"],
        query_budget=view_max_queries,
        queries_spent=queries_spent,
        turns_taken=len(world_result["trace"]),
        step_budget=conditions.step_budget,
        initial_state_digest=_json_digest(initial_state),
        view_digest=view_digest(initial_view),
        score=deepcopy(score),
        is_test_double=arm.is_test_double,
    )
    return record, tuple(issues)


def compare_arms(registry: ArmRegistry, arm_names: tuple[str, ...],
                 conditions: ComparisonConditions) -> ParityResult:
    condition_issue = _validate_conditions(conditions)
    if condition_issue is not None:
        return ParityResult("incomparable", conditions,
                            incompatibilities=(condition_issue,))
    if not isinstance(arm_names, tuple) or len(arm_names) < 2:
        return ParityResult(
            "incomparable", conditions,
            incompatibilities=(Incomparability(
                IncomparabilityReason.INSUFFICIENT_ARMS, arm_names,
                {"arm_count": len(arm_names)}),))
    if len(set(arm_names)) != len(arm_names):
        return ParityResult(
            "incomparable", conditions,
            incompatibilities=(Incomparability(
                IncomparabilityReason.DUPLICATE_ARM_NAME, arm_names),))
    unknown = tuple(name for name in arm_names if name not in registry._arms)
    if unknown:
        return ParityResult(
            "incomparable", conditions,
            incompatibilities=(Incomparability(
                IncomparabilityReason.UNREGISTERED_ARM, unknown),))
    arms = tuple(registry._arms[name] for name in arm_names)
    kinds = [arm.representation_kind for arm in arms]
    if len(set(kinds)) != len(kinds):
        return ParityResult(
            "incomparable", conditions,
            incompatibilities=(Incomparability(
                IncomparabilityReason.DUPLICATE_REPRESENTATION_KIND,
                arm_names, {"representation_kinds": kinds}),))

    records: list[ArmRecord] = []
    issues: list[Incomparability] = []
    for arm in arms:
        try:
            record, arm_issues = _run_arm(arm, conditions)
        except _ArmRunFailed as exc:
            issues.append(exc.issue)
            continue
        records.append(record)
        issues.extend(arm_issues)

    if len(records) == len(arms):
        view_digests = {record.view_digest for record in records}
        if len(view_digests) != 1:
            issues.append(Incomparability(
                IncomparabilityReason.VIEW_DIGEST_MISMATCH, arm_names,
                {record.arm_name: record.view_digest for record in records}))
        state_digests = {record.initial_state_digest for record in records}
        if len(state_digests) != 1:
            issues.append(Incomparability(
                IncomparabilityReason.INITIAL_STATE_MISMATCH, arm_names,
                {record.arm_name: record.initial_state_digest
                 for record in records}))
        condition_values = {
            canonical_json_bytes({
                "split": record.split,
                "seed": record.seed,
                "query_budget": record.query_budget,
                "step_budget": record.step_budget.as_dict(),
            })
            for record in records
        }
        if len(condition_values) != 1:
            issues.append(Incomparability(
                IncomparabilityReason.CONDITION_MISMATCH, arm_names,
                {record.arm_name: {
                    "split": record.split,
                    "seed": record.seed,
                    "query_budget": record.query_budget,
                    "step_budget": record.step_budget.as_dict(),
                } for record in records}))

    has_real_arm = any(not arm.is_test_double for arm in arms)
    if has_real_arm:
        status = "incomparable" if issues else "comparable"
    else:
        status = "incomparable"
        issues.append(Incomparability(
            IncomparabilityReason.INSUFFICIENT_ARMS, arm_names,
            {"reason": "comparison has no real representation arm"}))
    return ParityResult(status, conditions, tuple(records), tuple(issues))
