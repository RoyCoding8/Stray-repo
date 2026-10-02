# ENG-SOLV: solver output contract + live baseline smoke

Base: `f478143c520977da179cef3da309824a996a42cb`
Tip: `79f1fbab7a250978633b920be0794bbdf036b0a9` (contract+smoke commit)
Branch: `codex/eng-solv`, worktree `/tmp/asv2-eng-solv`
Identity verified: `git config user.name` is the private identity; unchanged.
Skill loaded first: `diagnosing-bugs` (red loop before hypotheses before fix).

## Contract decision D-ENG-SOLV-01

ONE shared verbatim-source contract for development collection, all A/B/C
arms and incumbent use, distinct from the diagnose/construct JSON envelopes:

- `experiment.SOLVER_SOURCE_CONTRACT`: the response bytes ARE the candidate
  source, byte-for-byte. Carried identically in `_arm_prompt` (A/B/C), the
  DEV collection prompts (`_run_development`, `development._collect_task`)
  and incumbent use (via arm-A prompt).
- No fence stripping, no prose salvage, no per-arm differences, no
  post-exposure edits. Rationale: any extraction is a second source of
  truth and a per-arm divergence risk; the defect was unmeasured format
  confounding, and the fix must make format visible, not guess through it.
- `validate_solver_output` classifies without executing, without any
  correctness dependence: transport (no usable text) before truncation
  (`length` / `incomplete-*` stop) before format (empty or `compile`
  rejection) before ok. Staging always writes the validated source bytes;
  digests bind staged bytes to the raw receipt text.
- `attribute_grade_receipt` classifies sandbox results: pass / timeout /
  import-execution (any exception-shaped case actual) / wrong-answer /
  ungraded (no case payload). `_dispatch_grade` delegates to it, so every
  existing outcome string is preserved bit-for-bit.
- Known boundary, by design: a JSON-envelope response is parseable Python
  (a dict literal), so it grades as an import-execution failure and is
  never salvaged. Syntax is checked; meaning is graded.

## Findings ledger

- ENG-SOLV-01 (P1, fixed): `_arm_prompt` stated no response contract and
  four duplicated sites staged raw model text as `candidate.py`
  (`_run_development`, `run_abcs` arms, `run_subsequent_use` incumbent,
  `development._collect_task`). Correct fixes trapped in prose failed with
  `SyntaxError`, recorded as plain failure. Fix: the shared contract plus
  shared `begin_solver_grade` / `finish_solver_grade`; the four fallbacks
  are deleted, not wrapped.
- ENG-SOLV-02 (P1, fixed): `code = text if ... else task["broken"]`
  silently graded the broken input as if it were model output, masking
  transport/format failures. Fix: removed at all four sites; missing text
  validates as transport/format and grades honestly as empty source.
- ENG-SOLV-03 (P1, fixed): no stage attribution anywhere; format,
  execution and wrong-answer failures were one undistinguished
  `"failure"`. Fix: every solver record now carries `solver_status`,
  `grade_class`, raw bytes and the staged digest (arms, dev
  outcomes/transcripts, use record, experience claims).
- ENG-SOLV-04 (P2, fixed): the `_run_development` transcript-reuse path
  dropped the new attribution keys, breaking rerun equality. Caught by
  existing `test_dev_batch_runs_once`; fixed in production code, the test
  is untouched.
- ENG-SOLV-05 (smoke result): live baseline on panel-triangular through
  the real inference-to-source-to-grade path: solver `ok`, grade `pass`,
  outcome `success`. One attempt, no retries, no tuning. Evidence:
  `reports/evidence/eng-solv/smoke_result.json`.

## Checks (all with real PG + real subprocesses where they run)

- Red loop pre-fix: `pytest tests/test_eng_solv_contract.py -k "constant
  or validator or prompts"` failed with
  `AttributeError: ... has no attribute 'SOLVER_SOURCE_CONTRACT'`.
- `pytest tests/test_eng_solv_contract.py`: 14 passed (24s).
- `pytest tests/test_dev01_compare.py tests/test_dev02_episode.py
  tests/test_dev01_ops.py reviews/probes/test_live_evidence_controls.py`:
  green after ENG-SOLV-04 (one genuine regression found and fixed).
- `pytest tests/test_d02live_episode.py tests/test_dev01_episode.py`:
  32 passed.
- Positive control: `experiments/run_tests.py` on panel-triangular
  reference bytes: `passed 3, failed 0` (sha256 `042c915d...befe`).
- Adversarial probes: unicode/hints/fence-in-string accepted; JSON
  envelope grades (never salvaged); 5000-deep nesting and null bytes
  classify as format without crashing; `"a: b"` wrong-string is not
  execution-shaped.

## Live smoke limits (explicitly authorized, narrow)

- Gateway `http://localhost:6446/v1`, API `responses`, model
  `muse-spark-1.3-contributor-free` (same as prior campaign, comparable).
- ONE task: panel-triangular (visible-regression, not held-out transfer).
- Fresh DB `settlement_engsolv` (dropped/recreated pre-smoke), seeded
  allocation 2,000,000 units, `SETTLEMENT_MODEL_TOKENS=8192`,
  `--launcher local --allow-uncontained` per explicit authorization.
- Observed usage 172 in / 588 out tokens, `billed False, charge 0`:
  conservative settlement, no provider-billing claim. Allocation debit
  8455 units (model reservation release + 111 settled sandbox grade).
- Key from `$META_API_KEY` at runtime only; bundle carries no secrets.
- Source revision pinned in bundle (`f478143` + dirty list at run time);
  a format/harness failure would have stopped and become the result.

## Files changed (owned paths only)

- `src/settlement/experiment.py`: contract, validator, attribution,
  begin/finish helpers, four consumption sites, reuse carry-through.
- `src/settlement/development.py`: collection prompt + validation +
  transcript/claim attribution.
- `tests/test_eng_solv_contract.py`: new maintained contract suite.
- `reports/evidence/eng-solv/run_smoke.py`, `smoke_result.json`: runner +
  redacted single-attempt evidence.
