"""E2E-3/E2E-4: retained campaign artifacts drive evaluation, disposition, use."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.acquire import campaign
from experiments.representation.acquire import experiment as e2e
from experiments.representation.acquire import panel
from experiments.representation.acquire import retention
from experiments.representation.acquire import run as panel_run
from experiments.representation.experiment import checker
from settlement import launcher_local, store
from settlement.common import Command, ResultCode
from settlement.gateway import (GatewayAdapter, GatewayError, GatewayStatus,
                                ModelResponse, Usage)

ACQUIRE = ROOT / "experiments" / "representation" / "acquire"
EXPERIMENT_PY = ACQUIRE / "experiment.py"
DIAGNOSTIC_TASK = "gr-eva-00"


def _tag(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:8])


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _seed_grant(dsn: str) -> None:
    result = store.seed_grant(
        dsn, Command(request_id="grant-%s" % uuid.uuid4().hex[:8],
                     payload={"version": 1, "charter_text": "rpr13 e2e",
                              "authority_grant": {}, "envelopes": {}}))
    assert result.code == ResultCode.APPLIED


def _need() -> int:
    need, _ = campaign.required_grant_for_contexts()
    return need


def _roots(tmp_path) -> dict:
    roots = {}
    for key in ("artifacts", "staging", "runs", "evidence"):
        path = tmp_path / key
        path.mkdir(parents=True, exist_ok=True)
        roots[key] = path
    return roots


def _flipped(name: str) -> str:
    raw = (ACQUIRE / name).read_text()
    assert '"order": "tail"' in raw
    return ("# constructor-acquired variant (rpr13 double)\n"
            + raw.replace('"order": "tail"', '"order": "head"'))


VARIANT_DESC = ("# Acquired composition (rpr13 double)\n\n"
                "Scope: selection task only.\n")


def _lessons(method: str, extra: str = "") -> str:
    return ("# Acquired lessons (rpr13 double)\n\n"
            "software: %s\ngraph: %s\n%s" % (method, method, extra))


def _procedure(method: str, extra: str = "") -> str:
    return ("# Acquired procedure (rpr13 double)%s\n"
            "def select(measure):\n"
            "    return '%s'\n" % (extra, method))


class AcquireDouble(GatewayAdapter):
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


def _useful_text(arm: str, stage: str, procedure: str = "greedy",
                 directive: str = "ddmin", extra: str = "") -> str:
    if arm == "A":
        files = {"lessons.md": _lessons(directive, extra)}
        kind = "lessons"
    elif arm == "B":
        files = {"procedure.py": _procedure(procedure, extra)}
        kind = "procedure"
    elif stage == "source":
        files = {"core.py": _flipped("atom_core.py"),
                 "adapter.py": _flipped("sw_adapter.py"),
                 "DESCRIPTION.md": VARIANT_DESC + extra}
        kind = "core"
    else:
        files = {"adapter.py": _flipped("gr_adapter.py"),
                 "DESCRIPTION.md": VARIANT_DESC + extra}
        kind = "adapter"
    return json.dumps({"kind": kind, "files": files})


def _double(procedure: str = "greedy", directive: str = "ddmin",
            extra: str = ""):
    return AcquireDouble(
        lambda arm, stage, slot: _useful_text(arm, stage, procedure,
                                             directive, extra))


def _abstain_double():
    return AcquireDouble(
        lambda arm, stage, slot: json.dumps({"abstain": True,
                                             "reason": "no-useful-form"}))


def _experiment(dsn: str, double, tag: str, roots: dict, phases=None):
    kw = {} if phases is None else {"phases": phases}
    return e2e.run_experiment(
        dsn, gateway=double, model="rpr13-double", grant_units=_need(),
        tag=tag, artifacts_root=roots["artifacts"],
        staging_root=roots["staging"], runs_root=roots["runs"],
        evidence_root=roots["evidence"], **kw)


def assert_retained_acceptance(eval_root, retention_path) -> bool:
    raw = Path(retention_path).read_bytes()
    frozen = json.loads(raw.decode("utf-8"))
    rdigest = _digest(raw)
    assert frozen["format"] == "rpr-retention/1"
    problems = []
    records = sorted(Path(eval_root, "arm_task").glob("*.json"))
    assert records, "no benefit records"
    for path in records:
        rec = json.loads(path.read_bytes())
        key = "%s-%s" % (rec["arm"],
                         panel_run.STAGE_OF_FAMILY[rec["family"]])
        entry = frozen["entries"][key]
        identities = entry.get("identities") or {}
        acq = rec.get("acquired")
        if entry["selected"] is None:
            if not acq or acq.get("selected") is not None:
                problems.append("%s: no-candidate lacks fallback marker"
                                % path.name)
                continue
            comp = rec.get("composition", {})
            if comp.get("directive_source") != "fallback-frozen-selector" \
                    and rec["result"]["disposition"] != "refused":
                problems.append("%s: fallback not labeled" % path.name)
            continue
        if not acq:
            problems.append("%s: retained record carries no acquired block"
                            % path.name)
            continue
        if acq.get("retention_digest") != rdigest:
            problems.append("%s: retention digest not followed" % path.name)
        if acq.get("response_digest") != entry["lineage"]["response_digest"]:
            problems.append("%s: response digest not followed" % path.name)
        if rec["arm"] in ("A", "B"):
            if acq.get("artifact_digest") != identities["artifact_digest"]:
                problems.append("%s: artifact digest not followed"
                                % path.name)
        else:
            comp = rec.get("composition", {})
            for field in ("composition_id", "package_digest", "core_digest",
                          "adapter_digest"):
                if comp.get(field) != identities[field]:
                    problems.append("%s: %s not followed"
                                    % (path.name, field))
    assert not problems, problems
    return True


def _pair_ctx(dsn: str, tag: str, roots: dict, retention_path):
    base = panel_run.ensure_foundation(dsn, tag)
    panel_run.ensure_protocols(dsn, tag, base["manifest"])
    loaded = retention.load_retention(str(retention_path), dsn,
                                      roots["artifacts"])
    rdigest = _digest(Path(retention_path).read_bytes())
    ctx = {**base, "tag": tag, "run_tag": "%s-ret" % tag,
           "launcher": launcher_local.LocalLauncher(str(roots["runs"])),
           "artifacts_root": roots["artifacts"],
           "staging_root": roots["staging"],
           "evidence_root": roots["evidence"],
           "retention": loaded, "retention_digest": rdigest,
           "retention_path": str(retention_path)}
    panel_run.bind_retention(dsn, ctx)
    return ctx


def _eval_root(roots, tag: str) -> Path:
    return roots["evidence"] / ("eval-%s" % tag)


def _campaign_ops(dsn: str, tag: str) -> int:
    from settlement import db as _db

    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM operations WHERE id LIKE %s",
                        ("rpr-camp-%s-%%" % tag,))
            count = cur.fetchone()[0]
            conn.commit()
            return count


def test_acquired_end_to_end(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("e2e")
    roots = _roots(tmp_path)
    status = _experiment(dsn, _double(), tag, roots)
    assert status["phase_completed"] == "use"
    assert status["phases_completed"] == ["acquisition", "evaluation",
                                          "disposition", "use"]
    assert status["acquired"] is True
    rpath = Path(status["retention_path"])
    assert rpath == roots["evidence"] / "campaign" / ("retention-%s.json" % tag)
    frozen = retention.load_retention(str(rpath), dsn, roots["artifacts"])
    assert frozen["format"] == "rpr-retention/1"
    assert frozen["tag"] == tag
    eval_root = _eval_root(roots, tag)
    assert assert_retained_acceptance(eval_root, rpath) is True
    authored_core = _digest((ACQUIRE / "atom_core.py").read_bytes())
    assert frozen["frozen_core_digest"] != authored_core
    benefit = {p.stem: json.loads(p.read_bytes())
               for p in (eval_root / "arm_task").glob("*.json")}
    assert len(benefit) == 48
    for stem, rec in sorted(benefit.items()):
        arm = rec["arm"]
        key = "%s-%s" % (arm, panel_run.STAGE_OF_FAMILY[rec["family"]])
        entry = frozen["entries"][key]
        identities = entry["identities"]
        assert entry["selected"] is not None
        if arm == "A":
            assert rec["composition"]["procedure"] == "ddmin"
            assert rec["composition"]["directive_source"] == "acquired"
            assert rec["acquired"]["artifact_digest"] == \
                identities["artifact_digest"]
        elif arm == "B":
            assert rec["composition"]["procedure"] == "greedy"
            assert rec["composition"]["directive_source"] == "acquired"
            assert rec["procedure"]["method"] == "greedy"
            assert rec["procedure"]["procedure_digest"] == \
                identities["file_digest"]
            assert rec["acquired"]["artifact_digest"] == \
                identities["artifact_digest"]
        else:
            assert rec["composition"]["composition_id"] == \
                identities["composition_id"]
            assert rec["composition"]["core_digest"] == \
                identities["core_digest"]
            assert rec["composition"]["package_digest"] == \
                identities["package_digest"]
            assert rec["invocations"], stem
    assert frozen["entries"]["C-source"]["identities"]["core_digest"] == \
        frozen["frozen_core_digest"]
    assert frozen["entries"]["C-transfer"]["core"]["core_adapted"] is False
    proc_ops = _procedure_ops(dsn, tag)
    assert proc_ops, "no sandboxed procedure executions recorded"
    disp = status["disposition"]
    assert disp["release_eligible"] is False
    assert disp["use_authorized"] is False
    assert isinstance(disp["promising"], bool)
    use = {p.stem: json.loads(p.read_bytes())
           for p in (eval_root / "use").glob("*.json")}
    assert len(use) == 4
    for task_id, rec in sorted(use.items()):
        assert rec["acquired"]["retention_digest"] == status["retention_digest"]
        if "out-of-scope" in task_id:
            assert rec["selected"]["route"] == "incumbent"
        else:
            assert rec["selected"]["route"] == "A-fallback"
            assert rec["fallback"]["procedure"] == "ddmin"
            assert rec["c_attempt"]["composition_id"] == \
                frozen["entries"]["C-source" if rec["family"] == "software"
                       else "C-transfer"]["identities"]["composition_id"]
    report = checker.check_all(eval_root, dsn=dsn)
    assert report["clean"], report["problems"]


def _procedure_ops(dsn: str, tag: str) -> list:
    from settlement import db as _db

    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT operation_id, receipt_identity FROM receipts"
                        " WHERE operation_id LIKE %s",
                        ("%%%s-ret%%:procedure:%%" % tag,))
            rows = list(cur.fetchall())
            conn.commit()
            return rows


def test_invalid_selected_procedure_refuses_with_reason(migrated_db,
                                                         tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("badproc")
    roots = _roots(tmp_path)

    def respond(arm, stage, slot):
        if (arm, stage) == ("B", "source"):
            return json.dumps({"kind": "procedure",
                               "files": {"procedure.py": "# no entry\nX = 1\n"}})
        return _useful_text(arm, stage)

    status = _experiment(dsn, AcquireDouble(respond), tag, roots)
    assert status["phase_completed"] == "use"
    eval_root = _eval_root(roots, tag)
    source_recs = [json.loads(p.read_bytes())
                   for p in (eval_root / "arm_task").glob("*.json")
                   if json.loads(p.read_bytes())["arm"] == "B"
                   and json.loads(p.read_bytes())["family"] == "software"]
    assert source_recs, "no B-source records"
    for rec in source_recs:
        assert rec["result"]["disposition"] == "refused"
        assert rec["result"]["reason"].startswith(
            "rejected-procedure: missing-select-entry"), rec["result"]["reason"]


def test_sensitivity_behavioral_not_cosmetic(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    roots = _roots(tmp_path)
    observed = {}
    digests = {}
    variants = {"greedy": _double(procedure="greedy"),
                "ddmin": _double(procedure="ddmin"),
                "cosmetic": _double(procedure="greedy",
                                    extra="\n# cosmetic-only comment\n")}
    for name, double in variants.items():
        tag = _tag("sens%s" % name)
        record = campaign.run_campaign(
            dsn, tag=tag, model="rpr13-double", grant_units=_need(),
            gateway=double, artifacts_root=roots["artifacts"],
            staging_root=roots["staging"], runs_root=roots["runs"],
            evidence_root=roots["evidence"])
        assert record["acquired"] is True
        rpath = roots["evidence"] / record["retention_path"]
        frozen = retention.load_retention(str(rpath), dsn,
                                          roots["artifacts"])
        entry = frozen["entries"]["B-transfer"]
        digests[name] = entry["identities"]["file_digest"]
        ctx = _pair_ctx(dsn, tag, roots, rpath)
        result = panel_run.run_benefit_pair(dsn, ctx, "B", DIAGNOSTIC_TASK)
        rec = result["record"]
        assert rec["composition"]["procedure"] == \
            ("ddmin" if name == "ddmin" else "greedy")
        observed[name] = (rec["result"]["improvement_u"],
                          rec["result"]["disposition"])
    assert digests["cosmetic"] != digests["greedy"]
    assert observed["greedy"] != observed["ddmin"]
    assert observed["greedy"] == observed["cosmetic"]
    assert observed["greedy"] == (0.1, "improved")
    assert observed["ddmin"] == (0.0, "no_improvement")


def test_disconnect_negative(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("neg")
    roots = _roots(tmp_path)
    status = _experiment(dsn, _double(), tag, roots)
    rpath = Path(status["retention_path"])
    eval_root = _eval_root(roots, tag)
    assert assert_retained_acceptance(eval_root, rpath) is True
    authored = tmp_path / "authored"
    authored.mkdir()
    base = panel_run.ensure_foundation(dsn, "%s-auth" % tag)
    panel_run.ensure_protocols(dsn, "%s-auth" % tag, base["manifest"])
    actx = {**base, "tag": "%s-auth" % tag, "run_tag": "%s-auth" % tag,
            "launcher": launcher_local.LocalLauncher(str(tmp_path / "runs2")),
            "artifacts_root": roots["artifacts"],
            "staging_root": roots["staging"], "evidence_root": authored,
            "retention": None}
    result = panel_run.run_benefit_pair(dsn, actx, "B", DIAGNOSTIC_TASK)
    assert "acquired" not in result["record"]
    with pytest.raises(AssertionError):
        assert_retained_acceptance(authored, rpath)
    rpath.unlink()
    with pytest.raises(retention.RetentionError):
        retention.load_retention(str(rpath), dsn, roots["artifacts"])
    bare = tmp_path / "noroot"
    with pytest.raises(retention.RetentionError):
        panel_run.run_panel(dsn, tag="%s-noret" % tag,
                            artifacts_root=roots["artifacts"],
                            staging_root=bare / "staging",
                            runs_root=bare / "runs",
                            evidence_root=bare / "evidence",
                            mode="retained", retention_path=rpath)


def test_no_candidate_path(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("nocand")
    roots = _roots(tmp_path)
    status = _experiment(dsn, _abstain_double(), tag, roots)
    assert status["acquired"] is False
    assert status["phase_completed"] == "use"
    assert status["phases_completed"] == ["acquisition", "evaluation",
                                          "disposition", "use"]
    assert status["disposition"]["promising"] is False
    eval_root = _eval_root(roots, tag)
    assert assert_retained_acceptance(eval_root, status["retention_path"]) \
        is True
    incumbent = {}
    for task_id in panel.BENEFIT_SW + panel.BENEFIT_GR:
        task, _ = panel_run.load_task(task_id)
        kept, _ = panel_run.incumbent_of(task)
        incumbent[task_id] = panel_run._digest(panel_run._canon(kept))
    for path in (eval_root / "arm_task").glob("*.json"):
        rec = json.loads(path.read_bytes())
        assert rec["acquired"]["selected"] is None
        if rec["arm"] == "A":
            assert rec["composition"]["directive_source"] == \
                "fallback-frozen-selector"
            assert rec["composition"]["procedure"] == "greedy"
        else:
            assert rec["result"]["disposition"] == "refused"
            assert rec["result"]["delivered_digest"] == \
                incumbent[rec["task_id"]]
            assert "rpr-C-source-v1" not in json.dumps(rec)
            assert "rpr-C-transfer-v1" not in json.dumps(rec)
    use = {p.stem: json.loads(p.read_bytes())
           for p in (eval_root / "use").glob("*.json")}
    assert len(use) == 4
    for task_id, rec in sorted(use.items()):
        if "out-of-scope" in task_id:
            assert rec["selected"]["route"] == "incumbent"
        else:
            assert rec["selected"]["route"] == "A-fallback"
    report = checker.check_all(eval_root, dsn=dsn)
    assert report["clean"], report["problems"]


def test_tampered_retention_hard_errors(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("tamper")
    roots = _roots(tmp_path)
    record = campaign.run_campaign(
        dsn, tag=tag, model="rpr13-double", grant_units=_need(),
        gateway=_double(), artifacts_root=roots["artifacts"],
        staging_root=roots["staging"], runs_root=roots["runs"],
        evidence_root=roots["evidence"])
    assert record["acquired"] is True
    rpath = roots["evidence"] / record["retention_path"]
    from settlement.common import SettlementError

    bad = json.loads(rpath.read_bytes())
    bad["entries"]["B-source"]["identities"]["file_digest"] = "0" * 64
    bad_path = tmp_path / "retention-bad.json"
    bad_path.write_text(json.dumps(bad, sort_keys=True, indent=2) + "\n")
    with pytest.raises(SettlementError):
        _pair_ctx(dsn, tag, roots, bad_path)
    gone = json.loads(rpath.read_bytes())
    gone["entries"]["C-source"]["identities"]["package_digest"] = "f" * 64
    gone_path = tmp_path / "retention-gone.json"
    gone_path.write_text(json.dumps(gone, sort_keys=True, indent=2) + "\n")
    with pytest.raises(SettlementError):
        _pair_ctx(dsn, tag, roots, gone_path)
    ctx = _pair_ctx(dsn, tag, roots, rpath)
    result = panel_run.run_benefit_pair(dsn, ctx, "B", DIAGNOSTIC_TASK)
    assert result["record"]["result"]["disposition"] == "improved"


def test_fresh_process_use_from_disk(migrated_db, tmp_path):
    dsn = migrated_db
    _seed_grant(dsn)
    tag = _tag("fresh")
    roots = _roots(tmp_path)
    status = _experiment(dsn, _double(), tag, roots)
    assert status["phase_completed"] == "use"
    eval_root = _eval_root(roots, tag)
    for path in (eval_root / "use").glob("*.json"):
        path.unlink()
    before = _campaign_ops(dsn, tag)
    env = dict(os.environ, SETTLEMENT_TEST_DSN=dsn)
    proc = subprocess.run(
        [sys.executable, str(EXPERIMENT_PY), "--tag", tag,
         "--artifacts-root", str(roots["artifacts"]),
         "--staging-root", str(roots["staging"]),
         "--runs-root", str(roots["runs"]),
         "--evidence-root", str(roots["evidence"]),
         "--phases", "use"],
        env=env, cwd=str(ROOT), capture_output=True, text=True,
        timeout=290)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert '"phase_completed": "use"' in proc.stdout
    assert _campaign_ops(dsn, tag) == before
    frozen = json.loads(Path(status["retention_path"]).read_bytes())
    use = {p.stem: json.loads(p.read_bytes())
           for p in (eval_root / "use").glob("*.json")}
    assert len(use) == 4
    for task_id, rec in sorted(use.items()):
        assert rec["acquired"]["retention_digest"] == \
            status["retention_digest"]
        assert rec["acquired"]["disposition_digest"] == \
            status["disposition"]["digest"]
        if "out-of-scope" not in task_id:
            assert rec["c_attempt"]["composition_id"] == \
                frozen["entries"]["C-source" if rec["family"] == "software"
                       else "C-transfer"]["identities"]["composition_id"]
