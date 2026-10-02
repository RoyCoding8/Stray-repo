# ENG-INVB: dispatch / containment / gateway sweep

Base: `f478143`. Code tip: see "Tips" below (code commit, then report commit).
Branch: `codex/eng-invb`. Worktree: `/tmp/asv2-eng-invb`. DB: `settlement_enginvb`
(socket `host=/var/run/postgresql dbname=settlement_enginvb`), real PG + real subprocess.
No live inference anywhere (stub HTTP servers only). No credentials in this report.

## Tips

- Code commit: `af3df52a1056736533ff3ad35fc55758dda9efe6` (staged-only hunks
  listed under "Commit scope").
- Report commit: this commit (see tip SHA in reply).
- Identity verified `Nightjar` for author and committer; unchanged.

## Commit scope (hunk-split)

A second worker is concurrently editing `launcher_local.py`, `exec_profile.py`
and `gateway_http.py` in this same worktree (untracked
`tests/test_eng_invb_dispatch.py`, plus uncommitted hunks in those three files).
Per the one-writer-per-directory rule I staged ONLY my hunks and left every
foreign hunk and the foreign test file uncommitted and untouched:

- `src/settlement/broker.py`: whole-file diff is mine (3 hunks).
- `src/settlement/exec_profile.py`: my 6 hunks (signal import, `_child_session`,
  `_kill_group`, `grace_ms`, preexec, 2 call sites); sibling `proc_starttime` /
  supervisor-script hunk excluded.
- `src/settlement/gateway_http.py`: my wait-slice hunk only; sibling
  `from_settings(api=...)` / `SETTLEMENT_GATEWAY_API` hunk excluded.
- `src/settlement/launcher_local.py`: my pid-unlink hunk only; sibling supervise /
  cwd-default / `_check_relpath` hunks excluded.
- `tests/test_launchers.py`: whole-file diff is mine (pgrep rewrite).
- New `tests/test_eng_invb_{broker,launchers,gateway}.py`: mine.
- NOT committed: `tests/test_eng_invb_dispatch.py` (foreign), all sibling hunks.

## Coverage matrix (one row per owned file)

| File | Invariants / boundaries | Techniques | Evidence | Findings | Limits | Disposition |
|---|---|---|---|---|---|---|
| `src/settlement/broker.py` | prepare->dispatching->sent/observed/unresolved single-send; ownership/grant fencing at point of effect; gateway failures become unknown receipts, never resends | A journey dispatch/reconcile/cancel; B null/edge payloads; C crash-before/after-send, stale generation; D grant/cap to effect; F red-first regressions on real PG | `test_eng_invb_broker.py` (3 new, real PG), `test_broker_dispatch.py`, `test_adv_broker.py` | ENG-INVB-01, 02, 06 | store.py internals not owned; gateway doubles except stub HTTP | fixed + verified |
| `src/settlement/gateway_http.py` | chat + responses decode paths; deadline bound; cancel observable; no secret in errors | A both API shapes end to end vs stub; B malformed/usage edge bodies (existing suite); C cancel-during-blocked race; D auth header handling | `test_eng_invb_gateway.py` (hang stub + cancel race), `test_s0_gateway.py` | ENG-INVB-03, 10 (to ENG-ACCT) | worker thread lingers to read-timeout after cancel return; daemon-bounded | fixed + verified; billing filed out |
| `src/settlement/boot.py` | honest dependency grades; no secret in diagnostics | D secret-in-error probe ×4 DSN shapes; G operator readability | inline probes (timeout/refused/DNS/peer-auth/malformed) | ENG-INVB-08 rebutted | no change | assessed, no defect |
| `src/settlement/exec_profile.py` | scrubbed env; rlimits; group kill on timeout; probe-gated gvisor, never silent fallback | C timeout vs grandchild (wall-clock proof); D env scrub + mounts; F red-first | `test_eng_invb_launchers.py::test_run_local_process_reaps_grandchildren_on_timeout` | ENG-INVB-04 | setsid-escapers still escape (documented, local != containment) | fixed + verified |
| `src/settlement/launcher_local.py` | op-derived identity; typed-JSON-only worker bytes; group kill; claim/generation fencing | C stale-generation interleavings; D cwd/traversal/env; F pgrep-flake forensics | scratch repro + `test_eng_invb_launchers.py`, rewritten `test_launchers.py` group-kill test | ENG-INVB-05, 07, 09 (sibling-fixed), 11 (note) | same-uid worker can still `../` (not containment); symlink plants readable (same uid) | fixed + verified; 09 left to sibling tip |
| `src/settlement/launcher_runsc.py` | probe-gated, raises (never falls back); op-derived names; verified stop | C claim-twin trace vs local; D shim liveness/stop probe; H dead-path check | twin-trace scratch, docker-shim probe, `test_r01_runsc.py`, `test_launchers.py` runsc tests | ENG-INVB-12 (observation, no change) | no runsc/docker daemon on host: shim only, never claimed as containment | assessed, verified vs shim |

Cross-module journeys assessed: sandbox dispatch (broker->launcher->receipt->settle),
model dispatch (broker->gateway->usage receipt), cancel (broker->launchers+gateway),
boot grading, runsc-unavailable refusal (raises `IncompatibleVersion`, broker maps to
`incompatible-profile`, no local fallback anywhere in owned files).

## Findings ledger

- ENG-INVB-01 (P2, fixed): `broker._send_model` let a raising gateway escape
  `dispatch_operation` (HttpGatewayAdapter re-raises worker-thread errors). Now
  contained as unknown-receipt/unresolved with exposure retained, matching the
  lost-response branch. Adversarial note: swallows programming errors too, by
  design (interface promises return-values, not raises); kill-path unchanged.
- ENG-INVB-02 (P2, fixed): `broker.request_cancel` stopped launchers but never
  called `gateway.cancel`, so model-inference cancel never reached the adapter.
  Added optional `gateway` param (default None; `api.py` caller unaffected),
  best-effort with `gateway_cancelled` recorded. api.py passing the gateway is
  outside my paths (coordinator/API lane).
- ENG-INVB-03 (P2, fixed): `HttpGatewayAdapter.infer` waited the full deadline
  even after `cancel`; the waiter now slices at 50ms and returns CANCELLED
  promptly (proven vs hang stub: ~1s vs 30s deadline). Worker thread still lingers
  to the bounded read timeout (daemon); cancel wins over a late response,
  consistent with the existing post-completion check.
- ENG-INVB-04 (P2, fixed): `exec_profile.run_local_process` had no setsid and
  killed only the direct child; grandchildren survived AND the timeout call
  blocked 60s on an 800ms budget (pipe EOF held by grandchildren; measured).
  Now setsid + TERM/grace/KILL group kill (`grace_ms` additive param).
  Callers (`boot`, `artifacts.tar`, `dispatch`) unaffected in the common path.
- ENG-INVB-05 (P2, fixed): `LocalLauncher.dispatch` stale-generation refusal left
  its own empty pid claim behind, so the live generation was refused forever as
  `prior-send-recorded` with `prior_send True` and no result (reproduced). Now
  unlinks its own claim on that path. The claim-failed branch is untouched
  (file is someone else's, possibly live). Runsc twin already unlinked; verified
  by trace, no change.
- ENG-INVB-06 (P3, fixed): `ensure_operation(retries=None)` raised uncaught
  `TypeError`; non-int/negative retries now return INVALID_INPUT. All repo
  callers pass valid ints.
- ENG-INVB-07 (P3, fixed in test): `test_timeout_kills_whole_process_group` used
  single-shot `pgrep -f "sleep 30"`. Forensics: `pgrep -f` matches any cmdline
  containing the pattern (my own probe matched itself and SIGKILLed itself),
  cross-test `sleep 30` matches, and zombies match during async reap. Rewrote to
  pid-file observation + killpg assertion + 5s poll; no pgrep. Not a rename.
- ENG-INVB-08 (rebutted): `boot.check_database` error with password-bearing DSN
  across timeout/refused/DNS/peer-auth/malformed shapes: libpq never echoes the
  password. No change.
- ENG-INVB-09 (P2 confirmed; fixed in working tree by sibling, EXCLUDED from my
  tip): `LocalLauncher.read_output` had no relpath check (runsc twin had
  `_check_relpath`; `stage_input` had an inline check). Current callers pass
  constants/operator data (latent, not live). Sibling's uncommitted hunk adds the
  check; their `test_read_output_refuses_traversal` covers it. I verified by
  read-only run; coordinator to integrate their tip.
- ENG-INVB-10 (cross-boundary -> ENG-ACCT, not implemented): billing semantics.
  Responses path always `billed=False` with no `charge_units`/`charge_scale`
  parsing, while chat strictly enforces canonical milli-scale and bills; unbilled
  chat usage settles `actual_cost None`. Filed here as report only.
- ENG-INVB-11 (P4 note, no change): broker validator rejects `cwd` keys while
  `LocalLauncher` honors `payload["cwd"]` — unreachable via the public path
  (fail-closed); launcher docstring overclaims. Kept as-is; sibling is changing
  the cwd default in their tip (their tests), which is their design decision.
- ENG-INVB-12 (P3 observation, no change): with docker down, stale `.container`
  track files make `RunscLauncher.live_ids`/`is_live` report alive and `stop`
  report False (shim-proven). Direction is safe (exposure retained, reconcile
  defers) but repair wedges on `still-running` until the daemon returns.
  Flipping to assume-dead risks duplicate sends; coordinator decision.
- ENG-INVB-13 (P4, no change): `HttpGatewayAdapter._decode` (httpx.Response
  variant) has no callers; `_decode_body` serves all paths. Left to avoid churn
  against the sibling's in-flight gateway edits.
- ENG-SOLV: nothing to file (no solver-contract need found in owned files).

## Checks (all real PG + real subprocess unless noted)

- New regressions: `test_eng_invb_broker.py test_eng_invb_launchers.py
  test_eng_invb_gateway.py tests/test_launchers.py` — 14 passed (were 5 red + 1
  false-green pre-fix; the false-green grandchild test took 60.7s pre-fix).
- Neighboring: `test_broker_dispatch.py test_broker_prepare.py test_broker_dbos.py
  test_broker_review.py test_adv_broker.py test_r01c_redispatch.py
  test_reconcile_reset.py test_s0_gateway.py test_s0_boot.py test_s0_profile.py
  test_r01_runsc.py test_adv_isolation.py` — 116 passed on the standalone tip
  (detached worktree `/tmp/verify-invb`, DB `settlement_enginvb_verify`).
- More neighbors: `test_r01_deadline_ui.py test_r02_exec.py test_settle_actual.py
  test_s3_experiment.py` — 43 passed; `test_broker_dbos.py` — 3 passed with
  URL-form DSN (keyword DSN breaks that file's `_swap_db` derivation;
  pre-existing fixture limitation, unrelated to this lane).
- Base neighbors pre-change: `test_launchers.py test_broker_dispatch.py
  test_adv_isolation.py` 30 passed.
- `probe_gvisor` on this host: unavailable (no runsc/docker) — shim only, honest.

## Limits and collisions

- No runsc/docker daemon: runsc paths verified against a failing-docker shim
  (ENG-INVB-12) and existing shim tests only. Never claimed as containment.
- No live inference: stub HTTP servers only.
- Shared-worktree collision: sibling's uncommitted hunks and
  `tests/test_eng_invb_dispatch.py` remain in `/tmp/asv2-eng-invb` untouched;
  my push contains only the hunks above (verified via `git diff --cached`).
  `api.py` cancel path still does not pass a gateway (needs API-lane change).
- Ruff: not a configured gate (153 pre-existing errors on base); my files add none
  (unused-import cleanup done).
