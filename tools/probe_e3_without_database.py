"""Exercise the E3 module's database-free paths without pytest's conftest.

`tests/conftest_isolation.py:751` acquires a PostgreSQL admin claim in
`pytest_configure`, so on a host with no database pytest cannot even collect
this module -- there is no `--co` that gets past it. That is a property of the
host, not of the code under test, and CI carries postgres:18.

What this does instead: loads the module the way the fixture does and calls
the tests that need no database, with a real `tmp_path` and the one fixture
they require (`INVL02_LIVE_GRANT`). It therefore proves the module IMPORTS,
that the fixture wiring is consistent, and that the no-database assertions
still hold. It proves nothing about the four database-backed fixtures, and it
is not a substitute for them.

    python tools/probe_e3_without_database.py
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))


def load():
    spec = importlib.util.spec_from_file_location(
        "tei_under_test", ROOT / "tests" / "test_evidence_integrity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Env:
    """The one fixture the database-free tests ask for."""

    def __init__(self) -> None:
        self.saved = None

    def setenv(self, name: str, value: str) -> None:
        import os

        self.saved = os.environ.get(name)
        os.environ[name] = value

    def restore(self) -> None:
        import os

        if self.saved is None:
            os.environ.pop("INVL02_LIVE_GRANT", None)
        else:
            os.environ["INVL02_LIVE_GRANT"] = self.saved


class _MonkeyPatch:
    """The part of pytest's `monkeypatch` these tests actually use.

    They call `setenv` and `setattr`. An object that silently accepted a
    `setattr` without undoing it would let one test's patch leak into the
    next and make a failure mean nothing, so every patch is recorded and
    undone, exactly as pytest does.
    """

    def __init__(self) -> None:
        self._env: list[tuple[str, object]] = []
        self._attrs: list[tuple[object, str, object]] = []

    def setenv(self, name: str, value: str) -> None:
        import os

        self._env.append((name, os.environ.get(name)))
        os.environ[name] = value

    def setattr(self, target, name, value=None) -> None:
        if value is None and not isinstance(name, str):
            raise NotImplementedError("only setattr(obj, 'name', value)")
        self._attrs.append((target, name, getattr(target, name)))
        setattr(target, name, value)

    def undo(self) -> None:
        import os

        for name, saved in reversed(self._env):
            if saved is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = saved
        for target, name, saved in reversed(self._attrs):
            setattr(target, name, saved)
        self._env.clear()
        self._attrs.clear()


#: The tests that take no database. Anything whose signature names
#: `e3_database` or `dsn` is excluded, because this probe has no database to
#: give it.
NEEDS_DATABASE = {"e3_database", "dsn", "migrated_db"}


def database_free_tests(module) -> list[tuple[str, object]]:
    out = []
    for name, func in sorted(vars(module).items()):
        if not name.startswith("test_") or not callable(func):
            continue
        params = set(inspect.signature(func).parameters)
        if params & NEEDS_DATABASE:
            continue
        out.append((name, func))
    return out


def main() -> int:
    module = load()
    print("module imports; %d tests take no database"
          % len(database_free_tests(module)))
    import os
    import shutil

    # Every test here drives `run_e3`, which refuses without the grant. The
    # tests that patch it themselves set it too, harmlessly.
    os.environ["INVL02_LIVE_GRANT"] = "test"

    passed = failed = 0
    for name, func in database_free_tests(module):
        params = inspect.signature(func).parameters
        patch = _MonkeyPatch()
        work = Path(tempfile.mkdtemp(prefix="e3probe-"))
        try:
            kwargs = {}
            if "monkeypatch" in params:
                kwargs["monkeypatch"] = patch
            if "tmp_path" in params:
                kwargs["tmp_path"] = work
            func(**kwargs)
            passed += 1
            print("  PASS %s" % name)
        except Exception as exc:
            failed += 1
            print("  FAIL %s -- %s: %s" % (name, type(exc).__name__, exc))
            if os.environ.get("E3_PROBE_TRACE"):
                traceback.print_exc()
        finally:
            patch.undo()
            shutil.rmtree(work, ignore_errors=True)
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
