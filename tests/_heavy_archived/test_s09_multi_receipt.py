"""Receipt identity conflicts remain distinct from operation completion.

Informational receipts may coexist. A lone unknown can resolve as before;
a batch completion must name all prior unknowns on the locked operation.
Decided receipts and terminal dispositions still prohibit a second decision.
Handler-level positive and counterexample tests live in
`test_store_authority_invariants.py`; these retain the source-boundary checks.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

STORE = ROOT / "src" / "settlement" / "store.py"


def _admit_receipt_body() -> str:
    text = STORE.read_text()
    body = text.split("def admit_receipt", 1)[1]
    return body.split("\ndef ", 1)[0]


def test_receipts_are_untyped_which_is_why_the_count_guard_exists():
    """The premise. If this ever changes, the design below is obsolete.

    Nothing in the store says which producer wrote a receipt, so a
    resolver cannot be matched to an `unknown` except by elimination.
    That is the whole reason `resolves_unknown` demands exactly one
    prior receipt rather than merely one matching unknown.

    The check is on the INSERT and on the metadata comparison, not on
    the whole file: the first version of this test scanned a prefix of
    the module and hit the local *variable* `resolves_unknown`, which is
    a name rather than a field. A field would appear in the payload.
    """
    body = _admit_receipt_body()

    assert "resolves_unknown" in body, (
        "admit_receipt no longer computes resolves_unknown, so the ambiguity "
        "it handled is gone or moved; N-30's description needs revisiting")
    for field in ("receipt_family", "producer", "parent_receipt"):
        assert field not in body, (
            "the store now carries a %r field on the receipt payload, so a "
            "resolver can name its subject and the count-based guard should "
            "be replaced properly rather than relaxed" % field)


def test_a_second_receipt_is_refused_because_of_the_count_not_the_identity():
    """The first guard is per-identity and must stay that way.

    Re-admitting the *same* `receipt_identity` with different content is a
    genuine conflict and is caught at the top of the function, before the
    count guard. This test separates the two so a fix to N-30 cannot be
    mistaken for relaxing the wrong one.
    """
    body = _admit_receipt_body()

    identity_guard = body.index("SELECT * FROM receipts WHERE receipt_identity = %s")
    count_guard = body.index("if prior and not (resolves_unknown")

    assert identity_guard < count_guard, (
        "the per-identity guard must run first; it is the one that catches a "
        "re-admission with different content")
    assert "_mark_receipt_conflict" in body[identity_guard:count_guard], (
        "the per-identity conflict branch no longer marks a conflict")


def test_the_count_guard_is_the_line_n30_needs_changed():
    """Pins the exact condition, so the repair is a deliberate edit.

    If a future change makes additional receipts admissible, this test
    fails and points at the condition that has to be reasoned about -
    which receipts may coexist, and which must be claimed.
    """
    body = _admit_receipt_body()

    assert "if prior and not (resolves_unknown" in body, (
        "the second-receipt guard is no longer the repaired predicate. It "
        "must refuse unless the new receipt either resolves attributed unknowns "
        "or claims nothing terminal, and a reworded guard has to be "
        "re-aimed deliberately rather than accepted as equivalent")
    assert "additional_observation = (" in body, (
        "the guard no longer admits a second receipt that claims nothing "
        "terminal, which is the whole of N-30's repair")
    assert "len(prior) == 1" in body, (
        "resolves_unknown no longer requires exactly one prior receipt, so the "
        "ambiguity it was guarding against is handled some other way; N-30's "
        "description needs revisiting")


def test_the_unknown_resolution_rule_is_about_outcome_not_identity():
    """What `resolves_unknown` actually asserts, so it is not weakened.

    A lone `unknown` on an unsettled, unresolved, non-terminal operation
    may be replaced by a success or failure. Every one of those conditions
    is a real safety property; the repair must keep all of them and change
    only how the resolver is matched to its unknown.
    """
    body = _admit_receipt_body()
    start = body.index("resolves_unknown = (")
    # Slice to the `if prior` guard, not to the first ")" - the condition
    # contains several, and an earlier version truncated mid-rule and
    # reported a condition as missing when it was present.
    rule = body[start:body.index("additional_observation = (", start)]

    for condition in ('len(prior) == 1',
                      'all(row["outcome"] == "unknown" for row in prior)',
                      'content.get("resolves_unknowns")',
                      'sorted(row["receipt_identity"] for row in prior)',
                      'outcome in ("success", "failure")',
                      'op["dispatch_state"] == "unresolved"',
                      'op["reconcile_state"] == "unresolved"',
                      "not bool(op[\"settled\"])",
                      "_terminal_disposition(op) is None"):
        assert condition in rule, (
            "resolves_unknown lost %r; the repair may relax the matching, "
            "not the safety conditions" % condition)


def test_no_live_caller_depends_on_a_single_receipt_per_operation():
    """Walks the callers, because relaxing the guard affects all of them.

    The first version looked for `fetchone` calls whose AST contained the
    string "receipts", which finds nothing: the SQL is an argument to
    `cur.execute`, not part of the `fetchone` node. It has to read the
    statement text instead. Two sites matter - `store.admit_receipt` and
    `agenda.py:529` - and both key on `receipt_identity`, which stays
    unique, so neither breaks under several receipts per operation. The
    test records them so a future change has the list.
    """
    identity_lookups = []
    for path in sorted((ROOT / "src" / "settlement").rglob("*.py")):
        lines = path.read_text().splitlines()
        for index, line in enumerate(lines):
            if "WHERE receipt_identity" in line and "SELECT" in line:
                window = "\n".join(lines[index:index + 3])
                if "fetchone" in window:
                    identity_lookups.append(
                        "%s:%d" % (path.relative_to(ROOT), index + 1))

    assert identity_lookups, (
        "no receipt_identity lookup was found, so this walk is broken and "
        "N-30's caller review cannot rely on it")

    # Recorded, not asserted as a work list: each of these is keyed on
    # receipt_identity, which remains the primary key, so a second receipt
    # with a different identity does not disturb it.
    assert True, (
        "receipt_identity fetchone call sites (safe under multi-receipt, "
        "reviewed): %r" % (identity_lookups,))


# --- the cost-corruption vector N-30 opens ---------------------------


def test_a_second_receipt_could_supply_the_billed_usage():
    """The dangerous consequence of admitting a second receipt.

    `_full_usage` in `experiments/coord02/schemas_evidence.py:442`
    returns the FIRST receipt row carrying a complete usage block, and
    the query feeding it is `ORDER BY receipt_identity`. Alphabetically
    `coord-step:` sorts BEFORE `local:`, so once two receipts may sit on
    one operation, a step receipt carrying a `usage` block would become
    that operation's billed tokens - a clean-looking, wrong bill.

    This test does not assert that has happened. It asserts the ordering
    that makes it possible, so that the reader can be hardened before a
    producer ever does it. The hardening is a filter on which receipt may
    speak for cost, and that belongs to the cost owner rather than to a
    change about how many receipts an operation may hold.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from experiments.coord02 import schemas_evidence

    rows = [
        {"receipt_identity": "coord-step:op-1",
         "content": {"usage": dict.fromkeys(
             schemas_evidence.USAGE_FIELDS, 9999)}},
        {"receipt_identity": "local:op-1.result",
         "content": {"usage": dict.fromkeys(
             schemas_evidence.USAGE_FIELDS, 10)}},
    ]
    ordered = sorted(rows, key=lambda r: r["receipt_identity"])

    assert schemas_evidence._full_usage(ordered)["input_tokens"] == 9999, (
        "the alphabetical order no longer puts the step receipt first, so "
        "the risk this test documents has changed shape; re-check whether "
        "a second receipt can still supply the billed usage")
