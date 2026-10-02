# The experience gate on the `ad01-exp-axis` panel

The control arm ran over the new freeze's use tasks, through the
campaign's own `trajectory.run_use`, with the freeze redirected to
`ad01-exp-axis` for the duration of the call. The members are
authored control bytes under the `ctl-` namespace, so this measures
the instrument and the panel, not a model. No prompt was sent and no
provider was called.

## The gate

`experience_varies`: **True**

36 observations on the development split, 1 distinct verdict(s) ['preserved'], 2 distinct reason(s) ['ok-incumbent', 'ok-preserved'], 2 distinct outcome(s) ['preserved/ok-incumbent', 'preserved/ok-preserved'], methods named ['ddmin', 'greedy'].

The verdict is one bit on every well-formed task in this repository.
That is the fixpoint, and the outcome is what the gate counts.

**The split matters and is the correction this run forced.** The
gate asks what an arm's experience was, and an arm's experience is
what it observed while it learned, which is the development split.
Grading the use split instead answers a different question:

- use split, 24 records, 21 graded, 3 refused by the selector
- use split outcomes: ['preserved/ok-preserved'], varies False

The use split is a constant because the selector picks the smaller
candidate and that is `ok-preserved` on every task it admits, at the
run's own budget of 4. That is a property of the selector, not of
the panel.

## Cost, in four separate currencies

- **dispatch_allowance** UNMEASURED
  - reason: study not bound: no authority for study 's09iso-expaxis64c03bb7-root' in this store; refusing to seed
- **reservation_allowance** REPORTED
  - study_units_authorized: 1673728
- **provider_billing** NOT_REPORTED
  - reason: recording doubles bill false; the run made no provider call to bill
  - note: a spend that cannot be read is UNMEASURED, never zero
- **internal_held_units** UNMEASURED
  - reason: study not bound: no authority for study 's09iso-expaxis64c03bb7-root' in this store; refusing to seed

The run is authorized against no bound study, so the two store-read
currencies are UNMEASURED with the reason. A spend that cannot be
read is uncertain, never zero.

## Both arms

Arm A picks by measured public shape, so it spans both strategies on
its own. Arm B names one strategy per family. Both are authored bytes
and neither is a model acquisition.

`control_distinct`: **False**

> refused: control is not distinct from the acquired arm: 3 task(s) named no executed policy on at least one arm

| task | arm A ran | arm B ran | A verdict | A reason | A size | B size |
|---|---|---|---|---|---|---|
| exp-w0-transfer-gr-00 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 7 | 10 |
| exp-w0-transfer-gr-01 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 7 | 10 |
| exp-w0-transfer-sw-00 | ctl-software-greedy | ctl-software-ddmin | preserved | greedy | 4 | 5 |
| exp-w0-transfer-sw-01 | ctl-software-greedy | ctl-software-ddmin | preserved | greedy | 4 | 6 |
| exp-w0-within-gr-00 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 6 | 9 |
| exp-w0-within-gr-01 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 6 | 7 |
| exp-w0-within-sw-00 | refused | ctl-software-ddmin | refused |  | 0 | 3 |
| exp-w0-within-sw-01 | ctl-software-greedy | ctl-software-ddmin | preserved | greedy | 3 | 4 |
| exp-w1-transfer-gr-00 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 7 | 10 |
| exp-w1-transfer-gr-01 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 7 | 10 |
| exp-w1-transfer-sw-00 | ctl-software-greedy | ctl-software-ddmin | preserved | greedy | 4 | 5 |
| exp-w1-transfer-sw-01 | ctl-software-greedy | ctl-software-ddmin | preserved | greedy | 4 | 6 |
| exp-w1-within-gr-00 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 6 | 9 |
| exp-w1-within-gr-01 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 6 | 7 |
| exp-w1-within-sw-00 | refused | ctl-software-ddmin | refused |  | 0 | 3 |
| exp-w1-within-sw-01 | ctl-software-greedy | ctl-software-ddmin | preserved | greedy | 3 | 4 |
| exp-w2-transfer-gr-00 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 7 | 10 |
| exp-w2-transfer-gr-01 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 7 | 10 |
| exp-w2-transfer-sw-00 | ctl-software-greedy | ctl-software-ddmin | preserved | greedy | 4 | 5 |
| exp-w2-transfer-sw-01 | ctl-software-greedy | ctl-software-ddmin | preserved | greedy | 4 | 6 |
| exp-w2-within-gr-00 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 6 | 9 |
| exp-w2-within-gr-01 | ctl-graph-greedy | ctl-graph-ddmin | preserved | greedy | 6 | 7 |
| exp-w2-within-sw-00 | refused | ctl-software-ddmin | refused |  | 0 | 3 |
| exp-w2-within-sw-01 | ctl-software-greedy | ctl-software-ddmin | preserved | greedy | 3 | 4 |

Executed policy ids, arm A: ctl-graph-greedy, ctl-software-greedy, refused.
Executed policy ids, arm B: ctl-graph-ddmin, ctl-software-ddmin.

A record reading `refused` named no executed policy at all: the
selector raised on a task whose two strategies return the same
candidate size, so it had no measured basis to pick. That is the
selector's own rule and it is why `control_distinct` refuses on the
unnamed leg. Arm B names its strategy unconditionally and ran all
24.

## Tasks the panel does not separate

- `exp-w0-within-sw-02` software, 3 removable atom(s). the two strategies return the same candidate size, so the selector has no measured basis to pick and refuses by its own rule
- `exp-w0-within-gr-02` graph, 6 removable atom(s). not drawn by this run's task list
- `exp-w0-transfer-sw-02` software, 5 removable atom(s). not drawn by this run's task list
- `exp-w0-transfer-gr-02` graph, 2 removable atom(s). not drawn by this run's task list
- `exp-w1-within-sw-02` software, 3 removable atom(s). the two strategies return the same candidate size, so the selector has no measured basis to pick and refuses by its own rule
- `exp-w1-within-gr-02` graph, 6 removable atom(s). not drawn by this run's task list
- `exp-w1-transfer-sw-02` software, 5 removable atom(s). not drawn by this run's task list
- `exp-w1-transfer-gr-02` graph, 2 removable atom(s). not drawn by this run's task list
- `exp-w2-within-sw-02` software, 3 removable atom(s). the two strategies return the same candidate size, so the selector has no measured basis to pick and refuses by its own rule
- `exp-w2-within-gr-02` graph, 6 removable atom(s). not drawn by this run's task list
- `exp-w2-transfer-sw-02` software, 5 removable atom(s). not drawn by this run's task list
- `exp-w2-transfer-gr-02` graph, 2 removable atom(s). not drawn by this run's task list
