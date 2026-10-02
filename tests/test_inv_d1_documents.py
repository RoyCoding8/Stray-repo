"""Delivery lane D1: the documentary defects the acceptance pass found.

Every assertion here reads the real artifact, the real source or a named
document. None of them asserts that a document contains a phrase this lane
wrote: where a claim is a measurement, the measurement is re-derived and the
document is checked against it. That is the difference between a test that
pins a fact and one that pins its own author's wording.

Findings, by anchor:

- FA-01  Two live documents claimed exactly ONE powered panel. The census
        measures THREE, and `graph:dev+transfer` is the smallest of them.
        The cap sheet is the document that gates live dispatch.
- FA-02  A gate read a freeze artifact that was never committed. The lane
        declared the cancelled sweep honestly; the defect was that four
        errors were outstanding with no completion report naming them.
- FA-03  The plan's State column was entirely pre-merge: sixteen lanes
        unfinished, none merged, twenty-eight landed lanes absent.
- FA-04  Two archived generators are stale. They are ARCHIVED EVIDENCE and
        are not edited; the staleness is recorded instead.
- FA-05  The two documents that own current status did not record the batch.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The six dispositions, exactly as the acceptance pass issued them. A
# disposition is a verdict, so each is pinned separately: softening one
# must fail here rather than read as a stylistic choice.
DISPOSITIONS = {
    "mechanism": "CONFIRMED",
    "acquisition": "NEGATIVE",
    "utility": "NEGATIVE",
    "transfer": "NEGATIVE",
    "autonomous selection": "NOT ESTABLISHED",
    "learner improvement": "NEGATIVE",
}

STATUS_OWNING = [
    "reports/PROJECT-LEDGER.md",
    "docs/design/REFINEMENT-ROADMAP.md",
]

MATRIX = "reports/STAGE-09-10-COMPLETION-MATRIX.md"

# The singular claim FA-01 names at a file and a line.
STALE_PANEL_PHRASE = "only powered panel"

POWERED = {
    "graph:dev+transfer",
    "graph:within+transfer",
    "graph:dev+within+transfer",
}


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _flat(relative: str) -> str:
    """The document with its prose wrapping and emphasis collapsed.

    Documents are hard-wrapped, so a sentence is not readable as a substring
    across a line break, and emphasis markers sit inside the very words a
    claim is made of. Asserting on the raw text would make these gates tests
    of the documents' column width and their bolding rather than of what
    they say.
    """
    return " ".join(_read(relative).split()).replace("**", "")


def _census() -> dict:
    return json.loads(_read("reports/evidence/invr1b8-panel-census/census.json"))


# --- FA-01: three panels are powered, and the cap sheet must say so ------


def test_the_census_measures_three_powered_panels():
    """The fact the corrected documents assert, re-derived from the artifact.

    Recomputed here rather than trusted, so a document that claimed three
    would be caught if the census ever moved.
    """
    census = _census()
    powered = {p["panel_id"] for p in census["panels"] if p["powered"]}
    assert powered == POWERED, (
        "the powered set is %r; the documents were corrected against three "
        "graph combinations at ceiling 0.285714" % sorted(powered))
    for panel_id in sorted(POWERED):
        panel = next(p for p in census["panels"] if p["panel_id"] == panel_id)
        assert panel["cluster_count"] == panel["required_clusters"] == 6
        assert panel["shortfall"] == 0
        assert panel["max_attainable_positive_delta"] == pytest.approx(0.285714)


@pytest.mark.parametrize(
    "relative",
    [
        "reports/cap-sheets/b-live-cap.md",
        "reports/workstreams/b13b-replseed.md",
        "reports/PLAN.md",
        "reports/PROJECT-LEDGER.md",
        MATRIX,
    ],
)
def test_no_document_claims_exactly_one_powered_panel(relative):
    """The singular claim is false, so no current document may carry it.

    The cap sheet is the important one: it is the document that gates live
    dispatch, and a wrong count in it is read as an authorization fact.
    """
    offenders = [
        (number, line.strip())
        for number, line in enumerate(_read(relative).splitlines(), 1)
        if STALE_PANEL_PHRASE in line.lower()
    ]
    assert offenders == [], (
        "%s claims exactly one powered panel; the census measures three "
        "combinations, and `graph:dev+transfer` is the SMALLEST of them: %r"
        % (relative, offenders))


def test_the_cap_sheet_names_three_and_says_which_is_smallest():
    """A corrected cap sheet must carry the count AND the reason B13 named it.

    Changing "only" to "three" would pass the test above and lose the
    reason the smallest was chosen, which is the part a reader of a frozen
    cap sheet needs: the choice was a cost decision, not a power claim.
    """
    text = _flat("reports/cap-sheets/b-live-cap.md")
    plain = text.lower()
    assert "three panels are powered" in plain, (
        "the cap sheet does not state that three panels are powered; it "
        "gates live dispatch and must carry the count")
    assert "smallest" in plain, (
        "the cap sheet does not say that graph:dev+transfer is the smallest "
        "of the three, which is why B13 and B14 name it")
    # The count error sat beside a second one in the same sentence: the
    # census has seven software rows, not ten.
    assert "seven `software` rows" in plain or \
        "seven software rows" in plain, (
        "the cap sheet no longer counts the software rows correctly; the "
        "census has seven, and the sentence beside the repaired one said ten")


def test_the_cap_sheet_keeps_the_controls_it_was_verified_having():
    """The repair must not have weakened the rest of a frozen document.

    FA-01 was a count error in one sentence. The ceilings, the unresolved
    output-budget item and the carried-in-spend separation were all verified
    correct, and a cap sheet that lost them would be a worse defect than the
    one being fixed.
    """
    text = _flat("reports/cap-sheets/b-live-cap.md")
    for required in (
        "0.285714",
        "minimum_clusters_for_alpha",
        "the output budget is unresolved",
        "carried_in_true_exposure",
        "5563",
    ):
        assert required in text.lower(), (
            "the cap sheet no longer carries %r; the FA-01 repair must not "
            "have removed a ceiling, a freeze or a separation this sheet "
            "gates on" % required)


# --- FA-02: an unmeasured freeze is not a broken gate -------------------


def test_the_b4_freeze_is_still_absent_and_still_declared_unmeasured():
    """Nothing was measured, so nothing may have been created.

    The single `control_competence(40)` sweep was cancelled before it
    returned. Creating the artifact now would manufacture a crossover
    nobody measured, which is the one thing this finding forbids.
    """
    assert not (ROOT / "reports/evidence/invr1b4-mean-score").exists(), (
        "the B4 freeze artifact was created after the sweep was cancelled. "
        "A cancelled measurement is not a null measurement: the crossover "
        "is unknown in either direction and must not be written down.")


def test_the_b4_gate_reports_an_unmeasured_freeze_instead_of_erroring():
    """An absent measurement must read as unmeasured, not as a broken test.

    The old fixture called `pytest.fail` on the missing file, so four tests
    errored at setup. The gate now returns `None` and each consuming test
    asserts the absence is the declared one.
    """
    source = _read("tests/test_inv_b4_constant_score.py")
    assert "def freeze() -> dict | None:" in source, (
        "the freeze fixture no longer returns an optional value, so an "
        "absent measurement would again read as a broken gate")
    assert "pytest.fail" not in source, (
        "the B4 gate calls pytest.fail on the missing freeze again; an "
        "unmeasured freeze is a recorded state, not a failing test")
    assert "cancelled measurement is not a null measurement" in _flat(
        "tests/test_inv_b4_constant_score.py"), (
        "the gate no longer states the rule that makes the absence honest")


def test_the_b4_freeze_assertions_are_not_weakened_by_the_repair():
    """The single-budget rule must still bind, measured or not.

    The repair branched on the absent artifact. If the branch had also
    dropped the assertion that a crossing was never claimed, the freeze
    could later land claiming a first-crossing budget with nothing to
    catch it.
    """
    source = _read("tests/test_inv_b4_constant_score.py")
    for assertion in (
        'first_budget_behind_is_claimed',
        'agenda_beats_the_best_constant_rule',
        'crossover_scope',
        'control_rules_beating_it',
    ):
        assert assertion in source, (
            "the B4 gate no longer asserts on %r; the absent-freeze branch "
            "must narrow when the assertions run, not delete them" % assertion)


# --- FA-03: the plan records merged reality ------------------------------


LANDED_LANES = [
    "a1-preflight", "a2-nodsn", "a3-action", "a4b-lostupdate", "a5-chain",
    "a6-callers", "a7-probe", "a8-improveauth", "b8-panel", "b10-cap",
    "b11-probe", "b12-live", "b13b-replseed", "b14-retention", "b18-view",
    "c1-mission", "c2-freeze", "c3-fixture", "c4-construction", "c6-suspend",
    "c7-twodomain", "p1-search", "p2-search",
]

# A plan row names the lane; its workstream report is filed under a report
# stem. Three lanes differ, and the mapping is spelled out rather than
# guessed so a renamed report fails here instead of passing on a prefix.
LANE_REPORTS = {lane: lane for lane in LANDED_LANES}
LANE_REPORTS["b10-cap"] = "b10-capsheet"
LANE_REPORTS["b12-live"] = "b12-swe"

NEVER_RUN_LANES = ["b5-sealed-state", "c4-live"]


def test_every_lane_the_plan_calls_landed_has_its_report_and_a_commit():
    """A landed lane is one with a report on this tree and a merge commit.

    Both halves are checked. A row naming a lane with no report is a plan
    that credits work that did not happen; a report with no commit is a
    report of work that was never integrated.
    """
    plan = _read("reports/PLAN.md")
    for lane, report_stem in LANE_REPORTS.items():
        assert (ROOT / "reports/workstreams" / ("%s.md" % report_stem)).exists(), (
            "the plan calls %s landed and reports/workstreams/%s.md does not "
            "exist" % (lane, report_stem))
        row = [
            line for line in plan.splitlines()
            if line.startswith("| %s |" % lane)
        ]
        assert len(row) == 1, (
            "expected exactly one lane row for %s, found %d" % (lane, len(row)))
        state = row[0].rsplit("|", 2)[1].strip().lower()
        assert state.startswith("landed") and re.search(r"`\w{7}`", state), (
            "the State cell for %s does not open with `landed <commit>`: %r"
            % (lane, state[:80]))


def test_the_plan_marks_no_landed_lane_as_unfinished():
    """The defect was one marker for shipped and unshipped alike.

    A State column that cannot tell the two cannot answer "what is
    outstanding", which is the only question a plan is read for.
    """
    plan = _read("reports/PLAN.md")
    rows = [
        line for line in plan.splitlines()
        if re.match(r"\|\s*[abc]\d[\w-]*\s*\|", line) and line.rstrip().endswith("|")
    ]
    unfinished = [
        line for line in rows
        if re.search(r"\|\s*(running|queued[^|]*)\s*\|\s*$", line)
    ]
    assert unfinished == [], (
        "the lane graph still marks %d of %d rows `running` or `queued`; the "
        "State column must distinguish landed from never run: %r"
        % (len(unfinished), len(rows), unfinished))


def test_the_never_run_lanes_are_recorded_as_never_run():
    """Both, and with the reason. Inventing a c4-live result is forbidden.

    `c4-live` is the milestone-C deliverable, so it cannot be dropped
    silently; and the batch acquired nothing, so no result for it could
    honestly exist.
    """
    plan = _flat("reports/PLAN.md")
    for lane in NEVER_RUN_LANES:
        assert "| %s |" % lane in _read("reports/PLAN.md"), (
            "%s has left the plan table; a never-run lane must be recorded "
            "as outstanding, not removed" % lane)
    assert plan.lower().count("never run") >= len(NEVER_RUN_LANES), (
        "the plan does not mark both never-run lanes as never run; the "
        "marker is what distinguishes them from the merged ones")
    # No result may be claimed for a lane that never ran. The verdict is
    # the opening of the State cell, not the whole cell: the c4-live row
    # legitimately names a lane that DID land, in its explanation of why
    # the mechanism exists but was never attempted against.
    for lane in NEVER_RUN_LANES:
        row = [ln for ln in _read("reports/PLAN.md").splitlines()
               if ln.startswith("| %s |" % lane)][0]
        verdict = row.rsplit("|", 2)[1].strip().lower()
        assert verdict.startswith("**never run"), (
            "the plan's State cell for %s opens with %r; it must open with "
            "the never-run verdict" % (lane, verdict[:60]))


# --- FA-04: recorded, never edited ---------------------------------------


def test_the_archived_generators_are_untouched_and_still_stale():
    """Archived evidence stays byte-identical, and its staleness is recorded.

    The C4 deletion of the fixed menu is the correct repair. These
    generators are the one place it leaves a dangling reader, and repairing
    them would rewrite an archived artifact's generator. So they are
    recorded, in prose, outside the evidence tree.
    """
    e4 = _read("reports/evidence/inv_r1_e4/make_evidence.py")
    assert "REACHABLE_EVIDENCE" in e4, (
        "the archived e4 generator no longer reads the deleted menu; this "
        "finding is stale and may be dropped")

    e2 = _read("reports/evidence/inv_r1_e2_offline/make_evidence.py")
    assert 'capability_id = "seed-%s-%s" % (prefix, method)' in e2, (
        "the archived e2 generator no longer mints seed-prefixed ids; this "
        "finding is stale and may be dropped")

    # The staleness is recorded, in the acceptance report and the matrix.
    for record in ("reports/FINAL-ACCEPTANCE.md", MATRIX):
        flat = _flat(record)
        assert "inv_r1_e4/make_evidence.py" in flat, (
            "%s does not record the archived e4 generator" % record)
        assert "inv_r1_e2_offline/make_evidence.py" in flat, (
            "%s does not record the archived e2 generator" % record)


def test_the_b14_freeze_requirements_still_hold_after_the_fa01_repair():
    """B14's own contract with the cap sheet survives the correction.

    `tests/test_inv_b14_retention.py` pins the cap sheet byte-for-byte to
    `794520f`, so correcting FA-01 necessarily breaks that pin. The pin is
    not in this lane's ownership and is not rewritten here. What IS this
    lane's obligation is to show the pin's *purpose* — B14 needs a new
    freeze, and the parent sheet allocates nothing to it — still holds on
    the corrected sheet, so the conflict is a pin over the wrong thing
    rather than a loss of the freeze discipline.
    """
    sheet = _read("reports/cap-sheets/b-live-cap.md").replace("\r\n", "\n")
    for required in (
        "`B14` and `B15` are **not allocated",
        "They need a new freeze of this sheet",
    ):
        assert required in sheet, (
            "the corrected cap sheet no longer carries %r; B14's freeze "
            "discipline is a live contract and the FA-01 repair must not "
            "have disturbed it" % required)


def test_the_fa01_repair_is_the_only_change_to_the_cap_sheet():
    """A frozen document must change only where the finding was.

    The acceptance pass verified the sheet's ceilings, its unresolved
    output-budget item and its carried-in-spend separation as correct. This
    pins that the correction is confined to the panel-count sentence, by
    asserting every other line of the frozen sheet survives unchanged.

    The base blob is read through B14's own git helper, because a linked
    worktree needs `--git-dir` under WSL and this repository needs
    `safe.directory`; duplicating that plumbing here would be a second
    answer to the same question.
    """
    from tests.test_inv_b14_retention import _git_prefix

    recorded = subprocess.run(
        ["git", *_git_prefix(), "cat-file", "blob",
         "794520f:reports/cap-sheets/b-live-cap.md"],
        cwd=str(ROOT), capture_output=True, check=True,
    ).stdout.decode("utf-8").replace("\r\n", "\n")
    current = _read("reports/cap-sheets/b-live-cap.md").replace("\r\n", "\n")

    current_lines = [ln.strip() for ln in current.splitlines() if ln.strip()]
    removed = [
        line for line in recorded.splitlines()
        if line.strip() and line.strip() not in current_lines
        # The two lines the finding named are allowed to change; nothing
        # else in a frozen sheet is.
        and "only powered panels" not in line
        and "ten `software`" not in line
        and "unpowered remainder" not in line
        and "from this table" not in line
        and "is empty, because" not in line
        and "every panel that reaches" not in line
    ]
    assert removed == [], (
        "the FA-01 repair changed lines in the frozen cap sheet that had "
        "nothing to do with the finding: %r" % removed)
    assert "only powered panels" in recorded, (
        "the base blob no longer carries the stale claim; this finding is "
        "stale and may be dropped")


def test_no_file_was_added_to_the_two_archived_evidence_directories():
    """A note beside the generators would be the first step to editing one.

    The assignment permits a note only if the directory allows it without
    touching the generators. Two such notes would make the archives
    ambiguous about which bytes are frozen, so the record lives in the
    acceptance report instead.
    """
    for directory in (
        "reports/evidence/inv_r1_e4",
        "reports/evidence/inv_r1_e2_offline",
    ):
        names = {p.name for p in (ROOT / directory).iterdir()}
        assert "STALENESS.md" not in names
        assert "NOTE.md" not in names
        assert "README.md" not in names, (
            "%s has gained a README; archived evidence directories are "
            "frozen and the staleness is recorded in the acceptance report"
            % directory)


# --- FA-05: the status-owning documents carry the batch ------------------


@pytest.mark.parametrize("relative", STATUS_OWNING)
def test_the_status_owning_document_records_this_batch(relative):
    """AGENTS.md names these two as owning current status.

    They described the 2026-09-30 closure and had no mention of the batch,
    its two live campaigns or its two search passes. A reader of the ledger
    could not learn from the ledger what the batch established.
    """
    text = _read(relative)
    assert "consolidation batch" in text.lower() or \
        "stage09-consolidation-2026-10-01" in text, (
            "%s owns current status and does not record the 2026-10-01 batch"
            % relative)


@pytest.mark.parametrize("relative", STATUS_OWNING)
def test_the_status_owning_document_states_all_six_dispositions(relative):
    """All six, each named, none softened.

    The test is that the disposition word appears beside its question. A
    document that says "acquisition is negative" passes; one that says
    "acquisition was limited" does not. The mechanism result must not be
    allowed to imply the others, so this asserts each independently.
    """
    flat = _flat(relative).lower()
    missing = [
        "%s (%s)" % (question, verdict)
        for question, verdict in DISPOSITIONS.items()
        if question not in flat or verdict.lower() not in flat
    ]
    assert missing == [], (
        "%s does not state these dispositions as acceptance issued them: %r. "
        "Each is a verdict and none may be softened or omitted; the "
        "mechanism result does not license the others."
        % (relative, missing))


def test_the_utility_disposition_is_not_measurable_and_says_so():
    """Utility is the disposition most likely to be softened into "partial".

    It is not measurable: a failed acquisition is never promoted to an
    authored learned arm, so there is no arm to compare. A document that
    calls it merely negative has dropped the reason.
    """
    for relative in STATUS_OWNING + [MATRIX]:
        flat = _flat(relative).lower()
        assert "not measurable" in flat, (
            "%s does not record that utility is not measurable rather than "
            "merely negative" % relative)


def test_the_learner_improvement_result_is_not_inferred_from_the_mechanism():
    """The two must not blur. A confirmed mechanism is not an improved
    learner, and the inheritable construction procedure existing is not a
    revision that ran."""
    for relative in STATUS_OWNING + [MATRIX]:
        flat = _flat(relative).lower()
        assert "does not claim beneficial rsi" in flat or \
            "no eligible revision ran" in flat, (
            "%s must state that the prototype's existence does not claim "
            "beneficial RSI; the mechanism result is not a learner result"
            % relative)


def _ranked_bottlenecks(relative: str) -> list[str] | None:
    """The numbered items in a document's bottleneck section.

    Read from the raw lines rather than a flattened string, because a
    section boundary is a line structure. Returns None when the document
    has no such section, which is legitimate: the roadmap carries the
    stage model and the ledger carries the ranking.
    """
    lines = _read(relative).splitlines()
    start = None
    for number, line in enumerate(lines):
        if line.lstrip("#").strip().lower().endswith("bottlenecks"):
            start = number
            break
    if start is None:
        return None
    body = []
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        body.append(line)
    return re.findall(r"^\s*(\d+)\.\s", "\n".join(body), re.MULTILINE)


def test_the_ledger_ranks_exactly_three_bottlenecks():
    """The assignment permits no more than three, and the ceiling binds.

    The ledger is where the short list lives, so the ceiling is enforced
    there.
    """
    ranked = _ranked_bottlenecks("reports/PROJECT-LEDGER.md")
    assert ranked is not None, (
        "the ledger has no ranked-bottleneck section; the batch owes the next "
        "worker the short list")
    assert ranked == ["1", "2", "3"], (
        "the ledger ranks %r; the assignment permits no more than three"
        % ranked)


@pytest.mark.parametrize("relative", STATUS_OWNING)
def test_no_status_document_exceeds_the_three_bottleneck_ceiling(relative):
    """Neither status document may exceed the ceiling, wherever it ranks them.

    The ceiling is a property of the batch, not of one document, so a
    second list elsewhere would breach it even though each list alone
    looks short.
    """
    ranked = _ranked_bottlenecks(relative)
    if ranked is None:
        return
    assert len(ranked) <= 3, (
        "%s ranks %d bottlenecks; the assignment permits no more than three"
        % (relative, len(ranked)))


def test_the_roadmap_names_the_two_binding_constraints():
    """The roadmap carries the stage model, so it must carry the two facts
    that decide what stage 9 does next: the output budget that bounds
    acquisition, and the unpowered Boolean side that makes the two-domain
    question unaskable. Without them a reader of the roadmap cannot tell
    why stage 9 is still open."""
    flat = _flat("docs/design/REFINEMENT-ROADMAP.md").lower()
    for anchor in ("2048", "hypothesis class", "not a two-domain result"):
        assert anchor in flat, (
            "the roadmap no longer records %r, which is what makes stage 9's "
            "remaining work specific rather than open-ended" % anchor)


def test_the_three_ranked_bottlenecks_are_architecture_relevant():
    """Each must name a mechanism, not a symptom.

    "acquisition returned zero" is a result. "the output budget is the
    binding constraint on the acquisition route" is an architectural
    bottleneck, because it says what would have to change.
    """
    ledger = _flat("reports/PROJECT-LEDGER.md")
    section = re.search(
        r"three architecture-relevant bottlenecks(.*?)(?=\n## |\Z)",
        ledger, re.IGNORECASE | re.DOTALL)
    assert section, "the ledger no longer names its bottleneck section"
    body = section.group(1).lower()
    for anchor in (
        "acquisition rate is zero",
        "output budget",
        "not powered",
    ):
        assert anchor in body, (
            "the ranked bottlenecks no longer name %r; each must point at a "
            "mechanism rather than restate a measurement" % anchor)


# --- the honest live numbers --------------------------------------------


def test_the_ledger_live_numbers_match_the_evidence():
    """Every live figure in the ledger is re-derived from the artifact.

    These are the numbers a reader will act on, so they are pinned to the
    evidence rather than to the ledger's own text.
    """
    b12 = json.loads(_read("reports/evidence/invr1b12-swe/campaign.json"))
    summary = b12["summary"]
    assert summary["acquired_lineages"] == 0
    assert summary["lineages_attempted"] == 4
    assert summary["no_acquisition_lineages"] == 4
    assert summary["physical_sends"] == 5
    assert all(
        lineage["acquisition_digest"] is None
        for lineage in b12["construction"]["lineages"])

    b14 = json.loads(_read("reports/evidence/invr1b14-retention/retention.json"))
    members = b14["live_acquired_members"]
    assert len(members) == 3
    rows = [row for m in members for row in m["rows"]]
    comparable = [r for r in rows if not r["acquisition_task"]]
    assert len(rows) == 27
    assert len(comparable) == 26
    assert {r["verdict"] for r in comparable} == {"preserved"}
    assert sum(1 for r in comparable if r["same_reduction_as_seed"]) == 26

    b11 = json.loads(_read("reports/evidence/invr1b11-budget/budget-probe.json"))
    assert b11["sends_used"] == b11["authorised_sends"] == 6
    served = [r for r in b11["rungs"] if r["kind"] != "lost-response"]
    assert [r["max_output_tokens"] for r in served] == [16, 64, 256, 1024, 2048]

    ledger = _flat("reports/PROJECT-LEDGER.md")
    for figure in ("0 of 4 lineages", "0 of 3", "27 executions", "19"):
        assert figure in ledger, (
            "the ledger no longer carries the live figure %r that this "
            "artifact recomputation confirms" % figure)


def test_the_output_budget_constraint_is_recorded_as_the_binding_one():
    """The one positive finding from the live campaigns.

    The route serves 2048 output tokens; the authored control is 22734
    characters and the loader accepts 7000. No response at the frozen
    budget could carry the policy. This is the finding that makes the
    acquisition zero actionable rather than merely disappointing.
    """
    b12 = json.loads(_read("reports/evidence/invr1b12-swe/campaign.json"))
    construction = b12["construction"]
    assert construction["max_output_tokens"] == 2048
    assert construction["authored_source_characters"] == 22734
    assert construction["max_source_characters"] == 7000

    for relative in STATUS_OWNING + [MATRIX]:
        flat = _flat(relative).lower()
        assert "2048" in flat, (
            "%s does not record the served output budget, which is the "
            "binding constraint on every acquisition result" % relative)


def test_no_credential_value_appears_in_any_document_this_lane_wrote():
    """The sweep the acceptance pass ran, re-run over this lane's own diff.

    Names are not values. `SETTLEMENT_GATEWAY_KEY` appears in these
    documents as a variable name, and the acceptance report names it as one
    of the *patterns* it swept for; what must not appear is an assignment
    carrying a literal, so the variable pattern requires a value-like
    right-hand side rather than any non-space character. The B12 runner
    reads a key from the environment and prints only its name and length.
    """
    patterns = [
        re.compile(r"sk-[A-Za-z0-9]{16,}"),
        re.compile(r"ghp_[A-Za-z0-9]{20,}"),
        re.compile(r"nvapi-[A-Za-z0-9]{16,}"),
        # A value, not a mention: an unquoted token or a quoted string.
        re.compile(r"SETTLEMENT_GATEWAY_KEY\s*=\s*[\"']?[A-Za-z0-9_\-]{8,}"),
        re.compile(r"postgresql://[^\s:]+:[^\s@]+@"),
    ]
    for relative in STATUS_OWNING + [
        "reports/PLAN.md",
        "reports/cap-sheets/b-live-cap.md",
        "reports/workstreams/b13b-replseed.md",
        "reports/FINAL-ACCEPTANCE.md",
        MATRIX,
    ]:
        hits = [p.pattern for p in patterns if p.search(_read(relative))]
        assert hits == [], (
            "%s contains a credential value: %r" % (relative, hits))
