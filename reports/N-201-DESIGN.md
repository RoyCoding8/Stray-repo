# N-201 design analysis: fail closed or fail open

Lane L7, read-only. No code changed. Probes ran in `/tmp`; no test suite run.

## 1. Recommendation

**Fail closed, and the cheapest correct form of it is not a policy toggle but a
durable pre-send claim ledger written inside `dispatch`.** Once that ledger
exists, the deletion case is answered from the store rather than from a
directory, and the "evidence gone" question never reaches a boolean.

## 2. Current state of the code

The launcher half of N-201 is **closed**. `114ac3e` did what its message
claims, and the ledger row is stale on the live-process point.

`LocalLauncher.prove_never_sent` at `src/settlement/launcher_local.py:153`
today reads: refuse if `run_dir` is not a directory (line 162), refuse if
`is_live(operation_id)` (line 164), otherwise defer to `_never_sent_on_disk`
(line 166), which globs the five suffixes in `_NEVER_SENT_SUFFIXES`
(`launcher_local.py:40`). `live_ids` at line 199 enumerates every `*.pid` in the
run directory and keeps the ones `os.kill(pid, 0)` answers for.
`is_live` at line 209 is the per-operation form, and `broker._is_live`
(`src/settlement/broker.py:1089`) reaches it through `live_ids`.

Measured on a live launcher, one real spawn:

| state | `prove_never_sent` |
|---|---|
| never claimed | True |
| after a real `dispatch` | **False** |
| run directory wiped, launcher alive | **True** |

So the live-process check is present and correct. What is still open is
narrower than the finding says: **the deletion case**, and only the deletion
case. Commit `114ac3e`'s own message says so, and
`reviews/STAGE-09-FINDINGS.md:356` never got the update. `TASKS.md:15` is stale
in the same way.

One trap worth recording. `prior_send` at `launcher_local.py:141-142` uses
`if any(self.run_dir.glob(...))`, and `Path.glob` returns a generator, which is
always truthy. So `prior_send` returns True for *every* operation, including
one that never ran. I measured it: `prior_send("NOTHING-EVER-RAN")` is False
only because the second line reads a result file that does not exist; add any
`.pid` file for any operation and `prior_send` becomes True for all of them.
`114ac3e`'s message says the lane hit exactly this and reverted it inside
`prove_never_sent` (`launcher_local.py:148-151` keeps the `for` loop). The same
generator-truthiness is still live in `prior_send`. It is a fail-closed bug,
so it is safe today, and it is outside N-201's scope. It should be a separate
finding.

## 3. How `launcher_runsc` answers the same question

`RunscLauncher.prove_never_sent` at `src/settlement/launcher_runsc.py:271`
refuses if `run_dir` is `None` or not a directory (line 272), refuses on any
tracked container, result, `.spawns`, `.gen` or `.supervise.json` (lines 275-282),
then consults `docker ps` through `_ps_names` (line 283) and returns
`found is not None and not found` (line 284).

Two things follow. First, the last clause is the answer to the question posed:
**runsc fails closed on the uncertain case.** When `docker ps` times out or
errors, `_ps_names` returns `None` (line 252), and `None is not None` is False,
so the whole predicate is False. A launcher that cannot ask the question does
not get to say yes.

Second, and this corrects the finding's premise. Runsc is **not** actually more
robust here. Its live-process check consults a *different filesystem* than its
disk check. `docker ps` survives deletion of the run directory; the local
profile's `is_live` reads `run_dir.glob("*.pid")` (`launcher_local.py:210`),
which does not. So on the deletion case the two profiles answered the same way
before N-201 was written. The local profile has not regressed relative to runsc,
and the finding's "port the check" remediation is already done and does not
address the case the finding is actually about.

## 4. The money model

Both failure modes hit the same place, and the two costs are not symmetric in
kind but are close in size.

**Fail open** (delete the run dir, get a proof). `broker.redispatch_after_reset`
(`broker.py:1260`) calls `store.reset_dispatch` (`store.py:2102`), which
validates the proof and returns the operation to `prepared` at generation + 1
(`store.py:2131-2134`), then re-dispatches. The side effect runs a second time.
The refund side of the same proof is `store.release_reservation`
(`store.py:881`), which decrements `allocations.reserved` on the strength of
the proof alone (`store.py:917-919`), and `reconcile_operation`'s never-sent
branch (`store.py:2253-2268`), which releases the reservation too. The cost of
fail-open is a **double execution plus a refund for work that was actually
done**: the ledger reconciles clean and the world is wrong. This is the failure
`authority.verify_ledger` cannot see. `_stranded_exposure`
(`src/settlement/authority.py:331`) calls receiptless exposure in
`dispatching`/`sent`/`unresolved` *lost rather than pending*, and `match`
(`authority.py:407-409`) is False whenever `stranded` is non-empty. Fail-open
produces no stranded exposure, because the operation gets a receipt on the
second run. The one accounting check in the system that was purpose-built to
catch N-202's silent 111-unit leak stays green through a forged refund.

**Fail closed** (evidence gone, no proof). The operation stays in
`dispatching`. `broker.reconcile` (`broker.py:1012`) returns
`unresolved-liability` with "exposure retained" (`broker.py:1077-1079`) and
`next="retry-later"`. The reservation stays `uncertain`. `verify_ledger`
reports the units under `stranded` and `match: False`. The cost is a real,
visible, bounded leak.

**Is fail-closed recoverable?** No, and this is the finding that decides the
question. There is no operator reclaim path. `release_reservation` is the only
thing that decrements `allocations.reserved` for a stranded reservation, and
it demands the very proof that is unobtainable. Its only production caller is
`team.py:1020`. There is no `forgive`, no `appeal`, no `force_release`, no
`write_off` anywhere in `src/`. `_TERMINAL_UNKNOWN` (`store.py:100`) is the
opposite: it makes an operation *more* permanent, and
`_refuse_terminal_unknown` (`store.py:623`) blocks `release_reservation` from
ever touching one.

So the honest comparison is not "safe refund versus an outage". It is **a
visible budget leak versus an invisible correctness breach**. This system has
already chosen the visible leak. `authority.py:331-346` says so in terms:
counting stranded units as pending "is what let a study holding them report an
all-clear". The whole point of N-202's repair was to make the leak *loud*. A
fail-open `prove_never_sent` gives that repair a bypass.

## 5. The run-directory threat model

The finding's threat model is right and the mitigation is worse than it looks.
The run directory is **not** a system temp dir with a sticky bit. The caller
chooses it and it is created by the launcher's own process:
`self.run_dir.mkdir(parents=True, exist_ok=True)` at `launcher_local.py:91`,
with the mode Python's `mkdir` gives it, 0o775 under the process umask.
Measured on this machine: mode 0o775, owned by the launching uid.

The party that could forge a proof is the worker. Every production call site
hands the launcher a directory under the study's own scratch or work tree
(`experiments/ad01/method_exec.py:498,769` use `work / "launcher"`), and the
worker's `cwd` is the operation work directory, a sibling. The worker's
process is a child of the same uid. `PROFILE = "local-process"` and
`containment=False` on every outcome (`launcher_local.py:85`,
`exec_profile.py:171,205,226`) state that the worker is **not** contained.
`scrub_env` (`exec_profile.py:104`) reduces the environment, not the uid, and
the run dir is explicitly placed outside the worker's listing, which is a
confirmation that the worker is expected to be able to see and reach sibling
paths under it.

So the deletion is not a privileged act. It is a write the worker can already
do. That makes fail-open actively wrong here, and it is why the runsc profile's
fail-closed `docker ps` clause matters as *precedent* rather than as robustness.

## 6. Cheapest design that makes the question moot

**A launcher-held claim ledger, written before the send, outside the evidence
directory.** Not a digest, not a hash of the evidence: a record of the fact of
having claimed, which `prove_never_sent` then answers from.

The window is already open and already correctly ordered. `dispatch` writes
`_claim(paths["pid"])` at line 286, the generation at line 300, and the spawn
count at line 317, all *before* `subprocess.Popen` at line 320. Moving the
durable write is not new work on the crash path; it is giving the earliest of
those three writes a home outside the directory the failure deletes.

Concretely: at construction, open an append-only ledger outside `run_dir` (a
sibling, or a path passed in by the caller, since `run_dir` itself is the thing
that vanishes). In `dispatch`, append `(operation_id, execution_version,
generation, pid, monotonic)` and `fsync` *before* line 320. `prove_never_sent`
then reads the ledger first. A record present means claimed, so return False
regardless of what the run directory says. No record means never claimed, so
return True.

Cost, honestly. One append plus one `fsync` per dispatch, on the order of a
millisecond on this filesystem, on a path that already writes three markers
and spawns a subprocess. It is *cheaper* than either policy, because it makes
the fail-closed branch's cost, the permanently stranded reservation, rare
rather than routine. A crash that loses only the run directory now still
answers False from the ledger and still strands, so fail-closed is not free.
What changes is that stranding requires the ledger to be gone too, which
means the attacker needs the ledger path as well as the run directory.

The ledger must live in the store, not just on disk, to be complete. A
durable store row written by `prepare_operation` alongside the existing
`_dispatch_generation` bump closes it fully, and `store._bump_inflight_dispatch`
(`store.py:2382-2396`) is already fencing in-flight dispatches by bumping that
generation. It is more work and it is the right end state. The launcher-held
file is the cheap 80 percent and it is honest about being 80 percent.

## 7. What changes in code

Adopting the recommendation, in order.

1. `src/settlement/launcher_local.py:89-94`. Add a claim-ledger path beside
   `self.run_dir`, open at construction.
2. `src/settlement/launcher_local.py:317-320`. Append and `fsync` the claim
   record before `subprocess.Popen`, reusing the pre-send slot that already
   exists. This is the whole fix and it is three lines at an existing boundary.
3. `src/settlement/launcher_local.py:153-166`. Consult the ledger before
   `_never_sent_on_disk`. A ledger hit returns False unconditionally. The
   `run_dir.is_dir()` check at line 162 stays and already fails closed.
4. `tests/test_s09_controls.py:280-282`. That test erases the run-directory
   record and asserts `prove_never_sent(op, 1) is True`. Under a durable
   ledger it is asserting the bug. It must be rewritten to erase the ledger too,
   or inverted. This is the reason 114ac3e could not close N-201, and it is
   correct that it did not.
5. `TASKS.md:15` and `reviews/STAGE-09-FINDINGS.md:356`. Both are stale. The
   live-process remediation is done; the open half is deletion only.

Not recommended, and named so it is not re-proposed: a digest or hash of the
run-directory evidence. It leaves the property false, which the handoff
forbids, and it adds a false sense of durability to files that are deletable
together.

Separately, and outside N-201: `launcher_local.py:141-142` has the
generator-truthiness bug in `prior_send`. Fail-closed, so safe today, but it
should be its own finding with its own fix.
