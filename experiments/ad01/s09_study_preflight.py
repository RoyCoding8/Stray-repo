"""A preflight that refuses to let a live study start on an unproven premise.

The doubles dry run and the live run shared one database. Deterministic
operation ids let the live run settle against receipts the doubles had
already written, and the verifier passed. Every precondition here exists
because a gate that reported `unknown` and let the run continue is what
turned that into a result.

The catastrophic failure this module exists to prevent is an `unknown`
silently counted as a `pass`. So `may_start` is derived rather than carried,
and an unknown blocks as loudly as a failure does.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict

from settlement.gateway_http import HttpGatewayAdapter

from experiments.ad01.s09_run_isolation import DB_PREFIX

STUDY_CONFIG_ENV = "S09_STUDY_CONFIG"
LIVE_GRANT_ENV = "S09_M5_LIVE_GRANT"
DEFAULT_CONFIG_PATH = "~/.config/agent-society-live.env"
ENDPOINT_VAR = "SETTLEMENT_GATEWAY_ENDPOINT"
KEY_VAR = "SETTLEMENT_GATEWAY_KEY"
DISPOSABLE_PREFIXES = ("s09pf_", DB_PREFIX + "_")
ROW_CEILING = 10_000
NO_EVIDENCE = "evidence"
EXPOSURE_MODULE = "experiments.ad01.s09_exposure_ledger"


BUNDLE_MEMBERS = ("freeze", "development", "construction", "assessment",
                  "use_records", "operations", "accounting",
                  "refusal_probes", "conformance_replay")
TAMPERINGS = ("model-mismatch", "digest-provenance-mismatch")
_JUDGE_AUTHORITY = object()


class Precondition(StrEnum):
    ROUTE_LIVENESS = "route-liveness"
    STUDY_DATABASE = "study-database"
    VERIFIER_AUTHORITY = "verifier-authority"
    POLICY_GOVERNANCE = "policy-governance"
    EXPOSURE_BUDGET = "exposure-budget"


ASKS = {
    Precondition.ROUTE_LIVENESS:
        "a live route answers metadata, and the freeze names the model",
    Precondition.STUDY_DATABASE:
        "the study database is disposable, unique, and holds nothing from "
        "before the freeze",
    Precondition.VERIFIER_AUTHORITY:
        "the verifier that will judge the bundle refuses a model mismatch "
        "and a digest-provenance mismatch",
    Precondition.POLICY_GOVERNANCE:
        "the use evidence persists the executed digest list and the action "
        "the policy admitted, so execution is distinguishable from a copy",
    Precondition.EXPOSURE_BUDGET:
        "carried exposure is reconciled and the ceiling follows from it",
}


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class Refusal(StrEnum):
    NO_GATEWAY_ENDPOINT = "no-gateway-endpoint"
    NO_GATEWAY_KEY = "no-gateway-key"
    GATEWAY_UNREACHABLE = "gateway-unreachable"
    GATEWAY_UNHEALTHY = "gateway-unhealthy"
    GATEWAY_UNAUTHENTICATED = "gateway-unauthenticated"
    GATEWAY_UNUSABLE = "gateway-unusable"
    NO_ROUTE_PROBE = "no-route-probe"
    NOT_DISPOSABLE = "not-disposable"
    CROSS_STUDY_OPERATIONS = "cross-study-operations"
    MODEL_MISMATCH = "model-mismatch"
    UNREADABLE_DATABASE = "unreadable-database"
    NAMESPACE_PREDATES_FREEZE = "namespace-predates-freeze"
    NAMESPACE_AGE_UNMEASURABLE = "namespace-age-unmeasurable"
    MISSING_FREEZE = "missing-freeze"
    UNFROZEN_BUNDLE = "unfrozen-bundle"
    FREEZE_SELF_INCONSISTENT = "freeze-self-inconsistent"
    VERIFIER_UNREADABLE = "verifier-unreadable"
    NO_CLAIM_PROBE = "no-claim-probe"
    CAPABILITY_MISSING = "capability-missing"
    POLICY_GOVERNANCE_UNPROVEN = "policy-governance-unproven"
    NO_EXPOSURE_LEDGER = "no-exposure-ledger"
    EXPOSURE_UNRECONCILED = "exposure-unreconciled"
    BUDGET_UNRESOLVED = "budget-unresolved"
    NO_OBSERVATION = "no-observation"


class Unknown(Exception):
    """A fact this preflight could not determine.

    A `fail` is a measurement that went the wrong way. An `unknown` is the
    absence of one, and the last study died of the absence.
    """

    def __init__(self, refusal: Refusal, detail: str = "") -> None:
        self.refusal = Refusal(refusal)
        self.detail = detail
        super().__init__("%s: %s" % (self.refusal, detail) if detail
                         else str(self.refusal))

    @property
    def verdict(self) -> Unmeasured:
        return Unmeasured(self.refusal, self.detail)


class Refused(Exception):
    """An input this preflight could not read at all."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NamespaceAge(StrEnum):
    AFTER_FREEZE = "after-freeze"
    BEFORE_FREEZE = "before-freeze"
    UNMEASURABLE = "unmeasurable"


@dataclass(frozen=True)
class Evidence:
    """A fact read off disk, the wire, or a database.

    The only way to hold one is to have read it. It refuses to be built
    without the moment the reading was taken, so no check can reason about
    a value whose moment is unstated.
    """

    detail: str
    read_at: str

    def __post_init__(self) -> None:
        if not self.read_at.strip():
            raise ValueError("evidence needs the moment it was read")
        if not self.detail.strip():
            raise ValueError("evidence must say what was read")

    def as_dict(self) -> dict:
        return {"detail": self.detail, "read_at": self.read_at}


@dataclass(frozen=True)
class Verdict_:
    status: Verdict
    evidence: str = NO_EVIDENCE

    def __post_init__(self) -> None:
        if self.status is Verdict.UNKNOWN and self.evidence != NO_EVIDENCE:
            raise ValueError("an unknown carries no evidence to carry")
        if self.status is not Verdict.UNKNOWN and not self.evidence.strip():
            raise ValueError("a decided verdict needs the evidence for it")

    @property
    def blocks(self) -> bool:
        return self.status is not Verdict.PASS


class Pass(Verdict_):
    def __init__(self, evidence: Evidence) -> None:
        super().__init__(Verdict.PASS, evidence.detail)


class Fail(Verdict_):
    def __init__(self, refusal: Refusal, evidence: Evidence | None = None
                 ) -> None:
        super().__init__(Verdict.FAIL,
                         evidence.detail if evidence is not None
                         else str(Refusal(refusal)))
        object.__setattr__(self, "refusal", Refusal(refusal))

    @property
    def reported(self) -> str:
        return "%s: %s" % (self.refusal, self.evidence)


class Unmeasured(Verdict_):
    """The unknown verdict: a fact nobody measured.

    It holds the refusal and nothing else, because an unknown has no
    evidence to report and any string it carried could be mistaken for
    one.
    """

    def __init__(self, refusal: Refusal, detail: str = "") -> None:
        super().__init__(Verdict.UNKNOWN, NO_EVIDENCE)
        object.__setattr__(self, "refusal", Refusal(refusal))
        object.__setattr__(self, "detail", detail)

    @property
    def reported(self) -> str:
        return ("%s: %s" % (self.refusal, self.detail) if self.detail
                else str(self.refusal))


@dataclass(frozen=True)
class Outcome:
    precondition: Precondition
    verdict: Verdict_
    detail: str = ""

    @property
    def blocks(self) -> bool:
        return self.verdict.status is not Verdict.PASS

    @property
    def subject(self) -> str:
        if self.verdict.status is Verdict.UNKNOWN:
            return self.verdict.reported
        if self.verdict.status is Verdict.FAIL:
            return self.verdict.reported
        return ("%s %s" % (self.verdict.evidence, self.detail)
                if self.detail else self.verdict.evidence)

    def as_dict(self) -> dict:
        record = {"precondition": str(self.precondition),
                  "asks": ASKS[self.precondition],
                  "status": str(self.verdict.status),
                  "evidence": self.subject}
        if self.detail:
            record["detail"] = self.detail
        return record


@dataclass(frozen=True)
class PreflightResult:
    """The start decision, and nothing a caller can assemble by hand.

    `_authority` is the brand. It exists so a passing result cannot be
    fabricated out of five `Pass` outcomes: only `Preconditions.judge`
    holds the token, and it hands one out only after judging every
    precondition from what was actually observed.

    `may_start` is derived, never carried. A caller cannot hand this a
    verdict, a count, or a boolean, so there is no field to set wrongly.
    """

    outcomes: tuple[Outcome, ...]
    judged_at: str = field(default="", repr=False, compare=False)
    _authority: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._authority is not _JUDGE_AUTHORITY:
            raise TypeError(
                "a PreflightResult is only Preconditions.judge's to build")
        if [outcome.precondition for outcome in self.outcomes] != \
                list(Preconditions.ORDER):
            raise ValueError(
                "every precondition must be judged exactly once, in order")

    @property
    def blockers(self) -> tuple[Outcome, ...]:
        return tuple(outcome for outcome in self.outcomes if outcome.blocks)

    @property
    def unknowns(self) -> tuple[Outcome, ...]:
        return tuple(outcome for outcome in self.outcomes
                     if outcome.verdict.status is Verdict.UNKNOWN)

    @property
    def may_start(self) -> bool:
        """True only when every precondition passed, and no one is unknown.

        An `unknown` is not a soft fail. It is the absence of the
        measurement that would have decided, and the last study turned an
        absence into a result. So the count of unknowns is checked
        separately from the count of blockers: a gate that only looked at
        blockers could read a missing precondition as a quiet pass.
        """
        return not self.blockers and not self.unknowns

    def __bool__(self) -> bool:
        return self.may_start

    def outcome(self, precondition: Precondition) -> Outcome:
        for outcome in self.outcomes:
            if outcome.precondition is Precondition(precondition):
                return outcome
        raise KeyError(str(precondition))

    def status(self, precondition: Precondition) -> Verdict:
        return self.outcome(precondition).verdict.status

    def evidence(self, precondition: Precondition) -> str:
        return self.outcome(precondition).verdict.evidence

    def refusals(self) -> list[str]:
        return ["%s %s -- %s" % (outcome.precondition,
                                 outcome.verdict.status, outcome.subject)
                for outcome in self.blockers]

    def as_dict(self) -> dict:
        return {"may_start": self.may_start,
                "preconditions": [outcome.as_dict()
                                  for outcome in self.outcomes],
                "unknown": [str(outcome.precondition)
                            for outcome in self.unknowns],
                "refusals": self.refusals(),
                "judged_at": self.judged_at}


@dataclass(frozen=True)
class GatewayKey:
    """The only type here allowed to hold key bytes.

    It refuses to be formatted, so the value cannot reach a report, a log
    line, a fixture, or an exception message by accident.
    """

    _value: str = field(repr=False, compare=False)

    def __str__(self) -> str:
        return "<gateway-key redacted>"

    def __repr__(self) -> str:
        return "<GatewayKey redacted>"

    def __format__(self, spec: str) -> str:
        return str(self)

    def __len__(self) -> int:
        return len(self._value)


@dataclass(frozen=True)
class GatewayConfig:
    endpoint: str
    key_digest: str
    source: str

    def as_dict(self) -> dict:
        return {"endpoint": self.endpoint, "key_digest": self.key_digest,
                "source": self.source}


@dataclass(frozen=True)
class StudyDatabase:
    dsn: str
    name: str

    def as_dict(self) -> dict:
        return {"dsn": self.dsn, "name": self.name}


@dataclass(frozen=True)
class StudyFreeze:
    study_id: str
    study_root: str
    model: str
    frozen_at: str
    digest: str

    def as_dict(self) -> dict:
        return {"study_id": self.study_id, "study_root": self.study_root,
                "model": self.model, "frozen_at": self.frozen_at,
                "digest": self.digest}


@dataclass(frozen=True)
class ModelDrift:
    operation_id: str
    frozen_model: str
    observed_model: str


@dataclass(frozen=True)
class ForeignOperation:
    operation_id: str
    study_root: str


@dataclass(frozen=True)
class DatabaseObservation:
    database: StudyDatabase
    age: NamespaceAge = NamespaceAge.UNMEASURABLE
    schema: str = ""
    prefreeze_operations: int = 0
    operations_in_namespace: int = 0
    drift: tuple[ModelDrift, ...] = ()
    foreign: tuple[ForeignOperation, ...] = ()
    refused: str = ""

    @property
    def readable(self) -> bool:
        return not self.refused

    @property
    def name(self) -> str:
        return self.database.name

    def as_dict(self) -> dict:
        return {**self.database.as_dict(), "schema": self.schema,
                "age": str(self.age),
                "operations_in_namespace": self.operations_in_namespace,
                "prefreeze_operations": self.prefreeze_operations,
                "drift": [{"operation_id": item.operation_id,
                           "frozen_model": item.frozen_model,
                           "observed_model": item.observed_model}
                          for item in self.drift],
                "foreign": [{"operation_id": item.operation_id,
                             "study_root": item.study_root}
                            for item in self.foreign],
                "refused": self.refused}


@dataclass(frozen=True)
class RouteProbe:
    verdict: Verdict_
    detail: str = ""


@dataclass(frozen=True)
class VerifierProbe:
    tampering: str
    verdict: Verdict_


@dataclass(frozen=True)
class ExposureTerm:
    label: str
    units: int
    evidence: str


@dataclass(frozen=True)
class ExposureLedger:
    """The units earlier studies still carry, as the ledger reconciled them.

    Units, not operations. The last two settlements are worth 5563 units
    between them and settled a handful of operations, so any budget
    computed in operations would clear by six orders of magnitude.
    """

    study_id: str
    source: str
    carried_units: int
    all_verified: bool
    arithmetic: str
    terms: tuple[ExposureTerm, ...] = ()

    @property
    def reconciled(self) -> bool:
        return self.all_verified

    @property
    def carried_forward(self) -> tuple[ExposureTerm, ...]:
        return tuple(term for term in self.terms if term.evidence != "VERIFIED")

    def as_dict(self) -> dict:
        return {"study_id": self.study_id, "source": self.source,
                "carried_units": self.carried_units,
                "all_verified": self.all_verified,
                "arithmetic": self.arithmetic,
                "terms": [{"study": term.label, "units": term.units,
                           "evidence": term.evidence}
                          for term in self.terms]}


@dataclass(frozen=True)
class Budget:
    """A resume reading, in dispatches alone.

    `ceiling` is a count of sends the freeze authorized and `exposure` is
    not a number in this currency at all. The 5563 held units belong to two
    prior campaigns under their own grants; subtracting them from a send
    count produced a negative number of dispatches that meant nothing.
    """

    already_spent: int
    ceiling: int

    @property
    def remaining(self) -> int:
        return self.ceiling - self.already_spent

    def as_dict(self) -> dict:
        return {"already_spent_dispatches": self.already_spent,
                "ceiling_dispatches": self.ceiling,
                "remaining_dispatches": self.remaining}


@dataclass(frozen=True)
class Observations:
    """Everything the outside world was asked, captured before the run.

    The preflight is pure, so a study can never half-execute. A probe that
    failed reports no observation at all, and an absent observation is an
    `unknown` rather than a default.
    """

    freeze: StudyFreeze | None = None
    database: DatabaseObservation | None = None
    route: GatewayConfig | None = None
    route_probe: RouteProbe | None = None
    verifier: tuple[VerifierProbe, ...] = ()
    governance: Verdict_ | None = None
    exposure: ExposureLedger | None = None
    ceiling: int | None = None
    already_spent: int | None = None


@dataclass(frozen=True)
class StudyConfig:
    dsn: str
    bundle: str
    model: str = ""
    frozen_at: str = ""
    config_path: str = ""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest_of(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_env_text(text: str, *, source: str) -> Mapping[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        values[name.strip().removeprefix("export ").strip()] = value.strip()
    if not values:
        raise Refused("%s defines no variables" % source)
    return values


def config_file(explicit: str = "") -> Path:
    if explicit:
        return Path(explicit).expanduser()
    from_env = os.environ.get(STUDY_CONFIG_ENV, "")
    if from_env:
        return Path(from_env).expanduser()
    return Path(DEFAULT_CONFIG_PATH).expanduser()


def config_values(explicit: str = "",
                  environ: Mapping[str, str] | None = None
                  ) -> Mapping[str, str]:
    values: dict[str, str] = dict(os.environ if environ is None else environ)
    source = config_file(explicit)
    if source.is_file():
        values = {**parse_env_text(source.read_text(encoding="utf-8"),
                                   source=str(source)), **values}
    return values


def gateway_config(path: str = "", environ: Mapping[str, str] | None = None
                   ) -> tuple[GatewayConfig, GatewayKey]:
    source = str(config_file(path))
    values = config_values(path, environ)
    endpoint = values.get(ENDPOINT_VAR, "")
    if not endpoint:
        raise Unknown(Refusal.NO_GATEWAY_ENDPOINT,
                      "%s sets no %s" % (source, ENDPOINT_VAR))
    raw_key = values.get(KEY_VAR, "")
    if not raw_key:
        raise Unknown(Refusal.NO_GATEWAY_KEY, "%s sets no %s" % (source,
                                                                 KEY_VAR))
    config = GatewayConfig(endpoint=endpoint.rstrip("/"),
                           key_digest=digest_of(raw_key), source=source)
    return config, GatewayKey(raw_key)


def database_name(dsn: str) -> str:
    """Read the database name out of a DSN without trusting its shape.

    The isolation guarantee is that this preflight only ever inspects a
    local database it was pointed at by name, so the name has to be
    derivable. A DSN this cannot read is refused rather than guessed at.
    """
    import os

    try:
        values = conninfo_to_dict(dsn)
    except psycopg.ProgrammingError as exc:
        raise Refused("dsn is not a libpq connection string: %s" % exc) from exc
    name = values.get("dbname", "")
    if not name or name == os.environ.get("PGDATABASE", ""):
        raise Refused("dsn names no database")
    host = values.get("host", "")
    if host and not (host.startswith("/") or host in ("localhost",
                                                       "127.0.0.1", "::1")):
        raise Refused("dsn host %r is not this machine's socket" % (host,))
    return name


def study_database(dsn: str) -> StudyDatabase:
    return StudyDatabase(dsn=dsn, name=database_name(dsn))


def is_disposable(name: str) -> bool:
    return name.startswith(DISPOSABLE_PREFIXES)


def freeze_from_mapping(freeze: Any, frozen_at: str = "",
                        source: Any = "freeze") -> StudyFreeze:
    if not isinstance(freeze, Mapping):
        raise Unknown(Refusal.MISSING_FREEZE, "%s is not an object" % (source,))
    config = freeze.get("config")
    if not isinstance(config, Mapping) or not isinstance(
            config.get("model"), str) or not config["model"]:
        raise Unknown(Refusal.MISSING_FREEZE,
                      "%s names no config.model" % (source,))
    return StudyFreeze(study_id=str(freeze.get("study_id", "")),
                       study_root=str(freeze.get("study_root", "")),
                       model=str(config["model"]),
                       frozen_at=frozen_at or str(freeze.get("frozen_at", "")),
                       digest=str(freeze.get("freeze_digest", "")))


def read_bundle(bundle_dir: str) -> dict[str, Any]:
    root = Path(bundle_dir)
    return {name: json.loads(
        (root / ("%s.json" % name)).read_text(encoding="utf-8"))
        for name in BUNDLE_MEMBERS}


def read_study_freeze(bundle_dir: str, frozen_at: str = "") -> StudyFreeze:
    """Read the freeze and require its own digest to recompute.

    A doubles bundle is a lawful study. It is not a live one, and a digest
    that does not recompute means the freeze is not a freeze at all.
    """
    from scripts import s09_verify
    bundle = read_bundle(bundle_dir)
    freeze = bundle.get("freeze")
    study = freeze_from_mapping(freeze, frozen_at, Path(bundle_dir) / "freeze.json")
    recomputed = s09_verify.freeze_digest(dict(freeze))
    if recomputed != study.digest:
        raise Unknown(Refusal.FREEZE_SELF_INCONSISTENT,
                      "freeze_digest %s recomputes to %s" % (study.digest,
                                                             recomputed))
    return study


def probe_route(config: GatewayConfig, key: GatewayKey, *,
                client: Any | None = None) -> RouteProbe:
    """Confirm liveness and a configured route with no inference call.

    Both surfaces are metadata. Neither dispatches a model, so this probe
    cannot spend the study's budget.
    """
    adapter = HttpGatewayAdapter(
        endpoint=config.endpoint, api_key=key._value, api="responses",
        route_mode="free", client=client, timeout_connect_ms=5_000,
        timeout_read_ms=10_000, timeout_total_ms=15_000)
    health_url = "%s/health" % control_plane_root(config.endpoint)
    health = _get(adapter, health_url)
    if health is None:
        return RouteProbe(Unmeasured(Refusal.GATEWAY_UNREACHABLE,
                                  "GET %s did not answer" % health_url))
    code, body = health
    if code != 200 or not isinstance(body, Mapping) \
            or body.get("status") != "ok":
        return RouteProbe(Unmeasured(Refusal.GATEWAY_UNHEALTHY,
                                  "GET %s returned %d %s" % (
                                      health_url, code, canonical(body))))
    catalog_url = "%s/models" % adapter.endpoint
    catalog = _get(adapter, catalog_url)
    if catalog is None:
        return RouteProbe(Unmeasured(Refusal.GATEWAY_UNREACHABLE,
                                  "GET %s did not answer" % catalog_url))
    code, digest, listed = catalog
    if code != 200:
        return RouteProbe(Unmeasured(Refusal.GATEWAY_UNAUTHENTICATED,
                                  "GET %s returned %d with the configured key"
                                  % (catalog_url, code)))
    if not listed:
        return RouteProbe(Unmeasured(Refusal.GATEWAY_UNUSABLE,
                                  "GET %s listed no model" % catalog_url))
    return RouteProbe(Pass(Evidence(
        "GET %s 200 status=ok; GET %s 200 sha256=%s models=%d"
        % (health_url, catalog_url, digest, listed),
        now())))


def control_plane_root(endpoint: str) -> str:
    """Strip the API version segment, which health is not served under.

    The adapter's endpoint is the versioned API base. The gateway serves
    `/health` from its own root, so asking for `<base>/health` 404s against
    a live gateway and the probe would report an unreachable route for a
    route that is up.
    """
    base, separator, version = endpoint.rpartition("/")
    if separator and version.startswith("v") and version[1:].isdigit():
        return base
    return endpoint.rstrip("/")


def _get(adapter: HttpGatewayAdapter, url: str
         ) -> tuple[int, Any] | tuple[int, str, int] | None:
    """GET a URL and return its body, or None if the wire refused to answer.

    `/health` yields `(code, body)` and `/models` yields
    `(code, digest, count)`. The caller unpacks, so this cannot know which
    shape is wanted; the health check is done on the parsed body.
    """
    import httpx

    owned = adapter._client is None
    client = adapter._client if not owned else httpx.Client(
        timeout=adapter.total_s)
    try:
        response = client.get(url, headers=adapter._headers())
    except httpx.HTTPError:
        return None
    finally:
        if owned:
            client.close()
    if url.endswith("/health"):
        try:
            return response.status_code, json.loads(response.content)
        except ValueError:
            return response.status_code, {}
    listed = 0
    try:
        body = json.loads(response.content)
    except ValueError:
        body = None
    if isinstance(body, Mapping) and isinstance(body.get("data"), list):
        listed = len(body["data"])
    return response.status_code, digest_of(response.text), listed


def _namespace_token(study_root: str) -> str:
    """The per-run token a study root carries, or "" when it carries none.

    The root is `<base>-<token>`, so the token is whatever follows the last
    dash. A root with no token yields "", and the caller then falls back to
    the study_root column rather than guessing.
    """
    if not study_root or "-" not in study_root:
        return ""
    return study_root.rsplit("-", 1)[-1]


def observe_database(database: StudyDatabase, freeze: StudyFreeze, *,
                     client: Any | None = None) -> DatabaseObservation:
    """Read what the study's database already holds, before the study owns it.

    Every row is read, not just the ones matching this study's namespace.
    A row foreign in both its id and its `study_root` matches neither a
    namespace predicate, so a scoped query reports a contaminated database
    as empty. This precondition is only meaningful against a database
    dedicated to the study, and a dedicated database holds nothing else.

    The model comparison happens here rather than in SQL so a mismatch is
    named the same way whichever lane reads it.
    """
    owned = client is None
    if owned:
        from psycopg.rows import dict_row
        from settlement import db
        client = db.connect(database.dsn, row_factory=dict_row,
                            connect_timeout=5)
    try:
        if "operations" not in _table_names(client):
            return DatabaseObservation(
                database, refused="%s has no operations table" % database.name)
        rows = client.execute(
            "SELECT id, payload->>'model' AS model,"
            " payload->>'study_root' AS study_root, created_at"
            " FROM operations ORDER BY id LIMIT %s",
            (ROW_CEILING + 1,)).fetchall()
    except Exception as exc:
        return DatabaseObservation(
            database, refused="%s: %s" % (type(exc).__name__, exc))
    finally:
        if owned:
            client.close()
    if len(rows) > ROW_CEILING:
        return DatabaseObservation(
            database, refused="%s holds more than %d operations, so the read "
            "was truncated and its rows cannot be cleared" % (
                database.name, ROW_CEILING))
    drift: list[ModelDrift] = []
    foreign: list[ForeignOperation] = []
    prefreeze = 0
    token = _namespace_token(freeze.study_root)
    for row in rows:
        observed_root = str(row.get("study_root") or "")
        operation_id = str(row["id"])
        if observed_root:
            if observed_root != freeze.study_root:
                foreign.append(ForeignOperation(operation_id, observed_root))
                continue
        elif token and token not in operation_id:
            # No study_root on the row, which is the normal shape, so the
            # operation id has to carry the run's namespace. An id without it
            # belongs to some other run, and treating it as ours is how a
            # settled receipt from a prior run gets replayed.
            foreign.append(ForeignOperation(
                operation_id, "no study_root and no namespace token on the id"))
            continue
        observed_model = str(row.get("model") or "")
        if observed_model and observed_model != freeze.model:
            drift.append(ModelDrift(str(row["id"]), freeze.model,
                                     observed_model))
        created = row.get("created_at")
        if created is not None and _predates(created, freeze.frozen_at):
            prefreeze += 1
    return DatabaseObservation(
        database=database, age=_age(freeze.frozen_at, prefreeze),
        schema="migrated", prefreeze_operations=prefreeze,
        operations_in_namespace=len(rows) - len(foreign), drift=tuple(drift),
        foreign=tuple(foreign))


def _age(frozen_at: str, prefreeze: int) -> NamespaceAge:
    if not frozen_at.strip():
        return NamespaceAge.UNMEASURABLE
    return (NamespaceAge.BEFORE_FREEZE if prefreeze
            else NamespaceAge.AFTER_FREEZE)


def _predates(created: Any, frozen_at: str) -> bool:
    from datetime import datetime
    if not frozen_at.strip():
        return False
    try:
        moment = datetime.fromisoformat(frozen_at)
    except ValueError:
        return False
    if created.tzinfo is None and moment.tzinfo is not None:
        moment = moment.replace(tzinfo=None)
    elif moment.tzinfo is None and created.tzinfo is not None:
        created = created.replace(tzinfo=None)
    return created < moment


def _table_names(client: Any) -> frozenset[str]:
    rows = client.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    ).fetchall()
    return frozenset(str(row["tablename"] if isinstance(row, Mapping)
                         else row[0]) for row in rows)


POLICY_SOURCE = (
    "def STEP(view, state):\n"
    "    return {'kind': 'check', 'target': 'view', 'inputs': {},"
    " 'evidence_refs': [], 'requested_resources': {}}\n"
)
METHOD_SOURCE = "def solve(task, oracle):\n    return oracle()\n"
FROZEN_MODEL = "frozen-model-under-test"


PROBE_ARM = "P0"
PROBE_TASK = "probe-use-task"
PROBE_RECORD = "probe-assess-1-" + PROBE_TASK
PROBE_OPERATION = "probe-op-1"
FOREIGN_SOURCE = "def solve(task, oracle):\n    return None\n"


def probe_bundle() -> dict[str, Any]:
    """A minimal bundle that `verify_bundle` accepts as honest.

    The verifier probe needs an honest baseline it can compare a tampered
    bundle against, or it cannot tell a refusal from a complaint the
    fixture would have made anyway.
    """
    from scripts import s09_verify
    policy_digest = digest_of(POLICY_SOURCE)
    method_digest = digest_of(METHOD_SOURCE)
    freeze = {
        "study_id": "s09-preflight-probe", "study_root": "s09-preflight",
        "artifact_kind": "learning-policy", "policy_abi": "ad01-policy-step-v1",
        "arms": [PROBE_ARM], "order": ["probe-assess-1"], "development": [],
        "construction_allowance": {PROBE_ARM: {"init": 0, "repair": 0}},
        "assessment": [{"arm": PROBE_ARM, "episode_id": "probe-assess-1",
                        "domain": "software",
                        "investigation_task": "probe-task",
                        "use_tasks": [PROBE_TASK]}],
        "caps": {"per_episode": {"policy_steps": 6, "model_calls": 6},
                 "diagnostic_queries_per_episode": 16,
                 "study_model_calls": 10},
        "metric_rule": {}, "resource_rule": {}, "config": {"model": FROZEN_MODEL},
        "policy_identities": {PROBE_ARM: {
            "status": "available", "source": POLICY_SOURCE,
            "source_digest": policy_digest,
            "artifact": {"kind": "learning-policy",
                         "source_digest": policy_digest, "entry": "STEP",
                         "abi": "ad01-policy-step-v1",
                         "origin": "authored-control"}}},
        "method_repertoires": {PROBE_ARM: {
            "members": [{"method_source": METHOD_SOURCE,
                         "source_digest": method_digest, "entry": "solve",
                         "capability_id": "probe-member"}],
            "member_digests": [method_digest]}},
    }
    freeze["freeze_digest"] = s09_verify.freeze_digest(freeze)
    return {"freeze": freeze, "development": [],
            "assessment": [{"arm": PROBE_ARM, "episode_id": "probe-assess-1",
                            "policy_steps": 1, "model_calls": 0,
                            "witness_queries": 0,
                            "policy_actions": [{"kind": "check"}],
                            "policy_digest": policy_digest,
                            "operations": [PROBE_OPERATION]}],
            "construction": {PROBE_ARM: {
                "arm": PROBE_ARM, "status": "available",
                # The verifier reads the model off the construction request,
                # which is where the contaminated bundle recorded
                # `recorded-double`. An empty construction section made the
                # model-mismatch tampering untestable, so the probe reported a
                # missing capability the verifier had all along.
                "construction_requests": [
                    {"model": FROZEN_MODEL, "operation_id": PROBE_OPERATION,
                     "adapter": "probe", "api": "responses",
                     "endpoint_digest": "probe"}]}},
            "use_records": [], "operations": {},
            "accounting": s09_verify.empty_accounting(),
            "refusal_probes": [{"probe_id": "probe-1", "refused": True,
                                "observed_new_ops": []}],
            "conformance_replay": {"status": "conformance",
                                   "identity": "supported",
                                   "changed": "refused"}}

def tampered_bundle(tampering: str) -> dict[str, Any]:
    """Break the one thing the judge must refuse, in the way the last run broke.

    A use record claiming a digest it did not run is the campaign's named
    failure, and a record naming a model the freeze never froze is the
    other. Each tampering leaves everything else honest, so any complaint
    the verifier adds is a complaint about the tampering.
    """
    from scripts import s09_verify
    if tampering not in TAMPERINGS:
        raise Refused("unknown tampering %r" % (tampering,))
    bundle = probe_bundle()
    method_digest = digest_of(METHOD_SOURCE)
    record = {"record_id": PROBE_RECORD, "arm": PROBE_ARM,
              "study_arm": PROBE_ARM, "executed": "policy",
              "policy_digest": digest_of(POLICY_SOURCE),
              "executed_source_digest": method_digest,
              "executed_source": METHOD_SOURCE, "model": FROZEN_MODEL,
              "costs": {"witness_queries": 0}, "operation_ids": [PROBE_OPERATION]}
    if tampering == "model-mismatch":
        # The verifier reads the model off the construction request, which is
        # where the contaminated bundle recorded `recorded-double`. Tampering
        # a use record's model left the request honest, so the check correctly
        # drew nothing and the probe reported a missing capability that was
        # present all along.
        for entry in (bundle.get("construction") or {}).values():
            if not isinstance(entry, dict):
                continue
            for request in entry.get("construction_requests") or []:
                if isinstance(request, dict):
                    request["model"] = "a-model-the-freeze-never-named"
    else:
        record["executed_source"] = FOREIGN_SOURCE
    bundle["use_records"] = [record]
    bundle["operations"] = {PROBE_OPERATION: {
        "effect": "model-inference",
        "receipts": [{"operation_id": PROBE_OPERATION, "outcome": "success",
                      "receipt_identity": "gw:" + PROBE_OPERATION,
                      "text": record["executed_source"]}]}}
    bundle["freeze"]["freeze_digest"] = s09_verify.freeze_digest(
        bundle["freeze"])
    return bundle


def accepted_bundles() -> dict[str, tuple[dict[str, Any], str]]:
    """The honest bundle and each tampering, paired with the complaint each
    is required to draw.

    The needle is part of the contract with the verifier lane. If that lane
    names its refusals differently, this table is the one place to correct,
    and the preflight will refuse the study rather than accept a verifier
    that did not say the word.
    """
    method_digest = digest_of(METHOD_SOURCE)
    record = {"record_id": PROBE_RECORD, "arm": PROBE_ARM,
              "study_arm": PROBE_ARM, "executed": "policy",
              "policy_digest": digest_of(POLICY_SOURCE),
              "executed_source_digest": method_digest,
              "executed_source": METHOD_SOURCE, "model": FROZEN_MODEL,
              "costs": {"witness_queries": 0}, "operation_ids": [PROBE_OPERATION]}
    honest = tampered_bundle("digest-provenance-mismatch")
    honest["use_records"] = [record]
    operations = honest["operations"]
    operations[PROBE_OPERATION]["receipts"][0]["text"] = METHOD_SOURCE
    return {
        "honest": (honest, ""),
        "model-mismatch": (tampered_bundle("model-mismatch"),
                           "request-model-not-frozen"),
        "digest-provenance-mismatch": (
            tampered_bundle("digest-provenance-mismatch"),
            "executed-source-mismatch"),
    }


def verify_problems(bundle: Mapping[str, Any]) -> list[str]:
    """Every reason the verifier names, from either result shape.

    The verifier lane reports a `problems` list of wire strings and a
    structured `findings` list. Reading both means this preflight does not
    have to know which shape the lane settled on, and does not lose the
    finding when a problem string is filtered out downstream.
    """
    from scripts import s09_verify
    result = s09_verify.verify_bundle(bundle)
    named = {str(problem) for problem in result.get("problems", [])}
    for finding in result.get("findings", []) or ():
        named.add(str(finding))
    return sorted(named)


def probe_verifier() -> tuple[VerifierProbe, ...]:
    """Ask the verifier to refuse the two tamperings it must refuse.

    Reading a verifier's names proves nothing about its power, so the
    preflight runs it on a bundle it knows is honest, then on each
    tampering, and asks whether the tampering drew a complaint of its own.
    A verifier that draws none has not yet earned the authority to judge
    this study, so the capability's absence is `unknown` and blocks.
    """
    cases = accepted_bundles()
    try:
        baseline = set(verify_problems(cases["honest"][0]))
    except Exception as exc:
        return tuple(VerifierProbe(
            tampering,
            Unmeasured(Refusal.VERIFIER_UNREADABLE,
                       "verify_bundle on an honest bundle raised %s: %s"
                       % (type(exc).__name__, exc)))
            for tampering in TAMPERINGS)
    probes = []
    for tampering in TAMPERINGS:
        bundle, needle = cases[tampering]
        try:
            added = sorted(set(verify_problems(bundle)) - set(baseline))
        except Exception as exc:
            probes.append(VerifierProbe(
                tampering, Unmeasured(Refusal.VERIFIER_UNREADABLE,
                                      "verify_bundle raised %s: %s" % (
                                          type(exc).__name__, exc))))
            continue
        if not any(needle in complaint for complaint in added):
            probes.append(VerifierProbe(tampering, Unmeasured(
                Refusal.CAPABILITY_MISSING,
                "verify_bundle added %s to a %s bundle, where %s is the "
                "complaint it owes, so it has no authority to judge this "
                "study" % (added, tampering, needle))))
            continue
        probes.append(VerifierProbe(tampering, Pass(Evidence(
            "verify_bundle added %s for a %s bundle" % (added, tampering),
            now()))))
    return tuple(probes)


def _import(subject: str) -> Any | None:
    import importlib
    try:
        return importlib.import_module(subject)
    except Exception:
        return None


def qualification(config: StudyConfig) -> Any:
    """Qualify the apparatus from reviewer-authored policies, before launch.

    These run in their own namespace against the deterministic qualification
    world, never against the study's store. A qualification that read the
    study's own bundle would be judging the experiment by its output.

    They do execute policy source, so they need authority, and the
    authority is their own. The study's own database is the wrong store to
    take here: a launch qualification that wrote into the run it is about
    to launch would be judging the experiment by its output, which is the
    circularity this module exists to remove. So it takes a disposable
    database of its own and an allocation authorized against that.
    """
    from experiments.ad01 import s09_causal_proof
    from experiments.ad01 import s09_instruments as instruments
    from experiments.ad01 import policy_step
    panel = instruments.build_panel(instruments.ORDERING, dev=1, held=2)
    cell = panel.by_split("dev")[0]
    view = policy_step.materialize_view(
        task={"task_id": cell.task_id, "split": cell.split,
              "seed": cell.seed, "instrument": "ordering-constraints-v1"},
        observations=[], open_questions=["which order?"], last_result=None,
        eligible_methods=["schedule.compare", "schedule.commit"],
        remaining={"queries": 8})
    operations = [{"operation_id": "qualification-%s" % cell.task_id,
                   "effect": "probe",
                   "action": {"target": "schedule.compare"}}]
    with _qualification_authority() as authority:
        runs = tuple(
            s09_causal_proof.PolicyRun(
                policy_source=source, view=view,
                operations=("qualification-%s" % cell.task_id,),
                entry=policy_step.STEP_ENTRY,
                dsn=authority["dsn"] if authority else None,
                allocation_id=authority["allocation_id"]
                if authority else None)
            for source in _reviewer_policy_sources())
        return s09_causal_proof.qualify_pre_launch(
            policies=runs, operations=operations)


@contextlib.contextmanager
def _qualification_authority():
    """A disposable store and an allocation, for this qualification alone.

    Created and dropped around the check. It exists so the policies can
    execute under real authority without touching the study's database, and
    it is dropped immediately so nothing it wrote can be mistaken for a
    study record afterwards.
    """
    import uuid

    from experiments.ad01 import s09_run_isolation as isolation
    from settlement import authority as _authority

    token = "preflight-%s" % uuid.uuid4().hex[:8]
    database = isolation.create_disposable_db(token,
                                              admin_dsn=isolation.admin_dsn())
    try:
        handle = _authority.authorize_study(
            database.dsn, isolation.study_root_for(token), authorized=1000,
            allocation_id=token)
    except BaseException:
        isolation.drop_disposable_db(database,
                                     admin_dsn=isolation.admin_dsn())
        raise
    try:
        yield {"dsn": database.dsn, "allocation_id": handle.allocation_id}
    finally:
        isolation.drop_disposable_db(database,
                                     admin_dsn=isolation.admin_dsn())


def _reviewer_policy_sources() -> tuple:
    """Two STEP policies differing only in what they read from the view.

    They exist to show the apparatus admits a decision and records the
    effect. A policy that ignored its view would not distinguish a working
    chain from a constant, so the pair is the point.
    """
    return (
        "def STEP(view, state):\n"
        "    observed = view['observations']\n"
        "    action = {'kind': 'diagnose', 'target': 'schedule.compare',\n"
        "              'inputs': {'left': 'analysis',\n"
        "                         'right': 'build' if observed else 'deploy'},\n"
        "              'evidence_refs': [],\n"
        "              'requested_resources': {'queries': 1}}\n"
        "    return {'action': action, 'state': {'seen': len(observed)}}\n",
        "def STEP(view, state):\n"
        "    observed = view['observations']\n"
        "    action = {'kind': 'diagnose', 'target': 'schedule.compare',\n"
        "              'inputs': {'left': 'deploy',\n"
        "                         'right': 'build' if observed else 'analysis'},\n"
        "              'evidence_refs': [],\n"
        "              'requested_resources': {'queries': 1}}\n"
        "    return {'action': action, 'state': {'seen': len(observed)}}\n",
    )


def launch_governance(qualification: Any) -> Verdict_:
    """Read a pre-launch qualification of the apparatus.

    This used to be `probe_policy_execution`, which read the study's own
    bundle and passed on a nonempty digest list, a nonempty action field and
    two or more distinct digests. None of those is a causal claim: the
    digest and the action were read from different records, so two unrelated
    records could satisfy the pair, and a single valid retained policy
    produces one digest and was scored `unproven`. It also qualified launch
    using the output of the run being launched, which is circular.

    The qualification now comes from `s09_causal_proof.qualify_pre_launch`,
    which executes reviewer-authored policies through the same out-of-process
    boundary the study uses and marks every link unpersisted. The post-effect
    join is a separate call over a separate export.
    """
    proved = bool(getattr(qualification, "proved", False))
    detail = getattr(qualification, "detail", None) or (
        "%d reviewer-authored policies had their decisions admitted"
        % len(getattr(qualification, "chains", ())))
    if proved:
        return Pass(Evidence(detail, now()))
    return Unmeasured(Refusal.POLICY_GOVERNANCE_UNPROVEN, detail)


def post_effect_governance(export: Mapping[str, Any]) -> Verdict_:
    """Join a completed run's policy decisions to the operations they caused.

    Seven links per use record, every one recomputed from bytes. This is not
    the launch check with a flag flipped: it runs after effects exist, and a
    record that cannot produce its decision, its operation and its receipt is
    `unproven` rather than passed on a digest that moved.
    """
    from experiments.ad01 import s09_causal_proof
    verdict = s09_causal_proof.join_post_effect(export)
    if verdict.proved:
        return Pass(Evidence(verdict.detail or
                             "the chain walked for %d records"
                             % len(verdict.chains), now()))
    reasons = ", ".join(verdict.reasons) or verdict.detail
    return Unmeasured(Refusal.POLICY_GOVERNANCE_UNPROVEN, reasons)


def load_exposure_ledger() -> ExposureLedger | None:
    """Read the carried exposure off the real ledger, or nothing at all.

    The arithmetic belongs to `s09_exposure_ledger`, which reconciles the
    units against the artifacts and refuses to invent a ceiling from
    unresolved inputs. This only reports what the ledger already settled,
    so a preflight cannot re-derive a friendlier total.
    """
    module = _import(EXPOSURE_MODULE)
    reader = getattr(module, "prior_exposure", None) if module else None
    total_of = getattr(module, "conservative_total", None) if module else None
    if not callable(reader) or not callable(total_of):
        return None
    try:
        total = total_of(reader())
    except Exception:
        return None
    terms = getattr(total, "terms", None)
    if not terms:
        return None
    return ExposureLedger(
        study_id="prior-exposure",
        source="%s conservative total" % EXPOSURE_MODULE,
        carried_units=int(getattr(total, "value", 0)),
        all_verified=bool(getattr(total, "all_verified", False)),
        arithmetic=str(getattr(total, "arithmetic", "")),
        terms=tuple(ExposureTerm(label=str(label),
                                 units=int(units.value),
                                 evidence=str(units.evidence.value))
                    for label, units in terms))


def already_spent_in_store(
        database: DatabaseObservation | None) -> int | None:
    """Sends the study's store already holds, or None if it was never read.

    This was `reported_spend`, and it read `S09_STUDY_CALLS_ALREADY_SPENT` from
    the environment. Nothing in the repository writes that name:
    `invl02_live._load_live_env` copies four gateway and grant variables out of
    the environment file and this was not one of them. So the number was
    hand-authored from a cap sheet and never moved as sends happened, and a
    resume after a crash read what it read before the first send. The ceiling
    was then enforced against a fiction. `invl02_live._output_already_spent`
    had already moved its own derivation to `SELECT COUNT(*) FROM operations`,
    which is the same unit: a send that reached the store.

    The store is not a foreign dependency here. `collect` opens it for
    `observe_database` before this runs, and that read already counts every
    operation row, so deriving the number costs a subtraction. A store that
    was never read yields None rather than zero, because a zero here reads as
    "nothing spent" and re-opens the same hole for every database that is
    briefly unreachable.
    """
    if database is None or not database.readable:
        return None
    return database.operations_in_namespace


def study_ceiling() -> int | None:
    """The dispatch count this study's freeze authorizes, or None.

    This is a count of sends and nothing else. It used to be a unit ceiling
    derived by multiplying a dispatch limit by a per-dispatch cost that a
    null provider charge had been folded into, and reservation units from two
    prior campaigns were then subtracted from the result and called
    dispatches. Three currencies, one subtraction. The dispatch count is
    authorized by the freeze; the unit allowance is authorized by the cap
    sheet; neither is derived from the other.
    """
    module = _import(EXPOSURE_MODULE)
    capacity = getattr(module, "route_capacity_from_freeze", None) \
        if module else None
    if not callable(capacity):
        return None
    try:
        allowance = getattr(capacity(), "max_dispatches", None)
    except Exception:
        return None
    return None if allowance is None else int(allowance)


def collect(config: StudyConfig) -> Observations:
    route: GatewayConfig | None = None
    probe: RouteProbe | None = None
    freeze: StudyFreeze | None = None
    database: DatabaseObservation | None = None
    governance: Verdict_ | None = None
    try:
        route, key = gateway_config(config.config_path)
        probe = probe_route(route, key)
    except (Unknown, Refused):
        route, probe = None, None
    try:
        freeze = read_study_freeze(config.bundle, config.frozen_at)
        if config.model and config.model != freeze.model:
            raise Unknown(Refusal.MODEL_MISMATCH,
                          "requested model %r differs from the frozen %r" % (
                              config.model, freeze.model))
        database = observe_database(study_database(config.dsn), freeze)
        governance = launch_governance(qualification(config))
    except (Unknown, Refused, OSError, ValueError):
        database = None
    return Observations(freeze=freeze, database=database, route=route,
                        route_probe=probe, verifier=probe_verifier(),
                        governance=governance,
                        exposure=load_exposure_ledger(),
                        ceiling=study_ceiling(),
                        already_spent=already_spent_in_store(database))


def evaluate(observations: Observations, *,
             requested_model: str = "") -> PreflightResult:
    return Preconditions(observations, requested_model=requested_model).judge()


class Preconditions:
    """The only constructor of a `PreflightResult`.

    A caller cannot fabricate a startable result. This class reads the five
    preconditions out of what was observed and hands each one its status;
    an observation that was never captured becomes an `unknown`.
    """

    ORDER = (Precondition.ROUTE_LIVENESS, Precondition.STUDY_DATABASE,
             Precondition.VERIFIER_AUTHORITY, Precondition.POLICY_GOVERNANCE,
             Precondition.EXPOSURE_BUDGET)

    def __init__(self, observations: Observations, *,
                 requested_model: str = "") -> None:
        self.observations = observations
        self.requested_model = requested_model

    def judge(self) -> PreflightResult:
        judges: Mapping[Precondition, Callable[[], Outcome]] = {
            Precondition.ROUTE_LIVENESS: self._route,
            Precondition.STUDY_DATABASE: self._database,
            Precondition.VERIFIER_AUTHORITY: self._verifier,
            Precondition.POLICY_GOVERNANCE: self._governance,
            Precondition.EXPOSURE_BUDGET: self._budget,
        }
        return PreflightResult(tuple(judges[name]() for name in self.ORDER),
                               judged_at=now(), _authority=_JUDGE_AUTHORITY)

    def _route(self) -> Outcome:
        name = Precondition.ROUTE_LIVENESS
        seen = self.observations
        if seen.route is None:
            return Outcome(name, Unmeasured(Refusal.NO_GATEWAY_ENDPOINT,
                                         "no %s is configured" % ENDPOINT_VAR))
        if seen.route_probe is None:
            return Outcome(name, Unmeasured(Refusal.NO_ROUTE_PROBE,
                                         "%s is configured with key sha256=%s"
                                         " but its liveness was never probed"
                                         % (seen.route.endpoint,
                                            seen.route.key_digest)))
        return Outcome(name, seen.route_probe.verdict, seen.route_probe.detail)

    def _database(self) -> Outcome:
        name = Precondition.STUDY_DATABASE
        seen = self.observations
        freeze = seen.freeze
        if freeze is None:
            return Outcome(name, Unmeasured(
                Refusal.MISSING_FREEZE,
                "the study database was never compared against a freeze"))
        if seen.database is None:
            return Outcome(name, Unmeasured(Refusal.NO_OBSERVATION,
                                         "%s was never read" % freeze.study_root))
        seen_database = seen.database
        if not seen_database.readable:
            return Outcome(name, Unmeasured(Refusal.UNREADABLE_DATABASE,
                                         seen_database.refused))
        if not is_disposable(seen_database.name):
            return Outcome(name, Fail(Refusal.NOT_DISPOSABLE, Evidence(
                "database %s is not a disposable %s name" % (
                    seen_database.name,
                    " or ".join(DISPOSABLE_PREFIXES)), now())),
                detail=seen_database.name)
        if seen_database.foreign:
            first = seen_database.foreign[0]
            return Outcome(name, Fail(Refusal.CROSS_STUDY_OPERATIONS, Evidence(
                "%d operations in %s belong to another study, first %s "
                "carrying study_root %r" % (len(seen_database.foreign),
                                             seen_database.name,
                                             first.operation_id,
                                             first.study_root), now())),
                detail="%s study_root=%s" % (first.operation_id,
                                             first.study_root))
        if seen_database.drift:
            first = seen_database.drift[0]
            return Outcome(name, Fail(Refusal.MODEL_MISMATCH, Evidence(
                "%d operations in %s record a model the freeze does not "
                "name, first %s recorded %r against frozen %r" % (
                    len(seen_database.drift), seen_database.name,
                    first.operation_id, first.observed_model,
                    first.frozen_model), now())),
                detail="%s observed=%s frozen=%s" % (
                    first.operation_id, first.observed_model,
                    first.frozen_model))
        if seen_database.age is NamespaceAge.UNMEASURABLE:
            return Outcome(name, Unmeasured(
                Refusal.NAMESPACE_AGE_UNMEASURABLE,
                "the freeze names no moment, so nothing can be shown not to "
                "predate it"))
        if seen_database.prefreeze_operations:
            return Outcome(name, Fail(Refusal.NAMESPACE_PREDATES_FREEZE,
                                      Evidence(
                "%d operations in %s were written before the freeze at %s" % (
                    seen_database.prefreeze_operations, seen_database.name,
                    freeze.frozen_at), now())),
                detail=freeze.frozen_at)
        return Outcome(name, Pass(Evidence(
            "postgresql:///%s holds %d operations, every one bound to "
            "study_root %s with model %r, none older than %s" % (
                seen_database.name, seen_database.operations_in_namespace,
                freeze.study_root, freeze.model, freeze.frozen_at), now())))

    def _verifier(self) -> Outcome:
        name = Precondition.VERIFIER_AUTHORITY
        probes = self.observations.verifier
        if not probes:
            return Outcome(name, Unmeasured(
                Refusal.NO_CLAIM_PROBE,
                "scripts/s09_verify.py was never probed for refusal power"))
        blocking = next((probe for probe in probes if probe.verdict.blocks),
                        None)
        if blocking is not None:
            return Outcome(name, blocking.verdict, blocking.tampering)
        return Outcome(name, Pass(Evidence("; ".join(
            "%s: %s" % (probe.tampering, probe.verdict.evidence)
            for probe in probes), now())))

    def _governance(self) -> Outcome:
        name = Precondition.POLICY_GOVERNANCE
        verdict = self.observations.governance
        if verdict is None:
            return Outcome(name, Unmeasured(
                Refusal.POLICY_GOVERNANCE_UNPROVEN,
                "the bundle's use records were never read, so nothing shows "
                "the bound policy governed them"))
        return Outcome(name, verdict)

    def _budget(self) -> Outcome:
        name = Precondition.EXPOSURE_BUDGET
        seen = self.observations
        if seen.exposure is None:
            return Outcome(name, Unmeasured(
                Refusal.NO_EXPOSURE_LEDGER,
                "%s is absent, so no exposure can be reconciled and no "
                "ceiling derived" % EXPOSURE_MODULE))
        if seen.ceiling is None or seen.already_spent is None:
            missing = ", ".join(
                name for name, value in (("a unit ceiling", seen.ceiling),
                                         ("an already-spent count",
                                          seen.already_spent))
                if value is None)
            return Outcome(name, Unmeasured(
                Refusal.BUDGET_UNRESOLVED,
                "study %s names %s, and a count of model calls is not a unit "
                "ceiling, so no authorized ceiling is in evidence" % (
                    seen.exposure.study_id, missing)))
        exposure = seen.exposure
        if not exposure.reconciled:
            carried = ", ".join("%s %d units is %s" % (
                term.label, term.units, term.evidence)
                for term in exposure.carried_forward)
            return Outcome(name, Unmeasured(
                Refusal.EXPOSURE_UNRECONCILED,
                "%s carries exposure no artifact verifies (%s), so a ceiling "
                "read off it would be invented" % (exposure.source, carried)),
                detail=canonical(exposure.as_dict()))
        budget = Budget(already_spent=seen.already_spent, ceiling=seen.ceiling)
        if budget.remaining < 0:
            return Outcome(name, Fail(Refusal.BUDGET_UNRESOLVED, Evidence(
                "ceiling of %d dispatches less %d already spent leaves %d, so "
                "this freeze is over its own send limit" % (
                    budget.ceiling, budget.already_spent, budget.remaining),
                now())), detail=canonical(budget.as_dict()))
        return Outcome(name, Pass(Evidence(
            "ceiling of %d dispatches less %d already spent leaves %d "
            "dispatches for study %s; the %d held reservation units under %s "
            "are a separate currency and are not charged against sends" % (
                budget.ceiling, budget.already_spent, budget.remaining,
                seen.exposure.study_id, exposure.carried_units,
                seen.exposure.source),
            now())), detail=canonical(budget.as_dict()))


def parse_cli(argv: Sequence[str]) -> StudyConfig:
    parser = argparse.ArgumentParser(
        prog="python3 -m experiments.ad01.s09_study_preflight",
        description="Refuse to start a live study whose preconditions are "
                    "unproven.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--frozen-at", default="",
                        help="ISO moment the freeze was taken, which is what "
                             "makes 'nothing predates it' checkable")
    parser.add_argument("--config", default="")
    args = parser.parse_args(list(argv))
    if not os.environ.get(LIVE_GRANT_ENV):
        parser.error("a live study needs a fresh human grant in %s"
                     % LIVE_GRANT_ENV)
    return StudyConfig(dsn=args.dsn, bundle=args.bundle, model=args.model,
                       frozen_at=args.frozen_at, config_path=args.config)


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_cli(sys.argv[1:] if argv is None else argv)
    try:
        result = evaluate(collect(config), requested_model=config.model)
    except Refused as exc:
        print(canonical({"may_start": False, "refusals": [exc.detail]}))
        return 3
    print(json.dumps(result.as_dict(), sort_keys=True, indent=1))
    return 0 if result.may_start else 1


if __name__ == "__main__":
    raise SystemExit(main())
