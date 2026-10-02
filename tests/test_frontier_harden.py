from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments.ad01 import frontier


def _mission():
    return {
        "objective": "harden replay accounting",
        "constraints": ["deterministic only"],
        "success_criteria": ["charged serves"],
        "environments": [
            {"instrument": "boolean-rule-v1", "split": "dev", "seed": 4},
        ],
    }


def _make_store(tmp_path, queries=8, steps=8):
    path = tmp_path / "harden.json"
    return frontier.create_store(
        path,
        namespace="invl02_m2",
        mission=_mission(),
        authority={"queries": queries, "steps": steps},
    )


def _key(store, x=3, instrument="boolean-rule-v1", env=None):
    return {
        "instrument": instrument,
        "inputs": {"x": x},
        "environment": env if env is not None else store.environment_digest,
    }


def test_duplicate_query_charged_twice_not_free(tmp_path):
    store = _make_store(tmp_path)
    store.record_outcome(_key(store), {"y": [0, 1, 0, 1]})
    before = store.authority["queries_used"]
    first = store.replay(_key(store))
    assert first["class"] == "recorded-replay"
    mid = store.authority["queries_used"]
    assert mid == before + 1
    second = store.replay(_key(store))
    assert second["class"] == "recorded-replay"
    after = store.authority["queries_used"]
    assert after == before + 2


def test_cached_serve_names_support_class_and_reason(tmp_path):
    store = _make_store(tmp_path)
    store.record_outcome(_key(store), {"y": [0, 1, 0, 1]})
    hit = store.replay(_key(store))
    assert hit["class"] == "recorded-replay"
    assert hit["outcome"] == {"y": [0, 1, 0, 1]}
    assert "cached-serve" in str(hit.get("reason", ""))
    assert hit.get("queries_charged") == 1


def test_near_miss_key_returns_unsupported(tmp_path):
    store = _make_store(tmp_path)
    store.record_outcome(_key(store, x=3), {"y": [0, 1, 0, 1]})
    before = store.authority["queries_used"]
    cases = [
        _key(store, x=4),
        _key(store, x=3, instrument="other-instrument"),
        _key(store, x=3, env="other-environment"),
        {"instrument": "boolean-rule-v1", "inputs": {"x": 3}},
        {"instrument": "boolean-rule-v1", "inputs": {"x": 3},
         "environment": store.environment_digest, "extra": 1},
        "not-a-dict",
    ]
    for bad in cases:
        verdict = store.replay(bad)
        assert verdict["class"] == "unsupported"
        assert verdict["class"] != "recorded-replay"
        assert verdict["class"] != "prediction"
    assert store.authority["queries_used"] == before


def test_exact_hit_replays(tmp_path):
    store = _make_store(tmp_path)
    store.record_outcome(_key(store, x=5), {"y": [1, 0, 1, 1]})
    hit = store.replay(_key(store, x=5))
    assert hit["class"] == "recorded-replay"
    assert hit["outcome"] == {"y": [1, 0, 1, 1]}


def test_prediction_never_returns_replay_verdict(tmp_path):
    store = _make_store(tmp_path)
    guess = store.predict(_key(store, x=4), {"y": [1, 1, 1, 1]})
    assert guess["class"] == "prediction"
    assert guess["class"] != "recorded-replay"
    assert guess["class"] != "unsupported"
    again = store.replay(_key(store, x=4))
    assert again["class"] == "unsupported"
    assert again["class"] != "recorded-replay"


def test_exhausted_budget_refuses_cached_serve(tmp_path):
    store = _make_store(tmp_path, queries=1, steps=8)
    store.record_outcome(_key(store), {"y": [0, 1, 0, 1]})
    first = store.replay(_key(store))
    assert first["class"] == "recorded-replay"
    with pytest.raises(frontier.Refused):
        store.replay(_key(store))
