# R02-011/012 billing completion — task report

- Base: `d9f03da` (integration tip after W-D + W-B merges).
- Tip: `3f312c7` on branch `codex/r02-billing`, merged to integration.
- Worktree: `/tmp/asv2-r02-r02-bill` (temp, deleted after merge).

## Finding

R02-011 has four layers; three were already implemented and one was
untested. The two review probes encoded the pre-fix behavior and failed
on the merged tip for the right reason, so both were migrated.

- Gateway decode (`gateway_http._decode_body`): token-only usage decodes
  to `charge_units=0, billed=False` (W-B, `ebab960`/`8f85692`).
- Broker mapping (`broker._send_model`): unbilled usage proposes
  `actual_cost=None` instead of zero (W-A, `cc83dca`).
- Store settlement (`store._settle_amount`): success with `actual=None`
  consumes the full reservation; unknown outcomes retain exposure in
  `uncertain` state (W-A, `cc83dca`).
- CLI grant cap (`experiments/run_live_abc._bind_grant_cap`): grant binds
  to a fresh allocation and refuses when the cap cannot cover it (W-D,
  `4d2979b`).

## Owned changes (this slice only)

- `tests/test_settle_actual.py`: new
  `test_success_without_actual_cost_consumes_full_reservation` pins the
  conservative branch (success receipt with no `actual_cost` consumes the
  whole reservation; unknown billing is never settled as free).
- `reviews/probes/test_review_02.py`:
  `test_http_usage_without_billing_becomes_zero_actual_cost` renamed to
  `test_http_usage_without_billing_retains_unknown_cost`, asserting
  `billed is False` and `actual_cost is None`;
  `test_slow_response_headers_outlive_total_deadline` renamed to
  `test_slow_response_headers_respect_total_deadline`, asserting TIMEOUT
  with `elapsed < 0.8` against the 200 ms budget (observed 0.20 s).

## Checks with outcomes

- Both migrated probes pass on the merged tip (previously failed for the
  right reason: `assert None == 0`, `assert 0.20 > 0.8`).
- New settlement test passes; full verification deferred to the
  integration suite run on the merged tip.

## Remaining limitations

- No live paid-inference check: unknown-cost handling is proven with
  scripted doubles, never against a real provider bill.
- No monetary-ceiling claim: token estimates stay labeled estimates; the
  grant cap is a unit cap, not a currency conversion.
