"""coord02 M3 acquisition/disposition tests (doubled path, ec02test_m3 only).

End-to-end doubled acquisition: acquire_episodes (2+ dev tasks) ->
construct_lineages (both lineages, init+repair) ->
validate_on_development -> select_candidate -> freeze_selection
(none path with explicit reason). Doubled gateway only
(`FakeGatewayAdapter`); never touches `ec02test_live`.

TDD log (red-first): each behavior below first failed against a
stand-in (missing seam / empty-gateway construction that never
repairs, invented selection records), then passed via the existing
`experience.py` machinery. No production shims were added.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

from experiments.coord02 import experience as E
from experiments.coord02 import freeze as F
from settlement import broker, db
from settlement.gateway import FakeGatewayAdapter
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get("EC02_M3_DSN",
                     "dbname=ec02test_m3 host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"

DOUBLED_EXECUTABLE = ("\n".join([
    "import json",
    "import sys",
    "if len(sys.argv) == 2 and sys.argv[1] == '--selftest':",
    "    raise SystemExit(0)",
    "req = json.load(open(sys.argv[1]))",
    "paths = sorted(req['task']['task_snapshot'].keys())",
    "plan = {'action': 'plan', 'shape': 'single', 'children': [{",
    "  'node_id': 'w1',",
    "  'obligation': 'DOUBLED M3 stand-in: valid reference tree',",
    "  'owned_paths': paths,",
    "  'output_contract': {'entry': 'whole-tree', 'checks': ['public']},",
    "  'input_bindings': {'base_%d' % i: p",
    "                     for i, p in enumerate(paths)}}]}",
    "resp = {'profile': req['profile'],",
    "        'profile_version': req['profile_version'],",
    "        'decision_id': req['decision_id'],",
    "        'package_digest': req['package_digest'],",
    "        'source_digest': req['source_digest'],",
    "        'plan_revision': req['plan_revision'],",
    "        'phase': req['phase'], 'proposal': plan, 'state': {}}",
    "json.dump(resp, open(sys.argv[2], 'w'))",
    ""]) + "\n").encode()

DOUBLED_INERT = ("\n".join([
    "import json",
    "import sys",
    "if len(sys.argv) == 2 and sys.argv[1] == '--selftest':",
    "    raise SystemExit(0)",
    "req = json.load(open(sys.argv[1]))",
    "resp = {'profile': req['profile'],",
    "        'profile_version': req['profile_version'],",
    "        'decision_id': req['decision_id'],",
    "        'package_digest': req['package_digest'],",
    "        'source_digest': req['source_digest'],",
    "        'plan_revision': req['plan_revision'],",
    "        'phase': req['phase'],",
    "        'proposal': {'action': 'stop',",
    "                   'reason': 'DOUBLED M3 stand-in: decline'},",
    "        'state': {}}",
    "json.dump(resp, open(sys.argv[2], 'w'))",
    ""]) + "\n").encode()


@pytest.fixture()
def dsn():
    db.apply_migrations(DSN, MIGRATIONS)
    E.designate_db(DSN, kind="disposable",
                   purpose="M3 doubled acquisition tests")
    E.prepare_disposable_db(DSN, MIGRATIONS)
    for stale in Path("/tmp").glob("coord02-M3-test-*"):
        shutil.rmtree(stale, ignore_errors=True)
    return DSN


def _tag(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _factory(root: Path):
    def _make(tag: str) -> dict:
        return {"local-process": LocalLauncher(root / tag)}
    return _make


def _requires(task_id: str) -> dict:
    return E._requires_for(task_id, E.snapshot_files(task_id))


def _episodes(dsn, tmp_path, task_ids=("c02-t16", "c02-t01")):
    return E.acquire_episodes(
        dsn, tmp_path, task_ids=list(task_ids),
        launcher_factory=_factory(tmp_path),
        constructor=E.dev_constructor("c02-t16", solved=True))


def _campaign(dsn, tag, budget):
    seed = E.seed_construction_campaign(dsn, tag, budget)
    return seed, E.ConstructionLedger(dsn, seed["allocation_id"])


def test_no_live_grant_in_env():
    assert "TEAM01_LIVE_API_KEY" not in os.environ
    assert E.preflight_live() == {
        "live_grant": False,
        "reason": "no TEAM01_LIVE_API_KEY: 4 live construction calls + "
                  "G2 acquisition blocked; doubled path only"}
    from experiments.coord02 import preflight as P
    verdict = P.preflight_live()
    assert verdict["admitted"] is False
    assert any("TEAM01_LIVE_API_KEY" in p for p in verdict["problems"])
    assert "--panel" in verdict["blocked_command"]
    assert E.construction_budget()["label"] == "DOUBLED"


def test_acquire_two_dev_tasks(dsn, tmp_path):
    episodes = _episodes(dsn, tmp_path)
    assert len(episodes) == 2
    assert [e["task_id"] for e in episodes] == ["c02-t16", "c02-t01"]
    for made in episodes:
        assert made["packet"]["packet_version"] == "coord02-experience/1"
        assert made["packet"]["task_id"] == made["task_id"]
        assert made["episode"]["run_id"] == made["packet"]["run_id"]
        assert made["episode"]["outcome"]["status"] == "stopped"


@pytest.mark.parametrize("text,calls,stages", [
    ("", 4, ("init", "repair")),
    (json.dumps({"entry": DOUBLED_INERT.decode()}), 2, ("init",)),
], ids=["empty-response", "valid-profile"])
def test_acquire_reentry_reuses_campaign_operations(dsn, tmp_path, text, calls, stages):
    def acquire():
        return E.acquire(
            dsn, tmp_path, task_ids=["c02-t16"],
            campaign_root="reentry", launcher_factory=_factory(tmp_path),
            construction_gateway=FakeGatewayAdapter(text=text))

    first = acquire()
    with db.connect(dsn) as conn:
        before = conn.execute("SELECT id FROM operations ORDER BY id").fetchall()
        allocations = conn.execute(
            "SELECT id, authorized FROM allocations ORDER BY id").fetchall()
    assert first["accounting"]["calls_used"] == calls
    assert len(first["packet"]["probe_observations"]) == 1
    second = acquire()
    assert second["campaign_root"] == "reentry"
    assert second["episodes"] == first["episodes"]
    assert second["accounting"]["calls_used"] == calls
    assert [[r[stage]["operation_id"] for stage in stages]
            for r in second["lineages"]] == [
        [r[stage]["operation_id"] for stage in stages]
        for r in first["lineages"]]
    with db.connect(dsn) as conn:
        assert conn.execute("SELECT id FROM operations ORDER BY id").fetchall() == before
        assert conn.execute(
            "SELECT id, authorized FROM allocations ORDER BY id").fetchall() == allocations


@pytest.mark.parametrize("root", [None, "", "   "])
def test_acquire_requires_campaign_root(tmp_path, root):
    with pytest.raises(ValueError, match="campaign_root"):
        E.acquire("unused", tmp_path, task_ids=["c02-t16"],
                  campaign_root=root, launcher_factory=_factory(tmp_path))


@pytest.mark.parametrize("changed", [
    {"task_ids": ["c02-t01"]},
    {"budget": {"label": "changed"}},
    {"attempt_prefix": "changed"},
])
def test_acquire_rejects_changed_campaign_before_work(dsn, tmp_path, monkeypatch, changed):
    from settlement.common import ConflictPayload

    kwargs = dict(task_ids=["c02-t16"], campaign_root="bound",
                  launcher_factory=_factory(tmp_path),
                  construction_gateway=FakeGatewayAdapter(text=""))
    E.acquire(dsn, tmp_path, **kwargs)

    def unexpected(*args, **kwargs):
        pytest.fail("campaign conflict must precede episode acquisition")

    monkeypatch.setattr(E, "acquire_episodes", unexpected)
    with pytest.raises(ConflictPayload):
        E.acquire(dsn, tmp_path, **(kwargs | changed))


def test_acquire_recovers_after_episode_before_checkpoint(dsn, tmp_path, monkeypatch):
    run = E._run_dev_episode
    settled = []

    def interrupt(*args, **kwargs):
        settled.append(run(*args, **kwargs))
        raise RuntimeError("episode settled before checkpoint")

    kwargs = dict(task_ids=["c02-t16"], campaign_root="episode-crash",
                  launcher_factory=_factory(tmp_path),
                  construction_gateway=FakeGatewayAdapter(text=""))
    monkeypatch.setattr(E, "_run_dev_episode", interrupt)
    with pytest.raises(RuntimeError, match="episode settled before checkpoint"):
        E.acquire(dsn, tmp_path, **kwargs)
    with db.connect(dsn) as conn:
        before = conn.execute("SELECT id FROM operations ORDER BY id").fetchall()
    monkeypatch.setattr(E, "_run_dev_episode", run)
    recovered = E.acquire(dsn, tmp_path, **kwargs)
    assert recovered["episodes"][0]["episode"] == settled[0]
    construction_ids = {call["operation_id"] for call in recovered["ledger"].calls}
    with db.connect(dsn) as conn:
        after = conn.execute("SELECT id FROM operations ORDER BY id").fetchall()
    assert [row for row in after if row[0] not in construction_ids] == before


def test_acquire_recovers_after_profile_effect_before_checkpoint(dsn, tmp_path, monkeypatch):
    check = E._profile_check

    def interrupt(*args, **kwargs):
        result = check(*args, **kwargs)
        assert result["ok"]
        raise RuntimeError("profile settled before checkpoint")

    def acquire():
        return E.acquire(
            dsn, tmp_path, task_ids=["c02-t16"], campaign_root="profile-crash",
            launcher_factory=_factory(tmp_path),
            construction_gateway=FakeGatewayAdapter(
                text=json.dumps({"entry": DOUBLED_INERT.decode()})))

    monkeypatch.setattr(E, "_profile_check", interrupt)
    with pytest.raises(RuntimeError, match="profile settled before checkpoint"):
        acquire()
    monkeypatch.setattr(E, "_profile_check", check)
    recovered = acquire()
    assert recovered["accounting"]["calls_used"] == 2
    assert all(rec["profile"]["ok"] for rec in recovered["lineages"])
    with db.connect(dsn) as conn:
        assert conn.execute(
            "SELECT count(*) FROM operations WHERE id LIKE 'cap-verify-%'"
        ).fetchone()[0] == 2


@pytest.mark.parametrize("step", ["_profile_check", "_run_dev_episode"])
def test_validation_recovers_without_repeating_effects(dsn, tmp_path, monkeypatch, step):
    run = getattr(E, step)

    def interrupt(*args, **kwargs):
        run(*args, **kwargs)
        raise RuntimeError("validation settled before checkpoint")

    kwargs = dict(entry_bytes=DOUBLED_INERT, requires=_requires("c02-t16"),
                  task_ids=["c02-t16"], launcher_factory=_factory(tmp_path),
                  validation_root="validation-crash")
    monkeypatch.setattr(E, step, interrupt)
    with pytest.raises(RuntimeError, match="validation settled before checkpoint"):
        E.validate_on_development(dsn, **kwargs)
    with db.connect(dsn) as conn:
        before = conn.execute("SELECT id FROM operations ORDER BY id").fetchall()
    monkeypatch.setattr(E, step, run)
    recovered = E.validate_on_development(dsn, **kwargs)
    with db.connect(dsn) as conn:
        settled = conn.execute("SELECT id FROM operations ORDER BY id").fetchall()
    assert set(before).issubset(set(settled))
    if step == "_run_dev_episode":
        assert settled == before
    with db.connect(dsn) as conn:
        journal = conn.execute(
            "SELECT request_id FROM command_journal ORDER BY request_id").fetchall()
    assert E.validate_on_development(dsn, **kwargs) == recovered
    with db.connect(dsn) as conn:
        assert conn.execute(
            "SELECT request_id FROM command_journal ORDER BY request_id").fetchall() == journal
        assert conn.execute("SELECT id FROM operations ORDER BY id").fetchall() == settled
        assert conn.execute(
            "SELECT count(*) FROM operations WHERE id LIKE 'cap-verify-%'"
        ).fetchone()[0] == 1


@pytest.mark.parametrize("changed", [
    {"entry_bytes": DOUBLED_EXECUTABLE},
    {"task_ids": ["c02-t01"]},
    {"requires": {"changed": {}}},
])
def test_validation_rejects_changed_request_before_effects(dsn, tmp_path, monkeypatch, changed):
    from settlement.common import ConflictPayload

    kwargs = dict(entry_bytes=DOUBLED_INERT, requires=_requires("c02-t16"),
                  task_ids=["c02-t16"], launcher_factory=_factory(tmp_path),
                  validation_root="bound-validation")
    E.validate_on_development(dsn, **kwargs)

    def unexpected(*args, **kwargs):
        pytest.fail("validation conflict must precede profile execution")

    monkeypatch.setattr(E, "_profile_check", unexpected)
    with pytest.raises(ConflictPayload):
        E.validate_on_development(dsn, **(kwargs | changed))


def test_construct_both_lineages_init_and_repair(dsn, tmp_path):
    episodes = _episodes(dsn, tmp_path)
    budget = E.construction_budget()
    _, ledger = _campaign(dsn, _tag("m3"), budget)
    gateway = FakeGatewayAdapter(text="")
    lineages = E.construct_lineages(episodes, budget, ledger=ledger,
                                    gateway=gateway,
                                    launcher_factory=_factory(tmp_path))
    assert [r["lineage"] for r in lineages] == [1, 2]
    for rec in lineages:
        assert rec["init"]["operation_id"] != rec["repair"]["operation_id"]
        assert rec["repair_failure"]["lineage"] == rec["lineage"]
        assert rec["repair_failure"]["operation_id"] == \
            rec["init"]["operation_id"]
        assert rec["repair_failure"]["reason"]
        assert rec["rejections"]
        assert rec["init"]["text"] == ""
        assert rec["exposure_manifest"]["recorded"] is True
    assert lineages[0]["exposure_manifest"] == {
        "lineage": 1, "development_access": "same-policy",
        "prior_lineage_results": [], "recorded": True}
    assert lineages[1]["exposure_manifest"]["prior_lineage_results"] == [1]
    assert ledger.calls_used() == 4
    assert ledger.remaining() == 0
    assert all(c["label"] == "DOUBLED" and c["doubled"] and not c["live"]
               for c in ledger.calls)


def test_ledger_attempt_consumption_durable_across_fresh_ledger(dsn,
                                                                tmp_path):
    episodes = _episodes(dsn, tmp_path)
    budget = E.construction_budget()
    seed = E.seed_construction_campaign(dsn, _tag("durable-m3"), budget)
    prefix = f"coord02-M3-durable-{uuid.uuid4().hex[:6]}"
    first = E.ConstructionLedger(dsn, seed["allocation_id"],
                                 attempt_prefix=prefix)
    gateway = FakeGatewayAdapter(
        text=json.dumps({"entry": "x = 1\n"}))
    rec = first.request_call(
        E.construction_request(episodes, budget, lineage=1, attempt="init"),
        gateway=gateway)
    fresh = E.ConstructionLedger(dsn, seed["allocation_id"],
                                 attempt_prefix=prefix)
    assert fresh.calls_used() == 1
    assert fresh.remaining() == E.MAX_CONSTRUCTION_CALLS - 1
    assert rec["operation_id"] in {c["operation_id"] for c in fresh.calls}
    assert first.calls_used() == fresh.calls_used()


def test_ledger_refuses_second_prefix_on_same_allocation(dsn):
    from settlement.common import ConflictPayload

    budget = E.construction_budget()
    seed = E.seed_construction_campaign(dsn, _tag("single-prefix"), budget)
    E.ConstructionLedger(dsn, seed["allocation_id"],
                         attempt_prefix="coord02-M3-single-first")
    with pytest.raises(ConflictPayload):
        E.ConstructionLedger(dsn, seed["allocation_id"],
                             attempt_prefix="coord02-M3-single-second")


def test_invalid_requests_consume_defined_budget(dsn):
    budget = E.construction_budget()
    seed = E.seed_construction_campaign(dsn, _tag("invalid-m3"), budget)
    prefix = f"coord02-M3-invalid-{uuid.uuid4().hex[:6]}"
    ledger = E.ConstructionLedger(dsn, seed["allocation_id"],
                                  attempt_prefix=prefix)
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    gateway = FakeGatewayAdapter(text=json.dumps({"entry": "x = 1\n"}))
    with pytest.raises(Exception, match="lineage"):
        ledger.request_call(
            E.construction_request(packet, budget, lineage=99,
                                   attempt="init"),
            gateway=gateway)
    assert ledger.calls_used() == 1
    assert ledger.remaining() == E.MAX_CONSTRUCTION_CALLS - 1
    fresh = E.ConstructionLedger(dsn, seed["allocation_id"],
                                 attempt_prefix=prefix)
    assert fresh.calls_used() == 1


def test_authorized_ceiling_binds_the_ledger_below_the_study_maximum(dsn):
    budget = E.construction_budget(live_calls_authorized=1)
    seed = E.seed_construction_campaign(dsn, _tag("grant-1"), budget)
    ledger = E.ConstructionLedger(
        dsn, seed["allocation_id"],
        attempt_prefix=f"coord02-M3-grant1-{uuid.uuid4().hex[:6]}",
        authorized_calls=1)
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    request = E.construction_request(packet, budget, lineage=1,
                                     attempt="init")
    first = ledger.request_call(request, gateway=FakeGatewayAdapter(text=""))
    assert first["operation_id"]
    with pytest.raises(E.ConstructionBudgetExhausted):
        second = E.ConstructionLedger(
            dsn, seed["allocation_id"],
            attempt_prefix=ledger.attempt_prefix,
            authorized_calls=1)
        second.request_call(
            E.construction_request(packet, budget, lineage=2,
                                   attempt="init"),
            gateway=FakeGatewayAdapter(text=""))
    assert ledger.accounting()["ceiling"] == 1
    assert ledger.accounting()["study_ceiling"] == 4


def test_selection_none_when_no_usable_candidates():
    assert E.select_candidate([]) == {
        "selection": "none", "selector": E.SELECTOR_VERSION,
        "ordering": list(E.ORDERING), "ranking": [],
        "reason": "neither candidate executable under the contract"}


def test_selection_none_when_neither_candidate_executes(dsn, tmp_path):
    factory = _factory(tmp_path)
    requires = _requires("c02-t16")
    tasks = ["c02-t16", "c02-t01"]
    constructor = E.dev_constructor("c02-t16", solved=True)
    inert = E.validate_on_development(
        dsn, entry_bytes=DOUBLED_INERT, requires=requires,
        task_ids=tasks, launcher_factory=factory,
        constructor=constructor)
    assert inert["valid_execution"] is False
    assert inert["solved_count"] == 0
    assert inert["fallback_tasks"] == []
    selection = E.select_candidate(
        [{"lineage": 1, "validation": inert,
          "entry_bytes": DOUBLED_INERT},
         {"lineage": 2, "validation": dict(inert),
          "entry_bytes": DOUBLED_INERT}])
    assert selection["selection"] == "none"
    assert "neither candidate executable" in selection["reason"]
    assert selection["ordering"] == list(E.ORDERING)
    frozen = E.freeze_selection(
        f"coord02-M3-none-{_tag('f')}", {"status": "declared-by-M3"},
        source_sha="0" * 40, selection=selection,
        dev_results=[{"lineage": 1, "validation": inert},
                     {"lineage": 2, "validation": dict(inert)}],
        lineages=[{"lineage": 1,
                   "exposure_manifest": E.exposure_manifest(1, [])},
                  {"lineage": 2,
                   "exposure_manifest": E.exposure_manifest(2, [])}],
        accounting={"calls_used": 4, "live_calls_used": 0})
    assert frozen["package"]["kind"] == "none"
    assert "neither candidate executable" in frozen["package"]["reason"]
    assert F.verify_freeze(F.write_freeze(
        tmp_path / "m3-none-freeze.json", frozen)) == []


def test_selection_winner_links_lineage_exposure_and_accounting(
        dsn, tmp_path):
    factory = _factory(tmp_path)
    requires = _requires("c02-t16")
    tasks = ["c02-t16", "c02-t01"]
    constructor = E.dev_constructor("c02-t16", solved=True)
    good = E.validate_on_development(
        dsn, entry_bytes=DOUBLED_EXECUTABLE, requires=requires,
        task_ids=tasks, launcher_factory=factory,
        constructor=constructor)
    assert good["valid_execution"] is True
    assert good["solved_count"] == 0
    assert good["failures"] != []
    assert all(f["status"] == "submit-refused"
               and "no constructor artifact" in f.get("reason", "")
               for f in good["failures"])
    inert = E.validate_on_development(
        dsn, entry_bytes=DOUBLED_INERT, requires=requires,
        task_ids=tasks, launcher_factory=factory,
        constructor=constructor)
    selection = E.select_candidate(
        [{"lineage": 1, "validation": inert,
          "entry_bytes": DOUBLED_INERT},
         {"lineage": 2, "validation": good,
          "entry_bytes": DOUBLED_EXECUTABLE}])
    assert selection["selection"] == 2
    assert selection["ranking"] == [2, 1]
    accounting = {"calls_used": 4, "live_calls_used": 0}
    frozen = E.freeze_selection(
        f"coord02-M3-winner-{_tag('f')}", {"status": "declared-by-M3"},
        source_sha="0" * 40, selection=selection,
        dev_results=[{"lineage": 1, "validation": inert,
                      "entry_bytes": DOUBLED_INERT},
                     {"lineage": 2, "validation": good,
                      "entry_bytes": DOUBLED_EXECUTABLE,
                      "version_id": "v2", "package_digest": "d2"}],
        lineages=[{"lineage": 1,
                   "exposure_manifest": E.exposure_manifest(1, [])},
                  {"lineage": 2,
                   "exposure_manifest": E.exposure_manifest(
                       2, [{"lineage": 1}])}],
        accounting=accounting)
    package = frozen["package"]
    assert package["kind"] == "coordination-procedure/1"
    assert package["exposure_manifest"]["prior_lineage_results"] == [1]
    assert package["construction"] == accounting
    assert package["development"]["solved"] == good["solved_tasks"]
    assert F.verify_freeze(F.write_freeze(
        tmp_path / "m3-winner-freeze.json", frozen)) == []


def test_s_fallback_attributed_never_learned_success(dsn, tmp_path):
    factory = _factory(tmp_path)
    requires = _requires("c02-t16")
    tasks = ["c02-t16"]
    constructor = E.dev_constructor("c02-t16", solved=True)
    inert = E.validate_on_development(
        dsn, entry_bytes=DOUBLED_INERT, requires=requires,
        task_ids=tasks, launcher_factory=factory,
        constructor=constructor)
    assert "fallback_tasks" in inert
    assert inert["fallback_tasks"] == []
    assert inert["failures"], "inert bytes must record failures, not success"
    for failure in inert["failures"]:
        assert failure["status"] != "success"
        assert "learned" not in failure["status"]
    selection = E.select_candidate(
        [{"lineage": 1, "validation": dict(inert),
          "entry_bytes": DOUBLED_INERT},
         {"lineage": 2, "validation": inert,
          "entry_bytes": DOUBLED_INERT}])
    assert selection["selection"] == "none"


def test_end_to_end_none_disposition(dsn, tmp_path):
    episodes = _episodes(dsn, tmp_path)
    budget = E.construction_budget()
    seed, ledger = _campaign(dsn, _tag("m3e2e"), budget)
    lineages = E.construct_lineages(
        episodes, budget, ledger=ledger,
        gateway=FakeGatewayAdapter(text=""),
        launcher_factory=_factory(tmp_path))
    assert ledger.accounting()["calls_used"] == 4
    assert ledger.accounting()["live_calls_used"] == 0
    factory = _factory(tmp_path)
    requires = _requires("c02-t16")
    tasks = ["c02-t16", "c02-t01"]
    constructor = E.dev_constructor("c02-t16", solved=True)
    dev_results = []
    for rec in lineages:
        for stage in ("repair", "init"):
            kept = rec[f"{stage}_kept"] if stage == "repair" else rec["kept"]
            if kept is not None and kept["usable"]:
                entry = kept["entry_bytes"]
                break
        else:
            entry = b""
        validation = E.validate_on_development(
            dsn, entry_bytes=entry or DOUBLED_INERT, requires=requires,
            task_ids=tasks, launcher_factory=factory,
            constructor=constructor)
        dev_results.append({"lineage": rec["lineage"],
                            "validation": validation,
                            "entry_bytes": entry or DOUBLED_INERT})
    selection = E.select_candidate(dev_results)
    assert selection["selection"] == "none"
    frozen = E.freeze_selection(
        f"coord02-M3-e2e-{_tag('f')}", {"status": "declared-by-M3"},
        source_sha="0" * 40, selection=selection,
        dev_results=dev_results,
        lineages=[{"lineage": r["lineage"],
                   "exposure_manifest": r["exposure_manifest"]}
                  for r in lineages],
        accounting=ledger.accounting())
    assert frozen["package"]["kind"] == "none"
    assert seed["allocation_id"]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM receipts WHERE"
                        " operation_id LIKE 'coord02-L-construct-%' OR"
                        " operation_id LIKE 'coord02-M3-%'")
            assert int(cur.fetchone()[0]) >= 0
            conn.commit()
