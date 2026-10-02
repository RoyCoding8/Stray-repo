"""Frozen protocol for the S09 live study, as data the study must match.

The previous live round failed in three ways that no assertion caught. A
doubles dry run and the live run shared one database, and the operation
ids were mode-independent, so the live run found already-settled double
receipts and its freeze recorded `model: "recorded-double"`. The use
phase then executed an authored method and copied the bound policy's
digest onto the record, so the study never tested what it claimed. The
verifier passed that bundle.

Each failure is a field here, not a paragraph. The run id is derived from
the frozen content and folded into every campaign and operation id, so
ids stay stable across a resume and the protocol can enumerate the exact
dispatchable set. Stable ids are also why the disposable database is a
precondition: the id cannot tell a doubles row from a live one, so
nothing may be reused. The persisted model string is compared to the
frozen model, and a construction receipt that is a reuse fails the
acquisition claim rather than counting toward it.

The power position is the uncomfortable part. Clusters are
`(family, template)` because the generator reuses each pair across cells
and worlds. A two-sided sign sweep over n clusters has minimum p
`2^(1-n)`, so alpha 0.05 needs 6. The frozen panel supplies 4 software
clusters, whose best possible p is 0.125, and 6 graph clusters. This
study therefore CANNOT support a significance claim, and that is not a
caveat attached to the results: the verdict carries a `DescriptiveOnly`
claim, a type with no significant inhabitant, so no code path can issue
one. Spending a large dispatch budget to reach a descriptive-only result
is a cost the protocol states rather than hides.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from fractions import Fraction
from typing import Any, Callable, Iterable, Mapping, Sequence

from experiments.ad01 import s09_panel_inventory as panel_inventory
from experiments.ad01 import worlds

PROTOCOL_VERSION = "s09-study-protocol/1"

STUDY_ID = "s09-live-study"
STUDY_ROOT_PREFIX = "reports/evidence/s09-live-study-r1"
PROTOCOL_ID = "s09-live-study-r1-v1"

ADAPTER = "HttpGatewayAdapter"
API = "responses"
REASONING_EFFORT = "low"

ALPHA = Fraction(1, 20)
WORLDS = (1, 2)
DOMAINS = ("software", "graph")
SPLITS = ("dev", "within", "transfer")
CLAIM_SPLITS = ("within", "transfer")

ARM_P0 = "P0"
ARM_P1 = "P1"
ARM_P2 = "P2"
ARMS = (ARM_P0, ARM_P1, ARM_P2)
DISPATCHING_ARMS = (ARM_P1, ARM_P2)

# Construction gets a repair attempt; use-phase evaluation does not. A
# retry there would be a second draw at the measured outcome, which is
# the test being re-rolled rather than run.
ATTEMPTS_BY_SPLIT = {"dev": 2, "within": 1, "transfer": 1}

BENEFIT_MARGIN = Fraction(1, 10)

REQUESTED_MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
RESOLVED_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
PROVIDER = "nvidia"
TIER = "free"
ENDPOINT = "http://localhost:4000/v1"

ACQUIRED = "model-acquired"
DOUBLED = "recorded-double"


class ProtocolRefused(ValueError):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__("%s: %s" % (reason, detail) if detail else reason)
        self.reason = reason
        self.detail = detail


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Disposition:
    """The outcome of checking something against the frozen protocol."""

    matched: bool
    reasons: tuple[str, ...] = ()
    details: tuple[str, ...] = ()

    @property
    def reason(self) -> str:
        return self.reasons[0] if self.reasons else ""

    def __bool__(self) -> bool:
        return self.matched


@dataclass(frozen=True)
class Arm:
    """One study arm. `control` and `benchmark` are what a verdict needs."""

    name: str
    role: str
    control: bool = False
    benchmark: bool = False
    dispatches: bool = False

    def __post_init__(self) -> None:
        if self.control and self.benchmark:
            raise ProtocolRefused("arm-is-both-control-and-benchmark",
                                  self.name)


ARMS_BY_NAME: tuple[Arm, ...] = (
    Arm(name=ARM_P0, role="authored-control", control=True),
    Arm(name=ARM_P1, role="acquisition", dispatches=True),
    Arm(name=ARM_P2, role="improvement", dispatches=True, benchmark=True),
)


@dataclass(frozen=True)
class Episode:
    """One ordered study step. `dispatches` is what it can spend."""

    order: int
    world: int
    domain: str
    split: str
    task_id: str
    arms: tuple[str, ...]
    attempts: int
    dispatch_arms: tuple[str, ...]
    namespace_token: str = ""

    def __post_init__(self) -> None:
        if self.world not in WORLDS:
            raise ProtocolRefused("episode-world-not-in-protocol",
                                  repr(self.world))
        if self.domain not in DOMAINS:
            raise ProtocolRefused("episode-domain-not-in-protocol",
                                  repr(self.domain))
        if self.split not in SPLITS:
            raise ProtocolRefused("episode-split-not-in-protocol",
                                  repr(self.split))
        if self.arms != ARMS:
            raise ProtocolRefused("episode-arms-not-in-protocol",
                                  repr(self.arms))
        if self.attempts != ATTEMPTS_BY_SPLIT[self.split]:
            raise ProtocolRefused("episode-attempts-not-in-protocol",
                                  "%s=%d" % (self.task_id, self.attempts))
        if self.dispatch_arms != DISPATCHING_ARMS:
            raise ProtocolRefused("episode-dispatch-arms-not-in-protocol",
                                  repr(self.dispatch_arms))
        if self.task_id != "ad01-w%d-%s-%s-%02d" % (
                self.world, self.split,
                "sw" if self.domain == "software" else "gr",
                int(self.task_id.rsplit("-", 1)[1])):
            raise ProtocolRefused("episode-task-id-malformed", self.task_id)

    @property
    def claims(self) -> bool:
        return self.split in CLAIM_SPLITS

    @property
    def dispatches(self) -> int:
        return len(self.dispatch_arms) * self.attempts

    def campaign_id(self) -> str:
        return "ad01-%s-w%d-%s-%s" % (
            self.namespace_token, self.world, self.split, self.task_id)

    def operation_id(self, arm: str, attempt: int) -> str:
        if arm not in DISPATCHING_ARMS:
            raise ProtocolRefused("arm-does-not-dispatch", arm)
        if attempt not in range(1, self.attempts + 1):
            raise ProtocolRefused("attempt-out-of-range", repr(attempt))
        return "s09proto-%s-%s-%s-a%d" % (self.namespace_token, arm,
                                          self.task_id, int(attempt))


@dataclass(frozen=True)
class Cell:
    """One arm by world by domain, with the task ids it runs."""

    arm: str
    world: int
    domain: str
    task_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.arm not in ARMS:
            raise ProtocolRefused("cell-arm-not-in-protocol", repr(self.arm))
        if self.world not in WORLDS:
            raise ProtocolRefused("cell-world-not-in-protocol",
                                  repr(self.world))
        if self.domain not in DOMAINS:
            raise ProtocolRefused("cell-domain-not-in-protocol",
                                  repr(self.domain))
        if not self.task_ids:
            raise ProtocolRefused("cell-has-no-tasks",
                                  "%s w%d %s" % (self.arm, self.world,
                                                  self.domain))

    @property
    def count(self) -> int:
        return len(self.task_ids)

@dataclass(frozen=True)
class NamespaceToken:
    """The run-bound token every campaign and operation id must carry.

    It is derived from the run id rather than minted, so a token for
    another round is a real token for the wrong namespace and is refused
    on comparison instead of being indistinguishable from a fresh one.
    """

    token: str
    run_id: str

    def __post_init__(self) -> None:
        if not self.token or not self.run_id:
            raise ProtocolRefused("namespace-token-empty",
                                  "token=%r run_id=%r" % (self.token,
                                                          self.run_id))
        if self.token != run_token(self.run_id):
            raise ProtocolRefused("namespace-token-not-derived-from-run-id",
                                  self.token)

    def qualifies(self, value: str) -> bool:
        return self.token in value


def run_token(run_id: str) -> str:
    return hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class Route:
    endpoint: str
    requested_model: str
    resolved_model: str
    provider: str
    tier: str
    endpoint_digest: str

    def __post_init__(self) -> None:
        if self.endpoint_digest != digest(self.endpoint):
            raise ProtocolRefused("endpoint-digest-mismatch", self.endpoint)
        for field_name, expected in (("requested_model", REQUESTED_MODEL),
                                     ("resolved_model", RESOLVED_MODEL),
                                     ("provider", PROVIDER),
                                     ("tier", TIER),
                                     ("endpoint", ENDPOINT)):
            actual = getattr(self, field_name)
            if actual != expected:
                raise ProtocolRefused("route-%s-not-the-confirmed-free-route"
                                      % field_name, repr(actual))

    def as_dict(self) -> dict:
        return {"endpoint": self.endpoint,
                "requested_model": self.requested_model,
                "resolved_model": self.resolved_model,
                "provider": self.provider,
                "tier": self.tier,
                "endpoint_digest": self.endpoint_digest}


FROZEN_ROUTE = Route(endpoint=ENDPOINT, requested_model=REQUESTED_MODEL,
                     resolved_model=RESOLVED_MODEL, provider=PROVIDER,
                     tier=TIER, endpoint_digest=digest(ENDPOINT))


@dataclass(frozen=True)
class PanelCell:
    task_id: str
    family: str
    template: str
    world: int
    split: str


def _panel_cells(root: Any = None) -> tuple[PanelCell, ...]:
    """Read the frozen panel's own cell identities.

    The task ids and their families are read from the freeze rather than
    restated, so a regenerated panel changes the protocol instead of
    silently contradicting it.
    """
    import pathlib
    base = pathlib.Path(root) if root is not None else worlds.FROZEN_DIR
    cells = []
    for path in sorted(base.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        task = json.loads(path.read_text())
        parts = path.relative_to(base).parts
        cells.append(PanelCell(
            task_id=task["task_id"], family=task["family"],
            template=task["template"], world=int(parts[0].split("-")[-1]),
            split=parts[1]))
    return tuple(cells)


@dataclass(frozen=True)
class DomainPower:
    domain: str
    cluster_count: int
    minimum_p: Fraction | None
    required_clusters: int
    cluster_templates: tuple[str, ...]

    @property
    def powered(self) -> bool:
        return self.cluster_count >= self.required_clusters

    @property
    def shortfall(self) -> int:
        return max(0, self.required_clusters - self.cluster_count)

    def as_dict(self) -> dict:
        return {"domain": self.domain,
                "cluster_count": self.cluster_count,
                "minimum_p": (None if self.minimum_p is None
                              else str(self.minimum_p)),
                "required_clusters": self.required_clusters,
                "powered": self.powered,
                "shortfall": self.shortfall,
                "cluster_templates": list(self.cluster_templates)}


def minimum_sign_flip_p(cluster_count: int) -> Fraction | None:
    """Smallest two-sided sign-sweep p-value over `cluster_count` clusters."""
    if cluster_count < 0:
        raise ProtocolRefused("negative-cluster-count", repr(cluster_count))
    if cluster_count == 0:
        return None
    return Fraction(1, 2 ** (cluster_count - 1))


def minimum_clusters_for_alpha(alpha: Fraction) -> int:
    """Smallest n whose minimum p-value is at or under `alpha`."""
    if not 0 < alpha < 1:
        raise ProtocolRefused("alpha-out-of-range", str(alpha))
    count = 1
    while True:
        smallest = minimum_sign_flip_p(count)
        if smallest is not None and smallest <= alpha:
            return count
        count += 1


@dataclass(frozen=True)
class Power:
    """The independent units the study has, and what they can support."""

    alpha: Fraction
    cluster_rule: str
    minimum_p_rule: str
    all_domains: tuple[DomainPower, ...]
    total_clusters: int

    @property
    def required_clusters(self) -> int:
        return minimum_clusters_for_alpha(self.alpha)

    @property
    def supports_significance(self) -> bool:
        return all(domain.powered for domain in self.all_domains)

    @property
    def powered_domains(self) -> tuple[str, ...]:
        return tuple(domain.domain for domain in self.all_domains
                     if domain.powered)

    @property
    def unpowered_domains(self) -> tuple[str, ...]:
        return tuple(domain.domain for domain in self.all_domains
                     if not domain.powered)

    @property
    def shortfall(self) -> int:
        return sum(domain.shortfall for domain in self.all_domains)

    def domain(self, name: str) -> DomainPower:
        for entry in self.all_domains:
            if entry.domain == name:
                return entry
        raise ProtocolRefused("domain-not-in-power-position", name)

    def as_dict(self) -> dict:
        return {"alpha": str(self.alpha),
                "cluster_rule": self.cluster_rule,
                "minimum_p_rule": self.minimum_p_rule,
                "required_clusters": self.required_clusters,
                "total_clusters": self.total_clusters,
                "supports_significance": self.supports_significance,
                "powered_domains": list(self.powered_domains),
                "unpowered_domains": list(self.unpowered_domains),
                "domains": [domain.as_dict() for domain in self.all_domains]}


def compute_power(cells: Iterable[PanelCell], *,
                  alpha: Fraction = ALPHA) -> Power:
    """Cluster the study's own cells and state what they can support."""
    if panel_inventory.CLUSTER_RULE != "(family, template)":
        raise ProtocolRefused("panel-cluster-rule-changed",
                              panel_inventory.CLUSTER_RULE)
    exact = minimum_clusters_for_alpha(alpha)
    if exact != panel_inventory.minimum_clusters_for_alpha(float(alpha)):
        raise ProtocolRefused("cluster-requirement-disagrees-with-panel",
                              "%d vs %d" % (exact, panel_inventory
                               .minimum_clusters_for_alpha(float(alpha))))
    required = exact
    per_domain = []
    for domain in DOMAINS:
        templates = sorted({cell.template for cell in cells
                            if cell.family == domain})
        per_domain.append(DomainPower(
            domain=domain, cluster_count=len(templates),
            minimum_p=minimum_sign_flip_p(len(templates)),
            required_clusters=required,
            cluster_templates=tuple(templates)))
    total = sum(domain.cluster_count for domain in per_domain)
    return Power(alpha=alpha, cluster_rule=panel_inventory.CLUSTER_RULE,
                 minimum_p_rule="2^(1-n) two-sided sign sweep over n clusters",
                 all_domains=tuple(per_domain), total_clusters=total)


@dataclass(frozen=True)
class Freeze:
    """Everything a bundle's freeze must match, plus its own digest."""

    protocol: str
    study_id: str
    study_root: str
    run_id: str
    namespace: NamespaceToken
    model: str
    adapter: str
    api: str
    reasoning_effort: str
    route: Route
    episodes: tuple[Episode, ...]
    panel_digest: str
    freeze_digest: str = ""

    def __post_init__(self) -> None:
        if self.protocol != PROTOCOL_ID:
            raise ProtocolRefused("protocol-id-not-frozen", self.protocol)
        if self.study_id != STUDY_ID:
            raise ProtocolRefused("study-identity-not-frozen", self.study_id)
        if self.study_root != "%s-%s" % (STUDY_ROOT_PREFIX,
                                         self.namespace.token):
            raise ProtocolRefused("study-root-not-derived-from-the-namespace",
                                  self.study_root)
        if self.model != REQUESTED_MODEL:
            raise ProtocolRefused("model-not-the-confirmed-free-route",
                                  self.model)
        if self.adapter != ADAPTER or self.api != API:
            raise ProtocolRefused("transport-not-frozen",
                                  "%s/%s" % (self.adapter, self.api))
        if self.reasoning_effort != REASONING_EFFORT:
            raise ProtocolRefused("reasoning-effort-not-frozen",
                                  self.reasoning_effort)
        if not self.episodes:
            raise ProtocolRefused("freeze-has-no-episodes")
        if [ep.order for ep in self.episodes] != list(
                range(len(self.episodes))):
            raise ProtocolRefused("episode-order-is-not-dense",
                                  "orders are not 0..n-1")
        computed = self.computed_digest()
        if self.freeze_digest and self.freeze_digest != computed:
            raise ProtocolRefused("freeze-digest-mismatch",
                                  "recorded %s computed %s"
                                  % (self.freeze_digest, computed))
        object.__setattr__(self, "freeze_digest", computed)

    def computed_digest(self) -> str:
        return digest(self.body())

    def body(self) -> dict:
        return {
            "protocol": self.protocol,
            "study_id": self.study_id,
            "study_root": self.study_root,
            "run_id": self.run_id,
            "namespace": {"token": self.namespace.token,
                          "run_id": self.namespace.run_id},
            "model": self.model,
            "adapter": self.adapter,
            "api": self.api,
            "reasoning_effort": self.reasoning_effort,
            "route": self.route.as_dict(),
            "panel_digest": self.panel_digest,
            "episodes": [{"order": episode.order,
                          "task_id": episode.task_id,
                          "world": episode.world,
                          "domain": episode.domain,
                          "split": episode.split,
                          "arms": list(episode.arms),
                          "attempts": episode.attempts,
                          "dispatch_arms": list(episode.dispatch_arms)}
                         for episode in self.episodes],
        }

    def as_bundle(self) -> dict:
        body = self.body()
        body["freeze_digest"] = self.freeze_digest
        return body

    @property
    def task_ids(self) -> tuple[str, ...]:
        return tuple(episode.task_id for episode in self.episodes)

    @property
    def operation_ids(self) -> tuple[str, ...]:
        ids = []
        for episode in self.episodes:
            for arm in episode.dispatch_arms:
                for attempt in range(1, episode.attempts + 1):
                    ids.append(episode.operation_id(arm, attempt))
        return tuple(ids)

    @property
    def campaign_ids(self) -> tuple[str, ...]:
        return tuple(episode.campaign_id() for episode in self.episodes)

    @property
    def dispatch_ceiling(self) -> int:
        return sum(episode.dispatches for episode in self.episodes)

    @property
    def episode_count(self) -> int:
        return len(self.episodes)

    @property
    def claim_episode_count(self) -> int:
        return sum(1 for episode in self.episodes if episode.claims)


@dataclass(frozen=True)
class Precondition:
    code: str
    statement: str
    refusal_reason: str


PRECONDITIONS: tuple[Precondition, ...] = (
    Precondition(
        code="disposable-database",
        statement=("the study runs against a database created for this run "
                   "alone; no other study, dry run or replay has ever been "
                   "connected to it"),
        refusal_reason=("a shared database is what let the live run settle "
                        "against already-settled double receipts")),
    Precondition(
        code="namespace-token",
        statement=("the study root, every campaign id and every operation "
                   "id carry this run's namespace token, and no operation "
                   "id outside this run's enumerated set may be read or "
                   "written"),
        refusal_reason=("an operation id that does not carry the token "
                        "cannot be told apart from a prior run's")),
    Precondition(
        code="no-prior-operation-in-namespace",
        statement=("no operation in this run's namespace was created "
                   "before the freeze, and none predates the freeze "
                   "timestamp"),
        refusal_reason=("a pre-freeze row under this run's token is a "
                        "reuse, not an effect of this study")),
    Precondition(
        code="persisted-model-matches-freeze",
        statement=("every persisted operation payload in this namespace has "
                   "`payload->>'model'` equal to the frozen requested model, "
                   "and no row reads `recorded-double` or another model"),
        refusal_reason=("the previous freeze recorded model "
                        "`recorded-double` and the verifier passed it")),
    Precondition(
        code="construction-receipt-is-not-a-reuse",
        statement=("at least one receipt for the construction operation "
                   "settles a real dispatch, not a replay of a receipt "
                   "settled before the freeze"),
        refusal_reason=("a reused construction receipt is a mechanism "
                        "witness wearing an acquisition record")),
    Precondition(
        code="executed-bytes-are-the-bound-bytes",
        statement=("for every arm, the digest of the bytes that executed is "
                   "the digest of the bytes that were bound, and neither is "
                   "an authored fixture's"),
        refusal_reason=("the previous use phase executed an authored method "
                        "and copied the bound digest onto the record")),
)

PRECONDITIONS_BY_CODE = {item.code: item for item in PRECONDITIONS}


@dataclass(frozen=True)
class PreconditionReport:
    code: str
    passed: bool
    detail: str = ""

    def __post_init__(self) -> None:
        if self.code not in PRECONDITIONS_BY_CODE:
            raise ProtocolRefused("unknown-precondition", self.code)


@dataclass(frozen=True)
class PreconditionVerdict:
    satisfied: bool
    unsatisfied: tuple[PreconditionReport, ...]
    unreported: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "satisfied": self.satisfied,
            "unsatisfied": [{"code": report.code, "detail": report.detail}
                            for report in self.unsatisfied],
            "unreported": list(self.unreported),
        }


def evaluate_preconditions(
        reports: Iterable[PreconditionReport]) -> PreconditionVerdict:
    """Pass only on a report for every precondition, and only if all pass.

    A precondition with no report is a refusal, so a gate that skips one
    cannot read as green.
    """
    seen = {}
    for report in reports:
        if report.code in seen:
            raise ProtocolRefused("duplicate-precondition-report",
                                  report.code)
        seen[report.code] = report
    unsatisfied = tuple(seen[item.code] for item in PRECONDITIONS
                        if item.code in seen and not seen[item.code].passed)
    unreported = tuple(item.code for item in PRECONDITIONS
                       if item.code not in seen)
    return PreconditionVerdict(
        satisfied=not unsatisfied and not unreported,
        unsatisfied=unsatisfied, unreported=unreported)


@dataclass(frozen=True)
class BudgetInput:
    name: str
    value: int | None
    source: str

    def __post_init__(self) -> None:
        if not self.name or not self.source:
            raise ProtocolRefused("budget-input-is-unnamed", repr(self.name))
        if self.value is not None and (type(self.value) is not int
                                      or self.value < 0):
            raise ProtocolRefused("budget-value-is-not-a-count",
                                  "%s=%r" % (self.name, self.value))

    @classmethod
    def unknown(cls, name: str, source: str) -> "BudgetInput":
        return cls(name=name, value=None, source=source)

    @property
    def is_known(self) -> bool:
        return self.value is not None


SPENT_INPUT = "already_dispatched"
CEILING_INPUT = "hard_ceiling"

BUDGET_SOURCES = {
    SPENT_INPUT: ("the count of operations in this run's enumerated "
                  "operation-id set that the store holds, settled or with an "
                  "unresolved reservation; never a crash-losable file"),
    CEILING_INPUT: "the study's own enumerated dispatchable operation count",
}


@dataclass(frozen=True)
class Refusal:
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class DispatchCeiling:
    hard_ceiling: int
    already_dispatched: int

    def __post_init__(self) -> None:
        if self.hard_ceiling < 0 or self.already_dispatched < 0:
            raise ProtocolRefused("negative-dispatch-count")

    @property
    def remaining(self) -> int:
        return self.hard_ceiling - self.already_dispatched

    def as_dict(self) -> dict:
        return {"hard_ceiling": self.hard_ceiling,
                "already_dispatched": self.already_dispatched,
                "remaining": self.remaining,
                "sources": dict(BUDGET_SOURCES)}


@dataclass(frozen=True)
class StoppingRule:
    """The dispatch ceiling, derived or refused. Never assumed."""

    rule: str
    default_ceiling: int

    def ceiling(self, inputs: Mapping[str, BudgetInput]) \
            -> DispatchCeiling | Refusal:
        unknown = sorted(name for name, item in inputs.items()
                         if not item.is_known)
        if unknown:
            return Refusal(
                reason="unknown-budget-input",
                detail=("the ceiling is not derivable while %s is unknown; "
                        "naming a number here would authorise dispatches the "
                        "store may already have spent"
                        % ", ".join(unknown)))
        hard = inputs[CEILING_INPUT].value
        spent = inputs[SPENT_INPUT].value
        if hard is None or spent is None:
            return Refusal("missing-budget-input",
                           "the rule needs %s and %s"
                           % (CEILING_INPUT, SPENT_INPUT))
        if spent > hard:
            return Refusal(
                reason="already-over-ceiling",
                detail=("the store holds %d dispatches against a ceiling of "
                        "%d; the round is over budget, not resumable"
                        % (spent, hard)))
        return DispatchCeiling(hard_ceiling=hard, already_dispatched=spent)

    def budget(self, spent: int | None) -> dict[str, BudgetInput]:
        return {CEILING_INPUT: BudgetInput(
                    name=CEILING_INPUT, value=self.default_ceiling,
                    source=BUDGET_SOURCES[CEILING_INPUT]),
                SPENT_INPUT: (
                    BudgetInput(name=SPENT_INPUT, value=spent,
                                source=BUDGET_SOURCES[SPENT_INPUT])
                    if spent is not None else
                    BudgetInput.unknown(SPENT_INPUT,
                                        BUDGET_SOURCES[SPENT_INPUT]))}


STOPPING_RULE = StoppingRule(
    rule=("the ceiling is the freeze's own enumerated dispatchable "
          "operation count, less the dispatches the store holds over that "
          "same enumerated set; an unknown input refuses the ceiling rather "
          "than defaulting it, and the rule never changes after an effect"),
    default_ceiling=0)


@dataclass(frozen=True)
class Acquisition:
    """What the construction phase can support, given what it recorded."""

    state: str
    detail: str
    construction_receipts: int
    non_reuse_receipts: int

    def __post_init__(self) -> None:
        if self.state not in ACQUISITION_STATES:
            raise ProtocolRefused("unknown-acquisition-state", self.state)
        if self.non_reuse_receipts > self.construction_receipts:
            raise ProtocolRefused("non-reuse-receipts-exceed-receipts",
                                  repr(self))

    @property
    def demonstrated(self) -> bool:
        return self.state == ACQ_DEMONSTRATED


ACQ_DEMONSTRATED = "acquisition-demonstrated"
ACQ_UNPROVEN = "acquisition-unproven"
ACQ_CONTAMINATED = "acquisition-contaminated"
ACQ_UNAVAILABLE = "acquisition-unavailable"
ACQUISITION_STATES = (ACQ_DEMONSTRATED, ACQ_UNPROVEN, ACQ_CONTAMINATED,
                      ACQ_UNAVAILABLE)


def classify_acquisition(receipts: Sequence[Mapping[str, Any]], *,
                         frozen_model: str = REQUESTED_MODEL) -> Acquisition:
    """Read the acquisition claim off the construction receipts alone.

    An authored program is a mechanism witness. A receipt that replays a
    pre-freeze settlement is a reuse. A receipt that persisted a model
    other than the frozen one is contamination even when it claims to be
    model-acquired, which is the case the previous round shipped: its
    freeze recorded `recorded-double` and its verifier passed it. A
    receipt that persisted no model at all is a witness, so it leaves
    the phase unproven rather than contaminating it.
    """
    if not receipts:
        return Acquisition(state=ACQ_UNAVAILABLE,
                           detail=("no construction receipt was persisted, "
                                   "so the phase is unavailable rather than "
                                   "negative"),
                           construction_receipts=0, non_reuse_receipts=0)
    clean = [receipt for receipt in receipts
             if receipt.get("provenance") == ACQUIRED
             and not receipt.get("is_reuse")
             and receipt.get("model") == frozen_model]
    reused = [receipt for receipt in receipts if receipt.get("is_reuse")]
    wrong_model = [receipt for receipt in receipts
                   if receipt.get("model") is not None
                   and receipt.get("model") != frozen_model]
    if clean:
        return Acquisition(state=ACQ_DEMONSTRATED,
                           detail=("%d of %d construction receipts are "
                                   "model-acquired on the frozen model and "
                                   "not a reuse"
                                   % (len(clean), len(receipts))),
                           construction_receipts=len(receipts),
                           non_reuse_receipts=len(clean))
    if wrong_model:
        return Acquisition(
            state=ACQ_CONTAMINATED,
            detail=("%d of %d construction receipts persisted a model other "
                    "than the frozen %r; the previous round recorded %r and "
                    "passed its verifier"
                    % (len(wrong_model), len(receipts), frozen_model,
                       DOUBLED)),
            construction_receipts=len(receipts), non_reuse_receipts=0)
    if reused:
        return Acquisition(
            state=ACQ_CONTAMINATED,
            detail=("%d of %d construction receipts replay a settlement "
                    "that predates the freeze"
                    % (len(reused), len(receipts))),
            construction_receipts=len(receipts), non_reuse_receipts=0)
    return Acquisition(state=ACQ_UNPROVEN,
                       detail=("%d construction receipts, none of them "
                               "model-acquired and none a reuse, so the phase "
                               "neither demonstrated nor refuted acquisition"
                               % len(receipts)),
                       construction_receipts=len(receipts),
                       non_reuse_receipts=0)


VERDICT_INELIGIBLE = "ineligible"
VERDICT_UNAVAILABLE = "arm-unavailable"
VERDICT_BENEFIT = "benefit"
VERDICT_TIE = "tie"
VERDICT_NO_BENEFIT = "no-benefit"
VERDICT_TRANSFER = "transfer"
VERDICT_NO_TRANSFER = "no-transfer"

VERDICT_STATEMENT = (
    "A negative, contaminated or unavailable arm is a result. Every arm "
    "that did not produce a measurement is named on the verdict, so a "
    "missing arm cannot be reported by omission.")


@dataclass(frozen=True)
class RuleRow:
    condition: str
    verdict: str
    statement: str
    test: Callable[["Outcome"], bool]


@dataclass(frozen=True)
class Outcome:
    """Everything the decision rule is allowed to look at."""

    freeze_matched: bool
    preconditions_satisfied: bool
    acquisition: Acquisition
    within_delta: Fraction | None
    transfer_delta: Fraction | None
    arm_measurements: Mapping[str, Fraction | None]
    detail: str = ""

    def __post_init__(self) -> None:
        unknown = sorted(set(self.arm_measurements) - set(ARMS))
        if unknown:
            raise ProtocolRefused("arm-not-in-protocol", unknown)
        for arm in ARMS:
            if arm not in self.arm_measurements:
                raise ProtocolRefused("arm-measurement-missing", arm)


def _all_measured(outcome: Outcome) -> bool:
    return all(outcome.arm_measurements[arm] is not None for arm in ARMS)


INELIGIBILITY_RULE: tuple[RuleRow, ...] = (
    RuleRow(condition="freeze-does-not-match",
            verdict=VERDICT_INELIGIBLE,
            statement=("the bundle's freeze digest, model, namespace token, "
                       "route or episode list differs from this protocol"),
            test=lambda outcome: not outcome.freeze_matched),
    RuleRow(condition="preconditions-unproven",
            verdict=VERDICT_INELIGIBLE,
            statement=("a study precondition was unsatisfied or went "
                       "unreported; an unreported precondition is an "
                       "unsatisfied one"),
            test=lambda outcome: not outcome.preconditions_satisfied),
)

ACQUISITION_RULE: tuple[RuleRow, ...] = (
    RuleRow(condition="construction-is-model-acquired",
            verdict=ACQ_DEMONSTRATED,
            statement=("at least one construction receipt is a non-reuse "
                       "model-acquired response with a model equal to the "
                       "frozen model"),
            test=lambda outcome: outcome.acquisition.demonstrated),
    RuleRow(condition="construction-receipt-is-contaminated",
            verdict=ACQ_CONTAMINATED,
            statement=("every construction receipt is a reuse or names a "
                       "model other than the frozen one; this is the "
                       "previous round's failure and it is reported as "
                       "such, not counted as a negative result"),
            test=lambda outcome: outcome.acquisition.state
            == ACQ_CONTAMINATED),
    RuleRow(condition="construction-phase-unavailable",
            verdict=ACQ_UNAVAILABLE,
            statement=("no construction receipt exists; the phase is "
                       "unavailable, which is a result and is reported"),
            test=lambda outcome: outcome.acquisition.state
            == ACQ_UNAVAILABLE),
    RuleRow(condition="construction-produced-no-acquisition",
            verdict=ACQ_UNPROVEN,
            statement=("construction ran and produced no acquired, "
                       "non-reuse bytes; acquisition is unproven, which is "
                       "not the same as refuted"),
            test=lambda outcome: True),
)

BENEFIT_RULE: tuple[RuleRow, ...] = (
    RuleRow(condition="an-arm-produced-no-measurement",
            verdict=VERDICT_UNAVAILABLE,
            statement=("an arm produced no within-scope measurement; the arm "
                       "is named on the verdict and the benefit question is "
                       "not answered on the arms that did measure"),
            test=lambda outcome: not _all_measured(outcome)
            or outcome.within_delta is None),
    RuleRow(condition="improvement-clears-the-margin",
            verdict=VERDICT_BENEFIT,
            statement=("the improvement arm's within-scope mean exceeds the "
                       "authored control's by at least the frozen margin"),
            test=lambda outcome: outcome.within_delta is not None
            and outcome.within_delta >= BENEFIT_MARGIN),
    RuleRow(condition="improvement-within-the-margin",
            verdict=VERDICT_TIE,
            statement=("the improvement arm's within-scope advantage is "
                       "below the frozen margin, so the arms are tied and "
                       "the tie is reported rather than broken"),
            test=lambda outcome: outcome.within_delta is not None
            and outcome.within_delta > 0),
    RuleRow(condition="improvement-below-the-control",
            verdict=VERDICT_NO_BENEFIT,
            statement=("the improvement arm's within-scope mean is below the "
                       "authored control's; no benefit, reported as a result"),
            test=lambda outcome: True),
)

TRANSFER_RULE: tuple[RuleRow, ...] = (
    RuleRow(condition="no-structural-transfer-measurement",
            verdict=VERDICT_NO_TRANSFER,
            statement=("no arm produced a structural-transfer measurement, "
                       "so transfer is not established and is not refuted"),
            test=lambda outcome: outcome.transfer_delta is None),
    RuleRow(condition="improvement-transfers",
            verdict=VERDICT_TRANSFER,
            statement=("the improvement arm's structural-transfer mean "
                       "exceeds the authored control's by at least the "
                       "frozen margin"),
            test=lambda outcome: outcome.transfer_delta is not None
            and outcome.transfer_delta >= BENEFIT_MARGIN),
    RuleRow(condition="improvement-does-not-transfer",
            verdict=VERDICT_NO_TRANSFER,
            statement=("the improvement arm's structural-transfer advantage "
                       "is below the frozen margin; the within-scope result "
                       "does not carry across the structural change"),
            test=lambda outcome: True),
)

DECISION_RULE = "verdict-ineligible-overrides-all-others"


@dataclass(frozen=True)
class DescriptiveOnly:
    """The only claim this study can carry.

    It has no significant variant, so a significance claim is not
    reachable by any code path. When the panel is short of clusters the
    shortfall is named here rather than left to the reader.
    """

    reason: str
    shortfall: int
    unpowered_domains: tuple[str, ...]
    required_clusters: int
    minimum_p_by_domain: tuple[tuple[str, Fraction | None], ...]

    @property
    def is_significant(self) -> bool:
        return False

    def as_dict(self) -> dict:
        return {"claim": "descriptive-only",
                "significant": self.is_significant,
                "reason": self.reason,
                "cluster_shortfall": self.shortfall,
                "unpowered_domains": list(self.unpowered_domains),
                "required_clusters": self.required_clusters,
                "minimum_p_by_domain": [
                    {"domain": domain,
                     "minimum_p": None if value is None else str(value)}
                    for domain, value in self.minimum_p_by_domain]}


@dataclass(frozen=True)
class Verdict:
    ineligible: str | None
    acquisition: str
    within: str
    transfer: str
    claim: DescriptiveOnly
    unavailable_arms: tuple[str, ...]
    evidence: tuple[str, ...]
    rule: str = DECISION_RULE

    @property
    def primary(self) -> str:
        if self.ineligible:
            return self.ineligible
        if self.acquisition in (ACQ_CONTAMINATED, ACQ_UNAVAILABLE):
            return self.acquisition
        return self.within

    def as_dict(self) -> dict:
        return {"primary": self.primary,
                "ineligible": self.ineligible,
                "acquisition": self.acquisition,
                "within_scope": self.within,
                "structural_transfer": self.transfer,
                "unavailable_arms": list(self.unavailable_arms),
                "claim": self.claim.as_dict(),
                "evidence": list(self.evidence),
                "rule": self.rule,
                "verdict_statement": VERDICT_STATEMENT}


def _first(rows: Sequence[RuleRow], outcome: Outcome) -> RuleRow:
    for row in rows:
        if row.test(outcome):
            return row
    raise ProtocolRefused("decision-rule-has-no-matching-row",
                          outcome.detail or outcome.acquisition.state)


@dataclass(frozen=True)
class StudyProtocol:
    freeze: Freeze
    cells: tuple[Cell, ...]
    power: Power
    decision: tuple[RuleRow, ...]
    acquisition_rule: tuple[RuleRow, ...]
    benefit_rule: tuple[RuleRow, ...]
    transfer_rule: tuple[RuleRow, ...]
    preconditions: tuple[Precondition, ...] = PRECONDITIONS
    stopping_rule: StoppingRule = field(default=STOPPING_RULE)

    @property
    def supports_significance(self) -> bool:
        return self.power.supports_significance

    @property
    def claim(self) -> DescriptiveOnly:
        return DescriptiveOnly(
            reason=("the sign sweep's minimum p-value is %s, so a "
                    "significance claim at alpha %s is not reachable"
                    % (", ".join(
                        "%s %s" % (domain.domain, domain.minimum_p)
                        for domain in self.power.all_domains),
                       self.power.alpha)),
            shortfall=self.power.shortfall,
            unpowered_domains=self.power.unpowered_domains,
            required_clusters=self.power.required_clusters,
            minimum_p_by_domain=tuple(
                (domain.domain, domain.minimum_p)
                for domain in self.power.all_domains))

    def cell(self, arm: str, world: int, domain: str) -> Cell:
        for entry in self.cells:
            if (entry.arm, entry.world, entry.domain) == (arm, world, domain):
                return entry
        raise ProtocolRefused("cell-not-in-protocol",
                              "%s/w%d/%s" % (arm, world, domain))

    def validate(self, bundle: Mapping[str, Any]) -> Disposition:
        """Say whether a bundle's freeze MATCHES, and refuse when it does not."""
        reasons: list[str] = []
        details: list[str] = []
        if not isinstance(bundle, Mapping):
            return Disposition(matched=False, reasons=("not-a-freeze-bundle",),
                               details=(type(bundle).__name__,))
        recorded = bundle.get("freeze_digest")
        body = {key: value for key, value in bundle.items()
                if key != "freeze_digest"}
        if recorded != self.freeze.freeze_digest:
            reasons.append("freeze-digest-mismatch")
            details.append("bundle %s protocol %s"
                           % (recorded, self.freeze.freeze_digest))
        elif recorded != digest(body):
            reasons.append("freeze-digest-not-self-consistent")
            details.append("recorded %s recomputes %s"
                           % (recorded, digest(body)))
        for field_name, expected in (
                ("protocol", self.freeze.protocol),
                ("study_id", self.freeze.study_id),
                ("study_root", self.freeze.study_root),
                ("model", self.freeze.model),
                ("adapter", self.freeze.adapter),
                ("api", self.freeze.api),
                ("reasoning_effort", self.freeze.reasoning_effort)):
            if bundle.get(field_name) != expected:
                reasons.append("%s-differs-from-protocol" % field_name)
                details.append("bundle %r protocol %r"
                               % (bundle.get(field_name), expected))
        if not self.freeze.namespace.qualifies(str(bundle.get("study_root"))):
            reasons.append("namespace-token-absent-from-study-root")
            details.append(str(bundle.get("study_root")))
        namespace = bundle.get("namespace")
        run_id = namespace.get("run_id") if isinstance(
            namespace, Mapping) else None
        if run_id != self.freeze.run_id or namespace.get(
                "token") != self.freeze.namespace.token:
            reasons.append("namespace-token-absent-from-this-run")
            details.append("bundle run %r protocol run %r"
                           % (run_id, self.freeze.run_id))
        for value in bundle.get("campaign_ids", ()) or ():
            if not self.freeze.namespace.qualifies(str(value)):
                reasons.append("namespace-token-absent-from-campaign-id")
                details.append(str(value))
                break
        for value in bundle.get("operation_ids", ()) or ():
            if value not in self.freeze.operation_ids:
                reasons.append("operation-id-outside-the-frozen-set")
                details.append(str(value))
                break
        if self.freeze.route.as_dict() != bundle.get("route"):
            reasons.append("route-differs-from-protocol")
            details.append("bundle %s protocol %s"
                           % (bundle.get("route"), self.freeze.route.as_dict()))
        bundle_episodes = bundle.get("episodes")
        if not isinstance(bundle_episodes, Sequence) or isinstance(
                bundle_episodes, (str, bytes)) or len(
                    bundle_episodes) != self.freeze.episode_count:
            reasons.append("episode-count-differs-from-protocol")
            details.append("bundle %s episodes protocol %s"
                           % (len(bundle_episodes) if isinstance(
                               bundle_episodes, Sequence) else "malformed",
                              self.freeze.episode_count))
        elif [item.get("task_id") if isinstance(item, Mapping) else item
              for item in bundle_episodes] != list(self.freeze.task_ids):
            reasons.append("episode-list-differs-from-protocol")
            details.append("ordered task ids differ")
        return Disposition(matched=not reasons, reasons=tuple(reasons),
                           details=tuple(details))

    def require_match(self, bundle: Mapping[str, Any]) -> Freeze:
        disposition = self.validate(bundle)
        if not disposition.matched:
            raise ProtocolRefused(disposition.reason,
                                  "; ".join(disposition.details))
        return self.freeze

    def decide(self, outcome: Outcome) -> Verdict:
        ineligible = None
        evidence = []
        for row in INELIGIBILITY_RULE:
            if row.test(outcome):
                ineligible = row.verdict
                evidence.append("%s: %s" % (row.condition, row.statement))
                break
        acquisition = _first(self.acquisition_rule, outcome)
        within = _first(self.benefit_rule, outcome)
        transfer = _first(self.transfer_rule, outcome)
        unavailable = tuple(arm for arm in ARMS
                            if outcome.arm_measurements[arm] is None)
        for row in (acquisition, within, transfer):
            evidence.append("%s: %s" % (row.condition, row.statement))
        evidence.append(outcome.acquisition.detail)
        if outcome.detail:
            evidence.append(outcome.detail)
        return Verdict(
            ineligible=ineligible, acquisition=acquisition.verdict,
            within=within.verdict, transfer=transfer.verdict,
            claim=self.claim, unavailable_arms=unavailable,
            evidence=tuple(evidence))

    def ceiling(self, already_dispatched: int | None) \
            -> DispatchCeiling | Refusal:
        inputs = self.stopping_rule.budget(already_dispatched)
        return self.stopping_rule.ceiling(inputs)

    def as_dict(self) -> dict:
        body = self.freeze.as_bundle()
        body["protocol_version"] = PROTOCOL_VERSION
        body["cells"] = [{"arm": cell.arm, "world": cell.world,
                          "domain": cell.domain, "count": cell.count,
                          "task_ids": list(cell.task_ids)}
                         for cell in self.cells]
        body["arms"] = [{"name": arm.name, "role": arm.role,
                         "control": arm.control,
                         "benchmark": arm.benchmark,
                         "dispatches": arm.dispatches}
                        for arm in ARMS_BY_NAME]
        body["power"] = self.power.as_dict()
        body["preconditions"] = [
            {"code": item.code, "statement": item.statement,
             "refusal_reason": item.refusal_reason}
            for item in self.preconditions]
        body["stopping_rule"] = self.stopping_rule.rule
        body["dispatch_ceiling"] = self.freeze.dispatch_ceiling
        body["verdict_statement"] = VERDICT_STATEMENT
        body["decision_rule"] = DECISION_RULE
        body["claim"] = self.claim.as_dict()
        return body


def _ordered_episodes(panel: Sequence[PanelCell],
                      namespace_token: str) -> tuple[Episode, ...]:
    selected = [cell for cell in panel
                if cell.world in WORLDS and cell.split in SPLITS]
    selected.sort(key=lambda cell: (
        cell.world, DOMAINS.index(cell.family), SPLITS.index(cell.split),
        cell.task_id))
    episodes = []
    for order, cell in enumerate(selected):
        episodes.append(Episode(
            order=order, world=cell.world, domain=cell.family,
            split=cell.split, task_id=cell.task_id, arms=ARMS,
            attempts=ATTEMPTS_BY_SPLIT[cell.split],
            dispatch_arms=DISPATCHING_ARMS,
            namespace_token=namespace_token))
    return tuple(episodes)


def _ordered_cells(panel: Sequence[PanelCell]) -> tuple[Cell, ...]:
    cells = []
    for arm in ARMS:
        for world in WORLDS:
            for domain in DOMAINS:
                cells.append(Cell(
                    arm=arm, world=world, domain=domain,
                    task_ids=tuple(sorted(
                        cell.task_id for cell in panel
                        if cell.world == world and cell.family == domain
                        and cell.split in SPLITS))))
    return tuple(cells)


def build_protocol(panel_root: Any = None) -> StudyProtocol:
    panel = _panel_cells(panel_root)
    if not panel:
        raise ProtocolRefused("frozen-panel-is-empty", str(panel_root))
    seed_body = {
        "protocol": PROTOCOL_ID,
        "study_id": STUDY_ID,
        "study_root": STUDY_ROOT_PREFIX,
        "model": REQUESTED_MODEL,
        "adapter": ADAPTER,
        "api": API,
        "reasoning_effort": REASONING_EFFORT,
        "route": FROZEN_ROUTE.as_dict(),
        "episodes": [[cell.task_id, cell.world, cell.family, cell.split]
                     for cell in sorted(
                         (cell for cell in panel
                          if cell.world in WORLDS and cell.split in SPLITS),
                         key=lambda cell: (
                             cell.world, DOMAINS.index(cell.family),
                             SPLITS.index(cell.split), cell.task_id))],
    }
    # The run id is derived from the frozen content, so re-freezing the
    # same protocol reproduces the same namespace and a different round
    # cannot inherit one by accident.
    run_id = digest(seed_body)[:32]
    token = run_token(run_id)
    study_root = "%s-%s" % (STUDY_ROOT_PREFIX, token)
    episodes = _ordered_episodes(panel, token)
    freeze = Freeze(
        protocol=PROTOCOL_ID, study_id=STUDY_ID, study_root=study_root,
        run_id=run_id, namespace=NamespaceToken(token=token, run_id=run_id),
        model=REQUESTED_MODEL, adapter=ADAPTER, api=API,
        reasoning_effort=REASONING_EFFORT, route=FROZEN_ROUTE,
        episodes=episodes,
        panel_digest=digest([asdict(cell) for cell in panel]))
    return StudyProtocol(
        freeze=freeze, cells=_ordered_cells(panel),
        power=compute_power(panel), decision=INELIGIBILITY_RULE,
        acquisition_rule=ACQUISITION_RULE, benefit_rule=BENEFIT_RULE,
        transfer_rule=TRANSFER_RULE,
        stopping_rule=replace(
            STOPPING_RULE, default_ceiling=freeze.dispatch_ceiling))


PROTOCOL = build_protocol()
