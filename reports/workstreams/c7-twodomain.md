# C7 — one mission crossing both task structures

Lane C7 of the milestone-C build. Base `58aaae7`, branch `wt/c7-twodomain`,
forked from `58aaae7`. Offline, no live model call, no network, fixture
gateway only.

## The property this lane exists for

ONE mission entry crosses both selected task structures, in more than one
episode in each, and permitted experience advances across the crossing.

C1 built the entry (six fields on one `investigations` row). C6 made
suspend and resume answer from it. Neither ever ran a mission through more
than one structure, so the question was unanswerable rather than answered.

## The gap I was told to check, and what it actually is

`s09_arm_parity.py:39-46` claimed `swe` was "registered for addressability,
not because the harness can normalise its view", because `_run_arm` hands
every arm `contract_view`, "which demands exactly eight public-state
fields", and the SWE world publishes twelve.

**Both halves of that are false today, and the gap is the comment.** Measured
on this tree, in one run:

| step | Boolean/reducer | SWE |
|---|---|---|
| the world's own view | `boolean_active.public_state` — **8** fields | `SweSession.policy_view` — **12** fields |
| `admit_world_view` | `None` (admitted) | `None` (admitted) |
| `contract_view` | the **6** contract fields | the **same 6** |
| `admit_shared_view` | `None` | `None` |

The contract publishes **6** fields, not 8, and each world declares its OWN
field set against `VIEW_CONTRACT_FIELDS` (`:329-340`), so 8-against-12 is a
per-world declaration rather than a refusal. The test the comment cited,
`test_a_swe_arm_is_refused_by_the_harness_view_normaliser`, **does not exist
on this tree** — B18 replaced it with the admission.

So the honest repair was the comment, which is the file I own for view
normalisation. I did not touch `contract_view`, `admit_world_view`,
`admit_shared_view` or `VIEW_CONTRACT_FIELDS`, so no field count moved and no
existing check changed.

**I did not repair the `remaining` shape conflict B18 recorded.** The
contract publishes the `test` budget scalar where the SWE world publishes a
five-dimension mapping, so `swe.admits` raises `'int' object has no
attribute 'get'` when the guard reaches that turn. Every repair is a
widening rather than a repair, and B18's two measured reasons still hold.

## The crossing

`experiments/ad01/twodomain.py`. It calls `mission.record_mission`; it never
writes the six fields itself, because a second writer would be the second
owner C1 removed.

Three Boolean episodes, then three SWE episodes, all on the real worlds, no
model call. What crosses is thin and the module says so: **what transfers is
the predicate, not the answers.** A Boolean probe returns four output bits
about a hidden function; the SWE side has no way to spend that vector. What
it does spend is the distinction the observation established — an entry whose
expected and actual differ, whose result is well formed, is a *value* fault
and not an error — and it applies exactly that to classify its own
mismatching public tests. A transfer claiming more than this would be
fabricated, because nothing in these two worlds makes it true.

The observations are read from the view the world published to the driver,
captured inside `choose`. An earlier shape rebuilt the episode to re-read its
view and observed an unprobed session: zero observations for an episode that
probed eight. The test caught it, which is how I found it.

## The comparison is powered on one side only, and that is measured

**B8's census does not transfer to these instruments, so I measured this
lane's own.** B8 answered the power question for the frozen `software` and
`graph` families. My Boolean side is `boolean_rule` and my SWE side is
`s09_swe_world`. The cluster rule transfers; the counts do not.

Under the study's own rule `(family, template)`, at alpha 1/20, six clusters
required:

| structure | clusters | shortfall | powered |
|---|---|---|---|
| `boolean-rule-v1` | **1** | 5 | **no** |
| `software-fault-repair-v1` | 9 | 0 | yes |

The Boolean side's one cluster is not a count I guessed. `boolean_rule`
publishes **120 tasks with 120 distinct hidden tables and exactly one
published hypothesis class** — same `form`, same `class_digest`, same
`class_size`, every split, every seed. A contrast over it has one independent
unit however many tasks it runs, so no split choice and no panel can move it.
This is a stronger version of the thing the brief warned me about: the
Boolean/reducer structure cannot carry a powered comparison at all.

`cluster_census` returns power **per structure**, and `crossing_powered` is
the derived conjunction rather than a hardcoded `False`, so widening the
instrument would flip it instead of leaving a stale claim. A test pins both
halves, and I watched it fail when I forced every structure to report
`powered: True`.

## Honesty constraints held

**A failed acquisition stays a no-acquisition row.** No acquisition runs
here. `acquired_artifacts` is asserted `[]`, `retained_use` is asserted
`None`, and `frontier["acquisition"]` is `not-attempted`. The Boolean driver
commits nothing either, because committing a predictor needs a hypothesis the
instrument was never given and a guess would be a fabricated result rather
than a measurement.

**No DSL and no new notation.** Nothing new is authored. Every episode runs
through the world's own `run_episode` with the world's own actions. No new
table, no migration, no new owner: the crossing is two keys of one jsonb
value on the one row C1 created, and a test asserts via
`information_schema` that `investigations` is still the only table carrying
any mission field.

## Tests

`tests/test_inv_c7_two_domain.py`, mine alone. 6 passed.

| Test | Proves |
|---|---|
| `test_one_mission_row_carries_both_structures_and_is_not_a_join` | both structures live in ONE jsonb value on ONE row, and `information_schema` shows `investigations` is the only table carrying any mission field, so the crossing cannot be a join |
| `test_the_second_structure_sees_what_the_first_produced` | the SWE episodes consume observations **named by id** that the Boolean episodes produced, and each consumed input is a real input of the Boolean instrument |
| `test_each_structure_ran_more_than_one_episode` | `>= 2` episodes per structure, **counted from the entry**, on distinct task ids, with the entry order recorded |
| `test_both_structures_normalise_to_the_same_contract_field_count` | the normalisation claim at the **count measured today (6)**, read from `policy_action.view_contract()` so a widening fails; also pins 8 and 12 as the declared per-world counts |
| `test_the_boolean_side_cannot_be_powered_and_the_mission_says_so` | 1 cluster against 6 required, `powered is False`, shortfall 5, and `crossing_powered` derived |
| `test_a_failed_acquisition_stays_a_no_acquisition_row` | nothing authored is counted as acquired |

**Trained TDD.** The file was written first and watched fail: 5 failed on
`ImportError: cannot import name 'twodomain'`, and the view test passed
immediately because B18's fix had already landed.

**The regression was watched failing in both directions, three times.**
Not assumed, run:

| tamper | result |
|---|---|
| disable the cross-domain consumption (`if False`) | `test_the_second_structure_...` fails, `assert []` |
| one episode per structure | `test_each_structure_ran_more_than_one_episode` fails, `assert 1 >= 2` |
| report every structure powered | `test_the_boolean_side_cannot_be_powered...` fails, `assert True is False` |

A green run against a defect that was never installed proves nothing.

## Gate

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/c7.jsonl; \
  cd /mnt/d/AI/Agent-Society-v2/.worktrees/c7-twodomain && \
  PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/c7-twodomain/src \
  timeout 1500 /home/ubuntu/.venvs/as9/bin/python -m pytest \
  tests/test_inv_c7_two_domain.py tests/test_view_contract_swe.py \
  tests/test_s09_arm_parity.py tests/test_mission_entry.py \
  tests/test_inv_c6_suspend_resume.py tests/test_inv_b18_view_contract.py \
  -q -p no:cacheprovider'

45 passed in 46.07s (0:00:46)
S09ISO: dropped 13 database(s) for this run
```

Blast radius, all green: `test_inv_b1_swe_view`, `test_s09_swe_binding`,
`test_s09_representation_matrix`, `test_boolean_graph_arm`,
`test_ordering_graph_policy`, `test_m3_rule_instrument`,
`test_s09swe_contamination` — 105 passed. `test_s09m1_state`,
`test_s09_durable_state`, `test_s2_context` — pass.

## Pre-existing, reproduced not chased

`tests/test_p2c_ad01_resweep.py::test_resume_campaign_id_mismatch_refuses`.
`OperationalError: database "ec02test_p2c_unused" does not exist`. This is
C6's documented red, reproduced unchanged, not mine and not fixed.

## Files

- `experiments/ad01/twodomain.py` (new — the crossing and the census)
- `experiments/ad01/s09_arm_parity.py` (modified — the stale comment only)
- `tests/test_inv_c7_two_domain.py` (new, mine alone)

No migration. No new table. No change to C1's, C6's or C2's deliverables.
`git diff --name-only 58aaae7 HEAD -- reports/evidence/` is **empty**.

## What I would tell the coordinator

The milestone-C prototype requirement is met on the crossing and only
partially on the result: **one mission crosses both structures in three
episodes each with permitted experience advancing, and the comparison is
powered on the SWE side alone.** The Boolean side is one cluster against
six and no panel changes that, so a "two-domain result" is not available
from these two instruments. If a powered Boolean comparison is wanted, the
Boolean instrument has to publish more than one hypothesis class, and that
is a change to `boolean_rule`'s class, not to anything in this lane.

## Final process count

Zero.

Co-Authored-By: Claude Code <noreply@anthropic.com>