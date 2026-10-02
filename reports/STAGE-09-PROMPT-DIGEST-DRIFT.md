# Stage 09: prompt-digest drift after `b9b7b4d`

**Status: ISSUES.** One live regression guard is red, but it was already red before
the contract change. No recorded digest is silently wrong, and the one artifact
that most needed checking reproduces exactly.

## What `b9b7b4d` changed

`experiments/ad01/method_exec.py` no longer hand-writes the `signature` string in
`child_contract()["callables"]`. Each entry is rendered from the wrapper the child
binds, by building the wrappers and reading their own `inspect.signature`. The
rendered text is the whole point of the fix: `reduce_software` used to be
documented as `reduce_software(task, oracle, method, max_queries)` when the wrapper
binds `method` keyword-only, and a member that obeyed the contract died with a
`TypeError`.

`packet.public_operations` (`experiments/ad01/packet.py:297-304`) copies that
string into the construction packet, and `render_construction_prompt`
(`packet.py:342`) serialises it into a prompt line labelled `Public operations:`.
So the contract text is prompt bytes, and the commit changed them.

`CHILD_CONTRACT_VERSION` is still `ad01-child-v1`. The version did not move with
the bytes.

## Census

Every committed JSON or Markdown artifact carrying a digest or byte count of
prompt or packet content, grouped by what the digest is a record *of*.

| Family | Count | Bears the child contract? |
|---|---|---|
| Live study exports (`evidence_inv01_live/exports/`, `reports/evidence/inv_r1_m3*/exports/`) | 12 files, 195 digests | 44 prompts embed `Public operations` |
| M3 pilot construction digests (`reports/evidence/inv_r1_aa3_m3/result.json`) | 4 `prompt_sha256` | yes, via `construct._prompt` |
| Menu audit (`reports/evidence/inv_r1_u2_menu/result.json`) | 7 `declared_signature` | yes, verbatim |
| Output-shape freezes (`reports/evidence/invl02-output-shape-550b-r{2,3,4}/`) | 3 freezes, 24 `rendered_digests` | **no** |
| `reviews/probes/closure-84d2094-observed.json` | 1 `prompt_sha256` | no (older prompt format) |
| Representation campaign evidence, `context-pilot-01`, `inv_r1_e4`, `inv_r1_m4_baseline` | 76 digests | no — different subsystems |

**Split: 0 live regression guards broken by `b9b7b4d`. 226 historical records,
of which 4 are not reproducible from the repository at all.**

The fourth contract form matters. The 44 prompts embedded in the exports read
`reduce_software(task, oracle, *, method="ddmin"|"greedy", max_queries=16)` — a
form that matches neither the pre-commit source nor the post-commit render. It is
older than both. Those dispatches predate the settlement route contract
entirely: the exports carry no `route_error` field and were committed on
2026-09-21, so C16 cannot have been in force.

## The four that are not reproducible

`reports/evidence/inv_r1_aa3_m3/result.json` records four `prompt_sha256` values
for construction dispatches run at 18:47 on 2026-09-28, and stores **no prompt
text**. The digests were therefore only ever computable by re-running the render
against the working tree at that moment.

I extracted the tree at the run's own commit (`7e9128b`, 18:51) and re-rendered
each prompt through `experiments/ad01/construct.py` with that tree, holding the
arm's recorded experience (`result.json["experience"]`) and the frozen
`request_bounds`:

| arm | recorded | reproduced at `7e9128b` | today |
|---|---|---|---|
| `dev-exp` graph | `7a9f53b787a90e` | `7a9f53b787a90e` | `6ca3ca1e2a3e15` |
| `public-interface` graph | `d87a22190fd104` | `d87a22190fd104` | `53288bd2e042b1` |
| `dev-exp` software | `9e730a67208e07` | `9e730a67208e07` | `c3b67a6069a508` |
| `public-interface` software | `c471869253755c` | `c471869253755c` | `da56dae8388525` |

**All four reproduce exactly against the run-time code, and all four are stale
against HEAD.** This is the strongest form of the finding: not "recorded and
different" but "recorded, proven faithful to its moment, and now unreachable from
the repository". Anyone re-verifying this evidence must first reconstruct the tree
at `7e9128b`; nothing in the file says so. The dispatch records carry `sent: True`,
and two of the four hold real model replies, so these were genuine provider
sends.

## Live guards: one red, and it predates the change

The only place that re-derives prompt bytes from live code and compares them to a
recorded digest is `experiments/ad01/s09_exposure_ledger.py:658-664`, via
`_render_frozen_prompts()`. It re-renders every frozen prompt and compares
against `freeze["prompt"]["rendered_digests"]`.

It is currently **0 of 8 matching** against
`reports/evidence/invl02-output-shape-550b-r4/freeze.json`. The check is running
correctly; the recorded digests are not reproducible from the current source. I
verified this is **pre-existing**: re-running the identical check against the tree
at `7e9128b`, before `b9b7b4d`, also gives 0 of 8. `b9b7b4d` neither caused nor
fixed it.

This guard is **immune to the contract change by construction**:
`_render_frozen_prompts` calls `live_construct.render_output_prompt`, which formats
`OUTPUT_PROMPT_TEMPLATE` with a boolean-rule public input. That template never
embeds the child contract. None of the eight rendered prompts contains
`Public operations`. So the output-shape protocol and the child contract are
disjoint, and the red guard is a separate defect.

`experiments/ad01/offline_recompute.py:2495-2500` and `:2540-2552` are the other
two re-derivation sites. Both call the same `render_output_prompt`, so both are
likewise unaffected. I confirmed the recorded output-shape freezes do not carry a
construction prompt at all.

The digests that *are* affected are all self-consistent. Every ad01
`prompt_digest` and `packet_digest` in the exports is derived from text stored
beside it in the same record — `records.py:168` hashes `dr["prompt"]`,
`records.py:626` stores `packet` alongside `packet_digest`. I verified all 47
`delivered_requests` digests against their own stored prompts: 43 match; the 4
that do not are the intentional `""` for non-prompt operations, produced by
`records.py:168`'s `if prompt else ""`. Both `transition` packet digests I checked
recompute exactly. A self-consistent digest cannot be invalidated by a change to
the code that produced it once, because the code is not consulted.

## The C16 interaction: these digests are archival, with one exception

`src/settlement/gateway_http.py:697` refuses a response when the returned route
does not match the frozen one, and the gateway sends no `provider` field. The
refusal is constructed in `_response_meta` from the `body` of a response that has
already arrived.

Ordering settles it. `experiments/ad01/live_construct.py:387-390` calls
`self.delegate.infer(request)` — which is where the send and the C16 refusal both
happen — and only then, at `:420`, enters the `isinstance(response, GatewayError)`
branch. The tokens are spent before the comparison. C16 therefore does not prevent
a send; it converts a completed send into a refusal.

So C16 is not upstream of prompt-digest recording, and it does not make the
question archival. Both categories coexist:

- The 2026-09-21 exports predate the route contract, carry no `route_error`, and
  are **purely archival**.
- The four `inv_r1_aa3_m3` dispatches ran *after* the route contract was in force
  and were sent anyway — `sent: True`, and two hold real replies. Their digests
  are **archival but were produced by a live path**, which is exactly the case
  worth having checked.

## The menu audit is the finding with the sharpest edge

`reports/evidence/inv_r1_u2_menu/result.json` records, per callable, the exact
`declared_signature` the contract held and a `problems` list derived from it. It
found 13 problems, including the two that `b9b7b4d` fixed. All seven recorded
signatures now read differently from what the code renders, and one of them is
not a signature at all:

- recorded: `reduce_graph(task, oracle, *, method, max_queries) where method is one of "ddmin" or "greedy" and you must choose it; there is no default`
- today: `reduce_graph(task, oracle, *, max_queries=16, **kwargs) one of "ddmin" or "greedy"; you must name one everything after * is a keyword argument; passing one positionally raises TypeError **kwargs forwards a keyword the callee declares, so 'method' must be passed by name and the wrapper supplies no value for it`

The audit's own text says `child_contract()` is what the constructor prompt is
built from. Its `problem_count: 13` is a statement about a contract that no longer
exists. Nothing re-reads this file — it is history, and it should stay exactly as
it is. The point is that it is now a record of a *third* contract state, and it is
the only committed artifact that documented the M3 defect by name.

## What is not stale

- `reports/evidence/invl02-output-shape-550b-r{2,3,4}/freeze.json` `code_digests`
  and `source_digests`: `method_exec.py` is **not** in `OUTPUT_CODE_PATHS` or
  `OUTPUT_SOURCE_PATHS`, so `b9b7b4d` cannot have invalidated them. They are
  already stale against HEAD for other files (`gateway_http.py`, `invl02_live.py`,
  `live_construct.py`, `boolean_rule.py`) — pre-existing and unrelated.
  `method_exec.py` *is* in `LIVE_CODE_PATHS` (`scripts/invl02_live.py:36-47`),
  which `_require_live_digest_maps` re-hashes, but no committed freeze carries
  that field.
- `reviews/probes/closure-84d2094-observed.json`: stores the prompt text, digest
  verifies, no child-contract content.
- `tests/test_s89a2_extract.py`: `EXPECTED_DIGESTS` digests model *source*, not
  prompt, and passes.
- `s09_exposure_ledger.RequestEstimate.prompt_digest_matched` is hardcoded `True`
  at `:451`, `:604` and `:669`. The name outlived any check; it is a label now, not
  a fact. Not a regression from this commit.

## Tests

`tests/test_s89a1_contract.py` (6 passed) and
`tests/test_method_exec_contract_signature.py` (11 passed) both pass. The first
derives its assertion from the live contract, so it cannot detect drift in a
recorded digest; it confirms the contract is self-consistent, nothing more.
`tests/test_s89a2_extract.py` and `test_s89a2_rerun.py` (10 passed) read the
exports and do not touch the contract.

There is no test anywhere that re-derives a *construction* prompt and compares it
to a recorded digest. `s09_m3_pilot.py:364` records `prompt_sha256` and
`prompt_chars` and never compares them to anything. That gap is why the four
`aa3_m3` digests could go stale without a signal.

## Classification

- **Historical, correct, never rewrite:** the 195 export digests; the 7
  `declared_signature` strings in `inv_r1_u2_menu/result.json`; the 4
  `inv_r1_aa3_m3` `prompt_sha256` values; the 24 output-shape `rendered_digests`.
- **Live guard, red, pre-existing, not caused by this commit:**
  `s09_exposure_ledger.py:658-664`.
- **Live guard, immune by construction:** `offline_recompute.py:2495-2500` and
  `:2540-2552`.
- **Recorded but not reproducible:** the 4 `inv_r1_aa3_m3` `prompt_sha256`
  values. Reproducible only against the tree at `7e9128b`.
- **Sharpest edge:** the three distinct contract states now visible across
  committed evidence — `method="ddmin"|"greedy"` in the 2026-09-21 exports, the
  `*, method, max_queries ... no default` form in `inv_r1_u2_menu`, and today's
  `**kwargs`-forwarding render — all under the same `ad01-child-v1` version
  string.

## Not done, deliberately

No digest updated, no evidence regenerated, no stale record deleted, no code
changed. The only file written is this one. `git status` shows the two
modifications in the tree (`experiments/ad01/control_distinctness.py`,
`tests/test_inv_r1_method_menu.py`) and the untracked
`tests/test_ad01_menu_binding_gate.py` as other lanes' work, untouched here.
