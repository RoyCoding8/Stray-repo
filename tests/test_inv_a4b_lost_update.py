"""Lane A4b: a charge is authoritative state, so it cannot be silently lost.

`FrontierStore.save()` writes a tmp file and `os.replace`s it, which is atomic.
The read-modify-write around that replace is not. Two processes each load the
document, each charge, each replace the whole file, and the second replace
discards the first charge. The counter reads 1 where 2 is durable, so one
charge is silently refunded. A crash would announce itself; this does not.

The barrier in the child below forces both processes to hold their snapshot
before either charges, so the race is reproduced deterministically rather than
by luck.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel

SRC = str(Path(__file__).resolve().parents[1] / "src")


def _store(tmp_path, *, opportunities=("opp-a", "opp-b")):
    store = frontier.create_store(
        tmp_path / "frontier.json", namespace=frontier.NAMESPACE,
        mission={"objective": "concurrent charge",
                 "environments": [{"instrument": "boolean-rule-v1",
                                   "split": "dev", "seed": 4}]},
        authority={"queries": 16, "steps": 12})
    store.bind_active(channel.make_control("low"))
    for opportunity_id in opportunities:
        store.propose({
            "opportunity_id": opportunity_id,
            "mission_link": "concurrent charge",
            "question": "observe input 3",
            "intervention": {"instrument": "boolean-rule-v1",
                             "target": "rule-dev-0004", "inputs": {"x": 3}},
            "resources": {"queries": 1, "steps": 1}})
    return store


def _observation(effect, opportunity_id):
    return {
        "observation_id": "obs-%s" % opportunity_id,
        "task": opportunity_id,
        "verdict": "observed",
        "x": 3,
        "y": [1, 0, 0, 1],
        "effect_id": effect["effect_id"],
        **effect["expected_identity"],
    }


_CHILD = r'''
import os, sys, time
sys.path.insert(0, os.environ["A4B_SRC"])
from experiments.ad01 import frontier

store_path, wait_dir, name, opportunity_id = sys.argv[1:5]
store = frontier.FrontierStore(store_path)
baseline = store.authority["queries_used"]
with open(os.path.join(wait_dir, "baseline-" + name), "w") as fh:
    fh.write(str(baseline))
with open(os.path.join(wait_dir, "ready-" + name), "w") as fh:
    fh.write("ready")
deadline = time.time() + 120
while not os.path.exists(os.path.join(wait_dir, "go")):
    if time.time() > deadline:
        raise SystemExit("go never arrived")
    time.sleep(0.01)
effect = store.admit_and_spend(
    opportunity_id, store.active_digest, {"queries": 1, "steps": 1},
    effect_identity={"operation_id": "op-" + name})
print("CHARGED from=%d to=%d effect=%s" % (
    baseline, store.authority["queries_used"], effect["effect_id"]))
'''

_CRASHER = r'''
import os, signal, sys
sys.path.insert(0, os.environ["A4B_SRC"])
from experiments.ad01 import frontier

store_path, opportunity_id = sys.argv[1:3]
store = frontier.FrontierStore(store_path)
effect = store.admit_and_spend(
    opportunity_id, store.active_digest, {"queries": 1, "steps": 1},
    effect_identity={"operation_id": "op-crash"})
print("admitted effect=%s" % effect["effect_id"], flush=True)
os.kill(os.getpid(), signal.SIGKILL)
'''


def _child(script, *args):
    env = dict(os.environ, A4B_SRC=SRC)
    return subprocess.run(
        [sys.executable, "-c", script, *[str(a) for a in args]],
        capture_output=True, text=True, env=env, timeout=180)


def _await_both(wait_dir, count=2, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(list(Path(wait_dir).glob("ready-*"))) == count:
            return
        time.sleep(0.01)
    raise AssertionError("children never reached the barrier")


def test_two_concurrent_charges_are_both_durable(tmp_path):
    """Both charges survive, or the second is refused. Neither may vanish.

    This asserts the literal 2. On the unfixed source the durable count is 1:
    the second process replaces the whole document with its own stale
    snapshot, refunding the first charge in silence.
    """
    store = _store(tmp_path)
    wait_dir = tmp_path / "barrier"
    wait_dir.mkdir()

    children = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(store.path), str(wait_dir),
             name, opportunity_id],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=dict(os.environ, A4B_SRC=SRC))
        for name, opportunity_id in (("a", "opp-a"), ("b", "opp-b"))]

    _await_both(wait_dir)
    baselines = sorted(
        int((wait_dir / ("baseline-" + name)).read_text())
        for name in ("a", "b"))
    assert baselines == [0, 0], (
        "both children must charge against the same confirmed baseline")

    (wait_dir / "go").write_text("go")
    results = [(child.wait(timeout=180), child.stdout.read(),
                child.stderr.read()) for child in children]

    for returncode, stdout, stderr in results:
        assert returncode == 0, "child failed: %s / %s" % (stdout, stderr)
        assert "CHARGED" in stdout

    reloaded = frontier.FrontierStore(str(store.path))
    assert reloaded.authority["queries_used"] == 2
    assert reloaded.authority["steps_used"] == 2
    charged = [effect for effect in reloaded.pending_effects
               if effect["charged"]]
    assert len(charged) == 2
    assert len({effect["effect_id"] for effect in charged}) == 2


def test_concurrent_charges_charge_the_opportunities_not_one_twice(tmp_path):
    """A lost update shows up as a duplicated counter and a missing effect."""
    store = _store(tmp_path)
    wait_dir = tmp_path / "barrier"
    wait_dir.mkdir()

    children = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(store.path), str(wait_dir),
             name, opportunity_id],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=dict(os.environ, A4B_SRC=SRC))
        for name, opportunity_id in (("a", "opp-a"), ("b", "opp-b"))]

    _await_both(wait_dir)
    (wait_dir / "go").write_text("go")
    for child in children:
        assert child.wait(timeout=180) == 0

    reloaded = frontier.FrontierStore(str(store.path))
    identities = {effect["expected_identity"]["operation_id"]
                  for effect in reloaded.pending_effects}
    assert identities == {"op-a", "op-b"}


def test_sequential_charges_still_accumulate_and_replay_still_deduplicates(
        tmp_path):
    """The concurrency fix must not change single-process charge semantics."""
    store = _store(tmp_path)
    digest = store.active_digest
    first = store.admit_and_spend(
        "opp-a", digest, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-a"})
    replay = store.admit_and_spend(
        "opp-a", digest, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-a"})

    assert replay == first
    assert store.authority["queries_used"] == 1

    store.admit_and_spend(
        "opp-b", digest, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-b"})
    assert store.authority["queries_used"] == 2

    reloaded = frontier.FrontierStore(str(store.path))
    assert reloaded.authority["queries_used"] == 2


def test_crash_after_charge_leaves_a_recoverable_pending_record(tmp_path):
    """A charge is durable when the process dies, and stays settleable.

    This is the property that already holds and must not regress while the
    lost update is fixed: the admission and its charge land in one atomic
    replace, so a SIGKILL after `admit_and_spend` returns cannot separate them.
    """
    store = _store(tmp_path)
    result = _child(_CRASHER, store.path, "opp-a")

    assert result.returncode == -signal.SIGKILL, result.stderr
    assert "admitted" in result.stdout

    reloaded = frontier.FrontierStore(str(store.path))
    assert len(reloaded.pending_effects) == 1
    assert reloaded.pending_effects[0]["charged"] is True
    assert reloaded.settled_effects == []
    assert reloaded.authority["queries_used"] == 1

    effect = reloaded.pending_effects[0]
    reloaded.complete_effect(
        effect["effect_id"], _observation(effect, "opp-a"))
    settled = frontier.FrontierStore(str(store.path))
    assert len(settled.settled_effects) == 1
    assert settled.authority["queries_used"] == 1


def test_charge_refuses_rather_than_writing_a_damaged_document(tmp_path):
    """The charge boundary re-reads under its lock, so it validates first."""
    store = _store(tmp_path)
    store.admit_and_spend(
        "opp-a", store.active_digest, {"queries": 1, "steps": 1},
        effect_identity={"operation_id": "op-a"})
    stale = frontier.FrontierStore(str(store.path))

    document = json.loads(Path(store.path).read_text())
    document["observations"] = [
        {"observation_id": "obs-x", "task": "one", "verdict": "observed"},
        {"observation_id": "obs-x", "task": "two", "verdict": "observed"},
    ]
    Path(store.path).write_text(frontier.canonical(document) + "\n")

    with pytest.raises(frontier.Refused):
        stale.admit_and_spend(
            "opp-b", stale.active_digest, {"queries": 1, "steps": 1},
            effect_identity={"operation_id": "op-b"})

    on_disk = json.loads(Path(store.path).read_text())
    assert on_disk["used"]["queries"] == 1
    assert len([e for e in on_disk["pending_effects"] if e["charged"]]) == 1