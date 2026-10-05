"""Reproduce the E3 refusal chain without a database.

The refusal at `drive_improve_round` fires on `store.identity` before the
round touches anything durable, so an owned store on a JSON file is enough
to produce the innermost message. The two wrappers that rename it are then
applied by hand, exactly as `bind_live_revision` and
`bind_retained_acquisition` apply them.

Run from the repo root:
    python tools/e3_refusal_repro.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel


def build(path, identity):
    store = frontier.create_store(
        path, namespace=frontier.NAMESPACE, identity=identity,
        mission={"objective": "m",
                 "environments": [{"split": "dev", "seed": 4}]},
        authority={"queries": 16, "steps": 12})
    store.bind_active(channel.make_control("low"))
    return store


def main() -> int:
    import tempfile

    named = "invl02-e12-P1-repro"
    task = rules.make_task("dev", 4)

    with tempfile.TemporaryDirectory() as tmp:
        owned = os.path.join(tmp, "owned.json")
        identity = frontier.StoreIdentity(investigation_id=named,
                                          dsn="postgresql:///unused-here")
        store = build(owned, identity)
        print("owned store identity: investigation_id=%r dsn=%r" % (
            store.identity.investigation_id, store.identity.dsn))
        try:
            channel.drive_improve_round(store, task, round_no=1)
        except Exception as exc:
            print("innermost (%s): %s" % (type(exc).__name__, exc))
            innermost = str(exc)
        else:
            print("innermost: NO REFUSAL")
            innermost = None

        nameless = os.path.join(tmp, "nameless.json")
        plain = build(nameless, None)
        print("nameless store identity: %r" % (plain.identity,))
        try:
            channel.drive_improve_round(plain, task, round_no=1)
        except Exception as exc:
            print("nameless innermost (%s): %s" % (type(exc).__name__, exc))
        else:
            print("nameless innermost: NO REFUSAL at the ownership check")

    if innermost is None:
        return 1

    # The two renames, applied as live_construct applies them.
    rejected = ("rejected: post-restart round refused: "
                "live improvement refused: %s" % innermost)
    print("\nwrapper 1 (bind_live_revision:1546): %s" % rejected)
    wrapped = ("retained without binding: the round refused before it"
               " executed anything: %s" % rejected)
    print("wrapper 2 (bind_retained_acquisition:1632):\n  %s" % wrapped)

    # Compared against the CI log rather than a transcription of it. The log
    # strips the space at the source's own line break, so whitespace is
    # normalized on both sides. Point `--ci-log` at the run's suite log.
    import re

    normalize = lambda s: re.sub(r"\s+", " ", s).strip()   # noqa: E731
    ci_line = None
    argv = sys.argv[1:]
    log_path = (argv[0] if argv else os.path.join(
        os.path.dirname(ROOT), ".a53-ci2", "suite__py3.131_.log"))
    if os.path.exists(log_path):
        for raw in open(log_path, encoding="utf-8", errors="replace"):
            if "test_e3_accepts_only_matching_bound_e12_store_and_receipt" \
                    in raw and "LiveRefused" in raw:
                ci_line = raw.split("FAILED ", 1)[1].strip()
                ci_line = ci_line.split(" - ", 1)[-1]
                break
    mine = "experiments.ad01.live_construct.LiveRefused: " + wrapped
    if ci_line is None:
        print("\nCI log not read (looked for %s); comparison NOT RUN" % log_path)
        return 1
    print("\nequals the CI message: %s" % (
        normalize(ci_line) == normalize(mine)))
    return 0


if __name__ == "__main__":
    sys.exit(main())