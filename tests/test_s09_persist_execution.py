from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from experiments.ad01.s09_run_isolation import create_disposable_db, \
    disposable_db, drop_disposable_db

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
BEFORE_BUNDLE = ROOT / "evidence_s09_m3_live"
RUN_TOKEN = "persist"
ENTRY = (
    "def ENTRY(task, oracle, max_queries=16):\n"
    "    if task['family'] == 'software':\n"
    "        return reducers.reduce_software(task, oracle, method='greedy', max_queries=16)\n"
    "    return reducers.reduce_graph(task, oracle, method='greedy', max_queries=16)\n"
)


class RecordingProvider:
    label = "S09PE-PROVIDER"

    def __init__(self, policy_source: str):
        from settlement.gateway import Usage
        self.policy_source = policy_source
        self.usage = Usage(input_tokens=11, output_tokens=7)

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse
        prompt = " ".join(str(message.get("content", ""))
                          for message in request.messages)
        source = self.policy_source if "Write one python policy" in prompt \
            else ENTRY
        return ModelResponse(request.operation_id,
                             json.dumps({"entry": source, "notes": "s09pe"}),
                             {}, self.usage, "stop")

    def cancel(self, operation_id):
        return False


@pytest.fixture(scope="module")
def live_store():
    database = create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)
    try:
        yield database
    finally:
        drop_disposable_db(database)


@pytest.fixture(scope="module")
def live_bundle(tmp_path_factory, live_store):
    from scripts import s09_pilot
    out = tmp_path_factory.mktemp("persist")
    return s09_pilot.run_study(
        live_store.dsn, out, namespace_token="pe",
        gateway=RecordingProvider(s09_pilot.P1_POLICY_SOURCE))


def _read(record: dict) -> list:
    return [digest for digest in record["executed_policy_digests"] if digest]


def test_store_read_record_carries_the_digests_it_read(live_bundle):
    from scripts import s09_pilot
    p0 = hashlib.sha256(s09_pilot.P0_POLICY_SOURCE.encode()).hexdigest()
    observed = {record["executed_policy_digests"][0]
                for record in live_bundle["use_records"]}
    assert observed == {p0, live_bundle["construction"]["P1"]["bound_digest"]}
    for record in live_bundle["use_records"]:
        assert _read(record) == [record["executed_policy_digest"]]
        assert record["policy_store_read"] is True


def test_backfilled_record_is_distinguishable_from_one_the_store_proved():
    from scripts import s09_pilot
    bound = "b" * 64
    episode = {"executed_policy_digests": [], "executed_policy_digest": bound,
               "policy_actions": [{"kind": "development", "diagnostic":
                                  "software", "task_id": "ad01-w1-dev-sw-00",
                                  "max_queries": 15}]}
    backfilled = s09_pilot._use_policy_provenance(episode)
    proved = s09_pilot._use_policy_provenance(dict(
        episode, executed_policy_digests=[bound]))
    assert backfilled == {"executed_policy_digests": [],
                          "executed_policy_digest": bound,
                          "policy_store_read": False,
                          "policy_actions": [{"kind": "development",
                                              "diagnostic": "software",
                                              "task_id": "ad01-w1-dev-sw-00",
                                              "max_queries": 15}]}
    assert proved == {"executed_policy_digests": [bound],
                      "executed_policy_digest": bound,
                      "policy_store_read": True,
                      "policy_actions": [{"kind": "development",
                                          "diagnostic": "software",
                                          "task_id": "ad01-w1-dev-sw-00",
                                          "max_queries": 15}]}


def test_the_real_reader_names_a_backfill_and_clears_a_proven_read(live_bundle):
    from scripts import s09_pilot, s09_verify
    unproven = str(s09_verify.Finding.POLICY_EXECUTION_UNPROVEN)
    template = live_bundle["use_records"][0]
    backfilled = dict(template, executed_policy_digests=[],
                      policy_store_read=False)
    assert [finding["subject"] for finding in s09_verify.verify_bundle(
        dict(live_bundle, use_records=[backfilled]))["findings"]
        if finding["reason"] == unproven] == [template["record_id"]]
    assert [finding for finding in s09_verify.verify_bundle(
        dict(live_bundle, use_records=[template]))["findings"]
        if finding["reason"] == unproven] == []
    assert s09_pilot._use_policy_provenance(
        {"executed_policy_digests": [], "executed_policy_digest": "b" * 64,
         "policy_actions": []}) == {"executed_policy_digests": [],
                                    "executed_policy_digest": "b" * 64,
                                    "policy_store_read": False,
                                    "policy_actions": []}


def test_admitted_action_is_on_the_saved_record(live_bundle):
    actions = {record["policy_actions"][0]["task_id"]
               for record in live_bundle["use_records"]}
    assert actions == {"ad01-w1-dev-sw-00", "ad01-w1-dev-gr-00",
                       "ad01-w2-dev-sw-00", "ad01-w2-dev-gr-00"}
    p0 = [record for record in live_bundle["use_records"]
          if record["study_arm"] == "P0" and record["domain"] == "software"
          and record["task_id"].endswith("sw-00") and record["world"] == 1]
    assert len(p0) == 2
    for record in p0:
        assert record["policy_actions"] == [{"kind": "development",
                                             "diagnostic": "software",
                                             "task_id": "ad01-w1-dev-sw-00",
                                             "max_queries": 15}]
    revised = [record for record in live_bundle["use_records"]
               if record["study_arm"] == "P1" and record["domain"] == "software"
               and record["task_id"].endswith("sw-00") and record["world"] == 1]
    assert len(revised) == 2
    for record in revised:
        assert record["policy_actions"] == [{"kind": "development",
                                             "diagnostic": "software",
                                             "task_id": "ad01-w1-dev-sw-00",
                                             "max_queries": 4}]


def test_saved_action_matches_the_episode_that_produced_it(live_bundle):
    by_episode = {}
    for episode in live_bundle["assessment"]:
        by_episode.setdefault(episode["episode_id"], episode)
    for record in live_bundle["use_records"]:
        episode = by_episode[record["episode_id"]]
        assert record["policy_actions"] == episode["policy_actions"]
        assert record["executed_policy_digests"] == \
            episode["executed_policy_digests"]


def _before() -> list:
    return json.loads((BEFORE_BUNDLE / "use_records.json").read_text())


def test_preserved_bundle_proves_nothing_the_new_one_proves():
    before = _before()
    assert len(before) == 24
    for record in before:
        assert "executed_policy_digests" not in record
        assert "policy_store_read" not in record
        assert "policy_actions" not in record
    real = [record for record in before
            if record.get("executed_policy_digest")
            and record["executed_policy_digest"] != record["policy_digest"]]
    copies = [record for record in before
              if record.get("executed_policy_digest")
              and record["executed_policy_digest"] == record["policy_digest"]]
    assert len(real) == 4
    assert len(copies) == 12
    for record in real:
        assert record["executed_policy_digest"]
    for record in real + copies:
        assert {key for key in record
                if key.startswith("policy_") or key.startswith(
                    "executed_policy")} == {"policy_artifact_kind",
                                            "policy_digest",
                                            "executed_policy_digest"}


def test_a_genuine_execution_reads_as_a_copy_in_the_preserved_bundle(live_bundle):
    from scripts import s09_verify
    unproven = str(s09_verify.Finding.POLICY_EXECUTION_UNPROVEN)
    before = _before()
    findings = s09_verify.verify_bundle_dir(BEFORE_BUNDLE)["findings"]
    flagged = {finding["subject"] for finding in findings
               if finding["reason"] == unproven}
    genuine = {record["record_id"] for record in before
               if record.get("executed_policy_digest")
               and record["executed_policy_digest"] != record["policy_digest"]}
    copied = {record["record_id"] for record in before
              if record.get("executed_policy_digest")
              and record["executed_policy_digest"] == record["policy_digest"]}
    assert flagged == genuine | copied
    assert genuine <= flagged
    proved = {record["record_id"]: record["policy_store_read"]
              for record in live_bundle["use_records"]}
    assert set(proved) == {record["record_id"] for record in before}
    assert set(proved.values()) == {True}


def test_the_preserved_bundle_reads_as_unproven_and_the_new_one_does_not(
        live_bundle):
    from scripts import s09_verify
    unproven = str(s09_verify.Finding.POLICY_EXECUTION_UNPROVEN)
    before = s09_verify.verify_bundle_dir(BEFORE_BUNDLE)["findings"]
    assert len([finding for finding in before
                if finding["reason"] == unproven]) == 16
    assert [finding for finding in s09_verify.verify_bundle(live_bundle)
            ["findings"] if finding["reason"] == unproven] == []


def test_the_store_is_one_this_run_created(live_store):
    """A dropped store must never be a store somebody else still runs on.

    This file's study mints its namespace token but used to mint its store
    from a name the reader had to trust, so a sibling run of the same file
    dropped the store mid-study and the provenance assertions read a torn
    study as a product defect. The name carries a per-run token.
    """
    assert live_store.name.startswith("s09iso_persist_"), live_store.name
    assert live_store.dsn.count(live_store.name) == 1, live_store.dsn


def test_the_store_survives_a_second_module_scope():
    """Re-deriving the store must not reuse this module's database.

    The collision that produced the original failures was two runs of this
    file at once. Each run's fixture mints its own name, so a second fixture
    can never observe or destroy the first one's database.
    """
    with disposable_db(RUN_TOKEN) as other:
        assert other.name.startswith("s09iso_persist_"), other.name
