"""RPR-03 acquisition contexts, lineage and tunable core (Lane D)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation import splits
from experiments.representation.acquire import contexts, panel
from settlement import development, store
from settlement import representation as R
from settlement.common import Command, ResultCode

ACQUIRE = ROOT / "experiments" / "representation" / "acquire"
FIXTURES = ROOT / "experiments" / "representation" / "fixtures"


def _cmd(payload: dict) -> Command:
    return Command(request_id="req_%s" % uuid.uuid4().hex[:12], payload=payload)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_context_shapes():
    source = json.loads((ACQUIRE / "source_context.json").read_bytes())
    transfer = json.loads((ACQUIRE / "transfer_context.json").read_bytes())
    assert [t["task_id"] for t in source["tasks"]] == contexts.SOURCE_TASKS
    assert len(source["tasks"]) == 6
    assert [t["task_id"] for t in transfer["tasks"]] == contexts.TRANSFER_TASKS
    assert len(transfer["tasks"]) == 4
    for doc in (source, transfer):
        assert doc["version"] == contexts.CONTEXT_VERSION
        assert doc["provenance"] == "authored-fixture, not model output"
        assert doc["usable_by"] == ["arm-A", "arm-B", "arm-C", "future-arm"]
        assert set(doc["transcripts"]) == {t["task_id"] for t in doc["tasks"]}
        for runs in doc["transcripts"].values():
            assert set(runs) == {"ddmin", "greedy"}
            for run in runs.values():
                assert run["queries"] <= 16
                assert run["history"]


def test_source_context_carries_no_graph_vocabulary():
    text = (ACQUIRE / "source_context.json").read_text().lower()
    hits = [token for token in contexts.BARRIER_TOKENS if token in text]
    assert hits == []


def test_contexts_deterministic():
    for name, builder in (("source_context.json",
                           contexts.build_source_context),
                          ("transfer_context.json",
                           contexts.build_transfer_context)):
        rebuilt = (json.dumps(builder(FIXTURES), sort_keys=True, indent=2)
                   + "\n").encode()
        assert _digest(rebuilt) == _digest((ACQUIRE / name).read_bytes())


def test_parent_refs_match_lane_b_manifest():
    pinned = (FIXTURES / "manifest.sha256").read_text().strip()
    assert splits.verify_manifest(FIXTURES) == []
    for name in ("source_context.json", "transfer_context.json"):
        doc = json.loads((ACQUIRE / name).read_bytes())
        assert doc["parent_refs"]["lane_b_manifest_digest"] == pinned
        assert doc["parent_refs"]["lane_b_manifest_version"] == "RPR-01/1"
        for task in doc["tasks"]:
            rel, digest, _ = contexts._fixture_digest(FIXTURES, task["task_id"])
            assert task["digest"] == digest


def test_selectors_come_from_dev_data_only():
    source = json.loads((ACQUIRE / "source_context.json").read_bytes())
    transfer = json.loads((ACQUIRE / "transfer_context.json").read_bytes())
    assert panel.derive_selectors(source, transfer) == \
        json.loads((ROOT / "experiments" / "representation" / "experiment"
                    / "manifest.json").read_bytes())["selectors"]


def _foundation(dsn):
    store.seed_allocation(dsn, _cmd({"allocation_id": "a-rpr03",
                                     "domain": "cpu", "authorized": 1000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i-rpr03",
                                      "objective": "o"}))


def test_episode_lineage_and_access_fence(migrated_db):
    dsn = migrated_db
    _foundation(dsn)
    lane_b = (FIXTURES / "manifest.sha256").read_text().strip()
    refs = [{"task_id": t, "family": "software", "digest": "d" * 64,
             "lane_b_manifest": lane_b} for t in contexts.SOURCE_TASKS]
    development.observe(dsn, _cmd({}), episode_id="ep-rpr03",
                        investigation_id="i-rpr03", trigger_refs=refs,
                        bottleneck="b")
    development.propose(dsn, _cmd({}), episode_id="ep-rpr03",
                        predicted_effect="e")
    development.admit(dsn, _cmd({}), episode_id="ep-rpr03",
                      reference_version="RPR-01/1:%s" % lane_b,
                      access_policy={"families": ["software"]},
                      allocation_id="a-rpr03")
    episode = development.get_episode(dsn, "ep-rpr03")
    assert episode["state"] == "admitted"
    assert [r["task_id"] for r in episode["trigger_refs"]] == contexts.SOURCE_TASKS
    assert episode["reference_version"] == "RPR-01/1:%s" % lane_b
    assert episode["access_policy"] == {"families": ["software"]}
    assert episode["disposition"] == "open"
    episode["trigger_refs"].append({"task_id": "gr-dev-00",
                                    "family": "graph"})
    with pytest.raises(Exception):
        development._check_policy_scope(episode)


def _stage(dsn, staging, comp_id, core_name, adapter_name, desc_name,
           role="source"):
    core_raw = (ACQUIRE / ("%s.py" % core_name)).read_bytes()
    adapter_raw = (ACQUIRE / ("%s.py" % adapter_name)).read_bytes()
    desc_raw = (ACQUIRE / "descriptions" / ("%s.md" % desc_name)).read_bytes()
    receipt = R.stage_composition(staging, core_bytes=core_raw,
                                  adapter_bytes=adapter_raw,
                                  description=desc_raw, dsn=dsn)
    return receipt, core_raw, adapter_raw


def test_candidate_lineage_capped_at_two_versions(migrated_db, tmp_roots,
                                                  tmp_path):
    dsn = migrated_db
    staging = tmp_roots["staging"]
    artifacts = tmp_roots["artifacts"]
    for slot in ("v1", "v2"):
        receipt, _, _ = _stage(dsn, staging, "rpr-C-source-%s" % slot,
                               "atom_core", "sw_adapter", "source")
        published = R.publish_composition(dsn, _cmd({}), artifacts, receipt)
        assert published.code in (ResultCode.APPLIED,
                                  ResultCode.ALREADY_APPLIED)
        recorded = R.record_composition(
            dsn, _cmd({}), artifacts,
            composition_id="rpr-C-source-%s" % slot,
            package_digest=receipt["digest"], role="source")
        assert recorded.code == ResultCode.APPLIED
    from settlement import db as _db
    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM capability_versions"
                        " WHERE id LIKE 'rpr-C-source-v%'")
            assert cur.fetchone()[0] == 2
            conn.commit()


def test_core_tunable_interface_changes_proposals(tmp_path):
    core = str(ACQUIRE / "atom_core.py")
    bodies = []
    for tunables in ({"chunk_frac": 2, "max_proposals": 4, "order": "tail"},
                     {"chunk_frac": 2, "max_proposals": 4, "order": "head"}):
        req = {"profile": R.PROFILE, "profile_version": R.PROFILE_VERSION,
               "action": "start", "task_id": "t", "composition_id": "c",
               "core_digest": "c" * 64, "adapter_digest": "a" * 64,
               "state": None,
               "payload": {"encoded_object": {"atoms": list(range(10)),
                                              "tunables": tunables},
                           "feedback": None, "limits": {}}, "budget": {}}
        req_path = tmp_path / "req.json"
        resp_path = tmp_path / "resp.json"
        req_path.write_text(json.dumps(req))
        proc = subprocess.run([sys.executable, core, str(req_path),
                               str(resp_path)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == ""
        bodies.append(json.loads(resp_path.read_text())["result"]["proposal"])
    assert bodies[0] != bodies[1]


def test_shared_core_bytes_across_stages():
    manifest = json.loads((ROOT / "experiments" / "representation"
                           / "experiment" / "manifest.json").read_bytes())
    comps = {c["composition_id"]: c for c in manifest["compositions"]}
    assert comps["rpr-C-source-v1"]["core_digest"] == \
        comps["rpr-C-transfer-v1"]["core_digest"]
    assert comps["rpr-C-source-v1"]["adapter_digest"] != \
        comps["rpr-C-transfer-v1"]["adapter_digest"]


def test_insufficient_encoding_pair():
    sys.path.insert(0, str(ACQUIRE))
    import sw_adapter
    from experiments.representation import checkers
    task = splits.generate_software("development", 0)
    agreeing = None
    ref = task["witness"]["ref"]
    from experiments.representation import software
    ref_run = software.reference_run(task["ops"])
    bad_run = software.faulty_run(task["ops"], task["fault"])
    for oid, seen in ref_run.items():
        if bad_run.get(oid) == seen and oid != task["witness"]["observation"]:
            agreeing = oid
            break
    assert agreeing is not None
    other = dict(task, task_id="probe-twin",
                 witness={"observation": agreeing, "ref": ref_run[agreeing],
                          "faulty": ref_run[agreeing]})
    ctx = {"profile": R.PROFILE, "profile_version": R.PROFILE_VERSION,
           "action": "encode", "task_id": "t", "composition_id": "c",
           "core_digest": "c" * 64, "adapter_digest": "a" * 64}
    encs = []
    for candidate_task in (task, other):
        out = sw_adapter._encode({**ctx, "payload": {
            "source_task": candidate_task,
            "domain_spec": {"family": "software"}}})
        assert out["status"] == "ok"
        encs.append(out["result"])
    assert encs[0]["encoded_object"]["atoms"] == encs[1]["encoded_object"]["atoms"]
    assert encs[0]["aux"] != encs[1]["aux"]
    kept = {"kept": encs[0]["encoded_object"]["atoms"][:6]}
    verdicts = []
    for candidate_task, enc in ((task, encs[0]), (other, encs[1])):
        dec = sw_adapter._decode({**ctx, "action": "decode", "payload": {
            "proposal": kept, "source_task": candidate_task,
            "aux": enc["aux"]}})
        verdicts.append(checkers.check_software(
            candidate_task, dec["result"]["candidate_source"])["verdict"])
    assert verdicts[0] != verdicts[1]
