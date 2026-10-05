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
in `_check_identity`. Of the round-driving tests, three were red before the
repair and the rest held throughout; the ones that held are the invariants
that keep this from becoming a general "every open needs a dsn" rule.

The stub that replaces the round records what `fresh_round` forwarded. Opening
a store under its owner is not authority to execute against it -- an owned
store's round settles receipts somewhere that investigation has to reach -- so
the entry forwards the caller's allocation and, where there is none, forwards
nothing at all and lets `drive_improve_round` refuse. The refusal is decided
above `fresh_round`'s reach and no test here drives it, so what each
round-driving test pins is the forwarding: that the entry passes the authority
its caller holds rather than passing nothing and relying on the round to
notice.
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

# The charter shape `ensure_live_store` accepts, as a fixture. It was a
# production helper with no production caller, deleted in 8d354a5.
from conftest import live_mission

ENVIRONMENTS = [{"instrument": "boolean-rule-v1", "split": "dev", "seed": 4}]
DSN = "dbname=a55-continuation"


def _mission():
    return live_mission(live.LIVE_MISSION_OBJECTIVE, ENVIRONMENTS)


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


def _stub_round():
    """The round, replaced by the summary `fresh_round` reads.

    Each call site patched this inline as a lambda naming `store`, `task`,
    `round_no` and `admit_probes`. That is `drive_improve_round`'s signature
    restated by hand, so every keyword added to it since reached a double with
    no word for it as a `TypeError`, and the breakage said nothing about the
    store -- which is what this file measures.

    The keyword arguments are collected and recorded rather than enumerated or
    dropped. Collecting them means a signature that grows leaves the stub
    working without a second edit, and recording them means a keyword that
    changes the round's authority is still something a test can read. The
    positional parameters are named because `fresh_round` passes `store` and
    `task` positionally, which the production call sites are checked against.

    `round_calls` is where those assertions read.
    """
    calls = []

    def stub(store, task, round_no=None, **forwarded):
        calls.append({"store": store, "task": task, "round_no": round_no,
                      **forwarded})
        return {"candidate": {"control_id": "cand",
                              "parent_digest": "p" * 64,
                              "imp_digest": "i" * 64}}

    stub.round_calls = calls
    return stub


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
    round_stub = _stub_round()
    monkeypatch.setattr(channel, "drive_improve_round", round_stub)

    channel.fresh_round(path, 2, dsn=DSN, investigation_id="a55-owned")

    assert opened["path"] == path
    assert opened["identity"] == frontier.StoreIdentity(
        investigation_id="a55-owned", dsn=DSN)
    # Naming the owner opens it; it is not authority to execute against it.
    # With no allocation the entry forwards `None` and `drive_improve_round`
    # refuses the round, which is the refusal this thread exists to reach.
    assert round_stub.round_calls[0]["authority"] is None


def test_fresh_round_forwards_the_allocation_it_was_given(tmp_path, monkeypatch):
    """The entry passes the round an allocation when the caller holds one.

    The other round-driving tests supply no allocation, so all three read a
    forwarded authority of `None`. That is the right value for each of them
    and it cannot see an entry that dropped the caller's allocation, which is
    the defect this leg repaired: an owned store names an investigation whose
    unresolved work settles somewhere, so a round holding no authority mints a
    disposable ledger whose receipts the investigation cannot reach.

    This is the fourth test, and the only one here that supplies the third
    name. It reads the forwarded pair rather than calling `_round_authority`,
    so it measures the wiring and not the constructor.
    """
    path = _owned(tmp_path, "owned.json", "a55-owned")
    store = frontier.FrontierStore(path, identity=frontier.StoreIdentity(
        investigation_id="a55-owned", dsn=DSN))
    live.bind_live_control(store, "low")
    round_stub = _stub_round()
    monkeypatch.setattr(channel, "drive_improve_round", round_stub)

    channel.fresh_round(path, 2, dsn=DSN, investigation_id="a55-owned",
                        allocation_id="a55-alloc")

    assert round_stub.round_calls[0]["authority"] == {
        "dsn": DSN, "allocation_id": "a55-alloc"}
    # Half the pair names nothing, so the entry offers no authority at all
    # rather than one half of it. `drive_improve_round` owns the refusal.
    assert channel._round_authority(DSN, None) is None
    assert channel._round_authority(None, "a55-alloc") is None


def test_fresh_round_still_continues_a_nameless_store(tmp_path, monkeypatch):
    """Adding the owner is not a reason to stop opening nameless stores."""
    path = _nameless(tmp_path, "nameless.json")
    store = frontier.FrontierStore(path)
    live.bind_live_control(store, "low")
    round_stub = _stub_round()
    monkeypatch.setattr(channel, "drive_improve_round", round_stub)

    summary = channel.fresh_round(path, 2)

    assert summary["candidate_id"] == "cand"
    assert summary["round"] == 2
    # The fixture boundary spends nothing and mints no ledger, which is what
    # forwarding `None` means on a store that names no owner.
    assert round_stub.round_calls[0]["authority"] is None


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
    round_stub = _stub_round()
    monkeypatch.setattr(channel, "drive_improve_round", round_stub)

    assert channel.main(["improve_channel", str(path), "3"]) == 0

    assert json.loads(capsys.readouterr().out)["round"] == 3
    assert round_stub.round_calls[0]["authority"] is None
