# B8, power the panel

Lane B8 of the milestone-B build. Offline. No model call, no network, no dispatch.
Worktree `D:/AI/Agent-Society-v2/.worktrees/b8-panel`, branch `wt/b8-panel`, forked from
`f03db5b`.

## The question

The E2 experience contrast ran twice and both runs were null. The brief names that as a
power problem. This lane answers it with a census rather than a guess, and it separates the
two defects the brief tells me not to conflate.

## Two defects, kept apart

**The panel power problem.** A contrast needs independent units. One cluster is one
`(family, template)` (`experiments/ad01/s09_panel_inventory.py:18`). Six are required at
alpha 1/20, because `minimum_clusters_for_alpha` (`s09_panel_inventory.py:119`,
`s09_study_protocol.py:356`) first satisfies `2^(1-n) <= 1/20` at n = 6. Both archived
contrasts ran the software panel, which offers four templates in the whole frozen world
and two of them on the split they ran, so `sign_flip.minimum_p` was `1/2`
(`reports/evidence/invr1e2contrast/report.json`, `sign_flip`). This is a power problem and
a panel choice fixes it.

**The retention closure.** `RETENTION_BLOCKER` (`experiments/ad01/w2_retention_campaign.py:176`)
states the repertoire is closed and identical for every arm, so no difference in
`method_id` can be a retention effect. This is not a power problem. No panel moves it by
one bit. B3 opens the repertoire; nothing here does.

Both are measured in this lane and reported in separate fields, so a later reader cannot
read the census as a retention repair.

## The census method

`panel_combinations()` (`experiments/ad01/w2_retention_campaign.py`) enumerates every
non-empty subset of the three splits the frozen world offers (`dev`, `within`,
`transfer`), per family. Fourteen panels. Two properties per panel, both re-derived from
source rather than carried from an archive.

**Cluster count.** Distinct `(family, template)` over the panel's own task ids, using the
frozen cluster rule. The count comes from the frozen tasks' own `template` field, so a
regenerated world changes the census instead of contradicting it.

**Ceiling.** `census()`, the module's existing reachability function, per task. It sweeps
the whole decision grid, both seed methods by six budgets, against a family-aware default
(`default_method`, `seed-gr-ddmin@8` for graph, `seed-sw-ddmin@8` for software) rather
than the inherited hardcoded software default. This is the same enumeration
`reports/evidence/invr1w2retention-census/report.json` used, recomputed, so the numbers
are comparable to the archive and a disagreement would be visible.

The ceiling is measured once per task and reused across the combinations containing it, so
fourteen panels cost six per-family censuses rather than fourteen.

## The enumeration

Alpha 1/20, cluster rule `(family, template)`, required clusters 6.

| panel | clusters | shortfall | powered | ceiling | open rows |
|---|---|---|---|---|---|
| software:dev | 2 | 4 | no | 0.312500 | 1/3 |
| software:within | 2 | 4 | no | 0.000000 | 0/3 |
| software:transfer | 2 | 4 | no | 0.285714 | 2/3 |
| software:dev+within | 2 | 4 | no | 0.312500 | 1/6 |
| software:dev+transfer | 4 | 2 | no | 0.312500 | 3/6 |
| software:within+transfer | 4 | 2 | no | 0.285714 | 2/6 |
| software:dev+within+transfer | 4 | 2 | no | 0.312500 | 3/9 |
| graph:dev | 3 | 3 | no | 0.263158 | 3/3 |
| graph:within | 3 | 3 | no | 0.263158 | 3/3 |
| graph:transfer | 3 | 3 | no | 0.285714 | 3/3 |
| graph:dev+within | 3 | 3 | no | 0.263158 | 6/6 |
| **graph:dev+transfer** | **6** | **0** | **yes** | **0.285714** | **6/6** |
| **graph:within+transfer** | **6** | **0** | **yes** | **0.285714** | **6/6** |
| **graph:dev+within+transfer** | **6** | **0** | **yes** | **0.285714** | **9/9** |

Three findings fall out of this table.

**A six-cluster positive-ceiling panel exists. It is graph, ceiling 0.285714.** Three
combinations reach it, and the smallest of them, `graph:dev+transfer`, already has every
one of its six rows open. It is not a panel that reaches six clusters and can only
sometimes express a difference.

**The software family cannot reach six clusters on any combination.** Four software
templates exist in the entire frozen world and six are required, so the shortfall is at
least two everywhere. This is why both prior runs were underpowered and no split choice
would have saved them. The ceiling on software is mostly positive (0.285714 to 0.312500
off the `within` split), so the software failure was never that the panel was blind. It
was that the panel had too few independent units to say anything.

**No panel is powered and blind.** `powered_but_blind` is empty. Every panel with six
clusters also has a non-zero ceiling, so the cluster count and the ceiling do not trade
against each other here. That is worth stating because it would not survive a different
world; `powered_but_blind` is a reported field so a reader can see it is empty rather than
assume the two properties were never separated.

## What I fixed, named precisely

**I fixed power. I did not touch the retention closure.**

The repair is a panel identification, not a code change to any campaign. Three graph
combinations reach six clusters with a positive ceiling, and `graph:dev+transfer` is the
smallest such panel. B13 should run the third E2 contrast there rather than on
`software:within` again.

The retention closure is unchanged and asserted. `test_the_repertoire_is_still_closed_so_opening_it_cannot_happen_silently`
and `test_a_powered_panel_does_not_move_the_retained_method_leg` both fail if the
repertoire opens. That is deliberate. When B3 lands it will have to change those
assertions in the same commit and say which archived reports read the closure from, rather
than discovering later that four reports describe a world that no longer exists.

I did not need to change `tests/test_ad01_w2_retention.py:71-72`. My change makes the
closure more firmly true, not less, and the existing assertion still holds unchanged.

## One environment defect found, not fixed

The qualification gate measures `separates_reader_from_blind: false` on every target,
software included, on the clean base. That is not what
`reports/evidence/invr1w2retention/report.json` recorded, where software read true on all
nine rows.

Root cause is the environment, not the code. `LocalLauncher._append_claim`
(`src/settlement/launcher_local.py:478`) fsyncs a claim ledger whose default path is
under `tempfile.gettempdir()`. In this WSL image `/tmp/settlement-claims` is owned by
root, so `_append_claim` returns `False`, `dispatch` returns
`refused_reason="claim-not-durable"` (`launcher_local.py:879`), and
`run_step_out_of_process` raises `refused: child receipt identity is missing`
(`experiments/ad01/method_exec.py:1528`). Every reader and echoer scores unscored, so the
gate cannot separate anything.

With `SETTLEMENT_CLAIM_LEDGER` pointed at a writable path the gate behaves as archived:
software separates on all six targets I measured, graph refuses on all six because its five
authored policies hardcode a `seed-sw-` method. That is the documented graph-only defect
and it is unchanged.

This is why the gate command below exports `SETTLEMENT_CLAIM_LEDGER`. It is an
environment workaround, not a code fix. The repair is a one-line environment change
(`chown` the directory, or export the variable in the image), which is outside my owned
paths, so it is recorded here rather than made.

It also means the 22 failures in `tests/test_s09_e2_scored.py` and
`tests/test_s09_e2_replication.py` are this same environment defect and not code
regressions. I verified both on the clean base and on the parent checkout `110287f` before
concluding so. Neither file is in my gate.

## The tests

`tests/test_inv_b8_panel_power.py`, fourteen tests.

Reproducibility and literal counts, per the brief:

- `test_the_enumeration_covers_every_non_empty_combination_of_splits` asserts 14 panels
  and that the split sets are exactly the seven non-empty subsets of three.
- `test_the_census_names_a_literal_cluster_count_per_family_and_split` asserts twelve
  literal cluster counts read off the frozen world, not a self-consistent set.
- `test_the_census_artifact_is_reproducible_from_source` re-derives the verdict and the
  fourteen panels from the frozen world and the frozen reducers and compares them against
  the committed artifact, so a hand-edited `census.json` fails.
- `test_the_census_artifact_records_how_to_recompute_it` pins the recomputation entry
  point, `model_calls: 0`, alpha and cluster rule.

Positive ceiling, as a literal:

- `test_the_graph_panel_that_reaches_six_clusters_has_a_positive_ceiling` asserts
  `0.2857142857` for every powered panel and that every row is open.

Closure still asserted:

- `test_the_repertoire_is_still_closed_so_opening_it_cannot_happen_silently`
- `test_a_powered_panel_does_not_move_the_retained_method_leg`
- `test_the_verdict_names_the_panel_and_does_not_claim_retention`, which requires
  `not_claimed` to name retention and the verdict to carry the closure mechanism beside
  it.

Plus the negative halves: `test_the_software_panel_the_prior_run_used_cannot_be_powered`
asserts the prior panel is 2 clusters against 6,
`test_software_is_short_of_clusters_on_every_combination_it_offers` asserts software never
reaches 4, and `test_the_closed_software_within_panel_is_reported_as_zero_and_not_as_power`
pins the prior panel's ceiling at exactly 0.0.

TDD was followed. The file was written first and watched fail, 12 of 14 red with
`AttributeError: module 'w2_retention_campaign' has no attribute 'panel_combinations'`.
The two that passed were the closure tests, which assert something already true and are
supposed to.

## The artifact

`reports/evidence/invr1b8-panel-census/census.json`, a new directory. No existing file
under `reports/evidence/` was read-modified or moved, confirmed by `git status` showing
only `M experiments/ad01/w2_retention_campaign.py` and two untracked additions.

The source change is additive only, 266 insertions into
`experiments/ad01/w2_retention_campaign.py`, all of it in the census region adjacent to
`RETENTION_BLOCKER`. `RETENTION_BLOCKER` itself is untouched.

## The gate

    wsl -d Ubuntu -u ubuntu -- bash -lc 'export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/b8-gate.jsonl; mkdir -p /home/ubuntu/claims; cd /mnt/d/AI/Agent-Society-v2/.worktrees/b8-panel && PYTHONPATH=src timeout 1200 /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_inv_b8_panel_power.py tests/test_ad01_w2_retention.py -q -p no:cacheprovider'

    47 passed in 865.83s (0:14:25)

The `SETTLEMENT_CLAIM_LEDGER` export is required for the reason above. Without it the
gate reports failures that exist on the clean base and belong to no lane.

The 14:25 duration is not the tests being slow. `tests/test_inv_b8_panel_power.py` alone
runs in 90s. The retention file dominates, and this run shared one WSL instance with at
least four other lanes under a load average of 6.8, most of it blocked in `p9_client_rpc`
against the `/mnt/d` mount. CPU ticks on the pytest process advanced throughout, so it was
I/O contention rather than a hang.

## What I would tell the coordinator

Run B13 on `graph:dev+transfer`. Six clusters, ceiling 0.285714, every row open, and the
qualification gate is the next thing standing between that and a dispatch, since graph is
the family its five authored policies cannot read. That last point is worth someone's
attention: the only panel with enough power is the one the current gate refuses. B13 will
need either a graph-readable qualification policy or an explicit decision to run on an
unqualified graph panel. Neither is this lane's call and neither is B8's scope.

B14 stays blocked on B3. The closure is unchanged.
