# w2-e2-retention

The two §W2 contrasts the E2 batch did not run: **retention** (a method
retained from earlier work, reused, against reacquiring it cold) and
**adaptation** (within-domain against held-out-domain).

Everything here is NEW. No existing experiment or `src` module is edited.
The apparatus is imported, not forked.

## The premise under test

`5cf3fe8` measured the *experience* contrast and found it null, then ran a
reachability census and reported the panel closed on the positive side. The
project ledger now says the retention and adaptation halves of §W2 are
unrun, and that is where the batch stopped short of its own scope.

This lane's first job is to check that premise rather than inherit it. The
prior census was measured on *one* panel: three `software` `within` targets.
§W2 asks two different questions on two different splits, so the ceiling
has to be measured per panel. Three measured facts set the design.

**Fact 1 — the prior census is closed only on its own panel.** Recomputing
the same grid offline over all 18 frozen targets, with a family-aware
default, the positive side is open on `graph` (both splits, 3/3 cells) and
partly open on `software` `transfer` (2/3). It is closed on `software`
`within` (0/3) — the prior panel. So the two §W2 contrasts are *not*
inheriting a ceiling, and a null here would be a real null.

**Fact 2 — the inherited census has a defect that matters here.**
`reachability_census` compares every row against `DEFAULT_METHOD`, a
hardcoded `seed-sw-ddmin`. Run on a `graph` target, `default` is `None`
and every positive delta is computed against nothing. Measured directly:
the graph rows report a "default" of 0.0 where the real default is
0.2105. The prior census never hit this because its panel was software
only. I do not patch the frozen module; this lane computes its own default
per family and reports the discrepancy.

**Fact 3 — retention cannot be read off the terminal verdict.** `verdict`
is `preserved` on every reducer outcome, so it cannot vary. The observable
is `normalized_reduction` plus the decision vector
(`method_id`, `max_queries`), exactly as the prior lane did. That is
reported as a *bounded* instrument, not a repaired one.

**Fact 4 — the retained-method leg itself has no lever.** The repertoire
`assessment_profile.default_repertoire()` admits is four authored seed ids,
and `eligible_for(task)` returns the two belonging to the task's family,
identically for every arm. A method acquired on one task can never enter
another task's repertoire, so "reuse a retained method" cannot be expressed
as a difference in `method_id` here. `measure_repertoire_closure` measures
this on all nine panel targets with no model and no dispatch.

**Fact 5 — the inherited evidence budget is a property of one pool.**
`EVIDENCE_MAX_QUERIES = 3` is the largest whole budget at which the
*software* dev pool's graded outcome varies. On a graph panel it is
uniform, `require_varying_graded_outcome` refuses, and the campaign produces
a named refusal per target and no reading at all. The first live run of
this campaign did exactly that. The budget is now searched per family over a
range declared in the freeze: graph 6, software 2.

## The retention blocker, and what follows from it

Fact 4 is the load-bearing one. The retention contrast as §W2 words it —
*retained-method reuse against cold reacquisition* — is not expressible as a
difference in `method_id` on this instrument, because the repertoire is
closed and authored and no arm can add to it.

What *is* expressible is the observable that survives: given a policy that
was **shown** a retained method's prior observations, does it beat the same
policy shown none? That is measured, paired per task, on panels whose
ceiling is open.

This lane therefore does what the assignment permits: it **measures the
transfer-shaped leg of retention on the splits where the ceiling is open**,
and it **reports the `method_id` leg as unmeasurable on this instrument**
with the exact code that makes it so. It does not manufacture a retained
method to fill the cell.

## Layout

| File | Role |
|---|---|
| `experiments/ad01/w2_retention_campaign.py` | freeze, arms, census, run, report |
| `experiments/ad01/w2_retention_verify.py` | offline verifier, re-derives from observations |
| `tests/test_ad01_w2_retention.py` | behaviour tests, one file |
| `reports/evidence/invr1w2retention*/` | two namespaces |

## Constraints honoured

Never the full suite. `uv run pytest tests/test_ad01_w2_retention.py -q` at
most, one file. Out-of-process children only under WSL. Live calls capped
and counted. No double or authored solver substituted for a model.

**30 tests, all passing.** 28 on the Windows host in 13.7s; the whole file
under WSL with `/root/w0venv/bin/python3` in 4m19s, because the two
child-spawning tests cannot run on a host that cannot bound a child. The
full suite was never run.

## A note on the run script

`scripts/w2_retention_run.sh` **verifies the relay before it spends
anything**, with one real completion rather than a health check. Port 4100
was held by a relay from another lane whose Windows bridge half pointed at a
worktree that no longer exists; it answered `/health` and returned a
confident JSON error to every chat request. A health check alone would have
passed it.

