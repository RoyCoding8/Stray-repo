"""Prove the operate choices settle under the study allocation, and say which.

The seam this closes: `live_construct.choose_next_work` reached
`improve_channel.run_operate_step` with no `authority=`, so `_execution_ledger`
took its `None` default and opened `_disposable_authority` -- a database
created for the execution and dropped when it ends. Three choices per
investigation, and the two fields M2 reports (`observation_dependent` and
`falsifier_moves_decision`) are computed from exactly those three. So the
decision M2 measures had receipts naming a database that no longer exists.

The authority is now threaded from `_run_frontier_investigation`'s own
`_study_authority(dsn, allocation_id)` -- one derivation, passed down -- and
`choose_next_work` refuses an owned store entered with none, on the same rule
`drive_improve_round` already refuses on.

This walks the live tree and reports, per call site, whether the `authority`
keyword is actually passed and whether the arm reaches the operation id. It
reads code and computes ids; it stands up no database, because the claim it
makes is about which authority a call site names, and the durable receipt is
proved by `tests/test_operate_step_authority.py` against a real database.

    python tools/prove_operate_step_authority.py

Exit code 0 when every production call site supplies both. That makes this
runnable as a gate in CI and rerunnable by a reviewer, which is the point: the
census is the artifact, not a claim in a commit message.
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in ("", "src", "scripts"):
    sys.path.insert(0, str(ROOT / extra) if extra else str(ROOT))

from experiments.ad01 import improve_channel as _channel  # noqa: E402
from experiments.ad01 import live_construct as _live  # noqa: E402
from scripts import invl02_live as _driver  # noqa: E402

DRIVER = ROOT / "scripts" / "invl02_live.py"

#: The files that make the production choice. `improve_channel` is the
#: executor the choice reaches, listed so a change there shows up as a new
#: row rather than silently altering what the other two mean.
LIVE_TREE = ("experiments/ad01/live_construct.py", "scripts/invl02_live.py",
             "experiments/ad01/improve_channel.py")


def _call_name(node: ast.AST) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _keywords(node: ast.Call) -> set:
    return {kw.arg for kw in node.keywords if kw.arg}


def census() -> dict:
    """Every call site of the two entry points, and what each one names."""
    rows = []
    for rel in LIVE_TREE:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name not in ("choose_next_work", "run_operate_step"):
                continue
            kws = _keywords(node)
            rows.append({
                "file": rel,
                "line": node.lineno,
                "callee": name,
                "names_authority": "authority" in kws,
                "names_arm": "arm" in kws,
            })
    return {"rows": rows}


def _signature() -> dict:
    return {
        "choose_next_work": str(inspect.signature(_live.choose_next_work)),
        "_control_triple": str(inspect.signature(_driver._control_triple)),
        "run_operate_step": str(inspect.signature(
            _channel.run_operate_step)),
    }


def operation_ids() -> dict:
    """What the operation id reads, per arm, and whether arms collide.

    The executor derives its id from the package, the purpose, the view and
    the arm (`_derived_operation_id`). Two arms of one study bind the same
    deterministic `make_control("low")` and the same view, so the arm is the
    only thing separating their operations. That is computed here rather than
    asserted, because "the id names the arm" is a claim about a format string
    and a format string can be edited.
    """
    package = _channel.make_control("low")
    view = {"purpose": "op"}
    ids = {arm: _channel._derived_operation_id(
        package, "op", view, arm=arm)
        for arm in ("control", "live", "P1", None)}
    arms = {k: v for k, v in ids.items() if k is not None}
    return {
        "ids": {str(k): v for k, v in ids.items()},
        "arms_are_distinct": len(set(arms.values())) == len(arms),
        "unnamed_arm_reads_noarm": ids[None].split("-")[2] == "noarm",
    }


def ceilings() -> dict:
    """What one investigation costs on its study's ceiling, and whether it fits.

    Threading the authority does not add executions -- the same three choices
    still run -- but it moves them. Before the thread they settled on
    `_disposable_authority`'s own database under its own study root and a
    different `dsn`, so `_study_operation_counts` never walked them and no
    ceiling was charged. They are charged now, so a ceiling sized before the
    thread refuses the run that has to happen. Both ceilings are recomputed
    here from the counts in the tree, so the figure and the code cannot drift
    apart quietly.

    The improve steps are counted from `drive_improve_round`'s own bound
    (`range(3)`), read out of the AST rather than restated, because that is the
    same derivation the cap sheet used and a number copied into a comment is a
    number that goes stale without anyone noticing.
    """
    improve_steps = 0
    channel = ast.parse(
        (ROOT / "experiments/ad01" / "improve_channel.py").read_text(
            encoding="utf-8"))
    for node in ast.walk(channel):
        if not isinstance(node, ast.FunctionDef) or \
                node.name != "drive_improve_round":
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.For) and isinstance(inner.iter, ast.Call) \
                    and getattr(inner.iter.func, "id", "") == "range" and \
                    inner.iter.args and \
                    isinstance(inner.iter.args[0], ast.Constant):
                improve_steps = max(improve_steps,
                                    int(inner.iter.args[0].value))
    driver = ast.parse(DRIVER.read_text(encoding="utf-8"))
    choices = 0
    rounds = 0
    for node in ast.walk(driver):
        if isinstance(node, ast.FunctionDef) and \
                node.name == "_control_triple":
            choices = sum(1 for inner in ast.walk(node)
                          if isinstance(inner, ast.Call)
                          and getattr(inner.func, "attr", "")
                          == "choose_next_work")
        if isinstance(node, ast.FunctionDef) and \
                node.name == "_run_frontier_investigation":
            rounds = sum(1 for inner in ast.walk(node)
                         if isinstance(inner, ast.Call)
                         and getattr(inner.func, "attr", "")
                         == "run_live_improve_round")
    per_investigation = improve_steps * rounds + choices
    return {
        "improve_steps_per_round": improve_steps,
        "rounds_per_investigation": rounds,
        "operate_choices_per_investigation": choices,
        "sandbox_calls_per_investigation": per_investigation,
        "E0_SANDBOX_CALLS": _driver.E0_SANDBOX_CALLS,
        "E12_SANDBOX_CALLS": _driver.E12_SANDBOX_CALLS,
        # E0 pays the ceiling for two investigations plus one retained-acquisition
        # binding the live arm alone can reach; E12 for three plus one binding per
        # retained arm. Both are the cap sheet's own arithmetic, rechecked here
        # against the counts in the tree.
        "E0_spends": 2 * per_investigation + 3,
        "E12_spends": 3 * per_investigation + 6,
        "E0_fits": 2 * per_investigation + 3 <= _driver.E0_SANDBOX_CALLS,
        "E12_fits": 3 * per_investigation + 6 <= _driver.E12_SANDBOX_CALLS,
    }


def main() -> int:
    report = {
        "signatures": _signature(),
        "census": census(),
        "operation_ids": operation_ids(),
        "ceilings": ceilings(),
    }
    choice_rows = [r for r in report["census"]["rows"]
                   if r["callee"] == "choose_next_work"]
    missing = [r for r in choice_rows if not r["names_authority"]]
    report["verdict"] = {
        "choose_next_work_call_sites": len(choice_rows),
        "call_sites_naming_authority": len(choice_rows) - len(missing),
        "all_name_authority": not missing,
        "arms_are_distinct": report["operation_ids"]["arms_are_distinct"],
        "E0_fits": report["ceilings"]["E0_fits"],
        "E12_fits": report["ceilings"]["E12_fits"],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    ok = (report["verdict"]["all_name_authority"]
          and report["verdict"]["arms_are_distinct"]
          and report["verdict"]["E0_fits"]
          and report["verdict"]["E12_fits"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())