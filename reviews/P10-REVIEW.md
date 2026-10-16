# P10 independent review

GPT-6.1 Sol High independently reviewed the integrated campaign implementation
in an isolated worktree using PostgreSQL 18 and actual bounded children. Its
final scoped verdict at `c6a8ca4a1737630cec461dcc5fdfbe3db290ce83` is PASS.
All eight material findings below were reproduced and closed. The review made
no production edits or model calls.

## Findings and repairs

| Finding | Repaired behavior |
| --- | --- |
| R1. Missing reservation evidence counted as zero cost. | Offline recomputation requires operation-specific reservations, allocation roots, effect/domain/amount agreement and settlement state. Missing support produces unknown resource totals. |
| R2. A due assessment could be admitted after the charter deadline. | Assignment admission checks the deadline under the agenda owner lock. An assignment admitted before expiry remains recoverable afterward. |
| R3. All-skipped native checks vetoed an otherwise eligible method. | Exact applicability uses the existing known-test predicate. Skipped checks remain unknown and do not establish a failure in that scope. |
| R4. Protocol byte limits rejected larger valid exports. | Protocol parsing retains its input bound. Export canonicalization accepts the larger finite JSON evidence bundle. A six-round export recomputes successfully. |
| R5. The pilot could report completion after artifact loss. | Completion requires the exported evidence to qualify. Artifact loss at the export boundary produces an incomplete phase with the campaign identified. |
| R6. Due assessment blocked recovery of an admitted development flight. | The single existing wake path recovers that flight before assessment admission or new-work exit checks. |
| R7. Slow ranking could cross the deadline and still admit development. | Choice commitment rechecks the persisted deadline under the owner lock. Late ranking admits no choice or operation. |
| R8. Deleting completed development effects reduced exported cost. | Acknowledged development requires its original worker, verifier, episode and verdict evidence. Removing that closure invalidates the export and leaves resource totals unknown. |

## Executed verification

At `b6fb4fc4`, Sol's seven-file component gate passed 39 tests, zero skips,
in 522.47 seconds. Its separate neighboring agenda/capability/gate scope passed
40 tests, zero skips, in 552.51 seconds. These are separate scopes, not an
aggregate or a whole-repository suite.

On final repaired source `c6a8ca4a`, independent public owner/deadline probes
passed four cases, zero skips, in 60.57 seconds. An unexpired interrupted flight
was acknowledged before assessment and completed with one choice and one
assignment. An expired admitted flight was acknowledged before returning
deadline, with one choice, one worker and no assessment assignment. Slow-ranking
probes admitted zero turns after expiry.

The independent R8 probe first accepted the unchanged public CLI export with
45,000 settled token units and 555 CPU units. Removing its two acknowledged
development operation closures, while retaining decisions and investigation
history, then returned `tampered` with resource totals unknown. Before repair,
that same deletion was accepted as consistent at a falsely lower cost.

Additional independent probes exercised allocation/reservation/effect mutations,
all-skipped applicability, a six-round export, literal protected assessment
values, actual export-boundary artifact loss and public CLI fixture execution.
The coordinator inspected the repairs and ran separate integrated checks. Its
final export-file gate passed six tests, zero skips, in 239.71 seconds. The new
maintained R8 regression failed before the fix. Lane tests also reproduced R6
and R7 before repair and passed six owner/deadline checks afterward.

A neighboring run using a database token concurrently with another lane was
invalid setup evidence and is excluded. Both owners ended their processes;
the two inactive scratch databases were removed. An earlier artifact-loss probe
was also excluded because later fixture work restored identical bytes. The
corrected probe removed bytes at the export boundary after a clean assessment.

## Boundaries

These checks qualify campaign ownership, restart, bounded admission, sealed
decision inputs, applicability and export consistency. Native children are
bounded, cooperative and uncontained. Offline checks cannot authenticate provider
usage, elapsed time, compute attestations or a coordinated rewrite of trusted
evidence. They establish neither live acquisition, transfer nor learning gain.

The prospectively bounded live pilot and final CI are recorded separately in
[the project ledger](../reports/PROJECT-LEDGER.md).
