# P04 live attempt 2

The manifest was committed at `b058499c` before execution, after independent
review of source `d18c67a5`. The configured inference route was exactly
`openrouter/openrouter/free`. The constructor ran through the real Codex
launcher and timed out at its 180-second limit.

There was one constructor invocation, one settled failure receipt, no candidate,
no check, no retention and no later method use. The trace contains 15 completed
shell commands, seven of which failed. Several used Unix or cmd syntax in
PowerShell, or malformed quoting. These observations describe this attempt;
they do not establish general model incapacity or a provider outage.

Token usage is unknown. The kernel charged the 100,000-token reservation ceiling,
not measured model usage. Both allocations have zero reserved units. Provider
billing was not independently measured. No paid route was configured.

The original report is preserved byte-for-byte. Its older driver mislabels the
timeout `no-acquisition`. The corrected checker derives `unscored` from the
failure receipt and captured constructor evidence, retaining the reported label
in its output. It establishes no acquisition or task-capability verdict.

Recompute without gateway or database access:

```text
python experiments/capability04/check.py experiments/capability04/evidence/live2
```

The database `p04_live_20261014b` on local port 55432 and private runtime
`D:/AI/tools/p04/live2/` remain evidence anchors. Credentials and constructor
configuration are not committed. Native execution is cooperative and uncontained.
No P04 learning advantage or broad transfer is claimed.
