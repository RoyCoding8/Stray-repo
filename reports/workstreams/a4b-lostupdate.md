# Lane A4b — fix the frontier's lost update, the defect lane A4 actually found

Branch `wt/a4b-lostupdate`, base `6caacbc`. Owned and changed:
`experiments/ad01/frontier.py` (charge/admit path and `save()` only) and
`tests/test_inv_a4b_lost_update.py` (new). No other lane's file is touched.

## Re-verification of the lost update

I reproduced it myself rather than trusting lane A4's report. Two children
each construct a `FrontierStore`, write their confirmed baseline to a barrier
directory, and wait for a `go` file. Both baselines read `0`, both children
then charge and both print `CHARGED`. On the unfixed source:

    reloaded.authority["queries_used"] == 2
    E   assert 1 == 2

The durable count is `1`. Both children exited `0` and reported success. The
second `os.replace` overwrote the first child's entire document with its own
stale snapshot, so `pending_effects` held one charged effect and the counter
held `1`. One query was charged to the gateway and never recorded. A crash
would announce itself; this does not.

The race is deterministic here because the barrier forces both snapshots to be
taken before either charge lands. Without it the interleaving is luck.

I also confirmed lane A4's crash-loss finding. `save()` is tmp plus
`os.replace`, and it runs before `admit_and_spend` returns, so a `SIGKILL`
after that point leaves the admission and its charge intact. My fourth test
asserts that property so it cannot silently regress while this defect is
fixed. I did not re-derive a crash-loss migration.

## Both-or-refuse, as implemented: both are durable

Requirement 1 allows both charges to survive or the second to be refused. I
implemented **both durable**. The durable count is the literal `2`.

Locking `save()` alone would not have worked, and that was the design
question worth getting right. The second process holds a stale `_doc` in
memory, so serializing only the write still lets it replace the first
process's committed charge. The read-modify-write is the unit that has to be
serialized, so the lock spans the reload, the charge and the save.

The lock is a sidecar file at `self.path + ".lock"`, not the document itself.
`os.replace` swaps the inode, so a lock held on the document would not exclude
a process that had already opened the old one. Under the lock the document is
re-read and, if another process committed since this one's snapshot, adopted
and re-validated before the charge is computed. The charge is therefore
recomputed against current authority, so a stale holder cannot overspend
against a budget someone else already consumed.

I reused the `fcntl`/`msvcrt` idiom already in `scripts/invl02_live.py:1261`
rather than introducing a locking library or dependency.

## Why this is the smallest correct change

Three charge paths mutate `used` and write the whole document:
`admit_and_spend`, `spend`, `spend_round_command`. Each now runs inside
`with self._exclusive():`. That is the entire behavioural change. Supporting
it is `_read_document` (the read half of `__init__`, extracted so the reload
path validates identically), a content digest, and two small methods.

Subtracted rather than added: no lock manager, no coordinator, no version
field in the document, no retry loop, no second authority. The document schema
is unchanged, so existing stores keep validating and `frontier_version` stays
`invl02-frontier-v2`.

Enforcement is at the boundary, not caller discipline. A caller cannot opt out;
every charge goes through the locked path. The fifth test proves this by
hand-corrupting the document under a stale store and showing the next charge
is refused rather than writing the damaged document forward.

One regression I introduced and caught: my first `__init__` refactor dropped
`self._validate_document()`, which broke 13 integrity tests. I measured the
before and after failure-id sets to find it and restored the call. That is
recorded because it is why the gate is reported as an id-set diff rather than
a count.

## The JSON document stays

Not deleted. Lane A4 measured 23 of 24 production construction sites holding
no dsn; deleting the document would destroy restart survival outright.

## Gate

Real PostgreSQL, WSL Ubuntu, one process, scoped file list:

    wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims; export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/a4b.jsonl; cd /mnt/d/AI/Agent-Society-v2/.worktrees/a4b-lostupdate && PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/a4b-lostupdate/src timeout 1500 /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_frontier_atomicity.py tests/test_inv_a4b_lost_update.py tests/test_m2_frontier_inherit.py tests/test_frontier_harden.py tests/test_evidence_integrity.py -q -p no:cacheprovider'

    20 failed, 46 passed in 15.97s (0:00:15)
    S09ISO: dropped 13 database(s) for this run

My own file, alone:

    5 passed in 2.64s

The 20 failures are pre-existing and **not mine**. Measured by stashing
`frontier.py` and re-running the identical file list: the baseline is the same
20 ids, and `comm -13` on the sorted id sets is empty, so my change introduces
zero new failures and fixes none. All 20 trace to one inherited cause, lane
A2's no-dsn refusal:

    20 execution needs explicit authority and identity

That is `method_exec.py`, which I do not own. I reproduced the ids and left
them alone.

Wider gate over the remaining frontier-touching files
(`test_invl02_causality`, `test_binding_provenance`, `test_s09c2a_actions`,
`test_s09c2b_bind`, `test_final_provenance`, `test_s09rev_acquisition`,
`test_live_integration`): baseline without my fix is 16 failed / 130 passed,
and with the fix those same 16 fail. The combined run is `36 failed, 176
passed`.

I did not run the full suite, per the resource policy. The files named as other
lanes' (`test_s09_e2_*`, `test_s09_swe_executor_capability.py`,
`test_s89a1_contract`, `test_invc1_method_envelope`,
`test_construction_response_envelope`, `test_staging_fidelity_crlf`) are
outside my scoped list and are left unmeasured.

No live model call, no network, no pip, fixture gateway only. No API key is
hardcoded or printed.

## Incident: another lane wrote into this worktree

Mid-run, `git stash pop` reported modifications to four files I do not own
(`experiments/ad01/ordering_graph_policy.py`, `experiments/ad01/s09_graph_budget.py`,
`src/settlement/exec_profile.py`, `src/settlement/launcher_local.py`) plus an
untracked `tests/test_inv_b2_graph_child.py`, and my `frontier.py` change was
absent from the working tree. I recovered `frontier.py` from `stash@{0}`,
which held exactly that one file, and re-ran the gate to confirm the restored
code behaves identically (same 20-id set, zero new).

I left all four foreign modifications in place, untouched and uncommitted, and
committed only `experiments/ad01/frontier.py` and
`tests/test_inv_a4b_lost_update.py`. Someone is running outside their
worktree; the coordinator should know.