# P10 free-route pilot

The prospectively frozen run `p10-live-20261016-01` made one real bounded worker
admission through the authorized free route. Development stopped on a timeout;
assessment was not started. This is an incomplete campaign result, with no task
score, comparison verdict, acquisition or learning claim.

The freeze was committed at `b7a08ea3` before effects. It pins source bytes,
task/genome/epoch identities, the route digest, protocol and finite caps. The
parent and candidate genomes are human-authored. The worker timeout was 90.3
seconds, within the frozen action timeout plus process shutdown overhead. The
development phase took 101.705 seconds against its 120-second wall envelope.

One of at most six model admissions was used. Its receipt reports `timeout` and
unknown tokens. The token reservation settled at its 400,000-unit unknown-charge
fallback. That is internal admission accounting, not measured provider token
usage, a price or evidence of payment. No verifier operation ran. No model reply,
successful execution or learning failure is inferred from the worker timeout.

The operation itself has a settled timeout receipt. Its P01 episode and P05
flight remain unfinished. Consequently `development.json` has no unsettled
dispatch IDs, while `recomputed.json` identifies the unfinished episode under
`unresolved_operations`. Both name the same incomplete campaign; these are
different views of dispatch settlement and task completion.

The original pilot database `p10_live_20261015_01` and private run area
`D:/AI/tools/p10/live1/p10-live-20261016-01` are preserved. The campaign was
suspended, not retried, reset or replaced. Its envelopes were not raised.

These JSON files are byte-identical copies of the run exports. Literal private
route values were checked in both plain JSON and decoded artifact payloads;
none was present, so no redaction was needed. Offline recomputation with gateway
variables unset and an unreachable DSN reproduced `recomputed.json` exactly,
returning `incomplete`, no consistency problems and no gain verdict.

```powershell
$env:PYTHONPATH = "src;tests;."
& .venv/Scripts/python.exe -m rsi.campaign recompute --bundle experiments/campaign10/evidence/live1/bundle.json
```

Fixture qualification and independent review establish the remaining campaign
mechanisms separately. Native child execution is cooperative and uncontained.
