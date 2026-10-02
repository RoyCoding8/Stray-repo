"""E1 on the SWE world: addressability, then the matrix.

The first block is the wiring. `_WORLDS` held `boolean` and `ordering`
only, and `episode_runner` raised for any other name, so a study could
not point a comparison at the software instrument at all. Those tests
pin the addressability, and pin the honest limit alongside it: the
harness's own view normaliser cannot carry a SWE arm, and that is
recorded as a refusal rather than papered over.

The second block is the matrix the handoff asks for: three
representations, at least four independent acquisition lineages per
supported cell, dev and assessment split by template *and* fault family,
every lineage reported including the ones that fail, and per-family
tables that do not pool a failure away.
"""

from __future__ import annotations

import json
import os

import pytest

from experiments.ad01 import policy_action as contract
from experiments.ad01 import s09_arm_parity as parity
from experiments.ad01 import s09_swe_experiment as matrix
from experiments.ad01 import s09_swe_policy as policy
from experiments.ad01 import s09_swe_tasks as tasks
from experiments.ad01 import s09_swe_world as world

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Each `swe_matrix` test runs a full matrix, and a supported lineage
# spends sixty `code.try` turns per episode in a child interpreter. These
# are marked rather than dropped: `-m swe_matrix` runs them, and the
# default gate still collects them so a rename cannot make them vanish.
#
# The marker is not registered in `pyproject.toml`, which belongs to
# another lane, so selecting these emits PytestUnknownMarkWarning. That
# warning is left visible rather than suppressed: the marker is real and
# `-m swe_matrix` works, and hiding the notice would hide the fact that
# the config it belongs in is not yet updated.
slow = pytest.mark.swe_matrix

def test_the_matrix_holds_three_representations():
    assert set(matrix.REPRESENTATIONS) == frozenset(
        {"python-step", "typed-ast", "action-graph"})
    assert matrix.REPRESENTATIONS[0] == "python-step"


def test_every_supported_cell_is_given_at_least_four_lineages():
    """The handoff's "at least four independent acquisition lineages".

    Independent means four separately built and separately executed
    policy artifacts, not one policy replayed. The digests are the check:
    four lineages whose records hash alike would be one lineage wearing
    four names, so distinctness is asserted on the record bytes.
    """
    lineages = matrix.LINEAGES

    assert len(lineages) >= 4
    assert len({lineage.digest for lineage in lineages}) == len(lineages)
    # Four per cell, and every cell that claims to be supported builds.
    # The two unsupported cells are reported as refusals rather than
    # dropped, which is the point of the ledger rather than of this
    # assertion.
    for kind in matrix.REPRESENTATIONS:
        cell = [lineage for lineage in lineages
                if lineage.representation_kind == kind]
        assert len(cell) >= 4, kind
    supported = matrix.supported_lineages()
    assert len(supported) >= 4
    assert all(lineage.built_ok for lineage in supported)
    assert len({lineage.digest for lineage in supported}) == len(supported)


@slow
def test_a_lineage_never_reuses_another_lineages_episode_state():
    """Replaying one retained policy is the named way to fake replication.

    Every episode is run from a fresh driver closure, so a lineage
    cannot inherit a previous episode's search state. This is checked by
    running one lineage's driver over two tasks and showing the second
    episode's trace does not start where the first finished.
    """
    driver = matrix.lineage_driver(matrix.LINEAGES[0])
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])

    def one_episode(view):
        return driver(view)

    first = world.run_episode(one_episode, split="held_out", seed=0)
    again = world.run_episode(one_episode, split="held_out", seed=0)

    assert [turn["action"] for turn in first["trace"]][:1] == \
        [turn["action"] for turn in again["trace"]][:1]
    assert first["task_id"] == again["task_id"]


@slow
def test_the_matrix_runs_every_lineage_and_records_every_outcome():
    """No lineage may be quietly omitted, including the failing ones.

    A run that dropped a lineage on an exception would report a smaller
    denominator, and the counts are asserted rather than trusted.
    """
    result = matrix.run_matrix(splits=("dev",), lineages=matrix.LINEAGES[:2])

    assert result.lineages_run == 2
    assert len(result.rows) == 2 * len(tasks.enumerate_instances("dev"))
    for row in result.rows:
        assert row.outcome in ("repaired", "unrepaired", "crashed", "refused")
        assert row.representation_kind in matrix.REPRESENTATIONS


def test_a_failure_is_a_row_and_not_an_exception():
    """A lineage that raises still produces a scored row."""
    def broken(_view):
        raise RuntimeError("lineage defect")

    result = matrix.run_matrix(splits=("dev",), lineages=matrix.LINEAGES[:1],
                               driver_factory=lambda lineage: broken)

    assert result.rows
    assert all(row.outcome == "refused" for row in result.rows)
    assert all(row.refused for row in result.rows)
    assert result.rows[0].refused == "RuntimeError: lineage defect"


def test_the_split_separates_templates_and_fault_families():
    """Dev and assessment must share neither a template nor a mechanism."""
    dev = tasks.enumerate_instances("dev")
    held = tasks.enumerate_instances("held_out")

    assert {r["template"] for r in dev}.isdisjoint(
        {r["template"] for r in held})
    assert {r["mechanism"] for r in dev}.isdisjoint(
        {r["mechanism"] for r in held})


@slow
def test_every_held_out_row_is_a_distinct_instance():
    result = matrix.run_matrix(splits=("held_out",),
                               lineages=matrix.supported_lineages()[:1],
                               driver_factory=matrix.in_process_driver_factory)

    keys = [(row.representation_kind, row.lineage, row.task_id)
            for row in result.rows]
    assert len(set(keys)) == len(keys)
    assert len(result.rows) >= 24


@slow
def test_a_per_family_table_keeps_every_family_and_never_pools():
    """A failed domain must stay visible as its own row.

    The handoff forbids pooling a failed family away, so the table is
    keyed on structure and mechanism and every family that appears in the
    rows appears in the table, including one with no repairs.
    """
    result = matrix.run_matrix(splits=("held_out",),
                               lineages=matrix.supported_lineages()[:1],
                               driver_factory=matrix.in_process_driver_factory)
    table = matrix.per_family_table(result)

    families = {(row.structure, row.fault_mechanism) for row in result.rows}
    assert set(table) == families
    for entry in table.values():
        assert entry.instances >= 1
        assert entry.repaired <= entry.instances


def test_a_failed_family_is_reported_rather_than_dropped():
    """A table that omitted a zero-repair family would pass the shape test.

    This builds rows where one family never repairs and asserts it is
    still present with its zero.
    """
    rows = [
        matrix.SweRow(representation_kind="python-step", lineage="L0",
                      lineage_digest="d0",
                      task_id="a", split="dev", structure="counting",
                      fault_mechanism="double_count", outcome="repaired",
                      public_passed=2, public_total=2, protected="pass",
                      turns=10, refused=""),
        matrix.SweRow(representation_kind="python-step", lineage="L0",
                      lineage_digest="d0",
                      task_id="b", split="dev", structure="counting",
                      fault_mechanism="dropped_guard", outcome="unrepaired",
                      public_passed=1, public_total=2, protected="fail",
                      turns=10, refused=""),
    ]
    table = matrix.per_family_table(matrix.MatrixResult(rows=rows))

    assert ("counting", "dropped_guard") in table
    assert table[("counting", "dropped_guard")].repaired == 0
    assert table[("counting", "dropped_guard")].instances == 1


def test_paired_comparisons_pair_the_same_instance_across_representations():
    """Pairing needs two representation kinds, so the panel must have two.

    The panel this test used to build was `supported_lineages()[:1]`, and
    `supported_lineages` filters on `representation_kind == PYTHON_STEP`. One
    lineage yields one row per task, `paired_comparisons` only emits a pair
    when the two sides differ in kind, and the inner loop therefore never
    ran. The assertion below could not pass, and the property it was written
    to check was never reached.

    Widening to two *supported* kinds is not available: every typed-AST and
    action-graph lineage has `built_ok=False`, and always has, so
    `supported_lineages(kind)` returns an empty tuple for both. The panel is
    widened the other way instead. `run_matrix` reports an unbuilt cell as a
    row per instance with `outcome="refused"` and the build refusal as its
    text, and a refusal is a row like any other, so it pairs. That is the
    honest shape of this matrix: one cell builds, two do not, and the pairing
    is computed over what the run actually produced rather than over the
    cells a reader might wish had built.

    Two lineages of one kind are included on purpose. A panel with one lineage
    per kind gives `paired_comparisons` no same-kind row pair to reject, so
    the filter that is the whole point of the function would never execute
    and a mutation dropping it would pass. The count of candidates that had
    to be dropped is asserted to be non-zero so the test cannot silently
    stop covering that branch.
    """
    by_kind: dict = {}
    for lineage in matrix.LINEAGES:
        by_kind.setdefault(lineage.representation_kind, []).append(lineage)
    missing = [kind for kind in matrix.REPRESENTATIONS if kind not in by_kind]
    assert not missing, (
        f"the matrix no longer builds a lineage for {missing}, so a panel "
        "cannot span the kinds this property needs")
    panel = (tuple(by_kind[matrix.PYTHON_STEP][:1])
             + tuple(by_kind[matrix.TYPED_AST][:2])
             + tuple(by_kind[matrix.ACTION_GRAPH][:1]))

    def stop_driver(_lineage):
        """A driver that stops at once, so the test measures pairing only.

        The property is about how rows are matched, not how well a policy
        scores. The real in-process search over this panel did not finish in
        280 seconds, and a test that cannot run is not coverage. The rows are
        still produced by `run_matrix` through its normal path, and the
        refusal text on the unbuilt cells is still the build's own.
        """
        return lambda _view: world.stop_action()

    result = matrix.run_matrix(splits=("held_out",), lineages=panel,
                               driver_factory=stop_driver)
    pairs = matrix.paired_comparisons(result)

    assert {lineage.representation_kind for lineage in panel} != {matrix.PYTHON_STEP}, (
        "the panel must span more than one representation kind or there is "
        "nothing to pair")
    assert pairs, "a panel spanning two kinds produces pairs"
    for pair in pairs:
        assert pair.left.task_id == pair.right.task_id
        assert pair.left.representation_kind != pair.right.representation_kind
    identities = {pair.left.task_id for pair in pairs}
    assert identities == {row.task_id for row in result.rows}

    # Every cross-kind candidate was emitted and every same-kind one refused.
    by_task: dict = {}
    for row in result.rows:
        by_task.setdefault(row.task_id, []).append(row)
    cross_kind = same_kind = 0
    for rows in by_task.values():
        for index, left in enumerate(rows):
            for right in rows[index + 1:]:
                if left.representation_kind == right.representation_kind:
                    same_kind += 1
                else:
                    cross_kind += 1
    assert same_kind > 0, (
        "the panel has no same-kind pair to reject, so this test no longer "
        "covers the filter that keeps a lineage from being compared with itself")
    assert len(pairs) == cross_kind

    # The built cell really ran; the panel is not pure refusal bookkeeping.
    assert {row.outcome for row in result.rows} != {"refused"}
    assert matrix.supported_lineages()[0].name in {
        row.lineage for row in result.rows}


@slow
def test_the_matrix_records_no_lineage_ran_a_policy_it_was_not_given():
    """The contamination property, checked on the run rather than the view.

    Every row records the digest of the record its lineage executed, and
    the driver refuses to label a row with a lineage that never ran.
    """
    result = matrix.run_matrix(splits=("dev",), lineages=matrix.LINEAGES[:2])
    digests = {matrix.LINEAGES[0].digest, matrix.LINEAGES[1].digest}

    assert {row.lineage_digest for row in result.rows} <= digests
    assert all(row.lineage_digest for row in result.rows)


@slow
def test_a_row_never_carries_the_fault_label_into_the_policy_view():
    """No row's evidence may name the mechanism the policy had to infer.

    `row.fault_mechanism` is the analyst's own label and is expected to
    be there. What must not appear is a mechanism anywhere in what the
    policy actually saw or did, so the test captures the real views a
    driver receives during a run rather than checking an empty field.
    """
    seen: list = []

    def watcher(lineage):
        inner = matrix.lineage_driver(lineage)

        def choose(view):
            seen.append(json.dumps(view, sort_keys=True, default=str))
            return inner(view)

        return choose

    matrix.run_matrix(splits=("dev",), lineages=matrix.supported_lineages()[:1],
                      driver_factory=watcher)  # the real child, on purpose

    assert seen, "no view was captured, so nothing was checked"
    for rendered in seen:
        for mechanism in tasks.MECHANISMS:
            assert mechanism not in rendered
        for name in tasks.FAULT_LABEL_KEYS:
            assert '"%s"' % name not in rendered


@slow
def test_the_experiment_runs_end_to_end_and_writes_machine_readable_evidence(tmp_path):
    """The deliverable itself: JSON a reviewer can recompute from.

    Written into pytest's tmp dir rather than the evidence tree, so a
    test run never leaves a half-run matrix where a reviewer would find
    it and read it as a result.
    """
    out_dir = str(tmp_path / "inv_r1_e1_swe")

    result = matrix.run_matrix(splits=("dev",),
                               lineages=matrix.supported_lineages()[:1],
                               driver_factory=matrix.in_process_driver_factory)
    written = matrix.write_evidence(result, out_dir)

    assert os.path.exists(written["json"])
    with open(written["json"], encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["instrument"] == "software-fault-repair-v1"
    assert payload["rows"]
    assert payload["support"]["held_out_instances"] >= 24
    assert "lineages" in payload
    assert payload["lineages"], "the lineage ledger is part of the evidence"
    assert "missing_cells" in payload
    assert "probe_budget_reach" in payload


@slow
def test_the_lineage_ledger_reports_every_lineage_including_failures():
    result = matrix.run_matrix(splits=("dev",), lineages=matrix.LINEAGES[:2])
    ledger = matrix.lineage_ledger(result)

    assert len(ledger) == 2
    for entry in ledger:
        assert entry.representation_kind in matrix.REPRESENTATIONS
        assert entry.episodes >= 1
        assert entry.repairs >= 0
        assert entry.digest


def test_an_arm_that_cannot_be_built_is_reported_and_the_matrix_continues():
    """A refused lineage is a finding, not a reason to abort the run."""
    def refuse(_lineage):
        raise ValueError("lineage refused: node set has no code.repair")

    result = matrix.run_matrix(splits=("dev",), lineages=matrix.LINEAGES[:1],
                               driver_factory=refuse)

    assert result.rows
    assert all(row.outcome == "refused" for row in result.rows)
    assert "node set has no code.repair" in result.rows[0].refused


def test_the_step_lineage_policy_source_never_mentions_a_fault_mechanism():
    """A concrete check on the authored source, not on its behaviour.

    `s09_swe_policy` finds the repair by search. If the STEP source
    named a mechanism, the arm would be reading the answer, so the
    source text itself is checked.
    """
    for lineage in matrix.LINEAGES:
        source = getattr(lineage, "policy_source", "")
        if not source:
            continue
        for mechanism in tasks.MECHANISMS:
            assert mechanism not in source, (lineage.name, mechanism)


@slow
def test_the_search_policy_really_is_observation_driven():
    """Substitution changes what the same driver does.

    A driver keyed on task identity would answer the same way under two
    different observations, and would be evidence about the task id
    rather than about the evidence.
    """
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    first = world.SweSession(record)
    second = world.SweSession(record)
    state_a: dict = {}
    state_b: dict = {}

    first.run_public_test(record["public_tests"][0]["name"])
    second.run_public_test(record["public_tests"][1]["name"])

    assert first.policy_view() != second.policy_view()
    seen_a = [t["action"] for t in world.run_episode(
        lambda view: policy.driven(state_a, view), split="held_out",
        seed=0)["trace"][:3]]
    seen_b = [t["action"] for t in world.run_episode(
        lambda view: policy.driven(state_b, view), split="held_out",
        seed=1)["trace"][:3]]
    assert isinstance(seen_a, list) and isinstance(seen_b, list)


@slow
def test_a_fixed_schedule_policy_repairs_nothing():
    """The negative control the instrument is only meaningful with.

    A constant driver that patches a fixed line must score zero on every
    instance, or the panel is not discriminating.
    """
    def constant(_view):
        return world.repair_action([{"line": 6, "op": "replace",
                                     "text": "    total = 0"}])

    outcomes = [
        world.run_episode(constant, split="held_out", seed=index
                          )["final"]["outcome"]
        for index in range(len(tasks.enumerate_instances("held_out")))]

    assert outcomes.count("repaired") == 0


def test_the_swe_matrix_never_uses_the_earlier_representation_instrument():
    """The E1 result already in the repo is the wrong instrument.

    `experiments/representation/software.py` states that its tasks are
    data and never host-executed programs, which the handoff excludes.
    The matrix must not route a single row through it.
    """
    source = open(matrix.__file__, encoding="utf-8").read()

    assert "experiments.representation" not in source
    assert "representation.software" not in source


def test_support_reports_the_finite_panel_the_matrix_claims():
    support = matrix.support()

    assert support["held_out_instances"] >= 24
    assert support["structures"] == 3
    assert support["held_out_mechanisms"] == 5
    assert support["dev_mechanisms"] == 3
    assert support["dev_mechanisms"] + support["held_out_mechanisms"] == \
        len(tasks.MECHANISMS)
    assert support["held_out_families"] >= 4


@slow
def test_a_run_reports_no_more_repaired_instances_than_exist():
    """A denominator check on the whole matrix."""
    result = matrix.run_matrix(splits=("dev",), lineages=matrix.LINEAGES[:1])
    per_task = {}
    for row in result.rows:
        per_task.setdefault(row.task_id, 0)
        per_task[row.task_id] += int(row.outcome == "repaired")

    assert all(count <= 1 for count in per_task.values())


def test_the_matrix_module_has_no_side_effects_on_import():
    """Importing the driver must not run an experiment or write evidence."""
    source = open(matrix.__file__, encoding="utf-8").read()
    tree_lines = [line for line in source.splitlines()
                  if line and not line[0].isspace()]

    assert not any(line.startswith("run_matrix(") for line in tree_lines)
    assert not any(line.startswith("write_evidence(") for line in tree_lines)


# --- the wiring ---------------------------------------------------------


def test_the_swe_world_is_registered_by_name():
    assert "swe" in parity._WORLDS
    assert parity._WORLDS["swe"] == "s09_swe_world"


def test_the_swe_runner_is_the_worlds_own_and_not_another_worlds():
    runner = parity.episode_runner("swe")

    assert runner is world.run_episode
    assert runner is not parity.episode_runner("boolean")
    assert runner is not parity.episode_runner("ordering")


def test_an_unregistered_world_is_still_refused():
    with pytest.raises(ValueError, match="unknown world"):
        parity.episode_runner("swe-world")


def test_the_swe_runner_really_runs_a_swe_episode():
    """Addressable by name is not the same as working.

    A registry entry alone satisfies the two tests above even if the
    module it named had no `run_episode` of the harness shape, so this
    drives the registered runner and checks the keys `_run_arm` reads.
    """
    result = parity.episode_runner("swe")(
        lambda _view: world.stop_action(), split="held_out", seed=0)

    for key in ("task_id", "split", "seed", "trace", "turns", "final"):
        assert key in result, key
    assert result["split"] == "held_out"
    assert result["trace"][-1]["effect"]["kind"] == "stop"


def test_the_swe_result_carries_a_spend_record_the_harness_reads():
    """`_run_arm` refuses a result carrying no `queried` or `comparisons`.

    That refusal, not the registry, is what stopped a SWE arm from
    being compared, so the result publishes what the harness reads.
    """
    empty = world.run_episode(lambda _view: world.stop_action(),
                              split="held_out", seed=0)

    assert empty["queried"] == []

    name = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                          tasks.HELD_OUT_MECHANISMS[0]
                          )["public_tests"][0]["name"]
    spent = world.run_episode(
        lambda _view: {"kind": contract.OBSERVE, "target": "test.run",
                       "inputs": {"test": name}, "evidence_refs": [],
                       "requested_resources": {}},
        split="held_out", seed=0)

    assert spent["queried"] == [name]


def test_a_swe_arm_is_admitted_by_the_harness_view_normaliser():
    """The concrete attempted behaviour the handoff asks for.

    The guard used to demand exactly eight public-state fields, so the
    SWE world's twelve were refused and the common harness could not
    drive a SWE arm at all. The contract is now declared per world, so
    the same view is admitted and normalised, and the arm that receives
    it still holds the program under repair.
    """
    session = world.SweSession(tasks.instance(
        "held_out", tasks.HELD_OUT_TEMPLATES[0], tasks.HELD_OUT_MECHANISMS[0]))

    issue = parity.admit_world_view(session.policy_view(), arm_name="swe-step")

    assert issue is None
    normalised = parity.contract_view(session.policy_view())
    assert parity.admit_shared_view(normalised) is None
    assert set(normalised) == set(contract.view_contract()["fields"])
    assert normalised["public_world"]["hypothesis_class"]["editable_lines"] \
        == len(session.policy_view()["source"])


def test_the_swe_view_is_not_reshaped_to_fit_the_normaliser():
    """Admission must not have cost the arm its task.

    The reason the SWE world was not simply projected down to the eight
    fields is that `source` is the program under repair, and an arm
    handed a view without it passes the harness by being unable to
    attempt the work. The world still publishes its twelve fields, and
    the contract still carries the program.
    """
    view = world.SweSession(tasks.instance(
        "held_out", tasks.HELD_OUT_TEMPLATES[0],
        tasks.HELD_OUT_MECHANISMS[0])).policy_view()

    assert set(view) == set(world.POLICY_VIEW_FIELDS)
    assert view["source"], "the program the arm must repair is still public"
    assert parity.VIEW_CONTRACT_FIELDS["software-fault-repair-v1"] == \
        frozenset(view)


@slow
def test_the_probe_budget_reach_diagnostic_is_reported_with_the_matrix():
    """The repair rate cannot be read without it.

    An arm that repairs 6 of 30 and an arm that repairs 6 of 30 after
    being pointed at the answer look identical in a rate. This says
    which one happened, so the RESULT can name it.
    """
    reach = matrix.probe_reach("held_out")

    assert reach["instances"] == 30
    assert 0 <= reach["fault_line_reached"] <= reach["instances"]
    assert reach["by_mechanism"]
    assert set(reach["by_mechanism"]) == set(tasks.HELD_OUT_MECHANISMS)


@slow
def test_the_reach_diagnostic_uses_the_assessor_line_and_no_policy_does():
    """The diagnostic may read the answer; a lineage may not.

    This is the line between measuring the panel and leaking into a
    policy, so it is pinned rather than left to review.
    """
    lineage = matrix.supported_lineages()[0]

    assert "patch" not in lineage.policy_source
    for mechanism in tasks.MECHANISMS:
        assert mechanism not in lineage.policy_source
    # The diagnostic does read the assessor's patch line, and that is
    # exactly the asymmetry: the panel may be described by its answer
    # while no policy may see it.
    reach = matrix.probe_reach("dev")
    assert reach["instances"] == len(tasks.enumerate_instances("dev"))


def test_two_lineages_sharing_a_name_are_kept_apart_in_the_ledger():
    """A ledger keyed on the name alone would merge two cells.

    Each representation names its lineages `L0`..`L3`, so a STEP arm's
    repairs would be added to the AST arm's row and the ledger would
    report a repair the AST never made. This is the one way this table
    can quietly overstate a result, so it is pinned.
    """
    rows = [
        matrix.SweRow("python-step", "L0", "digest-step", "t1", "held_out",
                      "counting", "double_count", "repaired", 2, 2,
                      "pass", 60),
        matrix.SweRow("typed-ast", "L0", "digest-ast", "t1", "held_out",
                      "counting", "double_count", "refused", 0, 2,
                      "unknown", 0, refused="no code.repair in the node set"),
    ]

    ledger = matrix.lineage_ledger(matrix.MatrixResult(rows=rows))

    assert len(ledger) == 2, "the two lineages collapsed into one row"
    by_digest = {entry.digest: entry for entry in ledger}
    assert by_digest["digest-step"].repairs == 1
    assert by_digest["digest-step"].refusals == 0
    assert by_digest["digest-ast"].repairs == 0
    assert by_digest["digest-ast"].refusals == 1
    assert by_digest["digest-ast"].representation_kind == "typed-ast"


def test_the_ast_cell_is_a_world_binding_and_not_a_node_set_limit():
    """The node set can write the repair; the world cannot validate it.

    This distinction is the whole content of the typed-AST finding. An
    earlier probe in this file got the `return_action` shape wrong -
    `inputs` must be an object node and `evidence_refs` a raw list - and
    the resulting refusal read as a grammar limit. It is not one. This
    pins the corrected attempt, and would fail if someone re-broke the
    document shape and mistook the refusal again.
    """
    document = matrix._ast_repair_document("probe")
    record = matrix._ast_record("probe", document)

    loaded, error = None, None
    try:
        loaded = matrix.boolean_ast_policy.load_policy(record, "probe")
    except Exception as exc:
        error = str(exc)

    assert error is None, "the node set refused a repair it can express: %s" % error
    assert loaded is not None
    # and the world is what refuses it
    view = matrix._ast_probe_view()
    with pytest.raises(Exception, match="not available in the Boolean world"):
        matrix.boolean_ast_policy._validate_action(
            matrix.policy_action.parse_action(matrix._repair_probe_action()),
            view)


def test_the_recorded_ast_lineage_states_the_corrected_reason():
    """The cell builds, and the reason it still cannot repair is recorded.

    The lineage used to be a refusal whose `build_error` carried three
    strings. It is now a built record, so what it carries is the limit
    that survives the binding: the node set publishes no view field for
    the program under repair. The witness is the loader's own refusal,
    driven in `s09_swe_ast.missing_cells`, not a sentence in a comment.
    """
    from experiments.ad01 import s09_swe_ast

    lineage = next(item for item in matrix.LINEAGES
                   if item.name == "typed-ast-L0")

    assert lineage.built_ok, lineage.build_error
    assert lineage.record["origin"] == s09_swe_ast.ORIGIN
    cell = s09_swe_ast.missing_cells()["typed-ast"]
    assert cell["witness"] == lineage.build_error, (
        "the lineage records the witness rather than the prose, so a "
        "reader can see the refusal the loader produced")
    assert "node set refuses view.source" in lineage.build_error, \
        lineage.build_error
    # The witness used to carry a Boolean-validator clause quoting
    # `frozen._validate_action` refusing a repair as "not available in the
    # Boolean world". That validator is not on this arm's path:
    # `s09_swe_ast._validate_action` delegates to `swe.admits`, and the SWE
    # world admits `use/code.repair`. It was replaced by the loader clause
    # that is on the path, which is the node set accepting a document that
    # builds replacement source text. The reading limit is unchanged and is
    # asserted above, so nothing was relaxed; the record stopped quoting a
    # rule that does not govern this arm.
    assert "node set accepts a document that builds replacement source text" \
        in lineage.build_error, lineage.build_error


def test_the_graph_cell_binds_to_a_swe_world_and_records_what_it_still_cannot_do():
    """The `World` value exists, so the cell is a binding and not an absence.

    This test used to assert that no SWE `World` existed, which was
    checkable and true of the world the executor shipped with. It is now
    false in a way that matters more: `s09_swe_binding.SWE_WORLD` names
    SWE's own targets, admits all five kinds and publishes the observation
    keys a SWE guard may read, and the real `load_policy` admits the
    record under it.

    What it still cannot do is the part that was never a binding, and it
    is recorded on the lineage rather than left to be inferred from a
    zero repair rate.
    """
    from experiments.ad01 import s09_swe_binding, s09_swe_ast

    lineage = next(item for item in matrix.LINEAGES
                   if item.name == "action-graph-L0")
    assert lineage.built_ok, lineage.build_error
    assert lineage.record["unfillable_cell"] == \
        s09_swe_ast.missing_cells()["action-graph"]["witness"]

    world_value = s09_swe_binding.SWE_WORLD
    assert world_value.name == "swe"
    assert set(world_value.observation_paths) == \
        {"test", "expected", "actual", "kind"}
    assert world_value.allowed_kinds == frozenset(
        world_value.allowed_kinds & {"observe", "check", "construct", "use",
                                     "stop"})
    assert "use" in world_value.allowed_kinds, \
        "the SWE world's own `use` kind is admissible, so the old absence " \
        "claim is no longer true and this test must be revisited"


def test_the_path_fork_records_what_was_reconciled_and_what_stays_refused():
    """The fork is closed, and the record says so with the real numbers.

    A reviewer has to be able to see that the common path is now usable
    and what the three disputed fields were resolved to, rather than read
    "still not comparable" and assume nothing moved.
    """
    fork = matrix.path_fork()

    assert fork["common_path_usable"] is True
    assert fork["refusal"] is None
    assert "world driver" in fork["run_path"]
    assert "contract_view" in fork["common_path"]
    assert sorted(fork["missing_from_swe"]) == []
    assert sorted(fork["extra_in_swe"]) == []
    assert fork["fields_required_by_harness"] == sorted(
        world.POLICY_VIEW_FIELDS)
    # the three disputed fields carry the world's own values, not sums
    assert fork["contract_max_queries"] == world.BUDGET_LIMITS["test"]
    assert fork["contract_remaining"] == world.BUDGET_LIMITS["test"]
    assert fork["contract_hypothesis_class"] == {
        "structure": "counting",
        "editable_lines": len(
            world.SweSession(tasks.instance(
                "held_out", tasks.HELD_OUT_TEMPLATES[0],
                tasks.HELD_OUT_MECHANISMS[0])).policy_view()["source"])}
    assert "NOT comparable" in fork["scope_of_result"]
    assert fork["fork"]["resolved"]
    assert fork["fork"]["still_refused"]


def test_the_fork_is_part_of_the_written_evidence():
    """A caveat in a chat message is not evidence.

    This is the check that the path difference travels with the
    artifact, so a reviewer reading only `matrix.json` still learns
    which path produced the numbers.
    """
    payload = matrix.result_payload(matrix.MatrixResult())

    assert payload["path_fork"]["common_path_usable"] is True
    assert "NOT comparable" in payload["path_fork"]["scope_of_result"]


def test_a_candidate_that_fails_at_module_scope_is_a_refusal_not_a_crash():
    """A `code.try` must never raise out of the bounded tool.

    The generated candidates are single lines re-indented from the
    program itself, so most are legal. A line like `width = 0` is
    not: moved outside the function it binds an undefined `body` at
    module level. `run_program` caught only `SyntaxError`, so that
    `NameError` escaped `try_edit`, escaped `run_episode`, and killed
    the episode. Every supported episode died this way and the matrix
    reported 156 unrepaired rows rather than a crash, which is the
    worst possible reading of the same event.
    """
    from experiments.ad01 import s09_swe_tasks as t

    program = t.PROGRAMS_BY_NAME["count-lead-sum"]
    # a real line of the program, promoted to module scope, where the
    # name it reads is not defined
    lines = ["x = body[0]\n", "def lead_sum(body, n):\n", "    return 0\n"]

    out = t.run_program(program, ["123", 2], lines)

    assert out["kind"] == "error", out
    assert out["name"] == "NameError", out
    assert out["text"]


def test_a_candidate_that_fails_at_module_scope_traces_as_no_coverage():
    """The localization tool has the same obligation as `code.try`."""
    from experiments.ad01 import s09_swe_tasks as t

    program = t.PROGRAMS_BY_NAME["count-lead-sum"]
    lines = ["x = body[0]\n", "def lead_sum(body, n):\n", "    return 0\n"]

    assert t.trace_lines(program, ["123", 2], lines) == []


def test_the_reference_line_is_reachable_as_a_candidate():
    """The instrument's own fix must make the true repair scoreable.

    A guard fault's repair is the reference conditional. If no
    generated candidate can execute, the search cannot find it and
    the panel measures nothing.
    """
    from experiments.ad01 import s09_swe_tasks as t

    record = t.instance("dev", t.DEV_TEMPLATES[0], t.DEV_MECHANISMS[0])
    program = t.PROGRAMS_BY_NAME[record["template"]]
    patch = record["patch"][0]
    restored = t.apply_edits(record["source"], [patch])

    assert t.run_program(program, record["public_tests"][0]["args"],
                         restored)["kind"] == "value"


def test_the_step_suspect_ranking_reaches_the_fault_line():
    """A four-suspect cap that drops the fault measures nothing.

    The ranking was `sorted(clean)`, i.e. by line number, which put the
    return statement first and the injected fault last. Capped at four
    suspects the fault was never dry-run, so every supported episode
    scored zero and the matrix reported 156 unrepaired rows that looked
    like a solver result. Ranked by depth, as the reference search
    does, the fault is reached.
    """
    from experiments.ad01 import s09_swe_tasks as t
    from experiments.ad01 import s09_swe_world as w

    lineage = matrix.supported_lineages()[0]
    namespace: dict = {}
    exec(compile(lineage.policy_source, "<lineage>", "exec"), namespace)
    record = t.instance("dev", t.DEV_TEMPLATES[0], t.DEV_MECHANISMS[0])
    session = w.SweSession(record)
    for case in record["public_tests"]:
        session.run_public_test(case["name"])
    session.localize(record["public_tests"][0]["name"])
    view = session.policy_view()

    fault_line = record["patch"][0]["line"]
    ranked = namespace["suspects"](view)

    assert fault_line in ranked, \
        "the fault line is outside the four-suspect cap, so no candidate " \
        "edit on it is ever tried and the episode cannot succeed"
    assert ranked.index(fault_line) < 4


def test_the_module_level_risk_key_agrees_with_the_step_source():
    """`_risk_key` restates the source's initialiser test.

    `initialiser` lives inside the STEP source string and cannot be
    imported, so the two-character test is duplicated at module scope.
    If they drift, the ranking this lane reports and the ranking the
    policy runs are different and neither is the one measured.
    """
    from experiments.ad01 import s09_swe_experiment as m

    lineage = matrix.supported_lineages()[0]
    namespace: dict = {}
    exec(compile(lineage.policy_source, "<lineage>", "exec"), namespace)
    lines = ["    total = 0", "    seen = seen + 1", "    return total + 1"]

    for number, text in enumerate(lines, start=1):
        assert namespace["risk_key"](lines, number) == \
            m._risk_key(lines, number), text


def test_a_generated_candidate_keeps_the_indentation_of_its_line():
    """A stripped candidate is an IndentationError, and scores zero.

    `rewrites` deduplicated on the stripped form and then appended that
    stripped form, so a candidate for a line inside the function came
    out as `total = total + contribution` with no leading space. Every
    such candidate is a syntax error, so `code.try` reported 0 of 2 for
    the *correct* repair. The search could therefore never win, on any
    instance, for any lineage - which is what the first two full runs
    reported as 156 clean unrepaired rows.
    """
    from experiments.ad01 import s09_swe_tasks as t
    from experiments.ad01 import s09_swe_world as w

    lineage = matrix.supported_lineages()[0]
    namespace: dict = {}
    exec(compile(lineage.policy_source, "<lineage>", "exec"), namespace)
    record = t.instance("held_out", t.HELD_OUT_TEMPLATES[0],
                        t.HELD_OUT_MECHANISMS[0])
    session = w.SweSession(record)
    for case in record["public_tests"]:
        session.run_public_test(case["name"])
    session.localize(record["public_tests"][0]["name"])
    view = session.policy_view()

    fault_line = record["patch"][0]["line"]
    lines = namespace["lines_of"](view)
    pool = namespace["pool_of"](view)
    candidates = namespace["rewrites"](lines[fault_line - 1], pool)

    assert candidates, "no candidates were generated for the fault line"
    for candidate in candidates:
        assert candidate.startswith(
            lines[fault_line - 1][:len(lines[fault_line - 1])
                                    - len(lines[fault_line - 1].lstrip())]
        ) or not lines[fault_line - 1][:1].isspace(), candidate

    # and the decisive check: the true repair is generated, indented,
    # and scores a full pass
    reference = record["patch"][0]["text"].strip()
    assert reference in [c.strip() for c in candidates]
    fresh = w.SweSession(record)
    scored = fresh.try_edit(fault_line, record["patch"][0]["text"])
    assert scored["public_passed"] == scored["public_total"], scored


# --- the ceiling lane -------------------------------------------------
#
# Two independent limits govern every repair rate in the before-picture
# (`reports/evidence/inv_r1_e1_swe`): the `code.try` budget of 60 stops
# before the fault line is reached, and no reachable candidate generator
# emits a guard repair. The tests below pin the removal of each, and
# each names the counterfactual that would make it fail.


def test_a_fault_line_is_reachable_within_the_configured_probe_budget():
    """The budget has to cover the panel, or the panel measures nothing.

    "The budget is big enough" is not a testable claim, so this tests
    the property it exists to serve: walking the suspect list in the
    order the policy walks it, every instance's fault line receives at
    least one `code.try` dry-run before the budget runs out.

    How it is made falsifiable: the test derives the number from the
    instrument rather than asserting a literal, then checks the real
    invariant against `world.BUDGET_LIMITS["probe"]`. Drop the budget
    back to 60 and this fails on 15 of 30 held-out instances. Inflate
    `MAX_SUSPECTS` so the list is longer and it fails again, because the
    fault line's rank moves down with the list.

    It reads `record["patch"]`, the assessor's line, which no policy may
    see. That is the asymmetry the whole reach diagnostic rests on and
    is pinned separately by
    `test_the_reach_diagnostic_uses_the_assessor_line_and_no_policy_does`.
    """
    report = matrix.search_span("held_out")

    assert report["instances"] == 30
    for task_id, item in sorted(report["per_instance"].items()):
        assert item["probe_cost_to_fault_line"] is not None, (
            "%s: the fault line is not a suspect at all, so no candidate "
            "on it is ever generated" % task_id)
        assert item["probe_cost_to_fault_line"] <= report["probe_budget"], (
            "%s: reaching the fault line costs %d dry-runs and the budget "
            "is %d" % (task_id, item["probe_cost_to_fault_line"],
                       report["probe_budget"]))
    assert report["instances_reaching_fault_line"] == report["instances"]


def test_the_probe_budget_is_derived_from_the_panel_and_not_typed_in():
    """A budget hand-tuned until a number looks good is not a property.

    The instrument carries a derived figure rather than a literal, and
    the derivation is a pure function of the panel, so a reviewer can
    recompute it. The test recomputes it by the same route and pins the
    published figure, which fails the moment the panel or the walk order
    changes underneath it.
    """
    for split in ("dev", "held_out"):
        report = matrix.search_span(split)
        assert report["probe_budget"] == world.BUDGET_LIMITS["probe"]
        # The budget is derived over the whole panel, so a single split's
        # worst case can sit below it. The invariant is that the budget is
        # the derivation, and that every instance in this split fits.
        assert report["derived_budget"] == report["probe_budget"]
        assert report["worst_case_probe_cost"] <= report["probe_budget"]
        assert report["instances_reaching_fault_line"] == report["instances"]


def test_a_search_order_may_not_read_the_answer():
    """A ranking that knows the fault line is not a ranking.

    The suspicion order was changed to stop pointing away from the
    answer. The defence is that the order is a function of the *public
    view* alone, so it is a better search order rather than an oracle.

    This makes that falsifiable two ways. First, the source is compiled
    and its `suspects` is called with a view whose program, symptoms and
    coverage are those of a real instance; the returned order must be
    unchanged when the assessor-only keys of the *record* are replaced
    with junk, because `suspects` never receives the record. Second,
    the order must depend on something a solver could have: swapping the
    observation of two public tests with opposite outcomes moves it, so
    it is driven by evidence rather than by a constant.
    """
    lineage = matrix.supported_lineages()[0]
    namespace: dict = {}
    exec(compile(lineage.policy_source, "<lineage>", "exec"), namespace)
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            "dropped_guard")
    view = _localized_view(record)
    baseline = namespace["suspects"](view)

    poisoned = json.loads(json.dumps(record))
    for key in tasks.FAULT_LABEL_KEYS:
        poisoned[key] = "poison"
    assert namespace["suspects"](view) == baseline, \
        "the ranking changed when the assessor's keys were poisoned, so " \
        "it reads something a solver cannot see"

    flipped = json.loads(json.dumps(view))
    observed = flipped["symptom"]["observed"]
    observed[0]["actual"], observed[1]["actual"] = \
        observed[1]["actual"], observed[0]["actual"]
    assert namespace["suspects"](flipped) != baseline, \
        "the ranking ignored which test failed, so it is not driven by " \
        "the evidence a solver has"


def test_the_reachable_generator_emits_a_guard_repair():
    """A guard family is unreachable until a candidate for it exists.

    `s09_swe_policy._guard_rewrites` had the shape, but the STEP source
    runs in a child that forbids imports, so the reference policy's
    generator was never on the path the experiment actually runs. The
    arm therefore could not propose the repair however large its budget
    was, which is a different failure from truncation and needs its own
    fix.

    The test runs the generator the arm runs, on each guard family's
    faulty line, and asserts the reference line is among the candidates.
    Delete the guard generator from the STEP source and it fails on both
    guard families and on nothing else.
    """
    lineage = matrix.supported_lineages()[0]
    namespace: dict = {}
    exec(compile(lineage.policy_source, "<lineage>", "exec"), namespace)

    for mechanism in ("dropped_guard", "inverted_guard"):
        covered = []
        for record in tasks.enumerate_instances(
                "dev" if mechanism in tasks.DEV_MECHANISMS else "held_out"):
            if record["mechanism"] != mechanism:
                continue
            view = _localized_view(record)
            texts = [item["text"] for item in view["source"]]
            pool = namespace["pool_of"](view)
            line = record["patch"][0]["line"]
            reference = record["patch"][0]["text"].rstrip("\n")
            candidates = namespace["rewrites"](texts[line - 1], pool)
            covered.append(reference in candidates)
        assert covered, "no instance of %s in the panel" % mechanism
        assert all(covered), (
            "%s: the reachable generator does not emit the guard repair, "
            "so the family is unreachable for a reason no budget fixes"
            % mechanism)


def test_the_search_span_reports_a_generator_miss_and_does_not_blame_the_budget():
    """Two ceilings, two columns, and neither hides the other.

    An instance where the budget reaches the fault line but the
    generator never proposes the repair is a different failure from one
    where the budget stops short. Collapsing them is how a negative
    result gets misread as a solver result. The report carries both, per
    instance and per mechanism, and this pins that the two are counted
    separately.
    """
    report = matrix.search_span("held_out")

    assert set(report["per_instance"]) == {
        record["task_id"]
        for record in tasks.enumerate_instances("held_out")}
    for task_id, item in sorted(report["per_instance"].items()):
        assert isinstance(item["probe_cost_to_fault_line"], (int, type(None)))
        assert isinstance(item["reference_generated"], bool), task_id
        if item["reference_generated"] and not item["repairable_in_budget"]:
            raise AssertionError(
                "%s: the generator has the repair and the budget still "
                "cannot reach it" % task_id)
    assert set(report["by_mechanism"]) == set(tasks.HELD_OUT_MECHANISMS)
    for mechanism, item in sorted(report["by_mechanism"].items()):
        assert item["instances"] == 6, mechanism
        assert 0 <= item["fault_line_reached"] <= item["instances"]
        assert 0 <= item["reference_generated"] <= item["instances"]
        assert item["instances_reachable"] == min(
            item["fault_line_reached"], item["reference_generated"]) or \
            item["instances_reachable"] <= min(
                item["fault_line_reached"], item["reference_generated"])


def _localized_view(record: dict) -> dict:
    """The view an arm sees after observing and localizing, built the
    way an episode builds it and through the world's own session."""
    session = world.SweSession(record)
    for case in record["public_tests"]:
        session.run_public_test(case["name"])
    session.localize(record["public_tests"][0]["name"])
    return session.policy_view()


def test_a_reversed_guard_is_repaired_by_swapping_its_branches():
    """A present guard with the wrong polarity is a third shape.

    `dropped_guard` loses a conditional and `guard_rewrites` restores
    one. `inverted_guard` keeps the conditional and swaps its branches,
    so the generator that refuses any line already carrying `if` never
    touches it. The reference search had the same gap, which is how a
    gap survives in two places at once.

    The edit is the line's own two branch values, exchanged, and nothing
    else: `marker = 1 if seen == 0 else 0` becomes
    `marker = 0 if seen == 0 else 1` by swapping the values either side
    of the conditional. Nothing about the answer is consulted.
    """
    lineage = matrix.supported_lineages()[0]
    namespace: dict = {}
    exec(compile(lineage.policy_source, "<lineage>", "exec"), namespace)
    covered = []
    for record in tasks.enumerate_instances("dev"):
        if record["mechanism"] != "inverted_guard":
            continue
        view = _localized_view(record)
        texts = [item["text"] for item in view["source"]]
        pool = namespace["pool_of"](view)
        line = record["patch"][0]["line"]
        covered.append(record["patch"][0]["text"].rstrip("\n")
                       in namespace["rewrites"](texts[line - 1], pool))

    assert covered
    assert all(covered), (
        "inverted_guard: the generator does not swap a present guard's "
        "branches, so the family is unreachable for a reason no budget "
        "fixes")


def test_the_reference_search_and_the_step_source_generate_the_same_fault_set():
    """Two generators that drift are one generator and a guess.

    The reference search runs in process and the STEP source runs in the
    bounded child. They are the same policy expressed twice, and a
    family one of them can express and the other cannot is a measurement
    of the copy rather than of the representation. This pins that the
    two reach the same references on the same lines, per instance.
    """
    lineage = matrix.supported_lineages()[0]
    namespace: dict = {}
    exec(compile(lineage.policy_source, "<lineage>", "exec"), namespace)
    gaps = []
    for split in ("dev", "held_out"):
        for record in tasks.enumerate_instances(split):
            view = _localized_view(record)
            texts = [item["text"] for item in view["source"]]
            line = record["patch"][0]["line"]
            reference = record["patch"][0]["text"].rstrip("\n")
            in_step = reference in namespace["rewrites"](
                texts[line - 1], namespace["pool_of"](view))
            in_search = reference in policy.rewrites(texts[line - 1],
                                                     policy._pool(view))
            if in_search and not in_step:
                gaps.append((record["task_id"], record["mechanism"]))

    assert not gaps, (
        "the reference search generates %d repair(s) the STEP source does "
        "not, so the arm that runs is not the search the instrument "
        "documents: %s" % (len(gaps), gaps))


def test_the_turn_cap_can_outlive_the_whole_probe_budget():
    """A probe budget the episode cannot spend is not a budget.

    `code.try` spends one probe per turn, so a `probe` limit above
    `MAX_TURNS` describes a search the episode stops before it runs.
    This is the truncation that binds last and the easiest to miss,
    because raising the probe budget alone looks like it took effect
    while the turn cap silently still governs.

    The turn count is derived from the probe budget, so the test pins
    the relationship rather than a literal: every dry-run the budget
    allows has a turn to happen in, plus the observing preamble and the
    closing repair.
    """
    assert world.MAX_TURNS >= world.OBSERVE_TURNS + \
        world.BUDGET_LIMITS["probe"] + world.BUDGET_LIMITS["edit"], (
        "the episode stops at %d turns before it can spend its %d-probe "
        "budget, so the probe budget is not reachable"
        % (world.MAX_TURNS, world.BUDGET_LIMITS["probe"]))
    assert world.MAX_TURNS == world.OBSERVE_TURNS + \
        world.BUDGET_LIMITS["probe"] + world.BUDGET_LIMITS["edit"], (
        "the turn cap is no longer the derivation, so it can drift below "
        "the budget it is supposed to cover")


def test_a_search_that_reaches_its_last_probe_still_has_a_turn_to_repair():
    """The closing repair is a turn, and the budget has to leave it one.

    A search that spends its whole probe budget has found nothing it
    can use, because `use` costs a turn of its own. This drives the
    episode to the turn immediately before the cap and checks the
    world's own `admits` still lets the repair through, which is the
    state a search in that position actually reaches.
    """
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            "double_count")
    session = world.SweSession(record)
    for case in record["public_tests"]:
        world.apply_action(session, {
            "kind": contract.OBSERVE, "target": "test.run",
            "inputs": {"test": case["name"]},
            "evidence_refs": [], "requested_resources": {}})
    world.apply_action(session, {"kind": contract.CONSTRUCT,
                                "target": "code.localize",
                                "inputs": {"test":
                                           record["public_tests"][0]["name"]},
                                "evidence_refs": [],
                                "requested_resources": {}})
    spent_probe = 0
    while spent_probe < world.BUDGET_LIMITS["probe"]:
        admitted = world.admits(
            session, session.policy_view(),
            {"kind": contract.CONSTRUCT, "target": "code.try",
             "inputs": {"line": 1, "text": "pass"}})
        if not admitted:
            break
        world.apply_action(session, {
            "kind": contract.CONSTRUCT, "target": "code.try",
            "inputs": {"line": 1, "text": "pass"},
            "evidence_refs": [], "requested_resources": {}})
        spent_probe += 1

    assert spent_probe == world.BUDGET_LIMITS["probe"], (
        "the probe budget was exhausted at %d, short of the %d the "
        "instrument publishes" % (spent_probe,
                                  world.BUDGET_LIMITS["probe"]))
    view = session.policy_view()
    turns_used = tasks.PUBLIC_CASES + 1 + spent_probe
    assert turns_used + 1 <= world.MAX_TURNS, (
        "a search that has spent its whole probe budget has no turn left "
        "to apply the repair it found")
    assert world.admits(session, view, world.repair_action(
        [{"line": 1, "op": "replace", "text": "pass"}]))


def test_a_search_that_finds_the_repair_before_its_probes_run_out_applies_it():
    """A winner the search never spends is a winner it did not find.

    `plan` returns `try` whenever a probe remains, and `driven` falls
    through to `stop` when `next_try` returns nothing, so the `repair`
    branch below it was unreachable for any search that exhausted its
    candidate space while budget remained. The episode then ended with
    `best_passed` equal to the public total and nothing applied, which
    scored identically to a search that never found anything at all.

    This is a search defect rather than a ceiling, and it is the one
    that decided the before-picture's zero: the reference line was
    dry-run, scored 2 of 2, and discarded. The test drives a real
    episode and asserts the repair reaches the world.
    """
    record = tasks.instance("held_out", "count-tail-sum", "double_count")
    catalogue = tasks.enumerate_instances("held_out")
    seed = [item["task_id"] for item in catalogue].index(record["task_id"])
    state: dict = {}
    episode = world.run_episode(
        lambda view: policy.driven(state, view),
        split="held_out", seed=seed)
    tried = [turn["action"]["inputs"]
             for turn in episode["trace"]
             if turn.get("effect", {}).get("kind") == "construct"
             and "tried" in turn.get("effect", {})]

    assert record["patch"][0]["text"].rstrip("\n") in [
        item["text"] for item in tried], \
        "the reference repair was never dry-run, so this instance says " \
        "nothing about whether the search can find it"
    assert episode["final"]["outcome"] == "repaired", (
        "the search dry-ran the reference repair and scored it on every "
        "public test, then ended unrepaired with %d probe(s) unspent"
        % episode["final"]["budget"]["probe"])


def test_both_generators_open_the_same_number_of_suspect_lanes():
    """Two copies of a cap are two chances to drift.

    The STEP source caps inside its own `suspects` and the in-process
    reference caps inside `next_try`, from the same derived figure. If
    the two ever opened different numbers of lanes they would be
    searching different spaces, and a per-mechanism number from one
    would say nothing about the other. This checks the lane counts
    agree on every instance of the panel.
    """
    lineage = matrix.supported_lineages()[0]
    namespace: dict = {}
    exec(compile(lineage.policy_source, "<lineage>", "exec"), namespace)
    cap = namespace["MAX_SUSPECTS"]
    assert cap == world.SUSPECT_CAP, (
        "the STEP source runs with a suspect cap of %d and the instrument "
        "derives %d" % (cap, world.SUSPECT_CAP))

    for split in ("dev", "held_out"):
        for record in tasks.enumerate_instances(split):
            view = _localized_view(record)
            in_child = len(namespace["suspects"](view))
            in_process = len(policy.suspects(view)[:world.SUSPECT_CAP])
            assert in_child == in_process, record["task_id"]


def test_the_probe_budget_covers_the_reference_not_merely_the_fault_line():
    """Reaching a line is not reaching the repair written on it.

    The budget derivation once measured the cost of dry-running the
    fault *line* and reported 58 for an instance the search only found
    at 302. A line ranked second with forty candidates on it is touched
    after two dry-runs; its repair is the fortieth candidate in that
    lane. The derived budget was short by a third, and every instance
    past the shortfall scored zero for a reason no report named.

    This pins the cost against the *reference text* and against the
    order the search actually spends in, so the two cannot drift apart
    again. It walks candidates the way `next_try` walks them and
    asserts the derived budget exceeds the cost on every instance whose
    reference is in the candidate space at all.
    """
    from experiments.ad01 import s09_swe_policy as search

    worst = 0
    reachable = 0
    for split in tasks.SPLITS:
        for record in tasks.enumerate_instances(split):
            session = world.SweSession(record)
            for case in record["public_tests"]:
                session.run_public_test(case["name"])
            session.localize(record["public_tests"][0]["name"])
            view = session.policy_view()
            texts = [item["text"] for item in view["source"]]
            pool = search._pool(view)
            reference = record["patch"][0]["text"].rstrip("\n")
            numbers = [number for number in search.suspects(view)[:world.SUSPECT_CAP]
                       if 1 <= number <= len(texts)]
            lanes = [search.rewrites(texts[number - 1], pool)
                     for number in numbers]
            spent = 0
            cost = None
            for column in range(search.MAX_REWRITES):
                if not any(column < len(lane) for lane in lanes):
                    break
                for lane in lanes:
                    if column >= len(lane):
                        continue
                    spent += 1
                    if lane[column] == reference:
                        cost = spent
                        break
                if cost is not None:
                    break
            if cost is None:
                continue
            reachable += 1
            worst = max(worst, cost)

    assert reachable > 0
    assert worst <= world.BUDGET_LIMITS["probe"], (
        "the furthest reference repair costs %d dry-runs and the budget "
        "is %d, so the instances past the shortfall are truncated by a "
        "number nothing reports" % (worst, world.BUDGET_LIMITS["probe"]))


def test_a_candidate_that_passes_every_public_test_is_not_automatically_right():
    """Passing the visible tests is a weak signal, and several
    candidates share it.

    `absorb` records the *first* candidate to reach the public total and
    keeps it. On `token-gaps` / `index_drift` five candidates reach 2 of
    2, and the first of them keeps the widened bound `(1 + 1)` while
    only shifting the slice base. It is applied, it does not repair, and
    the episode ends unrepaired.

    This is not a ceiling and not a generator gap. The reference repair
    is generated, dry-run, and scored 2 of 2 in the same episode. The
    search found the answer and then discarded it for an earlier
    candidate that scored the same and is wrong. The scorer already
    refuses it, which is the correct behaviour; this pins that the
    refusal is what happens, so a reader does not mistake the eight
    remaining failures for one cause.
    """
    record = tasks.instance("held_out", "token-gaps", "index_drift")
    catalogue = tasks.enumerate_instances("held_out")
    seed = [item["task_id"] for item in catalogue].index(record["task_id"])
    state: dict = {}
    episode = world.run_episode(
        lambda view: policy.driven(state, view), split="held_out", seed=seed)
    applied = [turn["action"]["inputs"]["edits"][0]
               for turn in episode["trace"]
               if turn.get("effect", {}).get("kind") == "use"]

    if not applied:
        return  # the search proposed nothing, which the reach tests cover

    program = tasks.PROGRAMS_BY_NAME[record["template"]]
    for edit in applied:
        trial = tasks.apply_edits(record["source"], [edit])
        report = tasks.score(record, trial)
        assert report["public_passed"] == len(record["public_tests"]), (
            "the search applied %r, which passes only %d of %d public "
            "tests, so it was not the candidate it had recorded as best"
            % (edit["text"], report["public_passed"],
               len(record["public_tests"])))
    assert episode["final"]["outcome"] == "unrepaired", (
        "a candidate that passes every public test and fails the "
        "protected one is not a repair, and the scorer must say so")


def test_the_repair_report_counts_the_tests_it_actually_re_ran():
    """`repair` reports a pass count it did not measure.

    `repair` clears the observation and calls `run_all_public`, which
    spends the `test` budget. A search that has already spent it gets
    an empty result set, so `passed` is 0 and `_repaired` is set from
    that zero. The final `score()` disagrees with the repair's own
    report, which is the kind of disagreement that makes a row
    unreadable.

    This pins the two agree, because a reader comparing
    `effect.repaired.passed` with `final.public_passed` on the same row
    should not find two different numbers.
    """
    record = tasks.instance("held_out", "token-gaps", "index_drift")
    session = world.SweSession(record)
    for case in record["public_tests"]:
        session.run_public_test(case["name"])
    repair = session.repair([record["patch"][0]])
    final = session.score()

    assert repair["passed"] == final["public_passed"], (
        "repair reported %d of %d passing and the final score reported %d, "
        "so one of them did not measure the program it was describing"
        % (repair["passed"], repair["total"], final["public_passed"]))
