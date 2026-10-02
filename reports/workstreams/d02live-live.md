# Workstream report: DEVELOPMENT-02-LIVE live inference (Responses API)

Branch: `codex/implementation-development-02` (work on top of `976cee1`).
Model: live model via `/v1/responses` at `http://localhost:6446/v1`
(`SETTLEMENT_GATEWAY_API=responses`, key from `META_API_KEY`;
exact model id in the entry evidence). Launcher `local --allow-uncontained`
(explicit; runsc binary absent so real containment still unverified).
Budgets: `SETTLEMENT_MODEL_TOKENS=8192`,
`SETTLEMENT_PACKET_BUDGET_CHARS=65536` (A-ep-05/C-ep-04 only),
read 300s / total 1200s gateway timeouts, 10M-unit grant caps.
Three isolated DBs (`settlement_live_{a,b,c}`), one episode each.

## Adapter changes (both APIs kept)

- `src/settlement/gateway_http.py`: `HttpGatewayAdapter(..., api="chat"|"responses")`
  (default `"chat"` — chat-completions behavior byte-identical; unknown
  api fails closed). Responses path posts `{model, input, max_output_tokens}`
  to `{endpoint}/responses` and decodes `output[]` message/`output_text`
  (plus `refusal`) parts, `completed→stop`, `incomplete/max_output_tokens→length`,
  `failed/cancelled→PROTOCOL` errors, `input_tokens/output_tokens` usage.
  Provider reports no billable charge (`cost: "0"`, no `charge_units`),
  so responses usage settles token counts with charge 0 / unbilled.
  `gateway_timeout_overrides()` reads
  `SETTLEMENT_GATEWAY_TIMEOUT_{CONNECT,READ,TOTAL}_MS` (defaults
  5s/60s/300s, fail-closed on garbage).
- `src/settlement/experiment.py`: `model_token_budget()` reads
  `SETTLEMENT_MODEL_TOKENS` (default `MODEL_TOKENS = 512`), used as the
  inference reservation cap; fail-closed on non-positive.
- `src/settlement/development.py`: `packet_budget()` reads
  `SETTLEMENT_PACKET_BUDGET_CHARS` (default 24000/2000), used by
  `_packet_for`; fail-closed on non-positive.
- `experiments/run_dev_episode.py` (`_live_adapter`, shared by
  `run_use.py`) and `experiments/run_live_abc.py`: `SETTLEMENT_GATEWAY_API`,
  timeout overrides, and both budget knobs validated before any write
  (exit 2 with reason).
- Tests (all stub-local, no live): `test_s0_gateway.py` +4 responses
  decoder/failure/refusal-of-unknown-api tests via a `/responses`
  stub route; `test_r02_exec.py` +3/+3 env-knob default/override/refusal
  tests. Focused: 25 passed. Pre-change runs observed failing first.

## Why each knob was needed (observed, in order)

1. Base URL must include `/v1` (`{endpoint}/models` is the discovery path).
2. Chat-completions rejected: provider shim refuses `max_tokens`
   ("unknown parameter") → Responses API required.
3. `MODEL_TOKENS = 512` starves thinking-model reasoning (a trivial
   prompt burns 158 reasoning tokens; diagnose emits reasoning-only
   output → honest "not typed JSON"). 8192 suffices for diagnose.
4. 60s read timeout trips on long reasoning bursts under parallel load.
5. Default 24k packet budget trips on real live transcripts
   (construct packet needed 25140+ chars → honest needs_information,
   nothing stripped — D2A-005 working as designed).

## Live episodes (4 full, all EXIT 0, identical honest shape)

| episode | diagnose | construct | compare verdicts | disposition | use |
|---|---|---|---|---|---|
| B `liveb-ep-02` | typed JSON live (4368 in / 3542 out) | slot 0 staged, check: no successful transcript | 4× inconclusive (0/0) | fallback baseline-v0 | incumbent, `unreleased-no-release-for-wrong_operator`, trial false |
| A `livea-ep-05` | typed JSON live | staged path exercised | 4× inconclusive (0/0) | fallback baseline-v0 | incumbent, same reason, trial false |
| D `lived-ep-01` | typed JSON live | staged path exercised | 4× inconclusive (0/0) | fallback baseline-v0 | incumbent, same reason, trial false |
| E `livee-ep-01` | typed JSON live | staged path exercised | 4× inconclusive (0/0) | fallback baseline-v0 | incumbent, same reason, trial false |

Cost unions over live ops (46 unique ops each, 8 phases + 6 shared
collection ops, unresolved 0): B 11,856 in / 37,930 out;
A-ep-05 16,173 / 37,624; D 9,555 / 36,096; E 10,619 / 45,105.
Provider reports no billable charge on any call (`cost: "0"`, no
`charge_units`): token counts settle honestly, monetary charge 0.
Entry records kept at `reports/evidence/d02live/`.

All 9 phases (admit/diagnose/construct/check/select/freeze/compare/
dispose/use) present in every full record with `simulated: False`,
live model id, and `local-process` launcher in the environment block.

- **A path**: ep-02 refused (chat-era 400s, pre-fix); ep-03 refused
  (512-cap reasoning-only diagnose); ep-04 reached construct then
  honestly refused on the 24k packet budget gate
  (`needs_information`, nothing stripped — D2A-005 live proof).
- **C path (instructive partials)**: ep-02/ep-03/ep-04 all reached
  live diagnose + construct inference; slot-0 candidates failed the
  staged selftest (honest invalid-output, slot consumed) or emitted
  reasoning-only output; with no candidate the episodes honestly
  refused at compare (`unknown protocol <ep>-panel-eval` = freeze
  skipped with nothing frozen). C-ep-04's live diagnose correctly
  identified the harness-level failure mode (correct fixes trapped in
  prose with em-dash SyntaxErrors).

## Empirical reading (this model, these tasks)

Every comparison arm (A/B/C) runs live model inference; arm A is the
statistical reference (baseline prompt), not pinned bytes. The model
scored 0 on all 5 panel/transfer tasks in all 4 full episodes (20/20
arm-tasks failed both candidate and reference) → 16/16 verdicts
`inconclusive`, zero releases, incumbent fallback throughout. The
construct bottleneck is real: one slot per family per episode entry,
file-ABI + typed-JSON-selftest enforced — the model cleared the
envelope repeatedly but cleared staging+check only via B slot 0
(which then failed check). No release means the live
router-verified `selected` path stays unexercised; the live
incumbent path (D2A-003) is proven 4/4 with reasons and recorded
dispositions.

Open harness observation (not changed mid-campaign, filed for
review): the entry attempts one construct slot per family while
`max_candidates = 2` admits two — half the admitted ceiling goes
unused in every episode, fixture and live alike.

## Deterministic gate on the live-capable tree

New code is additive-with-defaults (`api="chat"`, 512 tokens, 24k
budget, 5s/60s/300s timeouts) so the deterministic suite runs
unchanged with no env vars set. Full `tests/` on the final tree:
**530 passed, 0 failed in 738.91s** (517 prior + 13 new: 4
responses/api, 3 token-budget, 3 timeout-override, 3 packet-budget;
fresh DB `settlement_t1livegate`, URL-form DSN). Acceptance probes:
**6 passed** separately. The launcher load flake from the prior gate
did not reproduce. `ruff` still not installed (no CI gate).
