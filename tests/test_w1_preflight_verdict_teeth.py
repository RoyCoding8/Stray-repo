"""The live preflight's assertion, driven to each outcome, with no network.

`test_the_live_route_carries_one_construction_end_to_end` asserts
`verdict["outcome"] == "constructed"`. It cannot run here, because the
credential is not configured and a live call is not available, so this
file is what proves the assertion has teeth.

It rebuilds that test's own body against a real `HttpGatewayAdapter`
over a mock socket. The adapter, the guard, the prompt, the dispatch
identity, the parser and the scorer are the shipped ones; the record
and the assertion are the same two lines the live test reads. So the
`route-refusal` case below is not a re-implementation of the check. It
is the check, fed the failure it exists to catch.

The old assertion was
`assert verdict["outcome"] in live.PREFLIGHT_OUTCOMES`, and
`route-refusal` is a member of that set, so every failure case below
passed it. That is why it stayed green while the route refused every
answer. Each case here asserts the literal the live test now asserts,
and each failure case is red under it.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import live_construct as live
from experiments.ad01.boolean_rule import _TABLE_TO_SPEC
from settlement.gateway_http import HttpGatewayAdapter

ROUTE = dict(live.OUTPUT_ROUTE)

# A program that solves nothing. It parses, so the taxonomy has to
# reach its scorer to call this a poor task result, which is why a
# preflight that only checks the transport would miss it.
ZERO_PROGRAM = json.dumps(
    {"specs": [{"const": 0, "mask": 0, "pair": None}] * 4})

# The body measured on the frozen route, with the `provider` the chat
# surface carries and the responses surface does not. Spelled `Nvidia`
# against a frozen `nvidia`, which the caseless label absorbs.
CHAT_BODY = {
    "id": "gen-w1",
    "object": "chat.completion",
    "model": ROUTE["resolved_model"],
    "provider": "Nvidia",
    "service_tier": None,
    "choices": [{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant", "content": ZERO_PROGRAM}}],
    "usage": {"prompt_tokens": 900, "completion_tokens": 48, "cost": 0},
}


def _gateway(body: dict, *, status: int = 200, api: str = "chat",
             route: dict = ROUTE, content: str | None = None):
    """A real adapter, real socket contract, no socket."""
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        payload = dict(body)
        if content is not None:
            payload["choices"] = [{"index": 0, "finish_reason": "stop",
                                   "message": {"role": "assistant",
                                               "content": content}}]
        raw = json.dumps(payload).encode()
        return httpx.Response(status, stream=httpx.ByteStream(raw))

    adapter = HttpGatewayAdapter(
        endpoint=ROUTE["endpoint"], api_key="unused", api=api,
        expected_route=dict(route),
        client=httpx.Client(transport=httpx.MockTransport(handler)))
    return adapter, sent


def _live_assertion(record: dict) -> None:
    """The two lines the live test reads, verbatim.

    Copied rather than imported because the live test skips without a
    credential, and this file exists to drive the same assertion. If
    the live test's assertion changes, this copy is the thing that
    stops matching, and `test_this_file_tracks_the_live_assertion`
    fails instead of this file quietly proving a stale claim.
    """
    verdict = record["verdict"]
    assert verdict["outcome"] == "constructed", (
        "the pinned free route did not carry a live construction: "
        f"{verdict['outcome']} ({verdict['reason']})")


def test_this_file_tracks_the_live_assertion():
    """A proof of a stale assertion proves nothing.

    The live test is the authority on what the preflight must produce.
    This file is the authority on whether that assertion can fail. If
    the two drift, this is where it shows, rather than in a live run
    nobody can afford.
    """
    source = (ROOT / "tests" / "test_w1_live_preflight.py").read_text(
        encoding="utf-8")

    assert 'assert verdict["outcome"] == "constructed"' in source
    assert 'assert verdict["outcome"] in live.PREFLIGHT_OUTCOMES' not in source


def test_a_correct_transport_with_a_wrong_route_is_red(tmp_path):
    """The failure the live test used to pass on.

    A 200 with a correct answer on the frozen route, except that the
    body names a different vendor. `_response_meta` files
    `response_metadata` over it, and the preflight reports
    `route-refusal`. Under the old membership assertion this was
    green. Under the assertion the live test now makes, it is red.
    """
    adapter, sent = _gateway({**CHAT_BODY, "provider": "Openai"})
    record = live.preflight_run(tmp_path, adapter)

    assert len(sent) == 1, "the send happened; only the verdict is at issue"
    assert record["verdict"]["outcome"] == "route-refusal"
    with pytest.raises(AssertionError, match="route-refusal"):
        _live_assertion(record)


def test_a_responses_body_that_carries_no_provider_is_red(tmp_path):
    """Defect 1 seen from the preflight, which is where it was spent.

    The responses surface cannot attest the frozen route, and the
    adapter now refuses it before the wire. Either way the preflight
    reports a refusal, and either way the live assertion is red. A test
    that cannot tell those two apart is why the defect survived three
    repairs.
    """
    responses_body = {
        "id": "resp-w1", "object": "response", "status": "completed",
        "model": ROUTE["resolved_model"],
        "output": [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text",
                                 "text": ZERO_PROGRAM}]}],
        "service_tier": None,
        "usage": {"input_tokens": 900, "output_tokens": 48, "cost": 0},
    }
    adapter, sent = _gateway(responses_body, api="responses")
    record = live.preflight_run(tmp_path, adapter)

    assert record["verdict"]["outcome"] == "route-refusal"
    assert sent == [], (
        "the refusal must cost nothing; the live test would be paying "
        "for a verdict it could have had before the send")
    with pytest.raises(AssertionError, match="route-refusal"):
        _live_assertion(record)


def test_a_program_that_parses_but_solves_nothing_is_red(tmp_path):
    """A transport that worked and a model that failed the task.

    Worth its own case because it is the one the old assertion handled
    honestly: `poor-task-result` is in the set, so the old test would
    have passed it too. The point is that the new assertion is not
    merely stricter about refusals. It refuses a live route that
    answers and is wrong, which is a claim about the model.
    """
    adapter, sent = _gateway(CHAT_BODY)
    record = live.preflight_run(tmp_path, adapter)

    assert len(sent) == 1
    assert record["verdict"]["outcome"] == "poor-task-result"
    with pytest.raises(AssertionError, match="poor-task-result"):
        _live_assertion(record)


def test_a_solved_task_is_the_only_green(tmp_path):
    """The positive half. Without it the assertion could be `False`.

    A refused answer and a wrong answer are easy to reject. If nothing
    could ever be accepted, the assertion would be unfalsifiable in the
    other direction and would have stopped describing a working route.
    This builds a program that solves the frozen task, through the
    shipped prompt and scorer, and requires the preflight to accept it.
    """
    task, session = live._preflight_task()
    program = json.dumps(
        {"specs": [_TABLE_TO_SPEC[table] for table in task["tables"]]},
        sort_keys=True)

    adapter, sent = _gateway(CHAT_BODY, content=program)
    record = live.preflight_run(tmp_path, adapter)

    assert len(sent) == 1
    assert record["verdict"]["outcome"] == "constructed"
    assert record["attempts"][0]["score"]["overall"] == 1.0
    _live_assertion(record)
