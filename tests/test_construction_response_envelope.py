"""The construction prompt never says what shape the *response* must be.

`treatment_prompt` tells the model to return
`{"action": <action>, "state": <object>}`. That is the shape the policy's
`STEP` function must return at run time — `method_exec`'s
`result_envelope` — and it is correctly in the prompt as a constraint on
the source it writes.

It is not the shape the *response* must be. `packet.parse_construction_response`
reads a JSON object with an `entry` field holding the source, and
`s09_e2_scored.proposal_source` goes through it. So the prompt asked for
one shape and the parser wanted another, and the model — obeying the
prompt — returned bare python source that no parser would accept:

    ScoreRefused: proposal does not parse: parse-failure:
    Expecting value: line 1 column 1 (char 0)

That is a real defect and it is mine. The E2 contrasts could never have
been scored end to end, because the acquisition step and the scoring step
disagreed about the envelope. These tests pin both: the prompt states the
response shape, and a response in that shape round-trips through the real
parser.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import learner
from experiments.ad01 import method_exec
from experiments.ad01 import packet

MIGRATIONS = ROOT / "migrations"


@pytest.fixture(scope="module")
def authority():
    """Real store, real allocation, one fresh operation id per execution.

    The prompt-to-action chain is proved by running the bytes a model would
    have written through the real child. Under the durable mandate that
    requires a store, an allocation and an operation id; without them the
    executor refuses before the child runs and the test would be asserting
    a refusal instead of a step.
    """
    from experiments.ad01 import trajectory
    from experiments.ad01.s09_run_isolation import create_disposable_db, \
        drop_disposable_db

    database = create_disposable_db("construction-envelope",
                                    migrations_dir=MIGRATIONS)
    try:
        trajectory.set_namespace_token("")
        campaign = "construction-env-%s" % uuid.uuid4().hex[:8]
        allocation = trajectory.authorize_campaign(
            database.dsn, campaign, authorized=100000)
        counter = {"n": 0}

        def run(source: str, views: dict, state: dict, **kwargs) -> dict:
            counter["n"] += 1
            return method_exec.run_step_out_of_process(
                source, views, state, dsn=database.dsn,
                allocation_id=allocation["allocation_id"],
                operation_id="%s-op%d" % (campaign, counter["n"]), **kwargs)

        yield run
    finally:
        drop_disposable_db(database)


def _task():
    return {"task_id": "ad01-w1-transfer-sw-00", "family": "software",
            "seed": 3, "template": "software"}


def _prompt() -> str:
    arm = learner.relevant_experience(
        _task(), ["ad01-w1-dev-gr-00"], visible=[])
    return learner.treatment_prompt(arm, _task(), arm)


def test_the_prompt_states_the_response_envelope_the_parser_requires():
    """The parser wants {"entry": "<source>"}; the prompt must say so.

    Without this the model returns bare source, correctly following the
    prompt, and the scorer refuses it.
    """
    prompt = _prompt()

    assert '"entry"' in prompt, (
        "the prompt must name the entry key the construction parser reads")
    assert "exactly one JSON object" in prompt


def test_the_step_envelope_stays_because_it_constrains_the_source():
    """Both envelopes belong, and they are different things.

    `{"action": ..., "state": ...}` is what the policy function must
    return when it runs. `{"entry": ...}` is what the model must send
    back. Conflating them is the bug; dropping either is a different one.
    """
    prompt = _prompt()
    contract = method_exec.step_contract()

    assert contract["result_envelope"]["rule"].split("{")[0] in prompt or \
        '"state"' in prompt
    assert '"entry"' in prompt


def test_a_response_in_the_stated_shape_round_trips_through_the_parser():
    source = ("def STEP(view, state):\n"
              "    return {'action': {'kind': 'stop', 'target': 't',\n"
              "                     'inputs': {}, 'evidence_refs': [],\n"
              "                     'requested_resources': {}}, 'state': {}}\n")
    response = json.dumps({"entry": source})

    parsed, problem = packet.parse_construction_response(response)

    assert problem == ""
    assert parsed == source


def test_bare_source_is_still_refused_so_the_prompt_is_doing_the_work():
    """The parser is right to refuse; the prompt was wrong to elicit it.

    If this ever passes, the parser has been loosened to accept anything,
    which would mean the prompt no longer has to be correct.
    """
    parsed, problem = packet.parse_construction_response(
        "def STEP(view, state):\n    return {}\n")

    assert parsed is None
    assert problem


def test_the_prompt_names_the_methods_a_policy_may_select():
    """`eligible_methods` was named as a view field and left empty.

    A policy that reads the view found nothing to select, so every scored
    arm reported "admitted no action that reaches a method executor". The
    prompt now carries the family's authored controls, which is what the
    scorer dispatches against.
    """
    arm = learner.relevant_experience(
        _task(), ["ad01-w1-dev-gr-00"], visible=[])
    arm["family"] = "software"
    prompt = learner.treatment_prompt(arm, _task(), arm)

    assert "Eligible methods for this task:" in prompt
    assert "seed-sw-ddmin" in prompt


def test_a_policy_that_selects_a_named_method_is_reachable(authority):
    """The chain the scorer walks: prompt names a method, source uses it.

    This is the step that was broken three ways in sequence — the response
    envelope, the empty method list, and the missing instruction to select
    one — and each break showed up only as `scored=False` downstream.
    """
    from experiments.ad01 import method_exec
    source = (
        "def STEP(view, state):\n"
        "    methods = view.get('eligible_methods') or []\n"
        "    if not methods:\n"
        "        return {'action': {'kind': 'stop', 'target': 'ad01.task',\n"
        "                         'inputs': {}, 'evidence_refs': [],\n"
        "                         'requested_resources': {}}, 'state': {}}\n"
        "    return {'action': {'kind': 'use_method',\n"
        "                     'target': 'ad01.task',\n"
        "                     'inputs': {'method_id': methods[0],\n"
        "                                'max_queries': 8},\n"
        "                     'evidence_refs': [],\n"
        "                     'requested_resources': {}}, 'state': {}}\n")
    record = method_exec.verify_step_source(source, "STEP")
    views = {"task_content": {"task_id": "t"}, "observations": [],
             "open_questions": [], "last_result": None,
             "eligible_methods": ["seed-sw-ddmin"],
             "remaining": {}, "contract_versions": {}}
    result = authority(source, views, {})

    assert result["action"]["kind"] == "use_method"
    assert result["action"]["inputs"]["method_id"] == "seed-sw-ddmin"
    assert record is not None


def test_the_prompt_shows_a_complete_action_object():
    """Naming the kinds is not the same as showing the shape.

    `policy_step.ACTION_REQUIRED` is five fields: kind, target, inputs,
    evidence_refs, requested_resources. The prompt listed the action
    *kinds* and never showed an action, so the model wrote
    `{"kind": ..., "target": ...}` and the validator refused it with
    "policy action missing: evidence_refs, inputs, requested_resources".
    That is the fourth break in the same chain, and it is the one a
    reader would most expect the prompt to have prevented.
    """
    from experiments.ad01 import policy_step

    arm = learner.relevant_experience(
        _task(), ["ad01-w1-dev-gr-00"], visible=[])
    arm["family"] = "software"
    prompt = learner.treatment_prompt(arm, _task(), arm)

    for field in policy_step.ACTION_REQUIRED:
        assert '"%s"' % field in prompt, (
            "the prompt must show the %r field; the validator requires it"
            % field)


def test_a_policy_written_to_the_prompt_shape_survives_validation():
    """The prompt's example must itself be a valid action.

    A worked example that does not validate teaches the model to write
    something the executor refuses, and the failure arrives as a step
    error rather than as a prompt defect.
    """
    import json as _json
    from experiments.ad01 import method_exec
    from experiments.ad01 import policy_step

    arm = learner.relevant_experience(
        _task(), ["ad01-w1-dev-gr-00"], visible=[])
    arm["family"] = "software"
    prompt = learner.treatment_prompt(arm, _task(), arm)
    # Split on the newline, not on "." - the JSON carries periods of its own.
    example = None
    for line in prompt.splitlines():
        if line.startswith("An action is exactly "):
            candidate = line[len("An action is exactly "):].strip()
            try:
                example = _json.loads(candidate)
            except ValueError:
                continue
            break
    assert example is not None, "no parseable action example in the prompt"

    policy_step.validate_action(example)
    assert set(example) >= set(policy_step.ACTION_REQUIRED)
    assert method_exec.verify_step_source("def STEP(view, state):\n    return {}\n", "STEP") is not None


def test_the_prompt_states_that_the_view_is_a_plain_dict():
    """The model guessed attribute access and the child raised.

    `materialize_view` returns a `dict`. The prompt listed the fields it
    holds and showed no access syntax, so the model wrote
    `view.eligible_methods` and the step died with

        AttributeError: 'dict' object has no attribute 'eligible_methods'

    Everything the model did was right — it named a real method id, used
    the right input key, and built a valid action. The one thing it could
    not know is that the parameter is a mapping, and that is the kind of
    thing a prompt exists to say.
    """
    arm = learner.relevant_experience(
        _task(), ["ad01-w1-dev-gr-00"], visible=[])
    arm["family"] = "software"
    prompt = learner.treatment_prompt(arm, _task(), arm)

    assert "view is a plain python dict" in prompt
    assert "view['" in prompt, "the prompt must show subscript access"
    assert "view.eligible_methods" not in prompt.split("Prior observations")[0]


def test_a_policy_written_to_the_stated_access_survives_the_step(authority):
    """End to end: prompt's access form, real view, real child."""
    import json as _json
    from experiments.ad01 import method_exec
    from experiments.ad01 import s09_e2_scored as scored
    from experiments.ad01 import worlds

    task = worlds.load_task(
        worlds.FROZEN_DIR, "ad01-w1-transfer-sw-00")
    methods = [scored.control_name(task, m) for m in ("ddmin", "greedy")]
    views = scored.build_views(
        task, [{"observation_id": "o", "task_id": task["task_id"],
                "capability_id": "c", "verdict": "unmeasured"}],
        eligible_methods=methods)
    source = (
        "def STEP(view, state):\n"
        "    methods = view['eligible_methods'] or []\n"
        "    if not methods:\n"
        "        return {'action': {'kind': 'stop',\n"
        "                         'target': view['task_content']['task_id'],\n"
        "                         'inputs': {}, 'evidence_refs': [],\n"
        "                         'requested_resources': {}}, 'state': {}}\n"
        "    return {'action': {'kind': 'use_method',\n"
        "                     'target': view['task_content']['task_id'],\n"
        "                     'inputs': {'method_id': methods[0],\n"
        "                                'max_queries': 8},\n"
        "                     'evidence_refs': [],\n"
        "                     'requested_resources': {'queries': 8}},\n"
        "            'state': {}}\n")
    result = authority(source, views["scored"], {}, entry="STEP")

    assert result["action"]["kind"] == "use_method"
    assert result["action"]["inputs"]["method_id"] in methods
    assert _json.dumps(result)  # the envelope is JSON-serialisable
