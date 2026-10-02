"""Deterministic scripted model double backing the §11 arms.

Implements the gateway adapter interface with fixed per-arm competence, so
the harness runs end to end with no live inference. Every response carries
``simulated: True`` metadata; nothing here may be reported as live.
"""

from __future__ import annotations

import json

from settlement.gateway import (GatewayAdapter, GatewayError, GatewayStatus,
                                ModelRequest, ModelResponse, Usage)


LESSON_TEXT = (
    "Off-by-one repair lesson. Python `range(n)` stops before n, so a loop "
    "meant to include n must use `range(n + 1)` or `range(1, n + 1)`. "
    "Likewise `while i < n:` excludes n; use `while i <= n:` when n is "
    "included. Check every loop bound against the documented inclusive range."
)


class ScriptedDouble(GatewayAdapter):
    def __init__(self, competence: dict, fixes: dict, broken: dict) -> None:
        self.competence = dict(competence)
        self.fixes = dict(fixes)
        self.broken = dict(broken)
        self.calls: list[dict] = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request: ModelRequest):
        try:
            body = json.loads(request.messages[-1]["content"])
        except (ValueError, IndexError, TypeError):
            return GatewayError("protocol", "scripted double needs a JSON body",
                                False, request.operation_id)
        if body.get("author_lesson"):
            summary = body.get("dev_summary", [])
            wins = sum(1 for row in summary if row.get("outcome") == "success")
            text = (f"{LESSON_TEXT} Authored from {wins}/{len(summary)}"
                    " successful development repairs.")
            self.calls.append({"author_lesson": True})
            return ModelResponse(request.operation_id, text,
                                 {"simulated": True, "author_lesson": True},
                                 Usage(input_tokens=60, output_tokens=150,
                                       charge_units=210), "stop")
        try:
            arm, task_id = body["arm"], body["task_id"]
        except (KeyError, TypeError):
            return GatewayError("protocol", "scripted double needs JSON arm/task_id",
                                False, request.operation_id)
        self.calls.append({"arm": arm, "task_id": task_id})
        code = (self.fixes if self.competence.get((arm, task_id)) else self.broken)[task_id]
        return ModelResponse(request.operation_id, code,
                             {"simulated": True, "arm": arm, "task_id": task_id},
                             Usage(input_tokens=50, output_tokens=120,
                                   charge_units=170), "stop")

    def cancel(self, operation_id: str) -> bool:
        return True
