from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments.ad01 import frontier


def _mission():
    return {
        "objective": "route an admitted effect to its durable owner",
        "environments": [{"instrument": "boolean-rule-v1",
                          "split": "dev", "seed": 4}],
    }


def _store(path, investigation_id=None, dsn=None):
    identity = None
    if investigation_id is not None or dsn is not None:
        identity = frontier.StoreIdentity(investigation_id=investigation_id,
                                          dsn=dsn)
    return frontier.create_store(
        path, namespace="invl02_m2", mission=_mission(),
        authority={"queries": 16, "steps": 12}, identity=identity)


def _package():
    from experiments.ad01 import improve_channel as channel
    return channel.make_control("low")


def _admitted(store):
    """One admitted-unrun effect, admitted the way a real caller does."""
    store.bind_active(_package())
    store.propose({
        "opportunity_id": "opp-probe",
        "mission_link": "route an admitted effect to its durable owner",
        "question": "observe input 3",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004", "inputs": {"x": 3}},
        "resources": {"queries": 1, "steps": 1}})
    return store.admit_and_spend("opp-probe", store.active_digest,
                                 {"queries": 1, "steps": 1},
                                 effect_identity={"operation_id": "op-1"})


DSN = "dbname=s09a27 host=/var/run/postgresql user=ubuntu"
OTHER_DSN = "dbname=s09a27b host=/var/run/postgresql user=ubuntu"


def test_store_carries_the_durable_identity_it_was_given(tmp_path):
    """A store holds the two names that reach `investigations.in_flight`."""
    store = _store(tmp_path / "id.json", "inv-a27", DSN)
    assert store.identity.investigation_id == "inv-a27"
    assert store.identity.dsn == DSN
    assert store.identity.durable is True


def test_admit_and_spend_routes_against_that_identity(tmp_path):
    """The admitted-unrun effect is addressable from the store itself.

    This is the write at `_admit_and_spend` that A26 measured as the only
    creation of an admitted-unrun effect in the tree. The store now names
    the row that would own it, so the effect's owner is read off the store
    rather than carried beside it by the caller.
    """
    store = _store(tmp_path / "id.json", "inv-a27", DSN)
    effect = _admitted(store)
    assert effect["status"] == "pending"
    assert store.identity.investigation_id == "inv-a27"
    assert effect["charged"] is True


def test_identity_is_persisted_and_the_dsn_is_not(tmp_path):
    """The document names the investigation; the connection stays in process."""
    path = tmp_path / "id.json"
    _store(path, "inv-a27", DSN)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["identity"] == {"investigation_id": "inv-a27"}
    assert DSN not in path.read_text(encoding="utf-8")


def test_reopening_under_a_different_investigation_is_refused(tmp_path):
    """A wrong identity is refused, not accepted and ignored.

    Opening under another investigation would route this store's effects to
    a row that owns a different mission, so the store refuses rather than
    reconciling the two names.
    """
    path = tmp_path / "id.json"
    _store(path, "inv-a27", DSN)
    with pytest.raises(frontier.Refused, match="owned by investigation"):
        frontier.FrontierStore(path, frontier.StoreIdentity(
            investigation_id="inv-other", dsn=OTHER_DSN))


def test_reopening_under_no_identity_cannot_address_an_owned_store(tmp_path):
    """Losing the identity is losing the ability to address, not a default."""
    path = tmp_path / "id.json"
    _store(path, "inv-a27", DSN)
    with pytest.raises(frontier.Refused, match="nameless store"):
        frontier.FrontierStore(path)


def test_reopening_under_the_same_identity_succeeds(tmp_path):
    path = tmp_path / "id.json"
    _store(path, "inv-a27", DSN)
    reopened = frontier.FrontierStore(path, frontier.StoreIdentity(
        investigation_id="inv-a27", dsn=DSN))
    assert reopened.identity.investigation_id == "inv-a27"


def test_a_nameless_store_reopens_without_one(tmp_path):
    """The genuinely JSON-only paths still work, and say so in the file."""
    path = tmp_path / "plain.json"
    _store(path)
    reopened = frontier.FrontierStore(path)
    assert reopened.identity is None
    assert json.loads(path.read_text(encoding="utf-8"))["identity"] is None


def test_a_nameless_store_cannot_be_adopted_after_the_fact(tmp_path):
    """An identity cannot be attached to a store that was written nameless."""
    path = tmp_path / "plain.json"
    _store(path)
    with pytest.raises(frontier.Refused, match="owned by investigation"):
        frontier.FrontierStore(path, frontier.StoreIdentity(
            investigation_id="inv-a27", dsn=DSN))


@pytest.mark.parametrize("investigation_id,dsn", [
    ("inv-a27", None),
    (None, DSN),
    ("", DSN),
    ("   ", DSN),
    ("inv-a27", ""),
    ("inv-a27", "   "),
    (17, DSN),
])
def test_half_an_identity_identifies_nothing(tmp_path, investigation_id, dsn):
    """A dsn with no investigation, or the reverse, names no row at all.

    Both halves together address `investigations.in_flight`. Either alone is
    a caller that believes it supplied an identity and did not, which is the
    silent-wrong-owner failure this is here to prevent.
    """
    with pytest.raises(frontier.Refused):
        frontier.create_store(
            tmp_path / "half.json", namespace="invl02_m2",
            mission=_mission(), authority={"queries": 16, "steps": 12},
            identity=frontier.StoreIdentity(
                investigation_id=investigation_id, dsn=dsn))


def test_a_non_identity_argument_is_refused_not_ignored(tmp_path):
    """A caller that passes a bare string gets a refusal, not a silent store.

    Passing the investigation id where an identity belongs would otherwise
    produce a store that carries no owner at all while the caller believes it
    supplied one.
    """
    with pytest.raises(frontier.Refused):
        frontier.create_store(
            tmp_path / "str.json", namespace="invl02_m2",
            mission=_mission(), authority={"queries": 8, "steps": 8},
            identity="inv-a27")


def test_a_tampered_identity_record_is_refused(tmp_path):
    """An edited document cannot re-point its owner."""
    path = tmp_path / "id.json"
    _store(path, "inv-a27", DSN)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["identity"]["investigation_id"] = "inv-other"
    path.write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")),
                    encoding="utf-8")
    with pytest.raises(frontier.Refused, match="owned by investigation"):
        frontier.FrontierStore(path, frontier.StoreIdentity(
            investigation_id="inv-a27", dsn=DSN))


def test_a_second_authority_is_not_accepted_while_reloading(tmp_path):
    """Identity is checked on every locked reload, not only at open.

    `_reload_under_lock` is where every admitted effect is written, so an
    identity checked only in `__init__` would leave the write path trusting
    an in-memory value that no longer matches the document that owns it.
    """
    path = tmp_path / "id.json"
    store = _store(path, "inv-a27", DSN)
    _admitted(store)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["identity"]["investigation_id"] = "inv-other"
    path.write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")),
                    encoding="utf-8")
    with pytest.raises(frontier.Refused, match="owned by investigation"):
        store._reload_under_lock()


def test_a_forged_in_memory_identity_is_refused_on_the_write_path(tmp_path):
    """A store whose identity diverged from its document cannot write.

    `object.__setattr__` reaches past the frozen dataclass, and a caller with
    the file handle can edit the document directly. Either way the store's
    in-memory identity and its document can disagree, and an admitted effect
    routed on the in-memory value would land on another investigation's row
    while the document recorded the first. The reload check runs on every
    locked transaction precisely so this is refused at the write.
    """
    path = tmp_path / "id.json"
    store = _store(path, "inv-a27", DSN)
    store.bind_active(_package())
    store.propose({
        "opportunity_id": "opp-probe",
        "mission_link": "route an admitted effect to its durable owner",
        "question": "observe input 3",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004", "inputs": {"x": 3}},
        "resources": {"queries": 1, "steps": 1}})
    object.__setattr__(store.identity, "investigation_id", "inv-forged")
    with pytest.raises(frontier.Refused, match="owned by investigation"):
        store.admit_and_spend("opp-probe", store.active_digest,
                              {"queries": 1, "steps": 1},
                              effect_identity={"operation_id": "op-1"})
    assert json.loads(path.read_text(encoding="utf-8"))[
        "identity"]["investigation_id"] == "inv-a27"
