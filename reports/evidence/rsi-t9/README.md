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

[route-check.json](route-check.json) records the follow-up gateway diagnosis.
Authenticated `/v1/models` returned HTTP 200 and listed the original model.
The original traces include Unix commands in PowerShell and malformed patches.
A direct custom-tool request returned a valid patch. Using the same published
seed and Proverb task, `cohere/north-mini-code:free` completed through Codex in
79.2 seconds with measured usage. Its pristine verifier failed. This proves a
completed live execution on the gateway, without proving task competence or
agent improvement. The original timeouts remain recorded above.

[cohere-loop.json](cohere-loop.json) records a subsequent bounded run on that
model. Its dev execution completed in 200 seconds and failed pristine tests.
The improver made 40 shell calls, then the provider rejected malformed tool
arguments with HTTP 400 after 133.2 seconds. No child or gate was produced.
The historical receipt says `failed`; it is preserved. Reprocessing the actual
trajectory with the corrected classifier yields `infra_failed`. New runs stop
on that infrastructure failure and expose its reason through the meta result.
Unknown usage on the proposal was charged at its 300,000-token ceiling.
