"""M4's mechanism, measured, and the comparison it refuses to build.

The claim pinned here is narrow and is the only one M4 can support without a
model. It is not "a revised learner is better". It is: the acquisition
decision is executable, an eligible revision changes it, the change survives a
restart in a fresh process, the other three controls behave as they declare,
the program cannot write the frozen fields, and no reachable input beats the
incumbent by more than the cohort's own noise.

That last one is the reason most of these tests are refusals. A harness that
compared two arms and printed a delta of 0.0067 would be reporting the cohort's
resampling spread as a result. So the panel assertion is that no panel is
built, and it fails on a tree whose noise floor is not measured.

Every test here runs without a database. That is a property of the boundary,
not an accident of the host: `improve_channel._execution_ledger` opens a
disposable PostgreSQL for every execution, which is what keeps gate 6 and
`drive_improve_round` out of this file. CI carries the postgres:18 service and
owns those two.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import m4_mechanism_harness as harness
from experiments.ad01 import channel_controls as controls
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import learner_revision as revision

COHORT = list(range(1, 26))

# The view the decision is judged on, built by the module that builds it for
# the real run so this file holds no second copy of it.
ADMISSION_VIEW = {"experience": [], "round": 1, "frontier": [], "step": 0}

# A backticked span in the prompt. The repaired prompt marks its worked
# examples this way and the rule below does not care why they are backticked,
# so an example written in other markup is not read as one.
EXAMPLE_SPAN = re.compile(r"`([^`\n]+)`")

# The prompt that produced E4's six refusals, held by the harness so both
# halves of the discriminating test read the same bytes.
BROKEN_USER_TEMPLATE = harness.BROKEN_USER_TEMPLATE


def _artifact(workdir: Path) -> dict:
    return harness.run(workdir, cohort=COHORT)


def _offered_expressions(prompt: str) -> list:
    """Every expression the prompt offers as an acceptable x.

    Found by mechanism rather than by wording. A backticked span that parses
    as an expression and evaluates to an integer at the admission view is an
    example the prompt offers, whatever its markup and whatever the rule
    thinks of it. A bare literal counts even though gate 4 refuses it, because
    offering one is the original defect returning through a different door.
    """
    offered = []
    for span in EXAMPLE_SPAN.findall(prompt):
        try:
            node = ast.parse(span.strip(), mode="eval").body
        except SyntaxError:
            continue
        try:
            value = eval(compile(ast.Expression(node), "<x>", "eval"), {},
                         {"view": ADMISSION_VIEW, "len": len})
        except Exception:                          # noqa: BLE001
            continue
        if type(value) is int:
            offered.append(span)
    return offered


# --- the decision is executable and the eligible one changes it -------------

def test_the_harness_executes_a_real_decision_not_a_declared_one():
    view = harness._admission_view(Path(tempfile.mkdtemp()))
    decision = harness.execute_decision(
        channel._revision_source('(len(view.get("experience", [])) or 12)'),
        view)
    assert decision["x"] == 12
    assert decision["kind"] == "probe"
    assert decision["executed_bytes_digest"]


def test_every_control_executes_the_integer_it_declares():
    view = harness._admission_view(Path(tempfile.mkdtemp()))
    for role in sorted(controls.CONTROL_BUILDERS):
        control = controls.build_control(role)
        executed = harness.execute_decision(control["source"], view)["x"]
        assert executed == control["x_under_revision"], (
            "%s declares %s and executed %s" % (
                role, control["x_under_revision"], executed))


def test_the_effectful_control_changes_the_decision_the_incumbent_makes():
    view = harness._admission_view(Path(tempfile.mkdtemp()))
    parent = harness.execute_decision(channel.IMPROVE_LOW_SOURCE, view)["x"]
    revised = harness.execute_decision(
        channel._revision_source('(len(view.get("experience", [])) or 12)'),
        view)["x"]
    assert parent == 3
    assert revised == 12
    assert revised != parent


def test_the_change_survives_a_restart_in_a_fresh_process():
    """The clause says after restart, so the reading happens in another
    interpreter. An in-process read would prove the store is a dict."""
    root = Path(tempfile.mkdtemp())
    artifact = harness.run(root, cohort=COHORT)
    restart = artifact["restart"]
    assert restart["effectful"]["restarted"] is True
    assert restart["parent"]["restarted"] is True
    assert restart["effectful"]["x"] == 12
    assert restart["parent"]["x"] == 3
    assert restart["effectful_changed_after_restart"] is True
    assert restart["effectful_matches_in_process"] is True


def test_the_effectful_control_is_not_a_cosmetic_source_edit():
    """A comment changes the bytes and nothing else. This asserts the
    executed bytes differ, not the file contents."""
    view = harness._admission_view(Path(tempfile.mkdtemp()))
    source = channel._revision_source(
        '(len(view.get("experience", [])) or 12)')
    cosmetic = source.replace("def STEP(view, state):",
                              "# revised\ndef STEP(view, state):")
    assert cosmetic != source
    assert revision._frontier.source_digest(cosmetic) != \
        revision._frontier.source_digest(source)
    assert harness.execute_decision(cosmetic, view)["x"] == \
        harness.execute_decision(source, view)["x"] == 12
    assert revision.differs_from_incumbent(source) is True
    assert revision.is_constant_x(source) is False


# --- the controls are distinguishable, which is what qualifies them ---------

def test_the_disconnect_is_refused_by_the_instrument_and_builds_nothing():
    root = Path(tempfile.mkdtemp())
    artifact = harness.run(root, cohort=COHORT)
    arm = artifact["arms"]["disconnect"]
    assert arm["executed_x"] == 16
    assert arm["in_instrument_range"] is False
    assert arm["refused_by_instrument"] is True
    assert arm["descendant_built"] is False
    assert arm["refusal"]


def test_the_no_op_and_the_bytes_that_differ_reach_the_same_decision():
    root = Path(tempfile.mkdtemp())
    artifact = harness.run(root, cohort=COHORT)
    no_op = artifact["arms"]["no-op"]
    by_bytes = artifact["arms"]["disconnect-bytes"]
    incumbent = artifact["arms"]["incumbent"]
    assert no_op["executed_x"] == incumbent["executed_x"] == 3
    assert by_bytes["executed_x"] == 3
    assert no_op["source_digest"] != by_bytes["source_digest"]


def test_no_arm_moved_the_frozen_state_during_adoption():
    artifact = _artifact(Path(tempfile.mkdtemp()))
    adopted = [arm for arm in artifact["arms"].values()
               if "frozen_unchanged" in arm]
    assert adopted
    for arm in adopted:
        assert arm["frozen_unchanged"] is True, arm["role"]


# --- the program cannot reach the frozen fields ------------------------------

def test_every_frozen_field_write_is_refused_on_real_revision_bytes():
    """Six attacks, six refusals, and the clean source admitted. A guard that
    refused everything would pass the first six and fail the seventh."""
    source = channel._revision_source(
        '(len(view.get("experience", [])) or 12)')
    guard = harness.freeze_guard(source)
    assert guard["clean_source_refused"] is False
    assert guard["every_attack_refused"] is True
    assert set(guard["attacks"]) == set(harness.FROZEN_ATTACKS)
    for name, entry in guard["attacks"].items():
        assert entry["refused"] is True, name
        assert entry["reason"], name


def test_the_guard_covers_every_frozen_field_by_name():
    """A count is not a cover. If the guard were narrowed to refuse `grant`
    and nothing else, six attacks and a count of six would both still pass, so
    each frozen field is required to appear in the refusals themselves."""
    source = channel._revision_source(harness.EFFECTFUL_EXPRESSION)
    guard = harness.freeze_guard(source)
    reasons = " | ".join(entry["reason"]
                         for entry in guard["attacks"].values())
    for field in channel.FROZEN_FIELDS:
        assert field in reasons, (
            "%s is a frozen field and no refusal names it" % field)
    assert len(channel.FROZEN_FIELDS) == 6


def test_a_smuggled_frozen_write_is_reported_as_a_write_not_a_shape_failure():
    source = channel._revision_source(
        '(len(view.get("experience", [])) or 12)')
    reason = channel._frozen_write_reason(
        source + '\n    view["grant"] = {}')
    assert reason == "writes view['grant'], a frozen field"


# --- eligibility, and the gate that cannot run here -------------------------

def test_five_of_six_eligibility_gates_execute_without_a_database():
    artifact = _artifact(Path(tempfile.mkdtemp()))
    gates = artifact["eligibility"]["gates"]
    assert artifact["eligibility"]["executed"] == 5
    assert list(gates.values()).count("pass") == 5
    unexecuted = [value for value in gates.values()
                  if value.startswith("not executed")]
    assert len(unexecuted) == 1
    assert "delegates-to-unchanged-reducer" in \
        artifact["eligibility"]["not_executed"]


def test_the_constructed_revision_names_something_other_than_zero():
    """Gate 6 reads as a refusal to name 0 at the admission view. The reading
    is recorded here because the gate itself cannot be executed here."""
    root = Path(tempfile.mkdtemp())
    view = harness._admission_view(root)
    source = channel._revision_source(
        '(len(view.get("experience", [])) or 12)')
    assert channel._reducer_argmax(view) == [0]
    assert harness.execute_decision(source, view)["x"] == 12
    assert channel._x_is_data_dependent(source) is True
    assert channel.unauthorised_change(
        source, channel.IMPROVE_LOW_SOURCE) == {}
    assert channel._frozen_write_reason(source) == ""


# --- the comparison this harness refuses to build ---------------------------

def test_no_comparison_panel_is_built_because_nothing_clears_the_noise():
    """The named failure mode is an empty comparison panel. The panel here
    would not be empty, it would be wrong: every delta is inside the
    cohort's own resampling spread."""
    artifact = _artifact(Path(tempfile.mkdtemp()))
    panel = artifact["panel"]
    assert panel["built"] is False
    assert panel["arms"] == []
    assert panel["reason"] == "no reachable input clears the noise floor"
    assert artifact["benefit_measured"] is False


def test_the_best_available_input_does_not_clear_the_noise_floor():
    artifact = harness.run(Path(tempfile.mkdtemp()), cohort=COHORT)
    rows = [row for row in artifact["per_input"] if row["z"] is not None]
    assert rows
    best = max(rows, key=lambda row: abs(row["z"]))
    assert abs(best["z"]) < harness.NOISE_FLOOR_Z, (
        "x=%d reached z=%.3f, which clears the floor; this test's premise has"
        " changed and the panel rule needs re-reading"
        % (best["x"], best["z"]))
    assert artifact["panel"]["built"] is False


def test_the_cohort_argmax_does_not_agree_with_itself():
    """An input that wins one half of the cohort and loses the other has not
    been shown to win. The instrument already reports this, and the harness
    reports it too rather than selecting on the full cohort."""
    floor = harness.noise_report(harness.ASSESS_SPLIT, COHORT)
    assert floor["argmax_stable"] is False
    assert len(set(floor["quarter_argmaxes"])) > 1


def test_a_widened_cohort_produces_the_same_refusal():
    """The bar must not be a function of cohort size. 150 seeds is the size
    the apparatus reports elsewhere; if a panel appeared there and not here,
    the refusal would be an artefact of the small cohort."""
    artifact = harness.run(Path(tempfile.mkdtemp()),
                           cohort=list(range(1, 151)))
    assert artifact["cohort_size"] == 150
    assert artifact["panel"]["built"] is False
    assert artifact["panel"]["reason"] == (
        "no reachable input clears the noise floor")


def test_the_panel_rule_builds_one_when_an_arm_really_clears_the_bar():
    """The refusal is a rule, not a hardcoded no. Lowering the bar to zero and
    handing it rows that clear it must produce arms, or the rule is a stub."""
    rows = [{"x": 3, "mean": 0.5, "delta": 0.25, "z": 5.0, "measured": True},
            {"x": 4, "mean": 0.1, "delta": -0.4, "z": -4.0, "measured": True},
            {"x": 5, "mean": 0.2, "delta": 0.001, "z": 0.1, "measured": True}]
    panel = harness.panels(rows, noise_z=1.96)
    assert panel["built"] is True
    assert panel["n_arms"] == 2
    assert [arm["x"] for arm in panel["arms"]] == [3, 4]
    refused = harness.panels(
        [{"x": 5, "mean": 0.2, "delta": 0.001, "z": 0.1, "measured": True}],
        noise_z=1.96)
    assert refused["built"] is False


# --- the freeze -------------------------------------------------------------

def test_the_harness_reports_the_run_version_it_measured_under():
    """An arm acquired under one prompt is not comparable with an arm acquired
    under another, so the version the acquisition would use travels in the
    artifact rather than being pinned here where it can drift."""
    artifact = _artifact(Path(tempfile.mkdtemp()))
    assert artifact["run_version"] == revision.RUN_VERSION
    assert artifact["run_version"] == "invl02-e4-run-v2"


def test_the_effectful_arm_is_the_prompt_s_own_admissible_example():
    """The discriminating test for the prompt repair, from the harness side.

    The harness's effectful arm is a hand-written expression. If it stays a
    hand-written expression it measures a revision the prompt never asked for,
    and the run version it reports is a label over bytes the acquisition would
    not produce. So the arm is taken from the examples the current prompt
    offers, which is what a competent reader following the prompt writes, and
    every one of those examples has to survive the gates the harness can run.

    This fails on the prompt that produced E4's six refusals, because that
    prompt offers no expression that names a non-zero integer at the admission
    view, so there is nothing to drive the arm with.
    """
    prompt = revision.prompt_for()["user"]
    offered = _offered_expressions(prompt)

    assert offered, (
        "the prompt offers no admissible expression, so a reader following it"
        " produces the refused 0 again and the harness has nothing to drive")

    for expression in offered:
        source = channel._revision_source("(%s)" % expression)
        assert channel._x_is_data_dependent(source), expression
        assert channel.unauthorised_change(
            source, channel.IMPROVE_LOW_SOURCE) == {}, expression
        executed = harness.execute_decision(
            source, harness._admission_view(Path(tempfile.mkdtemp())))
        assert executed["x"] != 0, expression

    assert _names_same_integer_as_an_offer(prompt), (
        "the arm this harness drives is not one the prompt offers, so the"
        " measurement is of bytes the acquisition would never produce")


def _names_same_integer_as_an_offer(prompt: str) -> bool:
    """Whether the harness's arm does what one of the prompt's examples does.

    Compared by executed behaviour, not by text. The prompt offers
    `len(view["experience"]) or 12` and `m4-eligibility.md` names
    `(len(view.get("experience", [])) or 12)`; those are the same decision
    written two ways, and pinning the harness to one spelling would make it a
    test of punctuation. What matters is that the arm names the same integer
    as an example a competent reader would copy, at the view the rule judges.
    """
    arm = harness.execute_decision(
        channel._revision_source(harness.EFFECTFUL_EXPRESSION), ADMISSION_VIEW)
    for expression in _offered_expressions(prompt):
        offered = harness.execute_decision(
            channel._revision_source("(%s)" % expression), ADMISSION_VIEW)
        if offered["x"] == arm["x"]:
            return True
    return False


def test_the_unfixed_prompt_offers_nothing_the_arm_could_be_built_from():
    """The negative half of the test above, held in the same file so the two
    cannot drift apart. If the old prompt ever offered an admissible
    expression, this file's discriminating claim is stated wrong."""
    assert _offered_expressions(
        BROKEN_USER_TEMPLATE.format(template=revision.template_for())) == []


def test_the_artifact_is_serialisable_and_round_trips():
    artifact = _artifact(Path(tempfile.mkdtemp()))
    text = json.dumps(artifact, sort_keys=True, default=str)
    assert json.loads(text)["run_version"] == revision.RUN_VERSION


def test_the_harness_makes_no_network_call():
    """Gateway material is by name only. The harness must be runnable on a
    host with no route at all, which is asserted by running it with the
    environment stripped rather than by inspecting the source for a hostname.
    """
    root = Path(tempfile.mkdtemp())
    program = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "import m4_mechanism_harness as h\n"
        "print(json.dumps(h.run(Path(%r), cohort=list(range(1, 9)))\n"
        "                  ['panel']['built']))\n"
    ) % (str(ROOT), str(ROOT / "src"), str(ROOT / "tools"), str(root))
    environment = {"PATH": "", "SYSTEMROOT": "C:\\Windows",
                   "HOME": str(root), "PYTHONPATH": ""}
    completed = subprocess.run([sys.executable, "-c", program],
                               capture_output=True, text=True, env=environment,
                               timeout=180)
    assert completed.returncode == 0, completed.stderr[-500:]
    assert json.loads(completed.stdout) is False
