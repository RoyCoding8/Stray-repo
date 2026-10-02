# EC02 closure and AD01: full assignment assessment

Reviewed `23a3e686da19e2a65087684ce4e5a24cddd008d8` against assignment base `fa777d5`, 2026-09-15, in an isolated review worktree. The worker's suggested inspection order was useful input, not the acceptance standard. This assessment covers C1–C5 and ECA/AD obligations. No production implementation or historical evidence was changed.

## Decision

**Do not accept EC02 closure or AD01 C3 yet.** These are central missing behaviors, not prototype polish. The public EC02 path still substitutes unchanged sources or comment stamps for model-generated repair and publishes synthetic costs. AD01 runs authored reducers along an externally supplied task list; its recorded decisions do not govern that list, and no acquired executable is constructed. Passing these tests cannot establish the commissioned learning cycle.

Keep the useful environment, gateway propagation, provenance fields, validation separation and ledger helpers. Finish the already specified two-domain cycle. No larger experiment, new domain, new framework or positive learning result is required to advance.

| Gate | Current disposition |
|---|---|
| C1 shared execution | Not complete: actual child generation and exported accounting remain disconnected. New tests accept the disconnect. |
| C2 live EC02 closure | Partial live construction is worker-reported. Committed summary records two calls, no accepted candidate, and four validation rows including two nonexistent repairs. It does not establish completed bounded acquisition or the intended live fallback experiment. |
| C3 AD01 qualification | Environment and authored reducer orchestration exist; the specified learner, initiative, construction and retained execution path do not. |
| C4 AD01 live | Unrun. Missing separate allocation is legitimate, but allocation alone would not make the present CLI a live learner. |
| C5 final delivery | Reports and tests are delivered. Their unconditional completion labels exceed the observed behavior. Receipt anchors remain worker-reported, not independently reconciled here. |

## Material findings

### EAR-01 — P1: repair execution is still a stand-in

`experiments/coord02/entry.py:314–351` accepts only the `FIXTURE` constructor label. S/F/L return original owned source; A appends a hash of the obligation as a Python comment. `run_cell:554–556` always uses this factory, and `run_panel` exposes no alternative real constructor. A's decision model can now influence a proposal, but there is no downstream repair inference. The live CLI also supplies empty `package_text`, whereas the A factory asserts that it is nonempty.

Independent probe: different obligations changed all four owned Python files' bytes while leaving their parsed programs identical to the original broken inputs. A `LIVE` constructor request was refused. This cannot test whether learned coordination improves real repair workers. It also cannot establish a competent iterative S baseline.

A's `selected_source_text:210–220` still serializes the task snapshot, not the selected retained coordination algorithm. The interpreted arm therefore also lacks the specified retained-source input. Supplying a nonempty `package_text` merely to bypass the factory assertion would not fix either connection.

The independent verifier codified this mistake: `tests/test_ec02ad_verif.py:286–300` explicitly demands the stamp-only channel, and the nearby causal test checks tree inequality rather than functional effect. Do not fix this by allowing arbitrary repairs in the policy envelope: EC02 deliberately separates structured coordination decisions from child-generated patches. Invoke the real child model after admission, with the trusted renderer's permitted inputs, and submit that response's bytes.

### EAR-02 — P1: public accounting still fabricates measurements

`entry.py:390–417` computes 100 input tokens, 20 output tokens and one model call without reading the DB, and substitutes a run ID when no operation IDs are found. `write_evidence:671–674` attaches the entire cell cost to every receipt before unioning. The new `reconcile_campaign_union_from_store` helper has no caller in this entry module.

Independently counted all 96 committed `evidence-live/c2-fallback/episodes` records: every record is a failure, every one claims exactly 100/20 model tokens and one model call, including S/F/L. This is not a measured full-resource comparison. Model operations absent from a cell's enumerated IDs can also disappear from its export. The verifier report itself acknowledges that entry constants remain owned by another lane while ending with completion.

Connect the existing canonical operation projection to actual entry/export callers. Measure each operation once; preserve unknown quantities and liabilities. Lane ownership does not discharge a coordinator's integration obligation.

### EAR-03 — P1: EC02 public resume and campaign authority are not closed

`entry.run_panel` always runs its schedule and `run_cell:491–493` creates a fresh UUID/seed. The public CLI does not load an existing selected freeze, reconcile a saved campaign or resume pending cells; its grant preflight at `:715` also excludes development. New `resume_plan` helper behavior does not repair this caller. In addition, `_resume_skippable:759–760` accepts any nonempty claimed identity if no reconciliation set is supplied. A fabricated success with receipt string `invented-not-reconciled` still skips in the independent probe. Rejecting an empty claim is an improvement, not proof of receipt attribution.

Construction now has serialization and pending-effect handling for a supplied prefix, which is useful. But `experience.acquire:1242` still defaults to a new root and acquires development episodes before establishing that construction root; public cell seeding likewise creates fresh authority rather than consuming a durable study allowance. Re-entry must preserve the commissioned root, stable scheduled identities, original caps and unsettled exposure. Wire the actual campaign entry, not another resume demonstration.

### EAR-04 — P1: acquisition stops before the required repair/closure process

`experience.construct_lineages:1203` repairs only empty/unparseable source. The live candidates parsed but failed profile/execution checks, which are eligible repair inputs under EC02 section 7. `run_live_acquisition.py:63–65` then reuses the initial bytes when no repair exists and labels their second validation `repair`. The committed summary confirms two calls out of four and four rows; the duplicate rows produce `artifact already published` refusals. This is not four actual construction attempts or an exhausted eligible process.

The same driver creates its development experience and validation children with `dev_constructor("c02-t01", solved=False)` for every task. It does not use the newly required shared real child path. Its export strips candidate bytes and omits raw construction responses and attributable usage/receipt details, so profile refusals cannot be independently reconstructed from that JSON alone.

There is also a scope discrepancy to reconcile before further spend: the committed cap sheet preserves **48 development episodes including calibration and validation**, but the fallback export alone contains **96 development cells**. An overall 204-episode ceiling does not transfer evaluation capacity into development. We cannot infer what private authorization the worker received; publish the relevant redacted grant/amendment and complete phase totals, or record the breach. Do not reset or rerun away the discrepancy.

Retain the narrow observation that this run selected no candidate. Do not call the commissioned live study closed until eligible repairs, actual execution, phase accounting and evidence are handled, or its remainder is explicitly blocked.

### EAR-05 — P1: AD01 has no operative initiative or executable acquisition

`experiments/ad01/trajectory.py:232–256` executes the supplied `tasks` sequence regardless of `next_decision`. With default inputs, both I and R run the same three software tasks; the I/R test creates apparent divergence by passing different task lists. Forcing every decision to `stop` still executes three episodes. The injected proposal callback receives only a fabricated current-task `unmeasured` seed and an empty charter (`:153–171`), not accumulated diagnostic experience or the actual objective.

`dev_episode:410–457` selects from `SEED_CAPABILITIES`, runs the authored reducer, and returns its authored method ID as a retained executable. `run_use:326–334` looks that ID up in the same supplied menu. No method construction occurs. The JSON honestly says `authored: true`; the C3/AD03 report nevertheless treats this as the assigned acquisition path. `cli.py` exposes no live learner/construction configuration.

Make admitted actions govern task/diagnostic/development/stop execution. Pass the complete permitted decision packet and subsequent real observations. I selects opportunities; R alone fixes the curriculum item; both use the same learner and constructor thereafter. Seed methods remain authored incumbents. A successful acquisition control must supply executable bytes outside the authored seed menu through the model seam and later execute those retained bytes.

### EAR-06 — P1: AD01 persistence and budgets describe work after it happens

`trajectory._run_boundary` performs diagnostics and reducer execution before `_publish_boundary` records a decision. `_claimed_ops:71–73` invents strings; `_read_campaign:142–144` treats their presence as settlement without checking corresponding operations. The saved episode contains only disposition and query count (`:203–207`), discarding executable identity, candidate and diagnostic contents. Replaying that exact persisted shape loses every retained executable. A process restart test comparing only spend cannot establish continuity of learned state.

`ensure_campaign` directly inserts a 1000-unit allocation. The runtime enforces a boundary limit, but not the declared three-episode ceiling: six tasks produce six development episodes in the probe. Diagnostic limits are applied per reducer, and the stopping threshold is `16 * max_boundaries`, not the trajectory's aggregate sixteen additional diagnostic queries. `cost_union` uses caller-provided costs/zero defaults rather than authoritative effects.

Use existing agenda/development/broker records before effects, persist attributable outputs and capability references, and restore the same decision state and repertoire. Enforce independent aggregate caps at admission. Reject a fabricated boundary with nonexistent operation IDs. This is required for the bounded experiment, not deferred deployment hardening.

## What is accepted and what was checked

Scoped improvements: configurable HTTP adapter propagation; A proposal inserted into controller state; persistent scheduled/executed/fallback fields; profile/admission separated from solved quality; construction serialization and pending reconciliation helpers; evidence-resource designation protection; two-domain frozen environment and authored controls. These do not imply their surrounding study is complete.

Independent local checks on the unchanged production tree at `23a3e68`:

- `python -m pytest tests/test_ad01_env.py tests/test_ad01_traj.py -q -k 'not kill and not fresh_process'`: **47 passed, 3 deselected**. The deselected checks require the worker's PostgreSQL/process environment. No DB setup/cleanup or provider call was performed here.
- `python reviews/probes/ec02_ad01_completion_review.py`: all observation assertions passed. See [recorded observations](probes/ec02-ad01-completion-observed.json). These are offline/direct-boundary probes; the persisted-shape replay uses a mocked read and is not described as a real-DB restart test.
- All 96 fallback JSONs and the acquisition summary were independently read and counted. Receipt anchors, the worker's live gateway calls and full PostgreSQL suites were not independently rerun. Provider usage cannot be inferred from labels.

The new probes preserve what this revision does. They are not production acceptance tests to invert blindly: write semantic integration gates for the repaired path and map each observation to them. Historical evidence stays immutable.

## Review task list and next decision

- [x] Fetch exact tip into an isolated checkout and compare the whole assignment.
- [x] Trace public EC02 and AD01 callers, not just nominated helper tests.
- [x] Execute independent falsification probes and bounded existing tests.
- [x] Separate accepted components, unimplemented behavior and externally unverified claims.
- [x] Refine action authority, acquired-method identity and behavioral acceptance in AD01 section 10.
- [ ] Worker completes the existing C1–C5 batch under the replacement handoff, including live work when separately granted.
- [ ] Assess initiative, investigation, construction and retained use separately, then select the next architectural experiment.

The next useful work is implementation of these settled semantics. More design layers would not resolve the observed disconnect. The full worker assignment is [WORKER-EC02-AD01-BEHAVIORAL-COMPLETION.md](../docs/HISTORY.md#worker-ec02-ad01-behavioral-completion).
