# Investigation Learning 02 live handback assessment

Reviewed `codex/implementation-investigation-learning-02` at `4c709722076e94cbfc7af80de14cfdcc6cf51349`. This is a source and committed-evidence review. It does not rerun the live gateway, PostgreSQL suite or worker's reported tests.

## Accepted conclusion

The frozen E0 attempt reached a broker-routed construction operation and returned no text. `reports/evidence/invl02-live/e0-run.json` records four timeout attempts for one construction operation; the diagnostic records show a 60-second timeout and two HTTP 502 responses after about 180 seconds, on Responses and Chat routes. Discovery and earlier smoke responses distinguish this from a universal authentication failure. The evidence supports **route or upstream serving failure during this attempt**. It does not isolate the provider's internal cause, measure model competence or establish a learning null. Stopping E1/E2 under the frozen preflight was correct.

The worker's “seven calls” means four construction network attempts plus three separate diagnostic probes. `scripts/invl02_live.py::recompute` counts one construction operation from the E0 run. These are different quantities; the latter is not an independent recomputation of all seven dispatches. Keep attempt, operation and probe counts separate.

## Material gaps before a future E1/E2 run

**IL02-R1: The live path does not exercise the new investigation owner.** `scripts/invl02_live.py:191-226` calls `trajectory.run_campaign` with fixed task IDs and an authored `_apparatus_record` consumer. Its E1/E2 path at lines 378-443 does the same. The new `frontier` and `improve_channel` modules are not invoked by this driver. A live response from this path could demonstrate construction and operational use, but it could not establish system-selected investigation or inherited improvement behavior. Before a new prospective run, connect the durable frontier and actual executable improvement entry through the public child/effect path. Show an observation-dependent choice and a second improvement round after restart. Keep authored controls labeled.

**IL02-R2: The proposed P1/P2 treatment is confounded.** In `scripts/invl02_live.py:394-436`, P1 runs first. The `history` passed into P2 is built from P1's predictor digest and score. The model prompt in `boolean_live_round` receives this cross-arm result, while P1 receives an empty list. That is prior treatment outcome exposure, not the intended permitted development history. P0 is run only as a software control; its competent rule learner is not evaluated on the same Boolean instances. Even with working inference, these records could not identify the benefit of experience over a competent fixed learner. Build P1 and P2 from separate matched snapshots and the same development task history, withholding that history only from P1. Run P0 on the same held-out tasks and count all acquisitions.

**IL02-R3: The new live recompute is narrower than the frozen comparison verifier.** `scripts/invl02_live.py:488-529` checks the freeze digest, the run's matching digest, a count derived from run labels, and observed nonzero cost fields. It does not call `experiments/ad01/offline_recompute.py::verify_bundle` or independently derive task quality, candidate identity, arm availability and full resource accounting. Its passing result is valid only for those narrow E0 checks. For E1/E2, export the bundle required by the M4 verifier and run that verifier offline. Preserve the declared measurement limits for provider usage and billed cost.

These findings do not change the E0 transport outcome or require rerunning it immediately. Route recovery should trigger a short response-byte preflight, then completion of R1-R3 before a new frozen comparative run. A different free model would be a new protocol and should not be relabeled as the Nemotron treatment.

## Next decision

Treat Stage 9E as **mechanism parts built; connected general learning comparison not yet qualified**. The next engineering batch is R1-R3 plus a route-health preflight, not a broad bug sweep. If the pinned free route remains unavailable, preserve the transport result and stop that live study. If it recovers, run a new frozen E0 and then E1/E2 only after the three gates pass. E3 remains contingent on a genuinely acquired eligible revised improver.
