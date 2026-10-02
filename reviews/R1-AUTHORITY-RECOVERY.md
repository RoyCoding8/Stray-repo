# R1 — authority and recovery: independent review

Reviewer lane R1, per `WORKER-STAGE-09-PARALLEL-EXPANSION.md:41`. Read-only on
`src/`, `experiments/`, `tests/`, `conftest*`, `reports/`. Nothing under those
trees was edited. All reproductions are throwaway scripts under `/tmp/r1/`, run
against databases created by `experiments.ad01.s09_run_isolation.disposable_db`
and dropped on exit. Tip reviewed: `254f43e` on
`codex/implementation-investigation-learning-02`.

**The question this lane was asked:** can the system be made to spend,
dispatch or settle something it is not entitled to?

**The answer, in one line: yes, and it takes one string.** A caller that knows
an operation's id, its dispatch generation and the admitted launcher's id can
release a reservation for work that really ran, and the refund goes back into
the allocation as free capacity. N-55 records that a launcher id is not a
secret; this is what the consequence of that judgement is, measured.

---

## Findings, most severe first

### N-200 — HIGH — a caller-forged never-sent proof returns a real sandbox's whole reservation to the free pool

**Location**

| | |
|---|---|
| the proof check | `src/settlement/store.py:453-503` (`_never_sent_proof`), `:506-528` (`_provenance_attested`) |
| the acceptance test | `src/settlement/store.py:520` — `provenance == attested_by or provenance.startswith(f"{attested_by}:")` |
| the secret | `src/settlement/launcher_local.py:61` — `launcher_id = "local-1"`, a class constant |
| the caller | `src/settlement/steward.py:66-67` → `store.release_reservation` |
| the state machine | `src/settlement/store.py:817-858` — for a `reserved` or `uncertain` reservation the proof is the **only** gate between "units stay held" and "units return to the allocation" |
| the same gate on cancellation | `src/settlement/store.py:1932-1937` (`confirm_cancellation`) |

**Reproduction** — `/tmp/r1/p8_release_real_work.py` and
`/tmp/r1/p11_steward_release.py`:

```
cd /home/ubuntu/AI/Agent-Society-v2
.venv/bin/python /tmp/r1/p11_steward_release.py
```

Output:

```
real executions: 1
launcher says prove_never_sent: False
steward.release_reservation: applied | released
reserved 111 -> 0 | consumed 0 -> 0 | free 999889 -> 1000000
```

`p8` drives `store.release_reservation` directly and prints the reservation
row, which is left `state='released', amount=111`. `p11` drives it through
`steward.release_reservation`, the public wrapper.

The sequence, all against a real `LocalLauncher` and a real disposable store:

1. An operation is prepared and `advance_dispatch` puts it in `dispatching`.
2. `launcher.dispatch(...)` really executes a Python child that appends to a
   counter file. `real executions: 1`.
3. The store is never told — the crash window. An `unknown` receipt
   (`gw:<op>:lost-response`) is admitted, which is what a lost gateway
   response produces, and which sets the reservation to `uncertain`.
4. The caller supplies a hand-written proof:
   `{"claim": "never-sent", "subject": <op>, "provenance": "local-1:prove_never_sent", "dispatch_generation": <read from the operations row>}`.
5. `release_reservation` returns `APPLIED`. `reserved` goes 111 → 0, the
   reservation is marked `released`, `consumed` stays 0.

**Impact.** 111 units of a sandbox that ran and produced a side effect are
recorded as never spent, and the allocation's free capacity rises by exactly
that. This is the durable owner's *refund* path, so it is the one place where
an unproven claim converts directly into spendable budget. Combined with the
second execution below, a single forged string both doubles the work and hides
the cost.

Two facts make this cheap to do rather than theoretical:

* the generation and the operation id are columns in `operations`, readable by
  any caller with store read access;
* the "attestation" is `"local-1"`, a class constant in the same package
  (`launcher_local.py:61`). Nothing is compared against a value the caller
  cannot read.

**Who owns it.** The N-48/N-55 pair — settlement. N-55 already names the
judgement ("whether a launcher id is a sufficient secret"); this says the
judgement is not neutral, because the thing being bought with it is budget.

**What the ledger gets right here.** N-55 is a *judgement* row and it names
`launcher_id` as "a public constant in the same package". That is exactly
right. What the ledger does not carry is the consequence: the same string
releases real work, not just a stranded one. N-48's row is still correct —
the shape-only forgery (`provenance: "forged"`) really is refused.

---

### N-201 — HIGH — `LocalLauncher.prove_never_sent` returns True after a send, so the production redispatch path executes a side effect twice

**Location**

| | |
|---|---|
| the predicate | `src/settlement/launcher_local.py:119-126` |
| the runsc contrast | `src/settlement/launcher_runsc.py:271-284` — also checks `self._ps_names(base)`, i.e. whether a process for this operation is live. `LocalLauncher` has no equivalent. |
| the production caller | `src/settlement/broker.py:1249-1266` (`redispatch_after_reset`) |
| the store side | `src/settlement/store.py:2000-2039` (`reset_dispatch`) |
| the test that pins the property | `tests/test_r01c_redispatch.py:36-45` — `prove_never_sent` is False *after* `dispatch`. The test's own setup is a completed `dispatch`, which writes `*.result.json`, so only the first of the five markers is ever load-bearing. |

**Reproduction** — `/tmp/r1/p12_honest_crash.py`:

```
cd /home/ubuntu/AI/Agent-Society-v2
.venv/bin/python /tmp/r1/p12_honest_crash.py
```

Output:

```
executions: 1
markers before: ['N1_exec-default.gen', 'N1_exec-default.result.json', 'N1_exec-default.spawns', 'N1_exec-default.work', 'counter']
markers after : ['N1_exec-default.work', 'counter']
prove_never_sent: True | receipts: 0
redispatch -> observed terminal
executions after: 2
SIDE EFFECT REPLAYED
```

**Stated honestly, and this is the finding's sharpest edge:** the markers were
removed by the reproduction, not by a kill. I tried to produce it without
that and could not — see the negative results below. What the reproduction
*does* establish without any hand-editing is the first half: the store holds
an operation in `dispatching` with zero receipts whose work has already run,
and `prove_never_sent` answers True the moment the run directory stops
carrying its bookkeeping. The only external trigger needed is losing that
bookkeeping — a cleaned run directory, a tmpfs that did not survive, a
different `run_dir` handed to the recovery path, or any caller with write
access to the run directory.

**Why the predicate is not a proof.** `LocalLauncher.dispatch` writes its
markers in this order (`launcher_local.py:212-229, 246, 259`): `_claim(pid)` →
`.gen` → `.spawns` → `Popen` → `.pid`. The result file comes after `wait()`.
So *during* a send the markers are present and the predicate is correctly
False. But the predicate is a **negative** test over five glob patterns and a
positive test over nothing. It cannot distinguish "never claimed" from
"claimed and the evidence is gone". `launcher_runsc` adds a live-process
check for exactly this reason; the local profile has no equivalent, and its
own `dispatch` also returns `LaunchOutcome(sent=False,
refused_reason="prior-send-recorded")` for that same case — so the *dispatch*
side knows the difference while the *proof* side does not.

**Impact.** A second real execution of the same operation, and then (via
`_finish_send`) a single `success` receipt that the ledger reads as the whole
story. Exactly the N-47 "one operation, two executions, one receipt" shape.

**Who owns it.** Settlement, with the launcher owner. The comment at
`launcher_local.py:12` — "This profile is still explicitly not containment" —
is about the sandbox; this is a durability claim, and the durability claim is
what is weak.

---

### N-202 — HIGH — `test_kill_during_validation_resumes_identical_to_control` fails deterministically: a crash costs a *second construction call*, not a re-send

**Severity note.** This is HIGH, not blocker, for a reason the ledger's own
N-42 warns about: it is a test failure, and I could not measure the underlying
runtime on a quiet box (N-83: a foreign process has held half this host since
before the reported runs). It is deterministic in the sense that matters —
**4 of 4 isolated runs failed** — and the test's own stores are per-run
derived (`8f01023`), so it is not the shared-database contamination N-46
describes. It is not a flake.

**Location.** `tests/test_invd1_dispatch.py:435`, reached from `:482`.
Failing key: `model_calls`, `2 != 1`.

**Reproduction**

```
cd /home/ubuntu/AI/Agent-Society-v2
for i in 1 2 3 4; do .venv/bin/python -m pytest \
  "tests/test_invd1_dispatch.py::test_kill_during_validation_resumes_identical_to_control" \
  -q -p no:randomly 2>&1 | tail -1; done
```

Four `1 failed`. The failure text:

```
control = {'model_calls': 1, 'construction_calls': 1, ...}
got     = {'model_calls': 2, 'construction_calls': 2, ...}
resume_gw_calls = ['ad01-ad01-w0-I-00-b0-ad01-w0-dev-sw-00-construct-l1-repair']
E  AssertionError: ('model_calls', 2, 1)
```

**What actually happens** — `/tmp/r1/p14_repair_leak.py` replays the same
staged kill and prints the store afterwards:

```
staged kill on ad01-...-validate-l1-init state dispatching receipts 0
op: {...-construct-l1-init}   observed  settled=True  res=settled  amount=3403
op: {...-construct-l1-repair} observed  settled=True  res=settled  amount=3452
op: {...-validate-l1-init}   (no row after the resume)
alloc 'ad01-w0-I-00-construct': authorized 16384 consumed 6855 reserved 0
```

The validation operation is **not re-sent** — `gw_calls` is empty and no
second validation row exists. What happened is that the stranded validation
operation stayed `dispatching` with zero receipts, so
`experiments/ad01/construct.py:107` raised `ConstructionFailed("construction
call ... left no settled response")`, and `construct_method` took its
`repair-transport` branch (`construct.py:224-233`), issuing a **brand-new
model call** to redo the construction.

So the crash costs one extra model call, not one extra sandbox execution. That
is a budget and protocol property, not a replay.

**Impact, and the part that matters for R1.** The extra construction call spent
**3452 units against a control that spent 3403** — 1.4% over. Within the
campaign's `caps`, so not a ceiling breach. But:

* `experiments/ad01/trajectory.py:1109-1121` recomputes `state["model_calls"]`
  by counting existing `model-inference` operation rows, so the *count* stays
  honest across a resume; the cap itself is honoured.
* The stranded operation's 111 units are **not** recovered by the resume. They
  stay `reserved` forever unless someone reconciles by hand.

**The second half is the finding.** `/tmp/r1/p15_strand_cost.py` runs the same
kill and then calls `authority.verify_ledger`, the function CS-02/N-04 name as
the reconciliation:

```
verify_ledger: { ..., "pending": 111, "reserved": 111,
                 "unreceipted": ["ad01-...-validate-l1-init"],
                 "match": true }
```

`match: true`. A store holding 111 units of unsettled exposure on an operation
that will never settle reports a **matching ledger**. The number is right; the
verdict is not. `verify_ledger:380` computes

```python
"match": not conflicts and consumed == summary["expected_consumed"]
and reserved == pending
```

and `pending` includes exactly the stranded amount by construction
(`authority.py:366-367` adds `summary["pending"]` to the unreceipted reserved
rows). So a stranded operation is a *named* liability that never trips the
match. For a study whose evidence rests on this reconciliation, that is the
difference between "the ledger agrees" and "the ledger agrees with itself".

Reconciling it by hand works and is cheap — but it needs a forged proof:

```
reconcile: applied operation ad01-...-validate-l1-init reconciled with never-sent proof
alloc after reconcile: reserved 0
```

N-205 (below) is why that is a defect and not a procedure.

**Who owns it.** The test: INV-D1's author or the integration owner. The
`match` predicate: settlement, alongside CS-02. N-33 and N-74 both record
counts measured before the settlement repairs; this is a settlement file this
lane never ran, and it is a hard failure rather than a stale assertion, so it
belongs in the same list as N-33's cluster (a).

---

### N-203 — MEDIUM — the live `LiveGuard` ceiling counts attempts, so a store refusal permanently burns dispatch budget

**Location.** `experiments/ad01/live_construct.py:317-322`:

```python
attempts = 0
while True:
    attempts += 1
    self.dispatch_count += 1
    try:
        response = self.delegate.infer(request)
    except Exception:
        ... record an 'unresolved' evidence entry ... raise
```

`dispatch_count` is never decremented, and `is_ceiling_reached` compares it
against the frozen `max_dispatches` (`live_construct.py:212-213`).
`_DurableBrokerOutput.infer` raises `RuntimeError` when the store refuses to
prepare (`scripts/invl02_live.py:877-879`), which is the ordinary way a
dispatch dies before it happens.

**Reproduction** — `/tmp/r1/p6_guard_ceiling.py`, real `LiveGuard` over a
real disposable store with a delegate that raises exactly as
`_DurableBrokerOutput` does:

```
cd /home/ubuntu/AI/Agent-Society-v2
.venv/bin/python /tmp/r1/p6_guard_ceiling.py
```

```
baseline (no store refusals): {'ceiling': 3, 'admitted': 3, 'real_dispatches': 3, 'operations_rows_in_store': 3}
one store-refused attempt:      {'ceiling': 3, 'admitted': 2, 'real_dispatches': 2, 'operations_rows_in_store': 3}
```

One attempt the store refused before any dispatch cost the study one of its
three authorized dispatches. The baseline proves the ceiling is otherwise
exact, so the loss is precisely the refused attempts.

**Impact.** Under-counting authority. The frozen `max_dispatches` is spent by
things that did not dispatch, which is the failure mode the Stage 9 expansion
doc's "derive and record a finite cap sheet from the actual matrix" is meant
to prevent: the cap sheet becomes an estimate of attempts rather than a bound
on dispatches. Nothing over-spends; the study just cannot finish.

This is the *opposite* direction from N-200, and the two are the same
asymmetry — the guard is the only thing between the study and the store, so
when the two disagree the guard wins and the store's refusal is invisible.

**Who owns it.** Study (the invl02 guard owner). Note the ledger's N-40
already records `_output_evidence_spent` dereferencing `operation_id` into a
set with no type guard, and N-26 an E4 verdict that reports `informs_decision:
True` for a revision that selected nothing. This is the same shape in a third
place: a counter that advances on an attempt rather than on a fact.

---

### N-204 — LOW (confirmation, not a new defect) — a declared-only ceiling is still unenforced, and `require_enforceable_ceilings` has no caller outside tests

**N-32 confirmed, and its repair is only a predicate nobody calls.**

`store.py:1276-1314` (`_check_study_ceilings`) is real and it is on the live
path. Reproduction `/tmp/r1/p1_ceiling.py`:

```
cd /home/ubuntu/AI/Agent-Society-v2
.venv/bin/python /tmp/r1/p1_ceiling.py
```

```
enforceable: True False
require_enforceable_ceilings: REFUSED -> ceilings this layer does not count
  or enforce: max_boundaries, max_witness_queries
admit 3 insufficient_resources study root:study ceiling model_calls=3 reached at 3
admitted: 3   (ceiling was 3)
```

A counted ceiling is enforced on the live dispatch path (3 admitted, the
fourth refused before spending exposure). A name in `DECLARED_CEILINGS` is
accepted, stored as authoritative, and skipped forever — exactly as N-32
says. `store.is_ceiling_enforced` and `store.require_enforceable_ceilings`
exist to make the gap answerable; `grep` finds them in `store.py` and in
`tests/test_s09_store_cleanup.py` and **nowhere else** — not in
`experiments/`, not in `scripts/`, not in `src/`. The two live cap sheets
(`scripts/s09_pilot.py:66`, `scripts/invl02_live.py:1692-1709`) name only
enforceable ceilings, and the lane that wrote `_output_study_ceilings`
documents in its own docstring that it once authorized `construction_calls: 0`
"which was unenforced when it was written, so nothing noticed" — i.e. the
hazard has already bitten once and was fixed by hand rather than by a check.

This is not a new defect and it is not a regression. It is recorded because
"the guard exists" reads, from the source, like a repair, and the guard has
never been asked a question. Owner: settlement, if anyone; the fix is one call
site.

---

### N-205 — LOW — `loop.py:199` folds "not measured" into a measured zero, and the "not measured" case is much wider than N-03 says

N-03 is OPEN-PARTIAL on this line and is right that the line is unrepaired.
The recheck is the finding: the *severity* is understated, because the fold is
not only an unreported charge. It also fires for a receipt that never arrived
at all.

**Reproduction** — `/tmp/r1/` (inline script, the real function, the seams
monkeypatched exactly as `tests/test_invl02_accounting.py` does):

```
no receipt at all                    -> measured=0  provider_charge_units=None  billed=None  unknown=[]
unknown outcome, no usage            -> measured=0  provider_charge_units=None  billed=None  unknown=['r1']
unbilled usage (billed=False)        -> measured=0  provider_charge_units=0     billed=False unknown=[]
no usage field on a success          -> measured=0  provider_charge_units=None  billed=None  unknown=['r1']
```

Row 1 is the one N-03's wording does not reach. `loop.py:186-187` sets
`billing, charge = None, None` when `terminal is None` and never records the
absence; `loop.py:199` then emits `"measured": charge or 0`. The result is a
`0` for an operation that has no receipt — and the two fields that exist to
distinguish the cases, `billed: None` and `unknown: []`, are not the ones a
reader sums.

`ExperienceTransition` at `loop.py:559-562` copies `measured` into
`costs_measured` and `provider_charge_units` alongside it, so both the folded
zero and the honest `None` reach the journal.

**Why the ledger is nonetheless right to call this PARTIAL rather than a live
defect.** I traced the consumer: `experiment._provider_billing`
(`src/settlement/experiment.py:894-911`) filters on `billed is True` and
reports `status: "unknown"` whenever any model entry has `billed is None`. The
publication layer therefore does not treat the folded zero as a measurement.
The `ProviderCharge` tri-state in `experiments/ad01/s09_exposure_ledger.py:118`
exists for the same reason. So: two sources of truth for "measured", and
whichever a reader reaches first decides whether an unmeasured call is a zero.
That is N-03's own framing, now with a wider trigger set. Owner: unchanged.

---

## Existing ledger rows I believe are WRONG

**None.** I checked the rows this lane was told to probe, and each one is
factually correct at this tip. Specifically:

* **N-81** (E4's six dispatches bypassed the durable owner). **Correct, and
  the bypass is still reachable from code, but the reachable paths are
  disciplined.** The evidence is
  `reports/evidence/inv_r1_e4/result.json` → `authority_deviation`, which
  states the deviation in its own words. I then went looking for other
  producers of `HttpGatewayAdapter` and found the picture the row does not
  record:
  - `experiments/ad01/e3_ladder.py:578-586` and `experiments/coord02/entry.py:823`
    build a `urllib.request.Request` and call `urlopen` **directly** — no
    broker, no store, no guard at all. Not a deviation from the durable owner;
    an absence of one. It is gated by a `no-credential` check (`:569-571`) and
    a `PROBE_MAX_TOKENS` cap, and it is a *probe*, not a study dispatch.
  - `experiments/ad01/e2_replication.py:956` builds the adapter directly, but
    through `_DurableBrokerOutput`, i.e. the same durable owner as
    `scripts/invl02_live.py:1638`.
  So the answer to "is the bypass path still reachable" is: yes, in two
  places, and in both the exposure is bounded by construction rather than by
  authority. **What an unaccounted dispatch costs the ledger** I can now
  answer with a measurement rather than a sentence: nothing in the store, and
  the artifact records its own prompt digests, operation ids, replies and usage
  — which is why N-81's consequence ("a later reconciliation will not find
  them") is right and no worse. The row needs no correction; it needs a
  sibling row for `e3_ladder`'s raw `urlopen`, which is a different defect
  (no reservation at all, not a bypassed one) and is not N-81.

* **N-43** (failure receipts). **Correct and still a repair.** I drove the
  `LocalLauncher` vocabulary: a receipt carrying only
  `{"parse": "ok", "data": {"returncode": 0}}` is admitted and settles
  (`/tmp/r1/p2_double_decided.py`, first receipt: `applied {'settled': True}`).
  The refusal at `store.py:1702` is reached before the prior-receipt guard, as
  the row says.

* **N-47** (strand handling). **Correct, repaired in source**, and the
  controls at `tests/test_s09_controls.py:309` and `:370` do what the row
  says. My p12/p15 work is downstream of it, not against it.

* **N-48** (attested proof). **Correct as a repair and, given N-55, correct as
  an incomplete one.** The shape-only forgery is refused; the
  launcher-id forgery is not. N-200 is the consequence N-55 did not measure.

* **N-30 / `tests/test_s09_multi_receipt.py`.** **The test still describes the
  current code, exactly as the row says.** 6 passed. It asserts
  `"if prior and not (resolves_unknown" in body`,
  `"additional_observation = (" in body` and `"len(prior) == 1" in body`, and
  all three are present at `store.py:1818`, `:1814` and `:1789`. The test's
  docstring still says "These tests pin the shape. They do not repair
  `store.py`" — which is now a statement about the past, since `c4e8e93`
  applied the repair and the test's own assertion (`additional_observation = (`)
  is asserting the repair is present. **The pin is live and it is green
  because the repair landed, not because the pin is obsolete.** The task
  brief's framing ("pins that the repair is NOT yet applied") is the one thing
  here that is out of date, and it is out of date in the good direction. I also
  drove the counter-case the test does not cover: a second **decided** receipt
  on a settled operation is refused and latches `reconcile_state='conflict'`
  (`p2_double_decided.py`), with the reservation untouched
  (`consumed 10, reserved 0` before and after). The one-decided-receipt
  invariant N-43 rests on holds.

---

## Negative results (things I tried that did not reproduce)

Recording these because the ledger's own N-28 and N-44 both record a symptom
that turned out to be something else, and a reviewer's negative is evidence.

1. **A real supervisor kill does not produce the N-201 window.**
   `/tmp/r1/p5_kill_replay.py` SIGKILLs the launcher's process group
   mid-`dispatch`, then reports the run directory. The result file is written
   by the *parent* immediately after `proc.communicate()` returns, and the
   `.gen`/`.spawns`/`.pid` markers are written before and immediately after
   `Popen` (`launcher_local.py:215-259`). Killing cannot remove them:
   `prove_never_sent` correctly returns `False` and
   `redispatch_after_reset` correctly returns `refused-never-sent-proof`,
   twice in a row. **The N-201 window needs the run directory's bookkeeping to
   disappear, not a process to die.** That is a materially weaker claim than
   "a crash causes a replay", and N-201 is written to say so.
2. **The production cancellation path is sound.**
   `broker.confirm_cancel` (`team.py:1033`, `broker.py:893-901`) reaches the
   releasing branch only when `_structured_never_sent_proof` returns non-None,
   and returns `None` whenever the launcher declines. Measured
   (`/tmp/r1/p9_team_cancel.py`, `/tmp/r1/p10_settle_superseded.py`):
   `cancellation retained unresolved exposure`, `reserved 111 -> 111`,
   reservation left `uncertain`. **No refund through
   `_settle_superseded`.** The gap is `steward.release_reservation`
   (`steward.py:66`), which is a thin wrapper over the same store function and
   takes the proof from its caller.
3. **The store's spent-currency arithmetic is not reachable by a lie.**
   `receipt_actual_cost` (`store.py:1597-1642`) refuses a nonzero `actual_cost`
   against `billed: False`, against a non-canonical `charge_scale`, and against
   usage whose `charge_units` disagrees with the explicit cost;
   `_settle_amount` (`store.py:565-592`) refuses `actual > amount`. There is
   no path I found that settles a reservation for less than it should by
   mis-stating the receipt.
4. **A second decided receipt on a settled operation is refused**, and the
   N-30 `additional_observation` branch does not reach `_settle_amount`
   (verified by the reservation being byte-identical before and after).
5. **The counted study ceiling holds on the live dispatch path** (p1: 3
   admitted under a ceiling of 3, fourth refused with no exposure spent).
6. **`admit_study_call` is no longer dead** — N-02's recheck says it has no
   caller; `experiments/ad01/e3_ladder.py:326` calls it. The row's *status*
   (REPAIRED) is right and its "no caller anywhere" is now stale. Flagged, not
   contradicted: the row's own text already scopes the claim to the mechanism
   that is dead (`authority.py:230`), and the live enforcement is
   `_prepare_operation`, which I confirmed.

---

## What I could not test, and why

* **A full-suite run.** The coordination and environment constraints (N-46,
  N-83) make one meaningless on this host, and this lane was given a read-only
  contract-challenger brief. I ran the authority/recovery files that do not
  need a shared box, on per-run derived databases:
  `tests/test_r01_recovery.py tests/test_r01_authority.py
  tests/test_r02_authority.py tests/test_authority_recovery_hardening.py
  tests/test_s09_controls.py tests/test_s09_multi_receipt.py
  tests/test_store_authority_invariants.py` → **65 passed, 77 skipped**;
  `tests/test_broker_review.py tests/test_invd1_dispatch.py
  tests/test_broker_route_recovery.py tests/test_r01c_redispatch.py
  tests/test_s09_n56_resolution.py tests/test_ec02_review_recovery.py
  tests/test_invc2_recovery.py tests/test_s09_receipt_readback.py` →
  **1 failed, 48 passed, 7 skipped** (the failure is N-202, measured 4/4).
  The skips are the suite's own; I did not investigate them.
* **A real N-36 seed recovery, the E4 live arm, and any 1:1 E2/E3 numbers.**
  All need a live gateway, and N-53 records the standing constraint.
* **Whether the N-202 extra construction call is a budget breach.** The
  campaign's own cap is not exceeded (2 calls against a cap of 60), so the
  answer at the campaign level is no. Whether a *frozen* cap sheet for a real
  study would treat a lost response as a second dispatch is a design question
  I did not answer, because `WORKER-STAGE-09-PARALLEL-EXPANSION.md:89` puts
  the cap sheet in the researcher's hands.
* **Whether `e3_ladder`'s raw `urlopen` has actually been executed against a
  credential.** The lane editing it is mid-flight in the working tree; I read
  the code and did not run it.

---

## Reproduction index

Every script is under `/tmp/r1/` and creates and drops its own database. The
token in each is fixed so a rerun is reproducible; each `disposable_db` call
creates a fresh suffixed name and drops it on exit.

| script | finding |
|---|---|
| `p1_ceiling.py` | N-204 — counted ceiling enforced live, declared-only ceiling skipped |
| `p2_double_decided.py` | N-30 — a second decided receipt is refused and latches conflict |
| `p5_kill_replay.py` | negative result 1 — a real kill does not produce the window |
| `p8_release_real_work.py` | N-200 — `store.release_reservation` with a forged proof |
| `p9_team_cancel.py`, `p10_settle_superseded.py` | negative result 2 — the production cancel path is sound |
| `p11_steward_release.py` | N-200 — the same through `steward.release_reservation` |
| `p12_honest_crash.py` | N-201 — a side effect executed twice through the production redispatch |
| `p14_repair_leak.py` | N-202 — the store after a staged kill and a resume |
| `p15_strand_cost.py` | N-202 — `verify_ledger` reports `match: true` with 111 stranded units |
| `p6_guard_ceiling.py` | N-203 — a store refusal burns a dispatch from the frozen ceiling |

`p3_forged_proof.py` and `p4_prod_replay.py` are earlier drafts of N-201 and
are superseded by `p12_honest_crash.py`, which is the one to read.
