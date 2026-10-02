# Worker brief U8: drive the three-arm prospective comparison through the new cycle

Repository `D:\AI\Agent-Society-v2-investigation-review`, branch
`codex/stage-09-opus-completion` at `42a4f04`. Clean tree. Work in place.

You own exactly these files:

- `scripts/s09_pilot.py`
- `tests/test_s09o_pilot.py` (new)

Do not edit any other file, and in particular do not edit
`tests/test_s09c3_policy_pilot.py` (7 tests) or `tests/test_s09m5_pilot.py` (8 tests).
Both must keep passing. If one of them genuinely must migrate because a contract changed,
STOP and report which test, which contract changed, and what the test's purpose was, so the
coordinator can migrate it. Do not edit production files other than the pilot.

## CORRECTION, round 2. Read this before anything else

A first attempt produced two regressions in `tests/test_s09m5_pilot.py`. Neither test is
wrong. Both keep passing. Do not edit them, and do not migrate them.

**C1. One candidate per ARM, not one per domain.** The first attempt gave P1 two
construction calls by constructing one candidate per domain. That is a misreading. The cap
sheet says "4 calls total: 1 initial + 1 repair per P1/P2". So each arm gets ONE candidate,
and its second call is reserved for a REPAIR of that same candidate if the first attempt
fails. A per-domain candidate scheme exhausts the cap with zero repair allowance. An
independent typed check agreed at 0.85, and agreed at 0.91 that per-domain candidates
violate the cap.

`test_doubled_pilot_verifies_green` pins the correct shape: P1 available with `calls == 1`,
P2 unavailable with `calls == 2`, three construction calls in that run. Reproduce exactly
that.

**C2. The domain the arm's single candidate does not cover runs the incumbent, explicitly
attributed.** A policy's applicability is one family, so one candidate covers one domain.
For the arm's other domain, run the incumbent, mark every such use record with a reason
naming why, and report that domain's comparison for that arm as NOT covered by a revised
policy. Do not construct a second candidate, do not reuse the same bytes for the other
family, and do not drop the domain or reduce the twelve assessment episodes. An independent
typed check chose this treatment at 0.93 with 0.91 confidence, over the alternatives.

**C3. The unavailable-arm path must still work.** The first attempt made the same scripted
failing constructor bind successfully, so the study could no longer represent an unavailable
arm. That is a regression in the rewiring, not a contract change; the typed check agreed at
0.81. `test_unavailable_arm_uses_incumbent_only` requires that for an unavailable arm every
one of its 8 use records has `executed == "incumbent"` and a `fallback_reason` starting
`arm-unavailable:`. That is honest attributed reporting of an absent arm, which is what
"missing arms remain missing" requires, and it is NOT the forbidden substitution. Keep it
working from the same scripted input.

To be explicit about the distinction that matters here: recording an absent arm as incumbent
with a reason that names the absence is required. Presenting an absent arm as a successful
revised arm, or quietly relabelling it, is forbidden. The first is bookkeeping, the second
is a false claim.

**C4. Reconcile with rule 3 of the original brief.** Rule 3 said a rejected or unavailable
arm must not be "silently" replaced by the incumbent. C3 above is the precise form of that:
not silent, explicitly attributed. There is no conflict.

---

## Why this matters

A typed review of the integrated source named this the single largest remaining threat to
the experiment's conclusion, at 0.58. The reason is blunt: the revision cycle was connected
to production last week, but the pilot still supplies each arm's policy directly. An
experiment that does not drive the connected mechanism does not measure it. Whatever the
comparison currently reports, it is not a measurement of the acquired-and-bound policy.

## What already exists

`scripts/s09_pilot.py` already holds the C3/N5 structure: `STUDY_ID`, `STUDY_ROOT`,
`ARMS = ["P0", "P1", "P2"]`, `PER_EPISODE_STEPS = 6`, `_authorize`, `_assess_specs`,
`_policy_identity`, `_method_repertoire`, `build_freeze`, `_policy_record`, `_run_episode`,
`_construct_arm`, `_embed_operations`, `_refusal_probes`, `_conformance_replay`,
`run_study`, `_dev_observations`, `main`. `_run_episode` already calls the public
`trajectory.run_campaign` with `constructor="model"`.

The new cycle, landed in `trajectory.py`, gives you:

- `run_campaign(..., policy_release=<release id>)` and
  `resume_campaign(..., policy_release=<release id>)`. When a release is named and no
  consumer is passed, production resolves the exact bound policy bytes from durable state
  through `records.load_freeze` via the binding provenance. Passing both a consumer and a
  release raises `ValueError`.
- `_construct_policy_revision` now continues past freeze into a policy-specific sealed
  assessment and then binds or records an explicit durable rejection or unavailability. The
  revision episode carries `disposition` in `{"bound", "rejected", "unavailable"}`, plus
  `release_id` and `bound_digest` when bound, and an `assessment` record.
- `records.export_campaign` now exports the policy sections and
  `records.verify_campaign` plus `scripts/s09_verify.py` verify them offline with no
  provider and no database.

Read `experiments/ad01/trajectory.py` lines 734-943, `experiments/ad01/policy_assess.py`,
and `tests/test_s09o_cycle.py` in full before changing the pilot.

## What to change

1. **P1 and P2 policies must come from the cycle, not from the script.** For each of P1 and
   P2, run the public development and revision path so that the arm's candidate policy is
   constructed from returned model bytes, frozen, assessed and bound by production. Take
   the arm's `release_id` from the revision episode. Do not call
   `open_revision_proposal`, `freeze_candidate`, `assess_frozen`, `assess_policy`,
   `freeze_protocol` or `bind_revision` from the pilot. If the pilot needs one of those, the
   production wiring is incomplete: STOP and report it.

2. **Assessment episodes must run under the bound policy.** Every assessment episode for P1
   and P2 must call the public path with that arm's `policy_release` and no injected
   consumer, so the policy actually being measured is the bound one. P0 keeps the frozen
   incumbent and names no release.

3. **A missing arm stays missing.** If an arm's candidate is rejected or unavailable, record
   that arm as rejected or unavailable with its reason. Do NOT silently fall back to the
   incumbent and do NOT relabel it P0. An incomplete comparison must report as incomplete.

4. **Preserve the C3/N5 schedule exactly.** At most four visible development episodes, two
   per domain. One policy candidate plus one repair for P1 and for P2, four construction
   calls maximum in total. Twelve matched assessment episodes over two fresh worlds per
   domain across three arms. Two sealed method-use tasks per assessment episode, one in
   scope and one a structural variation. Six policy steps and six model calls per episode as
   cumulative limits.

5. **P1 and P2 differ only in permitted experience.** Identical objective, interface,
   construction task and allowance. P2 additionally receives the permitted development
   experience. Nothing else may differ. Assert this in a test by comparing the two
   construction requests field by field and showing that only the experience differs.

6. **Freeze before assessment.** The preassessment freeze must record the actual acquired
   policy bytes and digests per arm, the effective configuration, the gateway adapter and
   model identity, the panel identities and the comparison rule, and the frozen method
   repertoire. Extend `build_freeze` rather than adding a second freeze path.

7. **Report the arms separately.** Report P2 against P0 and P2 against P1 as separate
   comparisons. Do not report a single aggregate verdict. Record construction delivery,
   executable validity, changed decisions and effects, downstream task quality, and complete
   resource cost as separate quantities. A changed digest alone proves none of them.

8. **Prove the HTTP adapter is on the full path before any live call.** `_http_gateway`
   already exists. Add a check, runnable with a controlled local HTTP server, that proves
   the real `HttpGatewayAdapter` carried the bytes that were constructed, frozen, assessed
   and bound. This is a preflight for the live study, so it must fail loudly if the
   configured adapter is not actually the one used.

## Tests: tests/test_s09o_pilot.py

Own only database names beginning `s09o_pilot`. Never touch `ec02test_*`, `inv_*`, or an
`s09_*` database you did not create. `tests/test_ad01_traj.py` has 5 pre-existing errors
from a missing `ec02test_adtr` database owned by another task; ignore it.

Use provider doubles and a controlled local HTTP server. No live calls.

Required cases, each asserting literal expected values:

1. A full doubled three-arm study runs end to end. P1 and P2 each obtain a
   `release_id` from a production revision episode whose `disposition == "bound"`, and every
   assessment episode for those arms names that release. Assert the executed policy digest
   in the assessment episodes equals the arm's `bound_digest`.
2. P0 names no release and runs the frozen incumbent.
3. An arm whose candidate is rejected is reported as rejected, contributes no release, and
   is NOT relabelled or replaced by the incumbent. Assert the study's own report says the
   comparison is incomplete.
4. The schedule limits hold: at most 4 development episodes, at most 4 construction calls,
   exactly 12 assessment episodes, exactly 2 sealed use tasks per assessment episode.
   Assert the actual observed counts.
5. P1 and P2 construction requests are identical except for the experience field.
6. The controlled HTTP path proves the real adapter carried the bound bytes.
7. The exported study verifies offline with `scripts/s09_verify.py`, no provider and no
   database.
8. A deterministic rerun with the same doubles produces the same study report.

## Verification you must run and report

```
wsl -d Ubuntu -u ubuntu -- bash /mnt/d/AI/s09o/gate.sh u8-pilot tests/test_s09o_pilot.py
wsl -d Ubuntu -u ubuntu -- bash /mnt/d/AI/s09o/gate.sh u8-regress tests/test_s09c3_policy_pilot.py tests/test_s09m5_pilot.py tests/test_s09o_cycle.py tests/test_s09o_causal.py tests/test_s09o_export.py tests/test_s09o_integrity.py tests/test_s09o_policy_assess.py tests/test_s09o_boundary.py
```

Report exact pass, fail, skip and error counts for both, plus a red result from before your
change for at least cases 1 and 3. The second command must show no failures. Let long runs
finish; a stream timeout is not a failure. Never report a count you did not observe.

Do not invert an assertion, weaken a runtime check, or delete a test to reach green.

## Style

No inline comments. Compact functions, data-driven repeated structure for the arm and
schedule tables, no abstraction layer with a single caller. Match surrounding formatting.
