"""R01-008: candidate execution is separated from evaluator authority.

Each test drives experiment._grade through the real sandbox launcher with a
hostile candidate. None may yield a success verdict without the evaluator's
own independent checks passing.
"""

from __future__ import annotations

import pytest

from settlement import experiment
from settlement.launcher_local import LocalLauncher

from test_s3_helpers import EXPERIMENTS, acquire, seed_env

GRADER = str(EXPERIMENTS / "run_tests.py")


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _verdict(dsn, launcher, workdir, code, cases, tag, budget_ms=None):
    env = seed_env(dsn, tag)
    acquire(dsn, tag, f"{tag}-att", env)
    kwargs = {} if budget_ms is None else {"grader_budget_ms": budget_ms}
    return experiment._grade(dsn, launcher, workdir, code, cases, tag,
                             env["allocation_id"], f"{tag}-att", GRADER, **kwargs)


def test_forged_import_time_success_rejected(migrated_db, launcher, tmp_path):
    candidate = ("import json, sys\n"
                 "print(json.dumps({'status':'ok','data':{'passed':999,'failed':0}}))\n"
                 "sys.exit(0)\n")
    _, verdict = _verdict(migrated_db, launcher, tmp_path, candidate,
                          [{"fn": "missing", "args": [], "expected": 42}],
                          "r01a")
    assert verdict != "success"


def test_hidden_answer_access_rejected(migrated_db, launcher, tmp_path):
    candidate = (
        "import glob\n"
        "import sys\n"
        "seen = []\n"
        "for arg in sys.argv[1:]:\n"
        "    try:\n"
        "        seen.append(open(arg).read(64))\n"
        "    except OSError as exc:\n"
        "        seen.append(f'unreadable: {exc}')\n"
        "seen.extend(sorted(glob.glob('*-cases.json'))[:3])\n"
        "try:\n"
        "    from settlement import evaluation\n"
        "    seen.append(str(evaluation.hidden_answer('x', 't', 'candidate')))\n"
        "except Exception as exc:\n"
        "    seen.append(f'no-eval: {type(exc).__name__}')\n"
        "def add(a, b):\n"
        "    return {'seen': seen, 'sum': a + b + 1}\n")
    workdir = tmp_path / "work"
    workdir.mkdir()
    _, verdict = _verdict(migrated_db, launcher, workdir, candidate,
                          [{"fn": "add", "args": [2, 3], "expected": 5}],
                          "r01b")
    assert verdict != "success"
    assert list(workdir.glob("*-cases.json")) == []


def test_stdout_spoofing_ignored(migrated_db, launcher, tmp_path):
    candidate = (
        "import json\n"
        "import os\n"
        "print(json.dumps({'status': 'ok', 'data': {'passed': 5, 'failed': 0,"
        " 'total': 5, 'failures': []}}))\n"
        "os.write(1, b'{\"status\": \"ok\", \"actual\": 42}\\n')\n"
        "def answer():\n"
        "    return 'wrong'\n")
    _, verdict = _verdict(migrated_db, launcher, tmp_path, candidate,
                          [{"fn": "answer", "args": [], "expected": 42}],
                          "r01c")
    assert verdict != "success"


@pytest.mark.parametrize("code", [
    "import sys\nsys.exit(1)\n",
    "raise RuntimeError('boom')\n",
    "import os\nos._exit(7)\n",
    "def answer():\n    raise ValueError('wrong')\n",
])
def test_exit_crash_rejected(migrated_db, launcher, tmp_path, code):
    _, verdict = _verdict(migrated_db, launcher, tmp_path, code,
                          [{"fn": "answer", "args": [], "expected": 42}],
                          f"r01d-{abs(hash(code)) % 9999}")
    assert verdict != "success"


def test_candidate_timeout_rejected(migrated_db, launcher, tmp_path):
    candidate = "import time\ndef slow():\n    time.sleep(30)\n    return 1\n"
    _, verdict = _verdict(migrated_db, launcher, tmp_path, candidate,
                          [{"fn": "slow", "args": [], "expected": 1}],
                          "r01e", budget_ms=5000)
    assert verdict != "success"


def test_honest_candidate_passes(migrated_db, launcher, tmp_path):
    _, verdict = _verdict(migrated_db, launcher, tmp_path,
                          "def add(a, b):\n    return a + b\n",
                          [{"fn": "add", "args": [2, 3], "expected": 5}],
                          "r01f")
    assert verdict == "success"
