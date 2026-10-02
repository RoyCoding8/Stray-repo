# INV-C3 study lane

Lane C3 owns trace export, offline replay and the runnable pilot.
Base is `692af23`. Branch is `wt/inv-c3-study`.
Worktree is `.worktrees/inv-c3`.

## Owned paths

List:

- `scripts/inv01_study.py`
- `experiments/doubles.py`
- `experiments/ad01/records.py`
- `experiments/ad01/cli.py`
- `tests/test_invc3_*.py`
- `reports/workstreams/inv-c3.md`

Lane C3 reads the C1 lifecycle and the C2 envelope. It duplicates neither.

## Export and replay

`records.export_campaign` builds one transition per boundary from durable operations, receipts, settled decisions and episodes.
Each transition carries the packet, the decision, the observation, the episode, operation identities, receipt identities, permitted raw text, configuration identities, unknown exposure and retained digests.
Packets are rebuilt with `packet.decision_packet` from identical inputs. Digests match the live path.

`doubles.recorded_from_export` returns those transitions for `check_replay_prefix`.
`doubles.replay_export` calls the unchanged checker.
No second corpus exists.
Offline replay returns supported only on an exact prefix match.
It returns unsupported with empty results on hidden future, changed dependencies, new code bytes, changed context and version drift.
It returns refused on malformed probes.

`records.verify_byte_chain` checks receipt text against raw responses.
It checks parsed entry against retained source.
It checks retained digest against computed digest.
It checks fresh-process executed source against retained source.
It covers incumbent use with an empty repertoire.

`cli export` writes an export file from a durable campaign.
`cli replay` replays one probe offline with no database.
`cli recompute` recomputes accounting from an export file.
`run` and `resume` accept `--export-out` and emit the same format.

## Pilot

`scripts/inv01_study.py` runs the engineering pilot on recording doubles.
It runs two calibration trajectories on world 0.
It freezes repertoires and policy versions before protected use.
It runs four comparison trajectories on worlds 1 and 2 with matched I and R task sets.
It writes 24 protected use records from fresh subprocesses.
It writes empty-repertoire incumbent use separately.
It enforces per-trajectory and study caps before effects.
It enforces an overall wall clock deadline.
The cap sheet derives from runner request and operation bounds.
Token math stays an estimate. Query ceilings come from explicit budgets.
Estimates, measured use, internal charges and provider billing stay separate.
External requirements report presence only. Values never appear.

## Gates

`tests/test_invc3_export.py` holds 4 passing tests.
`tests/test_invc3_study.py` holds 3 passing tests.
The full lane gate is 7 passing tests on disposable `inv_c3_*` databases.
Doubled runs prove doubled behavior only.
Live inference, containment and billing stay unvalidated.
No old campaign reran. No evidence reset.

## Open work

Live work needs a gateway endpoint, a key and finite construction authority.
The study output names each item as present or missing.
A C1 lifecycle change may require a fresh check of packet rebuild inputs.
