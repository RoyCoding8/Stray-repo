from __future__ import annotations

import hashlib
import json
import uuid

from settlement import evaluation, trials
from settlement.common import Command, SettlementError

from . import freeze, oracle

EVALUATOR_ID = oracle.EVALUATOR_ID
EVALUATOR_VERSION = oracle.EVALUATOR_VERSION
PROTOCOL_DEV = freeze.PROTOCOL_DEV
PROTOCOL_EVAL = freeze.PROTOCOL_EVAL


def oracle_digest() -> str:
    return hashlib.sha256(
        (oracle.ROOT / "oracle.py").read_bytes()).hexdigest()


def _cmd() -> Command:
    return Command(request_id="team01-%s" % uuid.uuid4().hex, payload={})


def _dev_groups() -> list:
    dev = list(oracle.SPLITS["development"])
    return [{"name": "development", "kind": "development", "tasks": dev},
            {"name": "visible-regression", "kind": "visible-regression",
             "tasks": dev},
            {"name": "protected-eval", "kind": "protected-eval",
             "tasks": dev}]


def _eval_groups() -> list:
    dev = list(oracle.SPLITS["development"])
    vis = list(oracle.SPLITS["evaluation"])
    pro = list(oracle.SPLITS["evaluation"]) + list(oracle.SPLITS["transfer"])
    return [{"name": "development", "kind": "development", "tasks": dev},
            {"name": "visible-regression", "kind": "visible-regression",
             "tasks": vis},
            {"name": "protected-eval", "kind": "protected-eval",
             "tasks": pro}]


def _freeze(dsn: str, protocol_id: str, groups: list) -> None:
    try:
        trials.freeze_protocol(
            dsn, _cmd(), protocol_id=protocol_id,
            candidate_version="team01-candidate/1",
            reference_version="team01-reference/1",
            evaluator_version=EVALUATOR_VERSION,
            task_groups=groups, budgets=dict(freeze.CEILINGS),
            metrics=["protected_pass"], stopping={"rule": "fixed-panel"},
            supported_scope={"study": "team01"})
    except SettlementError as exc:
        if "already exists" not in str(exc):
            raise


def ensure_foundation(dsn: str) -> dict:
    problems = freeze.verify_committed()
    if problems:
        raise SettlementError("frozen inputs invalid: %s" % problems)
    evaluation.register_evaluator(
        dsn, _cmd(), EVALUATOR_ID, EVALUATOR_VERSION,
        access_policy={"scope": "team01-evaluator"},
        code_digest=oracle_digest())
    for task_id in oracle.ALL_TASKS:
        cases = json.loads(
            (oracle.PROTECTED / (task_id + ".json")).read_text())
        evaluation.propose_hidden_answer(dsn, _cmd(), task_id,
                                         {"cases": cases})
    _freeze(dsn, PROTOCOL_DEV, _dev_groups())
    _freeze(dsn, PROTOCOL_EVAL, _eval_groups())
    manifest = json.loads(
        (oracle.ROOT / "manifest.json").read_bytes())
    return {"problems": [], "manifest": manifest["version"],
            "evaluator": {"id": EVALUATOR_ID,
                          "version": EVALUATOR_VERSION,
                          "code_digest": oracle_digest()},
            "protocols": [PROTOCOL_DEV, PROTOCOL_EVAL]}
