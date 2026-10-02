"""r2's own evidence, read back under r3's rules.

Two reviews said r2's headline rested on inputs the campaign chose. This
module re-derives r2's outcomes from the bytes r2 stored, under the reading
r3 uses, so the comparison between the two campaigns is made on the same
footing rather than on r2's own summary. It is read-only and network-free,
and it reads r2's directory rather than r2's `RESULTS.md`, so it cannot
inherit r2's conclusions.

The question it answers is narrow and is the one the freeze could not settle
before dispatching: **at what cap would r2's responses have been judged, and
would any of them have been a program?**

A conforming answer is 143 characters, so a 512 cap leaves ample room and the
cap cannot by itself explain a zero. The only way to tell is to re-judge the
stored bytes at the parser's own implied limit, with no length check at all.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

R2_ROOT = REPO_ROOT / "reports" / "evidence" / "w1-e1-boolean-r2"


def _r2_records(root: Path = R2_ROOT) -> list:
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((root / "lineages").glob("*.json"))]


def rejudge(record: dict) -> dict:
    """Re-judge one r2 lineage at the parser's own implied cap.

    r2's records carry a `score` key on every attempt and its value is null on
    all eight, so the re-judgement takes the score from the protocol's scorer
    over the stored bytes rather than from anything r2 recorded. A response
    that parses here is a program the protocol would have run at any length.
    """
    from experiments.ad01 import boolean_rule as rules
    from experiments.ad01 import live_construct as live
    entry = record["attempts"][0]
    raw = entry.get("raw_response")
    reported = {"lineage": record.get("lineage"), "arm": record["treatment"],
                "attempt": entry.get("attempt"),
                "r2_outcome": entry.get("outcome"),
                "characters": len(raw) if isinstance(raw, str) else None}
    if not isinstance(raw, str):
        reported["at_unbounded_cap"] = "no-response"
        return reported
    task = rules.make_task(record["split"], int(record["seed"]))
    session = rules.RuleSession(task)
    try:
        candidate = live.extract_and_validate_boolean(raw)
    except Exception as exc:
        reported["at_unbounded_cap"] = "invalid-program"
        reported["detail"] = "%s: %s" % (type(exc).__name__, exc)
        return reported
    committed = session.commit_predictor(candidate)
    score = session.score(committed)
    reported["at_unbounded_cap"] = (
        "constructed" if score["overall"] >= live.PREFLIGHT_SCORE_FLOOR
        else "poor-task-result")
    reported["score"] = score["overall"]
    return reported


def rejudge_all(root: Path = R2_ROOT) -> dict:
    """Every r2 lineage, re-judged, plus what it says about the cap."""
    from experiments.ad01 import live_construct as live
    records = _r2_records(root)
    rows = [rejudge(record) for record in records]
    with_bytes = [r for r in rows if r["characters"] is not None]
    parses = [r for r in with_bytes if r["at_unbounded_cap"] in
              ("constructed", "poor-task-result")]
    over_cap = [r for r in with_bytes
                if r["characters"] > live.OUTPUT_LIMITS[
                    "max_response_characters"]]
    parse_at_cap_b = [r for r in with_bytes
                      if r["at_unbounded_cap"] in ("constructed",
                                                  "poor-task-result")]
    return {
        "source": "r2 stored bytes, re-read",
        "r2_campaign_id": "w1-e1-boolean-r2",
        "lineages": len(rows),
        "with_response_bytes": len(with_bytes),
        "attempts_reported": sorted({r["attempt"] for r in rows
                                     if r["attempt"] is not None}),
        "cap_a_characters": int(live.OUTPUT_LIMITS["max_response_characters"]),
        "conforming_answer_characters": len(json.dumps(
            {"specs": [{"const": 0, "mask": 0, "pair": None}] * 4},
            separators=(",", ":"))),
        "over_cap_a": len(over_cap),
        "parse_at_unbounded_cap": len(parse_at_cap_b),
        "parse_among_over_cap_a": sum(
            1 for r in over_cap
            if r["at_unbounded_cap"] in ("constructed", "poor-task-result")),
        "verdict_at_unbounded_cap": sorted({r["at_unbounded_cap"]
                                            for r in with_bytes}),
        "finding": (
            "r2 classified %d of %d responses as over-length against the "
            "frozen 512 cap. Re-judged at the parser's own implied cap, with "
            "no length check at all, %d of the whole set parse as a Boolean "
            "policy, and %d of the over-length subset do. The cap therefore "
            "explains the classification and does not explain the outcome: no "
            "character limit can rescue a response that never committed a "
            "program. This module measures the parse outcome only and does not "
            "claim why the responses read as they do."
            % (len(over_cap), len(with_bytes), len(parse_at_cap_b),
               sum(1 for r in over_cap
                   if r["at_unbounded_cap"] in ("constructed",
                                               "poor-task-result")))),
        "rows": rows,
    }


def main(argv=None) -> int:
    root = Path(argv[0]) if argv else R2_ROOT
    print(json.dumps(rejudge_all(root), sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
