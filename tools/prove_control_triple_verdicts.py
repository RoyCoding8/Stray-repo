"""Does sharing an operation id change the reported verdict? Measured.

`_control_triple`'s `preserved` and `refuted` arms derive the same operation id
exactly when the rewrite is a no-op, because their views are then equal. Under
one shared allocation the second reads the first's settled receipt instead of
executing. That is the executor's designed idempotence, and it is sound only if
equal evidence means equal bytes means an equal answer.

The field at risk is `falsifier_moves_decision`, computed from
`choices["preserved"]["choice"] != choices["refuted"]["choice"]
(`invl02_live.py:2250-2251`). If the rewrite is a no-op the two evidence lists
are equal, so the field reads False -- which the E0 freeze already asserts. The
question this tool answers is whether it reads False for the RIGHT reason there,
or whether the shared id is quietly doing the work.

The right reason is that the rewrite could not move the decision. The wrong one
is that the second arm was skipped and reported the first's answer. They are
indistinguishable from the verdict alone, so this sweeps the second probe's
input and reports both, per input: whether the rewrite moves the evidence, and
whether the two arms share an operation id.

    python tools/prove_control_triple_verdicts.py

The store is built exactly as `_run_frontier_investigation` builds it -- the
shipped `freeze_e0` and the shipped `_live_opportunities(freeze)` -- and the
two probes are the shipped ones at `opp-rule-dev-4` x=3 and
`invl02_live.SECOND_PROBE_X`. What is NOT exercised is the out-of-process
dispatch and the durable receipt, which need a PostgreSQL this harness
deliberately does not stand up; `tests/test_operate_step_authority.py` proves
those against a real database. What is exercised here is everything that
decides the choice: the shipped op_source bytes, the shipped `step_view`, the
shipped `validate_view` and `validate_operate_action`, and the shipped
`_control_triple` arithmetic.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in ("", "src", "scripts"):
    sys.path.insert(0, str(ROOT / extra) if extra else str(ROOT))

from experiments.ad01 import boolean_rule as _rules  # noqa: E402
from experiments.ad01 import frontier as _frontier  # noqa: E402
from experiments.ad01 import improve_channel as _channel  # noqa: E402
from experiments.ad01 import live_construct as _live  # noqa: E402
from scripts import invl02_live as _driver  # noqa: E402

NOT_PRESERVED = _channel.NOT_PRESERVED
FIRST_OPPORTUNITY = "opp-rule-dev-4"
FIRST_X = 3


def run_op_source(store, package: dict, experience: list):
    """The operate source's own answer, from the shipped bytes and view.

    `run_operate_step` builds the view through `store.step_view`, replaces only
    `view["experience"]` (`live_construct.py:1230-1231`), validates the view,
    dispatches `op_source` out of process, and validates the returned action.
    The `opportunity_id` that action carries is the choice, and the shipped
    bytes produce it identically here over the shipped view. A hand-built view
    is what makes this go wrong: it is missing the keys the source reads.
    """
    view = store.step_view(_frontier.OPERATE, package)
    view["experience"] = list(experience)
    _frontier.validate_view(view)
    namespace: dict = {}
    exec(compile(package["op_source"], "<op_source>", "exec"), namespace)
    action = _channel._unwrap(namespace["STEP"](view, {})["action"])
    action = _frontier.validate_operate_action(action)
    # `choose_next_work` reads the choice as `action["inputs"]["opportunity_id"]`
    # (`live_construct.py:1240`), so an action without one carries no choice
    # rather than raising. A `stop` lands here.
    return action.get("inputs", {}).get("opportunity_id")


def build(tmp: Path, second_x: int):
    """The E0 store, exactly as `_run_frontier_investigation` builds it.

    `ensure_live_store` is called with no `dsn`, which is the fixture boundary
    that file already names. The opportunities are the shipped ones, so the
    frontier holds members on more than one task -- which is what lets the
    operate source answer a non-target alternative when the last observation
    refuted its target (`improve_channel.SHARED_OPERATE_SOURCE`).
    """
    freeze = _driver.freeze_e0(tmp / ("freeze-%s" % second_x))
    store = _live.ensure_live_store(
        str(tmp / ("frontier-%s.json" % second_x)),
        {"objective": _live.LIVE_MISSION_OBJECTIVE,
         "environments": _driver._live_environments(freeze)},
        dict(_live.LIVE_AUTHORITY))
    _live.propose_live_work(store, _driver._live_opportunities(freeze))
    package = _live.bind_live_control(store, "low")
    task = _rules.make_task("dev", 4)

    def probe(opportunity_id: str, x: int):
        return _live.execute_chosen_work(store, {
            "kind": "probe",
            "inputs": {"opportunity_id": opportunity_id, "x": x},
            "requested_resources": {"queries": 1, "steps": 1}}, task)

    probe(FIRST_OPPORTUNITY, FIRST_X)
    probe(_driver.SECOND_PROBE_OPPORTUNITY, second_x)
    return store, package


def measure(tmp: Path, second_x: int, label: str) -> dict:
    """One second input: the earned verdict, the ids, and both fields."""
    store, package = build(tmp, second_x)
    recorded = store.observations
    refuted = [dict(o) for o in recorded]
    refuted[-1] = {**refuted[-1], "verdict": NOT_PRESERVED}
    ids = {name: _channel._derived_operation_id(
        package, "op", {"experience": exp}, arm=label)
        for name, exp in (("preserved", recorded),
                          ("refuted", refuted),
                          ("disconnected", []))}
    choices = {
        "preserved": run_op_source(store, package, recorded),
        "refuted": run_op_source(store, package, refuted),
        "disconnected": run_op_source(store, package, []),
    }
    return {
        "second_x": second_x,
        "earned_verdict": recorded[-1].get("verdict") if recorded else None,
        "rewrite_moves_evidence": refuted != recorded,
        "preserved_refuted_share_an_id": ids["preserved"] == ids["refuted"],
        "disconnected_shares_with_preserved":
            ids["disconnected"] == ids["preserved"],
        "observation_dependent": (choices["preserved"]
                                  != choices["disconnected"]),
        "falsifier_moves_decision": (choices["preserved"]
                                     != choices["refuted"]),
        "choices": choices,
    }


def main() -> int:
    failures = []
    rows = []
    print("%-4s %-14s %-7s %-7s %-7s %-7s  choices"
          % ("x", "earned", "rewrite", "shared?", "obsdep", "falsifier"))
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        for second_x in range(_rules.N_STATES):
            row = measure(tmp, second_x, "control")
            rows.append(row)
            print("%-4s %-14s %-7s %-7s %-7s %-7s  %s"
                  % (row["second_x"], row["earned_verdict"],
                     row["rewrite_moves_evidence"],
                     row["preserved_refuted_share_an_id"],
                     row["observation_dependent"],
                     row["falsifier_moves_decision"],
                     row["choices"]))
            # The invariant: an operation id is shared exactly when the evidence
            # is equal. Sharing on DIFFERING evidence would make the falsifier
            # read False because it reused a receipt rather than because the
            # rewrite could not move anything -- the one failure this closes.
            if row["preserved_refuted_share_an_id"] != \
                    (not row["rewrite_moves_evidence"]):
                failures.append(
                    "x=%s shares an id=%s while the rewrite moves evidence=%s"
                    % (row["second_x"],
                       row["preserved_refuted_share_an_id"],
                       row["rewrite_moves_evidence"]))
            if row["disconnected_shares_with_preserved"]:
                failures.append(
                    "x=%s: the disconnected arm shares an operation id with "
                    "the preserved arm, so `observation_dependent` would "
                    "compare a receipt against itself" % (row["second_x"],))

    observed_true = [r for r in rows if r["observation_dependent"]]
    falsifier_true = [r for r in rows if r["falsifier_moves_decision"]]
    print("\nobservation_dependent True on %d of %d second inputs"
          % (len(observed_true), len(rows)))
    print("falsifier_moves_decision True on %d of %d second inputs"
          % (len(falsifier_true), len(rows)))
    load_bearing = [r for r in rows if r["rewrite_moves_evidence"]]
    print("the rewrite moves the evidence on %d of %d"
          % (len(load_bearing), len(rows)))
    if load_bearing:
        print("  at x=%s"
              % ([r["second_x"] for r in load_bearing],))
    for row in load_bearing:
        print("    x=%s earned=%s falsifier_moves_decision=%s"
              % (row["second_x"], row["earned_verdict"],
                 row["falsifier_moves_decision"]))
        if not row["falsifier_moves_decision"]:
            failures.append(
                "x=%s: the rewrite moved the evidence and yet the falsifier "
                "did not move the decision; if the arms shared an id here it "
                "would be reading a receipt" % (row["second_x"],))
    e0_row = next((r for r in rows
                   if r["second_x"] == _driver.SECOND_PROBE_X), None)
    if e0_row is None:
        failures.append("the E0 second input was not measured")
    elif not (e0_row["observation_dependent"]
              and not e0_row["falsifier_moves_decision"]):
        failures.append(
            "the E0 input reads obs_dep=%s falsifier=%s; the pinned gates "
            "expect True and False"
            % (e0_row["observation_dependent"],
               e0_row["falsifier_moves_decision"]))

    if failures:
        print("\nFAIL:")
        for item in failures:
            print("  - %s" % (item,))
        return 1
    print("\nOK: an operation id is shared exactly when the evidence is equal, "
          "so no arm reports another's choice. Where `falsifier_moves_decision` "
          "reads False it is because the rewrite writes a verdict the run had "
          "already earned, which is the reason the pinned gates give -- not "
          "because the second arm was skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())