# P06 search experiment

This experiment separates four evidence classes. Authored native methods create
supported P01 branches. Two authored policies screen the identical frozen
corpus. Model construction receives a real P03 packet built from a captured P01
observation. A candidate can reach one fresh P05 agenda turn only after screening
on all three frames. Fixture success qualifies the collector and evaluator; it
does not establish acquired competence, transfer, or learning.

Run collection and fixture screening with the isolated PostgreSQL test database:

```powershell
D:/AI/Agent-Society-v2/.venv/Scripts/python.exe experiments/search06/driver.py collect --output D:/AI/tools/p06/experiment
D:/AI/Agent-Society-v2/.venv/Scripts/python.exe experiments/search06/driver.py screen --collection D:/AI/tools/p06/experiment/collection.json --output D:/AI/tools/p06/experiment/screen
```

The collection publishes every frame after all its fresh starts and contexts
are prepared, then executes only the two named native alternatives. A third
prepared option is left unexecuted. Screening includes the missing continuation
query, which remains a coverage gap. The private branch artifacts contain
outcomes; policy inputs contain only the visible objective, menu, prefix, and
limits.

Prepare a live freeze only after collection and source are final. The freeze
pins the source-file hashes, scenario caps, route identity hash, and the exact
collection frame, branch, and policy identities. Commit the freeze before
running the live command. The route key is read from
`D:/AI/tools/rsi-openrouter-route.env` and is never copied to the bundle.

```powershell
D:/AI/Agent-Society-v2/.venv/Scripts/python.exe experiments/search06/driver.py freeze --freeze D:/AI/tools/p06/experiment/freeze.json --collection D:/AI/tools/p06/experiment/collection.json --mode live
D:/AI/Agent-Society-v2/.venv/Scripts/python.exe experiments/search06/driver.py run --freeze D:/AI/tools/p06/experiment/freeze.json --collection D:/AI/tools/p06/experiment/collection.json --output D:/AI/tools/p06/experiment/live
```

The planned live construction allows two admissions total, each bounded at 90 seconds and
400,000 reserved token units. Only one repair follows a completed unusable
response. A timeout, infrastructure failure, or unresolved effect ends the
slice. Candidate bytes are screened unchanged. Eligibility requires supported
coverage on every frame, checked quality at least as high as the frozen
incumbent, closed actions, and known bounded costs. A negative result completes
this bounded pilot without demonstrating sustained learning.

Offline recomputation consumes a saved evaluation bundle only:

```powershell
D:/AI/Agent-Society-v2/.venv/Scripts/python.exe experiments/search06/driver.py recompute --bundle PATH_TO_EVALUATION_JSON --output D:/AI/tools/p06/experiment/recomputed.json
```

The collector's authored native children run as local, uncontained fixtures.
The candidate screening path is currently implemented with the same native
child launcher, which conflicts with the repository rule against executing
untrusted candidate code on the coordinator host. That execution boundary is
unresolved: do not run the live command until a separately reviewed containment
design replaces or authorizes that boundary. No live candidate run has been
made. Fixture qualification does not make the live slice ready. Do not place
credentials or the route file in this experiment directory or its evidence
exports.

The live freeze pins the 180-second P05 use window as a duration. Its absolute
deadline starts when the agenda is first created, after construction and
screening. Resuming an existing run reuses the deadline in that durable agenda
charter, including when the deadline has already passed.
