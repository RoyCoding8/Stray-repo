# W5 ship check: re-verification of the four corrections at `2fa573b`

**NO — do not ship.** The four fixes hold. A fifth false claim does not, in two
places, and it is the same claim the third fix just corrected elsewhere in the
same document.

throughput checkpoint: n/a, read-only investigation

Scope: verify the four corrections at `2fa573b`, hunt a fifth claim, and return a
ship verdict. No file outside this one was edited. No test suite was run beyond
one named file. No live model call, no Jev, no paid route.

---

## 1. The four fixes

### Fix 1 — `reports/PROJECT-LEDGER.md:44` (E3 row) — **HOLDS**

Every clause verified against source, not against the row's prose.

| Required clause | Verdict | Evidence |
|---|---|---|
| Withdraws "2.7x" as a fresh numerator over a withdrawn denominator | HOLDS | The row states `0.419328 / 0.156883 = 2.6729` "pairs a fresh numerator with the **withdrawn shared-instance** denominator". `0.419328` is the fresh-path sum (measured below); `0.156883` is the *shared* agenda mean, visible at `reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json` under `regenerated_shared.direction.per_budget[2].agenda_held_out_reduction = 0.1568834941383961`. The two substrates are indeed different, so the ratio cannot reproduce on the live path. |
| States the ratio is an identity, not a result | HOLDS | The row: "The 'ratio exactly 3.0 at every non-zero budget' is an **identity, not a result** -- MEAN is defined as SUM/3 over exactly three worlds, so it must be 3." |
| States the sum/mean defect is real, consumed by `gap_to_best` / `rules_beating_it` / two tests | HOLDS | Source: `experiments/ad01/agenda_policy.py:435-440` returns `sum(...)` over `worlds` with no division. `selection.WORLDS == (0, 1, 2)`, so n=3. The value flows to `control_competence` at `:488` (`score = by_rule[key]`), then to `:495` `held_out_reduction`, `:496` `rules_beating_it` (via `value > score` at `:490`), and `:498` `gap_to_best` (`best - score`). Confirmed by live call, see §3. |
| Says **both** guards cannot fail | HOLDS | `tests/test_s09_e3_control_competence.py:189` and `:235-236` both compare `_mean(...)` against `step["best_rule_held_out_reduction"]`, which is the sum. The row says "**Both guards cannot fail**, not one: `:185-189` and `:236`". |
| Crossover 20, not 30 | HOLDS | Measured on live source, see §3. Agenda below best-in-space first at budget 20. |
| Budget-14 sum-is-0.000000-while-mean-is-0.083721 form | HOLDS | Measured: at budget 14 `best_rule_held_out_reduction = 0.0` (the sum) while the agenda arm mean is `0.08372060038726704`. The guard at `:186` takes its `if best <= 0.0: continue` branch there, so the check is skipped at the one budget where the agenda wins. |

The row is longer than the original, names both guards, and concedes the
identity. This is the fix as specified.

### Fix 2 — `reports/STAGE-09-RECOMMENDATION.md:769` (E3 guards) — **HOLDS**

The passage now says "**And the guard on it cannot fail.** **Both guards cannot
fail.**" and traces the value: `s09_e3_selection.py:293-294` ->
`agenda_policy.py:505` -> `:480`. It also concedes the earlier error: "An earlier
revision of this section said 'half wrong'; it was not."

The trace was verified end to end, and it **does** terminate at
`_score_constant_rules`:

1. `experiments/ad01/s09_e3_selection.py:293-294` —
   `step["best_rule_held_out_reduction"] = competence["best_held_out_reduction"]`
2. `experiments/ad01/agenda_policy.py:505` — `"best_held_out_reduction": best`
3. `agenda_policy.py:480` — `best = max(by_rule.values())`
4. `agenda_policy.py:479` — `by_rule = {_rule_key(rule): score for score, rule in scores}`
5. `agenda_policy.py:407` and `:477` — `scores = _score_constant_rules(budget, worlds, depths, "held_out_reduction")`
6. `agenda_policy.py:424` `_score_constant_rules`, summing at `:435-440` with no division.

Confirmed live: `inspect.getsource(_score_constant_rules)` contains `sum(` and does
not contain `/ len(`. The trace is real, it ends where the document says, and the
comparison is a mean against a sum at both sites.

The two guards pass today, and that is the point being made. I ran the one file:
`uv run pytest tests/test_s09_e3_control_competence.py -q` -> `8 passed in 88.01s`.

### Fix 3 — `reports/STAGE-09-RECOMMENDATION.md:727-745` (route probe) — **HOLDS AT THIS PASSAGE ONLY**

Checked against `reports/evidence/w1-e1-boolean-r3/route-probe.json` directly.

The passage now:

- drops the nonexistent "short prompt returns 200 at 2048" as fact;
- names `campaign-prompt-budget-2048` as a `TimeoutError`;
- names `short-prompt-budget-2048` as the 502;
- records that the probe's own `findings` text contradicts its `probes` data;
- calls "the trigger is the budget, not the prompt" **unsupported**.

Ground truth from the JSON:

```text
campaign-prompt-budget-16    status=200
campaign-prompt-budget-256   status=200
campaign-prompt-budget-2048  status=null  error=TimeoutError: timed out  seconds=182.06
short-prompt-budget-2048     status=502   error=empty
```

The `findings` entry `output-budget-causes-the-502` claims "a short prompt
returns 200 at 2048". `probes['short-prompt-budget-2048'].status` is `502`. The
contradiction is real and the passage reports it correctly.

**This passage holds. The same document asserts the opposite at line 424. See §2.**

### Fix 4 — E4 citations at `reports/STAGE-09-RECOMMENDATION.md:51`, `:85`, `:120` — **HOLDS**

All three now carry the disclosure:

- `:51` — "its three JSON artifacts are **not** on HEAD"
- `:85` — "its `w4-leakage.json` is **not** on HEAD"
- `:120` — "`w4-leakage-controls.json` is **not** on HEAD"

And the files really are absent:

```text
$ git ls-tree -r HEAD --name-only | grep -i w4-leakage.json
  (no match)
$ git ls-tree -r HEAD --name-only | grep -i w4-leakage-controls.json
  (no match)
$ git ls-tree -r HEAD --name-only | grep -i leakage
reports/workstreams/w4-leakage.md
```

Only the lane markdown is on HEAD, which is consistent with the citation: the
document claims the JSONs are missing and names the markdown as the restatement
source. Both the disclosure and the underlying absence hold.

---

## 2. The fifth claim

**`reports/STAGE-09-RECOMMENDATION.md:424-427` and `reports/PROJECT-LEDGER.md:22`.**

Both assert that the campaign prompt 502s at the protocol's 2048, and both draw a
budget-not-prompt conclusion from it. That is the exact claim Fix 3 withdrew
eleven lines above the wrong instance, in the same document.

`reports/STAGE-09-RECOMMENDATION.md:424`:

> "the campaign's own probe refutes it: the same prompt returns **200 at 16 and
> 256 output tokens** and 502s at the protocol's 2048. A frozen id absent from
> the 256-entry catalog still answers when dispatched. So the route is answering
> and the 502 tracks the budget the protocol asks for."

`campaign-prompt-budget-2048` has `status: null` and
`error: "TimeoutError: timed out"` after `182.06 s`. It is not a 502. The only
502 in the probe is `short-prompt-budget-2048`, a **short** prompt. The sentence
therefore pairs the campaign prompt with a failure mode recorded against a
different prompt, and then concludes from it. The conclusion is also the one Fix 3
labels **unsupported**.

`reports/PROJECT-LEDGER.md:22`:

> "The r3 route probe shows the same campaign prompt returning 200 at 16 and 256
> output tokens and 502 at the protocol's own 2048, so the 502 tracks the
> requested output budget rather than the prompt or the route being down."

Same false pairing, same retired conclusion, in the ledger's "what is still not
proven" table. The ledger is the document the next reader trusts first, and this
is its rate-limit row.

This is the class the brief asked me to hunt: a claim true at an earlier commit
and false now. The probe data never said this, so the true-at-one-commit form
belongs to the withdrawn `findings` text rather than to the probes. Either way
both live sentences are false against the artifact they cite.

**Aggravating detail.** The fixed passage at `:736` records that "An earlier
revision of this document sided with the text." That is now only half true. The
document currently sides with the text in the same breath, at `:427`. A reader
who reads §2 and then §6 gets opposite answers to the same question.

Two further notes, neither of which I am calling a defect:

- `reports/STAGE-09-RECOMMENDATION.md:421` heads the passage "The route's
  2048-token output budget is the largest single cause, not its availability."
  Even on the corrected reading, the probe establishes that 2048 fails and 16/256
  succeed, which is consistent with a budget cause but does not isolate it, since
  the one 2048 probe is not comparable. The heading is stronger than the
  corrected passage admits. Fixing the sentence below it does not fix the heading
  above it.
- `reports/STAGE-09-COMPLETION-MATRIX.md:184-188` still says "The 2.7x was real
  arithmetic over two real record values but a **denominator artifact**." The
  ledger retracted 2.7x for a reason the matrix does not carry, namely that
  `0.156883` is a withdrawn shared-instance value, not only a sum where a mean
  was wanted. The matrix's 1.67x figure is correct on the live path
  (`0.139776 / 0.083721 = 1.6695`, both fresh means), so the number is not wrong.
  The characterisation of why 2.7x fell is now narrower than the ledger's. I rate
  this a stale characterisation rather than a false claim, and it is not what
  blocks the ship.

---

## 3. The measurement behind the above

Run on live source, not read off any document. `S09ISO_DISABLE=1`,
`PYTHONPATH="<repo>;<repo>/src"`, DSN variables unset.

```text
WORLDS (0, 1, 2)  n=3   BUDGETS (8, 14, 20, 30, 40, 60)
sum( in _score_constant_rules: True | '/ len(' present: False
```

`experiments/ad01/s09_e3_selection.py:283` builds the arm row as
`sum(reductions) / len(reductions)`; `_score_constant_rules` does not divide. The
mismatch is real.

Budget-by-budget, agenda mean against the specified-default mean against the true
best-rule mean (`best_rule_held_out_reduction / 3`):

```text
b  8 agenda=0.000000 default=0.000000 fitted=0.000000 best_mean=0.000000
b 14 agenda=0.083721 default=0.000000 fitted=0.000000 best_mean=0.000000
b 20 agenda=0.083721 default=0.000000 fitted=0.139776 best_mean=0.139776
b 30 agenda=0.111748 default=0.111111 fitted=0.175257 best_mean=0.175257
b 40 agenda=0.144745 default=0.359281 fitted=0.210738 best_mean=0.359281
b 60 agenda=0.205876 default=0.391007 fitted=0.187032 best_mean=0.414277
```

Agenda above best-in-space only at 14. Crossover is 20, as the ledger says. The
`best_rule_held_out_reduction` values the guards compare against are the sums
`0.419328` at 20, `0.525770` at 30, `1.077842` at 40, `1.242831` at 60, matching
`reports/workstreams/w3-e3-recompute.md:138-141`. `0.419328 / 0.156883 = 2.6729`,
matching the retracted figure's own arithmetic.

`uv run pytest tests/test_s09_e3_control_competence.py -q` -> `8 passed in 88.01s`.
One file, eight tests. No other test file was run.

**Stale header, worth a separate fix.** `reports/PROJECT-LEDGER.md:3` reads
"Current checkpoint: 2026-09-30 at `97b320a` ... 22 commits have landed since,
15 touching code." Measured at HEAD `2fa573b`: `git rev-list --count 97b320a..HEAD`
= **31**, and `git rev-list --count 0a17ca9..97b320a` = 22. The counts are a true
statement about the range `0a17ca9..97b320a`, now presented as the current
checkpoint. This is a stale claim rather than a false one, and it sits on the same
line as the "two lanes are live" hedge that keeps the line from being read as
settled. I would fix it in the same pass, but it is not the blocker.

---

## 4. Smallest change set to ship

**Three sentences.** Two rewrites and one heading.

1. **`reports/STAGE-09-RECOMMENDATION.md:424-427`.** Replace "the same prompt
   returns 200 at 16 and 256 output tokens and 502s at the protocol's 2048 ... and
   the 502 tracks the budget the protocol asks for" with the wording already used
   at `:733-740`: the campaign prompt at 2048 is a `TimeoutError` after 182 s, the
   only 502 is `short-prompt-budget-2048`, and the budget-not-prompt reading is
   unsupported. This is one sentence rewritten, not a new argument.

2. **`reports/PROJECT-LEDGER.md:22`.** Same correction, compressed to the ledger's
   register: the campaign prompt returns 200 at 16 and 256 and **times out** at
   2048; the 502 belongs to `short-prompt-budget-2048`; the probe does not
   cross budget against prompt. One sentence.

3. **`reports/STAGE-09-RECOMMENDATION.md:421`.** Retitle from "The route's
   2048-token output budget is the largest single cause, not its availability" to
   something the probe supports, such as "The route answers at 16 and 256 output
   tokens, and 2048 is where the campaign's evidence stops."

Nothing else is required. Fixes 1, 2 and 4 are done and need no touch. Fix 3 is
done at `:727-745` and needs no touch there.

### If only one sentence may change

Change `reports/STAGE-09-RECOMMENDATION.md:424` and leave the ledger. That does not
make the ledger shippable, because a reader lands on the ledger's rate-limit row
first. I would not take that trade. The honest minimum is the three sentences
above, and it is three.

---

## 5. What I did not determine

- Whether the 182 s `TimeoutError` at 2048 is a route limit, a client timeout, or
  a slow generation. The probe has one 2048 campaign-prompt sample and no
  repeat. Undetermined, and nothing above depends on it.
- Whether the nine `transport-loss` records in r3 are the same 502. The document
  asserts 9 at HTTP 502; I did not open the twelve r3 records to check, because
  the fifth claim does not depend on it and the instruction caps me at three
  named test files.
- `reports/STAGE-09-COMPLETION-MATRIX.md` is reconstructed at `19fbe69` and
  predates E1 r2 and the E2 repair. `reports/PROJECT-LEDGER.md:65` says so and
  calls its own E1 r2 rows superseded. I did not re-audit the matrix row by row
  beyond the 2.7x characterisation, since the brief forbids re-reviewing the
  batch.
