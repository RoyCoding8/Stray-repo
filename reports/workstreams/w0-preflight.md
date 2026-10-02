# W0 preflight: the apparatus, exercised for real

Revision `dfbd557`. Lane `w0-preflight`, worktree `.worktrees/w0-preflight`.

This lane owns the apparatus. It proves the real child execution path, artifact
binding, response capture, execution and receipt export, and offline
recomputation, or it says exactly where they do not hold. It does not discover
the route. No live model call was made; no credential was read, created or
printed.

## Environment, and why it changed

The worktree host is Windows (MINGW64, `uname -r` = `MINGW64_NT-10.0-26200`).
The apparatus is POSIX-shaped: `launcher_local` links `libc.so.6` through
`ctypes`, applies `RLIMIT_CPU` and `RLIMIT_AS` through `resource`, and calls
`os.setsid`. It cannot run on the Windows host. Running it there produced
`landlock unavailable: Could not find module 'libc.so.6'`, which is an
environment fact, not an apparatus verdict.

WSL2 Ubuntu (kernel `6.18.33.2-microsoft-standard-WSL2`) is present and was
used. It reports `landlock abi 7` and can set `no_new_privs`, and it has a live
PostgreSQL. A venv was built at `/root/w0venv` with the project dependencies
(`pydantic`, `httpx`, `psycopg[binary]`, `dbos`, `pytest`). A disposable
database `w0_preflight_apparatus` was created and migrated (18 migrations,
68 tables).

Every result below was produced in that environment, importing the worktree
source, confirmed by `settlement.__file__` resolving under
`.worktrees/w0-preflight/src`. A disposable database was used, never a live
one. The harness script is `w0run.sh`, uncommitted.

```
cd D:/AI/Agent-Society-v2/.worktrees/w0-preflight
wsl.exe -d Ubuntu -- bash ./w0run.sh _w0_stage1.py
```

## Stage table

| Stage | What was actually executed | Exact command | Observed outcome | Verdict |
|---|---|---|---|---|
| 1. Real child execution | `LocalLauncher.dispatch` with a real `BrokerOp`; 7 child programs written to disk and run as `python <file>`. The child printed its own rlimits. | `wsl.exe -d Ubuntu -- bash ./w0run.sh _w0_stage1.py` | Children launch. `setsid` applied, verified from inside the child (`sid_leader=true`). Wall deadline fires: `rc=-15 timed_out=True wall_ms=1507` at `timeout_ms=1500`. Output cap binds: `truncated=True` at 4096 bytes. **But `cpu_seconds` and `memory_bytes` are NOT applied** (see blocker 1). | **BROKEN (partially)** |
| 1b. Limit enforcement isolated | Same probe through `exec_profile.run_local_process` and through `LocalLauncher.dispatch`, side by side | `... _w0_stage1b.py` | `run_local_process(cpu=7, as=256MB)` → child reports `RLIMIT_CPU=[7,7]`, `RLIMIT_AS=[268435456,…]`. `LocalLauncher.dispatch` with the identical values → child reports `[-1,-1]`. A CPU-bounded spin child under `dispatch` ran the full 30s wall budget and returned `rc=-15`; the same child under `run_local_process` died at 2132ms with `rc=-24` (SIGXCPU). | **Defect isolated** |
| 2. Artifact binding | Own candidate bytes: `core.py` (STEP role) and `adapter.py`, different lengths, staged, published, recorded as a composition | `... _w0_stage2.py` | Roles resolve to different files. `core` digest `c9af1ba9…`, `adapter` digest `b1c60936…`. They differ, and each matches its own bytes. The design property "STEP and ENTRY each match their own bytes; their digests need not equal" holds. | **VERIFIED** |
| 2b. Tamper detection | Four self-authored tampers against the real `representation.check_composition` | `... _w0_stage2b.py` | T1 file-content swap → `digest mismatch`. T2 manifest role swap → `digest mismatch`. T3 consistent swap under its own digest → accepted, and correctly so: it is a different artifact, and the honest composition still verifies. T4 one-byte edit → `digest mismatch`. Honest composition verified after every tamper. | **VERIFIED** |
| 3. Response capture | Real `trajectory.run_campaign` end to end; the response text is the local double's authored bytes | `... _w0_final345.py` | 7 real children produced `*.result.json` under `.ad01-runs/`, all `outcome=success parse=typed-json`. The retained program bytes and their digest travel with the receipt (`source_digest`, `input_digest`, `driver_digest`, `result_digest`, `raw_payload_digest`). | **VERIFIED — FAKE provider** |
| 4. Execution + receipt export | `records.export_campaign` then `records.write_export` | `... _w0_final345.py` | Export written, 181369 bytes. It carries the policy source (292 bytes) and its digest, the artifact block (`abi`, `applicability`, `dependencies`, `entry`, `instruments`, `kind`, `origin`, `parent_digest`, `source_digest`), per-arm quality and resources, 4 use records with `executed_source_digest`, 12 operations, 6 transitions, identities and freeze. Enough to recompute: inputs, program bytes plus digest, outputs, resource usage, grading inputs. | **VERIFIED** |
| 5. Offline recomputation | Fresh process, reads only the export file. Run twice: once normally, once with `/var/run/postgresql` physically renamed away | `... _w0_final345.py` | Both runs returned `status=pass, problem_count=0` with identical recomputed accounting. `s09_verify.py` contains zero database references. The verdict is recomputable from the export alone. | **VERIFIED** |
| 6. Gateway probe | Real `HttpGatewayAdapter.from_settings(Settings.from_env())` | `... _w0_stage6.py` | `SETTLEMENT_GATEWAY_ENDPOINT`, `SETTLEMENT_GATEWAY_KEY`, `SETTLEMENT_GATEWAY_API`, `SETTLEMENT_DSN` all NOT SET. `check_discovery`, `check_auth`, `infer` each return `GatewayError(kind='transport', 'gateway endpoint is not configured')`. | **BLOCKED — external** |
| 7. Failure-mode discrimination | Real `HttpGatewayAdapter` against a local fault-injecting server, plus real child execution and real `check_composition` | `... _w0_stage7a.py`, `_w0_stage7c.py` | All five modes separable. Three carry a defect, detailed below. | **VERIFIED with 2 defects** |

## Failure-mode discrimination

How the system currently distinguishes each, with the evidence that separates
them. "Durable" means the distinction survives into the stored receipt, which
is what a later campaign reads, rather than existing only as a Python type at
the adapter boundary.

| Mode | Discriminating field | Proven | How |
|---|---|---|---|
| (a) route refusal | `GatewayErrorKind.AUTH` / `RATE_LIMIT`; `GatewayRouteError.response_metadata` for a contract mismatch. Durable as `error_kind` + `route_error` | Yes | 401 → `auth`, `response_received=true`, `response_status=401`, digest set. 429 → `rate_limit`, retryable. 404 → `transport` (**defect 3**). Contract mismatch on a 200 → `protocol` + `route_error=response_metadata`. Durable receipt for 401: `error_kind='auth'`, `response_class='lost-response'`. |
| (b) transport loss | `GatewayErrorKind.TRANSPORT` / `TIMEOUT`. Durable as `error_kind` | Yes | Real connection-refused to a closed port → `transport`, `[Errno 111]`, retryable, `response_received=false`. Real read timeout against a socket that accepts and never answers → `timeout`, `total attempt deadline exceeded`. Durable receipt: `error_kind='transport'`, `response_class='lost-response'`. |
| (c) empty content | Durable `response_class='empty-response'` | Yes, with a defect | Chat/completions with `content: ""` returns a **`ModelResponse` with `text=""`, not an error** (defect 2). The broker still catches it: durable receipt `outcome='failure'`, `error='gateway returned no response text'`, `text=''`, `response_digest=e3b0c442…` (the sha256 of the empty string), `response_class='empty-response'`. Distinct from (a) and (b) at every layer. |
| (d) invalid program | `MethodExecutionError` with a distinct token, raised before any child runs | Yes | `verify_step_source` on non-Python → `refused: unparseable-python`. Valid Python with no `STEP` → `refused: missing-entry-function`. `validate_step_result` on a malformed return → `policy step must return {action, state}`. `check_composition` on altered bytes → `binding invalid: digest mismatch`. Four distinct strings for four distinct causes. |
| (e) poor task result | The program runs, produces a receipt, and the **evaluator** grades it. Not a construction failure | Yes | A valid `STEP` requesting a nonexistent method was accepted, executed, and returned a full evidence receipt with `outcome=success` and the returned action. Downstream, the campaign's arms separated cleanly: candidate `quality={tasks:2, failed:0, reduced:2, preserved:2}` against incumbent `quality={tasks:2, failed:2, reduced:0, preserved:0}` (defect 4). |

**No two of the five modes are conflated.** Each has its own observable field
and its own string, at the layer where it should appear. That is the single
most useful result in this preflight: a large campaign's failures can be
attributed.

## Verdict per stage

**Proven working.**

- Real child execution, launch, `setsid`, wall deadline, output cap, typed-JSON
  result interpretation.
- Artifact binding. Content-addressed, role-resolved, tamper-detected, and
  robust: a consistent swap is correctly treated as a different artifact
  rather than a tamper, and the honest composition keeps verifying.
- Response capture, receipt export, and offline recomputation. The verdict was
  recomputed from the export file alone with the database socket directory
  physically removed, and was byte-identical to the run with the database
  present.
- Failure-mode discrimination for all five modes.

**Broken.**

- **Resource limits are declared but not applied by the child launcher.** This
  is a real defect, not a configuration gap. Details below.

**Blocked on an external dependency.**

- Stage 6, and any live response capture. The dependency is exactly this:
  `SETTLEMENT_GATEWAY_ENDPOINT` and `SETTLEMENT_GATEWAY_KEY` are unset in this
  environment, and no `.env` exists in the worktree or the repo root. Until
  those are set for a verified free route, no live call is possible. The
  apparatus for it is built and exercised; the fault-injecting server proves
  the adapter path end to end over real HTTP.

## The two decision-relevant blockers

### 1. `LocalLauncher.dispatch` silently drops `cpu_seconds` and `memory_bytes`

`src/settlement/launcher_local.py:709-711` builds the dict passed to
`_child_setup`:

```python
confinement = {"read_deny": list(payload.get("read_deny") or []),
               "read_allow": list(payload.get("read_allow") or []),
               "cwd": child_cwd}
```

`_child_setup` (line 794) reads `payload.get("cpu_seconds")` and
`payload.get("memory_bytes")` (lines 798-799). Neither key is ever in
`confinement`, so both reads return `None` and no `setrlimit` call is made.
The dispatch payload accepts both keys at line 1394 of
`experiments/ad01/method_exec.py` and they are stored on the durable
operation.

Measured, not inferred. The child reports its own rlimits:

- `run_local_process(cpu_seconds=7, memory_bytes=256MB)` → `RLIMIT_CPU=[7,7]`,
  `RLIMIT_AS=[268435456, 268435456]`. Applied.
- `LocalLauncher.dispatch` with identical values → `RLIMIT_CPU=[-1,-1]`,
  `RLIMIT_AS=[-1,-1]`. Not applied.

Enforcement consequence: a CPU-bound policy step declared at
`cpu_seconds=STEP_CPU_SECONDS` (10s, `policy_step.STEP_CPU_SECONDS`) runs
unbounded on CPU. A spin child declared at 2s ran the full 30s wall budget and
came back `rc=-15` from the wall kill, not `rc=-24` (SIGXCPU) from the CPU
limit. The wall deadline still bounds it, so this is not unbounded execution,
but the CPU and memory ceilings a campaign would budget against are not the
ceilings in force. The receipts record a limit that was never applied.

**What must be repaired.** Add both keys to the `confinement` dict:

```python
confinement = {"read_deny": list(payload.get("read_deny") or []),
               "read_allow": list(payload.get("read_allow") or []),
               "cwd": child_cwd,
               "cpu_seconds": payload.get("cpu_seconds"),
               "memory_bytes": payload.get("memory_bytes")}
```

Then re-run `_w0_confirm.py` and require `CPU LIMIT APPLIED = True` for a
declared `cpu_seconds`. Until that assertion passes, a large campaign's
resource accounting is recording intent, not enforcement.

### 2. `PR_SET_NO_NEW_PRIVS` is the wrong constant, disabling Landlock confinement

`src/settlement/launcher_local.py:81` sets `_PR_SET_NO_NEW_PRIVS = 1`. In
`linux/prctl.h`, `PR_SET_NO_NEW_PRIVS` is **38**; 1 is `PR_SET_PDEATHSIG`. The
module's own `_PR_GET_NO_NEW_PRIVS = 39` is correct, so the read-back check
that was written specifically to catch a silently dropped prctl reads a flag
that was never set.

Measured in the same WSL environment:

```
prctl(1, 1, ...)   [module value] -> 0  nnp now 0
prctl(38, 1, ...)  [correct]     -> 0  nnp now 1
```

Consequence: `probe_landlock()` reports unavailable in an environment that can
do Landlock, so any dispatch declaring `read_deny` is refused with
`read-boundary-unavailable`. The failure is safe (it refuses rather than runs
unbounded), but every confinement-gated dispatch fails on a host that could
have provided it, and the refusal reason will read as a missing kernel
capability when the capability is present. This is the same class of defect the
module's docstring says it exists to prevent.

**What must be repaired.** Change the constant to 38, then confirm
`probe_landlock()` reports `available=True` in WSL, then run one dispatch with
`read_deny` set and verify the child cannot read the denied path.

## Two further defects found, not blockers for a launch

- **Empty content is a success at the adapter, a failure at the broker.** On
  chat/completions, `content: ""` returns a `ModelResponse` with `text=""`
  (`_decode_body`, `gateway_http.py:978`). The responses API treats empty
  output as `protocol` error. The asymmetry is real. The broker then catches
  it and stores `outcome='failure'`, `response_class='empty-response'`, and the
  sha256 of the empty string, so the mode stays attributable. The gap is that
  `ModelResponse` with empty text and `ModelResponse` with a short real answer
  are the same type; only the broker distinguishes them.
- **A 404 from the provider is classified as transport loss.** `_STATUS_ERRORS`
  (`gateway_http.py:67`) maps 401, 403 and 429. Everything else falls through
  to `GatewayErrorKind.TRANSPORT` with `response_received=True`. So
  "model not available" is recorded as transport loss, with `response_status=404`
  present but no field saying the model was refused. A campaign reading
  `error_kind` alone would attribute a model-availability refusal to the
  network. `response_status` does separate it, so it is recoverable, but not
  by the obvious field.

## Limits of this preflight

- No live model call. Stage 3 and 6 are proven against a local double and a
  local fault-injecting server, both labelled. Nothing here validates live
  inference, a real route, or provider-side behaviour.
- Every child result reports `containment=False`. No gVisor, no docker, no
  `runsc` on this host. Nothing here validates containment, only bounded
  subprocess execution.
- One campaign, one arm pair, six boundaries. Enough to exercise every stage
  of the path, not enough to say anything about campaign-scale behaviour.
- The Landlock and rlimit findings are in the local-process profile. The
  gVisor profile was never available to test, so its enforcement is untested
  here, not cleared.

## Before a large campaign is safe

1. Fix the two blockers and add the assertions that hold them fixed. A
   regression test that a declared `cpu_seconds` actually reaches the child's
   `RLIMIT_CPU` is the missing guard; `_w0_confirm.py` is that test.
2. Decide whether a 404 should be its own `error_kind`. If a large campaign
   will run against a model whose availability is uncertain, leaving it as
   `transport` means availability refusals are counted as network failures.
3. Configure `SETTLEMENT_GATEWAY_ENDPOINT` and `SETTLEMENT_GATEWAY_KEY` for a
   verified free route, then re-run stage 6 and one live capture before any
   multi-arm work.
4. Only then scale. Stages 2, 3, 4, 5 and 7 are proven and do not need redoing.

## Throwaway files

Not committed, per the lane contract. All in
`D:/AI/Agent-Society-v2/.worktrees/w0-preflight/`:

`w0run.sh` (WSL harness), `_w0_db.py`, `_w0_stage1.py`, `_w0_stage1b.py`,
`_w0_stage2.py`, `_w0_stage2b.py`, `_w0_final345.py`, `_w0_stage6.py`,
`_w0_stage7a.py`, `_w0_stage7b.py`, `_w0_stage7c.py`, `_w0_confirm.py`.

Artifacts outside Git: database `w0_preflight_apparatus` on the local WSL
PostgreSQL, exports under `/root/w0-artifacts/`, run directories under
`.ad01-runs/`.
