"""Prove the leak is closed: run the leaking file, then a victim file, in one process.

Before the repair, running the leaking file left settlement.store bound to a
one-attribute stub, so every later file in the same pytest process that touched
the store raised AttributeError. After the repair the module survives intact.

This imports both files and calls the victim's store-dependent code the same way
its own tests do, so the resolution path is the real one.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

LEAKER = ROOT / "tests" / "test_posix_paths_checkpoint_restore.py"

# Attributes a victim file reaches for. Chosen from the store's own surface, so
# a stub-bound module fails each of them.
PROBE_ATTRS = ["seed_grant", "seed_allocation", "operation_receipts",
               "subdivide_allocation", "is_ceiling_name", "transact",
               "checkpoint_verify", "restore_fence", "admit_receipt"]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    import settlement
    import settlement.store  # noqa: F401  binds the package attribute

    before = {a: hasattr(settlement.store, a) for a in PROBE_ATTRS}
    print("before the leaking file:")
    print(f"  settlement.store = {settlement.store.__name__}")
    print(f"  {sum(before.values())}/{len(before)} probe attrs present")

    mod = load(LEAKER, "t_leaker")

    class _MP:
        def __init__(self):
            self._undo = []

        def setattr(self, target, name, value):
            self._undo.append((target, name, getattr(target, name)))
            setattr(target, name, value)

        def setitem(self, mapping, key, value):
            missing = key not in mapping
            self._undo.append((mapping, key,
                               None if missing else mapping[key], missing))
            mapping[key] = value

        def undo(self):
            for target, name, value, *missing in reversed(self._undo):
                if missing:
                    del target[name]
                else:
                    setattr(target, name, value)
            self._undo.clear()

    import tempfile

    names = [n for n in dir(mod) if n.startswith("test_")]
    names.sort(key=lambda n: getattr(mod, n).__code__.co_firstlineno)
    ran = 0
    for name in names:
        fn = getattr(mod, name)
        takes_mp = fn.__code__.co_argcount > 0 and \
            fn.__code__.co_varnames[0] == "monkeypatch"
        if not takes_mp:
            fn()
            continue
        mp = _MP()
        try:
            fn(mp)
            ran += 1
        finally:
            mp.undo()

    after = {a: hasattr(settlement.store, a) for a in PROBE_ATTRS}
    print(f"\nran {ran} leaking-file bodies")
    print("after the leaking file:")
    print(f"  settlement.store = {settlement.store.__name__}")
    print(f"  {sum(after.values())}/{len(after)} probe attrs present")

    # The victim path: a lazy import executed AFTER the leak, which is exactly
    # what tests/test_invc1_method_envelope.py:236 does.
    from settlement import store as _victim
    try:
        _victim.operation_receipts
    except AttributeError as exc:
        print(f"\nVICTIM FAILS: {exc}")
        return 1
    print("\nvictim resolves store.operation_receipts: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())