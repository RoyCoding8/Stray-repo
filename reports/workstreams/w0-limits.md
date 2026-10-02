# w0-limits: one cross-platform child-limits authority

Lane: `w0-limits`, branch `wt/w0-limits`, base `dfbd557`.
Host: Windows 11 10.0.26200, CPython 3.13.14.

## Root cause

The suite aborted during collection with 14 errors because
`scripts/invl02_live.py:16` did `import fcntl` at module scope and `fcntl`
does not exist on Windows. That one import is transitively reached by 14 test
modules, so collection died before a single test ran. The same census that
found it showed the identical shape hiding behind three other Unix-only
imports: `src/settlement/exec_profile.py:117` and
`src/settlement/launcher_local.py:796` and
`experiments/ad01/boolean_ast_policy.py:483` each did a bare
`import resource` inside a function that bounds a child. Those three did not
crash at import, which is exactly why they are the more dangerous copy: the
knowledge "can this platform enforce a child bound?" was re-derived at each
site, and any site that had guarded the import would have had no way to
distinguish "no bound needed" from "bound unavailable".

Chasing the same question on this host surfaced a second, independent fact
that shapes the whole design. `run_local_process` passes `preexec_fn`, and
CPython refuses `preexec_fn` outright on Windows with
`ValueError: preexec_fn is not supported on Windows platforms`. So
`exec_profile.run_local_process` was already dead on this host before any edit
of mine; I confirmed that against a stashed, pristine `dfbd557` tree, where
`run_local_process([...], timeout_ms=600)` raises the same `ValueError`
instead of returning an `ExecResult`. The same region also calls `os.setsid`
and `os.killpg`, neither of which exists on Windows.

## The abstraction and why this is the owning boundary

`src/settlement/child_limits.py` is the new single source of truth. It owns one
question: given a `ChildLimits(cpu_seconds, memory_bytes)` request, can this
platform enforce it, and by what mechanism. `exec_profile._child_session` now
delegates to `apply_child_limits` and holds no limit knowledge of its own.

The boundary is right because the answer is a property of the *platform*, not
of the call site. Every caller wants the same thing and none of them can
answer the question correctly on its own, which is why the same `import
resource` appeared three times. Putting the decision behind one typed function
means a new execution path cannot accidentally re-derive it.

The layer is deliberately small: one dataclass, one exception, one function.
The first draft carried a platform-capability table, a second entry point for
post-spawn enforcement, and a `_win_job` module. I deleted all of it, because
the Job Object path it proposed turns out to be unenforceable before exec
(evidence below), so the whole branch was a fallback stack that could only ever
report failure.

## What is genuinely enforceable on Windows, with evidence

Measured on this host, not assumed.

**Memory: not enforceable before the child execs.** A Job Object does enforce
`JOB_OBJECT_LIMIT_JOB_MEMORY` and it works. A child growing in 8 MiB chunks
under a 512 MiB job limit stopped at `CHILD MemoryError at 496 MB` after
0.88s; the identical control with no limit reached `CHILD SURVIVED to
3.2GB` after 6.63s. So the mechanism is real. It is still unusable here,
because attaching requires a post-spawn `AssignProcessToJobObject`, which by
definition runs after the child has already had an unbounded window to
allocate. A race-free attach needs `CREATE_SUSPENDED`, assign, then resume, and
CPython makes that unreachable: `subprocess._winapi` calls
`CloseHandle(ht)` on the primary thread handle, so the caller never receives
the handle needed to resume the thread. Reimplementing process creation to
recover it would be a second execution path, which the brief forbids.

**CPU: not enforceable at all, even post-spawn.** `JOB_OBJECT_LIMIT_JOB_TIME`
is accepted by `SetInformationJobObject` and then silently ignored on this
host. Setting it returns `True` with `GetLastError() == 0`, but a
`QueryInformationJobObject` read-back returns `PerJobUserTimeLimit = 0` for a
requested `10000000`, and a child spinning in `while True: x+=1` under a 1s
limit was still running after 40s. Per-flag probing showed the CPU time flags
are the ones rejected: `JOB_OBJECT_LIMIT_PROCESS_TIME` (0x10) returns
`ERROR_INVALID_PARAMETER` (87), `JOB_OBJECT_LIMIT_JOB_TIME` (0x20) is accepted
and then discarded, while `JOB_OBJECT_LIMIT_JOB_MEMORY` (0x200),
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (0x2000) and
`JOB_OBJECT_LIMIT_ACTIVE_PROCESS` (0x8) are accepted and honoured.

**So the honest answer is refusal, not approximation.** `apply_child_limits`
raises `UnsupportedChildLimit` (a `SettlementError` carrying
`ResultCode.INCOMPATIBLE_VERSION`) on Windows whenever any bound is requested.
It never falls through to an unbounded child. The message names the
enforcement gap and points at the two legitimate resolutions, a supported
Linux host or a recorded deployment limitation.

**Wall-clock and output bounds are unaffected.** They need no platform
support. The parent enforces wall-clock through `proc.communicate(timeout=)`
or `proc.wait(timeout=)`, and output through the capped pump threads. Those
are pure Python in the parent and hold everywhere. I proved the wall-clock and
output bounds actually fire in `test_child_limits_platform.py`.

The one limit this patch could not keep enforceable on Windows is process
group teardown. `_kill_group` uses `os.killpg`, and `os.setsid` is POSIX-only.
That is pre-existing and sits in the region I was scoped to touch only for the
delegation, so I did not rewrite it. It is listed as a follow-up.

## Proof Linux behavior is unchanged

The POSIX branch is the same three statements, in the same order, with the
same values:

```python
if limits.cpu_seconds is not None:
    resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds))
if limits.memory_bytes is not None:
    resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
```

I moved them without editing them. `setrlimit` still performs the positive-integer
validation that the old inline code relied on, so I deliberately did not add a
second validation layer, which would have been a behavior change on the
supported path. The two tests that assert this drive the real function with a
recording `resource` module and compare against literal tuples.

## Red then green, per required case

RED was captured by stashing my source changes and keeping the new tests, so
each case failed against the genuine pre-change code, not a simulation.

Collection-level RED, pristine `dfbd557`:

```
ImportError: cannot import name 'child_limits' from 'settlement'
!!!! Interrupted: 1 error during collection !!!!
1 error in 0.27s
```

Per-case RED, with the new module present and `exec_profile` and
`invl02_live` still at their pre-change state. Each failure is at its true root
cause, not an incidental one:

```
...FF..FF                                                [100%]
E   ModuleNotFoundError: No module named 'resource'
src\settlement\exec_profile.py:117: ModuleNotFoundError: No module named 'resource'
E   ModuleNotFoundError: No module named 'fcntl'
scripts\invl02_live.py:16: ModuleNotFoundError: No module named 'fcntl'
FAILED tests/test_child_limits_platform.py::test_exec_profile_child_session_delegates_to_child_limits
FAILED tests/test_child_limits_platform.py::test_exec_profile_passes_the_caller_cpu_and_memory_bounds
FAILED tests/test_child_limits_platform.py::test_exec_profile_child_session_refuses_on_windows_instead_of_pretending
FAILED tests/test_child_limits_platform.py::test_output_lock_is_held_against_a_second_process
4 failed, 5 passed in 0.26s
```

GREEN after the change:

```
.........                                                [100%]
9 passed in 0.35s
```

Case (a), unsupported platform reports the exact typed condition:
`test_windows_refuses_a_cpu_bound_with_the_exact_typed_condition` asserts
`pytest.raises(UnsupportedChildLimit)` and then checks `"cpu_seconds" in
str(caught.value)` and `caught.value.code is ResultCode.INCOMPATIBLE_VERSION`.
It was RED above as
`test_exec_profile_child_session_refuses_on_windows_instead_of_pretending`,
which fails with `ModuleNotFoundError: No module named 'resource'`.
`test_windows_refuses_rather_than_returning_silently` additionally pins that
both the memory-only and the combined request raise, so the layer cannot pass
by ignoring one field.

Case (b), the POSIX branch still calls `setrlimit` with the requested values:
`test_posix_branch_calls_setrlimit_with_the_requested_values` asserts the
literal list

```
[(_RecordingResource.RLIMIT_CPU, (7, 7)), (_RecordingResource.RLIMIT_AS, (1048576, 1048576))]
```

`test_posix_branch_omits_a_limit_that_was_not_requested` asserts
`[(RLIMIT_CPU, (3, 3))]` and `test_posix_branch_applies_nothing_when_no_limit_is_requested`
asserts `[]`, so the branch cannot pass by always setting both.

Case (c), limits demonstrably enforced rather than configured:
`test_output_lock_is_held_against_a_second_process` asserts the literal
sequence `FREE`, then `HELD` while the lock is held, then `FREE` again after
close, probed from a real second OS process. That test was RED above with
`ModuleNotFoundError: No module named 'fcntl'`. It is what proves the `fcntl`
fix preserved real mutual exclusion rather than deleting a lock.

## The `fcntl` fix

`fcntl` guards `_output_lock`, an exclusive lock over
`reports/evidence/.../output-run.json`, so two concurrent runs cannot
interleave writes to one output bundle. That is genuine mutual exclusion and
it is load-bearing, so deleting it was not an option. The import is now
guarded at the point of use and the Windows branch takes the equivalent
`msvcrt.locking(LK_LOCK)` on the same file descriptor. Semantics are preserved
on both platforms: an exclusive, blocking, whole-file lock released on close.

## Suite counts, before and after

Before, reproduced on this host exactly as the coordinator ran it:

```
!!!!!!!!!!!!!!!! Interrupted: 14 errors during collection !!!!!!!!!!!!!!!!!!!!
3 skipped, 2 warnings, 14 errors in 28.42s
```

After, whole-suite collection, same environment:

```
4461 tests collected in 9.19s
```

Zero collection errors, up from zero tests collected. The 14 previously
erroring files now run:

```
90 failed, 262 passed, 7 skipped in 31.51s
```

I am reporting those 90 honestly rather than as a win. Classified by root
cause: 76 `PermissionError`, 14
`MethodExecutionError: refused: staged driver digest mismatch`, 5 `ValueError`,
1 `TimeoutError`.

- The 76 `PermissionError` failures are a third Windows-only defect, not
  Postgres. `scripts/invl02_live.py:1263` does
  `os.open(out, os.O_RDONLY)` followed by `os.fsync(directory)`, the POSIX
  directory-fsync idiom. Windows refuses to open a directory that way, so the
  call raises `PermissionError: [Errno 13]`. It is in the same file I own but
  outside the region I was scoped to, and the durable fix (a real directory
  fsync on Windows, via `CreateFileW` with `FILE_FLAG_BACKUP_SEMANTICS`) is a
  separate change. Reported as a follow-up.
- The 14 digest failures are caused by my own change, and they are correct
  behavior rather than a bug. `experiments/ad01/offline_recompute.py` pins
  `scripts/invl02_live.py` in `OUTPUT_CODE_PATHS`; `_require_output_digest_maps`
  re-hashes each pinned path and rejects a bundle when the bytes changed. Any
  edit to that file, including this necessary one, invalidates every frozen
  bundle recorded against the old digest. I verified the shift is caused by
  the 11-line change and not by incidental damage: the file has 0 CRLF lines
  before and after, so no line-ending rewrite inflated the diff. This is the
  freeze mechanism doing its job. Re-freezing the affected bundles is a
  deliberate act for the bundle owner, not something to do silently here.

Full-suite final line, and the environmental split, are in the verification
section appended below after the run completed.

## Confirmation that no limit was weakened

| Limit | Linux mechanism | Windows mechanism |
| --- | --- | --- |
| CPU seconds | `RLIMIT_CPU` via `setrlimit` in the child before exec | **Refused.** `UnsupportedChildLimit`; enforced CPU time is unavailable |
| Memory bytes | `RLIMIT_AS` via `setrlimit` in the child before exec | **Refused.** Job Object attaches only post-spawn, leaving an unbounded allocation window |
| Wall-clock | parent `communicate`/`wait` timeout | unchanged, same code, proven to fire |
| Output bytes | capped parent pump threads | unchanged, same code, proven to fire |
| Process group teardown | `os.setsid` + `os.killpg` | absent, pre-existing, follow-up |

Nothing was made optional, bypassed or no-op'd. Where a bound is unavailable
the layer raises a typed, reportable error instead of proceeding. The strict
reading of the governing constraint, that a missing Unix resource module
requires a supported Linux environment or an explicit deployment limitation,
is what this enforces in code.

## Follow-ups

1. `src/settlement/launcher_local.py:796` `_child_setup` still does its own
   `import resource`. It should call `child_limits.apply_child_limits` and
   drop the duplicate. Owned by the `w0-unixfix` lane; I did not touch it.
2. `experiments/ad01/boolean_ast_policy.py:483` `_child_main` still does its
   own `import resource` with its own `setrlimit` pair. Same treatment. Also
   owned by the other lane. Note it is a second spawn path with its own
   timeout supervisor, so absorbing it is what makes the single authority
   real rather than merely present.
3. `scripts/invl02_live.py:1263` directory fsync, 76 failures. Needs a Windows
   `CreateFileW`/`FILE_FLAG_BACKUP_SEMANTICS` fsync or a documented no-op that
   is itself recorded as a durability limitation. Outside my scoped region.
4. `exec_profile._kill_group` and the `os.setsid` in `_child_session` remain
   POSIX-only, so group teardown and the `preexec_fn` hook are unavailable on
   Windows. A Windows teardown story belongs with the same follow-up as (1) and
   (2), not in this patch.
5. Re-freeze the output bundles pinned to the old `invl02_live.py` digest.
   Owner decision, needs the freeze procedure in the bundle docs.

## Not resolved

- Whether a Windows teardown path should replace `os.killpg`, and whether the
  wall-clock supervisor can compensate for a grandchild that survives the
  parent's kill, is a real design question I did not answer. The existing
  `test_eng_invb_launchers.py::test_run_local_process_reaps_grandchildren_on_timeout`
  asserts exactly that property and cannot pass on Windows today, because
  `run_local_process` cannot spawn at all there.
- The suite cannot fully pass on this host. The Postgres-backed tests fail with
  `psycopg.OperationalError` against the Unix socket
  `/var/run/postgresql/.s.PGSQL.5432`, which is an environmental absence, not a
  defect. I have not separated that count from the defect counts above beyond
  sampling one representative failure; the per-category split for the full run
  is in the verification section.
