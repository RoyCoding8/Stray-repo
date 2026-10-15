from __future__ import annotations

from test_rsi_investigate import _scenario, _worker_calls

from rsi import investigate


def test_pinned_p01_revision_replays_its_observation_without_a_new_worker(
    migrated_db, tmp_path
):
    run = _scenario(migrated_db, tmp_path / "p01", "p05-replay", "repair-after-feedback")
    target_revision = run["state"]["revision"]

    checked_failure = investigate.step(
        run["dsn"], run["agent"], run["checker"], "p05-replay",
        target_revision=target_revision, **run["roots"]
    )
    before_replay = len(_worker_calls(run["worker_log"]))
    replayed = investigate.step(
        run["dsn"], run["agent"], run["checker"], "p05-replay",
        target_revision=target_revision, **run["roots"]
    )

    assert checked_failure["status"] == "ready"
    assert checked_failure["last_observation"]["passed"] is False
    assert replayed["revision"] == checked_failure["revision"]
    assert replayed["last_observation"] == checked_failure["last_observation"]
    assert len(_worker_calls(run["worker_log"])) == before_replay == 1

    completed = investigate.step(
        run["dsn"], run["agent"], run["checker"], "p05-replay", **run["roots"]
    )
    assert completed["status"] == "completed"
    assert len(_worker_calls(run["worker_log"])) == 2
