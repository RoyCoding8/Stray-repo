"""Check archived package bytes, decision evidence links and reported usage offline."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_bytes())


def check(condition, reason):
    if not condition:
        raise SystemExit(reason)


freeze = load("freeze.json")
check(hashlib.sha256((ROOT / "run.py").read_bytes()).hexdigest()
      == freeze["driver_sha256"], "driver digest mismatch")
packages = {}
for item in load("artifacts.json"):
    raw = (ROOT / "artifacts" / item["digest"]).read_bytes()
    check(len(raw) == item["bytes"], "package size mismatch")
    check(hashlib.sha256(raw).hexdigest() == item["digest"], "package digest mismatch")
    package = json.loads(raw)
    for entry in package["manifest"]["files"]:
        content = bytes.fromhex(package["files"][entry["path"]])
        check(len(content) == entry["size"], "file size mismatch")
        check(hashlib.sha256(content).hexdigest() == entry["digest"], "file digest mismatch")
    packages[item["digest"]] = package

store = load("operations.json")
operations = {row[0]: row for row in store["operations"]}
receipts = {row[0]: row for row in store["receipts"]}
episodes = {row[0]: row for row in store["episodes"]}
check(len(operations) == len(receipts) == 8, "operation/receipt count mismatch")
check(all(row[4] for row in operations.values()), "unsettled operation")
check(set(operations) == set(receipts), "receipt attribution mismatch")
check(len({row[1] for row in receipts.values()}) == 8, "repeated receipt identity")
exports = {name: load(name + ".json") for name in (
    "p02-prior-nonempty", "p02-prior-empty", "p02-live-raw-history", "p02-live-structured")}
originals = {row["id"]: row["content"]
             for export in exports.values() for row in export["observations"]}
check(load("lesson.json")["support"] == [1], "lesson support changed")
check(load("lesson.json")["opposition"] == [2], "lesson opposition changed")
live_usage = {"input_tokens": 0, "output_tokens": 0}
for name, export in exports.items():
    check(export["state"]["investigation_id"] == name, "investigation identity mismatch")
    observation = export["state"]["last_observation"]
    check(observation["passed"] is (name != "p02-prior-empty"), "reported task outcome changed")
    decision, = export["decisions"]
    data = decision["data"]
    operation = observation["episode"]
    check(data["operation_id"] == operation, "decision/episode mismatch")
    check(operation in receipts and observation["verdict"] in receipts, "missing worker/verifier receipt")
    check(observation["solution"] in packages, "missing solution package")
    snapshot = data["visible_input"]["memory"]
    for source in snapshot["observations"]:
        original = originals[source["observation_id"]]
        check(source["content"]["passed"] is original["passed"], "source outcome mismatch")
        check(source["identities"]["worker_operation_id"] == original["episode"], "source identity mismatch")
        check(all(digest in packages for digest in source["artifacts"]), "missing memory package")
    if name.startswith("p02-live-"):
        check({1, 2}.issubset({x["observation_id"] for x in snapshot["observations"]}), "missing contrary experience")
        usage = episodes[operation][2]
        check(usage == receipts[operation][4]["tokens"], "usage/receipt mismatch")
        for key in live_usage:
            live_usage[key] += usage[key]
check(exports["p02-live-raw-history"]["decisions"][0]["data"]["visible_input"]["memory"]["claims"] == [],
      "raw view contains claims")
claim, = exports["p02-live-structured"]["decisions"][0]["data"]["visible_input"]["memory"]["claims"]
check(claim["claim_id"] == "maximum-rule" and claim["opposition"] == [2], "structured opposition mismatch")
print(json.dumps({"offline_archive_checks": "pass", "packages": len(packages),
                  "settled_operations": len(operations), "live_usage": live_usage}))
