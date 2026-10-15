# P05 independent review

GPT-6.1 Sol High independently reviewed integrated source
`7f59a90925513fbeae8cd9bb7cd16ec22b8d62ad`. Verdict is **PASS for the scoped
implementation**, with the R6 limitation below. The review used its own isolated
worktree, PostgreSQL 18 and actual bounded fixture/native children. It made no
production edits or live model calls.

## Findings and repairs

| Finding | Repaired behavior |
| --- | --- |
| R1. Cached deferrals ignored changed eligibility. | Restored catalogue bytes and released resource reservations permit a new choice. Expired deferred agendas stop. Identical deferrals add no choice or audit entry. This also holds after an acknowledged turn. |
| R2. Existing P01 configuration exceeded the opportunity envelope. | One compatibility predicate checks task, genome, roots, required lessons, exact method request, model, token ceiling and timeout before choice and dispatch. Exposure uses the existing compatible P01 bounds. Immutable configuration is not rewritten. |
| R3. Pair checking required an activated treatment. | A real all-pass fixture pair with identical choices and no feedback remains a valid null result. Database-local memory clocks do not change semantic lesson identity. |
| R4. Initial lesson support accepted zero tests or skipped tests. | Initial support requires typed positive test counts, success and zero failures, errors and skips. Invalid support counts refuse after the clean pair passes. |
| R5. A peer's acknowledgement crashed the original wake. | Reconciliation retains the captured choice. It returns that acknowledgement while preserving any newer pending flight, with one child for the original action. |

The maintained regressions are
[test_rsi_agenda_review.py](../tests/test_rsi_agenda_review.py) and
[test_rsi_agenda_pair.py](../tests/test_rsi_agenda_pair.py).

## Executed verification

The independent nine-file gate passed **51 tests, zero skips, in 390.77 seconds**.
It covered agenda, policy, recovery, integration, campaign, review and pair tests,
Codex claim tests and P04 capability integration. The session dropped both
disposable databases. Ruff and the whitespace check passed.

Independent public-path probes additionally reproduced restored-source recovery,
released-root recovery, deadline stop, peer completion and bound refusal. A private
native-bound assertion initially expected a different refusal explanation; the
observed zero-turn, zero-new-operation and zero-extra-CPU behavior was correct.
Its corrected reason assertion passed separately. These runs are not combined
into a larger passing suite count.

An offline probe first accepted the clean export, then rejected missing operations,
missing reservations, unknown usage changed to zero, zero-test support and skipped
support. A clean timeout export remained unscored and pending with unknown usage.

The coordinator's separate integrated gate passed **65 tests, zero skips, in
377.72 seconds**, on the same source. It additionally covered the investigation
state tests. Neither gate is a whole-repository or CI result.

## Remaining boundary

R6 is a minor return limitation. If source bytes disappear immediately after
choice commitment, that call can raise `FileNotFoundError`. The flight survives
with zero dispatched children; a later absent-source wake returns pending, and
restoring the bytes acknowledges the same flight with one child. Callers must
retry that exceptional interleaving. No broad filesystem exception handler was
added.

These fixtures qualify execution, selection, evidence and recovery. They prove
neither live acquisition, task advantage, transfer, learner improvement nor
hostile containment. The initial lesson is explicitly authored from a scripted
pristine example. The bounded live study and final CI are recorded separately in
[the project ledger](../reports/PROJECT-LEDGER.md).
