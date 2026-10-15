"""Prepare real P10 task, genome, allocation and grant state for campaign tests."""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rsi import campaign, gate, genome, task
from settlement import store
from settlement.common import Command
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

from test_rsi_investigate import _task

ROOT = Path(__file__).resolve().parents[2]


def prepare_campaign(dsn, tmp_path, *, campaign_id, round_count=2, max_turns=1):
    """Publish pinned inputs and return API arguments without starting the agenda."""
    if type(round_count) is not int or not 1 <= round_count <= 32:
        raise ValueError("round_count must be 1..32")
    if type(max_turns) is not int or max_turns <= 0:
        raise ValueError("max_turns must be positive")
    tmp_path.mkdir(parents=True, exist_ok=True)
    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    roots["staging_root"].mkdir()
    roots["artifacts_root"].mkdir()
    development = _task()
    task.publish(dsn, development, **roots)
    parent = genome.Genome({"AGENTS.md": b"Work only on the assigned task."})
    genome.publish(dsn, parent, parent=None, origin="p10-fixture", **roots)
    token_id, cpu_id = "tokens-" + campaign_id, "cpu-" + campaign_id
    store.seed_allocation(dsn, Command(request_id=f"p10-token:{campaign_id}", payload={
        "allocation_id": token_id, "domain": "tokens", "authorized": 100_000,
    }))
    store.seed_allocation(dsn, Command(request_id=f"p10-cpu:{campaign_id}", payload={
        "allocation_id": cpu_id, "domain": "cpu", "authorized": 100_000,
    }))
    candidate = genome.Genome({"AGENTS.md": b"Implement add."})
    genome.publish(dsn, candidate, parent=parent.digest, origin="p10-fixture", **roots)

    val = replace(development, name="p10-val", split="val")
    task.publish(dsn, val, **roots)
    rounds, all_assessment_tasks = [], {development.digest, val.digest}
    for index in range(round_count):
        anchor = replace(
            development,
            name=f"p10-anchor-{index}",
            split="anchor",
            instruction=f"Implement add(2, 3) for protected assessment case {index}.",
        )
        task.publish(dsn, anchor, **roots)
        all_assessment_tasks.add(anchor.digest)
        epoch = gate.freeze(
            dsn, (development, val, anchor),
            gate.Budget("fixture:free", 5_000, 30_000), execution="benchmark",
        )
        rounds.append({
            "id": f"round-{index + 1}",
            "after_turn": max_turns,
            "epoch": epoch,
            "parent": parent.digest,
            "candidate": candidate.digest,
            "model": "fixture:free",
            "route_identity": campaign.route_identity("http://fixture/v1"),
        })
    protocol = {"schema": "p10-assessment/1", "rounds": rounds}
    agent = CodexLauncher(
        tmp_path / "campaign-runs",
        codex_cmd=[sys.executable, str(ROOT / "tests" / "fixtures" / "fake_gate.py")],
        provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
        allowed_overrides=genome.HARNESS_KEYS,
    )
    checker = LocalLauncher(tmp_path / "campaign-verifiers")
    charter = {
        "grant_version": 1,
        "objective": "Resolve the development task and compare a frozen candidate.",
        "allocations": {
            "tokens": {"id": token_id, "units": 100_000},
            "cpu": {"id": cpu_id, "units": 100_000},
        },
        "policy": "seed/1",
        "max_turns": max_turns,
        "deadline": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "opportunities": [{
            "id": "develop",
            "task_id": development.digest,
            "genome_id": candidate.digest,
            "objective": "Complete the addition implementation.",
            "question": "Does the candidate pass the development verifier?",
            "priority": 1,
            "resource_ceilings": {"tokens": 25_000, "cpu": 5_000},
            "timeout_ms": 30_000,
            "max_steps": max_turns,
            "expected_observation": "A pristine development verifier result.",
            "stop_condition": "The turn cap or deadline is reached.",
        }],
    }
    store.seed_grant(dsn, Command(
        request_id=f"p10-grant:{campaign_id}:1",
        payload={
            "version": 1,
            "charter_text": "bounded P10 test grant",
            "authority_grant": {
                "kind": "rsi-agenda",
                "agenda_id": campaign_id,
                "development_task_ids": [development.digest],
                "assessment_task_ids": sorted(all_assessment_tasks),
                "genome_ids": sorted({parent.digest, candidate.digest}),
                "effects": ["agent-run", "sandbox-exec"],
            },
            "envelopes": {
                "tokens": {"allocation_id": charter["allocations"]["tokens"]["id"],
                           "units": 100_000},
                "cpu": {"allocation_id": charter["allocations"]["cpu"]["id"],
                        "units": 100_000},
                "max_turns": max_turns,
            },
        },
    ))
    run = {"dsn": dsn, "agent": agent, "checker": checker, "roots": roots}
    return {
        "run": run,
        "charter": charter,
        "protocol": protocol,
        "rounds": rounds,
        "epochs": [item["epoch"] for item in rounds],
        "tasks": {"development": development, "val": val},
        "genomes": {"parent": parent, "candidate": candidate},
    }
