# w0-unixfix: typed-AST child on a host without POSIX rlimits

Lane: `w0-unixfix`. Branch `wt/w0-unixfix` at `dfbd557`. Host: Windows 11, Python 3.13.14.

## Decision

**Outcome (b): an explicit deployment limitation.** Not a Windows-equivalent limits
implementation.

The typed-AST step child still requires Linux. It is not runnable on this host. It now
fails with a named platform verdict instead of a `ModuleNotFoundError`.

## Reproduction

Command:

```
cd D:/AI/Agent-Society-v2/.worktrees/w0-unixfix
S09ISO_DISABLE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
PYTHONPATH="D:/AI/Agent-Society-v2/.worktrees/w0-unixfix/src;D:/AI/Agent-Society-v2" \
D:/AI/Agent-Society-v2/.venv/Scripts/python.exe -c "
import json
from experiments.ad01 import s09_swe_ast as ast, s09_swe_tasks as T, s09_swe_world as world
rec = T.instance('held_out', T.HELD_OUT_TEMPLATES[0], T.HELD_OUT_MECHANISMS[0])
decide = ast.choose_action(ast.make_record('probe-0', index=0))
print(json.dumps(decide(world.SweSession(rec).policy_view()), indent=2, default=str))
"
```

Driver output (task `swe-held_out-count-tail-sum-1fdc31`):

```json
{
  "kind": "stop",
  "target": "swe.task",
  "inputs": {
    "bridge_refusal": {
      "stage": "swe-ast-policy-step",
      "reason": "child exited 1: e 88, in _run_code\r\n  File \"...\\boolean_ast_policy.py\", line 893, in <module>\r\n    raise SystemExit(_child_main())\r\n                     ~~~~~~~~~~~^^\r\n  File \"...\\boolean_ast_policy.py\", line 483, in _child_main\r\n    import resource\r\nModuleNotFoundError: No module named 'resource'\r\n"
    }
  },
  "evidence_refs": [],
  "requested_resources": {}
}
```

Child exit behavior: the child process exits 1. The parent reads
`process.returncode != 0` and raises `_ExecutionRefused("child exited %d: %s")` with the
last 400 bytes of the child's stderr. `choose_action` catches it and records a `stop`
carrying the traceback. The reason a reader sees is a crash plus a truncated traceback,
which names a program bug rather than a host.

## Diagnosis

Root cause is a platform capability assumption, not a logic error. `_child_main` opened
with `import resource` and installed `RLIMIT_CPU` and `RLIMIT_AS`. On a host with no
POSIX `resource` module, the import raises before either cap is installed, and the
`_ExecutionRefused` is only reached afterward, so the traceback escapes as a child exit.

Measured platform facts on this host, not assumed:

| Capability | This host |
|---|---|
| `sys.platform` | `win32` |
| `import resource` | `ModuleNotFoundError` |
| `os.setrlimit` / `os.getrlimit` | absent |
| `os.setsid` | absent |
| `os.killpg` | absent |
| `signal.SIGKILL` | absent |
| `/proc` | absent |
| `Popen(start_new_session=True)` | accepted, and **ignored** |

That last row matters. In CPython's Windows `_execute_child` the parameter is literally
named `unused_start_new_session`. `subprocess` swallows it and returns normally, so the
"own process group" the timeout path depends on is not established either. The child
starts and dies, and the parent attributes that to a non-zero return code.

### Why not a Windows-equivalent limits implementation

There is no supported Windows mechanism that installs an equivalent of `RLIMIT_CPU` or
`RLIMIT_AS` in a Python child process:

- `subprocess` exposes no rlimit equivalent; it does not offer the mechanism at all.
- Job Objects are the real Windows mechanism, but they are a Win32 API, not a POSIX
  rlimit. Reaching them means ctypes, and they bound address space and CPU for a *process
  tree assigned to a job* at creation time. They cannot be installed from inside a
  Python child after it has started, and `setrlimit`-style per-process limits have no
  counterpart there.
- The CPU limit is the stronger objection. `RLIMIT_CPU` bounds a process's consumed CPU
  time and delivers `SIGKILL` past it. Windows Job Objects bound *wall-clock* lifetime via
  a kill-on-close or timeout, not accumulated CPU. A ctypes job object would therefore
  enforce a *different* limit, and the limits table would describe enforcement the system
  does not provide.

Writing that would be a second execution path with weaker semantics, which is exactly what
the governing constraint forbids. The constraint permits either a genuinely equivalent
enforcement or a loud deployment limitation. Only the second is available.

The repo already holds this exact shape. `settlement/launcher_local.py` defines
`probe_landlock` and `LandlockProbe` and refuses a dispatch that asks for confinement the
kernel cannot provide, with the docstring: "a boundary that silently degrades is the
defect N-36 names." `boolean_ast_policy` is the same boundary with the same hole, and
`Launcher.dispatch` already returns `read-boundary-unavailable: <probe reason>`.

## What changed

One capability decision, in one place, consulted once per step.

`experiments/ad01/boolean_ast_policy.py`:

- Added `ChildLimitSupport` (frozen dataclass: `name`, `available`, `reason`) and
  `child_limit_support()`, mirroring `LandlockProbe` / `probe_landlock` in
  `launcher_local.py` so the codebase has one idiom for "can this host enforce this".
  It measures rather than assumes: it checks the import, then checks for `setrlimit`,
  `RLIMIT_CPU` and `RLIMIT_AS`, so a `resource` module present but incomplete is caught
  rather than crashing mid-child.
- `_run_step` consults the probe and raises `_ExecutionRefused` with the reason **before**
  `subprocess.Popen`. The host is reported as unable to enforce the caps, and no child is
  started.
- `_child_main` consults the same probe and raises the same reason, so the boundary holds
  for any other caller of the child entry point rather than only for `_run_step`. The
  `import resource` moved below the value checks, so a non-positive limit is still refused
  before the caps are touched.
- Added a `host` key to the `expressivity_limits()["enforcement"]` table recording that
  these caps are POSIX rlimits and that a host which cannot install them is refused.

No `sys.platform` check is scattered through the call stack. The platform decision lives in
one function and both call sites ask it the same question.

Complexity is up by one small function and one dataclass, which is the cost of naming the
capability. Nothing was added as a fallback, retry, or second execution path.

### Scope

The two `import resource` sites in `src/settlement/` (`exec_profile.py:117` and
`launcher_local.py:796`) are the same defect, but they are outside my owned scope. See
"Out of scope" below.

## The limits were not weakened

The governing constraint is that the child CPU, wall, output and state limits must not be
removed, weakened, disabled, bypassed or made optional. None were.

- `RLIMIT_CPU` and `RLIMIT_AS` are still installed, by the same `resource.setrlimit` calls
  with the same hard-equal soft-equal pairs, in the child, before the document runs.
- The limit *values* are still validated. `_child_main` still raises
  `cpu_seconds must be positive` and `memory_bytes must be positive`, and the parent still
  rejects a non-positive limit before a child is started.
- The wall timeout, output byte cap, state byte cap and load-time node and depth budgets
  are untouched.
- The probe is a refusal, not an override. It has no argument, no environment variable and
  no fallback branch. A host that cannot install the caps does not get a weaker step; it
  gets no step.

Per-platform enforcement mechanism after this change:

| Mechanism | POSIX (Linux/macOS) | This host |
|---|---|---|
| CPU | `RLIMIT_CPU` via `setrlimit` | not installable; step refused |
| Address space | `RLIMIT_AS` via `setrlimit` | not installable; step refused |
| Wall clock | parent `communicate(timeout=)`, killpg | parent timeout; `killpg`/`SIGKILL` also absent (separate defect, see below) |
| Output bytes | parent `_cap` on the captured streams | same |
| State bytes | load-time `policy_step` cap | same |
| Node count / depth | load-time budgets in `_document` | same |

## Regression: red before, green after

Two tests added to `tests/test_s09ast_boundary.py`, the file that already owns this
boundary. Both call the code the way its users do, through `ast_policy.ast_step` via
`_first_step`, and assert a literal expected string.

### Red, before the fix

Public behavior captured against the pre-fix source, calling `ast_policy.ast_step` exactly
as the driver does:

```
PRE-FIX PUBLIC BEHAVIOR:
'child exited 1: e 88, in _run_code\r\n  File "...\\boolean_ast_policy.py", line 893,
in <module>\r\n    raise SystemExit(_child_main())\r\n                     ~~~~~~~~~~~^^\r\n
File "...\\boolean_ast_policy.py", line 483, in _child_main\r\n    import resource\r\n
ModuleNotFoundError: No module named 'resource'\r\n...'
```

Running the new tests with the source change reverted:

```
E       AttributeError: module 'experiments.ad01.boolean_ast_policy' has no attribute
        'child_limit_support'
FAILED tests/test_s09ast_boundary.py::test_the_step_refuses_a_host_that_cannot_install_the_caps
FAILED tests/test_s09ast_boundary.py::test_the_refusal_names_the_platform_and_not_the_child_traceback
2 failed, 14 deselected in 0.15s
```

### Green, after the fix

```
$ python -m pytest tests/test_s09ast_boundary.py -q \
    -k "cannot_install_the_caps or names_the_platform"
..                                                                       [100%]
2 passed, 14 deselected in 0.08s
```

### The tests were mutation-checked

A green test that cannot fail is worthless, so I verified the assertions bind. Three
mutants of the source, each reverted immediately:

| Mutation | Result |
|---|---|
| Probe lies and reports `available=True` on a host with no `resource` (silent limit drop) | `1 failed, 1 skipped` |
| Probe returns an empty reason string | `2 failed, 14 deselected` |
| Parent-side refusal deleted, leaving only the child check | `2 failed, 14 deselected` |

The first mutant initially **passed by skipping**, which was a real flaw in my first
version: the test skipped whenever the probe said "available", so a probe that lied about
the caps hid exactly the defect it was written to catch. I removed the skip from the
primary test and made it assert both branches, so a lying probe now fails.

`test_the_refusal_names_the_platform_and_not_the_child_traceback` still skips on a host
that can install the caps, because the refusal under test cannot be produced there. That
skip is sound: it is reached only when the probe says available, and the first test already
pins that branch's behavior.

## Linux path unchanged

Verified, not assumed. I could not run Linux on this host, so I verified both branches of
the capability decision against the real code by placing a minimal `resource` stub
(`RLIMIT_CPU`, `RLIMIT_AS`, `setrlimit`, `getrlimit`) on `PYTHONPATH`:

- `available` branch: `child_limit_support()` returns
  `ChildLimitSupport(name='rlimit', available=True, reason='RLIMIT_CPU and RLIMIT_AS are
  available')`.
- Full end-to-end step: `ast_policy.ast_step` returned
  `{"action": {"evidence_refs": [], "inputs": {}, "kind": "stop", "requested_resources":
  {}, "target": "boolean.task"}, "state": {}}`. Both the parent and the child probe passed,
  the child installed the caps, and the step ran.

Reasoning for the real Linux case: on a host where `resource` imports and provides all
three names, `child_limit_support()` returns the `available=True` value, so both `if not
support.available` branches are skipped and control flow reaches the same two `setrlimit`
calls as before, with the same arguments. The `_child_main` reordering moves the import
after the value checks; the checks are unchanged and still precede `setrlimit`. The net
effect on Linux is one dict construction and one function call per step.

One caveat I could not test: on Linux the child probe is a second import of an
already-imported module, so it is cheap. I confirmed the child is reachable in the
simulated run, so both probes are genuinely exercised.

## Surrounding test results

Pre-fix baseline and post-fix, same 7 files, same command. Run separately, not combined.

Pre-fix: `40 failed, 70 passed in 22.42s`
Post-fix: `40 failed, 72 passed in 2.47s`

The failing set is **identical**. Verified by diffing the sorted `FAILED` lines:

```
=== only in POST (newly broken) ===
(none)
=== only in PRE (fixed by this change) ===
(none)
```

Net: no test broken, none fixed. The 2 added passes are the new regressions. The change
converts 37 of the 40 failures' root cause from a crash into a named platform verdict; the
tests still fail because they assert a step that succeeded, and that is correct on Windows.

Failure-reason classification, post-fix, across those 7 files:

| Reason | Count |
|---|---|
| `supported Linux execution environment` (the new honest verdict) | 37 |
| `No module named 'resource'` | 0 |
| `os.killpg` absent | 0 |

Per file, post-fix:

| File | Result |
|---|---|
| `tests/test_s09ast_boundary.py` | 7 failed, 9 passed |
| `tests/test_s09ast_view.py` | 1 failed, 9 passed |
| `tests/test_s09ast_registration.py` | 3 failed, 5 passed |
| `tests/test_s09ast_restart.py` | 3 failed, 2 passed |
| `tests/test_s09ast_expressivity.py` | 3 failed, 10 passed |
| `tests/test_s09ast_contingent.py` | 13 failed, 0 passed |
| `tests/test_boolean_ast_arm.py` | 10 failed, 37 passed |

Paired consumers, pre and post identical:

| File | Pre | Post |
|---|---|---|
| `tests/test_ordering_ast_policy.py` | 9 failed, 8 passed | 9 failed, 8 passed |
| `tests/test_ordering_graph_policy.py` | 1 failed, 26 passed | 1 failed, 26 passed |

`test_s09ast_boundary.py` failures are all pre-existing: all 7 names appear in the
pre-fix failure set.

Note that `test_the_cpu_limit_is_installed_but_no_legal_program_reaches_it` and
`test_a_step_child_runs_with_a_scrubbed_environment_and_its_own_directory` both **pass**.
They assert on source text (`"resource.setrlimit(resource.RLIMIT_CPU"` and
`"RLIMIT_CPU is installed and the child validates the value"`), all of which my change
preserved.

## Not resolved

**1. The same defect exists in `src/settlement/` and is outside my scope.** Two sites do
`import resource` inside a child setup with no capability check:

- `src/settlement/exec_profile.py:117` — `_limit_resources`, reached from
  `run_local_process` via `preexec_fn`.
- `src/settlement/launcher_local.py:796` — `_child_setup`, reached from
  `Launcher.dispatch`.

`launcher_local.py` already has `probe_landlock` and the `read-boundary-unavailable`
refusal, so the fix is the same shape I applied: one probe consulted where the
`preexec_fn` is installed. It is a strictly smaller change than the AST one, because the
refusal machinery already exists there. These are production `src/` files, not the AST
child, so I left them and am reporting them instead. I did not run their tests, so I cannot
state their current failure counts.

**2. Windows lacks the process primitives the timeout path needs, independently of
`resource`.** `os.killpg`, `os.setsid` and `signal.SIGKILL` are all absent, and
`start_new_session=True` is silently ignored by CPython on Windows. So even if the caps
were installable, the wall-timeout kill path could not work: `_run_step` calls
`os.killpg(process.pid, signal.SIGKILL)`, which would raise `AttributeError` rather than
kill anything. This is a **second, independent** platform gap in the same function. I did
not fix it, because a correct fix means rewriting the supervisor to use Job Objects or
`taskkill /T`, which is a substantially larger change than this lane's defect and belongs
with the `src/settlement/` work above. It does not change the decision: the step is
correctly refused before reaching it.

**3. The 40 remaining failures are not fixed by design.** They assert a typed-AST step
that succeeds. On Linux they pass. On this host they cannot. Making them green here would
mean either running the step without its caps, which the governing constraint forbids, or
skipping them, which would hide the limitation. They are left failing and legible.

## Decision-relevant answer for W1

**AST/typed-graph child execution is not runnable on this host. It requires a supported
Linux execution environment.**

Precisely, for W1 planning:

- **Typed-AST** (`experiments/ad01/boolean_ast_policy.py`, and
  `ordering_ast_policy` which delegates to its `_run_step`): requires Linux. Now reports the
  platform honestly.
- **Typed-graph** (`experiments/ad01/ordering_graph_policy.py`): **unaffected by this
  defect.** It runs in-process and spawns no child, so it imports no `resource` and
  carries no CPU or address-space cap. Its test results are unchanged by this fix. I did not
  assess whether an in-process representation without those caps satisfies the containment
  requirement, which is a separate question outside this lane.
- **The child CPU, wall, output and state limits are all still enforced on Linux** and none
  were weakened here.

Anything downstream that needs a typed-AST step executed needs a Linux host or a
container/VM providing POSIX rlimits.
