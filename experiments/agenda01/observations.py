"""AG01-EXP public observation mint (grammar AG01-OBS-1).

This module is the policy/runner-observation path: it carries a load mark
that forbids the privileged grader from being imported after it, and the
grader refuses calls issued from here. Only public fixture fields,
trajectory observations and budget state cross this boundary. Rotation and
the policy input shape live in settlement.agenda_policy; this module mints
simulated observations only.
"""

from __future__ import annotations

_AG01_POLICY_OBSERVATION_PATH = True

GRAMMAR = "AG01-OBS-1"

OBS_KEYS = {"prop", "scope", "dep", "dep_version", "value", "source_attempt",
            "receipt", "epoch", "simulated", "scored"}


def public_observation(prop: str, spec: dict, value, attempt: str,
                       receipt: str, epoch: int, scored: bool = True) -> dict:
    assert value in (True, False, "unknown")
    return {"prop": prop, "scope": spec["scope"], "dep": spec["dep"],
            "dep_version": spec["dep_version"], "value": value,
            "source_attempt": attempt, "receipt": receipt, "epoch": epoch,
            "simulated": True, "scored": scored}
