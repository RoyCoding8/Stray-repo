# w0-crlf: staged bytes, frozen digests, and the oracle/grader identity

Branch `wt/w0-crlf`, base `98c23c7`, commit `730fc0f`. Worktree
`D:/AI/Agent-Society-v2/.worktrees/w0-crlf`. No push, no merge.

## Summary

Defects 1 and 2 are fixed and are one defect. The shared root cause is that
nothing in this instrument binds the bytes it measures to the bytes it
measured. A driver is hashed in memory and re-hashed from disk; a frozen
world is hashed as a blob and re-hashed from a checkout. In both cases
something between the two steps is allowed to rewrite the bytes, and the
platform decides. `core.autocrlf=true` decided to translate LF to CRLF.

The fix is one rule at the two boundaries that write measured bytes:
`method_exec._stage_text` encodes explicitly and checks what it wrote, and
`.gitattributes` pins every content-hashed tree to LF so a checkout cannot
rewrite a frozen world.

Defect 3 is confirmed exactly as briefed and is **not** fixed. It cannot be
fixed in my scope, and the structural reason is below. The oracle and the
grader are the same function, and because both authored reducers only ever
return a trial the oracle already graded `preserved`, `preserved` is
constant by construction. This is a design property, not a host artifact, and
it needs a second grading path that does not exist.

## Environment

`PYTHONPATH` must put the worktree `experiments` ahead of the main checkout.
The venv ships an editable install at
`.venv/Lib/site-packages/__editable__.settlement-0.1.0.pth` containing the
line `D:\AI\Agent-Society-v2\src`, which injects the main checkout ahead of
any path this lane sets. Setting only `PYTHONPATH=<worktree>/src;<repo root>`
silently imports the main checkout's `experiments` while the `settlement`
check still prints the worktree path. Use:

```
PYTHONPATH="D:/AI/Agent-Society-v2/.worktrees/w0-crlf;D:/AI/Agent-Society-v2/.worktrees/w0-crlf/src"
```

`tests/test_staging_fidelity_crlf.py` asserts both `method_exec` and
`worlds.FROZEN_DIR` resolve inside the worktree, so this cannot recur
silently. It bit me once during this lane.

## Defect 1: staging rewrote bytes, provenance verification failed

### Reproduction

```
$ pytest tests/test_method_exec_source_authority.py -q
...
experiments\ad01\method_exec.py:885: in _verify_operation_provenance
    raise MethodExecutionError("refused: staged driver digest mismatch")
E   MethodExecutionError: refused: staged driver digest mismatch

provenance = {'source_digest': '46e88b0b...', 'driver_digest': 'e6a19a22...',
              'input_digest': '22ea7a5f...', 'source_path': 'policy.py', ...}

7 failed, 4 passed
```

The expected driver digest in the traceback is `e6a19a22661a3088`, matching
the value the brief cited. The staged bytes hashed to something else because
Python's text-mode `write_text` translated the 16 LFs of `_STEP_DRIVER` to
CRLF on the way to disk.

Direct measurement of the mechanism:

```
LF count in template   : 16
CR present             : False
expected driver_digest : 4f75d4a4f7c5c18aa21e20232939e0d83dbc20691ac3daf237fcc9717da63957
actual on-disk digest  : bf46f0be2b85c394e614432bb598709f97669d937f1f7f52839f0f51bf307963
MATCHES                : False
disk contains CRLF     : True
```

The silent part is upstream of that. `s09_e2_scored._execute` wraps the call
in `except method_exec.MethodExecutionError: return None`, and
`run_trials` turns any `None` into a refusal. So the instrument reported no
results rather than an error, and `candidates_moved` was never written. That
is why this shipped.

### Fix

`experiments/ad01/method_exec.py`. Two `driver.write_text(driver_source,
encoding="utf-8")` calls became `_stage_text`. The new function is the
boundary:

```python
def _stage_text(path: Path, text: str, expected: str) -> None:
    raw = text.encode("utf-8")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise MethodExecutionError("refused: staged text digest mismatch")
    path.write_bytes(raw)
```

It checks the bytes it encoded against the digest it was handed, rather than
assuming the write preserved them. `_stage_source` was already byte-exact
(`write_bytes(source.encode("utf-8"))`) and now routes through the same
function, so there is one staging primitive for the file instead of two that
look alike and differ.

### Deleted

The two `write_text` call sites. Nothing was superseded or branched around.

## Defect 2: the freeze manifest was computed over CRLF bytes

### Reproduction

All three freeze verifiers in `experiments/ad01/` failed:

```
worlds.verify_freeze(worlds.FROZEN_DIR)         -> ['manifest-hash-mismatch']
experience_axis.verify_freeze(FROZEN_DIR)       -> ['manifest-hash-mismatch']
panel_variation.verify_freeze()                 -> ['manifest-hash-mismatch']
```

The `ad01` manifest:

```
git blob len : 14399
disk   len   : 14846
blob sha     : 15e588a86c12cb68974a376352dcb6408ea524629ad6d3d98493b6e19ce07862
disk sha     : c4176f408b02f76eb385f8f0568f124e0b27d171bff283f1e758d4e10963abdf
pinned       : 15e588a86c12cb68974a376352dcb6408ea524629ad6d3d98493b6e19ce07862
```

The pinned digest is the LF digest and the file on disk is the CRLF one. A
scan of the tree found 3220 of 3256 tracked files carry CRLF on disk, so this
was not one file.

The brief says the freeze hashes 446 bytes that arrive CRLF'd. I could not
reproduce that number. No tracked file in the repository is 446 bytes either
LF-normalized or raw, and the three ad01 manifests are 14399, 14145 and 12260
bytes LF-normalized. The defect is real and the fix is unchanged; the byte
count in the brief does not correspond to anything in this tree.

### Fix

A new `.gitattributes` at the worktree root:

```
experiments/ad01/worlds/** text eol=lf
experiments/ad01/worlds_exp/** text eol=lf
experiments/ad01/worlds_panel/** text eol=lf
experiments/agenda01/** text eol=lf
experiments/coord02/corpus/** text eol=lf
experiments/representation/experiment/** text eol=lf
experiments/representation/fixtures/** text eol=lf
experiments/team01/** text eol=lf
```

Why each part is needed. `text` normalises CRLF to LF in the index, so the
pinned digest is the digest of the source. `eol=lf` materialises LF in the
working tree on every host, overriding that host's `core.autocrlf`. Without
`text`, `eol=lf` alone is ignored by git. The eight directories are exactly
the trees that contain a `manifest.sha256` and are therefore content-hashed;
the list is discovered by glob in the test, not hand-maintained.

It is deliberately not a repo-wide `* text=auto`. The experiment and library
code is not pinned by any manifest, and a global rule would rewrite 3200
unrelated files to buy nothing.

One mechanical consequence. `.gitattributes` does not rewrite a working tree
that is already checked out, so the frozen worlds had to be renormalized:

```
git add --renormalize experiments/ad01/worlds experiments/ad01/worlds_exp experiments/ad01/worlds_panel
Remove-Item -Recurse -Force <the three dirs>
git checkout-index -f -a
```

`--renormalize` alone changes the index and leaves the working tree CRLF, and
`checkout-index` is a no-op for files it considers up to date. The delete is
required. After it, `manifest.json` reads 14399 bytes with no CRLF, and the
committed bytes are unchanged, so the pinned digests still verify.

Verified end to end on a fresh clone under `core.autocrlf=true`:

```
experiments/ad01/worlds/manifest.json      len 14399 hasCRLF False
experiments/ad01/worlds_exp/manifest.json  len 14145 hasCRLF False
experiments/ad01/worlds_panel/manifest.json len 12260 hasCRLF False
experiments/ad01/method_exec.py            len 69651 hasCRLF True
```

The last line is the point of scoping: experiment code is not content-hashed
and keeps the host's convention.

## The one rule, and where it is encoded

> Bytes on disk must equal the bytes in memory for anything that is hashed,
> bound, or verified.

Encoded at the write boundary, not at the read boundary. Defect 1 is fixed in
`method_exec._stage_text`, the function that puts measured bytes on disk.
Defect 2 is fixed in `.gitattributes`, the function that decides what a
checkout of measured bytes looks like. Neither adds a normalizer, a shim, or
a fallback. A verifier that normalized before comparing would be hiding the
mismatch rather than removing it, and the coordinator's brief rules that out
explicitly.

Defect 3 is a genuinely different bug and I did not force it under this rule.
It is about who produces a verdict, not what bytes carry it. The evidence
below.

## Defect 3: the oracle and the grader are the same function

### Confirmed

`SoftwareOracle.check` returns `check_software(self.task, candidate)`.
`trajectory._check` returns `checkers.check_software(task, candidate)`. The
verdict a trial is accepted on is the verdict the output is graded on.

`check_software` returns `PRESERVED` on exactly two reachable branches:
`ok-incumbent` when the candidate is byte-identical to the task and the
witness holds, and `ok-preserved` from `_witness_verdict`. Both authored
reducers in `experiments/representation/reducers.py` hold one invariant over
their whole walk: `keep` is only ever assigned from a trial `probe` graded
`PRESERVED`, and they return `build(keep)`. So the returned candidate is
either the whole task, which the grader calls `ok-incumbent`, or a trial the
oracle already called `ok-preserved`. Both are `preserved`.

The committed evidence says so:

```json
"reachable_verdicts": {
  "budgets_swept": [1, 4, 8, 64],
  "reasons": {"ok-incumbent": 96, "ok-preserved": 120},
  "task_budget_pairs": 216,
  "verdict_is_constant": true,
  "verdicts": {"preserved": 216}
}
```

216 of 216. I re-derived the mechanism by reading the two reducers and the
checker, not by trusting the report.

### Not fixed, and why

An independent grader cannot be introduced inside my scope. The reason is
structural, and it is not about call ordering.

The oracle and the grader are the same function because there is only one
function. `check_software` decides two things at once: what counts as a legal
deletion, and whether a candidate stands in the legal subobject relation to
the task while holding the designated witness. Both questions are answered by
the same traversal because for a deletion-only walk they are the same
question. Any independent grader would have to answer at least one of them
differently, and there is no second answer available: `not_preserved` is
reachable only through a task that does not parse, whose witness does not
hold, or whose candidate is not a legal deletion, and a walk that only ever
deletes atoms from a well-formed task cannot produce any of those. Swapping
which function is called does not change the verdict, because both functions
would compute it. That is the fake independence the brief warns against.

The minimal change that would allow it, and the file that owns it:

1. `experiments/representation/checkers.py` needs a second entry point that
   answers only the output question. Concretely, a function that takes
   `(task, candidate)` and reports whether the candidate's *behaviour* on the
   task's inputs matches the task's specification, without consulting the
   reducer's own acceptance rule. For software that means running the
   candidate against the frozen input/output pairs rather than checking
   witness retention; for graphs it means checking the stated property holds
   on the reduced graph rather than that it is a legal subgraph.
2. `experiments/representation/reducers.py` then needs a `keep` rule that is
   not "the oracle said preserved". A reducer can only keep a trial whose
   *behaviour* survives, which is a different predicate from "the oracle
   accepted it" and is the whole point.
3. `experiments/ad01/control_distinctness.py::experience_varies` counts
   distinct outcomes and currently opens on `ok-incumbent` versus
   `ok-preserved`. Under an independent grader it would count behavioural
   outcomes, and the existing refusal text would need rewording.

Files 1 and 2 are outside this lane's scope. File 3 is a
`experiments/ad01/` file I was given conditionally, but the change is
meaningless until 1 and 2 exist, so I did not touch it.

The brief asked me to read the third defect and decide. My judgement is that
this is a design change to the representation layer, not a defect repair, and
it should not be smuggled in under a CRLF fix. The evidence artifacts
`reports/evidence/inv_r1_e2_gated/` and the module docstring at
`experiments/ad01/experience_axis.py` already characterize it accurately, and
`control_distinctness.experience_varies` already routes around it by counting
outcomes rather than verdicts. The W2 experiment is not blocked by a missing
patch; it is blocked on a decision about what an independent grader should
mean for these two families.

## Tests

New file: `tests/test_staging_fidelity_crlf.py`, 8 tests, all passing.

Red then green, both directions reported.

### Defect 1, before the fix

```
$ git checkout experiments/ad01/method_exec.py   # fix reverted
$ pytest tests/test_staging_fidelity_crlf.py -q
FAILED test_staged_driver_bytes_equal_the_source_that_was_hashed
FAILED test_step_provenance_accepts_the_bytes_it_just_staged
FAILED test_staging_text_refuses_a_digest_it_cannot_produce
FAILED test_member_driver_is_staged_byte_exactly
4 failed, 4 passed
```

### Defect 1, after the fix

```
$ pytest tests/test_staging_fidelity_crlf.py -q
8 passed
```

The staged driver digest is asserted against the literal
`e6a19a22661a30887cb52771ab6afe5805dc6e580247a3b67d235020be264a6b`, the value
the defect was measured against.

### Defect 2, before the fix

The `.gitattributes` rule was removed from the worktree and the three frozen
trees re-materialized as CRLF, which is what a checkout without the rule
produces:

```
FAILED test_committed_freeze_verifies_on_this_host
FAILED test_frozen_manifest_bytes_carry_no_carriage_returns
2 failed, 6 passed
```

### Defect 2, after the fix

```
$ pytest tests/test_staging_fidelity_crlf.py -q
8 passed
```

The mutation check for this half is worth noting. Removing the worktree file
did not disable the rule, because `.gitattributes` is read from the index.
The check that failed is the behavioural one, the freeze verifying against
real CRLF bytes, which is the right thing to fail.

### Test quality

Every test reads bytes off disk or asserts a literal digest. None of them
would pass if the imported functions returned `undefined`; the freeze tests
read `worlds.FROZEN_DIR` from disk, the staging tests read the staged file
after the real code path wrote it. The two tests that could not run a child
process do not skip. They monkeypatch `launcher_local.subprocess.Popen` to
capture the staged bytes and raise, because all the staging and provenance
work happens before `Popen`. That is why the suite reports 8 passed and 0
skipped on a host that cannot spawn a child at all.

## Test counts

Affected files, before and after. Baseline and final were run with the same
command and the same environment.

```
$ pytest tests/test_staging_fidelity_crlf.py tests/test_method_exec_source_authority.py \
         tests/test_ad01_env.py tests/test_ad01_experience_axis.py \
         tests/test_ad01_panel_variation.py -q
```

| | before | after |
|---|---|---|
| passed | 68 | 78 |
| failed | 15 | 13 |

Newly passing, 10 of them:

- `test_ad01_env.py::test_committed_freeze_matches_manifest`
- `test_ad01_experience_axis.py::test_the_new_panel_regenerates_and_audits_clean`
- the 8 new tests in `tests/test_staging_fidelity_crlf.py`

Still failing, 13, with the cause of each:

**12 are the Windows platform limit, not a code defect.**
`launcher_local.py:746` passes `preexec_fn=_child_setup(confinement)` to
`subprocess.Popen`, and CPython refuses `preexec_fn` on Windows outright.
`src/settlement/child_limits.py` documents this as a known, deliberate
limitation: the bound must be installed between fork and exec, and where that
is impossible the child is refused rather than run unbounded. Two of the
failures reach further and hit `socket.AF_UNIX`, also absent on Windows.

| file | count |
|---|---|
| `test_method_exec_source_authority.py` | 7 |
| `test_ad01_experience_axis.py` | 3 |
| `test_ad01_panel_variation.py` | 2 |

These are unchanged by this commit. I verified by reverting
`method_exec.py` and re-running: before the fix they failed at
`staged driver digest mismatch`, after the fix they fail further along at
`preexec_fn`. The provenance refusal is gone; the next boundary is a
platform that cannot enforce a containment, which is the correct refusal.
`src/settlement/launcher_local.py` is owned by another lane and I have not
touched it. The fix is a real decision for its owner, not a mechanical one:
either pass `preexec_fn` only on POSIX and refuse a bounded dispatch on
Windows with a named error, or move to `CREATE_SUSPENDED` with a Job Object,
which `child_limits.py` already measured as not buying a CPU-time bound.

**1 is a real defect I did not fix, in a file outside my scope.**
`tests/test_ad01_panel_variation.py::test_the_freeze_verifies_and_regenerates`
fails on `['manifest-content-mismatch']`. `panel_variation.build_manifest`
(line 692) writes `str(path.relative_to(directory))` into the manifest. On
Windows that yields `world-0\dev\panel-w0-dev-gr-00.json`; the committed
manifest has `world-0/dev/panel-w0-dev-gr-00.json`. Comparing the rebuilt
manifest against the committed one therefore fails on a correct checkout.

This is the same class as Defect 2, one layer over: the manifest is a
function of the checkout rather than the source, this time through the path
separator rather than the line endings. The committed manifests are correct,
all 54 entries use forward slashes, so only the rebuild is wrong.

`experiments/ad01/worlds.py:86` and `experiments/ad01/experience_axis.py:749`
have the identical `str(target.relative_to(root))`, but in both the committed
manifest and the rebuild are produced by the same expression, so they agree
with each other and the defect is invisible until a manifest is generated on
one platform and verified on another.

Minimal fix, in `experiments/ad01/panel_variation.py` line 692:

```python
files.append({"path": path.relative_to(directory).as_posix(),
              "task_id": path.stem, "digest": _digest(raw),
              "bytes": len(raw)})
```

The same one-word change belongs on `worlds.py:86` and
`experience_axis.py:749` to make those manifests portable if they are ever
regenerated on a different host. I did not make it, because
`panel_variation.py` is not in my owned scope and `worlds.py` and
`experience_axis.py` are adjacent to it. It is a one-line change and I would
rather flag it than have two lanes touching the same freeze.

## What I could not resolve

- The 446-byte figure in the brief. No tracked file in the repository is 446
  bytes, LF-normalized or raw. The defect is real and reproduced; the number
  does not correspond to anything in this tree.
- 12 tests blocked on `preexec_fn`. This is a documented, deliberate refusal
  owned by `src/settlement/launcher_local.py`, which is another lane's file.
  I have not touched it and did not work around it, because a workaround here
  would be exactly the silent unbounded-child degradation
  `child_limits.py` was written to prevent.
- `panel_variation.build_manifest` path separator, characterized above with
  the exact one-line fix and the three files it belongs in.
- Defect 3, characterized above with the structural reason an independent
  grader cannot be faked and the three-file change that would allow it.

## Files

Changed by this lane:

- `.gitattributes` (new)
- `experiments/ad01/method_exec.py` (staging region only)
- `tests/test_staging_fidelity_crlf.py` (new)
- `reports/workstreams/w0-crlf.md` (this file)

Not changed, and should not be by this lane:

- `src/settlement/launcher_local.py` (owned by another lane)
- `experiments/ad01/s09_arm_parity.py`, `experiments/ad01/s09_swe_world.py`
  (owned by another lane)
- `experiments/ad01/learner.py` (no defect found; the experience-record
  rendering at line 985 reads records and renders them, and never stages
  hashed bytes, so the scope grant went unused)
