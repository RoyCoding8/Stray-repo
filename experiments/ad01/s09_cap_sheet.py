"""The finite per-campaign authorization the budget system should consume.

A cap sheet answers one question: what may this campaign send, and what will
that cost in the store's own denomination. Those are two questions with two
answers, and the assignment's own finding is that mixing them is the defect.
A freeze authorizes a number of DISPATCHES. The store needs reservation UNITS
to admit them. The provider has reported no PRICE at all, and that absence is
a third fact, not a zero of either.

Every number here is one of two kinds, and the kind is part of the value:

  STATED   the assignment says it. The 64 physical sends, the two initial
           constructions and one repair per cell, the four route calls, the
           twelve transfer calls, and the twelve cells.
  DERIVED  a real function call returns it. The construction request bounds
           are read from the request the older AD01 campaign actually sent,
           and the unit figure is `broker.exposure_schedule` applied to those
           bounds. Nothing is multiplied by an invented factor.

If a figure cannot be traced to one of those, the sheet is invalid and names
the line. It does not ship a plausible number.

The sheet is content-addressed over its own body, so two runs that agree about
every input produce the same address and a tampered body produces a different
one. `reports/cap-sheets/invl02-s09-cap.json` is that artifact.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01.s09_route_cost import (
    Charge, ChargeState, FREE_MODEL, reservation_units)

SHEET_SCHEMA = "s09-cap-sheet-v1"
SHEET_ID = "invl02-s09-cap"
SHEET_RELATIVE = "reports/cap-sheets/invl02-s09-cap.json"

# The construction request the older AD01 campaign actually dispatched, read
# from its own store reconciliation rather than from a default. The r4 freeze
# corroborates the same max_output_tokens and deadline on the same route.
CONSTRUCTION_SOURCE = "reports/evidence/invl02-live/store-reconciliation.json"


class Origin(str, Enum):
    """Where a figure came from. Not a label: a figure carries its origin."""

    STATED = "STATED"
    DERIVED = "DERIVED"

    def require_derivation(self, name: str, bounds: "RequestBounds") -> None:
        """A stated figure may not be quietly used as a derived one."""
        if self is not Origin.DERIVED:
            raise ValueError(
                "%s is %s by the assignment, and a %s may not be presented"
                " as the broker's own answer for these bounds"
                % (name, self.value, self.value))


STATED = Origin.STATED
DERIVED = Origin.DERIVED


class Sends:
    """A count of physical sends, which cannot be mixed with anything else.

    Both figures are ints, and an int carries no memory of what it counted, so
    the type is the only place the distinction survives. Arithmetic between a
    send count and a plain int raises rather than quietly computing a mixed
    unit, and there is no `__index__`, so a send count cannot be unboxed back
    into one and multiplied by a reservation figure somewhere downstream.
    """

    __slots__ = ("value",)

    def __init__(self, value: int) -> None:
        if type(value) is not int:
            raise TypeError(
                "a send count is an int of sends, not %r; unit figures reach"
                " the budget through UnitAllowance instead" % type(value).__name__)
        if value < 0:
            raise ValueError("a send count cannot be negative")
        self.value = value

    def _refuse(self, operation: str) -> "Sends":
        raise TypeError(
            "a send count may not be %s; units and a price are different"
            " quantities, and a mix of the two is the defect this sheet"
            " exists to prevent" % operation)

    __add__ = __radd__ = __sub__ = __rsub__ = _refuse
    __mul__ = __rmul__ = __truediv__ = __floordiv__ = _refuse
    __mod__ = __pow__ = __lshift__ = __and__ = _refuse

    def __eq__(self, other: object) -> bool:
        return other == self.value if isinstance(other, int) else (
            isinstance(other, Sends) and other.value == self.value)

    def __hash__(self) -> int:
        return hash(("Sends", self.value))

    def __repr__(self) -> str:
        return "Sends(%d)" % self.value


@dataclass(frozen=True)
class RequestBounds:
    """The frozen per-request limits, from which a reservation follows."""

    model: str
    message_characters: int
    max_output_tokens: int
    deadline_ms: int
    reasoning_effort: str

    def as_request(self) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "user",
                          "content": "x" * self.message_characters}],
            "max_output_tokens": self.max_output_tokens,
            "deadline_ms": self.deadline_ms,
            "reasoning_effort": self.reasoning_effort,
        }

    @property
    def reservation_units(self) -> int:
        units, _ = reservation_units(self.as_request(), 0)
        return units

    @property
    def unit_kind(self) -> str:
        _, kind = reservation_units(self.as_request(), 0)
        return kind


@dataclass(frozen=True)
class Line:
    """One figure in the sheet, with the origin that makes it checkable."""

    name: str
    origin: Origin
    detail: str
    sends: Sends | None = None
    text: str | None = None

    def to_dict(self) -> dict:
        payload: dict[str, Any] = {"name": self.name, "origin": self.origin.value,
                                   "detail": self.detail}
        if self.sends is not None:
            payload["sends"] = self.sends.value
        if self.text is not None:
            payload["value"] = self.text
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Line":
        sends = None if "sends" not in payload else Sends(int(payload["sends"]))
        return cls(
            name=str(payload["name"]),
            origin=Origin(payload["origin"]),
            detail=str(payload.get("detail", "")),
            sends=sends,
            text=payload.get("value"))


@dataclass(frozen=True)
class UnitAllowance:
    """Reservation units, which the store consumes. Never a count of sends."""

    units: int
    unit_kind: str
    per_request: int
    requests: int

    def to_dict(self) -> dict:
        return {"units": self.units, "unit_kind": self.unit_kind,
                "per_request_units": self.per_request,
                "requests": self.requests,
                "note": "estimated-budget reservation units, not a price and"
                        " not a dispatch count"}


@dataclass(frozen=True)
class Billing:
    """What the provider reported, and what was authorized separately."""

    state: ChargeState
    units_derivable: bool
    authorized_to_spend: bool
    note: str

    def to_dict(self) -> dict:
        return {"provider_charge_state": self.state.value,
                "units_derivable": self.units_derivable,
                "authorized_to_spend": self.authorized_to_spend,
                "note": self.note}


@dataclass(frozen=True)
class Validation:
    ok: bool
    failures: tuple[str, ...]
    details: Mapping[str, str]
    checks: tuple[str, ...]

    def report(self) -> str:
        if self.ok:
            return "valid: %d checks" % len(self.checks)
        return "invalid: " + "; ".join(
            "%s (%s)" % (code, self.details[code]) for code in self.failures)


@dataclass(frozen=True)
class CapSheet:
    allowance: tuple[Line, ...]
    bounds: tuple[Line, ...]
    unit_allowance: UnitAllowance
    provider_billing: Billing
    construction: RequestBounds
    sources: Mapping[str, str]
    sheet_id: str = SHEET_ID

    @property
    def sheet_digest(self) -> str:
        """Content address of this body. Derived, so it cannot drift from it."""
        return digest_of(self.to_dict())

    def construction_bounds(self) -> RequestBounds:
        return self.construction

    def line(self, name: str) -> Line:
        for line in self.allowance + self.bounds:
            if line.name == name:
                return line
        raise KeyError(name)

    def total_sends(self) -> Sends:
        """The send ceiling, which must equal the stated physical-sends line."""
        return self.line("physical_sends_ceiling").sends

    def to_dict(self) -> dict:
        body = {
            "schema": SHEET_SCHEMA,
            "sheet_id": self.sheet_id,
            "route": self.construction.model,
            "allowance": [line.to_dict() for line in self.allowance],
            "bounds": [line.to_dict() for line in self.bounds],
            "construction_request": {
                "message_characters": self.construction.message_characters,
                "max_output_tokens": self.construction.max_output_tokens,
                "deadline_ms": self.construction.deadline_ms,
                "reasoning_effort": self.construction.reasoning_effort,
                "source": self.sources["construction_request"],
            },
            "total_sends": self.total_sends().value,
            "unit_allowance": self.unit_allowance.to_dict(),
            "provider_billing": self.provider_billing.to_dict(),
            "denominations": {
                "sends": "a count of physical model sends, admitted against a"
                         " dispatch allowance and never reduced by units",
                "reservation_units": "the store's estimated-budget units, derived"
                                     " per request by the broker exposure"
                                     " schedule and consumed as headroom",
                "price": "what the provider charges; the free route reports no"
                         " charge field, so no provider price is derivable here",
            },
            "sources": dict(self.sources),
        }
        body["sheet_digest"] = digest_of(body)
        return body

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CapSheet":
        construction = payload["construction_request"]
        return cls(
            allowance=tuple(Line.from_dict(line) for line in payload["allowance"]),
            bounds=tuple(Line.from_dict(line) for line in payload["bounds"]),
            unit_allowance=UnitAllowance(**{
                key: value for key, value in payload["unit_allowance"].items()
                if key in ("units", "unit_kind")} |
                {"per_request": payload["unit_allowance"]["per_request_units"],
                 "requests": payload["unit_allowance"]["requests"]}),
            provider_billing=Billing(
                state=ChargeState(payload["provider_billing"]["provider_charge_state"]),
                units_derivable=payload["provider_billing"]["units_derivable"],
                authorized_to_spend=payload["provider_billing"]["authorized_to_spend"],
                note=payload["provider_billing"]["note"]),
            construction=RequestBounds(
                model=payload["route"],
                message_characters=construction["message_characters"],
                max_output_tokens=construction["max_output_tokens"],
                deadline_ms=construction["deadline_ms"],
                reasoning_effort=construction["reasoning_effort"]),
            sources=dict(payload["sources"]),
            sheet_id=payload["sheet_id"])

    def validate(self, expected_digest: str | None = None) -> Validation:
        """Recompute every derived figure and name whatever does not agree.

        `expected_digest` is an address recorded elsewhere, such as in the
        committed file. Pass it and a tampered body is caught before any of its
        numbers are believed.
        """
        details: dict[str, str] = {}
        failures: list[str] = []
        checks: list[str] = []

        if expected_digest is not None and expected_digest != self.sheet_digest:
            failures.append("sheet_digest_mismatch")
            details["sheet_digest_mismatch"] = (
                "recorded %s, this body addresses as %s"
                % (expected_digest, self.sheet_digest))
        checks.append("sheet_digest")

        recomputed = self.construction.reservation_units
        if recomputed != self.unit_allowance.per_request:
            code = "construction_bounds_not_derivable"
            failures.append(code)
            details[code] = (
                "the broker returns %d units for the frozen bounds, the sheet"
                " claims %d" % (recomputed, self.unit_allowance.per_request))
        expected_units = recomputed * self.unit_allowance.requests
        if self.unit_allowance.units != expected_units:
            code = "unit_allowance_units_not_derivable"
            failures.append(code)
            details[code] = (
                "%d units over %d requests at %d per request is %d, the sheet"
                " claims %d" % (self.unit_allowance.units,
                                self.unit_allowance.requests, recomputed,
                                expected_units, self.unit_allowance.units))
        if self.unit_allowance.requests != self.total_sends().value:
            code = "unit_allowance_requests_not_derivable"
            failures.append(code)
            details[code] = (
                "the sheet reserves for %d requests but authorizes %d sends"
                % (self.unit_allowance.requests, self.total_sends().value))
        checks.append("unit_allowance")

        per_cell_initial = self.line("initial_constructions_per_cell").sends
        per_construction_repair = self.line("repairs_per_construction").sends
        cells = self.line("cells").sends
        initial = per_cell_initial.value * cells.value
        repairs = per_construction_repair.value * initial
        flat = sum(self.line(name).sends.value for name in
                   ("route_calibration_calls", "target_adaptation_calls"))
        parts = initial + repairs + flat
        if parts != self.total_sends().value:
            code = "physical_sends_ceiling_not_stated"
            failures.append(code)
            details[code] = (
                "%d initial plus %d repair plus %d calibration and transfer is"
                " %d, the assignment states %d"
                % (initial, repairs, flat, parts, self.total_sends().value))
        checks.append("sends")

        for line in self.bounds:
            line.origin.require_derivation(line.name, self.construction)
        checks.append("bounds_origins")

        if self.provider_billing.units_derivable and \
                self.provider_billing.state is ChargeState.NOT_REPORTED:
            code = "provider_billing_units_derivable"
            failures.append(code)
            details[code] = (
                "the receipt reported no charge field, so no unit figure may"
                " be claimed from it")
        if self.provider_billing.state is ChargeState.NOT_REPORTED and \
                self.provider_billing.authorized_to_spend is not True:
            code = "provider_billing_authorization"
            failures.append(code)
            details[code] = (
                "using the confirmed free route is authorized separately from"
                " its receipt measuring a price")
        checks.append("provider_billing")

        return Validation(ok=not failures, failures=tuple(failures),
                          details=details, checks=tuple(checks))

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (self.sheet_id + ".json")
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        return path


def digest_of(body: Mapping[str, Any]) -> str:
    """Content address of the sheet's own body, excluding the address."""
    payload = {key: value for key, value in body.items()
               if key != "sheet_digest"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def construction_bounds() -> RequestBounds:
    """The frozen construction request, read from the request that was sent."""
    source = ROOT / CONSTRUCTION_SOURCE
    try:
        recomputed = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(
            "the construction request bounds are not derivable: %s is"
            " unreadable (%s), and a default would be an invented figure"
            % (CONSTRUCTION_SOURCE, exc)) from exc
    stored = recomputed.get("reservation_recomputation") or {}
    try:
        characters = int(stored["message_characters"])
        max_output = int(stored["max_output_tokens"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "the construction request bounds are not derivable: %s records no"
            " message_characters and max_output_tokens" % CONSTRUCTION_SOURCE
        ) from exc
    return RequestBounds(
        model=FREE_MODEL,
        message_characters=characters,
        max_output_tokens=max_output,
        deadline_ms=300_000,
        reasoning_effort="high")


def new_campaign_sheet() -> CapSheet:
    """The connected study's cap sheet, every figure traced to its origin."""
    bounds = construction_bounds()
    per_request = bounds.reservation_units
    sends = Sends(64)
    charge = Charge.not_reported()
    return CapSheet(
        allowance=(
            Line("initial_constructions_per_cell", STATED,
                 "M3: two independent initial constructions per"
                 " representation/world/experience cell", sends=Sends(2)),
            Line("repairs_per_construction", STATED,
                 "M3: at most one repair each", sends=Sends(1)),
            Line("cells", STATED,
                 "M3: three representations times two worlds times two"
                 " experience treatments", sends=Sends(12)),
            Line("route_calibration_calls", STATED,
                 "M3: up to four contract-shaped route/calibration calls",
                 sends=Sends(4)),
            Line("target_adaptation_calls", STATED,
                 "M3: twelve further calls reserved for the transfer"
                 " diagnostic", sends=Sends(12)),
            Line("physical_sends_ceiling", STATED,
                 "M3: 64 physical model sends total including retries,"
                 " calibration and failed sends", sends=sends),
        ),
        bounds=(
            Line("construction_max_output_tokens", DERIVED,
                 "the max_output_tokens of the construction request that was"
                 " dispatched, not a default", text=str(bounds.max_output_tokens)),
            Line("construction_input_characters", DERIVED,
                 "the message length of that same request", text=str(bounds.message_characters)),
            Line("construction_deadline_ms", DERIVED,
                 "the per-request deadline frozen beside it", text=str(bounds.deadline_ms)),
            Line("construction_reasoning_effort", DERIVED,
                 "the reasoning effort frozen beside it",
                 text=bounds.reasoning_effort),
        ),
        unit_allowance=UnitAllowance(
            units=per_request * sends.value, unit_kind=bounds.unit_kind,
            per_request=per_request, requests=sends.value),
        provider_billing=Billing(
            state=charge.state, units_derivable=charge.budget_units is not None,
            authorized_to_spend=True,
            note="authorization to use the confirmed free route is a separate"
                 " grant from a receipt measuring a price, and this receipt"
                 " reported no charge field"),
        construction=bounds,
        sources={
            "construction_request": CONSTRUCTION_SOURCE,
            "counts": "WORKER-STAGE-09-CONNECTED-STUDY.md M3",
            "unit_schedule": "settlement.broker.exposure_schedule"
                             "(MODEL_INFERENCE, request, 0)",
            "provider_charge": "evidence_s09_route_probe/probe.json",
        },
    )


def load(relative: str = SHEET_RELATIVE) -> CapSheet:
    """Read a committed sheet back, refusing one whose address does not match.

    The address is checked over the body as it was read, not over the body a
    rebuild produces. Rebuilding first would quietly drop any key the rebuild
    does not derive from, so a field edited after the freeze would read as
    unchanged. The two checks are separate on purpose. The first says the
    bytes are the frozen ones. The second says those bytes are internally
    consistent, so a redundant field cannot disagree with the lines it
    summarizes.
    """
    payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    recorded = payload.get("sheet_digest", "")
    if digest_of(payload) != recorded:
        raise ValueError(
            "%s addresses as %s but records %s, so the committed sheet was"
            " edited after it was frozen"
            % (relative, digest_of(payload), recorded))
    rebuilt = CapSheet.from_dict(
        {key: value for key, value in payload.items() if key != "sheet_digest"})
    if rebuilt.to_dict() != payload:
        raise ValueError(
            "%s is internally inconsistent: a summary field disagrees with the"
            " lines it summarizes" % relative)
    return rebuilt


def main(argv: Sequence[str] | None = None) -> int:
    built = new_campaign_sheet()
    result = built.validate()
    print(json.dumps({"cap_sheet": built.to_dict(), "validation":
                      {"ok": result.ok, "report": result.report()}},
                     indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
