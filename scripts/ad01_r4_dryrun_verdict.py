"""What the r4 bundle's verdicts will read, from the r3 bytes, before spending.

The r3 run demoted itself twice for reasons that had nothing to do with the
model: the acquisition evidence was re-read from the member's `entry` field
instead of carried, so no arm earned; and the control arm's bound digest is
over its four-member repertoire rather than over the one source any single
record executed. The first is fixed. Whether the second blocks the verdict
is a question about `s09_verdict`, and answering it costs one dictionary
build rather than six live dispatches.

This reconstructs the bundle the driver writes -- the same construction
block, the same identities, the same operations, the same use records -- out
of the committed r3 artifacts, marks the earned arms earned, and runs both
verdicts. What it prints is what the run will print, unless the model
returns something the route has not returned before.

It reads `invl02_liveacq_r3/` and writes nothing.

Run: PYTHONPATH=. python -m scripts.ad01_r4_dryrun_verdict
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

R3 = ROOT / "reports" / "evidence" / "invl02_liveacq_r3"


def build() -> "s09_verdict.Bundle":
    from experiments.ad01 import control_arm, s09_verdict

    arms = json.loads((R3 / "acquired_arms.json").read_text())["arms"]
    operations = json.loads((R3 / "operations.json").read_text())
    records = json.loads((R3 / "use_records.json").read_text())
    freeze = json.loads((R3 / "freeze.json").read_text())
    model = freeze["config"]["model"]

    identities: dict = {}
    construction: dict = {}
    for arm in arms:
        if not arm.get("acquired"):
            continue
        evidence = dict(arm.get("evidence") or {})
        bound = arm["source_digest"]
        construction[arm["arm"]] = {
            "arm": arm["arm"], "task_id": arm["task_id"],
            "family": arm["family"], "campaign_id": arm["campaign_id"],
            "policy_source": arm["policy_source"],
            "candidate_digest": bound, "bound_digest": bound,
            "source_digest": bound,
            "acquisition_evidence": evidence,
            "construction_requests": [{
                "effect": "model-inference", "model": model,
                "operation_id": "ad01-%s-b0-%s-construct-l1-init"
                                % (arm["campaign_id"], arm["task_id"])}],
        }
        if evidence.get("earned") is True:
            identities.update(control_arm.acquisition_identity(
                arm["arm"], [arm["capability_id"]],
                {arm["capability_id"]: bound},
                acquisition_evidence=evidence))
    repertoire = control_arm.control_repertoire("ad01-ctl")
    identities.update(control_arm.policy_identities("C", repertoire))
    # The control has no construction entry in the r3 bundle, so
    # `_comparability_leg` falls back to `arm_policy_digest("C")`, which is
    # the digest of all four member sources concatenated. Each record
    # executed exactly one of them. This is the third question.
    return s09_verdict.Bundle(
        root=R3, freeze={**freeze, "policy_identities": identities},
        construction=construction, operations=operations,
        use_records=tuple(records), accounting={}, assessment=())


def main() -> int:
    from experiments.ad01 import s09_verdict

    bundle = build()
    print("earned acquired arms: %s"
          % (bundle.earned_arms_by_origin(s09_verdict.ORIGIN_ACQUIRED),))
    print("earned authored arms: %s"
          % (bundle.earned_arms_by_origin(s09_verdict.ORIGIN_AUTHORED),))
    for label, verdict in (("live_acquisition",
                            s09_verdict.live_acquisition_verdict(bundle)),
                           ("task_utility",
                            s09_verdict.task_utility_verdict(bundle))):
        print("\n%s = %s" % (label, verdict.value))
        for leg in verdict.legs:
            print("  %-42s %s" % (leg.name, leg.status))
            print("      %s" % leg.evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
