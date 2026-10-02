# Archived tests: real child processes

85 test files moved here on 2026-09-29. Each one spawns actual child
processes (`Popen`, `LocalLauncher`, `run_local_process`, `preexec_fn`,
`setrlimit`) and a full run of all of them saturated the host.

They are not deleted and not failing. They are excluded from a default
collection because the cost is CPU and memory, not correctness.

## Running them

Deliberately, one file at a time, never as a suite:

    uv run pytest tests/_heavy_archived/test_<name>.py -q -p no:cacheprovider

The subdirectory is not on the default `testpaths`, so `uv run pytest` with
no arguments will not pick these up. That is deliberate.

## What stays in tests/

Ten files also spawn children but are load-bearing and stay collectable.
Three of them (`test_d02live_episode`, `test_dev02_episode`,
`test_eng_close1`) import `test_dev01_episode` / `test_r02_authority`
directly, and `test_s09_n203_dispatch_ceiling` imports
`test_s09_controls`, so moving the imported module would break the importer.
The other six are the child-limits and staging regressions, which are the
fast check for whether an execution-path fix actually holds.
