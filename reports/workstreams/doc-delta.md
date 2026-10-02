# DOC-DELTA — delta analysis of the three governance documents

Lane DOC-DELTA, branch `wt/doc-delta`, base `6d7558c`. **No governance document
is edited by this lane.** This file is the delta; the orchestrator applies it
after the other lanes land, to keep the merge serial.

Every claim below carries how it was checked. Checks are one of:

- **measured** — read from source, an evidence file or a git count in this
  worktree at `6d7558c`.
- **executed** — the freeze check was run against probe sources in this
  worktree (see §5 for the exact harness).
- **unverified** — not checkable from this tree. Named, not guessed.

## Verdict per document

| Document | Verdict |
|---|---|
| `reports/PROJECT-LEDGER.md` | **Stale and, in one place, overstating.** Six disposition anchors are correct and must not be disturbed. The mechanism row and the freeze limit are wrong in the ledger's favour. Two counts are stale. |
| `docs/design/REFINEMENT-ROADMAP.md` | **Stale on one line, and it is the load-bearing one.** The `CONFIRMED` short form at line 30 is now too generous. The four negatives and the one non-establishment are correct. |
| `reports/STAGE-09-10-COMPLETION-MATRIX.md` | **Materially wrong in §0, §1 and §7, and the defect is the one the independent reviewer overturned.** Its reading rule and its own vocabulary already provide the correction. The numeric layer is still sound. |

The one finding that contradicts the brief I was given is in §6. Read it
before applying any of this.

---

## 1. The disposition correction (applies to all three documents)

The independent review pass (`reports/workstreams/r-final-review.md`, merged
`e442a02`) overturned mechanism CONFIRMED to **TOO GENEROUS**. Two halves:

- **Freeze half** — the documented runtime second layer cannot fire. **Closed
  by X3** (`4b8ff03`, merge `6afd724`). Measured: the claim is now true, but
  not in the way either document words it.
- **Causal half** — `experiments/ad01/trajectory.py:257` computes
  `return "ad01-%s-b%d-effect" % (cid, seq)`, a formatted string with no row
  behind it. **Open.** Being repaired by lane X4b, which is still running.

Measured, and worth recording because the documents could be read as claiming
otherwise. `migrations/0001_schema.sql:122-127` defines
`attempt_observations` as `(id, attempt_id, content, created_at)` — there is no
`operation_id` and no `effect_id` column, so the review's claim that no such
row carries either field is structurally true, not incidental. `operations`
rows in `reports/evidence/invr1b12-swe/store-rows.json` are ids like
`invr1b12-swe-L0-a1`; the `-effect` ids are minted only into
`s09_policy_state.effect_id` (`migrations/0017_s09_state.sql`), which is a
column, not a row.

### Recommended prose, shared by all three documents

Match each file's own vocabulary. The matrix has a `Vocabulary.` paragraph at
lines 19-24 that does not yet carry a word for this; the ledger and the
roadmap have none. Suggested addition to the matrix's vocabulary block:

> `over-claimed` — the mechanism does not do what the report says it does, so
> the mechanism is not credited with it. `not established` covers a
> demonstration; this covers a claim the demonstration does not reach.

Recommended replacement for the ledger's `What the batch established` bullet
in §3 below, and the corresponding matrix §0 row.

---

## 2. `reports/PROJECT-LEDGER.md`

### 2.1 WRONG — the freeze limit (lines 3, 22, 150, and §Evidence dispositions)

Three places state the same now-false limit. Verbatim:

Line 22 (disposition table, row 1):
```
| 1 | Mechanism | **CONFIRMED**, with one stated limit: a *computed* subscript key is not resolved by the static freeze check, and the dynamic before/after comparison in `admit_revision_under_freeze` is the layer that catches it. The freeze is one layer deep, not two. |
```

Line 150 (evidence dispositions table):
```
| Mechanism | **CONFIRMED**, with the stated limit that a computed subscript key is caught by the dynamic layer rather than the static one. |
```

Line 3-4 (header) does not itself make the claim, but names `8a207ab` as the
integration point. Measured: `6d7558c` is now the tip.

**Why it is wrong.** The limit is no longer a computed key. It is four method
forms plus a computed key, and the layer said to catch them does not exist as a
backstop. Measured in `experiments/ad01/improve_channel.py`:
`_frozen_write_reason`'s docstring now says the deferral "cannot fire: a
revision's bytes run out of process against a JSON view carrying none of the
six fields, against disposable stores, never the store compared. The
deferral was the reason the gap survived every gate, so it is deleted rather
than documented. There is no runtime backstop and this function is the whole
of the freeze." `admit_revision_under_freeze` (line 1164) carries the same
statement at 1177-1184. So the mitigation the ledger credits is one the code
has now deleted on purpose.

Measured, executed (§5): all nine forms the reviewer named and one more are
refused by the current check. X2 is also gone as a description — the
enumeration of node types it added was replaced. `_frozen_key` no longer
exists (measured: zero hits), which the ledger does not mention.

Recommended replacement for line 22:

```
| 1 | Mechanism | **CONFIRMED as to the chain, OVER-CLAIMED as to the freeze, and the freeze half is now repaired.** An independent review overturned the first verdict to TOO GENEROUS: the check admitted a frozen write through `dict.update`, `|=`, `pop` and `clear`, and the dynamic before/after comparison credited as the second layer cannot fire, because a revision's bytes run out of process against a view carrying none of the six frozen fields. X3 closed the freeze half. The causal half is open and lane X4b owns it. |
```

Recommended replacement for line 150:

```
| Mechanism | **CONFIRMED as to the durable chain. The freeze was over-claimed, was repaired by X3, and the causal link between an effect id and a store row is not established.** `_s09_effect_id` mints a formatted string with no row behind it; no `attempt_observations` row carries `operation_id` or `effect_id`. |
```

### 2.2 WRONG — counts (lines 14-15, 175)

Line 14-15:
```
Integration branch `codex/stage09-consolidation-2026-10-01`, base `70223fb`.
221 commits, ~53 lanes, two live campaigns, two search passes, an independent
acceptance pass.
```

Line 175:
```
- [x] Derive the next worker batch from the consolidation contract, with finite prospective studies and a stopping condition. **Implemented and integrated** at `8a207ab`, ~53 lanes.
```

Measured. `70223fb..8a207ab` is 87 commits and 34 merges; `70223fb..6d7558c`
is 99 commits and 40 merges. The full history is 235 commits. The brief I was
given says "62 lanes"; the merge subjects name 39 distinct lane labels
(`A1`-`A8`, `B1`-`B18`, `C1`-`C7`, `X1`-`X6b`). I could not reproduce 62 from
any count, and I could not reproduce "~53" from the merge count either — 34
merges at `8a207ab`. Flagged as unverified in §7.

Recommended replacement for line 14-15:

```
Integration branch `codex/stage09-consolidation-2026-10-01`, base `70223fb`,
tip `6d7558c`. 99 commits and 40 merges over the base, spanning 39 named
lanes, two live campaigns, two search passes, an independent acceptance pass
and the independent review that overturned its mechanism verdict.
```

Recommended replacement for the line 175 checkbox body:

```
**Implemented and integrated** at `8a207ab`; repaired after review and now at `6d7558c`.
```

### 2.3 STALE — §Stage 9 and Stage 10, the "Keep the enforced freeze" row (line 100)

```
| **Keep** | The enforced freeze and its refusal suite | The guard and its refusals cannot both pass by the guard being broad — a guard widened by X2 still leaves the authorised revision eligible. |
```

The reasoning is sound and worth keeping. The named lane is stale: X2 widened
the guard by enumeration, X3 then replaced the enumeration with the parse's
own binding contexts. The row now names a superseded mechanism as the reason.

Recommended replacement:

```
| **Keep** | The enforced freeze and its refusal suite | The guard and its refusals cannot both pass by the guard being broad — a guard widened by X2 still left the authorised revision eligible, and X3 then replaced the widened enumeration with the parse's own binding contexts, which is why the refusal suite still admits the authorised revision. |
```

### 2.4 MISSING — the X5 and X6b lanes, and the fifth lock defect

The ledger's §Search passes prose (lines 181-183) says the passes "found four
real defects". Measured: that was true at `8a207ab` and is now short one. The
independent review found a fifth in the same shape, in
`src/settlement/trials.py`, and X5 repaired it.

Measured in source: `amend_protocol` (line 191) now holds the parent `FOR
UPDATE` and inserts the child in the same transaction, and its docstring
states the refusal "raises rather than returning a `CommandResult`". Measured:
two live callers ignore the returned result —
`src/settlement/development.py:968` and `:1023` both catch `SettlementError`
only to re-test the message for `"already exists"`. That is the stated
justification for the raise, and it is correct.

Recommended addition, as a new bullet after the existing search-pass paragraph
at line 181:

```
A fifth defect of the same shape was found by the independent review rather
than by a search pass: `amend_protocol` read a protocol on one connection,
committed, and wrote `supersedes` on a second with autocommit, so four
concurrent amends of one parent all applied. X5 holds the parent `FOR UPDATE`
and inserts the child in the same transaction, so the read that decided the
amendment still holds its lock when the row it decided about is written. The
refusal raises rather than returning, because `store.transact` converts a
raised error into a returned one and two live callers ignore the result.
```

### 2.5 NOT MENTIONED — `source_kind`

The ledger never names `source_kind`, `fixed-menu` or `model-response`
(measured: zero hits across all three documents). Nothing to correct. X6b's
finding — that the label is a provenance cross-check against `origin` and not
a claim about a fixed menu — is a labelling fix with no behavioural change,
and the documents are silent rather than wrong. **No edit recommended.** If
the next writer wants the disposition recorded, §2.4's addition is the place,
but the honest entry is that X6b changed no behaviour.

---

## 3. `docs/design/REFINEMENT-ROADMAP.md`

### 3.1 WRONG — the short-form table (lines 26-32)

```
**The 2026-10-01 consolidation batch (`codex/stage09-consolidation-2026-10-01`, integrated at `8a207ab`) settled the mechanism question and returned four negatives and one non-establishment.**
```
```
| **CONFIRMED** | NEGATIVE | NEGATIVE, not measurable | NEGATIVE | NOT ESTABLISHED | NEGATIVE |
```

Measured: mechanism is not settled. It was confirmed, overturned to TOO
GENEROUS, and the freeze half has since been repaired while the causal half
is open. The other five cells are correct and must not move.

Recommended replacement for the lead sentence:

```
**The 2026-10-01 consolidation batch (`codex/stage09-consolidation-2026-10-01`, tip `6d7558c`, first integrated at `8a207ab`) returned four negatives and one non-establishment. The mechanism was confirmed, then overturned to too generous by an independent review, and the freeze half of that over-claim has since been repaired.**
```

Recommended replacement for the mechanism cell only:

```
| **CONFIRMED as to the chain; the freeze over-claimed, repaired, and its causal link unestablished** | NEGATIVE | NEGATIVE, not measurable | NEGATIVE | NOT ESTABLISHED | NEGATIVE |
```

### 3.2 WRONG — the mechanism paragraph (line 32)

```
What the batch built is real and worth keeping: durable dispatch identity, authority as a mandatory type rather than a runtime branch, a freeze enforced against the parse rather than a hand-kept list, and one mission owner. Two search passes found and fixed four live concurrency and parse defects that no lane's own gate could see. **None of that is evidence of learning.**
```

Two of the four claims hold and two are now wrong. "A freeze enforced against
the parse rather than a hand-kept list" was **false** at `8a207ab` — the
reviewer showed it matched two node types and admitted a mapping-method write —
and is now true again, because X3 rebuilt it on the parse's own binding
contexts. "Four live defects" is short the fifth.

Recommended replacement:

```
What the batch built is real and worth keeping: durable dispatch identity, authority as a mandatory type rather than a runtime branch, a freeze enforced against the parse rather than a hand-kept list, and one mission owner. The third of those was over-claimed when first written — the freeze matched two node types and admitted a write made through a mapping method — and an independent review overturned the mechanism verdict on it. X3 rebuilt the check on the parse's own binding contexts; the causal half of the review's finding is still open. Five concurrency and parse defects are now fixed that no lane's own gate could see. **None of that is evidence of learning.**
```

### 3.3 STILL TRUE — do not touch

The binding-constraint paragraph (line 34) and the instruments paragraph
(line 36) are unaffected by every lane in this batch and remain accurate.
So do the Stage 9/10 gating paragraph (line 40) and the `better mechanism did
not produce better outcomes` line (38), which the X-lane work strengthens
rather than disturbs. Line 38 names `6096442` and the inventory as a baseline
measurement, not a current count; leave the framing.

---

## 4. `reports/STAGE-09-10-COMPLETION-MATRIX.md`

This is the document the review lands on hardest, and its own reading rule
already says what to do: *"A lane's report is a claim, not a row. **A negative
valid study completes its question. An unrun study does not.** Where a report
and its own artifact disagree, the artifact decides."*

### 4.1 WRONG — §0 disposition row 1 (lines 33, 40-43)

```
| 1 | Mechanism | **CONFIRMED** | Every arrow of the milestone-A chain resolved to a durable row and held under tamper; authority is a type, not a branch; the freeze is enforced against the parse. |
```
```
**The limit on disposition 1, carried here so it is not lost:** a *computed*
subscript key is not resolved by the static freeze check, by decision, and the
guard says so. The dynamic before/after comparison in `admit_revision_under_freeze`
is the layer that catches it. **The freeze is one layer deep, not two.**
```

The first clause is measured true and stays. The second is the over-claim,
and the italicised "limit" is now wrong twice: the gap was wider than a
computed key, and the layer named as the mitigation is one X3 deleted because
it could not fire.

Recommended replacement for row 1:

```
| 1 | Mechanism | **CONFIRMED as to the chain; OVER-CLAIMED as to the freeze.** Every arrow of the milestone-A chain resolved to a durable row and held under tamper, and authority is a type rather than a branch. The freeze was over-claimed: at `8a207ab` it matched two node types and admitted a write made through a mapping method, and the dynamic comparison named as the second layer cannot fire. X3 repaired the freeze; the causal half is open. |
```

Recommended replacement for the limit paragraph:

```
**The limit on disposition 1, corrected by the independent review and recorded here so it is not lost.** At `8a207ab` the gap was wider than a computed subscript key: `dict.update`, `|=`, `pop` and `clear` all wrote a frozen field the guard never inspected. The dynamic before/after comparison in `admit_revision_under_freeze` was credited as the layer that catches this and **cannot fire** — a revision's bytes run out of process against a JSON view carrying none of the six frozen fields, and the store compared is never in the child's reach. There is no runtime backstop; the static check is the whole of the freeze. X3 closed this by matching the parse's own `Store` and `Del` contexts and adding the method forms, and deleted `_frozen_key`, whose docstring promised a backstop that could never fire. **What is still open is the causal half:** `_s09_effect_id` mints a formatted string with no row behind it, so the arrow from an effect to a store row is bound by `(investigation_id, seq)` and not by effect identity.
```

### 4.2 WRONG — §1 freeze row and the "Freeze depth" row (lines 51, 54)

```
| Freeze enforced against the parse | `confirmed` | Acceptance probed `improve_channel._attempts_frozen_write` with 19 binding forms it wrote itself — **zero mismatches**. A read and a write to a non-frozen key are correctly admitted. X2 widened the guard to the subscript position and the authorised revision stayed eligible. |
```
```
| Freeze depth | **limit** | A computed subscript key passes the static check; the dynamic layer catches it. |
```

The 19-probe result was real and stays as history, but "zero mismatches" is
now a claim about a probe set that did not open the door beside it. The
reviewer's point is precise: all 19 were subscript or attribute spellings.
X2 is superseded by X3.

Recommended replacement for the freeze row:

```
| Freeze enforced against the parse | `confirmed` after X3 | At `8a207ab` acceptance probed `improve_channel._attempts_frozen_write` with 19 binding forms it wrote itself and found zero mismatches; all 19 were subscript or attribute spellings, which is why the review's mapping-method forms were missed. X3 replaced X2's node-type enumeration with the parse's own `Store`/`Del` contexts and added the key-taking and keyless method forms. Executed against the merged tip: all nine forms refused, and a read of `view["grant"]` plus a write to a non-frozen key and to a revision-owned `seen[key]` are still correctly admitted. |
```

Recommended replacement for the `Freeze depth` row:

```
| Freeze depth | **`confirmed` as a single layer, `open` as to effect causality** | There is no second layer. The static check is the whole of the freeze, and a computed key is now refused as unreadable rather than deferred. Separately and independently, `_s09_effect_id` mints an id with no row behind it, so effect identity does not bind the effect to a store row. That half is open under X4b. |
```

### 4.3 WRONG — §7, the defects table is short one row

The section is headed "Search passes and the defects they fixed" and lists
four. The fifth exists, came from the review rather than a search pass, and is
repaired. The generalisation paragraph at 121-123 says it "produced four real
fixes", which is now understated rather than wrong.

Recommended addition as a new row after the `P2-03` row at line 119:

```
| R-final-01 | `amend_protocol` read a protocol on one connection, committed, and wrote `supersedes` on a second with autocommit, so four concurrent amends of one parent all applied. | X5 holds the parent `FOR UPDATE` and inserts the child in the same transaction. The refusal raises rather than returning a `CommandResult`, because `store.transact` converts a raised error into a returned one and two live callers ignore the result. |
```

And replace "it produced four real fixes" (line 123) with:

```
right one, and it produced four real fixes; an independent review found a fifth in the same shape, and X5 repaired it.
```

### 4.4 WRONG — §13, "Documentary defects recorded, not repaired in place" (line 224)

```
were in the documentary layer and in one unmeasured freeze.
```

"unmeasured" is the wrong word and it is the review's own. The freeze was
measured, by the review, and found wanting. Recommended replacement:

```
were in the documentary layer and in the freeze, which the review measured directly rather than leaving unmeasured.
```

### 4.5 STILL TRUE — do not disturb

Measured and correct, so the next writer should leave them alone:

- The reading rule (15-18) and the vocabulary block (19-24), except for the
  one addition proposed in §1.
- §2 Acquisition. Recomputed from
  `reports/evidence/invr1b12-swe/campaign.json`: `acquired_lineages 0`,
  `independent_acquired_lineages 0`, `distinct_acquisition_digests 0`,
  `lineages_attempted 4`, `no_acquisition_lineages 4`,
  `physical_sends 5`, `operations_in_store 5`, `receipts_in_store 5`. Note
  these live under the `summary` key, not at top level. The five operation ids
  are `invr1b12-swe-L{0,1,2,3}-a1` and `L3-a2`, matching the row.
- §8's budget arithmetic. `authored_source_characters 22734`,
  `max_source_characters 7000`, `authorised_physical_sends 25`,
  `dispatches_used 5`, `max_output_tokens 2048`. All five match.
- §9's panel census. 14 panels, exactly 3 with `powered: true` and 6 clusters
  against 6 required.
- §1's "Authority mandatory" row. Measured: `REACHABLE_EVIDENCE`,
  `MENU_EVIDENCE` and `_menu_probe` have zero hits in `experiments/` and `src/`.
  `_STRATEGY_SOURCE` has one hit, at `improve_channel.py:2090`, and it is
  prose saying the resolution "used to" consult it. "No longer exist" holds.
- §6's inheritable construction row. Executed: `_revision_source` returns
  1067, 1067 and 1068 characters for `(3)`, `(8)`, `(11)`, and all three are
  admitted by the freeze. "~1067-character sources" and "all pass the
  frozen-write check" both hold.
- §13's two archived-generator rows and the `120` vs `72` row. Measured: the
  `120` string is at `experiments/ad01/twodomain.py:102` and
  `tests/test_inv_c7_two_domain.py:16`, exactly as recorded.
- §10's keep/change/remove table apart from the "Keep the enforced freeze" row
  in §2.3 above, and §12's outstanding table, which is unaffected by any lane
  in this batch.

---

## 5. The freeze probe, for the reviewer to rerun

`experiments/ad01` cannot be imported on this host — `src/settlement/broker.py`
imports `dbos`, which is not installed in the Windows Python, and tests run in
WSL. The freeze check is pure `ast`, so I extracted the fifteen helpers and
their constants by parsing the module, loaded them standalone and ran them.
That is a weaker harness than the real test suite and is offered as such.

Extracted: `_frozen_write_reason`, `_target_frozen_reason`, `_names_frozen`,
`_call_write_reason`, `_update_write_reason`, `_keys_named_by_update`,
`_readable_key`, `_names_bound_to_view`, `_is_view`,
`_frozen_write_reason_unreadable_key`, `_frozen_write_reason_unreadable_arg`,
`_frozen_write_reason_keyless`, `_attempts_frozen_write`, `FROZEN_FIELDS`,
`_VIEW_PARAMETER`, `_KEY_WRITING_METHODS`, `_MAPPING_ARG_METHODS`,
`_PROTOCOL_WRITES`, `_BUILTIN_WRITES`. All from
`experiments/ad01/improve_channel.py` at `6d7558c`.

Refused, with the reason the check returns:

| source | reason |
|---|---|
| `view["grant"] = 1` | `writes view['grant'], a frozen field` |
| `view.update({"grant": 1})` | `view.update writes the frozen field 'grant'` |
| `view \|= {"grant": 1}` | `view \|= merges keys into the view it was handed` |
| `view.pop("grant", None)` | `view.pop writes the frozen field 'grant'` |
| `view.clear()` | `view.clear writes every key of the view it was handed` |
| `k = "grant"` then `view[k] = 1` | `writes view[k], a key this check cannot resolve to a name` |
| `view.update(grant=1)` | `view.update writes the frozen field 'grant'` |
| `view.popitem()` | `view.popitem writes every key of the view it was handed` |
| `view["frozen_source"]["grant"] = 1` | `writes view['grant'], a frozen field` |

Correctly admitted, which is the half that matters as much as the refusals:

| source | result |
|---|---|
| `print(view["grant"])` | admitted — a read is legitimate |
| `other["x"] = 1` | admitted — non-frozen key |
| `seen[key] = 1` | admitted — the revision built it |
| `view.update(seen=k)` | admitted — non-frozen key through a method |
| `eval(view)` | refused — `calls eval, which writes a frozen field` |

The one-hop case at the bottom of the refusal table is worth noting. The X3
docstring at `_frozen_write_reason` says the rule "does not reach a mapping the
revision reached through one hop", and then gives the reason it does not need
to: the view the child receives carries `authority_remaining` and
`improvement_budget` and none of the six frozen fields. The check refuses it
anyway, so the docstring's stated limit and the code's behaviour disagree in
the safe direction. **No document change is recommended for this.** It is a
note for whoever owns the docstring, and the docstring's own reasoning is
sound about *why* the hop is harmless.

---

## 6. What contradicts the brief I was given

Four things, stated plainly.

**6.1 The "8 non-test sites" figure for `source_kind` does not reproduce.**
The brief lists 8 and attributes the count to X6b. Measured at `6d7558c` by
grepping `experiments/`, `src/` and `scripts/` for the two literals, excluding
`tests/`: 18 lines match. Of those, 3 are prose or error-message strings rather
than values (`frontier.py:137`, `:441`, `:447`, plus `live_construct.py:1007`
and `:1242`, which are messages), and `scripts/invl02_live.py:1937` and
`:2979` are two more. The sites that literally assign or compare the value:

| file:line | what it is |
|---|---|
| `experiments/ad01/channel_controls.py:273` | assigns `"fixed-menu"` |
| `experiments/ad01/frontier.py:129` | default kwarg |
| `experiments/ad01/frontier.py:439` | the `authored-control` check |
| `experiments/ad01/frontier.py:446` | the `acquired` check |
| `experiments/ad01/frontier.py:487` | acquisition-evidence check |
| `experiments/ad01/improve_channel.py:1716` | assigns `"fixed-menu"` |
| `experiments/ad01/improve_channel.py:2119` | assigns `"fixed-menu"` |
| `experiments/ad01/learner_revision.py:608` | ternary on `acquired` |
| `experiments/ad01/live_construct.py:1180` | assigns `"model-response"` |
| `experiments/ad01/live_construct.py:1240` | the `fixed-menu` control check |
| `experiments/ad01/live_construct.py:1006` | requires `model-response` |
| `scripts/invl02_live.py:1937` | asserts `fixed-menu` |
| `scripts/invl02_live.py:2979` | requires `model-response` |

So the brief's 8 is a defensible count of *assignment* sites in
`experiments/ad01` minus the two it names as unowned, and it omits
`frontier.py:487` and `live_construct.py:1006`, which are comparisons the
validator makes. **This does not change any recommendation.** `source_kind`
appears zero times in all three governance documents, so there is nothing to
correct either way. I record the discrepancy because the ledger's new counts
should not inherit a figure I could not reproduce.

**6.2 `frontier.py:129` is a default kwarg, and the brief's line list places
the check itself at `:439`.** Both are correct as given. Not a contradiction,
noted so the next writer does not re-derive it.

**6.3 "62 lanes have been merged" does not reproduce.** Measured: 40 merges
over the base, naming 39 distinct lanes. The merge-count and the lane-label
count differ by one because one merge is not a lane — it is
`Merge independent review: mechanism was too generous`, at `e442a02`. I
report the measured numbers and flag the brief's figure as unreproducible.

**6.4 The X5 refusal claim needs one qualifier the brief omits.** The brief
says the refusal "now RAISES rather than returning a `CommandResult`, because
`store.transact` converts a raised error into a returned one and two live
callers ignore the returned result." Measured: that reasoning is in the code
and it is correct, but it is a justification for a re-raise at a specific
boundary, not a general property. `amend_protocol` re-raises
(`trials.py`, in the `_fn` closure's handler) precisely *because*
`store.transact` would otherwise swallow it. If the recommended §2.4 prose is
applied, it should say the refusal raises at this boundary for this reason,
which is what the draft above does. Do not generalise it to other commands.

---

## 7. Flags — claims I could not verify

Named rather than guessed. Each is a place where the next writer must either
find the evidence or leave the existing text alone.

1. **"~53 lanes" and "221 commits" (ledger 14-15).** 221 is reproducible at
   `8a207ab` — 223 total minus the base commit and its partner — but the
   ledger does not say what it counts, and 53 matches no count I could compute.
   34 merges at `8a207ab`, 40 at the tip, 39 distinct lane labels. **Do not
   replace 53 with 39 without knowing what 53 counted.** My §2.2 replacement
   states 99 commits and 40 merges over the base at `6d7558c`, which is
   measured, and drops the lane count rather than guessing a corrected one.
   If the orchestrator knows what 53 counted, substitute that.
2. **"62 lanes" from the brief.** Unreproducible. See §6.3.
3. **"129 passed" for X3, "8 passed" for X5, "43 passed" for X6b.** Test
   counts are claims in the commit messages. I did not run them: the suite
   needs WSL, PostgreSQL and the `dbos` dependency, none of which exist in
   this worktree. Per the project's standing rule, a green test count proves
   none of the research claims, and none of the recommended prose above rests
   on a count.
4. **"3 of 3 such ids are absent from the `operations` table."** Structurally
   confirmed (§1: no column can carry them, and the `operations` ids in the
   evidence file are a different family). I could not run R-final's actual
   query, because no database is reachable here. The claim is very likely
   right and is not independently reproduced.
5. **Whether X4b has landed.** The brief says it is still running. The tip is
   `6d7558c` and X4b is not in it. **The causal half of the finding must be
   re-checked against whatever X4b does**, and §2.1 and §4.1's replacement
   prose should be read against X4b's outcome before it is applied. I have
   written both to state the causal half as open, which is correct now and
   may be stale by the time the orchestrator applies it.
6. **The retention leg's 26 comparable rows and the Boolean hypothesis-class
   count.** Both are cited in the matrix §4, §5 and §9 and both were
   re-confirmed by the review at §2 and §5 above, but I read them from the
   documents and the panel census only. I did not re-derive the 26 or the
   single class. They are marked as still true on the review's attestation
   plus my census check, not on my own recomputation.
7. **B11's ladder rungs and the 4096 loss.** Not re-derived. The evidence
   directory was not opened.

---

## 8. Order of application

The three documents share the mechanism correction, so it should be applied in
one pass by one writer, after X4b lands, or the documents will disagree with
each other about the same claim.

1. Wait for X4b, then re-read §1 and decide whether the causal half is closed.
2. Apply §2 (ledger), §3 (roadmap), §4 (matrix) in one commit. The roadmap's
   one-line table and the ledger's disposition table must move together.
3. Apply §2.4 and §4.3 — the fifth defect — in the same commit, since both
   documents count the defects.
4. Leave the §2.5 note out. `source_kind` needs no governance change, and a
   document edit that records a labelling fix with no behavioural change adds
   reader load for nothing.
