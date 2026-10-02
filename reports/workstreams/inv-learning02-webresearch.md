# Web research: robust structured extraction from reasoning-model text

Base 4545a51. Branch wt/invl02-web. Context from `experiments/ad01/live_construct.py`
`parse_live_improver` (fence strip plus stdlib `json.loads` plus STEP gate) and the
gaps section of `reports/workstreams/inv-learning02-r123.md` (P1 P2 boolean predictor
JSON stayed malformed after two repairs, E3 unavailable). No live model calls. No database.

## Recommendation table

| Option | Verdict | One-line reason |
|---|---|---|
| Fenced-block extraction plus stdlib JSON Schema style validation | Adopt | Zero new dependencies, fixes the delimiter class, fails closed on bad properties |
| Dirty-JSON repair library (`json_repair`) | Reject | Extra dependency plus silent-coercion semantics conflict with fail-closed spec validation |
| Provider-side constrained decoding (`response_format` JSON Schema) | Reject for now | Gateway passthrough unproven, guarantees syntax not values, revisit only with live budget |

## Option 1: fenced-block extraction plus JSON Schema validation

Evidence read this session: https://www.glukhov.org/llm-performance/benchmarks/llm-structured-output-validation-python/

The page recommends a boring pipeline. Normalize raw text first (strip fences,
slice a leading preamble to the outer braces), then parse with stdlib `json`,
then validate against a closed contract. Its reference helper handles fenced
blocks and a leading natural-language preamble for a single top-level object.
It warns that naive brace slicing breaks when braces nest inside string values,
and the fix it names is stricter prompting, schema-bound completions, or a
dedicated parser library.

Correctness fit. This option directly fixes the delimiter class we see
(fences, preamble prose). It does not fix intra-JSON syntax errors, which is
exactly the P1 P2 failure mode. That failure needs the bounded retry the gaps
section already names: strict schema prompt plus fenced extractor plus
validator error text fed back to the model within the reserved repair budget.
Validation itself should stay hand-rolled and closed: required keys present,
value types checked, unknown properties rejected. The page mirrors this with
`additionalProperties: false` on the schema side and `extra="forbid"` on the
model side.

Dependency weight. Zero. Stdlib `json` only. No new service.

License and maintenance. No third-party code, so nothing to license or track.

Adopt. This is the smallest change that hardens the current path.

## Option 2: dirty-JSON repair library (`json_repair`)

Evidence read this session: https://github.com/mangiucugna/json_repair

The README documents a drop-in `json.loads` replacement that repairs missing
quotes, commas, brackets, comments, stray prose, and truncated values. It
defaults to trying stdlib parsing first and repairing only on failure. Schema
guided repair is explicitly marked beta. Its `salvage` mode drops invalid array
items, maps arrays to objects by property order, unwraps single-item root
arrays, and fills required fields with inferred safe values. The README warns
that forcing valid JSON through the repair parser can change structure or
values, and that `skip_json_loads=True` is only for known-bad input.

Correctness fit. Repair covers the syntax-error class that Option 1 cannot.
But the salvage semantics are wrong for our use. Dropping disallowed
properties or inventing defaults turns a malformed spec into a plausible but
unfaithful spec, and our pipeline must fail closed on bad properties, not
coerce them silently. Standard mode is less aggressive but still guesses, and
the beta label on schema guidance is stated by the maintainer.

Dependency weight. One new PyPI dependency (`pip install json-repair`, schema
mode needs the `schema` extra) against a stdlib-first constraint. Small
library, but every new dependency is review, pin, and supply-chain surface.

License. MIT, per the repository license section. No license conflict.

Maintenance. Active single-maintainer project: 5.1k stars, 217 forks, 637
commits, TDD plus strict semver claimed in the README with major-version
pinning requested. Healthy for its size, but still a side project with one
bus factor, and schema repair is beta.

Reject. Adopt the bounded validator-feedback retry pattern instead, without
vendoring the package. Revisit only if measured evidence shows syntax errors
dominating after the Option 1 retry loop ships.

## Option 3: provider-side constrained decoding

Evidence read this session: https://developers.openai.com/api/docs/guides/structured-outputs

The docs describe Structured Outputs as constrained decoding against a
supplied JSON Schema: the model cannot omit a required key or hallucinate an
invalid enum value. They distinguish it from JSON mode, which guarantees valid
JSON but no schema adherence, and recommend Structured Outputs over JSON mode.
They also document the limits that matter to us: only a subset of JSON Schema
is supported, all fields must be required, the root must be an object, and
refusals plus incomplete responses arrive outside the schema path. A separate
passage states that schema-valid output can still hold incorrect values.

Correctness fit. Constrained decoding removes the syntax-error class at the
source, which would moot the P1 P2 failure. It does not remove the bad
property or bad value class, so Python-side validation stays mandatory either
way. Reasoning models add a second gap: reasoning traces around the JSON still
need extraction, which is Option 1 work regardless.

Dependency weight. No new package, but it is a provider capability, not local
code. Our path calls a gateway chat API, and passthrough of `response_format`
with a strict JSON Schema through that gateway is unproven. Proving it costs
live calls, and no live spending is granted.

License and maintenance. Provider feature, no license question. Maintenance
risk is schema-dialect lock-in plus first-request latency on new schemas.

Reject for now. Keep Option 1 plus bounded retry. Revisit when the gateway
proves `response_format` passthrough and live budget exists, and keep the
Python validator as the authority in all cases.

## Final answer

Adopt Option 1. Reject Option 2. Reject Option 3 for now. Next work is the
strict boolean prompt schema plus hardened fenced extractor plus bounded
validator-feedback retry inside the reserved repair budget, per the gaps
section. No new dependencies. No new service.
