# Native real-model evidence

[report.json](report.json) records three bounded experiments on the approved
free route. The first two stopped at a dev timeout. The third used unscored
dev workflow evidence for one improver attempt, which timed out too.

No child, task score, acceptance gate, anchor exposure or model-led improvement
is claimed. No live task synthesis was attempted because these runs produced
no completed dev failures suitable for qualification. Fixture checks establish
synthesis plumbing separately.

Runtime receipts, trajectories and pinned evidence are recoverable from DB
`rsi_t5`, localhost port 55432, with artifact/run root `D:/AI/tools/rsi-t5`.
Credentials remain outside the repository. Consumed tokens on timed-out runs
are ceiling charges; actual model usage is unknown.
