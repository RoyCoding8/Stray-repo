# inv-h5: residual verification sweep for ag01 and r03 suites

## Verdict

Both suites pass fully on this tip with correctly provisioned databases. No residual environmental failure remains. No code change was made.

## Tip

`adb7161` on branch `wt/inv-h5-residual`. Worktree `/home/ubuntu/AI/Agent-Society-v2/.worktrees/inv-h5`. No `src/**`, `experiments/**`, `scripts/**`, or test edits.

## Results

`tests/test_r03_flow.py`: 9 passed in 25.90s.

`tests/test_ag01_experiment.py`: 37 passed in 161.68s.

## Commands

Provisioning used peer auth over the local socket with URL form DSNs. The base for r03 was a disposable database. The base for ag01 was the documented suite default.

```sh
psql -h /var/run/postgresql -U ubuntu -d postgres -c 'CREATE DATABASE "inv_h5_r03";'
SETTLEMENT_TEST_DSN='postgresql://ubuntu@/inv_h5_r03?host=/var/run/postgresql' PYTHONPATH='/home/ubuntu/AI/Agent-Society-v2/.worktrees/inv-h5/src' /home/ubuntu/AI/Agent-Society-v2/.venv/bin/python -m pytest tests/test_r03_flow.py -q
SETTLEMENT_TEST_DSN='postgresql://ubuntu@/agenda01_exp?host=/var/run/postgresql' PYTHONPATH='/home/ubuntu/AI/Agent-Society-v2/.worktrees/inv-h5/src' /home/ubuntu/AI/Agent-Society-v2/.venv/bin/python -m pytest tests/test_ag01_experiment.py -q
```

## Cleanup

Dropped the base created for this sweep.

```sh
psql -h /var/run/postgresql -U ubuntu -d postgres -c 'DROP DATABASE IF EXISTS "inv_h5_r03";'
psql -h /var/run/postgresql -U ubuntu -d postgres -c 'DROP DATABASE IF EXISTS "agenda01_w08v0_r_t0";'
```

`agenda01_w08v0_r_t0` was the one leftover from the passing ag01 run. The `_fresh_db` helper in `tests/test_r03_flow.py` creates `r03flow_dom_*`, `r03flow_wf_*`, and `r03flow_wft_*` databases with random suffixes and leaves them behind. Those stems belong to the suite. This sweep left those suite-stem databases in place and dropped only the named bases above.

## Observation outside allowed edits

`test_duplicate_effect_decisions_charged` in `tests/test_ag01_experiment.py` keeps its trajectory database and then drops `f"agenda01_{trace['db']}"`. `trace["db"]` already holds the full `agenda01_w08v0_r_t0` name from `runner.run_trajectory`, so the drop targets a doubled name and misses. The tests still pass. The miss only leaves one disposable database behind. This file is limited to prerequisite-pattern edits for this lane, so the finding is recorded here and the line is unchanged.
