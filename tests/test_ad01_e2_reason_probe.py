"""Rendering `reason` beside `verdict` did not unblock the E2 gate, and
rendering it into the gate does not open this panel either.

`cfa8ab3` stopped E2 at its gate and named two changes that would make a
dispatch worth spending. The smaller one was to render `reason` beside
`verdict` in the construction prompt, or read a scored observable that the
budget moves. This file pins the measurement that reordered those two: the
reason does vary with budget on the freeze's own source tasks, and
`experience_varies` still refused, because the gate counted distinct
`verdict` values and every record on the panel carried one.

That count has since changed. `experience_varies` now counts the outcome, the
verdict joined to the reason, and `ad01-exp-axis` is a panel built to span the
reason's axis. Neither moves *this* panel, which is the point of keeping the
file: the three source tasks `e2_replication` freezes are all mid-slack, so
at every budget they earn one outcome and the gate refuses. A gate that
opened here would be opening on a panel that has no variety in it, which is
the failure the original test was written to catch, now pointed at the
changed gate instead of the old one.

`experiments/ad01/experience_axis.py` holds the fixpoint that explains why the
verdict half can never vary, and `tests/test_ad01_experience_axis.py` holds
the panel that does vary.

Each test is written so it fails on the defect it names.
`test_rendering_the_reason_does_not_move_the_gate` calls the gate on
reason-bearing records, so it would pass a prompt that rendered the reason
only if the gate also read it. `test_the_reason_varies_where_the_verdict_does_
not` inverts its own assertion, so a world whose verdict moved would fail it
rather than the constant world the defect lives in.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import e2_gate_report as gated  # noqa: E402
from experiments.ad01 import e2_reason_probe as probe  # noqa: E402
from experiments.ad01 import e2_replication as replica  # noqa: E402
from experiments.ad01 import control_distinctness as gates  # noqa: E402


def _frozen() -> dict:
    return replica.freeze()["body"]


def test_rendering_the_reason_does_not_move_the_gate():
    """The gate counts verdicts, so a richer record is still a constant."""
    answer = probe.reason_bearing_gate(_frozen())

    assert "reason" in answer["records_carry"]
    assert answer["gate_before"]["distinct_verdicts"] == 1
    assert answer["gate_after"]["distinct_verdicts"] == 1
    assert answer["gate_moved"] is False
    assert answer["gate_after"]["varies"] is False
    assert answer["gate_after"]["refusal"]


def test_the_gate_still_refuses_on_records_that_carry_the_reason():
    """The refusal is the gate's own sentence, not this file's summary.

    The sentence now counts outcomes rather than verdicts, because the gate
    does. It is still a refusal, and it is still about a constant: three
    observations, one distinct outcome, minimum two.
    """
    answer = probe.reason_bearing_gate(_frozen())

    assert answer["gate_after"]["refusal"] == (
        "refused: the relevant-with-reason arm's experience is a constant:"
        " 3 observations, 1 distinct outcome(s)"
        " ['preserved/ok-preserved'], minimum 2")
    assert answer["gate_after"]["distinct_outcomes"] == 1
    assert answer["gate_after"]["distinct_verdicts"] == 1


def test_the_three_source_tasks_are_one_outcome_at_every_budget():
    """The panel this probe names cannot open, and that is the finding.

    `e2_replication` freezes three software source tasks at `max_queries: 8`.
    They are all mid-slack, so the reducer finds a removable atom on each and
    the reason is `ok-preserved` on each, which is one outcome. The gate
    refuses and the refusal is correct.
    """
    frozen = _frozen()
    for budget in (1, 2, 4, 8, 16, 64):
        observations = gated._panel_observations(
            frozen["source_task_ids"], max_queries=budget)
        gate = gates.experience_varies(observations, arm_name="source")
        assert gate["distinct_verdicts"] == 1, (budget, gate)
        assert gate["distinct_outcomes"] <= 2, (budget, gate)
        if budget == 1:
            assert not gate["varies"], (budget, gate)


def test_the_reason_varies_where_the_verdict_does_not():
    """The signal the prompt would gain is real, on the freeze's own tasks."""
    panel = probe.reason_by_budget(_frozen()["source_task_ids"],
                                   budgets=(1, 8, 64))
    reasons = {fields["reason"] for per_budget in panel.values()
               for fields in per_budget.values()}
    verdicts = {fields["verdict"] for per_budget in panel.values()
                for fields in per_budget.values()}

    assert reasons == {"ok-incumbent", "ok-preserved"}
    assert verdicts == {"preserved"}


def test_every_reason_on_the_world_is_still_a_preserved_verdict():
    """The budget moves the reason across the world, never the verdict."""
    surface = probe._world_surface()

    assert surface["verdict_is_constant"] is True
    assert surface["verdicts"] == {"preserved": surface["task_budget_pairs"]}
    assert surface["reason_is_constant"] is False
    assert set(surface["reasons"]) == {"ok-incumbent", "ok-preserved"}


def test_the_frozen_budget_panel_is_a_constant_under_either_field():
    """At the frozen budget, the panel earns one value in each field."""
    frozen = _frozen()
    panel = probe.reason_by_budget(frozen["source_task_ids"],
                                   budgets=(1, 8, 64))
    at_budget = {fields["reason"] for per_budget in panel.values()
                 for budget, fields in per_budget.items()
                 if budget == str(frozen["max_queries"])}

    assert at_budget == {"ok-preserved"}


def test_the_probe_dispatches_nothing_and_opens_no_database():
    """This is a pre-dispatch measurement and names its own cost."""
    report = probe.report()

    assert report["dispatches"] == 0
    assert report["database"] is None
    assert report["reason_bearing_gate"]["gate_after"]["varies"] is False


def test_the_gate_report_this_probe_reads_agrees_about_the_verdict_surface():
    """The two modules sweep the world separately and must not disagree."""
    surface = probe._world_surface()
    swept = gated.reachable_verdicts()

    assert surface["verdict_is_constant"] == swept["verdict_is_constant"]
    assert swept["verdicts"] == {"preserved": swept["task_budget_pairs"]}
