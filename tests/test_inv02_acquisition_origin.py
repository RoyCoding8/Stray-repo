"""`origin` has to be earned from a receipt, not written as a literal.

The construction path used to pass `origin="model-acquired"` to
`make_policy_artifact` at four sites and `verify_policy_record` only checked
that the string was one it knew. So a recording double's authored bytes
reached a durable record labelled as a model's. These tests drive the real
seam against a disposable database: a fixture adapter and an HTTP-shaped
adapter answer the same operation, and only the second may be called
acquired.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import construct, live_construct, method_exec, policy_step
from experiments.ad01.s09_run_isolation import disposable_db
from experiments.doubles import ACQUIRED_ORDER_SOURCE

TOKEN = "invl02acq%s" % uuid.uuid4().hex[:8]

POLICY_SOURCE = (
    "def STEP(view, state):\n"
    "    return {\"action\": {\"kind\": \"stop\", \"target\": \"t\",\n"
    "                      \"inputs\": {}, \"evidence_refs\": [],\n"
    "                      \"requested_resources\": {}},\n"
    "            \"state\": {}}\n"
)

FIXTURE_META = {"simulated": True, "stream": "software"}
LIVE_META = {
    "adapter": "http", "contract": "responses", "response_received": True,
    "endpoint": "http://localhost:4000/v1",
    "request_endpoint": "http://localhost:4000/v1",
    "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "provider": "Nvidia", "tier": "free",
}


def _response(source: str) -> str:
    return json.dumps({"entry": source, "notes": "one attempt"})


def _settle(dsn: str, operation_id: str, *, model: str, prompt: str,
            meta: dict) -> str:
    """Commit the prompt before the send, then settle a receipt for it.

    This is the order `construct._call` uses: `ensure_operation` pins the
    prompt, the adapter answers, and the broker writes the receipt. Building
    it here by hand keeps the test to the store's own contract instead of
    standing up a broker dispatch.
    """
    from psycopg.rows import dict_row
    from settlement import db
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO operations (id, payload_digest, payload,"
                " dispatch_state, settled) VALUES"
                " (%s, %s, %s, 'reconciled', TRUE)",
                (operation_id, hashlib.sha256(prompt.encode()).hexdigest(),
                 json.dumps({
                    "effect": "model-inference",
                    "payload": {"model": model,
                                "messages": [{"role": "user",
                                              "content": prompt}]}})))
            cur.execute(
                "INSERT INTO receipts (receipt_identity, operation_id,"
                " content_digest, content, outcome)"
                " VALUES (%s, %s, %s, %s, 'success')",
                ("gw:%s" % operation_id, operation_id,
                 hashlib.sha256(b"x").hexdigest(),
                 json.dumps({"operation_id": operation_id,
                             "text": _response(POLICY_SOURCE),
                             "model_meta": meta, "stop_reason": "stop",
                             "usage": {"billed": False}})))
            conn.commit()
    return operation_id


def test_fixture_served_response_is_not_model_acquired():
    with disposable_db(TOKEN) as database:
        operation = _settle(
            database.dsn, "ad01-campaign-1-construct-l1-init",
            model="inv01-study-double", prompt="Write one python method.",
            meta=FIXTURE_META)
        earned = construct.acquisition_origin(
            database.dsn, operation, _response(POLICY_SOURCE))
        assert earned["origin"] == "fixture-stand-in"
        assert earned["acquisition_evidence"]["earned"] is False
        assert earned["acquisition_evidence"]["simulated"] is True
        assert earned["acquisition_evidence"]["reason"] == (
            "response is marked simulated")


def test_live_served_response_is_model_acquired():
    with disposable_db(TOKEN) as database:
        operation = _settle(
            database.dsn, "ad01-campaign-1-policy-l1-init",
            model=LIVE_META["model"], prompt="Write one python policy.",
            meta=LIVE_META)
        earned = construct.acquisition_origin(
            database.dsn, operation, _response(POLICY_SOURCE))
        assert earned["origin"] == "model-acquired"
        assert earned["acquisition_evidence"]["earned"] is True
        assert earned["acquisition_evidence"]["route"]["provider"] == "Nvidia"


def test_a_routed_request_is_earned_for_the_model_it_resolves_to():
    """The study asks for `openrouter/...`; the receipt names `nvidia/...`.

    A live dispatch on 2026-09-29 returned genuine provider bytes with sha256
    e910a154, and `read_acquisition_evidence` still read them
    `fixture-stand-in`, because it compared the payload's `model` to the
    receipt's resolved name with `==`. Those are the `requested_model` and
    `resolved_model` fields of one route, and
    `tests/test_inv_r1_live_route_pin.py` already records that requiring them
    to be equal refuses every real route. So the arm was demoted to a stand-in
    over a routing prefix, and E1 with it.
    """
    with disposable_db(TOKEN) as database:
        operation = _settle(
            database.dsn, "ad01-campaign-1-policy-l1-init",
            model="openrouter/" + LIVE_META["model"],
            prompt="Write one python policy.", meta=LIVE_META)
        earned = construct.acquisition_origin(
            database.dsn, operation, _response(POLICY_SOURCE))
        assert earned["origin"] == "model-acquired"
        assert earned["acquisition_evidence"]["earned"] is True
        assert earned["acquisition_evidence"]["requested_model"] == (
            "openrouter/" + LIVE_META["model"])


@pytest.mark.parametrize("requested", [
    "nvidia/other-model:free",
    "openrouter/openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
    "nemotron-3-ultra-550b-a55b:free",
    "openai/nvidia/nemotron-3-ultra-550b-a55b:free",
    "",
])
def test_a_different_model_is_still_refused(requested):
    """The join is a spelling rule, not a licence to call anything earned.

    Each value here is a way the two names can differ while the receipt still
    names a different model, an unnamespaced one, or a second prefix. If any
    of them earned, the join would have stopped discriminating and every
    stand-in with a plausible model string would pass.
    """
    with disposable_db(TOKEN) as database:
        operation = _settle(
            database.dsn, "ad01-campaign-1-policy-l1-init",
            model=requested, prompt="Write one python policy.",
            meta=LIVE_META)
        earned = construct.acquisition_origin(
            database.dsn, operation, _response(POLICY_SOURCE))
        assert earned["origin"] == "fixture-stand-in"
        assert earned["acquisition_evidence"]["earned"] is False


def test_the_join_does_not_survive_a_missing_model_name():
    """Neither name being a string is not a match."""
    with disposable_db(TOKEN) as database:
        operation = _settle(
            database.dsn, "ad01-campaign-1-policy-l1-init",
            model="openrouter/nvidia/x:free", prompt="Write a policy.",
            meta=dict(LIVE_META, model=""))
        earned = construct.acquisition_origin(
            database.dsn, operation, _response(POLICY_SOURCE))
        assert earned["acquisition_evidence"]["earned"] is False
        assert earned["acquisition_evidence"]["reason"] == (
            "response carries no route metadata for model")


def test_the_double_constant_is_not_acquired():
    """The exact bytes ad3a60b named, on a real settled operation.

    `ACQUIRED_ORDER_SOURCE` is the source the recording study freeze calls
    `model-acquired`. Served by a fixture it must come back
    `fixture-stand-in`, or the label is a lie in a durable record.
    """
    with disposable_db(TOKEN) as database:
        from psycopg.rows import dict_row
        from settlement import db
        operation = "ad01-campaign-2-construct-l1-init"
        text = _response(ACQUIRED_ORDER_SOURCE)
        with db.connect(database.dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "INSERT INTO operations (id, payload_digest, payload,"
                    " dispatch_state, settled) VALUES (%s, %s, %s,"
                    " 'reconciled', TRUE)",
                    (operation, hashlib.sha256(b"prompt").hexdigest(),
                     json.dumps({
                        "effect": "model-inference",
                        "payload": {"model": "inv01-study-double",
                                    "messages": [{"role": "user",
                                                  "content": "prompt"}]}})))
                cur.execute(
                    "INSERT INTO receipts (receipt_identity, operation_id,"
                    " content_digest, content, outcome)"
                    " VALUES (%s, %s, %s, %s, 'success')",
                    ("gw:%s" % operation, operation,
                     hashlib.sha256(b"x").hexdigest(),
                     json.dumps({"operation_id": operation, "text": text,
                                 "model_meta": FIXTURE_META,
                                 "stop_reason": "stop"})))
                conn.commit()
        earned = construct.acquisition_origin(database.dsn, operation, text)
        assert earned["origin"] == "fixture-stand-in"
        entry = construct._entry_name(ACQUIRED_ORDER_SOURCE)
        member = {"capability_id": "acquired-sw-deadbeef",
                  "method_source": ACQUIRED_ORDER_SOURCE, "entry": entry,
                  "scope": {"family": "software"}, "authored": False,
                  "origin": earned["origin"]}
        assert member["origin"] == "fixture-stand-in"
        method_exec.verify_member(member)


def test_member_bytes_that_are_not_the_settled_response_are_refused():
    with disposable_db(TOKEN) as database:
        operation = _settle(
            database.dsn, "ad01-campaign-3-policy-l1-init",
            model=LIVE_META["model"], prompt="Write one python policy.",
            meta=LIVE_META)
        earned = construct.acquisition_origin(
            database.dsn, operation, _response(POLICY_SOURCE + "\n# edited\n"))
        assert earned["origin"] == "fixture-stand-in"
        assert earned["acquisition_evidence"]["reason"] == (
            "member bytes are not the settled response")


def test_adapter_that_is_not_http_is_refused():
    """A fixture that lies about its route still cannot be acquired.

    The route fields alone would pass if a caller also pinned its model to
    the same string, so the check is on the adapter that produced them.
    """
    meta = dict(LIVE_META, adapter="scripted")
    with disposable_db(TOKEN) as database:
        operation = _settle(
            database.dsn, "ad01-campaign-4-policy-l1-init",
            model=LIVE_META["model"], prompt="Write one python policy.",
            meta=meta)
        earned = construct.acquisition_origin(
            database.dsn, operation, _response(POLICY_SOURCE))
        assert earned["origin"] == "fixture-stand-in"
        assert "not http" in earned["acquisition_evidence"]["reason"]


def test_absent_operation_yields_no_claim():
    with disposable_db(TOKEN) as database:
        evidence = live_construct.read_acquisition_evidence(
            database.dsn, "ad01-nothing-here", _response(POLICY_SOURCE))
        assert evidence["earned"] is False
        assert "no committed operation" in evidence["reason"]


def test_settled_response_without_a_receipt_yields_no_claim():
    with disposable_db(TOKEN) as database:
        from settlement import db
        with db.connect(database.dsn) as conn:
            conn.execute(
                "INSERT INTO operations (id, payload_digest, payload,"
                " dispatch_state, settled) VALUES"
                " ('ad01-campaign-5-construct-l1-init', %s, %s, 'reconciled',"
                " TRUE)",
                (hashlib.sha256(b"p").hexdigest(),
                 json.dumps({"effect": "model-inference",
                             "payload": {"model": LIVE_META["model"],
                                         "messages": [{"role": "user",
                                                       "content": "p"}]}})))
            conn.commit()
        evidence = live_construct.read_acquisition_evidence(
            database.dsn, "ad01-campaign-5-construct-l1-init",
            _response(POLICY_SOURCE))
        assert evidence["earned"] is False
        assert "no settled success receipt" in evidence["reason"]


def test_replay_search_finds_the_constructing_operation():
    """A freeze stores bytes, so a replay has to look up who wrote them."""
    digest = hashlib.sha256(POLICY_SOURCE.encode("utf-8")).hexdigest()
    with disposable_db(TOKEN) as database:
        _settle(database.dsn, "ad01-campaign-6-construct-l1-init",
                model="inv01-study-double", prompt="p", meta=FIXTURE_META)
        found = live_construct.find_acquisition_operation(database.dsn, digest)
        assert found == "ad01-campaign-6-construct-l1-init"
        missing = live_construct.find_acquisition_operation(
            database.dsn, "0" * 64)
        assert missing is None


def test_trajectory_origin_helper_refuses_bytes_no_operation_produced():
    from experiments.ad01 import trajectory
    digest = hashlib.sha256(POLICY_SOURCE.encode("utf-8")).hexdigest()
    with disposable_db(TOKEN) as database:
        assert trajectory._frozen_policy_origin(
            database.dsn, digest, POLICY_SOURCE) is None


def test_verify_still_accepts_the_earned_origin_string():
    """`verify_policy_record` is unchanged; the label is what changed."""
    for origin in policy_step.POLICY_ORIGINS:
        record = policy_step.make_policy_artifact(
            POLICY_SOURCE, origin=origin)
        assert policy_step.verify_policy_record(record)["origin"] == origin


def test_unknown_origin_is_still_refused():
    with pytest.raises(ValueError):
        policy_step.make_policy_artifact(POLICY_SOURCE,
                                         origin="definitely-earned")
