"""AD01 repertoire selection: binding-aware over capability_releases.

Binding-aware selection only: a caller passes an explicit release id and
the store resolves that release's active eligible binding. No release
means no binding, and the caller falls back to the explicit incumbent.
The retired global-newest scan and the first-family-match fallback could
let an unrelated release decide a use. The release `fallback` substitution
is retired for the same reason: every disposition that reaches selection is
a promoting one, so substituting a fallback member could only ever execute
unassessed bytes while the use record still named the requested capability.
Absent pinned bytes now refuse, and `trajectory._use_refusal` reports why. A promoting bind (limited or
default) additionally requires a qualifying current assessment for the
exact frozen bytes, protocol, evaluator and scope; the release row pins
that provenance so fresh-process use resolves identical bytes.

Below the binding resolution sits the E3 investigation portfolio. That
layer is a different question and keeps its own model below: a finite
resource allocation, a portfolio of permitted investigations, a policy
that picks among them, and four yield measures read off recorded
operations. `run_investigations` is the only driver; nothing here decides
an investigation on the caller's behalf.
"""

from __future__ import annotations

import hashlib
import json

ELIGIBLE_DISPOSITIONS = ("default", "limited")

PROMOTING = ("limited", "default")

WORLDS = (0, 1, 2)
FAMILIES = ("software", "graph")
METHODS = ("ddmin", "greedy")

_CAPABILITY_PREFIX = {"software": "seed-sw-", "graph": "seed-gr-"}


def capability_for(family: str, method: str) -> str:
    return _CAPABILITY_PREFIX[family] + method


class StaleBind(Exception):
    pass


def _read_conn(dsn: str):
    from psycopg.rows import dict_row
    from settlement import db
    return db.connect(dsn, row_factory=dict_row)


def active_binding_for(dsn: str, family: str,
                       release_id: str | None = None) -> dict | None:
    if release_id is None:
        return None
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT * FROM capability_releases WHERE id = %s",
            (release_id,)).fetchone()
        conn.commit()
        rows = [row] if row is not None else []
    eligible = []
    for row in rows:
        if row is None:
            continue
        record = dict(row)
        scope = dict(record.get("scope") or {})
        if family and scope.get("family", family) != family:
            continue
        if record.get("disposition") not in ELIGIBLE_DISPOSITIONS:
            continue
        eligible.append(record)
    if not eligible:
        return None
    return eligible[-1]


def binding_provenance(binding: dict) -> dict:
    return dict((binding or {}).get("invalidation") or {})


def bind_revision(dsn: str, *, release_id: str, versions: list,
                  scope: dict, disposition: str, fallback: str = "",
                  expected_versions: list | None,
                  policy_version: str = "",
                  protocol_id: str = "",
                  evaluator_version: str = "",
                  evidence_refs: list | None = None,
                  proposal_id: str = "",
                  candidate_digest: str = "",
                  request_id: str | None = None) -> dict:
    from psycopg.types.json import Json
    from settlement import store
    from settlement.common import Command, ResultCode
    if not release_id or not versions:
        raise ValueError("bind needs a release id and exact versions")
    if disposition not in ("candidate", "experimental", "limited",
                           "default", "quarantined", "retired"):
        raise ValueError("unknown disposition %r" % (disposition,))
    if not protocol_id:
        raise ValueError("bind needs a protocol id for release %r"
                         % (release_id,))
    if not evaluator_version:
        raise ValueError("bind needs an evaluator version for release %r"
                         % (release_id,))
    refs = [ref for ref in (evidence_refs or [])
            if isinstance(ref, str) and ref]
    if not refs:
        raise ValueError("bind needs non-empty evidence references"
                         " for release %r" % (release_id,))
    if not proposal_id or not candidate_digest:
        raise ValueError("bind pins exact frozen bytes for release %r:"
                         " proposal and candidate digest required"
                         % (release_id,))
    from . import records as _records
    proposal = _records.load_revision_proposal(dsn, proposal_id)
    if proposal is None:
        raise ValueError("no revision proposal %r for release %r"
                         % (proposal_id, release_id))
    freeze = _records.load_freeze(dsn, proposal_id)
    if freeze is None or not freeze.get("candidate_digest"):
        raise ValueError("no frozen candidate for proposal %r"
                         " (release %r)" % (proposal_id, release_id))
    if freeze["candidate_digest"] != candidate_digest:
        raise ValueError("bind bytes %r mismatch frozen bytes %r"
                         " (proposal %r)"
                         % (candidate_digest,
                            freeze["candidate_digest"], proposal_id))
    if proposal.get("protocol_id") != protocol_id:
        raise ValueError("bind protocol %r mismatches proposal protocol %r"
                         % (protocol_id, proposal.get("protocol_id")))
    assessment = _records.load_assessment(
        dsn, proposal_id, candidate_digest)
    if assessment is None:
        raise ValueError("absent assessment for proposal %r bytes %r"
                         " (release %r): assess frozen bytes before binding"
                         % (proposal_id, candidate_digest, release_id))
    if assessment.get("attempt_id") not in refs:
        raise ValueError("bind evidence must cite assessment %r"
                         " for release %r"
                         % (assessment.get("attempt_id"), release_id))
    if assessment.get("protocol_id") != protocol_id:
        raise ValueError("bind protocol %r mismatches assessment"
                         " protocol %r (release %r)"
                         % (protocol_id, assessment.get("protocol_id"),
                            release_id))
    if assessment.get("evaluator_version") != evaluator_version:
        raise ValueError("bind evaluator %r mismatches assessment"
                         " evaluator %r (release %r)"
                         % (evaluator_version,
                            assessment.get("evaluator_version"),
                            release_id))
    if dict(assessment.get("scope") or {}) != dict(scope or {}):
        raise ValueError("bind scope %r mismatches assessed scope %r"
                         " (release %r)"
                         % (scope, assessment.get("scope"), release_id))
    if disposition in PROMOTING and assessment.get("outcome") != "bind":
        raise ValueError("assessment %r forbids promotion: %s"
                         % (assessment.get("attempt_id"),
                            assessment.get("reason",
                                           assessment.get("outcome"))))
    from settlement.common import payload_digest
    request_payload = {"release": release_id, "versions": list(versions),
                       "scope": dict(scope), "disposition": disposition,
                       "fallback": fallback, "policy_version": policy_version,
                       "protocol_id": protocol_id,
                       "evaluator_version": evaluator_version,
                       "evidence_refs": refs, "proposal_id": proposal_id,
                       "candidate_digest": candidate_digest}
    canonical_request_id = "s09-bind-%s-%s" % (
        release_id, payload_digest(request_payload)[:12])
    if request_id is not None and request_id != canonical_request_id:
        raise ValueError("bind request id must be canonical")
    request_id = canonical_request_id
    provenance = {"proposal_id": proposal_id,
                  "candidate_digest": candidate_digest}

    def _fn(cur, control):
        cur.execute("SELECT * FROM capability_releases WHERE id = %s"
                    " FOR UPDATE", (release_id,))
        current = cur.fetchone()
        if current is None:
            if expected_versions not in (None, []):
                raise StaleBind(
                    "no binding for %r, expected %r" % (
                        release_id, expected_versions))
            cur.execute(
                "INSERT INTO capability_releases"
                " (id, protocol_id, versions, scope, disposition,"
                " fallback, policy_version, invalidation,"
                " evidence_refs, evaluator_version)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (release_id, protocol_id, Json(list(versions)),
                 Json(dict(scope)), disposition, fallback,
                 policy_version, Json(provenance), Json(refs),
                 evaluator_version))
            return (ResultCode.APPLIED, "bound %s" % release_id,
                    {"release_id": release_id,
                     "versions": list(versions)}, [], [])
        have = list(dict(current).get("versions") or [])
        if expected_versions != have:
            raise StaleBind(
                "stale bind for %r: expected %r, have %r" % (
                    release_id, expected_versions, have))
        cur.execute(
            "UPDATE capability_releases SET protocol_id = %s,"
            " versions = %s, scope = %s, disposition = %s,"
            " fallback = %s, policy_version = %s,"
            " invalidation = %s, evidence_refs = %s,"
            " evaluator_version = %s"
            " WHERE id = %s",
            (protocol_id, Json(list(versions)), Json(dict(scope)),
             disposition, fallback, policy_version,
             Json(provenance), Json(refs),
             evaluator_version, release_id))
        return (ResultCode.APPLIED, "rebound %s" % release_id,
                {"release_id": release_id,
                 "versions": list(versions)}, [], [])

    result = store.transact(dsn, Command(request_id=request_id,
                                         payload={"release_id": release_id,
                                                  "versions": list(versions),
                                                  "scope": dict(scope),
                                                  "disposition": disposition}),
                            _fn)
    if result.code not in (ResultCode.APPLIED,
                           ResultCode.ALREADY_APPLIED):
        raise StaleBind(result.detail or "bind refused")
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT * FROM capability_releases WHERE id = %s",
            (release_id,)).fetchone()
        conn.commit()
        return dict(row) if row is not None else {}


def _bound_member(members: list, versions: list,
                  candidate_digest: str = "") -> dict | None:
    wanted = set(versions or [])
    for member in members:
        if member.get("capability_id") not in wanted:
            continue
        source = member.get("method_source")
        if not candidate_digest or not isinstance(source, str):
            continue
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if member.get("source_digest") != candidate_digest or digest != candidate_digest:
            continue
        return member
    return None


def select_member(repertoire: dict, task: dict,
                  dsn: str | None = None,
                  release_id: str | None = None) -> dict | None:
    members = list(repertoire.get("members", []))
    family = task.get("family", "")
    if release_id is None:
        for member in members:
            if member.get("scope", {}).get("family") == family:
                return member
        return None
    binding = None
    if dsn is not None:
        binding = active_binding_for(dsn, family,
                                     release_id=release_id)
    elif isinstance(repertoire.get("active_binding"), dict):
        candidate = dict(repertoire["active_binding"])
        if candidate.get("disposition") in ELIGIBLE_DISPOSITIONS:
            scope = dict(candidate.get("scope") or {})
            if not family or scope.get("family", family) == family:
                binding = candidate
    if binding is None:
        return None
    chosen = _bound_member(members, list(binding.get("versions") or []),
                           str(binding_provenance(binding).get(
                               "candidate_digest") or ""))
    if chosen is not None:
        return chosen
    return None


def versioned_use_op_id(campaign_id: str, task_id: str,
                        method_version: str) -> str:
    return "ad01-%s-use-%s-%s" % (campaign_id, task_id, method_version)


YIELD_MEASURES = {
    "retained_behaviors": "development episodes the checker returned "
                          "preserved for and the runner kept executable",
    "held_out_reduction": "mean normalized size reduction each retained "
                          "behavior achieves on the world's transfer tasks",
    "diagnoses_correct": "diagnostic claims whose predicted disposition the "
                         "development episode then confirmed",
    "resources_used": "allocation units charged for admitted operations",
}


def yield_measure_digest() -> str:
    raw = json.dumps(YIELD_MEASURES, sort_keys=True,
                     separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


FROZEN_MEASURE_DIGEST = \
    "ce5a140aff83bccc55a916958fdbaf568cb7c576d5c6a66361510181c83cf7e8"


class MeasureDrift(Exception):
    pass


def assert_measure_freeze(digest: str = FROZEN_MEASURE_DIGEST) -> str:
    """Refuse to score a run against redefined measures.

    The comparison is against a pinned literal, never against a freshly
    computed value, so redefining a measure after outcomes are visible
    cannot silently keep the old digest.
    """
    current = yield_measure_digest()
    if current != digest or current != FROZEN_MEASURE_DIGEST:
        raise MeasureDrift(
            "yield measures were redefined after outcomes were visible: "
            "frozen %s, current %s" % (digest, current))
    return current


class BudgetExhausted(Exception):
    pass


class Allocation:
    """A finite envelope. A charge that would exceed it is refused.

    A refused charge leaves the spend untouched, so an exhausted envelope
    stops the run rather than quietly under-spending.
    """

    def __init__(self, authorized: int):
        if not isinstance(authorized, int) or authorized < 0:
            raise ValueError("an allocation needs a nonnegative integer")
        self.authorized = authorized
        self.spent = 0

    def remaining(self) -> int:
        return self.authorized - self.spent

    def affords(self, cost: int) -> bool:
        return cost <= self.remaining()

    def charge(self, cost: int) -> int:
        if not isinstance(cost, int) or cost <= 0:
            raise ValueError("an operation must cost a positive integer")
        if cost > self.remaining():
            raise BudgetExhausted(
                "charge of %d exceeds the %d units remaining"
                % (cost, self.remaining()))
        self.spent += cost
        return self.spent


class Candidate:
    """One permitted investigation, before it is charged or run."""

    __slots__ = ("target", "family", "capability_id", "max_queries",
                 "diagnose_queries", "seq")

    def __init__(self, target, family, capability_id="", max_queries=0,
                 diagnose_queries=0, seq=0):
        self.target = target
        self.family = family
        self.capability_id = capability_id
        self.max_queries = max_queries
        self.diagnose_queries = int(diagnose_queries)
        self.seq = int(seq)

    @property
    def identity(self):
        return (self.target, self.capability_id, self.max_queries,
                self.diagnose_queries)

    def cost(self) -> int:
        """What the run charges, whether or not the operation succeeds.

        Development costs the diagnostic that must run first plus the
        queries the reduction was allowed. Deriving cost from the request
        rather than the outcome keeps a failed operation from looking free,
        which is what lets the envelope actually bind.
        """
        return 1 + int(self.diagnose_queries) + int(self.max_queries)

    def as_dict(self) -> dict:
        return {"target": self.target, "family": self.family,
                "capability_id": self.capability_id,
                "max_queries": self.max_queries,
                "diagnose_queries": self.diagnose_queries,
                "cost": self.cost()}


def portfolio_for_world(world: int) -> tuple:
    """Every development target a qualified world makes available.

    The portfolio is data the coordinator supplies: which worlds count,
    which tasks are development targets, and which capabilities may be run
    against them. No ordering, no priority, no next action.
    """
    from . import worlds
    if world not in WORLDS:
        raise ValueError("world %r is not qualified" % (world,))
    membership = worlds.world_membership(worlds.FROZEN_DIR)[str(world)]
    return tuple(membership["dev"][family] for family in FAMILIES)


def dev_targets(world: int) -> dict:
    return dict(zip(FAMILIES, portfolio_for_world(world)))


def transfer_targets(world: int) -> dict:
    from . import worlds
    membership = worlds.world_membership(worlds.FROZEN_DIR)[str(world)]
    return {family: list(membership["transfer"][family])
            for family in FAMILIES}


class Choice:
    """One admitted decision, what it cost, and why it was made.

    `charge` is what this decision alone cost, not the running total.
    """

    __slots__ = ("candidate", "charge", "rationale")

    def __init__(self, candidate, charge, rationale):
        self.candidate = candidate
        self.charge = charge
        self.rationale = rationale


class Execution:
    """A charged decision and the real operation the decision reached."""

    __slots__ = ("choice", "episode", "cost", "observation", "claim",
                 "observed", "correct")

    def __init__(self, choice, episode, cost, observation, claim=None,
                 observed=None, correct=None):
        self.choice = choice
        self.episode = episode
        self.cost = cost
        self.observation = observation
        self.claim = claim
        self.observed = observed
        self.correct = correct


class Yield:
    """The four frozen measures, each read off recorded operations.

    Three are counts and one is a rate, so the constructor checks them as
    what they are rather than as one loosely typed bag.
    """

    __slots__ = ("retained_behaviors", "held_out_reduction",
                 "diagnoses_correct", "resources_used")

    COUNTS = ("retained_behaviors", "diagnoses_correct", "resources_used")

    def __init__(self, retained_behaviors, held_out_reduction,
                 diagnoses_correct, resources_used):
        for name in self.COUNTS:
            value = locals()[name]
            if not isinstance(value, int) or isinstance(value, bool) \
                    or value < 0:
                raise ValueError(
                    "%s must be a nonnegative integer, got %r"
                    % (name, value))
        if not isinstance(held_out_reduction, (int, float)) \
                or isinstance(held_out_reduction, bool) \
                or not 0.0 <= float(held_out_reduction) <= 1.0:
            raise ValueError(
                "held_out_reduction must be a rate in [0, 1], got %r"
                % (held_out_reduction,))
        self.retained_behaviors = retained_behaviors
        self.held_out_reduction = float(held_out_reduction)
        self.diagnoses_correct = diagnoses_correct
        self.resources_used = resources_used

    def as_dict(self) -> dict:
        return {name: getattr(self, name) for name in sorted(YIELD_MEASURES)}


class InvestigationRun:
    def __init__(self, *, world, policy_version, choices, executions,
                 yield_, held_out_ledger, stop_reason, measure_digest,
                 recorder=None, allocation=None):
        self.world = world
        self.policy_version = policy_version
        self.choices = tuple(choices)
        self.executions = tuple(executions)
        self.yield_ = yield_
        self.held_out_ledger = tuple(held_out_ledger)
        self.stop_reason = stop_reason
        self.measure_digest = measure_digest
        self.recorder = recorder
        self.allocation = allocation

    @property
    def envelope(self) -> int:
        """The ceiling this run charged against, before it stopped.

        The ceiling and not `resources_used`, because a run that stops
        early has authority it never drew on, and the recorder's child
        allocation is sized against what the run could have spent.
        """
        return int(self.allocation.authorized) if self.allocation else 0

    @property
    def operations(self) -> tuple:
        """The operations this run's decisions reached, with receipts.

        Empty for a run given no store. Each record is what the
        recorder read back out of the receipts table, not what the
        admission call was handed.
        """
        return tuple(self.recorder.records) if self.recorder else ()

    @property
    def refusals(self) -> tuple:
        return tuple(self.recorder.refusals) if self.recorder else ()

    @property
    def adoption(self) -> dict:
        return self.recorder.adoption() if self.recorder else {
            "study_root": "", "adopted": False, "visible": 0, "total": 0}

    @property
    def adopted_operations(self) -> int:
        """Operations a study-scoped read of the store can find."""
        return int(self.adoption["visible"])

    @property
    def orphaned_operations(self) -> int:
        """Operations this run really made that no study can find.

        Zero for a run with no store, and zero for a run adopted under
        a study. A non-zero figure is a real gap between what the run
        did and what the study's own instrumentation measured.
        """
        return int(self.adoption["total"]) - self.adopted_operations


class Agenda:
    """The decision surface a policy reads and a run replays.

    A policy proposes the next investigation from the state it is shown.
    The run charges it, admits it through the shared gate, and executes
    whatever was admitted against the real checker. A proposal that names
    a target the portfolio does not offer is refused rather than silently
    redirected, so a policy cannot widen the portfolio by wishing.

    Every offered candidate is a development against a target, a
    capability and a depth, and every candidate's price already contains
    the diagnostic that must run before its reduction.
    """

    def __init__(self, world, policy, allocation, *, sever=False,
                 diagnose_queries=4, depths=(2, 3, 4, 5, 6, 7)):
        self.world = world
        self.policy = policy
        self.allocation = allocation
        self.sever = sever
        self.diagnose_queries = int(diagnose_queries)
        self.depths = self._ladder(depths)
        self.offered = self._offered()
        self.state = {"episodes": [], "ran": set()}

    @staticmethod
    def _ladder(depths):
        """The one ladder both policies walk.

        Depth is the number of oracle queries a reduction may spend. The
        ladder starts at 1 because a reduction that may ask nothing is a
        fixed point rather than an investigation. Both policies draw from
        this single sequence, so neither can reach a depth the other
        cannot and the comparison stays on one scale.
        """
        ladder = (1,) + tuple(int(d) for d in depths if int(d) != 1)
        return tuple(sorted(set(ladder)))

    def _offered(self) -> tuple:
        """Every (target, capability, depth) the ladder allows."""
        targets = dev_targets(self.world)
        rows = []
        for family in FAMILIES:
            for method in METHODS:
                for task in targets[family]:
                    for depth in self.depths:
                        rows.append(Candidate(
                            task, family, capability_for(family, method),
                            depth, self.diagnose_queries))
        return tuple(rows)

    def cheapest(self, family, method, depth):
        """The offered candidate of that shape, or None if there is none.

        Every dev target in a family yields the same cost for the same
        depth, so the first offered row of a shape stands for all of them
        and the policy is free to name any target in the portfolio.
        """
        for row in self.offered:
            if row.family == family and row.max_queries == depth \
                    and row.capability_id.endswith(method):
                return row
        return None

    def untried(self, family, method, depth):
        """The same shape, on a target this (family, capability) has not run.

        A policy that re-runs the identical operation is not investigating;
        it is spending the envelope to look busy. Re-targeting is how a
        policy gets a genuinely different investigation at the same depth.
        """
        for row in self.offered:
            if row.family == family and row.max_queries == depth \
                    and row.capability_id.endswith(method) \
                    and row.target not in self.state["ran"]:
                return row
        return None

    def note_ran(self, target) -> None:
        self.state["ran"].add(target)

    def afford(self, candidate) -> bool:
        return self.allocation.affords(candidate.cost())

    def observed(self, family, method):
        for row in self.state["episodes"]:
            if (row["family"], row["method"]) == (family, method):
                return row
        return None

    def advance(self, family, method, episode, cost, depth):
        self.state["episodes"].append(
            {"family": family, "method": method,
             "disposition": episode.get("disposition"), "cost": cost,
             "depth": depth,
             "initial": episode.get("initial_size"),
             "final": episode.get("final_size")})


def _claim_from(observation, family):
    """Read a falsifiable claim out of the diagnostic that already ran.

    The claim is a prediction about the development episode that followed
    it. `chain-necessary` says the reduction survives keeping the chain,
    so the episode must be retained. `chain-filler` says the chain
    carries the task, so the reduction should fail without it. The graph
    control names an ordering, and the episode confirms it only when that
    ordering is the one that is retained.

    Reading the claim from the operation that produced it means the
    diagnostic is run once per charged candidate, which is what the
    candidate's price says.
    """
    if observation is None:
        return None, {}
    detail = observation.get("detail") or {}
    report = detail.get("detail") or detail
    if family == "software":
        return ("chain-necessary"
                if report.get("diagnostic_verdict") == "preserved"
                else "chain-filler"), report
    return report.get("winner"), report


def _diagnostic_holds(claim, episode, method=""):
    """Whether the development episode confirmed the diagnostic's claim.

    Every claim is a prediction about the episode that followed it, and
    each has one falsifiable consequence:

    `chain-necessary` says the reduction survives keeping the chain, so
    the episode must be retained. `chain-filler` says the chain carries
    the task, so the reduction must fail without it. The graph control
    names an ordering; the episode confirms it only when the named
    ordering is the one that is retained.
    """
    disposition = episode.get("disposition")
    if claim == "chain-necessary":
        return disposition == "retained"
    if claim == "chain-filler":
        return disposition == "rejected"
    if claim in ("seed", "novel", "tie"):
        if disposition == "retained":
            return (claim == "seed") == method.endswith("greedy")
        if disposition in ("no-candidate", "rejected"):
            return (claim == "seed") != method.endswith("greedy")
        return None
    return None


def _held_out_row(world, family, executable, max_queries):
    """Run one retained behavior over the world's held-out transfer tasks."""
    from . import trajectory, worlds
    rows = []
    for target in transfer_targets(world)[family]:
        task = worlds.load_task(worlds.FROZEN_DIR, target)
        result = trajectory._run_member(executable, task,
                                        max_queries=max_queries)
        report = trajectory._check(task, result["candidate"])
        initial, final = trajectory._size(task, result["candidate"])
        rows.append({
            "target": target,
            "family": family,
            "verdict": report["verdict"],
            "initial": initial,
            "final": final,
            "reduction": ((initial - final) / initial
                          if report["verdict"] == "preserved" and initial
                          else 0.0),
            "queries": int(result.get("queries", 0)),
        })
    return rows


def _default_campaign(world: int) -> str:
    """A campaign name unique to this run and world.

    Two runs sharing one would read each other's receipts, and the second
    would report the first's decisions as its own. The uuid is what makes
    it unique; a caller that needs a stable name across a restart passes
    `campaign` itself.
    """
    import uuid

    return "e3w%d-%s" % (world, uuid.uuid4().hex[:12])


class DecisionRecorder:
    """Where an admitted investigation becomes a real store operation.

    A decision the agenda made is not evidence of anything until it
    reaches an operation the store admitted, dispatched and settled. This
    is the one place that does that, so "the run wrote operations" and
    "the witness bound decisions afterwards" can never be confused: the
    run calls this inside `_run_development`, the witness does not.

    Authority is real. `authorize` seeds the grant, the allocation and
    the investigation through the same settlement commands every other
    campaign uses, and every operation is prepared against that
    allocation and dispatched under its ownership generation. A
    decision that cannot be admitted is recorded as refused, never
    silently dropped, because a run that kept its agenda log while the
    store refused the work is exactly the defect this closes.

    Given a `study_root`, the allocation is seeded as a child of that
    study's allocation. A parentless one is real and settled, and the
    store's contamination scanner resolves a study by walking allocation
    parentage, so it cannot see a single operation the recorder made.
    The run then reports fewer decisions than it produced, on the same
    instrument that measured it. A run with no `study_root` is not
    wrong, but it is invisible, and it says so through
    `adopted_operations` rather than leaving the gap to be found later.
    """

    def __init__(self, dsn: str, *, campaign: str, authorized: int,
                 study_root: str = "", study_allocation: str = ""):
        self._dsn = dsn
        self._campaign = campaign
        self._authorized = int(authorized)
        self._allocation_id = "%s-a" % campaign
        self._attempt_id = "%s-att" % campaign
        self._investigation_id = "%s-i" % campaign
        self._study_root = str(study_root or "")
        self._study_allocation = str(study_allocation or "")
        self._generation = None
        self.records: list = []
        self.refusals: list = []
        self._authorize()

    def _authorize(self) -> None:
        import uuid

        from settlement import store
        from settlement.common import Command, ResultCode

        def apply(fn, payload, name, already=None) -> bool:
            result = fn(self._dsn, Command(
                request_id="%s-%s-%s" % (self._campaign, name,
                                         uuid.uuid4().hex[:8]),
                payload=payload))
            if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
                return True
            if already is not None and already in result.detail:
                return False
            raise RuntimeError("store refused %s: %s" % (name, result.detail))

        # The store treats a grant as immutable and keyed by version, so a
        # second run into the same database reuses the one already there
        # rather than asking for a version of its own.
        apply(store.seed_grant,
              {"version": 1, "charter_text": self._campaign,
               "authority_grant": {}, "envelopes": {}}, "grant",
              already="immutable")
        # Each recorded operation reserves and settles exactly one unit of
        # `cpu`, and the run charges every decision at least one unit
        # against its own envelope, so the envelope bounds how many
        # operations this recorder can ever write. Under a study the
        # child is sized to that bound and to no more: asking the parent
        # for its whole remainder is the same authority for one cell
        # whatever the run does, and it leaves the next cell of the same
        # study nothing to start from.
        parent = self._study_allocation or None
        wanted = max(self._authorized * 1000, 10_000)
        if parent:
            wanted = min(wanted, max(self._authorized, 1))
            wanted = min(wanted, store.allocation_free(self._dsn, parent))
            if wanted <= 0:
                raise RuntimeError(
                    "study allocation %s has no free units for %s"
                    % (parent, self._allocation_id))
        apply(store.seed_allocation,
              {"allocation_id": self._allocation_id, "domain": "cpu",
               "parent_id": parent, "authorized": wanted,
               "max_occupancy": 16}, "alloc")
        self._adopted = self._study_allocation if parent else ""
        apply(store.admit_commitment,
              {"investigation_id": self._investigation_id,
               "objective": "reduce retained behavior size"}, "commit")
        acquired = store.acquire_work(self._dsn, Command(
            request_id="acquire-%s" % self._attempt_id,
            payload={"attempt_id": self._attempt_id,
                     "investigation_id": self._investigation_id,
                     "allocation_id": self._allocation_id,
                     "composition": "ad01-e3",
                     "owner": self._campaign}))
        generation = acquired.data.get("ownership_generation")
        if generation is None:
            from psycopg.rows import dict_row

            from settlement import db
            with db.connect(self._dsn, row_factory=dict_row) as conn:
                row = conn.execute(
                    "SELECT ownership_generation FROM attempts"
                    " WHERE id = %s", (self._attempt_id,)).fetchone()
                conn.commit()
            if row is None:
                raise RuntimeError("no attempt %r in the store"
                                   % (self._attempt_id,))
            generation = row["ownership_generation"]
        self._generation = generation

    def _operation_id(self, seq: int, decision: dict) -> str:
        return "ad01-%s-op%d-%s-%s-d%d" % (
            self._campaign, seq, decision["target"],
            decision["capability_id"], decision["max_queries"])

    def record(self, seq: int, decision: dict) -> dict:
        """Admit one decision and return the receipt it settled with.

        Never raises on a refusal. A run whose operation the store
        rejected still produced a decision, and hiding that would make
        the run's own record disagree with the store's.
        """
        from settlement import broker
        from settlement.common import ResultCode

        operation_id = self._operation_id(seq, decision)
        entry = {"seq": int(seq), **decision, "operation_id": operation_id}
        ensured = broker.ensure_operation(
            self._dsn, operation_id=operation_id,
            effect=broker.DOMAIN_COMMAND,
            payload={"command": "note",
                     "payload": {"decision": dict(decision)},
                     "idempotency_key": operation_id},
            allocation_id=self._allocation_id,
            attempt_id=self._attempt_id)
        if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            refusal = {**entry, "code": str(ensured.code),
                       "detail": ensured.detail, "settled": False}
            self.refusals.append(refusal)
            return refusal
        broker.dispatch_operation(self._dsn, operation_id,
                                  ownership_generation=self._generation)
        receipt = self.read_receipt(operation_id)
        record = {**entry, "settled": bool(receipt),
                  "receipt_identity": receipt["receipt_identity"] if receipt
                  else "",
                  "receipt_outcome": receipt["outcome"] if receipt else ""}
        self.records.append(record)
        return record

    @property
    def adopted(self) -> bool:
        """Whether the store's study scanner can see this recorder's work."""
        return bool(self._adopted and self._study_root)

    def adoption(self) -> dict:
        """What the study's own read would find here, and what it would miss.

        Counted by running the scanner's query rather than by restating
        which parent was passed to `seed_allocation`, so a figure that
        claims the work is visible is one the store agrees with.
        """
        if not self._study_root:
            return {"study_root": "", "adopted": False,
                    "visible": 0, "total": len(self.records)}
        from psycopg.rows import dict_row

        from settlement import db

        with db.read_connect(self._dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT o.id FROM operations o"
                    " JOIN study_authority a"
                    " ON a.allocation_id = ("
                    "   WITH RECURSIVE up (id, parent_id) AS ("
                    "     SELECT id, parent_id FROM allocations"
                    "      WHERE id = o.allocation_id"
                    "     UNION ALL"
                    "     SELECT l.id, l.parent_id FROM allocations l"
                    "     JOIN up ON l.id = up.parent_id)"
                    "   SELECT id FROM up WHERE id = a.allocation_id)"
                    " WHERE a.study_root = %s", (self._study_root,))
                found = {r["id"] for r in cur.fetchall()}
            conn.commit()
        mine = {r["operation_id"] for r in self.records}
        return {"study_root": self._study_root, "adopted": self.adopted,
                "visible": len(mine & found), "total": len(mine),
                "invisible": sorted(mine - found)[:4]}

    def read_receipt(self, operation_id: str) -> dict | None:
        """The receipt for one operation, read out of the receipts table.

        Every field comes from a SELECT. Nothing here recomputes what the
        store already holds, which is what makes a returned receipt
        evidence rather than a restatement of the call that made it.
        """
        from psycopg.rows import dict_row

        from settlement import db

        with db.connect(self._dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT receipt_identity, operation_id, outcome,"
                " content_digest, content FROM receipts"
                " WHERE operation_id = %s ORDER BY receipt_identity"
                " LIMIT 1", (operation_id,)).fetchone()
            conn.commit()
        if row is None:
            return None
        found = dict(row)
        found["content"] = dict(found.get("content") or {})
        return found


def _run_development(candidate, world, agenda, recorder=None):
    """Admit the named investigation, then run it as two real operations.

    The decision reaches the work through the shared `DecisionConsumer`
    gate: a proposer names the target, admission checks it against the
    world and the curriculum, and only an admitted action is executed.

    Once admitted, the diagnostic and the reduction run as two separate
    operations with their own budgets rather than through
    `trajectory._run_boundary`. That driver draws both from one query
    pool, and the graph diagnostic spends the whole allowance, which
    clamps the reduction to a single query and makes graph development
    unreachable. Splitting them is what makes a graph investigation
    reachable at all, and it matches E3's requirement that the system
    choose which permitted diagnostic to run.

    Severing the consumer refuses admission, so no operation runs and the
    run keeps nothing.

    With a recorder the admitted decision is written to the store before
    the diagnostic and the reduction run, so the work the run reports is
    work an admitted operation already names. A severed run is refused
    above and never reaches the recorder, which is why the control
    condition still leaves an empty store.
    """
    from . import trajectory
    from . import agenda_policy

    def proposer(seen, asked):
        return {
            "basis_references": [],
            "question": "does %s reduce under %s"
                        % (candidate.target, candidate.capability_id),
            "unknown": "whether %s reduces under %s"
                       % (candidate.target, candidate.capability_id),
            "requested_resources": {"diagnostic_queries":
                                    candidate.diagnose_queries},
            "charter": asked.get("objective", "reduce"),
            "next_action": {
                "kind": "development",
                "diagnostic": candidate.family,
                "task_id": candidate.target,
                "max_queries": candidate.max_queries,
            },
        }

    if agenda.sever:
        consumer = agenda_policy.disconnected_consumer(
            "investigation portfolio severed for the control condition")
    else:
        consumer = agenda_policy.DecisionConsumer(
            proposer=proposer, admit=trajectory.admit_investigation,
            policy_version=agenda.policy.version())

    seed = {"observation_id": "obs-%s-seed" % candidate.target,
            "task_id": candidate.target,
            "capability_id": candidate.capability_id,
            "verdict": "unmeasured"}
    packet = trajectory._packet.decision_packet(
        charter={"objective": "reduce retained behavior size"},
        visible=(),
        experience={"observations": [seed]},
        retained=(), remaining={},
        curriculum=None,
        boundary={"world": world, "arm": "I", "seq": 0})
    outcome = consumer.decide(packet, {"objective": "reduce retained "
                                                  "behavior size"},
                              boundary={"world": world, "arm": "I", "seq": 0},
                              experience=packet)
    if outcome.get("status") != "admitted":
        return None, {"disposition": "no-candidate", "fallback": "incumbent",
                      "fallback_reason": outcome.get("reason", "refused"),
                      "task_id": candidate.target, "queries": 0}
    admitted = outcome["investigation"]
    if recorder is not None:
        recorder.record(candidate.seq, {
            "target": candidate.target,
            "capability_id": candidate.capability_id,
            "family": candidate.family,
            "max_queries": candidate.max_queries,
            "charge": candidate.cost(),
        })
    observation = trajectory.run_diagnostic(
        admitted, {"observations": [seed]},
        budget=candidate.diagnose_queries)
    episode = trajectory.dev_episode(
        admitted["next_action"]["task_id"],
        admitted["next_action"].get("capability_id")
        or candidate.capability_id,
        max_queries=candidate.max_queries)
    episode["diagnostic_observation"] = observation["observation_id"]
    episode["diagnostic_queries"] = int(observation.get("queries", 0))
    return observation, episode


def run_investigations(portfolio, policy, allocation, *, world=0,
                       sever=False, depths=(2, 3, 4, 5, 6, 7),
                       diagnose_queries=4, dsn=None, campaign=None,
                       study_root="", study_allocation=""):
    """Drive one policy over the portfolio under one finite allocation.

    A non-`None` portfolio must equal the qualified world's development
    targets, so a caller cannot hand in a schedule where a portfolio is
    required. `None` is accepted and the run reads the qualified world.
    The loop stops when the policy declines or when nothing is affordable,
    and never spends past the envelope.

    A `dsn` puts the store inside the run. Every decision the consumer
    admits is then written as a broker operation, prepared against a real
    allocation and dispatched under its ownership generation, so the
    decisions a caller reads back are the ones the store admitted. With
    no `dsn` the run keeps its agenda log and writes nothing, which is
    what a caller that wants no store asked for. `campaign` names the
    identities; it must be unique per run, because two runs sharing one
    would read each other's receipts.

    `study_root` with `study_allocation` puts the recorder's allocation
    inside that study's subtree, so the store's own contamination
    scanner can see what the run did. Without them the run is still
    real, but it is invisible to any study-scoped read, and
    `orphaned_operations` says so instead of letting the count quietly
    come up short.
    """
    expected = portfolio_for_world(world)
    if portfolio is not None and tuple(portfolio) != expected:
        raise ValueError(
            "portfolio does not match the qualified world %d" % world)
    assert_measure_freeze()
    recorder = None
    if dsn is not None:
        recorder = DecisionRecorder(
            dsn, campaign=campaign or _default_campaign(world),
            authorized=allocation.authorized,
            study_root=study_root or "",
            study_allocation=study_allocation or "")
    agenda = Agenda(world, policy, allocation, sever=sever,
                    depths=depths, diagnose_queries=diagnose_queries)
    offered = {row.identity for row in agenda.offered}
    choices, executions, ledger = [], [], []
    stop_reason = "policy declined"
    while True:
        proposal = policy.propose(agenda)
        if proposal is None:
            stop_reason = policy.stop_reason()
            break
        candidate = proposal["candidate"]
        if candidate.identity not in offered:
            stop_reason = "proposal outside the portfolio"
            break
        if not agenda.afford(candidate):
            stop_reason = "budget exhausted"
            break
        allocation.charge(candidate.cost())
        candidate.seq = len(choices)
        choices.append(Choice(candidate, candidate.cost(),
                              proposal["rationale"]))
        observation, episode = _run_development(candidate, world, agenda,
                                                recorder)
        method = candidate.capability_id.rsplit("-", 1)[-1]
        claim, report = _claim_from(observation, candidate.family)
        execution = Execution(choices[-1], episode, candidate.cost(),
                              observation, claim=claim, observed=report,
                              correct=_diagnostic_holds(claim, episode, method))
        executions.append(execution)
        agenda.note_ran(candidate.target)
        agenda.advance(candidate.family, method, episode, candidate.cost(),
                       candidate.max_queries)
        policy.observe(agenda, candidate, episode)
    for execution in executions:
        candidate = execution.choice.candidate
        if execution.episode.get("disposition") != "retained":
            continue
        ledger.extend(_held_out_row(
            world, candidate.family, execution.episode["executable"],
            candidate.max_queries))
    return InvestigationRun(
        world=world, policy_version=policy.version(), choices=choices,
        executions=executions,
        yield_=Yield(sum(1 for e in executions
                         if e.episode.get("disposition") == "retained"),
                     (sum(row["reduction"] for row in ledger) / len(ledger))
                     if ledger else 0.0,
                     sum(1 for e in executions if e.correct is True),
                     allocation.spent),
        held_out_ledger=ledger, stop_reason=stop_reason,
        measure_digest=yield_measure_digest(), recorder=recorder,
        allocation=allocation)


def best_fixed_allocation(world=0, authorized=14,
                          depths=(1, 2, 3, 4, 5, 6, 7)):
    """The strongest pre-committed rule, chosen by exhaustive search.

    This is an oracle: it ranks rules by the held-out score it is not
    allowed to see at run time. It exists to bound what any adaptive
    policy could win, not to be beaten inside the study.
    """
    from . import agenda_policy
    best = None
    for software_method in METHODS:
        for graph_method in METHODS:
            for software_queries in depths:
                for graph_queries in depths:
                    if max(software_queries, graph_queries) not in depths:
                        continue
                    policy = agenda_policy.fixed_policy(
                        {"software": (software_method, software_queries),
                         "graph": (graph_method, graph_queries)})
                    run = run_investigations(
                        None, policy, Allocation(authorized=authorized),
                        world=world, depths=depths)
                    key = (run.yield_.held_out_reduction,
                           run.yield_.retained_behaviors,
                           -run.yield_.resources_used)
                    if best is None or key > best[0]:
                        best = (key, run)
    return best[1]
