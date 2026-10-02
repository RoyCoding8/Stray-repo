"""S09-C2B bind plus public scoping: assessment-gated promotion."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01.s09_run_isolation import create_disposable_db, \
    disposable_db, drop_disposable_db

RUN_TOKEN = "c2bbind"
MIGRATIONS = ROOT / "migrations"

DEV_TASK = "ad01-w0-dev-sw-00"
USE_TASK = "ad01-w0-within-sw-00"
EVALUATOR = "ad01-method-exec-v1"
PROTOCOL = "s09-revision-v1"

GOOD_SOURCE = (
    "def c2b_good_entry(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
GOOD_ENTRY = "c2b_good_entry"
OTHER_SOURCE = (
    "def c2b_other_entry(task, oracle, max_queries=16):\n"
    "    greedy = reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
    "    return greedy\n"
)
OTHER_ENTRY = "c2b_other_entry"
BROKEN_SOURCE = (
    "def c2b_broken_entry(task, oracle, max_queries=16):\n"
    "    return task\n"
)
BROKEN_ENTRY = "c2b_broken_entry"


@pytest.fixture(scope="module")
def store():
    database = create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database)


def _admitting(method_id: str):
    """A STEP policy naming one method, as a bound release would.

    `run_use` takes its method identity from an admitted action, so a caller
    wanting a specific release has to say so. Naming a method the release
    does not hold is still refused, so this cannot admit its way past the
    release pin.
    """
    def step(view, state):
        task = view["task_content"]
        if state.get("used"):
            return {"action": {"kind": "stop", "target": task["task_id"],
                               "inputs": {"reason": "done"},
                               "evidence_refs": [], "requested_resources": {}},
                    "state": state}
        return {"action": {"kind": "use_method", "target": task["task_id"],
                           "inputs": {"method_id": method_id,
                                      "max_queries": 16},
                           "evidence_refs": [],
                           "requested_resources": {"queries": 16}},
                "state": {"used": True}}
    return step


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s:%s" % (ROOT, ROOT / "src",
                                      ROOT / "experiments")
    return env


def _digest(source):
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _lifecycle(dsn, tag, source, entry):
    from experiments.ad01 import records
    investigation = "c2b-inv-%s" % tag
    failure = {"task_id": USE_TASK, "parent_digest": "seed-sw-greedy",
               "verdict": "not_preserved"}
    proposal = records.open_revision_proposal(
        dsn, investigation_id=investigation,
        parent_digest="seed-sw-greedy", failure_record=failure,
        scope={"family": "software"})
    freeze = records.freeze_candidate(
        dsn, proposal_id=proposal["proposal_id"],
        source_bytes=source, entry=entry)
    assessment = records.assess_frozen(
        dsn, proposal_id=proposal["proposal_id"], tasks=[DEV_TASK],
        evaluator_version=EVALUATOR)
    assert assessment["candidate_digest"] == freeze["candidate_digest"]
    return {"proposal": proposal, "freeze": freeze,
            "assessment": assessment,
            "version_id": "c2b-%s-%s" % (
                tag, freeze["candidate_digest"][:8])}


def _bind_args(life, release, versions, expected=None, **over):
    args = {"release_id": release, "versions": list(versions),
            "scope": {"family": "software"}, "disposition": "default",
            "fallback": "seed-sw-greedy",
            "expected_versions": expected, "policy_version": "p1",
            "protocol_id": PROTOCOL, "evaluator_version": EVALUATOR,
            "evidence_refs": [life["assessment"]["attempt_id"]],
            "proposal_id": life["proposal"]["proposal_id"],
            "candidate_digest": life["freeze"]["candidate_digest"]}
    args.update(over)
    return args


def _bind(dsn, life, release, versions, expected=None, **over):
    from experiments.ad01 import selection
    return selection.bind_revision(dsn, **_bind_args(
        life, release, versions, expected, **over))


def _member(version_id, source, entry):
    return {"capability_id": version_id,
            "scope": {"family": "software"},
            "method_source": source, "entry": entry,
            "source_digest": _digest(source),
            "authored": False, "params": {"max_queries": 4}}


def _authorize(dsn, cid):
    from experiments.ad01 import trajectory
    return trajectory.authorize_campaign(
        dsn, cid, authorized=100000)["allocation_id"]


def test_refuses_empty_protocol_evaluator_evidence(store):
    from experiments.ad01 import selection
    base = {"release_id": "c2b-empty", "versions": ["v-x"],
            "scope": {"family": "software"}, "disposition": "default",
            "fallback": "seed-sw-greedy", "expected_versions": None,
            "policy_version": "p1", "proposal_id": "p-x",
            "candidate_digest": "d-x"}
    with pytest.raises(ValueError, match="protocol"):
        selection.bind_revision(
            store, protocol_id="", evaluator_version=EVALUATOR,
            evidence_refs=["att-x"], **base)
    with pytest.raises(ValueError, match="evaluator"):
        selection.bind_revision(
            store, protocol_id=PROTOCOL, evaluator_version="",
            evidence_refs=["att-x"], **base)
    with pytest.raises(ValueError, match="evidence"):
        selection.bind_revision(
            store, protocol_id=PROTOCOL, evaluator_version=EVALUATOR,
            evidence_refs=[], **base)


def test_refuses_absent_assessment(store):
    from experiments.ad01 import records, selection
    investigation = "c2b-inv-absent"
    failure = {"task_id": USE_TASK, "parent_digest": "seed-sw-greedy",
               "verdict": "not_preserved"}
    proposal = records.open_revision_proposal(
        store, investigation_id=investigation,
        parent_digest="seed-sw-greedy", failure_record=failure,
        scope={"family": "software"})
    freeze = records.freeze_candidate(
        store, proposal_id=proposal["proposal_id"],
        source_bytes=GOOD_SOURCE, entry=GOOD_ENTRY)
    with pytest.raises(ValueError, match="absent assessment"):
        selection.bind_revision(
            store, release_id="c2b-absent", versions=["v-absent"],
            scope={"family": "software"}, disposition="default",
            fallback="seed-sw-greedy", expected_versions=None,
            policy_version="p1", protocol_id=PROTOCOL,
            evaluator_version=EVALUATOR,
            evidence_refs=["att-absent-pin"],
            proposal_id=proposal["proposal_id"],
            candidate_digest=freeze["candidate_digest"])
    assert selection.active_binding_for(
        store, "software", release_id="c2b-absent") is None


def test_refuses_empty_assessment_panel(store):
    from experiments.ad01 import records
    proposal = records.open_revision_proposal(
        store, investigation_id="c2b-inv-empty-panel",
        parent_digest="seed-sw-greedy",
        failure_record={"task_id": USE_TASK,
                        "parent_digest": "seed-sw-greedy",
                        "verdict": "not_preserved"},
        scope={"family": "software"})
    records.freeze_candidate(store, proposal_id=proposal["proposal_id"],
                             source_bytes=GOOD_SOURCE, entry=GOOD_ENTRY)
    with pytest.raises(ValueError, match="non-empty task panel"):
        records.assess_frozen(store, proposal_id=proposal["proposal_id"],
                              tasks=[], evaluator_version=EVALUATOR,
                              protocol_id=PROTOCOL)


def test_refuses_idempotency_alias(store):
    life = _lifecycle(store, "alias", GOOD_SOURCE, GOOD_ENTRY)
    from experiments.ad01 import selection
    with pytest.raises(ValueError, match="canonical"):
        _bind(store, life, "c2b-alias", [life["version_id"]],
              request_id="caller-chosen-alias")
    assert selection.active_binding_for(
        store, "software", release_id="c2b-alias") is None


def test_refuses_assessment_currentness_alias(store):
    life = _lifecycle(store, "current", GOOD_SOURCE, GOOD_ENTRY)
    from experiments.ad01 import records
    with pytest.raises(ValueError, match="differs from stored"):
        records.assess_frozen(
            store, proposal_id=life["proposal"]["proposal_id"],
            tasks=[DEV_TASK], evaluator_version=EVALUATOR,
            protocol_id="different-protocol")


def test_reuses_default_protocol_assessment(store):
    life = _lifecycle(store, "default-protocol", GOOD_SOURCE, GOOD_ENTRY)
    from experiments.ad01 import records
    again = records.assess_frozen(
        store, proposal_id=life["proposal"]["proposal_id"],
        tasks=[DEV_TASK], evaluator_version=EVALUATOR)
    assert again["attempt_id"] == life["assessment"]["attempt_id"]


def test_refuses_failed_assessment(store):
    life = _lifecycle(store, "failed", BROKEN_SOURCE, BROKEN_ENTRY)
    assert life["assessment"]["outcome"] == "reject"
    from experiments.ad01 import selection
    with pytest.raises(ValueError, match="forbids promotion"):
        _bind(store, life, "c2b-failed", [life["version_id"]])
    assert selection.active_binding_for(
        store, "software", release_id="c2b-failed") is None


def test_refuses_stale_rebind(store):
    life = _lifecycle(store, "stale", GOOD_SOURCE, GOOD_ENTRY)
    from experiments.ad01 import selection
    first = _bind(store, life, "c2b-stale", ["v-stale-1"], None)
    assert first["versions"] == ["v-stale-1"]
    second = _bind(store, life, "c2b-stale", ["v-stale-2"], ["v-stale-1"])
    assert second["versions"] == ["v-stale-2"]
    with pytest.raises(selection.StaleBind, match="stale bind"):
        _bind(store, life, "c2b-stale", ["v-stale-3"], ["v-stale-1"])
    active = selection.active_binding_for(
        store, "software", release_id="c2b-stale")
    assert active["versions"] == ["v-stale-2"]


def test_concurrent_replacement_single_winner(store):
    life = _lifecycle(store, "conc", GOOD_SOURCE, GOOD_ENTRY)
    from experiments.ad01 import selection
    _bind(store, life, "c2b-conc", ["v-conc-0"], None)
    barrier = threading.Barrier(2)
    outcomes = []

    def _try(versions):
        barrier.wait()
        try:
            _bind(store, life, "c2b-conc", versions, ["v-conc-0"])
            outcomes.append("bound %s" % versions[0])
        except selection.StaleBind:
            outcomes.append("stale %s" % versions[0])

    first = threading.Thread(target=_try, args=(["v-conc-a"],))
    second = threading.Thread(target=_try, args=(["v-conc-b"],))
    first.start()
    second.start()
    first.join(timeout=120)
    second.join(timeout=120)
    assert sorted(o.split()[0] for o in outcomes) == ["bound", "stale"]
    active = selection.active_binding_for(
        store, "software", release_id="c2b-conc")
    assert active["versions"] in (["v-conc-a"], ["v-conc-b"])


def test_refuses_wrong_scope(store):
    life = _lifecycle(store, "scope", GOOD_SOURCE, GOOD_ENTRY)
    from experiments.ad01 import selection
    with pytest.raises(ValueError, match="scope"):
        selection.bind_revision(
            store, **_bind_args(life, "c2b-scope", [life["version_id"]],
                               scope={"family": "graph"}))


def test_refuses_wrong_source(store):
    first = _lifecycle(store, "src-a", GOOD_SOURCE, GOOD_ENTRY)
    second = _lifecycle(store, "src-b", OTHER_SOURCE, OTHER_ENTRY)
    from experiments.ad01 import selection
    with pytest.raises(ValueError, match="frozen bytes"):
        selection.bind_revision(
            store, **_bind_args(first, "c2b-source", [first["version_id"]],
                               candidate_digest=second["freeze"][
                                   "candidate_digest"]))
    with pytest.raises(ValueError, match="cite"):
        selection.bind_revision(
            store, **_bind_args(first, "c2b-source", [first["version_id"]],
                               evidence_refs=[second["assessment"][
                                   "attempt_id"]]))


def test_caller_labels_never_authorize(store):
    from experiments.ad01 import selection
    with pytest.raises(ValueError, match="no revision proposal"):
        selection.bind_revision(
            store, release_id="c2b-labels", versions=["v-unfrozen"],
            scope={"family": "software"}, disposition="default",
            fallback="seed-sw-greedy", expected_versions=None,
            policy_version="p1", protocol_id=PROTOCOL,
            evaluator_version=EVALUATOR,
            evidence_refs=["att-label-pin"],
            proposal_id="s09-rev-never-opened",
            candidate_digest="0" * 64)


def test_overlapping_family_studies_mutual_non_selection(store):
    from experiments.ad01 import trajectory
    life_a = _lifecycle(store, "fam-a", GOOD_SOURCE, GOOD_ENTRY)
    life_b = _lifecycle(store, "fam-b", OTHER_SOURCE, OTHER_ENTRY)
    _bind(store, life_a, "c2b-fam-a", [life_a["version_id"]])
    _bind(store, life_b, "c2b-fam-b", [life_b["version_id"]])
    cid = "c2b-fam-use"
    allocation = _authorize(store, cid)
    repertoire = {"campaign_id": cid, "queries": 0, "members": [
        _member(life_a["version_id"], GOOD_SOURCE, GOOD_ENTRY),
        _member(life_b["version_id"], OTHER_SOURCE, OTHER_ENTRY)]}
    [record_a] = trajectory.run_use(
        repertoire, 0, "I", [USE_TASK], {}, dsn=store,
        policy=_admitting(life_a["version_id"]),
        allocation_id=allocation, release_id="c2b-fam-a")
    [record_b] = trajectory.run_use(
        repertoire, 0, "I", [USE_TASK], {}, dsn=store,
        policy=_admitting(life_b["version_id"]),
        allocation_id=allocation, release_id="c2b-fam-b")
    assert record_a["selected"] == life_a["version_id"]
    assert record_a["executed_source"] == GOOD_SOURCE
    assert record_b["selected"] == life_b["version_id"]
    assert record_b["executed_source"] == OTHER_SOURCE


def test_pinned_use_resolves_identical_bytes_fresh_process(store, tmp_path):
    life = _lifecycle(store, "fresh", GOOD_SOURCE, GOOD_ENTRY)
    _bind(store, life, "c2b-fresh", [life["version_id"]])
    cid = "c2b-fresh-use"
    allocation = _authorize(store, cid)
    repertoire = {"campaign_id": cid, "queries": 0, "members": [
        _member(life["version_id"], GOOD_SOURCE, GOOD_ENTRY)]}
    frozen = tmp_path / "repertoire.json"
    frozen.write_text(json.dumps(repertoire))
    probe = tmp_path / "fresh_pinned_use.py"
    probe.write_text(
        "import json, sys\n"
        "repertoire_path, dsn, allocation, release, method = sys.argv[1:6]\n"
        "from experiments.ad01 import trajectory\n"
        "repertoire = json.loads(open(repertoire_path).read())\n"
        "def step(view, state):\n"
        "    task = view['task_content']\n"
        "    if state.get('used'):\n"
        "        return {'action': {'kind': 'stop', 'target': task['task_id'],\n"
        "               'inputs': {'reason': 'done'}, 'evidence_refs': [],\n"
        "               'requested_resources': {}}, 'state': state}\n"
        "    return {'action': {'kind': 'use_method',\n"
        "           'target': task['task_id'],\n"
        "           'inputs': {'method_id': method, 'max_queries': 16},\n"
        "           'evidence_refs': [],\n"
        "           'requested_resources': {'queries': 16}},\n"
        "            'state': {'used': True}}\n"
        "[record] = trajectory.run_use(\n"
        "    repertoire, 0, 'I', [%r], {}, dsn=dsn, policy=step,\n"
        "    allocation_id=allocation, release_id=release)\n"
        "print(json.dumps({'selected': record['selected'],\n"
        "                  'executed_source':"
        " record['executed_source']}))\n" % USE_TASK)
    proc = subprocess.run(
        [sys.executable, str(probe), str(frozen), store, allocation,
         "c2b-fresh", life["version_id"]],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out == {"selected": life["version_id"],
                   "executed_source": GOOD_SOURCE}
    assert _digest(out["executed_source"]) == life["freeze"][
        "candidate_digest"]


def test_selector_rejects_unverified_member_bytes():
    from experiments.ad01 import selection
    digest = _digest(GOOD_SOURCE)
    repertoire = {"members": [
        {"capability_id": "c2b-unverified", "scope": {"family": "software"},
         "method_source": OTHER_SOURCE, "entry": OTHER_ENTRY},
        {"capability_id": "c2b-forged", "scope": {"family": "software"},
         "method_source": OTHER_SOURCE, "entry": OTHER_ENTRY,
         "source_digest": digest}]}
    for member in repertoire["members"]:
        assert selection.select_member(
            {"members": [member], "active_binding": {
                "versions": [member["capability_id"]],
                "scope": {"family": "software"}, "disposition": "default",
                "invalidation": {"candidate_digest": digest}}},
            {"family": "software"}, release_id="c2b-unverified") is None


def test_cli_use_release_is_optional(store, tmp_path):
    life = _lifecycle(store, "cli", GOOD_SOURCE, GOOD_ENTRY)
    _bind(store, life, "c2b-cli", [life["version_id"]])
    cid = "c2b-cli-use"
    allocation = _authorize(store, cid)
    repertoire = {"campaign_id": cid, "queries": 0, "members": [
        _member(life["version_id"], GOOD_SOURCE, GOOD_ENTRY)]}
    frozen = tmp_path / "repertoire.json"
    frozen.write_text(json.dumps(repertoire))
    policy_file = tmp_path / "policy.py"
    policy_file.write_text(
                           "def STEP(view, state):\n"
                           "    task = view['task_content']\n"
                           "    if state.get('used'):\n"
                           "        return {'action': {'kind': 'stop',"
                           " 'target': task['task_id'],\n"
                           "                       'inputs': {'reason': 'done'},"
                           " 'evidence_refs': [],\n"
                           "                       'requested_resources': {}},"
                           " 'state': state}\n"
                           "    return {'action': {'kind': 'use_method',\n"
                           "           'target': task['task_id'],\n"
                           "           'inputs': {'method_id': %r,"
                           " 'max_queries': 16},\n"
                           "           'evidence_refs': [],\n"
                           "           'requested_resources': {'queries': 16}},\n"
                           "            'state': {'used': True}}\n"
                           % life["version_id"])
    base = [sys.executable, "-m", "experiments.ad01.cli", "use",
            "--repertoire", str(frozen), "--world", "0", "--arm", "I",
            "--tasks", USE_TASK, "--dsn", store,
            "--policy-source", str(policy_file),
            "--allocation-id", allocation]
    repertoire_only = subprocess.run(
        base, cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert repertoire_only.returncode == 0, repertoire_only.stderr
    [record] = json.loads(repertoire_only.stdout)
    assert record["selected"] == life["version_id"]
    assert record["executed_source"] == GOOD_SOURCE
    granted = subprocess.run(
        base + ["--release", "c2b-cli"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert granted.returncode == 0, granted.stderr
    [record] = json.loads(granted.stdout)
    assert record["selected"] == life["version_id"]
    assert record["executed_source"] == GOOD_SOURCE
    assert record["release_id"] == "c2b-cli"


def test_resumed_use_precise_refusal(store):
    from experiments.ad01 import trajectory
    life = _lifecycle(store, "refuse", GOOD_SOURCE, GOOD_ENTRY)
    _bind(store, life, "c2b-refuse", [life["version_id"]])
    cid = "c2b-refuse-use"
    allocation = _authorize(store, cid)
    absent = {"campaign_id": cid, "queries": 0, "members": [
        _member("c2b-unrelated", OTHER_SOURCE, OTHER_ENTRY)]}
    # The release holds a method this repertoire does not carry. It used to
    # answer `incumbent`, which was the silent fallback this campaign
    # removed: a run without a usable method now refuses and says why.
    [record] = trajectory.run_use(
        absent, 0, "I", [USE_TASK], {}, dsn=store,
        policy=_admitting(life["version_id"]),
        allocation_id=allocation, release_id="c2b-refuse")
    assert record["selected"] == "refused"
    assert record["executed_source"] == "refused"
    assert record["status"] == "refused"
    assert "c2b-refuse" in record["fallback_reason"]
    [unknown] = trajectory.run_use(
        absent, 0, "I", [USE_TASK], {}, dsn=store,
        policy=_admitting(life["version_id"]),
        allocation_id=allocation, release_id="c2b-never-bound")
    assert unknown["selected"] == "refused"
    assert "absent from the repertoire" in unknown["fallback_reason"]
    assert life["version_id"] in unknown["fallback_reason"]


def test_the_store_is_one_this_run_created(store):
    """A dropped store must never be a store somebody else still runs on.

    A fixed database name is shared state: any other suite that creates the
    same name destroys this run's rows, and the scoping refusals then fail on
    rows that vanished rather than on the collision that caused it. The name
    carries a per-run token, so only this run's name is ever destroyed.
    """
    name = store.split("dbname=")[1].split()[0]

    assert name.startswith("s09iso_c2bbind_"), name


def test_the_store_survives_a_second_module_scope():
    """Re-deriving the store must not reuse this module's database.

    The collision that produced the original failures was two runs of this
    file at once. Each run's fixture mints its own name, so a second fixture
    can never observe or destroy the first one's database.
    """
    with disposable_db(RUN_TOKEN) as other:
        assert other.name.startswith("s09iso_c2bbind_"), other.name
