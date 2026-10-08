# Archived tests: real child processes

85 test files moved here on 2026-09-29. After retiring study-layer tests,
22 files remain. Each one spawns actual child
processes (`Popen`, `LocalLauncher`, `run_local_process`, `preexec_fn`,
`setrlimit`) and a full run of all of them saturated the host.

They are excluded from a default
collection because the cost is CPU and memory, not correctness.

## Running them

Deliberately, one file at a time, never as a suite:

    uv run pytest tests/_heavy_archived/test_<name>.py -q -p no:cacheprovider

The subdirectory is not on the default `testpaths`, so `uv run pytest` with
no arguments will not pick these up. That is deliberate.
