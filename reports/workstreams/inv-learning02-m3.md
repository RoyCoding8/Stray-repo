# Inv-Learning-02 M3: finite Boolean-rule discovery instrument

Base: `d10c471` on `wt/m3-rule`. No live spend. Deterministic only, no
network, no database. Verdict: PASS.

## 1. Failing repro (red, then green)

`tests/test_m3_rule_instrument.py` written first against the absent
modules. Red recorded: collection `ImportError: cannot import name
'boolean_rule'`. Then `experiments/ad01/boolean_rule.py` and
`experiments/ad01/rule_learner.py` added. Green: 15 passed. The suite
keeps the red-shape probes live: ninth query refused, non-member truth
table refused, uncommitted predictor scoring refused.

## 2. Instrument (`experiments/ad01/boolean_rule.py`, new)

Four input bits, four output bits, sixteen states. Each output bit is an
affine expression over the four inputs, optionally XORed with one
pairwise product: 32 coefficient assignments times 7 product options
yields 224 syntactic specs, all 224 truth tables distinct
(`class_digest 285113caf4ab`). Query ceiling 8. Predictor is data (four
class-member specs), executed by `execute_predictor`, never `eval`ed.
`RuleSession` returns only the four output bits per query, refuses the
ninth query, illegal inputs, illegal hypotheses and scoring before
commit with typed `RuleRefused` reasons. Private `score` reports
overall, queried and unqueried exact-match fractions separately.
`public_view`, `model_input` and `child_view` carry only task identity,
class descriptor, observed pairs and budget. Split generators salt by
`boolean-rule-v1/<split>/<seed>`; 8 seeds per split verified pairwise
disjoint by `find_cross_split_duplicates`. One `instrument_spec` for
every arm.

## 3. Baseline (`experiments/ad01/rule_learner.py`, new)

`VersionSpaceLearner` holds per-bit surviving table sets, filters on
every observation, picks the unqueried input with maximal total
minority disagreement (seeded tie-break), predicts the version-space
member nearest the majority vote. Legal and query-consistent by
construction. Tuned on dev instances only; qual and audit instances
were scored but never used for any choice.

## 4. Per-split utility (8 queries, matched seeds, learner seed = task seed)

| Split | Queried | Unqueried | Overall |
|---|---|---|---|
| dev | 1.000 | 0.938 | 0.969 |
| qual | 1.000 | 0.875 | 0.938 |
| audit | 1.000 | 0.938 | 0.969 |

Per-seed unqueried fractions: dev
1.00 x7, 0.50 x1; qual 1.00 x6, 0.50 x2; audit 1.00 x7, 0.50 x1. Small
environment result about experiment selection and prediction only. No
claim of general scientific discovery.

## 5. Gates

| Gate | Result |
|---|---|
| `test_m3_rule_instrument.py` | 15 passed |
| `test_ad01_env.py` + `test_ad01_traj.py` (neighbors) | 63 passed |
| literal held-out scan (4 target tables absent from all views) | passed in-suite |
| cross-split truth-table duplicates over 24 tasks | none |

Commands (from the worktree):

- `.venv/bin/python -m pytest tests/test_m3_rule_instrument.py -q`
- `.venv/bin/python -m pytest tests/test_ad01_env.py tests/test_ad01_traj.py -q`

## 6. Gaps

- Predictor legality is membership by truth table, not syntactic audit
of a supplied expression. A caller-supplied spec is re-derived, so the
checked object is always the executed one.
- Duplicate queries are cached and free. A stricter charging rule would
count them against the ceiling.
- Held-out scoring assumes the harness keeps the task private. The
instrument guarantees the views leak nothing; it cannot stop a harness
that hands the task to the learner directly.
