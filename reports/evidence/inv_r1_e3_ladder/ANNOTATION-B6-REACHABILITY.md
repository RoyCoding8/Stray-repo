# B6 / N-80 — the ladder's withdrawal is annotated but not *reachable*

Second pass on B6. `RETRACTED.md` and `committed-ladder-status.json` in this
directory are correct and the marker reproduces: re-running
`experiments/regen_v2/regen_e3_ladder_status.py` at this tip produces
`committed-ladder-status.json` identical to the committed one in every field
except `measured_at`. The marker is sound.

**What is still open is the reachability requirement in the task row: "a reader
who opens the ladder should learn it was retracted without already knowing."**
A reader who opens the ladder does not learn it. Measured over the committed
tree, **zero of the five** directories carrying a `RETRACTED.md` have any sibling
artifact that mentions the retraction, and the ladder artifact itself contains
none of the four marker words.

## Measured: the marker is invisible from the artifact

`e3-postfix-ladder.json` is 165 KB. Counted over the committed bytes:

| word | occurrences |
|---|---|
| `retract` | 0 |
| `withdrawn` | 0 |
| `invalid` | 0 |
| `superseded` | 0 |

Its 18 top-level keys include `committed_ladder` and no marker key. The result a
reader is warned about is nested two levels down under a key that reads as a
result name. The sibling `RETRACTED.md` says exactly this, and it is right:

> The artifact contains no word that would warn a reader, and adding one would
> mean editing the bytes this notice exists to preserve.

That last clause is the constraint this annotation exists to resolve. The prior
pass read the constraint as forcing a sibling, and a sibling is what it built.
The constraint forbids editing **committed evidence bytes**. It does not forbid a
second artifact that names the first.

## The convention this repo already uses, and does not use here

Two committed artifacts already carry a `supersedes` field, and both are written
by the generator that produces the artifact, not by a later hand:

- `experiments/ad01/e2_gate_report.py:242` writes `freeze.supersedes =
  replica.NAMESPACE` into `inv_r1_e2_gated/report.json`
- `experiments/ad01/e2_reason_probe.py:160` writes a top-level
  `"supersedes": None`

So the precedent is a **provenance field in the artifact**, emitted by the
writer. That is stronger than a sibling file, because a consumer that parses the
JSON sees it without knowing to look for a second file.

**It cannot be applied to the ladder, and the reason is the whole point.** Both
`supersedes` fields are in artifacts their own writer produces. To add one to
`e3-postfix-ladder.json` means re-running `regen_e3_ladder.py` with a changed
writer and **overwriting the committed artifact**, which is the prohibited act.
The convention is available for the next artifact and unavailable for this one.
That is a property of the case, not a gap in the convention.

## What the ladder's writer would have to emit, for the next run

Recorded here because B7 asks what shape a supersession marker needs, and this
is the one instance where a reader is likely to be misled by a well-named key.
The field that would close it, if the artifact were ever legitimately
regenerated:

```json
"committed_ladder": {
  "supersedes": null,
  "withdrawn": true,
  "withdrawn_by": "reports/evidence/inv_r1_e3_selection/RETRACTED.md",
  "withdrawn_reason": "N-80: cumulative prefix sums of one traversal",
  "valid_for": "the pre-fix/post-fix comparison only",
  "superseded_by": "reports/evidence/inv_r1_e3_selection_regen_v2/",
  ...
}
```

Note the shape. `withdrawn_by` names the **document**, not a commit, and
`valid_for` carries the positive claim that survives. A marker that can only say
"retracted" is not enough, because `$.committed_ladder` is not wrong, it is
*scoped*. Deleting it would break the comparison permanently; that is why it is
annotated rather than deleted, and the marker has to say so in the artifact.

## What is available to a reader today, and it is not nothing

The marker is discoverable by three routes that need no prior knowledge of this
directory:

1. `git log -- reports/evidence/inv_r1_e3_ladder` names `3c1e5c5` ("E3 post-fix
   ladder: treatment INACTIVE, and the 227k-line matrix is a writer defect"),
   which is the commit that added `RETRACTED.md` and the marker beside the
   artifact.
2. `committed-ladder-status.json` is a sibling with a name that sorts beside the
   artifact and carries `finding: "B6 / N-80"`, so `ls` shows it.
3. The directory listing: four files, two of which are notices, and one of the
   two names the artifact by path.

That is enough for a reader who lists a directory. It is not enough for a reader
or a machine that opens the JSON, which is the case the task row names.

## What was not done

The artifact was not edited, so this notice adds no reachability that was not
already there. It records that the gap is real, names the convention that would
close it, and states why the convention is unavailable for this artifact. A
second notice saying the same thing in a third format would add a file and no
reachability.
