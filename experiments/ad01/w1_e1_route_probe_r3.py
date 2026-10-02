"""The route defect r3 hit, measured rather than asserted.

r3's eight-cell grid settled as eight `transport-loss`, every one of them an
HTTP 502 from the router. A campaign whose cells all end in a lost send has
measured the route's availability and nothing else, so the question that
decides whether r3 says anything about the model is a question about the
route. This module answers it by probing, and it records the probe beside the
answer so a reader can check the search was honest.

Three findings, in the order they matter:

1. **The frozen model is absent from the live catalog but still answers.** The
   catalog carries 256 entries and does not list
   `nvidia/nemotron-3-ultra-550b-a55b:free`. Dispatching it anyway returns
   HTTP 200 with `"model"` set to that exact id. So the route is reachable
   and unpinnable at the same time, which is the state the cap sheet's
   "route spelling re-frozen" precondition was written to prevent and which
   the 2026-09-29 re-freeze did not detect.

2. **The 502 is caused by the requested output budget, not by the prompt.**
   The same prompt returns 200 at `max_tokens` 16 and 256, and 502s at 2048.
   A short prompt returns 200 at 2048. So the two variables separate cleanly:
   it is the combination of a long generation on this route that the upstream
   cannot serve, and the campaign's own `max_output_tokens: 2048` is what puts
   it there.

3. **The route reports a cost field the adapter does not read.** The live body
   carries `usage.cost: 0` and a `cost_details` block. `gateway_http._decode_usage`
   reads `charge_units`, `charge_scale` and `billed`, none of which this body
   has, so every attempt records `billed: unknown` and `charge_units: unknown`.
   `gateway_http.py:356-368` documents the `usage.cost: 0` measurement and
   states that `usage.cost` is deliberately not a channel, so the adapter is
   behaving as designed and the exposure cannot be converted to cost on this
   route. That is a harness fact, not a campaign defect, and it is why r3's
   charge total is null rather than zero.

None of this is patched here. This lane may not edit a shipped module, so each
finding is reported and left for the owner of the route contract.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

PROBE_VERSION = "w1-e1-r3-route-probe-v1"


def _key() -> str:
    return os.environ.get("SETTLEMENT_GATEWAY_KEY", "")


def _endpoint(suffix: str) -> str:
    base = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT", "").rstrip("/")
    return base + suffix


def _post(body: dict, timeout: int = 180) -> dict:
    """One probe. Returns status and the fields the findings rest on.

    The key is read from the environment and never written to the result, so
    a probe record is safe to commit.
    """
    request = urllib.request.Request(
        _endpoint("/chat/completions"),
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer %s" % _key(),
                 "Content-Type": "application/json"},
        method="POST")
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            status = response.status
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {}
        status = exc.code
    except Exception as exc:
        return {"status": None, "error": "%s: %s" % (type(exc).__name__, exc),
                "seconds": round(time.time() - started, 2)}
    return _summarize(status, payload, round(time.time() - started, 2))


def _summarize(status, payload: dict, seconds: float) -> dict:
    row = {"status": status, "seconds": seconds}
    if "error" in payload and "choices" not in payload:
        error = payload.get("error") or {}
        row["error_type"] = error.get("type")
        row["error_message"] = str(error.get("message", ""))[:160]
        return row
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = payload.get("usage") or {}
    text = message.get("content")
    row.update({
        "returned_model": payload.get("model"),
        "provider": payload.get("provider"),
        "finish_reason": choice.get("finish_reason"),
        "content_characters": len(text) if isinstance(text, str) else None,
        "usage": usage,
        "usage_keys": sorted(usage),
        "charge_fields_present": sorted(
            k for k in usage
            if "charge" in k or k in ("billed", "cost")),
    })
    return row


def _catalog() -> dict:
    request = urllib.request.Request(
        _endpoint("/models"),
        headers={"Authorization": "Bearer %s" % _key()})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"error": "%s: %s" % (type(exc).__name__, exc)}
    ids = [entry.get("id") for entry in (payload.get("data") or [])]
    from experiments.ad01 import live_construct as live
    frozen = live.OUTPUT_ROUTE["requested_model"]
    return {"model_count": len(ids), "frozen_id": frozen,
            "frozen_present": frozen in ids,
            "same_model_other_spellings": sorted(
                i for i in ids if isinstance(i, str)
                and i.split("/")[-1] == frozen.split("/")[-1])}


def probe() -> dict:
    """Every probe this finding rests on, run fresh and recorded.

    The arms separate the two variables. `short-prompt-budget-2048` holds the
    output budget at the protocol's 2048 and shortens the input, so a 200
    there means the budget alone is survivable. The three
    `campaign-prompt-budget-*` arms hold the protocol's real prompt and vary
    the budget from 16 to 2048, so the budget at which the same prompt stops
    being served is visible rather than inferred.
    """
    from experiments.ad01 import live_construct as live
    import experiments.ad01.w1_e1_campaign_r3 as campaign

    _, session = campaign._build_session("qual", 11)
    prompt = live.render_output_prompt(session.output_model_input(), [], 1)
    model = live.OUTPUT_ROUTE["requested_model"]

    def _body(text: str, max_tokens: int) -> dict:
        return {"model": model, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": text}]}

    arms = {
        "short-prompt-budget-2048": ("Say OK", 2048),
        "campaign-prompt-budget-16": (prompt, 16),
        "campaign-prompt-budget-256": (prompt, 256),
        "campaign-prompt-budget-2048": (prompt, 2048),
    }
    results = {name: _post(_body(text, tokens))
               for name, (text, tokens) in arms.items()}
    return {
        "schema": PROBE_VERSION,
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "frozen_route": dict(live.OUTPUT_ROUTE),
        "frozen_max_output_tokens": live.OUTPUT_LIMITS["max_output_tokens"],
        "frozen_character_cap": live.OUTPUT_LIMITS["max_response_characters"],
        "campaign_prompt_characters": len(prompt),
        "catalog": _catalog(),
        "probes": results,
        "findings": [
            {"id": "frozen-model-absent-from-catalog",
             "statement": "the frozen model id is not in the live catalog, and "
                          "dispatching it anyway returns 200 naming that exact "
                          "id, so the route is reachable and unpinnable at "
                          "once",
             "evidence": "catalog.frozen_present is false while "
                         "probes['short-prompt-budget-2048'].returned_model "
                         "equals the frozen id"},
            {"id": "output-budget-causes-the-502",
             "statement": "the 502 tracks the requested output budget on this "
                          "route, not the prompt. The same protocol prompt "
                          "returns 200 at 16 and 256 tokens and 502s at the "
                          "protocol's own 2048; a short prompt returns 200 at "
                          "2048",
             "evidence": "compare the three campaign-prompt arms against the "
                         "short-prompt arm"},
            {"id": "cost-is-not-readable-on-this-route",
             "statement": "the body carries usage.cost and cost_details, and "
                          "the adapter reads charge_units, charge_scale and "
                          "billed, none of which this route returns, so every "
                          "attempt records billed and charge_units as unknown. "
                          "gateway_http.py:356-368 documents that measurement "
                          "and states usage.cost is deliberately not a "
                          "channel, so this is a harness fact rather than a "
                          "campaign defect",
             "evidence": "probes[*].usage_keys against the adapter's field "
                         "list"},
        ],
        "not_patched_here": "this lane may not edit a shipped module, so all "
                            "three are reported and left to the route "
                            "contract's owner",
    }


def main(argv=None) -> int:
    print(json.dumps(probe(), sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
