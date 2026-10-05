"""M4's comparison apparatus, measured offline, and its honest stopping rule.

`WORKER-PROMPT.md:119-134` asks for two different things and the difference
matters more than either. The first is an executable acquisition decision
qualified with effectful, no-op and disconnected controls from identical
starting conditions, where the effectful control changes the next
descendant-producing episode after restart. The second is a benefit
comparison between a parent learner and a revised one on fresh acquisition
episodes.

The first is reachable without a model and without a database. This harness
measures it. The second needs a live route and, more importantly, needs
headroom that does not currently exist. The harness measures that too, and
refuses to build the second from the first.

Two boundaries are drawn by execution rather than by reading, and both were
established by running the tree at `9c73b149`:

- Every eligibility gate except gate 6 runs with no database. Gate 6 is
  `delegates_to_frozen_reducer`, which executes revision bytes under real
  authority through `improve_channel._execution_ledger`, and that opens a
  disposable PostgreSQL. So the offline claim covers five of six gates, and
  `GATES_NEEDING_A_DATABASE` says which. `m4-eligibility.md:303-319` recorded
  the same five-by-one split and left gate 6 unexecuted for the same reason.
- `drive_improve_round` needs a database for the same reason. So the decision
  is executed here directly from the bytes, in a separate process, against the
  persisted store, and the descendant is scored by the frozen evaluator on the
  independent `audit` split. That is a measurement of the mechanism, and it is
  labelled as such rather than as an acquired arm.

What this harness will not do is score two arms that are the same thing.
`NOISE_FLOOR_Z` is the bar: a delta whose paired z does not clear it on the
frozen cohort is a difference the cohort itself produces, and a comparison
built on it is a table of noise. `panels()` returns nothing when no input
clears the bar, and the artifact says why.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import boolean_rule as _rules
from experiments.ad01 import channel_controls as _controls
from experiments.ad01 import frontier as _frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import learner_revision as lr

# The freeze this apparatus measures under. It is read from the module rather
# than written here, because a harness that pins its own copy is a second
# authority that can drift from the one the run uses. `run_version` in the
# artifact is the value the acquisition would run under, and an arm acquired
# under a different one is not comparable with anything here.
RUN_VERSION = lr.RUN_VERSION

# The independent tasks. The decision is made on `dev`, so scoring on `audit`
# keeps acquisition and assessment apart, which is the same split discipline
# the rest of the file uses.
ASSESS_SPLIT = "audit"

# The frozen cohort. Sized by `channel_controls.COHORT`'s successor and held
# fixed, because a cohort chosen after seeing the deltas is a cohort that can
# be made to agree with them.
COHORT = list(range(1, 151))

# The bar a delta must clear before two arms are worth calling different.
# 1.96 is the two-sided 5% point and is written here as a number rather than
# imported so that the threshold is a decision of this apparatus, visible in
# one place, rather than a constant buried in a helper.
NOISE_FLOOR_Z = 1.96

# The gates that cannot be executed without a database, named rather than
# described. `classify_revision` opens a disposable PostgreSQL through
# `_execution_ledger` before it can ask the delegation question, so a caller
# without one gets no verdict rather than a partial one.
GATES_NEEDING_A_DATABASE = ("delegates-to-unchanged-reducer",)

# The expression the effectful arm is built from. It is written here because
# the harness has to be runnable, and it is pinned against the prompt by
# `tests/test_m4_mechanism_offline.py`, which asserts the current prompt
# offers this exact expression. That pairing is what keeps the measurement
# honest: an arm the acquisition would never produce does not get a run
# version attached to it.
EFFECTFUL_EXPRESSION = '(len(view.get("experience", [])) or 12)'

# The prompt as it stood when E4 dispatched its six replies. Held here so the
# negative test has the same bytes the failure was recorded against rather
# than a paraphrase of them.
BROKEN_USER_TEMPLATE = """\
Rewrite the agent's improvement step so it chooses which input to probe.

The only thing you may change is the `x` in the probe action below. Emit the
whole function, unchanged except for that one integer.

```python
{template}
```

The integer must satisfy 0 <= x < 16. It must be computed from the view or
the state, never written as a constant. Reply with the function only. Start
your reply with ```python and end it with ```."""

# The view the decision is made on, built by the module that builds it for the
# real run, so the harness does not hold a second copy of the admission view.
def _admission_view(workdir: Path) -> dict:
    return lr._admission_views(workdir)[0]


# --- executing a revision's decision, with no database ----------------------

def execute_decision(source: str, view: dict) -> dict:
    """Run revision bytes and read the integer they name.

    The bytes are compiled and called in this process rather than through
    `drive_improve_round`, which needs a database the harness does not have
    and must not fake. What comes back is the decision itself, read off the
    action the source returns, which is the thing the acquisition is under
    study. The executed bytes are recorded alongside it because a decision
    that is not traceable to the bytes that made it is a decision with no
    provenance.
    """
    namespace: dict = {}
    exec(compile(source, "<revision>", "exec"), namespace)  # noqa: S102
    step = namespace["STEP"](dict(view), {})
    action = step["action"]["inputs"]["frontier_action"]
    return {"x": action["inputs"]["x"],
            "kind": action["kind"],
            "requested_resources": action.get("requested_resources"),
            "executed_bytes_digest": _frontier.source_digest(source)}


def _restart_probe(store_path: Path) -> dict:
    """Reopen the persisted store in a second process and read the decision.

    `WORKER-PROMPT.md:124-125` requires the effectful control to change the
    next descendant-producing episode *after restart*, so proving persistence
    means writing the store, leaving this process, and reading it back from a
    fresh interpreter. An in-process read would prove the store is a dict, not
    that the revision survives the round trip.
    """
    program = (
        "import json, sys\n"
        "sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "from experiments.ad01 import frontier as fr\n"
        "store = fr.FrontierStore(%r)\n"
        "package = store.active_package\n"
        "namespace = {}\n"
        "exec(compile(package['imp_source'], '<restarted>', 'exec'),"
        " namespace)\n"
        "step = namespace['STEP']({'experience': [], 'round': 1,"
        " 'frontier': [], 'step': 0}, {})\n"
        "action = step['action']['inputs']['frontier_action']\n"
        "print(json.dumps({'x': action['inputs']['x'],"
        " 'environment': store._doc['environments'][0],"
        " 'imp_digest': package['imp_digest']}))\n"
    ) % (str(ROOT), str(ROOT / "src"), str(store_path))
    completed = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True,
        timeout=120)
    if completed.returncode != 0:
        return {"restarted": False, "error": completed.stderr[-400:]}
    return {"restarted": True, **json.loads(completed.stdout)}


# --- the four controls, from identical starting conditions ------------------

def adopt(source: str, workdir: Path, control_id: str) -> dict:
    """Bind the incumbent, adopt `source` over it, and report the frozen state.

    Every arm in this harness starts here, with the same parent, the same
    mission and the same authority. The frozen digest is taken on both sides
    of the adoption because adoption is the only step a revision is close
    enough to the authority to touch it.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    store = _frontier.create_store(
        workdir / "store", namespace=_frontier.NAMESPACE,
        mission=lr._mission(), authority={"queries": 16, "steps": 12})
    parent = channel.make_control("low")
    store.bind_active(parent)
    before = lr.frozen_state_digest(store)
    store.adopt_revision(
        lr.revision_package(source, parent, control_id))
    after = lr.frozen_state_digest(store)
    lr.check_frozen(before, after)
    return {"frozen_before": before, "frozen_after": after,
            "frozen_unchanged": before == after,
            "imp_digest": store.active_package["imp_digest"]}


def in_range(x: int) -> bool:
    return isinstance(x, int) and 0 <= x < _rules.N_STATES


def _control_arm(role: str, workdir: Path) -> dict:
    control = _controls.build_control(role)
    adopted = adopt(control["source"], workdir, control["control_id"])
    decision = execute_decision(control["source"],
                                 _admission_view(workdir))
    record = {
        "role": role,
        "control_id": control["control_id"],
        "label": control["label"],
        "source_digest": _frontier.source_digest(control["source"]),
        "declared_x_under_revision": control["x_under_revision"],
        "executed_x": decision["x"],
        "executed_bytes_digest": decision["executed_bytes_digest"],
        "expects_changed_decision": control["expects_changed_decision"],
        "in_instrument_range": in_range(decision["x"]),
        "frozen_unchanged": adopted["frozen_unchanged"],
        "adopted_imp_digest": adopted["imp_digest"],
        "known_effect": control["known_effect"],
    }
    if not record["in_instrument_range"]:
        # The disconnect's outcome is a refusal at the instrument's own range
        # check, and the refusal is reproduced here rather than described.
        try:
            _rules.execute_predictor({"specs": [0, 0, 0, 0]}, decision["x"])
            record["refused_by_instrument"] = False
        except _rules.RuleRefused as exc:
            record["refused_by_instrument"] = True
            record["refusal"] = str(exc)
        record["descendant_built"] = False
    else:
        record["refused_by_instrument"] = False
        record["descendant_built"] = True
    return record


def effectful_arm(workdir: Path) -> dict:
    """The eligible constructed revision, driven like every other arm.

    The expression is the one `m4-eligibility.md:130-141` names as
    constructible and gate-passing. It reads the view, so it is a decision
    rather than a constant, and it names 12 when the experience is empty, so
    it is not the frozen reducer's choice.
    """
    source = channel._revision_source(EFFECTFUL_EXPRESSION)
    adopted = adopt(source, workdir, "authored-eligible-x12")
    decision = execute_decision(source, _admission_view(workdir))
    return {
        "role": "effectful",
        "control_id": "authored-eligible-x12",
        "label": _controls.AUTHORED,
        "source_digest": _frontier.source_digest(source),
        "expression": EFFECTFUL_EXPRESSION,
        "declared_x_under_revision": 12,
        "executed_x": decision["x"],
        "executed_bytes_digest": decision["executed_bytes_digest"],
        "expects_changed_decision": True,
        "in_instrument_range": in_range(decision["x"]),
        "frozen_unchanged": adopted["frozen_unchanged"],
        "adopted_imp_digest": adopted["imp_digest"],
        "descendant_built": True,
        "refused_by_instrument": False,
        "known_effect": (
            "Reads the view and names 12 where the incumbent names 3, so the "
            "descendant the next episode builds is a different one. The size "
            "of the difference is a property of the substrate, measured "
            "below, and not of the revision."),
    }


def controls_and_effectful(workdir: Path) -> dict:
    """Every arm from one starting condition, incumbent beside them."""
    incumbent_source = channel.IMPROVE_LOW_SOURCE
    incumbent_x = execute_decision(
        incumbent_source, _admission_view(workdir))["x"]
    incumbent = {
        "role": "incumbent",
        "control_id": "incumbent-low",
        "label": "incumbent",
        "source_digest": _frontier.source_digest(incumbent_source),
        "declared_x_under_revision": incumbent_x,
        "executed_x": incumbent_x,
        "executed_bytes_digest": _frontier.source_digest(incumbent_source),
        "expects_changed_decision": False,
        "in_instrument_range": in_range(incumbent_x),
        "descendant_built": True,
        "refused_by_instrument": False,
        "known_effect": (
            "The authored evidence-selection procedure this study replaces. "
            "It fails the data-dependence gate on its own bytes, which is why "
            "an eligible revision is not a second copy of it."),
    }
    arms = {"incumbent": incumbent}
    for role in sorted(_controls.CONTROL_BUILDERS):
        arms[role] = _control_arm(role, workdir / role)
    arms["effectful"] = effectful_arm(workdir / "effectful")
    return arms


# --- eligibility, as far as it runs without a database ----------------------

def eligibility(source: str, workdir: Path) -> dict:
    """The five gates that execute without a database, and the sixth named.

    Each gate is called on its own so a failure names the boundary that held
    rather than collapsing into one verdict. Gate 6 is recorded as unexecuted
    rather than skipped silently, because a reader who cannot tell the
    difference between "passed" and "not asked" will read the whole record as
    a pass.
    """
    view = _admission_view(workdir)
    gates: dict = {}
    try:
        lr._method_exec.verify_step_source(source, "STEP")
        gates["non-empty executable STEP source"] = "pass"
    except Exception as exc:                       # noqa: BLE001
        gates["non-empty executable STEP source"] = "fail: %s" % exc
    gates["at least one learner view"] = "pass" if view else "fail"
    gates["bytes emit a probe"] = \
        "pass" if execute_decision(source, view)["kind"] == "probe" else "fail"
    gates["the probed x is computed from the view"] = \
        "pass" if channel._x_is_data_dependent(source) else "fail"
    try:
        scope = channel.unauthorised_change(source,
                                            channel.IMPROVE_LOW_SOURCE)
        gates["differs at x and nowhere else"] = \
            "pass" if not scope else "fail: %s" % scope
    except Exception as exc:                       # noqa: BLE001
        gates["differs at x and nowhere else"] = "fail: %s" % exc
    gates["does not reproduce the frozen reducer's choice"] = (
        "not executed: opens a disposable PostgreSQL through"
        " _execution_ledger; _reducer_argmax at this view is %s and the"
        " executed x is %s, which is the reading the gate compares against"
        % (channel._reducer_argmax(view),
           execute_decision(source, view)["x"]))
    executed = [g for g in gates.values() if g == "pass"]
    return {"gates": gates,
            "executed": len(executed),
            "not_executed": list(GATES_NEEDING_A_DATABASE),
            "frozen_write_reason": channel._frozen_write_reason(source)}


# --- the freeze, structurally -----------------------------------------------

FROZEN_ATTACKS = {
    "grant-assignment": "    view[\"grant\"] = {}",
    "used-update": "    view.update({\"used\": {}})",
    "authority-pop": "    view.pop(\"authority\", None)",
    "execution-limits": "    view[\"execution_limits\"] = {}",
    "sealed-results": "    view[\"sealed_results\"] = []",
    "evaluator": "    view[\"evaluator\"] = \"none\"",
}


def freeze_guard(source: str) -> dict:
    """Attempt six frozen-field writes on real revision bytes.

    `WORKER-PROMPT.md:126` requires that the program cannot alter grants,
    accounting, executor limits or sealed assessment. Asserting it would be
    the wrong shape, so each field is written into actual bytes the real
    constructor produced and the refusal is read back off the guard. The clean
    source is included as the case that must be admitted, or a guard that
    refuses everything would pass all six.
    """
    results = {"clean_source_refused": bool(
        channel._frozen_write_reason(source)), "attacks": {}}
    for name, statement in FROZEN_ATTACKS.items():
        attacked = source + "\n" + statement
        reason = channel._frozen_write_reason(attacked)
        results["attacks"][name] = {"refused": bool(reason),
                                    "reason": reason}
    results["every_attack_refused"] = all(
        entry["refused"] for entry in results["attacks"].values())
    return results


# --- the comparison, and the rule that stops it ------------------------------

def per_input_deltas(split: str, cohort: list) -> list:
    """The paired difference each reachable input makes on the incumbent."""
    incumbent_x = _controls.INCUMBENT_X
    rows = []
    for x in range(_rules.N_STATES):
        result = lr.compare(x, incumbent_x, split=split, seeds=cohort)
        rows.append({"x": x, "mean": result["mean_revised"],
                     "delta": result["delta"], "z": result["z"],
                     "measured": result["measured"]})
    return rows


def panels(rows: list, *, noise_z: float) -> dict:
    """Build the comparison, or refuse it and say why.

    The refusal is the point. `WORKER-PROMPT.md:133-134` reserves the honest
    negative for the case where no eligible revision can be had, and that case
    does not apply here, but a panel whose two arms differ by less than the
    cohort's own resampling spread is the same failure wearing a number. So
    the panel is built only from inputs whose paired z clears the bar, and a
    run that clears nothing reports the measurement that stopped it instead of
    the best-looking delta it found.
    """
    clearing = [row for row in rows
                if row["z"] is not None and abs(row["z"]) >= noise_z]
    best = max(rows, key=lambda row: row["delta"] if row["delta"]
               is not None else float("-inf"))
    if not clearing:
        return {
            "built": False,
            "reason": "no reachable input clears the noise floor",
            "noise_floor_z": noise_z,
            "best_input": best["x"],
            "best_delta": best["delta"],
            "best_z": best["z"],
            "arms": [],
        }
    return {
        "built": True,
        "noise_floor_z": noise_z,
        "arms": [{"x": row["x"], "mean": row["mean"], "delta": row["delta"],
                  "z": row["z"]} for row in clearing],
        "n_arms": len(clearing),
    }


def noise_report(split: str, cohort: list) -> dict:
    floor = channel.noise_floor(split=split, seeds=cohort)
    quarters = [cohort[index::4] for index in range(4)]
    argmaxes = []
    for seeds in quarters:
        if not seeds:
            continue
        rows = per_input_deltas(split, seeds)
        argmaxes.append(max(rows, key=lambda row: row["delta"] if row["delta"]
                            is not None else float("-inf"))["x"])
    return {
        "resample_spread": floor["resample_spread"],
        "best_probe_agrees": floor["best_probe_agrees"],
        "half_best_probes": [floor["half_a"]["best_probe"],
                             floor["half_b"]["best_probe"]],
        "quarter_argmaxes": argmaxes,
        "argmax_stable": len(set(argmaxes)) == 1,
        "note": ("the cohort's own argmax is the check on any argmax measured"
                 " against it; an input that wins on one half and loses on the"
                 " other has not been shown to win"),
    }


# --- the run -----------------------------------------------------------------

def run(workdir: Path | None = None, *, cohort: list = None,
        noise_z: float = NOISE_FLOOR_Z) -> dict:
    """Measure the mechanism, stopping before the panel if the bar is unmet."""
    cohort = list(cohort or COHORT)
    temporary = workdir is None
    root = Path(tempfile.mkdtemp()) if temporary else workdir
    root.mkdir(parents=True, exist_ok=True)

    source = channel._revision_source(EFFECTFUL_EXPRESSION)
    arms = controls_and_effectful(root)
    incumbent_x = arms["incumbent"]["executed_x"]

    restart = _restart_probe(root / "effectful" / "store")
    parent_restart = _restart_probe(_adopted_parent_store(root))

    rows = per_input_deltas(ASSESS_SPLIT, cohort)
    floor = noise_report(ASSESS_SPLIT, cohort)
    panel = panels(rows, noise_z=noise_z)

    descendant = lr.descendant_of(
        arms["effectful"]["executed_x"], ASSESS_SPLIT, cohort[0])

    return {
        "run_version": RUN_VERSION,
        "split": ASSESS_SPLIT,
        "cohort_size": len(cohort),
        "frozen": {key: value for key, value in lr.FROZEN.items()
                   if key != "frozen_fields"},
        "frozen_fields": list(channel.FROZEN_FIELDS),
        "arms": arms,
        "incumbent_x": incumbent_x,
        "effectful_changed_decision":
            arms["effectful"]["executed_x"] != incumbent_x,
        "restart": {"effectful": restart, "parent": parent_restart,
                    "effectful_changed_after_restart":
                        restart.get("x") != parent_restart.get("x"),
                    "effectful_matches_in_process":
                        restart.get("x") == arms["effectful"]["executed_x"]},
        "eligibility": eligibility(source, root),
        "freeze_guard": freeze_guard(source),
        "per_input": rows,
        "noise": floor,
        "panel": panel,
        "effectful_descendant_sample": descendant,
        "benefit_measured": False,
        "benefit_note": (
            "No panel is built, so no benefit number is reported. A benefit "
            "claim needs an acquired arm from a live route; this artifact "
            "measures the apparatus that would carry it."),
    }


def _adopted_parent_store(root: Path) -> Path:
    """Adopt nothing, so the restart probe has an incumbent store to read."""
    root = root / "parent-store"
    root.mkdir(parents=True, exist_ok=True)
    store = _frontier.create_store(
        root / "parent-store", namespace=_frontier.NAMESPACE,
        mission=lr._mission(), authority={"queries": 16, "steps": 12})
    store.bind_active(channel.make_control("low"))
    store.save()
    return root / "parent-store"


def main(argv: list) -> int:
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    artifact = run()
    text = json.dumps(artifact, indent=2, sort_keys=True, default=str)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
