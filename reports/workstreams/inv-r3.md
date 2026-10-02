# inv-r3 export plus verify

Branch `wt/inv-r3-export`. Base `8d2b2a5`. Scope `experiments/ad01/records.py`, `tests/test_invr3_export.py`, this note.

## Change

`_seq_ops_for` selects the learner base plus the `-c` correction suffix and the campaign-prefixed `-b<seq>-` boundary marker. `model_so_far` counts every learner attempt. Each transition now carries `corrections`, `delivered_requests`, and `packet_source` set to `reconstructed`. Identities now pin `source` with `git_sha` plus `export_version` and `effective` with model, charter, caps, `reasoning_effort`, packet version, protocol, profile, freeze id, and freeze digest.

`recompute_from_corpus` counts model calls from operation payload effects and witness totals from episode plus use costs. It preserves unknown costs instead of writing zero. `verify_campaign` checks frozen membership, contiguous phases, one record per identity, receipt attribution, delivered coverage, correction counts, reported totals, and retained bytes through `verify_byte_chain`. Missing evidence returns `incomplete`. `verify_study` checks exact campaign membership and aggregates the per-campaign verdicts.

## Gates

Real PostgreSQL 16. Test database `inv_r3_export`. Probe database `inv_r3_probe` was dropped after use.

- ` .venv/bin/python -m pytest tests/test_invr3_export.py -q` gives 11 passed.
- ` .venv/bin/python -m pytest tests/test_invc3_export.py -q -k "not cli_export"` gives 3 passed.
- ` .venv/bin/python -m pytest tests/test_inv_c_qualification.py -q -k "replay or envelope or rejected"` gives 4 passed.
- `tests/test_invc3_export.py::test_cli_export_and_offline_replay` fails on base and on this tree with `No module named 'fault_tasks'` in the CLI subprocess. The failure predates this change.

## Tamper matrix

Valid pilot holds one correction campaign with retained plus incumbent fallback use. The verifier returns `pass` and the recomputed model total matches an independent database count of 5.

- Remove one use record gives `fail` with `missing-use-record`.
- Remove one transition pair gives `fail` with `missing-transition`.
- Duplicate one use record gives `fail` with `duplicate-record`.
- Set one episode query total to 999999 gives `fail` with `query-total-mismatch`.
- Omit the `learner-0-c1` receipt and raw response gives `fail` with `missing-receipt`.
- Remove one export from a two-export study gives `fail` with `missing-trajectory`.
- Pass `None` use evidence or an empty export gives `incomplete`.

## Gaps

The CLI `export`, `recompute`, and study runner in `scripts/inv01_study.py` still call the old producer summary. This tree does not touch that path. The coordinator needs to wire those entries to `verify_campaign` and `verify_study`. No live provider run happened here. Doubles report billed false. The pre-existing CLI import failure needs an owner.
