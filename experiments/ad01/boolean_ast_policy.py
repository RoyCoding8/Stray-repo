"""Execute a bounded typed policy document in the Boolean active world."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import boolean_rule as rules
from . import policy_action
from . import policy_step

_REPRESENTATION = "boolean-typed-ast-v1"
MAX_NODES = 256
MAX_DEPTH = 32
MAX_INTEGER_BITS = 64
MAX_BLOCK_STATEMENTS = 64

_EXPR_FIELDS = {
    "const": {"op", "value"},
    "list": {"op", "items"},
    "obj": {"op", "fields"},
    "field": {"op", "scope", "name"},
    "index": {"op", "value", "key"},
    "add": {"op", "left", "right"},
    "eq": {"op", "left", "right"},
    "lt": {"op", "left", "right"},
    "not": {"op", "value"},
}
_STMT_FIELDS = {
    "if": {"op", "cond", "then", "else"},
    "block": {"op", "stmts"},
    "return_action": {
        "op", "kind", "target", "inputs", "evidence_refs",
        "requested_resources", "state",
    },
    "assign": {"op", "name", "value"},
}
_VIEW_TYPES = {
    "instrument": "string",
    "task_id": "string",
    "observed": "observation_list",
    "remaining": "integer",
    "public_world": "world",
    "action_schema": "object",
}


class _LoadRefused(ValueError):
    pass


class _ExecutionRefused(Exception):
    pass


@dataclass(frozen=True)
class ChildLimitSupport:
    """Whether this host can enforce the caps a step child is promised."""

    name: str
    available: bool
    reason: str


def child_limit_support() -> ChildLimitSupport:
    """Whether this host can install the step child's CPU and memory caps.

    Measured rather than assumed, and consulted once by `_run_step` before
    a child exists. `RLIMIT_CPU` and `RLIMIT_AS` are POSIX rlimits: a host
    with no `resource` module has no supported equivalent for either, so a
    child there would carry the wall timeout, the output cap and the load
    budgets but no CPU cap and no address-space cap, and the limits table
    would claim a boundary that was never installed. A step whose caps
    cannot be installed is refused, not run with the caps dropped.

    This is a platform capability, not a policy. It has no override: a
    caller that needs the typed-AST executor on such a host is asking for
    a supported Linux execution environment.
    """
    try:
        import resource
    except ImportError:
        return ChildLimitSupport(
            "rlimit", False,
            "this host provides no POSIX resource module, so a child's "
            "cpu_seconds and memory_bytes caps cannot be installed; the "
            "typed-AST executor needs a supported Linux execution "
            "environment")
    missing = [name for name in ("setrlimit", "RLIMIT_CPU", "RLIMIT_AS")
               if not hasattr(resource, name)]
    if missing:
        return ChildLimitSupport(
            "rlimit", False,
            "the resource module does not provide %s, so a child's "
            "cpu_seconds and memory_bytes caps cannot be installed"
            % ", ".join(missing))
    return ChildLimitSupport(
        "rlimit", True, "RLIMIT_CPU and RLIMIT_AS are available")


@dataclass(frozen=True)
class _Node:
    op: str
    value: Any
    kind: Any = None
    path: str = ""


class _Budget:
    def __init__(self):
        self.nodes = 0

    def enter(self, path: str, depth: int) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            _fail(path, "policy exceeds %d nodes" % MAX_NODES)
        if depth > MAX_DEPTH:
            _fail(path, "policy exceeds depth %d" % MAX_DEPTH)

    def integer(self, value: int, path: str) -> int:
        if value.bit_length() > MAX_INTEGER_BITS:
            _fail(path, "integer exceeds %d bits" % MAX_INTEGER_BITS)
        return value


def _fail(path: str, message: str) -> None:
    raise _LoadRefused(f"{path}: {message}")


def _exact(node: Any, path: str, fields: set[str]) -> dict:
    if type(node) is not dict:
        _fail(path, "node must be an object")
    missing = sorted(fields - set(node))
    if missing:
        _fail(path, "missing required field: %s" % missing[0])
    unknown = sorted(set(node) - fields)
    if unknown:
        _fail(path, "unknown field: %s" % unknown[0])
    return node


def _json(value: Any, path: str, budget: _Budget | None = None) -> bool:
    if value is None or type(value) in (bool, str):
        return True
    if type(value) is int:
        return budget is None or budget.integer(value, path) == value
    if type(value) is float:
        return value == value and value not in (float("inf"), float("-inf"))
    if type(value) is list:
        return all(_json(item, path, budget) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _json(item, path, budget)
                   for key, item in value.items())
    return False


def _has_boolean_literal(node: _Node) -> bool:
    """Whether a subtree can produce a Python bool.

    `bool` is a subclass of `int`, so a boolean reaching `add` would
    otherwise add as 1 or 0 and the type tag alone would not catch it.
    """
    if node.op == "const":
        return isinstance(node.value, bool)
    if node.op == "not":
        return True
    if node.op in ("eq", "lt"):
        return True
    if node.op in ("add", "index", "list"):
        return any(_has_boolean_literal(child) for child in node.value)
    if node.op == "obj":
        return any(_has_boolean_literal(child) for child in node.value[1].values())
    if node.op == "field":
        return node.kind == "boolean"
    return False


def _json_kind(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    if type(value) is str:
        return "string"
    return "list" if type(value) is list else "object"


def _compatible(actual: str, expected: str) -> bool:
    return expected == "any" or actual == expected or (
        expected == "number" and actual == "integer"
    )


def _json_equal(left: Any, right: Any) -> bool:
    """JSON equality, which is not Python equality.

    Python calls `True == 1` and `1 == 1.0`; JSON calls none of those
    true, so a program comparing across those types would silently take
    the wrong branch on a host that used `==` directly.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    return left == right


def _same_type(left: str, right: str) -> bool:
    if left == "any" or right == "any":
        return True
    if {left, right} == {"list", "observation_list"}:
        return True
    if {left, right} == {"integer", "number"}:
        return True
    return left == right


def _expr(node: Any, path: str, budget: _Budget, depth: int = 1) -> _Node:
    budget.enter(path, depth)
    if type(node) is not dict or not isinstance(node.get("op"), str):
        _fail(path, "expression must name an op")
    op = node["op"]
    if op not in _EXPR_FIELDS:
        _fail(path, "unknown expression op %r" % op)
    _exact(node, path, _EXPR_FIELDS[op])

    if op == "const":
        if not _json(node["value"], path + ".value", budget):
            _fail(path + ".value", "const must be a finite JSON value")
        return _Node(op, deepcopy(node["value"]), _json_kind(node["value"]), path)
    if op == "list":
        items = node["items"]
        if not isinstance(items, list):
            _fail(path + ".items", "list items must be a list")
        parsed = tuple(
            _expr(item, path + ".items[%d]" % index, budget, depth + 1)
            for index, item in enumerate(items)
        )
        return _Node(op, parsed, "list", path)
    if op == "obj":
        fields = node["fields"]
        if not isinstance(fields, dict):
            _fail(path + ".fields", "obj fields must be an object")
        parsed = tuple(
            (key, _expr(value, path + ".fields[" + repr(key) + "]",
                        budget, depth + 1))
            for key, value in sorted(fields.items())
        )
        return _Node(op, parsed, "object", path)
    if op == "field":
        scope, name = node["scope"], node["name"]
        if scope not in ("view", "state"):
            _fail(path + ".scope", "field scope must be view or state")
        if not isinstance(name, str) or not name:
            _fail(path + ".name", "field name must be a nonempty string")
        if scope == "view" and name not in _VIEW_TYPES:
            _fail(path + ".name", "unknown view field %r" % name)
        if scope == "state" and name.startswith("_"):
            _fail(path + ".name", "state field must not start with underscore")
        kind = _VIEW_TYPES.get(name, "any") if scope == "view" else "any"
        return _Node(op, (scope, name), kind, path)
    if op == "index":
        value = _expr(node["value"], path + ".value", budget, depth + 1)
        key = _expr(node["key"], path + ".key", budget, depth + 1)
        if value.kind == "observation_list":
            if not _compatible(key.kind, "integer"):
                _fail(path + ".key", "list index must have integer type")
            kind = "observation"
        elif value.kind == "object":
            if not _compatible(key.kind, "string"):
                _fail(path + ".key", "object index must have string type")
            kind = "any"
        else:
            kind = "any"
        return _Node(op, (value, key), kind, path)
    if op in ("add", "lt"):
        left = _expr(node["left"], path + ".left", budget, depth + 1)
        right = _expr(node["right"], path + ".right", budget, depth + 1)
        for child in (left, right):
            if not _compatible(child.kind, "number"):
                _fail(path, "%s requires two numeric operands" % op)
            if child.kind == "boolean" or _has_boolean_literal(child):
                _fail(path + (".left" if child is left else ".right"),
                      "%s requires two numeric operands" % op)
        kind = "number" if op == "add" else "boolean"
        return _Node(op, (left, right), kind, path)
    if op == "eq":
        left = _expr(node["left"], path + ".left", budget, depth + 1)
        right = _expr(node["right"], path + ".right", budget, depth + 1)
        if not _same_type(left.kind, right.kind):
            _fail(path, "eq operands must have the same type")
        return _Node(op, (left, right), "boolean", path)
    value = _expr(node["value"], path + ".value", budget, depth + 1)
    if not _compatible(value.kind, "boolean"):
        _fail(path, "not operand must have boolean type")
    return _Node(op, value, "boolean", path)


def _stmt(node: Any, path: str, budget: _Budget, depth: int = 1) -> _Node:
    budget.enter(path, depth)
    if type(node) is not dict or not isinstance(node.get("op"), str):
        _fail(path, "statement must name an op")
    op = node["op"]
    if op not in _STMT_FIELDS:
        _fail(path, "unknown statement op %r" % op)
    _exact(node, path, _STMT_FIELDS[op])

    if op == "if":
        condition = _expr(node["cond"], path + ".cond", budget, depth + 1)
        if not _compatible(condition.kind, "boolean"):
            _fail(path + ".cond", "if condition must have boolean type")
        then_branch = _stmt(node["then"], path + ".then", budget, depth + 1)
        else_branch = _stmt(node["else"], path + ".else", budget, depth + 1)
        return _Node(op, (condition, then_branch, else_branch), path=path)
    if op == "block":
        statements = node["stmts"]
        if not isinstance(statements, list) or not statements:
            _fail(path + ".stmts", "block stmts must be a nonempty list")
        if len(statements) > MAX_BLOCK_STATEMENTS:
            _fail(path + ".stmts", "block exceeds %d statements"
                  % MAX_BLOCK_STATEMENTS)
        parsed = tuple(
            _stmt(statement, path + ".stmts[%d]" % index, budget, depth + 1)
            for index, statement in enumerate(statements)
        )
        return _Node(op, parsed, path=path)
    if op == "assign":
        name = node["name"]
        if not isinstance(name, str) or not name.isidentifier() \
                or name.startswith("_"):
            _fail(path + ".name", "assignment name must be a public identifier")
        value = _expr(node["value"], path + ".value", budget, depth + 1)
        return _Node(op, (name, value), path=path)

    kind, target = node["kind"], node["target"]
    if not isinstance(kind, str) or kind not in policy_action.ACTION_KINDS:
        _fail(path + ".kind", "kind must name the shared action contract")
    if not isinstance(target, str) or not target:
        _fail(path + ".target", "target must be a nonempty string")
    inputs = _expr(node["inputs"], path + ".inputs", budget, depth + 1)
    state = _expr(node["state"], path + ".state", budget, depth + 1)
    for field, parsed in (("inputs", inputs), ("state", state)):
        if not _compatible(parsed.kind, "object") and parsed.kind != "any":
            _fail(path + "." + field, "%s must evaluate to an object" % field)
    refs = node["evidence_refs"]
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        _fail(path + ".evidence_refs", "evidence_refs must be a list of strings")
    resources = node["requested_resources"]
    if type(resources) is not dict or not _json(resources, path + ".requested_resources"):
        _fail(path + ".requested_resources", "requested_resources must be a JSON object")
    return _Node(
        op,
        (kind, target, inputs, tuple(refs), deepcopy(resources), state),
        path=path,
    )


def _returns(node: _Node) -> bool:
    """Whether every path through `node` ends in a returned action.

    `assign` never returns. `if` returns only when both branches do.
    `block` returns when some statement returns and nothing after it can
    fall through, so a trailing `assign` after a `return_action` leaves
    unreachable code that is refused rather than silently accepted.
    """
    if node.op == "return_action":
        return True
    if node.op == "assign":
        return False
    if node.op == "if":
        _, then_branch, else_branch = node.value
        return _returns(then_branch) and _returns(else_branch)
    returns_at = None
    for index, statement in enumerate(node.value):
        if _returns(statement):
            returns_at = index
        elif returns_at is not None:
            _fail(statement.path, "unreachable statement after a returning one")
    return returns_at is not None


def _document(document: Any) -> tuple[dict, _Node]:
    path = "$.policy_ast"
    _exact(document, path, {"policy_id", "entry"})
    if not isinstance(document["policy_id"], str) or not document["policy_id"]:
        _fail(path + ".policy_id", "policy_id must be a nonempty string")
    return deepcopy(document), _stmt(document["entry"], path + ".entry", _Budget())


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _load(record: Any) -> tuple[dict, _Node]:
    artifact = _exact(record["artifact"], "$.artifact", {
        "kind", "representation", "version", "policy_id", "ast_digest",
    })
    fixed = {
        "kind": "learning-policy",
        "representation": "typed-ast",
        "version": _REPRESENTATION,
    }
    for field, expected in fixed.items():
        if artifact[field] != expected:
            _fail("$.artifact." + field, "must equal %r" % expected)
    document, entry = _document(record["policy_ast"])
    if not _returns(entry):
        _fail(entry.path, "program can complete without returning an action")
    if not isinstance(artifact["policy_id"], str) or not artifact["policy_id"]:
        _fail("$.artifact.policy_id", "policy_id must be a nonempty string")
    if artifact["policy_id"] != document["policy_id"]:
        _fail("$.policy_ast.policy_id", "does not match artifact policy_id")
    digest = hashlib.sha256(_canonical(document)).hexdigest()
    if artifact["ast_digest"] != digest:
        _fail("$.artifact.ast_digest", "does not match canonical AST bytes")
    return document, entry


def load_policy(record: Any, expected_policy_id: str) -> tuple[dict, _Node]:
    """Load an artifact and bind its policy identity to the caller's id."""
    if not isinstance(expected_policy_id, str) or not expected_policy_id:
        raise ValueError("expected_policy_id must be a nonempty string")
    document, entry = _load(record)
    if document["policy_id"] != expected_policy_id:
        _fail("$.policy_ast.policy_id", "does not match expected policy id")
    return document, entry


def _runtime_fail(path: str, detail: str) -> None:
    raise _ExecutionRefused(f"{path}: {detail}")


def _run_expression(node: _Node, env: dict) -> Any:
    path = node.path
    if node.op == "const":
        return deepcopy(node.value)
    if node.op == "list":
        return [_run_expression(item, env) for item in node.value]
    if node.op == "obj":
        return {key: _run_expression(value, env) for key, value in node.value}
    if node.op == "field":
        scope, name = node.value
        values = env[scope]
        if name not in values:
            if scope == "state" and node.kind == "any":
                return False
            _runtime_fail(path, "field %s.%s is unavailable" % (scope, name))
        return deepcopy(values[name])
    if node.op == "index":
        value, key = (_run_expression(child, env) for child in node.value)
        if isinstance(value, dict) and isinstance(key, str):
            if key not in value:
                _runtime_fail(path, "object key is unavailable")
            return deepcopy(value[key])
        if type(value) is not list or type(key) is not int:
            _runtime_fail(path, "index requires list and integer types")
        if not 0 <= key < len(value):
            _runtime_fail(path, "list index is out of range")
        return deepcopy(value[key])
    if node.op in ("add", "eq", "lt"):
        left, right = (_run_expression(child, env) for child in node.value)
        if node.op == "add":
            if isinstance(left, bool) or isinstance(right, bool):
                _runtime_fail(node.path, "add requires two numeric operands")
            return left + right
        if node.op == "eq":
            return _json_equal(left, right)
        return left < right
    return not _run_expression(node.value, env)


def _execute(node: _Node, env: dict):
    if node.op == "if":
        condition, then_branch, else_branch = node.value
        return _execute(then_branch if _run_expression(condition, env) else else_branch, env)
    if node.op == "block":
        for statement in node.value:
            result = _execute(statement, env)
            if result is not None:
                return result
        return None
    if node.op == "assign":
        name, expression = node.value
        env["state"][name] = _run_expression(expression, env)
        return None
    kind, target, inputs, refs, resources, state = node.value
    action = policy_action.parse_action({
        "kind": kind,
        "target": target,
        "inputs": _run_expression(inputs, env),
        "evidence_refs": list(refs),
        "requested_resources": deepcopy(resources),
    })
    return {"action": action.as_dict(), "state": _run_expression(state, env)}


def _execute_document(document: dict, view: dict, state: dict) -> dict:
    _, entry = _document(document)
    result = _execute(entry, {"view": deepcopy(view), "state": deepcopy(state)})
    if result is None:
        _runtime_fail(entry.path, "statement did not return an action")
    action, next_state = policy_action.parse_step_result(result)
    return {"action": action.as_dict(), "state": next_state}


def _child_main() -> int:
    request = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    limits = request["limits"]
    cpu_seconds = int(limits["cpu_seconds"])
    if cpu_seconds <= 0:
        raise ValueError("cpu_seconds must be positive")
    memory_bytes = limits.get("memory_bytes")
    if memory_bytes is not None:
        memory_bytes = int(memory_bytes)
        if memory_bytes <= 0:
            raise ValueError("memory_bytes must be positive")
    # Installed after the value is checked and before the document runs, so
    # the cap bounds this process and a refused value never reaches a child
    # that is already running unbounded. The parent has already refused a
    # host that cannot install these at all.
    support = child_limit_support()
    if not support.available:
        raise _ExecutionRefused(support.reason)
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    if memory_bytes is not None:
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    try:
        data = _execute_document(request["ast"], request["view"], request["state"])
        outcome = {"status": "ok", "data": data}
    except Exception as exc:
        outcome = {"status": "error", "error": str(exc) or type(exc).__name__}
    sys.stdout.write(json.dumps(outcome, allow_nan=False, separators=(",", ":")))
    return 0


def _run_step(document: dict, view: dict, state: dict, *,
              timeout_ms: int, cpu_seconds: int, max_output_bytes: int,
              memory_bytes: int | None) -> dict:
    """Run one step in a child interpreter.

    The document is re-parsed and re-typed in the child, so the
    parent's parsed tree is not sent and `entry` is not threaded
    through here. The parent still charges the node and depth budgets
    at load, so an oversized program is refused before any child is
    started.
    """
    request = {
        "ast": document,
        "view": view,
        "state": state,
        "limits": {"cpu_seconds": cpu_seconds, "memory_bytes": memory_bytes},
    }
    request_bytes = _canonical(request)
    if len(request_bytes) > policy_step.VIEW_LIMIT_BYTES:
        raise _ExecutionRefused("serialized AST step exceeds view byte cap")
    support = child_limit_support()
    if not support.available:
        # Refused here rather than in the child, so the host is reported as
        # unable to enforce the caps instead of a child dying on an import
        # and the reason reading like a program error.
        raise _ExecutionRefused(support.reason)
    with tempfile.TemporaryDirectory(prefix="ad01-boolean-ast-") as raw:
        work = Path(raw)
        request_path = work / "request.json"
        request_path.write_bytes(request_bytes)
        root = str(Path(__file__).resolve().parents[2])
        process = subprocess.Popen(
            [sys.executable, "-m", "experiments.ad01.boolean_ast_policy",
             "child", str(request_path)],
            cwd=work,
            env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0",
                 "PYTHONPATH": root},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_ms / 1000)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise _ExecutionRefused("wall timeout after %d ms" % timeout_ms) from None
    if len(stdout) > max_output_bytes or len(stderr) > max_output_bytes:
        raise _ExecutionRefused("AST step exceeded the output byte cap")
    if process.returncode != 0:
        detail = stderr.decode("utf-8", "replace")[-400:]
        raise _ExecutionRefused("child exited %d: %s" % (process.returncode, detail))
    try:
        outcome = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _ExecutionRefused("malformed child result: %s" % exc) from exc
    if not isinstance(outcome, dict) or outcome.get("status") not in ("ok", "error"):
        raise _ExecutionRefused("malformed child result envelope")
    if outcome["status"] == "error":
        raise _ExecutionRefused(str(outcome.get("error", "AST step failed")))
    if not isinstance(outcome.get("data"), dict):
        raise _ExecutionRefused("AST step data must be an object")
    return outcome["data"]


def _shared_schema(schema: Any) -> dict:
    if type(schema) is not dict or type(schema.get("actions")) is not dict:
        raise _ExecutionRefused("action schema must advertise actions")
    actions = deepcopy(schema["actions"])
    # Already in the shared spelling means the caller went through the
    # parity harness, which renames the world's `commit` to `construct`
    # before handing any arm a view. Renaming again found nothing to pop
    # and refused with "must advertise commit", so the AST could not run
    # under `compare_arms` at all — the graph survived only because its
    # own `make_view` swallows the exception. Idempotent is the whole fix.
    if policy_action.CONSTRUCT in actions:
        return {**deepcopy(schema), "actions": actions}
    if "commit" not in actions:
        raise _ExecutionRefused("action schema must advertise commit")
    actions[policy_action.CONSTRUCT] = actions.pop("commit")
    return {**deepcopy(schema), "actions": actions}


def _shared_view(public_state: dict) -> dict:
    if not isinstance(public_state, dict):
        raise _ExecutionRefused("public state must be an object")
    if "tables" in public_state:
        raise _ExecutionRefused("public state exposes hidden tables")
    required = {"instrument", "task_id", "split", "max_queries", "remaining",
                "observed", "hypothesis_class", "action_schema"}
    missing = sorted(required - set(public_state))
    if missing:
        # The parity harness hands every arm the six-field contract view,
        # and only this module required the world's own eight. The graph
        # arm gets away with it because `boolean_graph_policy.make_view`
        # calls `boolean_policy._shared_view` and catches whatever comes
        # back, so a shape the AST refused outright was a shape the graph
        # silently absorbed. `public_world` is where the three fields this
        # view nests live, so the projection is a re-nesting rather than a
        # reconstruction, and a caller cannot widen its own view by
        # sending one: the extra keys are read, not trusted.
        nested = public_state.get("public_world")
        if missing == ["hypothesis_class", "max_queries", "split"] \
                and isinstance(nested, dict) \
                and all(key in nested for key in missing):
            public_state = {**public_state, **nested}
            missing = []
    if missing:
        raise _ExecutionRefused("public state missing: %s" % ", ".join(missing))
    if type(public_state["remaining"]) is not int or public_state["remaining"] < 0:
        raise _ExecutionRefused("public state remaining must be a nonnegative integer")
    if not isinstance(public_state["observed"], list):
        raise _ExecutionRefused("public state observed must be a list")
    return {
        "instrument": public_state["instrument"],
        "task_id": public_state["task_id"],
        "observed": deepcopy(public_state["observed"]),
        "remaining": public_state["remaining"],
        "public_world": {
            "split": public_state["split"],
            "max_queries": public_state["max_queries"],
            "hypothesis_class": deepcopy(public_state["hypothesis_class"]),
        },
        "action_schema": _shared_schema(public_state["action_schema"]),
    }


def _validate_action(action: policy_action.Action, view: dict) -> None:
    """Admit one action under the Boolean world's rules.

    These checks are why this executor is a *Boolean* arm and not a
    portable one. `contract_view` in `s09_arm_parity` renames a world's
    advertised `commit` to the contract's `construct`; the constructor
    must instead be the Boolean world's own spelling.

    A conforming action for the ordering-constraints world
    (`probe`/`schedule.compare`, `construct`/`schedule.commit`,
    `stop`/`schedule.task`) is refused here, so this node set has no
    second-world arm. That is an expressivity limit of the frozen
    executor, recorded in `expressivity_limits`, and not a naming
    artifact of the schema rename.
    """
    if action.kind == policy_action.PROBE:
        if action.target != "boolean.query":
            raise policy_action.ActionRefused("probe target must be boolean.query")
        value = action.inputs.get("x")
        if type(value) is not int or not 0 <= value <= 15:
            raise policy_action.ActionRefused("probe x must be an integer in 0..15")
        if any(item.get("x") == value for item in view["observed"]):
            raise policy_action.ActionRefused("input %d was already queried" % value)
        if view["remaining"] <= 0:
            raise policy_action.ActionRefused("query budget is exhausted")
    elif action.kind == policy_action.CONSTRUCT:
        if action.target != "boolean.commit":
            raise policy_action.ActionRefused("construct target must be boolean.commit")
        try:
            rules.execute_all({"specs": action.inputs.get("specs")})
        except rules.RuleRefused as exc:
            raise policy_action.ActionRefused(str(exc)) from exc
    elif action.kind == policy_action.STOP:
        if action.target != "boolean.task":
            raise policy_action.ActionRefused("stop target must be boolean.task")
    else:
        raise policy_action.ActionRefused(
            "action %r is not available in the Boolean world" % action.kind
        )


def _refusal(exc: Exception) -> dict:
    return {
        "kind": policy_action.STOP,
        "target": "boolean.task",
        "inputs": {"bridge_refusal": {
            "stage": "ast-policy-step",
            "reason": (str(exc) or type(exc).__name__)[:500],
        }},
        "evidence_refs": [],
        "requested_resources": {},
    }


def _positive(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("%s must be a positive integer" % name)
    return value


def ast_step(record: dict, public_state: dict, state: dict | None = None, *,
             timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
             cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
             max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
             memory_bytes: int | None = None) -> dict:
    """Run one AST step and return the action with the next step state.

    `public_state` is the world's public state, the same object
    `run_episode` hands a decide callback, and not the six-field
    contract view. The step owns that projection so a caller cannot
    hand the program a view it assembled itself.

    `choose_action` closes over its state instead, which is the right
    shape for one process driving a whole episode and the wrong shape
    for the `policy_action.state_contract` promise that the step state
    is "carried between steps and across processes". This is the entry
    that keeps that promise deliverable: the caller owns the state, so a
    fresh interpreter can resume mid-episode from the same state.

    Returns `{"action": <shared action>, "state": <next state>}`, the
    exact `parse_step_result` payload. Unlike `choose_action` it raises
    on refusal rather than converting the failure into a recorded
    `stop`, so a caller retrying a step sees the failure instead of a
    policy that looks like it chose to stop.
    """
    document, _ = _load(record)
    timeout_ms = _positive(timeout_ms, "timeout_ms")
    cpu_seconds = _positive(cpu_seconds, "cpu_seconds")
    max_output_bytes = _positive(max_output_bytes, "max_output_bytes")
    if memory_bytes is not None:
        memory_bytes = _positive(memory_bytes, "memory_bytes")
    if state is None:
        state = {}
    policy_step.validate_state(state)
    shared = _shared_view(public_state)
    result = _run_step(
        document, shared, state,
        timeout_ms=timeout_ms, cpu_seconds=cpu_seconds,
        max_output_bytes=max_output_bytes, memory_bytes=memory_bytes,
    )
    action, next_state = policy_action.parse_step_result(result)
    _validate_action(action, shared)
    policy_step.validate_state(next_state)
    return {"action": action.as_dict(), "state": next_state}


def choose_action(record: dict, *,
                  timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
                  cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
                  max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
                  memory_bytes: int | None = None):
    """Return the Boolean episode callback for one canonical AST record."""
    document, _ = _load(record)
    timeout_ms = _positive(timeout_ms, "timeout_ms")
    cpu_seconds = _positive(cpu_seconds, "cpu_seconds")
    max_output_bytes = _positive(max_output_bytes, "max_output_bytes")
    if memory_bytes is not None:
        memory_bytes = _positive(memory_bytes, "memory_bytes")
    state: dict = {}

    def decide(public_state: dict) -> dict:
        nonlocal state
        try:
            view = _shared_view(public_state)
            policy_step.validate_state(state)
            result = _run_step(
                document,
                view,
                state,
                timeout_ms=timeout_ms,
                cpu_seconds=cpu_seconds,
                max_output_bytes=max_output_bytes,
                memory_bytes=memory_bytes,
            )
            action, next_state = policy_action.parse_step_result(result)
            _validate_action(action, view)
            policy_step.validate_state(next_state)
            state = next_state
            return action.as_dict()
        except Exception as exc:
            return _refusal(exc)

    return decide


def expressivity_limits() -> dict:
    """What the frozen node set can and cannot express, per world.

    The campaign requires an expressivity limit to be recorded rather
    than worked around with a substitute interpreter, and every entry
    here is a measured refusal. `tests/test_s09ast_expressivity.py`
    drives each `cannot` row back through the loader and asserts the
    refusal text, so a limit that stops being true fails the suite
    instead of quietly becoming a claim.
    """
    return {
        "version": "s09-ast-expressivity/1",
        "representation": _REPRESENTATION,
        "frozen_limits": {
            "max_nodes": MAX_NODES,
            "max_depth": MAX_DEPTH,
            "max_integer_bits": MAX_INTEGER_BITS,
            "max_block_statements": MAX_BLOCK_STATEMENTS,
            "request_byte_cap": policy_step.VIEW_LIMIT_BYTES,
            "state_byte_cap": policy_step.STATE_LIMIT_BYTES,
            "step_timeout_ms": policy_step.STEP_TIMEOUT_MS,
            "step_cpu_seconds": policy_step.STEP_CPU_SECONDS,
            "step_max_output_bytes": policy_step.STEP_MAX_OUTPUT_BYTES,
        },
        "worlds": {
            "boolean-rule": {
                "can": [
                    "read every field of the contract view",
                    "rebranch on any view field each step, so a policy "
                    "may keep no state at all and still be contingent",
                    "select an action's inputs from the observations, so "
                    "the committed predictor differs by world",
                    "recover an affine mask over a subset of the four "
                    "input weights, up to the node budget measured below",
                ],
                "cannot": [
                    {"behavior": "exact recovery of all four affine mask "
                                 "bits for all four outputs",
                     "missing_cell": "no arithmetic on a computed state value",
                     "witness": "a 4-output learner over the four weight "
                                "inputs is refused with 'policy exceeds "
                                "256 nodes'; combining two recovered weight "
                                "bits into one mask is what overruns the "
                                "budget, because the only way to combine "
                                "them is an if-cascade whose size is the "
                                "product of the bit count and the number "
                                "of cases"},
                    {"behavior": "a learned comparison against a number",
                     "missing_cell": "`lt` rejects a state or observation "
                                      "value, and the loader's type tag "
                                      "for both is not numeric",
                     "witness": "`lt(state.m, 8)` is refused with 'lt "
                                "requires two numeric operands'"},
                ],
            },
            "ordering-constraints": {
                "can": [],
                "cannot": [
                    {"behavior": "any action at all",
                     "missing_cell": "the constructor admits only the "
                                      "Boolean world's action targets",
                     "witness": "`probe`/`schedule.compare` is refused "
                                "with 'probe target must be boolean.query' "
                                "even with the schema rename patched out, "
                                "so this is the executor's own limit and "
                                "not an artifact of the world's spelling"},
                ],
            },
        },
        "measured_frontier": {
            "note": "nodes charged by the loader for the largest learner "
                    "that still loads, per output bits and weight inputs",
            "grid": [
                {"output_bits": 1, "probes": 2, "nodes": 65, "loads": True},
                {"output_bits": 1, "probes": 3, "nodes": 102, "loads": True},
                {"output_bits": 1, "probes": 4, "nodes": 154, "loads": True},
                {"output_bits": 1, "probes": 5, "nodes": 236, "loads": True},
                {"output_bits": 2, "probes": 2, "nodes": 108, "loads": True},
                {"output_bits": 2, "probes": 3, "nodes": 174, "loads": True},
                {"output_bits": 2, "probes": 4, "nodes": None,
                 "loads": False},
                {"output_bits": 3, "probes": 2, "nodes": 151, "loads": True},
                {"output_bits": 3, "probes": 3, "nodes": 246, "loads": True},
                {"output_bits": 3, "probes": 4, "nodes": None,
                 "loads": False},
                {"output_bits": 4, "probes": 2, "nodes": 194, "loads": True},
                {"output_bits": 4, "probes": 3, "nodes": None,
                 "loads": False},
            ],
            "reading": "the Boolean world commits four class members, so a "
                       "four-output learner is the smallest that could "
                       "recover the class, and it loads at two probes and "
                       "is refused at three",
        },
        "enforcement": {
            "load_time": "node count, depth, integer width, block length, "
                         "returning on every path, and every node's type "
                         "and field set",
            "per_step": "wall timeout, output byte cap, and policy state "
                        "byte cap are all proven to fire by exceeding them",
            "process": "each step runs in a child with a scrubbed "
                       "environment and its own working directory",
            "memory": "RLIMIT_AS is installed and fires, raising "
                      "MemoryError inside the child",
            "cpu": "RLIMIT_CPU is installed and the child validates the "
                   "value, but no legal program reaches it: the widest "
                   "document the loader admits finishes in well under a "
                   "second against a one-second resolution. The load-time "
                   "node budget is the limit that actually binds CPU.",
            "host": "RLIMIT_CPU and RLIMIT_AS are POSIX rlimits. A host "
                    "that cannot install them is refused before a child is "
                    "started, reported by `child_limit_support`; the caps "
                    "are never dropped so a step can still run.",
            "not_claimed": "there is no OS-level sandbox. The child shares "
                           "this uid, the filesystem and the network with "
                           "the parent. The interpreter is closed, which is "
                           "a property of the grammar, and the child is a "
                           "resource boundary, not a security boundary.",
        },
    }


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "child":
        raise SystemExit(_child_main())
    raise SystemExit("expected private child invocation")
