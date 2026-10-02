# Workstream inv-learning02-m4: prospective comparison, auditable lineage

Owner: m4-offline lane. Branch `wt/m4-offline`. Base `d10c471`.
Scope: this report, `experiments/ad01/offline_recompute.py`,
`tests/test_m4_offline_recompute.py`,
`reports/evidence/invl02-e1e2/` protocol and harness docs only.
No broker, gateway, executor, pilot, verifier, M0 or other lane edits.

## Task list

1. Confirm red with tamper-first tests. Done, collection error on the
   missing module before implementation.
2. Implement deterministic offline recomputation. Done, stdlib only.
3. Prove green plus isolation. Done, 13 passed, scrubbed env run done.
4. Freeze protocol, splits, comparison rule. Done in PROTOCOL.md.
5. Jev prospective comparison before freeze. Done, both accepted.
6. Hygiene, commit, push. See below.

## Decisions

The bundle embeds frozen tasks so recomputation needs no database.
Quality is data comparison of observed versus expected, with no
candidate execution in the trusted process. Resource classes follow
the architecture vector. Recountable classes are checked exactly.
Attested-only classes are type checked and reported. Billing unknown
stays unknown by rule, not by convention. Unavailable arms are honest
records, never problems, while substitution is a hard failure.

## Gates

`tests/test_m4_offline_recompute.py`: 13 passed in 0.17s, repeated
under `env -i` with identical result. Tamper identity, content,
membership, costs and results each fail under a distinct problem name.
Swapped candidate, disconnected artifact and forged witness are
refused. Reversed order reservation matches. Unavailable arms report
incomplete with no winner, and the cheating variant is refused.
JSON file round trip passes.

## Gaps

Consistent forgery of both observed and claimed bytes passes offline
checks and needs re-execution to catch. Token, compute and billed
magnitudes are attested, not measured. The live E1/E2 run through the
shared runtime is outside this lane and remains future work.

## Jev disposition

`reports/jev/invl02-m4-request.json` and
`reports/jev/invl02-m4-response.json`. Order control accepted at
confidence 1 with no code change. No substitution accepted at 0.92
with the consistent-forgery residual ledgered above. Jev is opinion,
not proof. Proof is the reversed-order test, the ceiling test and the
unavailable-arm tests in the gate.

## Hygiene

Disposable namespace `invl02_m4` only, used as a study-root label with
no database created. Scratch at `/tmp/opencode/m4-offline` was never
created. Jev staging files under `/tmp/opencode/m4-jev-*` are removed
before commit. No secrets entered prompts, commands, reports or Git.
