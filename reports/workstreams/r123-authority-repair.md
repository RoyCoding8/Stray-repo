# R123: the live investigation's authority, and why a third thread was the wrong fix

Status: repair committed as `f8036ae8` on `worktree-agent-ae6466976f1dd211c`,
base `529ae21c`. Nothing pushed. Two assertions are **CI-must-confirm** and are
named in *What CI must confirm*.

## The reported cause, confirmed

The report was right about the mechanism. It was wrong about the layer.

Both `tests/test_r123_gates.py` tests named in the assignment reach
`driver._run_frontier_investigation`, which opens an owned store and reaches
`drive_improve_round` with
`authority = _study_authority(dsn, allocation_id)`
(`scripts/invl02_live.py:2082`). `_study_authority` returns `None` when
`allocation_id` is falsy (`scripts/invl02_live.py:1867-1868`), and
`drive_improve_round` refuses an owned store entered with `authority=None`
(`experiments/ad01/improve_channel.py:2328-2332`).

**Reproduced by running it, not by reading it.** Built an owned store the way
production builds one, then drove a round both ways:

```
B) drive_improve_round(owned, authority=None)   <- what the 3 call sites do
   Refused
   refusal string present: True
   msg: refused: an owned store executes under the authority its investigation
        authorizes, not under a disposable one

C) drive_improve_round(owned, authority={dsn,allocation_id})   <- the repair
   ConnectionTimeout
   got PAST the owned-store refusal: True
```

Case C is the load-bearing half. It fails *later*, on a socket, which is what
shows the refusal was cleared rather than merely re-worded.

## The premise the assignment asked me to attack

The instruction was explicit: two fixture-level patches had already landed
(`baa14031` for `test_evidence_integrity.py`, `0d66125f` for
`test_invl02_causality.py`), and a third in the same shape would be evidence
the wrong layer was being fixed. So I censused before I edited.

**Census of every call site of `_run_frontier_investigation`** (AST walk over
tests, scripts, experiments, src). 9 sites:

| site | passed `allocation_id`? |
|---|---|
| `scripts/invl02_live.py` x4 (`run_e0` x2, `run_e12` x2) | yes, all 4 |
| `tests/test_invl02_causality.py:401`, `:1096` | yes, both |
| `tests/test_r123_gates.py:253`, `:297`, `:303` | **no, all 3** |

Six of nine call sites were already correct. The two prior lanes did not each
patch a shared site — they patched callers of a shared site correctly, in
different files. **The premise that three fixes shared one defective site is
false.** There was one defective *signature*, reached by three call sites in
one file, and six callers were quietly relying on its being optional.

What made `allocation_id=None` a defect rather than a supported mode:

- `dsn` is a **required** keyword-only parameter.
- `ensure_live_store(dsn=dsn, investigation_id=...)` is called with that
  non-`None` `dsn`, and `_live_identity` returns a `StoreIdentity` whenever
  `dsn is not None` (`experiments/ad01/live_construct.py:1062-1077`).

So the store this function drives is **always** owned. There was no input for
which omitting `allocation_id` succeeded. The default described a mode that
did not exist.

## The repair, and why it is in this layer

Two changes, one in each direction.

**1. `scripts/invl02_live.py` — `allocation_id` becomes required.**

```python
def _run_frontier_investigation(store_path, freeze: dict, label: str, *,
                                dsn: str, allocation_id: str,
                                guard=None, model: str = "",
                                history: list | None = None) -> dict:
```

Measured, not asserted:

```
omitting allocation_id now fails at the call:
   TypeError: _run_frontier_investigation() missing 1 required keyword-only
              argument: 'allocation_id'
```

**Why here and not in the fixture.** This is the same defect `_run_source` was
already closed against. Its `authority` and `operation_id` carry **no default**
(`improve_channel.py:1782-1798`), and
`tests/test_inv_a8_improve_authority.py:136-167` asserts that structurally, by
AST, so a new call site fails the test rather than only a change to a known
one. `_run_frontier_investigation` sat one hop further out with the identical
hole. A required parameter makes the omission a `TypeError` at the call site,
which is where a caller reads it, instead of a `Refused` three frames deeper.

The alternative — three more fixture threads — was rejected on evidence. It
would have left the signature claiming a supported mode that cannot work, so
the fourth caller to omit `allocation_id` would fail the same way.

**2. `tests/test_r123_gates.py` — a `live_allocation` fixture, on the same `dsn`.**

The allocation is bought by the caller, not derived inside the investigation,
for the reason `run_e0` buys it in the driver (`scripts/invl02_live.py:2344`)
and for the reason `WORKER-PROMPT.md:158` gives: *keep one campaign authority*.
A derivation inside `_run_frontier_investigation` would be a second authority
for one leg.

It is minted on **this file's own `dsn` fixture**, which is the same dsn the
store's `StoreIdentity` names. An allocation on another database leaves the
round's receipts settling where the investigation cannot reach them, which is
the condition `6f0baeb` exists to prevent.

**Ceilings are derived, not chosen.**

| constant | value | derived from |
|---|---|---|
| `R123_SANDBOX_EXPOSURE` | 91 | `broker.exposure_schedule(SANDBOX_EXEC, {"timeout_ms": method_exec.STEP_TIMEOUT_MS})[0]`, evaluated at import. Verified equal to the cap sheet's `10 + 80 + 1`. |
| `R123_STEPS_PER_INVESTIGATION` | 6 | `drive_improve_round` bounds a round at `for step in range(3)` (`improve_channel.py:2375`); `_run_frontier_investigation` runs exactly two rounds. |
| `R123_INVESTIGATIONS` | 3 | AST census of the call sites: one in `test_r1_driver_routes_through_frontier`, two in `test_r1_live_improver_via_doubles`. |
| `R123_SANDBOX_CALLS` | 18 | `6 * 3` |
| `authorized` | 1638 | `18 * 91` |

The unit figure is exact rather than a first-of-several because `retries` is
pinned: `broker.ensure_operation` returns `INVALID_INPUT` for any `retries`
but zero (`src/settlement/broker.py:263-269`), so the `(retries + 1)`
multiplier in `_sandbox_exposure` is always 1.

**The `choose_next_work` calls are deliberately not counted.** They look like
child executions but are not: `choose_next_work` reaches `run_operate_step`
**without an authority** (`live_construct.py:1193-1211`), so those settle on
`_disposable_authority`'s own database, not on this allocation. The
`execute_chosen_work` probes are in-process `RuleSession.query` calls that
reach no executor at all. Counting them would over-buy the grant by 4 per
investigation and misdescribe where the receipts go.

`model_calls` is **not** declared. The one guard in this file is a
`_ScriptGateway` behind `LiveGuard`, so no operation is ever admitted on this
allocation for it, and declaring a ceiling for a currency nothing draws on
would price nothing. `sandbox_calls` **is** declared, because an undeclared
ceiling is not a zero ceiling: `_check_study_ceilings` returns early on empty
`ceilings`, so a grant omitting the name admits every child execution.

**Study root is per-test** (`unique("r123-live")`), because
`_study_operation_counts` walks the subtree under one `allocation_id` — a
shared root would price a sibling's executions against this test's ceiling and
make the pass depend on file order. It is also what `authorize_study` is
immutable per. Verified: two calls yield distinct roots.

## Interaction with `9e164b29` / `32bf4ba4`

Verified rather than assumed. `tests/test_r123_gates.py` contains **zero**
references to `S09ISO_TOKEN`, `run_representation_suite`, `subprocess`,
`pytest.main`, or `os.system` (grep count 0). The only files that reach
`run_representation_suite` are `experiments/ad01/s09_verdict.py` and
`tests/test_s09_verdict.py`, neither of which this test touches. The two
changes are disjoint. `test_s09_verdict.py` staying green on CI is unaffected
by this diff.

## What I could NOT run locally

No `SETTLEMENT_TEST_DSN` on this host, so **both target tests skip here**.
They are unverified. Specifically unverified:

1. `test_r1_driver_routes_through_frontier` — every assertion from
   `record["observation_dependent"] is True` down through
   `record["adopted"]["status"] == "activated-control"`.
2. `test_r1_live_improver_via_doubles` — both `acquisition["status"]` checks
   (`retained`, then `unavailable`) and `guard.dispatch_count == 1`.

Nothing was weakened or skipped to achieve a local green. The 2 skips are the
harness's own `SETTLEMENT_TEST_DSN is not configured`, identical before and
after.

## Verification I did run

Windows, `PYTHONPATH=src`, `S09ISO_DISABLE=1`.

| | before (clean tree, diff stashed) | after |
|---|---|---|
| `test_r123_gates.py` | 4 failed, 29 passed, 2 skipped | 4 failed, 29 passed, 2 skipped |
| + `test_invl02_causality.py`, + `test_a22_mission_identity.py` | 19 failed/errored | 19 failed/errored |

The baseline was measured by stashing **this diff** and re-running, then
diffing the two sorted failure sets: **identical**. So this change introduced
no new failure in the three files that exercise it. The 4 pre-existing
failures are `test_r1_observation_dependent_choice`,
`test_r1_second_round_after_restart`,
`test_r1_disconnect_frontier_changes_effect` and
`test_r1_disconnect_improvement_refused_or_changes`, all
`psycopg.OperationalError` on the socket. They are **not** mine and **not**
fixed here.

Collection is unchanged at **35 tests**. No test was deleted, renamed, or
marked skip.

Also verified: the module imports; `inspect.signature` reports
`allocation_id` as required; all 9 call sites pass it (**0** omit);
every line citation in the new docstrings was read back off the file.

## What CI must confirm

1. `tests/test_r123_gates.py::test_r1_driver_routes_through_frontier` — the
   full assertion set, on real PostgreSQL, under a real allocation.
2. `tests/test_r123_gates.py::test_r1_live_improver_via_doubles` — the
   acquisition is `retained` and the bad source is `unavailable`.
3. **The ceiling is correctly sized.** If `R123_SANDBOX_CALLS = 18` is short,
   the failure is a `Refused` on the reservation, not a red assertion. 18 is
   derived from the `range(3)` round bound; a deeper protocol would change it.
4. The allocation resolves on the fixture's `dsn`, so the round's receipts
   settle where `StoreIdentity` points.
5. The 4 pre-existing socket failures still fail for their own reason and my
   fixture did not mask them.

## What this does not establish

- It does not verify a round now succeeds under real authority. That is
  CI's, with PostgreSQL.
- It does not fix the 4 pre-existing socket failures in this file.
- It does not address that `_control_triple`'s `choose_next_work` executions
  still settle on a **disposable** database (`live_construct.py:1193-1211`).
  That is a real seam — receipts for the arms whose actions are compared do not
  sit under the study allocation — and it is a separate defect in a file I do
  not own. Recorded here rather than fixed.