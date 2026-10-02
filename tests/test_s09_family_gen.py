"""Two new software generation families, and proof they are not duplicates.

The frozen panel's software family has four clusters and alpha 0.05 needs
six, so the shortfall is two families. The test that matters is
`test_a_relabelled_existing_family_is_not_a_new_family`: without it,
"one more task" and "one more family" look identical and the power problem
gets papered over by adding rows.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import s09_family_gen as gen
from experiments.ad01 import s09_panel_inventory as inv

FROZEN = ROOT / "experiments/ad01/worlds"


def _frozen_templates():
    return set(gen.frozen_software_templates(FROZEN))


def _frozen_forms():
    """Structural identity, finer than the cluster rule, for relabelling."""
    import pathlib
    forms = set()
    for path in sorted(pathlib.Path(FROZEN).rglob("*-sw-*.json")):
        forms.add(gen.canonical_form(json.loads(path.read_text())))
    return forms


def test_the_frozen_software_panel_really_has_four_clusters():
    """The cluster rule is `(family, template)`, as the frozen tool states."""
    templates = gen.frozen_software_templates(FROZEN)
    assert len(templates) == 4, templates
    assert inv.CLUSTER_RULE == "(family, template)"
    assert inv.minimum_clusters_for_alpha(0.05) == 6
    assert inv.minimum_sign_flip_p(4) == 0.125


def test_the_two_new_families_are_not_the_frozen_ones():
    existing = _frozen_templates()
    assert len(existing) == 4
    for template in gen.NEW_TEMPLATES:
        for world in range(3):
            for index in range(3):
                task = gen.generate(template, world, "dev", index)
                assert gen.is_new_family(task, existing), (
                    "%s world %d index %d collides with a frozen family"
                    % (template, world, index))


def test_the_two_new_families_are_distinct_from_each_other():
    forms = {t: {gen.canonical_form(gen.generate(t, w, "dev", i))
                 for w in range(3) for i in range(3)}
             for t in gen.NEW_TEMPLATES}
    left, right = (forms[t] for t in gen.NEW_TEMPLATES)
    assert not (left & right)


def test_every_task_of_one_family_shares_a_canonical_form():
    for template in gen.NEW_TEMPLATES:
        forms = {gen.canonical_form(gen.generate(template, w, "dev", i))
                 for w in range(3) for i in range(3)}
        assert len(forms) == 1, (template, len(forms))


def test_a_relabelled_existing_family_is_still_the_same_family():
    """The anti-duplication property, at the granularity that matters.

    The cluster rule is `(family, template)`, so a relabelled copy is the
    same family by the rule. The stronger property is that its structural
    canonical form is unchanged, which is what would catch a generator
    that produced the same fault under new names and called it new.
    """
    task = json.loads(sorted(FROZEN.rglob("*-sw-*.json"))[0].read_text())
    before = gen.canonical_form(task)

    renamed = copy.deepcopy(task)
    mapping = {"a": "zzz", "b": "yyy", "c": "xxx", "d": "www"}
    for op in renamed["ops"]:
        if "key" in op:
            op["key"] = mapping.get(op["key"], op["key"])
        if op.get("op") == "set":
            op["value"] = "renamed-%s" % op["value"]

    assert renamed != task, "the relabelling must actually change the task"
    assert gen.canonical_form(renamed) == before, (
        "relabelling changed the structural identity of %s" % task["task_id"])


def test_a_relabelled_new_family_keeps_its_form_too():
    for template in gen.NEW_TEMPLATES:
        task = gen.generate(template, 0, "dev", 0)
        renamed = copy.deepcopy(task)
        for op in renamed["ops"]:
            if "key" in op:
                op["key"] = {"a": "p", "b": "q", "c": "r", "d": "s"}[op["key"]]
            if op.get("op") == "set":
                op["value"] = "w%s" % op["value"]
        assert gen.canonical_form(renamed) == gen.canonical_form(task), template


def test_generation_is_deterministic_in_its_four_arguments():
    for template in gen.NEW_TEMPLATES:
        first = gen.generate(template, 1, "dev", 2)
        second = gen.generate(template, 1, "dev", 2)
        assert first == second
        assert gen.canonical_form(first) == gen.canonical_form(second)
    assert gen.generate("write-order-split", 0, "dev", 0) \
        != gen.generate("write-order-split", 0, "dev", 1)
    assert gen.generate("write-order-split", 0, "dev", 0) \
        != gen.generate("write-order-split", 0, "within", 0)


def test_generated_tasks_carry_the_panel_task_shape():
    for template in gen.NEW_TEMPLATES:
        task = gen.generate(template, 0, "dev", 0)
        assert sorted(task) == ["family", "fault", "ops", "seed",
                                "task_id", "template"]
        assert task["family"] == "software"
        assert task["template"] == template
        assert task["task_id"].startswith("ad01-w0-dev-")


def test_an_unknown_template_is_refused():
    with pytest.raises(ValueError):
        gen.generate("stale-read-2chain", 0, "dev", 0)


def test_the_two_new_families_take_software_to_six_clusters():
    """The point of the unit: the shortfall closes, by the cluster rule."""
    templates = set(_frozen_templates())
    for template in gen.NEW_TEMPLATES:
        templates.add(gen.generate(template, 0, "dev", 0)["template"])
    assert len(templates) == 6
    assert inv.minimum_sign_flip_p(6) < 0.05
