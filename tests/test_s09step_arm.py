"""Qualify the real Python STEP arm before it is compared against anything.

CS-03 says the representation comparison runs on one arm. This file
establishes whether that arm is real: that a reviewer-authored STEP policy
governs admitted actions, that what it decides comes from the observation it
was given, that the view it receives withholds the answer, that its state
survives a fresh interpreter, and what the execution boundary actually is.

The vocabulary table is already qualified in `test_s09_vocab_unify.py`; what
is not qualified is whether the STEP arm ever applies it. That is the first
test here, and it is a finding rather than a restatement.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_policy
from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import method_exec
from experiments.ad01 import policy_action
from experiments.ad01 import policy_step
from execution_authority import execution_authority


def _artifact(source: str) -> dict:
    return policy_step.make_policy_artifact(
        source, origin="authored-control", instruments=["boolean-rule-v1"])


def _child_receipt(dsn: str, operation_id: str) -> dict:
    """The launcher's own record of one execution, read back from the store.

    Every execution failure now settles a receipt and produces the same
    refusal message, so a refusal's text says only that an execution failed.
    What distinguishes a CPU kill from a wall timeout, or a truncated stream
    from a chatty policy, is in the receipt the child settled. Reading it back
    is how these tests stay assertions about the child rather than about the
    executor's wording, and it is the idiom `test_s89a1_contract.py` already
    established.
    """
    from settlement import store

    receipts = store.operation_receipts(dsn, operation_id)
    assert len(receipts) == 1, receipts
    return dict(receipts[0]["content"]["data"])


def _public_state(seed: int = 4, queried=()) -> dict:
    session = rules.RuleSession(rules.make_task("dev", seed))
    for x in queried:
        session.query(x)
    return active.public_state(session)


def _refusal(action: dict) -> dict:
    return action["inputs"]["bridge_refusal"]


def _decide(source: str, public_state: dict, **limits) -> dict:
    decide = boolean_policy.choose_action(_artifact(source), **limits)
    return decide(public_state)


def _commit(task: dict, specs: list) -> dict:
    session = rules.RuleSession(task)
    session.query(3)
    session.commit_predictor({"specs": specs})
    return session.score(session._committed)


# The arm must emit the shared contract's names, because that is what the
# Boolean world parses. `BOOLEAN_ACTIONS` is written out rather than read from
# the table under test.
BOOLEAN_ACTIONS = {"probe", "stop", "construct"}

# The mapping, written out by hand rather than read back from the table under
# test, so the assertion is about meaning and not about self-consistency.
EXPECTED_MAPPING = {
    "diagnose": policy_action.PROBE,
    "construct_method": policy_action.CONSTRUCT,
    "use_method": policy_action.USE,
    "request_model": policy_action.OBSERVE,
    "propose_revision": policy_action.CHECK,
    "stop": policy_action.STOP,
}


def test_the_step_table_is_total_and_sound_in_both_directions():
    """Derived, not read back from `vocabulary_coverage`.

    Total forward: every STEP kind is placed. Sound: every placement names a
    contract kind that exists. Bijective: no two STEP kinds collapse onto one
    contract kind, which is what makes the reverse total as well. Both
    vocabularies are six, and the table is a bijection between them.
    """
    forward = policy_step.STEP_KIND_TO_CONTRACT
    reverse = policy_step.CONTRACT_KIND_TO_STEP

    assert forward == EXPECTED_MAPPING
    assert set(forward) == set(policy_step.ACTION_KINDS)
    assert set(forward.values()) <= set(policy_action.ACTION_KINDS)
    assert len(set(forward.values())) == len(forward)
    assert set(reverse) == set(policy_action.ACTION_KINDS)
    assert set(reverse.values()) == set(policy_step.ACTION_KINDS)
    assert all(reverse[contract_kind] == step_kind
               for step_kind, contract_kind in forward.items())


def test_the_step_arm_emits_contract_names_and_the_abi_table_is_bypassed():
    """Finding: the six-kind translation is never applied on the STEP arm.

    `STEP_KIND_TO_CONTRACT` is total and sound as a table, and
    `test_s09_vocab_unify.py` proves that. Nothing on the Boolean bridge calls
    `as_contract_action`, and the bridge feeds the policy's action straight to
    `policy_action.parse_action`, which only accepts contract names. So a STEP
    policy written in its own ABI's vocabulary is refused on every kind except
    the one name the two vocabularies share.

    This is the fact lane I needs before registering STEP as a real arm: the
    arm does not speak the STEP vocabulary at the world boundary, it speaks the
    shared contract's. The table is correct and unused.
    """
    public_state = _public_state()
    refusals = {}
    for step_kind in policy_step.ACTION_KINDS:
        source = (
            'def STEP(view, state):\n'
            '    action = {"kind": "%s", "target": "boolean.query",\n'
            '              "inputs": {}, "evidence_refs": [],\n'
            '              "requested_resources": {}}\n'
            '    return {"action": action, "state": {}}\n' % step_kind)
        refusals[step_kind] = _refusal(_decide(source, public_state))["reason"]

    assert refusals["stop"] == "stop target must be boolean.task"
    for step_kind in sorted(set(policy_step.ACTION_KINDS) - {"stop"}):
        assert "unknown action kind %r" % (step_kind,) in \
            refusals[step_kind], step_kind

    # The refusal names the shared contract's vocabulary, not the STEP ABI's.
    # `validate_action` is never reached, because `parse_action` runs first.
    assert "unknown policy action kind" not in str(refusals)

    assert BOOLEAN_ACTIONS == set(
        boolean_policy._shared_view(public_state)["action_schema"]["actions"])
    assert policy_step.vocabulary_coverage()["step_unmapped"] == []
    assert policy_step.vocabulary_coverage()["contract_unmapped"] == []


def test_the_table_cannot_normalise_an_action_in_contract_vocabulary():
    """The obvious one-line fix does not work either.

    Feeding the bridge's own output back through the translator is refused by
    the STEP ABI, because `probe` is not a STEP kind. So the gap cannot be
    closed downstream of the policy: a STEP arm has to be authored against the
    shared contract, or the bridge has to grow a second translation seam.
    """
    from_contract = {
        "kind": policy_action.PROBE, "target": "boolean.query",
        "inputs": {"x": 3}, "evidence_refs": [],
        "requested_resources": {"queries": 1}}

    with pytest.raises(ValueError, match="unknown policy action kind"):
        policy_step.as_contract_action(from_contract)

    assert policy_step.as_contract_action(
        {**from_contract, "kind": "diagnose"})["kind"] == policy_action.PROBE


# Reads the observation's length, and nothing else.
COUNT_READER = '''def STEP(view, state):
    observed = view["observed"]
    if not observed:
        action = {"kind": "probe", "target": "boolean.query",
                  "inputs": {"x": len(observed)}, "evidence_refs": [],
                  "requested_resources": {"queries": 1}}
    else:
        action = {"kind": "stop", "target": "boolean.task", "inputs": {},
                  "evidence_refs": [], "requested_resources": {}}
    return {"action": action, "state": {"probes": len(observed)}}
'''

# Reads the observation's values, and nothing else.
VALUE_READER = '''def STEP(view, state):
    observed = view["observed"]
    bits = 0
    for row in observed:
        for value in row["y"]:
            bits += value
    if not observed:
        action = {"kind": "probe", "target": "boolean.query",
                  "inputs": {"x": 0}, "evidence_refs": [],
                  "requested_resources": {"queries": 1}}
    else:
        action = {"kind": "probe", "target": "boolean.query",
                  "inputs": {"x": bits % 16}, "evidence_refs": [],
                  "requested_resources": {"queries": 1}}
    return {"action": action, "state": {"probes": len(observed)}}
'''


@pytest.mark.parametrize(
    "source, queried, observations",
    [(COUNT_READER, [0], [(1, 1, 1, 1)]),
     (VALUE_READER, [0, 4, 7, 8, 10, 13],
      [(1, 1, 1, 1), (1, 1, 1, 0), (1, 0, 0, 0),
       (1, 1, 0, 0), (1, 0, 1, 1), (1, 0, 1, 1)])])
def test_a_step_policy_governs_admitted_probes_in_a_real_episode(
        source, queried, observations):
    """The policy's own decision is what the world executes and grades.

    `COUNT_READER` probes once and stops, because it reads the length of the
    observation list and that is the only input it consults. `VALUE_READER`
    keeps probing, because its own arithmetic walks into values that force new
    inputs. Neither sequence is written in this file, so neither could be
    produced by a replay of a fixed schedule.
    """
    result = active.run_episode(
        boolean_policy.choose_action(_artifact(source)), split="dev", seed=4)

    assert all("effect" in turn for turn in result["trace"])
    assert all("refused" not in turn for turn in result["trace"])
    assert [turn["action"]["kind"] for turn in result["trace"]] == \
        ["probe"] * len(queried) + ["stop"]
    assert [turn["effect"]["observation"] for turn in result["trace"]
            if turn["action"]["kind"] == "probe"] == observations
    assert result["queried"] == queried
    assert result["committed"] is False
    assert result["final"] is None


def test_two_policies_differing_only_in_how_they_read_the_probe_differently():
    """Different reading of one identical world, different admitted probes.

    Both sources read `view["observed"]` and nothing else. One takes its
    length, the other its values. The world, the seed and the episode are the
    same, so every difference in the query sequence is attributable to the
    reading. The count reader stops after one probe; the value reader spends
    six, and they are not a prefix of one another.
    """
    counted = active.run_episode(
        boolean_policy.choose_action(_artifact(COUNT_READER)),
        split="dev", seed=4)
    valued = active.run_episode(
        boolean_policy.choose_action(_artifact(VALUE_READER)),
        split="dev", seed=4)

    # The id is an opaque digest now, so this asserts the two episodes
    # were run against the *same* task rather than a literal that no
    # longer exists. Seed 4 produces `rule-dev-<digest>`; asserting the
    # old `rule-dev-0004` here is what made this fail after N-01.
    assert counted["task_id"] == valued["task_id"]
    assert counted["task_id"] == rules.make_task("dev", 4)["task_id"]
    assert counted["queried"] == [0]
    assert valued["queried"] == [0, 4, 7, 8, 10, 13]
    assert counted["queried"] != valued["queried"]
    assert len(valued["queried"]) > len(counted["queried"])
    assert len(set(valued["queried"]) & set(counted["queried"])) == 1


READS_OBSERVATION = '''def STEP(view, state):
    y = view["observed"][-1]["y"]
    specs = [{"const": bit, "mask": 0, "pair": None} for bit in y]
    action = {"kind": "construct", "target": "boolean.commit",
              "inputs": {"specs": specs}, "evidence_refs": [],
              "requested_resources": {}}
    return {"action": action, "state": {}}
'''

REPLAYS_A_SCHEDULE = '''def STEP(view, state):
    specs = [{"const": 1, "mask": 0, "pair": None}] * 4
    action = {"kind": "construct", "target": "boolean.commit",
              "inputs": {"specs": specs}, "evidence_refs": [],
              "requested_resources": {}}
    return {"action": action, "state": {}}
'''


def _state_with_observation(y: list) -> dict:
    public_state = _public_state(queried=(3,))
    public_state["observed"] = [{"x": 3, "y": y}]
    return public_state


def test_substituting_only_the_observation_changes_the_effect_it_causes():
    """One policy, one world, one changed input, a different committed world.

    The assertion is on the score, not on the recorded action, because a
    policy can record a different action and cause no difference at all.
    """
    task = rules.make_task("dev", 4)
    effects = {}
    for label, y in (("truth", [1, 0, 0, 1]), ("complement", [0, 1, 1, 0])):
        decision = _decide(READS_OBSERVATION, _state_with_observation(y))
        effects[label] = _commit(task, decision["inputs"]["specs"])

    assert [spec["const"] for spec in
            _decide(READS_OBSERVATION,
                    _state_with_observation([1, 0, 0, 1]))["inputs"]["specs"]
            ] == [1, 0, 0, 1]
    assert effects["truth"]["overall"] == 0.1875
    assert effects["complement"]["overall"] == 0.0
    assert effects["truth"]["overall"] != effects["complement"]["overall"]


def test_a_policy_that_replays_a_schedule_fails_that_same_substitution():
    """The control for the test above, so it cannot pass vacuously.

    Same two observations, same world, same assertions. The only difference is
    that this policy never reads the view, and it is therefore blind to the
    substitution the previous test detects.
    """
    task = rules.make_task("dev", 4)
    effects = {}
    for label, y in (("truth", [1, 0, 0, 1]), ("complement", [0, 1, 1, 0])):
        specs = _decide(REPLAYS_A_SCHEDULE,
                        _state_with_observation(y))["inputs"]["specs"]
        effects[label] = _commit(task, specs)

    assert effects["truth"] == effects["complement"]
    assert effects["truth"]["overall"] == 0.0625
    assert effects["complement"]["overall"] == 0.0625


def _leaves(value, path="$"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, "%s.%s" % (path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, "%s[%d]" % (path, index))
    else:
        yield path, value


def test_the_policy_view_withholds_every_hidden_value_at_every_depth():
    """Pinned field list, checked by value not by name.

    The existing bridge test checks that the key `tables` is absent. A hidden
    truth table is a number, and it would pass that test happily while riding
    in `observed` or under `public_world`. So every leaf of the delivered view
    is compared against the task's actual hidden tables.
    """
    task = rules.make_task("dev", 4)
    session = rules.RuleSession(task)
    for x in (3, 7, 11):
        session.query(x)
    view = boolean_policy._shared_view(active.public_state(session))

    assert set(view) == {
        "instrument", "task_id", "observed", "remaining", "public_world",
        "action_schema"}
    assert set(view["public_world"]) == {
        "split", "max_queries", "hypothesis_class"}

    hidden = set(task["tables"])
    assert len(hidden) == rules.N_OUTPUTS
    leaked = [(path, value) for path, value in _leaves(view)
              if isinstance(value, int) and not isinstance(value, bool)
              and value in hidden]
    assert leaked == []

    serialized = json.dumps(view, sort_keys=True)
    assert "tables" not in serialized
    assert "score" not in serialized


def test_the_only_door_to_the_hidden_tables_is_closed_before_the_child():
    """The id is a digest, and the child still cannot reach the tables.

    This test used to assert the opposite. It asserted that
    `task_id == "rule-dev-0004"` and that the last segment parsed as the
    generator seed - documenting a *live* leak. N-01 changed the id to
    `rule-<split>-<digest>`, so the assertion became false and the test
    failed. The repair was right and the test was describing the world
    as it used to be.

    Two separate things are worth asserting and the old test conflated
    them. The id no longer *names* its seed, and the child cannot import
    `boolean_rule` to regenerate the tables even if it could recover the
    seed. The second is the closed door; the first is N-01. The seed is
    still on the task dict for the grader, and the view does not carry
    it.
    """
    task = rules.make_task("dev", 4)
    view = boolean_policy._shared_view(_public_state(4))

    # The id is opaque: it does not name the seed, and it does not
    # parse as one.
    assert view["task_id"] == task["task_id"]
    assert view["task_id"] != "rule-dev-0004"
    assert not view["task_id"].endswith("0004")
    assert view["task_id"].split("-")[:2] == ["rule", "dev"]
    assert rules.make_task("dev", 4)["tables"] == task["tables"]

    # The grader keeps the seed; the policy's view does not.
    assert "seed" not in view

    reachable = '''def STEP(view, state):
    import experiments.ad01.boolean_rule as br
    seed = int(view["task_id"].split("-")[-1])
    action = {"kind": "stop", "target": "boolean.task",
              "inputs": {"tables": [list(t) for t in
                        br.make_task("dev", seed)["tables"]]},
              "evidence_refs": [], "requested_resources": {}}
    return {"action": action, "state": {}}
'''
    with pytest.raises(method_exec.MethodExecutionError,
                       match="imports-forbidden"):
        method_exec.verify_step_source(reachable, "STEP")

    refusal = _refusal(_decide(reachable, _public_state(4)))
    assert "refused: imports-forbidden" in refusal["reason"]


def test_the_opaque_id_is_still_recoverable_by_enumeration():
    """Why N-01 is a partial repair, and this is the test that shows it.

    The digest is unsalted and deterministic over a 0..9999 seed space,
    so a policy holding the public `task_id` can iterate the seeds and
    find the one that produces it. This costs a thousand hashes and no
    cleverness, which is why N-01 is recorded as a partial repair rather
    than a closure.

    The child cannot act on the result - `verify_step_source` refuses
    the import, which is what the previous test pins - so this is not a
    live exploit. It is the measurement that stopped me recording N-01 as
    repaired, and it is written to fail the moment the id scheme is
    keyed or the seed space is widened.
    """
    target = rules.make_task("dev", 4)["task_id"]

    recovered = None
    for seed in range(10_000):
        if rules.make_task("dev", seed)["task_id"] == target:
            recovered = seed
            break

    assert recovered is not None, (
        "the id is no longer recoverable by enumeration over 0..9999, so "
        "N-01 can be recorded as repaired rather than partial and N-34 "
        "should be closed: %s" % target)

    reachable = '''def STEP(view, state):
    import experiments.ad01.boolean_rule as br
    seed = int(view["task_id"].split("-")[-1])
    action = {"kind": "stop", "target": "boolean.task",
              "inputs": {"tables": [list(t) for t in
                        br.make_task("dev", seed)["tables"]]},
              "evidence_refs": [], "requested_resources": {}}
    return {"action": action, "state": {}}
'''
    with pytest.raises(method_exec.MethodExecutionError,
                       match="imports-forbidden"):
        method_exec.verify_step_source(reachable, "STEP")

    refusal = _refusal(_decide(reachable, _public_state(4)))
    assert "refused: imports-forbidden" in refusal["reason"]


RELOAD_SCRIPT = '''import json, os, sys
view_path, state_path, source_path, dsn, allocation_id, operation_id = sys.argv[1:7]
from experiments.ad01 import policy_step
source = open(source_path).read()
record = policy_step.make_policy_artifact(source, origin="authored-control")
view = json.load(open(view_path))
state = json.load(open(state_path)) if os.path.exists(state_path) else {}
result = policy_step.run_policy_step(record, view, state, timeout_ms=20000,
                                     dsn=dsn, allocation_id=allocation_id,
                                     operation_id=operation_id)
json.dump(result["state"], open(state_path, "w"))
print(json.dumps({"action": result["action"], "state": result["state"]}))
'''


def test_policy_state_survives_a_fresh_interpreter(tmp_path):
    """Retention across processes, not across object lifetimes.

    Two separate `subprocess` runs share nothing but the state file: the
    second interpreter never imports the first's modules, never sees the
    first's memory, and must resume from the serialized state alone. A policy
    that accumulated its state in a closure would return the same answer in
    both.
    """
    source_path = tmp_path / "policy.py"
    source_path.write_text(
        'def STEP(view, state):\n'
        '    seen = int(state.get("seen", 0)) + 1\n'
        '    action = {"kind": "diagnose",\n'
        '              "target": view["task_content"]["task_id"],\n'
        '              "inputs": {"seen": seen}, "evidence_refs": [],\n'
        '              "requested_resources": {}}\n'
        '    return {"action": action, "state": {"seen": seen}}\n')
    view_path = tmp_path / "view.json"
    view_path.write_text(json.dumps(policy_step.materialize_view(
        task={"task_id": "t-1", "family": "software"},
        observations=[], open_questions=[], last_result=None,
        eligible_methods=[], remaining={"steps": 6})))
    state_path = tmp_path / "state.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s" % (ROOT, ROOT / "src")

    # Three executions, three operation identities. The executor reads back the
    # first receipt rather than executing again for a repeated id, so reusing
    # one here would return `seen: 1` on every run and the test would pass
    # against a child that never ran the second or third time.
    with execution_authority("armreload") as auth:
        def run(step):
            return subprocess.run(
                [sys.executable, "-c", RELOAD_SCRIPT, str(view_path),
                 str(state_path), str(source_path), auth["dsn"],
                 auth["allocation_id"], "armreload-k%d" % step],
                cwd=str(ROOT), capture_output=True, text=True, timeout=120,
                env=env)

        first = run(0)
        assert first.returncode == 0, first.stderr
        assert json.loads(first.stdout)["action"]["inputs"] == {"seen": 1}
        assert json.loads(state_path.read_text()) == {"seen": 1}

        second = run(1)
        assert second.returncode == 0, second.stderr
        assert json.loads(second.stdout)["action"]["inputs"] == {"seen": 2}

        third = run(2)
        assert third.returncode == 0, third.stderr
        assert json.loads(third.stdout)["action"]["inputs"] == {"seen": 3}


def _step_view():
    return policy_step.materialize_view(
        task={"task_id": "t-1", "family": "software"}, observations=[],
        open_questions=[], last_result=None, eligible_methods=[],
        remaining={"steps": 6})


SPIN_SOURCE = '''def STEP(view, state):
    total = 0
    while True:
        total = total + 1
'''


def test_the_cpu_bound_kills_a_spinning_policy_without_a_wall_timeout():
    """`cpu_seconds` is enforced, and it is a CPU bound.

    One CPU-second of budget and a generous sixty-second wall limit, so the
    only thing that can stop this child is the rlimit. The kill signal is
    `-9` with no timeout flag, which is what distinguishes the two bounds from
    the outside.

    Both facts are read from the settled receipt rather than from the refusal
    text. A child that runs and fails settles its own receipt and the executor
    refuses with one message that every execution failure produces, so the
    message alone cannot tell this kill from any other. Reading the receipt
    back is the idiom `test_s89a1_contract.py` established for the same
    reason, and it is what keeps the assertion about the child rather than
    about the wording.
    """
    started = time.monotonic()
    with execution_authority("armspin") as auth:
        with pytest.raises(method_exec.MethodExecutionError):
            policy_step.run_policy_step(
                _artifact(SPIN_SOURCE), _step_view(), {},
                timeout_ms=60000, cpu_seconds=1,
                dsn=auth["dsn"], allocation_id=auth["allocation_id"],
                operation_id=auth["operation_id"])
        reason = _child_receipt(auth["dsn"], auth["operation_id"])
    elapsed = time.monotonic() - started

    assert reason["returncode"] == -9, reason
    assert reason["timed_out"] is False, reason
    assert elapsed < 60


def test_a_step_policy_has_no_way_to_burn_wall_time_without_cpu():
    """So the two bounds do not coincide in practice.

    A policy that idles would outlive the CPU budget, because `RLIMIT_CPU`
    counts CPU time and not elapsed time. One cannot be written here: imports
    are refused, so `time.sleep` is unreachable, and every loop a STEP source
    can express spends the budget as it runs. That is why the wall timeout is
    the backstop for a wedged child and the CPU limit is the gate on a runaway
    loop, rather than the two being redundant.
    """
    sleeper = ('def STEP(view, state):\n'
               '    import time\n'
               '    time.sleep(30)\n'
               '    action = {"kind": "stop", "target": "boolean.task",\n'
               '              "inputs": {}, "evidence_refs": [],\n'
               '              "requested_resources": {}}\n'
               '    return {"action": action, "state": {}}\n')

    with pytest.raises(method_exec.MethodExecutionError,
                       match="imports-forbidden"):
        method_exec.verify_step_source(sleeper, "STEP")


BOUNDED_SOURCE = '''def STEP(view, state):
    total = 0
    for index in range(200000):
        if index % 3 == 0:
            total = total + 1
    action = {"kind": "stop", "target": "boolean.task", "inputs": {},
              "evidence_refs": [], "requested_resources": {}}
    return {"action": action, "state": {"total": total}}
'''


def test_a_bounded_policy_completes_under_a_one_second_cpu_budget():
    """The bound is a ceiling, not a cost: ordinary work still runs.

    Twenty times the spin's iteration count finishes inside the same one
    CPU-second budget that killed it. The limit gates a runaway rather than
    rationing a policy, which is what makes it usable as a default.
    """
    with execution_authority("armbounded") as auth:
        result = policy_step.run_policy_step(
            _artifact(BOUNDED_SOURCE), _step_view(), {},
            timeout_ms=60000, cpu_seconds=1,
            dsn=auth["dsn"], allocation_id=auth["allocation_id"],
            operation_id=auth["operation_id"])

    assert result["action"]["kind"] == "stop"
    assert result["state"]["total"] > 0
    launcher = result["receipt"]["details"]["raw_payload"]["launcher_receipt"]
    assert launcher["data"]["timed_out"] is False
    assert launcher["_verdict"] == "success"


def test_the_output_bound_is_the_exact_cap_and_not_a_soft_hint():
    """Output is truncated to the byte cap, and the step then fails.

    A policy that prints 200 KB cannot smuggle it past a 1 KB cap, and cannot
    return a valid-looking action by having the cap applied after the envelope
    is read: the truncated stream does not parse, so the step is refused.

    The retained bytes are read from the settled receipt. The refusal carries
    no stream, so the assertion about the cap has to read the record the child
    settled, which is where the retained output lives.
    """
    noisy = ('def STEP(view, state):\n'
             '    print("z" * 200000)\n'
             '    action = {"kind": "stop", "target": "boolean.task",\n'
             '              "inputs": {}, "evidence_refs": [],\n'
             '              "requested_resources": {}}\n'
             '    return {"action": action, "state": {}}\n')

    with execution_authority("armoutput") as auth:
        for cap in (1024, 8192, 65536):
            with pytest.raises(method_exec.MethodExecutionError):
                policy_step.run_policy_step(
                    _artifact(noisy), _step_view(), {},
                    timeout_ms=20000, max_output_bytes=cap,
                    dsn=auth["dsn"], allocation_id=auth["allocation_id"],
                    operation_id="armoutput-%d" % cap)
            data = _child_receipt(auth["dsn"], "armoutput-%d" % cap)
            retained = data.get("stdout")
            assert retained is not None, (cap, sorted(data))
            assert len(retained) == cap, (cap, len(retained))

    assert policy_step.step_limits() == {
        "timeout_ms": policy_step.STEP_TIMEOUT_MS,
        "cpu_seconds": policy_step.STEP_CPU_SECONDS,
        "max_output_bytes": policy_step.STEP_MAX_OUTPUT_BYTES}
    assert (policy_step.STEP_TIMEOUT_MS, policy_step.STEP_CPU_SECONDS,
            policy_step.STEP_MAX_OUTPUT_BYTES) == (10_000, 10, 65_536)


QUIET_STEP = '''def STEP(view, state):
    action = {"kind": "diagnose", "target": "boolean.task", "inputs": {},
              "evidence_refs": [], "requested_resources": {}}
    return {"action": action, "state": {}}
'''

CHATTY_STEP = '''def STEP(view, state):
    print("hello")
    action = {"kind": "diagnose", "target": "boolean.task", "inputs": {},
              "evidence_refs": [], "requested_resources": {}}
    return {"action": action, "state": {}}
'''


def test_the_receipt_does_not_claim_os_containment():
    """The boundary is a budget and a source check, not a sandbox.

    The launcher reports `containment: False` under the `local-process`
    profile. The child is a normal process on the host, bounded by a wall
    timeout, an `RLIMIT_CPU`, an output cap and a refused-source check. Anyone
    reading a STEP run as sandboxed is reading more than the receipt says.
    """
    with execution_authority("armreceipt") as auth:
        result = policy_step.run_policy_step(
            _artifact(QUIET_STEP), _step_view(), {}, timeout_ms=20000,
            dsn=auth["dsn"], allocation_id=auth["allocation_id"],
            operation_id=auth["operation_id"])

    launcher = result["receipt"]["details"]["raw_payload"]["launcher_receipt"]
    assert launcher["containment"] is False
    assert launcher["profile"] == "local-process"
    assert launcher["parse"] == "typed-json"
    assert launcher["outcome"] == "success"
    assert launcher["truncated"] is False
    # `supervised` names whether a supervisor watched the child, and it is not
    # the same claim as `containment`. A supervised child is still a normal
    # process on this host: the boundary is a budget and a source check. The
    # assertion names the key and reads its value, so a supervisor appearing
    # later shows up as a value change rather than as a silently widened key
    # set the test never looks at again.
    assert sorted(launcher["data"]) == [
        "supervised", "timed_out", "wall_ms", "worker"]
    assert launcher["data"]["supervised"] is True


def test_stdout_is_the_channel_so_a_printing_policy_is_refused():
    """The child shares one pipe with the launcher receipt.

    `print` is not forbidden in a STEP policy. Any line it writes precedes the
    driver's JSON on the same stream, so the stream stops parsing and the step
    is refused even though the policy returned a perfectly well-formed action.
    A policy that logs cannot govern, and the failure names the policy rather
    than the environment.

    The child exits cleanly, which is the point: the policy did not crash and
    the environment did not fail. It returned `0` and its own output is what
    stopped the envelope parsing, so the receipt has to show a clean return
    code beside the line it wrote. `parse` is the executor's reading of that
    stream and is not `typed-json`.
    """
    with execution_authority("armchatter") as auth:
        with pytest.raises(method_exec.MethodExecutionError):
            policy_step.run_policy_step(
                _artifact(CHATTY_STEP), _step_view(), {}, timeout_ms=20000,
                dsn=auth["dsn"], allocation_id=auth["allocation_id"],
                operation_id=auth["operation_id"])
        reason = _child_receipt(auth["dsn"], auth["operation_id"])

    assert reason["returncode"] == 0, reason
    assert reason["timed_out"] is False, reason
    assert "hello" in reason["stdout"], reason
    assert method_exec.verify_step_source(CHATTY_STEP, "STEP") == "STEP"
