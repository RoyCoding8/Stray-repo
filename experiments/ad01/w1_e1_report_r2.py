"""Print the r2 campaign's tables from its written directory, offline.

Read-only. The gateway is withdrawn first, so if any code path reached for
one this would raise rather than quietly succeed. Every number below comes
from `campaign.json` or from the lineage records; nothing is recomputed
from a live call.

    uv run python -m experiments.ad01.w1_e1_campaign_r2 report
"""

from __future__ import annotations

import json
from pathlib import Path

from . import w1_e1_campaign_r2 as r2


def build(root: Path) -> dict:
    from experiments.ad01 import live_construct as live
    withdrawn = live.LiveGuard.infer
    live.LiveGuard.infer = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("report reached for a gateway"))
    try:
        campaign = r2.summarize(root)
        verification = r2.verify(root)
    finally:
        live.LiveGuard.infer = withdrawn
    baseline = campaign.get("authored_baseline")
    if baseline is None:
        baseline = r2.authored_baseline()

    rows = []
    for cell in campaign["cells"]:
        for verdict in cell["verdicts"]:
            rows.append({
                "lineage": verdict["lineage"],
                "treatment": cell["treatment"],
                "outcome": verdict["outcome"],
                "defect": verdict.get("invalid_program_defect"),
                "characters": verdict.get("response_characters"),
                "stop_reason": verdict.get("stop_reason"),
                "score": verdict.get("score"),
                "provider": verdict.get("provider"),
                "tier": verdict.get("tier"),
                "operation_id": verdict.get("operation_id"),
            })
    return {
        "campaign_id": campaign["campaign_id"],
        "offline": True,
        "counts": campaign["counts"],
        "score_floor": campaign["score_floor"],
        "reference_scores": campaign["reference_scores"],
        "exposure": campaign["exposure"],
        "per_treatment": [
            {"treatment": cell["treatment"],
             "lineages_run": cell["lineages_run"],
             "verified_offline": cell["verified_offline"],
             "outcomes": {k: v for k, v in cell["outcomes"].items() if v},
             "construction_events": cell["construction_events"],
             "unique_source_programs": cell["distinct_behaviours"],
             "score_distribution": cell["score_distribution"],
             "at_or_above_floor": cell["at_or_above_floor"]}
            for cell in campaign["cells"]],
        "lineages": rows,
        "authored_baseline": baseline,
        "verification": verification,
    }


def main() -> int:
    root = r2.REPO_ROOT / "reports" / "evidence" / r2.CAMPAIGN_ID
    print(json.dumps(build(root), sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
