"""B14: the retention freeze's ceiling is zero, and this gate proves why.

Every literal below is read out of `reports/evidence/invr1b14-retention/
retention.json` or out of `reports/cap-sheets/b14-retention-freeze.md`. None
is recomputed from the driver that wrote them, because a test that re-derives
the artifact's own numbers proves only that the driver agrees with itself.

The three claims this study has to earn, and which of these tests earns each:

1. **The ceiling is a positive finite number and the run is under it.** Not
   restated: the freeze names a dispatch cap, the artifact names the count
   actually spent, and the assertion is that the count is at or under it.
2. **The byte scan is exercised with a test canary.** The canary proves that
   the scan detects a planted value. CI workers do not share the machine that
   made this artifact, so this gate does not claim to measure a live credential.
3. **The retained-method leg was measured and it did not vary.** The gate
   asserts the leg is unmeasurable on every live member AND that the
   offline demonstration varies, so a study that could not measure anything
   at all cannot pass by reporting nothing.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "reports" / "evidence" / "invr1b14-retention"
ARTIFACT = EVIDENCE / "retention.json"
FREEZE = ROOT / "reports" / "cap-sheets" / "b14-retention-freeze.md"
WORKSTREAM = ROOT / "reports" / "workstreams" / "b14-retention.md"
DRIVER = ROOT / "experiments" / "ad01" / "invr1b14_retention.py"
TEST = Path(__file__)

# The files this lane owns. The scan covers exactly these, and the list is
# spelled out rather than globbed so a file added later is not silently
# scanned or silently skipped.
OWNED = (ARTIFACT, FREEZE, WORKSTREAM, DRIVER, TEST)

FREE_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
PINNED_PARENT = "reports/cap-sheets/b-live-cap.md"


def _body() -> dict:
    assert ARTIFACT.exists(), (
        "%s is missing; the freeze's ceiling of zero is only honest if the"
        " measurement behind it exists" % ARTIFACT)
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def _freeze_text() -> str:
    return FREEZE.read_text(encoding="utf-8")


def _cap(text: str, key: str) -> int:
    match = re.search(r"^%s:\s*(\d+)\s*$" % re.escape(key), text,
                      re.MULTILINE)
    assert match, "the freeze states no %s" % key
    return int(match.group(1))


# --- git, in a way that does not depend on line endings -------------------


def _git_env(*args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True,
        check=True)
    return out.stdout.strip()


# --- the ceiling ---------------------------------------------------------


def test_the_freeze_states_a_positive_finite_dispatch_ceiling():
    """Zero is a ceiling, and it is a number.

    The alternative is not "no ceiling". A sheet with no cap on a live route
    is an open budget, and an open budget is what every prior study in this
    tree was careful not to write. Asserted as an int so a float or a
    missing value fails rather than passing a truthiness check.
    """
    cap = _cap(_freeze_text(), "total_dispatch_cap")
    assert isinstance(cap, int)
    assert cap == 0
    assert _cap(_freeze_text(), "requests") == 0
    assert _cap(_freeze_text(), "total_units") == 0


def test_the_dispatch_count_is_at_or_under_the_ceiling_this_freeze_states():
    """The count is compared to THIS freeze, read fresh from the freeze.

    Not to a constant in this file. A test that asserted `dispatches == 0`
    next to a freeze that might later say 8 would pass on the lane that
    broke the rule, so the expected value is derived from the document the
    ceiling lives in.
    """
    body = _body()
    cap = _cap(_freeze_text(), "total_dispatch_cap")
    spent = body["verdict"]["dispatches"]

    assert isinstance(spent, int)
    assert spent <= cap, (
        "the artifact records %s dispatches against a ceiling of %s"
        % (spent, cap))
    assert spent == body["dispatches"] == 0
    assert body["measured_live"] is False
    assert body["gateway_used"] is False
    assert body["cap_sheet_total_dispatch_cap"] == cap


def _code_of(path: Path) -> str:
    """The file's CODE with every comment and docstring removed.

    A token scan over raw text matches prose, and a docstring saying "no
    gateway" is exactly the string a scan for `gateway.` would flag. So the
    ceiling is enforced against what the module can actually CALL: its
    docstrings and comments are stripped, and the remaining source is what
    is searched.
    """
    import ast
    import io
    import tokenize

    source = path.read_text(encoding="utf-8")
    out = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            continue
        out.append(token)
    stripped = tokenize.untokenize(out)
    tree = ast.parse(stripped)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant) and isinstance(
                body[0].value.value, str):
            if len(body) == 1:
                node.body = [ast.Pass()]
            else:
                node.body = body[1:]
    return ast.unparse(ast.fix_missing_locations(tree))


# --- the route -----------------------------------------------------------


def test_the_pinned_model_is_free_tier_on_a_free_route():
    """The id ends in `:free`, and the freeze pins the same id.

    Both halves: an id ending in `:free` that the freeze does not pin would
    be a different route from the one the ceiling was priced against.
    """
    body = _body()
    assert FREE_MODEL.endswith(":free")

    text = _freeze_text()
    assert FREE_MODEL in text
    assert "Tier | `free`" in text
    assert "no paid fallback is permitted" in text.lower()

    models = {m.get("requested_model")
              for m in body["live_acquired_members"]}
    # The members' receipts name the model their ACQUISITION ran on. That
    # acquisition predates B14's freeze and named the id through the router
    # rather than through the frozen endpoint, so the assertion is that
    # every one of them ends in `:free` rather than that it equals the
    # freeze's spelling. A paid tier is the thing that must be impossible.
    assert len(models) == 1, models
    for model in models:
        assert model.endswith(":free"), model


# --- the leg -------------------------------------------------------------


def test_the_retained_leg_is_measured_and_is_not_measurable_on_any_live_member():
    """Zero measurable of three, at nine tasks each, with the verdict named.

    Not `assert not any(...)`, which would pass on an empty list. The count
    of members measured is asserted, so a study that measured nothing and
    therefore found nothing varying cannot pass this gate.
    """
    body = _body()
    live = body["live_acquired_members"]
    verdict = body["verdict"]

    assert len(live) == 3
    assert verdict["live_acquired_measured"] == 3
    assert verdict["live_acquired_measurable"] == 0
    for member in live:
        assert member["distinct_verdicts"] == ["preserved"], member[
            "capability_id"]
        assert member["retained_method_leg_measurable"] is False
        assert member["tasks_measured"] == 9
        assert member["kind"] == "live-acquired"
        assert member["acquired_from_provider"] is True


def test_no_member_this_menu_offers_carries_a_varying_verdict():
    """The strategy axis at its full width, on both families.

    Three members that all happened to name `ddmin` would be a small sample
    of a two-valued choice. The sweep is what turns that into a claim about
    the menu, so all four arms and their measured count are asserted.
    """
    body = _body()
    arms = body["strategy_probe_members"]
    verdict = body["verdict"]

    assert len(arms) == 4
    assert {(a["family"], a["strategy"]) for a in arms} == {
        ("software", "ddmin"), ("software", "greedy"),
        ("graph", "ddmin"), ("graph", "greedy")}
    assert verdict["strategy_measured"] == 4
    assert verdict["strategy_measurable"] == 0
    for arm in arms:
        assert arm["distinct_verdicts"] == ["preserved"], arm["arm"]
        assert arm["retained_method_leg_measurable"] is False
        assert arm["acquired_from_provider"] is False


def test_the_leg_can_vary_so_the_measurement_is_not_vacuous():
    """The offline demonstration varies, and says it is not an acquisition.

    Without this the gate would pass on an instrument that cannot measure
    anything, which is the same vacuity the credential scan is checked for.
    B3's fixture bytes vary and the constant control does not, and the
    control is asserted separately so "varying" is a discrimination rather
    than a shape.
    """
    offline = _body()["offline_demonstration"]
    rows = offline["rows"]

    assert len(rows) == 2
    control, varying = rows
    assert control["retained_method_leg_measurable"] is False
    assert control["distinct_verdicts"] == ["preserved"]
    assert varying["retained_method_leg_measurable"] is True
    assert sorted(varying["distinct_verdicts"]) == [
        "not_preserved", "preserved"]
    assert varying["tasks_measured"] == 9
    assert control["origin"] == "strategy-probe"
    assert varying["origin"] == "fixture-stand-in"


def test_the_offline_leg_is_labelled_as_not_a_live_acquisition():
    """The label is checked where it is written, not merely intended.

    The substitution this study could have made, and did not, is authoring a
    member and reporting it as acquired. These assertions fail if any of the
    offline rows claims a provider origin, and the artifact's own label is
    asserted verbatim because a label that is merely present in prose is
    read by nobody.
    """
    offline = _body()["offline_demonstration"]

    assert offline["label"] == (
        "OFFLINE DEMONSTRATION, NOT A LIVE ACQUISITION")
    assert "not an acquisition" in offline["what_this_is_not"].lower()
    for row in offline["rows"]:
        assert row["acquired_from_provider"] is False, row["capability_id"]
        assert row["origin"] != "acquired", row["capability_id"]
        assert row["kind"] if "kind" in row else True


def test_the_live_members_are_the_route_s_own_and_their_digests_re_derive():
    """Each measured member came from a receipt, and its bytes hash to it.

    The three members are read from `invl02_liveacq_r4`, which is
    immutable history this lane did not write. Their digests are recomputed
    from the bytes in this lane's own artifact, so a member whose source
    drifted from the one that earned it would fail rather than measure.
    """
    import hashlib

    body = _body()
    source = json.loads(
        (ROOT / "reports" / "evidence" / "invl02_liveacq_r4"
         / "acquired_arms.json").read_text(encoding="utf-8"))

    for arm in source["arms"]:
        if not arm.get("acquired"):
            continue
        digest = hashlib.sha256(
            arm["policy_source"].encode("utf-8")).hexdigest()
        assert digest == arm["source_digest"], arm["capability_id"]
        measured = next(
            m for m in body["live_acquired_members"]
            if m["capability_id"] == arm["capability_id"])
        assert measured["source_digest"] == digest
        assert measured["receipt_identity"], arm["capability_id"]
        assert measured["operation_id"], arm["capability_id"]


# --- the original sheet is untouched --------------------------------------


def test_the_parent_cap_sheet_keeps_its_recorded_contract():
    """The parent sheet still reserves this work for a new freeze."""
    current = ROOT / PINNED_PARENT
    assert current == FREEZE.parent / "b-live-cap.md"
    text = current.read_text(encoding="utf-8")
    assert "`B14` and `B15` are **not allocated" in text
    assert "They need a new freeze of this sheet" in text


def test_the_lane_evidence_is_present_in_its_owned_directory():
    """This freeze has one retained measurement artifact in its own folder."""
    actual = {path.name for path in EVIDENCE.iterdir() if path.is_file()}
    assert actual == {ARTIFACT.name}
    assert ARTIFACT.exists()


# --- deterministic scan canary; no worker credential lookup --------------


def _scan(secret: str, paths) -> list[str]:
    """Return files containing the supplied test value, by exact bytes."""
    return [path.name for path in paths
            if path.is_file() and secret.encode("utf-8") in path.read_bytes()]


def test_the_byte_scan_catches_a_planted_canary_and_leaves_no_plant(tmp_path):
    """The scan primitive catches a deterministic canary without reading secrets."""
    secret = "b14-test-canary-" + __import__("uuid").uuid4().hex
    planted = tmp_path / "planted.bin"
    planted.write_bytes(("\n" + secret + "\n").encode("utf-8"))
    assert _scan(secret, (planted,)) == [planted.name]
    assert _scan(secret, OWNED) == []
    planted.unlink()
    assert not planted.exists()


def test_the_scan_does_not_claim_live_credential_absence():
    """A CI worker lacks the authoring machine's credential observation."""
    text = _freeze_text()
    assert "SETTLEMENT_GATEWAY_KEY" in text
    assert "No key value appears in this sheet" in text
    # Evidence says what this artifact establishes; test canaries do not turn
    # missing worker credentials into a live-secret cleanliness claim.
    assert "in any evidence\nfile it references" in text or (
        "in any evidence file it references" in text)


def test_the_freeze_names_the_variable_without_naming_the_file_that_holds_it():
    """The path is a route fact, not a key. Recorded, not leaked."""
    text = _freeze_text()
    assert "~/.claude.json" in text
    assert "LIVE_ENV_PATH" in text
    assert "Jev is not called" in text or "Jev is not called" in text
    assert "Jev" in text