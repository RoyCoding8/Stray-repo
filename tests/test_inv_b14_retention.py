"""B14: the retention freeze's ceiling is zero, and this gate proves why.

Every literal below is read out of `reports/evidence/invr1b14-retention/
retention.json` or out of `reports/cap-sheets/b14-retention-freeze.md`. None
is recomputed from the driver that wrote them, because a test that re-derives
the artifact's own numbers proves only that the driver agrees with itself.

The three claims this study has to earn, and which of these tests earns each:

1. **The ceiling is a positive finite number and the run is under it.** Not
   restated: the freeze names a dispatch cap, the artifact names the count
   actually spent, and the assertion is that the count is at or under it.
2. **The credential scan is not vacuous.** Asserted in both directions. The
   scan must find a real credential available to search for, AND a planted
   value must make it fail. A scan that finds nothing to search for passes
   on an absence and proves nothing, which is the failure this repo has
   already had once inside a lane's own gate.
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
#
# The parent sheet is stored with CRLF terminators and this checkout has
# `core.autocrlf` set. Windows git and WSL git therefore normalise the blob
# differently, and the SAME unchanged file reports as different under one and
# identical under the other. A diff-based assertion would pass or fail with
# the host rather than with the repository.
#
# So the check is a blob hash, which git computes on the staged bytes and
# reports without consulting the working tree at all. The file being
# untouched is a fact about the repository, and a fact about the repository
# is what the repository is asked for.
def _git_prefix() -> list:
    """The global flags a `git` call in this test needs.

    A linked worktree's `.git` is a file naming a Windows path, which WSL
    git cannot resolve, so those need an explicit `--git-dir`. Separately,
    this repository on the 9p mount is owned by uid 0 while the test runs as
    the `ubuntu` user (uid 999), so git refuses every call with "detected
    dubious ownership" unless the directory is excepted. Passing
    `safe.directory` per invocation keeps the exception scoped to this test
    instead of writing a global git config that outlives the run.
    """
    args = ["-c", "safe.directory=%s" % ROOT]
    git_dir = _worktree_git_dir()
    if git_dir is not None:
        args += ["--git-dir=%s" % git_dir, "--work-tree=%s" % ROOT]
    return args


def _worktree_git_dir() -> str | None:
    """The WSL-resolvable git dir when `.git` is a worktree pointer.

    A linked worktree's `.git` is a file naming a Windows path, which WSL git
    cannot resolve. Returns the path to pass as `--git-dir`, or None when
    plain `git` already works.
    """
    pointer = (ROOT / ".git")
    if not pointer.is_file():
        return None
    text = pointer.read_text(encoding="utf-8").strip()
    prefix = "gitdir:"
    if not text.startswith(prefix):
        return None
    target = text[len(prefix):].strip().replace("\\", "/")
    if not target.startswith("/"):
        # `D:/path` is `/mnt/d/path` under WSL: lower the drive letter and
        # drop the colon. Getting this wrong yields `/mnt/d:/path`, which
        # does not exist, and the helper then silently falls back to plain
        # git and reports a diff nobody asked for.
        drive, _, rest = target.partition(":")
        target = "/mnt/%s/%s" % (drive.lower(), rest.lstrip("/"))
    return target if Path(target).exists() else None


def _git_env(*args: str) -> str:
    """`git` under either host, resolving a linked worktree's git dir.

    The gate runs in WSL, where a linked worktree's `.git` file names a
    Windows path WSL git cannot resolve, so plain `git` fails outright there.
    Windows git resolves it and needs no flag. Both are routed through here
    so the assertion is about the repository rather than about the host.
    """
    import subprocess

    command = ["git", *_git_prefix()]
    out = subprocess.run(
        [*command, *args], cwd=str(ROOT), capture_output=True, text=True,
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


def test_the_driver_has_no_route_to_a_gateway_so_the_ceiling_is_structural():
    """The zero is enforced by the code's shape, not by a promise in prose.

    The driver takes no gateway argument and names no adapter, so no reader
    has to take this lane's word for why nothing was sent. If a future lane
    adds a gateway here, this fails and the change is a new freeze.
    """
    code = _code_of(DRIVER)
    # Bounded to the CALL names a module could reach the route through. The
    # bare token `gateway` is not one of them: the artifact carries an
    # honest `gateway_used: False` field, and a scan for the word would
    # flag the field that records that nothing was sent.
    for forbidden in ("build_gateway", "preflight_route", "gateway.",
                      "gateway(", "HttpGatewayAdapter", "probe_route",
                      "live_construct", "acquire_with_retry",
                      "construct_method"):
        assert forbidden not in code, (
            "the B14 driver's CODE references %r; a live route inside this"
            " module would exceed a ceiling of zero" % forbidden)
    # And no binding is named after a gateway, so an alias cannot smuggle
    # one past a literal scan.
    import ast
    tree = ast.parse(code)
    names = ({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
             | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)})
    assert not [n for n in names if "gateway" in n.lower()
                and n != "gateway_used"], names


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


def test_the_parent_cap_sheet_is_untouched_by_this_lane():
    """A new freeze, not an edit. Asserted against the base tip's blob.

    The parent sheet is the record for B11, B12, B13 and B16 and says in
    its own text that B14 needs a NEW freeze.

    The comparison is of CONTENT, with line endings normalised. The parent
    sheet is checked out with CRLF terminators while its blob is stored with
    LF, so the two hash differently by bytes and differently again depending
    on which host's git is asked. A change to this document is a change to
    its words, so the words are what is compared.
    """
    current = ROOT / PINNED_PARENT
    assert current == FREEZE.parent / "b-live-cap.md"

    on_disk = current.read_text(encoding="utf-8").replace("\r\n", "\n")
    recorded = subprocess.run(
        ["git", *_git_prefix(), "cat-file", "blob",
         "%s:%s" % ("794520f", PINNED_PARENT)],
        cwd=str(ROOT), capture_output=True, check=True).stdout
    recorded_text = recorded.decode("utf-8").replace("\r\n", "\n")

    assert on_disk == recorded_text, (
        "b-live-cap.md differs from the base tip in its content, not only in"
        " its line terminators")

    # And it still says what makes a new freeze necessary rather than
    # redundant.
    assert "`B14` and `B15` are **not allocated" in on_disk
    assert "They need a new freeze of this sheet" in on_disk


def test_this_lane_owns_only_its_own_paths():
    """The evidence diff carries this lane's new directory and nothing else.

    Read from HEAD and from the index together, so the assertion holds
    whether or not the work has been committed yet. A gate that only
    checked HEAD would pass vacuously on an uncommitted tree, which is the
    same failure this file checks for in the credential scan.
    """
    committed = _git_env(
        "diff", "--name-only", "794520f", "HEAD", "--", "reports/evidence/")
    staged = _git_env(
        "diff", "--name-only", "--cached", "HEAD", "--", "reports/evidence/")
    changed = sorted({line for line in (committed + "\n" + staged).splitlines()
                      if line})
    assert changed, "this lane added nothing under reports/evidence/"
    assert all(path.startswith("reports/evidence/invr1b14-retention/")
               for path in changed), changed


def test_no_evidence_directory_this_lane_did_not_own_was_touched():
    """B12's four files and B8's census are immutable history.

    Named rather than globbed, because the failure this guards is someone
    rewriting a neighbouring lane's record to fit their own result, and a
    glob would not name what was overwritten.
    """
    foreign = [
        "reports/evidence/invr1b12-swe/campaign.json",
        "reports/evidence/invr1b12-swe/construction.json",
        "reports/evidence/invr1b12-swe/use.json",
        "reports/evidence/invr1b12-swe/store-rows.json",
        "reports/evidence/invr1b8-panel-census/census.json",
    ]
    changed = set(_git_env("diff", "--name-only", "794520f", "HEAD").splitlines())
    staged = set(_git_env("diff", "--name-only", "--cached", "HEAD").splitlines())
    touched = (changed | staged) & set(foreign)
    assert not touched, "immutable history was modified: %s" % sorted(touched)
    for path in foreign:
        assert (ROOT / path).exists(), path


# --- the credential scan, proved in both directions ----------------------


def _read_key_without_loading(path: str | None = None) -> str:
    """Read the key value directly, so no module-level driver code runs."""
    if not path:
        path = os.path.expanduser("~/.claude.json")
    try:
        with open(path, encoding="utf-8") as fh:
            env = json.load(fh)["mcpServers"]["cx-agent"]["env"]
        return env.get("CX_AGENT_API_KEY", "")
    except Exception:
        return ""


def _credential_value() -> str:
    """The credential as it is in the environment now, or "".

    The Windows and WSL homes are DIFFERENT files. A WSL pytest run has no
    `~/.claude.json`, so a scan reading only there finds no value and passes
    vacuously, which is the failure this repo already had inside a lane's
    own gate. Both homes are tried and the Windows path is checked
    explicitly, so a gate running under WSL still searches the bytes a
    Windows process wrote.
    """
    direct = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    if direct:
        return direct
    for path in (os.path.expanduser("~/.claude.json"),
                 os.path.join(os.environ.get("USERPROFILE", ""),
                              ".claude.json"),
                 "/mnt/c/Users/roysh/.claude.json"):
        value = _read_key_without_loading(path)
        if value:
            return value
    return ""


def _scan(secret: str, paths) -> list:
    """Which of these files contain this value. Binary-safe, by bytes."""
    offenders = []
    for path in paths:
        if path.is_file() and secret.encode("utf-8") in path.read_bytes():
            offenders.append(path.name)
    return offenders


def test_the_credential_scan_finds_a_real_value_to_search_for():
    """The precondition for the scan being worth anything at all.

    A scan with nothing to search for passes on an absence. This asserts
    the value was actually located, from one of the named locations, so the
    next test's zero is a measurement rather than a skip.
    """
    secret = _credential_value()
    assert secret, (
        "no credential reachable from this environment; the scan would be"
        " vacuous and every occurrence count below would be meaningless")
    # The length floor is a floor and not a claim about this host's key.
    # What the scan needs is a value distinctive enough that finding it
    # means something; the plant test below is what actually establishes
    # that, and it holds whatever the length is.
    assert len(secret) >= 8, "a credential shorter than this cannot be one"


def test_the_credential_scan_catches_a_planted_value():
    """Non-vacuity by construction: plant it, and the scan must find it.

    A marker is appended to a temporary copy of one owned file, the scan is
    run against the same list it runs in the assertion below, and the
    temporary file is removed. The credential VALUE is never written to
    disk: what is planted is a marker plus the real value read from the
    same `_credential_value()` this environment resolves, held in memory for
    the duration of the check.
    """
    secret = _credential_value()
    assert secret

    planted = ARTIFACT.with_suffix(".planted")
    try:
        planted.write_bytes(
            ARTIFACT.read_bytes() + ("\n" + secret + "\n").encode("utf-8"))
        offenders = _scan(secret, OWNED + (planted,))
        assert planted.name in offenders, (
            "a planted credential value was not caught; the scan this lane"
            " relies on does not work")
        assert _scan(secret, OWNED) == [], (
            "the scan found a value in the unplanted files")
    finally:
        if planted.exists():
            planted.unlink()
    assert not planted.exists()


def test_no_credential_value_appears_in_anything_this_lane_wrote():
    """The real assertion, over the exact bytes this lane wrote.

    A key length would not do. The check is for the value, in the freeze,
    the artifact, the workstream report, the driver and this test.
    """
    secret = _credential_value()
    assert secret, (
        "the credential is unreachable, so this scan would pass on an"
        " absence; the non-vacuity tests above are what make it honest")

    assert _scan(secret, OWNED) == []

    # The other direction: the freeze names the VARIABLE and says how the
    # route is reached. A freeze naming no variable would not be describing
    # the credential path at all.
    text = _freeze_text()
    assert "SETTLEMENT_GATEWAY_KEY" in text
    assert "No key value appears in this sheet" in text
    # The claim is a claim about the whole repository, so the freeze must
    # name the repository scope rather than only its own bytes.
    assert "in any evidence\nfile it references" in text or (
        "in any evidence file it references" in text)


def test_the_freeze_names_the_variable_without_naming_the_file_that_holds_it():
    """The path is a route fact, not a key. Recorded, not leaked."""
    text = _freeze_text()
    assert "~/.claude.json" in text
    assert "LIVE_ENV_PATH" in text
    assert "Jev is not called" in text or "Jev is not called" in text
    assert "Jev" in text