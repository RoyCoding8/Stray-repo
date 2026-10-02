"""The admission guard must still refuse a forged experience observation.

`admit_investigation` compares the experience list against the durable
store before a proposal is accepted. The experience list is
`packet.project_observations` output, reduced to five fields so assessor
detail stays out of model prompts, which is why the comparison verifies
identity and provenance rather than whole-object equality.

Both directions are pinned here. A projected copy of a genuinely settled
observation is accepted, and an observation that merely claims a known id
is still refused.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import packet, trajectory

CHARTER = {"objective": "smaller valid explanatory examples", "freeze_id": "ad01"}

STORED = {
    "observation_id": "obs-c4-diagnostic-ad01-w0-dev-sw-00",
    "task_id": "ad01-w0-dev-sw-00",
    "capability_id": "seed-sw-greedy",
    "verdict": "ok-presence",
    "detail": {"control_id": "c4-diagnostic", "authored": True},
    "basis_references": ["obs-ad01-w0-dev-sw-00-seed"],
    "grounded": True,
    "queries": 0,
}


def _proposal():
    # `unknown` and a charter objective are what an exploratory option needs
    # to clear the later admission check, so these tests isolate the forgery
    # guard rather than tripping the rule after it.
    return {
        "proposal_id": "p-1",
        "next_action": {"kind": "diagnostic", "diagnostic": "software",
                        "task_id": "ad01-w0-dev-sw-01", "max_queries": 4},
        "basis_references": [],
        "requested_resources": {},
        "unknown": "whether the stale-read core is reachable in this world",
    }


def _admit(observations, durable, trusted=()):
    return trajectory.admit_investigation(
        _proposal(), {"observations": observations, "retained": []},
        CHARTER, {"world": 0, "arm": "I", "seq": 1},
        durable_observations=durable,
        trusted_observation_ids=trusted)


def test_a_projected_copy_of_a_stored_observation_is_accepted():
    projected = packet.project_observations([STORED])[0]
    assert sorted(projected) == ["capability_id", "detail",
                                 "observation_id", "task_id", "verdict"]
    assert _admit([projected], {STORED["observation_id"]: STORED})["decision"] \
        != "refused"


def test_the_whole_stored_record_is_also_accepted():
    assert _admit([STORED], {STORED["observation_id"]: STORED})["decision"] \
        != "refused"


def test_an_unknown_observation_id_is_refused():
    unknown = dict(STORED, observation_id="obs-never-stored")
    result = _admit([unknown], {STORED["observation_id"]: STORED})
    assert result["decision"] == "refused"
    assert "forged" in result["reason"]


def test_a_known_id_with_a_swapped_task_is_refused():
    tampered = packet.project_observations(
        [dict(STORED, task_id="ad01-w0-dev-sw-99")])[0]
    result = _admit([tampered], {STORED["observation_id"]: STORED})
    assert result["decision"] == "refused"
    assert "forged" in result["reason"]


def test_a_known_id_with_a_swapped_capability_is_refused():
    tampered = packet.project_observations(
        [dict(STORED, capability_id="someone-elses-method")])[0]
    result = _admit([tampered], {STORED["observation_id"]: STORED})
    assert result["decision"] == "refused"
    assert "forged" in result["reason"]


def test_a_known_id_with_a_swapped_verdict_is_refused():
    tampered = packet.project_observations(
        [dict(STORED, verdict="everything-is-fine")])[0]
    result = _admit([tampered], {STORED["observation_id"]: STORED})
    assert result["decision"] == "refused"
    assert "forged" in result["reason"]


def test_a_known_id_with_tampered_detail_is_refused():
    tampered = packet.project_observations(
        [dict(STORED, detail={"control_id": "attacker"})])[0]
    result = _admit([tampered], {STORED["observation_id"]: STORED})
    assert result["decision"] == "refused"
    assert "forged" in result["reason"]


def test_an_observation_with_no_id_is_refused():
    anonymous = packet.project_observations([dict(STORED, observation_id=None)])[0]
    result = _admit([anonymous], {STORED["observation_id"]: STORED})
    assert result["decision"] == "refused"
    assert "forged" in result["reason"]


def test_a_non_dict_observation_is_refused():
    result = _admit(["not-an-observation"], {STORED["observation_id"]: STORED})
    assert result["decision"] == "refused"
    assert "forged" in result["reason"]


def test_the_explicitly_trusted_seed_observation_is_still_accepted():
    seed = {"observation_id": "obs-ad01-w0-dev-sw-01-seed",
            "task_id": "ad01-w0-dev-sw-01", "capability_id": "seed-sw-greedy",
            "verdict": "unmeasured"}
    assert _admit([seed], {}, trusted=(seed["observation_id"],))[
        "decision"] != "refused"
