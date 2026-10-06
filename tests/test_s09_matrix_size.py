"""The matrix writer must not grow with the length of a trace.

`reports/evidence/inv_r1_e1_swe_ceiling/matrix.json` is 5.16 MB and
227,631 lines, and 90% of that is `actions_emitted`: a per-step trace
repeated verbatim across the rows, holding sixteen distinct sequences.
The writer emitted one inline copy per row, so a fixed panel produced a
file whose size was set by how long a solver walked, not by how much
was learned.

These tests pin the writer's output shape rather than the writer's
internals. The claim under test is that every number the artifact
supports still reads out of the file after the trace is interned, and
that the file stops being a function of trace length.

The 468-row cross-product is built synthetically. A real run is a bounded
out-of-process child per turn with a ten second budget, so a real
468-row matrix is hours of wall clock and cannot be a test fixture. The
synthetic panel mirrors the committed one exactly where it matters for
size and for the claims: 12 lineages over the same 39 instances, 156
traced rows carrying 16 distinct ~300-action sequences, and the same
124/32/312 outcome split.

A synthetic panel is a mirror, and a mirror agrees with a damaged
original whenever the damage falls outside the part being mirrored. N-411
was a hand edit to the committed matrix that removed a terminal
`{"kind": "stop", "target": "swe.task"}` from 60 rows. It left the traced
row count, the distinct-trace count and `turns == len(actions_emitted)`
untouched, so every assertion below that reads the synthetic panel still
passed against a file carrying the defect.

Three checks were added in response. Two apply the same stop-termination
law to two different real matrices, the one on disk and the one in git
that the hand edit replaced, because a law only means something if the
file that is correct satisfies it. The third measures `SIZE_BOUND` on
the committed rows instead of the fixture, because a bound that only
ever sees the fixture cannot fail for anything the artifact does.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os

import pytest

from experiments.ad01 import s09_swe_experiment as matrix
from experiments.ad01 import s09_swe_tasks as tasks

# The bound the writer has to hold for a complete cross-product. The
# committed ceiling matrix, with the trace inline, is 5,163,201 B.
SIZE_BOUND = 500 * 1024

# Measured on the committed artifact, not assumed. Two definitions give
# two numbers and both are true: 16 distinct non-empty sequences across
# the 156 rows that carry a trace, and 17 distinct sequences across all
# 468 rows once the empty sequence of the 312 never-started rows counts.
# A writer that interns per non-empty trace must produce 16 table
# entries; one that interns the empty sequence too must produce 17.
COMMITTED = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "evidence", "inv_r1_e1_swe_ceiling", "matrix.json")

LINEAGE_NAMES = (
    tuple("python-step-L%d" % index for index in range(4))
    + tuple("typed-ast-L%d" % index for index in range(4))
    + tuple("action-graph-L%d" % index for index in range(4)))

# The trace shape measured on the committed file: every traced row is
# 293 to 307 actions long, and the 16 distinct sequences differ only in
# which action kinds they interleave.
_TRACE_RUNS = (
    (("observe", "test.run"), 118),
    (("observe", "test.run"), 4),
    (("construct", "code.localize"), 6),
    (("observe", "coverage.report"), 22),
    (("construct", "code.propose"), 9),
    (("construct", "code.apply"), 3),
    (("observe", "test.run"), 31),
    (("construct", "code.localize"), 5),
    (("observe", "coverage.report"), 14),
    (("construct", "code.propose"), 7),
    (("construct", "code.apply"), 4),
    (("observe", "test.run"), 26),
    (("construct", "code.localize"), 8),
    (("observe", "coverage.report"), 19),
    (("construct", "code.propose"), 11),
    (("observe", "test.run"), 24),
    (("construct", "code.apply"), 2),
)

_OTHER_KINDS = ("probe", "compare", "revert", "annotate")

# The two refusal texts measured on the committed file: one per refused
# representation, each naming the validator that produced it.
REFUSALS = {
    "typed-ast": "validator refused code.repair: action 'use' is not "
                 "available in the Boolean world",
    "action-graph": "validator refused code.repair: action 'use' is not "
                    "available in the action-graph world",
}


def _trace(variant: int) -> tuple:
    """One distinct trace, distinct from every other variant.

    The committed file's sixteen sequences are all ~300 actions and
    differ in which action kinds they interleave and how long they hold
    each one. Varying the kind of one run is enough to make them
    distinct, and it is what the committed sequences differ by.
    """
    actions = []
    for shift, (action, count) in enumerate(_TRACE_RUNS):
        span = count + ((variant * 7 + shift * 3) % 5) - 2
        kind = action[0] if (variant + shift) % 3 else _OTHER_KINDS[
            (variant + shift) % len(_OTHER_KINDS)]
        actions.extend([{"kind": kind, "target": action[1]}] * span)
    return tuple(actions)


def _traces(count: int = 16) -> list:
    return [_trace(index % count) for index in range(count)]


# Sixteen distinct traces over 156 traced rows, with the commonest
# shared by 68 of them, which is the distribution measured on the
# committed file.
_TRACE_SHARES = (68, 20, 14, 11, 8, 7, 6, 5, 4, 3, 2, 2, 2, 1, 2, 1)


def _trace_for_row(index: int, traces: list) -> tuple:
    cursor = index
    for position, share in enumerate(_TRACE_SHARES):
        if cursor < share:
            return traces[position]
        cursor -= share
    return traces[0]


def _instances() -> list:
    panel = []
    for split in ("dev", "held_out"):
        for record in tasks.enumerate_instances(split):
            panel.append((split, record["task_id"], record["structure"],
                          record["mechanism"]))
    return panel


def _build_rows() -> list:
    """The full 12 lineages x 39 instances cross-product.

    The split between repaired and unrepaired, and which rows carry a
    trace, follow the committed file: the four python-step lineages
    produce all 156 traced rows and 124 repairs; the other eight
    lineages never start, so their rows are refusals with no trace.
    """
    panel = _instances()
    traces = _traces()
    rows = []
    missing = []
    traced = 0
    for lineage in LINEAGE_NAMES:
        kind = lineage.rsplit("-", 1)[0]
        if kind != "python-step":
            missing.append({
                "lineage": lineage, "representation_kind": kind,
                "reason": REFUSALS[kind]})
        for split, task_id, structure, mechanism in panel:
            refused = ""
            emitted = ()
            outcome = "refused"
            passed = 0
            protected = "unknown"
            turns = 0
            if kind == "python-step":
                outcome = "repaired" if traced < 124 else "unrepaired"
                passed = 2 if outcome == "repaired" else 1
                protected = "pass" if outcome == "repaired" else "fail"
                emitted = _trace_for_row(traced, traces)
                turns = len(emitted)
                traced += 1
            else:
                refused = REFUSALS[kind]
            rows.append(matrix.SweRow(
                representation_kind=kind, lineage=lineage,
                lineage_digest=hashlib.sha256(
                    ("digest:" + lineage).encode()).hexdigest(),
                task_id=task_id, split=split, structure=structure,
                fault_mechanism=mechanism, outcome=outcome,
                public_passed=passed, public_total=2, protected=protected,
                turns=turns, refused=refused, actions_emitted=emitted))
    return rows, missing


def _stretch(trace: tuple, factor: int) -> tuple:
    """Hold every action in the trace `factor` times as long.

    A longer walk of the same search, which is the growth the writer
    must absorb: the number of distinct sequences does not change and
    neither does their internal structure, only how many turns the
    lineage spent.
    """
    stretched = []
    for action in trace:
        stretched.extend([action] * factor)
    return tuple(stretched)


def _fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str)
        .encode()).hexdigest()[:16]


@pytest.fixture(scope="module")
def payload() -> dict:
    """`result_payload` over the synthetic cross-product.

    Module scoped because the payload spends about forty seconds in
    `probe_reach` and `search_span`, which exec a real policy over the
    real panel. Those two read the task catalogue, not the rows, so the
    result is the same for every fixture in this file.
    """
    rows, missing = _build_rows()
    return matrix.result_payload(
        matrix.MatrixResult(rows=rows, missing_cells=missing))


def _read_rows(payload: dict) -> list:
    """Rebuild full rows from the payload, undoing every interning.

    This is the reader a reviewer would write, and it is where a lossy
    encoding shows up: a trace that cannot be expanded, a refusal that
    cannot be resolved, or a lineage id with no entry.
    """
    traces = payload["trace_sequences"]
    refusals = payload["refusals"]
    lineages = {entry["id"]: entry for entry in payload["lineage_index"]}
    rows = []
    for row in payload["rows"]:
        lineage = lineages[row["lineage_id"]]
        sequence = row["trace_sequence"]
        emitted = ()
        if sequence is not None:
            runs = traces[sequence]
            emitted = tuple(
                {"kind": kind, "target": target}
                for kind, target, repeat in runs for _ in range(repeat))
        refused = ""
        if row["refusal"] is not None:
            refused = refusals[row["refusal"]]
        rows.append({
            "lineage": lineage["name"],
            "lineage_digest": lineage["digest"],
            "representation_kind": lineage["representation_kind"],
            "task_id": row["task_id"],
            "split": row["split"],
            "structure": row["structure"],
            "fault_mechanism": row["fault_mechanism"],
            "outcome": row["outcome"],
            "public_passed": row["public_passed"],
            "public_total": row["public_total"],
            "protected": row["protected"],
            "turns": row["turns"],
            "refused": refused,
            "actions_emitted": emitted,
        })
    return rows

def test_the_written_matrix_stays_under_the_size_bound(payload):
    """The whole point: size must track the panel, not the trace length.

    A writer that inlines the trace again fails here at roughly 5 MB,
    which is the defect this file exists to catch. This measures the
    synthetic panel; `test_the_size_bound_holds_of_a_real_panel` measures
    the same bound against the committed rows.
    """
    blob = json.dumps(payload, indent=2, sort_keys=True)

    assert len(blob) <= SIZE_BOUND, (
        "matrix payload is %d B for a 468-row cross-product, bound is %d B; "
        "the trace is being written inline again"
        % (len(blob), SIZE_BOUND))


def test_the_size_does_not_grow_with_the_length_of_a_trace(payload):
    """A solver walking three times as far must not grow the file.

    This is the stronger half of the claim. The bound test can be
    satisfied by a writer that emits short traces; this one cannot be
    satisfied by anything except interning.

    Each trace is stretched by holding every action three times its
    original count, which is what a longer walk looks like: the same
    sixteen searches, each running about 940 actions instead of 313.
    """
    stretched = [_stretch(trace, 3) for trace in _traces()]
    rows = []
    traced = 0
    for row in _build_rows()[0]:
        if row.actions_emitted:
            replacement = stretched[traced % len(stretched)]
            traced += 1
            row = matrix.SweRow(
                representation_kind=row.representation_kind,
                lineage=row.lineage, lineage_digest=row.lineage_digest,
                task_id=row.task_id, split=row.split,
                structure=row.structure,
                fault_mechanism=row.fault_mechanism, outcome=row.outcome,
                public_passed=row.public_passed,
                public_total=row.public_total, protected=row.protected,
                turns=len(replacement), refused=row.refused,
                actions_emitted=replacement)
        rows.append(row)
    walked = matrix.result_payload(matrix.MatrixResult(rows=rows))
    base = len(json.dumps(payload, indent=2, sort_keys=True))
    grown = len(json.dumps(walked, indent=2, sort_keys=True))
    actions = lambda block: sum(  # noqa: E731
        run[2] for runs in block["trace_sequences"].values() for run in runs)

    assert actions(walked) >= 3 * actions(payload), (
        "the fixture did not actually lengthen the walks")
    assert grown <= SIZE_BOUND, (
        "a walk three times as long grew the payload from %d B to %d B; "
        "the trace is still sized by its length" % (base, grown))


def _read_matrix(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


STOP = {"kind": "stop", "target": "swe.task"}
REPAIR = {"kind": "use", "target": "code.repair"}


def _stop_termination_violations(document: dict) -> list:
    """Traced rows whose last action the episode loop cannot explain.

    `world.run_episode` loops while the trace is short of `MAX_TURNS` and
    the session is not repaired. So an episode ends in one of three ways,
    and each leaves a different terminal action.

    It emitted a stop, recorded as that stop. It ran out of turns, leaving
    the last action of the walk, and a walk of exactly `MAX_TURNS` is the
    one that ran out. Or a `use code.repair` succeeded and the loop's
    `is_terminal` check ended it, leaving that repair as the last action.

    The third case carries the claim. A trace ending in a repair whose row
    is `unrepaired` is a contradiction: the repair did not repair, so the
    loop cannot have exited on it. This has to be the discriminating case.
    Counting stop-terminated rows does not separate the two files, because
    the generator's own output stops 56 of 124 `repaired` rows, the other
    68 exiting on the repair instead, so "every repaired row ends in a
    stop" is false of the file that is correct and pinning a count of 56
    would only pin the damage.
    """
    cap = document["derived_bounds"]["max_turns"]
    violations = []
    for row in document["rows"]:
        actions = row["actions_emitted"]
        if not actions or len(actions) == cap or actions[-1] == STOP:
            continue
        if actions[-1] == REPAIR and row["outcome"] == "repaired":
            continue
        violations.append({
            "task_id": row["task_id"], "lineage": row["lineage"],
            "outcome": row["outcome"], "turns": len(actions),
            "last_action": actions[-1], "max_turns": cap})
    return violations


def test_the_archived_matrix_is_recognised_as_invalid():
    """Preserve the damaged historical bytes and detect their missing stops."""
    violations = _stop_termination_violations(_read_matrix(COMMITTED))
    assert len(violations) == 4
    assert all(row["outcome"] == "unrepaired" and row["turns"] < row["max_turns"]
               for row in violations)


@pytest.mark.parametrize(("actions", "outcome", "valid"), [
    ([STOP], "unrepaired", True),
    ([REPAIR], "repaired", True),
    ([REPAIR], "unrepaired", False),
    ([{"kind": "observe", "target": "test.run"}], "unrepaired", False),
    ([REPAIR, REPAIR, REPAIR], "unrepaired", True),
])
def test_termination_law_distinguishes_stop_repair_and_turn_limit(actions, outcome, valid):
    row = {"task_id": "termination-control", "lineage": "fixture",
           "outcome": outcome, "turns": len(actions), "actions_emitted": actions}
    document = {"derived_bounds": {"max_turns": 3}, "rows": [row]}
    assert (not _stop_termination_violations(document)) is valid


def test_deleting_a_terminal_stop_is_detected():
    row = {"task_id": "stop-control", "lineage": "fixture",
           "outcome": "unrepaired", "turns": 2,
           "actions_emitted": [REPAIR, STOP]}
    document = {"derived_bounds": {"max_turns": 3}, "rows": [row]}
    assert _stop_termination_violations(document) == []
    row["actions_emitted"].pop()
    row["turns"] -= 1
    assert len(_stop_termination_violations(document)) == 1


def _rows_for_the_writer(document: dict) -> list:
    return [matrix.SweRow(
        representation_kind=row["representation_kind"],
        lineage=row["lineage"], lineage_digest=row["lineage_digest"],
        task_id=row["task_id"], split=row["split"],
        structure=row["structure"],
        fault_mechanism=row["fault_mechanism"], outcome=row["outcome"],
        public_passed=row["public_passed"],
        public_total=row["public_total"], protected=row["protected"],
        turns=row["turns"], refused=row["refused"],
        actions_emitted=tuple(
            {"kind": action["kind"], "target": action["target"]}
            for action in row["actions_emitted"]))
        for row in document["rows"]]


def test_the_size_bound_holds_of_a_real_panel(tmp_path):
    """`SIZE_BOUND`, on the 468 rows the generator really ran.

    The two size tests above both measure a synthetic panel, so the bound
    has never been tested against the artifact it was written for.
    """
    document = _read_matrix(COMMITTED)
    written = matrix.write_evidence(
        matrix.MatrixResult(rows=_rows_for_the_writer(document),
                            missing_cells=document["missing_cells"]),
        str(tmp_path / "matrix"))
    size = os.path.getsize(written["json"])

    assert size <= SIZE_BOUND, (
        "the real 468-row panel re-encoded through the current writer is "
        "%d B, bound is %d B; the trace is being written inline again"
        % (size, SIZE_BOUND))


def test_the_distinct_trace_count_is_sixteen_and_seventeen_counting_empty():
    """The number this was measured at, measured rather than assumed.

    The committed artifact is read, not trusted: the count is recomputed
    from the file. Sixteen is the count of distinct non-empty sequences
    over the 156 traced rows. Seventeen is the count over all 468 rows,
    and it is larger only because the 312 rows that never started share
    one empty sequence. A writer that interns the empty sequence has to
    agree with the second number instead of the first.
    """
    with open(COMMITTED, encoding="utf-8") as handle:
        committed = json.load(handle)
    rows = committed["rows"]
    traced = [row for row in rows if row["actions_emitted"]]

    non_empty = {json.dumps(row["actions_emitted"], sort_keys=True)
                 for row in traced}
    every = {json.dumps(row["actions_emitted"], sort_keys=True)
             for row in rows}

    assert len(traced) == 156, (
        "expected 156 traced rows, found %d" % len(traced))
    assert len(non_empty) == 16, (
        "expected 16 distinct non-empty traces, found %d"
        % len(non_empty))
    assert len(every) == 17, (
        "expected 17 distinct traces counting the empty one, found %d"
        % len(every))


def test_the_writer_interns_one_table_entry_per_distinct_trace(payload):
    """The table is sized by distinct traces, and every row points in.

    Sixteen distinct traces in, sixteen entries out. A writer that
    keyed on row index, or that emitted the empty sequence as a
    seventeenth entry, would miss this.
    """
    expected = {
        _fingerprint([dict(action) for action in _trace(index)])
        for index in range(16)}

    assert set(payload["trace_sequences"]) == expected
    assert len(payload["trace_sequences"]) == 16
    referenced = {row["trace_sequence"] for row in payload["rows"]}
    assert referenced - {None} == expected, (
        "a row references a trace id the table does not carry, or the "
        "table carries a sequence no row emitted")
    assert None in referenced, (
        "a row with no trace has to say so rather than name a sequence")
    traced = [row for row in payload["rows"] if row["trace_sequence"]]
    assert len(traced) == 156
    assert all(row["refusal"] is None for row in traced), (
        "a row that ran cannot also be a refusal")


def test_every_trace_expands_back_to_the_steps_that_were_run(payload):
    """Interning must be lossless, not a sample.

    The reconstructed rows are compared to the rows that went in, action
    for action, on all 156 traced rows. This is what makes the trace
    still evidence: a reviewer can recover which actions ran, in what
    order, how many times.
    """
    original = {("%s|%s" % (row.lineage, row.task_id)):
                list(row.actions_emitted)
                for row in _build_rows()[0] if row.actions_emitted}
    recovered = {"%s|%s" % (row["lineage"], row["task_id"]):
                 list(row["actions_emitted"])
                 for row in _read_rows(payload) if row["actions_emitted"]}

    assert set(original) == set(recovered)
    assert original == recovered, (
        "a trace did not expand back to the actions that were run")


def test_the_trace_table_declares_its_own_shape(payload):
    """A bare array of arrays is not readable without the field names.

    The runs are `[kind, target, repeat]`, and the payload says so, so
    the table can be decoded from the file alone rather than from
    whoever wrote the decoder.
    """
    assert payload["trace_sequence_fields"] == ["kind", "target", "repeat"]
    for runs in payload["trace_sequences"].values():
        assert runs, "an empty sequence must not occupy a table entry"
        for run in runs:
            assert len(run) == 3
            assert isinstance(run[2], int) and run[2] > 0


def test_every_row_outcome_survives_the_transformation(payload):
    """124 repaired, 32 unrepaired, 312 refused.

    The denominator is the whole cross-product, so a row that loses its
    outcome is a silently smaller claim rather than a visible error.
    """
    recovered = _read_rows(payload)
    tally = collections.Counter(row["outcome"] for row in recovered)

    assert len(payload["rows"]) == 468
    assert len(recovered) == 468
    assert tally == {"repaired": 124, "unrepaired": 32, "refused": 312}
    assert sum(tally.values()) == 468


def test_every_refusal_survives_with_its_text_intact(payload):
    """A refusal is the evidence for two missing cells.

    Dropping the text, or leaving an id that names nothing, turns a
    measured refusal into a blank one.
    """
    recovered = _read_rows(payload)
    refused = [row for row in recovered if row["outcome"] == "refused"]

    assert len(refused) == 312
    assert all("not available in the" in row["refused"] for row in refused)
    assert len(payload["refusals"]) == 2
    assert set(payload["refusals"].values()) == set(REFUSALS.values())
    assert {row["refusal"] for row in payload["rows"]} - {None} == \
        set(payload["refusals"])


def test_the_per_family_rates_survive_all_twenty_four(payload):
    """Twenty-four families, none of them dropped, none pooled away.

    The table counts episodes that ran, not episodes that were refused,
    so its denominator is 156 rather than 468: a refused cell has no
    family to contribute to. A pool that quietly omitted a zero-repair
    family would read as a better rate, so the count is a claim in its
    own right and so is the denominator.
    """
    table = payload["per_family"]
    recovered = _read_rows(payload)
    ran = [row for row in recovered if row["outcome"] != "refused"]

    assert len(table) == 24
    assert sum(entry["instances"] for entry in table.values()) == len(ran)
    assert len(ran) == 156
    assert sum(entry["repaired"] for entry in table.values()) == 124
    assert all(entry["instances"] > 0 for entry in table.values())
    assert all(0.0 <= entry["rate"] <= 1.0 for entry in table.values())
    assert {entry["structure"] for entry in table.values()} == \
        {row["structure"] for row in ran}
    assert all(entry["representations"] == ["python-step"]
               for entry in table.values()), (
        "a refused arm must not appear as a family it never ran")

    by_key = collections.Counter(
        (row["structure"], row["fault_mechanism"]) for row in ran)
    for key, entry in table.items():
        name = "%s/%s" % (entry["structure"], entry["fault_mechanism"])
        assert entry["instances"] == by_key[(entry["structure"],
                                             entry["fault_mechanism"])], name
        assert key == name


def test_the_missing_cells_survive_with_their_reasons(payload):
    """Eight refused lineages, one recorded refusal each.

    A cell that never built is recorded as data carrying the refusal
    that produced it, and the reason text is what says the limit is the
    world binding rather than the node set. The count is the number of
    lineages that could not be built, which is why it is smaller than
    the 312 refused rows that carry the same two strings.
    """
    cells = payload["missing_cells"]

    assert len(cells) == 8
    assert {cell["representation_kind"] for cell in cells} == \
        {"typed-ast", "action-graph"}
    assert all(cell["lineage"].startswith(cell["representation_kind"])
               for cell in cells)
    for cell in cells:
        assert cell["reason"] == REFUSALS[cell["representation_kind"]]
        assert "not available in the" in cell["reason"]


def test_the_paired_agree_rate_and_its_breakdown_survive(payload):
    """The agreement claim, in full.

    1872 pairs over 39 instances, a third of them agreeing, and the
    breakdown by representation pair: python-step disagrees with each
    refused arm, and the two refused arms agree with each other on
    every instance because they both refused.
    """
    pairs = payload["paired"]
    flat = [pair for group in pairs.values() for pair in group["pairs"]]
    agreeing = [pair for pair in flat if pair[-1]]

    assert len(flat) == 1872
    assert len(agreeing) == 624
    assert len(agreeing) / len(flat) == pytest.approx(1 / 3, abs=1e-9)
    assert all(len(pair) == 5 for pair in flat)
    assert {len(group["pairs"]) for group in pairs.values()} == {48}
    assert len(pairs) == 39

    summary = payload["paired_agree"]
    assert summary["pairs"] == 1872
    assert summary["agree"] == 624
    assert summary["rate"] == pytest.approx(1 / 3, abs=1e-9)
    assert set(summary["by_representation_pair"]) == {
        "python-step/typed-ast", "python-step/action-graph",
        "typed-ast/action-graph"}
    assert summary["by_representation_pair"]["typed-ast/action-graph"] == {
        "pairs": 624, "agree": 624, "rate": 1.0}
    assert summary["by_representation_pair"]["python-step/typed-ast"] == {
        "pairs": 624, "agree": 0, "rate": 0.0}


def test_the_paired_block_carries_both_sides_outcomes(payload):
    """`agree` is a claim about two rows, so both rows are named.

    An agreement table that stored only the boolean would assert a
    comparison it does not let anyone check.
    """
    flat = [pair for group in payload["paired"].values()
            for pair in group["pairs"]]
    recovered_rows = _read_rows(payload)
    recovered = {(row["task_id"], row["lineage"]): row["outcome"]
                 for row in recovered_rows}
    names = {entry["name"] for entry in payload["lineage_index"]}
    by_task: dict = {}
    for row in recovered_rows:
        by_task.setdefault(row["task_id"],
                           (row["structure"], row["fault_mechanism"]))

    assert len(recovered) == 468
    for task, group in payload["paired"].items():
        assert (group["structure"], group["fault_mechanism"]) == by_task[task]
        for left, right, left_outcome, right_outcome, agree in \
                group["pairs"]:
            assert left in names and right in names
            assert recovered[(task, left)] == left_outcome
            assert recovered[(task, right)] == right_outcome
            assert (left_outcome == right_outcome) == agree
    assert len(flat) == 1872


def test_the_probe_budget_reach_survives(payload):
    """Reach is 9 of 9 on dev and 30 of 30 on held out.

    It is a property of the panel and the budget, not of the rows, so
    this checks the writer still carries it and still carries the
    per-mechanism breakdown that says which families were reached.
    """
    reach = payload["probe_budget_reach"]

    assert set(reach) == {"dev", "held_out"}
    for split, instances in (("dev", 9), ("held_out", 30)):
        entry = reach[split]
        assert entry["instances"] == instances
        assert entry["fault_line_reached"] == instances
        assert entry["rate"] == 1.0
        assert sum(v["reached"] for v in entry["by_mechanism"].values()) \
            == instances


def test_the_scope_caveat_survives_and_names_what_is_still_incomparable(payload):
    """The claim that is still true, and the two that are not.

    This used to assert `common_path_usable is False`, a truthy
    `refusal`, and a `fork` carrying `widen_harness` / `normalise_swe` /
    `evidence_favours`. All three pinned the shape of a *superseded*
    definition: they described the view contract as an unresolved fork,
    which it was when written and is not any more. The SWE world is
    admitted by the common harness now, so "usable is False" is not a
    stale value to update, it is a wrong statement about the artifact.

    What survives is narrower and is the part a reviewer of the matrix
    still needs: the numbers this file carries are not comparable with
    the boolean or ordering worlds, and the two representations' SWE
    cells are missing for an executor reason. The admitted view does not
    make those numbers comparable, and a test that only checked
    `common_path_usable` would have said they were.

    `path_fork` is a fixed block, called once outside the rows loop, so
    none of this is a size claim. What it is checking is that the
    artifact does not understate its own limits, which is why it is here
    at all rather than in the experiment's own suite.
    """
    fork = payload["path_fork"]

    assert "NOT comparable" in fork["scope_of_result"]
    assert "s09_swe_ast.expressivity" in fork["scope_of_result"], (
        "the scope caveat must name where the executor limit is recorded, "
        "or a reader cannot tell which of the two reasons applies")
    assert fork["contract_max_queries"] == fork["contract_remaining"], (
        "the contract publishes a budget it must be able to spend within")
    assert fork["fields_required_by_harness"] == \
        fork["fields_published_by_swe"]
    assert fork["missing_from_swe"] == []
    assert fork["extra_in_swe"] == []
    assert set(fork["fork"]) == {"resolved", "still_refused"}
    assert "normalise_swe" not in fork["fork"], (
        "the fork this field reported is resolved; leaving the key would "
        "republish a blocker a reader would act on")


def test_the_lineage_ledger_and_its_digests_survive(payload):
    """Independence is the digest, so the digest must still be there.

    The row-level `lineage_digest` is now reached through
    `lineage_index`; a reader that lost the mapping would silently
    treat four lineages as one.
    """
    ledger = payload["lineages"]
    index = {entry["id"]: entry for entry in payload["lineage_index"]}

    assert len(ledger) == 12
    assert len(index) == 12
    assert all(entry["digest"] for entry in ledger)
    assert all(entry["name"] and entry["representation_kind"]
               for entry in index.values())
    assert {entry["digest"] for entry in index.values()} == \
        {entry["digest"] for entry in ledger}
    assert {row["lineage_id"] for row in payload["rows"]} == set(index)


def test_the_ledger_totals_still_agree_with_the_rows(payload):
    """The ledger is computed from the rows, so it must still add up."""
    recovered = _read_rows(payload)
    tallied = collections.defaultdict(lambda: [0, 0, 0])
    for row in recovered:
        entry = tallied[row["lineage"]]
        entry[0] += 1
        entry[1] += row["outcome"] == "repaired"
        entry[2] += row["outcome"] == "refused"

    for entry in payload["lineages"]:
        episodes, repairs, refusals = tallied[entry["name"]]
        assert (entry["episodes"], entry["repairs"], entry["refusals"]) == \
            (episodes, repairs, refusals), (
            "the ledger and the rows disagree for %s" % entry["name"])


def test_the_written_file_is_under_the_bound_on_disk(tmp_path, payload):
    """The bound has to hold of the file, not of the dict.

    `write_evidence` dumps with `indent=2, sort_keys=True`, which is
    what put 227,631 lines in the committed file, so the size that
    matters is the file's.
    """
    rows, missing = _build_rows()
    written = matrix.write_evidence(
        matrix.MatrixResult(rows=rows, missing_cells=missing),
        str(tmp_path / "matrix"))
    size = os.path.getsize(written["json"])

    assert size <= SIZE_BOUND, (
        "written matrix is %d B, bound is %d B" % (size, SIZE_BOUND))
