"""R reference-curriculum rotation: frozen fair schedule as data.

Per world the R arm visits visible development tasks alternating domains in
fixed index order. This module only provides the schedule; trajectory
orchestration consumes it through the trajectory entry (T-ADTR owns that).
"""

from __future__ import annotations

from . import worlds

DOMAINS = ("software", "graph")


def r_schedule(world: int) -> list:
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    dev = membership[str(world)]["dev"]
    steps = []
    for index in range(3):
        for domain in DOMAINS:
            want = "ad01-w%d-dev-%s-%02d" % (
                world, "sw" if domain == "software" else "gr", index)
            if want not in dev[domain]:
                raise ValueError("R schedule task %r missing in world %d"
                                 % (want, world))
            steps.append({"seq": len(steps), "task_id": want,
                          "domain": domain})
    return steps
