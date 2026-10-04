"""The live store names the investigation whose row would own its effects.

`ensure_live_store` already received a `dsn` and an `investigation_id` and
read its mission off `investigations`. It handed neither to `FrontierStore`,
so the live store carried no owner: the durable entry named the mission and
the file said nothing about who owned the unresolved work in it. Two
authorities, one of which had no way to address the other.

These tests pin the join. Each names the mechanism it fails on, and the
first three were shown red against the unjoined `ensure_live_store` by
reverting the `StoreIdentity` construction and re-running, not by argument.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import frontier
from experiments.ad01 import live_construct as live
from experiments.ad01 import mission
from experiments.ad01.s09_run_isolation import create_disposable_db, \
    drop_disposable_db

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "a31wireidentity"

ENVIRONMENTS = [{"instrument": "boolean-rule-v1", "split": "dev", "seed": 4}]


@pytest.fixture(scope="module")
def dsn():
    database = create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database)


@pytest.fixture()
def entered(dsn, request):
    investigation_id = "a31-%s" % request.node.name.replace("_", "-")
    mission.record_mission(
        dsn, investigation_id, objective=live.LIVE_MISSION_OBJECTIVE,
        environments=ENVIRONMENTS, constraints=[], success_criteria=[],
        improvement_mode="improve")
    return dsn, investigation_id


def _read(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_the_live_store_records_the_investigation_that_owns_it(entered, tmp_path):
    """The document names the investigation, not merely the mission it holds.

    Red on the unjoined boundary: the store was written with no identity, so
    `identity` was absent rather than naming the entry the live path had
    already read its mission from.
    """
    database, investigation_id = entered
    path = tmp_path / "live.json"

    live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                           dsn=database, investigation_id=investigation_id)

    assert _read(path)["identity"] == {"investigation_id": investigation_id}


def test_the_live_store_carries_the_dsn_in_process_only(entered, tmp_path):
    """The connection reaches the row and never reaches the file.

    A `dsn` in the document would make a copied store a reachable handle on
    the durable side from wherever the copy lands, so the persisted identity
    is the investigation id alone.
    """
    database, investigation_id = entered
    path = tmp_path / "live.json"

    store = live.ensure_live_store(
        path, None, dict(live.LIVE_AUTHORITY), dsn=database,
        investigation_id=investigation_id)

    assert store.identity.investigation_id == investigation_id
    assert store.identity.dsn == database
    assert database not in Path(path).read_text(encoding="utf-8")


def test_a_nameless_live_store_says_it_has_no_owner(tmp_path):
    """The fixture boundary still works, and records the absence explicitly.

    `learner_revision`, `channel_controls` and the two-domain entry have no
    `dsn` in scope, so their stores stay nameless. An absent `identity` key
    would leave that to be inferred from whichever version wrote the file;
    an explicit `null` states it.
    """
    path = tmp_path / "fixture.json"

    store = live.ensure_live_store(
        path, live.live_mission(live.LIVE_MISSION_OBJECTIVE, ENVIRONMENTS),
        dict(live.LIVE_AUTHORITY))

    assert store.identity is None
    assert "identity" in _read(path)
    assert _read(path)["identity"] is None


def test_a_nameless_live_store_cannot_be_claimed_afterwards(entered, tmp_path):
    """The inverse: attaching an identity to a nameless store is refused.

    Without this the ownership would be decorative — a store could be written
    with no owner and later pointed at an investigation, so the effect it
    held would be attributed to an entry that never admitted it. The refusal
    is asserted at the live boundary, which is where a real caller arrives.
    """
    database, investigation_id = entered
    path = tmp_path / "fixture.json"
    live.ensure_live_store(
        path, live.live_mission(live.LIVE_MISSION_OBJECTIVE, ENVIRONMENTS),
        dict(live.LIVE_AUTHORITY))

    with pytest.raises(live.LiveRefused, match="owned by investigation"):
        live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                               dsn=database,
                               investigation_id=investigation_id)


def test_an_owned_live_store_cannot_be_reopened_namelessly(entered, tmp_path):
    """Losing the identity on restart loses the ability to address.

    A restart that dropped the pair would read an owned document with no
    identity in hand, which is the case the store refuses rather than
    defaults. The live restart therefore takes the pair, and this asserts
    that the nameless form is the thing that fails.
    """
    database, investigation_id = entered
    path = tmp_path / "live.json"
    live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                           dsn=database, investigation_id=investigation_id)

    with pytest.raises(live.LiveRefused, match="nameless store"):
        live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY))


def test_restart_carries_the_same_owner(entered, tmp_path):
    """A restarted live store is the same mission continuing, not a new one."""
    database, investigation_id = entered
    path = tmp_path / "live.json"
    live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                           dsn=database, investigation_id=investigation_id)

    restarted = live.restart_store(path, dsn=database,
                                   investigation_id=investigation_id)

    assert restarted.identity.investigation_id == investigation_id
    assert restarted.identity.dsn == database


def test_restart_of_a_nameless_live_store_stays_nameless(tmp_path):
    """The fixture restart path is unchanged by the identity being available."""
    path = tmp_path / "fixture.json"
    live.ensure_live_store(
        path, live.live_mission(live.LIVE_MISSION_OBJECTIVE, ENVIRONMENTS),
        dict(live.LIVE_AUTHORITY))

    assert live.restart_store(path).identity is None


def test_the_live_entry_arms_are_separately_owned(entered, tmp_path):
    """Two arms of one run are two stores under two owners.

    The E12 arms share a study root and a run id, so keying an identity on
    either alone would route the second arm's admitted-unrun effects at the
    first arm's row. The document has to say which.
    """
    database, _ = entered
    paths = []
    for label in ("P1", "P2"):
        investigation_id = "a31-%s" % label
        mission.record_mission(
            database, investigation_id,
            objective=live.LIVE_MISSION_OBJECTIVE,
            environments=ENVIRONMENTS)
        path = tmp_path / ("%s.json" % label)
        live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                               dsn=database,
                               investigation_id=investigation_id)
        paths.append(path)

    owners = {_read(path)["identity"]["investigation_id"] for path in paths}
    assert len(owners) == 2


def test_half_an_identity_is_refused_at_the_live_boundary(entered, tmp_path):
    """Neither half alone names a row, so neither alone opens a live store."""
    database, investigation_id = entered
    for kwargs in ({"dsn": database}, {"investigation_id": investigation_id}):
        with pytest.raises(live.LiveRefused, match="together"):
            live.ensure_live_store(tmp_path / "half.json", None,
                                   dict(live.LIVE_AUTHORITY), **kwargs)


def test_every_live_reopen_threads_an_identity():
    """No live-path opener reaches `FrontierStore` without naming its owner.

    The defect was four functions that each opened the store the live entry
    owns, none of them passing the identity the entry had. Asserting the
    signatures keeps it that way: a new live opener has to be counted here,
    because nothing else would notice it opening nameless.
    """
    tree = ast.parse(
        (ROOT / "experiments" / "ad01" / "live_construct.py").read_text(
            encoding="utf-8"))
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    for name in ("ensure_live_store", "restart_store", "bind_live_revision",
                 "bind_retained_acquisition"):
        node = functions[name]
        names = {arg.arg for arg in node.args.args}
        names |= {arg.arg for arg in node.args.kwonlyargs}
        assert {"dsn", "investigation_id"} <= names, (
            "%s opens a live store without an owner to open it under" % name)


def test_the_live_entry_records_the_identity_it_opened_under():
    """The record a caller reopens from carries the owner it must reopen with.

    `run_e0` and `run_e12` reopen the store their arm wrote, through
    `bind_retained_acquisition` and `run_e3`. Those reopenings need the
    identity, and re-deriving it at each call site would be a second place
    that decides which investigation a store belongs to.
    """
    driver = (ROOT / "scripts" / "invl02_live.py").read_text(encoding="utf-8")
    assert '"investigation_id": investigation_id' in driver
    tree = ast.parse(driver)
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr in {"bind_retained_acquisition",
                                    "restart_store"}]
    assert calls, "the live entry no longer reopens its own store"
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert "investigation_id" in keywords, (
            "the live entry reopens a store without naming its owner")


def test_an_edited_charter_is_still_refused_on_the_same_investigation(entered,
                                                                     tmp_path):
    """The mission-mismatch check survives the identity check.

    A27's guard refuses a *different* investigation before the objective is
    compared, which preempts the check `ensure_live_store` has always done.
    That check is still live for the case it was written for: the entry's own
    charter moving under a store that still names the same investigation.
    Without this the objective comparison would be dead code reached by
    nothing.
    """
    database, investigation_id = entered
    path = tmp_path / "live.json"
    live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                           dsn=database, investigation_id=investigation_id)
    mission.record_mission(
        database, investigation_id, objective="a charter that moved",
        environments=ENVIRONMENTS)

    with pytest.raises(live.LiveRefused, match="mission mismatch"):
        live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                               dsn=database,
                               investigation_id=investigation_id)


def test_a_different_investigation_is_refused_by_ownership_first(entered,
                                                                tmp_path):
    """Which refusal fires when the caller names the wrong investigation.

    Two arms of one run have separate owners, so opening one arm's store
    under the other arm's id is a wrong-owner fault. It is refused as that,
    before the objective is ever compared, and the message says so.
    """
    database, investigation_id = entered
    path = tmp_path / "live.json"
    live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                           dsn=database, investigation_id=investigation_id)
    other = "a31-a-different-investigation"
    mission.record_mission(
        database, other, objective="a different objective",
        environments=ENVIRONMENTS)

    with pytest.raises(live.LiveRefused, match="owned by investigation"):
        live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                               dsn=database, investigation_id=other)


def test_the_two_refusal_vocabularies_are_deliberate(entered, tmp_path):
    """`ensure_live_store` translates; `restart_store` does not.

    Measured, not assumed. Translating every live refusal into `LiveRefused`
    looks like tidying and breaks 46 inherited tests in
    `test_provenance_authority.py`, because `restart_store` and
    `bind_retained_acquisition` are documented and tested as passing
    `frontier.Refused` through: a caller tells "the store is unreadable"
    from "the caller got the arguments wrong" by that type. The opener that
    takes a caller-supplied mission keeps `LiveRefused`; the ones that reopen
    a store the live path already owns keep the store's own type.
    """
    database, investigation_id = entered
    path = tmp_path / "live.json"
    live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                           dsn=database, investigation_id=investigation_id)
    other = "a31-vocabulary-other"
    mission.record_mission(
        database, other, objective=live.LIVE_MISSION_OBJECTIVE,
        environments=ENVIRONMENTS)

    with pytest.raises(live.LiveRefused):
        live.ensure_live_store(path, None, dict(live.LIVE_AUTHORITY),
                               dsn=database, investigation_id=other)
    with pytest.raises(frontier.Refused):
        live.restart_store(path, dsn=database, investigation_id=other)
