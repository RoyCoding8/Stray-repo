"""The finite support of the SWE instrument, computed rather than asserted.

Nothing here hardcodes a wish. Counts are derived from the catalogue, and
instance identity is a program-plus-mechanism key, not a seed.
"""

from __future__ import annotations

from experiments.ad01 import s09_swe_tasks as tasks


def test_the_catalogue_enumerates_at_least_twenty_four_held_out_instances():
    held_out = tasks.enumerate_instances("held_out")

    assert len(held_out) == 30
    assert len(held_out) >= 24


def test_held_out_instances_are_distinct_by_program_and_mechanism():
    held_out = tasks.enumerate_instances("held_out")
    identities = [(record["template"], record["mechanism"]) for record in held_out]

    assert len(set(identities)) == len(identities)
    assert len(set(identities)) == len(held_out)
    assert len({record["task_id"] for record in held_out}) == len(held_out)


def test_distinct_instances_really_carry_distinct_faulty_programs():
    held_out = tasks.enumerate_instances("held_out")
    programs = {
        tasks.render_source(record["source"]) + "|" + record["mechanism"]
        for record in held_out
    }

    assert len(programs) == len(held_out)


def test_no_development_fault_family_appears_in_the_held_out_split():
    dev_families = {record["mechanism"] for record in
                    tasks.enumerate_instances("dev")}
    held_out_families = {record["mechanism"] for record in
                         tasks.enumerate_instances("held_out")}

    assert dev_families.isdisjoint(held_out_families)
    assert len(held_out_families) == 5
    assert dev_families | held_out_families == set(tasks.MECHANISMS)


def test_no_program_template_appears_in_both_splits():
    dev_templates = {record["template"] for record in
                     tasks.enumerate_instances("dev")}
    held_out_templates = {record["template"] for record in
                          tasks.enumerate_instances("held_out")}

    assert dev_templates.isdisjoint(held_out_templates)
    assert len(held_out_templates) == 6


def test_task_families_are_pairs_of_structure_and_fault_mechanism():
    held_out = tasks.enumerate_instances("held_out")
    families = {(record["structure"], record["mechanism"]) for record in held_out}

    assert len(families) == 15
    assert len(families) >= 4
    assert {structure for structure, _ in families} == set(tasks.STRUCTURES)
    assert {mechanism for _, mechanism in families} == \
        set(tasks.HELD_OUT_MECHANISMS)


def test_every_program_structure_carries_every_held_out_mechanism():
    for structure in tasks.STRUCTURES:
        mechanisms = {
            record["mechanism"] for record in tasks.enumerate_instances("held_out")
            if record["structure"] == structure
        }

        assert len(mechanisms) == 5
        assert mechanisms == set(tasks.HELD_OUT_MECHANISMS)


def test_the_three_program_structures_are_structurally_distinct():
    shapes = {structure: set() for structure in tasks.STRUCTURES}
    for program in tasks.PROGRAMS:
        source = tasks.render_source(
            program.render(tasks.reference_variants(program)))
        shapes[program.structure].add(_shape(source))

    assert all(shapes[structure] for structure in tasks.STRUCTURES)
    assert len({frozenset(value) for value in shapes.values()}) == 3
    while_kind = {structure: any("while" in shape for shape in value)
                  for structure, value in shapes.items()}
    assert sum(while_kind.values()) == 1
    assert while_kind["state_machine"] is True


def _shape(source: str) -> str:
    import ast

    tree = ast.parse(source)
    kinds = []
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            kinds.append("for")
        elif isinstance(node, ast.While):
            kinds.append("while")
        elif isinstance(node, ast.If):
            kinds.append("if")
        elif isinstance(node, ast.Compare):
            kinds.append("compare")
        elif isinstance(node, ast.Subscript):
            kinds.append("subscript")
    return " ".join(sorted(kinds))


def test_every_catalogue_instance_is_solvable_by_restoring_its_reference():
    for record in tasks.enumerate_instances("dev") + \
            tasks.enumerate_instances("held_out"):
        outcome = tasks.score(record, record["reference_source"])

        assert outcome["outcome"] == "repaired", record["task_id"]


def test_every_catalogue_instance_fails_while_its_fault_is_present():
    for record in tasks.enumerate_instances("dev") + \
            tasks.enumerate_instances("held_out"):
        outcome = tasks.score(record, record["source"])

        assert outcome["outcome"] == "unrepaired", record["task_id"]


def test_the_finite_support_of_each_split_is_reported_by_the_catalogue():
    support = tasks.support()

    assert support["dev"] == 9
    assert support["held_out"] == 30
    assert support["templates"] == 9
    assert support["structures"] == 3
    assert support["mechanisms"] == 8
    assert support["dev_families"].isdisjoint(support["held_out_families"])
