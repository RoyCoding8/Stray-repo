"""AG01-EXP apparatus tests on real PostgreSQL scratch DBs.

Scored paths use the REAL policies (settlement.agenda_policy decide_R/Q)
through the implemented agenda commands. No test doubles stand in for the
policies in scored runs.
"""

from __future__ import annotations

import ast
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.agenda01 import checker, grader, launcher, manifest, observations, runner, worlds
from settlement import broker, db, store
from settlement.agenda_policy import POLICY_Q_VERSION, POLICY_R_VERSION
from settlement.common import Command, ResultCode, SettlementError

POLICY_VERSIONS = {"R": POLICY_R_VERSION, "Q": POLICY_Q_VERSION}

BASE_DSN = os.environ.get("SETTLEMENT_TEST_DSN")
if not BASE_DSN:
    pytest.skip("SETTLEMENT_TEST_DSN is not configured", allow_module_level=True)

MANIFEST, MHASH = manifest.build()
WORLDS = {w["world_id"]: w for w in MANIFEST["worlds"]}
DEV = {w["world_id"]: w for w in worlds.dev_worlds()}


def durable(world_id, arm, tmp_path, tie=0):
    world = WORLDS[world_id] if world_id in WORLDS else DEV[world_id]
    return runner.run_trajectory(BASE_DSN, world, arm, tie,
                                 runner.resolve_policy(arm), POLICY_VERSIONS[arm],
                                 MANIFEST, MHASH, tmp_path)


def scratch_backend(name="scratch", setup=True, truth=True):
    from experiments.agenda01.runner import AgendaBackend
    db_name = f"agenda01_scratch_{name}_{os.getpid()}"
    try:
        runner.drop_db(BASE_DSN, db_name)
    except Exception:
        pass
    dsn = runner.create_db(BASE_DSN, db_name)
    db.apply_migrations(dsn, ROOT / "migrations")
    sim = launcher.AgendaProbeLauncher(
        dsn, observe=lambda probe, sample, prop: truth,
        claim=lambda prop: truth)
    backend = AgendaBackend(dsn, f"scratch-{name}", sim)
    if setup:
        backend.setup(manifest.BUDGETS)
    return dsn, db_name, backend


def drop_scratch(db_name):
    try:
        runner.drop_db(BASE_DSN, db_name)
    except Exception:
        pass


def test_fixture_cost_observation_validation():
    assert len(worlds.all_worlds()) == 32
    fams = {}
    for world in worlds.all_worlds():
        assert len(world["tasks"]) == 8
        assert set(world["props"]) == {f"p{i}" for i in range(8)}
        fams.setdefault(world["family"], []).append(world["variant"])
        for key, probe in world["probes"].items():
            assert probe["cost"] in (2, 4, 8), (world["world_id"], key)
            assert 0.0 <= probe["noise"] < 1.0
            for prop in probe["observes"]:
                assert prop in world["props"]
            if probe["followup"] is not None:
                assert probe["followup"] in world["probes"]
            if probe["product"] is not None:
                assert set(probe["product"]) <= set(world["props"])
            pre = probe.get("prereq")
            if pre is not None:
                assert "instrument" in pre or "dep_version" in pre
        for seed in world["seeds"]:
            assert seed["probe"] in world["probes"], (world["world_id"], seed)
            assert seed["seed_class"] in worlds.SEED_CLASSES
        for event in world["events"]:
            assert event["kind"] in ("instrument", "dep-bump")
            assert 0 <= event["tick"] < world["ticks"]
            if event["kind"] == "instrument":
                assert event["key"] in world["instruments"]
        task_props = {t["prop"] for t in world["tasks"]}
        assert task_props <= set(world["props"])
        if world["scored"]:
            assert task_props == set(world["props"])
    assert set(fams) == set(range(8))
    for fam, variants in fams.items():
        assert sorted(variants) == [0, 1, 2, 3]
        assert worlds.get_world(f"w{fam * 4 + 3:02d}")["adverse"] == worlds.ADVERSE[fam]


def _walk_keys(node, keys):
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            _walk_keys(value, keys)
    elif isinstance(node, list):
        for value in node:
            _walk_keys(value, keys)


def test_no_privileged_fields_in_public_fixtures():
    for path in ("worlds.py", "observations.py"):
        text = (ROOT / "experiments" / "agenda01" / path).read_text()
        for token in ("good_action", "expected_score_gain"):
            assert token not in text, (path, token)
    tree = ast.parse((ROOT / "experiments" / "agenda01" / "observations.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("grader" in name for name in imported)
    banned_keys = {"informative", "good_action", "expected_score_gain",
                   "latent", "answer", "truth", "expected", "privileged"}
    for world in worlds.all_worlds() + worlds.dev_worlds():
        keys: set = set()
        _walk_keys(world, keys)
        assert not (keys & banned_keys), (world["world_id"], keys & banned_keys)


def test_observation_release_independent_of_policy():
    world = WORLDS["w05"]
    key = next(k for k, p in world["probes"].items() if len(p["observes"]) == 1)
    prop = world["probes"][key]["observes"][0]
    first = [runner.simulate_value(world, key, 0, prop) for _ in range(2)]
    assert first[0] == first[1]
    probe = world["probes"][key]
    spec = dict(world["props"][prop])
    obs = observations.public_observation(prop, spec, True, "att", "rc", 3)
    assert set(obs) <= observations.OBS_KEYS
    assert obs["value"] in (True, False, "unknown")
    assert probe["cost"] in (2, 4, 8)


def test_wrong_answer_control_fails_grading():
    for world in worlds.all_worlds():
        wrong = grader.wrong_answers(world)
        inverted = {t["prop"]: wrong[t["task_id"]] for t in world["tasks"]}
        result = grader.grade([], inverted, world)
        assert result["total"] == 8
        assert result["correct"] == 0


def test_database_prerequisite_explicit():
    probe = f"agenda01_prereq_{os.getpid()}"
    try:
        runner.drop_db(BASE_DSN, probe)
    except Exception:
        pass
    try:
        runner.create_db(BASE_DSN, probe)
    except Exception as exc:
        pytest.fail(
            "missing database prerequisite: CREATE DATABASE failed"
            f" ({type(exc).__name__}: {exc})")
    try:
        runner.drop_db(BASE_DSN, probe)
    except Exception as exc:
        pytest.fail(
            "missing database prerequisite: DROP DATABASE failed"
            f" ({type(exc).__name__}: {exc})")


def test_positive_control_R(tmp_path):
    for wid in worlds.CONTROL_WORLDS:
        trace = durable(wid, "R", tmp_path)
        assert trace["grade"]["correct"] == 8, wid
        assert trace["manifest_sha256"] == MHASH


def test_positive_control_Q(tmp_path):
    for wid in worlds.CONTROL_WORLDS:
        trace = durable(wid, "Q", tmp_path)
        assert trace["grade"]["correct"] == 8, wid


def test_q_losing_world_reports_honestly(tmp_path):
    wid = worlds.Q_LOSING_WORLD
    trace_r = durable(wid, "R", tmp_path)
    trace_q = durable(wid, "Q", tmp_path)
    assert trace_r["complete"] and trace_q["complete"]
    report = checker.check_dir(tmp_path, MANIFEST, MHASH, manifest.BUDGETS)
    assert report["ok"], report["violations"]
    print(f"{wid}: R={trace_r['grade']['correct']} Q={trace_q['grade']['correct']}")


def test_cross_arm_discovery_replay_refused():
    dsn_a, name_a, backend_a = scratch_backend("arma")
    dsn_b, name_b, backend_b = scratch_backend("armb")
    try:
        backend_a.propose_seed("s-x", {"seed_class": "bottleneck", "question": "q",
                                       "probe": "m0", "cap": 8, "expiry": 24}, "s0")
        admitted = backend_a.admit_initial(
            0, "s-x", "m0", "execute-m0", {"d0": 1}, 2, 1,
            "AG01-TEST-1", "digest-test",
            {"observed": [], "product": [], "dud": True}, 1)
        assert admitted.code == ResultCode.APPLIED
        foreign = backend_b.record("s-x", admitted.data["attempt_id"], "rc-x")
        assert foreign.code == ResultCode.INVALID_INPUT
        assert "wrong attempt" in foreign.detail
        assert backend_b.export_ledger()["reservations"] == []
        agenda_status = store.allocation_status(dsn_a, backend_a.explore)
        assert agenda_status["reserved"] == 2
    finally:
        drop_scratch(name_a)
        drop_scratch(name_b)


def test_admit_without_grant_refused():
    from settlement import agenda
    _, name, backend = scratch_backend("nogrant", setup=False)
    try:
        refused = agenda.propose_option(
            backend.dsn, Command(request_id="ag01-test-propose-nogrant",
                                 payload={"option_key": "s-g", "scope": "s0",
                                          "question": "q", "revision": 1,
                                          "allocation_root": backend.explore,
                                          "body": {}}))
        assert refused.code == ResultCode.INVALID_INPUT
        assert "unknown allocation root" in refused.detail
    finally:
        drop_scratch(name)


def test_dispatch_without_launcher_awaits():
    _, name, backend = scratch_backend("nolaunch")
    try:
        backend.propose_seed("s-l", {"seed_class": "transfer", "question": "q",
                                     "probe": "m0", "cap": 8, "expiry": 24}, "s0")
        admitted = backend.admit_initial(
            0, "s-l", "m0", "execute-m0", {"d0": 1}, 2, 1,
            "AG01-TEST-1", "digest-test",
            {"observed": [], "product": [], "dud": True}, 1)
        assert admitted.code == ResultCode.APPLIED
        status = broker.dispatch_operation(backend.dsn, admitted.data["operation_id"])
        assert status.dispatch_state == "prepared"
        assert status.next_decision == "awaiting-launcher"
    finally:
        drop_scratch(name)


def test_rotated_grant_refuses_dispatch():
    dsn, name, backend = scratch_backend("revoke")
    try:
        backend.propose_seed("s-v", {"seed_class": "transfer", "question": "q",
                                     "probe": "m0", "cap": 8, "expiry": 24}, "s0")
        admitted = backend.admit_initial(
            0, "s-v", "m0", "execute-m0", {"d0": 1}, 2, 1,
            "AG01-TEST-1", "digest-test",
            {"observed": [], "product": [], "dud": True}, 1)
        assert admitted.code == ResultCode.APPLIED
        rotated = store.seed_grant(
            dsn, Command(request_id="ag01-test-grant-v2",
                         payload={"version": 2, "charter_text": "rotated authority",
                                  "authority_grant": {}, "envelopes": {}}))
        assert rotated.code == ResultCode.APPLIED
        status = backend.dispatch_probe(admitted.data["operation_id"])
        assert status.dispatch_state == "prepared"
        assert status.next_decision == "stale-grant"
    finally:
        drop_scratch(name)


def test_privileged_access_raises():
    code = ("import sys; sys.path.insert(0, %r);"
            " from experiments.agenda01 import observations;"
            " from experiments.agenda01 import grader" % str(ROOT))
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "privileged" in proc.stderr
    code_rev = ("import sys; sys.path.insert(0, %r);"
                " from experiments.agenda01 import grader;"
                " from experiments.agenda01 import observations" % str(ROOT))
    proc = subprocess.run([sys.executable, "-c", code_rev], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    mod = sys.modules[__name__]
    setattr(mod, grader.POLICY_PATH_MARK, True)
    try:
        try:
            grader.latent_bit("w00", "p0")
        except ImportError:
            pass
        else:
            raise AssertionError("grader must refuse policy-path callers")
    finally:
        delattr(mod, grader.POLICY_PATH_MARK)
    assert grader.latent_bit("w00", "p0") in (True, False)


def test_branch_cap_reset_refused():
    _, name, backend = scratch_backend("cap")
    try:
        reset = store.subdivide_allocation(
            backend.dsn,
            Command(request_id="ag01-cap-reset-attempt",
                    payload={"parent_id": backend.root,
                             "child_id": f"{backend.root}:explore2",
                             "authorized": 64, "domain": "agenda01"}))
        assert reset.code == ResultCode.INSUFFICIENT_RESOURCES, reset
        reseed = store.seed_allocation(
            backend.dsn,
            Command(request_id="ag01-reseed-attempt",
                    payload={"allocation_id": backend.explore,
                             "domain": "agenda01", "authorized": 64}))
        assert reseed.code == ResultCode.INVALID_INPUT, reseed
        assert "already exists" in reseed.detail
        status = store.allocation_status(backend.dsn, backend.explore)
        assert status["authorized"] == 64
        with pytest.raises(SettlementError):
            backend.charge_aux("dec-overdraft", 10 ** 6, backend.explore)
    finally:
        drop_scratch(name)


def test_duplicate_outoforder_wakeup_single_effect():
    from settlement import agenda
    from settlement.common import Command as _Command
    _, name, backend = scratch_backend("wake")
    try:
        backend.propose_seed("s-w", {"seed_class": "transfer", "question": "q",
                                     "probe": "m0", "cap": 8, "expiry": 24}, "s0")
        dormant = agenda.set_dormant(
            backend.dsn, _Command(request_id="ag01-decline-s-w",
                                  payload={"option_id": "s-w",
                                           "expected_disposition_version": 1,
                                           "reason": "awaiting evidence",
                                           "wake_condition": {"type": "evidence-change",
                                                              "dep": "d0"}}))
        assert dormant.code == ResultCode.APPLIED
        noise = agenda.process_wake(
            backend.dsn, _Command(request_id="ag01-wake-s-w-noise",
                                  payload={"option_id": "s-w",
                                           "event": {"identity": "ev:1:k",
                                                     "kind": "message"}}))
        assert noise.code == ResultCode.APPLIED
        assert noise.data["woke"] is False
        first = agenda.process_wake(
            backend.dsn, _Command(request_id="ag01-wake-s-w-ev",
                                  payload={"option_id": "s-w",
                                           "event": {"identity": "ev:0:k",
                                                     "kind": "evidence-changed",
                                                     "dep": "d0", "version": 2}}))
        assert first.code == ResultCode.APPLIED
        assert first.data["woke"] is True
        redeliver = agenda.process_wake(
            backend.dsn, _Command(request_id="ag01-wake-s-w-ev-again",
                                  payload={"option_id": "s-w",
                                           "event": {"identity": "ev:0:k",
                                                     "kind": "evidence-changed",
                                                     "dep": "d0", "version": 2}}))
        assert redeliver.code == ResultCode.ALREADY_APPLIED
        admitted = backend.admit_initial(
            0, "s-w", "m0", "execute-m0", {"d0": 2}, 2, 1,
            "AG01-TEST-1", "digest-test",
            {"observed": [{"prop": "p0", "scope": "s0", "dep": "d0"}],
             "product": [], "dud": False}, 1)
        assert admitted.code == ResultCode.APPLIED
        op = admitted.data["operation_id"]
        assert backend.dispatch_probe(op).sent_this_call
        receipt = backend.sim.read_result(op)["p0"]["receipt"]
        seen = backend.record("s-w", admitted.data["attempt_id"], receipt)
        assert seen.code == ResultCode.APPLIED
        again = backend.record("s-w", admitted.data["attempt_id"], receipt)
        assert again.code == ResultCode.ALREADY_APPLIED
    finally:
        drop_scratch(name)


def test_stale_select_admit_refused():
    from settlement import agenda
    from settlement.common import Command as _Command
    _, name, backend = scratch_backend("stale")
    try:
        backend.propose_seed("s-s", {"seed_class": "transfer", "question": "q",
                                     "probe": "m0", "cap": 8, "expiry": 24}, "s0")
        retired = agenda.retire_option(
            backend.dsn, _Command(request_id="ag01-retire-s-s",
                                  payload={"option_id": "s-s",
                                           "expected_disposition_version": 1,
                                           "reason": "stale"}))
        assert retired.code == ResultCode.APPLIED
        refused = backend.admit_initial(
            0, "s-s", "m0", "execute-m0", {"d0": 1}, 2, 1,
            "AG01-TEST-1", "digest-test",
            {"observed": [], "product": [], "dud": True}, 1)
        assert refused.code == ResultCode.INVALID_INPUT
    finally:
        drop_scratch(name)


def test_resolve_policy_binds_real_policies():
    assert runner.resolve_policy("R").__name__ == "decide_R"
    assert runner.resolve_policy("Q").__name__ == "decide_Q"
    assert (POLICY_R_VERSION, POLICY_Q_VERSION) == ("AG01-R-1", "AG01-Q-2")


def _comparable(trace):
    trace = copy.deepcopy(trace)
    trace.pop("db", None)
    trace.pop("backend", None)
    return trace


def _write_frozen_manifest(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    hash_path = tmp_path / "manifest.sha256"
    manifest_path.write_text(json.dumps(MANIFEST, sort_keys=True, indent=2))
    hash_path.write_text(MHASH + "\n")
    return manifest_path, hash_path


def _db_oid(db_name):
    with db.read_connect(BASE_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT oid FROM pg_database WHERE datname = %s", (db_name,))
            oid = int(cur.fetchone()[0])
            conn.commit()
    return oid


def test_resume_continues_saved_progress(tmp_path):
    from experiments.agenda01 import replay
    world_id, arm, tie = "w25", "R", 0
    world = WORLDS[world_id]
    control_dir = tmp_path / "control"
    control_dir.mkdir()
    control = runner.run_trajectory(
        BASE_DSN, world, arm, tie, runner.resolve_policy(arm),
        POLICY_VERSIONS[arm], MANIFEST, MHASH, control_dir)
    assert control["complete"]
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    partial = runner.run_trajectory(
        BASE_DSN, world, arm, tie, runner.resolve_policy(arm),
        POLICY_VERSIONS[arm], MANIFEST, MHASH, work_dir,
        keep_db=True, max_ticks=3)
    assert not partial["complete"]
    traj = runner._traj_for(world, arm, tie)
    db_name = f"agenda01_{traj}"
    traj_dsn = runner.swap_dbname(BASE_DSN, db_name)
    with db.connect(traj_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM agenda_attempt_links l"
                        " WHERE NOT EXISTS (SELECT 1 FROM agenda_outcomes o"
                        " WHERE o.attempt_id = l.attempt_id)")
            pending = int(cur.fetchone()[0])
            cur.execute("CREATE TABLE ag01_sentinel (v TEXT)")
            cur.execute("INSERT INTO ag01_sentinel VALUES ('sentinel-%s')" % traj)
            cur.execute("SELECT tick, ticks, idle FROM agenda_traj_state"
                        " WHERE trajectory = %s", (traj,))
            saved = cur.fetchone()
            conn.commit()
    assert pending > 0, "interrupted run must hold pending effects"
    assert saved[0] == 3, saved
    assert [t["tick"] for t in saved[1]] == [0, 1, 2], "saved progress keeps every tick record"
    oid_before = _db_oid(db_name)
    manifest_path, hash_path = _write_frozen_manifest(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.agenda01.replay", "run",
         "--base-dsn", BASE_DSN, "--world", world_id, "--arm", arm,
         "--tie", str(tie), "--manifest", str(manifest_path),
         "--manifest-hash-file", str(hash_path),
         "--out-dir", str(work_dir), "--keep-db", "--resume"],
        capture_output=True, text=True, timeout=280, cwd=str(ROOT),
        env=dict(os.environ, PYTHONPATH="src"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    try:
        assert _db_oid(db_name) == oid_before, "resume must continue the same database"
        with db.read_connect(traj_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT v FROM ag01_sentinel")
                assert cur.fetchone()[0] == f"sentinel-{traj}"
                conn.commit()
        resumed = json.loads((work_dir / f"{traj}.json").read_text())
        assert resumed["complete"]
        assert replay.compare_traces(control, resumed) == []
    finally:
        runner.drop_db(BASE_DSN, db_name)


def test_resume_refuses_fresh_database(tmp_path):
    traj = runner._traj_for(WORLDS["w25"], "R", 0)
    try:
        runner.drop_db(BASE_DSN, f"agenda01_{traj}")
    except Exception:
        pass
    manifest_path, hash_path = _write_frozen_manifest(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.agenda01.replay", "run",
         "--base-dsn", BASE_DSN, "--world", "w25", "--arm", "R",
         "--tie", "0", "--manifest", str(manifest_path),
         "--manifest-hash-file", str(hash_path),
         "--out-dir", str(tmp_path), "--resume"],
        capture_output=True, text=True, timeout=120, cwd=str(ROOT),
        env=dict(os.environ, PYTHONPATH="src"))
    assert proc.returncode != 0
    assert "no saved progress" in (proc.stdout + proc.stderr)


def test_replay_verify_detects_tampering(tmp_path):
    from experiments.agenda01 import replay
    control = durable("dev00", "R", tmp_path)
    assert control["complete"]
    tampered = copy.deepcopy(control)
    tampered["ledger"]["reservations"][0]["amount"] += 1
    assert replay.compare_traces(control, tampered) != []
    dropped = copy.deepcopy(control)
    dropped["ledger"]["reservations"].pop()
    assert replay.compare_traces(control, dropped) != []


def _continuation_admissions(trace):
    return [d for d in trace["ledger"]["decisions"]
            if d["selection"].get("kind") == "continuation"
            and d["selection"].get("decision") == "useful-continuation"]


def test_diagnostic_useful_continuation(tmp_path):
    for arm in ("R", "Q"):
        trace = durable("dev02", arm, tmp_path)
        assert trace["complete"], arm
        assert trace["grade"]["correct"] == 2, (arm, trace["grade"])
        admitted = _continuation_admissions(trace)
        assert len(admitted) == 1, (arm, trace["ledger"]["decisions"])
        assert admitted[0]["selection"]["probe"] == "m1", arm


def test_diagnostic_wasteful_split(tmp_path):
    awarded = durable("dev03", "R", tmp_path)
    refused = durable("dev03", "Q", tmp_path)
    assert awarded["grade"]["correct"] == refused["grade"]["correct"] == 1
    admitted = _continuation_admissions(awarded)
    assert len(admitted) == 1, awarded["ledger"]["decisions"]
    assert admitted[0]["selection"]["probe"] == "m1"
    assert _continuation_admissions(refused) == []
    assert not any(l["probe"] == "m1" for l in refused["ledger"]["links"])
    skips = [t for t in refused["ticks"]
             for e in t["decision"].get("evaluated", [])
             if e.get("skipped") == "unqualified-continuation"]
    assert skips, [t["decision"] for t in refused["ticks"]]
    assert (awarded["totals"]["explore_spent"]
            == refused["totals"]["explore_spent"] + 2)


def test_diagnostic_premature_stopping_cost(tmp_path):
    world = DEV["dev02"]
    full = durable("dev02", "R", tmp_path)
    assert full["grade"]["correct"] == 2
    late = [o for o in full["observations"] if o["prop"] == "p1"]
    assert len(late) == 1
    assert late[0]["source_attempt"].endswith("-m1")
    short = runner.run_trajectory(
        BASE_DSN, world, "R", 0, runner.resolve_policy("R"),
        POLICY_VERSIONS["R"], MANIFEST, MHASH, tmp_path,
        keep_db=True, max_ticks=1)
    assert not short["complete"]
    traj = runner._traj_for(world, "R", 0)
    try:
        with db.read_connect(runner.swap_dbname(BASE_DSN, f"agenda01_{traj}")) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM agenda_attempt_links"
                            " WHERE probe = 'm1'")
                assert int(cur.fetchone()[0]) == 0
                conn.commit()
    finally:
        runner.drop_db(BASE_DSN, f"agenda01_{traj}")


def test_agreement_durable_deterministic(tmp_path):
    for wid in ("dev00", "dev01"):
        for arm in ("R", "Q"):
            first = durable(wid, arm, tmp_path)
            second = durable(wid, arm, tmp_path)
            assert _comparable(first) == _comparable(second), (wid, arm)


def test_productless_probe_completes(tmp_path):
    for arm in ("R", "Q"):
        trace = durable("w11", arm, tmp_path)
        assert trace["complete"], ("w11", arm)
    report = checker.check_dir(tmp_path, MANIFEST, MHASH, manifest.BUDGETS)
    assert report["ok"], report["violations"]


def test_fence_admits_brain_selections(tmp_path):
    for arm in ("R", "Q"):
        trace = durable("dev00", arm, tmp_path)
        refused = [t for t in trace["ticks"]
                   if (t["decision"].get("idle_reason") or "").startswith("fence-refused")]
        assert refused == [], (arm, refused)


def test_checker_accepts_and_rejects(tmp_path):
    traces = [durable("w28", arm, tmp_path, tie)
              for arm in ("R", "Q") for tie in (0, 1)]
    assert len(traces) == 4
    report = checker.check_dir(tmp_path, MANIFEST, MHASH, manifest.BUDGETS)
    assert report["ok"], report["violations"]
    assert len(report["pairs"]) == 2
    bad = copy.deepcopy(traces[0])
    bad["ledger"]["reservations"][0]["amount"] += 1
    assert any("altered" in r or "mismatch" in r
               for r in checker.check_trace(bad, MANIFEST, MHASH, WORLDS["w28"],
                                            manifest.BUDGETS))
    missing = copy.deepcopy(traces[1])
    del missing["ledger"]
    assert any("missing" in r
               for r in checker.check_trace(missing, MANIFEST, MHASH, WORLDS["w28"],
                                            manifest.BUDGETS))
    dup = copy.deepcopy(traces[2])
    twin = copy.deepcopy(dup["ledger"]["reservations"][0])
    twin["amount"] += 5
    dup["ledger"]["reservations"].append(twin)
    assert any("duplicate" in r or "conflict" in r or "altered" in r
               or "mismatch" in r
               for r in checker.check_trace(dup, MANIFEST, MHASH, WORLDS["w28"],
                                            manifest.BUDGETS))
    drifted = checker.check_trace(traces[0], MANIFEST, "0" * 64, WORLDS["w28"],
                                  manifest.BUDGETS)
    assert any("manifest-hash-mismatch" in r for r in drifted)
    rebranded = copy.deepcopy(traces[0])
    rebranded["policy_version"] = "AG01-Q-1"
    assert any("policy-version-mismatch" in r
               for r in checker.check_trace(rebranded, MANIFEST, MHASH, WORLDS["w28"],
                                            manifest.BUDGETS))
    unattributed = copy.deepcopy(traces[0])
    unattributed["totals"]["liabilities"] = []
    unattributed["ledger"]["reservations"][0]["state"] = "held"
    assert any("unattributed-exposure" in r or "reserved-mismatch" in r
               for r in checker.check_trace(unattributed, MANIFEST, MHASH,
                                            WORLDS["w28"], manifest.BUDGETS))
    assert checker.main([]) == 2


def test_checker_pair_membership(tmp_path):
    for arm in ("R", "Q"):
        for tie in (0, 1):
            durable("w28", arm, tmp_path, tie)
    small = {"worlds": [WORLDS["w28"]]}
    full = checker.check_dir(tmp_path, small, MHASH, manifest.BUDGETS,
                             expect_full=True)
    assert full["ok"], full["violations"]
    victim = next(Path(tmp_path).glob("*_r_t0.json"))
    victim.unlink()
    partial = checker.check_dir(tmp_path, small, MHASH, manifest.BUDGETS,
                                expect_full=True)
    assert not partial["ok"]
    assert any("incomplete-pair" in v for vs in partial["violations"].values()
               for v in vs)
    for left in Path(tmp_path).glob("*_r_t1.json"):
        left.unlink()
    gone = checker.check_dir(tmp_path, small, MHASH, manifest.BUDGETS,
                             expect_full=True)
    assert not gone["ok"]
    assert any("incomplete-pair" in v for vs in gone["violations"].values()
               for v in vs)


def test_manifest_build_freeze_ready(tmp_path):
    first, digest = manifest.build()
    _, redigest = manifest.build()
    assert digest == redigest
    assert len(first["worlds"]) == 32
    assert first["budgets"] == {"ticks": 24, "exploration": 64,
                                "eval_per_trajectory": 8, "recovery_cap": 16,
                                "decision_cost": 1}
    assert first["policy_versions"] == {"R": "AG01-R-1", "Q": "AG01-Q-2"}
    assert first["grammar"] == "AG01-OBS-1"
    for wid, ties in first["tie_orders"].items():
        assert ties["t1"] == list(reversed(ties["t0"]))
    assert first["controls"]["q_losing"] == worlds.Q_LOSING_WORLD
    assert set(first["controls"]["positive"]) == set(worlds.CONTROL_WORLDS)
    saved_manifest = (manifest.MANIFEST_PATH.read_bytes()
                      if manifest.MANIFEST_PATH.exists() else None)
    saved_hash = (manifest.HASH_PATH.read_bytes()
                  if manifest.HASH_PATH.exists() else None)
    manifest_path, hash_path, _ = manifest.write()
    try:
        loaded, loaded_hash = manifest.load()
        assert loaded_hash == digest
        assert loaded["experiment"] == manifest.EXPERIMENT_VERSION
    finally:
        if saved_manifest is None:
            manifest_path.unlink(missing_ok=True)
            hash_path.unlink(missing_ok=True)
        else:
            manifest_path.write_bytes(saved_manifest)
            hash_path.write_bytes(saved_hash)


def test_freeze_identity_ignores_revision(tmp_path):
    doc, digest = manifest.build()
    relabeled = copy.deepcopy(doc)
    relabeled["source_revision"] = "doc-only-commit"
    assert manifest.canonical_digest(relabeled) == digest
    manifest_path, hash_path = _write_frozen_manifest(tmp_path)
    loaded, _ = manifest.load_verified(manifest_path, hash_path)
    assert loaded["experiment"] == manifest.EXPERIMENT_VERSION
    tampered = copy.deepcopy(MANIFEST)
    tampered["analysis_rule"] = "changed without changing supplied digest"
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text(json.dumps(tampered, sort_keys=True, indent=2))
    with pytest.raises(ValueError, match="manifest drift"):
        manifest.load_verified(tampered_path, hash_path)


def test_prepared_operation_resumed_without_receipt(tmp_path):
    world = WORLDS["w25"]
    partial = runner.run_trajectory(
        BASE_DSN, world, "R", 0, runner.resolve_policy("R"),
        POLICY_VERSIONS["R"], MANIFEST, MHASH, tmp_path,
        keep_db=True, max_ticks=2)
    assert not partial["complete"]
    traj = runner._traj_for(world, "R", 0)
    traj_dsn = runner.swap_dbname(BASE_DSN, f"agenda01_{traj}")
    try:
        backend = runner.AgendaBackend(traj_dsn, traj, None)
        bound = {(l["option_id"], l["probe"]) for l in backend.links()}
        seed = next(s for s in world["seeds"]
                    if (s["option_key"], s["probe"]) not in bound)
        cursor = backend.cursor()
        plan = runner._plan_for(world, seed["probe"])
        admitted = backend.admit_initial(
            2, seed["option_key"], seed["probe"],
            f"execute-{seed['probe']}", dict(cursor.get("dep_versions") or {}),
            world["probes"][seed["probe"]]["cost"], 1, POLICY_VERSIONS["R"],
            "digest-test", plan, int(cursor["epoch"]) + 1)
        assert admitted.code == ResultCode.APPLIED, admitted
        op_id = admitted.data["operation_id"]
        assert backend.receipts_for(op_id) == []
        assert (backend.operation(op_id) or {})["dispatch_state"] == "prepared"
        resumed = runner.run_trajectory(
            BASE_DSN, world, "R", 0, runner.resolve_policy("R"),
            POLICY_VERSIONS["R"], MANIFEST, MHASH, tmp_path,
            keep_db=True, resume=True)
        assert resumed["complete"]
        assert backend.receipts_for(op_id) != [], "resume must dispatch the prepared op"
        with db.read_connect(traj_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM agenda_outcomes o"
                            " JOIN agenda_attempt_links l ON l.attempt_id = o.attempt_id"
                            " WHERE l.operation_id = %s", (op_id,))
                assert int(cur.fetchone()[0]) > 0, "prepared op outcomes recorded"
                cur.execute("SELECT tick FROM agenda_decisions WHERE trajectory = %s"
                            " ORDER BY tick", (traj,))
                ticks = [r[0] for r in cur.fetchall()]
                conn.commit()
        assert ticks == sorted(ticks) and len(set(ticks)) == len(ticks), ticks
        assert len(resumed["ticks"]) == 24
        assert all(t.get("dec_op") for t in resumed["ticks"])
    finally:
        runner.drop_db(BASE_DSN, f"agenda01_{traj}")


def test_duplicate_effect_decisions_charged(tmp_path):
    world = WORLDS["w08"]
    trace = runner.run_trajectory(
        BASE_DSN, world, "R", 0, runner.resolve_policy("R"),
        POLICY_VERSIONS["R"], MANIFEST, MHASH, tmp_path, keep_db=True)
    try:
        assert trace["complete"]
        assert len(trace["ticks"]) == 24
        assert all(t.get("dec_op") for t in trace["ticks"]), "every tick carries its charge"
        assert any("duplicate-effect" in str(t["decision"].get("idle_reason") or "")
                   for t in trace["ticks"]), "w08 must exercise the duplicate path"
        dec_charges = [r for r in trace["ledger"]["reservations"]
                       if ":dec:" in str(r.get("operation_id", ""))]
        assert len(dec_charges) == 24, len(dec_charges)
        bad = checker.check_trace(trace, MANIFEST, MHASH, world, manifest.BUDGETS)
        assert bad == [], bad
    finally:
        runner.drop_db(BASE_DSN, trace["db"])


def test_receipt_timing_matches_declared_clock(tmp_path):
    trace = durable("w25", "R", tmp_path, 0)
    assert trace["complete"]
    world = WORLDS["w25"]
    launched_tick = {}
    for i, tick in enumerate(trace["ticks"]):
        if tick["decision"]["action"] == "probe" and tick.get("probe_op"):
            launched_tick[tick["probe_op"].rstrip("c")] = i
    links = {l["operation_id"]: l for l in trace["ledger"]["links"]}
    by_attempt = {}
    for outcome in trace["ledger"]["outcomes"]:
        by_attempt.setdefault(outcome["observation"]["source_attempt"], outcome["epoch"])
    checked = 0
    for op_id, launch in sorted(launched_tick.items()):
        link = links.get(op_id)
        if link is None:
            continue
        attempt = link["attempt_id"]
        if attempt not in by_attempt:
            continue
        delay = int(world["probes"][link["probe"]].get("delay", 0))
        assert by_attempt[attempt] == launch + delay, (op_id, launch, delay)
        checked += 1
    assert checked > 0
    slow = [l for l in trace["ledger"]["links"] if l["probe"] == "slow"]
    assert slow, "w25 must launch the delayed probe"


def test_checker_rejects_gate_mutations(tmp_path):
    traces = [durable("w28", arm, tmp_path, tie)
              for arm in ("R", "Q") for tie in (0, 1)]
    trace = traces[0]
    world = WORLDS["w28"]
    assert checker.check_trace(trace, MANIFEST, MHASH, world, manifest.BUDGETS) == []
    incomplete = copy.deepcopy(trace)
    incomplete["complete"] = False
    assert any("incomplete-trajectory" in r
               for r in checker.check_trace(incomplete, MANIFEST, MHASH, world,
                                            manifest.BUDGETS))
    uncharged = copy.deepcopy(trace)
    uncharged["ticks"][0]["dec_op"] = None
    assert any("missing-decision-charge" in r
               for r in checker.check_trace(uncharged, MANIFEST, MHASH, world,
                                            manifest.BUDGETS))
    drifted_sources = copy.deepcopy(trace)
    drifted_sources["sources"] = dict(trace["sources"])
    drifted_sources["sources"]["src/settlement/store.py"] = "0" * 64
    assert any("source-drift" in r
               for r in checker.check_trace(drifted_sources, MANIFEST, MHASH, world,
                                            manifest.BUDGETS))
    drifted_files = copy.deepcopy(trace)
    drifted_files["files"] = dict(trace["files"])
    drifted_files["files"]["runner.py"] = "0" * 64
    assert any("file-drift" in r
               for r in checker.check_trace(drifted_files, MANIFEST, MHASH, world,
                                            manifest.BUDGETS))
    report = checker.check_dir(tmp_path, MANIFEST, MHASH, manifest.BUDGETS)
    assert report["ok"], report["violations"]
    twin = tmp_path / "duplicate.json"
    twin.write_text((tmp_path / f"{trace['traj_id']}.json").read_text())
    try:
        duped = checker.check_dir(tmp_path, MANIFEST, MHASH, manifest.BUDGETS,
                                  expect_full=True)
        assert not duped["ok"]
        assert any("duplicate-trajectory" in v
                   for vs in duped["violations"].values() for v in vs)
    finally:
        twin.unlink()


def _lane_experiments():
    lane = str(ROOT / "experiments")
    if lane not in sys.path:
        sys.path.insert(0, lane)
    import doubles
    import fault_tasks
    return doubles, fault_tasks


def _adapter_run(script: str, action: str, payload: dict, tmp_path):
    req = {"profile": "representation-01/1", "profile_version": "1",
           "task_id": "t", "composition_id": "c", "core_digest": "d",
           "adapter_digest": "a", "action": action, "payload": payload}
    request_path = tmp_path / "req.json"
    response_path = tmp_path / "resp.json"
    request_path.write_text(json.dumps(req))
    proc = subprocess.run(
        [sys.executable,
         str(ROOT / "experiments" / "representation" / "acquire" / script),
         str(request_path), str(response_path)],
        capture_output=True, text=True, timeout=120)
    envelope = json.loads(response_path.read_text()) \
        if response_path.is_file() else None
    return proc, envelope


def test_doubles_lesson_counts_real_transcript_shape():
    doubles, fault_tasks = _lane_experiments()
    from settlement.gateway import ModelRequest, ModelResponse

    tasks = {t["id"]: t for t in fault_tasks.TASKS}
    double = doubles.ScriptedDouble(
        {("DEV", "dev-sum"): True},
        {i: t["fixed"] for i, t in tasks.items()},
        {i: t["broken"] for i, t in tasks.items()})
    record = [
        {"task_id": "dev-sum", "family": "off_by_one",
         "outcome": "success",
         "model_text": tasks["dev-sum"]["fixed"][:2000]},
        {"task_id": "dev-collect", "family": "off_by_one",
         "outcome": "success", "model_text": "repaired"},
        {"task_id": "dev-series", "family": "off_by_one",
         "outcome": "failure", "model_text": "still broken"}]
    request = ModelRequest(
        model="scripted",
        messages=({"role": "user",
                   "content": json.dumps({"author_lesson": True,
                                          "dev_transcripts": record})},),
        max_output_tokens=100, deadline_ms=1000, operation_id="op-lesson")
    response = double.infer(request)
    assert isinstance(response, ModelResponse)
    assert "Authored from 2/3 successful development repairs." in response.text


def test_sw_adapter_decode_refuses_nondict_aux(tmp_path):
    task = {"family": "software", "task_id": "t", "fault": "stale-read",
            "ops": [{"op": "set", "key": "a", "value": "v1"},
                    {"op": "get", "key": "a", "id": "o0"}],
            "witness": {"observation": "o0", "ref": 1, "faulty": 2},
            "seed": 1}
    proc, envelope = _adapter_run(
        "sw_adapter.py", "decode",
        {"proposal": {"kept": [0]}, "source_task": task, "aux": [1, 2]},
        tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert envelope is not None, "refusing adapter must still write an envelope"
    assert envelope["status"] == "refuse"
    assert envelope["reason"] == "malformed"


def test_atom_core_malformed_atoms_reports_cause(tmp_path):
    proc, envelope = _adapter_run(
        "atom_core.py", "start",
        {"encoded_object": {"atoms": [],
                            "tunables": {"chunk_frac": 2,
                                         "max_proposals": 4,
                                         "order": "tail"}}},
        tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert envelope is not None
    assert envelope["status"] == "refuse"
    assert envelope["reason"] == "malformed"
    assert envelope["detail"] == "encoded atoms must be a nonempty int list"


def test_charge_aux_books_a_charge_and_no_operation():
    """charge_aux is a charge, so it must leave no operations row behind.

    Three entry points are asserted separately on purpose. They agree only
    while the charge stays a charge: the direct call, the reservation's own
    operation_id, and the ledger the checker reads. A version that mints an
    operations row satisfies none of the third, and a version that blanks
    operation_id fails the checker by collapsing distinct charges into one
    union key.
    """
    _, name, backend = scratch_backend("charge")
    try:
        charge_id = backend.charge_aux("eval-final", 3, backend.eval)

        assert backend.operation(charge_id) is None, \
            "a charge that is never dispatched must not be an operations row"

        with db.read_connect(backend.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT operation_id, state, amount FROM reservations"
                            " WHERE id = %s", (f"{charge_id}:res",))
                row = cur.fetchone()
            conn.commit()
        assert row is not None, "the charge must leave a reservation row"
        operation_id, state, amount = row
        assert state == "settled"
        assert int(amount) == 3
        assert operation_id == charge_id, \
            "the charge keeps its own identity; reconciliation joins on it"

        status = store.allocation_status(backend.dsn, backend.eval)
        assert (status["consumed"], status["reserved"]) == (3, 0), status
    finally:
        drop_scratch(name)


def test_charge_aux_distinct_charges_do_not_collapse():
    """Two charges on one allocation must sum, not union into a single key.

    The checker adds settled cost per operation id
    (`checker._union_spent`). An empty operation_id — the literal reading of
    "stop naming operations" — collapses N recovery drains to one entry and
    under-reports the spend, which is the exact tamper the checker exists to
    reject.
    """
    _, name, backend = scratch_backend("collapse")
    try:
        backend.charge_aux("rec-a1", 1, backend.recovery)
        backend.charge_aux("rec-a2", 1, backend.recovery)

        ledger = backend.export_ledger()
        settled, unsettled, reasons = checker._union_spent(ledger, ":recovery", [])
        assert reasons == [], reasons
        assert unsettled == 0
        assert settled == 2, \
            f"two distinct charges must total 2, got {settled}"
        assert store.allocation_status(
            backend.dsn, backend.recovery)["consumed"] == 2
    finally:
        drop_scratch(name)


def test_charge_aux_refuses_an_unfundable_amount():
    """An overdraft must leave no reservation and spend no exposure."""
    _, name, backend = scratch_backend("overdraft2")
    try:
        with pytest.raises(SettlementError, match="charge overdraft refused"):
            backend.charge_aux("overdraft", 10 ** 6, backend.recovery)

        assert backend.export_ledger()["reservations"] == []
        status = store.allocation_status(backend.dsn, backend.recovery)
        assert (status["consumed"], status["reserved"]) == (0, 0), status
    finally:
        drop_scratch(name)


def test_charge_aux_is_idempotent_under_replay():
    """Replaying the same charge is ALREADY_APPLIED, not a second debit."""
    _, name, backend = scratch_backend("replay")
    try:
        first = backend.charge_aux("eval-final", 4, backend.eval)
        second = backend.charge_aux("eval-final", 4, backend.eval)

        assert first == second, (first, second)
        status = store.allocation_status(backend.dsn, backend.eval)
        assert (status["consumed"], status["reserved"]) == (4, 0), \
            "a replayed charge must debit exactly once"
    finally:
        drop_scratch(name)
