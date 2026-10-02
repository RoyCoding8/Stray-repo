"""What the free route actually reports, read as the three things it can say.

The preflight refused a budget because no units-per-dispatch figure existed,
and inventing one would have been the exact failure this campaign is about.
So one settled live call was made on the confirmed free route and the receipt
was committed at `evidence_s09_route_probe/probe.json`.

That receipt says the call happened, it succeeded, and it carried no charge
field. The third is an absence. It is not a measured zero, and an earlier
version of this module rendered it as "the provider charges nothing for this
call" and then converted the null into an integer zero stamped VERIFIED on the
strength of a settled receipt. The receipt verified a call. It verified no
price. `Charge` is the type that refuses the collapse.

The 25 units that admission required are still real, and they are not a
constant either. They are what the broker's exposure schedule returns for the
one 33-character, 16-output-token smoke request that was actually made, and
`reservation_units` recomputes that number for any request. The same schedule
returns 3269 for the 4880-character construction request the older campaign
sent. A smoke request's reservation is not a conversion rate, so nothing in
this module stores one.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

EVIDENCE = ROOT / "evidence_s09_route_probe" / "probe.json"
FREE_MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_DEADLINE_MS = 300_000


class ChargeState(str, Enum):
    """The three things a receipt can say about a charge, kept apart.

    REPORTED is an amount the response carried. NOT_REPORTED is a settled
    receipt with no charge field, which is an absence and not a zero.
    UNMEASURED is no committed receipt at all, which is not even a receipt.
    """

    REPORTED = "REPORTED"
    NOT_REPORTED = "NOT_REPORTED"
    UNMEASURED = "UNMEASURED"


@dataclass(frozen=True)
class Charge:
    """A provider charge in one of three states, never a number or nothing.

    `budget_units` is None for both absent states, so a caller cannot consume
    either one as a zero. Constructing NOT_REPORTED or UNMEASURED with a
    number is refused, which makes the old conversion unrepresentable rather
    than merely discouraged.
    """

    state: ChargeState
    units: int | None = None
    billed: bool | None = None
    charge_scale: int | None = None

    def __post_init__(self) -> None:
        if self.state is ChargeState.REPORTED and self.units is None:
            raise ValueError("a REPORTED charge needs the amount the receipt carried")
        if self.state is not ChargeState.REPORTED and self.units is not None:
            raise ValueError(
                "%s carries no amount, so a number beside it would be invented"
                % self.state.value)

    @classmethod
    def reported(cls, units: int) -> "Charge":
        return cls(ChargeState.REPORTED, units=int(units), billed=True)

    @classmethod
    def not_reported(cls) -> "Charge":
        return cls(ChargeState.NOT_REPORTED)

    @classmethod
    def unmeasured(cls) -> "Charge":
        return cls(ChargeState.UNMEASURED)

    @property
    def budget_units(self) -> int | None:
        """Units a budget may consume. None means no budget may be derived."""
        return self.units if self.state is ChargeState.REPORTED else None

    def reads_as(self) -> str:
        if self.state is ChargeState.REPORTED:
            return "the receipt reported a charge of %r units" % (self.units,)
        if self.state is ChargeState.NOT_REPORTED:
            return ("the receipt reported no charge field; that is an absence,"
                    " not a measured zero")
        return ("no committed receipt exists for this route, so the cost is"
                " unknown and no budget may be derived from it")


def probe_record() -> dict:
    """The committed probe, or {} when it is absent or unreadable."""
    try:
        record = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def probe_request(record: Mapping[str, Any] | None = None) -> dict:
    """The model-inference payload the committed probe actually sent."""
    request = (record if record is not None else probe_record()).get("request") or {}
    return {
        "model": FREE_MODEL,
        "messages": [{"role": "user",
                      "content": str(request.get("prompt", ""))}],
        "max_output_tokens": int(request.get("max_output_tokens", 0)),
        "deadline_ms": int(request.get("deadline_ms", DEFAULT_DEADLINE_MS)),
        "reasoning_effort": request.get("reasoning_effort", "low"),
    }


def reservation_units(payload: Mapping[str, Any], retries: int = 0) -> tuple[int, str]:
    """What the broker reserves for this exact request, by calling the broker.

    There is no local formula to drift from, because there is no local
    formula. The reservation is request-dependent: a longer prompt or a larger
    output allowance reserves more, and the same request always reserves the
    same amount.
    """
    from settlement.broker import MODEL_INFERENCE, exposure_schedule

    return exposure_schedule(MODEL_INFERENCE, dict(payload), int(retries))


def probe_reservation_units(record: Mapping[str, Any] | None = None
                            ) -> tuple[int, str]:
    """The probe's reservation, recomputed from its own request."""
    return reservation_units(probe_request(record), 0)


def _charge_from(receipt: Mapping[str, Any]) -> Charge:
    usage = dict(receipt.get("usage") or {})
    if "charge_units" not in usage or usage["charge_units"] is None:
        return Charge(ChargeState.NOT_REPORTED,
                      billed=usage.get("billed"),
                      charge_scale=usage.get("charge_scale"))
    return Charge(ChargeState.REPORTED, units=int(usage["charge_units"]),
                  billed=usage.get("billed"),
                  charge_scale=usage.get("charge_scale"))


def measurement(record: Mapping[str, Any] | None = None) -> dict:
    """What the committed receipt says, with its absences named as absences."""
    record = probe_record() if record is None else record
    receipt = record.get("receipt") if isinstance(record, dict) else None
    if not isinstance(receipt, dict) or receipt.get("outcome") != "success":
        return {
            "status": "unavailable",
            "charge": Charge.unmeasured(),
            "provider_charge_state": ChargeState.UNMEASURED.value,
            "provider_charge_units": None,
            "reads_as": Charge.unmeasured().reads_as(),
        }
    usage = dict(receipt.get("usage") or {})
    charge = _charge_from(receipt)
    return {
        "status": "measured",
        "measured_at": record.get("measured_at"),
        "model": record.get("route", FREE_MODEL),
        "outcome": receipt.get("outcome"),
        "response_text": receipt.get("text"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "charge": charge,
        "provider_charge_state": charge.state.value,
        "provider_charge_units": charge.units,
        "provider_billed": usage.get("billed"),
        "provider_charge_scale": usage.get("charge_scale"),
        "reads_as": charge.reads_as(),
    }


def caveats() -> list:
    """Why an absent charge is not a zero, and where the units come from."""
    units, kind = probe_reservation_units()
    return list(probe_record().get("caveats") or []) + [
        "the free route reports unknown usage, so reserved units are exposure"
        " rather than proven billing",
        "the %d units that admitted the probe were %s, computed for that one"
        " 33-character request; a construction request reserves more"
        % (units, kind),
        "reservation units come from the broker exposure schedule applied to"
        " each request's own bounds, never from a per-dispatch constant",
    ]


def main(argv=None) -> int:
    print(json.dumps({"measurement": {key: repr(value) for key, value
                                      in measurement().items()},
                      "probe_reservation_units": probe_reservation_units(),
                      "caveats": caveats()},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
