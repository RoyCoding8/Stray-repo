# P04 live attempt 1

This freeze was committed at `69716d9f` before execution. The source was
`ba95df09`. The operation was never sent, with zero settled receipts and zero
consumed or reserved units. No candidate was constructed or checked.

The installed Codex catalogue no longer includes the launcher's default
`gpt-5.4` metadata template. A local `codex debug models` inspection returned
11 entries and confirmed its absence. This is a launcher compatibility failure,
not evidence about the free model's capability.

The driver records `unresolved`; the offline checker preserves that status and
checks zero uses. The exported operation records the stronger durable fact that
it was reconciled with never-sent proof. It must not be rerun as a new study.
The dedicated database is `p04_live_20261014a` on local port 55432.

Recompute without model or database access:

```text
python experiments/capability04/check.py experiments/capability04/evidence/live1
```

Only the manifest and report are public. The route settings and constructor
configuration remain private. Native execution is cooperative and uncontained.
