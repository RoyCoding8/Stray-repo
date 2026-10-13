# P01 continuation smoke (2026-10-13)

Two live worker actions continued the same investigation across suspension and
fresh-process CLI resumption. The second received the first checked failure and
saved solution, then changed subtraction to addition. **The investigation ended
unresolved:** its final pristine verifier could not reserve CPU. There is no final
passing task verdict, acquired policy, transfer result or learning claim.

The task and genome were authored specifically to exercise diagnosis followed by
repair. The human-approved gateway alias was `openrouter/openrouter/free`.
Underlying router model identity and provider invoices were not measured. The
Codex catalogue template supplies CLI metadata; it does not select the gateway
model. Execution used cooperative native children; hostile-code containment is
unproved.

## Preserved envelopes

| Files | Source checkpoint | Prospective limits | Observed outcome |
|---|---|---|---|
| This directory | `e5593806` | Two worker actions, 40,000 tokens each, 80,000 token allocation, 120 CPU units | Installed Codex lacked the default `gpt-5.4` catalogue entry. Kernel proof establishes never sent; no inference or receipt. After the refusal fix, the investigation became unresolved. |
| `r2/` | `7b559850` | Same token/CPU allocation, explicit `gpt-6.1-sol` catalogue template | One worker diagnosed without editing. CLI reported 87,482 input and 1,171 output tokens, exceeding its 40,000 allowance. Episode marked over-budget; no verifier ran. |
| `r3/` | `5888cb50` | Fresh 600,000-token allocation, 300,000 per worker, two actions, 120 CPU units | Diagnosis completed; pristine check failed. Suspended, then resumed through a fresh CLI process. Repair completed, but final verifier preparation refused: 111 units required, only 9 remained. |

Worker timeout was 180 seconds in each envelope. Prior operations and charges
were preserved; no reset, refund or retroactive limit change made a run pass.
The 120-unit CPU allocation was our setup error: one checker reservation consumed
111 units. A later experiment must budget from the broker profile.

Token figures are CLI-reported usage, not provider invoice evidence. Cached and
reasoning counts are reported separately and must not be added again to input
and output totals. Token admission reserves a declared allowance; actual CLI
usage can exceed it before post-execution classification. In r2 the books settled
the 40,000 reservation, not the 88,653 actual reported input-plus-output tokens.
In r3 the books consumed 353,717 tokens and 111 CPU units, with zero reserved.

## Reading the evidence

- `freeze.json` and each round's freeze record prospective configuration and
  source identity. Initial/step/export files record successive observations;
  they do not represent separate repeated dispatches.
- `kernel-records.json` captures journal, operation, receipt and reservation
  rows. Round `operations.json` files are snapshots of the shared database and
  therefore include earlier rounds, not just that round's operations.
- `r3/export.json` contains both decisions, their visible inputs and checked
  observations. `r3/cli-resume.json` records the terminal CLI result (exit 2).
- `r3/audit.json` records the primary's checks of the shared investigation,
  prior failed observation, returned workspace bytes and usage. It is a derived
  audit, not a replacement for the underlying records.
- `artifacts/` preserves all seven registered packages byte-for-byte, named by
  SHA-256. They contain the authored task/genome, stored solutions and worker
  trajectories. JSON package file values are hex-encoded bytes. Package digests
  differ from the digest of an individual trajectory file or solution file.

The database contains five operations and four receipts: one proved never-sent
worker, three completed worker executions across r2/r3, and one pristine verifier.
The final verifier refusal has no operation or receipt. The never-sent operation
remains `settled=false` because there is no receipt; its reservation was released
using kernel proof. Its appearance in the export's unsettled-effects list does
not mean an uncertain financial charge. Do not synthesize a receipt to remove it.

## Reproduction boundary

The committed packages permit offline byte inspection and digest checking without
the gateway or database. The public behavioral gates are
`tests/test_rsi_investigation_state.py`, `tests/test_rsi_investigate.py` and the
loop's unsent-refusal regression. They use labeled fixture children and disposable
PostgreSQL databases; they do not reproduce live model output.

The original live receipt anchor remains in database `p01_live_20261013` at local
port 55432, with run directories under `D:/AI/tools/p01-live-20261013`. Gateway
credentials remain external. This bundle does not recreate that database or
claim deterministic replay of the provider. Existing identities are terminal;
do not redispatch them. No further live run is needed to close this checkpoint.
