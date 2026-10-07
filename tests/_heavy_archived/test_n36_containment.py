"""N-36: a policy that can read the repository recovers the seed it is measured against.

The finding claimed a policy recovered an invertible seed in 959 ms through
`LocalLauncher`, whose own docstring says it is not containment. These tests
reproduce that through the real launcher and then hold the launcher to the
property the finding says is missing.

What is actually provided by the launcher, measured rather than read off a
docstring:

* the seed is not an argument, an environment variable, or a file. The child's
  environment is scrubbed to `PATH`, `LANG` and `SETTLEMENT_OPERATION`, and
  `SETTLEMENT_OPERATION` is the operation id, not the seed;
* the key is a module-level constant in the repository, so the child reaches it
  by opening a source file;
* the recovery is invertible, not merely a key subject to further checks. The
  seed is the recipe: `make_task` seeds a `random.Random` from it, so recovering
  the seed recovers the answer exactly, with no query spent.

So the containment claim was false and the docstring understated the exposure.
The repair is a boundary, and the boundary the tests below require is a real
one: a dispatch that declares a read-deny list must actually deny it.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

from settlement import broker
from settlement.launcher_local import (
    LocalLauncher,
    PROFILE,
    landlock_available,
    probe_landlock,
    _child_read_allowlist,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _view_and_truth(split: str, seed: int) -> tuple[dict, tuple]:
    from experiments.ad01 import second_active as sa

    task = sa.make_task(split, seed)
    return sa.public_state(sa.ScheduleSession(task)), tuple(task["order"])


def _run_child(script: str, work: Path, operation_id: str,
               deny: list[str] | None = None,
               extra_argv: list[str] | None = None) -> dict:
    """Run a child under the real launcher and return the launcher's receipt."""
    (work / "child.py").write_text(script, encoding="utf-8")
    launcher = LocalLauncher(work / "launcher")
    payload = {
        "profile": PROFILE,
        "argv": [sys.executable, str(work / "child.py")] + list(extra_argv or []),
        "cwd": str(work),
        "timeout_ms": 60_000,
        "max_output_bytes": 1_048_576,
        "cpu_seconds": 30,
        "memory_bytes": 536_870_912,
    }
    if deny is not None:
        payload["read_deny"] = deny
    outcome = launcher.dispatch(broker.BrokerOp(
        operation_id=operation_id, effect=broker.SANDBOX_EXEC, payload=payload))
    assert outcome.sent is True, outcome.refused_reason
    return outcome.receipt.content


def _child_data(content: dict) -> dict:
    """The child's typed payload, read the way a caller reads a receipt.

    The launcher puts a well-formed worker's fields under ``worker`` and a
    rejected stdout under ``stdout``. Going through the same branch the
    launcher does is what makes this a measurement of the launcher rather
    than of the child.
    """
    data = content["data"]
    worker = data.get("worker")
    if isinstance(worker, dict) and isinstance(worker.get("data"), dict):
        return worker["data"]
    pytest.fail("child did not return a typed envelope: %r" % (data,))


# The attack, as an untrusted policy. It starts with the published view and
# nothing else, exactly as a STEP arm does.
_ATTACK = '''
import hashlib, hmac, json, pathlib, random, sys, time

view = json.loads(pathlib.Path(sys.argv[1]).read_text())
started = time.time()
try:
    source = pathlib.Path(__REPO__, "experiments/ad01/worlds.py").read_text()
except OSError as exc:
    print(json.dumps({"status": "ok", "data": {"readable": False, "errno": exc.errno, "error": exc.strerror}}))
    raise SystemExit(0)
key = None
for line in source.splitlines():
    if line.startswith("TASK_ID_KEY"):
        key = eval(line.split("=", 1)[1].strip())
suffix = view["task_id"].rsplit("-", 1)[-1]
seed = None
probe = ""
for candidate in range(10000):
    probe = "ordering-constraints-v1/" + view["split"] + "/" + str(candidate)
    if hmac.new(key, probe.encode(), hashlib.sha256).hexdigest()[:12] == suffix:
        seed = candidate
        break
if seed is None:
    print(json.dumps({"status": "ok", "data": {"readable": True, "seed": None}}))
    raise SystemExit(0)
rng = random.Random(int(hashlib.sha256(probe.encode()).hexdigest(), 16))
print(json.dumps({"status": "ok", "data": {
    "readable": True,
    "seed": seed,
    "order": rng.sample(("analysis", "build", "deploy", "verify"), 4),
    "ms": int((time.time() - started) * 1000),
}}))
'''.replace("__REPO__", repr(str(REPO_ROOT)))


def test_the_launcher_lets_a_policy_read_the_key_it_is_measured_against():
    """Red for the finding, green for the repair: this is the attack itself.

    Without ``read_deny`` the child reads the key and recovers the seed. That
    is the exposure the launcher documents and does not prevent.
    """
    with tempfile.TemporaryDirectory(prefix="n36-open-") as tmp:
        work = Path(tmp)
        view, truth = _view_and_truth("dev", 4)
        (work / "view.json").write_text(json.dumps(view), encoding="utf-8")
        content = _run_child(
            _ATTACK, work, "n36-unbounded",
            extra_argv=[str(work / "view.json")])
        result = _child_data(content)
        assert result["readable"] is True, (
            "the attack could not read the key source, so this test no longer "
            "measures the exposure it was written for")
        assert result["seed"] == 4
        # Invertibility, measured rather than asserted: the seed is the recipe,
        # so recovering it yields the answer outright and not a key that is
        # then subject to further checks.
        assert tuple(result["order"]) == truth


def test_a_declared_read_deny_actually_denies():
    """The boundary the repair installs, exercised through the real launcher."""
    if not landlock_available():
        pytest.skip("landlock unavailable on this kernel: %s"
                    % probe_landlock().reason)
    with tempfile.TemporaryDirectory(prefix="n36-deny-") as tmp:
        work = Path(tmp)
        view, _ = _view_and_truth("dev", 4)
        (work / "view.json").write_text(json.dumps(view), encoding="utf-8")
        content = _run_child(
            _ATTACK, work, "n36-denied",
            deny=[str(REPO_ROOT / "experiments")],
            extra_argv=[str(work / "view.json")])
        result = _child_data(content)
        assert result["readable"] is False, (
            "read_deny was declared and the child still read the key source")
        assert "seed" not in result


def test_the_deny_does_not_break_a_child_that_needs_only_its_work_tree():
    """A boundary that stops the attack but breaks the policies is not a fix.

    The STEP driver loads its policy from the work directory and imports
    nothing from the repository, so a child under the same deny list must
    still run and still see its own staged files.
    """
    if not landlock_available():
        pytest.skip("landlock unavailable on this kernel")
    with tempfile.TemporaryDirectory(prefix="n36-workdir-") as tmp:
        work = Path(tmp)
        (work / "staged.txt").write_text("visible", encoding="utf-8")
        script = (
            "import json, pathlib, sys\n"
            "out = {'staged': pathlib.Path(sys.argv[1]).read_text(),\n"
            "       'denied': None}\n"
            "try:\n"
            "    out['denied'] = pathlib.Path(sys.argv[2]).read_text()[:10]\n"
            "except OSError as exc:\n"
            "    out['denied'] = 'blocked:' + str(exc.errno)\n"
            "print(json.dumps({'status': 'ok', 'data': out}))\n")
        content = _run_child(script, work, "n36-workdir",
                             deny=[str(REPO_ROOT / "experiments")],
                             extra_argv=[str(work / "staged.txt"),
                                         str(REPO_ROOT / "experiments" / "ad01"
                                             / "worlds.py")])
        data = content["data"]
        result = _child_data(content)
        assert result["staged"] == "visible", (
            "the boundary hid the child's own work tree, which every policy "
            "needs and which is not where the key lives")
        assert str(result["denied"]).startswith("blocked:"), result


def test_the_receipt_still_says_containment_false():
    """The label must not be raised by a boundary that is not gVisor.

    Landlock confines the filesystem. It is not the container the profile
    names, and a receipt that claimed otherwise would be the digest the
    ledger forbids: the claim going away while the property stays false.
    """
    with tempfile.TemporaryDirectory(prefix="n36-label-") as tmp:
        work = Path(tmp)
        content = _run_child(
            "import json\nprint(json.dumps({'ok': True}))\n", work, "n36-label")
        assert content["containment"] is False
        assert content["profile"] == PROFILE


def test_probing_reports_the_kernel_rather_than_guessing():
    """A probe is what a deployment calls before it chooses a profile."""
    probe = probe_landlock()
    assert probe.name == "landlock"
    assert isinstance(probe.available, bool)
    if not probe.available:
        # An unavailable kernel must say why, and must not read as available.
        assert probe.reason
        assert "landlock" in probe.reason.lower()


def test_an_allowed_parent_cannot_reopen_a_denied_descendant(tmp_path):
    if not landlock_available():
        pytest.skip("landlock unavailable on this kernel")
    denied = tmp_path / "private"
    denied.mkdir()
    outcome = LocalLauncher(tmp_path / "runs").dispatch(broker.BrokerOp(
        operation_id="n36-overlap", effect=broker.SANDBOX_EXEC,
        payload={"profile": PROFILE, "argv": [sys.executable, "-c", "print(1)"],
                 "read_allow": _child_read_allowlist({"cwd": str(tmp_path)}),
                 "read_deny": [str(denied)],
                 "timeout_ms": 10_000, "max_output_bytes": 1024}))
    assert not outcome.sent
    assert "child-setup-failed" in outcome.refused_reason
