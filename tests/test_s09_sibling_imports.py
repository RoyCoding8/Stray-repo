"""`experiments` modules import their siblings through the package.

A bare `from fault_tasks import ...` inside a module that lives in
`experiments/` resolves only if something else has already put
`experiments/` on `sys.path`, which is an accident of import ordering.
The same defect in `experiments/doubles.py` killed the S09 conformance
replay lane outright, and these imports sit inside `main` bodies where
no existing test reached them, so they stayed latent.

The check is a fresh process with no other import run first, and it
reaches the import site by calling `main` far enough to pass argument
parsing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SIBLINGS = ("doubles", "fault_tasks", "run_live_abc", "run_dev_episode")


def _fresh_process(body: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", body],
        cwd=str(ROOT),
        env={"PYTHONPATH": ".", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_no_module_under_experiments_imports_a_sibling_by_bare_name():
    offenders = []
    for path in sorted((ROOT / "experiments").glob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip()
            for sibling in SIBLINGS:
                if stripped.startswith("from %s import" % sibling) \
                        or stripped.startswith("import %s" % sibling):
                    offenders.append("%s:%d %s"
                                     % (path.name, number, stripped))
    assert not offenders, "bare sibling imports: %s" % offenders


def test_run_use_main_reaches_its_sibling_imports():
    body = (
        "import sys\n"
        "sys.path.insert(0, '.')\n"
        "from experiments import run_use\n"
        "try:\n"
        "    run_use.main(['--use-task', 'ad01-w0-dev-sw-00'])\n"
        "except SystemExit as exc:\n"
        "    print('exit', exc.code)\n"
        "except ModuleNotFoundError as exc:\n"
        "    print('MODULE-NOT-FOUND', exc)\n"
    )
    done = _fresh_process(body)
    assert "MODULE-NOT-FOUND" not in done.stdout, done.stdout
    assert done.returncode == 0, done.stderr


def test_run_dev_episode_main_reaches_its_sibling_imports():
    body = (
        "import sys\n"
        "sys.path.insert(0, '.')\n"
        "from experiments import run_dev_episode\n"
        "try:\n"
        "    run_dev_episode.main([])\n"
        "except SystemExit as exc:\n"
        "    print('exit', exc.code)\n"
        "except ModuleNotFoundError as exc:\n"
        "    print('MODULE-NOT-FOUND', exc)\n"
    )
    done = _fresh_process(body)
    assert "MODULE-NOT-FOUND" not in done.stdout, done.stdout
    assert done.returncode == 0, done.stderr


def test_run_live_abc_main_reaches_its_sibling_imports():
    body = (
        "import sys\n"
        "sys.path.insert(0, '.')\n"
        "from experiments import run_live_abc\n"
        "import inspect\n"
        "print('main takes', len(inspect.signature(run_live_abc.main)"
        ".parameters), 'parameters')\n"
        "try:\n"
        "    run_live_abc.main()\n"
        "except SystemExit as exc:\n"
        "    print('exit', exc.code)\n"
        "except TypeError as exc:\n"
        "    print('TYPE-ERROR', exc)\n"
        "except ModuleNotFoundError as exc:\n"
        "    print('MODULE-NOT-FOUND', exc)\n"
    )
    done = _fresh_process(body)
    assert "MODULE-NOT-FOUND" not in done.stdout, done.stdout
    assert done.returncode == 0, done.stderr
