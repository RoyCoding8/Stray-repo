# M0 ownership map — adversarial challenge

Source `0ee4699`. Independent review of `reports/workstreams/m0-ownership-map.md`,
run before implementation depended on it, as WORKER-PROMPT M0 requires. The
reviewer attacked the map rather than confirming it, and **refuted one of its
four sections**.

## Verdicts

| Claim | Verdict |
|---|---|
| The five write-only columns | CONFIRMED, with a defect the map missed |
| The zero-production-caller claims | CONFIRMED |
| The lane split | **REFUTED** |
| The quiescence claim | CONFIRMED |

The central finding survived. The lane split did not, and it was the section
implementation would have depended on hardest.

## What held, and how hard it was attacked

**Claim 1 (write-only columns).** Attacked through every dynamic-access vector:
`getattr`, `**kwargs` forwarding, generic column iteration, JSON serialization of
the whole row. The `**kwargs` route is closed — `record_mission` takes `**fields`
(`mission.py:202`) but routes them through `_validate` (`:220`), which rejects
any key outside `MISSION_FIELDS`.

One near-miss worth recording. `src/settlement/api.py:98` does
`SELECT * FROM investigations` and `_rows` (`:75`) copies every column; 
`context._fetch_state` (`context.py:363`) does the same and returns the row. Both
transport all five columns as live values. Both then read **named keys only** —
`.get("objective")`, `.get("scope")`, `.get("obligations")`, `.get("disposition")`
(`context.py:438-441,603-607,639-641`). `create_app` renders HTML exclusively;
there is no JSON route. So the columns are carried and never consumed. The map's
conclusion holds, and the near-miss is why the claim is measured rather than
assumed.

**Claim 2 (zero-caller claims).** All four confirmed. On the `__main__` route
specifically: 80 modules carry `if __name__ == "__main__"`, and only
`improve_channel.py:2400` and `scripts/invl02_live.py` touch lane-owned files.
`live_construct.py`, `twodomain.py`, `frontier.py` and `mission.py` have none, so
`fresh_round` really is the unique case.

**Claim 4 (quiescence).** Confirmed exhaustively, including `getattr` and
re-export. Nothing in `src/`, `scripts/`, or a non-`mission` `experiments/ad01/`
module names `mission.is_quiescent`.

## What was refuted

**The lane split.** The map named **one** source-text gate. There are
**nineteen**, resolved from real imports rather than guessed aliases. Two live
gates contradict Lane C's contract outright.

The map told Lane C to "resolve `_disposable_authority` into a caller-held store
**or state why the disposable default stays**". But
`tests/test_inv_a8_improve_authority.py:231-247` already asserts the default
stays:

```python
assert "_disposable_authority" in body, (
    "drive_improve_round no longer constructs an authority to execute "
    "under, so a caller that supplies none has nothing")
```

The test is named `test_the_world_boundary_constructs_the_store_it_executes_under`
and its docstring gives the invariant: this is the one place allowed to own a
ledger, so a round's operations sit under a single study root. The map offered a
choice the gate had already closed, and did not mention the gate existed.

A second gate at `test_inv_a8_improve_authority.py:170-197` walks every call to
`_run_source`/`run_improve_step`/`run_operate_step` and requires
`{authority, operation_id}` keywords with `assert checked >= 4`. Any refactor
that adds or removes an executor-reaching call site moves that count.

**Two files are gate-read and lane-unowned.** The map's forced orderings were
also incomplete:

- `test_inv_x1_call_arity.py:232` asserts
  `inspect.getsource(channel_controls.drive_record)` contains `"authority={"`
  while **not** containing `"dsn=dsn"`. Lane C changing `run_improve_step`'s
  signature forces an edit to `channel_controls.py`, which no lane owned.
- `test_experiment_contract_repair.py:68-74` asserts
  `twodomain._active_program`'s `source_digest` equals
  `sha256(Path(twodomain.__file__).read_bytes())`. **Any byte change to
  `twodomain.py` changes the digest and breaks the test**, so Lane D cannot edit
  that file without accepting a digest rewrite in the same commit.

## The finding that matters most

The map treated `_disposable_authority` as a cleanup item. It is the reason M1
cannot be a column migration.

**The entire production live path executes against a database created and
destroyed per round.** `run_live_improve_round` (`live_construct.py:1216-1225`)
calls `drive_improve_round` with no `authority` keyword. Inside, `granted is None`
reaches `_disposable_authority("invl02-improve")` at
`improve_channel.py:2192-2198`, which runs `CREATE DATABASE`
(`s09_run_isolation.py:260`) and `DROP DATABASE ... WITH (FORCE)` (`:277`).
`_run_source` settles its receipt against that disposable dsn.

The live path holds a real, named `investigations` row and still executes against
a database destroyed when the round ends. Production receipts do not survive the
round. Moving mission state into SQL while execution authority is disposable
would produce a mission whose records point at a database that no longer exists
— the same "summaries into SQL columns nobody consumes" failure, one level down.

I verified this myself before accepting it: the gate assertion, the missing
`authority=` at the production call site, and the CREATE/DROP pair all confirmed
at the cited lines.

## Three smaller defects

**`permitted_experience` has the wrong default type.**
`migrations/0019_mission_entry.sql:25` declares `DEFAULT '[]'`, a list, while
`mission._JSON_TYPES` requires `dict` (`mission.py:51`). `read_mission`
launders it with `dict(row[...] or {})` at `mission.py:324`. A row admitted
without naming the column reads back as `{}`.

**`frontier.durable` is strictly deletable, not awaiting a writer.**
`StoreIdentity.durable` (`frontier.py:99-102`) returns `self.dsn is not None` and
has **no reader either**: `frontier.py:884,905,911,914` all read `self.identity`
directly. The real check is `_check_identity` (`:892-916`). Dead on both ends.

**The `twodomain.py` claim was true vacuously.** The map said the ledger's
"writes projections production does not consume" is confirmed. It is — but the
only writer of those projections is a module nothing in production runs. The
map's separate "needs no migration" point is right and more load-bearing than it
presented itself as.

## Correction applied

The map's lane section is superseded in place by a five-lane split with the
ordering **E → C → B → A**, where Lane E owns `trajectory.py` and `frontier.py`
and lands first because it removes the JSON owner the other lanes stop reading.
`channel_controls.py` folds into Lane C. The nineteen gates are listed by file
and line so no lane discovers them by surprise.

The map's central finding, its measurement discipline and its "what the
assignment text gets wrong" section all survived. The assignment errors stand:
`twodomain.py` needs no migration, and `run-e0`/`run-e12` are never run by CI.

**Principles applied.** *Attack the premise* — the review was commissioned to
refute rather than confirm, and did. *Proof it works* — the reviewer's decisive
claims were re-verified at source before the map was rewritten, not taken on
report. *Sequence verifiable units* — no lane was dispatched against the
four-lane split, so the refutation cost a document revision rather than a merged
commit and three lanes' rework.