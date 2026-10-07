# CI

Two remotes, one tree:

- **git.sr.ht** (`origin`) is the canonical backup.
- **GitHub** (`RoyCoding8/Stray-repo`) runs CI on every push.

`.github/workflows/ci.yml` runs:
- the suite against PostgreSQL 18 on Ubuntu, in two shards
- the suite without a database on Ubuntu, macOS and Windows
- `tests/_heavy_archived/` on Ubuntu, one file at a time
- an LF check on `tests/` and `migrations/`

Each job uploads `failures.txt`. To compare two runs, download both
(`gh run download <id>`) and diff the files. A skip is not a pass: check
`-rs` output before you call a platform covered.
