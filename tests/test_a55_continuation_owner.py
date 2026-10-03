"""The fresh-process continuation can open the store the live path owns.

`improve_channel.fresh_round` is the tree's only continuation entry: a second
process picks up a live investigation by opening its store and driving the next
round. It opened with `FrontierStore(store_path)` and no identity, so it could
only ever continue a nameless store. `live_construct.ensure_live_store` records
the owning investigation in the document it writes, and `_check_identity`
refuses a nameless open of an owned one. The result is that the one production
continuation path cannot continue anything the live entry creates, which is the
whole of the live path.

This file pins the join in both directions. A store with a recorded owner is
openable only by naming that owner; a store with no recorded owner stays
openable namelessly, because the fixture boundary has no owner to name. The
second case is the one that keeps this from becoming a general "every open
needs a dsn" rule.

The tests that drive a round need a disposable PostgreSQL database, so they
are stubbed and run anywhere. The refusal itself needs no SQL: it is decided
in `_check_identity`. Of the seven tests, three were red before the repair and
four held throughout; the four are the invariants that keep this from becoming
a general "every open needs a dsn" rule.
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
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live

ENVIRONMENTS = [{"instrument": "boolean-rule-v1", "split": "dev", "seed": 4}]
DSN = "dbname=a55-continuation"


def _mission():
    return live.live_mission(live.LIVE_MISSION_OBJECTIVE, ENVIRONMENTS)


def _owned(tmp_path, name, investigation_id):
    path = tmp_path / name
    frontier.create_store(
        path, namespace=frontier.NAMESPACE, mission=_mission(),
        authority=dict(live.LIVE_AUTHORITY),
        identity=frontier.StoreIdentity(investigation_id=investigation_id,
                                        dsn=DSN))
    return path


def _nameless(tmp_path, name):
    path = tmp_path / name
    frontier.create_store(
        path, namespace=frontier.NAMESPACE, mission=_mission(),
        authority=dict(live.LIVE_AUTHORITY))
    return path


def _read(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_the_owned_store_cannot_be_opened_namelessly(tmp_path):
    """The guard the repair routes around rather than removes.

    Green before and after: this is pre-existing behaviour, and it is the
    reason the repair is a join and not a loosening. What changed is that a
    caller can now answer the refusal instead of hitting it as a dead end.
    """
    path = _owned(tmp_path, "owned.json", "a55-owned")
    assert _read(path)["identity"] == {"investigation_id": "a55-owned"}

    with pytest.raises(frontier.Refused, match="nameless store cannot address"):
        frontier.FrontierStore(path)


def test_the_owned_store_opens_by_naming_its_owner(tmp_path):
    path = _owned(tmp_path, "owned.json", "a55-owned")

    store = frontier.FrontierStore(
        path, identity=frontier.StoreIdentity(investigation_id="a55-owned",
                                              dsn=DSN))

    assert store.identity.investigation_id == "a55-owned"


def test_a_nameless_store_still_opens_namelessly(tmp_path):
    """The fixture boundary has no owner to name, and must keep working."""
    path = _nameless(tmp_path, "nameless.json")
    assert _read(path)["identity"] is None

    store = frontier.FrontierStore(path)

    assert store.identity is None


def test_fresh_round_names_an_owner_when_one_is_supplied(tmp_path, monkeypatch):
    """`fresh_round` opens the store the owner named, not a nameless one.

    This is the continuation entry itself. Before the repair it called
    `FrontierStore(store_path)` with no identity, so on an owned document it
    raised the nameless refusal above and the second process could never
    continue a live investigation. `dsn` and `investigation_id` are the two
    halves `StoreIdentity` already required together.

    The round is stubbed because driving one needs a disposable PostgreSQL
    database; what is under test is which store the entry opened, not what a
    round does.
    """
    path = _owned(tmp_path, "owned.json", "a55-owned")
    opened = {}
    real = frontier.FrontierStore

    class Spy:
        def __init__(self, store_path, identity=None):
            opened["path"] = store_path
            opened["identity"] = identity
            self._delegate = real(store_path, identity)

        def __getattr__(self, name):
            return getattr(self._delegate, name)

    bound = real(path, identity=frontier.StoreIdentity(
        investigation_id="a55-owned", dsn=DSN))
    live.bind_live_control(bound, "low")
    monkeypatch.setattr(channel._frontier, "FrontierStore", Spy)
    monkeypatch.setattr(
        channel, "drive_improve_round",
        lambda store, task, round_no, admit_probes=False: {
            "candidate": {"control_id": "cand", "parent_digest": "p" * 64,
                          "imp_digest": "i" * 64}})

    channel.fresh_round(path, 2, dsn=DSN, investigation_id="a55-owned")

    assert opened["path"] == path
    assert opened["identity"] == frontier.StoreIdentity(
        investigation_id="a55-owned", dsn=DSN)


def test_fresh_round_still_continues_a_nameless_store(tmp_path, monkeypatch):
    """Adding the owner is not a reason to stop opening nameless stores."""
    path = _nameless(tmp_path, "nameless.json")
    store = frontier.FrontierStore(path)
    live.bind_live_control(store, "low")
    monkeypatch.setattr(
        channel, "drive_improve_round",
        lambda store, task, round_no, admit_probes=False: {
            "candidate": {"control_id": "cand", "parent_digest": "p" * 64,
                          "imp_digest": "i" * 64}})

    summary = channel.fresh_round(path, 2)

    assert summary["candidate_id"] == "cand"
    assert summary["round"] == 2


def test_fresh_round_requires_both_halves_of_an_identity(tmp_path):
    """Half an identity names nothing, so it is a refusal rather than a default.

    The same rule `live_construct._live_identity` already applies at the other
    end of this path: a dsn with no investigation names no row, and an
    investigation with no dsn names no row to address it on.
    """
    path = _owned(tmp_path, "owned.json", "a55-owned")

    with pytest.raises(frontier.Refused, match="together"):
        channel.fresh_round(path, 2, dsn=DSN)


def test_the_main_entry_can_pass_the_owner_through(tmp_path):
    """`main` is the argv surface a second process actually uses.

    `fresh_round` takes the two names as keywords; if `main` did not forward
    them the new parameters would be unreachable from the only process that
    needs them.
    """
    source = ast.parse((ROOT / "experiments/ad01/improve_channel.py")
                       .read_text(encoding="utf-8"))
    main_fn = next(node for node in source.body
                   if isinstance(node, ast.FunctionDef)
                   and node.name == "main")
    calls = [node for node in ast.walk(main_fn)
             if isinstance(node, ast.Call)
             and getattr(node.func, "id", None) == "fresh_round"]
    assert calls, "main no longer calls fresh_round"
    forwarded = {kw.arg for kw in calls[0].keywords}
    assert {"dsn", "investigation_id"} <= forwarded


def test_main_names_the_owner_rather_than_taking_it_positionally():
    """A trailing positional made the two-argument call mean two things.

    `fresh_round(store_path, round_no)` is the fixture boundary: a store with
    no recorded owner. With the names as trailing positionals, that same call
    also meant "an owned store whose names the caller forgot", and a failure
    pointed inside `fresh_round` rather than at the call that omitted them.
    The names are options, so omitting them is one meaning.
    """
    source = ast.parse((ROOT / "experiments/ad01/improve_channel.py")
                       .read_text(encoding="utf-8"))
    main_fn = next(node for node in source.body
                   if isinstance(node, ast.FunctionDef)
                   and node.name == "main")
    positional = [node for node in ast.walk(main_fn)
                  if isinstance(node, ast.Call)
                  and getattr(node.func, "id", None) == "fresh_round"
                  and len(node.args) > 2]
    assert not positional, (
        "main passes owner names positionally again; the two-argument call is"
        " the nameless case and must not share a meaning")
    options = [node for node in ast.walk(main_fn)
               if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute)
               and node.func.attr == "add_argument"
               and node.args and isinstance(node.args[0], ast.Constant)
               and isinstance(node.args[0].value, str)]
    flags = {node.args[0].value for node in options}
    assert {"--dsn", "--investigation-id"} <= flags, sorted(flags)


def test_main_still_runs_the_two_argument_call(tmp_path, monkeypatch, capsys):
    """The fixture boundary survives: two arguments, no owner, still runs.

    This is the call `tests/test_m2_frontier_inherit.py` makes, and the one the
    positional pair made ambiguous.
    """
    path = _nameless(tmp_path, "nameless.json")
    store = frontier.FrontierStore(path)
    live.bind_live_control(store, "low")
    monkeypatch.setattr(
        channel, "drive_improve_round",
        lambda store, task, round_no, admit_probes=False: {"candidate": {
            "control_id": "cand", "parent_digest": "p" * 64,
            "imp_digest": "i" * 64}})

    assert channel.main(["improve_channel", str(path), "3"]) == 0

    assert json.loads(capsys.readouterr().out)["round"] == 3
