# Lane A4 — converge the frontier's decision/authority projection (inv-a L4, seams S4/S5/S6)

Branch `wt/a4-owner`, base `450a988`. **No production file was changed.** This lane
stopped at measurement, and the report says why: two of the premises the lane was
assigned on are false against this base, and the migration is blocked in files this
lane does not own.

Owned paths, none modified: `experiments/ad01/frontier.py`,
`experiments/ad01/trajectory.py`, `experiments/ad01/improve_channel.py`,
`src/settlement/artifacts.py`. Diff touches only this report.

## The crash-loss premise is false. Measured, twice.

The brief's proof obligation is that "a process killed between admission and
settlement loses the record", and that a store reservation "survives" where the
JSON file "cannot". Both halves were tested with real `SIGKILL` against a real
child process.

**Kill immediately after `admit_and_spend` returns** (child `returncode -9`):

    child stderr: admitted eff-opp-probe-0
    pending_effects after kill: ['eff-opp-probe-0']
    queries_used after kill  : 1
    settled_effects          : []
    raw doc used             : {'queries': 1, 'steps': 0}

The recoverable pending record the lane was told to prove JSON *cannot* produce
**already exists**. `admit_and_spend` calls `save()` at `frontier.py:1823` before it
returns, so the admission and its charge are durable at the moment the kill lands.

**Kill inside the write itself** (patched `save()` to `SIGKILL` before
`os.replace`): nothing is half-written. `used=0`, `pending=0`,
opportunity still `admissible`, all 16 queries refunded. `save()` (`:1654`) is
`tmp` + `os.replace`, which is atomic on this platform.

So there is no crash window in the file path in either direction. The lane cannot
write a test that fails on this base for the reason the brief gives.

## What is actually broken: a lost update, not a crash

`os.replace` is atomic, but the read-modify-write around it is not. Two processes,
each holding a snapshot confirmed against the same baseline, each charge, each
replace the whole document:

    baseline queries_used: 0
    both children confirmed the baseline and hold a snapshot: True
    child0 rc=0 out='CHARGED from=0 to=1'
    child1 rc=0 out='CHARGED from=0 to=1'
    final queries_used: 1  expected if durable: 2
    CHARGES LOST: 1

A charge is silently refunded. That is a genuine defect and it is the shape a
store reservation would fix. It is **not** crash-loss, and it is not fixed by
anything this lane can reach (see next section).

## The migration is blocked outside this lane's ownership

Moving authority to PostgreSQL requires a dsn at every frontier entry. Measured
inventory of production `FrontierStore`/`create_store` construction sites:

    production construction sites: 24   (in my paths: 1)
      with dsn already in scope : 1
      WITHOUT dsn in scope       : 23

The one site that has a dsn is `scripts/invl02_live.py:2967` (`run_e3`). The 22 that
do not are in files another lane owns:

- `experiments/ad01/live_construct.py` — `ensure_live_store` :1056, :1064,
  `bind_live_revision` :1283, `bind_retained_acquisition` :1343, `restart_store` :1405
- `experiments/ad01/learner_revision.py` — `drive_arm` :920, `_admission_views` :1447,
  `_admit` :1461, `_run_one` :1484
- `scripts/invl02_live.py` — `_write_e12_revision_receipts` :2537
- `experiments/ad01/improve_channel.py` — `fresh_round` :1406 (mine, and its only
  caller is `main` :1423, a CLI entry with no dsn either)

`frontier.py` never mentions `dsn`, `psycopg`, or imports `settlement` at all
(measured: 0 hits each). Threading authority means changing 23 signatures across
three files this lane does not own, and changing a public contract (`ensure_live_store`
is called with `(path, mission, authority)`) is a separate lane's decision.

30 further construction sites are in `tests/`, which do not block production but
would each need a fixture.

## Frontier and trajectory are not two owners of one fact

The lane is framed as duplicate authority. They are disjoint studies:

| | frontier | trajectory |
|---|---|---|
| identity | `NAMESPACE = "invl02_m2"` | `NAMESPACE_TOKEN` per run |
| effect id | `eff-<opportunity_id>-<n>` | `ad01-<cid>-b<seq>-effect` |
| persistence | one JSON document | `s09_policy_state` (migration `0017_s09_state.sql`) |
| references the other | no | no |

Neither module mentions the other (measured). There is no shared key to converge
on. Merging them is a merge of two studies, not the retirement of a duplicate
admission path, and it would be a redesign rather than a migration.

## The frozen-instruments requirement is already met

`make_evidence_record` :150, `validate_package` :382,
`validate_acquisition_evidence` :447, `validate_operate_action` :666 were measured
for I/O and mutation:

    make_evidence_record           lines=71   io=False   returns a dict
    validate_package               lines=65   io=False   returns the package
    validate_acquisition_evidence  lines=118  io=False   returns a dict
    validate_operate_action        lines=22   io=False   returns the action

None performs I/O and none mutates state. They are already callable frozen
instruments that own nothing. Requirement 1 needs no work.

## Gate

Exact command, WSL Ubuntu, real PostgreSQL, one process, scoped to the six named
gate files (this lane's own test file was never created, so it is absent from the
list; the brief's command would fail collection on it):

    wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims; export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/a4.jsonl; cd /mnt/d/AI/Agent-Society-v2/.worktrees/a4-owner && PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/a4-owner/src timeout 1500 /home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_frontier_atomicity.py tests/test_invl02_causality.py tests/test_binding_provenance.py tests/test_s09c2a_actions.py tests/test_s09c2b_bind.py tests/test_final_provenance.py -q -p no:cacheprovider'

**Base `450a988`, unchanged: `22 failed, 114 passed in 64.74s (0:01:04)`**
(`S09ISO: dropped 13 database(s) for this run`)

Reproduced identically on a second run, and the 22 ids were captured to
`/home/ubuntu/claims/a4-baseline.txt` before anything was touched. **My brief names
none of these 22.** They are inherited from lane A2, which is already in this base
(measured: `method_exec.py` carries A2's refusal string and no raw
`launcher.dispatch`, and both `tests/test_inv_a_no_dsn_execution.py` and
`tests/test_inv_a_preflight_durable.py` exist). Representative cause, from the run:

    ValueError: assessment 's09-assess-...' forbids promotion: execution failed on
    ad01-w0-dev-sw-00: refused: execution needs explicit authority and identity

That is A2's no-dsn refusal. 8 are the `round-journal` params of
`test_restart_rejects_invalid_charged_resource_projection`, which reach
`drive_improve_round` and hit the same refusal. The rest are the `test_s09c2b_bind`
and `test_binding_provenance` promotion paths.

The brief's separately-named conditions (`test_s89a1_contract`,
`test_invc1_method_envelope`, `test_construction_response_envelope`,
`test_staging_fidelity_crlf`, `test_s09_e2_scored`, `test_s09_e2_replication`) are
not in my gate's file list, so their count is untouched by this lane. I did not
measure them; per the resource policy I left that unmeasured and say so.

## Incomplete

- **No code changed and no commit of code.** The four test names the brief asks for
  were never written, because two of them cannot fail on this base and the other two
  need a dsn threaded into files this lane does not own.
- The JSON document and `save()` are **not** deleted. Deleting them without a
  durable replacement for 23 call sites would destroy restart survival outright.
- The source anchor is **not** moved to `artifacts.py`. It is reachable only
  through `record_evidence` → `_append_evidence` (:1449) and the two
  `_validate_source_anchor` calls (:929, :1174); the only external reference is
  `tests/test_provenance_authority.py:525`. Moving it needs the same missing dsn.
- I did not run the full suite, per the resource policy.

## Recommended disposition

The real defect is the lost-update race, not crash-loss. Repairing it is one lane
with a clear boundary: thread a dsn, an allocation id and an operation id into
`ensure_live_store`, `restart_store`, `bind_live_revision`,
`bind_retained_acquisition`, `drive_arm`, `_admission_views`, `_admit`, `_run_one`
and `fresh_round`, charge through `store.reserve` instead of
`self._doc["used"]`, and make `used` a projection read back from
`store.allocation_free`. That owns `live_construct.py`, `learner_revision.py`,
`scripts/invl02_live.py` and the reservation path — none of which this lane holds.
It should be scheduled as a lane that owns those signatures, and it needs the
A2-style "no dsn means refused" ruling applied to the frontier's own callers,
otherwise the same 12-caller hole reappears under a new name.

The single-owner framing in `reports/workstreams/inv-a.md` §(b) S4/S5 should be
corrected to "frontier authority is a file counter that loses concurrent charges",
and the §(e) L4 crash-loss justification withdrawn, because measurement on this
base does not support it.