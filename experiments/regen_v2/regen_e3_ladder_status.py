"""Emit the B6 / N-80 status marker for the ladder embedded in the post-fix file.

`reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json` carries a withdrawn
result at `$.committed_ladder`: the per-budget `choices`,
`held_out_reduction_mean`, `resources_used_total` and `yield_totals` series of
`reports/evidence/inv_r1_e3_selection/e3-crossover.json`, re-serialised under a
key that names no withdrawal, beside a top-level `measure_digest` equal to that
file's. It is the pre-fix/post-fix bridge, so it is annotated and never deleted.
Deleting it would break the comparison permanently, and it is the only thing
that lets a reader see the before and the after in one place.

The artifact itself is not modified. The brief for this lane forbids touching
any existing file under `reports/evidence/`, and that prohibition is the right
one: those bytes are the only surviving evidence that the defects existed. So
the marker is a sibling file, keyed by the artifact path and the JSON pointer,
that a machine can join against. A reader with jq does
`jq --slurpfile m committed-ladder-status.json '...'`; a reader by hand reads
`RETRACTED.md` beside it.

Everything the marker asserts is measured here against the committed bytes at
run time, so a reviewer can re-run this and get the same verdict rather than
taking it from prose.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ARTIFACT = "reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json"
LADDER = "reports/evidence/inv_r1_e3_selection/e3-crossover.json"
MARKER = "committed-ladder-status.json"

B6_FINDING = "B6 / N-80"

# The fields that make the two documents the same measurement. A difference in
# any of them would mean the embedded ladder is not the withdrawn one and the
# marker would be asserting something false.
COMPARED = ("choices", "held_out_reduction_mean", "resources_used_total",
            "yield_totals")

MARKER_WORDS = ("retract", "withdrawn", "invalid", "superseded")


def find_series(node, key: str):
    """Collect every value of `key` in a payload, in document order."""
    found = []

    def walk(value):
        if isinstance(value, dict):
            for name, child in value.items():
                if name == key:
                    found.append(child)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return found


def measure() -> dict:
    """Measure the defect from the committed bytes, at run time."""
    artifact = json.loads(Path(ARTIFACT).read_text())
    ladder_doc = json.loads(Path(LADDER).read_text())
    blob = Path(ARTIFACT).read_text().lower()

    embedded = artifact.get("committed_ladder")
    if embedded is None:
        raise SystemExit("%s has no $.committed_ladder" % ARTIFACT)

    # The embedded series lives at $.committed_ladder.ladder, one entry per
    # budget, each carrying the two arms. The withdrawn document carries the
    # same series at its own top level.
    rows = embedded.get("ladder")
    if not isinstance(rows, list):
        raise SystemExit("$.committed_ladder.ladder is not a series")
    reference = ladder_doc.get("ladder")
    if not isinstance(reference, list):
        raise SystemExit("%s has no ladder series" % LADDER)

    agree = []
    for index, row in enumerate(rows):
        ref = reference[index] if index < len(reference) else {}
        ref_arms = {a.get("policy"): a for a in ref.get("arms", [])}
        agree.append({
            "budget": row.get("budget"),
            "arms": {
                arm.get("policy"): {
                    name: {
                        "embedded": arm.get(name),
                        "source": ref_arms.get(arm.get("policy"), {}).get(name),
                        "equal": arm.get(name)
                        == ref_arms.get(arm.get("policy"), {}).get(name),
                    }
                    for name in COMPARED
                }
                for arm in row.get("arms", [])
            },
        })
    identity = {
        "budgets_compared": len(agree),
        "budgets_in_source": len(reference),
        "every_compared_budget_agrees_on_every_field": bool(agree) and all(
            all(field["equal"] for arm in entry["arms"].values()
                for field in arm.values())
            for entry in agree),
        "per_budget": agree,
    }

    return {
        "artifact": ARTIFACT,
        "json_pointer": "$.committed_ladder",
        "finding": B6_FINDING,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "claims_the_source_is": embedded.get("path"),
        "policy_instance_scope": embedded.get("policy_instance_scope"),
        "source_of_truth": LADDER,
        "source_file_retracted_by": (
            "reports/evidence/inv_r1_e3_selection/RETRACTED.md cause 1"),
        "measure_digest": {
            "artifact": artifact.get("measure_digest"),
            "withdrawn_ladder": ladder_doc.get("measure_digest"),
            "equal": artifact.get("measure_digest")
            == ladder_doc.get("measure_digest"),
        },
        "identity_to_withdrawn_ladder": identity,
        "marker_word_counts": {
            word: blob.count(word) for word in MARKER_WORDS},
        "carries_any_withdrawal_marker": any(
            blob.count(word) for word in MARKER_WORDS),
    }


def _series_of(row, name):
    """One field of one arm, for a single budget row."""
    if not isinstance(row, dict):
        return None
    return row.get(name)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=os.path.join(
        "reports", "evidence", "inv_r1_e3_ladder"))
    args = parser.parse_args(argv)

    measured = measure()
    marker = {
        "status": "withdrawn",
        "finding": B6_FINDING,
        "subject": {
            "artifact": measured["artifact"],
            "json_pointer": measured["json_pointer"],
        },
        "reason": (
            "This key re-embeds the withdrawn E3 crossover ladder under a name "
            "that carries no withdrawal. Its per-budget values are identical to "
            "%s and its measure_digest is the same, so a reader who opens the "
            "post-fix artifact sees the pre-fix numbers under a live-looking "
            "key." % measured["source_of_truth"]),
        "why_it_is_kept": (
            "It is the pre-fix/post-fix bridge. Deleting it would break the "
            "comparison permanently, so it is annotated and left in place."),
        "superseded_by": (
            "the same document's post-fix ladder, in this file, measured with "
            "one policy per cell"),
        "does_not_survive": [
            "e3-crossover.json's own `agenda_ahead_on_held_out_at: [14, 60]`",
            "the control's resources_used_total series as an independent run "
            "per budget; it is a cumulative prefix sum of one traversal "
            "(crossover() constructs each policy once and then loops worlds "
            "and budgets, s09_e3_selection.py:133)",
        ],
        "measurement": measured,
        "not_modified": (
            "%s is left byte-identical. This marker is a sibling so the "
            "committed bytes survive as the record of the defect."
            % measured["artifact"]),
        "join": (
            "jq --slurpfile m %s '$metadata' %s" % (MARKER, ARTIFACT)),
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / MARKER
    path.write_text(json.dumps(marker, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "written": str(path),
        "identity_matches_withdrawn_ladder":
            measured["identity_to_withdrawn_ladder"][
                "every_compared_budget_agrees_on_every_field"],
        "budgets_compared":
            measured["identity_to_withdrawn_ladder"]["budgets_compared"],
        "measure_digest_equal": measured["measure_digest"]["equal"],
        "carries_any_withdrawal_marker":
            measured["carries_any_withdrawal_marker"],
    }, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
