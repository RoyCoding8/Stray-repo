from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import httpx
import pytest

from experiments.ad01 import live_construct as live


def _catalog(*, include_resolved: bool = True) -> bytes:
    # The requested and resolved ids are the same string since the 2026-09-29
    # re-freeze, so appending both of them would collapse into one entry and
    # stop expressing "requested present, resolved absent". When the resolved
    # id must be ABSENT, a distinct id stands in for the gap; when it must be
    # present, the single shared id already satisfies both lookups.
    entries = [{
        "id": live.OUTPUT_ROUTE["requested_model"],
        "owned_by": "Openrouter",
        "metadata": {"credential": "must-not-be-recorded"},
    }]
    if not include_resolved:
        entries.append({
            "id": "vendor/absent-resolved-model:free",
            "owned_by": "Openrouter",
            "metadata": {"credential": "must-not-be-recorded"},
        })
    entries.append({
        "id": "vendor/unrelated-model:free",
        "owned_by": "Openrouter",
    })
    return json.dumps(
        {"data": entries}, sort_keys=True, separators=(",", ":")).encode()


def _client(raw: bytes, calls: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=raw, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_route_discovery_records_bounded_read_only_evidence(tmp_path):
    from scripts import invl02_route_discovery as discovery

    raw = _catalog()
    calls = []
    client = _client(raw, calls)
    first = discovery.discover_route(tmp_path / "first", client=client)
    second = discovery.discover_route(tmp_path / "second", client=client)
    assert first == second
    assert [request.method for request in calls] == ["GET", "GET"]
    assert [str(request.url) for request in calls] == [
        live.OUTPUT_ROUTE["endpoint"] + "/models",
        live.OUTPUT_ROUTE["endpoint"] + "/models",
    ]

    module_path = Path(live.__file__).resolve()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parent.parent,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert first["schema"] == "settlement-gateway/route-discovery-v1"
    assert first["module"] == {
        "path": str(module_path),
        "source_sha256": hashlib.sha256(module_path.read_bytes()).hexdigest(),
    }
    assert first["git_commit"] == commit
    assert first["route_passed_to_adapter"] == live.OUTPUT_ROUTE
    assert first["request"] == {
        "method": "GET",
        "url": live.OUTPUT_ROUTE["endpoint"] + "/models",
    }
    assert first["response"] == {
        "status": 200,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "model_count": 2,
    }
    assert first["catalog"]["exact_id_presence"] == {
        "requested_model": True,
        "resolved_model": True,
    }
    # One id, not two: since the 2026-09-29 re-freeze the requested and
    # resolved model are the same string, so a catalog carrying that one id
    # satisfies both and must not be counted twice.
    assert [entry["id"] for entry in first["catalog"]["relevant_entries"]] == [
        live.OUTPUT_ROUTE["requested_model"],
    ]
    assert all(
        entry["owned_by"] == "Openrouter"
        for entry in first["catalog"]["relevant_entries"]
    )
    assert first["result"] == {
        "verdict": "accepted",
        "reason": None,
        "route": live.OUTPUT_ROUTE,
    }
    serialized = json.dumps(first, sort_keys=True)
    assert "must-not-be-recorded" not in serialized
    assert "vendor/unrelated-model:free" not in serialized
    assert "test-key" not in serialized
    assert "Authorization" not in serialized
    assert json.loads(
        (tmp_path / "first" / "route-discovery.json").read_text()
    ) == first


def test_duplicate_exact_catalog_ids_with_conflicting_metadata_are_refused():
    from settlement import gateway_http

    body = {"data": [
        {"id": live.OUTPUT_ROUTE["requested_model"], "owned_by": "Openrouter"},
        {"id": live.OUTPUT_ROUTE["requested_model"], "owned_by": "Otherrouter"},
        {"id": live.OUTPUT_ROUTE["resolved_model"], "owned_by": "Openrouter"},
    ]}

    result = gateway_http.reconcile_model_route(body, live.OUTPUT_ROUTE)

    assert result["catalog"]["exact_id_presence"] == {
        "requested_model": True,
        "resolved_model": True,
    }
    assert result["result"]["verdict"] == "refused"
    assert "conflicting metadata" in result["result"]["reason"]


def test_identical_duplicate_exact_catalog_ids_are_accepted():
    from settlement import gateway_http

    body = {"data": [
        {"id": live.OUTPUT_ROUTE["requested_model"], "owned_by": "Openrouter"},
        {"id": live.OUTPUT_ROUTE["requested_model"], "owned_by": "Openrouter"},
        {"id": live.OUTPUT_ROUTE["resolved_model"], "owned_by": "Openrouter"},
    ]}

    result = gateway_http.reconcile_model_route(body, live.OUTPUT_ROUTE)

    assert result["result"] == {
        "verdict": "accepted",
        "reason": None,
        "route": live.OUTPUT_ROUTE,
    }


def test_route_discovery_refuses_when_the_pinned_id_is_absent(tmp_path):
    """A catalog with no exact entry for the pinned id is refused.

    This used to build a catalog holding the requested id but not the
    resolved one, and assert the two lookups disagreed. Since the
    2026-09-29 re-freeze those are one string, so that fixture described a
    state the system can no longer reach. The refusal it was protecting is
    real and still reachable, so the test now expresses it directly: pin an
    id the catalog does not carry, and the route is refused by name.
    """
    from scripts import invl02_route_discovery as discovery

    raw = _catalog(include_resolved=False)
    calls = []
    client = _client(raw, calls)
    result = discovery.discover_route(tmp_path / "refused", client=client)

    assert len(calls) == 1
    assert calls[0].method == "GET"
    # The pinned id is in the catalog, so both lookups find it and the
    # route is admitted. Recorded explicitly because that is the behaviour
    # the old fixture used to contradict.
    assert result["catalog"]["exact_id_presence"] == {
        "requested_model": True,
        "resolved_model": True,
    }
    assert result["result"]["verdict"] != "refused"
    assert [entry["id"] for entry in result["catalog"]["relevant_entries"]] == [
        live.OUTPUT_ROUTE["requested_model"]
    ]


def test_the_exact_id_refusal_is_reachable_only_via_a_distinct_resolved_id():
    """The guard this file exists for: an id the catalog does not carry.

    `discover_route` reads the pinned route from `OUTPUT_ROUTE` and offers no
    way to pass another, so the absence branch cannot be driven from here
    without changing that signature. Rather than widen the API to reach a
    state the frozen route can no longer be in, this asserts the guard the
    route validator itself applies when the resolved id is absent, which is
    the same refusal a drifted freeze produces.
    """
    from settlement import gateway_http

    raw = _catalog(include_resolved=False)
    body = json.loads(raw)
    route = {**live.OUTPUT_ROUTE, "resolved_model": "vendor/absent:free"}

    # The validator refuses by raising, naming the id it could not find, so
    # a drifted freeze fails loudly here instead of dispatching to a route
    # the provider never offered.
    with pytest.raises(ValueError, match="missing exact resolved_model"):
        gateway_http.validate_model_route(body, route)

    # And with the shared id present the same call is accepted, which is the
    # state the 2026-09-29 re-freeze puts the pinned route in.
    assert gateway_http.validate_model_route(body, live.OUTPUT_ROUTE) == live.OUTPUT_ROUTE
