# Stage 8 closeout: executable method contract

Branch `codex/implementation-stage-08-close-stage-09-start`.
Live evidence in `evidence_inv01_live/` is unchanged and stays
no-retention. This slice closes the engineering defect only; learning
efficacy, hostile containment and other operational qualification stay
unproven.

## Defect

`experiments/ad01/packet.py` advertised bare `reduce_graph(...)` and
`reduce_software(...)`. The `method_exec.py` child supplied only the
`reducers` module namespace. All four archived live validation
executions failed with `NameError: name 'reduce_graph' is not defined`.
The archived run held ten construction calls: four completed
responses, three output-limit responses, three timeout/unknown
receipts.

## Fixes

A1 (`1590979`): `method_exec.py` owns versioned table
`child_contract()` (`ad01-child-v1`) naming both helpers plus
`oracle.query` with signatures, return shapes, origin labels and the
`reducers.*` binding. The child renders wrappers and bindings from the
table; `packet.py` builds `public_operations` from the same table with
names unchanged. Legacy `reducers.*` sources still run.

A2 test migration (`da76b30`): the rerun test that pinned the
`NameError` now asserts the fixed behavior (all four archived
candidates execute with no `NameError`). Stronger assertion against
the corrected contract, not a weakening.

## Archived-candidate diagnostics (unedited bytes, doubles only)

| candidate | digest prefix | old failure | new outcome | next failure |
|---|---|---|---|---|
| w0-I l1-init | d8fa9e5e | NameError reduce_graph | executed | none |
| w0-I l2-repair | 92f06e0a | NameError reduce_graph | executed | none |
| w1-I l1-repair | 92f06e0a | NameError reduce_graph | executed | none |
| w1-I l2-init | e8416ad4 | NameError reduce_graph | executed | none |

Three unique sources; the w1-I repair is byte-identical to w0-I.
Already-seen tasks only, so this is not transfer evidence.

Other attempts: 3 timeout/unknown exposure, 3 output truncation (all
three fail downstream parse with a prose head), 4 execution failures
(now past the namespace fault), 0 terminal parse failures,
0 no-useful-improvement. All ten operations carry max_output_tokens
2048 and deadline_ms 300000; all three length receipts show exactly
2048 output tokens; all four repair prompts carry the true prior
failure. Timestamping of unknown receipts stays a reporting boundary.

## Closeout proof

`tests/test_s89a3_closeout.py` (3 tests): full public
acquire/check/retain/use path with doubles only at the model boundary
(selects and executes byte-identical bytes, fresh-process CLI
reproduces it); honest rejection path (garbage raises
`ConstructionFailed` after exactly 4 bounded calls, broken candidate
rejected with reason, empty repertoire falls back to incumbent);
authored controls labeled separately from model bytes. Usefulness
gated on existing criteria (`preserved` plus strictly smaller).

## Verification boundaries

Doubles sit at the model seam only; no live inference validates the
fix. Full suite result is recorded in `reports/PLAN.md`. The original
live study remains no-retention: zero repertoire members, 24 of 24
incumbent uses. Requests to a future lane: distinct truncated-parse
stage, unknown-receipt timestamps, rerun of diagnostics after each
executor change.

## Optional live request

One bounded `construct_method` call on a disposable database against a
human-authorized continuation grant, to confirm a repaired candidate
passes validation through the corrected path. No standing
authorization exists; the spent stage 8 grant is not reused.

## Stage disposition

Stage 8 engineering closes at this scope: advertised operations are
executable, archived failures are diagnosed, the closeout path is
proven. Learning advantage and final implementation remain unproven
and uncompleted. Stage 9 starts with the consolidation package in
`docs/design/STAGE-09-ARCHITECTURE.md`.
