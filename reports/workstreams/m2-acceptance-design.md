# M2 acceptance demonstration: design and run plan

Read-only investigation at `7a00676`, branch `wt/m2design`. Nothing here ran
pytest, WSL, a live route or a database. Every claim below carries `file:line`
from that commit; inferences are labelled as such. Nothing in this document is
implemented.

The conclusion a reviewer needs first: **five of the eight M2 clauses are
demonstrable through one public entry today. The causal clause, which is the
one M2 exists to prove, is not — and the reason is a single unrepairable
string mismatch, not a missing test.** That finding is section 4.

---

## 1. The public mission entry

### What a reviewer calls

```
.venv/Scripts/python.exe scripts/invl02_live.py run-e0 --dsn <DSN> --out <DIR>
```

`main` dispatches `run-e0` at `scripts/invl02_live.py:4393-4400`. That verb
calls `run_e0` (`scripts/invl02_live.py:2161`), which calls
`_run_frontier_investigation` twice (`scripts/invl02_live.py:2191` control arm,
`:2200` live arm).

`_run_frontier_investigation` (`scripts/invl02_live.py:1934`) is the correct
single chain. It is the one function that walks experience → choice → admitted
effect → observation → artifact → restart, and it is reached by all four call
sites:

| Call site | Line | Arm | Used by |
|---|---|---|---|
| `run_e0` | `:2191` | `control` | `run-e0` |
| `run_e0` | `:2200` | `live` | `run-e0` |
| `run_e12` | `:2699` | `P1`/`P2` | `run-e12` |
| `run_e12` | `:2808` | `control` | `run-e12` |

The candidate in the assignment is correct. Verified at `7a00676`, not assumed.

### Why `run-e0` and not `run-e12`

`run-e12` needs a frozen four-arm study with a grant cap sheet, a route
preflight and two permitted-history arms (`scripts/invl02_live.py:2611`,
`:2716-2726`). `run-e0` is the two-arm form of the same chain and is the
smallest entry that still carries all eight clauses. Design M2 against
`run-e0`; use `run-e12` as the replication path once the E0 arm is green.

### Arguments a reviewer must supply

| Argument | Source | Requirement |
|---|---|---|
| `--dsn` | operator | A PostgreSQL DSN. Every production read/write in the chain goes through `mission.connect` (`experiments/ad01/mission.py:537`). **Not satisfiable on this host.** |
| `--out` | operator | A directory already holding `freeze.json` from `freeze-e0` (`scripts/invl02_live.py:2164`). |

Two environment variables are read before any work happens:

| Variable | Line | Requirement |
|---|---|---|
| `S09_M5_LIVE_GRANT` or `INVL02_LIVE_GRANT` | `:106-110` | Must be non-empty or `_require_grant` raises before the run starts. |
| `INVL02_LIVE_MODEL` | `:113-118` | Must equal `freeze["route"]["requested_model"]` (`:2167-2168`) and `live.OUTPUT_ROUTE` (`:2169-2171`). |

`run_e0` validates the freeze against `STUDY_ROOT_E0` (`:2165`) and requires a
route preflight record (`:2173`, `_require_route_preflight` at `:676`). A
failed preflight returns `_e0_unavailable` (`:2175`, `:2102`) rather than
raising, so a route refusal is distinguishable from a program failure in the
output JSON. That is the M1 repair at `PREFLIGHT_OUTCOMES`
(`experiments/ad01/live_construct.py:1648-1656`) working as intended.

---

## 2. The eight clauses and where each is evidenced

Two reads are worth stating before the table.

**The owner is unified for the mission row, but the frontier store is still a
JSON file.** `ensure_live_store`
(`experiments/ad01/live_construct.py:1062`) reads the mission through
`mission.read_mission` (`:1091`) and holds its identity in
`frontier.StoreIdentity` (`:1059`). The quiescence predicate is the SQL one,
`mission.is_quiescent`, called from `_require_quiescent` at
`experiments/ad01/live_construct.py:1333`. That is the M1 repair and it has
landed. But `FrontierStore` is still constructed at
`experiments/ad01/live_construct.py:1126` and
`experiments/ad01/improve_channel.py:2526`, and the run reads
`store.pending_effects` (`scripts/invl02_live.py:1979`) and
`store._doc["opportunities"]`
(`experiments/ad01/improve_channel.py:1954,1995`) directly. The mission row
owns the mission; the JSON store still owns the frontier. M2 can demonstrate
the clauses against this and must say so rather than claim the migration
finished.

### Permitted experience

| | |
|---|---|
| Producer | `live_construct.choose_next_work` (`experiments/ad01/live_construct.py:1175`), fed by `scripts/invl02_live.py:1962-1965` |
| Exact value to read | `store.private_state` (`experiments/ad01/frontier.py:984`) and the `view["experience"]` the operate step saw |
| Source of the view field | `experiments/ad01/frontier.py:1846-1852` |

**Demonstrable, but read the wrong field.** The experience the operate policy
receives is `view["experience"]`, built from
`self._doc["observations"]` at `experiments/ad01/frontier.py:1846-1852`. The
private state is at `:984` and is a separate document field.

The clause is satisfied in form but not in substance. The two experience lists
at `scripts/invl02_live.py:1958-1961` are hand-authored literals:

```python
preserved = [{"observation_id": "obs-seed", "task": dev_task, "verdict": "preserved"}]
mismatch = [{"observation_id": "obs-seed", "task": dev_task, "verdict": "mismatch"}]
```

No effect, observation or grant produced these. They are literals typed into a
study script. The clause M2 wants is that *permitted experience* reaches the
policy; that it does happen. What is not shown is that permitted experience
arose from the chain rather than from a constant. Section 4 is why that matters.

### Program choice

| | |
|---|---|
| Producer | `improve_channel.run_operate_step` (`experiments/ad01/improve_channel.py:1885`), reached from `live_construct.choose_next_work` (`experiments/ad01/live_construct.py:1186`) |
| Exact value to read | `result["executed_digest"]` (`experiments/ad01/improve_channel.py:1916`) and `store.active_digest` |
| Returned to the study as | `choice_preserved` / `choice_mismatch` (`scripts/invl02_live.py:2064-2065`) |

**Demonstrable.** The executed source digest is recorded and returned. The
program is the authored control bound by `bind_live_control`
(`experiments/ad01/live_construct.py:1161`, called at
`scripts/invl02_live.py:1953`) and asserted to be `authored-control`
(`:1956`). The package carries `package_digest`, `op_digest` and `imp_digest`
(`experiments/ad01/improve_channel.py:1698-1701`).

### Admitted effect

| | |
|---|---|
| Producer | `live_construct._admit_live_effect` (`experiments/ad01/live_construct.py:1223`), called from `execute_chosen_work` (`:1306`) |
| Exact value to read | `SELECT in_flight FROM investigations WHERE id = $1` via `mission.read_in_flight` (`experiments/ad01/mission.py:490-507`) |
| Effect identity | `attempt_id = "att-%s-%s" % (investigation_id, key)` (`experiments/ad01/live_construct.py:1253`) |

**Demonstrable.** The effect is held on the SQL row before the effect runs, and
released after it settles (`execute_chosen_work`, `:1307-1312`). The ordering
is documented at `:1226-1229` and is correct: a record written on completion
is missing exactly when a crash lands.

### Observation

| | |
|---|---|
| Producer | `improve_channel.execute_operate_action`, probe branch (`experiments/ad01/improve_channel.py:2144-2153`) |
| Exact value to read | `observation["verdict"]` — read `experiments/ad01/improve_channel.py:2148` |
| Attribution requirement | `settle` requires `operation_id` or `receipt_identity` on the stored observation (`experiments/ad01/frontier.py:2142-2144`) |

**Demonstrable, and this is where the causal clause dies.** The only verdict
the production operate path writes is the literal `"observed"`
(`experiments/ad01/improve_channel.py:2148`). A tree-wide grep for
`"mismatch"` across `experiments/`, `scripts/` and `src/` returns nothing. See
section 4.

### Checked artifact

| | |
|---|---|
| Producer | `live_construct.run_live_improve_round` via `scripts/invl02_live.py:1975` |
| Exact value to read | `candidate["control_id"]` (`:1976`), asserted `origin == "authored-control"` (`:1977`) and `source_kind == "fixed-menu"` (`:1978`) |
| Digest | `package["package_digest"]` (`experiments/ad01/improve_channel.py:1700`) |

**Demonstrable, with a scope caveat.** The artifact is built and its identity
is checked. But `source_kind == "fixed-menu"` means the constructor selected
from an authored menu (`experiments/ad01/improve_channel.py:1695`). M3's probe
measured that a menu cannot express the choice M2 needs: 33 of 39 SWE tasks
admit exactly one repair and **zero admit two plausible ones**
(`reports/workstreams/m3-expressive-probe.md:136-141`). A fixed menu has one
cell. The clause "checked artifact" is satisfied; the clause "the program
selected later work" is not, because on the improve side there is nothing to
select between.

### Retention and binding

| | |
|---|---|
| Producer | `live_construct.retain_acquired` (`experiments/ad01/live_construct.py:1012`), called at `scripts/invl02_live.py:2040` |
| Binder | `live_construct.bind_retained_acquisition` (`experiments/ad01/live_construct.py:1556`), called at `scripts/invl02_live.py:2209` and `:2707` |
| Exact value to read | `revision["disposition"]` and `revision["bound_digest"]` (`experiments/ad01/live_construct.py:1569`) |

**Demonstrable.** The binder verifies the retained package is in
`treatment_arms["acquired"]` (`:1570-1575`), that its response digest matches
(`:1576-1580`), and refuses on mismatch rather than binding anyway
(`:1585-1591`). Method release and policy binding carry separate identities:
the M1 repair.

**Caveat.** The retained-use history column has no writer anywhere in the
tree. Grep for `retained_use` across `experiments/`, `scripts/` and `src/`
returns nothing. Migration 0021 dropped the write-only columns per
`experiments/ad01/twodomain.py:380-386`, but retained-use history is the one
M0 named as having neither reader nor writer
(`reports/workstreams/m0-ownership-map.md:20`) and it has gained neither. The
clause "retention/binding" is satisfied through `treatment_arms`; the clause
"retained-use history is durable" is not, and nothing currently writes it.

### Fresh-process use

| | |
|---|---|
| Producer | `scripts/invl02_live.py::restart_use` (`:2258`), verb `restart-use` (`:4451-4465`) |
| Exact value to read | `result["records"]` count (`:2282`) |
| Binding resolution | `trajectory.run_use(..., release_id=release_id, policy_source=policy_bytes)` (`:2277-2280`) |

**Demonstrable — but the in-run restart at `:1995` is not it.** `restart_store`
is documented as reopening "in this process"
(`experiments/ad01/live_construct.py:1627`). A fresh-process demonstration has
to be the separate `restart-use` verb, which reads the policy source from disk
(`scripts/invl02_live.py:2265`) and resolves an explicit `release_id`
(`:2278`). The M1 requirement that a retained method resolves its actual
binding rather than a repertoire scan is met here: `release_id` is a required
CLI argument (`:4454`) and is passed through.

### Both supported domains in one mission

| | |
|---|---|
| Producer | `scripts/invl02_live.py::_live_environments` (`:1830`), passed to `mission.record_mission` (`:1928`) |
| Exact value to read | `mission.read_mission(dsn, investigation_id).environments` |
| Domain instrument set | `INSTRUMENTS = ("boolean-rule-v1", "deliberation")` (`experiments/ad01/frontier.py:68`) |

**Demonstrable, as declaration.** The mission row carries both instruments:
`boolean-rule-v1` environments (`:1831,1840`) and `deliberation` environments
over the SWE task ids (`:1835`). The opportunity set carries both too
(`_live_opportunities`, `:1849-1896`): `opp-sw-*` and `opp-use-*` over SWE
tasks, `opp-rule-dev-*` over boolean tasks.

**The execution does not cross domains.** Every effect the chain executes goes
through `_boolean_rule.RuleSession` (`experiments/ad01/improve_channel.py:2139`).
The `deliberation` opportunities are proposed and become admissible, and then
nothing executes them. M2 says "include both supported domains in the mission".
The mission includes both. It does not demonstrate that a program chose work
in the second domain. State it that way.

---

## 3. The causality requirement

### What M2 demands

> Show a real choice of probe, construction, reuse, continuation or stop which
> changes with permitted evidence. ... Labels and observation IDs alone do not
> demonstrate causal influence.

The mechanism exists and is real. `SHARED_OPERATE_SOURCE`
(`experiments/ad01/improve_channel.py:47-78`) branches on experience:

```python
last = exp[-1] if exp else None
if last is not None and last.get("verdict") == "mismatch":
    alt = [o for o in frontier if o.get("task") != last.get("task")]
    choice = alt[0] if alt else frontier[0]
else:
    choice = frontier[0]
```

Traced statically against the frontier order
`admissible()` produces (`experiments/ad01/frontier.py:1820-1826`, sorted by
cost then opportunity id), with the opportunities `_live_opportunities` builds:

| Experience | Chosen opportunity |
|---|---|
| `verdict == "preserved"` | `opp-first` |
| `verdict == "mismatch"` | `opp-followup` |

The choice does change. The program reads `experience` and picks a different
member of the frontier. That is exactly what M2 asks for, and the arithmetic
works.

### Why it does not count

The branch fires on the literal string `"mismatch"` at
`experiments/ad01/improve_channel.py:59`. The only verdict any production
observation carries is `"observed"`
(`experiments/ad01/improve_channel.py:2148`). A grep for `"mismatch"` across
the whole tree outside `tests/` returns nothing.

**Therefore the branch is dead in production.** Every real observation the
chain produces has `verdict == "observed"`, falls to the `else` at
`experiments/ad01/improve_channel.py:63-64`, and takes `frontier[0]`. The
policy's next-action choice never changes with permitted evidence in a real
run. `observation_dependent` (`scripts/invl02_live.py:2066-2067`) is `True`
in the output because the study feeds the dead branch two literals, not because
the chain branched.

This is the M2 failure in one line, and it is the failure M2's own sentence
warns about. `scripts/invl02_live.py:2066` computes
`observation_dependent` from two hand-typed dictionaries at `:1958-1965`. It
reads as a causal result. It is a tautology over two constants.

### The control triple, from identical starting conditions

Per M2's requirement for effectful, no-op and disconnected controls. All three
must start from one store state, one program digest, one frontier and one
authority. The only permitted difference is the permitted experience.

**Setup held identical across all three.** Same store opened by
`ensure_live_store` under one `investigation_id` (`scripts/invl02_live.py:1948-1950`).
Same bound program `make_control("low")` (`:1953`). Same proposed opportunities
(`:1951`). Same `step_view` frontier, because `admissible()`
(`experiments/ad01/frontier.py:1820`) is a pure function of the opportunity set
and costs. Same `authority_remaining`, from `LIVE_AUTHORITY`
(`experiments/ad01/live_construct.py:1041`) via the store's own spend.

**What varies: the `experience` list passed to `choose_next_work` only.**
`live_construct.choose_next_work` overwrites `view["experience"]` after
building the view (`experiments/ad01/live_construct.py:1183-1184`), so the
frontier, mission, obligations, retained set, instruments and environment
digest are identical by construction. This is the right seam — the experiment
needs no new plumbing.

| Control | `experience` passed | Expected read |
|---|---|---|
| **Effectful** | the real `store.observations` after a probe on a task *also* in the frontier, with that observation's true verdict | the branch taken must be the one the real verdict selects |
| **No-op** | the same list with the last verdict rewritten to `"observed"` | choice must be **identical** to the effectful arm |
| **Disconnected** | `[]` (no experience at all) | choice must equal `frontier[0]` regardless of what ran |

**The decisive control is the no-op arm, and it is currently impossible to
pass.** A no-op arm requires a real observation whose verdict, rewritten to
`"observed"`, changes nothing. Since every production verdict *is* `"observed"`,
the effectful arm and the no-op arm are the same arm by construction. There is
no verdict value available that both (a) a real observation can carry and
(b) the policy branches on. That is the blocker stated precisely.

**What a checker reads.** Not labels. Read the *admitted effect identity on the
SQL row*, for both arms, from `mission.read_in_flight`
(`experiments/ad01/mission.py:490-507`):

```sql
SELECT in_flight FROM investigations WHERE id = '<investigation_id>';
```

- Effectful arm: an entry whose `decision.inputs.opportunity_id` is the
  non-`frontier[0]` member.
- No-op arm: an entry whose `decision.inputs.opportunity_id` is the same as the
  effectful arm's.

If the two rows carry the same `decision`, the choice did not track the
evidence. If the effectful row's opportunity id equals `frontier[0]`, the
evidence did not move the choice either, and the demonstration fails on the
other side. The verdict string never appears in this check. The `attempt_id`
and `operation_id` do, and neither encodes a verdict — `attempt_id` is
`"att-%s-%s"` over investigation and opportunity key
(`experiments/ad01/live_construct.py:1253`), and the operation id is derived
from package digest and canonical view
(`experiments/ad01/improve_channel.py:1844-1848`).

### The falsification criterion

**Remove the permitted experience and re-run the choice step. If the chosen
opportunity is identical, the chain is not connected.**

Stated as a reviewer applies it: take the mission's `in_flight` decisions,
take the frontier the program saw, and confirm the decision is the frontier
member the experience selected rather than `frontier[0]`. Then delete the
experience that selected it and confirm the decision moves. Two runs, one
variable, opposite outcomes. Anything less is a label.

A second falsifier, and the stronger one: **if every admitted decision in the
mission's `in_flight` is `frontier[0]`, the causal clause is not demonstrated
no matter what the study JSON says.** At `7a00676` that is the predicted
outcome, because the only production verdict is `"observed"`
(`experiments/ad01/improve_channel.py:2148`).

---

## 4. What must be fixed first

### Blocked on instrument repair

**Causal influence (the hard part).** Blocked on the verdict vocabulary, not
on a scorer. `SHARED_OPERATE_SOURCE` branches on `"mismatch"`
(`experiments/ad01/improve_channel.py:59`); production writes `"observed"`
(`:2148`). Three options, and the choice is not mine to make:

1. Have the checker emit the verdict the policy branches on. The checker is
   `boolean_rule` (`experiments/ad01/improve_channel.py:2139`); a probe that
   *refutes* the incumbent prediction is a real outcome and would carry
   `"mismatch"` honestly.
2. Change the policy to branch on a field that already varies. `observation["y"]`
   (`experiments/ad01/improve_channel.py:2150`) versus the program's prediction
   would be the substantive signal, and it is real evidence rather than a label.
3. Branch on the observation's existence and task rather than a verdict string.

Option 2 is the honest one and it is also the smallest: the signal is already
recorded, and comparing a real result against the bound program's prediction is
what "changes with permitted evidence" means. Options 1 and 3 leave the policy
reading a string someone typed. I am not implementing any of them — that is a
lane, and this document is a design.

**Constructive selection.** Blocked on the expressive probe, not on a bug. 33 of
39 SWE tasks admit exactly one repair and zero admit two plausible ones
(`reports/workstreams/m3-expressive-probe.md:136-141`). The production
constructor is `source_kind == "fixed-menu"`
(`experiments/ad01/improve_channel.py:1695`), which has one cell. M2's "real
choice of probe, construction, reuse, continuation or stop" cannot be shown on
the construction side until the instrument admits more than one defensible
option. This is M3's repair and M2 waits on it.

**SWE-domain execution.** The AD01 software and graph worlds are marked
**REMOVE** (`reports/workstreams/m3-instrument-census.md:146-148`), and the
public task view leaks through `template`
(`reports/workstreams/m3-instrument-census.md:33-36`). Demonstrating a choice
*in* the SWE domain requires an instrument that does not expose its own answer.
Until the leak is closed, SWE opportunities can be declared in the mission but
they cannot carry a selection claim.

### Demonstrable now

Five clauses, through one public entry, with no instrument repair:

| Clause | Why it is reachable |
|---|---|
| Program choice | `run_operate_step` executes and returns `executed_digest` (`experiments/ad01/improve_channel.py:1916`). |
| Admitted effect | `_admit_live_effect` holds on the SQL row before execution (`experiments/ad01/live_construct.py:1257-1260`). |
| Observation | Probe branch writes an attributable observation (`experiments/ad01/improve_channel.py:2144-2153`). |
| Checked artifact | Candidate built and identity asserted (`scripts/invl02_live.py:1976-1978`). |
| Retention and binding | `bind_retained_acquisition` verifies and refuses on mismatch (`experiments/ad01/live_construct.py:1570-1591`). |

Plus two partially reachable, and I will not overstate either:

| Clause | Reachable part | Blocked part |
|---|---|---|
| Permitted experience | The view field is populated and reaches the policy (`experiments/ad01/live_construct.py:1184`). | The lists are literals (`scripts/invl02_live.py:1958-1961`), not chain-produced. |
| Fresh-process use | `restart-use` resolves an explicit `release_id` and reads policy bytes from disk (`scripts/invl02_live.py:2265,2278`). | The in-run restart at `:1995` is in-process by design (`experiments/ad01/live_construct.py:1627`). |
| Both domains | Both instruments are declared (`scripts/invl02_live.py:1831-1841`; `experiments/ad01/frontier.py:68`). | Execution crosses only `boolean-rule-v1` (`experiments/ad01/improve_channel.py:2139`). |

---

## 5. Run plan

Constraints on this host, verified not assumed: `.venv/Scripts/python.exe`
exists and carries psycopg 3.3.5 on Python 3.13.14; `psql` is absent; `docker`
is absent; `127.0.0.1:4000` is listening (PID 30360). Per
`reports/workstreams/windows-env.md:30-32`, pytest and WSL stay off this host.

| Step | Command | Needs | Produces | Stops here? |
|---|---|---|---|---|
| 1 | `ast.parse` every file in the chain via `.venv/Scripts/python.exe` | interpreter | syntax gate | Runs |
| 2 | `freeze-e0 --out <DIR>` | interpreter, env model var | `freeze.json` | Runs |
| 3 | `preflight --out <DIR>` | live route at 4000 | preflight record | Runs, spends one model call |
| 4 | `run-e0 --dsn <DSN> --out <DIR>` | **PostgreSQL** + route + grant | `e0-run.json`, store, receipts | **Blocked.** No server. |
| 5 | read `in_flight` for both arms | **PostgreSQL** | the causal check | **Blocked.** |
| 6 | `restart-use --dsn ... --campaign ... --release ...` | **PostgreSQL** | fresh-process records | **Blocked.** |

**Steps 4, 5 and 6 all need a database and cannot run on this machine.** Every
one of them calls `mission.connect` (`experiments/ad01/mission.py:537`) or
`settlement.store` (`scripts/invl02_live.py:2267`). There is no server, no
client and no container runtime to start one. Steps 1 through 3 run and stop at
the database boundary.

The honest disposition is the one WORKER-PROMPT:166-171 names. Deliver the
connected mechanism with precise attempted/unrun dispositions. Do not
manufacture a run.

What a reviewer can do on a machine with PostgreSQL: steps 4 through 6 as
written, then apply the section 3 check to the resulting `in_flight` rows. On
this host the section 3 check is **predicted to fail**, for the reason at
`experiments/ad01/improve_channel.py:59` versus `:2148`. Running it would
confirm a finding, not demonstrate the clause.

---

## 6. What would falsify the demonstration

A reviewer should reject M2 if any of these is observed.

1. **The choice survives without the evidence.** Remove the experience from the
   choice step and re-run. If `in_flight.decision.inputs.opportunity_id` is
   unchanged, the policy did not read the evidence. This is the primary test.
2. **Every admitted decision is `frontier[0]`.** The policy ran a fixed
   schedule wearing a frontier's clothes.
3. **`observation_dependent` is true while both arms produced the same admitted
   effect.** The field at `scripts/invl02_live.py:2066-2067` is computed from
   two literals (`:1958-1965`); it can read true with no causal content at all.
   Never accept this field as the demonstration.
4. **The mission row and the store disagree about the owner.** The row is keyed
   on `_live_investigation_id` (`scripts/invl02_live.py:1907`) and the store
   carries that identity through `StoreIdentity`
   (`experiments/ad01/live_construct.py:1059`). A store opened under a different
   investigation is refused by `_open_owned_store` (`:1113-1127`). If the
   reviewer's store and mission name different investigations, the chain is
   split.
5. **Admitted work survives a restart under different bytes.** Admission carries
   `program_digest` (`experiments/ad01/live_construct.py:1259`). If a resumed
   effect runs under a different digest than the one admitted, resume recomputed
   the work instead of finishing it.
6. **A `deliberation` opportunity ever receives an admitted effect.** Both
   instruments are declared in the mission, but every production effect goes
   through `boolean_rule.RuleSession`
   (`experiments/ad01/improve_channel.py:2139`). A SWE effect appearing is not a
   success — it means the two-domain declaration was taken as a two-domain
   execution.
7. **The retained package binds despite a digest mismatch.**
   `bind_retained_acquisition` returns `disposition: "retained"` with a reason
   on a store it cannot read (`experiments/ad01/live_construct.py:1566-1575`).
   That value reads as a pass and is not one. Check `bound_digest` and the
   reason, not the disposition alone.
8. **The run reports success while `status` is `incomplete`.** `run_e0` returns
   `"available"` only when acquisition retained *and* the revision bound
   (`scripts/invl02_live.py:2221-2225`); otherwise `incomplete`, which is a
   valid null, not a green run.

---

## Disposition

The design is complete and the entry is verified. The demonstration is
**blocked on this host** at the database boundary, and the causal clause is
**blocked on instrument repair** at
`experiments/ad01/improve_channel.py:59`.

Five clauses are demonstrable through `run-e0` today. The clause M2 exists to
prove — that the program's next-action choice changes with permitted evidence
— cannot be demonstrated, and the reason is one string that production never
emits. That is a finding, not a gap to paper over, and no control design fixes
it until a verdict vocabulary the policy can read exists.