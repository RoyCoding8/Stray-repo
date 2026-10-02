# M2 post-live join: the construction chain closes, the use chain does not

`inv_r1_m2_join`. Line 53 of `WORKER-STAGE-09-CONNECTED-STUDY.md`: after live
execution, "join each policy artifact and each task method to its own receipts
and byte identity, then join policy actions to their effects. Digest diversity
is neither necessary nor sufficient." Line 51 requires the retention/reload
proof "in a fresh process".

Both were built, offline, from the committed run-7 and run-8 evidence. One
closes. One cannot, and the reason is a finding rather than a gap in the work.

- `join.json` — 71 operation rows, 2 method rows, 4 repertoire-member rows.
- `reload_proof.json` — 3 cases, 21 checks, 0 failed, verdict `reproduced`.

Regenerate with `python3 experiments/ad01/s09_m2_join.py` and
`python3 experiments/ad01/s09_m2_reload_proof.py`. Both are byte-identical on
rerun.

## What joins

**Every operation has its own receipt.** All 71 operation rows across both runs
carry at least one receipt, keyed on the `operation_id` the receipt itself
holds. A receipt identity is launcher-prefixed (`gw:` for the gateway, `local:`
for the local-process sandbox), so the join does not reconstruct it by string
surgery. Where a `raw_responses[].digest` also exists, all 56 agree with
`sha256` of the receipt text. Zero mismatches.

**Both acquired methods join to the model call that wrote them.** This is the
chain line 53 asks for, and it verifies end to end for each method:

| run | capability | construct receipt | declared lineage op | agrees |
|---|---|---|---|---|
| `inv_r1_m3_run7` | `acquired-sw-2074657c` | `gw:…-b1-ad01-w0-dev-sw-00-construct-l1-init` | same | yes |
| `inv_r1_m3_run8` | `acquired-sw-5b65c917` | `gw:…-b1-ad01-w2-dev-sw-02-construct-l1-init` | same | yes |

The chain is: the receipt's response text parses to a construction response
whose `entry` field is the method source; the sha256 of that source equals both
`retained_bytes[].source_digest` and the repertoire member's `source_digest`;
and the member id's trailing eight hex re-derive from that digest under
`construct.FAMILY_TAG`. Every step is recomputed by the script, not trusted.
`retained_bytes` carries no operation id of its own, so the link is recovered by
matching content and then confirmed against the member's declared
`construction.init_operation` — the two agree independently.

**Unknown exposure is carried, not dropped.** Six operations across the two
runs have an `:lost-response` receipt whose outcome is `unknown`, and all six
appear in the matching export's `unknown_exposure`. The join records the
receipt, its `response_digest`, and `response_received`, and does not resolve
the uncertainty into a fabricated response.

## What does not join, and why

**The use phase has no receipts at all.** Run 8 is the only run with executed
use records, three of them, and each declares one operation id:

```
ad01-ad01-w2-I-00-use-ad01-w2-within-sw-00-acquired-sw-5b65c917
ad01-ad01-w2-I-00-use-ad01-w2-within-sw-01-acquired-sw-5b65c917
ad01-ad01-w2-I-00-use-ad01-w2-transfer-sw-00-acquired-sw-5b65c917
```

None of the three appears in any committed export, and a repository-wide search
finds the ids only inside `use_records.json` itself. So the three records that
carry the study's only executed capability are the three with **no receipt**.

This is not a search failure. The ids are minted by
`selection.versioned_use_op_id`, and `trajectory.py:1481` passes them to
`method_exec.run_member_out_of_process` as `operation_id`, which is the path
that calls `broker.ensure_operation` and `broker.dispatch_operation` and
persists a receipt. The run 7 and run 8 stores
(`s09iso_m3run7_c4642aac7359`, `s09iso_m3run8_ef70d43f4552`) were dropped at
teardown and are not on the cluster. Every export was written during the
trajectory phase and contains no use-phase row. So the receipts existed in the
store and the committed evidence does not carry them.

The consequence for line 53 is exact: **the join between a task method and its
own receipt is complete for acquisition and absent for use.** 3 of 60 use
records (run 7's 24 and run 8's 36) name a method, and all 3 lack a receipt.
The other 57 were refused before reaching execution, so they have nothing to
join.

## The fresh-process reload proof

`reload_proof.json`. Three cases, one per executed use record, all built from
the committed evidence rather than hand-listed.

Each case writes the member's `method_source` to its own file, and a
**subprocess with a scrubbed environment** reads that file, rebuilds the task
from the frozen world, and re-executes through the real bounded executor
`method_exec.run_member_out_of_process`. The subprocess is a separate
interpreter from the one that wrote the artifact, which is what "fresh
process" has to mean: a proof that only holds in the writing process proves
nothing about durability.

**No dispatch occurred.** The executor is called with no `dsn`, which is the
branch that runs the local launcher and reads the receipt back from it.
`authority.admit_study_call` and `broker.dispatch_operation` are not called, no
database is opened, and no gateway is contacted. Line 53's requirement of stores
and namespaces separate from live is met by opening none. Verified after the
run: zero `s09iso*` databases exist on the cluster, and `ec02test_live` was
never contacted.

All 21 checks agree. Per case: `source_digest`, `queries`, `initial_measure`,
`final_measure`, `normalized_reduction`, `verdict`, and byte equality of the
re-derived effect against the committed `output`.

**The proof is not vacuous.** Changing `ddmin` to `greedy` in the member's
bytes changes the reloaded `source_digest` from `5b65c917…` to `44721933…`,
makes `effect_equals_committed_output` false, and moves `final_measure` from 3
to 10. The comparison discriminates on the bytes, so passing means something.

## What this is not

This closes **M2's deterministic qualification and join requirement**. It does
not close SWE transfer, which line 47 puts outside M2's scope, and nothing here
supports a claim that a retained policy transfers. The reload reproduces three
executions of one method on two within-world tasks and one same-world transfer
task. It is a durability result, not a generalisation result.

Run 7 contributed one acquired method and zero executed use records. Run 8
contributed one acquired method and three executions. The 30 model calls and 36
use records in run 8 are dominated by 33 refusals, which the run's own
`RESULT.md` attributes to empty repertoires and one scope mismatch. That is
acquisition yield, and it is a different measurement from this join.

## A different defect, recorded and not fixed

`reports/evidence/inv_r1_m3b/repertoires/control-sw.json` declares two members,
`seed-sw-ddmin` and `seed-sw-greedy`, with different `source_digest` values
(`e2ca3cf1…` and `0ba85e81…`) but **byte-identical `method_source`**, and
neither digest equals `sha256(method_source)` of the text in the same record.
Both fail the byte-identity check in `join.json`
(`byte_identity_verified: false`). This is already recorded as N-77 in
`reports/STAGE-09-RETIRED-EVIDENCE.md:44-48`, and it is consistent with
`seed-sw-greedy` having been added to that repertoire at `18:57`, after the
freeze digests in `manifest.json` were taken. Not fixed here, and no artifact
under `reports/evidence/` was modified.

A second observation, smaller: the two control repertoires would fail any join
on byte identity regardless of receipts, because the control arm is not
byte-distinct from the acquired arm. Any future comparison of acquired against
authored control must join on more than the source digest.
