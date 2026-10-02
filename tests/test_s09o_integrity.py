"""Assessment integrity regressions from the byte-path review of c3e8566.

The reviewer bound a candidate policy that never investigated. It read the panel
task out of its own view, copied the witness, dropped one operation, and returned
the finished answer inline as action inputs["candidate"], scoring a bind with zero
queries and zero model calls. Two separate defects made that possible: the sealed
assessment credited a policy-supplied candidate as a task outcome, and the runtime
STEP view handed the policy the unstripped task. A third defect let compute be
free, because the comparison rule priced only queries and model calls.
"""

from experiments.ad01 import packet, policy_assess, policy_step, worlds

PANEL_TASK = "ad01-w0-within-sw-00"


def _policy(body: str) -> dict:
    return policy_step.make_policy_artifact(body, origin="authored-control")


def test_runtime_view_hides_sealed_task_fields():
    task = worlds.load_task(worlds.FROZEN_DIR, PANEL_TASK)
    view = policy_step.materialize_view(
        task=task, observations=[], open_questions=[], last_result=None,
        eligible_methods=[], remaining={"model_calls": 0})
    content = view["task_content"]
    leaked = sorted(k for k in content if k in packet.SEALED_KEYS)
    assert leaked == [], "sealed task keys reached the policy view: %r" % leaked
    assert "access_label" not in content
    assert content["task_id"] == PANEL_TASK
    assert content["family"] == task["family"]


def test_direct_candidate_in_action_inputs_is_not_credited():
    task = worlds.load_task(worlds.FROZEN_DIR, PANEL_TASK)
    source = (
        "def STEP(view, state):\n"
        "    task = view['task_content']\n"
        "    forged = dict(task)\n"
        "    action = {'kind': 'use_method', 'target': task['task_id'],\n"
        "              'inputs': {'candidate': forged},\n"
        "              'evidence_refs': [], 'requested_resources': {}}\n"
        "    return {'action': action, 'state': {'done': True}}\n")
    arm = policy_assess._run_arm(
        _policy(source), [PANEL_TASK], policy_assess.rule_for())
    accepted = [e for e in arm["effects"] if e.get("accepted")]
    assert accepted == [], (
        "a policy-supplied candidate was credited as a task outcome: %r"
        % (accepted,))
    assert arm["quality"]["preserved"] == 0
    assert arm["quality"]["reduced"] == 0
    reasons = " ".join(str(e.get("reason", "")) for e in arm["effects"])
    assert "candidate" in reasons.lower()
    assert task["task_id"] == PANEL_TASK


def test_comparison_rule_prices_policy_compute():
    cheap = {"quality": {"tasks": 2, "preserved": 2, "reduced": 2, "failed": 0},
             "resources": {"step_calls": 2, "model_calls": 0, "queries": 4,
                           "child_wall_ms": 10}}
    costly = {"quality": {"tasks": 2, "preserved": 2, "reduced": 3, "failed": 0},
              "resources": {"step_calls": 40, "model_calls": 0, "queries": 4,
                            "child_wall_ms": 10}}
    rule = policy_assess.rule_for(resource_ceiling=4)
    outcome, reason = policy_assess._decision(costly, cheap, rule)
    assert outcome == "reject", (
        "a candidate spending 40 policy steps against 2 must not bind on a"
        " one-task reduction gain; got %r because %r" % (outcome, reason))
    assert "step" in reason.lower() or "resource" in reason.lower()
