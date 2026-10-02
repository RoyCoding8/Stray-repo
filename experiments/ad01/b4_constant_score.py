"""B4: re-derive the constant-rule crossover offline, on the mean, at one budget.

Lane B4 repaired `agenda_policy._score_constant_rules`, which returned a sum
over worlds where every arm row it is read beside is a mean. The archived E3
numbers were produced under the sum, so they stay where they are. This
module re-derives the one comparison the repair changes -- an arm against
the best constant rule in its own space -- and writes it to a new namespace.

**It writes a new file and never opens an archived one.** The output path is
`reports/evidence/invr1b4-mean-score/`, which does not exist at the parent
commit. `assert_new_namespace` refuses to run if that path holds anything
this module did not write, so a rerun overwrites its own output and nothing
else. The archived directories named in `NOT_REPLACED` are listed only so a
reader knows what this is not a re-derivation of.

**One budget, and it is named.** `control_competence` sweeps 196 rules over
three worlds and refits `fitted_fixed_rule` over the same space. Measured at
this tip it costs 893.6 s at budget 20 alone, so the six-budget ladder is
roughly 90 minutes. That is a research run and not this lane's job, so
`FROZEN_BUDGET` is a single budget and the artifact says so in its own
`budgets` field. A freeze that reported a first-crossing budget would need
the ladder; this one does not claim one, and `crossover_scope` records that
the crossing is measured at one budget rather than located along a ladder.

Budget 40 is the budget the committed competence test runs at
(`tests/test_s09sel_divergence.py`) and the one where `DEFAULT_RULE` ties the
best rule in its own space rather than being beaten by it, so the yardstick
is doing work at this budget instead of reporting a gap the default cannot
close.

**What the result does and does not settle.** The archived `3.0` is
`SUM == 3 * MEAN` over three worlds, an identity that holds for any inputs
and therefore confirmed nothing when it reproduced
(`reports/workstreams/w3-reproduce.md:48-59`). It stays on the record and it
stays true. The *direction* it sat beside also survives, because dividing
every score by the same three is monotone and cannot flip a sign. What does
not survive is any figure that mixed the two scales -- the `2.7x` oracle
ratio, the `gap_to_best` column, the `2.6729x` pairings -- and none of those
is restated here. A corrected scale and a wrong one are not comparable, and
putting both in one column is the mistake this lane was opened for.

**What this module does not touch.** The reuse-versus-cold-acquisition cost
crossover at `reports/evidence/inv_r1_e2_retention/costs.json` is produced by
`learner.cost_report` over reservation units from the cap sheet. It imports
no part of `agenda_policy`, and no part of the constant-rule score reaches
it. That ledger's `crossover_uses: 5.0` is therefore untouched by this
repair, and this module makes no claim about it in either direction.

No model call, no network, no gateway, no database. Every portfolio
candidate is a `SEED_CAPABILITIES` id that `trajectory` resolves in process,
so the whole sweep is local arithmetic over the frozen measure set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import agenda_policy
from . import e3_ladder
from . import selection

# The new namespace. New because the archived E3 evidence is not superseded
# by this re-derivation: it is a different scale of a different comparison,
# and a reader who needs the old figures needs them where they are.
FREEZE_DIR = Path("reports") / "evidence" / "invr1b4-mean-score"
FREEZE_FILE = "b4-crossover-mean.json"

# The one budget measured, with the reason. 40 is where the committed
# competence test runs and where the specified control ties the best rule in
# its own space, so the yardstick is discriminating rather than trivially
# large. Measured cost at budget 20 is 893.6 s; a caller should bound this
# rather than assume a sweep is cheap.
FROZEN_BUDGET = 40
MEASURED_COST_SECONDS_AT_BUDGET_20 = 893.6

# The archived directories this re-derivation does not touch and does not
# replace. Named so the artifact can say so, and so a reader who diffs the
# tree after a run can check the list against what git reports.
NOT_REPLACED = (
    "reports/evidence/inv_r1_e3_selection",
    "reports/evidence/inv_r1_e3_ladder",
    "reports/evidence/inv_r1_e3_fitted_control",
    "reports/evidence/inv_r1_e3_selection_regen_v2",
    "reports/evidence/inv_r1_e2_retention",
)


def _arms_at(budget: int) -> dict:
    """One row per arm, each a fresh policy per cell.

    Fresh per cell rather than shared across worlds: both policies are
    stateful (`AgendaPolicy` pops from `_untried` and accumulates `_live`,
    `FixedPolicy` advances `_step`), so a shared instance makes world 1
    decide what world 2 is permitted to pick. That is N-80, retracted in
    `reports/evidence/inv_r1_e3_selection/RETRACTED.md`, and re-introducing
    it into a new freeze would be reproducing a withdrawn defect under a new
    name.
    """
    return {
        "agenda": agenda_policy.agenda_policy,
        "control": lambda: agenda_policy.fixed_policy(),
        "fitted_control": lambda: agenda_policy.fitted_control(budget),
    }


def _arm_row(name: str, factory, budget: int, worlds) -> dict:
    """One arm's mean and totals at one budget, over the qualified worlds."""
    per_world = [
        e3_ladder._measure(selection.run_investigations(
            selection.portfolio_for_world(world), factory(),
            selection.Allocation(authorized=budget), world=world))
        for world in worlds]
    return {
        "held_out_mean": sum(
            cell["held_out_reduction"] for cell in per_world) / len(per_world),
        "retained_total": sum(
            cell["retained_behaviors"] for cell in per_world),
        "choices_total": sum(cell["choices"] for cell in per_world),
        "resources_used_total": sum(
            cell["resources_used"] for cell in per_world),
        "policy_per_world": True,
    }


def row(budget: int = FROZEN_BUDGET, worlds=None) -> dict:
    """One budget, every arm, the yardstick beside them.

    The arms and the yardstick come from the same `control_competence` pass
    over the 196-rule space, which is also where the two fixed arms' handicap
    counts are read. Scoring the arms separately would double a cost that
    dominates the run.
    """
    worlds = tuple(worlds or selection.WORLDS)
    competence = agenda_policy.control_competence(budget, worlds=worlds)
    fixed = {record["arm"]: record for record in competence["arms"]}
    arms = {name: _arm_row(name, factory, budget, worlds)
            for name, factory in sorted(_arms_at(budget).items())}
    best = competence["best_held_out_reduction"]
    agenda_mean = arms["agenda"]["held_out_mean"]
    return {
        "budget": budget,
        "arms": arms,
        "best_rule_held_out_mean": best,
        "best_rule": {family: tuple(value) for family, value
                      in competence["best_rule"].items()},
        "rules_searched": competence["searched"],
        "control_rules_beating_it": fixed["control"]["rules_beating_it"],
        "control_gap_to_best": fixed["control"]["gap_to_best"],
        "control_optimal_here": fixed["control"]["optimal_here"],
        "fitted_control_rules_beating_it": fixed[
            "fitted_control"]["rules_beating_it"],
        "agenda_beats_the_best_rule": agenda_mean > best + 1e-12,
        "agenda_ahead_of_the_control": (
            agenda_mean > arms["control"]["held_out_mean"]),
    }


def payload(budget: int = FROZEN_BUDGET) -> dict:
    """The whole freeze, as a dict, before anything is written."""
    selection.assert_measure_freeze()
    measured = row(budget)
    best = measured["best_rule_held_out_mean"]
    agenda_mean = measured["arms"]["agenda"]["held_out_mean"]
    return {
        "study": "B4 constant-rule score re-derived on the mean",
        "freeze": "new-freeze, not comparable to the archived E3 figures",
        "source": "experiments/ad01/b4_constant_score.py",
        "repaired": (
            "agenda_policy._score_constant_rules returned a sum over worlds; "
            "it now returns the mean, which is the scale every arm row it is "
            "read beside is already on"),
        "what_this_is_not": [
            "not comparable to reports/evidence/inv_r1_e3_selection/ or "
            "reports/evidence/inv_r1_e3_ladder/, which were produced on the "
            "sum and stay byte-unchanged",
            "not a re-derivation of the 2.7x oracle ratio or any gap or "
            "count that mixed a sum with a mean. Those are wrong and stay "
            "wrong, and nothing here restates them on either scale",
            "not the 'exactly 3.0' ratio, which is SUM == 3 * MEAN over three "
            "worlds. That figure is true and stays; it holds for any inputs, "
            "so it confirmed nothing when it reproduced",
            "not about the reuse-versus-cold-acquisition cost crossover. "
            "reports/evidence/inv_r1_e2_retention/costs.json is produced by "
            "learner.cost_report over cap-sheet reservation units, imports no "
            "part of agenda_policy, and is untouched by this repair",
        ],
        "score_scale": "mean held_out_reduction over the qualified worlds",
        "crossover_scope": (
            "single budget. A first-crossing budget is not derivable from one "
            "budget and this freeze does not claim one; it reports the sign "
            "of the agenda against the best constant rule at this budget only"),
        "worlds": list(selection.WORLDS),
        "budgets": [budget],
        "measure_digest": selection.assert_measure_freeze(),
        "policy_instance_scope": "one-per-cell",
        "rows": [measured],
        "crossover": {
            "agenda_held_out_mean": agenda_mean,
            "best_rule_held_out_mean": best,
            "agenda_beats_the_best_constant_rule": (
                measured["agenda_beats_the_best_rule"]),
            "agenda_ahead_of_the_control": measured[
                "agenda_ahead_of_the_control"],
            "budgets_measured": [budget],
            "first_budget_behind_the_best_constant_rule": None,
            "first_budget_behind_is_claimed": False,
        },
        "direction_survives": (
            "The archived direction claim is a sign. Dividing every score by "
            "the same three is monotone, so no sign can move and the claim "
            "stands on its own reasoning. What cannot transfer is any ratio, "
            "gap or count read across the two scales, and none is restated "
            "here."),
    }


def assert_new_namespace(directory: Path) -> None:
    """Refuse to run into a directory this module did not create.

    A re-derivation that overwrote somebody else's evidence would destroy
    the record of the comparison that produced it, which is the same failure
    this lane was opened to fix. The namespace is new, so this holds on the
    first run and on every rerun: the directory either does not exist or
    contains only this module's own output file.
    """
    if not directory.exists():
        return
    unexpected = [p for p in directory.iterdir() if p.name != FREEZE_FILE]
    if unexpected:
        raise SystemExit(
            "refusing to write into %s: it holds %r, and this module writes "
            "only %s. A re-derivation belongs in a namespace of its own."
            % (directory, sorted(p.name for p in unexpected), FREEZE_FILE))


def build(directory: Path | None = None,
          budget: int = FROZEN_BUDGET) -> dict:
    """Run the sweep and write the new freeze. Nothing archived is opened."""
    target = Path(directory) if directory is not None else FREEZE_DIR
    assert_new_namespace(target)
    result = payload(budget)
    target.mkdir(parents=True, exist_ok=True)
    (target / FREEZE_FILE).write_text(
        json.dumps(result, indent=1, sort_keys=True) + "\n")
    return result


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    target = Path(argv[0]) if argv else FREEZE_DIR
    result = build(target)
    measured = result["rows"][0]
    print(json.dumps({
        "freeze": result["freeze"],
        "path": str(target / FREEZE_FILE),
        "score_scale": result["score_scale"],
        "crossover_scope": result["crossover_scope"],
        "measure_digest": result["measure_digest"],
        "budgets": result["budgets"],
        "agenda_held_out_mean": measured["arms"]["agenda"]["held_out_mean"],
        "control_held_out_mean": measured["arms"]["control"]["held_out_mean"],
        "fitted_held_out_mean":
            measured["arms"]["fitted_control"]["held_out_mean"],
        "best_rule_held_out_mean": measured["best_rule_held_out_mean"],
        "best_rule": measured["best_rule"],
        "rules_searched": measured["rules_searched"],
        "control_rules_beating_it": measured["control_rules_beating_it"],
        "agenda_beats_the_best_constant_rule":
            measured["agenda_beats_the_best_rule"],
    }, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
