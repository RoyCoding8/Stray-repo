# Workstream inv-learning02-harden: frontier replay accounting

Owner: harden lane. Worktree `.worktrees/invl02-harden`, branch
`wt/invl02-harden`, base `4545a51`. Owned paths only: this report,
`experiments/ad01/frontier.py`, `tests/test_frontier_harden.py`.

## Invariant

Every served query is charged exactly once. Every replay verdict names
its support class. Classes `recorded-replay`, `unsupported`,
`prediction` are disjoint. Any identity or input mismatch is
`unsupported`.

## Root cause

`FrontierStore.replay` served the stored outcome free. No authority
check. No `used` increment. Duplicate query cost zero. Exhausted budget
still served. Verdict carried no cached-serve reason. The outcomes dict
was the free duplicate-query cache.

## Fix

`experiments/ad01/frontier.py` `replay` now charges the cached serve
explicitly. Non-dict or non-comparable key returns `unsupported` with
identity mismatch reason. Miss returns `unsupported` without charge.
Hit calls `spend({"queries": 1})` then returns `recorded-replay` with
reason `cached-serve: exact identity and input match` and
`queries_charged: 1`. Exhausted budget raises `Refused` through `spend`
instead of serving free. `predict` untouched. No new abstraction.

## Failing-first

New `tests/test_frontier_harden.py` ran red before the fix: duplicate
charged twice failed with `queries_used 0 == 0 + 1`, cached-serve
reason failed with missing `reason`, exhausted refused failed with
`DID NOT RAISE`. Near-miss, exact hit, prediction separation passed
before and after as guards. After the fix all 6 pass.

## Gates

All with `PYTHONPATH=$PWD:$PWD/src:$PWD/experiments
.venv/bin/python -m pytest` in the worktree after `uv sync --extra test`:

- `tests/test_frontier_harden.py`: 6 passed.
- `tests/test_m2_frontier_inherit.py`: 12 passed.
- `tests/test_r123_gates.py`: 18 passed.
- Combined `test_frontier_harden.py test_m2_frontier_inherit.py
  test_r123_gates.py`: 36 passed.

Base `4545a51 Handback: R1 R2 R3 closed with live E0 bound and E12
incomplete`. Tip SHA recorded in the commit line.

## Gaps

- `RuleSession.query` still serves in-memory duplicates free. Frontier
  accounting charges per replay serve. Instrument-level duplicate
  billing stays out of scope by ownership.
- `record_outcome` accepts any JSON key shape. Replay hardens the read
  path only. Write-path schema validation not added.
- No serve ledger beyond `used` counters. Charged serves are visible in
  authority, not as separate rows.

## Hygiene

Deterministic only. No live network. No live calls. No database used,
so no `invl02_harden` object to drop. No scratch files committed.
No secrets in Git or output.
