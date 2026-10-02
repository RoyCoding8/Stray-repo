# R02-EXEC R02-006/011/012 execution, containment and gateway repairs — task report

- Base: `d7b46aa1c6f85e273103689134f7d0f36c65aad1` (branch `codex/r02-exec` start).
- Tip: `ebab960`
- Worktree: `/tmp/asv2-r02-r02-exec` only.
- Findings: `reviews/REVIEW-02.md` R02-006 (P1), R02-011 gateway side (P1),
  R02-012 gateway side (P2). Coordinator contracts C1, C2, C4 consumed read-only.
- Containment bound: this host has no docker daemon (`docker: not found`) and no
  runsc, so every container assertion below runs against an injected executable
  docker shim plus a PATH-provided runsc stub and is labeled as such. Real
  containment/isolation is NOT established here.

## Modified paths (owned only)

- `src/settlement/exec_profile.py`: `build_gvisor_argv` threads the configured
  docker binary into the spawn (previously hardcoded `docker` for `run` while
  stop/inspect used the parameter) and emits `scratch_bytes` as
  `--storage-opt size=<bytes>` plus `-v host:container:ro|rw` mounts;
  `docker_stop` returns success instead of swallowing it; new
  `terminate_verified` (stop, kill on still-running, final inspect must read
  exactly stopped); `docker_container_running` reports unknown (`None`) on
  nonzero inspect exit instead of claiming stopped; `run_gvisor` and
  `run_local_process` drain pipes through concurrent bounded pump threads that
  keep the first `max_output_bytes` per stream (communicate path kept only for
  doubles without pipes); `run_gvisor` spawns a detached stdlib-only
  supervisor (`start_new_session`, absolute `sys.executable`) that enforces
  stop then kill at the admitted timeout, reaped on the normal path.
- `src/settlement/launcher_runsc.py`: `dispatch` consumes
  `op.dispatch_generation` read-only with a `.gen` claim record
  (stale `superseded-generation`, newer-arrives-mid-flight `superseded-claim`,
  no spawn on any refusal); records `.supervise.json` (container, operation,
  deadline epoch, grace) before spawning and drops it once the result is
  stored; passes scratch/mounts into the container command; `stop` verifies the
  final state, preserves tracking and returns False on any unverified target;
  new `enforce_deadlines` recovery sweep over run-dir supervision state;
  new `stage_input` plus fixed `/work/inputs` (ro) `/work/outputs` (rw) mounts
  as the only artifact path for host-path programs (relpath validated, staged
  bytes capped by the scratch bound, no arbitrary host bind).
- `src/settlement/gateway_http.py`: `_decode_body` sets `billed=True` only from
  an explicit non-negative integer `usage.charge_units` (optional positive
  integer `usage.charge_scale`, default 1000); token-only usage decodes to
  `charge_units=0, billed=False`; malformed charge fields are PROTOCOL errors.
  `infer` runs open-plus-read in a worker thread joined on the absolute
  deadline (`min(request.deadline_ms, total)`), so slowly dribbling headers
  return TIMEOUT within budget; connect/write/pool timeouts are additionally
  capped by the remaining budget; cancellation still reports CANCELLED with
  external outcome unknown, distinct from retryable TIMEOUT.
- `tests/test_r02_exec.py` (new, 15 tests, shim-based, see bound above).

Untouched per assignment: `store.py`, `broker.py`, `run.py`, `evaluation.py`,
`capabilities.py`, `trials.py`, `experiment.py`, `experiments/`,
`launcher_local.py`, `gateway.py`, `common.py`, `db.py`, `config.py`,
`scripts/`, `reports/PLAN.md`, `reviews/probes/test_review_02.py` (read only).

## Checks with outcomes

- `tests/test_r02_exec.py`: 15 passed. Covers supervisor termination after
  SIGKILL of the waiting broker child (stop issued post-death by a foreign pid,
  termination inside the admitted bound, recovery sweep drops the state);
  100 MB flood through a 1 KiB cap with image peak (VmHWM, which unlike
  ru_maxrss resets on exec) far below the flood size; scratch flag present;
  stop uncertain on stop/kill/inspect failure with tracking preserved;
  kill fallback verified; stale/newer generation refusals without spawn;
  controlled staging/traversal refusal/mount contents; supervise sweep scope;
  billed True/False decode plus malformed-charge PROTOCOL error; header
  dribble TIMEOUT within budget; cancel distinct from timeout.
- Affected suites `test_r01_runsc.py test_s0_profile.py test_s0_gateway.py
  test_launchers.py test_broker_dispatch.py`: all pass (rerun after final edit).
- Full `tests/` excluding `tests/test_broker_dbos.py` (other worker's file):
  Deferred to integration full-suite run on the merged tip.
- `reviews/probes/test_review_02.py`: 8 passed, 1 failed, unedited.
  `test_slow_response_headers_outlive_total_deadline` now fails for the right
  reason: `result.kind == TIMEOUT` holds, elapsed is 0.20 s against the
  200 ms budget instead of outliving it past 0.8 s.
  `test_http_usage_without_billing_becomes_zero_actual_cost` still passes at
  this layer by construction: per C1 the gateway decodes unpriced 1500-token
  usage to `charge_units=0, billed=False`, so the doubled broker path still
  builds `actual_cost=0`. Turning that probe red needs the broker/store
  conservative-exposure change (unknown billing retained, not settled as
  zero), which lives outside these owned paths; flagged for the owning worker.

## Remaining limitations

- No real docker/runsc on this host: supervision, bounded I/O, scratch flag,
  mounts and stop verification are proven against a faithful CLI shim, not a
  real container runtime. A runsc host must rerun `test_r02_exec.py` plus a
  real kill-the-broker drill before any live use.
- `docker_container_running` can no longer distinguish "absent" from
  "unreachable" (both unknown); stop therefore reports uncertain until a
  positive stopped reading, which is the honest direction but keeps tracking
  on externally `docker rm`d names until inspected.
- Explicit priced-charge contract is exactly `usage.charge_units` (integer) plus
  optional `usage.charge_scale`; other provider billing shapes are not mapped
  and never invented.
- The leftover infer worker after a deadline abandon is bounded by the read
  timeout and daemonized; it holds one pooled connection until then.
