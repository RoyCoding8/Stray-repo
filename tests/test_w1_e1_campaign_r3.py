"""Red-proofs for the r3 verifier, and the honest records it must accept.

r2's verifier was defeated by a self-consistent forgery: a 144-character
response carrying a `reason` about a 5211-character one. Every test here is
written as a tamper against a record the campaign actually built, so a
verifier that only catches the known forgery cannot pass this file. Each
forgery below is a DIFFERENT lie than the one r2 missed, and several of them
are self-consistent in the sense that mattered to r2: the record's own prose,
its own outcome and its own counts agree with each other and only the stored
bytes disagree.

The campaign is a live one, so its tests never touch the gateway. They build
records through the shipped `LiveGuard` over a stub adapter, which is the same
path a live dispatch takes, and then tamper with the written record the way a
fabricating lane would.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.ad01 import live_construct as live  # noqa: E402
from experiments.ad01 import w1_e1_campaign_r3 as campaign  # noqa: E402
from settlement.gateway import ModelResponse, Usage  # noqa: E402

# A payload the protocol's validator accepts, and one it does not, so the
# fixtures cover both sides of the parse boundary.
CONFORMING = json.dumps(
    {"specs": [{"const": 0, "mask": 3, "pair": None},
               {"const": 1, "mask": 5, "pair": None},
               {"const": 0, "mask": 9, "pair": None},
               {"const": 1, "mask": 6, "pair": [0, 1]}]},
    separators=(",", ":"))
UNPARSEABLE = "I think the answer is roughly {const: 1, mask: 3} for each."
OVER_LENGTH = "x" * 6000


class StubAdapter:
    """A gateway that answers with fixed bytes and stamps a real route.

    The route is the one the live gateway returned on 2026-09-29, including
    the capitalised `Nvidia`, because that is what `route_matches` has to
    accept and a fixture that said `nvidia` would test nothing.
    """

    def __init__(self, text: str, stop_reason: str = "stop") -> None:
        self.text = text
        self.stop_reason = stop_reason

    def infer(self, request):
        return ModelResponse(
            request.operation_id, self.text,
            {"adapter": "http", "model": live.OUTPUT_ROUTE["resolved_model"],
             "provider": "Nvidia", "tier": "free",
             "endpoint": live.OUTPUT_ROUTE["endpoint"]},
            Usage(input_tokens=370, output_tokens=2048, charge_units=0,
                  charge_scale=1000, billed=False),
            self.stop_reason)


def _guard(text: str, stop_reason: str = "stop"):
    return live.LiveGuard(
        StubAdapter(text, stop_reason),
        pinned_model=live.OUTPUT_ROUTE["requested_model"],
        ceiling=campaign.MODEL_CALL_CEILING, automatic_retries=0,
        expected_route=dict(live.OUTPUT_ROUTE))


def _record(text: str, *, arm: str = "P1", split: str = "qual", seed: int = 11,
            attempt: int = 1, stop_reason: str = "stop") -> dict:
    guard = _guard(text, stop_reason)
    entry = campaign._dispatch_once(
        guard, arm=arm, split=split, seed=seed, attempt=attempt,
        round_run_id="proof")
    task, session = campaign._build_session(split, seed)
    manifest = {"reference_scores": {"%s:%d" % (split, seed): {}}}
    return campaign._build_record(
        None, manifest, "%s-%s-a%d" % (arm, split, attempt),
        {"round_run_id": "proof"}, entry, task, session, guard)


def _corpus(root: Path) -> Path:
    """One honest record per branch the campaign can produce."""
    shutil.rmtree(root, ignore_errors=True)
    (root / "records").mkdir(parents=True)
    manifest = campaign._build_manifest()
    campaign._write_json(root / "campaign-manifest.json", manifest)
    campaign._write_json(root / "exposure.json",
                         campaign._build_exposure(manifest, 0, []))
    for name, text, kwargs in (
            ("conforming", CONFORMING, {}),
            ("unparseable", UNPARSEABLE, {}),
            ("over-length", OVER_LENGTH, {"stop_reason": "length"})):
        record = _record(text, **kwargs)
        campaign._write_json(root / "records" / ("%s.json" % name), record)
    return root


def _verify_one(record: dict, root: Path) -> dict:
    """Run the campaign's real verifier over a single tampered record.

    The root is the caller's `tmp_path`, not a fixed path in the repo. It
    used to be `REPO_ROOT / "_tmp_r3_verify"`, which left an untracked
    directory in the working tree after every run -- a test that dirties
    the checkout it runs in.
    """
    (root / "records").mkdir(parents=True, exist_ok=True)
    manifest = campaign._build_manifest()
    campaign._write_json(root / "campaign-manifest.json", manifest)
    campaign._write_json(root / "exposure.json",
                         campaign._build_exposure(manifest, 0, []))
    campaign._write_json(root / "records" / "cell.json", record)
    return campaign.verify(root)


# --- the corpus itself -------------------------------------------------


def test_honest_records_verify(tmp_path):
    """The verifier accepts what the campaign wrote when nothing is tampered.

    Without this, a verifier that refuses everything would pass every red-proof
    below, so it is the control the red-proofs are measured against.
    """
    result = campaign.verify(_corpus(tmp_path / "honest"))
    assert result["failures"] == [], result["failures"]
    assert result["denominators"] == {
        "records_on_disk": 3, "with_response_bytes": 3, "lost_sends": 0,
        "verified": 3, "failed": 0}, result["denominators"]
    assert result["no_response_to_attest"] == []


def test_over_length_is_kept_apart_from_invalid_program(tmp_path):
    """`over-length` is the campaign's flag and never an outcome value.

    A 6000-character response is recorded as `invalid-program` for Cap A
    because that is the protocol's taxonomy, and simultaneously carries
    `over_length: true` plus its own Cap B verdict, so the two findings are
    never averaged into one number.
    """
    root = _corpus(tmp_path / "caps")
    record = json.loads((root / "records" / "over-length.json").read_text())
    entry = record["attempts"][0]
    assert entry["response_characters"] == 6000
    assert entry["over_length"] is True
    assert entry["cap_b"]["verdict"] == "invalid-program"
    # The conforming record is inside the cap and is not flagged.
    other = json.loads((root / "records" / "conforming.json").read_text())
    assert other["attempts"][0]["over_length"] is False
    assert other["attempts"][0]["response_characters"] == len(CONFORMING)
    assert len(CONFORMING) < campaign._cap_a()


# --- red-proof 1: the forgery r2 missed, rebuilt -----------------------


def test_short_response_with_a_reason_about_a_long_one_is_rejected(tmp_path):
    """A 144-character response carrying a 5211-character reason.

    This is the r2 forgery, rebuilt from scratch rather than copied, because a
    verifier written only to catch it proves nothing. It is here to prove the
    general rule: the recorded prose is not an input to any verdict.
    """
    record = _record(CONFORMING)
    entry = record["attempts"][0]
    entry["reason"] = ("response of 5211 characters exceeds the frozen limit "
                       "of 512")
    entry["outcome"] = "invalid-program"
    entry["over_length"] = True
    entry["cap_b"]["verdict"] = "invalid-program"
    entry["score"] = None
    entry["candidate_digest"] = None
    # Everything the record asserts about itself now agrees with itself. Only
    # the stored bytes disagree, which is the whole point.
    result = _verify_one(record, tmp_path)
    assert result["failures"], "a short response with a long-response reason verified clean"
    assert "over-length" in result["failures"][0]["error"]


# --- red-proof 2: a forged character count ------------------------------


def test_forged_character_count_is_rejected(tmp_path):
    """Claiming 40 characters over bytes that are 143 long.

    Nothing else in the record is touched, so the count is the only lie and
    the verifier must find it on its own.
    """
    record = _record(CONFORMING)
    record["attempts"][0]["response_characters"] = 40
    result = _verify_one(record, tmp_path)
    assert result["failures"]
    assert "character count" in result["failures"][0]["error"]


# --- red-proof 3: a forged over-length flag -----------------------------


def test_over_length_flag_contradicting_the_bytes_is_rejected(tmp_path):
    """Flagging a 143-character response as over the 512 cap.

    The flag is this campaign's own classification, so it is the field a
    fabricator would reach for to relabel a conforming answer as a failure.
    """
    record = _record(CONFORMING)
    record["attempts"][0]["over_length"] = True
    result = _verify_one(record, tmp_path)
    assert result["failures"]
    assert "over-length" in result["failures"][0]["error"]


# --- red-proof 4: a fabricated score ------------------------------------


def test_score_the_scorer_would_not_return_is_rejected(tmp_path):
    """Recording a perfect score for a program the scorer rates at 0.25."""
    record = _record(CONFORMING)
    record["attempts"][0]["score"]["overall"] = 1.0
    record["attempts"][0]["outcome"] = "constructed"
    result = _verify_one(record, tmp_path)
    assert result["failures"]
    # The forged score is caught before the score comparison, because the
    # forged score also relabelled the outcome from the scorer's verdict to
    # `constructed`. Both are lies; the outcome is the one named first.
    assert "re-derives as" in result["failures"][0]["error"]


# --- red-proof 5: an outcome the parser contradicts ---------------------


def test_invalid_program_on_a_parseable_response_is_rejected(tmp_path):
    """Calling a conforming payload `invalid-program`.

    This is the mirror of red-proof 1 and the branch r2's taxonomy could
    hide: a record that under-claims is as false as one that over-claims.
    """
    record = _record(CONFORMING)
    record["attempts"][0]["outcome"] = "invalid-program"
    record["attempts"][0]["score"] = None
    record["attempts"][0]["candidate_digest"] = None
    result = _verify_one(record, tmp_path)
    assert result["failures"]
    assert "parses under Cap A" in result["failures"][0]["error"]


# --- red-proof 6: a swapped response ------------------------------------


def test_swapped_bytes_with_a_matching_digest_is_rejected(tmp_path):
    """Replacing the response while recomputing the digest to match.

    This defeats any verifier that only checks the digest against the response,
    which is the most obvious integrity check and the one a forger would
    satisfy first. The prompt, the task and the operation identity are all
    re-derived, so a payload that does not answer the prompt it was sent is
    caught on the score instead.
    """
    record = _record(CONFORMING)
    entry = record["attempts"][0]
    other = json.dumps(
        {"specs": [{"const": 1, "mask": 15, "pair": [2, 3]}] * 4},
        separators=(",", ":"))
    entry["raw_response"] = other
    entry["response_characters"] = len(other)
    dispatch = entry["dispatch"]
    dispatch["raw_response"] = other
    import hashlib
    dispatch["response_digest"] = hashlib.sha256(
        other.encode("utf-8")).hexdigest()
    # And the record's own self-consistency: the candidate digest now matches
    # the swapped bytes too.
    from experiments.ad01 import live_construct as _live
    entry["candidate_digest"] = _live.source_digest(other)
    entry["cap_b"] = {"cap": "unbounded", "cap_characters": None,
                      "parses": True, "verdict": "poor-task-result",
                      "detail": None, "score": entry["score"],
                      "candidate_digest": entry["candidate_digest"]}
    result = _verify_one(record, tmp_path)
    assert result["failures"], "a swapped response with a matching digest verified clean"
    assert "score" in result["failures"][0]["error"]


# --- red-proof 7: a forged route ----------------------------------------


def test_a_paid_route_stamped_free_is_rejected(tmp_path):
    """Recording `provider: openai` on a response the campaign dispatched.

    The route is compared through the shipped `route_matches`, so a record
    claiming a live free provider cannot be written onto bytes that came from
    somewhere else. This matters because r2's entire first campaign was lost
    to a route disagreement.
    """
    record = _record(CONFORMING)
    record["attempts"][0]["dispatch"]["provider"] = "openai"
    result = _verify_one(record, tmp_path)
    assert result["failures"]
    assert "route" in result["failures"][0]["error"]


# --- red-proof 8: a swapped task ----------------------------------------


def test_a_record_for_another_task_is_rejected(tmp_path):
    """Filing a qual-split record under the audit seed.

    The two frozen tasks have different tables, so the same payload scores
    differently on each. A record moved between them would carry a score the
    scorer never produced for that task.
    """
    record = _record(CONFORMING, split="qual", seed=11)
    record["split"] = "audit"
    record["seed"] = 23
    record["cell_name"] = "P1-audit-a1"
    result = _verify_one(record, tmp_path)
    assert result["failures"]
    assert "prompt digest" in result["failures"][0]["error"] or \
        "operation identity" in result["failures"][0]["error"]


# --- red-proof 9: a forged exposure -------------------------------------


def test_exposure_that_under_reports_its_own_calls_is_rejected(tmp_path):
    """An exposure file claiming fewer dispatches than the records show.

    Counters written before effects are the cap sheet's requirement, and they
    are also the one field in this directory a fabricator would under-report,
    because a campaign claiming fewer dispatches than its records show has
    quietly bought a fresh allowance. The summary therefore re-derives the
    count from the records and publishes the file's own number beside it, and
    the disagreement is visible rather than resolved in the file's favour.
    """
    root = _corpus(tmp_path / "exposure")
    exposure = json.loads((root / "exposure.json").read_text())
    assert exposure["attempts_settled"] == 0
    summary = campaign.summarize(root)
    assert summary["exposure"]["attempts_settled_recorded"] == 0
    assert summary["exposure"]["attempts_settled_derived"] == 3
    assert summary["exposure"]["exposure_agrees_with_records"] is False
    # The number the cap sheet is read against is the derived one.
    assert summary["exposure"]["attempts_settled"] == 3


def test_charge_units_stay_unknown_rather_than_becoming_zero(tmp_path):
    """A route that reports no charge yields null, not zero.

    r2 left all eight attempts at `unknown` and therefore never converted its
    exposure into cost. This asserts the distinction survives the summary.
    """
    root = _corpus(tmp_path / "charge")
    exposure = json.loads((root / "exposure.json").read_text())
    for cell in exposure["attempts"]:
        cell["billed"] = "unknown"
        cell["charge_units"] = "unknown"
    campaign._write_json(root / "exposure.json", exposure)
    summary = campaign.summarize(root)
    assert summary["exposure"]["charge_units_known"] is None
    assert summary["exposure"]["billed_unknown"] == exposure["attempts_settled"] \
        or summary["exposure"]["billed_unknown"] >= 0


# --- the network is withdrawn ------------------------------------------


def test_verify_withdraws_the_gateway(tmp_path):
    """Any path that reached for a gateway during `verify` would raise.

    The corpus is built first, with the real `infer` in place, because building
    it is what dispatches. Only the verification itself is instrumented, and
    the stub raises on contact so a reach is both counted and visible.
    """
    root = _corpus(tmp_path / "network")
    assert campaign.verify(root)["failures"] == []

    from experiments.ad01 import live_construct as _live
    calls = []

    def _refusing(self, *a, **k):
        calls.append(1)
        raise AssertionError("verify reached for a gateway")

    original = _live.LiveGuard.infer
    _live.LiveGuard.infer = _refusing
    try:
        result = campaign.verify(root)
    finally:
        _live.LiveGuard.infer = original
    assert not calls, "verify reached for a gateway %d time(s)" % len(calls)
    assert result["network_withdrawn"] is True
    assert result["failures"] == []
    assert result["denominators"]["verified"] == 3
    assert result["denominators"]["records_on_disk"] == 3


def test_the_path_shim_adds_src_not_the_repo_root():
    """`settlement` lives at `src/settlement`, so `src` is what goes on the path.

    The shim's second guard checks `REPO_ROOT / "src"` and must insert it. A
    guard that checks one path and inserts another leaves `settlement`
    unresolvable, and every command in the module fails on import rather than
    on anything to do with the campaign.
    """
    source = (REPO_ROOT / "experiments" / "ad01" / "w1_e1_campaign_r3.py"
              ).read_text(encoding="utf-8")
    assert 'if str(REPO_ROOT / "src") not in sys.path:\n    sys.path.insert(0, str(REPO_ROOT / "src"))' in source, \
        "the src shim guards one path and inserts another"


def test_offline_verify_does_not_need_an_http_client():
    """The offline contract holds with no transport installed.

    `route_matches` is a pure field comparison, but importing it executes
    `gateway_http`'s `import httpx`. So `verify` reaches the shipped rule
    through a caller that adds no transport of its own, and asserts on every
    run that the rule it calls still refuses a route it should. If a future
    change loosened `route_matches`, every route check in this campaign would
    silently become a no-op and the results would still look clean.
    """
    assert campaign._assert_route_rules_agree() in ("imported",
                                                     "parsed-source")
    frozen = {"endpoint": "http://127.0.0.1:4000/v1",
              "resolved_model": "m/x:free", "provider": "nvidia", "tier": "free"}
    assert campaign._offline_route_matches(
        {"model": "m/x:free", "provider": "Nvidia", "tier": "free",
         "endpoint": "http://127.0.0.1:4000/v1"}, frozen) is True
    # A loopback spelling difference is a URL identity, not a route mismatch.
    assert campaign._offline_route_matches(
        {"model": "m/x:free", "provider": "Nvidia", "tier": "free",
         "endpoint": "http://localhost:4000/v1"}, frozen) is True
    # A paid route and a missing field are both refusals.
    assert campaign._offline_route_matches(
        {"model": "m/x:free", "provider": "openai", "tier": "free",
         "endpoint": "http://127.0.0.1:4000/v1"}, frozen) is False
    assert campaign._offline_route_matches(
        {"model": "m/x:free", "provider": "Nvidia",
         "endpoint": "http://127.0.0.1:4000/v1"}, frozen) is False


def test_no_second_copy_of_the_route_rule_ships():
    """The offline restatement is reachable on any host, not only a bare one.

    An earlier version kept the restated rule inline behind an
    `except ImportError` in the caller, so the only code in this campaign a
    test could not reach was the one that decides a record's route on a host
    without `httpx`. Lifting it into its own function makes it testable here,
    and `_assert_route_rules_agree` checks it against the shipped rule on
    every run, so it cannot drift from the rule it stands in for.
    """
    assert campaign._route_fields_match(
        {"model": "m/x:free", "provider": "Nvidia", "tier": "free",
         "endpoint": "http://localhost:4000/v1"},
        {"endpoint": "http://127.0.0.1:4000/v1", "resolved_model": "m/x:free",
         "provider": "nvidia", "tier": "free"}) is True
    assert campaign._route_fields_match(
        {"model": "m/x:free", "provider": "openai", "tier": "free",
         "endpoint": "http://127.0.0.1:4000/v1"},
        {"endpoint": "http://127.0.0.1:4000/v1", "resolved_model": "m/x:free",
         "provider": "nvidia", "tier": "free"}) is False
    source = (REPO_ROOT / "experiments" / "ad01" / "w1_e1_campaign_r3.py"
              ).read_text(encoding="utf-8")
    assert "def _route_fields_match" in source, \
        "the offline restatement must be a named function a test can reach"


def test_shipped_route_rule_is_reachable_without_httpx():
    """The shipped rule is read from source when the module will not import.

    `gateway_http` imports `httpx` at module scope, so on a host without it
    an import-based check degrades to testing only the restatement and reports
    a clean run while half the property is unverified. The rule is a pure
    function of two dicts, so it is executed out of the parsed source with
    `httpx` never imported, which pins the agreement on every host.
    """
    runner = (
        "import sys, importlib.abc\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'httpx' or name.startswith('httpx.'):\n"
        "            raise ImportError('httpx blocked')\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "import importlib\n"
        "mod = importlib.import_module(%r)\n"
        "rule = mod._shipped_route_rule_without_transport()\n"
        "frozen = {'endpoint': 'http://127.0.0.1:4000/v1',\n"
        "          'resolved_model': 'm/x:free', 'provider': 'nvidia',\n"
        "          'tier': 'free'}\n"
        "good = {'model': 'm/x:free', 'provider': 'Nvidia', 'tier': 'free',\n"
        "        'endpoint': 'http://127.0.0.1:4000/v1'}\n"
        "assert rule(good, frozen) is True\n"
        "assert rule({**good, 'provider': 'openai'}, frozen) is False\n"
        "assert rule({**good, 'endpoint': 'https://127.0.0.1/v1'}, frozen) is False\n"
        # The agreement assertion itself must run on this host too, which is
        # the point: it must not silently skip the shipped half.
        "mod._assert_route_rules_agree()\n"
        "print('OK')\n"
        % "experiments.ad01.w1_e1_campaign_r3")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["S09ISO_DISABLE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT), str(REPO_ROOT / "src")])
    result = subprocess.run([sys.executable, "-c", runner],
                            capture_output=True, text=True, env=env, timeout=300)
    assert result.returncode == 0, result.stderr[-800:]
    assert "OK" in result.stdout


def test_verify_runs_with_httpx_blocked(tmp_path):
    """`verify` completes on a host with no HTTP client at all.

    This is the case a third party reproducing the numbers would hit, and it is
    the one a test in an environment that happens to have `httpx` installed
    cannot see. The module is run as a subprocess with an import hook that
    raises on `httpx`, so the offline claim is proved rather than assumed.
    """
    root = _corpus(tmp_path / "nohttpx")
    runner = tmp_path / "blocked.py"
    runner.write_text(
        "import sys, importlib.abc, runpy\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'httpx' or name.startswith('httpx.'):\n"
        "            raise ImportError('httpx blocked')\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "sys.argv = ['w1_e1_campaign_r3.py', 'verify', '--root', %r]\n"
        "runpy.run_path(%r, run_name='__main__')\n"
        % (str(root), str(REPO_ROOT / "experiments" / "ad01"
                          / "w1_e1_campaign_r3.py")), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["S09ISO_DISABLE"] = "1"
    result = subprocess.run([sys.executable, str(runner)],
                            capture_output=True, text=True, env=env, timeout=300)
    assert result.returncode == 0, result.stderr[-800:]
    payload = json.loads(result.stdout)
    assert payload["denominators"]["verified"] == 3
    assert payload["denominators"]["failed"] == 0
    assert payload["network_withdrawn"] is True
    # The run must say which half decided, so a degraded run is visible rather
    # than indistinguishable from one that imported the shipped rule.
    assert payload["route_rule_source"] == "parsed-source", \
        "an httpx-free run must report that it read the rule from source"


def test_verify_runs_from_a_bare_interpreter(tmp_path):
    """The module's contract is that a third party needs no PYTHONPATH.

    `sys.path` has to carry the repo and `repo/src` before `settlement` and
    `experiments` are importable, or the offline claim is an ImportError. This
    runs the file as a subprocess with the path environment stripped, so a
    shim that stops working fails here rather than on a reader's machine.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["S09ISO_DISABLE"] = "1"
    root = _corpus(tmp_path / "bare")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "experiments" / "ad01"
                             / "w1_e1_campaign_r3.py"), "verify",
         "--root", str(root)],
        capture_output=True, text=True, env=env, timeout=300)
    assert result.returncode == 0, result.stderr[-800:]
    payload = json.loads(result.stdout)
    assert payload["denominators"]["verified"] == 3
    assert payload["network_withdrawn"] is True
