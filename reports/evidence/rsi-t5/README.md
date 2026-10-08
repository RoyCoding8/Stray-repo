# T5 bank evidence

The run imported 34 Python exercises from the local checkout at
`D:/AI/tools/polyglot-benchmark`, revision
`7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f`.

[bank-report.json](bank-report.json) records the content-addressed bank, each
task, its fixed split, reference/stub operations and solution snapshots. All
34 reference solutions passed their pristine tests and all 34 stubs failed.
There were no model calls. The split has 18 dev, 5 validation and 11 anchor
tasks. The bank digest is
`fe81ef1f56941acf910ca7f1ee9a53ac168bfc05e985938d1e70fffe972f5f43`.

The durable operation receipts, frozen task packages, index and solution
snapshots remain in database `rsi_t5` on local PostgreSQL port 55432 and in
`D:/AI/tools/rsi-t5`. This summary does not replace those receipts. To inspect
a recorded operation, use `settlement.store.operation_receipts(dsn, id)`;
each report entry names its operation. The artifact `art/<bank digest>`
contains the frozen `index.json` and its task/evaluator digests.

These were real bounded Python subprocesses, not fake verifier results.
Fake-Codex tests separately check the episode-to-verdict plumbing. Neither
result demonstrates learning, transfer or self-improvement. The local verifier
does not provide filesystem or network containment against hostile solutions.
