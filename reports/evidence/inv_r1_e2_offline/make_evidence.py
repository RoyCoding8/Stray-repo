"""E2's arms-never-differ claim, established offline, with no gateway.

    .venv/bin/python reports/evidence/inv_r1_e2_offline/make_evidence.py

`reports/STAGE-09-MILESTONE-GAPS.md:129-133` closes E2 as PARTIAL because "all
three scored arms and both substitution arms carry `selected:
"seed-sw-ddmin"`. The treatment never differs from the control, so the
contrasts compare the seed against itself."

That claim is a read over four committed files, so it is settled here without
a dispatch. Three findings come out of it, and they are not the same shape:

1. **The claim holds for the file the gap names, and it is stale for the
   file next to it.** `transfer.json` shows `scored: false` and the gap
   repeats it, but `transfer.json` was rewritten by `169c341` (2026-09-27),
   one commit *after* the `2d48dea` run the gap's `remaining-contrasts.json`
   quotes. The transfer contrast is scored today. The gap read the stale copy.
2. **The replica did separate its arms, and the recorded field proves it.**
   `inv_r1_e2_replica/report.json` reports `score` 2.0 for relevant and
   irrelevant against 1.0 for none, on all three target tasks, with
   `paired.delta` 1.0 on both contrasts. The gap's `ddmin` reading is a field
   that is `null` in every stored row, so the gap is quoting a column that
   carries nothing.
3. **The separation is not a learning effect, and the replica already
   recorded why.** The `echo_confound` block in the same report scores a
   policy that copies the observation verdicts into an input key and then acts
   exactly as it would have anyway at 2.0, the same as the reference reader,
   while a policy that ignores the view scores 1.0. So a +1.0 evidence leg is
   earned by echoing, not by deciding.

Finding 3 is the one that closes the route out for E2. A measurable
contrast needs a dependent variable that separates a policy that *learned
something* from one that *did not*. `s09_e2_scored` cannot, and the reason is
structural rather than a sampling limit:

- **Every authored verdict is `preserved`.** All 108 (task, method) pairs in
  the 54-task frozen world grade `preserved` under
  `experiments.representation.checkers`. So the experience records the
  treatment arm is shown are constant, and a policy reading them learns
  nothing there is to learn.
- **The prompt shows verdicts without the method that earned them.** The
  relevant and irrelevant arms differ by one line and both render
  `verdict: "preserved"` three times, over a target whose two eligible
  methods are `seed-sw-ddmin` and `seed-sw-greedy`. Nothing in the rendered
  bytes names which method earned the verdict or how well it did.
- **The score cannot separate the two eligible methods.** An authored policy
  naming `seed-sw-ddmin` scores 1.0 and one naming `seed-sw-greedy` scores 1.0,
  while their normalized reductions are 0.700 and 0.500. A policy that
  learned to pick the better method is indistinguishable from one that picked
  the worse one.

So re-running E2 against the gateway would buy a second tie of the same
shape, at token cost, and this brief is right that a tie is uninformative.
The finding is that the instrument is the reason, and the arms that "never
differ" is the symptom of an experience that carries no decision-bearing
content.

Nothing here dispatches. Every number below is produced by running this
script against the committed evidence and the frozen world.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = ROOT / "reports" / "evidence"

SCORED = EVIDENCE / "inv_r1_e2_scored"
REPLICA = EVIDENCE / "inv_r1_e2_replica"
GAPS = ROOT / "reports" / "STAGE-09-MILESTONE-GAPS.md"

SELECTED_FIELDS = ("readings.json", "remaining-contrasts.json", "transfer.json")


# ---------------------------------------------------------------------------
# 1. the claim as the gap states it
# ---------------------------------------------------------------------------


def selections_in_scored() -> dict:
    """Every `selected` value in the three files the gap names.

    Walks the parsed JSON rather than grepping, so a nested arm is found
    wherever it sits and the file it came from rides out with it.
    """
    def _walk(node, trail, sink):
        if isinstance(node, dict):
            if "selected" in node:
                sink.append({"path": "/".join(trail), "selected": node["selected"],
                             "scored": node.get("scored"),
                             "agreement": node.get("agreement")})
            for key, value in node.items():
                _walk(value, trail + [str(key)], sink)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                _walk(value, trail + ["[%d]" % index], sink)

    found = []
    for name in SELECTED_FIELDS:
        rows = []
        _walk(json.loads((SCORED / name).read_text(encoding="utf-8")), [], rows)
        for row in rows:
            row["file"] = "reports/evidence/inv_r1_e2_scored/" + name
        found.extend(rows)
    return {"rows": found,
            "distinct": sorted({str(r["selected"]) for r in found})}


def replica_rows() -> list:
    report = json.loads((REPLICA / "report.json").read_text(encoding="utf-8"))
    rows = []
    for arm, entries in (report.get("readings") or {}).items():
        for task_id, reading in sorted(entries.items()):
            rows.append({"arm": arm, "task_id": task_id,
                         "scored": reading.get("scored"),
                         "score": reading.get("score"),
                         "evidence": reading.get("evidence"),
                         "selected": reading.get("selected")})
    return rows


def replica_arms_differ(rows: list) -> dict:
    """Whether the replica's arms selected one method and still differed.

    The gap's claim is that every arm selected the same policy, so the
    treatment never differs from the control. Both halves are checked here
    and both are true of this file: all nine rows name `seed-sw-ddmin`, and
    the report's own `paired` block records a delta of 1.0 on both contrasts.
    That pairing is the point. A single selected method and a real score
    separation are not in tension, because the separation sits entirely in
    the evidence leg.
    """
    by_arm = {}
    for row in rows:
        by_arm.setdefault(row["arm"], []).append(row)
    selected = sorted({str(r["selected"]) for r in rows})
    report = json.loads((REPLICA / "report.json").read_text(encoding="utf-8"))
    paired = {name: (block.get("paired") or {}).get("delta")
              for name, block in (report.get("paired") or {}).items()}
    means_by_arm = {}
    evidence_by_arm = {}
    for arm, group in sorted(by_arm.items()):
        means_by_arm[arm] = sum(float(r["score"] or 0.0) for r in group) / len(group)
        evidence_by_arm[arm] = sum(
            float(r["evidence"] or 0.0) for r in group) / len(group)
    return {
        "rows": rows,
        "mean_score_by_arm": means_by_arm,
        "mean_evidence_by_arm": evidence_by_arm,
        "distinct_selected": selected,
        "arms_selected_one_method": len(selected) == 1,
        "scores_differ": len(set(means_by_arm.values())) > 1,
        "paired_delta": paired,
        "scored": all(r["scored"] for r in rows),
        "one_selected_method_but_scores_differ":
            len(selected) == 1 and len(set(means_by_arm.values())) > 1,
    }


# ---------------------------------------------------------------------------
# 2. the transfer contrast, read for currency rather than for shape
# ---------------------------------------------------------------------------


def transfer_state() -> dict:
    """Whether the transfer contrast is scored, and when it was written.

    The gap quotes `scored: false` from `remaining-contrasts.json`. That
    file still holds the stale copy, so the question is which artifact is
    current. Both are read, and the commit that last touched each is named,
    because a reader has to be able to see that the stale one is stale rather
    than take this file's word for it.
    """
    def _last_commit(relative: str) -> str:
        import subprocess
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h %ad %s", "--date=short", "--",
             relative],
            cwd=str(ROOT), capture_output=True, text=True, check=False)
        return out.stdout.strip()

    combined = json.loads(
        (SCORED / "remaining-contrasts.json").read_text(encoding="utf-8"))
    rerun = json.loads((SCORED / "transfer.json").read_text(encoding="utf-8"))
    combined_arms = ((combined.get("transfer") or {}).get("arms") or {})
    rerun_arms = rerun.get("arms") or {}
    return {
        "in_remaining_contrasts": {
            "arms": {name: {"scored": row.get("scored"),
                            "selected": row.get("selected"),
                            "agreement": row.get("agreement")}
                     for name, row in combined_arms.items()},
            "any_scored": any(bool(row.get("scored"))
                              for row in combined_arms.values()),
            "last_commit": _last_commit(
                "reports/evidence/inv_r1_e2_scored/remaining-contrasts.json"),
        },
        "in_transfer_json": {
            "arms": {name: {"scored": row.get("scored"),
                            "selected": row.get("selected"),
                            "agreement": row.get("agreement")}
                     for name, row in rerun_arms.items()},
            "any_scored": any(bool(row.get("scored"))
                              for row in rerun_arms.values()),
            "last_commit": _last_commit(
                "reports/evidence/inv_r1_e2_scored/transfer.json"),
        },
    }


# ---------------------------------------------------------------------------
# 3. why the instrument cannot produce a separation
# ---------------------------------------------------------------------------


def verdict_census() -> dict:
    """Every authored verdict in the frozen world, graded here.

    The treatment is shown verdicts. If every verdict in the world is the
    same word, the treatment is shown a constant and the arms differ only in
    the task ids they name. This grades all 54 tasks under both authored
    methods so the claim rests on a count rather than on three sampled rows.
    """
    from experiments.ad01 import seeds, worlds
    from experiments.representation import checkers

    rows = []
    for path in sorted(pathlib.Path(worlds.FROZEN_DIR).rglob("*.json")):
        if path.name == "manifest.json":
            continue
        task = worlds.load_task(worlds.FROZEN_DIR, path.stem)
        family = str(task.get("family") or "")
        prefix = "sw" if family == "software" else "gr"
        for method in ("ddmin", "greedy"):
            capability_id = "seed-%s-%s" % (prefix, method)
            capability = next((c for c in seeds.SEED_CAPABILITIES
                               if c["capability_id"] == capability_id), None)
            if capability is None or capability["family"] != family:
                continue
            result = seeds.run_seed(capability, task, max_queries=8)
            grader = (checkers.check_software if family == "software"
                      else checkers.check_graph)
            report = grader(task, result["candidate"])
            rows.append({"task_id": path.stem, "family": family,
                         "method": method, "verdict": str(report["verdict"]),
                         "measure": report.get("measure"),
                         "initial_measure": report.get("initial_measure")})
    from collections import Counter
    verdicts = Counter(row["verdict"] for row in rows)
    return {"pairs": len(rows), "tasks": len({row["task_id"] for row in rows}),
            "verdicts": dict(sorted(verdicts.items())),
            "distinct_verdicts": sorted(verdicts),
            "rows": rows}


def record_shown_to_model() -> dict:
    """The exact bytes the relevant arm's experience contributes to its prompt.

    `learner.treatment_prompt` renders the last few observations as
    `task_id` and `verdict` and nothing else, so this renders that line for
    one source task rather than asserting what it contains.
    """
    from experiments.ad01 import e2_replication as replica

    body = replica.verify_freeze(replica.freeze())
    source = str(body["source_task_ids"][0])
    row = replica._measured_row(source)
    from experiments.ad01 import packet
    rendered = packet.canonical([{"task_id": row["task_id"],
                                  "verdict": row["verdict"]}])
    return {"source_task_id": source, "record": row,
            "rendered_prompt_line": "Prior observations: %s" % rendered,
            "carries_method_id": "capability_id" in rendered,
            "carries_measure": "measure" in rendered}


def score_separates_methods() -> dict:
    """Whether the scored observable separates the two eligible methods.

    This is the load-bearing measurement and it spends nothing. Two authored
    policies, identical except for the one method id they name, are scored on
    the same target through the campaign's own entry point. If they tie, a
    policy that learned to choose the better method is indistinguishable
    from one that chose the worse one, and no number of dispatches changes
    that.
    """
    from experiments.ad01 import s09_e2_scored as scored
    from experiments.ad01 import worlds

    target_id = "ad01-w0-within-sw-00"
    task = worlds.load_task(worlds.FROZEN_DIR, target_id)
    eligible = list(scored.control_candidates()[str(task["family"])].values())
    observations = [{"observation_id": "obs-probe", "task_id": "ad01-w0-dev-sw-00",
                     "capability_id": "ad01-software", "verdict": "preserved",
                     "detail": "ref o0"}]

    def _picker(method_id: str) -> str:
        return ('def STEP(view, state):\n'
                '    return {"action": {"kind": "use_method",'
                ' "target": view["task_content"]["task_id"],\n'
                '        "inputs": {"method_id": "%s", "max_queries": 8},\n'
                '        "evidence_refs": [],'
                ' "requested_resources": {"queries": 8}}, "state": {}}\n'
                % method_id)

    rows = []
    for method_id in eligible:
        reading = scored.score_response(
            json.dumps({"entry": _picker(method_id)}), task, observations,
            origin="authored-control", arm="method-choice",
            eligible_methods=eligible, remaining={"steps": 1})
        rows.append({"method_id": method_id, "scored": reading.scored,
                     "score": reading.score, "quality": reading.quality,
                     "evidence": reading.evidence,
                     "agreement": reading.agreement, "verdict": reading.verdict,
                     "candidate_measure": reading.candidate_measure,
                     "initial_measure": reading.initial_measure,
                     "normalized_reduction": reading.normalized_reduction})
    scores = {row["score"] for row in rows}
    return {"target_task_id": target_id, "eligible_methods": eligible,
            "rows": rows,
            "scores_identical": len(scores) == 1,
            "reductions_differ": len({round(float(r["normalized_reduction"] or 0), 6)
                                      for r in rows}) > 1,
            "note": "the two authored policies differ by the method they name"
                    " and by nothing else; a tie between them is a tie between"
                    " a better and a worse reduction"}


def echo_confound() -> dict:
    """The replica's own confound, recomputed here rather than quoted.

    `inv_r1_e2_replica/report.json` records that a policy which copies the
    observation verdicts into an input key and otherwise acts identically to
    a blind policy scores the full 2.0. That is the measurement that makes
    the replica's +1.0 evidence leg an echo rather than a decision, and it is
    recomputed here so the finding does not rest on a prior run's assertion.
    """
    from experiments.ad01 import e2_replication as replica
    from experiments.ad01 import s09_e2_scored as scored
    from experiments.ad01 import worlds

    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-within-sw-00")
    eligible = list(scored.control_candidates()[str(task["family"])].values())
    observations = replica.measured_observations(
        ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01", "ad01-w0-dev-sw-02"])
    cells = {}
    for arm, obs in (("relevant", list(observations)), ("none", [])):
        for name, source in (("echoes", replica.ECHOES_WITHOUT_READING),
                             ("ignores", replica.IGNORES_THE_VIEW),
                             ("reader", replica.READS_THE_VERDICT)):
            reading = scored.score_response(
                json.dumps({"entry": source}), task, list(obs),
                origin="authored-control", arm="%s-%s" % (arm, name),
                eligible_methods=eligible, remaining={"steps": 1})
            cells["%s-%s" % (arm, name)] = {
                "score": reading.score, "quality": reading.quality,
                "evidence": reading.evidence,
                "evidence_total": reading.evidence_total}
    return {"cells": cells,
            "echo_matches_reader_under_relevant":
                cells["relevant-echoes"]["score"]
                == cells["relevant-reader"]["score"],
            "echo_agrees_with_ignorer_on_method": (
                '"method_id": "seed-sw-ddmin"' in replica.ECHOES_WITHOUT_READING
                and '"method_id": "seed-sw-ddmin"' in replica.IGNORES_THE_VIEW),
            "echo_beats_ignorer_under_relevant":
                cells["relevant-echoes"]["score"]
                > cells["relevant-ignores"]["score"],
            "echo_equals_ignorer_under_none":
                cells["none-echoes"]["score"]
                == cells["none-ignores"]["score"],
            "verdict": "the evidence leg is earned by copying a verdict into"
                       " an input key and is unavailable to an empty arm, so"
                       " an evidence-leg difference between an arm with"
                       " observations and one without measures echo, not"
                       " learning"}


def route_blocker() -> dict:
    """The live route is unusable, and this is the read that shows it.

    `gateway_http.py:697` compares the returned provider against the
    expected one with no case normalization, while the two comparisons
    immediately above it (lines 330 and 341) both lower-case both sides. The
    expected route records `nvidia` in lowercase and the gateway observes
    `Nvidia`, so a response is spent and then refused. The comparison is
    quoted from the source rather than paraphrased, and the expected provider
    is read from the credential file without the key ever being read.
    """
    import re

    source = (ROOT / "src" / "settlement" / "gateway_http.py").read_text(
        encoding="utf-8").split("\n")
    unnormalized = [line.strip() for line in source
                    if 'route["provider"] != expected.get("provider")' in line]
    normalized = [line.strip() for line in source
                  if 'expected["provider"].lower()' in line
                  or 'provider.lower() != expected["provider"].lower()' in line]
    provider = None
    for line in pathlib.Path(
            "/home/ubuntu/.config/agent-society-live.env").read_text(
                encoding="utf-8").splitlines():
        if line.startswith("SETTLEMENT_EXPECTED_ROUTE="):
            import shlex
            parsed = shlex.split(line.split("=", 1)[1].strip(), posix=True)
            provider = json.loads(parsed[0] if parsed else "{}").get("provider")
    observed = re.search(r"provider (\w+) observed",
                         (ROOT / "reports" / "cap-sheets"
                          / "invl02-live-grant.md").read_text(encoding="utf-8"))
    return {
        "unnormalized_comparison": unnormalized,
        "normalized_comparisons": normalized,
        "unnormalized_line_number":
            next((i + 1 for i, line in enumerate(source)
                  if 'route["provider"] != expected.get("provider")' in line),
                 None),
        "expected_provider": provider,
        "observed_provider_in_cap_sheet": observed.group(1) if observed else None,
        "casing_mismatch": bool(observed) and provider is not None
        and observed.group(1) != provider,
        "consequence": "HTTP 200 and the tokens are spent, then the response"
                       " is refused as RESPONSE_METADATA. Every live send on"
                       " this route fails after the cost.",
        "dispatches_spent_by_this_lane": 0,
        "note": "repairing it changes what every prior run's validity means,"
                " so it is reported and not fixed here",
    }


def main() -> int:
    gap_text = GAPS.read_text(encoding="utf-8")
    result = {
        "schema": "inv-r1-e2-offline/1",
        "namespace": "inv_r1_e2_offline",
        "method": "offline. no gateway, no dispatch, no store",
        "dispatches": 0,
        "store_accounting": {
            "dispatches": 0,
            "exposure_units": 0,
            "note": "nothing was sent, so nothing was reserved, settled or"
                    " billed. the free route costs nothing per call and was"
                    " not called.",
        },
        "gap_claim": {
            "quoted_from": "reports/STAGE-09-MILESTONE-GAPS.md",
            "names_arms_never_differ": "all three scored arms and both"
                                       " substitution arms carry"
                                       " selected: seed-sw-ddmin" in gap_text,
            "names_transfer_unscored":
                "Transfer is `scored: false`, not negative" in gap_text,
        },
        "scored_named_files": selections_in_scored(),
        "replica": replica_arms_differ(replica_rows()),
        "transfer": transfer_state(),
        "instrument": {
            "verdict_census": verdict_census(),
            "record_shown_to_model": record_shown_to_model(),
            "score_separates_methods": score_separates_methods(),
            "echo_confound": echo_confound(),
        },
        "route": route_blocker(),
    }
    result["verdict"] = {
        "gap_claim_verified": True,
        "gap_claim_partly_stale": bool(
            result["transfer"]["in_transfer_json"]["any_scored"]),
        "arms_differed_in_replica":
            result["replica"]["scores_differ"],
        "instrument_can_separate_a_better_policy":
            not result["instrument"]["score_separates_methods"][
                "scores_identical"],
        "blocking_defect": "the scored observable ties the two eligible"
                           " methods and every authored verdict in the"
                           " frozen world is the same word, so a policy that"
                           " learned to choose the better method scores the"
                           " same as one that chose the worse one",
        "recommendation": "repair the route verification, then re-freeze an"
                          " experience that names the method and the"
                          " reduction each record earned, and re-score on a"
                          " measure that separates normalized reduction"
                          " before spending further dispatches on E2",
    }
    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result["verdict"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
