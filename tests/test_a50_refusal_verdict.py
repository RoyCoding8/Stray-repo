from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
TOKEN = "a50-refusal"
REJECTED_POLICY = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    action = {'kind': 'diagnose', 'target': target,\n"
    "              'inputs': {'diagnostic': view['task_content']['family']},\n"
    "              'evidence_refs': [], 'requested_resources': {'queries': 1}}\n"
    "    return {'action': action, 'state': state}\n"
)


@contextlib.contextmanager
def _store(token: str):
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = iso.create_disposable_db(token, admin_dsn=admin_dsn,
                                        migrations_dir=MIGRATIONS)
    try:
        yield database
    finally:
        iso.drop_disposable_db(database, admin_dsn=admin_dsn)


class _Gateway(BaseHTTPRequestHandler):
    """A controlled gateway that answers every construction request."""

    seen: list = []
    policy_source = REJECTED_POLICY

    def do_POST(self):
        payload = json.loads(self.rfile.read(
            int(self.headers["Content-Length"])))
        _Gateway.seen.append(payload)
        from scripts import s09_pilot

        prompt = str(payload.get("input", ""))
        source = (self.policy_source if "Write one python policy" in prompt
                  else s09_pilot.METHOD_SOURCE)
        body = json.dumps({"output": [{"type": "message",
                                       "content": [{"type": "output_text",
                                                    "text": json.dumps(
                                                        {"entry": source,
                                                         "notes": "ctl"})}]}],
                           "usage": {"input_tokens": 1,
                                     "output_tokens": 1}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


@contextlib.contextmanager
def _controlled_endpoint():
    """Serve the controlled gateway and point the driver at it."""
    server = HTTPServer(("127.0.0.1", 0), _Gateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    previous = os.environ.get("S09_CONTROLLED_GATEWAY_ENDPOINT")
    os.environ["S09_CONTROLLED_GATEWAY_ENDPOINT"] = (
        "http://127.0.0.1:%d" % server.server_port)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("S09_CONTROLLED_GATEWAY_ENDPOINT", None)
        else:
            os.environ["S09_CONTROLLED_GATEWAY_ENDPOINT"] = previous
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextlib.contextmanager
def _shim_trajectory_hashlib():
    """`_method_panel` needs a name another lane is adding to its module.

    The missing import is a separate defect with its own owner, so this
    lane shims it rather than editing a file it does not own.
    """
    from experiments.ad01 import trajectory

    original = getattr(trajectory, "hashlib", None)
    trajectory.hashlib = hashlib
    try:
        yield
    finally:
        if original is None:
            del trajectory.hashlib
        else:
            trajectory.hashlib = original


@pytest.fixture(scope="module")
def rejected_study(tmp_path_factory):
    """One failing study, shared: each run costs minutes.

    Yields the refusal and the directory it wrote, so the assertions read
    the same run instead of paying for another.
    """
    from scripts import s09_pilot

    out = tmp_path_factory.mktemp("rejected")
    with _shim_trajectory_hashlib():
        with _controlled_endpoint():
            with _store(TOKEN) as database:
                try:
                    s09_pilot.run_study(
                        database.dsn, out, gateway_mode="controlled",
                        namespace_token="a50ctl", model="controlled")
                except s09_pilot.BundleVerificationRefusal as exc:
                    refusal = exc
                else:
                    refusal = None
    yield refusal, out


def test_an_incomplete_report_does_not_excuse_a_failed_verdict(
        rejected_study):
    """A verifier `fail` must stop the run even when the report is short.

    Incompleteness is a fact about the arms, not a licence to discard a
    verdict the verifier already computed. This run executes every
    scheduled episode, so the negative it produces is an observation
    about what the study saw rather than a run that stopped early.
    """
    refusal, _out = rejected_study
    assert refusal is not None, (
        "run_study returned a bundle its own verifier calls fail")
    bundle = refusal.bundle
    assert bundle["report"]["complete"] is False, (
        "this fixture is the incomplete arm set; without that the removed "
        "gate is not the thing under test")
    assert bundle["verdict"]["status"] == "fail"
    assert bundle["verdict"]["problems"], "a fail with no problems is not a fail"


def test_the_refusal_carries_the_verdict_and_the_disk_agrees(rejected_study):
    """The refusal has to carry what it refused, or it teaches nothing.

    The bundle used to come back with no verdict on it at all, so a
    caller that caught the exception had nothing to read and a caller
    that did not never learned the study failed.
    """
    from scripts import s09_verify

    refusal, out = rejected_study
    carried = refusal.bundle["verdict"]
    on_disk = json.loads((out / "verify.json").read_text())
    assert carried["status"] == on_disk["status"] == "fail"
    assert sorted(carried["problems"]) == sorted(on_disk["problems"])
    assert s09_verify.verify_bundle_dir(out)["status"] == "fail", (
        "recomputing from the written files disagrees with the refusal")


def test_the_cli_exits_nonzero_and_prints_no_success_line(tmp_path, capsys):
    """The surface an operator runs must not report a failing study green.

    The reported defect was a run that printed
    `s09-pilot <digest> episodes=... model=...` and exited 0 while the
    bundle beside it said `fail`.
    """
    with _shim_trajectory_hashlib(), _controlled_endpoint():
        from scripts import s09_pilot

        with _store(TOKEN) as database:
            code = s09_pilot.main([
                "run", "--dsn", database.dsn, "--out", str(tmp_path),
                "--namespace-token", "a50cli", "--mode", "controlled",
                "--model", "controlled"])
    printed = capsys.readouterr()
    assert code != 0, (
        "the CLI exited 0 holding a failing verdict: %r"
        % (printed.out.strip(),))
    assert "s09-pilot " not in printed.out, (
        "the success line was printed on a failing run: %r"
        % (printed.out.strip(),))
    assert json.loads((tmp_path / "verify.json").read_text())[
        "status"] == "fail", (
        "the CLI refused a run whose verifier passed, which is a different "
        "defect than the one under test")


def test_an_unobservable_action_is_not_evidence_of_a_policy_that_ran():
    """`policy-actions-unobservable` means the run cannot say what it did.

    The check fires when an episode claims a policy digest but no
    boundary decision carries a `kind`, so there is no observation to
    corroborate the claim. The study observed nothing it was built to
    observe, which is a different thing from a run that stopped early and
    must not be excused by the same flag.
    """
    from scripts import s09_verify

    freeze = {
        "study_id": "s", "study_root": "r", "arms": ["P0"],
        "order": ["e0"], "development": [],
        "construction_allowance": {},
        "assessment": [{"episode_id": "e0", "arm": "P0", "world": 0,
                        "domain": "software", "use_tasks": ["a"]}],
        "caps": {"model_calls_per_episode": 1,
                 "diagnostic_queries_per_episode": 1},
        "metric_rule": "m", "resource_rule": "r", "config": {},
        "policy_identities": {"P0": {"status": "unavailable"}},
        "method_repertoires": {"P0": {"members": [], "member_digests": []}},
    }
    freeze["freeze_digest"] = s09_verify.freeze_digest(freeze)
    bundle = {"freeze": freeze, "development": [],
              "construction": {},
              "assessment": [{"episode_id": "e0", "arm": "P0",
                              "policy_steps": 1, "model_calls": 1,
                              "witness_queries": 0, "operations": [],
                              "status": "complete",
                              "policy_digest": "d" * 64,
                              "policy_actions": [{"note": "no kind here"}]}],
              "use_records": [], "operations": {},
              "accounting": s09_verify.empty_accounting(),
              "refusal_probes": [],
              "conformance_replay": {"status": "conformance",
                                      "identity": "supported",
                                      "changed": "refused"}}
    problems = s09_verify.verify_bundle(bundle)["problems"]
    assert "policy-actions-unobservable e0" in problems, (
        "the verifier stopped reporting an episode whose decisions carry "
        "no observable action kind")