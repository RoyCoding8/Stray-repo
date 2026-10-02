"""Reconcile inherited model-unit exposure and bound a new study's allowances.

Every figure is recomputed from a committed artifact or from the project
ledger. A number that no committed artifact carries is CARRIED_FORWARD, and the
type keeps that distinction so a carried figure cannot be consumed as a
verified one.

Three quantities used to share one column, and the arithmetic between them
produced a number nobody measured. A provider that reports no charge field was
read as a price of zero, that zero was multiplied by a dispatch count to invent
a unit ceiling, and the ceiling then had carried reservation units subtracted
from it to produce a count of remaining dispatches. Nothing in that chain was
refused, because nothing in it knew what it was adding.

The three are separate types here, and they do not share an operation:

* `DispatchAllowance` counts physical sends, read from the freeze and spent
  from durable operations. A count of sends.
* `ReservationAllowance` counts broker reservation units, sized for a new
  campaign from that campaign's own request bounds by calling the broker's
  own exposure schedule. An internal estimate, not a cost and not a count.
* `ProviderCharge` is what a receipt actually said about a price, in three
  states. A receipt with no charge field says nothing, and `NOT_REPORTED`
  exposes no number, so no capacity can be derived from an absence.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
R4_EVIDENCE = "reports/evidence/invl02-output-shape-550b-r4"
R4_BUNDLE = R4_EVIDENCE + "/output-run.json"
R4_RECONCILIATION = R4_EVIDENCE + "/store-reconciliation.json"
R4_GRANT = R4_EVIDENCE + "/grant-binding.json"
PROBE_EVIDENCE = "evidence_s09_route_probe/probe.json"
OLDER_BUNDLE = "reports/evidence/invl02-live/e0-run.json"
OLDER_RECONCILIATION = "reports/evidence/invl02-live/store-reconciliation.json"
EVIDENCE_ROOT = "reports/evidence"
PROJECT_LEDGER = "reports/PROJECT-LEDGER.md"
R4_RESERVATION_PREFIX = "res-invl02-output-"

# The ledger states the measured broker reservation as
# (sum(floor(len(message.content)/4)) + 1 + max_output_tokens) * (retries + 1).
RESERVATION_FORMULA = (
    "(message_characters // 4 + 1 + max_output_tokens) * (retries + 1)")

LEDGER_ROW = re.compile(
    r"^\|\s*`(?P<id>res-[^`]+)`(?P<note>[^|]*)\|\s*(?P<amount>\d+)\s*\|"
    r"\s*(?P<state>\w+)\s*\|")
LEDGER_FENCE_ROW = re.compile(
    r"^(?P<id>res-\S+)\s+(?P<amount>\d+)\s+(?P<state>\w+)\s*$")
LEDGER_CORROBORATION = re.compile(
    r"floor\((?P<characters>\d+)/4\)\s*\+\s*1\s*\+\s*(?P<max_output>\d+)\s*=\s*"
    r"(?P<units>\d+)")
BOLD_UNIT_TOTAL = re.compile(r"\*\*(?P<amount>\d+)\s+units\*\*")


class Evidence(str, Enum):
    VERIFIED = "VERIFIED"
    CARRIED_FORWARD = "CARRIED_FORWARD"


class ChargeState(str, Enum):
    """The three things a receipt can say about a price.

    REPORTED is an amount the response carried. NOT_REPORTED is a settled
    receipt that carried no charge field, which is an absence. UNMEASURED is
    no committed receipt at all, which is not even a receipt.
    """

    REPORTED = "REPORTED"
    NOT_REPORTED = "NOT_REPORTED"
    UNMEASURED = "UNMEASURED"


@dataclass(frozen=True)
class Source:
    artifact: str
    locator: str
    detail: str = ""


@dataclass(frozen=True)
class Units:
    value: int
    source: Source
    evidence: Evidence

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("units must be non-negative")

    @property
    def verified(self) -> bool:
        return self.evidence is Evidence.VERIFIED

    def conservative_max(self, other: "Units") -> "Units":
        if other.value > self.value:
            return other
        if self.value > other.value:
            return self
        if self.verified and not other.verified:
            return self
        return Units(self.value, self.source, Evidence.CARRIED_FORWARD)

    def label(self) -> str:
        return "%d %s" % (self.value, self.evidence.value)


@dataclass(frozen=True)
class ProviderCharge:
    """A provider price in one of three states, never a number or nothing.

    `budget_units` is the only number a budget may read, and it is None for
    both absent states. Constructing an absent state with an amount is
    refused, which makes the old `int(charge or 0)` unrepresentable rather
    than merely discouraged.
    """

    state: ChargeState
    units: int | None = None
    billed: bool | None = None
    charge_scale: int | None = None
    source: Source | None = None

    def __post_init__(self) -> None:
        if self.state is ChargeState.REPORTED and self.units is None:
            raise ValueError("a REPORTED charge needs the amount the receipt "
                             "carried")
        if self.state is not ChargeState.REPORTED and self.units is not None:
            raise ValueError("%s carries no amount, so a number beside it "
                             "would be invented" % self.state.value)

    @classmethod
    def not_reported(cls, source: Source | None = None) -> "ProviderCharge":
        return cls(ChargeState.NOT_REPORTED, source=source)

    @classmethod
    def unmeasured(cls, source: Source | None = None) -> "ProviderCharge":
        return cls(ChargeState.UNMEASURED, source=source)

    @property
    def budget_units(self) -> int | None:
        """The units a budget may consume. None means it may not be derived."""
        return self.units if self.state is ChargeState.REPORTED else None


def charge_from_receipt(receipt: Mapping[str, Any] | None,
                        source: Source | None = None) -> ProviderCharge:
    """What a receipt actually said about a price, as one of three states.

    A null `charge_units` is an absence the receipt made, which is a
    different fact from a receipt that never arrived.
    """
    if not isinstance(receipt, Mapping) \
            or not isinstance(receipt.get("usage"), Mapping):
        return ProviderCharge.unmeasured(source)
    usage = dict(receipt["usage"])
    amount = usage.get("charge_units")
    if amount is None:
        return ProviderCharge.not_reported(source)
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        return ProviderCharge.unmeasured(source)
    return ProviderCharge(ChargeState.REPORTED, units=amount,
                          billed=usage.get("billed"),
                          charge_scale=usage.get("charge_scale"),
                          source=source)


@dataclass(frozen=True)
class DispatchClaim:
    value: int | str
    source: Source

    def label(self) -> str:
        return "%s per %s" % (self.value, self.source.artifact)

    @property
    def counted(self) -> int | None:
        """The claim as a number, or None when the source named no number.

        A bundle that never reconciled its dispatch count writes the string
        `"unknown"` rather than a zero, so a claim is either a count or the
        absence of one. An absent count is excluded from the max rather than
        counted as zero: `max_dispatch_claims` is the figure a ceiling is
        allowed to be read from, and a zero from a file that knows nothing
        would outrank the durable store's real count.
        """
        return self.value if type(self.value) is int else None


@dataclass(frozen=True)
class ArithmeticCheck:
    label: str
    expression: str
    stated_units: int
    recomputed_units: int
    inputs_source: Source
    inputs_evidence: Evidence

    @property
    def agrees(self) -> bool:
        return self.stated_units == self.recomputed_units

    def label_text(self) -> str:
        return "%s: %s = %d, stated %d" % (
            self.label, self.expression, self.recomputed_units, self.stated_units)


@dataclass(frozen=True)
class ReservationClaim:
    reservation_id: str
    amount: int
    state: str
    source: Source


@dataclass(frozen=True)
class AbridgedClaim:
    abridged_id: str
    full_id: str
    source: Source


@dataclass(frozen=True)
class StudyExposure:
    study_root: str
    study_label: str
    reservation_id: str
    operation_id: str
    dispatch_state: str
    reconcile_state: str
    settled: bool
    units_uncertain: Units
    dispatch_claims: tuple[DispatchClaim, ...]
    receipt_outcome: str
    corroborated_by_arithmetic: ArithmeticCheck | None
    bundle_under_reports_spend_by: int = 0
    held_reservation: "HeldReservation | None" = None

    @property
    def contributes_to_liability(self) -> bool:
        return not self.settled

    @property
    def max_dispatch_claims(self) -> int:
        """The largest count any of this study's sources actually states.

        A study whose every source declined to name a number has no max, and
        `max()` over nothing would raise inside a property. Zero is the right
        empty answer here rather than `None`: the property is an int, the
        count is compared against a reservation, and no source claiming a
        count is not evidence of a send. The settled rows that can reach this
        are the only ones with a single claim.
        """
        counted = [claim.counted for claim in self.dispatch_claims
                   if claim.counted is not None]
        return max(counted) if counted else 0

    @property
    def dispatch_count_disputed(self) -> bool:
        return len({claim.value for claim in self.dispatch_claims
                    if claim.counted is not None}) > 1

    def carried_units(self) -> Units:
        if self.corroborated_by_arithmetic is None:
            return self.units_uncertain
        recomputed = Units(
            self.corroborated_by_arithmetic.recomputed_units,
            self.corroborated_by_arithmetic.inputs_source,
            self.corroborated_by_arithmetic.inputs_evidence)
        return self.units_uncertain.conservative_max(recomputed)


@dataclass(frozen=True)
class Conflict:
    subject: str
    positions: tuple[str, ...]
    resolution: str

    def report(self) -> str:
        return "%s: %s -> %s" % (
            self.subject, " vs ".join(self.positions), self.resolution)


@dataclass(frozen=True)
class ProvenanceWarning:
    code: str
    detail: str
    consequence: str
    sources: tuple[Source, ...]


@dataclass(frozen=True)
class PriorExposure:
    repo_root: Path
    census_source: Source
    studies: tuple[StudyExposure, ...]
    settled_units: int
    corroborations: tuple[ArithmeticCheck, ...]
    abridged_claims: tuple[AbridgedClaim, ...]
    unresolved_citations: tuple[str, ...]

    def study(self, label: str) -> StudyExposure:
        for study in self.studies:
            if study.study_label == label:
                return study
        raise KeyError(label)



@dataclass(frozen=True)
class Grant:
    """The authority a held reservation was taken against.

    A number of units with no owner cannot be carried into a new freeze, so
    each hold names the grant it is owed against and the root it is scoped
    to. The grant is a record of what was authorized, not a source of
    authority now.
    """

    grant_id: str
    study_root: str
    authorized_units: int | None = None
    authorized_on: str = ""
    scope: tuple[str, ...] = ()
    source: Source | None = None


@dataclass(frozen=True)
class HeldReservation:
    """A reservation that is still owed, held as its own record.

    Nothing about reading this type releases a hold, settles it, or reduces
    it. The reservation row in the durable store is the thing those acts would
    change, and this type never writes there.
    """

    reservation_id: str
    operation_id: str
    units: int
    state: str
    settled: bool
    study_root: str
    grant: Grant | None
    source: Source
    computed_from_inputs: bool = False


@dataclass(frozen=True)
class RequestEstimate:
    """What the broker reserves for one real request, and what vouched for it.

    `prompt_digest_matched` is computed, never asserted. It is True only when
    a committed artifact carries the sha256 of these exact prompt bytes; the
    three sites that build this record did not all have a committed digest in
    scope, and two of them said True anyway. It is therefore a distinction
    between a bound the broker priced for a prompt somebody committed and a
    bound it priced for a character count, which is a weaker thing and is now
    readable as one.

    A False is recorded, not fatal. An unmatched prompt still yields a real
    broker answer for a real request, and refusing to price a request whose
    history nobody committed would price nothing at all. It does not gate a
    send either: `prompt_digest_note` says which of the two Falses this is,
    and callers that must not proceed on a count read the note, not the bool.
    """

    prompt_characters: int
    max_output_tokens: int
    retries: int
    units: int
    kind: str
    prompt_digest_matched: bool
    source: Source
    prompt_digest_note: str = ""

    def vouched(self) -> bool:
        """Whether the bound came from a committed prompt rather than a count.

        The narrow reading of the field, for a caller that needs a digest and
        will not accept a character count in its place.
        """
        return self.prompt_digest_matched


@dataclass(frozen=True)
class DispatchAllowance:
    """How many physical sends a study may make.

    A count of sends, and only ever a count of sends. The unit methods below
    refuse units outright, because a dispatch allowance converted to units was
    the invented number this module used to publish.
    """

    label: str
    max_dispatches: int | None
    source: Source
    charge: ProviderCharge

    @property
    def arithmetic(self) -> str:
        if self.max_dispatches is None:
            return "no dispatch count was authorized"
        return "%d physical dispatches authorized by %s" % (
            self.max_dispatches, self.source.artifact)

    def remaining_dispatches(self, spent: int) -> int | None:
        if self.max_dispatches is None:
            return None
        if spent < 0:
            raise ValueError("a spent count cannot be negative")
        return self.max_dispatches - spent



@dataclass(frozen=True)
class ReservationAllowance:
    """How many broker reservation units a new campaign needs to be admitted.

    Sized from the campaign's own frozen request bounds. A stand-in per
    dispatch constant would be exactly the invented number this replaces, so
    the only way to build one is from real requests the freeze vouched for.

    `is_derived` and `total_units` are one fact. A campaign whose sizing
    refused carries the reason in `refusal_reason` and no number, so a caller
    cannot read a default out of the absence.
    """

    label: str
    per_request: tuple[RequestEstimate, ...]
    total_units: int | None
    source: Source
    refusal_reason: str = ""

    @classmethod
    def unsized(cls, reason: str, label: str = "",
                source: Source | None = None) -> "ReservationAllowance":
        return cls(label=label, per_request=(), total_units=None,
                   source=source or Source("unknown", "unknown"),
                   refusal_reason=reason)

    @classmethod
    def for_request(cls, message_characters: int, max_output_tokens: int,
                    retries: int, *,
                    label: str = "single request",
                    prompt_digest_matched: bool = False,
                    prompt_digest_note: str = "",
                    source: Source | None = None
                    ) -> "ReservationAllowance":
        """One request, priced by the broker's own exposure schedule.

        The broker is called rather than re-derived, so this cannot drift
        from the number the store will actually take.

        The caller is priced a character count, not a prompt: the payload
        below is `x` repeated, so there are no prompt bytes here to compare
        against a committed digest. `prompt_digest_matched` therefore
        defaults to False and says so. It defaulted to True while the only
        thing that had been checked was that a length was supplied, which
        made the field a constant wearing an attestation.
        """
        payload = {
            "model": "unbound",
            "messages": [{"role": "user", "content": "x" * message_characters}],
            "max_output_tokens": max_output_tokens,
        }
        units, kind = _broker_exposure(payload, retries)
        estimate = RequestEstimate(
            prompt_characters=message_characters,
            max_output_tokens=max_output_tokens, retries=retries,
            units=units, kind=kind, prompt_digest_matched=prompt_digest_matched,
            source=source or Source("settlement.broker", "exposure_schedule"),
            prompt_digest_note=prompt_digest_note or (
                "priced from a character count: this site holds no prompt "
                "text, so no committed digest could have been compared"))
        return cls(label=label, per_request=(estimate,), total_units=units,
                   source=estimate.source)

    @property
    def is_derived(self) -> bool:
        return self.total_units is not None


@dataclass(frozen=True)
class LaunchPlan:
    """Both allowances for one campaign, and whether it may start.

    `carried_units_unchanged` is reported rather than spent. A new campaign is
    sized beside the old holds, never by discharging them.
    """

    dispatches: DispatchAllowance
    reservation: ReservationAllowance
    refusal_reason: str = ""
    carried_units_unchanged: int | None = None

    @property
    def may_launch(self) -> bool:
        return not self.refusal_reason


@dataclass(frozen=True)
class DispatchBudget:
    """A resume reading: ceiling, spent, remaining, in dispatches alone.

    There is no field a reservation unit could be put in, which is the point.
    """

    ceiling_dispatches: int | None
    spent_dispatches: int
    remaining_dispatches: int | None
    arithmetic: str
    refusal_reason: str = ""


def reserve_units(message_characters: int, max_output_tokens: int,
                  retries: int) -> int:
    return (message_characters // 4 + 1 + max_output_tokens) * (retries + 1)


def _broker_exposure(payload: Mapping[str, Any],
                     retries: int) -> tuple[int, str]:
    """The store's own answer for a request, from the broker itself.

    Importing the schedule rather than restating the formula is what makes
    the estimate a measurement of the store's behavior instead of a parallel
    implementation that can drift from it.
    """
    from settlement import broker
    from settlement.broker import MODEL_INFERENCE

    clean = broker.validate_effect(MODEL_INFERENCE, dict(payload))
    return broker.exposure_schedule(MODEL_INFERENCE, clean, int(retries))


def route_capacity_from_freeze(repo_root: Path | str = REPO_ROOT,
                               *,
                               freeze_relative: str = R4_EVIDENCE + "/freeze.json",
                               label: str = "free-550b"
                               ) -> DispatchAllowance:
    """The dispatch ceiling a study's own freeze committed.

    This is the only thing a freeze authorizes, so it is all that is read. A
    freeze carries no unit ceiling because a count of sends is not a
    denomination, and multiplying a send count by a price nobody reported is
    how this module came to claim an eight-dispatch study had a ceiling of
    zero units.
    """
    repo_root = Path(repo_root)
    limits = _read_json(repo_root, freeze_relative)["limits"]
    return DispatchAllowance(
        label=label,
        max_dispatches=int(limits["max_dispatches"]),
        source=Source(freeze_relative, "limits"),
        charge=_route_charge(repo_root),
    )


def _route_charge(repo_root: Path) -> ProviderCharge:
    """What the committed probe receipt said about a price, in one state.

    The probe is a single settled call, so it can report a charge or report
    that it reported none. It cannot speak for every later dispatch, which is
    why nothing here multiplies it by a count.

    The evidence file is read directly rather than through
    `s09_route_cost`, so the ledger's reading of a price does not depend on
    that module being importable.
    """
    try:
        record = _read_json(repo_root, PROBE_EVIDENCE)
    except (OSError, ValueError):
        return ProviderCharge.unmeasured(Source(PROBE_EVIDENCE, "absent"))
    receipt = record.get("receipt") if isinstance(record, Mapping) else None
    if not isinstance(receipt, Mapping) or receipt.get("outcome") != "success":
        return ProviderCharge.unmeasured(Source(PROBE_EVIDENCE, "absent"))
    return charge_from_receipt(
        receipt, Source(PROBE_EVIDENCE, "receipt.usage"))


def reservation_allowance_for_freeze(
        repo_root: Path | str = REPO_ROOT, *,
        freeze_relative: str = R4_EVIDENCE + "/freeze.json",
        freeze: Mapping[str, Any] | None = None,
        label: str = "free-550b"
        ) -> ReservationAllowance:
    """Size a campaign's reservation allowance from its own request bounds.

    A stand-in per-dispatch constant would make every campaign the same size
    regardless of what it sends, so the estimate is the broker's own answer
    for each request bound the campaign committed to.

    The cap sheet is the source for a new campaign. r4's freeze is the
    fallback, and it is a historical record: its prompts embed the task
    identifiers the instrument worlds published at the time, and those are
    now opaque, so r4's prompts no longer re-render against current source.
    That is the correct outcome, not a regression. A frozen campaign's sizing
    does not follow the source forward, and a new campaign must not inherit
    bounds priced from prompts it will not send.
    """
    repo_root = Path(repo_root)
    sized = _allowance_from_cap_sheet(repo_root, label)
    if sized is not None:
        return sized
    return _allowance_from_freeze(repo_root, freeze_relative, freeze, label)


def _allowance_from_cap_sheet(repo_root: Path, label: str
                              ) -> ReservationAllowance | None:
    """Price the committed cap sheet, or None when there is not one."""
    try:
        from experiments.ad01 import s09_cap_sheet
    except ImportError:
        return None
    if not Path(s09_cap_sheet.SHEET_RELATIVE).is_file():
        return None
    sheet = s09_cap_sheet.load()
    bounds = sheet.construction_bounds()
    # The sheet owns this product. `Sends` refuses arithmetic with an int on
    # purpose, so the multiplication happens where the two currencies are
    # both named and neither can be mistaken for the other.
    allowance_units = sheet.unit_allowance
    # The sheet commits a character count, not a prompt. Its `sheet_digest`
    # covers the sheet's own bytes, and the only prompt-shaped number it
    # holds is `construction_request.message_characters`. This site
    # therefore cannot produce a matching digest, and it used to assert one
    # anyway. It is the path a live campaign actually takes, so the record
    # this produced is the one a reader would have believed.
    matched, note = prompt_digest_verdict(None, None)
    per_request = (RequestEstimate(
        prompt_characters=bounds.message_characters,
        max_output_tokens=bounds.max_output_tokens, retries=0,
        units=allowance_units.per_request, kind=allowance_units.unit_kind,
        prompt_digest_matched=matched,
        prompt_digest_note=(
            "the cap sheet commits no prompt digest and this site holds no "
            "prompt text, so nothing vouches for these bounds (%s)" % note),
        source=Source("reports/cap-sheets", s09_cap_sheet.SHEET_ID)),)
    return ReservationAllowance(
        label=label, per_request=per_request,
        total_units=allowance_units.units,
        source=Source("reports/cap-sheets", s09_cap_sheet.SHEET_ID))


def _allowance_from_freeze(repo_root: Path, freeze_relative: str,
                           freeze: Mapping[str, Any] | None,
                           label: str) -> ReservationAllowance:
    repo_root = Path(repo_root)
    document = freeze if freeze is not None else _read_json(repo_root,
                                                            freeze_relative)
    digests = dict(document.get("prompt", {}).get("rendered_digests") or {})
    if not digests:
        return ReservationAllowance(
            label=label, per_request=(), total_units=None,
            source=Source(freeze_relative, "prompt.rendered_digests"),
            refusal_reason=("the freeze commits no prompt digest, so no "
                            "request bound is known and no reservation "
                            "allowance can be sized"))
    limits = dict(document.get("limits") or {})
    retries = int(limits.get("automatic_retries", 0))
    max_output = limits.get("max_output_tokens")
    if not isinstance(max_output, int) or max_output <= 0:
        return ReservationAllowance(
            label=label, per_request=(), total_units=None,
            source=Source(freeze_relative, "limits.max_output_tokens"),
            refusal_reason=("the freeze commits no max_output_tokens, so no "
                            "request bound is known and no reservation "
                            "allowance can be sized"))
    try:
        rendered = _render_frozen_prompts()
    except (ImportError, AttributeError, KeyError, TypeError) as exc:
        return ReservationAllowance(
            label=label, per_request=(), total_units=None,
            source=Source(freeze_relative, "prompt.rendered_digests"),
            refusal_reason=("the frozen source could not re-render its own "
                            "prompts (%s: %s), so no request bound is known"
                            % (type(exc).__name__, exc)))
    source = Source(freeze_relative, "prompt.rendered_digests + limits")
    estimates: list[RequestEstimate] = []
    for key, raw in sorted(rendered.items()):
        expected = digests.get(key)
        if expected is None:
            return ReservationAllowance(
                label=label, per_request=(), total_units=None, source=source,
                refusal_reason=("the freeze commits no rendered_digest for "
                                "%s, so its request bound is not known" % key))
        matched, note = prompt_digest_verdict(raw, expected)
        if not matched:
            return ReservationAllowance(
                label=label, per_request=(), total_units=None, source=source,
                refusal_reason=("the rendered_digest for %s does not match the "
                                "prompt the frozen source re-renders, so its "
                                "request bound is not known" % key))
        units, kind = _broker_exposure(
            {"model": str(document.get("route", {}).get("requested_model")
                          or "unbound"),
             "messages": [{"role": "user", "content": raw}],
             "max_output_tokens": max_output},
            retries)
        estimates.append(RequestEstimate(
            prompt_characters=len(raw), max_output_tokens=max_output,
            retries=retries, units=units, kind=kind,
            prompt_digest_matched=matched,
            prompt_digest_note=note,
            source=Source(freeze_relative, "prompt.rendered_digests[%s]" % key)))
    return ReservationAllowance(
        label=label, per_request=tuple(estimates),
        total_units=sum(estimate.units for estimate in estimates),
        source=source)


def _digest(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_digest_verdict(prompt: str | None,
                           committed: str | None) -> tuple[bool, str]:
    """Does a committed artifact carry the digest of these exact bytes?

    Returns `(matched, note)`. The comparison runs one way only: the bytes the
    code would render now, hashed, against a digest somebody committed. A
    caller that has no prompt text cannot match, and a caller that has no
    committed digest cannot match either, so both absences are False and both
    name themselves in the note.

    The direction matters. The alternative is to re-render the prompt the
    freeze recorded, which makes a freeze that predates the current source
    fail for every entry at once. That guard did exactly that: 0 of 8 against
    r4, on every arm, split and attempt, so it could not distinguish a drifted
    prompt from an unchanged one. A check that fails for everything carries no
    information, and one that passes for everything carries less.
    """
    if prompt is None:
        return False, ("no prompt text is in scope here, so no committed "
                       "digest was compared")
    if not committed:
        return False, ("no committed digest is in scope here, so nothing "
                       "vouches for these bytes")
    actual = _digest(prompt)
    if actual == committed:
        return True, "the committed digest is the digest of these bytes"
    return False, ("committed %s, these bytes hash to %s"
                  % (committed[:16], actual[:16]))


def _render_frozen_prompts() -> dict[str, str]:
    """Re-render every prompt the output study froze, from its own source.

    This is the same construction `scripts/invl02_live.py` performed to
    produce the freeze, so the prompts it returns are the ones the study will
    actually send rather than an approximation of them.
    """
    from experiments.ad01 import live_construct as live
    from experiments.ad01 import boolean_rule as rules
    from experiments.ad01 import rule_learner

    def session_for(split: str, seed: int):
        session = rules.RuleSession(rules.make_task(split, int(seed)))
        learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES,
                                                    int(seed))
        while session.remaining > 0:
            pick = learner.choose_query(dict(session.queried))
            if pick is None:
                break
            learner.observe(pick, session.query(pick))
        return session

    permitted = live.output_permitted_history()
    rendered: dict[str, str] = {}
    for arm, history in (("P1", []), ("P2", permitted)):
        for split, seed in live.OUTPUT_TASKS.items():
            public_input = session_for(split, seed).output_model_input()
            for attempt in (1, 2):
                key = "%s:%s:%d:a%d" % (arm, split, int(seed), attempt)
                rendered[key] = live.render_output_prompt(public_input, history,
                                                          attempt)
    return rendered


def launch_plan(dispatches: DispatchAllowance,
                reservation: ReservationAllowance,
                *,
                carried_units: int | None = None) -> LaunchPlan:
    """Pair a dispatch allowance with a sized reservation allowance.

    Neither is derived from the other, and the old holds are reported rather
    than spent. A plan is refused when either half cannot be stated, because a
    campaign sized from a half-answer is the failure being repaired.
    """
    if dispatches.max_dispatches is None:
        return LaunchPlan(
            dispatches=dispatches, reservation=reservation,
            refusal_reason=("no dispatch count was authorized, so a study "
                            "cannot be sized in sends either"),
            carried_units_unchanged=carried_units)
    if not reservation.is_derived:
        return LaunchPlan(
            dispatches=dispatches, reservation=reservation,
            refusal_reason=reservation.refusal_reason or (
                "the reservation allowance could not be sized"),
            carried_units_unchanged=carried_units)
    return LaunchPlan(dispatches=dispatches, reservation=reservation,
                      carried_units_unchanged=carried_units)


def resume_dispatch_budget(allowance: DispatchAllowance,
                           spent: int) -> DispatchBudget:
    """A resume reading, in dispatches alone.

    `spent` is a count of durable operations. No unit figure is accepted,
    and a spent count past the ceiling refuses rather than reporting a
    negative number of remaining sends.
    """
    if allowance.max_dispatches is None:
        return DispatchBudget(
            ceiling_dispatches=None, spent_dispatches=spent,
            remaining_dispatches=None,
            arithmetic="no dispatch count was authorized",
            refusal_reason=("no dispatch count was authorized, so no resume "
                            "count can be derived"))
    if spent < 0:
        raise ValueError("a spent dispatch count cannot be negative")
    remaining = allowance.max_dispatches - spent
    if remaining < 0:
        return DispatchBudget(
            ceiling_dispatches=allowance.max_dispatches,
            spent_dispatches=spent, remaining_dispatches=None,
            arithmetic="%d spent against a ceiling of %d" % (
                spent, allowance.max_dispatches),
            refusal_reason=("%d dispatches were already spent against a "
                            "ceiling of %d, so the run is over its allowance"
                            % (spent, allowance.max_dispatches)))
    return DispatchBudget(
        ceiling_dispatches=allowance.max_dispatches,
        spent_dispatches=spent, remaining_dispatches=remaining,
        arithmetic="%d authorized - %d already spent = %d dispatches remaining"
                   % (allowance.max_dispatches, spent, remaining))


def _read_json(repo_root: Path, relative: str) -> Mapping[str, Any]:
    return json.loads((repo_root / relative).read_text())


def _parse_ledger_reservations(ledger: str) -> tuple[
        dict[str, ReservationClaim], list[AbridgedClaim], list[str]]:
    table: dict[str, ReservationClaim] = {}
    lines = ledger.splitlines()
    for line in lines:
        row = LEDGER_ROW.match(line.strip())
        if row is not None:
            table[row.group("id")] = ReservationClaim(
                reservation_id=row.group("id"),
                amount=int(row.group("amount")),
                state=row.group("state"),
                source=Source(PROJECT_LEDGER, row.group("id")))
    abridged: list[AbridgedClaim] = []
    unresolved: list[str] = []
    for line in lines:
        fenced = LEDGER_FENCE_ROW.match(line.strip())
        if fenced is None or fenced.group("id") in table:
            continue
        citation = fenced.group("id")
        full = _expand_abbreviation(citation, table)
        if full is None:
            unresolved.append(citation)
            continue
        abridged.append(AbridgedClaim(
            abridged_id=citation, full_id=full,
            source=Source(PROJECT_LEDGER, citation)))
        table[full] = ReservationClaim(
            reservation_id=full,
            amount=int(fenced.group("amount")),
            state=fenced.group("state"),
            source=Source(PROJECT_LEDGER, citation,
                          "abbreviated citation of %s" % full))
    return table, abridged, unresolved


def _expand_abbreviation(citation: str,
                         table: Mapping[str, ReservationClaim]) -> str | None:
    if citation in table:
        return citation
    if "..." not in citation:
        return None
    head, tail = citation.split("...", 1)
    matches = [key for key in table
               if key.startswith(head) and key.endswith(tail)]
    return matches[0] if len(matches) == 1 else None


def _parse_ledger_arithmetic(ledger: str) -> tuple[ArithmeticCheck, ...]:
    source = Source(PROJECT_LEDGER, "live budget economics")
    checks = []
    for match in LEDGER_CORROBORATION.finditer(ledger):
        characters = int(match.group("characters"))
        max_output = int(match.group("max_output"))
        checks.append(ArithmeticCheck(
            label="stated reservation arithmetic",
            expression="%d // 4 + 1 + %d" % (characters, max_output),
            stated_units=int(match.group("units")),
            recomputed_units=reserve_units(characters, max_output, 0),
            inputs_source=source,
            inputs_evidence=Evidence.CARRIED_FORWARD,
        ))
    return tuple(checks)


def _dispatch_count(value: Any) -> int | str:
    """A bundle's dispatch count, kept as the number or the word it wrote.

    Since `c7d2952` a bundle whose store reconciliation did not confirm the
    count writes `"unknown"` in place of a number, and `int("unknown")` dies.
    The file's own convention is that a missing measurement is a state, not a
    zero: `ProviderCharge` makes one, `already_spent_in_store` returns `None`
    for it, and `offline_recompute` carries the string through. Anything that
    is not a nonnegative count is passed on unchanged so the claim stays a
    claim, and `DispatchClaim.counted` is where a caller reads a number.
    """
    if type(value) is int and value >= 0:
        return value
    return str(value)


def _r4_study(repo_root: Path,
              corroboration: ArithmeticCheck | None) -> StudyExposure:
    document = _read_json(repo_root, R4_RECONCILIATION)
    rows = document["durable_store_rows"]
    reservation = rows["reservation"]
    operation = rows["operation"]
    receipt = rows["receipt"]
    reconciliation = document["reconciliation"]
    bundle = document["bundle_claim"]
    locator = "durable_store_rows.reservation"
    return StudyExposure(
        study_root=document["study_root"],
        study_label="r4",
        reservation_id=reservation["id"],
        operation_id=reservation["operation_id"],
        dispatch_state=operation["dispatch_state"],
        reconcile_state=operation["reconcile_state"],
        settled=bool(operation["settled"]),
        units_uncertain=Units(int(reservation["amount"]),
                              Source(R4_RECONCILIATION, locator),
                              Evidence.VERIFIED),
        dispatch_claims=(
            DispatchClaim(int(reconciliation["physical_dispatches_spent"]),
                          Source(R4_RECONCILIATION,
                                 "reconciliation.physical_dispatches_spent")),
            DispatchClaim(_dispatch_count(bundle["dispatch_count"]),
                          Source(R4_EVIDENCE + "/" + bundle["file"],
                                 "bundle_claim.dispatch_count")),
        ),
        receipt_outcome=receipt["outcome"],
        corroborated_by_arithmetic=corroboration,
        bundle_under_reports_spend_by=int(
            reconciliation.get("bundle_under_reports_spend_by", 0)),
        held_reservation=HeldReservation(
            reservation_id=reservation["id"],
            operation_id=reservation["operation_id"],
            units=int(reservation["amount"]),
            state=str(reservation.get("state", "uncertain")),
            settled=bool(reservation.get("settled", operation["settled"])),
            study_root=document["study_root"],
            grant=_r4_grant(repo_root, document["study_root"]),
            source=Source(R4_RECONCILIATION, locator),
            computed_from_inputs=corroboration is not None
            and corroboration.agrees),
    )


def _r4_grant(repo_root: Path, study_root: str) -> Grant | None:
    """The authority r4's holds were taken against, read from its binding.

    The binding names the dispatch count and the route the grant covers, and
    says in its own scope that it expires with the study. Carrying the
    reference forward records who owed what, without implying the grant still
    authorizes anything.
    """
    try:
        document = _read_json(repo_root, R4_GRANT)
    except (OSError, ValueError):
        return None
    bound = document.get("bound_study") or {}
    if bound.get("study_root") != study_root:
        return None
    return Grant(
        grant_id="%s#%s" % (document.get("authorized_on", ""),
                            str(bound.get("protocol", ""))),
        study_root=study_root,
        authorized_units=None,
        authorized_on=str(document.get("authorized_on", "")),
        scope=tuple(document.get("scope_limits") or ()),
        source=Source(R4_GRANT, "bound_study + bound_limits + scope_limits"),
    )


def _older_ad01_study(repo_root: Path, claim: ReservationClaim,
                      corroboration: ArithmeticCheck | None) -> StudyExposure:
    bundle = _read_json(repo_root, OLDER_BUNDLE)
    attempts = bundle.get("ledger", [])
    operation_ids = {entry["operation_id"] for entry in attempts}
    claims = [
        DispatchClaim(len(attempts), Source(OLDER_BUNDLE, "ledger entries")),
        DispatchClaim(int(bundle["live"]["model_calls"]),
                      Source(OLDER_BUNDLE, "live.model_calls")),
    ]
    operation_id = ""
    if len(operation_ids) == 1:
        operation_id = next(iter(operation_ids))
        claims.append(DispatchClaim(
            len(operation_ids), Source(OLDER_BUNDLE, "distinct operation_id")))
    settled = StudyExposure(
        study_root=bundle["study"],
        study_label="older-ad01",
        reservation_id=claim.reservation_id,
        operation_id=operation_id,
        dispatch_state="unresolved",
        reconcile_state="unresolved",
        settled=False,
        units_uncertain=Units(claim.amount, claim.source,
                              Evidence.CARRIED_FORWARD),
        dispatch_claims=tuple(claims),
        receipt_outcome=(attempts[0]["diagnosis"]["kind"] if attempts else ""),
        corroborated_by_arithmetic=corroboration,
        held_reservation=HeldReservation(
            reservation_id=claim.reservation_id,
            operation_id=operation_id,
            units=claim.amount,
            state="uncertain",
            settled=False,
            study_root=bundle["study"],
            grant=None,
            source=claim.source,
            computed_from_inputs=False),
    )
    return _reconciled_older(repo_root, settled)


def _reconciled_older(repo_root: Path,
                      study: StudyExposure) -> StudyExposure:
    """Prefer the durable row over the bundle that described it.

    The prose figure was carried forward because no committed artifact
    carried the reservation inputs. They turned out to be readable, so the
    units are recomputed from the same row the broker reserved against. That
    changes what kind of evidence the number is, not whether it is owed: a
    verified figure on a still-uncertain reservation is still a debt.
    """
    try:
        document = _read_json(repo_root, OLDER_RECONCILIATION)
    except (OSError, ValueError):
        return study
    rows = document.get("durable_store_rows", {})
    reservation = rows.get("reservation", {})
    operation = rows.get("operation", {})
    recomputation = document.get("reservation_recomputation", {})
    if reservation.get("id") != study.reservation_id \
            or not recomputation.get("agrees"):
        return study
    return replace(
        study,
        study_root=document.get("study_root", study.study_root),
        dispatch_state=operation.get("dispatch_state",
                                     study.dispatch_state),
        reconcile_state=operation.get("reconcile_state",
                                      study.reconcile_state),
        settled=bool(operation.get("settled", study.settled)),
        units_uncertain=Units(
            int(recomputation["recomputed_units"]),
            Source(OLDER_RECONCILIATION,
                   "durable_store_rows.reservation + reservation_recomputation"),
            Evidence.VERIFIED),
        receipt_outcome=rows.get("receipt", {}).get(
            "outcome", study.receipt_outcome),
        held_reservation=_older_held_reservation(study, reservation, operation,
                                                 recomputation, document),
    )


def _older_held_reservation(study: StudyExposure,
                            reservation: Mapping[str, Any],
                            operation: Mapping[str, Any],
                            recomputation: Mapping[str, Any],
                            document: Mapping[str, Any]
                            ) -> HeldReservation:
    """The hold this study still owes, with the grant it was taken against.

    `agrees` gates the whole record. A recomputation that did not reproduce
    the reservation row leaves the units carried rather than verified, and the
    hold says so instead of claiming a derivation that did not happen.
    """
    authority = document.get("durable_store_rows", {}).get("study_authority", {})
    grant = None
    if authority.get("allocation_id"):
        grant = Grant(
            grant_id=str(authority.get("allocation_id")),
            study_root=str(authority.get("study_root",
                                         study.study_root)),
            authorized_units=authority.get("authorized_units"),
            source=Source(OLDER_RECONCILIATION, "durable_store_rows.study_authority"),
        )
    return HeldReservation(
        reservation_id=str(reservation.get("id", study.reservation_id)),
        operation_id=str(reservation.get("operation_id",
                                         study.operation_id)),
        units=int(recomputation.get("recomputed_units", study.units_uncertain.value)),
        state=str(reservation.get("state", "uncertain")),
        settled=bool(operation.get("settled", study.settled)),
        study_root=str(document.get("study_root", study.study_root)),
        grant=grant,
        source=Source(OLDER_RECONCILIATION, "durable_store_rows.reservation"),
        computed_from_inputs=bool(recomputation.get("agrees")),
    )


def _settled_study(repo_root: Path, claim: ReservationClaim) -> StudyExposure:
    for path in sorted((repo_root / EVIDENCE_ROOT).rglob("output-run.json")):
        document = json.loads(path.read_text())
        view = document.get("candidate_view", {})
        for receipt in view.get("durable_receipts", []):
            if receipt.get("reservation_id") != claim.reservation_id:
                continue
            return StudyExposure(
                study_root=document.get("study_root", ""),
                study_label="settled-output-shape",
                reservation_id=claim.reservation_id,
                operation_id=receipt["operation_id"],
                dispatch_state=receipt["dispatch_state"],
                reconcile_state=receipt["reconcile_state"],
                settled=bool(receipt["settled"]),
                units_uncertain=Units(0, claim.source, Evidence.VERIFIED),
                dispatch_claims=(DispatchClaim(
                    _dispatch_count(view["dispatch_count"]),
                    Source(path.relative_to(repo_root).as_posix(),
                           "candidate_view.dispatch_count")),),
                receipt_outcome=receipt.get("receipt_outcome", ""),
                corroborated_by_arithmetic=None,
            )
    raise KeyError(claim.reservation_id)


def prior_exposure(repo_root: Path | str = REPO_ROOT) -> PriorExposure:
    repo_root = Path(repo_root)
    ledger = (repo_root / PROJECT_LEDGER).read_text()
    table, abridged, unresolved = _parse_ledger_reservations(ledger)
    if not table:
        raise ValueError("no reservation rows in %s" % PROJECT_LEDGER)
    checks = _parse_ledger_arithmetic(ledger)
    studies = []
    for claim in table.values():
        if claim.state == "settled":
            studies.append(_settled_study(repo_root, claim))
            continue
        corroboration = checks[0] if claim.reservation_id.startswith(
            R4_RESERVATION_PREFIX) and checks else None
        if claim.reservation_id.startswith(R4_RESERVATION_PREFIX):
            studies.append(_r4_study(repo_root, corroboration))
            continue
        studies.append(_older_ad01_study(
            repo_root, claim,
            checks[1] if len(checks) > 1 else None))
    return PriorExposure(
        repo_root=repo_root,
        census_source=Source(PROJECT_LEDGER, "every reservation row naming a study"),
        studies=tuple(sorted(studies, key=lambda item: item.study_label)),
        settled_units=sum(claim.amount
                          for claim in table.values()
                          if claim.state == "settled"),
        corroborations=checks,
        abridged_claims=tuple(abridged),
        unresolved_citations=tuple(unresolved),
    )


@dataclass(frozen=True)
class ConservativeTotal:
    terms: tuple[tuple[str, Units], ...]
    arithmetic: str
    all_verified: bool

    @property
    def value(self) -> int:
        return sum(units.value for _, units in self.terms)


def conservative_total(prior: PriorExposure) -> ConservativeTotal:
    terms = sorted(
        ((study.study_label, study.carried_units())
         for study in prior.studies if study.contributes_to_liability),
        key=lambda item: item[1].value)
    arithmetic = " + ".join(
        "%s %d %s" % (label, units.value, units.evidence.value)
        for label, units in terms)
    return ConservativeTotal(
        terms=tuple(terms),
        arithmetic="%s = %d units" % (arithmetic, sum(u.value for _, u in terms)),
        all_verified=all(units.verified for _, units in terms),
    )


def _bold_unit_totals(memory_dir: Path) -> tuple[tuple[Source, int], ...]:
    found = []
    for path in sorted(memory_dir.glob("*.md")):
        for match in BOLD_UNIT_TOTAL.finditer(path.read_text()):
            found.append((Source(path.name, "stated total"),
                          int(match.group("amount"))))
    return tuple(found)


def conflicts(prior: PriorExposure,
              memory_dir: Path | None = None) -> tuple[Conflict, ...]:
    found = []
    for study in prior.studies:
        if study.dispatch_count_disputed:
            found.append(Conflict(
                subject="dispatch count for %s" % study.study_label,
                positions=tuple(claim.label() for claim in study.dispatch_claims),
                resolution="take the larger; the durable store outranks a bundle"))
        if study.study_root and study.reservation_id.startswith(
                "res-invl02-output-"):
            held = _study_root_from_dispatch_claim(study)
            if held is not None and held != study.study_root:
                found.append(Conflict(
                    subject="study root of %s" % study.study_label,
                    positions=(study.study_root, "held in %s" % held),
                    resolution=("report both; the row is settled so it "
                                "contributes no liability")))
    if prior.unresolved_citations:
        found.append(Conflict(
            subject="reservation ids cited outside the ledger table",
            positions=prior.unresolved_citations,
            resolution=("unresolved; the table row governs, and an uncitable id "
                        "cannot be reconciled")))
    total = conservative_total(prior).value
    for source, amount in _memory_totals(prior, memory_dir):
        if amount != total:
            found.append(Conflict(
                subject="stated unsettled total",
                positions=("recomputed %d from %s"
                           % (total, prior.census_source.artifact),
                           "%d from %s" % (amount, source.artifact)),
                resolution="take the larger figure, %d" % max(amount, total)))
    return tuple(found)


def _memory_totals(prior: PriorExposure,
                   memory_dir: Path | None) -> tuple[tuple[Source, int], ...]:
    if memory_dir is None or not memory_dir.is_dir():
        return ()
    return _bold_unit_totals(memory_dir)


def _study_root_from_dispatch_claim(study: StudyExposure) -> str | None:
    for claim in study.dispatch_claims:
        directory = claim.source.artifact.rsplit("/", 1)[0]
        if directory.startswith(EVIDENCE_ROOT + "/"):
            return directory.rsplit("/", 1)[-1]
    return None


def provenance_warnings(prior: PriorExposure) -> tuple[ProvenanceWarning, ...]:
    warnings = []
    for study in prior.studies:
        if study.bundle_under_reports_spend_by:
            bundle = _read_json(prior.repo_root, R4_BUNDLE)
            warnings.append(ProvenanceWarning(
                code="r4-crash-under-report",
                detail=("%s claims dispatch_count=%s with status %r, while the "
                        "durable store records %d physical dispatches"
                        % (R4_BUNDLE,
                           bundle["candidate_view"]["dispatch_count"],
                           bundle["status"], study.max_dispatch_claims)),
                consequence=("a ceiling derived from that file is unsound; read "
                             "durable operations instead"),
                sources=(Source(R4_RECONCILIATION, "reconciliation"),
                         Source(R4_BUNDLE, "candidate_view"))))
        elif study.dispatch_count_disputed:
            warnings.append(ProvenanceWarning(
                code="%s-attempt-count-disputed" % study.study_label,
                detail="dispatch claims are %s" % ", ".join(
                    claim.label() for claim in study.dispatch_claims),
                consequence=("one uncertain reservation covers one operation, "
                             "so a higher attempt count means the reservation "
                             "may understate real sends"),
                sources=tuple(claim.source for claim in study.dispatch_claims)))
    for check in prior.corroborations:
        if check.agrees:
            continue
        warnings.append(ProvenanceWarning(
            code="reservation-arithmetic-mismatch",
            detail=check.label_text(),
            consequence="the stated unit figure cannot be recomputed",
            sources=(check.inputs_source,)))
    for abridged in prior.abridged_claims:
        warnings.append(ProvenanceWarning(
            code="abridged-reservation-citation",
            detail=("%s cites %s" % (abridged.source.artifact,
                                      abridged.abridged_id)),
            consequence=("the citation is lossy; the unabridged table row %s "
                         "governs" % abridged.full_id),
            sources=(abridged.source,)))
    warnings.append(ProvenanceWarning(
        code="units-are-reservations-not-billing",
        detail=("every figure is a broker reservation estimate in units per %s, "
                "not tokens or billing, and the free route reports unknown usage"
                % RESERVATION_FORMULA),
        consequence="treat the reserved total as exposure, never as a cost",
        sources=(Source(PROJECT_LEDGER, "live budget economics"),)))
    return tuple(warnings)


def ledger_report(repo_root: Path | str = REPO_ROOT,
                  memory_dir: Path | None = None) -> dict[str, Any]:
    prior = prior_exposure(repo_root)
    total = conservative_total(prior)
    return {
        "prior_exposure": [
            {
                "study": study.study_label,
                "study_root": study.study_root,
                "reservation_id": study.reservation_id,
                "operation_id": study.operation_id,
                "dispatch_state": study.dispatch_state,
                "reconcile_state": study.reconcile_state,
                "settled": study.settled,
                "units_uncertain": study.units_uncertain.value,
                "units_evidence": study.units_uncertain.evidence.value,
                "units_source": asdict(study.units_uncertain.source),
                "carried_units": study.carried_units().value,
                "dispatch_claims": [
                    {"dispatches": claim.value, "source": asdict(claim.source)}
                    for claim in study.dispatch_claims],
                "receipt_outcome": study.receipt_outcome,
                "arithmetic_corroboration": (
                    asdict(study.corroborated_by_arithmetic)
                    if study.corroborated_by_arithmetic else None),
            }
            for study in prior.studies
        ],
        "conservative_total": {
            "units": total.value,
            "arithmetic": total.arithmetic,
            "all_terms_verified": total.all_verified,
            "settled_units_excluded": prior.settled_units,
        },
        "conflicts": [conflict.report()
                      for conflict in conflicts(prior, memory_dir)],
        "provenance_warnings": [
            {"code": warning.code, "detail": warning.detail,
             "consequence": warning.consequence,
             "sources": [asdict(source) for source in warning.sources]}
            for warning in provenance_warnings(prior)
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--memory-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    print(json.dumps(ledger_report(args.repo_root, args.memory_dir),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
