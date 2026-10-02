"""Acquired methods run through the bounded local-process profile (BDR-01).

The host owns the query budget and exposes only JSON oracle verdicts.
Local-process provides process separation, not hostile-code containment.

The child contract's wrappers are generated per binding from the callee's
own signature. The uniform template they replaced gave every binding
`(task, oracle, *, method="ddmin", max_queries=16)`, and four of the six
do not have that shape, so a member that trusted the contract and omitted
`method` still ran, on ddmin, without choosing it. A generated wrapper
passes a strategy through and never supplies one, so omitting it fails
execution; a binding needing a value the child cannot supply and the menu
does not offer as a choice is refused when the contract is built.
`verify_child_contract` is that refusal, and `run_member_out_of_process`
calls it before anything is staged.
"""

from __future__ import annotations

import ast
import hashlib
import json
import socket
import sys
import tempfile
import threading
from contextlib import nullcontext
from pathlib import Path

from experiments.representation import checkers
from settlement import broker
from settlement.common import ResultCode, payload_digest
from settlement.launcher_local import PROFILE, LocalLauncher

DEFAULT_TIMEOUT_MS = 30_000
MAX_FRAME_BYTES = 4 * 1024 * 1024

_FORBIDDEN_CALLS = frozenset([
    "open", "exec", "eval", "compile", "__import__", "input",
    "breakpoint", "exit", "quit", "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "dir", "help", "type", "memoryview"])


class MethodExecutionError(Exception):
    pass


CHILD_CONTRACT_VERSION = "ad01-child-v1"

# The budget a child wrapper hands its callee when the model does not ask
# for one. It is a budget, not a strategy: no wrapper passes `method`.
DEFAULT_CHILD_BUDGET = 16

# The name a wrapper accepts the budget under, when the callee declares
# none of its own. `max_queries` and not `budget`, because every archived
# member and every seed source in the campaign already spells it that way
# and a rename breaks eleven archived executions for no gain. The
# parameter's own name is used whenever the callee declares one.
DEFAULT_CHILD_BUDGET_PARAM = "max_queries"

# The key a reduction primitive returns its surviving atom indices under.
# The child adapter rebuilds the candidate from it, so a primitive that
# returned a different key would hand the model a candidate it did not
# reach, and the adapter would be wrong in a way no signature check sees.
_RETURN_KEY = "kept"

# The values a menu asks the model for, and that no wrapper may ever
# supply. `method` is here because it is the choice the whole comparison
# turns on, and it was the one value a uniform wrapper handed out for
# free. A binding requiring one of these is buildable; a binding
# requiring anything else the child cannot supply is not.
_CHOICE_PARAMS = frozenset({"method", "priority"})


def _callables() -> dict:
    """The menu's entries, without their signatures.

    Separate from `child_contract` because the signatures are rendered
    from the wrappers, and the wrappers are generated from this. Signing
    the table here and building the wrappers from the signed table is
    the loop that kept a hand-written string and a generated wrapper
    disagreeing about the same call.
    """
    callables = {
        # A callable with a binding is executed in the child. A callable
        # without one is a host affordance (`oracle.query`) and never is.
        # The distinction decides the refusal in `verify_child_contract`,
        # and it is stated because the two lists are read as one menu
        # and a model cannot tell which is which.
        "software_atoms": {
            "returns": "tuple (build, priority) for the software family",
            "origin": "authored-supplied-rpr01",
            "binding": "reducers.software_atoms",
        },
        "graph_atoms": {
            "returns": "tuple (build, priority) for the graph family",
            "origin": "authored-supplied-rpr01",
            "binding": "reducers.graph_atoms",
        },
        "reduce_software": {
            "returns": ("dict with candidate (software-shaped) and "
                        "queries used"),
            "origin": "authored-supplied-rpr01",
            "binding": "reducers.reduce_software",
        },
        "reduce_graph": {
            "returns": ("dict with candidate (graph-shaped) and "
                        "queries used"),
            "origin": "authored-supplied-rpr01",
            "binding": "reducers.reduce_graph",
        },
        "oracle.query": {
            "returns": ("the verdict report for that candidate; "
                        "past the query budget it returns unknown "
                        "with reason budget-exhausted"),
            "origin": "host-oracle",
        },
    }
    # The menu is a menu or it is not. Four of the five entries above can
    # be built, but only `reduce_software` and `reduce_graph` are direct
    # reducers; a control column drawn from a menu of two names is not a
    # comparison, and the two composed entries are what makes the two
    # strategies reachable by name without `reduce_*` to dispatch them.
    for method, name in sorted(_STRATEGY_METHODS.items()):
        callables[name] = {
            "returns": "dict with kept, queries, accepted, status, candidate",
            "origin": "authored-supplied-rpr01",
            "binding": "reducers.%s" % name,
        }
        callables["%s__%s" % (method, name)] = {
            "returns": "dict with kept, queries, accepted, status, candidate",
            "origin": "authored-composed",
            "binding": "reducers.%s" % name,
        }
    return callables


def child_contract() -> dict:
    callables = _callables()
    wrappers = _wrapper_signatures({"callables": callables})
    for name, spec in callables.items():
        spec["signature"] = _rendered_signature(name, spec, wrappers)
    return {
        "version": CHILD_CONTRACT_VERSION,
        "entry": entry_contract()["params"],
        "callables": callables,
        "binding_rule": ("a callable carrying `binding` is executed in the"
                         " child; a callable without one is a host affordance"
                         " and is never executed"),
        "choice_rule": (
            "A binding may require %s. The child wrapper accepts these as"
            " keyword arguments and supplies no value for them, so a"
            " member that omits one fails execution and a member that"
            " supplies one is the only thing that ever reaches the"
            " callee. A binding requiring any other value the child cannot"
            " supply is refused when the contract is built, not defaulted."
            % (list(_CHOICE_PARAMS),)),
        "adapters": (
            "The two reduction primitives take atoms rather than a task, and"
            " the child cannot invent atoms. The child adapter below binds"
            " them to `task` and `oracle` exactly as reduce_software and"
            " reduce_graph do, so composing the primitives by hand and"
            " calling the composed reducers are the same bytes. A primitive"
            " whose return shape the adapter cannot adapt is not offered."),
    }


# The child namespace, and the only host module a binding may name. The
# child binds `reducers` under exactly this name, so the host's
# resolution has to go through the same table rather than through the
# host's own import machinery, where `reducers` is a name nobody binds.
_CHILD_NAMESPACE = {"reducers": "experiments.representation.reducers"}


def _bound_names(contract: dict) -> list:
    return sorted(name for name, spec in contract["callables"].items()
                  if spec.get("binding") is not None)


def _resolve_binding(target: str) -> object:
    """The callable a binding names, refused if the name does not resolve.

    Resolution is by attribute walk from the child namespace, never by the
    last dotted segment. `ddmin_reduce` and `reduce_software` are both
    reducers whose own name does not contain the string `ddmin`, and a
    name-matched resolution would have found `reduce_software` for both.
    """
    import importlib

    module_name, _, attribute = target.rpartition(".")
    if not module_name or not attribute:
        raise MethodExecutionError("refused: binding is not a dotted path")
    if module_name not in _CHILD_NAMESPACE:
        raise MethodExecutionError(
            "refused: binding names module %r, which the child does not"
            " bind" % module_name)
    try:
        module = importlib.import_module(_CHILD_NAMESPACE[module_name])
    except (ImportError, ValueError) as exc:
        raise MethodExecutionError(
            "refused: binding module %r does not import"
            % module_name) from exc
    target_object = getattr(module, attribute, None)
    if not callable(target_object):
        raise MethodExecutionError(
            "refused: binding %r does not name a callable" % target)
    return target_object


def _binding_profile(target_object: object) -> dict:
    """What a wrapper must pass, read off the callable rather than a string.

    Every field the child can supply has a name the callable can receive.
    The child's two are `task` and `oracle`; the child's budget keyword is
    whichever of `max_queries` or `priority` the callee declares with a
    default, so the two never compete. A required name on neither list is
    the model's to answer, and a required name that is neither child-side
    nor a choice is a binding the wrapper cannot honestly build, so it
    refuses rather than inventing a value.
    """
    import inspect

    try:
        signature = inspect.signature(target_object)
    except (TypeError, ValueError) as exc:
        raise MethodExecutionError(
            "refused: binding signature is not introspectable") from exc
    parameter = inspect.Parameter
    signature_parameters = signature.parameters
    kinds = {name: value.kind for name, value in signature_parameters.items()}
    required = [name for name, value in signature_parameters.items()
                if value.default is inspect.Parameter.empty
                and value.kind in (parameter.POSITIONAL_ONLY,
                                   parameter.POSITIONAL_OR_KEYWORD,
                                   parameter.KEYWORD_ONLY)]
    budget = _budget_parameter(signature_parameters)
    budget_param = budget or DEFAULT_CHILD_BUDGET_PARAM
    supplies = {
        name: "task" if name == "task" else "oracle" for name in kinds
        if name in ("task", "oracle")
    }
    keyword_only = sorted(name for name, kind in kinds.items()
                          if kind == parameter.KEYWORD_ONLY)
    return {
        "name": target_object.__name__,
        "parameters": sorted(kinds),
        "required": sorted(required),
        "supplies": supplies,
        "choices": [name for name in required if name in _CHOICE_PARAMS],
        "keyword_only": keyword_only,
        "budget": budget_param,
        "bindable": [name for name in required if name not in supplies
                     and name not in _CHOICE_PARAMS],
    }


def _budget_parameter(signature_parameters) -> str | None:
    """The parameter a child's `budget` stands for, or None if it has none.

    `max_queries` and `priority` are both budgets the model may vary, and
    one of them may hold a default. Which one is read here, so the default
    belongs to the model and not to the wrapper. A budget the callee
    declares required is not one: a wrapper defaulting it would be choosing
    the budget for the model, which is the same defect as choosing the
    strategy for it.
    """
    import inspect

    empty = inspect.Parameter.empty
    for name in ("max_queries", "priority"):
        parameter = signature_parameters.get(name)
        if parameter is not None and parameter.default is not empty \
                and parameter.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY):
            return name
    return None


def _wrapper_for(name: str, target: str, profile: dict) -> str:
    """One wrapper, generated for one binding, with no strategy default.

    A binding needing a value the child cannot supply and the model was
    never asked for raises here, so a menu entry can never run with an
    authored answer standing in for a choice. `method` is a choice, so it
    is passed through and never supplied: that is the whole difference
    between this and the uniform template that made every acquisition
    greedy without its model choosing greedy.
    """
    missing = profile["bindable"]
    if missing:
        raise MethodExecutionError(
            "refused: %s requires %s, which the child cannot supply and"
            " the menu does not offer as a choice; the wrapper would have"
            " to invent a value" % (target, ", ".join(missing)))
    passed = ", ".join("%s=%s" % (parameter, source)
                       for parameter, source in sorted(
                           profile["supplies"].items()))
    return ("def %s(task, oracle, *, %s=%d, **kwargs):\n"
            "    return %s(%s, **kwargs)\n"
            % (name, profile["budget"] or DEFAULT_CHILD_BUDGET_PARAM,
               DEFAULT_CHILD_BUDGET, target, passed))


# The child adapter for the two reduction primitives. They take atoms
# rather than a task, and the child holds a task and an oracle, so the
# adapter reads the family's atom source, passes the task's own atom
# count, and threads the oracle through. It is what makes the primitives
# offered at all: a wrapper built from a signature alone would refuse
# them for needing `count`, `build` and `probe`, which is where four of
# the six bindings were left with a signature no callee had.
#
# The adapter passes the family's authored priority to `greedy_reduce`,
# which is what `reduce_software` and `reduce_graph` do. A member that
# wants a different one passes `priority` and the adapter uses it.
_CHILD_ADAPTER_SUPPORT = (
    "def __atom_source(family):\n"
    "    if family == 'software':\n"
    "        return reducers.software_atoms\n"
    "    if family == 'graph':\n"
    "        return reducers.graph_atoms\n"
    "    raise ValueError('unknown-family')\n"
    "def __atom_count(task, family):\n"
    "    if family == 'software':\n"
    "        return len(task['ops'])\n"
    "    if family == 'graph':\n"
    "        return len(task['vertices']) + len(task['edges'])\n"
    "    raise ValueError('unknown-family')\n"
    "def __probe(oracle):\n"
    # The oracle already returns a report shaped {"verdict": ...}, which
    # is exactly what a primitive subscripts. Wrapping it again makes the
    # verdict a dict, every comparison against the string PRESERVED fail,
    # and the primitive return the incumbent after one query on every
    # task. `reduce_software` passes the oracle straight through for the
    # same reason.
    "    return lambda candidate: oracle.query(candidate)\n"
    "def __candidate(build, result):\n"
    "    return build(result['%(kept)s'])\n"
)

# A primitive name, and the strategy its composed entry fixes. Read
# together so `ddmin__ddmin_reduce` is one declared pair and not a name
# parsed back apart by each caller.
_PRIMITIVE_ADAPTERS = {
    "ddmin_reduce": (
        "def __adapt_ddmin_reduce(task, oracle, *, family, method=None,\n"
        "                       priority=None, max_queries=16):\n"
        "    if method not in (None, 'ddmin'):\n"
        "        raise ValueError('unknown-method')\n"
        "    build, authored = __atom_source(family)(task)\n"
        "    result = reducers.ddmin_reduce(\n"
        "        __atom_count(task, family), build, __probe(oracle),\n"
        "        max_queries=max_queries)\n"
        "    result['candidate'] = __candidate(build, result)\n"
        "    return result\n"),
    "greedy_reduce": (
        "def __adapt_greedy_reduce(task, oracle, *, family, method=None,\n"
        "                          priority=None, max_queries=16):\n"
        "    if method not in (None, 'greedy'):\n"
        "        raise ValueError('unknown-method')\n"
        "    build, authored = __atom_source(family)(task)\n"
        "    result = reducers.greedy_reduce(\n"
        "        __atom_count(task, family), build, __probe(oracle),\n"
        "        priority=authored if priority is None else priority,\n"
        "        max_queries=max_queries)\n"
        "    result['candidate'] = __candidate(build, result)\n"
        "    return result\n"),
}

_STRATEGY_METHODS = {"ddmin": "ddmin_reduce", "greedy": "greedy_reduce"}

# The strategies a member may choose between by name. Written out here
# because they are a property of the campaign, not of any callee's
# signature: the model has to be told the menu, and the wrapper must supply
# nothing from it. The text is load-bearing. It is the open menu, and it is
# the reason a member that omits `method` fails execution rather than
# running on the authored answer.
_STRATEGY_MENU = "one of \"ddmin\" or \"greedy\"; you must name one"

_KEYWORD_ONLY_NOTE = ("everything after * is a keyword argument; passing"
                      " one positionally raises TypeError")

_FORWARDED_CHOICE_NOTE = (
    "**kwargs forwards a keyword the callee declares, so %s must be passed"
    " by name and the wrapper supplies no value for it")

_COMPOSED_NOTE = ("the strategy is fixed to %r and you cannot choose"
                  " another")

_GUARD_NOTE = ("%s has no value of its own: omit it and this entry runs the"
               " strategy it is named for, and passing any other name"
               " raises ValueError")


def _composed_strategy(name: str) -> str | None:
    """The strategy a composed name commits to, or None if it is not one.

    Split on `__` by the same rule `_composed_method` uses, and read
    through that function rather than repeated here, so a name is parsed
    one way. The note is load-bearing in the other direction from the menu
    note: a control column is drawn by naming one of these, and a member
    that believed it could choose differently would be wrong.
    """
    return _composed_method(name) if "__" in name else None


def _rendered_signature(name: str, spec: dict, wrappers: dict) -> str:
    """The call form of the wrapper the child binds, read off the wrapper.

    The prose and the wrapper were two hand-maintained descriptions of one
    call, and they drifted: the table declared `method` as the third
    positional argument while `_wrapper_for` bound it keyword-only, so a
    model that obeyed the contract passed `verify_member` and died with a
    `TypeError` in the child. Rendering from the wrapper's own
    `inspect.signature` makes the `*` a fact about the binding rather than
    about a string.

    The wrapper is what is rendered, not the callee. A member cannot call
    the callee — the child binds the wrapper under the menu name — and
    the callee's own parameter list is not the wrapper's either: the
    wrapper forwards a choice through `**kwargs`, and `**kwargs` is not a
    name a model can write, so a callee rendering would hand the model a
    `method` position the bytes refuse.

    Defaults are rendered too. A default is what a model reads to decide
    it need not choose, and `max_queries` is a budget rather than an
    answer, so hiding one and showing the other is the difference the
    whole comparison turns on.
    """
    if spec.get("binding") is None:
        return "oracle.query(candidate)"
    wrapper = wrappers.get(name)
    if wrapper is None:
        raise MethodExecutionError(
            "refused: %r has a binding but the child binds no wrapper for it"
            % name)
    positional, keyword_only, var_keyword, guarded = _split_keyword_only(
        wrapper, name, spec)
    choices = _binding_choices(spec)
    notes = []
    if choices and not guarded:
        notes.append(_STRATEGY_MENU)
    if keyword_only:
        notes.append(_KEYWORD_ONLY_NOTE)
    if var_keyword and choices:
        notes.append(_FORWARDED_CHOICE_NOTE % ", ".join(
            "'%s'" % choice for choice in choices))
    if guarded:
        notes.append(_GUARD_NOTE % " and ".join(
            "'%s'" % parameter for parameter in guarded))
    composed = _composed_strategy(name)
    if composed is not None:
        notes.append(_COMPOSED_NOTE % composed)
    return " ".join(
        ["%s(%s)" % (name, ", ".join(positional + ["*"] + keyword_only
                                      + var_keyword))] + notes)


def _binding_choices(spec: dict) -> list:
    """The choices a member must name to call this entry, or none.

    Read from the callee through `_binding_profile`, which derives the
    list from `inspect.signature`. The wrapper forwards these through
    `**kwargs` rather than declaring them, so the callee is the only
    place the names are written down.
    """
    if spec.get("binding") is None:
        return []
    return _binding_profile(_resolve_binding(spec["binding"]))["choices"]


def _split_keyword_only(wrapper, name: str, spec: dict) -> tuple:
    """A bound wrapper's parameters, split by the kind that decides a call.

    `inspect` already marks what follows a `*` as KEYWORD_ONLY, so this
    renders that region behind the separator rather than re-deriving it:
    a parameter listed after the `*` is one a call cannot pass positionally,
    and one listed before it is one it can. `**kwargs` is rendered by name
    because it is the route a choice takes into the callee, and a model
    cannot write a value for it — only a keyword the callee declares.

    A parameter whose default is the strategy is the one case where a
    default is not rendered as `name=value`. The adapted primitives
    declare `method=None` to check that a name matches the strategy the
    entry is already named for; there is no value behind the `None`, and
    writing `method=None` would both be a lie about the call and read, to
    the two gates that watch for a defaulted strategy, as a menu
    answering itself. Such a parameter is left unrendered and described in
    the notes. `priority` is not swept in with it: a `None` priority is
    the authored order inside one strategy, which a member may replace
    and the gates treat as a budget rather than an answer.
    """
    import inspect

    parameter = inspect.Parameter
    positional, keyword_only, var_keyword, guarded = [], [], [], []
    for value in wrapper.parameters.values():
        is_guard = (value.name == "method" and value.default is None)
        rendered = (value.name if is_guard or value.default is parameter.empty
                    else "%s=%r" % (value.name, value.default))
        if is_guard:
            guarded.append(value.name)
        if value.kind is parameter.VAR_KEYWORD:
            var_keyword.append("**" + value.name)
        elif value.kind is parameter.VAR_POSITIONAL:
            raise MethodExecutionError(
                "refused: a bound wrapper takes *args, so its rendered"
                " signature would not describe the call")
        elif value.kind is parameter.KEYWORD_ONLY:
            keyword_only.append(rendered)
        else:
            positional.append(rendered)
    if guarded and _adapter_for(name, _binding_profile(
            _resolve_binding(spec["binding"]))) is None:
        raise MethodExecutionError(
            "refused: %r defaults %s to None outside the adapter that"
            " checks it, where the default would reach the callee"
            % (name, ", ".join(guarded)))
    return positional, keyword_only, var_keyword, guarded


def _wrapper_signatures(contract: dict | None = None) -> dict:
    """The child's wrappers, built and introspected, keyed by menu name.

    The wrappers are the bytes the model has to be able to call, and they
    are generated per binding from `inspect.signature`. Reading the
    contract's prose off them means there is one description of a call and
    it is the one that runs; a wrapper that does not build refuses here
    instead of leaving a menu entry with a signature nothing implements.

    Built from `_callables`, never from `child_contract`, because the
    contract is what is being rendered from these.
    """
    import inspect

    if contract is None:
        contract = {"callables": _callables()}
    namespace = {"reducers": _import_reducers()}
    try:
        source = _child_wrapper_source(contract)
        exec(compile(source, "<child-wrappers>", "exec"),  # noqa: S102
             namespace)
    except Exception as exc:
        raise MethodExecutionError(
            "refused: the child wrappers do not build") from exc
    return {name: inspect.signature(namespace[name])
            for name in _bound_names(contract) if name in namespace}


def _import_reducers() -> object:
    """The module the child's namespace binds, resolved the child's way."""
    import importlib

    return importlib.import_module(_CHILD_NAMESPACE["reducers"])


def _adapter_for(name: str, profile: dict) -> str | None:
    """An adapter for a primitive that takes atoms, or None if it fits.

    Bound by name, never by a suffix match. A suffix match is what mistook
    `ddmin_reduce` for a dispatcher of `method=ddmin`, and the menu grew a
    `method` default on a callable that has no `method` parameter.
    """
    if name in _PRIMITIVE_ADAPTERS and "count" in profile["parameters"]:
        return _PRIMITIVE_ADAPTERS[name]
    return None


def _composed_method(name: str) -> str:
    """The strategy a composed name fixes, read from the primitive it wraps.

    Split on `__` and not on the last dotted segment. `ddmin__ddmin_reduce`
    carries `ddmin` twice, and a reader looking for the nearest strategy
    token finds the primitive's own name, which is a different thing from
    the strategy the wrapper commits to.
    """
    head, separator, _ = name.partition("__")
    if not separator or head not in _STRATEGY_METHODS:
        raise MethodExecutionError(
            "refused: %r is not a composed menu entry" % name)
    return head


def _composed_source(name: str) -> str | None:
    """The wrapper for a composed entry, or None if the name is not one."""
    if "__" not in name:
        return None
    method = _composed_method(name)
    primitive = name.split("__", 1)[1]
    return ("def %s(task, oracle, *, %s=%d):\n"
            "    return __adapt_%s(task, oracle, family=task['family'],\n"
            "                         method=%r, max_queries=%s)\n"
            % (name, DEFAULT_CHILD_BUDGET_PARAM, DEFAULT_CHILD_BUDGET,
               primitive, method, DEFAULT_CHILD_BUDGET_PARAM))


def _adapter_source(contract: dict) -> str:
    blocks = [_CHILD_ADAPTER_SUPPORT % {"kept": _RETURN_KEY}]
    for name in _bound_names(contract):
        target = contract["callables"][name]["binding"]
        profile = _binding_profile(_resolve_binding(target))
        template = _adapter_for(name, profile)
        if template is None:
            continue
        if profile["name"] != name:
            raise MethodExecutionError(
                "refused: binding %r for %s names a callable called %r,"
                " and the child adapter is written for the reduction"
                " primitives" % (target, name, profile["name"]))
        blocks.append(template)
    return "\n".join(blocks) + "\n"


def _child_wrapper_source(contract: dict | None = None) -> str:
    """The child's wrappers, one per binding, each built from its signature.

    This replaced a single template that every binding was asked to wear:
    `(task, oracle, *, method="ddmin", max_queries=16)`. Four of the six
    do not have that shape, so the template supplied a `method` the
    contract had said there was no default for, and supplied arguments for
    parameters the callable does not have. A binding still needs a value
    the child cannot supply and the menu does not offer as a choice; that
    one refuses here, naming the callable, rather than executing a default
    nobody chose.
    """
    contract = child_contract() if contract is None else contract
    blocks = [_adapter_source(contract)]
    for name in _bound_names(contract):
        target = contract["callables"][name]["binding"]
        composed = _composed_source(name)
        if composed is not None:
            blocks.append(composed)
            continue
        profile = _binding_profile(_resolve_binding(target))
        adapted = _adapter_for(name, profile)
        if profile["name"] != name and adapted is None:
            raise MethodExecutionError(
                "refused: binding %r for %s names a callable called %r"
                % (target, name, profile["name"]))
        if adapted is not None:
            blocks.append("def %s(task, oracle, *, family, method=None,\n"
                          "            priority=None, max_queries=%d):\n"
                          "    return __adapt_%s(task, oracle, family=family,"
                          " method=method,\n"
                          "                         priority=priority,"
                          " max_queries=max_queries)\n"
                          % (name, DEFAULT_CHILD_BUDGET, name))
            continue
        blocks.append(_wrapper_for(name, target, profile))
    return "\n".join(blocks)


def verify_child_contract(contract: dict | None = None) -> dict:
    """The menu, or a refusal naming the callable that cannot be built.

    Called before any child is staged, so a member is never run against a
    wrapper that would hand it a strategy it did not choose. Raises rather
    than returning a reason, because every caller is a gate.
    """
    contract = child_contract() if contract is None else contract
    if contract.get("version") != CHILD_CONTRACT_VERSION:
        raise MethodExecutionError("refused: unknown child contract version")
    wrappers = _child_wrapper_source(contract)
    return {
        "version": contract["version"],
        "bound": _bound_names(contract),
        "host_only": sorted(set(contract["callables"])
                            - set(_bound_names(contract))),
        "wrappers": wrappers,
    }


def _child_binding_source() -> str:
    contract = child_contract()
    return ("\n".join(
        "module.__dict__[%r] = %s" % (name, name)
        for name in _bound_names(contract)) + "\n")


def entry_contract() -> dict:
    return {
        "params": "ENTRY(task, oracle, max_queries=16)",
        "param_rule": ("the first two parameters must be named task and "
                       "oracle, at most three parameters in total, no "
                       "*args, **kwargs, or keyword-only parameters"),
        "result_envelope": {
            "shape": {"candidate": "candidate-shaped object",
                      "queries": "nonnegative integer"},
            "rule": ("the entry function must return its own result "
                     "envelope shaped {\"candidate\": <candidate-shaped "
                     "object>, \"queries\": <nonnegative integer of oracle "
                     "queries used>}; returning the candidate object "
                     "directly fails execution with "
                     "malformed-result-envelope"),
        },
        "forbidden": {
            "import_statements": "import statements fail validation",
            "dunder": ("attribute access starting with a single "
                       "underscore and variable names starting with a "
                       "double underscore fail validation"),
            "calls": sorted(_FORBIDDEN_CALLS),
        },
        "source_rule": ("non-empty python source that parses with exactly "
                        "one module-level function carrying the entry name"),
    }


def verify_member(member: dict) -> str:
    source = member.get("method_source")
    entry = member.get("entry")
    if not isinstance(source, str) or not source.strip():
        raise MethodExecutionError("refused: empty-method-source")
    if not isinstance(entry, str) or not entry:
        raise MethodExecutionError("refused: missing-entry")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        raise MethodExecutionError("refused: unparseable-python")
    targets = [n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == entry]
    if len(targets) != 1:
        raise MethodExecutionError("refused: missing-entry-function")
    params = list(targets[0].args.posonlyargs) + list(targets[0].args.args)
    names = [p.arg for p in params]
    if len(names) < 2 or names[0] != "task" or names[1] != "oracle" \
            or len(names) > 3 or targets[0].args.vararg is not None \
            or targets[0].args.kwarg is not None \
            or targets[0].args.kwonlyargs:
        raise MethodExecutionError("refused: entry-arity")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise MethodExecutionError("refused: imports-forbidden")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise MethodExecutionError("refused: dunder-access-forbidden")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise MethodExecutionError("refused: dunder-access-forbidden")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in _FORBIDDEN_CALLS:
            raise MethodExecutionError("refused: io-or-reflection-forbidden")
    return entry


_DRIVER = '''import importlib.util, json, socket, sys
work, sock_path, root = sys.argv[1:]
sys.path.insert(0, root)
from experiments.representation import reducers
__S89A1_WRAPPERS__spec = importlib.util.spec_from_file_location('acquired_member', work + '/member.py')
module = importlib.util.module_from_spec(spec)
module.__dict__['reducers'] = reducers
__S89A1_BINDINGS__class Proxy:
    def __init__(self):
        self._queries = 0
    def query(self, candidate):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as link:
            link.connect(chr(0) + sock_path)
            frame = json.dumps({'candidate': candidate}).encode()
            link.sendall(len(frame).to_bytes(4, 'big') + frame)
            size = int.from_bytes(read(link, 4), 'big')
            if size > 4194304:
                raise RuntimeError('oversize verdict')
            response = json.loads(read(link, size))
            self._queries = response['queries']
            return response['verdict']
def read(link, size):
    data = bytearray()
    while len(data) < size:
        chunk = link.recv(size - len(data))
        if not chunk:
            raise RuntimeError('oracle channel closed')
        data.extend(chunk)
    return bytes(data)
try:
    spec.loader.exec_module(module)
    envelope = json.load(open(work + '/task.json'))
    proxy = Proxy()
    _entry = getattr(module, %r)
    if %d == 3:
        out = _entry(envelope['task'], proxy, max_queries=envelope['max_queries'])
    else:
        out = _entry(envelope['task'], proxy)
    if not isinstance(out, dict) or not isinstance(out.get('candidate'), dict):
        print(json.dumps({'status': 'error', 'error': 'malformed-result-envelope: entry must return {"candidate": <candidate>, "queries": <int>}'}))
    else:
        print(json.dumps({'status': 'ok', 'data': {'candidate': out['candidate'], 'queries': proxy._queries}}))
except Exception as exc:
    print(json.dumps({'status': 'error', 'error': type(exc).__name__ + ': ' + str(exc)}))
'''

_DRIVER = _DRIVER.replace(
    "__S89A1_WRAPPERS__", _child_wrapper_source()).replace(
    "__S89A1_BINDINGS__", _child_binding_source())


def _read_exact(link, size: int) -> bytes:
    if size > MAX_FRAME_BYTES:
        raise ValueError("oversize-query")
    data = bytearray()
    while len(data) < size:
        piece = link.recv(size - len(data))
        if not piece:
            raise OSError("short frame")
        data.extend(piece)
    return bytes(data)


def _source_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _record_query(trace: list, candidate, verdict) -> None:
    """One row per query the member actually asked, in the order it asked.

    Written on the host side, in `serve`, immediately after
    `oracle.query` returns, because that is the only place the child
    cannot rewrite. The child's own `Proxy` sees a verdict and a counter
    and nothing else; if the trace were assembled from what the member
    reports about itself, a member could report a walk it did not take.

    The candidate is digested rather than kept whole. A trace is evidence
    about which questions were asked, and the questions are small compared
    to the runs that hold them: a graph candidate carries every vertex and
    every edge, and 18 tasks times 4 queries of those would multiply the
    use record for no question the gate asks. The digest is over the
    canonical candidate, so two members asking byte-identical questions
    produce byte-identical rows and the comparison is exact.

    The row carries the graded verdict and its bounded reason alongside the
    digest. A walk is the sequence of (question, answer) pairs, not the
    questions alone: two members asking the same four candidates and being
    graded the same four ways took the same walk, and one that asked a
    different fourth question did not.
    """
    trace.append({
        "candidate_digest": _source_digest(_canonical_input(candidate)
                                            .decode("utf-8")),
        "verdict": str((verdict or {}).get("verdict", "")),
        "reason": str((verdict or {}).get("reason", "")),
    })


def _canonical_input(data) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode(
        "utf-8")


def _input_digest(data) -> str:
    return hashlib.sha256(_canonical_input(data)).hexdigest()


def _driver_digest(driver: str) -> str:
    return _source_digest(driver)


def _operation_provenance(source: str, driver: str, input_data,
                          *, source_path: str, driver_path: str,
                          input_path: str) -> dict:
    source_value = _source_digest(source)
    driver_value = _driver_digest(driver)
    input_value = _input_digest(input_data)
    return {
        "source_digest": source_value,
        "driver_digest": driver_value,
        "input_digest": input_value,
        "source_path": source_path,
        "driver_path": driver_path,
        "input_path": input_path,
    }


def _verify_operation_provenance(work: Path, provenance: dict) -> None:
    _verified_source_digest(work / provenance["source_path"],
                            provenance["source_digest"])
    driver = work / provenance["driver_path"]
    try:
        actual_driver = hashlib.sha256(driver.read_bytes()).hexdigest()
    except OSError as exc:
        raise MethodExecutionError("refused: staged driver is unreadable") from exc
    if actual_driver != provenance["driver_digest"]:
        raise MethodExecutionError("refused: staged driver digest mismatch")
    input_path = work / provenance["input_path"]
    try:
        actual_input = hashlib.sha256(input_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise MethodExecutionError("refused: serialized input is unreadable") from exc
    if actual_input != provenance["input_digest"]:
        raise MethodExecutionError("refused: serialized input digest mismatch")


def _verified_source_digest(path: Path, expected: str) -> str:
    try:
        staged = path.read_bytes()
    except OSError as exc:
        raise MethodExecutionError("refused: staged source is unreadable") from exc
    actual = hashlib.sha256(staged).hexdigest()
    if actual != expected:
        raise MethodExecutionError("refused: staged source digest mismatch")
    return actual


def _stage_source(path: Path, source: str, expected: str, *,
                  preserve: bool) -> None:
    if preserve and path.exists():
        _verified_source_digest(path, expected)
        return
    _stage_text(path, source, expected)


def _stage_text(path: Path, text: str, expected: str) -> None:
    """Write `text` so the bytes on disk hash to `expected`, or refuse.

    Every staged artifact is hashed in memory and re-hashed from disk
    before and after dispatch, so a write that is not byte-exact makes the
    operation unverifiable. Python's text-mode `write_text` translates each
    `\\n` to `os.linesep` on Windows, so a driver written that way is 16 bytes
    longer on disk than the string the digest was taken from, and
    `_verify_operation_provenance` refuses before anything is dispatched.
    Text therefore reaches disk through this one function, encoded
    explicitly, and the bytes written are checked against the digest rather
    than assumed to be it.
    """
    raw = text.encode("utf-8")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise MethodExecutionError("refused: staged text digest mismatch")
    path.write_bytes(raw)


def _durable_operation(dsn: str, operation_id: str) -> dict | None:
    from settlement import db
    with db.connect(dsn) as conn:
        row = conn.execute(
            "SELECT dispatch_state, reconcile_state, settled, payload"
            " FROM operations WHERE id = %s",
            (operation_id,)).fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        state = row.get("dispatch_state")
        reconcile = row.get("reconcile_state")
        settled = row.get("settled")
        payload = row.get("payload")
    else:
        state, reconcile, settled, payload = row
    return {"dispatch_state": state, "reconcile_state": reconcile,
            "settled": bool(settled), "payload": payload or {}}


def _reclaimable(state: str | None, receipted: bool) -> bool:
    """Whether the broker can still recover this operation by re-sending it.

    The one shape that is recoverable is a `dispatching` operation holding
    no receipt: the dispatch was advanced, the worker was never started, and
    `broker.redispatch_after_reset` re-sends it once the launcher attests it
    was never sent. A receipt changes the answer even when the state does
    not. A receipted `dispatching` operation already ran, and re-sending it
    is a second execution of work whose result is already stored, so it is
    answered from that receipt instead of being reclaimed.

    Everything else stays refused. `conflict` and `unresolved` are verdicts
    the store reached deliberately, and a crash artefact is not evidence
    strong enough to overturn either. Loosening this for a receipted or an
    unresolved operation is a double-execution bug, not a recovery.
    """
    return state == "dispatching" and not receipted


def _durable_receipt(dsn: str, operation_id: str) -> dict | None:
    from settlement import db
    operation = _durable_operation(dsn, operation_id)
    if operation is None:
        raise MethodExecutionError(
            "refused: durable child operation is missing")
    if (operation.get("reconcile_state") in ("conflict", "unresolved")
            or operation.get("dispatch_state") == "unresolved"):
        raise MethodExecutionError(
            "refused: durable child operation is conflicted or unresolved")
    state = operation.get("dispatch_state")
    with db.connect(dsn) as conn:
        cursor = conn.execute(
            "SELECT receipt_identity, outcome, content, content_digest"
            " FROM receipts WHERE operation_id = %s"
            " ORDER BY created_at, receipt_identity",
            (operation_id,))
        rows = cursor.fetchall() if hasattr(cursor, "fetchall") else []
        if not rows and hasattr(cursor, "fetchone"):
            row = cursor.fetchone()
            rows = [] if row is None else [row]
    if not operation.get("settled") and state != "prepared" \
            and not _reclaimable(state, bool(rows)):
        raise MethodExecutionError(
            "refused: durable child operation is conflicted or unresolved")
    if not rows:
        return None
    if state == "prepared":
        raise MethodExecutionError(
            "refused: durable receipt exists for undispatched child operation")
    receipts = []
    for row in rows:
        if isinstance(row, dict):
            identity = row.get("receipt_identity")
            outcome = row.get("outcome")
            content = row.get("content")
            stored_digest = row.get("content_digest")
        else:
            identity, outcome, content, stored_digest = row
        if not isinstance(identity, str) or not identity:
            raise MethodExecutionError(
                "refused: durable child receipt identity is missing")
        if not isinstance(content, dict):
            raise MethodExecutionError(
                "refused: durable child receipt content is not an object")
        expected_digest = payload_digest(content)
        if stored_digest != expected_digest:
            raise MethodExecutionError(
                "refused: durable child receipt content digest mismatch")
        receipt = (str(identity), str(outcome), content, expected_digest)
        if receipt not in receipts:
            receipts.append(receipt)
    if len(receipts) != 1:
        raise MethodExecutionError(
            "refused: durable child operation has conflicting receipts")
    identity, outcome, content, content_digest = receipts[0]
    if outcome != "success":
        raise MethodExecutionError(
            "refused: durable child operation has no successful receipt")
    return {**content, "outcome": outcome, "receipt_identity": identity,
            "content_digest": content_digest, "_operation": operation}


def _result(receipt: dict | None, member: dict, operation_id: str | None,
            source_digest: str) -> dict:
    data = (receipt or {}).get("data", {})
    if receipt is None or receipt.get("outcome") != "success":
        raise MethodExecutionError("%s: %s" % (
            "timeout" if data.get("timed_out") else "member-failed", data))
    output = data.get("worker", {}).get("data", {})
    if not isinstance(output.get("candidate"), dict):
        raise MethodExecutionError("member-failed: malformed-result")
    return {"candidate": output["candidate"], "queries": output.get("queries", 0),
            "operation_id": operation_id,
            "operation_ids": [operation_id] if operation_id else [],
            "capability_id": member.get("capability_id", ""),
            "source_digest": source_digest}


def _verify_durable_payload(receipt: dict | None, expected: dict) -> None:
    if receipt is None:
        return
    operation = receipt.get("_operation")
    if not isinstance(operation, dict):
        raise MethodExecutionError(
            "refused: durable child operation anchor is missing")
    stored = operation.get("payload") or {}
    if isinstance(stored, dict) and isinstance(stored.get("payload"), dict):
        stored = stored["payload"]
    expected = broker.validate_effect(broker.SANDBOX_EXEC, expected)
    if stored != expected:
        raise MethodExecutionError(
            "refused: durable child operation payload does not match staged bytes")


def _result_provenance(source: str, input_data, payload: dict,
                        provenance: dict) -> dict:
    return {
        "driver_digest": provenance["driver_digest"],
        "input_digest": provenance["input_digest"],
        "operation_payload_digest": _source_digest(
            json.dumps(payload, sort_keys=True, separators=(",", ":"))),
        "source_bytes": source,
        "serialized_input": _canonical_input(input_data).decode("utf-8"),
    }


def run_member_out_of_process(member: dict, task: dict, *,
                              max_queries: int = 16,
                              timeout_ms: int = DEFAULT_TIMEOUT_MS,
                              dsn: str | None = None,
                              allocation_id: str | None = None,
                              operation_id: str | None = None) -> dict:
    entry = verify_member(member)
    verify_child_contract()
    if dsn is not None and (not allocation_id or not operation_id):
        raise MethodExecutionError("refused: execution needs explicit authority and identity")
    operation_id = operation_id or "member"
    requested_digest = _source_digest(member["method_source"])
    argc = next(len(n.args.args) for n in ast.parse(
        member["method_source"]).body
        if isinstance(n, ast.FunctionDef) and n.name == entry)
    oracle_type = checkers.GraphOracle if task.get("family") == "graph" else checkers.SoftwareOracle
    oracle = oracle_type(task, max_queries=max_queries)
    root = str(Path(__file__).resolve().parent.parent.parent)
    generation = None
    if dsn is not None:
        from settlement import db
        with db.connect(dsn) as conn:
            allocation = conn.execute("SELECT created_at FROM allocations WHERE id = %s",
                                      (allocation_id,)).fetchone()
        if allocation is None:
            raise MethodExecutionError("refused: unknown allocation")
        generation = str(allocation[0])
    identity = hashlib.sha256(json.dumps(
        [dsn, allocation_id, generation, operation_id, member, task, max_queries, timeout_ms, _DRIVER],
        sort_keys=True).encode()).hexdigest()
    directory = Path(root) / ".ad01-runs" / identity
    context = nullcontext(directory) if dsn else tempfile.TemporaryDirectory(prefix="ad01-")
    with context as directory:
        work = Path(directory)
        work.mkdir(parents=True, exist_ok=True)
        _stage_source(
            work / "member.py", member["method_source"], requested_digest,
            preserve=dsn is not None)
        input_data = {"task": task, "max_queries": max_queries}
        (work / "task.json").write_bytes(_canonical_input(input_data))
        driver_source = _DRIVER % (entry, argc)
        provenance = _operation_provenance(
            member["method_source"], driver_source, input_data,
            source_path="member.py", driver_path="driver.py",
            input_path="task.json")
        driver = work / provenance["driver_path"]
        _stage_text(driver, driver_source, provenance["driver_digest"])
        _verify_operation_provenance(work, provenance)
        socket_path = "ad01-" + hashlib.sha256(str(work).encode()).hexdigest()
        launcher = LocalLauncher(work / "launcher")
        payload = {"profile": PROFILE, "argv": [sys.executable, str(driver), str(work),
                   str(socket_path), root], "timeout_ms": timeout_ms}
        if dsn is not None:
            ensured = broker.ensure_operation(
                dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
                payload=payload, allocation_id=allocation_id)
            if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
                raise MethodExecutionError("refused: %s" % ensured.detail)
            _verify_operation_provenance(work, provenance)
            receipt = _durable_receipt(dsn, operation_id)
            if receipt is not None:
                _verify_durable_payload(receipt, payload)
                executed_digest = _verified_source_digest(
                    work / "member.py", requested_digest)
                result = _result(
                    receipt, member, operation_id, executed_digest)
                result.update(_result_provenance(
                    member["method_source"], input_data, payload, provenance))
                # The member did not ask anything in this process. The
                # receipt replays a settled operation, and a walk that was
                # never walked here is not an empty walk, it is an absent
                # one. `None` says that, where `[]` would say the member
                # ran and asked nothing, which is a different claim and
                # the one the gate must not mistake for a match.
                result["query_trace"] = None
                return result
            _verified_source_digest(work / "member.py", requested_digest)
        stopped = threading.Event()
        errors = []
        trace: list = []
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(chr(0) + socket_path)
            server.listen(1)
            server.settimeout(0.1)

            def serve():
                try:
                    while not stopped.is_set():
                        try:
                            link, _ = server.accept()
                        except socket.timeout:
                            continue
                        with link:
                            link.settimeout(0.1)
                            size = int.from_bytes(_read_exact(link, 4), "big")
                            message = json.loads(_read_exact(link, size))
                            if not isinstance(message, dict) or set(message) != {"candidate"} \
                                    or not isinstance(message["candidate"], dict):
                                raise ValueError("query-needs-candidate")
                            candidate = message["candidate"]
                            verdict = oracle.query(candidate)
                            _record_query(trace, candidate, verdict)
                            reply = json.dumps({"verdict": verdict,
                                                "queries": oracle.queries_used}).encode()
                            link.sendall(len(reply).to_bytes(4, "big") + reply)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    errors.append(str(exc))

            host = threading.Thread(target=serve)
            host.start()
            try:
                _verify_operation_provenance(work, provenance)
                if dsn is None:
                    launcher.dispatch(broker.BrokerOp(
                        operation_id=operation_id, effect=broker.SANDBOX_EXEC, payload=payload))
                else:
                    broker.dispatch_operation(dsn, operation_id, launchers={PROFILE: launcher})
            finally:
                stopped.set()
                host.join()
        receipt = (_durable_receipt(dsn, operation_id)
                   if dsn is not None else launcher.read_result(operation_id))
        if errors:
            raise MethodExecutionError("bad-frame: %s" % errors[0])
        _verify_operation_provenance(work, provenance)
        executed_digest = _verified_source_digest(
            work / "member.py", requested_digest)
        if dsn is not None:
            _verify_durable_payload(receipt, payload)
        result = _result(
            receipt, member, operation_id if dsn else None, executed_digest)
        result.update(_result_provenance(
            member["method_source"], input_data, payload, provenance))
        if dsn is None:
            result["queries"] = oracle.queries_used
        result["query_trace"] = trace
        return result


STEP_TIMEOUT_MS = 10_000
STEP_CPU_SECONDS = 10
STEP_MAX_OUTPUT_BYTES = 65_536


def step_contract() -> dict:
    from . import policy_step
    return {
        "version": policy_step.POLICY_STEP_VERSION,
        "entry": "%s(view, state)" % policy_step.STEP_ENTRY,
        "param_rule": ("the two parameters must be named view and state,"
                       " no *args, **kwargs, or keyword-only parameters"),
        "result_envelope": {
            "shape": {"action": "policy action object",
                      "state": "bounded JSON object"},
            "rule": ("the entry function must return its own result"
                     " envelope shaped {\"action\": <policy action object>,"
                     " \"state\": <bounded JSON object>}; anything else"
                     " fails execution with malformed-step-envelope"),
        },
        "forbidden": entry_contract()["forbidden"],
        "source_rule": ("non-empty python source that parses with exactly"
                        " one module-level function carrying the entry name"),
        "limits": {"cpu_seconds": STEP_CPU_SECONDS,
                   "wall_ms": STEP_TIMEOUT_MS,
                   "output_bytes": STEP_MAX_OUTPUT_BYTES,
                   "state_bytes": policy_step.STATE_LIMIT_BYTES},
    }


def verify_step_source(source: str, entry: str = "STEP") -> str:
    if not isinstance(source, str) or not source.strip():
        raise MethodExecutionError("refused: empty-policy-source")
    if not isinstance(entry, str) or not entry:
        raise MethodExecutionError("refused: missing-entry")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        raise MethodExecutionError("refused: unparseable-python")
    targets = [n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == entry]
    if len(targets) != 1:
        raise MethodExecutionError("refused: missing-entry-function")
    params = list(targets[0].args.posonlyargs) + list(targets[0].args.args)
    names = [p.arg for p in params]
    if names != ["view", "state"] \
            or targets[0].args.vararg is not None \
            or targets[0].args.kwarg is not None \
            or targets[0].args.kwonlyargs:
        raise MethodExecutionError("refused: entry-arity")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise MethodExecutionError("refused: imports-forbidden")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise MethodExecutionError("refused: dunder-access-forbidden")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise MethodExecutionError("refused: dunder-access-forbidden")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in _FORBIDDEN_CALLS:
            raise MethodExecutionError("refused: io-or-reflection-forbidden")
    return entry


_STEP_DRIVER = '''import importlib.util, json, sys
work = sys.argv[1]
__STEP_POLICY__spec = importlib.util.spec_from_file_location('acquired_policy', work + '/policy.py')
module = importlib.util.module_from_spec(__STEP_POLICY__spec)
try:
    __STEP_POLICY__spec.loader.exec_module(module)
    payload = json.load(open(work + '/step.json'))
    _entry = getattr(module, %r)
    out = _entry(payload['view'], payload['state'])
    if not isinstance(out, dict) or not isinstance(out.get('action'), dict) \\
            or not isinstance(out.get('state'), dict):
        print(json.dumps({'status': 'error', 'error': 'malformed-step-envelope: STEP must return {"action": <action object>, "state": <object>}'}))
    else:
        print(json.dumps({'status': 'ok', 'data': {'action': out['action'], 'state': out['state']}}))
except Exception as exc:
    print(json.dumps({'status': 'error', 'error': type(exc).__name__ + ': ' + str(exc)}))
'''


def _step_result(receipt: dict | None, operation_id: str | None, *,
                 durable_operation_id: str | None = None) -> dict:
    from . import policy_step
    data = (receipt or {}).get("data", {})
    if receipt is None or receipt.get("outcome") != "success":
        raise MethodExecutionError("%s: %s" % (
            "timeout" if data.get("timed_out") else "step-failed", data))
    output = data.get("worker", {}).get("data", {})
    if not isinstance(output.get("action"), dict) \
            or not isinstance(output.get("state"), dict):
        raise MethodExecutionError(
            "step-failed: malformed-step-envelope")
    try:
        policy_step.validate_step_result(
            {"action": output["action"], "state": output["state"]})
    except ValueError as exc:
        raise MethodExecutionError("step-failed: refused: %s" % exc)
    return {"action": output["action"], "state": output["state"],
            "operation_id": operation_id,
            "operation_ids": ([durable_operation_id]
                              if durable_operation_id else [])}


def _step_evidence(raw_receipt: dict, result: dict, *, operation_id: str,
                   source_digest: str, source_bytes: str, view: dict,
                   input_bytes: bytes, driver_digest: str,
                   operation_payload: dict, receipt_identity: str,
                   arm: str | None, task_id: str | None,
                   artifact_digest: str | None,
                   parent_digest: str | None,
                   round_no: int | None) -> dict:
    from . import frontier
    payload = {"action": result["action"], "state": result["state"],
               "launcher_receipt": {key: value for key, value in
                                    raw_receipt.items() if key != "_operation"},
               "source_bytes": source_bytes,
               "serialized_input": input_bytes.decode("utf-8"),
               "driver_digest": driver_digest,
               "operation_payload": operation_payload}
    return frontier.make_evidence_record(
        "child-execution", operation_id, "success",
        receipt_identity=receipt_identity, arm=arm, task_id=task_id,
        source_digest=source_digest, artifact_digest=artifact_digest,
        input_digest=_source_digest(input_bytes.decode("utf-8")),
        driver_digest=driver_digest,
        operation_payload_digest=_source_digest(
            json.dumps(operation_payload, sort_keys=True, separators=(",", ":"))),
        result_digest=frontier.source_digest(frontier.canonical({
            "action": result["action"], "state": result["state"]})),
        package_digest=artifact_digest, parent_digest=parent_digest,
        round_no=round_no, details={"raw_payload": payload})


def run_step_out_of_process(source: str, view: dict, state: dict, *,
                            entry: str = "STEP",
                            timeout_ms: int = STEP_TIMEOUT_MS,
                            cpu_seconds: int = STEP_CPU_SECONDS,
                            max_output_bytes: int = STEP_MAX_OUTPUT_BYTES,
                            memory_bytes: int | None = None,
                            dsn: str | None = None,
                            allocation_id: str | None = None,
                            operation_id: str | None = None,
                            arm: str | None = None,
                            task_id: str | None = None,
                            artifact_digest: str | None = None,
                            parent_digest: str | None = None,
                            round_no: int | None = None) -> dict:
    from . import policy_step
    entry = verify_step_source(source, entry)
    policy_step.validate_view(view)
    policy_step.validate_state(state)
    if dsn is not None and (not allocation_id or not operation_id):
        raise MethodExecutionError(
            "refused: execution needs explicit authority and identity")
    operation_id = operation_id or "step"
    requested_digest = _source_digest(source)
    root = str(Path(__file__).resolve().parent.parent.parent)
    generation = None
    if dsn is not None:
        from settlement import db
        with db.connect(dsn) as conn:
            allocation = conn.execute(
                "SELECT created_at FROM allocations WHERE id = %s",
                (allocation_id,)).fetchone()
        if allocation is None:
            raise MethodExecutionError("refused: unknown allocation")
        generation = str(allocation[0])
    identity = hashlib.sha256(json.dumps(
        [dsn, allocation_id, generation, operation_id, requested_digest, view,
         state, timeout_ms, cpu_seconds, max_output_bytes, memory_bytes,
         _STEP_DRIVER],
        sort_keys=True).encode()).hexdigest()
    directory = Path(root) / ".ad01-runs" / identity
    context = nullcontext(directory) if dsn else tempfile.TemporaryDirectory(prefix="ad01-step-")
    with context as directory:
        work = Path(directory)
        work.mkdir(parents=True, exist_ok=True)
        _stage_source(
            work / "policy.py", source, requested_digest,
            preserve=dsn is not None)
        input_data = {"view": view, "state": state}
        input_bytes = _canonical_input(input_data)
        (work / "step.json").write_bytes(input_bytes)
        driver_source = _STEP_DRIVER % (entry,)
        provenance = _operation_provenance(
            source, driver_source, input_data, source_path="policy.py",
            driver_path="driver.py", input_path="step.json")
        driver = work / provenance["driver_path"]
        _stage_text(driver, driver_source, provenance["driver_digest"])
        _verify_operation_provenance(work, provenance)
        launcher = LocalLauncher(work / "launcher")
        payload = {"profile": PROFILE, "argv": [sys.executable, str(driver), str(work)],
                   "timeout_ms": timeout_ms,
                   "max_output_bytes": max_output_bytes,
                   "cpu_seconds": cpu_seconds,
                   "memory_bytes": memory_bytes}
        receipt_identity = None
        if dsn is not None:
            ensured = broker.ensure_operation(
                dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
                payload=payload, allocation_id=allocation_id)
            if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
                raise MethodExecutionError("refused: %s" % ensured.detail)
            _verify_operation_provenance(work, provenance)
            raw_receipt = _durable_receipt(dsn, operation_id)
            if raw_receipt is not None:
                _verify_durable_payload(raw_receipt, payload)
                receipt_identity = str(raw_receipt["receipt_identity"])
                executed_digest = _verified_source_digest(
                    work / "policy.py", requested_digest)
                result = _step_result(
                    raw_receipt, operation_id,
                    durable_operation_id=operation_id)
                return {
                    **result,
                    "source_digest": executed_digest,
                    **_result_provenance(source, input_data, payload, provenance),
                    "receipt": _step_evidence(
                        raw_receipt, result, operation_id=operation_id,
                        source_digest=executed_digest,
                        source_bytes=source, view=view, input_bytes=input_bytes,
                        driver_digest=provenance["driver_digest"],
                        operation_payload=payload,
                        receipt_identity=receipt_identity, arm=arm,
                        task_id=task_id, artifact_digest=artifact_digest,
                        parent_digest=parent_digest, round_no=round_no),
                }
            _verify_operation_provenance(work, provenance)
            broker.dispatch_operation(dsn, operation_id, launchers={PROFILE: launcher})
            receipt = _durable_receipt(dsn, operation_id)
        else:
            _verify_operation_provenance(work, provenance)
            launched = launcher.dispatch(broker.BrokerOp(
                operation_id=operation_id, effect=broker.SANDBOX_EXEC,
                payload=payload))
            if launched.receipt is not None:
                receipt_identity = launched.receipt.receipt_identity
            receipt = launcher.read_result(operation_id)
        _verify_operation_provenance(work, provenance)
        executed_digest = _verified_source_digest(
            work / "policy.py", requested_digest)
        if dsn is not None:
            _verify_durable_payload(receipt, payload)
        if not receipt_identity and isinstance(receipt, dict):
            receipt_identity = receipt.get("receipt_identity")
        if not receipt_identity:
            raise MethodExecutionError("refused: child receipt identity is missing")
        result = _step_result(
            receipt, operation_id,
            durable_operation_id=operation_id if dsn is not None else None)
        return {
            **result,
            "source_digest": executed_digest,
            **_result_provenance(source, input_data, payload, provenance),
            "receipt": _step_evidence(
                receipt, result, operation_id=operation_id,
                source_digest=executed_digest, source_bytes=source, view=view,
                input_bytes=input_bytes, driver_digest=provenance["driver_digest"],
                operation_payload=payload, receipt_identity=receipt_identity,
                arm=arm, task_id=task_id, artifact_digest=artifact_digest,
                parent_digest=parent_digest, round_no=round_no),
        }
