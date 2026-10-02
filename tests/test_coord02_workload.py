from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from experiments.coord02 import checker, freeze as freeze_mod, oracle

DEV = oracle.SPLITS["development"]


def _combined(task_id: str, kind: str, tmp_path: Path) -> dict:
    src = oracle.prepare_tree(task_id, kind, tmp_path / task_id / kind)
    cases = oracle.public_cases(task_id) + oracle.protected_cases(task_id)
    return oracle.evaluate_tree(src, cases)


def test_corpus_inventory():
    assert len(oracle.ALL_TASKS) == 30
    assert len(oracle.SPLITS["development"]) == 12
    assert len(oracle.SPLITS["evaluation"]) == 12
    assert len(oracle.SPLITS["transfer"]) == 6
    for fam in oracle.FAMILIES:
        members = [t for t in oracle.ALL_TASKS
                   if oracle.TASK_FAMILY[t] == fam]
        assert len(members) == 5
        assert sum(t in oracle.SPLITS["development"] for t in members) == 2
        assert sum(t in oracle.SPLITS["evaluation"] for t in members) == 2
        assert sum(t in oracle.SPLITS["transfer"] for t in members) == 1
    manifest = json.loads(
        (oracle.ROOT / "corpus" / "manifest.json").read_bytes())
    pinned = (oracle.ROOT / "corpus" / "manifest.sha256").read_text().strip()
    raw = (oracle.ROOT / "corpus" / "manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pinned
    assert manifest["version"] == "coord02-corpus/1"
    assert manifest["splits"] == oracle.SPLITS
    assert manifest["membership"] == oracle.TASK_FAMILY
    seen = set()
    for entry in manifest["files"]:
        target = oracle.ROOT.parent.parent / entry["path"]
        assert target.is_file(), entry["path"]
        assert hashlib.sha256(target.read_bytes()).hexdigest() \
            == entry["digest"]
        seen.add(entry["path"])
    for task_id in oracle.ALL_TASKS:
        for rel in oracle.task_files(task_id):
            want = "experiments/coord02/corpus/tasks/%s/%s" % (task_id, rel)
            assert want in seen, want


def test_valid_passes_broken_fails(tmp_path):
    for task_id in oracle.ALL_TASKS:
        valid = _combined(task_id, "valid", tmp_path)
        assert valid["failed"] == 0, task_id
        broken = _combined(task_id, "broken", tmp_path)
        assert broken["failed"] > 0, task_id
        invalid = _combined(task_id, "invalid", tmp_path)
        assert invalid["failed"] > 0, task_id


def test_sep_shortcut_misses_required_edits(tmp_path):
    for task_id in ("c02-t01", "c02-t02"):
        first_two = sorted(
            Path(p).name for p in oracle.worker_files(task_id))[:2]
        assert len(first_two) == 2
        shortcut = oracle.partial_tree(task_id, first_two,
                                       tmp_path / task_id / "shortcut")
        cases = oracle.public_cases(task_id) + oracle.protected_cases(task_id)
        assert oracle.evaluate_tree(shortcut, cases)["failed"] > 0
        assert _combined(task_id, "valid", tmp_path)["failed"] == 0


def test_cpl_locally_plausible_fails_combined(tmp_path):
    for task_id in ("c02-t06", "c02-t07"):
        src = oracle.prepare_tree(task_id, "invalid",
                                  tmp_path / task_id / "invalid")
        public = oracle.evaluate_tree(src, oracle.public_cases(task_id))
        assert public["failed"] == 0, task_id
        combined = oracle.evaluate_tree(
            src, oracle.public_cases(task_id) + oracle.protected_cases(task_id))
        assert combined["failed"] > 0, task_id
        solo = oracle.partial_tree(task_id, ["producer.py"],
                                   tmp_path / task_id / "solo")
        assert oracle.evaluate_tree(
            solo, oracle.public_cases(task_id)
            + oracle.protected_cases(task_id))["failed"] > 0
        assert _combined(task_id, "valid", tmp_path)["failed"] == 0


def test_dia_observation_changes_justified_choice(tmp_path):
    assert oracle.implicate("c02-t11") == "detect"
    assert oracle.implicate("c02-t12") == "operate"
    obs_det = oracle.observe("c02-t11", oracle.DIA_PROBES["c02-t11"][1])
    obs_op = oracle.observe("c02-t12", oracle.DIA_PROBES["c02-t12"][1])
    assert obs_det["output"] != obs_op["output"]
    for task_id, faulty in (("c02-t11", "detect"), ("c02-t12", "operate")):
        other = "operate" if faulty == "detect" else "detect"
        fixed_right = oracle.partial_tree(
            task_id, [faulty + ".py"], tmp_path / task_id / "right")
        fixed_wrong = oracle.partial_tree(
            task_id, [other + ".py"], tmp_path / task_id / "wrong")
        cases = oracle.public_cases(task_id) + oracle.protected_cases(task_id)
        assert oracle.evaluate_tree(fixed_right, cases)["failed"] == 0
        assert oracle.evaluate_tree(fixed_wrong, cases)["failed"] > 0
    lowered = "\n".join(
        (oracle.TASKS / t / "spec.md").read_text() for t in ("c02-t11",
                                                             "c02-t12"))
    assert "detect" not in lowered or "detect.py must" in lowered


def test_sng_single_owner_suffices(tmp_path):
    for task_id in ("c02-t16", "c02-t17"):
        shipped = {p: body for p, body in oracle.task_files(task_id).items()
                   if p.startswith("src/")}
        valid = oracle.overlay_files(task_id, "valid")
        changed = [name for name, body in valid.items()
                   if shipped.get("src/" + name) != body]
        assert changed == ["compute.py"], (task_id, changed)
        assert _combined(task_id, "valid", tmp_path)["failed"] == 0
        invalid = _combined(task_id, "invalid", tmp_path)
        prot_only = oracle.evaluate_tree(
            oracle.prepare_tree(task_id, "invalid",
                                tmp_path / task_id / "inv-prot"),
            oracle.protected_cases(task_id))
        assert prot_only["failed"] > 0 and invalid["failed"] > 0


def test_rw_reusable_and_stale(tmp_path):
    assert oracle.stale_after("c02-t21", {"convention.json"}, "render.py")
    assert oracle.stale_after("c02-t21", {"convention.json"}, "emit.py")
    assert oracle.stale_after("c02-t21", {"emit.py"}, "render.py")
    assert not oracle.stale_after("c02-t21", {"spec.md"}, "render.py")
    assert not oracle.stale_after("c02-t21", {"render.py"}, "emit.py")
    assert oracle.stale_after("c02-t15", {"spec:list_keys"}, "operate.py")
    assert not oracle.stale_after("c02-t15", {"spec:list_keys"}, "detect.py")
    for task_id in ("c02-t21", "c02-t22"):
        stale = oracle.prepare_tree(task_id, "rework-stale",
                                    tmp_path / task_id / "stale")
        fresh = oracle.prepare_tree(task_id, "rework-fresh",
                                    tmp_path / task_id / "fresh")
        carried = oracle.prepare_tree(task_id, "rework-carried",
                                      tmp_path / task_id / "carried")
        cases = oracle.public_cases(task_id) + oracle.protected_cases(task_id)
        assert oracle.evaluate_tree(stale, cases)["failed"] > 0, task_id
        assert oracle.evaluate_tree(fresh, cases)["failed"] == 0, task_id
        assert oracle.evaluate_tree(carried, cases)["failed"] == 0, task_id


def test_sco_refusal_and_renamed_use(tmp_path):
    binding = oracle.check_binding("c02-t26", "cpl/1")
    assert binding["eligible"] is False
    assert "interface-mismatch" in binding["reason"]
    assert oracle.check_binding("c02-t26", "nope/9")["eligible"] is False
    assert oracle.check_binding("c02-t27", "cellsum/1")["eligible"] is True
    cross = oracle.prepare_tree("c02-t26", "broken", tmp_path / "cross")
    shutil.copy(oracle.REFERENCE / "cpl" / "valid" / "producer.py",
                cross / "producer.py")
    shutil.copy(oracle.REFERENCE / "cpl" / "valid" / "consumer.py",
                cross / "consumer.py")
    cross_cases = oracle.public_cases("c02-t26") \
        + oracle.protected_cases("c02-t26")
    assert oracle.evaluate_tree(cross, cross_cases)["failed"] > 0
    assert _combined("c02-t27", "valid", tmp_path)["failed"] == 0
    assert _combined("c02-t26", "valid", tmp_path)["failed"] == 0


def test_transfer_topology_and_combined_pressures(tmp_path):
    dev_files = {t: set(oracle.worker_files(t)) for t in
                 ("c02-t01", "c02-t06", "c02-t11", "c02-t16", "c02-t21",
                  "c02-t26")}
    transfer_files = {t: set(oracle.worker_files(t)) for t in
                      oracle.SPLITS["transfer"]}
    assert transfer_files["c02-t05"] != dev_files["c02-t01"]
    assert transfer_files["c02-t10"] != dev_files["c02-t06"]
    assert len(transfer_files["c02-t10"]) == 3
    assert transfer_files["c02-t20"] != dev_files["c02-t16"]
    assert "src/helper.py" in transfer_files["c02-t20"]
    assert transfer_files["c02-t30"] != dev_files["c02-t26"]
    first_two = sorted(Path(p).name
                       for p in oracle.worker_files("c02-t05"))[:2]
    shortcut = oracle.partial_tree("c02-t05", first_two,
                                   tmp_path / "t05" / "shortcut")
    cases = oracle.public_cases("c02-t05") + oracle.protected_cases("c02-t05")
    assert oracle.evaluate_tree(shortcut, cases)["failed"] > 0
    swapped = oracle.prepare_tree("c02-t05", "valid", tmp_path / "t05" / "mix")
    (tmp_path / "t05" / "mix" / "src" / "pconv.py").write_text(
        (oracle.REFERENCE / "sep" / "invalid" / "pconv.py").read_text())
    (tmp_path / "t05" / "mix" / "src" / "cconv.py").write_text(
        (oracle.REFERENCE / "sep" / "invalid" / "cconv.py").read_text())
    assert oracle.evaluate_tree(swapped, cases)["failed"] > 0
    assert oracle.evaluate_tree(
        swapped, oracle.public_cases("c02-t05"))["failed"] == 0
    assert _combined("c02-t05", "valid", tmp_path)["failed"] == 0
    assert oracle.implicate("c02-t15") == "detect"
    stale15 = oracle.prepare_tree("c02-t15", "dia-stale",
                                  tmp_path / "t15" / "stale")
    cases15 = oracle.public_cases("c02-t15") + oracle.protected_cases("c02-t15")
    assert oracle.evaluate_tree(stale15, cases15)["failed"] > 0
    assert _combined("c02-t15", "valid", tmp_path)["failed"] == 0
    assert oracle.check_binding("c02-t30", "cpl/1")["eligible"] is False
    assert oracle.check_binding("c02-t30", "cellchain/1")["eligible"] is True
    assert _combined("c02-t30", "valid", tmp_path)["failed"] == 0
    assert _combined("c02-t10", "valid", tmp_path)["failed"] == 0
    assert _combined("c02-t10", "invalid", tmp_path)["failed"] > 0
    assert _combined("c02-t20", "valid", tmp_path)["failed"] == 0
    assert _combined("c02-t25", "valid", tmp_path)["failed"] == 0


def test_no_protected_leakage_into_solver_payload():
    for task_id in oracle.ALL_TASKS:
        payload = oracle.build_solver_payload(task_id)
        assert set(payload) == {"task_id", "spec", "public", "files"}
        blob = json.dumps(payload, sort_keys=True)
        for case in oracle.protected_cases(task_id):
            assert json.dumps(case, sort_keys=True) not in blob, task_id
        assert oracle.task_input_digest(task_id) \
            == hashlib.sha256(json.dumps(
                payload, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
    assert oracle.audit_barrier() == []


def _freeze(tmp_path: Path, freeze_id: str = "coord02-w-test") -> tuple:
    freeze = freeze_mod.build_freeze(freeze_id, source_sha="w-base")
    path = freeze_mod.write_freeze(tmp_path / (freeze_id + ".json"), freeze)
    return freeze, path


def test_freeze_round_trip(tmp_path):
    freeze, path = _freeze(tmp_path)
    assert freeze_mod.verify_freeze(path) == []
    assert len(freeze["schedule"]) == (12 + 12 + 6) * 4 * 2
    pairs = [(c["panel"], c["task"], c["repeat"], c["arm"])
             for c in freeze["schedule"]]
    assert len(set(pairs)) == len(pairs)
    for panel, tasks in (("evaluation", oracle.SPLITS["evaluation"]),
                         ("transfer", oracle.SPLITS["transfer"])):
        expect = {(freeze["freeze_id"], panel, t, r, a)
                  for t in tasks for r in freeze_mod.REPEATS
                  for a in freeze_mod.ARMS}
        assert freeze_mod.expected_pairs(freeze["schedule"], panel,
                                         freeze["freeze_id"]) == expect
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b"coord02-w-test", b"coord02-w-tamp"))
    assert freeze_mod.verify_freeze(path) == ["hash mismatch for %s"
                                                   % path.name]
    freeze2, path2 = _freeze(tmp_path, "coord02-w-test2")
    doc = json.loads(path2.read_bytes())
    del doc["budgets"]
    path2.write_bytes(
        (json.dumps(doc, sort_keys=True, indent=2) + "\n").encode())
    Path(str(path2) + ".sha256").write_text(
        hashlib.sha256(path2.read_bytes()).hexdigest() + "\n")
    assert freeze_mod.verify_freeze(path2) == ["missing-field budgets"]


def _dsn():
    dsn = os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn:
        pytest.skip("SETTLEMENT_TEST_DSN is not configured")
    return dsn


def test_freeze_pg_anchor():
    dsn = _dsn()
    from settlement import db

    freeze = freeze_mod.build_freeze("coord02-w-anchor", source_sha="w-base")
    manifest_digest = freeze["corpus"]["manifest_digest"]
    table = "coord02_w_anchor"
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS %s" % table)
            cur.execute("CREATE TABLE %s (freeze_id TEXT PRIMARY KEY, "
                        "manifest_digest TEXT NOT NULL)" % table)
            cur.execute("INSERT INTO %s VALUES (%%s, %%s)"
                        % table, ("coord02-w-anchor", manifest_digest))
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT manifest_digest FROM %s WHERE freeze_id = %%s"
                        % table, ("coord02-w-anchor",))
            row = cur.fetchone()
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("DROP TABLE %s" % table)
        conn.commit()
    assert row[0] == manifest_digest


def _eval_evidence(tmp_path: Path, freeze: dict) -> Path:
    root = tmp_path / "evidence"
    for task in oracle.SPLITS["evaluation"]:
        for repeat in freeze_mod.REPEATS:
            for arm in freeze_mod.ARMS:
                checker.make_record(freeze, root, panel="evaluation",
                                    task=task, repeat=repeat, arm=arm,
                                    kind="valid")
    return root


@pytest.fixture(scope="module")
def frozen_eval(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("coord02-evidence")
    freeze = freeze_mod.build_freeze("coord02-w-eval", source_sha="w-base")
    freeze_path = freeze_mod.write_freeze(tmp_path / "freeze.json", freeze)
    root = _eval_evidence(tmp_path, freeze)
    return {"freeze": freeze, "freeze_path": freeze_path, "root": root}


def test_checker_accepts_clean_evidence(frozen_eval):
    report = checker.check_evidence(frozen_eval["root"],
                                    frozen_eval["freeze_path"],
                                    panels=("evaluation",))
    assert report["clean"], report["problems"]
    assert report["records"] == 12 * 4 * 2
    assert report["summary"]["evaluation/S"]["solved"] == 12 * 2


def _copy_evidence(src: Path, dest: Path) -> Path:
    shutil.copytree(src, dest, dirs_exist_ok=True)
    return dest


def _record_path(root: Path, freeze_id: str, panel: str, arm: str,
                 task: str, repeat: int) -> Path:
    return root / "episodes" / ("%s-%s-%s-%s-r%d.json"
                                % (freeze_id, panel, arm, task, repeat))


def _load_record(path: Path) -> dict:
    return json.loads(path.read_text())


def _save_record(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record, indent=2) + "\n")


def test_checker_detects_tamper_classes(frozen_eval, tmp_path):
    freeze_id = frozen_eval["freeze"]["freeze_id"]
    cases = {
        "missing-pair": ("delete", None),
        "wrong-procedure-digest": ("procedure_digest", "deadbeef"),
        "wrong-input-digest": ("input_digest", "0" * 64),
        "unattributed-cost": ("receipts", []),
        "omitted-cost-model_calls": ("drop-cost", "model_calls"),
        "ceiling-breach-model_calls": ("cost", ("model_calls", 999)),
        "validity-override": ("protected-failed", 1),
        "unquoted-failure": ("outcome-failure-noquotes", None),
        "unfrozen-success": ("frozen_digest", ""),
    }
    first = {"task": "c02-t03", "repeat": 1, "arm": "S"}
    for name, (field, value) in cases.items():
        root = _copy_evidence(frozen_eval["root"], tmp_path / name)
        path = _record_path(root, freeze_id, "evaluation", first["arm"],
                            first["task"], first["repeat"])
        record = _load_record(path)
        if field == "delete":
            path.unlink()
        elif field == "drop-cost":
            del record["costs"][value]
            _save_record(path, record)
        elif field == "cost":
            record["costs"][value[0]] = value[1]
            _save_record(path, record)
        elif field == "protected-failed":
            record["protected"]["failed"] = value
            _save_record(path, record)
        elif field == "outcome-failure-noquotes":
            record["outcome"] = "failure"
            record["failures"] = []
            record["frozen_digest"] = ""
            _save_record(path, record)
        else:
            record[field] = value
            _save_record(path, record)
        report = checker.check_evidence(root, frozen_eval["freeze_path"],
                                        panels=("evaluation",))
        assert not report["clean"]
        assert any(p.startswith(name) for p in report["problems"]), \
            (name, report["problems"])


def test_checker_detects_structural_tamper(frozen_eval, tmp_path):
    freeze_id = frozen_eval["freeze"]["freeze_id"]
    root = _copy_evidence(frozen_eval["root"], tmp_path / "dup")
    src = _record_path(root, freeze_id, "evaluation", "S", "c02-t03", 1)
    shutil.copy(src, root / "episodes" / "copy.json")
    report = checker.check_evidence(root, frozen_eval["freeze_path"],
                                    panels=("evaluation",))
    assert any(p.startswith("duplicate-pair") for p in report["problems"])

    root = _copy_evidence(frozen_eval["root"], tmp_path / "xpanel")
    record = _load_record(_record_path(root, freeze_id, "evaluation", "S",
                                       "c02-t03", 1))
    record["panel"] = "transfer"
    _save_record(_record_path(root, freeze_id, "transfer", "S", "c02-t03", 1),
                 record)
    report = checker.check_evidence(root, frozen_eval["freeze_path"],
                                    panels=("evaluation",))
    assert any(p.startswith("cross-panel-collision")
               for p in report["problems"]), report["problems"]

    root = _copy_evidence(frozen_eval["root"], tmp_path / "reuse")
    first = _load_record(_record_path(root, freeze_id, "evaluation", "S",
                                      "c02-t03", 1))
    second_path = _record_path(root, freeze_id, "evaluation", "A",
                               "c02-t03", 1)
    second = _load_record(second_path)
    second["receipts"] = list(first["receipts"])
    _save_record(second_path, second)
    report = checker.check_evidence(root, frozen_eval["freeze_path"],
                                    panels=("evaluation",))
    assert any(p.startswith("receipt-reuse") for p in report["problems"])

    root = _copy_evidence(frozen_eval["root"], tmp_path / "verdict")
    rec_path = _record_path(root, freeze_id, "evaluation", "S", "c02-t03", 1)
    record = _load_record(rec_path)
    cand_file = root / "candidates" / record["candidate_digest"] / "src"
    (cand_file / "names.py").write_text("def transform(items):\n"
                                        "    return list(items)\n")
    report = checker.check_evidence(root, frozen_eval["freeze_path"],
                                    panels=("evaluation",))
    assert any(p.startswith("verdict-mismatch") for p in report["problems"]), \
        report["problems"]

    root = _copy_evidence(frozen_eval["root"], tmp_path / "diverge")
    for arm in ("S", "A"):
        path = _record_path(root, freeze_id, "evaluation", arm, "c02-t03", 1)
        record = _load_record(path)
        if arm == "A":
            record["input_digest"] = "1" * 64
            _save_record(path, record)
    report = checker.check_evidence(root, frozen_eval["freeze_path"],
                                    panels=("evaluation",))
    assert any(p.startswith("cross-arm-input-divergence")
               for p in report["problems"])


def test_checker_db_crosscheck(tmp_path):
    dsn = _dsn()
    from settlement import db

    freeze = freeze_mod.build_freeze("coord02-w-db", source_sha="w-base")
    root = tmp_path / "db-evidence"
    records = [checker.make_record(freeze, root, panel="development",
                                   task=task, repeat=repeat, arm=arm,
                                   kind="valid")
               for task in oracle.SPLITS["development"]
               for repeat in freeze_mod.REPEATS
               for arm in freeze_mod.ARMS]
    table = "coord02_w_receipts"
    anchored = [r for record in records for r in record["receipts"]]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS %s" % table)
            cur.execute("CREATE TABLE %s (receipt_identity TEXT PRIMARY KEY)"
                        % table)
            for ref in anchored:
                cur.execute("INSERT INTO %s VALUES (%%s)" % table, (ref,))
        conn.commit()
    try:
        freeze_path = freeze_mod.write_freeze(tmp_path / "db-freeze.json",
                                              freeze)
        report = checker.check_evidence(root, freeze_path, dsn=dsn,
                                        receipt_table=table,
                                        panels=("development",))
        assert report["clean"], report["problems"]
        with db.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM %s WHERE receipt_identity = %%s"
                            % table, (anchored[0],))
            conn.commit()
        report = checker.check_evidence(root, freeze_path, dsn=dsn,
                                        receipt_table=table,
                                        panels=("development",))
        assert any(p.startswith("altered-receipt") for p in report["problems"])
    finally:
        with db.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS %s" % table)
            conn.commit()


def test_baseline_feasibility_on_development(tmp_path):
    solved = 0
    started = time.monotonic()
    for task_id in DEV:
        result = _combined(task_id, "valid", tmp_path)
        if result["failed"] == 0:
            solved += 1
    elapsed = time.monotonic() - started
    assert solved == len(DEV)
    assert elapsed < 300
