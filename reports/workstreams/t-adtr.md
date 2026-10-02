# T-ADTR workstream report: AD01 trajectory lane

Base `296cb07`, branch `wt/ad01-traj`. Red-first battery on the real
trajectory seam: real PG `ec02test_adtr` (durable campaign/decision
records, never `ec02test_live`), real subprocesses (fresh-process resume),
real T-ADEV controls/seeds/checkers; labeled recording doubles ONLY at
the model seam (`RecordingLearner`, replaying one valid proposal through
the public campaign interface).

## Owned scope

New: `experiments/ad01/trajectory.py` (one deep module: propose, admit,
diagnostic, next-decision, dev episode, campaign entry, PG resume,
repertoire freeze/load, use phase, cost union, protected-use barrier),
`experiments/ad01/cli.py` (one-shot `run`/`resume` for fresh processes,
no poll loop), `tests/test_ad01_traj.py` (20 tests),
`reports/workstreams/t-adtr.md` (this file). No other files touched.

## Design decisions

- One deep module behind the campaign entry. `run_campaign` is the single
  public trajectory entry; propose/admit/diagnostic/episode/resume/use
  are consumed through it, never around it.
- Durability reuses existing settlement tables, no new tables, no new
  migration: campaign = `investigations` row (`admit_commitment`),
  boundary = `attempts` row (`acquire_work`), decision/outcome =
  `attempt_observations` (`submit_observation`), allocation occupancy on
  `ad01-campaign-<cid>`. Resume skip requires non-empty `claimed_ops`
  on the settled boundary record, mirroring the hardened `37a6f7a`
  contract (no receipt-less skip).
- Decision identity is attempt-scoped: kill-at-decision resumes by
  reconciling the pending attempt (same attempt id, no re-acquire);
  kill-after-publication skips settled seqs and runs only unsettled ones.
  Resumed spend replays recorded spend; totals equal a direct run exactly.
- Observations are content-addressed (`obs-<control>-<task>`): the same
  task in both arms yields the same observation id deterministically.
  No-sharing is proved by distinct campaign/attempt attribution, not by
  id non-overlap (an earlier test asserted non-overlap and was wrong;
  replaced with the correct invariant).
- The retained artifact is an executable spec (capability + method +
  params + family scope + qualification), not a reduced instance. Use
  executes the frozen spec with real reducers; no model calls exist in
  the lane, so no reconstruction is possible by construction.
- Protected-use barrier: `admit_investigation` resolves every basis ref
  to its task and refuses tasks outside dev membership as protected-use
  feedback. Agency envelopes reuse frozen `records.make_envelope` /
  `record_intervention` untouched.
- Family router (`software→sw`, `graph→gr`) with per-family diagnostic
  adapters (`diagnostic_resolves` / `novel_order_unproductive`
  normalized). A `want[:2]` shortcut produced `so` and was replaced by
  an explicit tag map after it StopIterated.

## Per-claim table

| Behavior | Production path | Observed run + revision | Live / doubled deps | Countercheck |
|---|---|---|---|---|
| Proposal references actual experience | `propose_investigation` over recorded observations | green | pure | swapped experience changes basis + question |
| Invented basis refused; exploratory admitted | `admit_investigation` vs recorded ids; charter+unknown path | green | pure | ungrounded exploratory (no unknown) refused |
| Diagnostic yields attributed observation | `run_diagnostic` via `_DIAGNOSTICS` onto real `controls` | `preserved-vs-not_preserved` on sw-00 | real frozen task + checkers | unknown diagnostic name raises; stub cannot emit the compound verdict |
| Changed evidence changes next decision; renames do not | `next_decision` from content (task/capability/verdict) only | verdict flip changes question; id rename leaves question+action identical | pure | digest covers content tuple, never ids |
| Construct/check retain/reject/no-candidate | `dev_episode` via real `run_seed` + independent check | retained 14→3 ops preserved; broken rejected with reason; zero budget → incumbent fallback | real reducer + oracle + checkers | `accepted=11` real; tiny budget `accepted=0` |
| Campaign terminates on public entry | `run_campaign` propose→admit→diagnostic→observe→episode | 2 boundaries + explicit stop, `ad01-w0-I-` id | real seams | boundary cap stop observed |
| Kill at decision resumes same campaign | `record_decision` + `resume_campaign` on PG | same cid, same attempt, spend == direct | real PG `ec02test_adtr` | ConflictPayload on re-acquire reconciled, not duplicated |
| Kill after publication resumes w/o dup spend | settled skip via claimed ops | seqs [0,1], queries == direct | real PG | pending (no claimed ops) re-runs, never skips |
| Fresh processes resume via CLI | `cli run` then `cli resume` in two subprocesses | same cid, seqs [0,1], incremental spend exact | real subprocesses + PG | returncode asserted with stderr on failure |
| I + R run one world, no sharing | `run_campaign` I (sw tasks) + R (frozen `r_schedule`) | R order exact; same-task obs ids equal by content; distinct campaign ids | real rotation + reducers | family router + graph adapter added when R hit graph assert |
| Recording double enters through campaign | `RecordingLearner` injected as `propose` | 1 call, boundary on double's task, retained/no-candidate | labeled double at model seam only | double replays valid basis; invented basis still refused |
| Retained episode carries executable spec | `dev_episode` retained output | capability/method/params/scope/authored/qualified_on | pure | spec round-trips through repertoire JSON |
| Use phase: frozen selector, exact bytes, fallback | `freeze/load_repertoire` + `run_use` | 3 records checker-clean; sw selected, gr-transfer incumbent + reason; requested/selected/executed present | real reducer + independent `checker._verify_record` | no member → incumbent; outcome-independent recording |
| Cost union acquisition + use, mechanism separate | `cost_union` | totals == acquisition + use per key; mechanism counts only | pure | mechanism carries no cost keys |
| Agency boundary human vs system | frozen `records` envelope + intervention | set_by tags correct; stop/amend logged with reason | pure (T-ADEV frozen) | mixed-namespace charter/trajectory raise |
| Protected-use feedback refused | admit barrier on dev membership | use-task basis refused with protected-use reason | pure | dev-task basis still admitted |

## Test evidence

`tests/test_ad01_traj.py`: 20 passed. Command:
`python /tmp/ec02-pytest-progress.py /home/ubuntu/AI/Agent-Society-v2/.venv/bin/pytest tests/test_ad01_traj.py -v`.
Regression: `tests/test_ad01_env.py` 30 passed; RPR01
(splits/checkers/reducers/software/graphs) 45 passed. Total 95 green on
tip `296cb07`.

TDD notes: every slice went red-first (missing module, ImportError on
each new entry, AttributeError/TypeError on new seams, live AssertionErrors
on the graph-family path, the content-addressing correction, and the
attempt-scoped identity correction). No slice was implemented before its
test failed.

## Interface change requests (T-ADEV frozen — not edited)

None. All consumption stayed within the frozen surface
(`worlds`/`rotation`/`seeds`/`controls`/`checker`/`benefit`/`records`).

## Integrity notes

- Disposable DB `ec02test_adtr` only (asserted in fixture by name);
  `ec02test_live` never touched. No credentials, gateway config, or
  model names appear in this lane.
- Not merged; no other branches touched.
