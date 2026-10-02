# The conclusion in this directory is retracted

The claim in `RESULT.md` here — that relevant experience beats irrelevant
experience at equal context volume — **does not survive challenge**. It is kept
unedited as the record of what was claimed and when, and this notice sits with it
so it cannot be read as a live result.

There are two independent causes. Neither is the cause this notice used to
give, and the first is fatal on its own.

## Cause 1 (N-78) — both arms returned nothing at all

`contrast.json` records the same digest in both arms:

```
"digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
```

That is `sha256("")` — the digest of the empty string. Both arms also record
`"prompt_chars": 0`. The model returned nothing in either arm: the dispatch
came back empty, and the digest recorded is the fingerprint of that emptiness.

So the contrast did not compare a relevant proposal against an irrelevant one.
It compared two empty responses, and read a difference in a `diagnostic` field
that was never populated by a model at all. **This is not a weak result. It is
the absence of a result.** Nothing here measures relevance, and nothing here can
be cited for or against it.

## Cause 2 (N-400) — the equal-length premise is false in the committed prompts

`contrast.json` asserts `relevant_chars: 382, irrelevant_chars: 382`, and
`RESULT.md:27-30` leans on that match:

> The two rendered prompts are byte-identical except the trailing
> `Prior observations:` line, and both arms carry **382 characters** of
> experience. So a difference in what the model returns is attributable to the
> *content* of the experience, not to how much text it was shown.

The committed `prompts.txt` does not support it. Measured from the file in this
directory:

| | relevant | irrelevant |
|---|---|---|
| whole prompt block | **843** | **736** |
| block with the `Prior observations:` line stripped | **657** | **657** |
| experience JSON payload | **166** | **59** |

The full prompts are unequal by 107 characters. The two arms are equal only
once the experience is removed — which is the one comparison that cannot
establish anything about experience content. And the experience the contrast is
built on is lopsided 166 against 59, nearly three to one.

The `382` cannot have come from the function that owns this invariant.
`learner.equal_length_experience_pair` (`experiments/ad01/learner.py:407`)
measures `_observation_chars` — the canonical serialisation of the observation
list — and raises `TreatmentRefused` on an unequal pair. Fed these two arms it
raises:

```
experience arms must carry equal character length: 166 against 59. An unequal
control confounds semantic relevance with context volume.
```

`learner._set_observations` (`learner.py:432`) additionally refuses the records
outright, requiring an `observation_id` the committed records do not carry. The
arms in `prompts.txt` could not have been admitted by the construction path that
`RESULT.md:10-14` names. Whatever produced the `382`, it was not the size-matched
control the design claims.

Cause 2 is a distinct defect from cause 1 and is not repaired by fixing cause 1.
An empty dispatch is invalid whatever the prompt lengths; a false control is
invalid whatever the model returns.

## What the previous notice got right, and what it got wrong

The previous version of this notice attributed the invalidity to the
`diagnostic` field echoing the most recent family token in context. **That was
wrong**, and it named a different defect with a different fix — one that a
repaired dispatch would have satisfied, leaving the empty returns and the false
equal-length premise untouched. The echo mechanism was itself later falsified:
`../inv_r1_e2_challenge/RESULT.md` reports that changing the charter's family
mention did not move the `diagnostic` field at all, and calls it a dead
observable rather than an echo.

What survives of the challenge is the conclusion, not the mechanism. The 2×2
across both target families and both experience conditions, and the six-cell
replication, still stand, and they still retract the claim in this directory.

## What is not claimed here

The two causes above are recorded in `reviews/STAGE-09-FINDINGS.md` (N-78,
N-400) as recorded, not repaired. This notice is annotation. The directory's
`RESULT.md` remains in place and remains wrong; it should not be cited, and its
`outcome: differs` should not be read as a relevance effect.
