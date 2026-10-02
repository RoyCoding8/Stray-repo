"""ENG-SOLV solver output contract (EVID-01).

One shared verbatim-source contract for development collection, all A/B/C
arms and incumbent use: the model response bytes ARE the candidate source,
byte-for-byte. No fence stripping, no prose salvage, no per-arm differences,
no post-exposure edits. Validation classifies without executing; grading
attributes without reinterpreting.

Real PostgreSQL plus real subprocess sandboxes (LocalLauncher) wherever the
path under test touches them; pure unit checks for the deterministic
validator. Model inference is doubled with explicit local doubles.
"""

from __future__ import annotations

import hashlib
import json
import sys

sys.path.insert(0, "experiments")

import pytest

from fault_tasks import BY_ID
from settlement import experiment
from settlement.gateway import GatewayAdapter, GatewayStatus, ModelResponse, Usage
from settlement.launcher_local import LocalLauncher

from test_s3_helpers import EXPERIMENTS, seed_env

GRADER = str(EXPERIMENTS / "run_tests.py")
DEV_IDS = ["dev-sum"]
PANEL_IDS = ["panel-triangular"]
TRANSFER_IDS = ["transfer-sign"]

PROSE_FENCED = (
    "Here is your repaired module:\n```python\n"
    + BY_ID["panel-triangular"]["fixed"]
    + "```\nHope this helps!"
)


class SolverDouble(GatewayAdapter):
    def __init__(self, texts, stops=None):
        self.texts = dict(texts)
        self.stops = dict(stops or {})

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        body = json.loads(request.messages[-1]["content"])
        if body.get("author_lesson"):
            return ModelResponse(
                request.operation_id, "lesson: respect inclusive bounds",
                {"simulated": True}, Usage(input_tokens=10, output_tokens=10,
                                           charge_units=20), "stop")
        key = (body["arm"], body["task_id"])
        return ModelResponse(
            request.operation_id, self.texts[key],
            {"simulated": True},
            Usage(input_tokens=10, output_tokens=10, charge_units=20),
            self.stops.get(key, "stop"))

    def cancel(self, operation_id):
        return True


def _all_keys(dev_ids, panel_ids, transfer_ids):
    tasks = [BY_ID[i] for i in dev_ids + panel_ids + transfer_ids]
    keys = [("DEV", i) for i in dev_ids]
    for arm in ("A", "B", "C"):
        keys += [(arm, i) for i in panel_ids + transfer_ids]
    return tasks, keys


def _run(dsn, launcher, roots, env, tag, texts, stops=None):
    tasks, keys = _all_keys(DEV_IDS, PANEL_IDS, TRANSFER_IDS)
    double = SolverDouble({k: texts(k) for k in keys}, stops)
    return experiment.run_abcs(
        dsn, launcher=launcher, artifacts_root=roots["artifacts"],
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], tasks=tasks,
        dev_ids=list(DEV_IDS), panel_ids=list(PANEL_IDS),
        transfer_ids=list(TRANSFER_IDS), lessons=None, double=double,
        grader_path=GRADER, protocol_prefix=tag,
        fixer_version=f"{tag}-fixer-v1")


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def test_contract_constant_is_declared_once():
    assert isinstance(experiment.SOLVER_SOURCE_CONTRACT, str)
    assert "verbatim" in experiment.SOLVER_SOURCE_CONTRACT


def test_arm_prompts_carry_the_shared_contract():
    task = BY_ID["panel-triangular"]
    prompts = [experiment._arm_prompt(a, task, {"off_by_one": "L"}, None)
               for a in ("A", "B", "C")]
    assert prompts
    for prompt in prompts:
        assert prompt["response_contract"] == experiment.SOLVER_SOURCE_CONTRACT


def test_validator_accepts_raw_source_verbatim():
    code = BY_ID["panel-triangular"]["fixed"]
    result = experiment.validate_solver_output(code, stop_reason="stop")
    assert result["status"] == "ok"
    assert result["source"] == code


@pytest.mark.parametrize("raw", [None, "", "   \n  "])
def test_validator_rejects_missing_text_without_execution(raw):
    result = experiment.validate_solver_output(raw, stop_reason="stop")
    assert result["status"] in ("transport", "format")
    assert result["source"] == (raw if isinstance(raw, str) else "")


def test_validator_rejects_fenced_source_as_format():
    result = experiment.validate_solver_output(PROSE_FENCED, stop_reason="stop")
    assert result["status"] == "format"
    assert result["source"] == PROSE_FENCED


def test_validator_rejects_broken_syntax_as_format():
    result = experiment.validate_solver_output("def broken(:\n  pass",
                                               stop_reason="stop")
    assert result["status"] == "format"


def test_validator_flags_truncation_before_format():
    result = experiment.validate_solver_output(
        BY_ID["panel-triangular"]["fixed"], stop_reason="length")
    assert result["status"] == "truncated"
    incomplete = experiment.validate_solver_output(
        "def f():", stop_reason="incomplete-max_output_tokens")
    assert incomplete["status"] == "truncated"


def test_fenced_correct_fix_is_format_not_wrong_answer(
        migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "engfmt", authorized=2_000_000)
    report = _run(dsn, launcher, tmp_roots, env, "engfmt",
                  lambda key: PROSE_FENCED)
    for arm in ("A", "B", "C"):
        record = report["arms"][arm]["panel-triangular"]
        assert record["solver_status"] == "format", arm
        assert record["outcome"] == "failure", arm
        assert record["grade_class"] == "import-execution", arm
        assert record["raw_text"] == PROSE_FENCED, arm
        assert record["source_digest"] == hashlib.sha256(
            PROSE_FENCED.encode()).hexdigest(), arm
    dev_record = report["development"]["transcripts"]["dev-sum"]
    assert dev_record["solver_status"] == "format"


def test_raw_correct_fix_grades_success_through_contracted_path(
        migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "engok", authorized=2_000_000)
    report = _run(
        dsn, launcher, tmp_roots, env, "engok",
        lambda key: BY_ID[key[1]]["fixed"])
    for arm in ("A", "B", "C"):
        record = report["arms"][arm]["panel-triangular"]
        assert record["solver_status"] == "ok", arm
        assert record["outcome"] == "success", arm
        assert record["grade_class"] == "pass", arm
    assert report["development"]["transcripts"]["dev-sum"]["solver_status"] \
        == "ok"


def test_parseable_wrong_fix_is_wrong_answer_not_format(
        migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "engwrong", authorized=2_000_000)
    report = _run(
        dsn, launcher, tmp_roots, env, "engwrong",
        lambda key: BY_ID[key[1]]["broken"])
    record = report["arms"]["A"]["panel-triangular"]
    assert record["solver_status"] == "ok"
    assert record["outcome"] == "failure"
    assert record["grade_class"] == "wrong-answer"


def test_truncated_response_classified_before_grading(
        migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "engtrunc", authorized=2_000_000)
    partial = BY_ID["panel-triangular"]["fixed"][:40]

    def texts(key):
        if key == ("A", "panel-triangular"):
            return partial
        return BY_ID[key[1]]["fixed"]

    report = _run(dsn, launcher, tmp_roots, env, "engtrunc", texts,
                  stops={("A", "panel-triangular"): "length"})
    record = report["arms"]["A"]["panel-triangular"]
    assert record["solver_status"] == "truncated"
    assert record["outcome"] == "failure"
    control = report["arms"]["A"]["transfer-sign"]
    assert control["solver_status"] == "ok"
    assert control["outcome"] == "success"


def test_incumbent_use_classifies_prose_as_format(
        migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "enguse", authorized=2_000_000)
    use_task = BY_ID["panel-triangular"]
    double = SolverDouble(
        {("A", "panel-triangular"): PROSE_FENCED})
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tmp_roots["artifacts"], launcher=launcher,
        adapter=double, model="solver-double",
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], episode_id="enguse-ep",
        bindings={}, use_task=use_task, grader_path=GRADER,
        protocol_prefix="enguse")
    assert use["method"] == "incumbent"
    assert use["solver_status"] == "format"
    assert use["outcome"] == "failure"
    assert use["raw_text"] == PROSE_FENCED
