"""Four settlement-cleanup findings, each pinned by what the code does.

The four differ in kind, and the file says so rather than treating them as one
job. N-49 and N-32 are boundary defects with a mechanical rule. N-31 is a
reachability fact that decides a deletion. N-55 is a judgement about whether a
launcher id is a secret, and the evidence does not support repairing it.

Each test names in its own assertion what makes it fail. Each was shown red
against the pre-repair code before the repair was made, and each assertion was
then shown to have teeth by breaking the behaviour deliberately and watching
the test catch it. Those demonstrations are in the report rather than here,
because a comment claiming a demonstration is not one.

The last four tests restate the guards this lane must not regress. They are
duplicated from tests/test_s09_strand_and_proof.py on purpose: a guard that
lives only in a file another lane may edit is not a guard.

N-31's second half, added 2026-09-29. The deletion the finding licensed was
made at 15166f6, before the two production callers existed, so the
reconciliation the finding deferred was owed when the callers landed. It was
made there too: both paths now read `_study_operation_counts`. What the
earlier tests could not do is prove the shared counter has the property that
motivated it, because every one of them exercises a single path and a counter
that could see only its own subtree would pass all of them. The four tests at
the end of the N-31 block pin that property in both directions, plus the
mixed subtree that is the numeric disagreement itself.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

from settlement import authority, broker, store
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher


ROOT = Path(__file__).resolve().parents[1]


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"s09cl_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn: str, tag: str, authorized: int = 10_000) -> tuple[str, int]:
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "s09clean",
                                 "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": authorized}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "s09clean"}, f"{tag}i"))
    gen = store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                         "investigation_id": f"{tag}-i"},
                                        f"{tag}q")).data["ownership_generation"]
    return f"{tag}-a", int(gen)


def _sandbox(dsn: str, operation_id: str, alloc: str, *, attempt: str,
             execution_version: str = "exec-v1") -> None:
    assert broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 30_000, "max_output_bytes": 4096},
        allocation_id=alloc, attempt_id=attempt,
        execution_version=execution_version).code == ResultCode.APPLIED


# ---------------------------------------------------------------------------
# N-49. execution_version is validated where it is accepted.
#
# The rule is derived from the values the repository actually passes, not
# invented. Collected from src/, experiments/, scripts/ and tests/: "exec-v1",
# "exec-v2", "exec-default", "v1", "run/v1", "" and a build digest. "run/v1"
# (tests/test_r02_authority.py:51) carries a slash, so a rule of "no separator
# at all" would break a value the repository passes. The rule is therefore
# stated as: a bounded-length string of one path segment's worth of safe
# characters, where a segment is a run of [A-Za-z0-9._-]. That admits every
# real value including "run/v1" and refuses every traversal, because a
# traversal is precisely a ".." segment or a leading/absolute separator.
# ---------------------------------------------------------------------------

# Every value a production call site can pass, collected by reading them.
# `team.py:878` and `coord02/policy_exec.py:127,203` pass their module PROFILE,
# which is "team-work/1" and "coordination-procedure/1" - both carry a slash.
# `test_r02_authority.py:51` passes "run/v1". That is why the rule permits "/"
# and why a "no separator" rule is not available.
REAL_EXECUTION_VERSIONS = [
    "",                      # the default at broker.ensure_operation
    "exec-v1",               # tests/test_launchers.py:20
    "exec-v2",               # tests/test_wf_replay_immutable.py:48
    "exec-default",          # tests/test_r01c_redispatch.py:34
    "v1",                    # tests/test_r01_authority.py:103
    "run/v1",                # tests/test_r02_authority.py:51
    "team-work/1",           # src/settlement/team.py:38 via team.py:878
    "coordination-procedure/1",  # experiments/coord02/schemas.py:17
    "representation-01",     # src/settlement/representation.py:36
    "local-process",         # src/settlement/launcher_local.py:33
    "1.2.3",
    "s09-e2e-42",
    "a..b",                   # dots are legal as long as they are not a segment
]

UNSAFE_EXECUTION_VERSIONS = [
    "../etc/passwd",
    "..",
    ".",
    "/etc/shadow",
    "/",
    "a/../b",
    "a\x00b",
    "a\nb",
    "exec v1",
    " exec-v1 ",
    "../",
    "a/..",
]


@pytest.mark.parametrize("execution_version", REAL_EXECUTION_VERSIONS)
def test_a_boundary_admits_every_execution_version_the_repository_passes(
        migrated_db, execution_version):
    """The rule must fit the existing callers, or the repair breaks live studies.

    Fails if the rule is stricter than these values. That is the failure mode
    that turns a boundary check into an outage, and it is the reason the safe
    list is enumerated rather than described.
    """
    dsn = migrated_db
    alloc, _ = _env(dsn, "n49ok")
    op = f"n49ok-op-{uuid.uuid4().hex[:6]}"
    result = store.prepare_operation(dsn, _cmd({
        "operation_id": op, "allocation_id": alloc, "attempt_id": "n49ok-att",
        "operation": {"effect": "sandbox-exec"},
        "execution_version": execution_version}, "n49ok"))
    assert result.code == ResultCode.APPLIED, (
        f"the boundary refused a value the repository actually passes: "
        f"{execution_version!r}: {result.detail}")


@pytest.mark.parametrize("execution_version", UNSAFE_EXECUTION_VERSIONS)
def test_a_boundary_refuses_a_traversing_execution_version(
        migrated_db, execution_version):
    """The accepting boundary must refuse, not defer to a consumer's filter.

    Fails while `prepare_operation` returns APPLIED: the value reaches the
    `operations` column verbatim and its only remaining defence is
    `launcher_local.native_id`'s character filter, in a file this store's
    caller does not own and therefore cannot rely on to keep.
    """
    dsn = migrated_db
    alloc, _ = _env(dsn, "n49bad")
    op = f"n49bad-op-{uuid.uuid4().hex[:6]}"
    result = store.prepare_operation(dsn, _cmd({
        "operation_id": op, "allocation_id": alloc, "attempt_id": "n49bad-att",
        "operation": {"effect": "sandbox-exec"},
        "execution_version": execution_version}, "n49bad"))
    assert result.code is not ResultCode.APPLIED, (
        f"the store accepted a traversing execution_version {execution_version!r} "
        f"verbatim; its only remaining defence is a filter in a consumer")
    row = broker.read_operation(dsn, op) or {}
    assert row.get("execution_version") != execution_version, (
        "and the unsafe value reached the operations column")


def test_a_refused_execution_version_spends_no_reservation(migrated_db):
    """A refusal must leave the store untouched, not half-apply.

    Fails if the check runs after `_take_reservation`: the reservation would be
    consumed and the exposure lost even though the operation was never
    admitted. The check therefore has to precede the reservation.
    """
    dsn = migrated_db
    alloc, _ = _env(dsn, "n49res")
    store.reserve(dsn, _cmd({"allocation_id": alloc, "reservation_id": "n49res-r",
                             "amount": 5, "purpose": "n49"}, "n49resv"))
    before = store.allocation_status(dsn, alloc)["reserved"]
    result = store.prepare_operation(dsn, _cmd({
        "operation_id": "n49res-op", "allocation_id": alloc,
        "reservation_id": "n49res-r", "exposure": 5,
        "operation": {"effect": "sandbox-exec"},
        "execution_version": "../escape", "attempt_id": "n49res-att"}, "n49reso"))
    assert result.code is not ResultCode.APPLIED, result.detail
    assert store.allocation_status(dsn, alloc)["reserved"] == before, (
        "the refused operation consumed a reservation it was never admitted for")
    assert (broker.read_operation(dsn, "n49res-op") or {}).get("id") is None, (
        "the refused operation was still written")


def test_a_replay_of_an_admitted_version_is_still_accepted(migrated_db):
    """Idempotent replay must not break on the new check.

    Fails if the rule is applied to a replay's comparison rather than to the
    value, so an identical replay is refused with a conflict. The store's
    replay contract is that an unchanged operation returns ALREADY_APPLIED.
    """
    dsn = migrated_db
    alloc, _ = _env(dsn, "n49rep")
    payload = {"operation_id": "n49rep-op", "allocation_id": alloc,
               "attempt_id": "n49rep-att",
               "operation": {"effect": "sandbox-exec"},
               "execution_version": "exec-v1"}
    first = store.prepare_operation(dsn, _cmd(dict(payload), "n49rep1"))
    assert first.code == ResultCode.APPLIED, first.detail
    second = store.prepare_operation(dsn, _cmd(dict(payload), "n49rep2"))
    assert second.code == ResultCode.ALREADY_APPLIED, (
        f"an identical replay was refused: {second.code} {second.detail}")


def test_a_broker_ensure_operation_refuses_a_traversing_version(migrated_db):
    """The broker is the caller a policy reaches, so it must carry the rule too.

    Fails while `broker.ensure_operation` still admits a traversing version and
    passes it to the store, which then refuses it as a store error rather than
    a caller error. The property has to hold for whoever calls the store.
    """
    dsn = migrated_db
    alloc, _ = _env(dsn, "n49brk")
    op = f"n49brk-op-{uuid.uuid4().hex[:6]}"
    result = broker.ensure_operation(
        dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 30_000, "max_output_bytes": 4096},
        allocation_id=alloc, attempt_id="n49brk-att",
        execution_version="../escape")
    assert result.code is not ResultCode.APPLIED, (
        f"broker.ensure_operation admitted a traversing version: {result.detail}")


def test_a_the_study_write_site_applies_the_same_rule(migrated_db):
    """The second write site must carry the rule, or the check is half a check.

    Fails while `admit_study_operation` writes `str(p.get("execution_version"))`
    with no check, so a caller reaching the study path stores what the prepare
    path now refuses.
    """
    dsn = migrated_db
    authority.authorize_study(dsn, "n49st-root", authorized=1000,
                              allocation_id="n49st-root",
                              ceilings={"model_calls": 10})
    granted = authority.admit_study_call(
        dsn, "n49st-root", kind="development", operation_id="n49st-ok",
        effect=broker.MODEL_INFERENCE,
        payload={"model": "test", "messages": [{"role": "user", "content": "x"}],
                 "max_output_tokens": 16},
        execution_version="exec-v1")
    assert hasattr(granted, "allowance"), (
        f"the study path refused a valid version: {granted}")
    refused = authority.admit_study_call(
        dsn, "n49st-root", kind="development", operation_id="n49st-bad",
        effect=broker.MODEL_INFERENCE,
        payload={"model": "test", "messages": [{"role": "user", "content": "x"}],
                 "max_output_tokens": 16},
        execution_version="../escape")
    assert refused.reason is not None, (
        "the study write site still accepts a traversing execution_version")
    row = broker.read_operation(dsn, "n49st-bad") or {}
    assert row.get("execution_version") != "../escape", (
        "and the unsafe value reached the operations column")


# ---------------------------------------------------------------------------
# N-32. A declared-only ceiling is recorded as authoritative and never checked.
#
# The store's enforcement loop `continue`s past any name with no counter, so a
# ceiling in DECLARED_CEILINGS is accepted by `is_ceiling_name`, written to
# `study_authority.ceilings`, and never evaluated again. A live study declares
# two of them: scripts/inv01_study.py:1224 passes `max_boundaries: 36` and
# `max_witness_queries: 960` to `authorize_study`.
#
# The repair is not to refuse the declaration. The store's own comment records
# that refusing it "made the study unstartable with a valid grant, which is the
# worse failure", and the live caller proves it. The repair is to make the gap
# visible at the store's own boundary, so a declared ceiling cannot read as an
# enforced one. Refusing the declaration stays the caller-side decision, and
# `authority.authorize_study` is not this lane's file, so the store exposes
# the question instead of silently answering it "yes".
# ---------------------------------------------------------------------------

DECLARED_ONLY_CEILINGS = ["boundaries", "witness_queries", "dev_episodes",
                          "lineages", "deadline_s", "trajectories",
                          "diagnostic_queries"]


@pytest.mark.parametrize("name", DECLARED_ONLY_CEILINGS)
def test_b_a_declared_only_ceiling_is_accepted_and_never_counted(name, migrated_db):
    """The finding itself, as an executable property. Passes before and after.

    It is here because the repair does not change what the store counts, only
    what it claims, and a reader needs the underlying fact stated in a place
    that runs.
    """
    assert store.is_ceiling_name(name) is True, name
    assert store._ceiling_counter(name) is None, (
        f"{name} now has a counter, so this test's premise has moved")
    assert store.is_ceiling_enforced(name) is False, (
        f"{name} has no counter, so the store cannot enforce it, and it must "
        f"not report that it can")
    assert store.is_ceiling_enforced(f"max_{name}") is False, name


@pytest.mark.parametrize("name", ["model_calls", "max_model_calls",
                                  "construction_calls", "sandbox_calls",
                                  "execution_units", "max_execution_units"])
def test_b_a_counted_ceiling_reports_as_enforced(name):
    """The other half of the claim, so the predicate is not vacuously false.

    Fails if `is_ceiling_enforced` refuses everything, which would be a
    predicate no reader could act on.
    """
    assert store.is_ceiling_enforced(name) is True, (
        f"{name} has a counter in CEILING_COUNTERS, so the store does count it")


def test_b_is_ceiling_enforced_agrees_with_the_enforcement_loop():
    """`is_ceiling_enforced` must be derived from the loop, not assert its own truth.

    Fails if the predicate and the code that skips an unenforced ceiling ever
    disagree, which is the whole defect restated as a predicate. A stub that
    always returns True satisfies `require_enforceable_ceilings`, because both
    ask the same function; only reading the loop's own rule catches that.
    """
    loop_body = _code_lines("_check_study_ceilings")
    assert "counter is None" in loop_body, (
        "the enforcement loop no longer skips on a missing counter, so "
        "is_ceiling_enforced has nothing to describe; rederive it")
    for name in DECLARED_ONLY_CEILINGS:
        assert store._ceiling_counter(name) is None, name
        assert store.is_ceiling_enforced(name) is False, name
    for name in set(store.CEILING_COUNTERS):
        assert store._ceiling_counter(name) is not None, name
        assert store.is_ceiling_enforced(name) is True, name


def test_b_the_two_ceiling_loops_skip_on_the_same_rule():
    """Both loops must decide enforcement by the same test.

    The study path raises on a missing counter (`if limit is None or counter is
    None`) and the live path skips on one (`if counter is None`). That is a
    second, quieter disagreement of the same shape N-31 named, and it is why a
    declared-only ceiling stored by one path behaves differently on the other.
    """
    live = _code_lines("_check_study_ceilings")
    study = _code_lines("admit_study_operation")
    assert "counter is None" in live, "the live loop no longer skips on one"
    assert "counter is None" in study, "the study loop no longer refuses on one"
    for name in DECLARED_ONLY_CEILINGS:
        assert store.is_ceiling_name(name) is True, (
            f"{name} is declared-only, so both loops must have a branch for it")
    """The repair. The gap must be a question the store answers.

    Fails while the set is implicit. A study declares `max_boundaries`, the
    store accepts it, and nothing anywhere says the store will never check it.
    """
    assert set(store.unenforced_ceilings()) == set(DECLARED_ONLY_CEILINGS), (
        "the reported unenforced set drifted from the constant it names")
    assert store.DECLARED_CEILINGS == frozenset(DECLARED_ONLY_CEILINGS)


def test_b_a_caller_claiming_to_enforce_a_declared_only_ceiling_is_refused(
        migrated_db):
    """A caller must not be able to record a name the store will not check.

    Fails while nothing rejects the claim, so a future caller writing "these
    are the ceilings I enforce" gets `max_boundaries` accepted and a reader
    believes a bound that does not exist.
    """
    store.require_enforceable_ceilings({"max_model_calls": 360,
                                        "max_execution_units": 5328})
    with pytest.raises(Exception) as raised:
        store.require_enforceable_ceilings({"max_boundaries": 36,
                                            "max_model_calls": 360})
    assert "boundaries" in str(raised.value), (
        f"the refusal did not name the unenforceable ceiling: {raised.value}")


# ---------------------------------------------------------------------------
# N-31. The LIKE fallback is the second source of truth, and it is now live.
#
# `admit_study_operation` (store.py) holds it: a counter the five-entry
# `counts` dict does not carry falls back to
# `SELECT COUNT(*) ... WHERE allocation_id LIKE '<parent>/<counter>/%'`. The
# other counter, `_count_study_operations`, is a recursive CTE over the whole
# subtree. The two disagree.
#
# The finding's own caveat licensed the repair on a reachability fact: that
# `authority.admit_study_call` had no caller in src/, experiments/ or scripts/,
# so the wrong counter was in a dead path. That was true when this test was
# written (15166f6, 2026-09-27) and stopped being true the next day, when
# experiments/ad01/e3_ladder.py and experiments/ad01/s09_m3_pilot.py began
# admitting the E3 ladder's and the M3 pilot's decisions through it.
#
# So the reconciliation the caveat asked for is now owed, and the deletion is no
# longer available. This test no longer pins "no caller" - it pins the caller
# set, so that a NEW production caller still goes red here. Whether the
# fallback is deleted is a separate decision that belongs with the two callers,
# not with a reachability pin.
#
# Resolved 2026-09-29 (lane I). The premise this block rests on was already
# stale when it was written: the fallback was deleted at 15166f6, three days
# before the callers landed, not after. `test_c_the_like_fallback_is_gone_from_
# the_study_admission_path` was passing against code that no longer had a
# fallback to disagree with, and it stayed passing through the two commits
# that made the path live. The reconciliation is therefore already in the
# tree and no repair was owed; what was missing was a pin on the property the
# shared counter is supposed to have, which is what the four tests at the end
# of this block add. The measured disagreement, in both directions, is in that
# commit message.
# ---------------------------------------------------------------------------

PRODUCTION_ROOTS = ["src", "experiments", "scripts"]

# Every production caller of the study-call path, as of 2026-09-28. Both admit
# real study decisions, so both are the reconciliation the caveat named.
STUDY_PATH_CALLERS = {
    "experiments": {
        "experiments/ad01/e3_ladder.py",
        "experiments/ad01/s09_m3_pilot.py",
    },
    "src": set(),
    "scripts": set(),
}


@pytest.mark.parametrize("root_name", PRODUCTION_ROOTS)
def test_c_the_study_admission_path_callers_are_known(root_name):
    """Pin which production code reaches the study-call path.

    Every caller is a place where removing the LIKE fallback would be a
    reconciliation rather than a deletion. The set is pinned, not the absence
    of a set, because the absence is no longer the fact: e3_ladder and s09_m3_pilot
    reached the path after this pin was written, and a third caller must not
    appear without this going red.
    """
    offenders = []
    for path in sorted((ROOT / root_name).rglob("*.py")):
        if path.name == "authority.py":
            continue
        if "admit_study_call" not in path.read_text(encoding="utf-8") \
                and "admit_study_operation" not in path.read_text(encoding="utf-8"):
            continue
        # A name in a comment or a docstring is a note about the path, not a
        # call into it. store.py:1174 names `admit_study_call` in the docstring
        # of the check that replaced it, and that is not a caller.
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            offenders.append(path.relative_to(ROOT).as_posix())
            continue
        called = {node.attr for node in ast.walk(tree)
                  if isinstance(node, ast.Attribute)}
        if "admit_study_call" in called or "admit_study_operation" in called:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert set(offenders) == STUDY_PATH_CALLERS[root_name], (
        f"the set of production callers of the study-call path under {root_name}/ "
        f"changed. The LIKE fallback is a live second source of truth for each "
        f"of them, so a new caller means a new reconciliation site: {offenders}")


def _function_source(name: str) -> str:
    """The source of one top-level `def`, by reading the file as text.

    Parsing would be heavier than the answer is worth, and the file is the one
    under repair, so a rename must break this loudly rather than silently skip.
    """
    source = (ROOT / "src" / "settlement" / "store.py").read_text(encoding="utf-8")
    lines = source.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.startswith(f"def {name}(")), None)
    assert start is not None, f"{name} is not a top-level def in store.py"
    out = [lines[start]]
    for line in lines[start + 1:]:
        # A signature can wrap, and the closing ")" of a wrapped one starts at
        # column 0. Two blank lines then a `def` is the real end of a
        # top-level function; nothing else at column 0 ends one.
        if line.startswith(("def ", "class ", "@")):
            break
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def _code_lines(name: str) -> str:
    """One top-level function's source with its comments and docstring removed.

    A test that greps a function's text matches the comment explaining what the
    function used to do, which is exactly the text the repair adds. The check
    has to be about code.
    """
    import io
    import tokenize

    source = _function_source(name)
    out = []
    previous_type = tokenize.INDENT
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            continue
        if token.type == tokenize.STRING and previous_type in (
                tokenize.INDENT, tokenize.NEWLINE, tokenize.NL,
                tokenize.DEDENT):
            previous_type = token.type
            continue
        if token.type not in (tokenize.NL, tokenize.NEWLINE,
                              tokenize.INDENT, tokenize.DEDENT):
            out.append(token.string)
        previous_type = token.type
    return " ".join(out)


def test_c_the_like_fallback_is_gone_from_the_study_admission_path():
    """The repair. One counter, not two.

    Fails while `admit_study_operation` can still fall back to a LIKE count.
    The study path and the live path must then read the same walker, or the
    disagreement the finding names is still in the code.
    """
    body = _code_lines("admit_study_operation")
    assert "LIKE" not in body, (
        "admit_study_operation still holds a LIKE counter fallback, a second "
        "source of truth disagreeing with the live path's walker")
    assert "_study_operation_counts" in body, (
        "admit_study_operation must read the same walker the live path reads")


def test_c_both_ceiling_paths_now_read_one_walker():
    """The two counters must be the same function, not merely the same answer.

    Fails if one path is fixed to agree with the other by coincidence, which a
    caller cannot tell from the answer and which reopens on the next counter
    someone adds.
    """
    live = _function_source("_check_study_ceilings")
    study = _function_source("admit_study_operation")
    assert "_count_study_operations" in live, (
        "the live path no longer reads the shared counter")
    assert "_study_operation_counts" in study, (
        "the study path no longer reads the shared walker")
    walker = _function_source("_count_study_operations")
    assert "_study_operation_counts" in walker, (
        "the live path's counter no longer delegates to the shared walker")


def test_c_the_counter_walker_covers_every_enforceable_ceiling():
    """The shared counter must carry a key for every enforceable ceiling.

    This is the trap the LIKE fallback used to hide. `CEILING_COUNTERS` has
    nine distinct counters. The walker used to build a hand-written five-key
    dict, so a ceiling naming `calibration`, `development`, `repair` or `use`
    fell through to a LIKE count that read 0 and never fired. The fallback is
    gone, so a missing key would read 0 there instead, which is the same
    defect by a different route. The shape is now derived from the table; this
    is what stops it drifting back.
    """
    counts = store._empty_study_counts()
    enforceable = set(store.CEILING_COUNTERS.values())
    missing = enforceable - set(counts)
    assert not missing, (
        f"the walker's counter shape is missing {sorted(missing)}; a ceiling "
        f"naming one reads 0 and never fires")


def test_c_a_study_kind_ceiling_is_actually_counted(migrated_db):
    """The four kind counters must move, not sit at zero.

    Fails if `calibration`, `development`, `repair` or `use` are accepted by
    `is_ceiling_name` and reported as enforced while the walker never
    increments them. That is the defect the LIKE fallback papered over with a
    different query, and it would survive a naive "delete the fallback" fix.
    """
    for kind in ("calibration", "development", "repair", "use"):
        assert store.is_ceiling_enforced(kind) is True, kind
    dsn = migrated_db
    authority.authorize_study(dsn, "n31k-root", authorized=1000,
                              allocation_id="n31k-root",
                              ceilings={"development": 5, "model_calls": 5})
    first = authority.admit_study_call(
        dsn, "n31k-root", kind="development", operation_id="n31k-op-1",
        effect=broker.MODEL_INFERENCE,
        payload={"model": "test", "messages": [{"role": "user", "content": "x"}],
                 "max_output_tokens": 16})
    assert hasattr(first, "allowance"), (
        f"the study path refused a valid operation: {first}")
    counts = _walk_counts(dsn, "n31k-root")
    assert counts["development"] == 1, (
        f"a development-kind study operation was admitted and the counter "
        f"reads {counts['development']}, so the ceiling would never fire")


def _live_model_send(dsn: str, study_root: str, operation_id: str,
                     kind: str | None = None):
    """One operation on the path a real dispatch takes, not the study path.

    `broker.ensure_operation` never stamps `kind`, which is why this helper
    takes it as an argument: the live path's operations reach the study
    subtree either way, and the reconciliation is about whether the study
    path counts them, not about how they were admitted.
    """
    operation = {"effect": broker.MODEL_INFERENCE, "study_root": study_root,
                 "payload": {"model": "m"}}
    if kind is not None:
        operation["kind"] = kind
    return store.prepare_operation(dsn, Command(
        request_id=f"live-{operation_id}",
        payload={"operation_id": operation_id, "attempt_id": None,
                 "allocation_id": study_root, "reservation_id": None,
                 "exposure": 0, "operation": operation}))


def test_c_the_study_path_is_charged_for_operations_it_did_not_admit(migrated_db):
    """The reconciliation, as a property rather than as a shared function name.

    `test_c_both_ceiling_paths_now_read_one_walker` proves the two functions
    agree, and `test_c_a_study_kind_ceiling_is_actually_counted` proves the
    kind counter moves. Neither proves the property the shared walker is
    supposed to have: that an operation admitted on one path is charged
    against a ceiling enforced on the other. Every other test here exercises
    one path at a time, so each path could count its own subtree and all of
    them would still pass, which is the pre-repair shape restated.

    Break by scoping either counter to its own admission shape - the study
    path counting only `<root>/<kind>/%`, or the live path counting only
    rows it prepared - and the third operation is admitted past a ceiling of
    two.
    """
    authority.authorize_study(migrated_db, "n31x-root", authorized=1_000_000,
                              allocation_id="n31x-root",
                              ceilings={"model_calls": 2})
    for index in (1, 2):
        sent = _live_model_send(migrated_db, "n31x-root", f"n31x-live-{index}")
        assert sent.code is ResultCode.APPLIED, (
            f"the study path must start from a real subtree: {sent.detail}")

    granted = authority.admit_study_call(
        migrated_db, "n31x-root", kind="development",
        operation_id="n31x-dev-1", effect=broker.MODEL_INFERENCE,
        payload={"model": "test", "messages": [{"role": "user", "content": "x"}],
                 "max_output_tokens": 16})

    assert not hasattr(granted, "allowance"), (
        "two model operations are already in the study subtree against a "
        "ceiling of 2, so a third was admitted past the ceiling")


def test_c_the_live_path_is_charged_for_operations_it_did_not_admit(migrated_db):
    """The other direction, because the two paths fail oppositely.

    The first test fails if the study path under-counts, which admits past a
    ceiling. This one fails if the live path under-counts the study path's
    operations, which is the same overrun reached by the other door. A
    reconciliation verified in one direction only is half a reconciliation.
    """
    authority.authorize_study(migrated_db, "n31y-root", authorized=1_000_000,
                              allocation_id="n31y-root",
                              ceilings={"model_calls": 2})
    for index in (1, 2):
        granted = authority.admit_study_call(
            migrated_db, "n31y-root", kind="development",
            operation_id=f"n31y-dev-{index}", effect=broker.MODEL_INFERENCE,
            payload={"model": "test",
                     "messages": [{"role": "user", "content": "x"}],
                     "max_output_tokens": 16})
        assert hasattr(granted, "allowance"), (
            f"the live path must start from a real subtree: {granted}")

    over = _live_model_send(migrated_db, "n31y-root", "n31y-live-3")

    assert over.code is not ResultCode.APPLIED, (
        "two model operations the live path never admitted are already in the "
        f"study subtree against a ceiling of 2, and this third was admitted: "
        f"{over.code}")


def test_c_the_two_paths_agree_on_a_mixed_subtree(migrated_db):
    """The numeric disagreement itself, as the case that shows the gap.

    N-31 named two counters that disagreed; this builds the subtree they
    disagreed about and pins the shared answer. Three development operations
    through the study path plus two model operations through the live path is
    the shape where the old LIKE fallback read 0 for `model_calls` (it counts
    only `<root>/<counter>/%`, and a live operation sits on the root) while
    the walker read 2. Under-counting here is what admits past a ceiling, so
    the expected number is stated literally rather than recomputed from the
    code under test.
    """
    authority.authorize_study(migrated_db, "n31z-root", authorized=1_000_000,
                              allocation_id="n31z-root",
                              ceilings={"development": 10, "model_calls": 10})
    for index in (1, 2, 3):
        granted = authority.admit_study_call(
            migrated_db, "n31z-root", kind="development",
            operation_id=f"n31z-dev-{index}", effect=broker.MODEL_INFERENCE,
            payload={"model": "test",
                     "messages": [{"role": "user", "content": "x"}],
                     "max_output_tokens": 16})
        assert hasattr(granted, "allowance"), granted
    for index in (1, 2):
        sent = _live_model_send(migrated_db, "n31z-root", f"n31z-live-{index}")
        assert sent.code is ResultCode.APPLIED, sent.detail

    counts = _walk_counts(migrated_db, "n31z-root")

    assert counts["development"] == 3, (
        f"three development operations were admitted and the counter reads "
        f"{counts['development']}")
    assert counts["model_calls"] == 5, (
        f"three study-path and two live-path model operations are in the "
        f"subtree and the counter reads {counts['model_calls']}, so the "
        f"counter is not seeing both admission shapes")
    assert counts["operations"] == 5, (
        f"the subtree holds five operations and the counter reads "
        f"{counts['operations']}")


def test_c_the_live_path_enforces_a_kind_ceiling_it_never_admitted(migrated_db):
    """The pre-repair live path read every kind counter as zero.

    `_check_study_ceilings` asked `used.get(counter, 0)` for a dict that
    carried only five keys, so `max_development` was accepted at
    authorization, reported as enforced by `is_ceiling_enforced`, and then
    never checked by the path every real dispatch takes. That is the
    over-count/under-count asymmetry with money on it: the ceiling reads as
    a bound and bounds nothing.

    `test_c_a_study_kind_ceiling_is_actually_counted` covers the study path.
    Nothing covered this one, so the walker could have kept incrementing
    `development` only for study-shaped rows and every other test in this
    file would still pass. Break by dropping the `kind` increment from the
    walker and this goes red while the study-path test stays green.
    """
    authority.authorize_study(migrated_db, "n31w-root", authorized=1_000_000,
                              allocation_id="n31w-root",
                              ceilings={"development": 2})
    for index in (1, 2):
        sent = _live_model_send(migrated_db, "n31w-root",
                                f"n31w-live-{index}", kind="development")
        assert sent.code is ResultCode.APPLIED, (
            f"the first two must be admitted: {sent.detail}")

    over = _live_model_send(migrated_db, "n31w-root", "n31w-live-3",
                            kind="development")

    assert over.code is not ResultCode.APPLIED, (
        "two development operations are in the study subtree against a "
        f"ceiling of 2 and the live path admitted a third: {over.code} "
        f"{over.detail or ''}")


def _walk_counts(dsn: str, study_root: str) -> dict:
    """Read the shared counter through the store's own walker.

    The walker indexes rows by name, so this needs the store's `dict_row`
    cursor factory rather than the default tuple one.
    """
    from psycopg.rows import dict_row

    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT allocation_id FROM study_authority"
                        " WHERE study_root = %s", (study_root,))
            allocation_id = cur.fetchone()["allocation_id"]
            return dict(store._study_operation_counts(cur, allocation_id))


def test_c_admit_study_operation_still_exists_because_tests_cannot_be_edited():
    """Why the dead function was reconciled rather than deleted.

    Fails if the entry point is removed while `tests/
    test_store_authority_invariants.py` still calls it. That file is owned by
    another lane, and it fails 12 tests the moment the function goes. The
    finding's own fix - remove the dead second source of truth - is therefore
    executed as far as this lane's file ownership allows: the disagreeing
    counter inside it is removed, and the disagreeing query with it.
    """
    assert hasattr(store, "admit_study_operation"), (
        "removed, but tests/test_store_authority_invariants.py:487 calls it "
        "directly and 4 more tests monkeypatch it; those 12 failures have to "
        "be fixed by the owning lane first")
    invariants = (ROOT / "tests" / "_heavy_archived" / "test_store_authority_invariants.py") \
        .read_text(encoding="utf-8")
    assert "store.admit_study_operation(" in invariants, (
        "the direct call went away, so the function can be deleted after all; "
        "revisit this test")


# ---------------------------------------------------------------------------
# N-55. A launcher id is a naming convention, not a capability.
#
# No repair is made. These tests pin the current behaviour and the evidence
# against the repair, so the judgement is on the record as code rather than in
# a report that can be re-read past.
# ---------------------------------------------------------------------------

def test_e_a_provenance_naming_the_admitted_launcher_is_accepted():
    """The current behaviour, stated as the thing the finding disputes.

    Fails if the acceptance test changes in either direction. If it ever stops
    accepting this, the honest reset path is dead; if it ever starts accepting
    a name that is not the launcher's, N-48 is broken.
    """
    assert store._provenance_attested(
        {"provenance": "local-1:prove_never_sent"}, "local-1") is True
    assert store._provenance_attested({"provenance": "local-1"}, "local-1") is True
    assert store._provenance_attested(
        {"provenance": "strand-fake-2:prove_never_sent"}, "strand-fake-2") is True


def test_e_the_launcher_id_a_proof_must_name_is_a_public_constant():
    """The evidence that no bound secret is available in this design.

    Fails if a launcher ever carries a per-instance or per-secret id, which
    would reopen option (b) in the finding. As written, the "secret" is a class
    attribute in the same package, so a caller that has read the source knows
    it. A test that read the value off the class rather than off a literal
    keeps this honest if the constant ever changes.
    """
    assert LocalLauncher.launcher_id == "local-1"
    assert store._provenance_attested(
        {"provenance": f"{LocalLauncher.launcher_id}:prove_never_sent"},
        LocalLauncher.launcher_id) is True, (
        "if this ever fails, the launcher carries something a caller could not "
        "know, and the N-55 question needs reopening on new evidence")


def test_e_the_store_has_no_credential_of_its_own_to_verify_a_proof():
    """The evidence that the store cannot verify anything a caller cannot send.

    Fails if the store ever grows a key. With no key, the store has nothing to
    check a proof against except a name it already stored from the same
    untrusted call.
    """
    import settlement.store as store_module

    assert not hasattr(store_module, "SECRET"), (
        "the store grew a credential; the N-55 judgement would need redeciding")
    assert not hasattr(store_module, "PROOF_KEY"), store_module
    source = (ROOT / "src" / "settlement" / "store.py").read_text(encoding="utf-8")
    assert "hmac" not in source, (
        "the store started verifying proofs with a keyed digest, so a caller "
        "can no longer forge one by knowing the launcher name")


# ---------------------------------------------------------------------------
# The guards this lane must not regress.
# ---------------------------------------------------------------------------

def test_e_every_actor_that_can_reach_a_proof_entry_point_can_skip_it(migrated_db):
    """The evidence that makes the N-55 repair pointless, as a live check.

    Both proof entry points, `store.reset_dispatch` and
    `store.reconcile_operation`, have exactly one production caller each and
    both are in `broker.py`, which holds a DSN. A DSN holder can write the
    state the proof is supposed to gate with one statement, and this test does
    exactly that. It asserts the bypass SUCCEEDS.

    That is the point. The recorded judgement is that a launcher id is a naming
    convention rather than a capability, which is true, and this shows the
    repair that judgement would buy is worth nothing: the property is not
    reachable through the store's own API from an actor the secret would
    constrain. Option (a), routing every reset through the broker, is already
    what the call graph says, because both callers ARE the broker.

    If a future design gives the store a credential no DSN holder can reach,
    this test is where that fact belongs, and it should be inverted.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n55")
    op = "n55-op"
    _sandbox(dsn, op, alloc, attempt="n55-att")
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": op, "launcher_id": "local-1",
        "ownership_generation": gen}, "n55a"))
    assert (broker.read_operation(dsn, op) or {})["dispatch_state"] == "dispatching"

    from settlement import db

    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE operations SET dispatch_state = 'prepared'"
                        " WHERE id = %s", (op,))
        conn.commit()

    assert (broker.read_operation(dsn, op) or {})["dispatch_state"] == "prepared", (
        "a DSN holder can no longer move an operation out of dispatching "
        "without a proof. If this fails, the store gained a capability the "
        "DSN role does not have, and the N-55 judgement should be reopened.")


def test_e_the_two_proof_entry_points_are_reached_only_by_the_broker():
    """The call-graph fact behind the test above, pinned so it cannot drift.

    Fails if a new production caller of either entry point appears from
    anywhere other than `broker.py`, which is the only actor that would need
    the property to hold.
    """
    callers: dict[str, list[str]] = {"reset_dispatch": [], "reconcile_operation": []}
    for path in sorted((ROOT / "src").rglob("*.py")):
        if path.name == "store.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) \
                    and node.attr in callers:
                callers[node.attr].append(path.name)
    assert callers["reset_dispatch"] == ["broker.py"], callers["reset_dispatch"]
    assert callers["reconcile_operation"] == ["broker.py"], \
        callers["reconcile_operation"]


def test_d_a_real_local_launcher_failure_is_still_admitted(migrated_db, tmp_path):
    """N-43. A genuine LocalLauncher failure must record a failure receipt.

    Fails if the failure-evidence rule narrows back to the gateway's seven
    keys, which would make a real local failure unrepresentable and leave the
    operation at `dispatching` with no receipt at all.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n43")
    op = "n43-op"
    assert broker.ensure_operation(
        dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/false"],
                 "timeout_ms": 30_000, "max_output_bytes": 4096},
        allocation_id=alloc, attempt_id="n43-att").code == ResultCode.APPLIED
    launcher = LocalLauncher(tmp_path / "runs")
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                              ownership_generation=gen)
    receipts = store.operation_receipts(dsn, op)
    assert len(receipts) == 1, receipts
    assert receipts[0]["outcome"] == "failure", (
        "a LocalLauncher run of /bin/false must record a failure receipt")
    content = receipts[0]["content"]
    assert content.get("data", {}).get("returncode") == 1, (
        f"the launcher vocabulary that made this representable is gone: {content}")


def test_d_a_failure_receipt_with_no_evidence_at_all_is_refused(migrated_db, tmp_path):
    """N-43, the other half. A claim is still not evidence.

    Fails if the three launcher-vocabulary keys are accepted when empty, or if
    the evidence rule is dropped outright.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n43b")
    op = "n43b-op"
    assert broker.ensure_operation(
        dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 30_000, "max_output_bytes": 4096},
        allocation_id=alloc, attempt_id="n43b-att").code == ResultCode.APPLIED
    launcher = LocalLauncher(tmp_path / "runs")
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                              ownership_generation=gen)
    before = len(store.operation_receipts(dsn, op))
    store.admit_receipt(dsn, _cmd({
        "operation_id": op, "receipt_identity": "n43b-bare",
        "outcome": "failure", "provenance": "local-1",
        "content": {"operation_id": op}}, "n43b"))
    outcomes = [r["outcome"] for r in store.operation_receipts(dsn, op)]
    assert outcomes.count("failure") <= 1, outcomes
    assert len(store.operation_receipts(dsn, op)) == before, (
        f"an evidence-free receipt changed the receipt set: {outcomes}")


def test_d_a_caller_asserted_proof_with_a_forged_provenance_is_refused(
        migrated_db, tmp_path):
    """N-48. Shape alone must never buy a second execution.

    Fails if `_provenance_attested` accepts a provenance naming no launcher,
    which returns the operation to `prepared`, the state a second run starts
    from.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n48")
    op = "n48-op"
    _sandbox(dsn, op, alloc, attempt="n48-att")
    launcher = LocalLauncher(tmp_path / "runs")
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": op, "launcher_id": launcher.launcher_id,
        "ownership_generation": gen}, "n48a"))
    generation = int(advanced.data["dispatch_generation"])
    for provenance in ["forged", "", "   ", "other-launcher:prove_never_sent",
                       f"{launcher.launcher_id}x", "not-local-1", "local-10"]:
        result = store.reset_dispatch(dsn, _cmd({
            "operation_id": op, "expected_generation": generation,
            "never_sent_proof": {"claim": "never-sent", "subject": op,
                                 "provenance": provenance,
                                 "dispatch_generation": generation}}, "n48r"))
        assert result.code is not ResultCode.APPLIED, (
            f"a proof with provenance {provenance!r} was accepted; it returns "
            f"the operation to prepared, where a second run starts")
        assert (broker.read_operation(dsn, op) or {})["dispatch_state"] \
            == "dispatching", (
            f"provenance {provenance!r} moved the operation out of dispatching")


def test_d_an_operation_admitted_to_no_launcher_admits_no_proof():
    """N-48, the empty-launcher half. Nothing can speak for it, so nothing may.

    Fails if an empty `attested_by` is treated like `None`: an operation that
    exists but was admitted to no launcher has no launcher that could have
    been given the work.
    """
    assert store._provenance_attested(
        {"provenance": "local-1:prove_never_sent"}, "") is False
    assert store._provenance_attested({"provenance": ""}, None) is True, (
        "no operation at all keeps the shape check alone")


def test_d_a_second_decided_receipt_on_one_operation_is_refused(migrated_db, tmp_path):
    """The concurrency soundness claim N-43 rests on.

    Fails if a second `success` or `failure` lands on an operation that already
    carries one, which is the shape the trials found never happens.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "ndec")
    op = "ndec-op"
    assert broker.ensure_operation(
        dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 30_000, "max_output_bytes": 4096},
        allocation_id=alloc, attempt_id="ndec-att").code == ResultCode.APPLIED
    launcher = LocalLauncher(tmp_path / "runs")
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                              ownership_generation=gen)
    decided = [r for r in store.operation_receipts(dsn, op)
               if r["outcome"] in ("success", "failure")]
    assert len(decided) == 1, decided
    for outcome, identity in [("failure", "ndec-f"), ("success", "ndec-s")]:
        store.admit_receipt(dsn, _cmd({
            "operation_id": op, "receipt_identity": identity, "outcome": outcome,
            "provenance": "local-1",
            "content": {"operation_id": op, "text": "second"}}, "ndec"))
    after = [r for r in store.operation_receipts(dsn, op)
             if r["outcome"] in ("success", "failure")]
    assert len(after) == 1, (
        f"a second decided receipt was admitted; decided receipts are now "
        f"{[r['outcome'] for r in after]}")
