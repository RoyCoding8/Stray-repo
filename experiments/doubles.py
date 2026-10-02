"""Deterministic scripted model double backing the §11 arms.

Implements the gateway adapter interface with fixed per-arm competence, so
the harness runs end to end with no live inference. Every response carries
``simulated: True`` metadata; nothing here may be reported as live.
"""

from __future__ import annotations

import json

from settlement.gateway import (GatewayAdapter, GatewayError, GatewayStatus,
                                ModelRequest, ModelResponse, Usage)


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
            arm, task_id = body["arm"], body["task_id"]
        except (ValueError, KeyError, IndexError, TypeError):
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
