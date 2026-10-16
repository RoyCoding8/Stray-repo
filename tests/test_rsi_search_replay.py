from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from rsi_search_fixture import worlds

from rsi import capability, episode, genome, investigate, search, task, verifier
from settlement import store
from settlement.common import Command
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

ROOT = Path(__file__).resolve().parents[1]
FAKE_WORKER = ROOT / "tests" / "fixtures" / "fake_investigate.py"


def _task() -> task.Task:
    verifier = b"import unittest\nfrom calc import add\nclass TestAdd(unittest.TestCase):\n def test_add(self): self.assertEqual(add(2,3),5)\n"
    return task.Task("p06-search-add", "dev", "Implement add.",
                     {"calc.py": b"def add(a,b): return 0\n"},
                     {"test_add.py": verifier},
                     {"calc.py": b"def add(a,b): return a+b\n"},
                     ("test_add.py",))


def test_postgres_capture_reconstructs_a_completed_p01_branch(migrated_db, tmp_path):
    dsn = migrated_db
    tag = "ad1062" + uuid.uuid4().hex[:6]
    staging, artifacts = tmp_path / "staging", tmp_path / "artifacts"
    staging.mkdir()
    artifacts.mkdir()
    roots = {"staging_root": staging, "artifacts_root": artifacts}
    item = _task()
    seed = genome.Genome({"AGENTS.md": b"Use the prepared input.\n"})
    genome.publish(dsn, seed, parent=None, origin="p06-search-fixture", **roots)
    task.publish(dsn, item, **roots)
    store.seed_allocation(dsn, Command(
        request_id=tag + "-tokens", payload={"allocation_id": tag + "-tokens",
        "domain": "tokens", "authorized": 100_000}))
    store.seed_allocation(dsn, Command(
        request_id=tag + "-cpu", payload={"allocation_id": tag + "-cpu",
        "domain": "cpu", "authorized": 100_000}))
    agent = CodexLauncher(
        tmp_path / "worker", codex_cmd=[sys.executable, str(FAKE_WORKER),
        str(tmp_path / "worker.jsonl"), "pass-first"],
        provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
        allowed_overrides=genome.HARNESS_KEYS)
    checker = LocalLauncher(tmp_path / "checker")
    state = investigate.create(
        dsn, agent, seed, investigation_id=tag, task=item,
        token_allocation=tag + "-tokens", cpu_allocation=tag + "-cpu",
        max_steps=1, timeout_ms=30_000, token_ceiling=5_000, **roots)
    prepared = investigate.prepare_context(dsn, tag, target_revision=0,
                                           artifacts_root=artifacts)
    assert prepared["visible_input"]
    start = {"investigation_id": tag, "target_revision": 0,
             "visible_input": prepared["visible_input"], "task": item.digest,
             "genome": seed.digest, "model": "fixture:free", "method": None,
             "runtime": {"execution_version": "", "launcher_id": "codex",
                         "provider_id": "fixture"},
             "evaluator_version": item.evaluator_version,
             "limits": {key: state["config"][key] for key in
                        ("timeout_ms", "token_ceiling", "max_steps",
                         "token_allocation", "cpu_allocation")}}
    frame = search.publish_frame(
        dsn, {"objective": "Implement add", "menu": [{"opportunity_id": "fixture"}],
              "prefix": [], "resource_limits": {"cpu": 100_000}},
        {"fixture": start}, {"prepared_by": "P01", "revision": state["revision"]},
        **roots)

    finished = investigate.step(dsn, agent, checker, tag, target_revision=0, **roots)
    branch = search.capture(dsn, frame, "fixture", **roots)

    assert finished["last_observation"]["passed"] is True
    assert branch["status"] == "gap"
    assert "execution identity" in branch["reason"]
    assert branch["known_observation"] == {"status": "passed", "passed": True}


def test_postgres_capture_supports_a_pinned_native_method_execution(migrated_db, tmp_path):
    dsn = migrated_db
    tag = "ad1062" + uuid.uuid4().hex[:6]
    staging, artifacts = tmp_path / "staging", tmp_path / "artifacts"
    staging.mkdir()
    artifacts.mkdir()
    roots = {"staging_root": staging, "artifacts_root": artifacts}
    item = _task()
    method_value = {"goal": "add"}
    method_source = (
        "def invoke(request):\n"
        "    return {'value': {'implemented': True}, 'files': {"
        "'calc.py': 'def add(a,b): return a+b\\n'}}\n"
    )
    seed = genome.Genome({
        "AGENTS.md": b"Use the retained native method.\n",
        "skills/solve/SKILL.md": (
            b"---\nname: solve\ndescription: Produce an addition implementation.\n---\n"
            b"Return the implementation required by the task.\n"),
        "skills/solve/capability.json": json.dumps({
            "schema": "rsi-capability/1", "interface": "task-solver/1",
            "entrypoint": "method.py:invoke", "dependencies": ["python-stdlib"],
            "effects": ["return", "solution-files"],
            "limits": {"timeout_ms": 30_000, "max_output_bytes": 65_536},
        }).encode(),
        "skills/solve/method.py": method_source.encode(),
    })
    genome.publish(dsn, seed, parent=None, origin="p06-method-worker-fixture", **roots)
    task.publish(dsn, item, **roots)
    for domain in ("tokens", "cpu"):
        store.seed_allocation(dsn, Command(
            request_id=f"{tag}-{domain}", payload={"allocation_id": f"{tag}-{domain}",
            "domain": domain, "authorized": 100_000}))

    checker = LocalLauncher(tmp_path / "checker")
    input_files = {path: raw.decode("utf-8") for path, raw in item.workspace.items()}
    retained_episode = episode.run_method_episode(
        dsn, checker, seed, name="solve",
        request={"interface": "task-solver/1", "value": method_value,
                 "files": input_files, "context": {}},
        operation_id=tag + "-retained-use", task=item, allocation_id=tag + "-cpu",
        attempt_id=None, **roots)
    assert retained_episode.status == "completed"
    verdict = verifier.verify_episode(
        dsn, checker, checker, retained_episode.operation_id,
        allocation_id=tag + "-cpu", attempt_id=None, **roots)
    assert verdict.passed is True
    retention = capability.retain(
        dsn, tag + "-retention", genome=seed, name="solve",
        episode_id=retained_episode.operation_id, artifacts_root=artifacts)
    assert retention["status"] == "retained"

    state = investigate.create(
        dsn, None, seed, investigation_id=tag, task=item,
        token_allocation=tag + "-tokens", cpu_allocation=tag + "-cpu",
        max_steps=1, timeout_ms=30_000, token_ceiling=5_000,
        method={"name": "solve", "interface": "task-solver/1", "value": method_value},
        **roots)
    prepared = investigate.prepare_context(dsn, tag, target_revision=0,
                                           artifacts_root=artifacts)
    visible_input = prepared["visible_input"]
    continuation = {key: visible_input[key] for key in
                    ("objective", "objective_revision", "state_revision", "open_questions",
                     "artifact_refs", "previous_observation")}
    worker_request = {"interface": "task-solver/1", "value": method_value,
                      "files": input_files,
                      "context": {"continuation": {**continuation,
                                                    "context_packet": visible_input["context_packet"]},
                                  "task_digest": item.digest}}
    plan = capability.plan_invocation(checker, seed, "solve", worker_request,
                                      timeout_ms=state["config"]["timeout_ms"])
    start = {"investigation_id": tag, "target_revision": 0,
             "visible_input": visible_input, "task": item.digest,
             "genome": seed.digest, "model": "",
             "method": visible_input["capability"],
             "runtime": {"execution_version": plan.execution_version,
                         **dict(plan.runtime)},
             "evaluator_version": item.evaluator_version,
             "limits": {key: state["config"][key] for key in
                        ("timeout_ms", "token_ceiling", "max_steps",
                         "token_allocation", "cpu_allocation")}}
    frame = search.publish_frame(
        dsn, {"objective": "Implement add", "menu": [{"opportunity_id": "native"}],
              "prefix": [], "resource_limits": {"cpu": 100_000}},
        {"native": start}, {"prepared_by": "P01", "revision": 0}, **roots)

    finished = investigate.step(dsn, None, checker, tag, target_revision=0, **roots)
    branch = search.capture(dsn, frame, "native", **roots)

    assert finished["last_observation"]["passed"] is True
    assert branch["status"] == "supported", branch.get("mismatches") or branch.get("reason")
    assert branch["outcome"] == "passed"


def test_native_policy_receives_only_visible_frame_and_runs_once(migrated_db, tmp_path):
    dsn = migrated_db
    tag = "ad1062" + uuid.uuid4().hex[:6]
    staging, artifacts = tmp_path / "staging", tmp_path / "artifacts"
    staging.mkdir()
    artifacts.mkdir()
    roots = {"staging_root": staging, "artifacts_root": artifacts}
    source = (
        "import json\n"
        "def invoke(request):\n"
        "    assert 'future-secret' not in json.dumps(request, sort_keys=True)\n"
        "    return {'value': {'action': 'choose', 'opportunity_id': 'easy'}, 'files': {}}\n"
    )
    policy = genome.Genome({
        "skills/explore/SKILL.md": (b"---\nname: explore\ndescription: Select a prepared opportunity.\n---\n"
                                    b"Select an eligible prepared opportunity.\n"),
        "skills/explore/capability.json": json.dumps({
            "schema": "rsi-capability/1", "interface": search.POLICY_INTERFACE,
            "entrypoint": "method.py:invoke", "dependencies": ["python-stdlib"],
                "effects": ["return", "solution-files"], "limits": {"timeout_ms": 5_000,
            "max_output_bytes": 65_536},
        }).encode(),
        "skills/explore/method.py": source.encode(),
    })
    genome.publish(dsn, policy, parent=None, origin="p06-native-policy-fixture", **roots)
    store.seed_allocation(dsn, Command(
        request_id=tag + "-cpu", payload={"allocation_id": tag + "-cpu",
        "domain": "cpu", "authorized": 100_000}))
    artifacts_fixture = worlds()
    frame = artifacts_fixture["frame"]
    frame["starts"]["easy"]["source_future"] = "future-secret"
    frame_digest = search.publish_frame(dsn, frame["visible"], frame["starts"],
                                        frame["source"], **roots)
    branch = artifacts_fixture["branches"][artifacts_fixture["branch_digests"]["easy"]]
    branch["frame"] = frame_digest
    branch_digest = search._publish(dsn, staging, artifacts, search.BRANCH_SCOPE,
                                    "branch", branch)

    result = search.evaluate(
        dsn, LocalLauncher(tmp_path / "native"),
        {"genome": policy.digest, "name": "explore",
         "interface": search.POLICY_INTERFACE, "timeout_ms": 5_000,
         "max_output_bytes": 65_536}, [frame_digest], [branch_digest],
        evaluation_id=tag + "-evaluation", allocation_id=tag + "-cpu", **roots)

    assert result["results"][0]["status"] == "choose"
    assert result["results"][0]["selected"] == "easy"
    assert result["recomputed"]["supported"] == 1
    assert "future-secret" not in json.dumps(
        result["results"][0]["invocation"], sort_keys=True)
