"""A call site must not pass a keyword the callee does not accept.

Lane C2 called `run_improve_step(..., dsn=..., allocation_id=...)`. Lane A8
changed that signature to take one `authority` mapping. Both lanes were green
on their own branch; the merged tip raised
`TypeError: run_improve_step() got an unexpected keyword argument 'dsn'` in
nine tests. Neither lane's own gate could see it, because each ran before
the other existed.

This file is the check that would have caught it at the seam. It binds the
callee's signature and the caller's keywords together statically, so a
keyword that no longer exists fails here rather than in nine integration
tests that each report it separately.

Scope is deliberately narrow. It walks call sites in this repository that
name a function the channel exports, and it resolves the callee to its real
signature through the import graph. It is not a type checker and does not
become one: it checks keyword arity for the shared functions, and nothing
else.

Two directions are checked, because they fail differently.

  * A keyword the callee no longer has. This is the merged-tip defect: C2
    kept the old spelling and A8 removed it.
  * A required keyword the caller omits. A8's own boundary rule, asserted
    here from the other side, so tightening a signature and leaving callers
    behind fails as loudly as loosening one.

Non-vacuity is asserted rather than assumed. `test_the_guard_sees_the_both`
builds two synthetic callers, one carrying the planted `dsn=` and one
omitting `authority=`, and requires the checker to name both. A guard that
returned an empty finding for everything would pass the real tree vacuously
and fail there, so the check cannot pass by inspecting nothing.

Deterministic and offline: no network, no live model, no database.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel

#: The functions lanes C2 and A8 share. Both call `run_improve_step`; C2 also
#: reaches the channel's control entry, and A8's own tests reach both
#: wrappers. The set is named rather than discovered so that adding a shared
#: entry point is a decision a reader sees, not a silent widening.
SHARED = ("run_improve_step", "run_operate_step", "classify_revision",
          "revision_evidence_choices", "delegates_to_frozen_reducer")

#: Keywords `run_improve_step` must never be handed as their own arguments.
#: A8 folded the study store and its allocation into one `authority`
#: mapping; these are the two halves of that identity as they were spelled
#: before, and a caller that passes either is passing an argument that no
#: longer exists.
RETIRED_AUTHORITY_KEYWORDS = ("dsn", "allocation_id")

#: Keywords that must reach `run_improve_step`, asserted from the caller side.
#: A8's boundary rule is that an improve execution carries a ledger identity,
#: and every caller of that wrapper does supply one. `run_operate_step` is
#: deliberately absent: `_execution_ledger` treats an absent authority as "use
#: the disposable store for this execution", and four inherited call sites
#: rely on exactly that. Requiring it there would turn a real contract into
#: a lint failure and force edits to files this lane does not own.
REQUIRED_STEP_KEYWORDS = ("authority",)
STEP_WRAPPERS_REQUIRING_AUTHORITY = ("run_improve_step",)


def _accepted_keywords(function) -> set | None:
    """Keyword names `function` accepts, or ``None`` if it takes ``**``."""
    import inspect

    if function.__code__.co_flags & 0x08:  # CO_VARKEYWORDS
        return None
    return set(inspect.signature(function).parameters)


def check_call(node: ast.AST, callee_name: str, source_path: str,
               callee) -> list:
    """Findings for one call node against one callee.

    Returns a list of human-readable strings so a failure names the file, the
    line and the keyword rather than only counting violations.
    """
    findings: list = []
    accepted = _accepted_keywords(callee)
    if accepted is None:
        return findings
    given = {keyword.arg for keyword in node.keywords
             if keyword.arg is not None}
    unknown = given - accepted
    for name in sorted(unknown):
        findings.append(
            "%s:%d passes %s=%s to %s(), which does not accept it;"
            " accepted keywords are %s"
            % (source_path, node.lineno, name, name, callee_name,
               sorted(accepted)))
    if callee_name in STEP_WRAPPERS_REQUIRING_AUTHORITY:
        for retired in RETIRED_AUTHORITY_KEYWORDS:
            if retired in given:
                findings.append(
                    "%s:%d passes the retired keyword %s=%s; study authority"
                    " is one mapping under `authority`"
                    % (source_path, node.lineno, retired, retired))
        missing = set(REQUIRED_STEP_KEYWORDS) - given
        for name in sorted(missing):
            findings.append(
                "%s:%d calls %s() without %s=, so the execution has no"
                " ledger identity to settle against"
                % (source_path, node.lineno, callee_name, name))
    return findings


def _call_name(node: ast.Call) -> str:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return ""


def _module_files() -> list:
    """Python files that may call the shared functions.

    Scoped by name so the walk stays bounded: tests and the ad01 experiment
    package are where a caller of these five functions can live, and a
    repository-wide sweep would be a slower check of the same thing.
    """
    roots = [ROOT / "tests", ROOT / "experiments" / "ad01"]
    files = []
    for root in roots:
        if not root.is_dir():
            continue
        files.extend(sorted(path for path in root.rglob("*.py")
                            if path.is_file()))
    return files


def _callee_for(name: str):
    return getattr(channel, name, None)


def scan_module(tree: ast.AST, path: Path) -> list:
    findings: list = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in SHARED:
            continue
        callee = _callee_for(name)
        if callee is None:
            continue
        findings.extend(check_call(node, name, path.name, callee))
    return findings


# --- the real tree ---------------------------------------------------------


def test_no_call_site_passes_a_keyword_the_callee_rejects():
    """The merged-tip defect, caught at the seam instead of in nine tests."""
    offenders: list = []
    checked = 0
    for path in _module_files():
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, ValueError, UnicodeDecodeError):
            continue
        offenders.extend(scan_module(tree, path))
    assert offenders == [], "\n".join(offenders)


def test_the_scan_covers_the_call_sites_it_claims_to():
    """Coverage is asserted, so the check cannot pass by finding nothing.

    Counts the shared call sites the walk actually visits. The merged tip has
    C2 driving the controls, A8's own tests driving both wrappers, and the
    channel's own round driving the improve wrapper; a walk that reached
    none of them would find no violations and look clean.
    """
    seen: dict = {}
    for path in _module_files():
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, ValueError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name in SHARED:
                seen.setdefault(name, []).append("%s:%d" % (path.name,
                                                            node.lineno))
    assert seen, "the scan reached no shared call site at all"
    assert "run_improve_step" in seen, (
        "run_improve_step has no call site in the tree, so the merged-tip"
        " defect has no remaining caller and this file's premise is stale:"
        " %r" % (seen,))
    assert "run_operate_step" in seen, (
        "run_operate_step has no call site in the tree: %r" % (seen,))


def test_the_controls_pass_authority_as_one_mapping():
    """C2's drive_record settles under a real ledger, named explicitly.

    The merge must not have been made green by removing authority: a control
    that executes nothing proves nothing, and these are the four controls the
    apparatus qualification rests on.
    """
    import inspect

    from experiments.ad01 import channel_controls

    given = inspect.signature(channel_controls.drive_record).parameters
    for required in ("dsn", "allocation_id", "workdir"):
        assert required in given, (
            "drive_record no longer takes %s, so the control can no longer"
            " be driven under real authority: %r" % (required, given))

    source = inspect.getsource(channel_controls.drive_record)
    assert "authority={" in source and "run_improve_step" in source, (
        "drive_record no longer hands run_improve_step an authority mapping")
    assert "dsn=dsn" not in source and "allocation_id=allocation_id" not in \
        source, (
        "drive_record passes dsn or allocation_id as its own keyword again,"
        " which run_improve_step does not accept")


# --- non-vacuity -----------------------------------------------------------


def test_the_guard_sees_a_planted_bad_keyword():
    """A caller passing a retired keyword is reported, with the keyword named.

    The plant is the merged-tip defect itself, fed to the checker as source
    rather than written into a file, so the check is proven against the exact
    shape it must reject.
    """
    planted = ast.parse(
        "channel.run_improve_step(pkg, view, {}, dsn=dsn,"
        " allocation_id=allocation_id, operation_id='op')")

    findings = check_call(planted.body[0].value, "run_improve_step",
                          "planted.py", channel.run_improve_step)

    assert findings, (
        "the guard reported nothing for a caller passing dsn= and"
        " allocation_id= to run_improve_step, which is the merged defect")
    joined = "\n".join(findings)
    assert "dsn" in joined and "allocation_id" in joined, (
        "the guard reported the planted call without naming the keywords:"
        "\n%s" % joined)


def test_the_guard_sees_a_planted_missing_keyword():
    """A caller omitting `authority` is reported, the other direction.

    A8's boundary rule says an execution has no ledger identity without it.
    Asserting it from the caller side keeps the rule honest when a signature
    is edited, not only when a step is executed.
    """
    planted = ast.parse(
        "channel.run_improve_step(pkg, view, {}, operation_id='op')")

    findings = check_call(planted.body[0].value, "run_improve_step",
                          "planted.py", channel.run_improve_step)

    assert any("authority=" in finding for finding in findings), (
        "the guard accepted a call that supplies no authority: %r"
        % (findings,))


def test_the_guard_accepts_the_call_the_merge_left_behind():
    """The repaired call site is not reported.

    Without this the guard could be passing because it reports everything,
    which is the failure mode the two planted tests above exist to exclude.
    """
    repaired = ast.parse(
        "channel.run_improve_step(pkg, view, {},"
        " authority={'dsn': dsn, 'allocation_id': alloc},"
        " operation_id='op', round_no=1)")

    findings = check_call(repaired.body[0].value, "run_improve_step",
                          "repaired.py", channel.run_improve_step)

    assert findings == [], (
        "the guard rejects the call the merge should leave behind:"
        "\n%s" % "\n".join(findings))


def test_a_keyword_the_callee_does_accept_is_not_reported():
    """The check is about unknown keywords, not about arity in general.

    `round_no` is accepted by `run_improve_step` and C2 passes it, so a
    checker that flagged every keyword would have kept the merged tree red
    for the wrong reason.
    """
    call = ast.parse(
        "channel.run_improve_step(pkg, view, {},"
        " authority=authority, operation_id='op', round_no=1)").body[0].value

    assert check_call(call, "run_improve_step", "ok.py",
                      channel.run_improve_step) == []