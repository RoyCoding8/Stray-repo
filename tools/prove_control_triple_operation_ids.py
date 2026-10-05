"""May two arms of the triple share one operation id, and when?

`preserved` and `refuted` are handed lists that differ only in the LAST
recorded verdict. On the E0 freeze the second probe has already earned
`not_preserved`, so the rewrite is a no-op, the two lists are equal, and the
two arms are the same question. Their views are identical, so they derive the
same operation id -- and under one shared allocation the second reads the
first's settled receipt instead of executing.

That is correct, and it is the executor's designed idempotence: identical
source bytes, identical view, identical state, so the read-back IS the
re-execution rather than a substitute for it. Before the authority was threaded
it could not happen, because each choice settled on its own disposable database
and a fresh id space.

The invariant that matters is the other direction, and it is the one this tool
checks. Two arms handed DIFFERENT evidence must derive DIFFERENT ids, or the
second reports the first's choice and the comparison is a restatement of one
arm. If they share an id while their evidence differs, that is the defect: a
measurement that cannot tell it reused a receipt.

So the check is not "three distinct ids". It is "distinct ids exactly when the
evidence differs".

    python tools/prove_control_triple_operation_ids.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in ("", "src", "scripts"):
    sys.path.insert(0, str(ROOT / extra) if extra else str(ROOT))

from experiments.ad01 import boolean_rule as _rules  # noqa: E402
from experiments.ad01 import improve_channel as _channel  # noqa: E402
from experiments.ad01 import live_construct as _live  # noqa: E402


def build(tmp: Path):
    """A store holding recorded evidence, so the triple's refuted arm exists.

    With an empty store the triple collapses all three arms onto the
    disconnected one by its own documented rule, which would make every check
    here pass vacuously.
    """
    task = _rules.make_task("dev", 4)
    store = _live.ensure_live_store(
        str(tmp / "store.json"),
        {"objective": _live.LIVE_MISSION_OBJECTIVE,
         "environments": [{"instrument": "boolean-rule-v1", "split": "dev",
                           "seed": 4}]},
        dict(_live.LIVE_AUTHORITY))
    for oid, x in (("opp-first", 3), ("opp-extra", 5)):
        _live.propose_live_work(store, [{
            "opportunity_id": oid,
            "mission_link": _live.LIVE_MISSION_OBJECTIVE,
            "question": "what does input %d reveal" % x,
            "intervention": {"instrument": "boolean-rule-v1",
                             "target": "rule-dev-0004", "inputs": {"x": x}},
            "resources": {"queries": 1, "steps": 1}}])
    package = _live.bind_live_control(store, "low")
    for oid, x in (("opp-first", 3), ("opp-extra", 5)):
        _live.execute_chosen_work(store, {
            "kind": "probe", "inputs": {"opportunity_id": oid, "x": x},
            "requested_resources": {"queries": 1, "steps": 1}}, task)
    return store, package


def operation_id(package: dict, experience: list, arm: str) -> str:
    """The id `choose_next_work` -> `run_operate_step` derives for one arm.

    `choose_next_work` builds the view from `store.step_view` and replaces only
    `view["experience"]` (`live_construct.py:1230-1231`), so two arms of one
    triple differ in the experience list and in nothing else.
    """
    return _channel._derived_operation_id(
        package, "op", {"experience": list(experience)}, arm=arm)


def main() -> int:
    failures = []
    with tempfile.TemporaryDirectory() as raw:
        store, package = build(Path(raw))
        recorded = store.observations
        # The refuted arm as `_control_triple` builds it.
        refuted = [dict(o) for o in recorded]
        refuted[-1] = {**refuted[-1], "verdict": _channel.NOT_PRESERVED}
        last_verdict = recorded[-1].get("verdict")
        rewrite_is_noop = refuted == recorded
        print("recorded observations      : %d" % (len(recorded),))
        print("last recorded verdict      : %s" % (last_verdict,))
        print("rewrite to %-14s: %s"
              % (_channel.NOT_PRESERVED,
                 "a no-op, so preserved and refuted are one question"
                 if rewrite_is_noop else "changes the evidence"))

        for label in ("control", "live", "P1"):
            ids = {
                "preserved": operation_id(package, recorded, label),
                "refuted": operation_id(package, refuted, label),
                "disconnected": operation_id(package, [], label),
            }
            # The rule: an id is shared exactly when the evidence is equal.
            evidence = {"preserved": recorded, "refuted": refuted,
                        "disconnected": []}
            names = sorted(ids)
            for i, left in enumerate(names):
                for right in names[i + 1:]:
                    same_id = ids[left] == ids[right]
                    same_evidence = evidence[left] == evidence[right]
                    verdict = "OK" if same_id == same_evidence else "FAIL"
                    if same_id and same_evidence:
                        why = ("one question, so one receipt is the answer"
                               " rather than a substitute for it")
                    elif not same_id and not same_evidence:
                        why = "different evidence, so both execute"
                    elif same_id:
                        why = ("SAME ID ON DIFFERENT EVIDENCE: the second reads"
                               " the first's receipt and reports its choice")
                    else:
                        why = "same evidence, two executions: wasted, not wrong"
                    print("%-8s %-13s %-13s %s  %s"
                          % (label, left, right, verdict, why))
                    if verdict == "FAIL":
                        failures.append((label, left, right))

        # The load-bearing one, stated on its own: the disconnected arm passes
        # no evidence and must not share an id with an arm that has some,
        # because that is the comparison `observation_dependent` is built from.
        for label in ("control", "live", "P1"):
            same = (operation_id(package, [], label)
                    == operation_id(package, recorded, label))
            print("disconnected vs preserved under %-8s: %s"
                  % (label, "COLLIDE (defect)" if same else "distinct"))
            if same:
                failures.append((label, "disconnected", "preserved"))

        # And the arm still separates ids, or two arms of one study would
        # share one operation and the second would read the first's.
        arm_ids = {operation_id(package, recorded, label)
                   for label in ("control", "live", "P1")}
        print("distinct operation ids across arms: %d of 3"
              % (len(arm_ids),))
        if len(arm_ids) != 3:
            failures.append(("all", "control", "live"))

    if failures:
        print("\nFAIL: %d pair(s) share an id on differing evidence or an arm "
              "failed to separate" % (len(failures),))
        return 1
    print("\nOK: an operation id is shared exactly when the evidence is equal. "
          "Where preserved and refuted coincide it is because the rewrite is a "
          "no-op and they are one question, which is the E0 freeze and is why "
          "`falsifier_moves_decision` reads False there. Where evidence "
          "differs, every arm executes and reports its own choice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())