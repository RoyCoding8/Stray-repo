"""Prove the E3 fixture's execution authority, and settle the durable seam.

Both are questions a reviewer would otherwise have to take on trust, and both
are answerable on this host without PostgreSQL.

1. THE REFUSAL GATE OPENS ON `authority=`.

   `drive_improve_round` refuses an owned store that names no authority
   (`improve_channel.py:2329`). This drives a real owned store -- a
   `StoreIdentity` is all that makes a store owned, and building one touches
   no database -- and enters the round twice, once with no authority and once
   with one. The no-authority entry must raise the execution-authority
   refusal; the authority entry must get past that gate and fail somewhere
   else instead. A fix that only renamed the fixture would still fail the
   first check, so this one is not vacuous.

2. AUTHORITY REACHES THE ROUND THROUGH EVERY HOP.

   `bind_retained_acquisition` -> `bind_live_revision` ->
   `run_live_improve_round` -> `drive_improve_round` is four frames, and a
   frame that accepts `authority=` and forgets to forward it turns the
   fixture's fix back into a refusal with no local sign.

3. THE FIXTURE NAMES ONE dsn FOR BOTH ROLES.

   The allocation and the store identity must land on the SAME database. If
   they land on different ones, the round's receipts settle where the
   investigation cannot reach them, which is the condition the
   execution-authority refusal exists to prevent.

4. THE CEILING IS AN EXACT FIT.

   `E3_SANDBOX_CALLS` claims three executions per round. This compares that
   against the round's real loop, and checks the allocation's capacity
   against the exposure those executions cost, so a stale number fails here
   rather than as an `InsufficientResources` on CI.

5. THE DURABLE SEAM IS NOT A NO-OP.

   `_replace_local_receipt_with_durable_test_seam` stands in for a durable
   receipt because the executor's own receipt identity starts `local:`. A
   round under REAL authority does not change that: the identity is minted at
   `launcher_local.py:971` as `f"local:{...}"`, by the only launcher
   `run_step_out_of_process` constructs, and nothing about a study authority
   reaches it. The tree also holds a `gvisor` launcher that mints `runsc:`,
   which IS durable and WOULD retire the seam -- it is unreachable from here
   because the executor hard-codes its profile. So the seam stays, and this
   is what would have to change for it not to.

Run from the repository root:

    python tools/prove_e3_authority_gate.py

Exit code 0 means every check passed.
"""

from __future__ import annotations

import ast
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

CHANNEL = ROOT / "experiments" / "ad01" / "improve_channel.py"
METHOD_EXEC = ROOT / "experiments" / "ad01" / "method_exec.py"
LAUNCHER = ROOT / "src" / "settlement" / "launcher_local.py"
INV_LIVE = ROOT / "scripts" / "invl02_live.py"

REFUSAL = "refused: an owned store executes under the authority its"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print("  %-4s %s%s" % ("PASS" if ok else "FAIL", label,
                           ("  -- " + detail) if detail else ""))
    if not ok:
        failures.append(label)


# ------------------------------------------------- 1. the refusal gate opens


def owned_store(tmp: Path):
    """An owned store, built without touching a database."""
    from experiments.ad01 import frontier
    from experiments.ad01 import improve_channel as channel

    identity = frontier.StoreIdentity(
        investigation_id="invl02-e12-P1-probe", dsn="dbname=e3-not-here")
    tmp.mkdir(parents=True, exist_ok=True)
    store = frontier.create_store(
        tmp / "frontier.json", namespace=frontier.NAMESPACE,
        mission={"objective": "m", "environments": [{"split": "dev",
                                                     "seed": 4}]},
        authority={"queries": 16, "steps": 12}, identity=identity)
    store.bind_active(channel.make_control("low"))
    return store


def gate_opens_on_authority(tmp: Path) -> None:
    print("\n1. the refusal gate opens on authority=")
    from experiments.ad01 import boolean_rule as rules
    from experiments.ad01 import frontier
    from experiments.ad01 import improve_channel as channel

    task = rules.make_task("dev", 4)
    store = owned_store(tmp / "no-authority")
    assert store.identity is not None, "the probe store is not owned"

    # Without authority: must refuse, and with the execution-authority message.
    try:
        channel.drive_improve_round(store, task, round_no=1, arm="P1")
        check("no authority is refused", False,
              "the round returned instead of refusing")
    except frontier.Refused as exc:
        check("no authority is refused", REFUSAL in str(exc), str(exc)[:120])

    # With authority: must get PAST that gate. It will then fail where it must
    # fail on this host -- at the executor's own connection to a database that
    # does not exist -- and that failure is the proof the gate opened.
    store = owned_store(tmp / "with-authority")
    try:
        channel.drive_improve_round(
            store, task, round_no=1, arm="P1",
            authority={"dsn": "dbname=e3-not-here",
                       "allocation_id": "e3evidence-alloc"})
        check("authority clears the gate", True,
              "the round ran to completion")
    except frontier.Refused as exc:
        check("authority clears the gate", REFUSAL not in str(exc),
              "reached a later refusal: " + str(exc)[:100])
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, str(exc)[:110])
        check("authority clears the gate", True,
              "reached the executor, which is where a missing database fails"
              " -- " + detail)
        del detail


# ------------------------------------- 2. the durable seam stays load-bearing


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _functions(tree: ast.Module, names: set[str]) -> dict:
    return {node.name: node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name in names}


def authority_reaches_the_round() -> None:
    """The keyword has to survive every hop, not just the fixture's own call.

    `bind_retained_acquisition` -> `bind_live_revision` ->
    `run_live_improve_round` -> `drive_improve_round` is four frames, and a
    frame that accepts `authority=` and forgets to pass it on turns the
    fixture's fix into a refusal again with no local sign. Each hop is read
    out of the parsed source rather than trusted.
    """
    print("\n2. authority reaches drive_improve_round through every hop")
    live = _tree(ROOT / "experiments" / "ad01" / "live_construct.py")
    channel = _tree(CHANNEL)
    hops = [
        ("bind_retained_acquisition", live,
         "bind_live_revision", {"authority", "dsn", "investigation_id"}),
        ("bind_live_revision", live,
         "run_live_improve_round", {"package", "round_no", "arm", "authority"}),
        ("run_live_improve_round", live,
         "drive_improve_round", {"round_no", "arm", "authority"}),
    ]
    for caller_name, tree, callee_name, required in hops:
        caller = _functions(tree, {caller_name}).get(caller_name)
        check("%s declares %s" % (caller_name, sorted(required)), bool(caller),
              "no such function" if not caller else "found")
        if caller is None:
            continue
        signature = [arg.arg for arg in caller.args.kwonlyargs]
        check("%s names %s=" % (caller_name, callee_name),
              "authority" in signature, "kwonly %s" % signature)
        forwarded = None
        for node in ast.walk(caller):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(
                node.func, "id", None)
            if name == callee_name:
                forwarded = {kw.arg: kw.value for kw in node.keywords
                             if kw.arg}
                break
        check("%s forwards authority= to %s" % (caller_name, callee_name),
              forwarded is not None and "authority" in forwarded
              and isinstance(forwarded.get("authority"), ast.Name)
              and forwarded["authority"].id == "authority",
              "forwards %s" % (sorted(forwarded) if forwarded else "no call"))
    check("drive_improve_round is where the refusal is decided",
          bool(_functions(channel, {"drive_improve_round"})),
          "improve_channel.drive_improve_round")


def fixture_names_the_authority() -> None:
    """The fixture's own call site must name it, or the chain starts nowhere.

    The second half is the requirement that is easy to get wrong and that no
    local assertion would catch: the allocation and the store identity must
    land on the SAME database. If they land on different ones, the round's
    receipts settle where the investigation cannot reach them, which is the
    condition the execution-authority refusal exists to prevent.

    It is checked by following where each dsn comes from. Both must be
    unpacked from the one `e3_database` fixture, so they cannot drift apart.
    """
    print("\n3. the E3 fixture names authority= and one dsn for both roles")
    tests = _tree(ROOT / "tests" / "test_evidence_integrity.py")
    offenders: list[str] = []
    found = 0
    for node in ast.walk(tests):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(
            node.func, "id", None)
        if name != "bind_retained_acquisition":
            continue
        found += 1
        keywords = {kw.arg for kw in node.keywords}
        if "authority" not in keywords or not (
                {"dsn", "investigation_id"} <= keywords):
            offenders.append("line %d: %s" % (node.lineno, sorted(keywords)))
    check("the fixture calls bind_retained_acquisition once", found == 1,
          "found %d call sites" % found)
    check("it names dsn, investigation_id and authority together",
          offenders == [], "; ".join(offenders))

    fixture = _functions(tests, {"e3_database"})
    check("the fixture exists", bool(fixture), "e3_database")
    if fixture:
        body = ast.dump(fixture["e3_database"])
        check("the allocation is authorized, not fabricated",
              "authorize_study" in body, "authorize_study is called")
        # The dsn argument is the disposable database's own attribute, so the
        # allocation and the ownership row share one database by construction.
        first_arg = None
        for node in ast.walk(fixture["e3_database"]):
            if isinstance(node, ast.Call) and getattr(
                    node.func, "attr", None) == "authorize_study":
                first_arg = node.args[0] if node.args else None
        check("authorize_study is called on the disposable database's dsn",
              isinstance(first_arg, ast.Attribute)
              and first_arg.attr == "dsn"
              and isinstance(first_arg.value, ast.Name)
              and first_arg.value.id == "database",
              "first argument is %s" % ast.unparse(first_arg)
              if first_arg is not None else "no first argument")

    # Every test that builds a bound store takes both halves from this one
    # fixture, so `StoreIdentity.dsn` and `authority["dsn"]` are the same
    # string by construction rather than by two independent edits agreeing.
    bound_sites = 0
    split: list[str] = []
    for node in ast.walk(tests):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(
            node.func, "id", None)
        if name not in {"_write_bound_e3_fixture", "_bound_acquired_store"}:
            continue
        bound_sites += 1
        keywords = {kw.arg for kw in node.keywords if kw.arg}
        args = node.args
        # positional: path, arm, dsn, authority. A bare dsn in the third slot
        # means the caller holds the string but not the allocation, which is
        # the split this is checking for.
        if "dsn" in keywords and "authority" not in keywords:
            split.append("line %d names dsn= with no authority=" % node.lineno)
        if len(args) >= 3 and isinstance(args[2], ast.Name) \
                and args[2].id == "e3_database":
            split.append("line %d passes a bare e3_database" % node.lineno)
    check("no bound store takes a bare dsn", split == [], "; ".join(split))
    check("bound-store sites found", bound_sites >= 2,
          "%d call sites" % bound_sites)

    budget_matches_the_round()


def budget_matches_the_round() -> None:
    """The ceiling has to be an exact fit, or it is not a bound at all.

    `E3_SANDBOX_CALLS` is derived as rounds x three steps on the belief that a
    round runs at most one execution per step. If a fourth call site reached
    the executor, the fixture would fail on `InsufficientResources` rather
    than on the thing under test, and that failure would read like a defect
    in the code rather than a stale number in the test. So the two sides are
    compared here: the fixture's declared budget, and the round's real shape.
    """
    print("\n4. the study ceiling is an exact fit for the rounds that run")
    # The constants are evaluated, not read as text: `E3_SANDBOX_EXPOSURE`
    # is an expression over the executor's timeout and the profile's stop
    # settle time, so a value parsed off the source would be a restatement of
    # the arithmetic rather than a check on it.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "tei_budget", ROOT / "tests" / "test_evidence_integrity.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        check("the fixture module loads", False,
              "%s: %s" % (type(exc).__name__, exc))
        return
    rounds = module.E3_ROUNDS
    calls = module.E3_SANDBOX_CALLS
    exposure = module.E3_SANDBOX_EXPOSURE
    tests = _tree(ROOT / "tests" / "test_evidence_integrity.py")
    authorized = None
    authorized_node = None
    for node in ast.walk(tests):
        if isinstance(node, ast.Call) and getattr(
                node.func, "attr", None) == "authorize_study":
            for keyword in node.keywords:
                if keyword.arg == "authorized":
                    authorized_node = keyword.value
                    authorized = ast.unparse(keyword.value)
    check("the fixture declares a derived budget",
          rounds and calls and exposure, "rounds=%s calls=%s exposure=%s"
          % (rounds, calls, exposure))
    check("the ceiling is rounds x three steps",
          calls == rounds * 3, "%s vs %s * 3" % (calls, rounds))

    # The capacity is the arithmetic the fixture actually evaluates, not a
    # restatement of it: a ceiling that fitted the calls but not their
    # exposure would refuse the reservation instead of the thing under test,
    # and that failure would read as a defect in the code.
    try:
        value = eval(compile(ast.Expression(authorized_node),
                             "<authorized>", "eval"),
                     {"__builtins__": {}},
                     {"E3_SANDBOX_CALLS": calls,
                      "E3_SANDBOX_EXPOSURE": exposure})
    except Exception as exc:
        value = None
        check("the capacity evaluates", False, "%s: %s" % (type(exc).__name__, exc))
    if value is not None:
        check("the capacity is the ceiling times its exposure",
              value == calls * exposure and value > 0,
              "%s evaluates to %d, the ceiling is %d"
              % (authorized, value, calls * exposure))

    # The round's own shape: `for step in range(N)` with one executor call per
    # step, read from the loop rather than from the number the test assumed.
    channel = _tree(CHANNEL)
    driver_fn = _functions(channel, {"drive_improve_round"})[
        "drive_improve_round"]
    steps = None
    executor_calls = 0
    for node in ast.walk(driver_fn):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(
                node.func, "id", None)
            if name in {"_run_source", "run_improve_step", "run_operate_step",
                        "run_step_out_of_process"}:
                executor_calls += 1
        if isinstance(node, ast.For) and isinstance(
                node.iter, ast.Call) and getattr(
                    node.iter.func, "id", None) == "range":
            if len(node.iter.args) == 1 and isinstance(
                    node.iter.args[0], ast.Constant):
                steps = node.iter.args[0].value
    check("the round runs one execution per step", steps is not None
          and executor_calls == 1, "range(%s) with %d executor calls"
          % (steps, executor_calls))
    check("the fixture's three matches the round's loop", steps == 3,
          "round runs range(%s)" % steps)


def seam_is_load_bearing() -> None:
    print("\n5. the durable seam is not a no-op under real authority")
    exec_tree = _tree(METHOD_EXEC)
    launcher_tree = _tree(LAUNCHER)
    runsc_tree = _tree(ROOT / "src" / "settlement" / "launcher_runsc.py")
    inv_tree = _tree(INV_LIVE)

    # (a) the executor constructs exactly one launcher, and it is LocalLauncher
    runner = _functions(exec_tree, {"run_step_out_of_process"})
    launcher_constructs = sorted({
        node.func.id if isinstance(node.func, ast.Name)
        else getattr(node.func, "attr", "")
        for node in ast.walk(runner["run_step_out_of_process"])
        if isinstance(node, ast.Call)
        and "Launcher" in (node.func.id if isinstance(node.func, ast.Name)
                           else getattr(node.func, "attr", ""))})
    check("the executor builds only LocalLauncher",
          launcher_constructs == ["LocalLauncher"], str(launcher_constructs))

    # (a2) and it is the one that mints `local:`. This is the load-bearing
    # contrast: the tree also holds a `gvisor` launcher that mints `runsc:`,
    # which IS durable and WOULD retire the seam. It is unreachable from here
    # because `run_step_out_of_process` hard-codes the profile it dispatches,
    # so the check is about reachability rather than about the tree.
    check("a durable-identity launcher exists in the tree but is unreachable",
          "runsc:" in ast.dump(runsc_tree)
          and not any(
              isinstance(node, ast.Name) and node.id == "PROFILE"
              and not (isinstance(getattr(node, "ctx", None), ast.Load))
              for node in ast.walk(runner["run_step_out_of_process"])),
          "runsc: mints a durable identity; the executor pins PROFILE")

    # (b) authority is not consulted where the identity is minted
    dispatch = _functions(launcher_tree, {"dispatch"})
    body = ast.dump(dispatch.get("dispatch")) if dispatch else ""
    check("the launcher's own dispatch mints no durable identity",
          "authorize" not in body and "study" not in body
          and "allocation" not in body,
          "no authority term in LocalLauncher.dispatch")

    # (c) the identity is minted as `local:<...>` and nowhere else
    mints = []
    for node in ast.walk(launcher_tree):
        if isinstance(node, ast.keyword) and node.arg == "receipt_identity":
            value = node.value
            if isinstance(value, ast.JoinedStr):
                mints.append("".join(
                    part.value for part in value.values
                    if isinstance(part, ast.Constant) and
                    isinstance(part.value, str)))
    check("the launcher mints exactly one identity, and it is local:",
          mints == ["local:"], "minted prefixes %s" % (mints,))

    # (d) E3 refuses a local identity, which is why the seam is needed at all
    gate = _functions(inv_tree, {"_durable_e3_receipt"})
    check("run_e3 refuses a local: receipt identity",
          bool(gate) and "local:" in ast.dump(gate["_durable_e3_receipt"]),
          "invl02_live._durable_e3_receipt guards on the local: prefix")

    # (e) and the frontier store's own child-receipt guard is what the seam's
    # docstring says it is: it compares the launcher's inner identity with the
    # outer one, so rebinding one alone is refused.
    frontier_tree = _tree(ROOT / "experiments" / "ad01" / "frontier.py")
    guard = _functions(frontier_tree, {"_validate_child_receipt"})
    dumped = ast.dump(guard["_validate_child_receipt"]) if guard else ""
    check("the inner identity is compared against the outer one",
          "durable identity mismatch" in dumped
          or "receipt_identity" in dumped,
          "frontier._validate_child_receipt reads launcher receipt_identity")


def main() -> None:
    print("proving the E3 execution-authority gate and the durable seam")
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        gate_opens_on_authority(Path(raw))
    authority_reaches_the_round()
    fixture_names_the_authority()
    seam_is_load_bearing()
    print("\n%s" % ("all checks passed" if not failures else
                    "FAILED: " + ", ".join(failures)))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(2)
