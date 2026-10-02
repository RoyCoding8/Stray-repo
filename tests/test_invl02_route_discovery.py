from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import httpx

from experiments.ad01 import live_construct as live


def _catalog(*, include_resolved: bool = True) -> bytes:
    entries = [{
        "id": live.OUTPUT_ROUTE["requested_model"],
        "owned_by": "Openrouter",
        "metadata": {"credential": "must-not-be-recorded"},
    }]
    if include_resolved:
        entries.append({
            "id": live.OUTPUT_ROUTE["resolved_model"],
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
        "model_count": 3,
    }
    assert first["catalog"]["exact_id_presence"] == {
        "requested_model": True,
        "resolved_model": True,
    }
    assert [entry["id"] for entry in first["catalog"]["relevant_entries"]] == sorted([
        live.OUTPUT_ROUTE["requested_model"],
        live.OUTPUT_ROUTE["resolved_model"],
    ])
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


def test_route_discovery_records_exact_id_refusal(tmp_path):
    from scripts import invl02_route_discovery as discovery

    raw = _catalog(include_resolved=False)
    calls = []
    client = _client(raw, calls)
    result = discovery.discover_route(tmp_path / "refused", client=client)

    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert result["catalog"]["exact_id_presence"] == {
        "requested_model": True,
        "resolved_model": False,
    }
    assert result["result"]["verdict"] == "refused"
    assert result["result"]["route"] is None
    assert "exact resolved_model" in result["result"]["reason"]
    assert [entry["id"] for entry in result["catalog"]["relevant_entries"]] == [
        live.OUTPUT_ROUTE["requested_model"]
    ]
