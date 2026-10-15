# P05 bounded live comparison

Prospective freeze was committed at `260b0044` before model effects. Source pins
refer to `5c5a4370`, whose runtime was independently reviewed at `7f59a909`.
The route was exactly `openrouter/openrouter/free`. Each arm had one catalogue
availability check, a separate database and resource roots, at most three choices,
90 seconds per selected action and a 5,000-token admission ceiling. The initial
lesson in both arms is **authored-from-scripted-pristine-example**. It is not
model-acquired evidence.

## Observed result

Both arms selected `source`, invoked the real installed Codex worker once and
returned pending after a settled `over_budget` failure receipt. Both retain their
original flight. Neither obtained a pristine task verdict or a feedback trigger.
Offline recomputation returns **incomplete**, one unscored choice per arm, no
feedback effect and no different selections. This is neither a task tie nor a
capability failure.

| Arm | Worker seconds | Completed shell commands | Reported input tokens | Reported output tokens |
| --- | ---: | ---: | ---: | ---: |
| Seed | 29.6 | 6 | 93,921 | 1,129 |
| Adaptive | 48.6 | 9 | 187,368 | 1,540 |

These are worker-reported cumulative usage fields, including repeated context;
cached input and reasoning breakdowns remain in the original receipts. The worker
returned task edits, but its completion messages are self-reports, not pristine
verification. The 5,000-token ceiling was too small for the actual multi-command
Codex workload. It rejects over-budget completion; it is not a provider-enforced
preemption limit on physical token consumption.

Each token root settled the 5,000-unit reservation by the explicit unknown-charge
fallback. Each CPU root consumed 111 units for the authored prior's verifier.
All four roots have zero reserved units. These charged amounts are distinct from
the reported usage above. No independent provider-billing measurement was made.
The two live operations will not be rerun or granted larger limits under this
freeze. Their pending agenda continuations remain attributable to the original
decisions; settled failure does not become a checked task result.

## Reproduction and boundaries

Run from the repository without a database or gateway:

```text
python -m experiments.agenda05.check --manifest experiments/agenda05/evidence/live1/manifest.json --report experiments/agenda05/evidence/live1/seed.json --paired-report experiments/agenda05/evidence/live1/adaptive.json
```

`recomputed.json` is the recorded output. Raw arm exports include task and genome
packages, captured artifacts, decisions, operations, receipts and resource rows.
The checker verifies consistency of attested runtime exports; it does not
authenticate the provider or coordinated export forgery. No acquisition, useful
later use, transfer or learning advantage is claimed. Native children are
cooperative and uncontained.

Local evidence anchors are `p05_live_20261015_seed` and
`p05_live_20261015_adaptive` on the local PostgreSQL 18 server, with run files under
`D:/AI/tools/p05/live1`. Keep these anchors while the continuations are pending.
