"""Live-grant preflight gate for EC02 panels (lane E).

The entry refuses live panels unless a model gateway/API/key is
configured AND a finite campaign grant is declared. Discovery of a
reachable gateway alone never admits live spend; the grant is a
separate human declaration. On refusal the gate returns the exact
blocked command so the runner can report remaining cells without
presenting a doubled run as live evidence.
"""

from __future__ import annotations

import os

LIVE_ENTRY = "experiments/coord02/entry.py"

EPISODE_CELLS = {"development": 48, "evaluation": 96, "transfer": 48,
                 "interventions": 12}

CONSTRUCTION_CALLS = 4


def live_env(env: dict | None = None) -> dict:
    source = dict(os.environ) if env is None else dict(env)
    return {"endpoint": source.get("SETTLEMENT_GATEWAY_ENDPOINT", ""),
            "key": source.get("TEAM01_LIVE_API_KEY", "")
            or source.get("SETTLEMENT_GATEWAY_KEY", ""),
            "model": source.get("TEAM01_LIVE_MODEL", ""),
            "grant_episodes": source.get("EC02_LIVE_GRANT_EPISODES", ""),
            "grant_construction": source.get("EC02_LIVE_GRANT_CALLS", "")}


def blocked_live_command(env: dict | None = None) -> str:
    live = live_env(env)
    model = live["model"] or "<model>"
    return ("TEAM01_LIVE_API_KEY=<grant> EC02_LIVE_GRANT_EPISODES=<n> "
            "SETTLEMENT_GATEWAY_ENDPOINT=<endpoint> "
            "uv run python -m %s --panel <evaluation|transfer> "
            "--model %s" % (LIVE_ENTRY.replace("/", ".")[:-3], model))


def _grant_int(raw: str, name: str, problems: list) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        problems.append("grant %s %r is not an integer" % (name, raw))
        return None
    if value <= 0:
        problems.append("grant %s must be a positive finite declaration"
                        % name)
        return None
    return value


def preflight_live(*, panels: tuple = ("evaluation", "transfer"),
                   env: dict | None = None) -> dict:
    live = live_env(env)
    problems: list = []
    if not live["endpoint"]:
        problems.append("no gateway endpoint configured "
                        "(SETTLEMENT_GATEWAY_ENDPOINT)")
    if not live["key"]:
        problems.append("no live key configured (TEAM01_LIVE_API_KEY)")
    if not live["model"]:
        problems.append("no live model declared (TEAM01_LIVE_MODEL)")
    grant_episodes = _grant_int(live["grant_episodes"],
                                "EC02_LIVE_GRANT_EPISODES", problems) \
        if live["grant_episodes"] else None
    if grant_episodes is None and not live["grant_episodes"]:
        problems.append("no finite episode grant declared "
                        "(EC02_LIVE_GRANT_EPISODES)")
    grant_calls = _grant_int(live["grant_construction"],
                             "EC02_LIVE_GRANT_CALLS", problems) \
        if live["grant_construction"] else 0
    wanted = sum(EPISODE_CELLS.get(panel, 0) for panel in panels)
    if grant_episodes is not None and grant_episodes < wanted:
        problems.append("grant covers %d episodes but %d cells are "
                        "requested" % (grant_episodes, wanted))
    if problems:
        return {"admitted": False, "problems": problems,
                "blocked_command": blocked_live_command(env),
                "remaining_cells": {panel: EPISODE_CELLS.get(panel, 0)
                                    for panel in panels},
                "grant": {"episodes": grant_episodes,
                          "construction_calls": grant_calls}}
    return {"admitted": True, "problems": [],
            "blocked_command": "",
            "remaining_cells": {panel: EPISODE_CELLS.get(panel, 0)
                                for panel in panels},
            "grant": {"episodes": grant_episodes,
                      "construction_calls": grant_calls}}


def require_live(*, panels: tuple = ("evaluation", "transfer"),
                 env: dict | None = None) -> dict:
    verdict = preflight_live(panels=panels, env=env)
    if not verdict["admitted"]:
        raise PermissionError(
            "live panels blocked: %s; run %s once the grant exists"
            % ("; ".join(verdict["problems"]),
               verdict["blocked_command"]))
    return verdict
