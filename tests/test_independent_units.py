"""Coarse witness-signature counts and their limited interpretation."""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import independent_units as iu
from experiments.ad01 import s09_panel_inventory as inv
from experiments.representation import software

FROZEN = ROOT / "experiments/ad01/worlds"


def _programs(max_length: int, values: tuple[str, ...]) -> list:
    """Every legal op program up to `max_length`, in a fixed order."""
    sets = [{"op": "set", "key": key, "value": value}
            for key in software.KEYS for value in values]
    gets = [{"op": "get", "key": key, "id": "w0"} for key in software.KEYS]
    alphabet = sets + gets + [{"op": "clear"}] + [
        {"op": "del", "key": key} for key in software.KEYS]
    programs = []
    for length in range(1, max_length + 1):
        programs.extend(list(combo) for combo in
                        itertools.product(alphabet, repeat=length))
    return programs


def test_the_panel_census_agrees_with_the_cluster_rule_it_reads_from():
    """The panel reports 4 software clusters and needs 6. That is the claim."""
    observation = iu.software_family_observation(FROZEN)
    assert observation.template_count == 4
    assert inv.CLUSTER_RULE == "(family, template)"
    assert inv.minimum_clusters_for_alpha(0.05) == 6


def test_the_software_panel_reaches_exactly_two_observable_behaviours():
    """The load-bearing negative. Four templates, two behaviours."""
    observation = iu.software_family_observation(FROZEN)
    assert observation.signature_count == 2, [s.as_tuple() for s in
                                              observation.signatures]
    assert [s.as_tuple() for s in observation.signatures] == [
        ("stale-clear", software.MISSING, software.PRESENT),
        ("stale-read", software.PRESENT, software.PRESENT),
    ]


def test_every_software_template_reports_its_coarse_witness_signature():
    observation = iu.software_family_observation(FROZEN)
    stale_read_templates = {
        name for name, sigs in observation.signatures_by_template.items()
        if sigs == (iu.Signature("stale-read", software.PRESENT,
                                 software.PRESENT),)}
    assert stale_read_templates == {"stale-read-2chain", "stale-read-3chain"}
    stale_clear_templates = {
        name for name, sigs in observation.signatures_by_template.items()
        if sigs == (iu.Signature("stale-clear", software.MISSING,
                                 software.PRESENT),)}
    assert stale_clear_templates == {"stale-clear-core",
                                     "stale-clear-del-core"}


def test_the_surplus_templates_are_the_whole_shortfall_and_more():
    """4 templates, 2 behaviours: the 2 surplus cancel against the 2 missing."""
    observation = iu.software_family_observation(FROZEN)
    assert observation.collapses is True
    assert observation.surplus_templates == 2
    assert observation.signature_count == observation.template_count - 2


def test_programs_up_to_length_five_with_two_values_reach_two_signatures():
    """Exhaustive over this bounded alphabet, not all accepted programs."""
    programs = _programs(max_length=5, values=("v1", "v2"))
    reached = iu.reachable_software_signatures(programs)
    assert len(programs) == 402233, len(programs)
    assert {s.as_tuple() for s in reached} == {
        ("stale-clear", software.MISSING, software.PRESENT),
        ("stale-read", software.PRESENT, software.PRESENT),
    }


def test_the_absent_behaviour_is_absent_from_the_vocabulary_not_just_unreached():
    """Name what a third family would have to be, so its absence is specific."""
    space = iu.observable_space()
    reached = iu.reachable_software_signatures(
        _programs(max_length=4, values=("v1", "v2")))
    absent = {s.as_tuple() for s in space - reached}
    assert absent == {
        ("stale-clear", software.MISSING, software.MISSING),
        ("stale-clear", software.PRESENT, software.MISSING),
        ("stale-clear", software.PRESENT, software.PRESENT),
        ("stale-read", software.MISSING, software.MISSING),
        ("stale-read", software.MISSING, software.PRESENT),
        ("stale-read", software.PRESENT, software.MISSING),
    }


def test_a_forged_witness_is_reported_by_what_the_task_does():
    """A stored witness that disagrees with the operations must not be read.

    `signature_of` recomputes through the world's runners. A task claiming
    a behaviour its ops cannot produce is reported by the behaviour the ops
    produce, which is the only one a learner could ever observe.
    """
    path = sorted(FROZEN.rglob("*-sw-*.json"))[0]
    task = json.loads(path.read_text())
    honest = iu.signature_of(task)

    forged = json.loads(json.dumps(task))
    forged["witness"]["faulty"] = {"type": software.MISSING, "value": None}
    assert forged["witness"] != task["witness"]
    assert iu.signature_of(forged) == honest


def test_the_report_states_the_gap_in_words_and_numbers():
    report = iu.software_report(FROZEN)
    assert report["template_count"] == 4
    assert report["signature_count"] == 2
    assert report["collapses"] is True
    assert report["surplus_templates"] == 2
    assert report["reading"] == (
        "4 template names span 2 coarse witness signatures. "
        "This projection does not measure statistical independence.")
    assert len(report["unreachable_in_observable_space"]) == 6


def test_the_observable_vocabulary_has_no_third_type():
    """`parse_ops` admits exactly two observation types, so the space is 4."""
    assert iu.OBSERVATION_TYPES == (software.MISSING, software.PRESENT)
    assert len(iu.observable_space()) == 4 * len(software.FAULTS)


def test_an_illegal_program_is_refused_rather_than_counted():
    """A generator emitting malformed ops must not inflate the signature count."""
    illegal = [[{"op": "set", "key": "z", "value": "v1"}],
               [{"op": "get", "key": "a", "id": "w0"},
                {"op": "get", "key": "a", "id": "w0"}],
               [{"op": "nonsense", "key": "a"}]]
    assert iu.reachable_software_signatures(illegal) == set()
