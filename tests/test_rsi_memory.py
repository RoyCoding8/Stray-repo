from __future__ import annotations

import pytest
from test_rsi_investigate import _scenario

from rsi import experience, investigate, memory
from rsi.investigation import export
from settlement.common import SettlementError, StaleRevision


def test_consolidation_keeps_roots_and_withdrawn_ancestry_out_of_current_memory(
    migrated_db, tmp_path
):
    run = _scenario(migrated_db, tmp_path, "p02-memory-lineage", "repair-after-feedback")
    investigation_id = run["state"]["investigation_id"]
    dsn = run["dsn"]
    roots = run["roots"]
    first = investigate.step(dsn, run["agent"], run["checker"], investigation_id, **roots)
    assert first["last_observation"]["passed"] is False
    second = investigate.step(dsn, run["agent"], run["checker"], investigation_id, **roots)
    assert second["last_observation"]["passed"] is True
    experience.capture_investigation(
        dsn, investigation_id, artifacts_root=roots["artifacts_root"])
    observations = export(dsn, investigation_id)["observations"]
    opposition, support = (item["id"] for item in observations)

    for claim_id in ("memory-left", "memory-right"):
        memory.revise(
            dsn, claim_id=claim_id, expected_version=0,
            text="repair add after evidence", scope={"domain": "task"},
            status="challenged", support=(support,), opposition=(opposition,),
            artifacts_root=roots["artifacts_root"],
        )
    merged = memory.revise(
        dsn, claim_id="memory-merged", expected_version=0,
        text="consolidated method after review", scope={"domain": "task"},
        status="challenged", derived_from=(("memory-left", 1), ("memory-right", 1)),
        supersedes=(("memory-left", 1), ("memory-right", 1)),
        artifacts_root=roots["artifacts_root"],
    )

    old_text = memory.query(
        dsn, purpose="repair add evidence", investigation_id=investigation_id,
        scope={"domain": "task"}, artifacts_root=roots["artifacts_root"],
    )
    assert old_text["claims"] == []

    before_withdrawal = memory.query(
        dsn, purpose="consolidated method after review", investigation_id=investigation_id,
        scope={"domain": "task"}, artifacts_root=roots["artifacts_root"],
    )
    assert before_withdrawal["revision"] == merged["revision"]
    claim, = before_withdrawal["claims"]
    assert claim["claim_id"] == "memory-merged"
    assert claim["support"] == [support]
    assert claim["opposition"] == [opposition]
    assert {item["observation_id"] for item in before_withdrawal["observations"]} == {
        support, opposition,
    }

    memory.revise(
        dsn, claim_id="memory-narrow", expected_version=0,
        text="case-specific method", scope={"domain": "task", "case": "changed-input"},
        status="challenged", derived_from=(("memory-left", 1),),
        artifacts_root=roots["artifacts_root"],
    )
    with pytest.raises(SettlementError, match="cannot broaden"):
        memory.revise(
            dsn, claim_id="memory-narrow", expected_version=1,
            text="case-specific method", scope={"domain": "task"},
            status="challenged", artifacts_root=roots["artifacts_root"],
        )

    memory.revise(
        dsn, claim_id="memory-left", expected_version=1,
        text="repair add after evidence", scope={"domain": "task"},
        status="withdrawn", artifacts_root=roots["artifacts_root"],
    )
    current = memory.query(
        dsn, purpose="consolidated method after review", investigation_id=investigation_id,
        scope={"domain": "task"}, artifacts_root=roots["artifacts_root"],
    )
    historical = memory.query(
        dsn, purpose="consolidated method after review", investigation_id=investigation_id,
        scope={"domain": "task"}, artifacts_root=roots["artifacts_root"],
        revision=merged["revision"],
    )
    left_history = memory.history(
        dsn, "memory-left", artifacts_root=roots["artifacts_root"])

    assert current["claims"] == []
    assert [item["claim_id"] for item in historical["claims"]] == ["memory-merged"]
    assert [item["status"] for item in left_history] == ["challenged", "withdrawn"]
    assert left_history[-1]["opposition"] == [opposition]
    with pytest.raises(StaleRevision):
        memory.revise(
            dsn, claim_id="memory-left", expected_version=1,
            text="repair add after evidence", scope={"domain": "task"},
            status="withdrawn", artifacts_root=roots["artifacts_root"],
        )


def test_checked_original_experience_is_searchable_without_claims(
    migrated_db, tmp_path, monkeypatch
):
    run = _scenario(migrated_db, tmp_path, "p02-memory-raw-baseline", "repair-after-feedback")
    investigation_id = run["state"]["investigation_id"]
    dsn = run["dsn"]
    roots = run["roots"]
    first = investigate.step(dsn, run["agent"], run["checker"], investigation_id, **roots)
    second = investigate.step(dsn, run["agent"], run["checker"], investigation_id, **roots)
    assert first["last_observation"]["passed"] is False
    assert second["last_observation"]["passed"] is True
    experience.capture_investigation(dsn, investigation_id, artifacts_root=roots["artifacts_root"])

    originals = export(dsn, investigation_id)["observations"]
    expected = {item["id"]: item["content"]["passed"] for item in originals}
    assert len(expected) == 2
    assert set(expected.values()) == {False, True}

    for view in ("structured", "raw-history"):
        result = memory.query(
            dsn, purpose="Implement add(2, 3) so it returns 5.",
            investigation_id=investigation_id, scope={"domain": "task"},
            artifacts_root=roots["artifacts_root"], view=view,
        )
        assert result["claims"] == []
        assert {item["observation_id"]: item["content"]["passed"]
                for item in result["observations"]} == expected
        assert {item["content"]["task_instruction"] for item in result["observations"]} == {
            "Implement add(2, 3) so it returns 5."
        }

        exact = memory.query(
            dsn, purpose="unrelated explicit identity", investigation_id=investigation_id,
            scope={"domain": "task"}, artifacts_root=roots["artifacts_root"],
            view=view, observation_ids=(min(expected),),
        )
        assert [item["observation_id"] for item in exact["observations"]] == [min(expected)]

        absent = memory.query(
            dsn, purpose="Implement add(2, 3) so it returns 5.",
            investigation_id=investigation_id, scope={"domain": "task"},
            artifacts_root=roots["artifacts_root"], view=view,
            claim_ids=("absent-memory-claim",),
        )
        assert absent["observations"] == []
        assert absent["missing_information"] == [{
            "claim_id": "absent-memory-claim",
            "reason": "claim is unavailable at requested revision",
        }]

    monkeypatch.setattr(memory, "_MAX_QUERY_IDS", 1)
    bounded = memory.query(
        dsn, purpose="Implement add(2, 3) so it returns 5.",
        investigation_id=investigation_id, scope={"domain": "task"},
        artifacts_root=roots["artifacts_root"], view="raw-history",
    )
    assert len(bounded["observations"]) == 1
    assert bounded["missing_information"] == [{
        "reason": "experience search reached its bounded candidate limit",
    }]


def test_uncertain_experience_is_preserved_but_cannot_support_a_claim(migrated_db, tmp_path):
    run = _scenario(
        migrated_db, tmp_path, "p02-memory-refusal", "pass-first", token_authorized=1_000,
    )
    dsn = run["dsn"]
    roots = run["roots"]
    investigate.step(dsn, run["agent"], run["checker"], "p02-memory-refusal", **roots)
    experience.capture_investigation(
        dsn, "p02-memory-refusal", artifacts_root=roots["artifacts_root"])
    observation, = export(dsn, "p02-memory-refusal")["observations"]

    with pytest.raises(SettlementError, match="checked original evidence"):
        memory.revise(
            dsn, claim_id="memory-refusal", expected_version=0,
            text="the attempt is known to pass", scope={"domain": "task"},
            status="supported", support=(observation["id"],),
            artifacts_root=roots["artifacts_root"],
        )

    stored = memory.revise(
        dsn, claim_id="memory-refusal", expected_version=0,
        text="the attempt has an unresolved resource refusal", scope={"domain": "task"},
        status="untested", support=(observation["id"],),
        artifacts_root=roots["artifacts_root"],
    )
    result = memory.query(
        dsn, purpose="unresolved resource refusal", investigation_id="p02-memory-refusal",
        scope={"domain": "task"}, artifacts_root=roots["artifacts_root"],
        revision=stored["revision"],
    )
    claim, = result["claims"]
    source, = result["observations"]
    assert claim["status"] == "untested"
    assert claim["support"] == [observation["id"]]
    assert source["observation_id"] == observation["id"]
    assert source["content"]["passed"] is None
