"""RPR-12 retention freeze and constructor contracts (E2E-1 + E2E-2a)."""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.acquire import campaign, retention
from experiments.representation.acquire import contexts
from settlement import store
from settlement.common import Command, ResultCode
from settlement.gateway import (GatewayAdapter, GatewayError, GatewayStatus,
                                ModelResponse, Usage)

ACQUIRE = ROOT / "experiments" / "representation" / "acquire"


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _tag(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:8])


def _seed_grant(dsn: str) -> None:
    result = store.seed_grant(
        dsn, Command(request_id="grant-%s" % uuid.uuid4().hex[:8],
                     payload={"version": 1, "charter_text": "rpr12 test",
                              "authority_grant": {}, "envelopes": {}}))
    assert result.code == ResultCode.APPLIED


def _need() -> int:
    need, _ = campaign.required_grant_for_contexts()
    return need


LESSONS_BODY = """# Acquired selection guidance (test double)

software: greedy
graph: ddmin

Prefer tail-first single removals near the front of the sequence.
"""

PROCEDURE_BODY = """def select(measure):
    if measure > 10:
        return "greedy"
    return "ddmin"
"""


def _variant(name: str) -> str:
    return "# constructor-acquired bytes (test double)\n" + (
        ACQUIRE / name).read_text()


VARIANT_DESC = ("# Acquired composition (model-constructed test double)\n\n"
                "Scope: selection task only.\n")


def _useful_text(arm: str, stage: str) -> str:
    if arm == "A":
        return json.dumps({"kind": "lessons",
                           "files": {"lessons.md": LESSONS_BODY}})
    if arm == "B":
        return json.dumps({"kind": "procedure",
                           "files": {"procedure.py": PROCEDURE_BODY}})
    if stage == "source":
        return json.dumps({"kind": "core",
                           "files": {"core.py": _variant("atom_core.py"),
                                     "adapter.py": _variant("sw_adapter.py"),
                                     "DESCRIPTION.md": VARIANT_DESC}})
    return json.dumps({"kind": "adapter",
                       "files": {"adapter.py": _variant("gr_adapter.py"),
                                 "DESCRIPTION.md": VARIANT_DESC}})


class ConstructorDouble(GatewayAdapter):
    def __init__(self, respond):
        self._respond = respond
        self.calls: list[str] = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def cancel(self, operation_id):
        return True

    def infer(self, request):
        self.calls.append(request.operation_id)
        parts = request.operation_id.split("-")
        arm, stage, slot = parts[-3], parts[-2], int(parts[-1][1:])
        answer = self._respond(arm, stage, slot)
        if isinstance(answer, GatewayError) or answer is None:
            return answer
        prompt = request.messages[-1]["content"]
        return ModelResponse(
            request.operation_id, answer, {"test-double": True},
            Usage(input_tokens=len(prompt) // 4,
                  output_tokens=len(answer) // 4,
                  charge_units=0, billed=False), "stop")


def _roots(tmp_path) -> dict:
    roots = {}
    for key in ("artifacts", "staging", "runs", "evidence"):
        path = tmp_path / key
        path.mkdir(parents=True, exist_ok=True)
        roots[key] = path
    return roots


def _run(dsn: str, double, tag: str, roots: dict):
    return campaign.run_campaign(
        dsn, tag=tag, model="test-double-model", grant_units=_need(),
        gateway=double, artifacts_root=roots["artifacts"],
        staging_root=roots["staging"], runs_root=roots["runs"],
        evidence_root=roots["evidence"])


def _frozen_selectors() -> dict:
    manifest = json.loads(
        (ROOT / "experiments" / "representation" / "experiment"
         / "manifest.json").read_bytes())
    return manifest["selectors"]


def test_campaign_writes_retention_file(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("rpr12keep")
    roots = _roots(tmp_path)
    record = _run(dsn, ConstructorDouble(lambda arm, stage, slot: _useful_text(arm, stage)), tag, roots)
    assert record["blocked"] is False
    assert record["acquired"] is True
    target = roots["evidence"] / "campaign" / ("retention-%s.json" % tag)
    assert target.is_file()
    assert record["retention_path"] == "campaign/retention-%s.json" % tag
    frozen = json.loads(target.read_bytes())
    assert frozen["format"] == "rpr-retention/1"
    assert frozen["tag"] == tag
    assert sorted(frozen["entries"]) == ["A-source", "A-transfer", "B-source",
                                         "B-transfer", "C-source",
                                         "C-transfer"]
    for key, entry in frozen["entries"].items():
        arm, stage = key.split("-")
        assert entry["arm"] == arm
        assert entry["stage"] == stage
        assert entry["lineage"]["selection_task"] == \
            campaign.SELECTION_TASK[stage]
        assert entry["reason"]
        assert entry["budget"]["exposure"] > 0
        assert entry["applicability"]["families"] in (["software"], ["graph"])
    text = frozen["entries"]["A-source"]
    assert text["selected"] == 1
    assert text["identities"]["artifact_digest"]
    assert text["identities"]["file_digest"] == \
        _digest(LESSONS_BODY.encode())
    assert text["directive"]["source"] == "acquired"
    assert text["directive"]["directive"] == {"software": "greedy",
                                              "graph": "ddmin"}
    proc = frozen["entries"]["B-source"]
    assert proc["selected"] == 1
    assert proc["procedure"]["status"] == "valid"
    core = frozen["entries"]["C-source"]
    assert core["selected"] is not None
    assert core["identities"]["core_digest"] == frozen["frozen_core_digest"]
    transfer = frozen["entries"]["C-transfer"]
    assert transfer["core"]["core_adapted"] is False
    assert transfer["core"]["adaptation"] is None
    assert transfer["dependencies"]["frozen_core_digest"] == \
        frozen["frozen_core_digest"]
    assert transfer["identities"]["core_digest"] == \
        frozen["frozen_core_digest"]


def test_freeze_load_roundtrip(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("rpr12round")
    roots = _roots(tmp_path)
    _run(dsn, ConstructorDouble(lambda arm, stage, slot: _useful_text(arm, stage)), tag, roots)
    target = roots["evidence"] / "campaign" / ("retention-%s.json" % tag)
    loaded = retention.load_retention(str(target), dsn, roots["artifacts"])
    assert loaded["format"] == "rpr-retention/1"
    assert loaded["tag"] == tag
    assert loaded["entries"]["B-transfer"]["procedure"]["status"] == "valid"


def test_load_rejects_tampered_record(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("rpr12tamper")
    roots = _roots(tmp_path)
    _run(dsn, ConstructorDouble(lambda arm, stage, slot: _useful_text(arm, stage)), tag, roots)
    target = roots["evidence"] / "campaign" / ("retention-%s.json" % tag)
    doc = json.loads(target.read_bytes())
    bad_digest = tmp_path / "bad-digest.json"
    doc["entries"]["C-source"]["identities"]["core_digest"] = "0" * 64
    bad_digest.write_text(json.dumps(doc))
    with pytest.raises(retention.RetentionError):
        retention.load_retention(str(bad_digest), dsn, roots["artifacts"])
    bad_format = tmp_path / "bad-format.json"
    doc["format"] = "rpr-retention/0"
    bad_format.write_text(json.dumps(doc))
    with pytest.raises(retention.RetentionError):
        retention.load_retention(str(bad_format), dsn, roots["artifacts"])
    bad_manifest = tmp_path / "bad-manifest.json"
    doc["format"] = "rpr-retention/1"
    doc["manifest_sha256"] = "0" * 64
    bad_manifest.write_text(json.dumps(doc))
    with pytest.raises(retention.RetentionError):
        retention.load_retention(str(bad_manifest), dsn, roots["artifacts"])


def test_lessons_directive_fallback(migrated_db, tmp_path):
    selectors = _frozen_selectors()
    directive, info = retention.parse_lessons_directive(
        "no method guidance here", selectors)
    assert info["source"] == "fallback-frozen-selector"
    assert info["reason"]
    assert directive == {"software": selectors["arm-A"]["software"]["method"],
                         "graph": selectors["arm-A"]["graph"]["method"]}
    partial, info = retention.parse_lessons_directive(
        "software prefers greedy runs", selectors)
    assert info["source"] == "fallback-frozen-selector"
    assert partial["software"] == "greedy"
    assert partial["graph"] == selectors["arm-A"]["graph"]["method"]


def test_procedure_contract_valid_and_execute():
    valid = retention.validate_procedure(PROCEDURE_BODY)
    assert valid["status"] == "valid"
    assert valid["format"] == "rpr-procedure/1"
    done = retention.execute_procedure(PROCEDURE_BODY, 25.0)
    assert done["status"] == "ok"
    assert done["method"] == "greedy"
    assert done["elapsed_ms"] >= 0
    small = retention.execute_procedure(PROCEDURE_BODY, 4.0)
    assert small["method"] == "ddmin"


def test_procedure_contract_refusals():
    with_import = retention.validate_procedure(
        "import os\ndef select(measure):\n    return 'greedy'\n")
    assert with_import["status"] == "refused"
    assert with_import["reason"]
    with_io = retention.validate_procedure(
        "def select(measure):\n    open('/tmp/x', 'w')\n    return 'ddmin'\n")
    assert with_io["status"] == "refused"
    broken = retention.validate_procedure("def select(:\n")
    assert broken["status"] == "refused"
    refused = retention.execute_procedure(
        "import os\ndef select(measure):\n    return 'greedy'\n", 3.0)
    assert refused["status"] == "refused"
    wild = retention.execute_procedure(
        "def select(measure):\n    return 'maybe'\n", 3.0)
    assert wild["status"] in ("refused", "error")
    looping = retention.execute_procedure(
        "def select(measure):\n    while True:\n        pass\n", 3.0,
        timeout_ms=500)
    assert looping["status"] == "timeout"


def test_transfer_prompt_within_cap_and_source_barrier():
    source, transfer = campaign.load_contexts()
    frozen_bytes = (ACQUIRE / "atom_core.py").read_bytes()
    frozen_digest = _digest(frozen_bytes)
    plan = campaign.plan_prompts(source, transfer, frozen_digest,
                                 frozen_bytes)
    assert len(plan) == 12
    for entry in plan:
        assert entry["input_tokens"] <= campaign.MAX_INPUT_TOKENS
    live = next(entry["prompt"] for entry in plan
                if entry["stage"] == "transfer")
    assert retention.CORE_INTERFACE_VERSION in live
    assert frozen_bytes.decode() in live
    prompt = campaign.source_prompt("A", 1, source)
    lowered = prompt.lower()
    assert not [token for token in contexts.BARRIER_TOKENS
                if token in lowered]


def test_no_candidate_retention_roundtrip(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("rpr12none")
    roots = _roots(tmp_path)
    double = ConstructorDouble(
        lambda arm, stage, slot: json.dumps({"abstain": True,
                                             "reason": "no-useful-form"}))
    record = _run(dsn, double, tag, roots)
    assert record["blocked"] is False
    assert record["acquired"] is False
    target = roots["evidence"] / "campaign" / ("retention-%s.json" % tag)
    assert target.is_file()
    frozen = json.loads(target.read_bytes())
    for key, entry in frozen["entries"].items():
        assert entry["selected"] is None, key
        assert "no-useful-form" in entry["reason"] or \
            "abstain" in entry["reason"] or "no-candidate" in entry["reason"]
    loaded = retention.load_retention(str(target), dsn, roots["artifacts"])
    assert loaded["tag"] == tag
