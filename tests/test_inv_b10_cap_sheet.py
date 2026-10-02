"""B10: the B cap sheet, checked against its own numbers and its own prohibition.

A cap sheet is a record nobody reads twice, so nothing enforces it. That is the
defect this file repairs. It PARSES `reports/cap-sheets/b-live-cap.md` and asserts
literal values out of it, so a hand-edit that raises a cap, swaps the model, or
pastes a key fails rather than being inherited silently by the next study.

The numbers asserted here are not this lane's preferences. They are the derivation
in the sheet, checked against two independent sources so a typo in the sheet fails
instead of being copied onward:

- the panel numbers come from `reports/evidence/invr1b8-panel-census/census.json`,
  the B8 census, which is itself reproducible from the frozen world;
- the per-request unit figure is recomputed through
  `settlement.broker.exposure_schedule` and compared to the archived contrast's own
  `cap_sheet.unit_allowance.per_request_units`.

Nothing here calls a model, touches the network, or needs a database. The gate is
scoped to this file on purpose.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

SHEET_PATH = ROOT / "reports" / "cap-sheets" / "b-live-cap.md"
CENSUS_PATH = ROOT / "reports" / "evidence" / "invr1b8-panel-census" / "census.json"
CONTRAST_PATH = ROOT / "reports" / "evidence" / "invr1e2contrast" / "report.json"

SHEET = SHEET_PATH.read_text(encoding="utf-8")
# One whitespace-normalised view. A cap sheet is hard-wrapped prose, so a phrase
# that spans a line break is the same phrase; the test must not depend on where
# the author happened to wrap. The raw SHEET is still used where a literal
# inside one line is the thing being asserted.
FLAT = " ".join(SHEET.split())

CENSUS = json.loads(CENSUS_PATH.read_text(encoding="utf-8"))
CONTRAST = json.loads(CONTRAST_PATH.read_text(encoding="utf-8"))

# The pinned route, as literals, so a changed model or a changed host is a failure
# and not a silent substitution.
MODEL_ID = "nvidia/nemotron-3-ultra-550b-a55b:free"
ENDPOINT = "http://127.0.0.1:4000/v1"
KEY_VARIABLE = "SETTLEMENT_GATEWAY_KEY"

# The ceilings the sheet freezes. Raising one of these without re-deriving the
# totals below must fail this file.
EXPECTED_STUDY_CAPS = {
    "B11": (6, 0, 6),
    "B12": (24, 1, 25),
    "B13": (37, 1, 38),
    "B16": (8, 1, 9),
}
EXPECTED_TOTAL_DISPATCHES = 75
EXPECTED_TOTAL_SENDS = 78
EXPECTED_UNITS_PER_REQUEST = 2492
EXPECTED_TOTAL_UNITS = 194376

# Carried-in historical exposure. Independent of the allocation above; the sheet
# must not net it against the new cap and must not call it settled.
CARRIED_IN_VERIFIED_SUBTOTAL = 5563


def _named_value(name: str) -> str:
    """Read `name: value` out of the machine-readable block, not the prose.

    The block is the sheet's own record of its ceilings. Prose above it explains
    them; this is where a test can hold a number to.
    """
    block = re.search(r"```text\n(.*?)```", SHEET, re.DOTALL)
    assert block is not None, "the cap sheet has no machine-readable figures block"
    match = re.search(rf"^{re.escape(name)}:\s*(.+?)\s*$", block.group(1), re.MULTILINE)
    assert match is not None, f"the cap sheet states no {name}"
    return match.group(1)


def _study_caps() -> dict[str, tuple[int, int, int]]:
    """Parse the dispatch table rows out of the sheet itself.

    A row is `| `B11` label | 6 | 0 | 6 | basis |`. Reading it here rather than
    restating it is the point: the test then fails if a number in the table moves.
    """
    rows = re.findall(
        r"^\|\s*`(B\d+)`[^|]*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
        SHEET,
        re.MULTILINE,
    )
    return {name: (int(a), int(b), int(c)) for name, a, b, c in rows}


# --------------------------------------------------------------------------
# 1. The route is the loopback free route, and the model id ends in :free
# --------------------------------------------------------------------------


def test_the_route_is_the_loopback_gateway_and_the_model_id_is_free_tier() -> None:
    """A paid or non-loopback route would be an unauthorized dispatch."""
    assert ENDPOINT in SHEET
    assert MODEL_ID in SHEET
    assert MODEL_ID.endswith(":free")
    assert f"`{MODEL_ID}`" in SHEET
    # the endpoint is loopback, spelled as a URL and not as a bare port
    assert ENDPOINT.startswith("http://127.0.0.1:")
    assert ENDPOINT.endswith("/v1")


def test_the_catalog_count_recorded_is_the_live_one_and_not_the_superseded_one() -> None:
    """219 is today's live catalog. 256 is the archived probe and is history."""
    assert "219 entries" in SHEET
    assert "32 free-tier" in SHEET
    assert "2026-10-01" in SHEET
    # the superseded 256 figure is named as superseded, never as the current state
    assert "256-entry catalog that the archived probe recorded is superseded" in SHEET
    assert f"model_count: {219}" not in SHEET


# --------------------------------------------------------------------------
# 2. No credential value appears anywhere in the sheet
# --------------------------------------------------------------------------


def test_no_credential_value_appears_anywhere_in_the_sheet() -> None:
    """The key variable is named; its value never is."""
    assert KEY_VARIABLE in SHEET, "the sheet must name the variable it reads"
    assert "SETTLEMENT_GATEWAY_ENDPOINT" in SHEET

    # no `sk-` prefix, which is the OpenRouter/most-vendors secret shape
    assert "sk-" not in SHEET, "a credential value reached the cap sheet"

    # no high-entropy run that could be a key in another spelling. Paths and
    # snake_case identifiers are the only long runs a cap sheet legitimately
    # holds, so the assertion is on the character classes a key uses, not on
    # length alone.
    for token in re.findall(r"[A-Za-z0-9+/=_-]{24,}", FLAT):
        assert "/" in token or "_" in token or "-" in token or re.fullmatch(
            r"[0-9a-f]{24,}", token
        ), f"a bare opaque token in the cap sheet: {token[:8]}..."

    # a `KEY=<something>` or `key: <something>` assignment would be the value
    assert not re.search(rf"{KEY_VARIABLE}\s*[=:]\s*\S", SHEET), (
        "the key variable is assigned a value somewhere in the sheet"
    )
    assert not re.search(r"(?i)key\s*[:=]\s*[A-Za-z0-9]", SHEET), (
        "a key is given a value in the sheet"
    )

    # and the sheet says so in its own words
    assert "No key value appears in this sheet" in SHEET
    assert "mode 600" in SHEET
    assert "outside Git" in SHEET


def test_the_repository_records_the_key_variable_by_name_only() -> None:
    """The sheet is not a special case. No cap sheet may carry a key value."""
    for path in sorted((ROOT / "reports" / "cap-sheets").glob("*")):
        if path.suffix != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        assert "sk-" not in text, f"{path.name} carries a credential value"
        assert not re.search(rf"{KEY_VARIABLE}\s*[=:]\s*[A-Za-z0-9]", text), (
            f"{path.name} assigns a value to the gateway key variable"
        )


# --------------------------------------------------------------------------
# 3. Every dispatch cap is a positive integer and the sum is bounded
# --------------------------------------------------------------------------


def test_every_study_dispatch_cap_is_a_positive_integer_and_matches_its_ladder() -> None:
    """The table is parsed, then compared to the literal ceilings."""
    caps = _study_caps()
    assert set(caps) == set(EXPECTED_STUDY_CAPS), (
        "the dispatch table names different studies than this test pins"
    )
    for study, (dispatches, retries, sends) in caps.items():
        assert dispatches > 0, f"{study} has a non-positive dispatch cap"
        assert retries >= 0, f"{study} has a negative retry allowance"
        assert sends > 0, f"{study} has a non-positive send ceiling"
        assert caps[study] == EXPECTED_STUDY_CAPS[study], f"{study} moved a cap"


def test_the_dispatch_caps_sum_to_the_stated_total_and_no_more() -> None:
    """75 dispatches, 78 sends, and the sum is checked, not trusted."""
    caps = _study_caps()
    total_dispatches = sum(d for d, _, _ in caps.values())
    total_sends = sum(s for _, _, s in caps.values())
    total_retries = sum(r for _, r, _ in caps.values())

    assert total_dispatches == EXPECTED_TOTAL_DISPATCHES
    assert total_sends == EXPECTED_TOTAL_SENDS
    assert total_dispatches <= EXPECTED_TOTAL_DISPATCHES
    assert total_sends <= EXPECTED_TOTAL_SENDS

    assert int(_named_value("total_dispatch_cap")) == total_dispatches
    assert int(_named_value("total_physical_send_ceiling")) == total_sends
    assert total_retries == 3

    # each send is a dispatch plus its own retries, so the two are derivable
    for study, (dispatches, retries, sends) in caps.items():
        assert sends == dispatches + retries, f"{study} sends are not dispatches+retries"


def test_the_unit_allowance_is_recomputed_through_the_broker_not_restated() -> None:
    """2492 comes from the real exposure schedule, checked against the archive."""
    from settlement import broker

    units, kind = broker.exposure_schedule(
        broker.MODEL_INFERENCE,
        {
            "messages": [{"content": "x" * 1774}],
            "max_output_tokens": 2048,
        },
        0,
    )
    assert kind == "estimated-budget"
    assert units == EXPECTED_UNITS_PER_REQUEST
    # the derivation is the one the archived contrast recorded, not a new number
    assert CONTRAST["cap_sheet"]["unit_allowance"]["per_request_units"] == units

    assert int(_named_value("per_request_units")) == EXPECTED_UNITS_PER_REQUEST
    assert int(_named_value("requests")) == EXPECTED_TOTAL_SENDS
    assert int(_named_value("total_units")) == EXPECTED_TOTAL_UNITS
    assert _named_value("unit_kind") == "estimated-budget"
    assert EXPECTED_UNITS_PER_REQUEST * EXPECTED_TOTAL_SENDS == EXPECTED_TOTAL_UNITS


def test_the_studies_that_are_gated_record_zero_rather_than_disappearing() -> None:
    """B14 and B15 need a new freeze of the sheet, not a line in this one."""
    assert "not allocated and not in this total" in SHEET
    assert "**not allocated and not in this total.**" in SHEET
    assert "B14" in SHEET and "B15" in SHEET
    for gated in ("B14", "B15"):
        assert gated not in _study_caps(), (
            f"{gated} gained a dispatch cap without a new freeze of this sheet"
        )


# --------------------------------------------------------------------------
# 4. The output-budget item is present and marked unresolved
# --------------------------------------------------------------------------


def test_the_output_budget_is_present_and_marked_unresolved() -> None:
    """It is the first bounded item and this sheet must not resolve it."""
    assert "## The output budget is UNRESOLVED" in SHEET
    assert "**Status: UNRESOLVED." in SHEET
    assert "does not establish it" in SHEET
    assert "output-budget-causes-the-502" in SHEET

    # the recorded observations behind it, as literals
    assert "200 at 16 and at 256 output tokens" in FLAT
    assert "502 at the protocol's own 2048" in FLAT
    assert "a short prompt returns 200 at 2048" in FLAT
    assert "`max_output_tokens: 2048`" in SHEET

    # B11 is the bounded measurement, and it is first in the dispatch table
    assert _study_caps()["B11"] == EXPECTED_STUDY_CAPS["B11"]
    assert "served output budget" in FLAT
    # and it is the first thing an operator does, not an assumption
    assert "the first thing any" in FLAT
    assert "Its outcome is a new freeze." in SHEET

    # a changed budget is a new freeze, not a repair
    assert "does not make older and newer runs comparable" in FLAT


# --------------------------------------------------------------------------
# 5. Carried-in exposure is mentioned and NOT netted against the new cap
# --------------------------------------------------------------------------


def test_carried_in_historical_exposure_is_recorded_and_not_netted() -> None:
    """5563 uncertain, >= 5563 true, and the new cap is independent of it."""
    assert str(CARRIED_IN_VERIFIED_SUBTOTAL) in SHEET
    assert ">= 5563" in SHEET
    assert "**not** settled" in SHEET
    assert "**not** subtracted from the allocation above" in FLAT

    # the machine-readable record, so a later editor cannot drop it silently
    assert int(_named_value("carried_in_uncertain_units")) == CARRIED_IN_VERIFIED_SUBTOTAL
    assert _named_value("carried_in_true_exposure") == ">= 5563"
    assert _named_value("carried_in_netted_against_this_allocation") == "false"
    # and the 5563 sits beside the 194376, not inside it
    assert int(_named_value("total_units")) == EXPECTED_TOTAL_UNITS

    # the independent-of statement, in the sheet's own words
    assert "allocation above is independent of the 5563" in SHEET
    assert "194376 is not 194376 minus" in SHEET

    # the arithmetic the ledger records, not a rounded or invented one
    assert "2294" in SHEET and "3269" in SHEET
    assert 2294 + 3269 == CARRIED_IN_VERIFIED_SUBTOTAL

    # the excluded unidentified reservation stays excluded and named nowhere
    assert "excluded from every reconciliation artifact and identified nowhere" in FLAT
    assert "invl02_live" in SHEET

    # the netted figure must not appear as a total anywhere
    assert str(EXPECTED_TOTAL_UNITS - CARRIED_IN_VERIFIED_SUBTOTAL) not in SHEET
    assert str(EXPECTED_TOTAL_DISPATCHES - CARRIED_IN_VERIFIED_SUBTOTAL) not in SHEET


# --------------------------------------------------------------------------
# 6. The matrix is the census, not a preference
# --------------------------------------------------------------------------


def test_the_recorded_panel_is_the_census_powered_panel_with_a_positive_ceiling() -> None:
    """Read the census, then assert the sheet's numbers against it."""
    by_id = {p["panel_id"]: p for p in CENSUS["panels"]}
    supported = "graph:dev+transfer"
    panel = by_id[supported]

    assert CENSUS["required_clusters"] == 6
    assert CENSUS["alpha"] == "1/20"
    assert CENSUS["cluster_rule"] == "(family, template)"
    assert CENSUS["model_calls"] == 0

    assert panel["cluster_count"] == 6
    assert panel["required_clusters"] == 6
    assert panel["shortfall"] == 0
    assert panel["powered"] is True
    assert panel["max_attainable_positive_delta"] == 0.285714
    # the census rounds; 2/7 is the exact ceiling and the sheet records both
    assert round(panel["max_attainable_positive_delta"], 6) == 0.285714
    assert abs(panel["max_attainable_positive_delta"] - 2 / 7) < 1e-6
    assert panel["open_rows"] == 6
    assert panel["rows_measured"] == 6
    assert panel["minimum_p"] == "1/32"

    # it is the SMALLEST powered panel, which is why it was chosen
    powered = [p for p in CENSUS["panels"] if p["powered"]]
    assert min(p["cluster_count"] for p in powered) == 6
    assert min(len(p["task_ids"]) for p in powered) == 6

    # and the sheet says those numbers
    assert "| `graph:dev+transfer` | 6 | 6 | 0 | yes | 0.285714 | 1/32 | 6/6 |" in SHEET
    assert "`graph:dev+transfer`" in SHEET


def test_the_software_family_is_short_on_every_combination_it_offers() -> None:
    """Four software templates against six required. No split choice saves it."""
    software = [p for p in CENSUS["panels"] if p["family"] == "software"]
    assert len(software) == 7
    assert max(p["cluster_count"] for p in software) == 4
    assert min(p["shortfall"] for p in software) == 2
    assert all(p["powered"] is False for p in software)
    assert not any(
        "software" in panel_id
        for panel_id in CENSUS["verdict"]["powered_with_positive_ceiling"]
    )

    assert "software_templates_in_frozen_world: 4" in SHEET
    assert "required_clusters: 6" in SHEET

    # the archived contrast really did run the short panel
    sign = CONTRAST["sign_flip"]
    assert sign["required_clusters_at_alpha_1_20"] == 6
    assert sign["minimum_p"] in ("1/2", "1")


def test_no_panel_is_powered_and_blind_so_the_two_do_not_trade_off() -> None:
    assert CENSUS["verdict"]["powered_but_blind"] == []
    assert "powered_but_blind` is empty" in SHEET
    # and the sheet does not claim the retention leg
    assert "claims no retention result" in SHEET
    assert "is not the retention closure" in SHEET


# --------------------------------------------------------------------------
# 7. The freeze, the stopping condition and the honest-unknown rules
# --------------------------------------------------------------------------


def test_the_frozen_items_and_the_cost_of_a_change_are_named() -> None:
    assert "Status: FROZEN before any effect" in SHEET
    assert "## What is frozen, and what a change costs" in SHEET
    for item in (
        "source tip",
        "endpoint",
        "requested model id",
        "panel",
        "selectors",
        "per-request bounds",
    ):
        assert item in SHEET, f"the freeze does not name {item}"
    assert "creates a NEW freeze" in SHEET
    assert "does not retroactively" in SHEET


def test_the_stopping_condition_is_finite_and_stated_in_advance() -> None:
    assert "## The stopping condition, stated in advance" in SHEET
    assert "78 physical sends" in SHEET
    assert "6 B11 ladder rungs" in SHEET
    assert "30-day" in SHEET
    assert "does not authorize a replacement" in SHEET
    assert "is not replication" in SHEET
    assert "There is no search for a positive result" in SHEET
    # the free tier is not a licence to widen the numbers
    assert "not a reason to widen any of these numbers" in SHEET


def test_unknown_is_never_written_as_zero() -> None:
    assert "Unknown is recorded as unknown" in SHEET
    assert "never written as zero" in SHEET
    assert "the route is free and not a statement that it is not" in SHEET
    assert "**UNVERIFIED**" in SHEET
    assert "Rate limits, quota, concurrency" in SHEET
    assert "Unknown is recorded as unknown and is never written as zero." in " ".join(
        SHEET.split()
    )
    # the missing preconditions are recorded rather than removed
    for unmet in (
        "Out-of-process execution carries authority",
        "Uncertain historical reservation identified",
        "Confined read denial",
        "Served output budget",
    ):
        assert unmet in SHEET, f"precondition {unmet} vanished from the sheet"
    assert "Recording the gap is not removing it." in SHEET
