"""Forge the reviewer's surviving forgery and two of my own, then verify.

Run before and after the fix. Every forgery is self-consistent: where the
digest chain covers a field, the chain is recomputed over the forged field,
so the only thing standing between the forgery and a clean pass is the
verifier re-deriving a claim from the bytes.

    uv run python scripts/w5_forgery_probe.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import frontier  # noqa: E402
from experiments.ad01 import live_construct as live  # noqa: E402
from experiments.ad01 import w1_e1_campaign_r2 as r2  # noqa: E402

EVIDENCE = ROOT / "reports" / "evidence" / r2.CAMPAIGN_ID


def _reseal(record: dict) -> dict:
    """Recompute every digest that covers the bytes I am forging.

    A forger who cannot recompute the chain is caught by the chain, which
    proves the chain works and nothing about whether the record tells the
    truth. So each forgery here pays that cost in full -- response digest,
    payload digest, identity digest -- and is still caught or not. A
    forgery caught by its own arithmetic would demonstrate nothing about
    whether a claim is re-derived.
    """
    for entry in record.get("attempts", []):
        dispatch = entry.get("dispatch")
        if not isinstance(dispatch, dict):
            continue
        raw = entry.get("raw_response")
        dispatch["raw_response"] = raw
        details = dispatch.get("details")
        if isinstance(details, dict):
            payload = details.get("raw_payload")
            if isinstance(payload, dict):
                payload["raw_response"] = raw
        if raw is not None:
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            dispatch["response_digest"] = digest
            dispatch["result_digest"] = digest
        dispatch["raw_payload_digest"] = frontier._digest_text(
            frontier.canonical(
                (dispatch.get("details") or {}).get("raw_payload")))
        dispatch["route_digest"] = frontier._digest_text(
            frontier.canonical((dispatch.get("details") or {}).get("route")))
        dispatch["evidence_digest"] = frontier._evidence_identity_digest(
            dispatch)
    return record


def _answered(root: Path, reason_contains: str | None = None) -> Path:
    for path in sorted((root / "lineages").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        entry = record["attempts"][0]
        if not record.get("offline_verified"):
            continue
        if reason_contains and reason_contains not in str(entry.get("reason")):
            continue
        return path
    raise AssertionError("no answered lineage found")


# --- the three forgeries -------------------------------------------------


def forge_reviewer(root: Path) -> tuple[str, str]:
    """Swap 5211 bytes for a short unparseable one, keep the 5211 claim.

    The bytes no longer parse, so `verify_preflight_record`'s disjunction
    holds and the record is internally consistent. The `reason` string was
    never recomputed, so it still stated a length fact about bytes that
    were no longer there.
    """
    path = _answered(root, "exceeds the frozen limit")
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = record["attempts"][0]
    forged = ('{"specs": [{"const": 0, "mask": 99, "pair": null}, '
              '{"const": 0, "mask": 0, "pair": null}, '
              '{"const": 0, "mask": 0, "pair": null}, '
              '{"const": 0, "mask": 0, "pair": null}]}')
    entry["raw_response"] = forged
    entry["dispatch"]["parse_outcome"] = "parse-failed"
    _reseal(record)
    path.write_text(json.dumps(record, sort_keys=True, indent=1),
                    encoding="utf-8")
    return path.name, "%d bytes claiming 5211 characters" % len(forged)


def forge_mine(root: Path) -> tuple[str, str]:
    """Manufact an acquisition out of an over-length reply.

    A different forgery, and a cheaper one: the real 5211 bytes stay
    exactly as the gateway sent them, no digest is touched, and the entry
    simply acquires a `candidate_digest` and a perfect `score`. Nothing in
    the digest chain covers those two fields, and nothing re-derives them,
    so `summarize` reads one unique source program and a max score of 1.0
    out of a lineage that never emitted a program at all.

    The three-count collapse -- 8 records, 0 programs -- is the finding the
    E1 r2 handback rests on, and this is the forgery that turns it into
    "8 records, 1 program, max 1.0".
    """
    path = _answered(root, "exceeds the frozen limit")
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = record["attempts"][0]
    entry["candidate_digest"] = live.source_digest(
        json.dumps({"specs": []}, sort_keys=True, separators=(",", ":")))
    entry["score"] = {"overall": 1.0}
    path.write_text(json.dumps(record, sort_keys=True, indent=1),
                    encoding="utf-8")
    return path.name, "score.overall=1.0 with a candidate_digest"


def forge_mine_second(root: Path) -> tuple[str, str]:
    """Restate a gateway observation the verdict is not allowed to restate.

    `stop_reason: length` is what the campaign's own results table prints
    and what the whole over-length finding names. It is an observation
    from the gateway, so the verifier's job is not to re-derive it but to
    refuse a record whose narrative column disagrees with its dispatch
    evidence. Nothing compares the two, so `stop_reason: stop` -- the
    model answered cleanly and stopped -- verifies clean.
    """
    path = _answered(root, "exceeds the frozen limit")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["verdict"]["stop_reason"] = "stop"
    path.write_text(json.dumps(record, sort_keys=True, indent=1),
                    encoding="utf-8")
    return path.name, "verdict.stop_reason length -> stop"


def forge_mine_third(root: Path) -> tuple[str, str]:
    """Overstate a construction that never happened, and call it a route refusal.

    The only lineages in this campaign with a recorded route failure are
    the two 502s, and the batch's headline claim is that the route repair
    held -- `route_error: None` on every answered dispatch. So relabelling
    an over-length `invalid-program` as a `route-refusal` is the forgery
    that would let a reader believe the repair had failed and the E1
    finding were a harness fact after all, exactly as r1's was. The bytes
    are untouched, so no digest is touched, and the reason is then
    restated to match the story.
    """
    path = _answered(root, "exceeds the frozen limit")
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = record["attempts"][0]
    entry["outcome"] = "route-refusal"
    entry["reason"] = "returned route metadata does not match the frozen route"
    record["verdict"]["outcome"] = "route-refusal"
    record["verdict"]["reason"] = entry["reason"]
    path.write_text(json.dumps(record, sort_keys=True, indent=1),
                    encoding="utf-8")
    return path.name, "invalid-program relabelled route-refusal"


def forge_mine_fourth(root: Path) -> tuple[str, str]:
    """Claim the unspent second attempt settled the task.

    The protocol supports `attempt in (1, 2)` and the freeze recorded
    `repairs_planned: 0`, so a record that claims the second attempt ran
    and constructed is a claim about a dispatch that the exposure ledger
    says was never made. `attempt` is in the entry and in the verdict and
    nowhere in the dispatch evidence, so nothing before this fix re-derived
    it: a forger could report attempt 2 of a campaign that spent one.
    """
    path = _answered(root, "exceeds the frozen limit")
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = record["attempts"][0]
    entry["attempt"] = 2
    record["verdict"]["attempt"] = 2
    path.write_text(json.dumps(record, sort_keys=True, indent=1),
                    encoding="utf-8")
    return path.name, "attempt 1 restated as 2"


FORGERIES = (
    ("reviewer: 168 bytes claiming 5211", forge_reviewer),
    ("mine: an acquisition forged onto an over-length reply", forge_mine),
    ("mine: verdict.stop_reason restated", forge_mine_second),
    ("mine: over-length relabelled route-refusal", forge_mine_third),
    ("mine: attempt 1 restated as 2", forge_mine_fourth),
)


def main() -> int:
    print("baseline (untouched run directory)")
    clean = r2.verify(EVIDENCE)
    print("  checked=%d passed=%d failures=%d network_withdrawn=%s"
          % (clean["checked"], clean["passed"], len(clean["failures"]),
             clean["network_withdrawn"]))
    print()

    import tempfile
    caught = 0
    for label, forge in FORGERIES:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / "forged"
            shutil.copytree(EVIDENCE, root)
            target, detail = forge(root)
            outcome = r2.verify(root)
            summary = r2.summarize(root)
            verdicts = [v for cell in summary["cells"]
                        for v in cell["verdicts"] if v["lineage"] == target]
            counts = summary["counts"]
            failures = [f for f in outcome["failures"]
                        if f["record"] == target]
            passed = not failures
            caught += 0 if passed else 1
            print(label)
            print("  target            %s (%s)" % (target, detail))
            print("  verify failures   %d %s"
                  % (len(failures),
                     json.dumps(failures[:2]) if failures else ""))
            print("  summarize counts  construction_events=%d "
                  "unique_source_programs=%d retained_artifact_records=%d"
                  % (counts["construction_events"],
                     counts["unique_source_programs"],
                     counts["retained_artifact_records"]))
            if verdicts:
                print("  reported reason   %s" % verdicts[0]["reason"])
                print("  reported chars    %s  stop_reason %s  score %s"
                      % (verdicts[0]["response_characters"],
                         verdicts[0]["stop_reason"], verdicts[0]["score"]))
            print("  VERDICT           %s"
                  % ("FORGERY ACCEPTED" if passed else "caught"))
            print()
    print("%d of %d forgeries accepted" % (len(FORGERIES) - caught,
                                           len(FORGERIES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
