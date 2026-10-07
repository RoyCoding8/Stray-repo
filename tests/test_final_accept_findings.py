"""Final independent acceptance: defects found by recomputation, not by re-reading.

Every test here was written by the acceptance pass, not by the lane that owns
the region it names. Each asserts against the real artifact or the real
source, so it fails when the defect is present and passes only when the
defect is gone. None of them repairs anything: a failing test here is a
record for the next repair lane, not a licence to edit production code in
this pass.

Findings and their anchors:

- FA-01  `reports/workstreams/b13b-replseed.md:123` and
        `reports/cap-sheets/b-live-cap.md:48` still describe ONE powered
        panel. The census and source both say THREE. A stale claim about a
        measurement is a defect even when the sentence beside it is right.
- FA-02  `reports/evidence/invr1b4-mean-score/b4-crossover-mean.json` is the
        freeze four tests read, and it does not exist. The lane declared
        this honestly; the batch merged with four errors outstanding and no
        completion report naming them.
- FA-03  `reports/PLAN.md`'s lane table still says `b5-sealed-state` and
        `c4-live` are queued, and does not carry the lanes that actually
        landed. A plan whose state column is 100% stale cannot be used to
        decide what is outstanding.
- FA-04  `reports/evidence/inv_r1_e4/make_evidence.py:238` reads
        `channel.REACHABLE_EVIDENCE`, deleted by lane C4. The archived
        generator cannot run. Recorded rather than fixed: it is frozen
        history and repairing it would rewrite an archived artifact's
        generator.
- FA-05  `reports/PROJECT-LEDGER.md` and `docs/design/REFINEMENT-ROADMAP.md`
        own current status per AGENTS.md, and neither mentions this batch.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The single phrase P2 flagged at `p2-search.md:94` and left in place
# because the file belongs to another lane.
STALE_PHRASE = "only powered panel"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _panel_ids() -> dict:
    census = json.loads(_read("reports/evidence/invr1b8-panel-census/census.json"))
    return {p["panel_id"]: p for p in census["panels"]}


# --- FA-01: the singular "only powered panel" is a false claim ----------


def test_the_census_reports_three_powered_panels_not_one():
    """The fact the stale phrase contradicts, recomputed from the artifact.

    Three `graph` combinations reach six clusters with a positive ceiling.
    `graph:dev+transfer` is the SMALLEST of the three, which is why B13 and
    B14 name it. Smallest is not only.
    """
    census = json.loads(_read("reports/evidence/invr1b8-panel-census/census.json"))
    powered = census["verdict"]["powered_with_positive_ceiling"]
    assert len(powered) == 3, powered
    assert sorted(powered) == [
        "graph:dev+transfer",
        "graph:dev+within+transfer",
        "graph:within+transfer",
    ]
    for panel_id in powered:
        panel = _panel_ids()[panel_id]
        assert panel["cluster_count"] == panel["required_clusters"] == 6
        assert panel["shortfall"] == 0
        assert panel["max_attainable_positive_delta"] == pytest.approx(0.285714)


@pytest.mark.parametrize(
    "relative",
    [
        "reports/workstreams/b13b-replseed.md",
        "reports/cap-sheets/b-live-cap.md",
        "reports/PLAN.md",
        "reports/PROJECT-LEDGER.md",
        "reports/evidence/invr1b8-panel-census/census.json",
    ],
)
def test_no_governing_document_claims_one_powered_panel(relative):
    """FAILING on this tree: two of the five carry the singular claim.

    The cap sheet's sentence is about the three `graph` rows and is
    correct in meaning but wrong in number, so it is included. The
    `census.json` is checked too: an artifact that cannot be re-read by
    its own readers is not a durable artifact.
    """
    text = _read(relative)
    offenders = [
        (number, line.strip())
        for number, line in enumerate(text.splitlines(), 1)
        if STALE_PHRASE in line.lower()
    ]
    assert offenders == [], (
        "%s claims exactly one powered panel; the census measures three: %r"
        % (relative, offenders)
    )


def test_the_b13b_sentence_about_the_powered_graph_panel_reads_correctly():
    """The specific defect, named at file and line so the fix is locatable.

    `b13b-replseed.md:123` reads "would read nothing on the only powered
    panel". The panel it means is real and powered; the count is wrong.
    The repair is one word, and it belongs to that lane's owner, not here.
    """
    path = ROOT / "reports/workstreams/b13b-replseed.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = [
        (number, line)
        for number, line in enumerate(lines, 1)
        if STALE_PHRASE in line.lower()
    ]
    assert hits == [], (
        "%s:%s carries the singular claim. Three panels are powered; "
        "`graph:dev+transfer` is the smallest of them."
        % (path, [n for n, _ in hits])
    )


# --- FA-02: the cancelled B4 measurement stays unmeasured ---------------


def test_the_b4_freeze_remains_declared_unmeasured():
    """A cancelled sweep stays absent and the gate records that state."""
    source = _read("tests/test_inv_b4_constant_score.py")
    module = ast.parse(source)
    path_value = next(
        ast.literal_eval(statement.value)
        for statement in module.body
        if isinstance(statement, ast.Assign)
        and any(isinstance(target, ast.Name)
                and target.id == "FREEZE_PATH"
                for target in statement.targets)
    )
    assert not (ROOT / path_value).exists(), (
        "the cancelled crossover was never measured; creating its freeze "
        "would invent a result")
    fixture = next(node for node in module.body
                   if isinstance(node, ast.FunctionDef) and node.name == "freeze")
    assert "return None" in ast.get_source_segment(source, fixture)
    lane = " ".join(_read("reports/workstreams/b4-score.md").split())
    assert "cancelled measurement is not a null measurement" in lane


# --- FA-03: the plan's state column is stale in both directions ---------


def test_the_plan_names_the_lanes_that_actually_landed():
    """FAILING on this tree: the plan's state column is entirely pre-merge.

    `reports/PLAN.md`'s lane graph marks six lanes `running` and ten
    `queued`, and none of them `merged`. Sixteen workstream reports exist
    for lanes the table does not carry at all (a4b, a6, a7, a8, b9, b12,
    b13b, b14, b18, b1c, c3, c4, c6, c7, p1, p2, x1, x2). A reader asking
    "what is outstanding" gets an answer from a moment before any of it
    happened.
    """
    plan = _read("reports/PLAN.md")
    # Every lane that shipped has a workstream report on this tree.
    landed = [
        "a1-preflight", "a2-nodsn", "a3-action", "a4b-lostupdate",
        "a5-chain", "a6-callers", "a7-probe", "a8-improveauth",
        "b8-panel", "b10-capsheet", "b11-probe", "b12-swe", "b13b-replseed",
        "b14-retention", "b18-view", "c1-mission", "c2-freeze",
        "c3-fixture", "c4-construction", "c6-suspend", "c7-twodomain",
        "p1-search", "p2-search", "x1-sigfix", "x2-subscript",
    ]
    for lane in landed:
        assert (ROOT / "reports/workstreams" / ("%s.md" % lane)).exists(), (
            "the plan lists a lane with no report: %s" % lane
        )
    # Of the lanes the table DOES name, it names every one as unfinished.
    named_rows = [
        line for line in plan.splitlines()
        if re.match(r"\|\s*[abc]\d[\w-]*\s*\|", line)
        and line.rstrip().endswith("|")
    ]
    unfinished = [
        line for line in named_rows
        if re.search(r"\|\s*(running|queued[^|]*)\s*\|\s*$", line)
    ]
    assert unfinished == [], (
        "PLAN.md's lane graph still marks %d of %d named lanes `running` or "
        "`queued`, including a1-preflight which merged at 450a988 and whose "
        "gate is green on this tip. The State column carries no information, "
        "so it cannot be used to decide what is outstanding. Offending "
        "rows: %r"
        % (len(unfinished), len(named_rows), unfinished[:3])
    )


def test_the_plan_does_not_queue_lanes_that_were_never_run():
    """The other half. `b5-sealed-state` and `c4-live` really did not run.

    Naming them is correct. The finding is that the table gives them the
    same `queued` marker as the sixteen that shipped, so the column
    carries no information at all.
    """
    plan = _read("reports/PLAN.md")
    assert "| b5-sealed-state |" in plan, (
        "b5-sealed-state has left the plan table; if it is abandoned that "
        "needs saying, because WORKER-PROMPT.md section B asked for it"
    )
    assert "| c4-live |" in plan, (
        "c4-live has left the plan table; the bounded live revision "
        "attempt is the milestone-C deliverable and cannot be dropped "
        "silently"
    )


# --- FA-04: an archived generator keeps its historical input -------------


def test_the_archived_e4_generator_is_historical_and_uses_the_removed_menu():
    """The archived generator keeps its old input while current code drops it."""
    generator = _read("reports/evidence/inv_r1_e4/make_evidence.py")
    tree = ast.parse(generator)
    reads = [node for node in ast.walk(tree)
             if isinstance(node, ast.Attribute)
             and isinstance(node.value, ast.Name)
             and node.value.id == "channel"
             and node.attr == "REACHABLE_EVIDENCE"]
    assert len(reads) == 1
    assert reads[0].lineno == 238
    from experiments.ad01 import improve_channel as channel

    assert not hasattr(channel, "REACHABLE_EVIDENCE")


# --- FA-05: the documents that own current status do not carry the batch


@pytest.mark.parametrize(
    "relative",
    [
        "reports/PROJECT-LEDGER.md",
        "docs/design/REFINEMENT-ROADMAP.md",
    ],
)
def test_the_status_owning_documents_record_this_batch(relative):
    """FAILING on this tree: both still describe the 2026-09-30 closure.

    AGENTS.md names `PROJECT-LEDGER.md` as owning current status and
    `REFINEMENT-ROADMAP.md` as owning stage status. This batch ran ~26
    lanes, two live campaigns and two search passes, and neither document
    mentions any of it. The ledger's own `Stage status` line still reads
    "Stage 9 is active" with no note that a consolidation batch landed.
    """
    text = _read(relative)
    mentions_batch = (
        "stage09-consolidation-2026-10-01" in text
        or "invr1b12" in text
        or "consolidation batch" in text
    )
    assert mentions_batch, (
        "%s owns current status per AGENTS.md and does not mention the "
        "2026-10-01 consolidation batch, its two live campaigns, or its "
        "two search passes. A reader of the ledger cannot learn what "
        "this batch established from the ledger." % relative
    )