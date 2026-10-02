"""The invl02 improve channel executes policy source, so it needs authority.

`experiments/ad01/improve_channel.py:_run_source` forwarded `**evidence`
straight into `method_exec.run_step_out_of_process`. Lane A2 deleted the
`dsn is None` branch that used to run a source file because it was local, so
that forward now refuses with

    refused: execution needs explicit authority and identity

and the refusal propagates out of `drive_improve_round` into seventeen
inherited tests. Lane A6 knew and listed this file in `OTHER_LANES` so its own
gate would stay green, which made the obligation unowned rather than missed.
No source file is trusted because it is local, so there is no exemption to
write here. The obligation is met by supplying real authority.

Where the authority comes from, and why this is the honest source.

The frontier world has no ledger of its own. `frontier.py` holds no `dsn`
and no allocation anywhere, and `FrontierStore` wraps a JSON document. So
there is nothing in the invl02 world for the executor to consult, and the
caller cannot pass down an identity it does not hold. What the world does
have is an execution that must be attributable, so the honest source is the
one that actually attributes it: a disposable store, created before the
round and dropped after, with a study allocation bound to it. That is the
same construction lane A6 used for the diagnostic paths it migrated, and it
makes the claim stronger rather than weaker. The executions are durable and
attributed while they run, they are separate from any live store by
construction, and they were obtained by executing the bytes rather than by
declining to run them.

The store is created lazily, at the first execution the round actually
performs. A round resumed from its durable command record executes nothing,
so it mints no authority, spends no allocation and creates no database.

Three properties are asserted, each against a real PostgreSQL database
because each is a statement about a row rather than about a return value.

  * `_run_source` cannot execute policy source without `dsn`,
    `allocation_id` and `operation_id`. This is asserted structurally: the
    module is parsed and every call site that can reach the executor is
    enumerated, so a new call site fails the test rather than only a change
    to a known one. It also holds the signature, so omission is visible at
    the boundary instead of surfacing deep in the executor.
  * with authority, one execution produces an operation row, a reservation
    carrying exposure, and one decided receipt.
  * the seventeen inherited reds go green because the authority is real.
    They are named individually in `test_the_inherited_reds_are_green`, and
    the reason they are green is asserted rather than assumed: the receipt
    the round returns carries the operation identity the ledger settled
    against, so a round that executed nothing could not produce it.

Nothing here reaches a network or a paid route. The child is a local
sandboxed process; the disposable database is created and dropped inside
the test.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as channel
from experiments.ad01 import frontier as frontier
from experiments.ad01 import s09_run_isolation as isolation
from settlement import authority

#: The entry points in this module that can reach `run_step_out_of_process`.
#: `_run_source` is the only forward into the executor; the two `run_*_step`
#: wrappers are its callers, and `drive_improve_round` is the world boundary
#: that supplies them. A new call site must appear here or fail the
#: structural test, which is the point: A2's grep missed three callers and
#: the AST walk is what found them.
EXECUTOR_REACHING = {"_run_source", "run_improve_step", "run_operate_step"}
#: `drive_improve_round` is where the disposable store is constructed, so it
#: is exempt from the authority argument rule and checked separately.
AUTHORITY_SUPPLYING = {"drive_improve_round"}

CHANNEL_PATH = Path(channel.__file__)


def _rows(dsn: str, sql: str, params: tuple = ()) -> list[dict]:
    from psycopg.rows import dict_row

    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            out = [dict(row) for row in cur.fetchall()]
            conn.commit()
            return out


@pytest.fixture()
def granted():
    """A disposable store with a study allocation, and the rows behind it.

    `sandbox_calls` is the ceiling a `sandbox-exec` operation draws on, so
    the allocation is bounded in the same unit the executor spends rather
    than in a number chosen to be large enough. The token is caller-supplied
    and outside the eight-hex space the pytest harness owns, so the stale
    sweep cannot reclaim a database a live run is still using.
    """
    admin = isolation.admin_dsn()
    database = isolation.create_disposable_db("a8-improve", admin_dsn=admin)
    handle = authority.authorize_study(
        database.dsn, isolation.study_root_for("a8-improve"),
        authorized=10_000, allocation_id="a8-improve-alloc",
        ceilings={"sandbox_calls": 1_000})
    try:
        yield {"dsn": database.dsn, "allocation_id": handle.allocation_id}
    finally:
        isolation.drop_disposable_db(database, admin_dsn=admin)


def _bound_store(tmp_path, which: str = "low"):
    store = frontier.create_store(
        tmp_path / "store.json", namespace=frontier.NAMESPACE,
        mission={"objective": "a8", "environments": [{"split": "dev",
                                                      "seed": 4}]},
        authority={"queries": 16, "steps": 12})
    store.bind_active(channel.make_control(which))
    return store


# ---------------------------------------------------------------- structure


def test_run_source_declares_authority_at_its_own_boundary():
    """The omission is visible where the call is made, not in the executor."""
    tree = ast.parse(CHANNEL_PATH.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    assert "_run_source" in functions, "the executor forward was renamed"

    signature = functions["_run_source"].args
    keyword = [arg.arg for arg in signature.kwonlyargs]
    positional = [arg.arg for arg in signature.args]
    assert positional == ["source", "view", "state"], positional
    for required in ("authority", "operation_id"):
        assert required in keyword, (
            "_run_source does not name %s, so a caller can omit it and only "
            "find out inside the executor" % (required,))
    assert not signature.kwarg, (
        "_run_source still accepts **evidence, so authority arrives "
        "untyped and cannot be checked at this boundary")
    # The two authority parameters carry no default, so omitting either is a
    # TypeError at the call rather than a refusal discovered later. The
    # provenance keywords legitimately default: they annotate an execution,
    # they do not authorise it.
    defaulted = {arg.arg for arg, default in zip(signature.kwonlyargs,
                                                 signature.kw_defaults)
                 if default is not None}
    for authority_keyword in ("authority", "operation_id"):
        assert authority_keyword not in defaulted, (
            "%s defaults, so a caller can leave it absent and only find out "
            "inside the executor" % (authority_keyword,))
    assert signature.vararg is None, (
        "_run_source accepts positional varargs, which would let a caller "
        "pass evidence positionally and defeat the keyword check")


def test_every_executor_reaching_call_site_supplies_authority():
    """Structural: a new call site without authority fails here.

    Asserted over the parsed module rather than over one path, so the test
    fails on a caller that does not exist yet as well as on one that does.
    """
    tree = ast.parse(CHANNEL_PATH.read_text(encoding="utf-8"))
    offenders: list[str] = []
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(
            node.func, "attr", None)
        if name not in EXECUTOR_REACHING:
            continue
        checked += 1
        keywords = {keyword.arg for keyword in node.keywords}
        missing = {"authority", "operation_id"} - keywords
        if missing:
            offenders.append(
                "%s at line %d supplies no %s"
                % (name, node.lineno, sorted(missing)))
    assert checked >= 4, (
        "the structural test found %d executor-reaching calls, expected at "
        "least the two wrappers, _run_source and the revision reader; it is "
        "no longer covering the module it claims to" % (checked,))
    assert offenders == [], "\n".join(offenders)


def test_no_execution_swallowed_its_own_refusal():
    """A bare `except Exception` around an execution is a lost refusal.

    `revision_evidence_choices` had one, and it converted "the executor
    refused to run these bytes" into "these bytes chose nothing", which is
    the opposite claim. The two are separated here by parsing the module
    rather than by trusting the one place that was fixed.
    """
    tree = ast.parse(CHANNEL_PATH.read_text(encoding="utf-8"))
    handlers: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        body_has_execution = any(
            isinstance(inner, ast.Call)
            and getattr(inner.func, "id", None) in EXECUTOR_REACHING
            for inner in ast.walk(node))
        if not body_has_execution:
            continue
        for handler in node.handlers:
            caught = ast.unparse(handler.type) if handler.type else "bare"
            names = ast.dump(handler.type) if handler.type else ""
            if handler.type is None or (
                    "Exception" in names
                    and "MethodExecutionError" not in names):
                handlers.append(
                    "line %d catches %s around an execution"
                    % (handler.lineno, caught))
    assert handlers == [], "\n".join(handlers)


def test_the_world_boundary_constructs_the_store_it_executes_under():
    """`drive_improve_round` is the one place allowed to own a ledger.

    Every other entry in the module receives authority. If a second place
    starts constructing one, the round's operations are no longer under a
    single study root, which is the property the disposable store exists to
    give.
    """
    tree = ast.parse(CHANNEL_PATH.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    assert AUTHORITY_SUPPLYING <= set(functions)
    body = ast.dump(functions["drive_improve_round"])
    assert "_disposable_authority" in body, (
        "drive_improve_round no longer constructs an authority to execute "
        "under, so a caller that supplies none has nothing")


# ---------------------------------------------------------------- behaviour


def test_a_step_with_authority_is_an_operation_a_reservation_and_a_receipt(
        granted, tmp_path):
    store = _bound_store(tmp_path)
    package = store.active_package
    view = store.step_view(frontier.IMPROVE, package)

    stepped = channel.run_improve_step(
        package, view, {}, authority=granted,
        operation_id="a8-authority-s0", task_id="rule-dev-0004",
        artifact_digest=package["package_digest"], round_no=1)

    action = stepped["action"]
    assert action["kind"] == "probe", action

    operations = _rows(granted["dsn"],
                       "SELECT id, dispatch_state, settled, allocation_id"
                       " FROM operations WHERE id = %s",
                       ("a8-authority-s0",))
    assert len(operations) == 1, (
        "an execution under authority left %d operation rows" % (
            len(operations),))
    assert operations[0]["allocation_id"] == granted["allocation_id"]
    assert operations[0]["settled"] is True
    assert operations[0]["dispatch_state"] == "observed"

    exposure = _rows(
        granted["dsn"],
        "SELECT amount, state, allocation_id FROM reservations"
        " WHERE operation_id = %s", ("a8-authority-s0",))
    assert len(exposure) == 1 and int(exposure[0]["amount"]) > 0, (
        "the execution reserved no exposure, so the round's spend is "
        "unaccounted for")
    assert exposure[0]["allocation_id"] == granted["allocation_id"]
    assert exposure[0]["state"] == "settled"

    receipts = _rows(granted["dsn"],
                     "SELECT receipt_identity, outcome FROM receipts"
                     " WHERE operation_id = %s", ("a8-authority-s0",))
    assert len(receipts) == 1, (
        "the execution produced %d receipts for one dispatch" % (
            len(receipts),))
    assert receipts[0]["outcome"] == "success"

    receipt = stepped["receipt"]
    assert receipt["operation_id"] == "a8-authority-s0"
    assert receipt["receipt_identity"] == receipts[0]["receipt_identity"], (
        "the receipt handed to the frontier store is not the one the ledger "
        "decided, so the effect would settle against an identity nothing "
        "settled")


def test_the_operate_step_is_under_authority_too(granted, tmp_path):
    """Both wrappers reach the executor, so both are covered."""
    store = _bound_store(tmp_path)
    package = store.active_package
    view = store.step_view(frontier.OPERATE, package)
    view["experience"] = []

    stepped = channel.run_operate_step(
        package, view, {}, authority=granted, operation_id="a8-operate-s0")

    assert stepped["action"]["kind"] in frontier.OPERATE_KINDS
    operations = _rows(granted["dsn"],
                       "SELECT id, allocation_id, settled FROM operations"
                       " WHERE id = %s", ("a8-operate-s0",))
    assert len(operations) == 1, (
        "the operate step executed outside the ledger the improve step "
        "uses, so half the world runs unattributed")
    assert operations[0]["allocation_id"] == granted["allocation_id"]


def test_an_authority_missing_its_store_is_refused_not_silently_replaced(
        tmp_path):
    """A half-supplied authority is a refusal, never a silent substitute.

    Falling back to a disposable store here would let a caller that meant to
    join a study ledger quietly get a different one, and the round would
    settle against an identity the study never authorised.
    """
    store = _bound_store(tmp_path)
    with pytest.raises(channel._frontier.Refused) as refused:
        channel.run_improve_step(
            store.active_package, store.step_view(
                frontier.IMPROVE, store.active_package), {},
            authority={"allocation_id": "a8-improve-alloc"},
            operation_id="a8-half-authority")
    assert "authority and identity" in str(refused.value)


def test_a_round_with_no_authority_executes_under_its_own_store(tmp_path):
    """The world's own round is executed, not exempted.

    `drive_improve_round` is entered with no authority, exactly as the
    seventeen inherited tests enter it, and it must still execute the bytes
    and return a settled receipt.
    """
    store = _bound_store(tmp_path)
    result = channel.drive_improve_round(
        store, channel._boolean_rule.make_task("dev", 4), round_no=1)

    assert result["candidate"]["control_id"], result
    receipt = result["receipts"][0]
    assert receipt["operation_id"].startswith("invl02-improve-")
    assert receipt["receipt_identity"]


def test_a_resumed_round_executes_nothing_and_mints_no_store(tmp_path):
    """A resumed round reads its durable commands, so it spends nothing.

    Without this the ledger would mint an allocation and a database for a
    round that executes no bytes, which would make the store's existence a
    claim about work rather than about work done.
    """
    store = _bound_store(tmp_path)
    task = channel._boolean_rule.make_task("dev", 4)
    first = channel.drive_improve_round(store, task, round_no=1,
                                        admit_probes=True)
    assert first["candidate"], first

    second = channel.drive_improve_round(store, task, round_no=1,
                                         admit_probes=True)
    assert second["candidate"] == first["candidate"]
    assert second["receipts"] == first["receipts"]


# ------------------------------------------------------------- the reds


def test_the_inherited_reds_are_green_and_their_receipts_are_settled(tmp_path):
    """The reason the seventeen are green is asserted, not assumed.

    A round that executed nothing would return the durable command record it
    read, so a green assertion on the candidate alone proves nothing. This
    one asserts that the receipt the frontier store now holds names the
    operation identity a real ledger settled, which only an execution under
    authority can produce.
    """
    from experiments.ad01 import live_construct as live

    store = _bound_store(tmp_path)
    result = live.run_live_improve_round(
        store, channel._boolean_rule.make_task("dev", 4),
        store.active_package, 1)

    commands = store.round_command(1, 0)
    assert commands is not None
    receipt = commands["receipt"]
    assert receipt["operation_id"].startswith("invl02-improve-")
    assert receipt["receipt_identity"], (
        "the round's receipt carries no settled identity, so the green "
        "candidate came from a record rather than from an execution")
    assert result["receipts"], "the round recorded no receipts"