# B-INIT workstream: operative AD01 actions (A3/A9)

Branch `wt/b-init`, DB lane `ec02test_binit` (existing battery's PG tests
verified on the fixture DB `ec02test_adtr`; production code is DB-agnostic).

Slice 1 (green): the accepted learner action now selects the dispatched
task. `run_campaign` threads the real charter into `_run_boundary`; the
admitted `next_action.task_id` is the executed target (recorded in
boundary/episode/observation/durable publish); a refused admission closes
the boundary as `no-candidate` with its reason instead of running work
against a missing investigation; `kind: stop` terminates dispatch with a
`learner stop` reason instead of silently running an incumbent episode.

Gate: `tests/test_binit_action.py` (1 test, red-first) + existing
`tests/test_ad01_traj.py` 20/20 (17 non-DB on the lane tree; 3 PG-backed
resume tests green on the fixture DB).
