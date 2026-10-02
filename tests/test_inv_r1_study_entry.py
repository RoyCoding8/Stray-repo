

def test_every_used_world_is_also_acquired_in():
    """A policy can only be used where it was acquired.

    The first completed M3 run acquired in the calibration world alone and
    used only the comparison worlds, so all twenty-four use records refused
    with an empty repertoire. That is a design gap rather than a wiring bug,
    and this is the check that keeps it from returning.
    """
    from scripts import inv01_study as S

    acquired = {world for world, _ in S._v1_specs(6)}
    used = set(S._v1_use_worlds())

    assert used, "the use phase must run over at least one world"
    assert used <= acquired, (
        "used but never acquired: %s" % sorted(used - acquired))
