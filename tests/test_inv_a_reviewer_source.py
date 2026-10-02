"""Reviewer-written policy source for the A5 acceptance chain.

Nothing in this module is authored by the lanes whose work it exercises.
Every STEP program below was written for this verification, so the chain
proves that a *foreign* policy's bytes drive the durable rows rather than
that a lane's own fixture is self-consistent.

The programs are source strings, not callables. They reach the chain the
only way a real policy reaches it: through `run_campaign`'s
`StepPolicyConsumer` or `run_use`'s `policy_source`, both of which stage
the bytes and run them in the bounded child under `broker.ensure_operation`
plus `broker.dispatch_operation`.

Each program is deliberately small enough that its whole causal signature
is readable on one screen. A policy that decides, asks, checks, builds and
uses is a policy whose arrows cannot be told apart.
"""

from __future__ import annotations

import hashlib

# The method bytes a construction round returns. `reducers` is a name the
# child already binds, so this source is executable rather than a snippet,
# and it is the member the checker can preserve.
ACQUIRED_METHOD = (
    "def carried(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method='greedy',"
    " max_queries=max_queries)\n"
)

# The acquisition chain, as a counter machine over boundaries. Each
# boundary admits exactly one action and returns, so a program that wants
# three decisions needs three boundaries and a private state that survives
# between them. That counter is the point: the state crosses a boundary
# only through the durable row, so a chain that reaches its last stage
# proves the state survived every boundary it crossed.
CHAIN_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    stage = int(state.get('stage', 0))\n"
    "    if stage == 0:\n"
    "        return {'action': {'kind': 'diagnose', 'target': target,\n"
    "                           'inputs': {'diagnostic': 'software',\n"
    "                                      'unknown': 'does the seed hold',\n"
    "                                      'question': 'why this verdict'},\n"
    "                           'evidence_refs': [],\n"
    "                           'requested_resources': {'queries': 1}},\n"
    "                'state': {'stage': 1}}\n"
    "    if stage == 1:\n"
    "        methods = list(view.get('eligible_methods') or [])\n"
    "        if not methods:\n"
    "            return {'action': {'kind': 'construct_method',\n"
    "                               'target': target,\n"
    "                               'inputs': {'method_id': '',"
    " 'max_queries': 4},\n"
    "                               'evidence_refs': [],\n"
    "                               'requested_resources': {'queries': 4}},\n"
    "                    'state': {'stage': 1}}\n"
    "        return {'action': {'kind': 'use_method', 'target': target,\n"
    "                           'inputs': {'method_id': methods[0],\n"
    "                                      'max_queries': 4},\n"
    "                           'evidence_refs': [],\n"
    "                           'requested_resources': {'queries': 4}},\n"
    "                'state': {'stage': 3}}\n"
    "    return {'action': {'kind': 'stop', 'target': target,\n"
    "                       'inputs': {'reason': 'chain complete'},\n"
    "                       'evidence_refs': [],\n"
    "                       'requested_resources': {}},\n"
    "            'state': {'stage': 4}}\n"
)

# The use-side program. It names one repertoire member by capability id and
# asks for a bounded budget. `run_use` refuses anything else, so a program
# wanting a member the repertoire does not hold is the `no candidate`
# tamper rather than a second policy here.
USE_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    method = (view.get('eligible_methods') or ['%s'])[0]\n"
    "    return {'action': {'kind': 'use_method', 'target': target,\n"
    "                       'inputs': {'method_id': method,\n"
    "                                  'max_queries': 4},\n"
    "                       'evidence_refs': [],\n"
    "                       'requested_resources': {'queries': 4}},\n"
    "            'state': {'selected': method}}\n"
)

# Reaches for a member the repertoire does not hold. The refusal names the
# member, which is what makes it a refusal rather than a substitution the
# policy never asked for.
NO_CANDIDATE_SOURCE = (
    "def STEP(view, state):\n"
    "    return {'action': {'kind': 'use_method',\n"
    "                       'target': view['task_content']['task_id'],\n"
    "                       'inputs': {'method_id': 'a5-absent-method',\n"
    "                                  'max_queries': 4},\n"
    "                       'evidence_refs': [],\n"
    "                       'requested_resources': {'queries': 4}},\n"
    "            'state': {}}\n"
)

# Reaches for a member the repertoire holds but that is scoped to another
# family. The refusal is about scope, not absence, so a chain proved only
# on absence would not have covered it.
WRONG_FAMILY_SOURCE = (
    "def STEP(view, state):\n"
    "    return {'action': {'kind': 'use_method',\n"
    "                       'target': view['task_content']['task_id'],\n"
    "                       'inputs': {'method_id': 'seed-gr-dfs',\n"
    "                                  'max_queries': 4},\n"
    "                       'evidence_refs': [],\n"
    "                       'requested_resources': {'queries': 4}},\n"
    "            'state': {}}\n"
)

# Burns every policy step asking the same question. The allowance runs out
# before the program reaches a terminal kind, and the refusal has to reach
# the durable row rather than dropping the step.
EXHAUSTED_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    n = int(state.get('n', 0))\n"
    "    return {'action': {'kind': 'request_model', 'target': target,\n"
    "                       'inputs': {'prompt': 'ask number %d' % n,\n"
    "                                  'max_output_tokens': 16},\n"
    "                       'evidence_refs': [],\n"
    "                       'requested_resources': {'model_calls': 1}},\n"
    "            'state': {'n': n + 1}}\n"
)

# Never reaches a terminal kind, so the boundary ends on a *pending*
# accepted action. Restarting under that pending row is what the
# `pending resume` tamper perturbs.
PENDING_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    return {'action': {'kind': 'request_model', 'target': target,\n"
    "                       'inputs': {'prompt': 'the one question',\n"
    "                                  'max_output_tokens': 16},\n"
    "                       'evidence_refs': [],\n"
    "                       'requested_resources': {'model_calls': 1}},\n"
    "            'state': {'n': int(state.get('n', 0)) + 1}}\n"
)

# Asks for a model reason and then stops on what came back. A response
# that arrives truncated reaches the program flagged, and an empty one
# cannot settle at all, so this is the partial-response program.
REASONING_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    if int(state.get('asked', 0)) == 0:\n"
    "        return {'action': {'kind': 'request_model', 'target': target,\n"
    "                           'inputs': {'prompt': 'name the failure mode',\n"
    "                                      'max_output_tokens': 16},\n"
    "                           'evidence_refs': [],\n"
    "                           'requested_resources': {'model_calls': 1}},\n"
    "                'state': {'asked': 1}}\n"
    "    return {'action': {'kind': 'stop', 'target': target,\n"
    "                       'inputs': {'reason': 'heard the witness'},\n"
    "                       'evidence_refs': [],\n"
    "                       'requested_resources': {}},\n"
    "            'state': {'asked': 1}}\n"
)

# The program a pending boundary is accepted for. `accept_action` records it
# as the boundary's accepted action without running it, which is what makes
# the restart under a pending operation a real pending operation rather than
# a second decision. Its next action asks for a model reason, so a resumed
# run has an admitted effect to settle.
PENDING_STEP_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    n = int(state.get('n', 0))\n"
    "    if n == 0:\n"
    "        return {'action': {'kind': 'request_model', 'target': target,\n"
    "                           'inputs': {'prompt': 'the one question',\n"
    "                                      'max_output_tokens': 16},\n"
    "                           'evidence_refs': [],\n"
    "                           'requested_resources': {'model_calls': 1}},\n"
    "                'state': {'n': 1}}\n"
    "    return {'action': {'kind': 'stop', 'target': target,\n"
    "                       'inputs': {'reason': 'resolved after restart'},\n"
    "                       'evidence_refs': [],\n"
    "                       'requested_resources': {}},\n"
    "            'state': {'n': n}}\n"
)

# The decision `accept_action` records for a pending boundary. Its identity
# is the program's source digest plus the boundary it was accepted for, so a
# resumed run can tell this decision from any other.
def pending_decision(task_id: str, capability_id: str) -> str:
    return (
        "{'basis_references': [],"
        " 'question': 'reviewer pending boundary',"
        " 'next_action': {'kind': 'diagnostic', 'task_id': %r,"
        " 'diagnostic': 'software', 'capability_id': %r},"
        " 'policy_source': %r}"
        % (task_id, capability_id, digest(PENDING_STEP_SOURCE)))

# Spins inside the child until the bounded step timeout fires. The refusal
# has to name the timeout rather than reporting a method that ran.
TIMEOUT_SOURCE = (
    "def STEP(view, state):\n"
    "    total = 0\n"
    "    while True:\n"
    "        total = total + 1\n"
)


def digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def use_source(method_id: str) -> str:
    return USE_SOURCE % method_id