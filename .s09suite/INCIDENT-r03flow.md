# The 345 `r03flow_*` databases are gone

Observed 2026-09-29. At 08:19 UTC this lane counted 345 `r03flow_*`
databases. At 09:20 UTC it counted 0. The PostgreSQL log shows a burst of
~711 `FATAL: database "..." does not exist` at 08:27:56, which is when they
went.

## What this lane did, and did not, do

Two reclaim passes were run in this lane, both restricted by a SQL pattern
to `^s09iso_5e9[ab]` -- my own run tokens, 79 databases in total:

    select datname from pg_database where datname ~ '^s09iso_5e9[ab]'

That pattern cannot match a name beginning `r03flow`. The reclaim script
printed `REFUSING` for any name containing `r03flow` and had a `case`
guard that would have skipped one.

## What this lane proved cannot have done it

`tests/conftest_isolation.py`'s `sweep_stale` selects only names matching

    DERIVED_NAME_RE = \As09iso_([0-9a-f]{8})_[A-Za-z0-9][A-Za-z0-9._-]*\Z

Verified directly: `derived_token("r03flow_dom_ab12cd34")` is `None`, and
the regex does not match. The rule is byte-identical at `633d3fb` and at
`c92c760`; the commits between them did not loosen it.

## The window

Another lane committed into this same worktree five times between 09:04 and
09:15 (`ef76f7b`, `84f76a3`, `ba70e89`, `2f24c8b`, `c92c760`), and the drop
window (08:27) sits inside the period that lane was working. This lane
cannot attribute the drop to a specific process: `log_statement` is `none`
on this server, so successful `DROP DATABASE` statements are not recorded.
The only `DROP DATABASE` lines in the log are six failures from 09-28
("cannot run inside a transaction block").

## Why it matters

`TASKS.md:164` records these 345 as evidence, "not garbage", deliberately
not reclaimed. `reviews/STAGE-09-SUITE-AFTER.md:456` counted them at 345
"after every run in this session. Untouched." That claim is now false
against the live server.

## The defect this exposes

A reclaim that is safe by name-shape still needs an audit trail, because
"the guard cannot have fired" and "the databases are still there" are
different claims and only one of them is checkable after the fact. On a
server with `log_statement=none` there is no way to answer the second
question from the server. The 08:27:56 `FATAL` burst carries corrupted
`datname` values with `pg_stat_file` columns appended
(`agenda01_demo|ubuntu|UTF8|libc|...`), which is the signature of a
conninfo built from `_latest_modification`'s tuples rather than their
names -- a caller iterating that function's rows and using row[0] as a
database name would not raise, it would connect to a name that does not
exist. That is a hypothesis about the mechanism, not an established one.
