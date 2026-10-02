"""One durable mission entry.

A mission is six things and one record holds all of them: what is still open,
what the mission is allowed to have learned, which program is authorised to
act, what it has acquired, what of that it retains and uses, and whether it is
operating or improving.

Before this module, three aggregates each held a part. `s09_policy_state` held
the accepted decisions, `FrontierStore.pending_effects` the unresolved work,
and `context.resume_package` the continuation. Each is keyed for a different
question, so answering "what is this investigation for" meant reading three
places and reconciling them, and a crash between two of the writes left a
mission that answered all three differently.

The entry is one row on `investigations`, which already owns an
investigation's identity and objective. Adding six columns there keeps the
entry reachable with no join, and it means no sixth aggregate is introduced.
The fields are deliberately opaque JSON: a mission is the study's to
describe, and a schema here would make every new study a migration. What this
module does own is the identity of the six, so a caller cannot record a
seventh thing by accident and a second table cannot take one of them without
being caught.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

MISSION_FIELDS = (
    "frontier",
    "permitted_experience",
    "active_program",
    "acquired_artifacts",
    "retained_use",
    "improvement_mode",
)

# `improvement_mode` is the one field with a closed value set. The other five
# are the study's own descriptions and stay opaque, so constraining them here
# would make every new study a migration to this module. The mode is not the
# study's: "improve" versus "operate" decides which executor holds authority,
# so an unrecognised value has to be a refusal rather than a typo that leaves
# a mission silently inert.
IMPROVEMENT_MODES = ("operate", "improve")

# The six are per-field JSON types, so a caller writing the wrong shape is
# refused at the boundary rather than read back as something else.
_JSON_TYPES = {
    "frontier": dict,
    "permitted_experience": dict,
    "active_program": (dict, type(None)),
    "acquired_artifacts": list,
    "retained_use": (dict, type(None)),
}


class MissionRefused(Exception):
    """A mission entry that is not the shape the entry requires."""


@dataclass(frozen=True)
class MissionEntry:
    """One investigation's mission, read whole.

    `objective`, `environments`, `constraints` and `success_criteria` are the
    study's charter and are already on the row; the six fields are the entry.
    Keeping the charter beside the entry is what lets a caller build a view
    without a second read, and it is why `as_declaration` round-trips into
    the frontier store's own constructor.
    """

    investigation_id: str
    objective: str
    environments: list
    constraints: list
    success_criteria: list
    frontier: dict
    permitted_experience: dict
    active_program: dict | None
    acquired_artifacts: list
    retained_use: dict | None
    improvement_mode: str

    def as_declaration(self) -> dict:
        """The mission as a study declares it, before it is recorded.

        This is the shape `frontier.create_store` accepts. A frontier store
        used to carry its own mission dict; after the migration it carries
        this one, read from the durable entry rather than restated in a file.
        """
        return {"objective": self.objective,
                "environments": list(self.environments),
                "constraints": list(self.constraints),
                "success_criteria": list(self.success_criteria)}


# An operation is `held` the moment its decision is admitted and its effect has
# not run, and `restored` once a restart has read it back without running it.
# Neither state means the effect happened: only `s09_policy_state.effect_record`
# does, and a resume that wrote one would be re-running the work rather than
# restoring it.
IN_FLIGHT_STATES = ("held", "restored", "suspended")


@dataclass(frozen=True)
class InFlightOperation:
    """One admitted operation, and the identity it was admitted under.

    `program_digest` and `input_identity` are the whole point of this record.
    The admitted decision says what to run; these two say under which program
    and with which inputs, which a restart cannot recompute without silently
    substituting a different program. A study that resumes under a
    substituted program is measuring a different thing than it claims, and
    nothing downstream would say so.
    """

    investigation_id: str
    seq: int
    attempt_id: str
    decision_digest: str
    program_digest: str
    input_identity: str
    status: str
    barrier_ref: str
    task_id: str
    capability_id: str
    admitted_at: str
    restored_at: str

    def as_json(self) -> dict:
        return {"seq": self.seq, "attempt_id": self.attempt_id,
                "decision_digest": self.decision_digest,
                "program_digest": self.program_digest,
                "input_identity": self.input_identity, "status": self.status,
                "barrier_ref": self.barrier_ref, "task_id": self.task_id,
                "capability_id": self.capability_id,
                "admitted_at": self.admitted_at, "restored_at": self.restored_at}

    @classmethod
    def from_json(cls, investigation_id: str, raw: dict) -> "InFlightOperation":
        status = str(raw.get("status") or "")
        if status not in IN_FLIGHT_STATES:
            raise MissionRefused("unknown in-flight state %r" % status)
        return cls(investigation_id=investigation_id,
                   seq=int(raw.get("seq", -1)),
                   attempt_id=str(raw.get("attempt_id") or ""),
                   decision_digest=str(raw.get("decision_digest") or ""),
                   program_digest=str(raw.get("program_digest") or ""),
                   input_identity=str(raw.get("input_identity") or ""),
                   status=status,
                   barrier_ref=str(raw.get("barrier_ref") or ""),
                   task_id=str(raw.get("task_id") or ""),
                   capability_id=str(raw.get("capability_id") or ""),
                   admitted_at=str(raw.get("admitted_at") or ""),
                   restored_at=str(raw.get("restored_at") or ""))


def connect(dsn: str):
    """A connection the caller commits.

    `trajectory._read_conn` is the same seam and is not imported: `mission` is
    reachable without `trajectory`, and a module that needs only a connection
    should not pull the whole campaign driver in to get one.
    """
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(dsn, row_factory=dict_row)


def _validate(fields: dict) -> None:
    unknown = sorted(set(fields) - set(MISSION_FIELDS))
    if unknown:
        raise MissionRefused("unknown mission field: %s" % unknown[0])
    for name, expected in _JSON_TYPES.items():
        if name not in fields:
            continue
        value = fields[name]
        if not isinstance(value, expected):
            wanted = (expected.__name__ if isinstance(expected, type)
                      else " or ".join(t.__name__ for t in expected))
            raise MissionRefused("%s must be %s, not %s" % (
                name, wanted, type(value).__name__))
    mode = fields.get("improvement_mode")
    if mode is not None and mode not in IMPROVEMENT_MODES:
        raise MissionRefused("improvement mode must be one of %s"
                             % ", ".join(IMPROVEMENT_MODES))


def record_mission(dsn: str, investigation_id: str, *,
                   objective: str | None = None,
                   environments: Iterable | None = None,
                   constraints: Iterable | None = None,
                   success_criteria: Iterable | None = None,
                   **fields: Any) -> None:
    """Write the mission entry for one investigation, creating it if absent.

    Both halves live here because they are one write. A study that has no
    investigation yet still needs somewhere to put a mission, and splitting
    admission from recording would leave the same two-step window the old
    three-aggregate arrangement had.

    A field the caller does not pass is left as it is. A mission is built
    over its life -- the charter is frozen first, and experience, program
    and retained use are written as they are acquired -- so an update naming
    one of the six must not blank the other five, and naming the charter must
    not blank the six. The columns below are assembled from what was
    actually supplied, which is why this is a partial UPDATE rather than a
    wholesale overwrite. `scope` and `obligations` merge rather than replace
    for the same reason, and because the steward writes other keys into
    `obligations`.
    """
    _validate(fields)
    if not isinstance(investigation_id, str) or not investigation_id.strip():
        raise MissionRefused("a mission needs an investigation id")

    environment_value = _charter("environments", environments)
    columns = ["id", "revision", "objective", "origin"]
    values: list = [investigation_id, 1,
                    objective if objective is not None else "",
                    "ad01-mission"]
    # What the caller actually named. `objective` is on every INSERT because
    # the column is NOT NULL, but it is only an UPDATE when it was supplied.
    supplied = {"objective"} if objective is not None else set()
    merged = {"scope", "obligations"}
    for name, value in (("scope", environment_value),
                        ("obligations", _charter_pair(constraints,
                                                      success_criteria))):
        if value is None:
            continue
        columns.append(name)
        values.append(_j(value))
        supplied.add(name)
    for name in MISSION_FIELDS:
        if name not in fields:
            continue
        columns.append(name)
        values.append(fields[name] if name == "improvement_mode"
                      else _j(fields[name]))
        supplied.add(name)

    updates = ["updated_at = now()"]
    for name in ("objective", "scope", "obligations", *MISSION_FIELDS):
        if name not in supplied:
            continue
        # The two charter bags are shared with the steward and hold keys this
        # module does not own, so a mission update merges rather than
        # replaces. The six are this module's alone and are written whole.
        updates.append("%s = investigations.%s || EXCLUDED.%s" % (name, name, name)
                       if name in merged
                       else "%s = EXCLUDED.%s" % (name, name))

    with connect(dsn) as conn:
        existing = conn.execute(
            "SELECT 1 FROM investigations WHERE id = %s FOR UPDATE",
            (investigation_id,)).fetchone()
        if existing is None and (
                not isinstance(objective, str) or not objective.strip()
                or not environment_value
                or not environment_value["environments"]):
            raise MissionRefused(
                "an initial mission needs an objective and environments")
        conn.execute(
            "INSERT INTO investigations (%s) VALUES (%s)"
            " ON CONFLICT (id) DO UPDATE SET %s"
            % (", ".join(columns),
               ", ".join(["%s"] * len(values)),
               ", ".join(updates)),
            values)
        conn.commit()


def _charter(key: str, value: Iterable | None):
    return None if value is None else {key: list(value)}


def _charter_pair(constraints: Iterable | None,
                  success_criteria: Iterable | None) -> dict | None:
    if constraints is None and success_criteria is None:
        return None
    bag: dict = {}
    if constraints is not None:
        bag["constraints"] = list(constraints)
    if success_criteria is not None:
        bag["success_criteria"] = list(success_criteria)
    return bag


def _j(value: Any):
    from psycopg.types.json import Json

    return Json(value)


def read_mission(dsn: str, investigation_id: str) -> MissionEntry:
    """The whole mission, or a refusal. Never a partial entry."""
    with connect(dsn) as conn:
        row = conn.execute(
            "SELECT id, objective, scope, obligations, frontier,"
            " permitted_experience, active_program, acquired_artifacts,"
            " retained_use, improvement_mode"
            " FROM investigations WHERE id = %s",
            (investigation_id,)).fetchone()
        conn.commit()
    if row is None:
        raise MissionRefused("no mission for investigation %r"
                             % investigation_id)
    scope = dict(row["scope"] or {})
    obligations = dict(row["obligations"] or {})
    return MissionEntry(
        investigation_id=row["id"],
        objective=row["objective"],
        environments=list(scope.get("environments") or []),
        constraints=list(obligations.get("constraints") or []),
        success_criteria=list(obligations.get("success_criteria") or []),
        frontier=dict(row["frontier"] or {}),
        permitted_experience=dict(row["permitted_experience"] or {}),
        active_program=(None if row["active_program"] is None
                        else dict(row["active_program"])),
        acquired_artifacts=list(row["acquired_artifacts"] or []),
        retained_use=(None if row["retained_use"] is None
                      else dict(row["retained_use"])),
        improvement_mode=row["improvement_mode"])


def read_declaration(dsn: str, investigation_id: str) -> dict:
    """The mission in the form a frontier store accepts.

    A study that builds a frontier store needs the objective and the frozen
    environments and nothing else. It used to hand-build that dict and the
    store wrote its own copy; it now reads the one the entry already holds.
    """
    return read_mission(dsn, investigation_id).as_declaration()


def seed_program_digest() -> str:
    """The identity of the program a decision runs under when none was named.

    `seeds.SEED_CAPABILITIES` carries a method name rather than source bytes, so
    the seed program's digest is taken over its declared identity: what it is,
    what family it serves, which method it is and which freeze it came from.
    That is stable across processes, which is what a record read back after a
    restart requires, and it distinguishes the four seed programs from each
    other, which is the whole reason the field exists.
    """
    import hashlib
    import json

    from . import seeds

    capability = next(c for c in seeds.SEED_CAPABILITIES
                      if c["capability_id"] == "seed-sw-greedy")
    raw = json.dumps({"capability_id": capability["capability_id"],
                      "family": capability["family"],
                      "method": capability["method"],
                      "origin": capability["origin"],
                      "freeze": capability["freeze"]},
                     sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


# `in_flight` is the mission's, not one of `MISSION_FIELDS`. Those six are a
# study's own descriptions and `mission` refuses an unknown key against them;
# the in-flight list is this module's own bookkeeping and is written by a
# different function, so folding it in would let a caller overwrite a held
# operation's program identity by naming a seventh field. The column name is
# therefore spelled where it is used, and `read_mission` does not return it,
# because a caller that can write the whole list is an owner this module does
# not intend to have.


def _wire(decision: dict, task_id: str, capability_id: str) -> dict:
    """The digests an admitted operation is pinned to.

    Both are derived from bytes the caller cannot change afterwards, so a
    restart that reads them back is reading the identity the operation was
    admitted under rather than whatever the restarting process now holds. The
    canonical form is sorted and separator-tight, matching
    `save_continuation`, so the same decision always produces the same digest.
    """
    import hashlib
    import json

    def digest_of(value) -> str:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()

    return {"decision_digest": digest_of(decision),
            "input_identity": digest_of({"decision": decision,
                                         "task_id": task_id,
                                         "capability_id": capability_id})}


def admit_operation(dsn: str, investigation_id: str, *, seq: int,
                    attempt_id: str, decision: dict, program_digest: str,
                    task_id: str, capability_id: str) -> InFlightOperation:
    """Record an admitted operation, held, with the identity it was admitted under.

    Called at the moment the decision is admitted and before its effect runs.
    That ordering is the whole point: an operation whose identity is recorded
    only when the effect completes is missing precisely the record a restart
    needs, because a restart happens when the effect has not completed.

    `program_digest` is required rather than defaulted. A caller with no
    program to name has no in-flight operation; the alternative is an empty
    digest that reads as "admitted under nothing" and is indistinguishable
    from a lost record, which is the substitution this module exists to
    prevent.

    Idempotent on `(seq, attempt_id)`. Re-admitting an operation already
    present leaves it exactly as it is, including its `restored_at` and
    `barrier_ref`: a restart that re-reads an admitted decision must not
    silently un-hold an operation a barrier is waiting on.
    """
    if not isinstance(program_digest, str) or not program_digest.strip():
        raise MissionRefused("an admitted operation needs the program digest"
                             " it was admitted under")
    if not isinstance(decision, dict):
        raise MissionRefused("an admitted operation needs its decision")
    digests = _wire(decision, task_id, capability_id)
    held = InFlightOperation(
        investigation_id=investigation_id, seq=int(seq), attempt_id=attempt_id,
        decision_digest=digests["decision_digest"],
        program_digest=program_digest,
        input_identity=digests["input_identity"], status="held",
        barrier_ref="", task_id=task_id, capability_id=capability_id,
        admitted_at="", restored_at="")

    with connect(dsn) as conn:
        row = conn.execute(
            "SELECT in_flight FROM investigations WHERE id = %s FOR UPDATE",
            (investigation_id,)).fetchone()
        if row is None:
            raise MissionRefused("no mission for investigation %r"
                                 % investigation_id)
        current = [_entry(investigation_id, raw)
                   for raw in (row["in_flight"] or [])]
        for existing in current:
            if existing.seq == held.seq and existing.attempt_id == held.attempt_id:
                return existing
        if held not in current:
            current.append(held)
        conn.execute(
            "UPDATE investigations SET in_flight = %s, updated_at = now()"
            " WHERE id = %s",
            (_j([item.as_json() for item in current]), investigation_id))
        conn.commit()
    return held


def _entry(investigation_id: str, raw: dict) -> InFlightOperation:
    return InFlightOperation.from_json(investigation_id, dict(raw))


def read_in_flight(dsn: str, investigation_id: str) -> list[InFlightOperation]:
    """Every operation this investigation still holds, whole.

    Read by seq so a caller restoring one investigation does not depend on the
    order the rows were appended.
    """
    with connect(dsn) as conn:
        row = conn.execute("SELECT in_flight FROM investigations WHERE id = %s",
                           (investigation_id,)).fetchone()
        conn.commit()
    if row is None:
        raise MissionRefused("no mission for investigation %r"
                             % investigation_id)
    return sorted((_entry(investigation_id, raw)
                   for raw in (row["in_flight"] or [])),
                  key=lambda item: (item.seq, item.attempt_id))


def held_operation(dsn: str, investigation_id: str,
                   attempt_id: str) -> InFlightOperation | None:
    """The one operation an attempt is holding, or None.

    Keyed on the attempt because that is what a suspension names. A barrier
    arrives holding an attempt id and nothing else, so looking it up by the
    attempt is the only lookup that answers the question as asked.
    """
    for item in read_in_flight(dsn, investigation_id):
        if item.attempt_id == attempt_id:
            return item
    return None


def resume_operation(dsn: str,
                     investigation_id: str) -> list[InFlightOperation]:
    """Restore this investigation's held operations without running any of them.

    Restoration is a read of the recorded identity and a status change. It
    deliberately writes no effect record, executes nothing, and does not
    advance the operation past its point: an operation restored here is
    admitted and still to run, and the boundary that runs it is the only thing
    that may mark it done. A resume that executed the work would be
    re-running it, which is how a study ends up double-counting an effect
    after a crash it thought it recovered from.

    `restored_at` is stamped on first restoration and left alone afterwards,
    so restoring twice is one restoration rather than two, and a caller can
    tell a restored operation from one that is merely held.
    """
    with connect(dsn) as conn:
        row = conn.execute(
            "SELECT in_flight, now() AS stamped FROM investigations"
            " WHERE id = %s FOR UPDATE", (investigation_id,)).fetchone()
        if row is None:
            raise MissionRefused("no mission for investigation %r"
                                 % investigation_id)
        stamped = str(row["stamped"])
        current = [_entry(investigation_id, raw)
                   for raw in (row["in_flight"] or [])]
        restored = [InFlightOperation(
            investigation_id=item.investigation_id, seq=item.seq,
            attempt_id=item.attempt_id,
            decision_digest=item.decision_digest,
            program_digest=item.program_digest,
            input_identity=item.input_identity, status="restored",
            barrier_ref=item.barrier_ref, task_id=item.task_id,
            capability_id=item.capability_id, admitted_at=item.admitted_at,
            restored_at=item.restored_at or stamped)
            for item in current]
        conn.execute(
            "UPDATE investigations SET in_flight = %s, updated_at = now()"
            " WHERE id = %s",
            (_j([item.as_json() for item in restored]), investigation_id))
        conn.commit()
    return sorted(restored, key=lambda item: (item.seq, item.attempt_id))


def release_operation(dsn: str, investigation_id: str,
                      attempt_id: str) -> None:
    """Drop an operation that has settled.

    An operation whose effect is recorded in `s09_policy_state.effect_record`
    is no longer in flight, and leaving it on the entry would make a later
    resume restore work that already ran.

    The read and the write are one transaction under `FOR UPDATE`, as in
    `admit_operation` and `resume_operation`. This used to read on one
    connection, filter the attempt out in Python, and overwrite the column on
    a second connection with no lock, which is a lost update against every
    other writer of the same column: two boundaries of one campaign settling
    at once each read the pre-settle list, and the second write restored the
    first one's settled operation. That operation then reads back as still in
    flight, and a later resume restores an effect that already ran. The
    unlocked overwrite existed only to express this removal, so removing the
    helper removed the unlocked path rather than adding a second guard to it.
    """
    with connect(dsn) as conn:
        row = conn.execute(
            "SELECT in_flight FROM investigations WHERE id = %s FOR UPDATE",
            (investigation_id,)).fetchone()
        if row is None:
            raise MissionRefused("no mission for investigation %r"
                                 % investigation_id)
        current = [_entry(investigation_id, raw)
                   for raw in (row["in_flight"] or [])]
        remaining = [item for item in current if item.attempt_id != attempt_id]
        if len(remaining) == len(current):
            conn.commit()
            return
        conn.execute(
            "UPDATE investigations SET in_flight = %s, updated_at = now()"
            " WHERE id = %s",
            (_j([item.as_json() for item in remaining]), investigation_id))
        conn.commit()
