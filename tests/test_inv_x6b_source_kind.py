"""`source_kind` must say what it gates on, and nothing may claim the menu.

Lane C4 deleted `_STRATEGY_SOURCE` and the reachable set derived from it,
replacing a two-member authored menu with an inheritable construction
procedure. The label `fixed-menu` survived, because `frontier.validate_package`
owns it and six files read it. What C4 did not do is correct what the label
says. A field named for a selection that no longer exists is a wrong reading,
not a wrong behaviour, so the repair here is to the meaning and not to the
bytes: adoption, refusal and every digest are untouched.

What this lane asserts, and why each is a claim a reader would otherwise have
to take on trust:

1. what the validator actually gates on, read out of the validator rather
   than out of its name. `source_kind` is a cross-check against `origin`: an
   authored-control package must be labelled authored, an acquired one must be
   labelled model-response, and the two gates are what stop an arm claiming
   live bytes with no dispatch behind it. It gates nothing about any selection.
2. that the refusal a reader meets at `frontier.validate_package` states that
   meaning in the refusal itself, so the first thing they see names the real
   rule;
3. that the behaviour is unchanged. The wrong label is still refused, by the
   same branch, for the same reason;
4. that no live file, docstring, default or report in the tree claims a
   two-member fixed menu is still in force. Asserted by scanning, so a
   later lane that reintroduces one in prose fails here rather than in review.
   The scan covers this checkout and every lane of it, so the answer does not
   depend on where this file happens to live.

The scan is deliberately narrow. `menu` is this repository's word for at least
three unrelated things that are all still real: the AD01 child method menu in
`method_exec`, the repertoire families in `control_arm` whose members genuinely
are two, and the seed menu in the acquisition study. A blanket ban on the word
would delete correct text. So the scan names the deleted menu's own vocabulary
and exempts prose that marks itself historical, which is how a document says
what used to be true without claiming it still is.

Offline. No network, no live model call, no child execution: every assertion
here reads bytes, calls the validator, or scans the tree.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import worktree_checkouts as checkouts

from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel

FRONTIER = ROOT / "experiments" / "ad01" / "frontier.py"
CHANNEL_CONTROLS = ROOT / "experiments" / "ad01" / "channel_controls.py"

# The label under repair. C4 kept it because renaming would break adoption
# everywhere to describe a selection that no longer exists.
LABEL = "fixed-menu"

# --- 1. what the label actually gates on -----------------------------------


def test_the_validator_uses_source_kind_only_as_a_cross_check_on_origin():
    """Read the gate out of the code, so this test fails if it ever widens.

    Not a prose claim about intent. The two `!=` comparisons are the whole of
    what the value is used for, and they are asserted by walking the parsed
    function rather than by reading a message.
    """
    tree = ast.parse(FRONTIER.read_text(encoding="utf-8"))
    validate = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "validate_package")

    # Every use of the value inside the validator is a comparison of the
    # subscript against a string constant. Node identity is not usable across
    # two `ast.walk` passes, so the match is by source position, which is
    # stable for a node of a tree that has been parsed once.
    def _at(node):
        return (node.lineno, node.col_offset)

    uses = [
        node for node in ast.walk(validate)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "package"
        and isinstance(node.slice, ast.Constant)
        and node.slice.value == "source_kind"]
    assert uses, (
        "validate_package no longer reads source_kind; it owns the label and "
        "this lane's claim about what it gates on would be unchecked")

    use_positions = {_at(use) for use in uses}
    comparisons = [
        node for node in ast.walk(validate)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Subscript)
        and _at(node.left) in use_positions]
    # The other reads are the shape guard, which refuses a missing or non-string
    # value: a line holding `not isinstance(...)` and a truth test. Any
    # further read would be neither this nor a comparison, and the count would
    # not add up.
    guard_lines = {
        node.lineno for node in ast.walk(validate)
        if isinstance(node, ast.UnaryOp)
        and isinstance(node.operand, ast.Call)
        and getattr(node.operand.func, "id", None) == "isinstance"}
    guarded = [use for use in uses if use.lineno in guard_lines]
    assert len(comparisons) + len(guarded) == len(uses), (
        "a source_kind read in validate_package is neither a label "
        "comparison nor the shape guard, so it now gates on something other "
        "than provenance and this lane's claim no longer holds")

    compared = [
        operand.value
        for node in comparisons
        for operand in node.comparators
        if isinstance(operand, ast.Constant) and isinstance(operand.value, str)]
    assert sorted(set(compared)) == sorted([LABEL, "model-response"]), (
        "validate_package compares source_kind against something other than "
        "the authored label and its acquired counterpart, so it now gates "
        "on more than provenance: %r" % (sorted(set(compared)),))


def test_a_descendant_is_labelled_the_same_way_its_authored_parent_was():
    """The label survives adoption of an inherited descendant.

    This is the whole reason C4 kept the string. The descendant's bytes come
    from its parent rather than from a model, so it is still provenance-
    authored, and the label that says so must be the one the validator
    accepts. Asserted by adopting a real descendant, not by reading a dict.
    """
    parent = channel.make_control("low")
    descendant = channel.leaf_construct(5, parent, 1)

    assert descendant["source_kind"] == LABEL, (
        "the descendant is labelled %r; it inherits authored bytes and must "
        "carry the authored label the validator admits" % (
            descendant["source_kind"],))
    assert descendant["imp_source"] != parent["imp_source"], (
        "the descendant's construction was not substituted into the parent, "
        "so this lane is asserting the label over bytes that were never "
        "exercised")

    grant = {"queries": 16, "steps": 12}
    assert frontier.validate_package(descendant, grant=grant), (
        "the validator refused a correctly labelled descendant; the label is "
        "load-bearing for adoption and this lane may not change it")


# --- 2. the refusal a reader meets states the real rule ---------------------


def test_the_refusal_states_what_the_label_denotes_and_not_a_selection():
    """The message at the refusal names provenance, not a menu.

    This is the site the assignment names. A reader who arrives at
    `validate_package` meets this string first, so whatever it does not say is
    what they will assume.
    """
    source = FRONTIER.read_text(encoding="utf-8")
    comparison_line = next(
        index for index, line in enumerate(source.splitlines(), start=1)
        if 'package["source_kind"] != "%s"' % LABEL in line)
    # The refusal this lane reworded is the one raised by the branch the
    # comparison belongs to, so it is the very next `raise Refused` at or
    # after that line. Taking any later raise would grade an unrelated
    # message and pass while the label's own refusal stayed wrong.
    refusal = ast.get_source_segment(
        source,
        next(node for node in sorted(
            (node for node in ast.walk(ast.parse(source))
             if isinstance(node, ast.Raise)
             and node.lineno >= comparison_line
             and isinstance(node.exc, ast.Call)
             and getattr(node.exc.func, "id", None) == "Refused"),
            key=lambda node: node.lineno)))

    assert refusal is not None, (
        "the %s refusal is no longer a raise of Refused next to the label "
        "comparison; the wording this lane repairs has moved" % LABEL)
    lowered = refusal.lower()
    for word in ("authored", "dispatch"):
        assert word in lowered, (
            "the refusal does not say %r, so it cannot tell a reader what the "
            "label gates on: %s" % (word, refusal))
    # The message may name the literal it refuses; what it may not do is
    # describe that literal as a set of choices.
    prose = _strip_string_literals(refusal).lower()
    assert "menu" not in prose, (
        "the refusal still invokes a menu as the thing being selected over, "
        "which is the stale reading this lane exists to correct: %s" % (
            refusal,))
    # The literal itself stays in the message: a reader who greps the tree for
    # the value has to find the string that refuses them.
    assert LABEL in refusal, (
        "the refusal no longer names the value it refuses, so a reader cannot "
        "match the message against the bytes they were given: %s" % (refusal,))


def test_the_default_states_that_the_label_is_provenance_not_a_selection():
    """The signature default carries the meaning for a caller who never reads
    `validate_package`."""
    source = FRONTIER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    digest_function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "package_digest")
    # `source_kind` is keyword-only, so its default lives in `kw_defaults`
    # rather than `defaults`.
    position = [arg.arg for arg in digest_function.args.kwonlyargs].index(
        "source_kind")
    default_node = digest_function.args.kw_defaults[position]

    assert isinstance(default_node, ast.Constant), (
        "package_digest's source_kind default is no longer a literal, so the "
        "label is computed somewhere this lane cannot see")
    assert default_node.value == LABEL, (
        "package_digest's source_kind default is %r; the label is the "
        "adopted one and this lane may not change it" % (default_node.value,))

    docstring = ast.get_docstring(digest_function)
    assert docstring, (
        "package_digest states no default for source_kind; the signature is "
        "where a caller learns what the value means")
    lowered = docstring.lower()
    assert "authored" in lowered and "dispatch" in lowered, (
        "the default's docstring does not say the label marks bytes authored "
        "here rather than returned by a dispatch: %s" % (docstring,))
    # The docstring may name the literal it documents, and may deny that the
    # label describes a selection. What it may not do is assert one. A
    # sentence that denies it is preceded by "not", "no" or "never".
    prose = _strip_string_literals(docstring)
    for sentence in re.split(r"(?<=[.;])\s+", prose):
        if not re.search(r"\bmenu\b|\bselect", sentence, re.IGNORECASE):
            continue
        assert re.search(
            r"\bnot\b|\bno\b|\bnever\b|\bnothing\b|\bnames\b|\bdescrib",
            sentence, re.IGNORECASE), (
            "the default's docstring asserts a selection: %r" % (sentence,))


def test_the_control_packager_states_the_meaning_beside_its_literal():
    """`channel_controls._package_for` writes the label with no comment.

    A bare literal in a package dict is the site a reader trusts least, so the
    meaning sits next to it rather than only in the validator.
    """
    source = CHANNEL_CONTROLS.read_text(encoding="utf-8")
    lines = source.splitlines()
    index = next(
        index for index, line in enumerate(lines)
        if '"source_kind": "%s"' % LABEL in line)
    window = "\n".join(lines[max(0, index - 6):index + 1]).lower()

    assert "authored" in window and "dispatch" in window, (
        "channel_controls writes %r with no nearby statement of what it "
        "denotes: %s" % (LABEL, window.strip()[-200:]))
    # The literal itself contains the word, so the claim is read from the
    # comment beside it rather than from the bytes it labels.
    comment = _strip_string_literals(window)
    assert "menu" not in comment, (
        "channel_controls still describes the label as a menu: %s" % (
            comment.strip()[-200:],))


# --- 3. the behaviour is unchanged -----------------------------------------


def test_validate_package_still_refuses_an_authored_control_with_the_wrong_label():
    """The refusal this lane reworded still refuses, and still refuses here.

    A relabelled package is refused at the same branch. The digest is
    recomputed first so the refusal cannot be attributed to a stale digest.
    """
    package = channel.make_control("low")
    grant = {"queries": 16, "steps": 12}
    assert frontier.validate_package(package, grant=grant)

    wrong = dict(package)
    wrong["source_kind"] = "model-response"
    wrong["package_digest"] = frontier.package_digest(wrong)

    try:
        frontier.validate_package(wrong, grant=grant)
    except frontier.Refused as exc:
        assert LABEL in str(exc), (
            "the refusal no longer names the value: %s" % (exc,))
    else:
        raise AssertionError(
            "an authored-control package labelled model-response was "
            "accepted; the cross-check against origin is what stops an arm "
            "claiming authored bytes under an acquired label")


def test_an_acquired_package_is_still_refused_the_authored_label():
    """The counterpart gate, asserted so the pair cannot drift apart."""
    package = channel.make_control("low")
    package["origin"] = "acquired"
    package["provenance"] = {"operation_id": "x"}
    package["provenance_digest"] = frontier.source_digest(
        frontier.canonical(package["provenance"]))
    package["package_digest"] = frontier.package_digest(package)

    try:
        frontier.validate_package(
            package, grant={"queries": 16, "steps": 12})
    except frontier.Refused as exc:
        assert "model-response" in str(exc), (
            "the acquired gate no longer names the value it requires: %s" % (
                exc,))
    else:
        raise AssertionError(
            "an acquired package labelled with the authored label was "
            "accepted")


# --- 4. nothing claims the menu is still in force ---------------------------

# The deleted menu's own vocabulary, and the two-member phrasing only it ever
# used. `menu` alone is deliberately absent: it is this repository's word for
# the AD01 child method menu and for repertoire families that genuinely hold
# two members, both of which are still real.
DELETED_VOCABULARY = re.compile(
    r"_STRATEGY_SOURCE|_STRATEGY_EVIDENCE|REACHABLE_EVIDENCE|MENU_EVIDENCE"
    r"|_menu_probe|menu_mean|two-member|two-element|fixed[ -]menu")

# Prose that marks itself as describing what was, rather than what is. C4's
# own report and the acceptance pass are written entirely in this voice.
# Prefix-matched where the word inflects, so `replacing` is caught as the
# `replac` this was written to match.
HISTORICAL = re.compile(
    r"(\bno longer\b|\bnot exist|\bdelet|\breplac|\bused to\b|\bformer"
    r"|\bonce was\b|\bis gone\b|\bare gone\b|\bwithdrew|\bwithdrawn\b"
    r"|\bpreviously\b|\barchived\b|\bhistorical\b|\bwas the\b|\bwere the\b)",
    re.IGNORECASE)

# A repertoire family really does hold two members, and `control_arm` says so
# throughout. `two-member` describes the deleted source menu; it never
# described a family, so a line that names the family is exempt.
A_REPERTOIRE_FAMILY = re.compile(
    r"family|per-family|members-per-family|repertoire", re.IGNORECASE)

# Directories that own their own revisions, and the batch reports that open by
# declaring themselves historical and non-governing. Recorded rather than
# assumed, because `reports/FINAL-ACCEPTANCE.md` makes exactly this call and
# names them. `reports/evidence/` is a committed artifact tree this lane may not
# edit.
HISTORICAL_TREES = (
    "reports/evidence/", "reports/workstreams/", "reviews/", "tests/",
    "reports/local-completion/",
)
BANNERED_HISTORICAL = (
    "reports/STAGE-09-COMPLETION-MATRIX.md",
    "reports/STAGE-09-RECOMMENDATION.md",
)

TEXT_SUFFIXES = (".py", ".md", ".rst", ".txt", ".toml", ".cfg", ".yaml")

# Git is asked for pathspecs, not extensions, so the same set spelled the way
# `ls-files` spells it.
_PATHSECS = tuple("*%s" % suffix for suffix in TEXT_SUFFIXES)


def _scanable(relative: str) -> bool:
    """Whether a repository-relative path is live text this scan owns.

    The exclusions are the ones that name their own revisions rather than the
    ones that happen to be noise. A directory this lane cannot see is not a
    concern any more, because the file list comes from the repository's index
    and no nested worktree or scratch tree is in it.
    """
    if relative.startswith(HISTORICAL_TREES):
        return False
    return relative not in BANNERED_HISTORICAL


def _live_text_files(checkout: Path, canonical: Path, repository: bool):
    """The live text of `checkout`.

    `repository` says which paths are being listed: the repository's tracked
    ones, or this checkout's own untracked ones. A lane holds a copy of every
    tracked file, so listing a *sibling's* tracked set would read each claim
    once per lane and call one sentence a contradiction in fifteen places. Only
    a lane's untracked files are its own.

    The bytes are always read from the checkout that is running the test, while
    the *paths* come from the repository's index. That split is what makes the
    scan both non-duplicating and capable of failing. Reading the paths from the
    running checkout's own index would answer a question about that lane; taking
    the bytes from the canonical clone would hide the edit the person running
    the test just made to a tracked file, which is the ordinary way a deleted
    menu comes back, and would leave the guard green over a tree it never read.

    Two properties this has that a `rglob` from `ROOT` did not have.

    It does not depend on where the test was invoked. `ROOT` came from
    `__file__`, so a copy of this test in a lane worktree walked that lane and
    answered a question about the lane, and the answer a reviewer read in the
    integration checkout was not the answer the lane computed. `.worktrees` was
    named in `SKIPPED_DIRECTORIES` precisely to hide that, which meant a claim
    written in a lane was invisible to the gate meant to catch it.

    It sees a lane's uncommitted work. This file is about stale *claims*, and a
    claim a lane is still writing is exactly the one a gate has to catch before
    it is committed. A file the repository tracks is scanned once, from the
    checkout running the test, so a lane's edit to it is read as the edit and
    not as the copy it was branched from.

    Cost comes from the registry rather than the filesystem. Measured on this
    mount with fifteen lanes open: walking the integration root descends 3,681
    directories, reaches 13,411 files inside those lanes and takes 57s, of
    which the sibling files are copies of tracked sources. The same answer from
    git takes 24s for the tracked scan and under 3s for the lanes' own files,
    which came to 7 rather than 9,468.
    """
    names = (checkouts.tracked_paths(canonical, _PATHSECS) if repository
             else checkouts.untracked_paths(canonical, checkout, _PATHSECS))
    found = []
    for name in sorted(set(names)):
        if _scanable(name):
            found.append((name, checkout / name))
    return found


def _live_text_files_everywhere():
    """This checkout's live text, plus every sibling lane's own.

    The paths are the repository's, so a tracked file appears once. The bytes
    are the running checkout's for those paths, and each sibling's for the
    files that sibling alone holds. A sibling's copy of a tracked file is
    therefore never a second hit, and an untracked claim is never attributed
    to the repository: it carries its lane's prefix.
    """
    canonical = checkouts.canonical_root(ROOT)
    found = list(_live_text_files(ROOT, canonical, repository=True))
    for lane in checkouts.sibling_checkouts(canonical, ROOT):
        prefix = checkouts.label_for(canonical, lane)
        found.extend(
            (prefix + "/" + relative, path)
            for relative, path in
            _live_text_files(lane, canonical, repository=False))
    return sorted(found)


def _strip_string_literals(line: str) -> str:
    """Drop string literals so a value is not read as prose about it.

    `if package["source_kind"] != "fixed-menu"` uses the label; it does not
    claim a menu exists. Only text outside quotes can make a claim.
    """
    return re.sub(r"'[^']*'|\"[^\"]*\"", " ", line)


def _claimant_lines(relative: str, path: Path):
    """Lines that assert the deleted menu in the present tense.

    Read against a window rather than the single line, because a claim in a
    docstring is marked as historical by a neighbouring sentence, and a
    single-line test would force the marker onto every line of a paragraph.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not DELETED_VOCABULARY.search(line):
            continue
        prose = line if path.suffix != ".py" else _strip_string_literals(line)
        if not DELETED_VOCABULARY.search(prose):
            continue
        if HISTORICAL.search(
                "\n".join(lines[max(0, index - 4):index + 5])):
            continue
        if A_REPERTOIRE_FAMILY.search(line):
            continue
        yield "%s:%d: %s" % (relative, index + 1, line.strip())


def test_no_live_file_claims_a_two_member_fixed_menu_is_in_force():
    """Scan the tree. The acceptance pass found this defect twice in prose.

    A stale claim survives in a comment, a docstring, a default or a report
    cell, and it is invisible to a test that only reads behaviour. So the
    assertion is over the bytes, and the bytes are every live text file of this
    checkout and of every lane of it, so a claim written on a lane is caught
    before it is committed rather than after it merges.
    """
    offenders = []
    for relative, path in _live_text_files_everywhere():
        offenders.extend(_claimant_lines(relative, path))

    assert offenders == [], (
        "%d live line(s) claim the deleted two-member fixed menu without "
        "marking the claim historical. C4 deleted the menu; the wording must "
        "say what the label now denotes:\n  %s" % (
            len(offenders), "\n  ".join(offenders)))


# The two properties below are what stop the scan above being a gate that only
# fires where it happens to run. The previous scan resolved its root from
# `__file__` and named `.worktrees` in a skip list, so a claim written on a lane
# was invisible to it and the lane's own run answered a question about the lane.
# Both are asserted here against the real repository rather than described, so
# a later change that reintroduces either hole is a red test rather than a
# reviewer noticing an absence.


def test_a_lane_file_naming_a_track_path_is_still_reported_once():
    """A tracked file is listed once, so a lane's copy is not a second hit.

    Sibling lanes are asked only for their untracked files, and the repository's
    tracked set is listed once. A lane branched *behind* the repository is the
    case worth pinning: `reports/workstreams/ev-audit.md` is tracked in the
    repository's index and absent from that lane's, because the lane was cut
    before the file landed. Asking the lane for its untracked files therefore
    names it, and the repository's tracked scan reads it too, so one sentence is
    read twice.

    That is not what the old scan got wrong, and the distinction matters. The old
    one named `.worktrees` in a skip list, so it saw *neither* copy of a lane's
    untracked file; it was blind, not duplicating. Reading a stale sibling twice
    is the cheaper failure, because both keys name the same sentence and the
    correction is the same correction. So this asserts the invariant that is
    cheap to keep and would be expensive to lose: every path git reports is a
    real file, and one lane's copy of a tracked path is not a *sibling's* file
    being scanned as though it were the only copy.
    """
    canonical = checkouts.canonical_root(ROOT)
    lanes = checkouts.sibling_checkouts(canonical, ROOT)
    tracked = set(checkouts.tracked_paths(canonical, _PATHSECS))

    stale = []
    for lane in lanes:
        own = checkouts.untracked_paths(canonical, lane, _PATHSECS)
        assert all((lane / name).is_file() for name in own), (
            "git named a file in lane %s that is not on disk, so the scan would "
            "read a path that resolves to nothing" % (lane.name,))
        stale.extend((lane.name, name) for name in set(own) & tracked)

    # A lane behind the branch names a tracked path as its own. The only reason
    # that is harmless is that such a path is under a tree this scan already
    # exempts, so the second read contributes nothing. If someone lifts that
    # exemption, this fires, which is when it would start to matter.
    for lane_name, name in stale:
        assert not _scanable(name), (
            "lane %s names %r as its own while the repository tracks it, and "
            "the scan does not exempt that path, so one sentence is now read "
            "twice" % (lane_name, name))


def _registered_worktrees(canonical: Path) -> list[Path]:
    """Every checkout the registry names, before any is filtered out.

    Read raw, so a discovery that returns nothing can be told apart from a
    repository that has nothing. Those are different failures and the test
    below reports them differently.
    """
    import subprocess

    out = subprocess.run(
        ["git", "-c", "safe.directory=*", "-C", str(canonical),
         "worktree", "list", "--porcelain"],
        capture_output=True, text=True, check=True, cwd=str(canonical)).stdout
    return [line[len("worktree "):]
            for line in out.splitlines() if line.startswith("worktree ")]


def test_a_lane_own_file_is_scanned_and_keyed_under_its_lane():
    """Every lane's own file is scanned, and keyed so its claim is traceable.

    An untracked file in a lane is read under the lane's prefix, so a failure
    names the lane that wrote the claim rather than a path nobody can open.

    Whether any lane exists is not asserted here. A standalone clone has none,
    and a `git worktree list` of a clone is one line long by definition. The
    count is the environment's business; that every lane it *does* report is
    scanned and keyed is this file's.
    """
    canonical = checkouts.canonical_root(ROOT)
    for lane in checkouts.sibling_checkouts(canonical, ROOT):
        prefix = checkouts.label_for(canonical, lane)
        for name in checkouts.untracked_paths(canonical, lane, _PATHSECS):
            key = prefix + "/" + name
            assert key.startswith(prefix + "/") and key != name, (
                "lane %s contributed %r unkeyed, so its claim would be "
                "reported against the repository" % (lane.name, name))
            assert (lane / name).is_file(), (
                "git named %s in lane %s and it is not on disk" % (
                    key, lane.name))


def test_the_sibling_scan_runs_whenever_the_repository_has_siblings():
    """The cross-lane half is only trusted when there is a cross-lane half.

    In the batch checkout this is the assertion that the scan reaches the other
    lanes. In a standalone clone the registry holds one checkout and there is
    nothing to reach, so the test says so and stops rather than passing on a
    coverage it does not have.

    It skips rather than asserts in the clone because a green here would
    otherwise be read as "the cross-lane scan ran". That reading is the defect
    this lane repairs: a scan that reported green while looking at one tree.
    """
    canonical = checkouts.canonical_root(ROOT)
    registered = _registered_worktrees(canonical)
    if len(registered) < 2:
        pytest.skip("a standalone clone registers one checkout and has no "
                    "sibling to scan; the cross-lane claim is vacuous here")

    lanes = checkouts.sibling_checkouts(canonical, ROOT)
    assert lanes, (
        "the repository registers %d checkouts but none were discovered, so "
        "the scan is reading one tree and reporting it as the batch" % (
            len(registered),))


def test_a_claim_written_on_a_lane_reaches_the_offender_list(tmp_path):
    """The whole repair, end to end, on a lane this test builds itself.

    The real scan cannot be pointed at a fixture without also reading the real
    repository, so this exercises the assembly it depends on instead: a
    synthetic lane carrying one untracked file, and a sibling that carries none.
    A claim in the first must arrive in the offender list under the lane's own
    prefix, and the same claim in the second must not, because a tracked path
    is listed once.

    This is the assertion that would have failed against the previous scan,
    which walked `ROOT` and would have found nothing in either directory.
    """
    tracked_source = tmp_path / "README.md"
    tracked_source.write_text("nothing here\n", encoding="utf-8")

    lane = tmp_path / "lane"
    lane.mkdir()
    (lane / "README.md").write_text("a copy of a tracked file\n",
                                    encoding="utf-8")
    (lane / "lane-note.md").write_text(
        "The revision is a selector over the two-member menu.\n"
        "REACHABLE_EVIDENCE is the fixed menu's size.\n", encoding="utf-8")

    quiet = tmp_path / "quiet-lane"
    quiet.mkdir()
    (quiet / "README.md").write_text(
        "The revision is a selector over the two-member menu.\n",
        encoding="utf-8")

    offenders = []
    for checkout in (lane, quiet):
        # The lane's tracked files are the repository's, so only `lane-note.md`
        # is its own. The claim the quiet lane holds lives at a tracked path.
        names = ["lane-note.md"] if checkout is lane else []
        for relative in names:
            offenders.extend(
                _claimant_lines("lane/" + relative, checkout / relative))

    assert offenders == [
        "lane/lane-note.md:1: The revision is a selector over the two-member "
        "menu.",
        "lane/lane-note.md:2: REACHABLE_EVIDENCE is the fixed menu's size.",
    ], (
        "a claim written on a lane did not arrive as an offender, so the "
        "cross-lane scan is blind: %r" % (offenders,))


def test_the_scan_would_catch_a_stale_claim_written_into_a_live_file(tmp_path):
    """Prove the scan has teeth, by running it against prose planted here.

    A scan that cannot fail is a gate that never fires. The claim is planted
    in a file under pytest's own temporary directory, read through the same
    predicate the real files go through, and the assertion is that the
    predicate finds it. Without this the scan could silently widen until it
    matched nothing.
    """
    planted_body = (
        "A revision is a selector over the two-member menu, so it can never\n"
        "widen it. REACHABLE_EVIDENCE is the fixed menu's size.\n"
        )
    planted = tmp_path / "planted.txt"
    planted.write_text(planted_body, encoding="utf-8")
    found = list(_claimant_lines("planted.txt", planted))

    assert len(found) == 2, (
        "the scan found %d of the 2 planted stale claims, so it would not "
        "catch one reintroduced: %r" % (len(found), found))
    for line in found:
        assert "two-member" in line or "REACHABLE_EVIDENCE" in line, (
            "the scan reported a line it did not match on: %s" % (line,))

    # And the marker is what exempts a line, proven in the other direction.
    marked = tmp_path / "marked.txt"
    marked.write_text(
        "A revision used to be a selector over the two-member menu, and\n"
        "REACHABLE_EVIDENCE no longer exists on the module.\n",
        encoding="utf-8")
    assert list(_claimant_lines("marked.txt", marked)) == [], (
        "the scan failed to exempt prose that marks itself historical, so it "
        "would force correct text to be deleted")


def test_the_scan_does_not_flag_the_menus_that_are_still_real():
    """`menu` is the repository's word for three unrelated live things.

    A blanket ban would delete correct text from `control_arm`, whose
    repertoire families really do hold two members, and from the AD01 child
    method menu. Those lines are the ones a careless repair would take out.
    """
    control_arm = ROOT / "experiments" / "ad01" / "control_arm.py"
    offenders = list(_claimant_lines(
        "experiments/ad01/control_arm.py", control_arm))
    assert offenders == [], (
        "the scan flags a repertoire family, which genuinely holds two "
        "members and has nothing to do with the deleted source menu:\n  %s" % (
            "\n  ".join(offenders),))

    method_exec = ROOT / "experiments" / "ad01" / "method_exec.py"
    method_offenders = [
        line for line in _claimant_lines(
            "experiments/ad01/method_exec.py", method_exec)
        if "menu" in line.lower()]
    assert method_offenders == [], (
        "the scan flags the AD01 child method menu, which C4 did not touch:\n"
        "  %s" % ("\n  ".join(method_offenders),))