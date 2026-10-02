# Stage 9 feasibility (draft)

Base `da76b30`. Existing code only. No production edits. One
disposable database (`s89_b2_p2`) was created for the pending-work
probe and dropped after. No live inference. No secrets in Git.

Probe scripts live outside the repo at `/tmp/opencode/s89b2/` and
are not committed. Each probe below names the real path it
exercises.

## 1. Policy substitution changes admitted and executed behavior

Path: `DecisionConsumer.decide` with two stub proposers through the
real `admit_investigation`.

Result: pass. Policy A admitted with target `ad01-w0-dev-sw-00`.
Policy B admitted with target `ad01-w0-dev-gr-00`. Swapping the
proposer changed the admitted target through the real admission
gate. A substituted policy is therefore replaceable at this seam.
It is an engineering control unless it learns from experience, and
it stays labeled as one.

## 2. Pending work survives process loss

Path: `authorize_campaign`, `ensure_campaign`, and
`trajectory.record_decision` in one process; `trajectory._read_campaign`
in a fresh process; same DSN.

Result: pass. The writer recorded attempt `att-ad01-w0-I-900-0`.
A new process read zero settled and one pending row, kind
`decision`, at seq 0. Acceptance persists before effects, and a
resumed participant reconciles instead of re-deciding.

## 3. Both domain contracts are usable

Path: `method_exec.run_member_out_of_process` with independently
written bare-helper candidates, then `trajectory._check`.

Result: pass. `reduce_software` on `ad01-w0-dev-sw-00` executed and
returned verdict `preserved`. `reduce_graph` on
`ad01-w0-dev-gr-00` executed and returned verdict `preserved`.
Both advertised operations run through the corrected child path.

## 4. Replay accepts a supported continuation and refuses unsupported ones

Path: `doubles.recorded_from_export` plus `check_replay_prefix` on
committed `evidence_inv01_live` exports.

Result: pass. An identity probe on transition 0 of `export-w0-I.json`
returned `supported` with the recorded results. A changed-target
probe returned `unsupported` with reason `unsupported-decision`.
A future-observation probe returned `unsupported` with reason
`hidden-future`. Supported probes return recorded results verbatim.
Everything else returns no results.

## 5. Archived candidates on the corrected path

The four archived validation executions from the live study were
re-executed unedited through the corrected child path at
`max_queries=16`. All four execute past the old `NameError`. All
four check as `preserved`. Two tie the incumbent (16 to 16) and two
are strictly smaller (12 to 11). This is a post-fix diagnostic on
already-seen dev tasks, not held-out transfer. The live study
outcome stands. Six repertoires hold zero members, 24 of 24 use
records on the incumbent.

## 6. Corpus and bottleneck ranking

The committed corpus holds 28 transitions across 6 exports, 10
construction attempts, and 24 use records. Episode dispositions are
23 inspected, 4 rejected, 1 no-candidate. Observation verdicts show
10 preserved-vs-not-preserved splits, 6 mutual not-preserved, and 12
ties.

Ranked hypotheses:

1. Delivery and format loss. Six of ten construction attempts never
   reached validation. Three are timeout-unknown exposures and three
   are output truncations cut exactly at the 2048 token cap. Repair
   prompts carried the true priors, so wiring is faithful. The
   bottleneck is transport and output limits.
2. Usefulness bar. Even executed candidates must preserve and beat
   strong seeds. The live panel retained nothing, and the two
   smaller post-fix candidates arrived only as intervention
   diagnostics. Candidate quality relative to the incumbent is the
   next binding constraint once delivery improves.
3. Residual validity risk, resolved as a cause. The bare-helper
   mismatch explained four attempts and is fixed. What remains is
   labeling discipline. Delegating wrappers count as valid
   execution, never as novel algorithms, and full-budget burns
   (16 of 16 queries) need watching.

## 7. Selected next experiment

Replay policy-comparison coverage on the committed corpus.

Question: can this corpus rank a changed policy, or must the next
learner question be prospective?

Method: probe every recorded prefix twice. First with the identity
action, which must return supported. Then with the counterfactual
a learner would need, which is construct where the record stopped
or stop where the record constructed. Count supported against
unsupported.

Predictions: the replay-optimization view predicts the corpus
ranks the two policies. The design predicts at least 90 percent of
counterfactual probes return unsupported, because one trajectory
per prefix cannot supply matching continuations for changed
actions.

Controls: identity probes guard the harness. Unknown costs stay
unknown and are never scored as failure.

Cost: zero live spend. CPU only over 28 transitions times a small
fixed probe factor.

Stopping rule: if at least half the counterfactual probes return
supported, the corpus supports policy comparison and a
replay-assisted campaign is viable. Otherwise the negative is the
result. The next step is then the smallest prospective
investigation that separates hypothesis 1 (transport) from
hypothesis 2 (quality), with its own finite grant and frozen
judge. Either outcome is informative.

## 8. Limits

Fake providers and fake sandboxes did not validate live inference
or containment. The child path gives process separation, not
hostile-code containment. Unknown-receipt timeouts carry no
timestamps, so gateway attribution stays unverified. Truncated
responses share the generic parse-failure stage, which spends
bounded repair on verbose but well-formed output. Feasibility probes
1, 2 and 4 ran from throwaway scripts outside the repo, so only
their code paths plus probe 3 plus the gate reruns are independently
reproducible from committed bytes. No new live authority was
requested or used.
