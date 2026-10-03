# Source Hut is the source of truth

Two remotes, one tree:

- **git.sr.ht** — the canonical remote. Full history, full tree, every
  archived evidence file. If this machine is lost, clone from here and the
  project is recovered exactly.
- **GitHub** (`RoyCoding8/Stray-repo`) — CI only. Public, because the work
  is intended to be open-sourced once built. Runs the same tree, unmodified;
  nothing is filtered out of it.

## Why tests run on GitHub and not here

The suite needs Linux, PostgreSQL and real POSIX child processes. WSL here
is capped at 3GB / 3 CPUs because six lanes share it, and a lane that runs
the full suite exhausts the host. CI runners have dedicated cores and a
PostgreSQL service container, so the whole suite runs in parallel with
nobody else's tests in the same box.

This host keeps running only the focused gates a lane needs, one file per
process.

## What CI checks

- The collected suite across Python 3.12 / 3.13 / 3.14 against PostgreSQL 18.
- `tests/_heavy_archived/` one file at a time — those spawn real child
  processes and saturate a machine when run together.
- Line endings. `tests/` and `migrations/` must be LF on Linux; a CR byte
  breaks a byte-exact needle in a way Windows cannot see.