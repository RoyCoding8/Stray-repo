# W1 / E1 cap sheet — live representation and acquisition comparison

Status: FROZEN pending coordinator sign-off. Written before any W1 dispatch. Supersedes no existing grant.

## Authority and lineage

Standing authorization: the human authorized live testing on a verified free
model for fresh, prospectively bounded studies in this assignment, and stated
token minimization is not required. This sheet is that authorization, made
concrete. It is a NEW study root with explicit allocation. It does not reuse,
settle, replay, or discharge any historical grant.

Old reservations stay under their original grants and are reported separately:

| Reservation | Units | State |
|---|---:|---|
| `res-invl02-output-872608eb94c3-P1-audit-0023-a1` (r4) | 2294 | uncertain, VERIFIED term |
| `res-ad01-ad01-w0-I-72-b0-…-construct-l1-init` | 3269 | uncertain, VERIFIED term |
| one further uncertain reservation | unknown | **excluded from every reconciliation artifact and named nowhere** |

The subtotal is 5563 internal estimated reservation units. It is not a dispatch
count, not provider billing, and not the current total. The third row comes
from `other_uncertain_reservations_excluded: 1` in
`reports/evidence/invl02-live/store-reconciliation.json:44`. The true exposure
is `>= 5563`. Closing that gap needs one read-only query against the
`invl02_live` store, which this host cannot reach; it is a named blocker, not
an assumption.

## Why a new freeze is mandatory

`experiments/ad01/live_construct.py:25-31` pins `OUTPUT_ROUTE`, and both
`offline_recompute.py` and `invl02_live.py` compare against that exact
constant. The frozen `requested_model` spelling
`openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` **no longer exists** in the
live 255-entry catalog; the same model is reachable bare or under `kilo/`.

Changing the constant invalidates every existing frozen bundle by design.
Therefore: new freeze, explicit lineage, old results retained and never mixed
into the new ones as though comparable. This is not a fix to be applied
quietly.

## Pinned before any assessment

| Item | Pinned value |
|---|---|
| Source | integration tip, recorded with the freeze |
| Endpoint | `http://localhost:4000/v1` |
| Requested model | new spelling, validator-accepted, recorded verbatim |
| Provider | `nvidia` |
| Tier | `free` |
| Effort / sampling / temperature | recorded verbatim from the request |
| Protocols | Boolean, ordering, SWE, each with its own arm matrix |
| Selectors | per-world declared policy view contract |
| Limits | per the table below |

Rate limits, quota and concurrency are **UNVERIFIED**. Two probe calls cannot
characterise them. Reserve headroom is treated as unknown, not as available.

## Matrix

Three acquisition treatments through ONE shared controlled path: authored
baseline, interface-only acquisition, experience-conditioned acquisition.
The experience arm's design is frozen in W2 and is NOT run here; W1 covers
authored and interface-only.

Representations are compared only where each can express the required
behaviour. Cells that cannot express it are left missing with the concrete
limitation recorded. **No Python interpreter is hidden beneath an AST or graph
label, and no general DSL is built to fill a table.**

| World | STEP (Python) | Typed AST | Action graph |
|---|---|---|---|
| Boolean | supported | supported | supported |
| Ordering | supported | supported | supported |
| SWE | supported | **executor supported; typed AST cannot repair** | **executor supported; action graph cannot repair** |

**Superseded 2026-09-29.** This row previously read "missing — executor cannot
read a file, run a test, or return a value" for the typed AST. That was wrong,
and `s09_swe_experiment.py:26-36` already said so before this row was written.
All three capabilities are present in `s09_swe_world.py`: read at `:212-213`
and `:240-250`, run at `:293-306`, return at `:317-327` and `:391-395`.

The real limits are three separate facts, and conflating them misreports how
much of the matrix is lost:

1. **Representation, typed AST** — the frozen `_VIEW_TYPES` publishes no field
   for the program under repair, and no node builds replacement source text.
2. **Representation, action graph** — `_parse_action` deep-copies the raw
   action node, so a value a guard just read never reaches an action input;
   `code.localize` is admitted only for a test the world has already seen fail,
   which the load-time `static_view` never has.
3. **Host** — no supported Linux execution environment on this coordinator, so
   the child cannot be spawned under its caps.

Limits 1 and 2 are recorded as data in `s09_swe_ast.missing_cells()` and
attached to the lineage, so a zero repair rate cannot be misread as model
inability. Limit 3 is a deployment fact and must not be removed to unblock the
study.

Typed AST requires a supported Linux execution environment for the child. It
refuses by name on a host that cannot install the caps. That is a measured
limit, not a gap to fill.

## Construction opportunities

At least 4 independent construction opportunities per supported
representation/world/treatment cell. The required count and the total are
computed at freeze time from the matrix above, not guessed here.

## Replication definition (from W0/TR-03)

A lineage is ONE construction opportunity plus its record. Independence is
disjointness of ancestor chains, **never digest difference**. Two independent
model calls that converge on identical programs are independent lineages and
are counted as such; requiring distinct digests would bias acquisition
sampling. Behavioural duplication is reported as a `distinct_behaviours`
figure published beside `lineages_run`. It is never enforced.

The `origin` field is normalised across all three representations so a reader
can distinguish "never acquired" from "this cell's shape has no such field".
The fixture lineage builders are retained as qualification evidence and count
toward **no** requested live lineage.

## SWE scale

At least 4 distinct families and 24 held-out instances, if the instrument
supports genuine diversity. Family/template separation is frozen BEFORE
evaluation. Replication is not created by renaming one hidden target.
Finite target support in the tiny worlds is deduplicated and the support
count is reported alongside the result, so a reader can see common support.

## Caps

Derived from the matrix, with a named ceiling for each category. Persisted
counters and pending exposure are written BEFORE effects, including crashes.

| Category | Ceiling | Basis |
|---|---|---|
| Construction attempts | `N = 4 × supported cells × treatments` | computed at freeze |
| Repairs | 1 per construction opportunity | bounded development loop |
| Model calls, construction | `≤ N × 2` | one construction plus at most one repair |
| Model calls, use | `≤ 6 × held-out instances per supported cell` | per-cell use phase |
| Repeats / retries | ≤ 1 retry per operation identity | retries reuse identity |
| Resume | from persisted pending exposure only | a context reset cannot replenish the root |
| Control calls | counted separately from learned arms | so the comparison is auditable |

Every call, success, failure, refusal, and unknown is counted. Unknown is
recorded as unknown and is never written as zero. Free price does not make
usage, compute, or experimental opportunity unmeasured.

## Stopping rule (predetermined)

- A stop, unknown, or no-candidate outcome does NOT authorise a replacement episode.
- A rerun after an apparatus failure is NOT replication. Only a second
  independent campaign namespace is.
- Sampling and selection rules are fixed here, before assessment.
- No tuning on sealed outcomes.
- The study stops when the matrix is filled or a cell is recorded as missing
  with its concrete limitation. There is no search for a positive result past
  that point.

## Preconditions, all currently met or explicitly blocked

| Precondition | State |
|---|---|
| Free route live and answering | MET — HTTP 200, provider-reported model id matches |
| Child limits installed and firing | MET under WSL; refuses by name on Windows |
| Artifact binding tamper-detected | MET — three author-written tampers, all detected |
| Offline recomputation from export alone | MET — byte-identical with the database socket removed |
| Failure modes separable | MET — five modes, distinct fields in durable receipts |
| Per-world view contract | MET — 21 tests pass including 12 contamination tests |
| Confined read denial proven | **NOT MET** — WSL2 kernel rejects Landlock; needs bare metal |
| Unknown reservation identified | **NOT MET** — needs the `invl02_live` store |
| Route spelling re-frozen | REQUIRED before first dispatch |
