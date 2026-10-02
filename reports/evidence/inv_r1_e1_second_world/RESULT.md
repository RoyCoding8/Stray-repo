# E1 on a second world: reachable, and two measured limits

N-21 was that `_run_arm` called `boolean_active.run_episode` directly, so
`compare_arms` could not be pointed at another instrument. "Does this
representation work on a second world" was unaskable rather than
answered, and the E1 matrix could only ever say something about one world.

`ComparisonConditions` now carries a `world`, and `episode_runner(name)`
resolves it. An unrecognised name raises: a silent fallback to the Boolean
world would hand a study a clean comparison against the first instrument
and read it as evidence about the second.

## The second world runs, and answers

Asking for the ordering-constraints world and pointing the Boolean matrix
at it:

```
status: incomparable
  issue  world-action-refused  probe target must be schedule.compare
```

Both the STEP and the AST arms are **refused at turn 0**. The harness does
not mis-score them and does not fall back — it reports that a policy
targeting `boolean.query` cannot answer a `schedule.compare` question.

And the ordering-world action graph is refused at load by the graph
executor:

```
node probe arm 0 action: probe target must be boolean.query
```

`boolean_graph_policy.choose_action` validates every action against the
**Boolean** world. The same decision — probe one pair, commit a four-job
order — loads on the Boolean world and does not load here.

## What this is

Two measured expressivity limits, in the form the handoff asks for: *"if a
representation is inexpressive on a world, demonstrate that limitation with
a concrete attempted behavior, record the missing cell and continue the
remaining matrix."* The attempted behaviour is a policy that means the
right thing for the ordering world and is refused by the executor.

The distinction the result draws is the useful one. **The representation is
portable; the policy is not.** A STEP program is arbitrary Python and
targets whatever the prompt names — the ordering STEP arm is loadable and
was written for this world. The AST and the graph are typed against one
world's action vocabulary, and that typing is the thing that does not
travel.

## What this is not

**Not a second-world comparison.** One arm is drivable on the ordering
world, and `compare_arms` needs two kinds. A real three-representation
matrix on a second instrument needs an AST constructor and a graph executor
that accept the ordering vocabulary — a build, not a wiring change. I did
not half-build it: `build_ordering_registry` registers both so the
refusals above are reachable and testable, and the docstring says the
comparison is a build.

So E1's claim is still one world: the three representations agree on the
Boolean world, and all three now run under one compute bound. The second
world is reachable and has produced two limits, not a parity result.
