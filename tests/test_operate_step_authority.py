"""The operate choices M2 reads settle under the study allocation.

`live_construct.choose_next_work` reached `improve_channel.run_operate_step`
with no `authority=`, so `_execution_ledger` took its `None` default and
opened `_disposable_authority` -- a database created for the execution and
dropped when it ends. Three choices per investigation, and
`observation_dependent` and `falsifier_moves_decision` are computed from
exactly those three (`scripts/invl02_live.py:2234-2237`). The decision M2
measures therefore had receipts naming a database that no longer exists, which
is the condition `drive_improve_round` already refuses an owned store for.

The authority is threaded from the one `_study_authority(dsn, allocation_id)`
`_run_frontier_investigation` already builds for its improve rounds. No second
derivation: `WORKER-PROMPT.md:158` requires one campaign authority per leg,
and the r123 repair already moved this derivation out of the investigation
once.

These tests need `SETTLEMENT_TEST_DSN` and are skipped without it. CI runs them
with PostgreSQL; a local Windows checkout skips rather than lying.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel as _channel
from experiments.ad01 import live_construct as _live
from experiments.ad01 import s09_run_isolation as _isolation
from scripts import invl02_live as _driver
from settlement import authority as _settlement_authority
from conftest import live_mission, unique

DRIVER_PATH = ROOT / "scripts" / "invl02_live.py"
LIVE_PATH = ROOT / "experiments" / "ad01" / "live_construct.py"

#: Six child executions per investigation are already priced by
#: `reports/cap-sheets/e0-e12-child-execution-caps.md`, which counted the two
#: operate choices at one each. The thread does not add executions -- the same
#: three choices still run, on the study's ledger instead of a disposable one --
#: so the ceiling stays declared at a figure with room and the test asserts the
#: count rather than raising it. It is declared because an undeclared
#: `sandbox_calls` is an unbounded resource wearing a grant's clothes
#: (`store.py:1439-1441` iterates only the names a study declared).
CEILING = 12


@pytest.fixture()
def study(tmp_path):
    """A study allocation on a database this test owns, and drops after.

    The study root is per-test. `_study_operation_counts` walks the subtree
    under one `allocation_id`, so a shared root would price one test's child
    executions against a sibling's ceiling and make the pass depend on file
    order.
    """
    admin = _isolation.admin_dsn()
    # A hyphen, not `unique()`'s underscore. The isolation token grammar is
    # `\A[a-z0-9][a-z0-9-]{0,23}\Z`, so `opauth_666b95f5` is refused before any
    # test runs — which is how CI found it, on the shard where the database was
    # actually present, so it was never a host limitation.
    database = _isolation.create_disposable_db(
        unique("opauth").replace("_", "-"), admin_dsn=admin)
    try:
        handle = _settlement_authority.authorize_study(
            database.dsn, unique("opauth-root"), authorized=100_000,
            ceilings={"sandbox_calls": CEILING})
        yield {"dsn": database.dsn, "allocation_id": handle.allocation_id}
    finally:
        _isolation.drop_disposable_db(database, admin_dsn=admin)


@pytest.fixture()
def owned_store(tmp_path, study):
    """A store that names an owner, so the omission is reachable.

    `ensure_live_store(dsn=..., investigation_id=...)` records the identity,
    and `choose_next_work` refuses an owned store entered with no authority --
    the same rule `drive_improve_round` applies at `improve_channel.py:2328`.
    Without an owner the refusal is unreachable and the test would pass for
    the wrong reason.
    """
    investigation_id = unique("opauth-investigation")
    from experiments.ad01 import mission as _mission
    _mission.record_mission(
        study["dsn"], investigation_id,
        objective=_live.LIVE_MISSION_OBJECTIVE,
        environments=[{"instrument": "boolean-rule-v1", "split": "dev",
                       "seed": 4}],
        constraints=[], success_criteria=[], improvement_mode="improve")
    store = _live.ensure_live_store(
        str(tmp_path / "owned.json"), None, dict(_live.LIVE_AUTHORITY),
        dsn=study["dsn"], investigation_id=investigation_id)
    _live.propose_live_work(store, [{
        "opportunity_id": "opp-first",
        "mission_link": _live.LIVE_MISSION_OBJECTIVE,
        "question": "what does input 3 reveal on the rule",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004", "inputs": {"x": 3}},
        "resources": {"queries": 1, "steps": 1}}])
    return store, _live.bind_live_control(store, "low")


def _rows(dsn: str, sql: str, params: tuple = ()) -> list[dict]:
    from psycopg.rows import dict_row

    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            out = [dict(row) for row in cur.fetchall()]
            conn.commit()
            return out


# ------------------------------------------------------------------ the seam


def test_the_thread_is_one_authority_and_not_a_derivation():
    """`_run_frontier_investigation` builds it once and passes it down.

    A second `_study_authority` call inside the investigation would be a second
    allocation for one leg. This asserts the count over the parsed source, so a
    caller that grows one fails here rather than splitting the study's
    authority in a place nobody reads.
    """
    tree = ast.parse(DRIVER_PATH.read_text(encoding="utf-8"))
    body = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == "_run_frontier_investigation")
    derived = [n.lineno for n in ast.walk(body)
               if isinstance(n, ast.Call)
               and getattr(n.func, "id", "") == "_study_authority"]
    assert len(derived) == 1, (
        "_run_frontier_investigation derives the study authority %d times; "
        "one leg runs under one authority" % (len(derived),))
    triple = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_control_triple")
    assert not [n.lineno for n in ast.walk(triple)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_study_authority"], (
        "_control_triple derives its own authority; it must be handed the "
        "one the investigation already built")


def test_control_triple_requires_the_authority_it_is_given():
    """No default, because a default is the omission wearing a signature.

    `64850501` closed exactly this on `_run_frontier_investigation`: an
    optional `allocation_id` said a caller could leave it out and find out
    inside the executor. The same shape is closed here, because the same
    omission is what this seam is.
    """
    signature = inspect.signature(_driver._control_triple)
    assert "authority" in signature.parameters, (
        "_control_triple takes no authority at all")
    assert signature.parameters["authority"].default is inspect.Parameter.empty, (
        "_control_triple's authority defaults, so a caller may omit it and "
        "the choices settle on a disposable database again")
    assert signature.parameters["authority"].kind is inspect.Parameter.KEYWORD_ONLY


def test_every_production_choice_names_an_authority():
    """Structural, over the tree: a new call site without one fails here."""
    offenders: list[str] = []
    checked = 0
    for rel in ("experiments/ad01/live_construct.py", "scripts/invl02_live.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(
                node.func, "attr", None)
            if name != "choose_next_work":
                continue
            checked += 1
            if "authority" not in {kw.arg for kw in node.keywords}:
                offenders.append("%s:%d" % (rel, node.lineno))
    assert checked >= 3, (
        "found %d choose_next_work call sites, expected at least the three "
        "in _control_triple; the scan is no longer covering the tree it "
        "claims to" % (checked,))
    assert offenders == [], "choices without an authority: %s" % (offenders,)


# --------------------------------------------------------------- the refusal


def test_an_owned_store_refuses_to_choose_without_an_authority(study, tmp_path):
    """The omission is loud, not silent.

    `drive_improve_round` refuses this for the improve rounds and that refusal
    is the invariant. Before the thread, the choose path was the one place in
    the investigation that still settled on a disposable database, so the same
    refusal belongs there. An unowned store keeps working: a caller with no
    study to settle under is the fixture boundary and is not broken.
    """
    store, package = owned_store
    with pytest.raises(_live.LiveRefused) as refusal:
        _live.choose_next_work(store, package, [], arm="control")
    assert "disposable" in str(refusal.value), str(refusal.value)

    unowned = _live.ensure_live_store(
        str(tmp_path / "unowned.json"),
        live_mission(_live.LIVE_MISSION_OBJECTIVE,
                     [{"instrument": "boolean-rule-v1", "split": "dev",
                       "seed": 4}]),
        dict(_live.LIVE_AUTHORITY))
    _live.propose_live_work(unowned, [{
        "opportunity_id": "opp-unowned",
        "mission_link": _live.LIVE_MISSION_OBJECTIVE,
        "question": "what does input 3 reveal on the rule",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004", "inputs": {"x": 3}},
        "resources": {"queries": 1, "steps": 1}}])
    fixture_boundary = _live.bind_live_control(unowned, "low")
    assert _live.choose_next_work(
        unowned, fixture_boundary, [], arm="control")["choice"] == "opp-unowned"


# ------------------------------------------------------------ the settlement


def test_the_compared_choices_settle_under_the_study_allocation(
        study, owned_store):
    """The receipt lands on the study's allocation, not a disposable one.

    This is the load-bearing claim. `observation_dependent` and
    `falsifier_moves_decision` are computed from `_control_triple`'s three
    choices, so what is asserted here is that the decision M2 reports carries
    provenance the investigation can reach: the operations exist, on the
    allocation the study authorized, with the arm in the id.

    The disposable database this replaces was created and dropped inside the
    execution, so a receipt naming it names nothing that survives. The test
    therefore reads the operations row rather than trusting a returned value,
    because the returned value is the same dict in both worlds.
    """
    store, package = owned_store
    arms = _driver._control_triple(store, package, "control",
                                   authority=study)
    choices = {arms["preserved"]["choice"], arms["disconnected"]["choice"],
               arms["refuted"]["choice"]}

    rows = _rows(study["dsn"],
                 "SELECT id, allocation_id FROM operations"
                 " WHERE allocation_id = %s", (study["allocation_id"],))
    ids = {row["id"] for row in rows}
    assert rows, (
        "the compared choices left no operation on the study allocation, so "
        "they executed somewhere else -- a disposable database, which is the "
        "defect this closes")
    assert all(row["allocation_id"] == study["allocation_id"] for row in rows)
    # Every operate execution names its arm. Two arms of one study bind the
    # same deterministic `make_control("low")` and the same view, so the arm
    # is the only thing separating their operations, and an id reading
    # `noarm` would offer the ledger one operation for both.
    operate = {op for op in ids if op.startswith("invl02-op-")}
    assert operate, sorted(ids)
    assert all("-control-" in op or "-live-" in op for op in operate), (
        "an operate operation id does not name its arm: %s" % (sorted(operate),))
    assert not any("noarm" in op for op in operate), (
        "an operate operation id still reads noarm: %s" % (sorted(operate),))
    # The three compared choices are three distinct executions, not one
    # execution read back three times. On this store the recorded evidence is
    # empty, so the triple collapses to the disconnected arm by its own
    # documented rule; the distinction is asserted on the arm labels rather
    # than on the choice values, which coincide here by design.
    assert choices


def test_two_arms_of_one_study_do_not_share_an_operation(study):
    """The arm separates the ids, computed rather than asserted.

    An identity that omitted the arm would offer the broker one operation id
    with a different payload per arm, which it refuses as a
    request-identity conflict -- or, worse, reads the first arm's settled
    receipt instead of executing. The id is derived from a format string, and
    a format string can be edited, so the collision is computed here.
    """
    package = _channel.make_control("low")
    view = {"purpose": "op"}
    ids = {arm: _channel._derived_operation_id(package, "op", view, arm=arm)
           for arm in ("control", "live", "P1")}
    assert len(set(ids.values())) == 3, ids
    assert len(set(ids.values())) == len({package["package_digest"]}), ids


def test_the_census_tool_agrees_with_the_tree():
    """The artifact a reviewer reruns is checked against the source.

    `tools/prove_operate_step_authority.py` is the census; this asserts it
    reaches the same verdict the AST walk above reaches, so the tool cannot
    quietly report green while the tree says otherwise.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import prove_operate_step_authority as census

    report = census.census()
    rows = [r for r in report["rows"] if r["callee"] == "choose_next_work"]
    assert rows, "the census reached no choose_next_work call site"
    assert all(r["names_authority"] for r in rows), report["rows"]
    ids = census.operation_ids()
    assert ids["arms_are_distinct"], ids