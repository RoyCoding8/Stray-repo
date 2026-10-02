# Investigation 01 completion re-verification

Independent re-review of `c519926ea6a976eb4766c4c5b671bb5f5c162c23` on
`codex/implementation-investigation-01-completion` against the design in
`docs/design/INVESTIGATION-01.md` and the completion criteria in
`WORKER-INVESTIGATION-01-COMPLETION.md`. Prior findings INV-R1..R5 (review at
`44f1f7c`) and INV-C1..C7 (review at stale tip `89c2eff`) are each re-decided
below from real runs on real Postgres with doubles only at the provider seam.
The reviewer invented cases N1, N2 and the M5 probes. Disposition: every prior
finding is closed. Two new findings are filed, one P2 and one P3 observation.
Live qualification remains unrun for lack of a grant, which is the only
remaining external dependency.

## Milestone verdicts

M1, integrated lifecycle: met. `DecisionConsumer` gates propose, admit,
bounded correction, continuation and stopping on the public trajectory for
both domains. Deciding run: `tests/test_invc1_lifecycle.py`, 8 passed on
`inv_rr_v2_c1`, including shared-consumer decisions on software plus graph,
disconnected-consumer refusal of both domains with zero gateway calls, and a
real CLI run across both domains.

M2, one authority: met. Construction subdivides from remaining parent study
authority and names the shortfall otherwise. Deciding runs:
`tests/test_invc2_authority.py`, 4 passed on `inv_rr_v2_c2` / `inv_rr_v2_c2b`
(exhaustion refusals, fresh-store missing authority with zero calls and zero
writes, children from remaining parent, independent ledger sums); real CLI
with no grant exits 2 with 0 operations, 0 receipts, 0 allocations on
`inv_rr_v2_b3`; grant 2560 admits the learner then rejects construction with
16384 needed and 2550 free and zero construction operations on `inv_rr_v2_exh`.

M3, feedback and recovery: met. Same-target correction carries the refusal
reason into the next actual learner prompt (op `-c1`, `PRIOR FAILURE` present,
retained, `inv_rr_v2_corr`). The correction limit survives a fresh-process
resume with zero new operations (N1, `inv_rr_v2_n1`). A real SIGKILL staged
mid-validation (dispatching, zero receipts, zero launcher files) resumes
identical to control with no repair ops (`inv_rr_v2_kill3`). A real SIGKILL
staged after the validation receipt but before publish resumes identical too
(`inv_rr_v2_killb`).

M4, executable interfaces: met. The construction prompt carries the
executor-owned envelope rule verbatim. Deciding runs: an independently written
single-scan method runs through the real child preserved 14 ops to 3, and the
bare-candidate form passes the gate but fails in the child with structured
`malformed-result-envelope`; `tests/test_invd3_envelope.py` 4 passed.

M5, trace, export, replay: met. A public run exports one transition per
boundary with packets, decisions, operations, receipts, identities and byte
digests. Deciding runs on my own export: exact-prefix `cli replay` supported
with the recorded result identities; hidden-future, new-code-bytes and
version-mismatch probes unsupported with empty results; the malformed probe
refused; `cli recompute` matches the run totals.

M6, runnable study: met on recording doubles. The `run_study` flow runs
calibration, freeze, matched I/R worlds, disposition, fresh-process use and
empty-repertoire incumbent use on `inv_rr_v2_study`: 6 trajectories, 24
protected use records, 6 empty-use records all incumbent, clean byte chains,
totals 39 model calls and 12 construction calls within caps, cap sheet
mechanically clean, and the entry's own `--recompute` exits 0 with matching
totals. Live inference did not run: endpoint, key and grant report missing by
presence only.

## Prior findings

INV-R1, shared path not public: closed. The consumer is the one gate on the
public boundary for both domains; the M1 deciding run stages replacement and
disconnection directly.

INV-R2, independent construction authority: closed. Subdivision from the
parent replaces per-episode minting; the M2 deciding runs refuse at each
exhaustion point instead of seeding.

INV-R3, correction and recovery unqualified: closed. Same-decision correction,
restart-persistent budget and both kill points are staged above on the public
path with doubles only at the provider seam.

INV-R4, implicit return contract: closed. Renderer, parser and executor agree
through the executor-owned rule, proven with independently written bytes.

INV-R5, caps and exports not executable: closed. The cap sheet derives from
runner bounds, the study budget and deadline enforce before effects, and the
pilot plus recompute run end to end on recordings.

INV-C1, mid-validation kill spends repair plus lineage: closed. The resume
reclaims the receipt-less dispatching op exactly once; my rerun resumes
identical with no repair ops.

INV-C2, construction ignores parent authority: closed and inverted. The same
shape now refuses with the parent shortfall named and zero construction
operations.

INV-C3, fresh database renews authority: closed. Unbound stores refuse before
any write; the renamed cross-database test asserts refusal with zero
allocations, zero operations and zero gateway calls, and my B3 run proves it
at the public entry.

INV-C4, undocumented ENTRY envelope: closed. The rule is rendered verbatim
and the child reports the documented structured error.

INV-C5, unbilled calls settle at estimate: closed. `tests/test_invd2_settle.py`
3 passed on `inv_rr_v2_d2`: a 2485-unit exposure with 5 plus 5 unbilled tokens
settles consumed 10, reserved 0; billed and unknown paths unchanged.

INV-C6, no correction in the next request: closed. The M3 deciding run shows
the reason inside the next real learner prompt.

INV-C7, tests asserting the opposite of their names: closed. The kill-resume
name now claims only completed-boundary replay without respend, the
cross-database name now claims refusal, both pass on my stores, and staged
kills carry the recovery proof in `test_invd1_dispatch.py` and my reruns.

## New findings

INV-N2, model-inflight kill is scored as a candidate rejection (P2). A SIGKILL
staged during the construction init model call (`dispatching`, zero receipts)
resumes with zero new gateway calls because receipt-less model ops never
resend. The boundary settles `rejected` for a transport miss, consumes a
development episode, and the killed op rests in `dispatching` with its
3244-unit reservation held and no release path. M3 holds at its two specified
points; this adjacent seam neither recovers nor retries with a distinct
attempt. Suggested fix: record interruptions as a distinct verdict from
candidate rejection and either retry the call under a new operation identity
or release the stranded reservation.

INV-N3, exports omit effective caps (P3 observation). A post-hoc export
rebuilt with different caps yields a different packet digest through the
remaining-budgets field only; with matching caps the digest reproduces the
run-time value exactly, and run identity is unaffected. Replay from any one
export stays self-consistent. Suggested fix: persist the run caps inside the
export document.

## Verification boundaries

Recording doubles sit at the provider seam only; validation and use run in the
real local child launcher. No live inference ran, so no learning benefit or
transfer is established. Hostile containment is unvalidated. Post-spawn kills
park for reconciliation and were not staged here. Cross-store double grants
are detectable by fingerprint but not prevented. The script entry refuses
stores whose DSN lacks the `inv_c3_` marker with exit 2 (observed); the pilot
above therefore replicates the entry flow on a designated-disposable `inv_rr`
store rather than invoking the guarded line.

## Remaining external dependency

To run live: provide `SETTLEMENT_GATEWAY_ENDPOINT`, the key behind
`SETTLEMENT_GATEWAY_KEY`, and a written grant naming the study root, model
id, effort level and the enforced cap sheet, then run the entry in
`reports/INVESTIGATION-01-COMPLETION.md` with a live model label.
