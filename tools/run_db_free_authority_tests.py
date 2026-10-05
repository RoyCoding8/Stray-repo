"""Run the DB-free tests in test_operate_step_authority without pytest.

`tests/conftest_isolation.py` connects to PostgreSQL at `pytest_configure`, so
the suite cannot start at all without a database even for a test that touches
none. This calls those tests directly so they can be verified red-on-unfixed on
a host with no database, which is the honest way to check the structural gates
here. The database-backed ones are listed and skipped rather than faked.
"""
import inspect
import sys

sys.path.insert(0, "tests")
sys.path.insert(0, "src")
sys.path.insert(0, ".")

import test_operate_step_authority as t  # noqa: E402

DB_PARAMS = {"study", "owned_store", "tmp_path", "dsn"}

passed, failed, skipped = [], [], []
for name in sorted(n for n in dir(t) if n.startswith("test_")):
    fn = getattr(t, name)
    params = set(inspect.signature(fn).parameters)
    if params & DB_PARAMS:
        skipped.append(name)
        continue
    try:
        fn()
        passed.append(name)
    except Exception as exc:  # noqa: BLE001
        failed.append((name, type(exc).__name__, str(exc)[:300]))

print("PASSED (%d):" % len(passed))
for name in passed:
    print("  ", name)
print("FAILED (%d):" % len(failed))
for name, kind, message in failed:
    print("  %s -> %s: %s" % (name, kind, message))
print("SKIPPED, needs a database (%d): %s" % (len(skipped), ", ".join(skipped)))
raise SystemExit(1 if failed else 0)