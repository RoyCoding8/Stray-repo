"""Deterministic ordering for the bounded P05 agenda catalogue."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_POLICIES = frozenset({"seed/1", "adaptive/1"})
_ADAPTIVE_KINDS = frozenset({"scope-probe", "instrument"})


def rank(options: Sequence[Mapping[str, Any]], policy: str) -> list[dict[str, Any]]:
    """Return copied options in policy order, with the reason for each rank."""
    if policy not in _POLICIES:
        raise ValueError(f"unknown agenda policy: {policy}")

    ranked = [dict(option) for option in options]

    def key(option: Mapping[str, Any]) -> tuple[Any, ...]:
        eligible = option["eligible"]
        adaptive_trigger = (
            policy == "adaptive/1"
            and eligible
            and option["triggered"]
            and option["kind"] in _ADAPTIVE_KINDS
        )
        last_selected = option["last_selected"]
        return (
            not eligible,
            not adaptive_trigger,
            -option["priority"],
            last_selected is not None,
            last_selected if last_selected is not None else 0,
            option["id"],
        )

    ranked.sort(key=key)
    for option in ranked:
        if not option["eligible"]:
            option["rank_reason"] = f"deferred: {option['reason']}"
        elif (
            policy == "adaptive/1"
            and option["triggered"]
            and option["kind"] in _ADAPTIVE_KINDS
        ):
            option["rank_reason"] = f"policy: adaptive/1 triggered {option['kind']}"
        else:
            order = "priority and fair order" if policy == "seed/1" else "seed order"
            option["rank_reason"] = f"policy: {policy} {order}"
    return ranked
