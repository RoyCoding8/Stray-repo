"""CBR-01 real acquisition orchestration through the production entry."""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.acquire import campaign, live_campaign
from settlement import broker, store
from settlement import representation as R
from settlement.common import Command, ResultCode
from settlement.gateway import (GatewayAdapter, GatewayError, GatewayStatus,
                                ModelResponse, Usage)

ACQUIRE = ROOT / "experiments" / "representation" / "acquire"


def _tag(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:8])


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _seed_grant(dsn: str) -> None:
    result = store.seed_grant(
        dsn, Command(request_id="grant-%s" % uuid.uuid4().hex[:8],
                     payload={"version": 1, "charter_text": "cbr01 test",
                              "authority_grant": {}, "envelopes": {}}))
    assert result.code == ResultCode.APPLIED


def _need() -> int:
    need, _ = campaign.required_grant_for_contexts()
    return need


def _variant(name: str, order: bool = False) -> str:
    raw = (ACQUIRE / name).read_text()
    assert "tail" in raw
    if order:
        raw = raw.replace('"order": "tail"', '"order": "head"')
        assert '"order": "head"' in raw
    return "# constructor-acquired variant (test double)\n" + raw


VARIANT_DESC = ("# Acquired composition (model-constructed test double)\n\n"
                "Scope: selection task only. Preservation decided by the "
                "independent oracle.\n")
VARIANT_LESSONS = ("# Acquired lessons (test double)\n\n"
                   "Prefer tail-first single removals near the front.\n")
VARIANT_PROCEDURE = ("PROCEDURE = 'acquired-greedy'\n\n"
                     "def select(bucket_measure):\n"
                     "    return 'greedy'\n")


class ConstructorDouble(GatewayAdapter):
    def __init__(self, respond, discovery=None, auth=None):
        self._respond = respond
        self._discovery = discovery
        self._auth = auth
        self.calls: list[str] = []

    def check_discovery(self):
        return self._discovery or GatewayStatus.CONFIGURED

    def check_auth(self):
        return self._auth or GatewayStatus.AUTHENTICATED

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


def _useful_text(arm: str, stage: str) -> str:
    if arm == "A":
        files = {"lessons.md": VARIANT_LESSONS}
        kind = "lessons"
    elif arm == "B":
        files = {"procedure.py": VARIANT_PROCEDURE}
        kind = "procedure"
    elif stage == "source":
        files = {"core.py": _variant("atom_core.py", order=True),
                 "adapter.py": _variant("sw_adapter.py", order=True),
                 "DESCRIPTION.md": VARIANT_DESC}
        kind = "core"
    else:
        files = {"adapter.py": _variant("gr_adapter.py", order=True),
                 "DESCRIPTION.md": VARIANT_DESC}
        kind = "adapter"
    return json.dumps({"kind": kind, "files": files})


def _roots(tmp_path) -> dict:
    roots = {}
    for key in ("artifacts", "staging", "runs", "evidence"):
        path = tmp_path / key
        path.mkdir(parents=True, exist_ok=True)
        roots[key] = path
    return roots


def _run(dsn: str, double, tag: str, roots: dict, grant: int | None = None):
    return campaign.run_campaign(
        dsn, tag=tag, model="test-double-model",
        grant_units=grant if grant is not None else _need(),
        gateway=double, artifacts_root=roots["artifacts"],
        staging_root=roots["staging"], runs_root=roots["runs"],
        evidence_root=roots["evidence"])


def _model_ops(dsn: str, tag: str) -> list:
    from settlement import db as _db

    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, payload FROM operations"
                        " WHERE id LIKE %s ORDER BY id",
                        ("rpr-camp-%s-%%" % tag,))
            rows = cur.fetchall()
            conn.commit()
    return rows


def test_preflight_keeps_exact_blocker_shape():
    record = live_campaign.preflight({})
    assert record["blocked"] is True
    assert record["reason"] == "missing-inputs"
    assert record["missing"] == ["SETTLEMENT_GATEWAY_ENDPOINT",
                                 "SETTLEMENT_GATEWAY_KEY",
                                 "SETTLEMENT_GRANT_UNITS"]
    assert "live_campaign.py" in record["command"]
    assert record["spent"] == {"model_calls": 0, "input_tokens": 0,
                               "output_tokens": 0, "grant_units": 0}
    assert record["budget"]["model_calls"] == 12
    assert record["model_output"].startswith("none:")


def test_cli_grant_reaches_preflight_over_env():
    env = {live_campaign.ENDPOINT_ENV: "https://example.invalid/v1",
           live_campaign.KEY_ENV: "non-secret-probe-placeholder",
           live_campaign.GRANT_ENV: "1",
           "SETTLEMENT_MODEL": "probe-model",
           "SETTLEMENT_TEST_DSN": "postgresql://example.invalid/db"}
    assert live_campaign.preflight(dict(env))["reason"] == "grant-below-requirement"
    record = live_campaign.preflight(dict(env), {"grant": str(_need() + 7)})
    assert record["blocked"] is False
    assert record["reason"] == "configured"
    assert record["grant_units"] == _need() + 7


def test_useful_bytes_become_executed_candidates(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("campuseful")
    roots = _roots(tmp_path)
    double = ConstructorDouble(lambda arm, stage, slot:
                               _useful_text(arm, stage))
    record = _run(dsn, double, tag, roots)
    assert record["blocked"] is False
    assert record["disposition"] == "complete"
    assert record["acquired"] is True
    assert len(record["slots"]) == 12
    assert {slot["status"] for slot in record["slots"]} == {"retained"}
    assert len(double.calls) == 12
    rows = _model_ops(dsn, tag)
    assert len(rows) == 12
    for op_id, payload in rows:
        body = dict(payload)
        assert body["effect"] == broker.MODEL_INFERENCE
        assert body["retries"] == 0
        assert body["payload"]["max_output_tokens"] == 8192
        inbound = sum(len(message["content"])
                      for message in body["payload"]["messages"]) // 4 + 1
        assert inbound <= 16384
    seen = set()
    for slot in record["slots"]:
        seen.add((slot["arm"], slot["stage"]))
        assert slot["dispatch_state"] == "observed"
    assert seen == {(arm, stage) for arm in "ABC"
                    for stage in ("source", "transfer")}
    variant_core = _digest(_variant("atom_core.py", order=True).encode())
    authored_core = _digest((ACQUIRE / "atom_core.py").read_bytes())
    assert variant_core != authored_core
    frozen = record["frozen_core_digest"]
    assert frozen == variant_core
    transfer = next(slot for slot in record["slots"]
                    if slot["arm"] == "C" and slot["stage"] == "transfer")
    assert transfer["core_digest"] == frozen
    assert transfer.get("core_change_refused") is False
    for slot in record["slots"]:
        if slot["arm"] != "C":
            continue
        execution = slot["execution"]
        assert execution["executed"] is True
        assert slot["composition_id"].endswith("-%s-s%d" % (tag, slot["slot"]))
        checked = R.check_composition(dsn, roots["artifacts"],
                                      slot["composition_id"])
        assert checked["core_digest"] == slot["core_digest"]
        assert checked["adapter_digest"] == slot["adapter_digest"]
    written = json.loads((roots["evidence"] / "campaign"
                          / ("%s.json" % tag)).read_bytes())
    assert written == record
    assert record["spent"]["model_calls"] == 12
    assert record["spent"]["input_tokens"] > 0
    assert record["spent"]["output_tokens"] > 0
    assert record["spent"]["grant_units"] == 0


def test_always_refusing_abstains_without_candidates(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("camprefuse")
    roots = _roots(tmp_path)
    double = ConstructorDouble(
        lambda arm, stage, slot: json.dumps({"abstain": True,
                                             "reason": "no-useful-form"}))
    record = _run(dsn, double, tag, roots)
    assert record["blocked"] is False
    assert record["disposition"] == "complete"
    assert record["acquired"] is False
    assert len(double.calls) == 12
    assert {slot["status"] for slot in record["slots"]} == {"abstained"}
    assert all("composition_id" not in slot for slot in record["slots"])
    assert all("artifact_digest" not in slot for slot in record["slots"])
    for key, value in record["retention"].items():
        assert value["selected"] is None, key
    from settlement import db as _db

    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM capability_versions"
                        " WHERE id LIKE %s", ("rpr-C-%%-%s-s%%" % tag,))
            assert cur.fetchone()[0] == 0
            conn.commit()
    assert record["spent"]["model_calls"] == 12


def test_ignored_responses_consume_budget_without_candidates(
        migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("campignored")
    roots = _roots(tmp_path)

    def respond(arm, stage, slot):
        if arm == "C" and stage == "source" and slot == 2:
            return json.dumps({"kind": "lessons",
                               "files": {"lessons.md": "wrong kind"}})
        return "not json {{{"

    record = _run(dsn, ConstructorDouble(respond), tag, roots)
    assert record["blocked"] is False
    assert record["acquired"] is False
    reasons = {(slot["arm"], slot["stage"], slot["slot"]): slot["reason"]
               for slot in record["slots"]}
    assert reasons[("C", "source", 2)] == "wrong-kind"
    assert all(reason == "not-json" for key, reason in reasons.items()
               if key != ("C", "source", 2))
    assert all("composition_id" not in slot for slot in record["slots"])
    assert record["spent"]["model_calls"] == 12


def test_authored_fallback_cannot_impersonate_acquisition(
        migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("campplant")
    roots = _roots(tmp_path)
    core_raw = (ACQUIRE / "atom_core.py").read_bytes()
    adapter_raw = (ACQUIRE / "sw_adapter.py").read_bytes()
    desc_raw = (ACQUIRE / "descriptions" / "source.md").read_bytes()
    receipt = R.stage_composition(roots["staging"], core_bytes=core_raw,
                                  adapter_bytes=adapter_raw,
                                  description=desc_raw, dsn=dsn)
    published = R.publish_composition(dsn, Command(
        request_id="plant-pub-%s" % uuid.uuid4().hex[:8]),
        roots["artifacts"], receipt)
    assert published.code == ResultCode.APPLIED
    planted_id = campaign.composition_id(tag, "source", 1)
    recorded = R.record_composition(
        dsn, Command(request_id="plant-rec-%s" % uuid.uuid4().hex[:8]),
        roots["artifacts"], composition_id=planted_id,
        package_digest=receipt["digest"], role="source",
        protocol_id="planted-fixture")
    assert recorded.code == ResultCode.APPLIED
    double = ConstructorDouble(
        lambda arm, stage, slot: json.dumps({"abstain": True,
                                             "reason": "refusing"}))
    record = _run(dsn, double, tag, roots)
    assert record["retention"]["C-source"]["selected"] is None
    assert record["acquired"] is False
    assert receipt["digest"] not in json.dumps(record)
    from settlement import db as _db

    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM receipts"
                        " WHERE operation_id LIKE %s",
                        ("rpr:rprD-" + tag + "-sel-%",))
            assert cur.fetchone()[0] == 0
            conn.commit()


def test_core_freeze_before_graph_exposure(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("campfreeze")
    roots = _roots(tmp_path)
    changed_core = _variant("atom_core.py", order=True).replace(
        "head-first", "head-first-changed")

    def respond(arm, stage, slot):
        if arm == "C" and stage == "transfer":
            return json.dumps({"kind": "adapter",
                               "files": {"core.py": changed_core,
                                         "adapter.py": _variant(
                                             "gr_adapter.py", order=True),
                                         "DESCRIPTION.md": VARIANT_DESC}})
        return _useful_text(arm, stage)

    record = _run(dsn, ConstructorDouble(respond), tag, roots)
    frozen = record["frozen_core_digest"]
    assert frozen == _digest(_variant("atom_core.py", order=True).encode())
    transfer = [slot for slot in record["slots"]
                if slot["arm"] == "C" and slot["stage"] == "transfer"]
    assert len(transfer) == 2
    assert all(slot["core_change_refused"] is True for slot in transfer)
    assert all(slot["core_digest"] == frozen for slot in transfer)
    assert all(slot["status"] == "retained" for slot in transfer)
    assert record["retention"]["C-transfer"]["selected"] is not None


def test_grant_admission_blocks_before_dispatch(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("camppoor")
    roots = _roots(tmp_path)
    store.seed_allocation(
        dsn, Command(request_id="poor-seed-%s" % uuid.uuid4().hex[:8],
                     payload={"allocation_id": campaign.campaign_allocation(tag),
                              "domain": "cpu", "authorized": 10}))
    double = ConstructorDouble(lambda arm, stage, slot:
                               _useful_text(arm, stage))
    record = _run(dsn, double, tag, roots)
    assert record["blocked"] is True
    assert record["reason"] == "insufficient-grant"
    assert double.calls == []


def test_durable_grant_required_despite_credentials(migrated_db, tmp_path):
    dsn = migrated_db
    tag = _tag("campnogrant")
    roots = _roots(tmp_path)
    double = ConstructorDouble(lambda arm, stage, slot:
                               _useful_text(arm, stage))
    record = _run(dsn, double, tag, roots)
    assert record["blocked"] is True
    assert record["reason"] == "no-installed-grant"
    assert double.calls == []


def test_transport_failure_abstains_slot_without_candidate(
        migrated_db, tmp_path):
    from settlement.gateway import GatewayErrorKind

    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("camperror")
    roots = _roots(tmp_path)

    def respond(arm, stage, slot):
        if (arm, stage, slot) == ("C", "source", 1):
            return GatewayError(GatewayErrorKind.TRANSPORT, "down", True,
                                 "opaque")
        return _useful_text(arm, stage)

    record = _run(dsn, ConstructorDouble(respond), tag, roots)
    assert record["blocked"] is False
    first = next(slot for slot in record["slots"]
                 if (slot["arm"], slot["stage"], slot["slot"])
                 == ("C", "source", 1))
    assert first["status"] == "error"
    assert first["reason"].startswith("transport:")
    assert record["retention"]["C-source"]["selected"] == 2
    assert record["spent"]["model_calls"] == 12


def test_live_entry_routes_cli_grant_to_orchestration(
        migrated_db, tmp_path, monkeypatch, capsys):
    dsn = migrated_db
    roots = _roots(tmp_path)
    monkeypatch.setenv(live_campaign.ENDPOINT_ENV, "https://example.invalid/v1")
    monkeypatch.setenv(live_campaign.KEY_ENV, "non-secret-test-placeholder")
    monkeypatch.setenv(live_campaign.GRANT_ENV, "1")
    monkeypatch.setenv("SETTLEMENT_MODEL", "probe-model")
    argv = ["--grant", str(_need() + 3), "--dsn", dsn,
            "--tag", _tag("campcli"),
            "--artifacts-root", str(roots["artifacts"]),
            "--staging-root", str(roots["staging"]),
            "--runs-root", str(roots["runs"]),
            "--evidence-root", str(roots["evidence"])]
    assert live_campaign.main(argv) == 2
    record = json.loads(capsys.readouterr().out)
    assert record["blocked"] is True
    assert record["reason"] == "no-installed-grant"
