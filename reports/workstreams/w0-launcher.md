# w0-launcher workstream report

Lane: `w0-launcher`. Worktree `D:/AI/Agent-Society-v2/.worktrees/w0-launcher`, branch `wt/w0-launcher`, base `98c23c7`.

Owned scope touched: `src/settlement/launcher_local.py`, `tests/test_launcher_local_bounds.py` (new), this report. Nothing else was modified. No commit, merge, or push was made.

## Both defects reproduced before any change

Environment: Windows 11 host at `D:/AI/Agent-Society-v2/.venv/Scripts/python.exe` (CPython 3.13.14) for the Windows branches, and WSL2 Ubuntu (`Linux 6.18.33.2-microsoft-standard-WSL2`, CPython 3.14.4) for the POSIX branches. Import source was verified in both before every run.

```
$ PYTHONPATH="D:/AI/Agent-Society-v2/.worktrees/w0-launcher/src" \
    "D:/AI/Agent-Society-v2/.venv/Scripts/python.exe" -c "import settlement; print(settlement.__file__)"
D:\AI\Agent-Society-v2\.worktrees\w0-launcher\src\settlement\__init__.py
```

### Defect 1: declared bounds never reached the child

`dispatch` built the dict passed to `_child_setup` with only `read_deny`, `read_allow` and `cwd`. `_child_setup` read `cpu_seconds` and `memory_bytes` from that same dict and called `resource.setrlimit` for each, so neither key was ever present and `setrlimit` was never called on any platform.

Measured in WSL, comparing the same child through `exec_profile.run_local_process` and through `LocalLauncher.dispatch` with identical requested values:

```
os.name = posix
A run_local_process  child RLIMIT = {"cpu": [7, 7], "as": [67108864, 67108864]}
B LocalLauncher     child RLIMIT = {"stdout": "{\"cpu\": [-1, -1], \"as\": [-1, -1]}\n", "returncode": 0, "timed_out": false, "wall_ms": 53, "supervised": true}
C spin declared cpu_seconds=2 -> rc=-15 timed_out=True wall_ms=30045 (budget 30000)
   (SIGXCPU=-24 means the CPU bound fired; -15 means the wall kill did)
```

The child observed `[-1, -1]` where the reference path observed `[7, 7]`. The spinning child declared at 2 CPU seconds ran the full 30 second wall budget and was killed by the wall deadline. The wall deadline did bound it, so this was not unbounded execution, but the ceilings a campaign budgets against were not the ceilings in force.

### Defect 2: `PR_SET_NO_NEW_PRIVS` was set to the wrong constant

`_PR_SET_NO_NEW_PRIVS = 1` named `PR_SET_PDEATHSIG`. `PR_SET_NO_NEW_PRIVS` is 38. `_PR_GET_NO_NEW_PRIVS = 39` was already correct, so the module set one flag and read a different flag that had never been set. Measured in clean, separate WSL processes, each starting with the flag clear:

```
### A: what the module's constant sets
module constants : _PR_SET_NO_NEW_PRIVS = 1   _PR_GET_NO_NEW_PRIVS = 39
kernel truth     : PR_SET_PDEATHSIG=1  PR_SET_NO_NEW_PRIVS=38  PR_GET_NO_NEW_PRIVS=39
nnp at process start = 0
module sets prctl(1, 1) -> rc=0
nnp after            = 0

### B: what the real constant sets
module constants : _PR_SET_NO_NEW_PRIVS = 1   _PR_GET_NO_NEW_PRIVS = 39
kernel truth     : PR_SET_PDEATHSIG=1  PR_SET_NO_NEW_PRIVS=38  PR_GET_NO_NEW_PRIVS=39
nnp at process start = 0
real   sets prctl(38, 1) -> rc=0
nnp after            = 1
```

`prctl(1, 1)` returns 0 (success) and leaves `no_new_privs` at 0. `prctl(38, 1)` returns 0 and sets it to 1.

The end-to-end consequence on this WSL2 host, from a clean process, before the fix:

```
clean-process probe_landlock().available = False
reason: landlock unavailable: this process cannot set no_new_privs, which Landlock
        requires before it will restrict. The call reports success and leaves the
        flag clear, so confinement would be recorded without being applied.
```

and the dispatch it produced:

```
launcher landlock_available() = False
sent = False refused = read-boundary-unavailable: landlock unavailable: this process cannot set
  no_new_privs, which Landlock requires before it will restrict. ...
```

One correction to the preflight account, stated because it changes what the fix had to do. The wrong constant did not let an unconfined dispatch run. The module's own read-back caught it, `_no_new_privs_settable()` returned `False`, and the existing pre-spawn refusal fired. The damage was availability, not safety: every `read_deny` dispatch was refused on a host that could have confined it, and the refusal was misreported as a missing kernel capability. That is the read-back working, not failing, on a setter that was wrong.

## What changed and why it is the owning boundary

### `_PR_SET_NO_NEW_PRIVS` 1 to 38, and the child path routed through it

The child path in `_landlock_restrict` had the same bug in a bare literal, `libc.prctl(1, 1, 0, 0, 0)` with a comment claiming it was `PR_SET_NO_NEW_PRIVS`. It now calls the named constant and raises if the call fails, so the setter and the read-back can never drift apart again. One constant, two call sites, one meaning.

### The declared bounds are read into a typed shape and installed by the one authority

`dispatch` now builds the child payload with `"limits": _requested_limits(payload)`, which reads `cpu_seconds` and `memory_bytes` into a `settlement.child_limits.ChildLimits`. A missing or null key is no request rather than a zero.

`_child_setup` no longer imports `resource` at all. It calls `child_limits.apply_child_limits(payload["limits"])`, so the platform decision is made in the module that owns it, in the child, between fork and exec, and it raises `UnsupportedChildLimit` rather than degrading to an unbounded child. The deleted lines were a second `import resource` and a second copy of the same decision, which is what the governing constraint forbids.

### A pre-spawn refusal for limits, in the shape the read denial already uses

The task asked whether the limits need an equivalent to the Landlock refusal. They do. A requested ceiling the host cannot install would leave the child bounded only by the wall deadline, which is exactly the state Defect 1 produced, and it would be silent. The refusal reuses `_unwind_claim(paths, seen, prior_generation)` and the same reason shape, so a refusal releases the pid claim, restores the spawn count and the prior generation, and leaves the operation reclaimable. It never strands an operation that never ran.

### A third defect found while testing, and fixed

The first version of the refusal asked the authority whether the host could enforce the bound by calling `child_limits.apply_child_limits(limits)` in a `try`. That is wrong, and it corrupted the launcher. `apply_child_limits` both decides and enforces, and the refusal check runs in the parent, where `setrlimit` is permanent rather than scoped to a child. Measured:

```
  apply_child_limits cpu=None mem=536870912 (parent AS now (-1, -1))
b -> parent AS after = (536870912, 536870912)
c -> parent AS after = (536870912, 536870912)
```

A launcher that checked a 512MB bound had permanently lowered its own `RLIMIT_AS`, and every later child inherited that ceiling even when it asked for nothing:

```
  payload keys: ['argv', 'timeout_ms']
a -> 0 [-1, -1]
  payload keys: ['argv', 'memory_bytes', 'timeout_ms']
b -> 0 [536870912, 536870912]
  payload keys: ['argv', 'timeout_ms']
c -> 0 [536870912, 536870912]      <-- asked for nothing, inherited 512MB
```

This is exactly the "one platform decision in one place" failure the task warned about, in the other direction: a query that was an act. The refusal is now a question that installs nothing. After the change:

```
  payload keys: ['argv', 'timeout_ms']
a -> 0 [-1, -1]
  payload keys: ['argv', 'memory_bytes', 'timeout_ms']
b -> 0 [536870912, 536870912]
  payload keys: ['argv', 'timeout_ms']
c -> 0 [-1, -1]                   <-- no carry-over
```

The generalisation this sits on, for the record: a pre-spawn capability check must be side-effect free. Calling the enforcing function to ask the question is a defect even when the answer is right, because the question has an effect the caller did not ask for.

### `MemoryError` joined `OSError` in the spawn handler

`preexec_fn` runs in the forked child, so a memory ceiling low enough to starve that child's own address space raises `MemoryError` rather than reporting a limit, and `MemoryError` is not an `OSError`. Measured at 2MB: `dispatch` raised a raw `MemoryError` out of the caller's hands instead of returning a receipt. Pre-existing, in the handler my change made reachable. Now recorded as a `spawn_error` receipt like any other spawn failure.

## Red then green, per required case

All runs against the new file `tests/test_launcher_local_bounds.py`, 16 tests. `S09ISO_DISABLE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, and the three `SETTLEMENT_*DSN` variables unset.

**On base `98c23c7` (red), WSL:**

```
FAILED tests/test_launcher_local_bounds.py::test_requested_limits_carry_both_declared_values
FAILED tests/test_launcher_local_bounds.py::test_absent_bound_is_absent_rather_than_zero
FAILED tests/test_launcher_local_bounds.py::test_cpu_ceiling_stops_a_spinning_child_well_before_the_wall_budget
FAILED tests/test_launcher_local_bounds.py::test_memory_ceiling_actually_bounds_the_child
FAILED tests/test_launcher_local_bounds.py::test_a_memory_bound_below_the_interpreters_own_floor_fails_the_child
FAILED tests/test_launcher_local_bounds.py::test_a_bound_reaches_the_child_and_leaves_the_next_child_unbounded
FAILED tests/test_launcher_local_bounds.py::test_no_limit_requested_means_no_refusal_on_any_host
FAILED tests/test_launcher_local_bounds.py::test_no_new_privs_constant_is_pr_set_no_new_privs_not_pdeathsig
FAILED tests/test_launcher_local_bounds.py::test_the_read_back_confirms_the_flag_whose_setter_ran
FAILED tests/test_launcher_local_bounds.py::test_the_child_restrict_path_uses_the_named_constant
FAILED tests/test_launcher_local_bounds.py::test_a_child_dict_without_the_limits_key_never_yields_an_unbounded_child
11 failed, 2 passed, 3 skipped in 47.95s
```

**After the fix (green), WSL:**

```
..s...ss........                                                         [100%]
13 passed, 3 skipped in 4.48s
```

**On base `98c23c7` (red), Windows host**, the two Windows-only refusal tests:

```
E   ValueError: preexec_fn is not supported on Windows platforms
C:\...\python.exe\Lib\subprocess.py:857: ValueError: preexec_fn is not supported on Windows platforms
FAILED tests/test_launcher_local_bounds.py::test_a_requested_bound_this_host_cannot_install_is_refused
FAILED tests/test_launcher_local_bounds.py::test_a_refused_bound_leaves_no_durable_claim_and_no_markers
2 failed, 14 deselected in 1.31s
```

**After the fix (green), Windows host**, whole file:

```
...sss..ss..s.ss                                                         [100%]
8 passed, 8 skipped in 1.17s
```

### Coverage against each required case

(a) **The requested limits reach the child.** `test_requested_limits_carry_both_declared_values` asserts the literal payload keys resolve to `ChildLimits(cpu_seconds=7, memory_bytes=1048576)`. `test_memory_ceiling_actually_bounds_the_child` dispatches and has the child print its own `getrlimit(RLIMIT_AS)`, asserting `[536870912, 536870912]`. The value is read by the child, not inferred from a config.

(b) **A limit actually fires.** `test_cpu_ceiling_stops_a_spinning_child_well_before_the_wall_budget` dispatches a spinning child with `cpu_seconds=2` and `timeout_ms=30000`, then asserts `timed_out is False`, `returncode < 0`, and `wall_ms < 15000`. The wall deadline is 30s, so passing requires the CPU bound to have stopped it. `test_a_memory_bound_below_the_interpreters_own_floor_fails_the_child` uses 8MB, measured on this host as the point where the interpreter fails to load (`rc=127`, "error while loading shared libraries") while 16MB still starts, and asserts the payload's `print` output is absent.

(c) **A missing capability refuses and strands nothing.** `test_a_requested_bound_this_host_cannot_install_is_refused` and `test_a_refused_bound_leaves_no_durable_claim_and_no_markers` run on Windows, where no bound can be installed. They assert `sent is False`, a `child-limit-unavailable:` reason, `claimed(...) is False`, `prove_never_sent(...) is True`, and that a retry is refused for the same reason rather than reported as a prior send.

(d) **The read-back confirms the flag that was set.** `test_the_read_back_confirms_the_flag_whose_setter_ran` does not compare constants. It forks a fresh interpreter, calls the module's own setter, and asserts the kernel read-back is 1. On base it failed with `assert 0 == 1` and the message naming the PDEATHSIG trap. `test_no_new_privs_constant_is_pr_set_no_new_privs_not_pdeathsig` pins the literal 38 and 39, and `test_the_child_restrict_path_uses_the_named_constant` asserts the bare `prctl(1, 1` literal is not back in the child path.

(e) **Tamper cases authored here.** `test_a_wrong_prctl_constant_is_caught_by_the_behavioural_read_back` reverts the constant to 1 with `monkeypatch` and asserts `_no_new_privs_settable() is False`, then restores 38 and asserts `True`. Confirmed to bite: reverting the constant in the source makes both the literal test and the behavioural read-back fail. `test_a_child_dict_without_the_limits_key_never_yields_an_unbounded_child` builds a valid child dict, removes the `limits` key, and asserts a dict missing the key cannot produce a bounded or unbounded running child, so a silent `[-1, -1]` (the original bug) fails.

### Proof the limits are installed and fire

Through the real `LocalLauncher.dispatch`, after the fix, in WSL:

```
A run_local_process  child RLIMIT = {"cpu": [7, 7], "as": [67108864, 67108864]}
B LocalLauncher     child RLIMIT = {"stdout": "{\"cpu\": [7, 7], \"as\": [67108864, 67108864]}\n", "returncode": 0, "timed_out": false, "wall_ms": 40, "supervised": true}
C spin declared cpu_seconds=2 -> rc=-9 timed_out=False wall_ms=2517 (budget 30000)
```

The launcher path now matches the reference path exactly where it previously read `[-1, -1]`. The spinning child dies at 2517ms against a 30000ms wall budget, and `timed_out` is `False`, so the wall deadline did not stop it.

One measurement worth recording, because the preflight report predicted `-24` and the actual signal is `-9`. Both are enforcement; the difference is the soft/hard split. Measured directly on this kernel:

```
soft only 2, hard -1   rc=-24 wall_ms=2670
soft=hard=2            rc=-9  wall_ms=2724
```

`child_limits.apply_child_limits` sets soft equal to hard, so the kernel delivers SIGKILL at the ceiling instead of the SIGXCPU that a soft-only limit gives. That is the pre-existing behaviour of the authority module, unchanged by this work, and it fires at the declared ceiling either way. Changing soft/hard to produce `-24` would mean editing `child_limits`, which is outside this lane's scope, and would change a contract other callers rely on.

## The Linux path, and what was actually proven

The POSIX path was exercised in WSL2 Ubuntu, kernel `6.18.33.2-microsoft-standard-WSL2`. That is a real Linux kernel with a real `resource` module, and the CPU and address-space limits are enforced there by the kernel, measured through the real dispatch as shown above. The Landlock probe is also correct there after the fix:

```
clean-process probe_landlock().available = True
reason: landlock ABI 7
```

**What WSL2 cannot prove, stated plainly.** The `read_deny` enforcement path cannot be validated end to end on this host. After fixing the constant, the launcher correctly believes Landlock is available and proceeds to build the ruleset, and the child-side `landlock_restrict_self` then fails:

```
allowlist = ['/root/w0venv']
restrict FAILED: 22 [Errno 22] landlock_restrict_self failed
```

This is a WSL2 kernel limitation, not this module. A minimal hand-written ruleset outside this repository reproduces it, with a two-bit access mask and no `settlement` code involved:

```
ABI = 7
READ_FILE only         add_rule=0 restrict_self=-1 errno=22 Invalid argument
EXECUTE|READ_FILE      add_rule=0 restrict_self=-1 errno=22 Invalid argument
```

and again with the simplest possible form:

```
create_ruleset(version) rc=7 errno=0
create concrete rc=4
restrict_self rc=-1 errno=22 (Invalid argument)
restrict_self(int-fd) rc=-1 errno=22
```

There is no seccomp filter (`Seccomp: 0`, `Seccomp_filters: 0`) and the kernel reports ABI 7, so this is the WSL2 kernel advertising Landlock and then refusing to apply it. Consequently: the read-back fix, the constant, and the pre-spawn refusal are all proven on Linux; the actual read denial inside a confined child is **not** proven on this host and needs a bare-metal or VM Linux kernel. What I can state is that the code refuses rather than degrades, which is the property the governing constraint names: the dispatch either confines or does not run, and on this host it does not run.

## Surrounding test results, real counts, no combining

**Windows host**, `PYTHONPATH` pointed at the worktree `src`, `SETTLEMENT_DSN` / `SETTLEMENT_TEST_DSN` / `SETTLEMENT_TEST_TRUNCATE_DSN` unset, `S09ISO_DISABLE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`:

- New file only, `tests/test_launcher_local_bounds.py`: **8 passed, 8 skipped, 16 collected**.
- Existing only, `tests/test_launchers.py tests/test_child_limits_platform.py tests/test_adv_isolation.py`, on base `98c23c7`: **6 failed, 11 passed, 10 skipped**.
- The same three existing files with the fix: **6 failed, 11 passed, 10 skipped**.

Those 6 failures are identical before and after and are all `ValueError: preexec_fn is not supported on Windows platforms` from CPython's `subprocess`. They are pre-existing on this host and unrelated to either defect.

**WSL2**, worktree copied to the native filesystem (`/root/w0run`) because the 9p mount made the suite 10x slower and was the direct cause of an unrelated OOM in pytest's own traceback renderer:

- New file only: **13 passed, 3 skipped, 16 collected**, stable across 3 consecutive runs (4.34s, 4.26s, 4.39s).
- Existing only, `tests/test_launchers.py tests/test_child_limits_platform.py`, on base: **14 passed, 3 skipped**.
- The same two existing files with the fix: **14 passed, 3 skipped**.

`tests/test_coord02_exec.py` could not be run in WSL: 9 of its tests error at setup on `psycopg.OperationalError ... Peer authentication failed for user "ubuntu"`, a database fixture unavailable there. That file is untouched by this work.

## Required changes outside this lane's scope

`src/settlement/child_limits.py` should gain a side-effect-free capability query beside `apply_child_limits`, roughly:

```python
def child_limits_supported(limits: ChildLimits) -> bool: ...
```

`launcher_local.child_limits_unsupported_reason` currently duplicates the `os.name != "nt"` test that lives inside `child_limits`, because the shared shape does not exist yet: `apply_child_limits` cannot answer the question without also doing the thing, and doing the thing in the parent permanently lowers the launcher's own limits. The duplication is called out in the function's docstring and the two answers currently agree, but the single source of truth belongs in `child_limits` and the launcher should become a call to it. `child_limits.py` was left unmodified because it is outside this lane's owned scope.

## Unverifiable on this host, stated explicitly

- **A confined `read_deny` child actually cannot read a denied path.** Blocked by the WSL2 `landlock_restrict_self` EINVAL, proven above to be a host kernel defect rather than this module. Needs bare-metal or VM Linux.
- **`RLIMIT_CPU` SIGXCPU versus SIGKILL semantics on a non-WSL kernel.** Only the WSL2 kernel was available. The soft/hard split is POSIX-standard and the measurement is consistent with it, but a second kernel was not tested.
- **`RLIMIT_AS` numbers are interpreter-specific.** The 8MB and 16MB thresholds were measured on WSL's CPython 3.14.4. A different interpreter will have a different floor; the test asserts the observable effect, not a constant, but the constant in the test is host-specific and would need a fresh measurement elsewhere.
- **The pre-existing `MemoryError` handler change was verified only against the WSL kernel.** Its behaviour on Windows cannot be exercised because no dispatch reaches `Popen` there.
- **The WSL2 CPU watchdog fires on long CPU burns and kills the whole process group**, including the test runner (`CPU Watchdog Timeout (hard): python[...]` in `dmesg`). This is why the test suite is run from a native WSL filesystem. It is a host artifact and does not affect the code under test, but a future lane running CPU-bound tests under WSL on a 9p mount will see the runner killed mid-session.
