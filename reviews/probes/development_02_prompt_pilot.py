"""Two frozen live prompt checks; synthetic state, no generated-code execution."""

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from test_development_02_acceptance import capture_construct_prompt, materialize
from settlement import experiment


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main(destination):
    destination.mkdir(parents=True, exist_ok=False)
    packet = materialize()
    diagnosis = json.dumps({"episode": "episode", "phase": "diagnose", "packet_id": packet["packet_id"],
                           "packet": packet["rendered"], "ceilings": {"explanations": 2},
                           "ask": "explanations and one intervention"})
    bundle = {"claim_id": "episode-exp-dev-sum-claim", "proposition": {
        "task_id": "dev-sum", "family": "off_by_one",
        "broken": "def sum_to(n):\n    return sum(range(n))\n",
        "cases": [{"fn": "sum_to", "args": [5], "expected": 15}],
        "model_text": "def sum_to(n):\n    return sum(range(n+1))\n", "outcome": "success"},
        "scope": {"episode": "episode", "family": "off_by_one"}, "access_label": "candidate",
        "disposition": "supported", "selected_route": {"derivation": "warrant", "premises": []},
        "alternative_routes": [], "opposition": [], "premise_content": [], "qualifications": []}
    constructor = capture_construct_prompt([bundle])["prompt"]
    protocol = {"id": "development-02-prompt-pilot", "implementation": "a1d2525a37571abf45a54de45c3dfcdad4aaaf9f",
        "model": "claude-opus-4-6-thinking", "max_requests": 2, "max_tokens": experiment.MODEL_TOKENS,
        "timeout_seconds": 120, "retries": 0, "order": ["diagnose", "construct"],
        "prompts": {"diagnose": diagnosis, "construct": constructor},
        "apparatus_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                             [Path(__file__), Path(__file__).with_name("test_development_02_acceptance.py")]},
        "checks": ["finish reason", "strict JSON parse", "diagnosis intervention present", "constructor code present"],
        "limits": ["independent prompt checks over synthetic database-shaped records",
                   "production packet rendering and constructor prompt assembly; diagnosis wrapper transcribed from production",
                   "not sequential live episode, DB, broker, billing, sandbox, learning or generated-code validation"]}
    (destination / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    results = {"protocol_digest": digest(protocol), "calls": []}
    for phase in protocol["order"]:
        request = urllib.request.Request(os.environ["PILOT_GATEWAY_URL"].rstrip("/") + "/chat/completions",
            data=json.dumps({"model": protocol["model"], "max_tokens": protocol["max_tokens"],
                             "messages": [{"role": "user", "content": protocol["prompts"][phase]}]}).encode(),
            headers={"Authorization": "Bearer " + os.environ["PILOT_GATEWAY_KEY"], "Content-Type": "application/json"})
        row, started = {"phase": phase}, time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=protocol["timeout_seconds"]) as response:
                data = json.load(response)
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
            row.update({"response_model": data.get("model"), "response": text,
                        "finish_reason": choice.get("finish_reason"), "usage": data.get("usage")})
            try:
                parsed = json.loads(text)
                row["strict_json"] = True
                row["expected_field_present"] = bool(parsed.get("intervention" if phase == "diagnose" else "code"))
            except (ValueError, AttributeError):
                row["strict_json"] = False
        except urllib.error.HTTPError as exc:
            row.update({"error": "HTTP", "status": exc.code})
        except Exception as exc:
            row["error"] = type(exc).__name__
        row["seconds"] = round(time.monotonic() - started, 3)
        results["calls"].append(row)
        (destination / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in row.items() if k != "response"}), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
