"""Frozen, read-only model pilot; no generated code is executed.

This apparatus tests synthetic decision packets, not Settlement runtime
integration, learned retrieval, containment, paid billing or broad competence.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "claude-opus-4-6-thinking"
CONTRACT = (
    "Choose the next action from the request's allowed_actions using only its records. "
    "Treat this as a closed-world operational decision. A pending external effect must "
    "be reconciled before repeating it. A claim can have alternative support routes; "
    "one defeated route does not defeat another valid route. Respect method scope "
    "and registered counterexamples. Required artifact content cannot be replaced by "
    "a summary when bytes are unavailable. Missing required information must remain "
    "explicit. Return only JSON with decision (one allowed action), basis (all decisive "
    "record IDs), and a brief explanation. No external actions are authorized."
)
CASES = [
    {
        "id": "pending-effect",
        "request": {"question": "Resume the outstanding write operation.",
                    "allowed_actions": ["repeat", "reconcile", "declare_done"],
                    "required_refs": ["objective", "current-operation"]},
        "records": [
            {"id": "objective", "text": "Complete one write, preserving its identity.",
             "refs": ["current-operation"]},
            {"id": "current-operation", "text": "Operation w17 was sent; receipt absent; outcome unknown.",
             "refs": ["old-operation"]},
            {"id": "old-operation", "text": "Different operation w02 failed before dispatch last week."},
        ],
        "expected": "reconcile", "decisive": ["current-operation"],
    },
    {
        "id": "alternative-support",
        "request": {"question": "Is claim C supported for the declared finite domain?",
                    "allowed_actions": ["supported", "unsupported", "universal_theorem"],
                    "required_refs": ["claim-C"]},
        "records": [
            {"id": "claim-C", "text": "C concerns exactly inputs 1 through 10. Routes: A AND B, OR D.",
             "refs": ["premise-A", "premise-B", "route-D"]},
            {"id": "premise-A", "text": "A remains valid in the declared domain."},
            {"id": "premise-B", "text": "B was retracted; its former evidence was invalid."},
            {"id": "route-D", "text": "D is an independently checked exhaustive verification of C on 1 through 10; current, valid, no dependencies on A or B."},
        ],
        "expected": "supported", "decisive": ["route-D"],
    },
    {
        "id": "negative-transfer",
        "request": {"question": "Choose the method for input -2 within the available budget.",
                    "allowed_actions": ["new_method", "incumbent", "declare_done"],
                    "required_refs": ["new-method", "incumbent-method"]},
        "records": [
            {"id": "new-method", "text": "Released fast method M2 is supported only for nonnegative integers. Read linked opposition before selecting.",
             "refs": ["negative-case"]},
            {"id": "negative-case", "text": "Verified counterexample: M2 returns a wrong value on -2. It remains quarantined for negative inputs."},
            {"id": "incumbent-method", "text": "M1 is available, authorized, within the task budget, and verified for integers -10 through 10."},
        ],
        "expected": "incumbent", "decisive": ["negative-case"],
    },
    {
        "id": "missing-bytes",
        "request": {"question": "Can the next worker invoke the exact selected method now?",
                    "allowed_actions": ["invoke", "invent_replacement", "needs_information"],
                    "required_refs": ["selected-method"]},
        "records": [
            {"id": "selected-method", "text": "Use exact artifact digest abc123. Its byte content is required; no replacement version is admitted.",
             "refs": ["artifact-state", "method-summary"]},
            {"id": "artifact-state", "text": "Artifact abc123 metadata exists, but its bytes are unavailable in the declared store."},
            {"id": "method-summary", "text": "An old summary describes abc123 as a successful sorting method. This is a summary, not executable bytes."},
        ],
        "expected": "needs_information", "decisive": ["artifact-state"],
    },
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def records_for(case):
    noise = [{"id": f"unrelated-{i}", "text":
              f"Archived unrelated investigation {i}: a worker considered indexing, "
              "formatting and naming choices. Its local benchmark improved after a "
              "cache adjustment; the record makes no claim about the current task, "
              "its methods, evidence, operations, or artifact availability."}
             for i in range(16)]
    return noise[:8] + case["records"] + noise[8:]


def packet(case, arm):
    corpus = records_for(case)
    if arm == "dependency-context":
        by_id, needed = {r["id"]: r for r in corpus}, set(case["request"]["required_refs"])
        pending = list(needed)
        while pending:
            for ref in by_id[pending.pop()].get("refs", []):
                if ref not in needed:
                    needed.add(ref)
                    pending.append(ref)
        corpus = [r for r in corpus if r["id"] in needed]
    return {"request": case["request"], "records": corpus}


def protocol():
    return {"id": "context-pilot-01", "model": MODEL, "max_requests": 8,
            "max_output_tokens_per_request": 2048, "timeout_seconds": 120,
            "max_input_characters_per_request": 32768, "retries": 0,
            "arms": ["full-context", "dependency-context"],
            "order": [[case["id"], arm] for i, case in enumerate(CASES)
                      for arm in (("full-context", "dependency-context") if i % 2 == 0
                                  else ("dependency-context", "full-context"))],
            "cases": CASES, "instruction": CONTRACT,
            "source_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "limits": ["synthetic hand-authored cases", "fixed explicit dependency links",
                       "not a learned policy", "no repeated sampling or inferential claim",
                       "not repository runtime validation", "reported usage is not verified billing"],
            "primary_metric": "exact allowed decision equals frozen expected decision",
            "secondary_metric": "decisive source IDs present and all cited IDs delivered"}


def run(destination):
    destination.mkdir(parents=True, exist_ok=True)
    manifest, output = protocol(), destination / "results.json"
    manifest_path = destination / "protocol.json"
    if manifest_path.exists() or output.exists():
        raise SystemExit("Use a new run directory; prior evidence will not be overwritten.")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    base, key = os.environ["PILOT_GATEWAY_URL"].rstrip("/"), os.environ["PILOT_GATEWAY_KEY"]
    results = {"protocol_digest": digest(manifest), "model": MODEL, "calls": [], "complete": False}
    by_id = {c["id"]: c for c in CASES}
    for case_id, arm in manifest["order"]:
        case, context = by_id[case_id], packet(by_id[case_id], arm)
        rendered = json.dumps(context, sort_keys=True)
        if len(rendered) + len(CONTRACT) > manifest["max_input_characters_per_request"]:
            raise SystemExit("Frozen input ceiling exceeded.")
        body = json.dumps({"model": MODEL, "messages": [
            {"role": "system", "content": CONTRACT},
            {"role": "user", "content": rendered}], "max_tokens": 2048}).encode()
        request = urllib.request.Request(base + "/chat/completions", data=body,
                                        headers={"Authorization": "Bearer " + key,
                                                 "Content-Type": "application/json"})
        started = time.monotonic()
        row = {"case": case_id, "arm": arm, "input_chars": len(rendered) + len(CONTRACT),
               "packet_digest": digest(context), "packet": context}
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                decoded = json.load(response)
            choice = decoded["choices"][0]
            text = choice["message"].get("content") or ""
            row.update({"response_model": decoded.get("model"), "usage": decoded.get("usage"),
                        "finish_reason": choice.get("finish_reason"), "response": text})
            parsed = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
            row["decision_correct"] = isinstance(parsed, dict) and parsed.get("decision") == case["expected"]
            cited = parsed.get("basis", []) if isinstance(parsed, dict) else []
            delivered = {r["id"] for r in context["records"]}
            row["basis_correct"] = (isinstance(cited, list) and all(isinstance(x, str) for x in cited)
                                    and set(case["decisive"]) <= set(cited) <= delivered)
        except urllib.error.HTTPError as exc:
            row.update({"error": "HTTP", "status": exc.code})
        except Exception as exc:
            row["error"] = type(exc).__name__
        row["elapsed_seconds"] = round(time.monotonic() - started, 3)
        results["calls"].append(row)
        results["complete"] = len(results["calls"]) == manifest["max_requests"] and not row.get("error")
        output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in row.items() if k in {
            "case", "arm", "decision_correct", "basis_correct", "elapsed_seconds", "error", "status"}}), flush=True)
        if row.get("error"):
            return 2
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(run(Path(sys.argv[1])))
