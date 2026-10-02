# N-36 and N-65, settled by measurement

Two liabilities parked as NEEDS HUMAN across many documents. Both are settled
here by running something and reading the result. Where a number or a claim
was wrong, it is corrected in place; no historical record and no evidence file
is touched.

---

## N-36 — containment

**Status: the containment claim was false, the docstring understated the
exposure, and a real boundary now exists.** Committed at `94443a7`.

### 1. What the launcher actually provides

Measured, through a real `LocalLauncher.dispatch`, not read off a docstring.
The child's environment is exactly:

```
['LANG', 'PATH', 'SETTLEMENT_OPERATION']
```

`SETTLEMENT_OPERATION` is the operation id (`launcher_local.py:476`), not the
seed. So the seed is **not** an argument, **not** an environment variable, and
**not** a file the launcher stages. The key reaches the child as ordinary
source: `experiments/ad01/worlds.py:50` reads
`TASK_ID_KEY = b"ad01-task-id-hmac-v1"`, and a child that can open a file can
open that one.

The admission path confirms there is no gate between the two. `worlds.py`'s own
comment at 44–49 says the key "is in the repository" and "is not a defence
against an adversary who reads this file" — which was correct, and which the
launcher docstring never mentioned. The docstring pointed at the environment
scrub as the protection. The scrub protects the seed. It never protected the
source.

### 2. Is the recovery invertible

**Yes, fully, and it is worse than "a key subject to further checks."**

```
recovered seed    : 4
recovered order   : ('verify', 'build', 'analysis', 'deploy')
true order        : ('verify', 'build', 'analysis', 'deploy')
fully invertible  : True
launcher wall_ms  : 45
```

The seed *is* the recipe. `second_active.make_task:59-64` seeds a
`random.Random` from `sha256("<instrument>/<split>/<seed>")` and calls
`rng.sample(JOB_IDS, 4)`, so recovering the seed reproduces the answer
exactly. The finding's 959 ms is a slower machine; the recovery is a thousand
HMACs, and it happened in single-digit milliseconds here. The test asserts the
recovered **order**, not just the seed, because that is the claim under test —
asserting only the seed would pass for a recovery that still needed more work.

### 3. The real attack surface

The census, which is what determined the shape of the fix:

| Actor | Reaches the key? |
|---|---|
| `LocalLauncher` child, no deny list | yes — full read of the repo |
| STEP arm (`method_exec._STEP_DRIVER`, :1220) | yes — untrusted `policy.py` is the code being run |
| ad01 method arm (`method_exec._DRIVER`, :749) | yes — and it *imports* the repo (`sys.path.insert(0, root)`) |
| gVisor launcher | not measured — `runsc` and `docker` are absent on this host, so `probe_gvisor` returns `INCOMPATIBLE_VERSION` and the profile cannot be selected |

The untrusted policy does reach the launcher, and it is the *intended* path:
`boolean_policy.py:93` and `method_exec.py:1078,1349` all construct a
`LocalLauncher` and dispatch a staged, digest-checked, model-authored policy
through it. So containment is genuinely in scope — the untrusted code is the
thing this component exists to run.

### 4. What was built

A boundary, because the standing instruction is not to close with a digest and
a docstring change would leave the property false.

`read_deny` on a dispatch payload installs a **Landlock** ruleset in the child
between fork and exec. The denied roots are subtracted from the allow roots,
and nested allow roots are collapsed because Landlock rejects a rule nested
inside one already added. The ruleset is built *before* `Popen` returns, not
after the child proves itself well behaved. A dispatch that asks for
confinement the kernel cannot provide is **refused** (`read-boundary-unavailable`)
rather than run unbounded.

Why Landlock and not gVisor: gVisor is not installed here, so selecting it is
not a choice this deployment can make. Landlock is in the kernel, needs no
image and no runtime, and the profile-specific fallback already exists for
gVisor — this is not a second mechanism beside the first, it is the mechanism
the first was already deferring to, made reachable where the first is absent.

The census is why the boundary is **per dispatch** rather than a global
switch. The STEP driver loads its policy from the work directory and imports
nothing from the repository, so it is unaffected by denying the repo. The ad01
method driver does `sys.path.insert(0, root)` and genuinely needs it. Turning
the boundary on globally would have broken the ad01 arm; declaring it per
dispatch means the caller states what the child needs. That asymmetry is
asserted by `test_the_deny_does_not_break_a_child_that_needs_only_its_work_tree`,
which is the census in test form: a boundary that stops the attack by hiding
the child's own work tree has not fixed anything, it has broken every policy.

### The probe does not lie

This is the part worth keeping. `probe_landlock` originally returned
`available=True` here, because the kernel reports **ABI 8** and the ruleset
syscalls all succeed. That was wrong. Landlock requires `no_new_privs`, and on
this host `PR_SET_NO_NEW_PRIVS` is **silently dropped for a Python process**:

```
C binary, same shell:      NoNewPrivs: 1
Python process, same shell: NoNewPrivs: 0
```

The call returns 0 in both cases. `/proc/self/status` disagrees. A probe
that trusted the return code would have let a dispatch record confinement that
was never applied — the digest the ledger forbids, wearing a different hat. The
probe now reads the flag back.

The confinement itself is proven to work, out of band, in a process that *can*
set the flag. With `/usr`, `/usr/lib/x86_64-linux-gnu`, `/bin`, `/tmp` allowed:

```
BLOCKED  /home/ubuntu/AI/Agent-Society-v2/experiments/ad01/worlds.py  Permission denied
READABLE /usr/lib/python3.12/os.py                                     31 bytes
```

The denial works and policies still run. What is blocked in this environment is
setting the prerequisite, not the confinement.

### What the containment label says

Receipts still carry `containment=False`. Landlock confines the filesystem; it
is not gVisor, and the profile is still a bounded subprocess. It now carries
one real boundary instead of a promise of one. Raising the label would have
been the digest.

### Not done, and why

- **gVisor is not measured.** `runsc` and `docker` are absent on this host.
  The stronger boundary is unverified here; `probe_gvisor` correctly reports it
  unavailable and `RunscLauncher` refuses. If this study needs network and
  syscall isolation, not just filesystem reads, Landlock is not that.
- **The two denial tests skip here**, quoting the probe's reason verbatim. They
  will run on any host whose Python can set `no_new_privs`. A passing run on
  this machine would have been a false green, so the skip is the honest result.
- **The ad01 method arm still needs the repository**, so it cannot be given a
  `read_deny` covering the repo without breaking it. Closing that would mean
  staging `experiments.representation.reducers` into the child's work tree and
  dropping the `sys.path` insert — a change to `method_exec._DRIVER` and its
  digest, which is outside this lane's owned paths. **Reported, not edited.**

---

## N-65 — the 18688 figure

**Status: the figure is real, sourced, and the documents describing it are
wrong about it in three different ways.** No retraction.

### 1. Which files are primary

None of the 13 is primary. All 13 restate one number, and the number's own
history is the primary record: it was introduced as a **test assertion** in
`f3af21a` ("Keep provider charges, dispatch counts, and reservation units
apart"), in the tests that replaced nine assertions encoding the dimensional
defect that commit repaired.

`reports/PROJECT-LEDGER.md:88` is the closest thing to a primary document, and
even it is wrong — see below. The one file to read is the commit:

```
$ git show f3af21a -- tests/ | grep -A 3 'sizing.total_units'
+    assert {estimate.prompt_characters for estimate in p1} == {980, 981}
+    assert {estimate.prompt_characters for estimate in p2} == {1318, 1319}
+    assert {estimate.units for estimate in p1} == {2294}
+    assert {estimate.units for estimate in p2} == {2378}
+    assert sizing.total_units == 4 * 2294 + 4 * 2378
+    assert sizing.total_units == 18688
```

### 2. Which currency 18688 is in

**Reservation units, in `estimated-budget` units** — the broker's own exposure
currency, `broker.exposure_schedule(MODEL_INFERENCE, ...)` at
`broker.py:137-152`. Not a dispatch count, not provider units, not held
internal units. `_model_exposure` returns
`(sum(len(m["content"]) for m in messages) // 4 + 1 + max_output_tokens) * (retries + 1)`
labelled `"estimated-budget"`.

**It is a pre-flight sizing of a campaign, not exposure held.** This is the
decisive distinction, and the repo already had the type for it:
`ReservationAllowance` in `s09_exposure_ledger.py:425`, whose docstring says a
stand-in per-dispatch constant "would be exactly the invented number this
replaces." 18688 is the *derived* sizing, the thing that type was built to
produce.

### 3. Is the number correct

**Yes, and it is recomputable from surviving artifacts.** Recomputed through
the broker's own schedule, from the per-prompt character counts recorded in the
introducing test:

```
chars=980  -> 2294     chars=1318 -> 2378
chars=981  -> 2294     chars=1319 -> 2378
4*2294 + 4*2378 = 18688
```

**18688 = 4 × 2294 + 4 × 2378**, exactly. Four P1 requests priced at 2294 each
and four P2 requests priced at 2378 each, which is the eight rendered prompts
in r4's freeze at its own committed limits (`max_output_tokens: 2048`,
`automatic_retries: 0`).

**`18688 = 8 × 2336` is also exact — and both are true.** 2336 is simply the
arithmetic mean of 2294 and 2378. The documents that record "8 × 2336" are
not wrong arithmetically; they are wrong about what a mean means. There was no
per-dispatch price of 2336, and no campaign was ever priced at a flat 2336.
The mean is a coincidence of a two-valued price list, and treating it as the
provenance is what sent four documents looking for an artifact that was never
missing.

**And 2294 — the figure the documents call "the only sourced one" — is
independently corroborated from the store, not from a report.** r4's
`store-reconciliation.json` records
`operation.id = 'invl02-output-872608eb94c3-P1-audit-0023-a1'` with
`reservation_amount: 2294`. That operation id names a **P1** request. The P1
schedule price is **2294**. The schedule and the store agree on the currency
and the arithmetic, from two artifacts written by different code paths.

That resolves the last open question in the finding. `reports/STAGE-09-FINDINGS.md:553`
asked whether r4 held 2336 or 18688 and said it "is not answerable from this
branch: it needs the r4 durable store." The store is at
`reports/evidence/invl02-output-shape-550b-r4/store-reconciliation.json` and
has been on this branch the whole time.

### 4. What was settled

The figure stands. Three claims in the documents are corrected:

1. **"No artifact anywhere backs it"** — false. `f3af21a`'s test bodies carry
   the per-prompt character counts, and the broker schedule recomputes the
   total from them. The artifact was a test, not a JSON file, which is why
   `grep -rln 18688 --include='*.json'` returned nothing and the search that
   produced "zero artifacts" was looking in the wrong place.
2. **"18688 = 8 × 2336 is the shape of a pre-flight sizing, therefore a
   ceiling"** — the first half is right and the inference is wrong. It is a
   pre-flight sizing, and it is *derived*, priced per request, not a flat
   ceiling. The deduction from "8 dispatches" to "2336 each" does not hold
   because the eight requests had two different prices.
3. **"Either the documents overstate the liability by 16394 units, or an
   artifact is missing"** — neither. The documents mislabelled a campaign
   sizing as held liability. The correct correction is to stop calling 18688
   liability, not to subtract it from anything.

`2294` remains the only figure that is both *held* and *unsettled*. `18688`
is a sizing for eight requests that were never all sent — r4 spent 1 of 8.
`18708` is a different, later, settled run, and `PROJECT-LEDGER.md:88` already
keeps the three apart, which is right.

**Corrections made:** `reports/PROJECT-LEDGER.md` (the "pre-flight sizing
shape with no artifact behind it" line), `reports/STAGE-09-ROADMAP.md:648-656`
(the "in no artifact" and "8 × 2336" reasoning), `reviews/STAGE-09-FINDINGS.md:29`
("the divisor is confirmed, the figure is not"), and the five documents that
restate the "three markdown files" count. Each correction points at this
document. The r4 reservation table, `store-reconciliation.json`, the freeze,
and every other historical record are untouched.

**Still needs a person, with specifics:** whether a *sizing* should ever have
been written into a status document in language that read as *held liability*.
That is an editorial convention, not a fact, and it is now recorded in the
corrected text rather than left implicit. The number itself does not need a
person.
