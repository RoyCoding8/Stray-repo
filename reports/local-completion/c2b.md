# C2B local completion

## Scope

The lane owns the binding boundary in `experiments/ad01/selection.py`, the assessment cache guard in `experiments/ad01/records.py`, the release-scoped use regression, and this report. No `_run_boundary` or campaign-loop code was changed.

## Findings and repairs

- `_bound_member` accepted a member with no `source_digest`, then `run_use` executed bytes different from the assessed frozen candidate. It now requires the member digest and the SHA-256 digest of `method_source` to equal the bound candidate digest.
- `assess_frozen` persisted a zero-task assessment and silently returned a cached assessment when protocol, evaluator, or task identity changed. It now rejects an empty task panel and conflicting cached identity.
- `bind_revision` accepted a caller-chosen journal request alias. It now derives a canonical request id from the full binding provenance and rejects a different caller id.
- `bind_revision` now requires the requested protocol to equal the revision proposal protocol.
- `assess_frozen` now uses the proposal protocol before cache identity comparison, so repeated calls that omit the default protocol reuse the same assessment.
- The CLI `use --release` flag is optional again. With no release, execution uses the repertoire-scoped member path; with a release, it keeps the pinned binding path.

## Evidence

The new selector regression was red before the production repair. The pre-fix run accepted a member whose source bytes differed from the assessed digest and whose digest was absent. After the repair, `tests/test_s09c2b_bind.py::test_selector_rejects_unverified_member_bytes` passed. Windows `py_compile` passed for the changed production and test files. `git diff --check` passed.

Jev classified the current verification as `partial` with probability 1.0. The result is evidence only.

The C2B PostgreSQL and child-process gate passed with 17 tests in 23.54 seconds under PostgreSQL 18.6. The adjacent binding and sealed-visibility migration gate passed with 23 tests in 26.00 seconds after migrating label-only fixtures to carry frozen source bytes and digests. The older `/tmp` runtime failure is superseded by the persistent coordinator runtime at `/home/ubuntu/.venvs/as9/bin/python`.

## Remaining gate

Run as `ubuntu` from WSL after the shared runtime is available:

```text
PYTHONPATH=$PWD:$PWD/src:$PWD/experiments /tmp/as9-venv/bin/python -m pytest tests/test_s09c2b_bind.py -q -p no:cacheprovider
```

The suite owns only `s09_c2b_*` databases. C1 and merged-stack verification remain outside this lane.
