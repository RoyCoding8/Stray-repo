"""What the executor's boundary actually is, and where it stops being one.

Three separate claims are kept apart on purpose. The interpreter is
*closed*, which is a property of the grammar. A step is *resource
bounded*, which is a property of the child process. Neither is a sandbox:
the child shares this uid, the filesystem and the network with the
parent, and the last test below says so in a form that fails if anyone
ever writes that it is one.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_ast_policy as ast_policy
from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import policy_action


def _const(value):
    return {"op": "const", "value": value}


def _field(scope, name):
    return {"op": "field", "scope": scope, "name": name}


def _index(value, key):
    return {"op": "index", "value": value, "key": key}


def _not(value):
    return {"op": "not", "value": value}


def _obj(**fields):
    return {"op": "obj", "fields": {
        name: value if isinstance(value, dict) and "op" in value
        else _const(value)
        for name, value in fields.items()}}


def _action(kind="stop", target="boolean.task", inputs=None, state=None,
            resources=None):
    return {"op": "return_action", "kind": kind, "target": target,
            "inputs": _obj(**(inputs or {})),
            "evidence_refs": [], "requested_resources": resources or {},
            "state": _const({} if state is None else state)}


def _record(document):
    encoded = json.dumps(document, allow_nan=False, ensure_ascii=False,
                         separators=(",", ":"), sort_keys=True).encode()
    return {"artifact": {
        "kind": "learning-policy", "representation": "typed-ast",
        "version": "boolean-typed-ast-v1",
        "policy_id": document["policy_id"],
        "ast_digest": hashlib.sha256(encoded).hexdigest(),
    }, "policy_ast": document}


def _public(seed=4, **overrides):
    session = rules.RuleSession(rules.make_task("dev", seed))
    public = active.public_state(session)
    public.update(overrides)
    return public


def _first_step(document, **limits):
    return ast_policy.ast_step(_record(document), _public(), {}, **limits)


def _refusal(result):
    return result["action"]["inputs"]["bridge_refusal"]


def _wide_document(name="wide", items=200, size=3000):
    """The largest program the loader admits.

    Every node is a constant, so nothing here is bounded by a branch or
    an index. It is the shape that actually reaches the child's memory
    and output limits, which a deep or a wide control flow does not.
    """
    blob = "z" * size
    return {"policy_id": name, "entry": _action(
        inputs={"v": {"op": "list", "items": [_const(blob) for _ in range(items)]}})}


def test_a_wide_program_loads_and_its_request_fits_the_byte_cap():
    document = _wide_document()
    ast_policy.load_policy(_record(document), expected_policy_id="wide")

    budget = ast_policy._Budget()
    ast_policy._stmt(document["entry"], "$.entry", budget)
    assert budget.nodes <= ast_policy.MAX_NODES

    result = _first_step(document, max_output_bytes=1 << 20)
    assert result["action"]["inputs"] != {}
    assert result["action"]["kind"] == policy_action.STOP


def test_the_output_cap_fires_when_the_step_exceeds_it():
    document = _wide_document("over-output")
    with pytest.raises(ast_policy._ExecutionRefused) as raised:
        _first_step(document, max_output_bytes=4096)
    assert "output byte cap" in str(raised.value)


def test_the_memory_cap_fires_and_surfaces_as_a_child_failure():
    document = _wide_document("over-memory", items=200, size=3000)
    with pytest.raises(ast_policy._ExecutionRefused) as raised:
        _first_step(document, max_output_bytes=1 << 20, memory_bytes=16 * 1024 * 1024)
    assert "child exited" in str(raised.value)
    assert "MemoryError" in str(raised.value)


def test_the_wall_timeout_fires():
    with pytest.raises(ast_policy._ExecutionRefused) as raised:
        _first_step(_action_document("timeout"), timeout_ms=1)
    assert str(raised.value) == "wall timeout after 1 ms"


def test_the_wall_timeout_measures_interpreter_startup_not_just_the_program():
    """Why a tight timeout in another test can flake, measured.

    `tests/test_boolean_ast_arm.py::test_a_failing_ast_step_becomes_a_
    legal_recorded_stop` asks for `timeout_ms=1000` and then expects the
    program's own `list index is out of range`. The child is a fresh
    interpreter, and on a loaded machine its cold import alone measured
    0.82s to 2.46s over five runs, so the timeout fires first and the
    assertion fails. It reproduces on the base commit with this lane's
    changes stashed, so it is pre-existing and load-dependent, not a
    regression.

    This test pins the mechanism: the *same* program produces the right
    refusal once the budget covers startup. It is the fix the other test
    wants, written where the boundary is documented rather than by
    weakening an assertion another lane owns.
    """
    program = {"policy_id": "startup-cost", "entry": _action(
        inputs={"v": _index(_const([]), _const(0))})}

    with pytest.raises(ast_policy._ExecutionRefused) as tight:
        _first_step(program, timeout_ms=1)
    assert str(tight.value) == "wall timeout after 1 ms"

    with pytest.raises(ast_policy._ExecutionRefused) as generous:
        _first_step(program, timeout_ms=60_000)
    assert "list index is out of range" in str(generous.value)


def _action_document(name, entry=None):
    return {"policy_id": name, "entry": entry or _action()}


def test_the_state_cap_fires_before_the_state_reaches_the_child():
    document = {"policy_id": "over-state", "entry": _action(
        state={"blob": "y" * 6000})}
    with pytest.raises(ValueError) as raised:
        _first_step(document)
    assert "policy state exceeds %d bytes" % ast_policy.policy_step.STATE_LIMIT_BYTES \
        == str(raised.value)


def test_the_node_budget_fires_at_load_and_names_the_budget():
    document = {"policy_id": "over-nodes", "entry": {
        "op": "block", "stmts": [
            {"op": "if", "cond": _const(index < 99),
             "then": {"op": "assign", "name": "v%d" % index, "value": _const(index)},
             "else": _action()} for index in range(40)]}}
    with pytest.raises(ast_policy._LoadRefused) as raised:
        ast_policy.load_policy(_record(document), expected_policy_id="over-nodes")
    assert str(raised.value).endswith("policy exceeds 256 nodes")


def test_the_depth_budget_fires_at_load():
    deep = _const(True)
    for _ in range(40):
        deep = _not(deep)
    document = {"policy_id": "over-depth", "entry": {
        "op": "if", "cond": deep, "then": _action(), "else": _action()}}
    with pytest.raises(ast_policy._LoadRefused) as raised:
        ast_policy.load_policy(_record(document), expected_policy_id="over-depth")
    assert str(raised.value).endswith("policy exceeds depth 32")


def test_the_closed_interpreter_reaches_no_reflection_primitive():
    source = Path(ast_policy.__file__).read_text(encoding="utf-8")
    for forbidden in ("eval(", "exec(", "__import__(", "getattr(",
                      "setattr(", "globals(", "locals(", "__subclasses__"):
        assert forbidden not in source, forbidden

    grammar = set(ast_policy._EXPR_FIELDS) | set(ast_policy._STMT_FIELDS)
    assert "eval" not in grammar and "exec" not in grammar


def test_a_step_child_runs_with_a_scrubbed_environment_and_its_own_directory():
    """The boundary that exists is a process boundary, not a sandbox."""
    limits = ast_policy.expressivity_limits()["enforcement"]
    assert "no OS-level sandbox" in limits["not_claimed"]
    assert "resource boundary, not a security boundary" in limits["not_claimed"]

    source = Path(ast_policy.__file__).read_text(encoding="utf-8")
    assert '"PATH": "/usr/bin:/bin"' in source
    assert "start_new_session=True" in source
    assert 'os.killpg' in source
    assert source.count("stdin=subprocess.DEVNULL") == 1


def test_the_cpu_limit_is_installed_but_no_legal_program_reaches_it():
    """Reported as a limit that binds, not one that fires.

    The child installs `RLIMIT_CPU` and refuses a non-positive value, so
    the mechanism is present. But the load-time node budget bounds the
    work, and the widest legal document finishes in well under a second
    against a one-second resolution, so nothing legal trips it. Saying
    this plainly is the point; claiming enforcement that was never
    observed is the failure mode this test exists to prevent.
    """
    source = Path(ast_policy.__file__).read_text(encoding="utf-8")
    assert "resource.setrlimit(resource.RLIMIT_CPU" in source
    assert "cpu_seconds must be positive" in source

    assert ast_policy.expressivity_limits()["enforcement"]["cpu"].startswith(
        "RLIMIT_CPU is installed and the child validates the value")


@pytest.mark.parametrize("value", [0, -1])
def test_a_non_positive_limit_is_refused_before_a_child_is_started(value):
    with pytest.raises(ValueError) as raised:
        _first_step(_action_document("limits"), timeout_ms=value)
    assert str(raised.value) == "timeout_ms must be a positive integer"

    with pytest.raises(ValueError) as raised:
        _first_step(_action_document("limits"), cpu_seconds=value)
    assert str(raised.value) == "cpu_seconds must be a positive integer"


def test_indexing_past_the_end_of_an_observation_is_a_runtime_refusal():
    document = {"policy_id": "past-end", "entry": _action(
        inputs={"v": _index(_index(_field("view", "observed"), _const(0)),
                            _const("y"))})}
    with pytest.raises(ast_policy._ExecutionRefused) as raised:
        _first_step(document)
    assert "list index is out of range" in str(raised.value)


def test_the_step_refuses_a_host_that_cannot_install_the_caps():
    """A missing `resource` module is a deployment fact, not a program error.

    The child installs RLIMIT_CPU and RLIMIT_AS before the document runs.
    A host with no POSIX `resource` module has no supported equivalent for
    either cap, so the step is refused by name rather than left to die on
    an import whose traceback reads like a bug in the policy.

    The verdict is asserted as a literal, so this test cannot pass with the
    probe answering `None` or an empty reason. It is keyed to the host's
    own answer rather than skipped, because a probe that reported a cap it
    could not install is the silent-degradation defect these tests exist to
    catch, and skipping on it would hide exactly that.
    """
    support = ast_policy.child_limit_support()
    document = {"policy_id": "caps", "entry": _action()}

    if support.available:
        # A host that can install the caps must install them, and the step
        # must run rather than refuse itself.
        assert support.reason == "RLIMIT_CPU and RLIMIT_AS are available"
        result = _first_step(document)
        assert result["action"]["kind"] == "stop"
        return

    assert support.name == "rlimit"
    with pytest.raises(ast_policy._ExecutionRefused) as raised:
        _first_step(document)
    assert str(raised.value) == (
        "this host provides no POSIX resource module, so a child's "
        "cpu_seconds and memory_bytes caps cannot be installed; the "
        "typed-AST executor needs a supported Linux execution environment")


def test_the_refusal_names_the_platform_and_not_the_child_traceback():
    """The step's own traceback must never be the thing a reader diagnoses.

    Before the capability was consulted in one place, the child exited 1 on
    `ModuleNotFoundError: No module named 'resource'` and the parent
    reported "child exited 1", which names a crash rather than a host.
    """
    if ast_policy.child_limit_support().available:
        pytest.skip("this host installs POSIX rlimits, so the refusal under "
                    "test cannot be produced here")

    document = {"policy_id": "caps-2", "entry": _action()}
    with pytest.raises(ast_policy._ExecutionRefused) as raised:
        _first_step(document)
    reason = str(raised.value)
    assert "No module named" not in reason
    assert "child exited" not in reason
    assert "supported Linux execution environment" in reason
