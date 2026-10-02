# E2: relevant experience versus none, run live

Two live calls on the confirmed free route, same task, same interface, same
budget. The arms are the ones `learner.matched_experience_arms` constructs,
and the equal-length enforcement is structural rather than a test a caller can
skip.

| condition | prompt chars | source chars | compiles as a STEP policy |
|---|---|---|---|
| relevant experience | 841 | 1608 | yes |
| no experience | 709 | 2039 | yes |

The two policies are different, and both are valid STEP policies rather than
one of them being unparseable.

## What this is

A real acquisition difference under a controlled contrast: the model wrote a
different policy when it had been shown relevant development observations, and
wrote a valid one either way.

## What this is not

**It is not a quality result.** Nothing here scores the two policies. A
longer source and a different one are not a better one. Running them on tasks
and scoring with the checker is the experiment, and it did not happen here.

**The two prompts differ in length by 132 characters.** The relevant arm
carries the experience block and is therefore longer. `equal_length_experience_pair`
is what makes the *irrelevant* control match the relevant arm, and this probe
contrasted relevant against **none**, which is the other declared arm and is
allowed to differ in size. So this is not the size-controlled contrast; that
one is constructible and unrun.

**One task, one lineage, two calls.** No distribution, no confidence, no
significance. A single paired difference is an anecdote with a receipt.
