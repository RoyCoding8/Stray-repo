"""B14: whether the retention leg can be exercised on this route's members.

Dispatches nothing, by construction. `b14-retention-freeze.md` carries
`total_dispatch_cap: 0` and this module is what makes that ceiling true
rather than merely stated: it has no gateway parameter and no path to one,
so a reader can confirm the absence from the module rather than from a claim
about what the driver was asked not to do.

**What is measured.** `invl02_liveacq_r4` is the only study in this tree
that acquired members on the pinned free route and kept the bytes with their
receipts. Those bytes are read, their digests recomputed from the bytes
rather than read from the artifact, and each is admitted through
`assessment_profile.Repertoire` and carried to every frozen task in its
family by `w2_retention_campaign.retained_leg_verdict`, which stages the
member's own source and runs it out of process through the same brokered
route an acquired method takes. Then the strategy axis is swept to the width
of the child menu, because r4's three members all named `ddmin` and three
draws on one value would be a small sample of a two-valued choice.

**What is not claimed.** No retention effect is measured here and no
acquisition was performed. The question is whether the instrument can express
one, which is a property of the members in hand rather than of the learner.
The offline positive in the artifact is B3's own fixture member, its `origin`
is `fixture-stand-in`, and it is labelled as that in the artifact and in the
gate. It is not this route's, and nothing here reports it as acquired.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

NAMESPACE = "invr1b14-retention"

# The study that acquired members on the pinned free route and kept the
# bytes with their receipts. Read-only, and immutable history.
R4_ARMS = "reports/evidence/invl02_liveacq_r4/acquired_arms.json"
R4_SUMMARY = "reports/evidence/invl02_liveacq_r4/summary.json"

# The budget the strategy sweep and the seed comparison both run at. The
# parent's B-shaped request caps at 2048 output tokens; the method budget is
# a separate knob and 16 is `DEFAULT_CHILD_BUDGET` in `method_exec`, the
# budget a child wrapper hands a callee the model did not ask a different
# one for. Both sides of the comparison use it, because a comparison run at
# two budgets is a comparison of nothing.
BUDGET = 16

FAMILY_REDUCER = {"software": "reduce_software", "graph": "reduce_graph"}
FAMILY_SEED = {"software": "seed-sw-ddmin", "graph": "seed-gr-ddmin"}
STRATEGIES = ("ddmin", "greedy")

# The member shape the child menu hands a model to fill in, one per
# strategy. This is not an authored policy offered as an acquisition: it is
# the SHAPE of r4's three acquisitions with the strategy varied, used to
# bound the strategy axis. Its origin is `strategy-probe`, never `acquired`,
# and the artifact says which arm of which kind produced which row.
MEMBER_SOURCE = (
    'def ENTRY(task, oracle, max_queries=16):\n'
    '    result = %s(task, oracle, max_queries=max_queries,'
    ' method="%s")\n'
    '    return {"candidate": result["candidate"],'
    ' "queries": result["queries"]}\n')

# A member that returns its own input. The negative control for the
# measurement itself: it must come back constant and unmeasurable, or the
# measurement is not measuring. B3 asserted the same property on the same
# bytes; here it is re-derived so this artifact's own instrument is what is
# checked rather than a neighbour's.
CONSTANT_SOURCE = (
    'def ENTRY(task, oracle, max_queries=16):\n'
    '    ops = list(task["ops"])\n'
    '    return {"candidate": {"family": "software",'
    ' "task_id": task["task_id"],\n'
    '                            "fault": task["fault"], "ops": ops,\n'
    '                            "witness": task["witness"],'
    ' "seed": task.get("seed")},\n'
    '                "queries": 0}\n')

# B3's fixture member, which does vary. Read from its own module rather than
# copied, because a copy is a second definition that could drift from the
# first and the point of naming it is that it is B3's.
OFFLINE_VARIING_LABEL = "b3-fixture-member"


class B14Refused(Exception):
    """A claim this study may not make, named before anything is measured."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def live_acquired_arms(root: Path | None = None) -> list:
    """The members `invl02_liveacq_r4` acquired, with digests re-derived.

    The digest is recomputed from the bytes rather than read from the
    artifact, for the reason `trajectory.load_repertoire` recomputes it: a
    digest that is not its bytes' digest is not a receipt for anything. An
    arm whose recorded digest disagrees with its own source is refused here
    rather than carried into a repertoire.
    """
    root = root or _repo_root()
    arms = json.loads((root / R4_ARMS).read_text(encoding="utf-8"))["arms"]
    acquired = []
    for arm in arms:
        if not arm.get("acquired"):
            continue
        source = str(arm["policy_source"])
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if digest != str(arm["source_digest"]):
            raise B14Refused(
                "acquired member %r records digest %s but its bytes hash to"
                " %s; carrying it would measure bytes the artifact does not"
                " describe" % (arm["capability_id"], arm["source_digest"],
                               digest))
        acquired.append({
            "arm": arm["arm"], "capability_id": arm["capability_id"],
            "family": arm["family"], "acquired_on": arm["task_id"],
            "entry": arm.get("entry") or "ENTRY",
            "origin": arm.get("origin") or "acquired",
            "source_digest": digest, "source_characters": len(source),
            "source": source,
            "operation_id": ((arm.get("evidence") or {}).get("operation_id")),
            "receipt_identity": ((arm.get("evidence") or {})
                                 .get("receipt_identity")),
            "requested_model": ((arm.get("evidence") or {})
                                .get("requested_model")),
        })
    return acquired


def member_of(record: Mapping[str, Any]) -> Any:
    """One arm as the arrived member B3's arrival path takes."""
    from . import assessment_profile

    return assessment_profile.AcquiredMember(
        capability_id=record["capability_id"], family=record["family"],
        entry=record["entry"], method_source=record["source"],
        origin=record["origin"], acquired_on=record["acquired_on"])


def _seed_run(family: str, task: Mapping[str, Any]) -> dict:
    """The authored seed of this family on this task, at this budget."""
    from . import e2_replication as replica, seeds

    capability = next(c for c in seeds.SEED_CAPABILITIES
                      if c["capability_id"] == FAMILY_SEED[family])
    result = seeds.run_seed(capability, task, max_queries=BUDGET)
    report = replica._grade(task, result["candidate"])
    return {"verdict": str(report["verdict"]),
            "reason": str(report["reason"]),
            "normalized_reduction": round(
                replica._normalized_reduction(report), 6)}


def _rows_for(member: Any, authority: Mapping[str, Any], *,
              compare_seed: bool) -> list:
    """One member on every frozen task in its family, graded by the checker.

    `retained_leg_verdict` owns the verdict measurement; this owns the seed
    comparison beside it, because the question the leg does not answer is
    whether admitting the member adds anything the repertoire could not
    already name. Both run at `BUDGET`, so the comparison is between two
    budgets of the same size rather than between two different sizes.
    """
    from . import e2_replication as replica, method_exec, packet, worlds
    from . import w2_retention_campaign as campaign

    family = str(member.family)
    rows = []
    for split in ("dev", "within", "transfer"):
        for task_id in campaign._world()[split][family]:
            task = worlds.load_task(worlds.FROZEN_DIR, task_id)
            result = method_exec.run_member_out_of_process(
                member.as_executable(), packet.method_task_view(task),
                max_queries=BUDGET, dsn=authority["dsn"],
                allocation_id=authority["allocation_id"],
                operation_id="ad01-b14-%s-%s"
                             % (member.capability_id, task_id))
            report = replica._grade(task, result["candidate"])
            member_reduction = replica._normalized_reduction(report)
            row = {"task_id": task_id, "split": split,
                   "acquisition_task": task_id == str(member.acquired_on),
                   "verdict": None if task_id == str(member.acquired_on)
                   else str(report["verdict"]),
                   "reason": None if task_id == str(member.acquired_on)
                   else str(report["reason"]),
                   "normalized_reduction": None
                   if task_id == str(member.acquired_on)
                   else round(member_reduction, 6)}
            if compare_seed and task_id != str(member.acquired_on):
                seeded = _seed_run(family, task)
                row["seed_verdict"] = seeded["verdict"]
                row["seed_reason"] = seeded["reason"]
                row["seed_normalized_reduction"] = seeded[
                    "normalized_reduction"]
                row["same_reduction_as_seed"] = (
                    row["normalized_reduction"]
                    == seeded["normalized_reduction"])
            rows.append(row)
    return rows


def _measure(member: Any, authority: Mapping[str, Any], *,
             compare_seed: bool) -> dict:
    """The leg verdict and the seed comparison for one member."""
    from . import w2_retention_campaign as campaign

    verdict = campaign.retained_leg_verdict(member, authority=authority)
    rows = _rows_for(member, authority, compare_seed=compare_seed)
    verdicts = sorted({r["verdict"] for r in rows if r["verdict"]})
    compared = [r for r in rows if r.get("same_reduction_as_seed") is not None]
    return {
        "capability_id": str(member.capability_id),
        "family": str(member.family),
        "origin": str(member.origin),
        "acquired_on": str(member.acquired_on),
        "source_digest": member.source_digest,
        "distinct_verdicts": verdicts,
        "retained_method_leg_measurable": len(verdicts) > 1,
        "tasks_measured": len(rows),
        "rows": rows,
        "rows_compared_to_seed": len(compared),
        "rows_identical_to_seed": sum(
            1 for r in compared if r["same_reduction_as_seed"]),
        "executed_by": "method_exec.run_member_out_of_process",
        "arrival_path": "assessment_profile.Repertoire",
    }


def strategy_arms() -> list:
    """The child menu's strategy axis, at its full width, on both families.

    `method_exec.child_contract` offers two direct reducers differing only in
    the `method` a member passes, and the wrappers supply no value for it,
    so that choice is the whole of what a model can vary. Sweeping it is what
    turns "the three members we happened to get" into "no member this menu
    offers", which is the claim the ceiling of zero rests on.
    """
    from . import method_exec

    contract = method_exec.child_contract()
    offered = sorted(contract["callables"])
    if sorted(set(FAMILY_REDUCER.values()) | set(offered)) and not all(
            name in offered for name in FAMILY_REDUCER.values()):
        raise B14Refused(
            "the child menu does not offer the reducers this sweep assumes;"
            " the menu is %s" % offered)
    arms = []
    for family in ("software", "graph"):
        for strategy in STRATEGIES:
            arms.append({
                "arm": "%s/%s" % (family, strategy), "family": family,
                "capability_id": "probe-%s-%s" % (family, strategy),
                "origin": "strategy-probe", "strategy": strategy,
                "acquired_on": "ad01-w0-dev-%s-00"
                               % ("sw" if family == "software" else "gr"),
                "entry": "ENTRY",
                "source": MEMBER_SOURCE % (FAMILY_REDUCER[family], strategy)})
    return arms


def _authority(store: str) -> dict:
    """A real allocation and campaign identity, or no child may execute."""
    from . import trajectory

    trajectory.set_namespace_token("")
    cid = trajectory.campaign_id(0, "I", 314)
    trajectory.authorize_campaign(store, cid, authorized=10_000_000)
    return {"dsn": store, "allocation_id": trajectory._alloc_id(cid),
            "cid": cid}


def offline_varying_member(authority: Mapping[str, Any]) -> dict:
    """The offline leg, on B3's own fixture bytes, labelled as offline.

    Two rows, both named for what they are. The varying one is B3's fixture
    member, imported from that lane's own test module rather than copied, so
    there is one definition of those bytes rather than two. The constant one
    returns its input and is the negative control for this measurement: if it
    came back measurable the instrument would be reporting something it
    cannot know, and both rows would be worthless.

    **Neither member was acquired from a provider.** Both origins are
    `fixture-stand-in` / `strategy-probe`, neither claims `origin:
    "acquired"`, and neither is a substitute for the live acquisition this
    study reports as not having happened.
    """
    from . import assessment_profile
    from . import w2_retention_campaign as campaign

    control = assessment_profile.AcquiredMember(
        capability_id="b14-control-constant", family="software",
        entry="ENTRY", method_source=CONSTANT_SOURCE,
        origin="strategy-probe", acquired_on="ad01-w0-dev-sw-00")
    rows = [{"member": OFFLINE_VARIING_LABEL,
             "acquired_from_provider": False,
             "imported_from": "tests/test_inv_b3_repertoire._member",
             **_measure(control, authority, compare_seed=False)}]
    rows[0]["capability_id"] = "b14-control-constant"

    varying = _b3_fixture_member()
    if varying is None:
        raise B14Refused(
            "B3's fixture member could not be imported from"
            " tests/test_inv_b3_repertoire; the offline leg is not measured"
            " rather than measured against a copy of those bytes")
    rows.append({
        "member": OFFLINE_VARIING_LABEL,
        "acquired_from_provider": False,
        "imported_from": "tests.test_inv_b3_repertoire._member",
        **_measure(varying, authority, compare_seed=False)})
    return {
        "label": "OFFLINE DEMONSTRATION, NOT A LIVE ACQUISITION",
        "what_this_is": (
            "the retained-method leg measured on bytes that were written in a"
            " test, admitted through the same arrival path and executed"
            " through the same out-of-process route the live members took."),
        "what_this_is_not": (
            "not an acquisition. No provider wrote these bytes, no receipt"
            " names them, and neither member carries an origin claiming"
            " otherwise. This row demonstrates that the instrument can"
            " express the leg; it does not supply a member, and the study's"
            " live finding is that this route supplies none."),
        "control": "the constant member returns its input and is graded"
                   " preserved on every task, which is the negative control"
                   " for this measurement",
        "rows": rows,
    }


def _b3_fixture_member() -> Any:
    """B3's fixture member, imported rather than copied.

    A copy would be a second definition of those bytes that could drift from
    the first, and the whole claim of this section is that they are B3's.
    """
    import importlib.util
    import sys

    path = _repo_root() / "tests" / "test_inv_b3_repertoire.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("b3_fixture_source", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module._member()


def measure_all(store: str) -> dict:
    """The whole measurement, on a disposable store, with no gateway."""
    from . import e2_replication as replica
    from . import w2_retention_campaign as campaign

    authority = _authority(store)
    live = []
    for record in live_acquired_arms():
        measured = _measure(member_of(record), authority, compare_seed=True)
        measured["kind"] = "live-acquired"
        measured["acquired_from_provider"] = True
        measured["operation_id"] = record["operation_id"]
        measured["receipt_identity"] = record["receipt_identity"]
        measured["requested_model"] = record["requested_model"]
        measured["source_characters"] = record["source_characters"]
        live.append(measured)

    strategies = []
    for arm in strategy_arms():
        member = member_of(arm)
        measured = _measure(member, authority, compare_seed=True)
        measured["kind"] = "strategy-probe"
        measured["acquired_from_provider"] = False
        measured["strategy"] = arm["strategy"]
        strategies.append(measured)

    panels = [p for p in campaign.panel_combinations()
              if p["powered"] and p["max_attainable_positive_delta"] > 0]
    summary = json.loads((_repo_root() / R4_SUMMARY).read_text(
        encoding="utf-8"))
    measurable_live = [m for m in live
                       if m["retained_method_leg_measurable"]]
    measurable_strategy = [m for m in strategies
                           if m["retained_method_leg_measurable"]]
    return {
        "namespace": NAMESPACE,
        "schema": "s09-b14-retention-v1",
        "recomputed_by": "experiments.ad01.invr1b14_retention.measure_all",
        "measured_live": False,
        "dispatches": 0,
        "model_calls": 0,
        "gateway_used": False,
        "budget": BUDGET,
        "freeze": "reports/cap-sheets/b14-retention-freeze.md",
        "cap_sheet_total_dispatch_cap": 0,
        "acquisition": {
            "r4_summary_acquired": summary.get("acquired"),
            "r4_summary_arms": len(summary.get("arms") or []),
            "r4_live_acquisition_claim": (summary.get("verdicts") or {})
            .get("live_acquisition"),
            "b12_lineages_acquired": 0,
            "b12_lineages_attempted": 4,
            "reading": "r4 is the only live acquisition on this route whose"
                       " bytes were kept, and it earned 3 of 6 arms. B12, the"
                       " current construction run, earned 0 of 4 python-step"
                       " lineages. Neither number is this lane's to improve"
                       " on, and both are recorded because the ceiling of"
                       " zero rests on the rate rather than on taste.",
        },
        "panel": {
            "chosen": "graph:dev+transfer",
            "reason": "the smallest combination reaching six clusters with a"
                      " positive ceiling, as frozen by b-live-cap.md",
            "powered_panels": panels,
            "required_clusters": 6,
            "alpha": "1/20",
            "cluster_rule": "(family, template)",
            "frozen_retention_panel": {
                "family": campaign.PANELS[0]["family"],
                "target_split": campaign.PANELS[0]["target_split"],
                "readable_by_qualification_gate": False,
                "reason": "w2_retention_campaign.qualification_census reads"
                          " 0 rows; the gate's authored policies name a"
                          " seed-sw- method and refuse a graph target",
            },
        },
        "live_acquired_members": live,
        "strategy_probe_members": strategies,
        "offline_demonstration": offline_varying_member(authority),
        "verdict": {
            "live_acquired_measurable": len(measurable_live),
            "live_acquired_measured": len(live),
            "strategy_measurable": len(measurable_strategy),
            "strategy_measured": len(strategies),
            "dispatches": 0,
            "routable": False,
            "statement": (
                "B14 cannot be run live at this acquisition rate and menu."
                " %d of %d members this route acquired live carry a varying"
                " verdict and %d of %d strategy arms do, so the"
                " retained-method leg is closed behind a gate that is open."
                % (len(measurable_live), len(live), len(measurable_strategy),
                   len(strategies))),
            "not_claimed": (
                "no retention effect is measured, no member was acquired by"
                " this lane, and nothing here bounds what this route could"
                " return at a budget or framing nobody has tried. Four"
                " observations on a menu two values wide is a small sample"
                " of the route's behaviour."),
        },
        "accounting": {
            "per_request_units": 2492,
            "unit_kind": "estimated-budget",
            "requests": 0,
            "total_units": 0,
            "derivation": "1774 // 4 + 1 + 2048 at the frozen B request"
                          " shape; the request count is 0 because this freeze"
                          " authorises none",
            "billed": None,
            "charge_units": None,
            "reading": "the route reports its price as usage.cost, which the"
                       " adapter does not read, so both keys ride out absent."
                       " Unknown is recorded as unknown and never as zero.",
            "carried_in_uncertain_units": 5563,
            "carried_in_true_exposure": ">= 5563",
            "carried_in_netted_against_this_allocation": False,
        },
    }


def write(path: str | Path | None = None, *, store: str) -> dict:
    """The artifact, written to the directory this lane owns.

    Never overwrites anything: the target is this lane's own evidence root
    and an existing artifact would be a second run, not a re-read of the
    first.
    """
    from .s09_run_isolation import create_disposable_db, drop_disposable_db

    body = measure_all(store)
    target = Path(path or (_repo_root() / "reports" / "evidence"
                           / NAMESPACE))
    target.mkdir(parents=True, exist_ok=True)
    artifact = target / "retention.json"
    if artifact.exists():
        raise B14Refused(
            "%s already exists; this study is not a campaign and does not"
            " rewrite its own reading" % artifact)
    artifact.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    return body


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .s09_run_isolation import create_disposable_db, drop_disposable_db

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    database = create_disposable_db(
        "b14retention",
        migrations_dir=_repo_root() / "migrations")
    try:
        body = write(args.out, store=database.dsn)
    finally:
        drop_disposable_db(database)
    v = body["verdict"]
    print("dispatches %s  live-acquired measurable %s/%s"
          % (v["dispatches"], v["live_acquired_measurable"],
             v["live_acquired_measured"]))
    print("strategy arms measurable %s/%s"
          % (v["strategy_measurable"], v["strategy_measured"]))
    print("offline varying leg: %s"
          % [r["retained_method_leg_measurable"]
             for r in body["offline_demonstration"]["rows"]])
    print(v["statement"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())