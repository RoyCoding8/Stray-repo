# Stage 9 consolidation

Branch `codex/implementation-stage-09-consolidation`. Contract
`docs/design/STAGE-09-IMPLEMENTATION-CONTRACT.md` governs. Stage 8
helper fix stays closed. `evidence_inv01_live/` is byte-identical and
still no-retention. No live inference ran anywhere in this batch. No
positive learning outcome is claimed.

## Implemented contracts

N1 durable ownership: one trusted driver in `experiments/ad01/trajectory.py`
owns accept, execute, reconcile, incorporate. Accept persists in
`s09_policy_state` before effects. Resume reconciles the same operation
identity with no duplicate effects and no renewed limits. Selection lives
in `experiments/ad01/selection.py`, extracted from first-match with
identical behavior. Migration `migrations/0017_s09_state.sql` adds only
`s09_policy_state` and `s09_assessment_exposure`. All other N1 fields reuse
existing rows. Public driver is `experiments/ad01/cli.py` with run, resume,
use. `run_c3_qualification.py` is a client, not a parallel driver.

N2 policy ABI: `experiments/ad01/policy_step.py` pins
`ad01-policy-step-v1` with view, state, action shapes and pure validators.
`run_step_out_of_process` in `experiments/ad01/method_exec.py` executes
STEP source in the child with CPU, wall, output, state caps. Policy source
never runs as a host proposer. Admission, evaluation, budgets stay trusted.
Model requests are broker effects whose settled text feeds the next view.
`construct_policy` in `experiments/ad01/construct.py` returns model bytes
with lineage, response digests, validation, exactly one repair. Two authored
policies diverge through the public entry. One policy restarts consistently.

N3 feedback versus assessment: `packet.py` plus `learner.py` filter sealed
keys and observations at the boundary. Provider prompts build from filtered
packets. Exposure appends `s09_assessment_exposure` and retires the batch
for descendants. Protected references are refused. The AD01 protected-task
guard keeps its original protocol.

N4 revision plus bind: proposals persist in the journal, candidates freeze
before assessment, assessment runs frozen bytes out of process. Bind is
atomic against the expected version in `capability_releases` with fallback
preserved. Selection consults the active eligible binding. Retry reuses
identity. Intentional revision gets a new attempt.

N5 pilot: `scripts/s09_pilot.py` plus `scripts/s09_verify.py` implement the
prospective P0, P1, P2 study. Doubled bundle `evidence_s09pilot/doubled-r1`
spends 3 of 100 calls with 24 use records and verifier pass. P2 failed its
repair and ships as an unavailable arm with incumbent fallback, which proves
the missing-arm path. Replay stays conformance only.

N6 migration: old campaign state keeps historical reproduction. Pending
legacy work drains unless a lossless versioned resume proof lands.

## Fixture qualification

Doubled and fake providers qualify machinery only. Recording doubles stand
at the gateway seam. Authored policies prove the executor diverges and
persists, not autonomous learning. The doubled pilot is deterministic:
two runs are byte-identical across all 9 bundle files.

## Live results

None. No fresh grant exists. The spent stage 8 grant is not reused. The
single live-run command plus cap sheet live in `reports/workstreams/s09-m5.md`.

## What the system itself chose

Nothing autonomous. Every policy executed in these gates was human-authored
or scripted. Revised bytes changed decisions and effects in the M34 cycle
gate: binding the revised member selected and executed it fresh-process.
Independently measured quality or resource improvement is unproven. After a
restart the driver reconciles pending work and continues without new spend.

## Limits not verified here

Child execution gives process separation, not hostile-code containment.
Sealed assessment relies on filter plus label discipline, not on a separate
enclave. Unknown receipts keep conservative exposure and stay unknown.
Trial gates are not wired into bind. Use operation ids still need the
versioned helper for method version. M6 independent verification is pending
below.

## Next bottlenecks (at most three)

1. Live policy acquisition is unproven: no model has yet returned policy
bytes through `construct_policy`.
2. Assessment depth is thin: trial protocol gates are not bound into
promotion, so qualification rests on the frozen comparison only.
3. Transfer is untested: all rerun and pilot tasks are already-seen; nothing
measures a revised policy on genuinely new tasks.

## Verification

Independent review (M6) at 089ef59 with reviewer-authored bytes: effect
execution pass, protected refusal pass, revision identity pass,
binding-aware selection fail (F1), kill plus resume pass, evidence
completeness pass, constructor disconnect pass. 58 gates green.

F1 plus F2 fix merged as 5b7fd8a: run_use routes through the
binding-aware selector with dsn plus release_id; use operations mint
versioned identity. Tip gates 62 passed plus verifier pass. Known gap:
the CLI use subcommand threads dsn but no release flag, so exact release
pinning goes through run_use callers; single-release stores agree. Legacy
unversioned use ids keep their old identity under retry.

Full suite result is recorded in reports/PLAN.md. Live evidence
`evidence_inv01_live/` is byte-identical to the handoff. No live
inference ran. No model calls without a fresh grant; none was granted.
