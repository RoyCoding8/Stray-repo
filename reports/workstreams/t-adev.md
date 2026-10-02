# T-ADEV workstream report: AD01 environment lane

Base `fa777d5`, branch `wt/ad01-env`. Model-free lane: no DB seam exists in
this scope (disk + pure in-memory checks only), so no PG tests; no model
inference seam exists, so no doubles. Determinism is proved in real
subprocesses. Disposable DB `ec02test_adev` was never needed and never
touched; `ec02test_live` never touched.

## Owned scope

New: `experiments/ad01/` (`worlds.py`, `rotation.py`, `seeds.py`,
`controls.py`, `checker.py`, `benefit.py`, `records.py`),
`experiments/ad01/worlds/` (54 task JSONs + `manifest.json` +
`manifest.sha256`, freeze id `ad01`), `tests/test_ad01_env.py` (30 tests).
Appended one AD01 section to `experiments/representation/splits.py`
(generators + `ad01_content_key`); no existing function touched, no RPR
fixture regenerated, RPR manifest bytes untouched. Nothing under
`experiments/representation/fixtures/` was added: the AD01 freeze lives
entirely under `experiments/ad01/worlds/` with its own manifest + hash, so
the existing panels cannot be disturbed.

## Design decisions

- AD01 tasks reuse the `representation-01/1` task semantics with fresh AD01
  seed streams (sw dev 5101 / sw use 5301 / gr dev 5201 / gr use 5401, +
  world*100 + index). Seed formula is re-derived by the audit.
- Within-scope use reuses development templates with fresh seeds;
  structural-transfer uses disjoint templates (software: 3-deep overwrite
  chain, del-in-core; graphs: C9 / shared-edge / joined-by-path only).
- The audit, not the generator, owns separation: generation asserts
  validity; `audit_tasks` asserts disjoint content, template separation and
  seed regeneration. When the audit fired on two real graph collisions
  (C5+tree has few distinct small witnesses), the fix was a salted
  resampling loop inside the generator that keeps seeds stable and conflict
  content out, converging callers on the single `ad01_content_key`.
- Unknown measurements use the explicit `"unknown"` sentinel. An
  `unknown` verdict with all-numeric measures is rejected as
  `unknown-scored-as-zero`: an unmeasured outcome must not be recorded as
  zeros. Costs with `"unknown"` are accepted and force an `unevaluable`
  benefit verdict.
- Benefit rule is a declarative dict (`benefit.BENEFIT_RULE`) with a
  content digest pinned in the worlds manifest (`benefit_rule_digest`).
  Validity/solved rules apply per domain; reduction and cost rules apply
  to totals, per §7 wording.

## Per-claim table

| Behavior | Production path | Observed run + revision | Live / doubled deps | Countercheck |
|---|---|---|---|---|
| Freeze byte-deterministic across processes | `worlds.build_freeze` in two fresh `python -m` subprocesses, byte-compare of all 57 files | green at working-tree rev (30/30) | real subprocesses, real disk | `verify_committed` fails on any drift; manifest hash mismatch short-circuits |
| No dev/use leakage; within/transfer separation; seed derivation | `worlds.audit_tasks` over committed freeze: content keys, template sets, seed formula + regeneration | audit fired on 2 real collisions pre-fix, clean post-fix | pure + real disk reads | planted leak / relabeled template / bumped seed each flagged |
| R rotation exact, all 3 worlds | `rotation.r_schedule` derived from manifest dev membership, alternating domains, fixed index order | green | pure | covers-dev-set-only test; golden id vectors pin naming + order |
| Seed repertoire labeled authored | `seeds.SEED_CAPABILITIES` (ddmin/greedy x sw/gr) + `run_seed` adapter over supplied reducers | green; all four yield checker-`preserved` candidates | real reducers + oracles, in-memory | unknown capability / family mismatch raise `KeyError` |
| C0 evidence-path base | charter + identities fixed; incumbent vs broken candidate through `ledger_query` | changed=True, label_stable=True | real checkers | same-candidate probe changed=False; label smuggled into content flips verdict |
| C1 cheap suffices | seed greedy on dev task within budget | accepted=11, reduced, floor 6 | real reducer + oracle | max_queries=1 gives accepted=0, no reduction |
| C2 dependency invalidates naive deletion | 3-chain transfer task: bulk chain drop vs single-distractor drop | not_preserved/witness-lost-agree vs preserved | real checker | dropping two distractors still preserved |
| C3 novel direction unproductive | reversed-priority greedy vs domain-aware, budget 8, on dev-gr-02 | novel final 14 vs seed 10, both preserved | real reducer + oracle | full budget converges equal; rigged comparator reports novel-wins |
| C4 diagnostic resolves uncertainty | chain+witness keep-only vs prefix-only keep-only | preserved vs not_preserved | real checker | nondiagnostic verdict proves discrimination |
| C5 prior negative blocks repeat | `NegativeLedger` + `prior_negative` with JSON persistence | repeat refused, 0 budget consumed, survives reload | real disk (tmp), real oracle once | novel candidate proceeds and consumes budget |
| Checker rejects bad records | `checker.verify_use_records` over 72-cell I/R x worlds x use sets | altered/missing/duplicate/wrong-freeze/unknown-as-zero all rejected; complete set clean | real disk + independent checkers | each mutant targets one rejection; clean set proves no false positives |
| Benefit rule frozen + evaluated | `benefit.BENEFIT_RULE` + digest in manifest; `evaluate` on real-reduced records | benefit / no-benefit on tie / no-benefit on solved-loss / unevaluable on unknown cost | pure | improved records verified checker-clean before evaluation |
| Agency surface | `records.make_envelope` / `record_intervention`, disjoint namespaces + set_by tags | green; interventions carry mandatory reason on human side | pure | mixed/unknown fields raise; JSON roundtrip stable |

## Test evidence

`tests/test_ad01_env.py`: 30 passed. Command:
`python /tmp/ec02-pytest-progress.py /home/ubuntu/AI/Agent-Society-v2/.venv/bin/pytest tests/test_ad01_env.py -v`.
RPR regression: `test_rpr01_splits/checkers/reducers/software/graphs`
45 passed — the `splits.py` addition is purely additive.

TDD notes: every slice went red-first (missing module, then missing
freeze files, then audit findings, then kwargs collision, then a
record_id typo). The audit's two collision findings were genuine
generator output, fixed by salted resampling with stable seeds rather
than by weakening the audit.

## Interface for T-ADTR

- `rotation.full_rotation()` / `r_schedule(world)`: frozen R order.
- `seeds.SEED_CAPABILITIES` / `run_seed(capability, task)`: labeled
  authored repertoire.
- `checker.verify_use_records(records, worlds.FROZEN_DIR)` and
  `benefit.evaluate(records)`: independent recheck + verdict.
- `records.make_envelope(charter, trajectory)`: agency-boundary schema;
  T-ADTR drives population. Trajectory orchestration is T-ADTR's; the
  schedule here is data only.

## Integrity notes

- During S4 an unrelated edit session appended foreign test blocks to
  `tests/test_ad01_env.py` (duplicate names, undefined helpers,
  `provenance` field my schema does not define). Removed verbatim;
  file verified to contain exactly the 30 owned tests before commit.
- No credentials, gateway config, or model names appear in this lane.
- Not merged; no other branches touched.
