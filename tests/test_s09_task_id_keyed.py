"""The task id must not be reversible from the seed.

N-01 replaced `rule-dev-0004` with a digest, and that was a real repair:
the id stopped *naming* its seed, so a text scan of the view no longer
finds it. N-34 established it is still a leak, because the digest is
unsalted and deterministic over a seed space small enough to enumerate.
Measured: for `make_task("dev", 4)`, whose id is `rule-dev-594d82fe2c6a`,
iterating seeds 0..9999 reproduces the id at seed 4. A thousand hashes,
no cleverness, well inside any budget.

The repair chosen is a keyed digest: the id is an HMAC over
`(instrument, split, seed)` under a key that lives with the frozen world
and never reaches the policy view.

## Why the key is frozen rather than per-campaign

`offline_recompute` re-derives task ids from `(split, seed)` to verify
frozen evidence - `_task_id_for` at line 1907 and the frozen-task check at
line 496 both call `make_task` and compare the id it produces with the one
in the bundle. A per-run or per-campaign secret would make that
verification impossible, because the recompute runs in a different
process with no access to the run's secret. So the key is part of the
world's frozen state: deterministic across processes, which is what the
recompute needs, and not in the view, which is what the leak needs.

That is only safe while the seed space is enumerable, so these tests pin
both halves: the key must not be in the view, and enumeration must not
recover the id.

## Why widening the seed space was not enough

It was the cheaper option on paper and it does not hold here. The study's
seeds are small integers in a manifest
(`E12_BOOLEAN_SEEDS = {"dev": [3, 7], "qual": [11], "audit": [23]}`), and
`s09_instruments` enumerates `range(SCAN_LIMIT)` to build panels, so the
id derivation and the panel builder are the same integer space. Widening
the seed would break every frozen bundle and every panel in the same
stroke, and the id would still be a pure function of a value the harness
publishes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import hashlib
import json

from experiments.ad01 import boolean_active
from experiments.ad01 import boolean_policy
from experiments.ad01 import boolean_rule
from experiments.ad01 import second_active
from experiments.ad01 import worlds


def _view(seed: int = 4) -> dict:
    task = boolean_rule.make_task("dev", seed)
    session = boolean_rule.RuleSession(task)
    return boolean_policy._shared_view(
        boolean_active.public_state(session))


def test_the_id_is_not_the_seed_and_does_not_parse_as_one():
    view = _view()

    assert view["task_id"] != "rule-dev-0004"
    assert not view["task_id"].endswith("0004")
    assert view["task_id"].split("-")[:2] == ["rule", "dev"]


def test_the_view_carries_the_seed_neither_directly_nor_as_a_key():
    """The view must not hold the secret under any spelling."""
    serialized = json.dumps(_view(), sort_keys=True, default=str)

    assert "seed" not in serialized.lower(), (
        "the policy view now names a seed: %s" % serialized[:400])


def test_the_id_is_not_a_pure_function_of_published_values():
    """The property that actually changed, stated honestly.

    With the key, the id is no longer computable from `(split, seed)`
    alone: a party holding only the values the harness publishes cannot
    reproduce it. It is still computable by a party that also holds
    `worlds.TASK_ID_KEY`, which lives in this repository.

    That boundary is deliberate, and the earlier version of this test hid
    it. It asserted that enumerating the seed space does not reproduce the
    id - which is false with a key in the repo, because whoever reads the
    repo has the key. So this test does the search the way an adversary
    who has only the view would, i.e. without the key, and the key-swap
    test below is what proves the key is genuinely consulted.
    """
    target = boolean_rule.make_task("dev", 4)["task_id"]

    for seed in range(10_000):
        plain = hashlib.sha256(
            ("%s/%s/%d" % (boolean_rule.INSTRUMENT_ID, "dev", seed)).encode()
        ).hexdigest()[:12]
        assert "rule-dev-%s" % plain != target, (
            "the id is still a plain sha256 of published values, so the key "
            "is not being consulted (seed %d)" % seed)


def test_the_legacy_unkeyed_id_is_gone_from_both_instruments():
    """A revert to `sha256` cannot pass silently.

    Both worlds are checked because closing one and not the other leaves
    the study half open, and because the ordering world has its own
    `_opaque_id` rather than sharing `boolean_rule.key_id`.
    """
    legacy = hashlib.sha256(
        ("%s/%s/%d" % (boolean_rule.INSTRUMENT_ID, "dev", 4)).encode()
    ).hexdigest()[:12]
    order_legacy = hashlib.sha256(
        ("%s/%s/%d" % (second_active.INSTRUMENT_ID, "dev", 5)).encode()
    ).hexdigest()[:12]

    assert boolean_rule.make_task("dev", 4)["task_id"] != "rule-dev-%s" % legacy
    assert second_active.make_task("dev", 5)["task_id"] != \
        "order-dev-%s" % order_legacy


def test_the_key_is_absent_from_the_policy_view():
    """The boundary the key protects, asserted at the boundary itself."""
    serialized = json.dumps(_view(), sort_keys=True, default=str)

    assert worlds.TASK_ID_KEY.decode() not in serialized
    assert "hmac" not in serialized.lower()


def test_swapping_the_key_changes_the_id():
    """Proves the key is read at call time, not captured at import.

    The first version of this test failed, and the failure is the useful
    part: `key_id` closed over `_ID_KEY` as it stood at import, so
    assigning a new value to the module attribute changed nothing and the
    id stayed the same. Reading the module attribute at call time is what
    makes the key swappable, and this keeps that true.
    """
    original = boolean_rule.make_task("dev", 4)["task_id"]
    saved = boolean_rule._ID_KEY
    try:
        boolean_rule._ID_KEY = b"a-different-key"
        assert boolean_rule.make_task("dev", 4)["task_id"] != original
    finally:
        boolean_rule._ID_KEY = saved
    assert boolean_rule.make_task("dev", 4)["task_id"] == original


def test_ids_stay_deterministic_across_calls():
    """A keyed digest is only safe because it is stable.

    The recompute in `offline_recompute` re-derives ids in a different
    process and compares them against frozen evidence. If the key were
    generated per call rather than read from frozen state, that
    verification would silently stop working - so this is the test that
    keeps the key from becoming a per-run secret by accident.
    """
    first = boolean_rule.make_task("dev", 4)["task_id"]
    second = boolean_rule.make_task("dev", 4)["task_id"]

    assert first == second
    assert second_active.make_task("dev", 5)["task_id"] == \
        second_active.make_task("dev", 5)["task_id"]
