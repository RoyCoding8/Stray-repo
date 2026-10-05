# Probes for the s09 equivalence certificate

Six scripts, all runnable from the repository root with the repo venv, all
read-only with respect to the module under test except `before_after.py` and
`study_impact.py`, which monkeypatch `_NORMALISERS` in memory to compare
against the pre-fix rule.

| script | what it answers | runtime |
|---|---|---|
| `repro.py` | does the n=1 candidate still score `repaired`? | seconds |
| `oracle.py` | is every rewrite the rule fires on an identity over all inputs? | seconds |
| `census.py` | how many credited candidates are wrong? (`identity` or `churn`) | minutes |
| `before_after.py` | the same census, pre-fix rule and post-fix rule, one run | minutes |
| `study_impact.py` | does the fix disturb the shipped policy's own results? | minutes |
| `verify.py` | reference, renamed reference, and the other three rules | seconds |

Run them with the repo venv, not a bare `python`:

```
.venv/Scripts/python.exe -W ignore tools/s09_probes/oracle.py
.venv/Scripts/python.exe -W ignore tools/s09_probes/before_after.py
```

## What each measurement rests on

`oracle.py` and `repro.py` take direct evaluation as ground truth, so an
operator that raises counts as raising on both sides rather than silently
agreeing with itself. `oracle.py` detects that the rule fired by comparing the
AST before and after, not the source text, because `ast.unparse` rewrites
`not (a < b)` as `not a < b` and that would read as a rewrite that never
happened.

`census.py` builds two generators. The identity generator emits the forward
image of each of the four rules in `_NORMALISERS`, as a direct product so that
two rules touching the same span are both generated rather than one
overwriting the other. The churn generator replaces literals and comparison
operators and is mostly wrong by construction, which measures how much noise
passes the certificate.

Every credited candidate is then checked against the reference over a probe
grid that leads with `n <= 1`, because the drawn domain is `N_RANGE == (2, 4)`
and the divergence lives just outside it. A grid that cannot reach every
reachable state still reaches the drawn domain and its near misses, which is
where the wrong credits were found.

## The numbers this branch measured

Over 4,572 single-line mutations from both generators:

| | credited | credited and wrong | distinct wrong forms |
|---|---|---|---|
| pre-fix rule | 425 | 78 | 4 |
| post-fix rule | 230 | 0 | 0 |

Over `s09_swe_policy.rewrites`, 39 instances, 16,312 scorable candidates, 21
credited and 0 wrong, identical before and after.

## Why the probes are here rather than in a test

`pytest` is not run on this host; see `reports/workstreams/windows-env.md`.
These are measurement scripts, not assertions, and the regression specs they
imply belong to whoever owns `tests/test_s09_swe_experiment.py`.

They sat under `experiments/ad01/probes` and were moved here, because
`PROD_TREES` in `tests/test_a42_chain_demonstration.py` is `("src",
"experiments", "scripts")`. Seven measurement scripts in the production tree
moved the pinned `EXPECTED_PROD_FILES` from 468 to 475, and a pinned count that
has to be moved to accommodate a measurement harness is a count measuring the
wrong thing. `tools/` is outside `PROD_TREES` and outside `TEST_TREES`, so
these files are walked by neither census and collected by neither, which is
what a measurement harness wants to be.