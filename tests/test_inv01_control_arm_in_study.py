"""The control arm is in the study, and each of the four blockers is gone.

M3-2 documented four blockers and deleted the function that would have
supplied a control arm. Five lanes reported E1 as PARTIAL on the strength of
that document. This file is the other answer: each blocker is a test, and a
test that would still pass with the blocker in place is not one of these.

The four, and what each test pins:

1. The selector refuses a family claimed by two members. Replaced here by
   one that answers it from the task's public shape.
2. A `seed-` capability id never runs the member's own bytes.
   `trajectory._run_member` shadows it with `seeds.run_seed` in the host.
3. The budget does not fit. The ceilings were hard-coded for one arm.
4. Nothing reads the control record: the study wrote no
   `policy_identities`, so `task_utility_verdict` found no authored arm.

Nothing under `reports/evidence/` is written or modified. Every test here
dispatches nothing: the members are executed out of process in the child
namespace, which is where a `seed-` id's shadowing is visible, and the
study's own wiring is checked by reading the source and calling the
functions the run calls.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

BUDGET = 4
ARM = "C"


def _freeze_keys(study) -> set:
    """The keys of the dict `run_study_v1` writes to `freeze.json`.

    Read off the parsed tree rather than the text or the constants: a dict
    literal's keys are nested tuples in `co_consts`, and a substring search
    over the source would also match the local variable that holds the
    block. The defect this test exists for is exactly a block that was
    built and never written, so the question is what reached the file.
    """
    import ast

    tree = ast.parse(inspect.getsource(study.run_study_v1))
    keys = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", None) != "write_text":
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            for piece in ast.walk(arg):
                if not isinstance(piece, ast.Call):
                    continue
                name = getattr(piece.func, "attr", None) or getattr(
                    piece.func, "id", None)
                if name != "dumps":
                    continue
                for inner in ast.walk(piece):
                    if isinstance(inner, ast.Dict):
                        for key in inner.keys:
                            if isinstance(key, ast.Constant) \
                                    and isinstance(key.value, str):
                                keys.add(key.value)
    return keys


# ---------------------------------------------------------------------------
# blocker 2: the id namespace
# ---------------------------------------------------------------------------


def test_a_control_member_runs_its_own_bytes_not_the_host_dispatch():
    """A member whose source would raise is executed, so the bytes ran.

    This is the shadowing measurement. `_run_member` looks the
    `capability_id` up in `seeds.SEED_CAPABILITIES` and, on a hit, calls
    `seeds.run_seed` in the host and returns without staging the source. A
    `seed-` id therefore returns a result for a member whose source never
    ran; the result is indistinguishable from a real execution unless the
    source is written to announce itself. Here the control's ids are `ctl-`
    and the bytes are counted.
    """
    from experiments.ad01 import control_arm, method_exec, seeds, worlds

    repertoire = control_arm.control_repertoire("ad01-ctl")
    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-within-sw-00")

    for member in repertoire["members"]:
        assert member["capability_id"] not in seeds._KNOWN, (
            "%s collides with the host dispatch table, so the host would run "
            "seeds.run_seed instead of these bytes"
            % member["capability_id"])

    control = next(m for m in repertoire["members"]
                   if m["capability_id"] == "ctl-software-greedy")
    result = method_exec.run_member_out_of_process(control, task,
                                                   max_queries=BUDGET)

    assert result["queries"] == BUDGET
    assert result["candidate"]["task_id"] == "ad01-w0-within-sw-00"

    shadowed = {"capability_id": "seed-sw-greedy", "entry": "ENTRY",
                "method_source": "def ENTRY(task, oracle, max_queries=16):\n"
                                 "    raise RuntimeError('never run')\n",
                "source_digest": "0" * 64}
    from experiments.ad01 import trajectory
    host = trajectory._run_member(shadowed, task, max_queries=BUDGET)

    assert host["executed_source"] == "greedy", (
        "the control's own execution is only evidence if a seed- id does"
        " something different, and this is that: the host returned the method"
        " name without ever staging the source above")


def test_the_control_ids_are_namespaced_and_digests_are_of_their_own_bytes():
    """No id collides, and every digest is a digest of the source."""
    from experiments.ad01 import control_arm, seeds

    repertoire = control_arm.control_repertoire("ad01-ctl")
    members = repertoire["members"]

    assert [m["capability_id"] for m in members] == [
        "ctl-software-ddmin", "ctl-software-greedy",
        "ctl-graph-ddmin", "ctl-graph-greedy"]
    assert not (set(m["capability_id"] for m in members)
                & set(seeds._KNOWN))
    for member in members:
        assert member["source_digest"] == hashlib.sha256(
            member["method_source"].encode("utf-8")).hexdigest(), (
            "%s carries a digest that is not a digest of its own source"
            % member["capability_id"])
    by_family = {}
    for member in members:
        by_family.setdefault(member["scope"]["family"], []).append(member)
    for family, pair in by_family.items():
        assert len(pair) == 2
        assert pair[0]["method_source"] != pair[1]["method_source"], (
            "%s: the two members are the same bytes, which is the C15 shape"
            % family)


# ---------------------------------------------------------------------------
# blocker 1: the selector
# ---------------------------------------------------------------------------


def test_the_selector_answers_a_family_two_members_both_claim():
    """The case `_v1_use_policy_fallback` refused by design.

    The refusal was correct for what the fallback had: a repertoire with one
    member per family, where two members in a family meant the study could
    not say which one it meant. A control arm has two per family by
    construction, so the fallback's precondition is what has to change, not
    its refusal.
    """
    from experiments.ad01 import control_arm, policy_step, worlds

    repertoire = control_arm.control_repertoire("ad01-ctl")
    source = control_arm.selector_source(repertoire)
    policy = policy_step.compile_step(source, origin="<control-arm-test>")

    assert callable(policy), "the control selector must compile to a STEP"
    eligible = [m["capability_id"] for m in repertoire["members"]]
    picked = set()
    for world in (0, 1, 2):
        for task_id in control_arm.control_tasks(world):
            task = worlds.load_task(worlds.FROZEN_DIR, task_id)
            from experiments.ad01 import packet
            decision = policy(
                {"task_content": packet.strip_task(task),
                 "eligible_methods": eligible, "observations": [],
                 "open_questions": [], "last_result": None, "remaining": {}},
                {})
            action = decision["action"]

            assert action["kind"] == "use_method"
            assert action["inputs"]["method_id"] in eligible
            assert action["inputs"]["max_queries"] == BUDGET
            picked.add(action["inputs"]["method_id"])

    assert picked & {"ctl-software-ddmin", "ctl-software-greedy"}, (
        "no software task was answered, so the control arm would record a"
        " refusal on every software row")


def test_the_selector_never_reads_list_position():
    """Reordering the repertoire must not change the answer.

    `eligible[0]` is the bug `28c3e65` fixed: in
    `repertoire-w1-I.json` position zero was the graph member, so all three
    software tasks were refused as family-mismatched. A selector that
    answers by shape is unaffected by the order it was handed its members
    in, and this is what makes that true rather than asserted.

    Both families are checked, and the graph one is the load-bearing case:
    `sorted()` puts `ddmin` first in both families, the measured table
    answers `ddmin` for 17 of the 18 study tasks, and it answers `greedy`
    for all 6 graph tasks. A selector reading position would therefore
    agree with the measurement everywhere except the graph rows, so a
    software-only check would pass against `named[0]`.
    """
    from experiments.ad01 import control_arm, policy_step, worlds, packet

    repertoire = control_arm.control_repertoire("ad01-ctl")
    tables = control_arm.measured_tables(repertoire)

    def answer(doc, task_id):
        policy = policy_step.compile_step(
            control_arm.selector_source(
                doc, features=tables["shape"], coarse=tables["template"]),
            origin="<order-test>")
        view = packet.strip_task(
            worlds.load_task(worlds.FROZEN_DIR, task_id))
        return policy(
            {"task_content": view,
             "eligible_methods": [m["capability_id"]
                                  for m in doc["members"]],
             "observations": [], "open_questions": [],
             "last_result": None, "remaining": {}}, {})

    shuffled = dict(repertoire)
    shuffled["members"] = list(reversed(repertoire["members"]))
    for task_id, want in (("ad01-w0-within-sw-00", "ctl-software-ddmin"),
                          ("ad01-w0-within-gr-00", "ctl-graph-greedy")):
        forward = answer(repertoire, task_id)
        backward = answer(shuffled, task_id)

        assert forward["action"]["inputs"]["method_id"] \
            == backward["action"]["inputs"]["method_id"] == want, (
            "%s: the pick changed when the member list was reordered, or"
            " moved off the measured shape answer, so the selector is"
            " reading position rather than task shape" % task_id)


def test_the_selector_refuses_a_shape_no_measurement_covers():
    """An uncovered shape is a refusal, not a guess and not a position.

    The two feature tables are finite and were measured. A task outside
    both has nothing to select on, and the answer it gets is a refusal —
    which is what the original rule was for, and what a control arm that
    answered anyway would be violating.
    """
    from experiments.ad01 import control_arm, policy_step

    repertoire = control_arm.control_repertoire("ad01-ctl")
    policy = policy_step.compile_step(
        control_arm.selector_source(repertoire, features={}, coarse={}),
        origin="<uncovered-test>")

    with pytest.raises(ValueError) as refusal:
        policy(
            {"task_content": {"task_id": "ad01-x", "family": "software",
                              "template": "never-measured", "ops": [1]},
             "eligible_methods": [m["capability_id"]
                                  for m in repertoire["members"]],
             "observations": [], "open_questions": [],
             "last_result": None, "remaining": {}}, {})

    assert "no member of family" in str(refusal.value)


def test_the_study_hands_the_control_its_own_selector():
    """`_fresh_use` must not route the control through the fallback.

    The fallback refuses the control's repertoire, so a control arm run
    through it produces twenty-four refusals and a clean exit code.
    """
    from scripts import inv01_study as study

    source = inspect.getsource(study._fresh_use)

    assert "policy_path" in source, (
        "_fresh_use has no way to hand in a selector, so the control arm can"
        " only reach the single-member fallback that refuses it")
    assert inspect.getsource(study._v1_control_arm)


# ---------------------------------------------------------------------------
# blocker 3: the budget
# ---------------------------------------------------------------------------


def test_the_control_arm_gets_its_own_subdivision():
    """`free_of` counts every child against its parent.

    The second run refused the control's use phase with
    `insufficient-authority` after six campaign subdivisions had already
    been carved out of the study's allocation. The control has no campaign,
    so it names its own child, and the study is authorized one allowance
    wider per control arm so there is something left to subdivide.
    """
    from scripts import inv01_study as study

    from experiments.ad01 import s09_cap_sheet
    allowance = int(s09_cap_sheet.load().unit_allowance.units)
    campaigns = study._v1_campaign_count(6)

    assert study._v1_study_units(campaigns) == allowance * (
        campaigns + study._v1_use_arms() - 1), (
        "the study is not authorized wide enough to hold a subdivision per"
        " control arm, so the control's use phase is refused for"
        " insufficient authority after the campaigns take theirs")
    assert study._v1_study_units(campaigns) > allowance * campaigns

    source = inspect.getsource(study.run_study_v1)

    assert "_v1_ensure_alloc" in source, (
        "the control's use phase is admitted against the study's own"
        " allocation, whose balance the campaigns have already consumed")
    assert '"ad01-control-%s"' in source
    assert inspect.getsource(study._v1_ensure_campaign_alloc).count(
        "_v1_ensure_alloc") == 1, (
        "the campaign subdivision must route through the shared helper, or"
        " the two arms' allocation paths have drifted apart")


def test_the_control_arm_runs_through_its_own_fresh_process():
    """The CLI refuses an arm outside ("I", "R"), and that is correct.

    `cli.py:238` closes that vocabulary because I and R are the two
    orderings of one trajectory. A control arm is not a third ordering: it
    has no campaign and no rotation. So it runs through
    `experiments.ad01.control_use`, which makes the same `run_use` call in
    a fresh process, and the process boundary is what matters — it is what
    makes the child's member bytes the bytes that run.
    """
    from scripts import inv01_study as study

    source = inspect.getsource(study._fresh_use)

    assert "experiments.ad01.control_use" in source, (
        "the control arm is being sent to the CLI's use branch, which"
        " refuses an arm outside ('I', 'R') with a usage error and exits"
        " before the study sees a record")
    assert 'policy_path' in source
    from experiments.ad01 import control_use
    text = inspect.getsource(control_use)
    assert "trajectory.run_use" in text, (
        "the control's entry point must call the same run_use the CLI does,"
        " or the two arms are measured by different code")
    assert "compile_step" in text, (
        "a policy handed to run_use as source text raises at the call and is"
        " recorded as a policy that failed rather than one that governed")


def test_a_fallback_record_is_not_an_executed_policy():
    """A run where the control fell back must not read as `distinct`.

    The third real run spent its whole ceiling on the acquired arm. All
    eighteen control records fell back to `incumbent`, each carrying
    `executed: "incumbent"` and `executed_source: "incumbent"` while the
    selected member's body naming `ddmin` sat in another field. The gate
    read that as `distinct: True` over two arms where one ran nothing.
    Three separate readings had to change, and each is pinned here.
    """
    from experiments.ad01 import control_distinctness

    fallback = {"task_id": "t", "executed": "incumbent",
                "executed_source": "incumbent",
                "method_source": "def ENTRY(t, o, method='ddmin'):\n",
                "output": {}, "costs": {"witness_queries": 0},
                "fallback_reason": "member execution failed: ceiling reached"}
    real = {"task_id": "t", "executed": "ctl-software-greedy",
            "executed_source": "method='greedy'", "output": {"ops": [1]},
            "costs": {"witness_queries": 4}}

    assert control_distinctness.executed_policy_id(fallback) == "", (
        "a fallback names no policy; `incumbent` is the absence of one")
    assert control_distinctness._strategy_of(fallback) == "", (
        "a fallback's retained body is not evidence the member ran")

    verdict = control_distinctness.control_distinct([fallback], [real])

    assert verdict["distinct"] is False, (
        "a task where one arm fell back is unmeasured, not distinct: the"
        " empty id and the real id are different sets, which is exactly"
        " what made the third run a false pass")
    assert [row["task_id"]
            for row in verdict["unnamed_executed_policy"]] == ["t"]
    assert verdict["unnamed_executed_policy"][0]["fallback"]["control"] == [
        "member execution failed: ceiling reached"]
    assert "at least one arm" in verdict["refusal"]


def test_the_study_admits_three_arms_not_two():
    """The use loop walks two acquired orderings before the control.

    The ceiling derived on two arms came to exactly 4662, which is what the
    acquired arm alone spends, so the control had nothing left and every
    one of its records fell back. A ceiling sized on the arms the loop
    actually walks is the only one that can be spent by them.
    """
    from scripts import inv01_study as study

    assert study.ACQUIRED_ARMS == ("I", "R")
    assert study._v1_use_arms() == 3, (
        "the study runs two acquired orderings and a control, so the"
        " ceiling and the authority must be sized for three")
    ceilings = study._v1_ceilings(study._v1_use_arms())
    acquired = (study._v1_acquisition_budget()["execution_units"]
                + study._v1_use_budget(2)["execution_units"])
    assert ceilings["max_execution_units"] > acquired, (
        "the ceiling must exceed what the acquired arm alone spends, or"
        " the control is refused for insufficient authority")
    assert study._v1_study_units(6) > 209216 * 6


def test_the_result_pairs_the_control_against_one_acquired_ordering():
    """Two acquired orderings, one comparison.

    The use loop runs I and R over the same 18 tasks, so pairing the
    control's 18 records against all 36 acquired records counts every task
    twice. The mean delta is unchanged in value but the task count is
    doubled, and a reader counting rows in the artifact would see 36
    paired tasks where there are 18.
    """
    from experiments.ad01 import control_arm_result as result

    def record(arm, task_id, **extra):
        row = {"record_id": "%s-%s" % (arm, task_id), "arm": arm,
               "task_id": task_id, "domain": "software",
               "executed": "%s-x" % arm, "executed_source": "method='greedy'",
               "output": {"ops": [1, 2]}, "final_measure": 2,
               "initial_measure": 4, "normalized_reduction": 0.5,
               "verdict": "preserved", "costs": {"witness_queries": 4}}
        row.update(extra)
        return row

    records = [record("C", "t%d" % i, study_arm="C") for i in range(3)]
    records += [record(arm, "t%d" % i)
                for arm in ("I", "R") for i in range(3)]

    control, acquired = result.split_arms(records)

    assert len(control) == 3
    assert len(acquired) == 6
    orderings = result.split_acquired_orderings(acquired)
    assert sorted(orderings) == ["I", "R"]
    assert len(orderings["I"]) == 3
    paired = result.per_task(result.arm_rows(control),
                             result.arm_rows(orderings["I"]))
    assert len(paired) == 3, (
        "pairing against both orderings counts every task twice, so the"
        " artifact's paired-task count is double the real one")
    both = result.per_task(result.arm_rows(control),
                           result.arm_rows(acquired))
    assert len(both) == 6


def test_the_ceilings_are_derived_from_the_arms_that_run():
    """No study ceiling is a literal, and two arms fit inside one."""
    from scripts import inv01_study as study

    assert "960" not in inspect.getsource(study._v1_admit), (
        "_v1_admit still carries a hard-coded witness ceiling")
    assert "5328" not in inspect.getsource(study._v1_admit)

    acquisition = study._v1_acquisition_budget()
    one = study._v1_use_budget(1)
    two = study._v1_use_budget(2)
    three = study._v1_use_budget(3)
    ceilings = study._v1_ceilings(study._v1_use_arms())

    assert two["witness_queries"] == 2 * one["witness_queries"]
    assert two["execution_units"] == 2 * one["execution_units"]
    assert three["witness_queries"] == 3 * one["witness_queries"]
    assert ceilings["max_witness_queries"] > (
        acquisition["witness_queries"] + three["witness_queries"]), (
        "the ceiling must exceed the sum of what every phase admits."
        " Sized at exactly the sum it was 6660 against 6660, the first two"
        " phases consumed it all, and the control's last world fell back on"
        " every task with 'ceiling max_execution_units=6660 reached at"
        " 6660'. A budget with no headroom is a race between phases for"
        " the last unit, and the phase that loses is the one the loop"
        " reaches last.")


def test_the_ceiling_covers_what_every_phase_actually_admits():
    """The sum of the halves is at least the sum of the requests.

    The per-trajectory and per-arm `need` dicts are the numbers admission
    compares against, so a ceiling below their sum refuses a run that is
    within the study's own design. This is the check that would have caught
    the use-only ceiling before it cost a run.
    """
    from scripts import inv01_study as study

    acquisition = study._v1_acquisition_budget()
    use = study._v1_use_budget(study._v1_use_arms())
    ceilings = study._v1_ceilings(study._v1_use_arms())

    # 96 diagnostic witness queries and 111 sandbox units per acquisition
    # campaign; 16 witness queries and 111 sandbox units per use task per
    # arm, which is the larger of the two arms' per-task budgets.
    wanted_queries = (96 * acquisition["campaigns"]
                      + use["tasks_per_arm"] * 16 * study._v1_use_arms())
    wanted_units = (111 * acquisition["campaigns"]
                    + use["tasks_per_arm"] * 111 * study._v1_use_arms())

    assert ceilings["max_witness_queries"] >= wanted_queries, (
        "1152 against %d: the acquisition loop alone asks 576 and two use"
        " arms ask the rest" % wanted_queries)
    assert ceilings["max_execution_units"] >= wanted_units, (
        "4662 against %d" % wanted_units)


def test_the_control_arm_fits_inside_the_study_ceiling():
    """The ceiling is spendable by the arms the study actually runs.

    A ceiling no combination of the study's own arms can spend is not a
    bound. The M3-2 measurement was 1152 against a hard-coded 960 and 7992
    against 5328; the derived ceiling has to clear the arm the study runs
    at the budget it runs it at.
    """
    from experiments.ad01 import control_arm
    from scripts import inv01_study as study

    worlds = study._v1_use_worlds()
    per_arm = control_arm.arm_budget(worlds, per_task_queries=BUDGET)
    use = study._v1_use_budget(study._v1_use_arms())
    ceilings = study._v1_ceilings(study._v1_use_arms())

    assert per_arm["tasks"] == use["tasks_per_arm"], (
        "the control's task set must be the study's own use tasks, or the"
        " two arms are not paired and the comparison is not one")
    assert per_arm["witness_queries"] == per_arm["tasks"] * BUDGET
    assert use["witness_queries"] == per_arm["tasks"] * 16 * 3, (
        "the use half is sized on the larger per-task budget and on every"
        " arm the loop walks, so all three fit rather than the cheapest one")
    assert ceilings["max_execution_units"] >= (
        study._v1_acquisition_budget()["execution_units"]
        + use["execution_units"]), (
        "the control's own use phase does not fit inside the ceiling")
    assert study._v1_use_arms() == 3, (
        "the study declares a control arm and must count it")


# ---------------------------------------------------------------------------
# blocker 4: the freeze block
# ---------------------------------------------------------------------------


def test_the_study_writes_policy_identities_for_both_origins():
    """The verdict layer needs an arm on each origin or it compares nothing.

    `task_utility_verdict` returns NOT_COMPARABLE when either
    `arms_by_origin("model-acquired")` or
    `arms_by_origin("authored-control")` is empty, and the study wrote no
    `policy_identities` at all.

    Checked against the freeze document the run actually builds, not
    against the function's text: a local variable named
    `policy_identities` survives deleting the key from what is written,
    which is the exact shape of the original defect, where the arm existed
    and nothing could read it.
    """
    from experiments.ad01 import control_arm, s09_verdict
    from scripts import inv01_study as study

    written = _freeze_keys(study)
    assert "policy_identities" in written, (
        "the freeze document written by run_study_v1 carries no"
        " policy_identities key, so no consumer can find either arm;"
        " freeze keys: %s" % sorted(written))
    assert "repertoires" in written
    identities = control_arm.policy_identities(
        ARM, control_arm.control_repertoire("ad01-ctl"))
    bundle = s09_verdict.Bundle(
        root=ROOT, freeze={"policy_identities": identities},
        construction={}, operations={}, use_records=(),
        accounting={}, assessment=())

    assert bundle.arms_by_origin(s09_verdict.ORIGIN_AUTHORED) == (ARM,)
    assert identities[ARM]["artifact"]["origin"] \
        == s09_verdict.ORIGIN_AUTHORED
    assert identities[ARM]["member_digests"]
    assert all(len(d) == 64 for d in identities[ARM]["member_digests"].values())


def test_the_acquired_block_writes_no_origin_it_cannot_earn():
    """`acquisition_identity` is handed ids and digests, and sees no receipt.

    It used to write `model-acquired` anyway. That is how the E1 freeze
    labelled a repertoire whose executed bytes are
    `experiments/doubles.py::ACQUIRED_ORDER_SOURCE`, and the verdict layer
    then compared those rows against the control and reported CONTROL_WINS.

    An absent key is the honest record: the function cannot know who wrote
    the bytes, and the verdict layer reads a missing origin as unknown.
    """
    from experiments.ad01 import control_arm

    blind = control_arm.acquisition_identity(
        "I", ["acquired-sw-x"], {"acquired": "a" * 64})
    assert "origin" not in blind["I"]["artifact"], (
        "the acquired block declared an origin with no receipt behind it")

    earned = control_arm.acquisition_identity(
        "I", ["acquired-sw-x"], {"acquired": "a" * 64},
        acquisition_evidence={"earned": True, "reason": "live provider response"})
    assert earned["I"]["artifact"]["origin"] == "model-acquired"

    refused = control_arm.acquisition_identity(
        "I", ["acquired-sw-x"], {"acquired": "a" * 64},
        acquisition_evidence={"earned": False,
                              "reason": "response is marked simulated"})
    assert "origin" not in refused["I"]["artifact"], (
        "evidence that says the bytes were not acquired still produced the "
        "label")


def test_a_block_with_no_origin_is_not_an_acquired_arm_to_the_verdict(tmp_path):
    """The missing key has to mean unknown, not acquired, at the gate.

    `acquisition_identity` and the verdict layer are separate changes, and
    either alone would be inert. This runs the first's real output through
    the second's real reader.
    """
    from experiments.ad01 import control_arm, s09_verdict

    identity = control_arm.acquisition_identity(
        "I", ["acquired-sw-x"], {"acquired": "a" * 64})
    bundle = s09_verdict.Bundle(
        root=tmp_path, freeze={"policy_identities": identity},
        construction={"I": {}}, operations={}, use_records=(),
        accounting={}, assessment=())

    assert bundle.arm_origin("I") == ""
    assert bundle.earned_arms_by_origin(s09_verdict.ORIGIN_ACQUIRED) == ()
    assert s09_verdict.task_utility_verdict(bundle).value == "not_comparable"


def test_the_freeze_block_is_written_after_the_use_loop():
    """The acquired arm's digest comes from what it executed.

    `_comparability_leg` requires sha256(record["executed_source"]) to equal
    the arm's bound digest. A digest computed from the repertoire file
    before the use loop has run cannot be that, so the write has to come
    after.
    """
    from scripts import inv01_study as study

    source = inspect.getsource(study.run_study_v1)
    write = source.index('"freeze.json"')
    acquired = source.index("acquisition_identity")
    use_loop = source.index("control_records")

    assert use_loop < acquired < write, (
        "the freeze is written before the identities that must be derived"
        " from executed records exist")


def test_the_verdict_layer_finds_the_authored_arm(tmp_path):
    """`task_utility_verdict` gets past the missing-arm refusal.

    Not past the whole comparison: a fixture with no shared tasks still
    refuses, and that refusal is correct. What is pinned here is that the
    arm is *found*, which is what the missing `policy_identities` prevented.
    """
    from experiments.ad01 import control_arm, s09_verdict

    repertoire = control_arm.control_repertoire("ad01-ctl")
    freeze = {"policy_identities": control_arm.policy_identities(
        ARM, repertoire)}
    bundle = s09_verdict.Bundle(
        root=tmp_path, freeze=freeze, construction={}, operations={},
        use_records=(), accounting={}, assessment=())

    assert bundle.arms_by_origin(s09_verdict.ORIGIN_AUTHORED) == (ARM,)
    assert bundle.arms_by_origin(s09_verdict.ORIGIN_ACQUIRED) == ()


# ---------------------------------------------------------------------------
# the gate, on bytes that execute
# ---------------------------------------------------------------------------


def test_the_gate_reads_a_control_against_an_acquired_as_distinct():
    """`control_distinct` passes on a real two-arm comparison.

    Both arms are executed here, in the child namespace, at the same
    witness budget, over the study's own use tasks. The E1 failure was a
    greedy control against a greedy acquired body; here the control's
    members are ddmin and greedy by byte-distinct source, and the acquired
    side names greedy, so the two arms differ in executed policy id, in
    strategy, and in returned candidate.
    """
    from experiments.ad01 import (control_arm, control_distinctness,
                                  method_exec, worlds, packet)

    repertoire = control_arm.control_repertoire("ad01-ctl")
    members = {m["capability_id"]: m for m in repertoire["members"]}
    control, acquired = [], []
    for world in (0, 1, 2):
        for task_id in control_arm.control_tasks(world):
            task = worlds.load_task(worlds.FROZEN_DIR, task_id)
            family = task["family"]
            view = packet.strip_task(task)
            for method, capability_id in (
                    ("ddmin", "ctl-%s-ddmin" % family),
                    ("greedy", "ctl-%s-greedy" % family)):
                member = members[capability_id]
                result = method_exec.run_member_out_of_process(
                    member, task, max_queries=BUDGET)
                row = {"task_id": task_id, "executed": capability_id,
                       "executed_source": member["method_source"],
                       "output": result["candidate"],
                       "costs": {"witness_queries": result["queries"]}}
                (acquired if method == "greedy" else control).append(row)
            assert view["family"] == family

    verdict = control_distinctness.control_distinct(control, acquired)

    assert len(verdict["paired_tasks"]) == 18
    assert verdict["same_executed_policy"] == [], verdict["same_executed_policy"]
    assert verdict["same_candidate"] == [], verdict["same_candidate"]
    assert verdict["differing_budget"] == [], verdict["differing_budget"]
    assert verdict["distinct"] is True, verdict.get("refusal")


def test_a_greedy_control_against_a_greedy_acquired_is_the_e1_finding():
    """Why the control needs two members, as a red gate.

    The E1 arms differed in id and nothing else. Reproduced here from
    executed bytes rather than read from a report, so the fix cannot be
    undone by restoring the old repertoire.
    """
    from experiments.ad01 import (control_arm, control_distinctness,
                                  method_exec, worlds)

    repertoire = control_arm.control_repertoire("ad01-ctl")
    greedy = next(m for m in repertoire["members"]
                  if m["capability_id"] == "ctl-software-greedy")
    ddmin = next(m for m in repertoire["members"]
                 if m["capability_id"] == "ctl-software-ddmin")
    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-within-sw-00")

    def row(member, capability_id):
        result = method_exec.run_member_out_of_process(
            member, task, max_queries=BUDGET)
        return {"task_id": task["task_id"], "executed": capability_id,
                "executed_source": member["method_source"],
                "output": result["candidate"],
                "costs": {"witness_queries": result["queries"]}}

    same_id = control_distinctness.control_distinct(
        [row(greedy, "ctl-software-greedy")], [row(greedy, "ctl-software-greedy")])
    assert same_id["distinct"] is False
    assert same_id["same_executed_policy"], (
        "one id on both arms must refuse, or the gate reads two columns of"
        " the same policy as a comparison")

    greedy_arms = control_distinctness.control_distinct(
        [row(greedy, "ctl-software-greedy")],
        [row(greedy, "acquired-sw-58d90427")])
    assert greedy_arms["distinct"] is False
    assert greedy_arms["same_strategy"], (
        "greedy against greedy must read as one strategy even when the ids"
        " differ; this is the E1 finding")

    fixed = control_distinctness.control_distinct(
        [row(ddmin, "ctl-software-ddmin")],
        [row(greedy, "acquired-sw-58d90427")])
    assert fixed["distinct"] is True, fixed.get("refusal")


def test_experience_varies_reports_its_own_numbers():
    """The second gate, and what it says about this arm.

    The treatment's experience was 72 observations and one distinct
    verdict, so `experience_varies` refused. That refusal is about the
    experience, not about the control, and it is reported here with the
    numbers behind it rather than asserted.
    """
    from experiments.ad01 import control_distinctness

    constant = control_distinctness.experience_varies(
        [{"task_id": "t%d" % i, "verdict": "preserved"}
         for i in range(72)])

    assert constant["observations"] == 72
    assert constant["distinct_verdicts"] == 1
    assert constant["varies"] is False
    # The gate counts distinct *outcomes*, which is the verdict joined with the
    # reason. It was changed from counting verdicts alone at 61ad0d0, because a
    # verdict is a constant on every well-formed task: the oracle a reducer
    # probes with and the grader a record is marked by are the same function,
    # so a reducer only ever keeps something graded preserved. The message
    # follows the field, so this string changed with it.
    assert "72 observations, 1 distinct outcome" in constant["refusal"]

    varying = control_distinctness.experience_varies(
        [{"task_id": "t%d" % i, "verdict": "preserved" if i % 2 else "broken",
          "method": "ddmin" if i % 2 else "greedy"} for i in range(72)])
    assert varying["varies"] is True
    assert varying["distinct_verdicts"] == 2
