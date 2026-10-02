# E1 with a control arm in the study

A control arm is in the study and it ran. This is what the two arms executed and what the difference between them was.

## The gate

`control_distinct`: **False**

> refused: control is not distinct from the acquired arm: 8 task(s) took the same walk on both arms; 11 task(s) returned a byte-identical candidate on both arms, of which 3 took different walks and are reported as converged; 1 task(s) named no executed policy on at least one arm

paired tasks 18, unpaired 0, same strategy 0, same executed policy 0, same candidate 11, unnamed 1, differing budget 1

`experience_varies`: **True**

18 observations, 1 distinct verdict(s) ['preserved'], methods named ['ddmin', 'greedy'].

## Utility

Compared against the acquired ordering 'I'. The use loop runs I and R, so pairing against both would count every task twice.

**CONTROL_WINS** over 18 paired tasks, mean acquired-minus-control normalized reduction -0.00359362859362859.

A tie is a result. It is reported here as a tie, with the numbers that produced it, and not as a failure.

| task | control ran | acquired ran | control size | acquired size | same bytes | delta |
|---|---|---|---|---|---|---|
| ad01-w0-transfer-gr-00 | ctl-graph-greedy | acquired-gr-b0bd83b7 | 9 | 9 | yes | 0.0 |
| ad01-w0-transfer-sw-00 | ctl-software-ddmin | acquired-sw-b0bd83b7 | 3 | 3 | yes | 0.0 |
| ad01-w0-within-gr-00 | ctl-graph-greedy | acquired-gr-b0bd83b7 | 5 | 5 | yes | 0.0 |
| ad01-w0-within-gr-01 | ctl-graph-greedy | acquired-gr-b0bd83b7 | 7 | 7 | yes | 0.0 |
| ad01-w0-within-sw-00 | ctl-software-ddmin | acquired-sw-b0bd83b7 | 3 | 3 | yes | 0.0 |
| ad01-w0-within-sw-01 | ctl-software-ddmin | acquired-sw-b0bd83b7 | 3 | 11 | no | -0.6154 |
| ad01-w1-transfer-gr-00 | ctl-graph-greedy | acquired-gr-b0bd83b7 | 9 | 9 | yes | 0.0 |
| ad01-w1-transfer-sw-00 | ctl-software-ddmin | acquired-sw-b0bd83b7 | 8 | 3 | no | 0.4545 |
| ad01-w1-within-gr-00 | ctl-graph-greedy | acquired-gr-b0bd83b7 | 5 | 5 | yes | 0.0 |
| ad01-w1-within-gr-01 | ctl-graph-greedy | acquired-gr-b0bd83b7 | 7 | 7 | yes | 0.0 |
| ad01-w1-within-sw-00 | ctl-software-greedy | acquired-sw-b0bd83b7 | 5 | 3 | no | 0.25 |
| ad01-w1-within-sw-01 | ctl-software-ddmin | acquired-sw-b0bd83b7 | 9 | 11 | no | -0.1538 |
| ad01-w2-transfer-gr-00 | incumbent | acquired-gr-b0bd83b7 | 10 | 9 | no | 0.1 |
| ad01-w2-transfer-sw-00 | ctl-software-ddmin | acquired-sw-b0bd83b7 | 7 | 3 | no | 0.4 |
| ad01-w2-within-gr-00 | ctl-graph-greedy | acquired-gr-b0bd83b7 | 5 | 5 | yes | 0.0 |
| ad01-w2-within-gr-01 | ctl-graph-greedy | acquired-gr-b0bd83b7 | 7 | 7 | yes | 0.0 |
| ad01-w2-within-sw-00 | ctl-software-ddmin | acquired-sw-b0bd83b7 | 3 | 3 | yes | 0.0 |
| ad01-w2-within-sw-01 | ctl-software-ddmin | acquired-sw-b0bd83b7 | 3 | 8 | no | -0.5 |

## Cost, in four separate currencies

- **dispatch_allowance** REPORTED
  - operations: 106
  - uncertain_note: an operation that was dispatched and is not settled may have spent a provider call whose response was lost; its cost is uncertain, not zero
- **reservation_allowance** REPORTED
  - study_units_authorized: 1673728
- **provider_billing** NOT_REPORTED
  - reason: recording doubles bill false; the run made no provider call to bill
- **internal_held_units** REPORTED
  - free_units: 209216
