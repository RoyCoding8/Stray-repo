# Stage 09 byte-path review — c3e8566

Reviewer: byte-path-review (second independent review)

## Scope and checkout note

Reviewed commit `c3e856653ae81e63c98a1b24aa227dbf2f57e97c` (`c3e8566`) from the requested branch. The Windows checkout was not actually clean when inspected: `experiments/ad01/records.py` was modified; `scripts/s09_verify.py` and `tests/test_s09o_export.py` were also modified; and four `reports/jev/*` files were untracked. I did not alter or reset that worktree. All runtime probes imported an archive materialized from exactly `c3e8566` at `/mnt/d/AI/s09o/snapshot-c3e8566`; only databases named `s09o_rev2_*` were created and dropped. `evidence_inv01_live/` was not touched.

## Executive answer

The exact candidate policy bytes do reach a fresh continuation process. The gateway response is parsed into source bytes, frozen with a full SHA-256, assessed under that frozen digest, bound with the same full digest, reloaded from the freeze by release resolution, verified again, and executed in a child process. My fresh-process probe observed the candidate-only `construct_method` decision and an exact digest match; it did not silently run the incumbent or legacy consumer.

The assessment is nevertheless not a sufficient proof of useful policy work. It really runs each candidate as `STEP`, but its action adapter accepts `inputs["candidate"]` directly. A policy can read the full panel task supplied in its view, delete one operation, return that artifact, and obtain `bind` without executing a task method or making a query. I demonstrated this on both held-out panel tasks. The incumbent arm is separately executed and its values are real, but a trivial stop incumbent can be compared and beaten; identical bytes tie and reject; empty bytes fail verification.

Assessment-side child STEP calls and local oracle queries are not broker operations and have no allocation/operation identity. Local query counts are copied into the revision episode and therefore appear as episode/query accounting in the public result, but they are not charged as settlement operations. Assessment `model_calls` are currently always zero: `request_model` is explicitly rejected and the task-producing adapter returns zero model calls. Assessment child wall time and step calls are recorded inside the assessment record but are not part of the export's measured cost totals.

## 1. From model output to executed decision

### Hop 1 — gateway response to candidate source

`construct._call` creates or reuses a durable model-inference operation, reads the success receipt's `text`, and returns that exact response text (`experiments/ad01/construct.py:72-112`). `_evaluate` passes that response to `_parse_entry`, which extracts the source from the response envelope, obtains its entry, validates it, and runs the validation child (`construct.py:144-190`). This is the first re-derivation: the response envelope is parsed into a source string. The source itself is then carried, not regenerated.

`construct_policy` performs the same response-to-source evaluation and, on success, creates a `learning-policy` artifact from `evaluated["source"]`; the returned member carries `policy_source`, `source_digest`, the artifact, response digests, and model operation lineage (`construct.py:404-449`, `construct.py:460-499`). The artifact digest is recomputed from the exact source bytes (`policy_step.py:151-172`). A different response can substitute only by producing different bytes and therefore a different digest; a response-envelope variation that extracts to the same source is semantically the same policy source.

### Hop 2 — freeze

`_construct_policy_revision` freezes `candidate["policy_source"]` (`trajectory.py:784-808`). `records.freeze_candidate` computes SHA-256 over the UTF-8 source, stores both `candidate_digest` and `source`, and refuses a second byte sequence for an already frozen proposal (`records.py:910-945`). The freeze request is proposal-scoped and idempotent (`records.py:927-945`). A different source cannot replace the frozen source through this path without a SHA-256 collision or database tampering.

The assessment then uses `freeze["source"]` as `candidate_source`, constructs an artifact from those bytes, and verifies it (`trajectory.py:809-832`). The candidate digest supplied to assessment is `freeze["candidate_digest"]`; assessment independently checks source-to-digest equality before executing (`policy_assess.py:389-404`).

### Hop 3 — sealed protocol and assessment

The proposal freezes a panel and rule through `freeze_protocol`; assessment refuses a panel/rule different from that journaled protocol (`policy_assess.py:141-178`, `policy_assess.py:389-404`). The candidate record is built as `{artifact, policy_source}` and the incumbent record is built separately from the incumbent bytes; the two arms are run separately and then compared (`policy_assess.py:438-461`). There is no candidate-byte re-derivation at this point: the candidate source is carried from the freeze into the record. Artifact metadata is re-derived from the carried source by `make_policy_artifact`.

### Hop 4 — bind

On `bind`, `_construct_policy_revision` uses the candidate's capability id as the release version and passes the frozen full digest, proposal id, assessment attempt id, protocol, evaluator and scope to `selection.bind_revision` (`trajectory.py:833-876`). `bind_revision` reloads the proposal, freeze and assessment, requires the supplied digest to equal the frozen digest, requires the evidence to cite that assessment, and requires protocol/evaluator/scope equality (`selection.py:66-141`). The release row stores the candidate digest in `invalidation` and the version list (`selection.py:156-214`).

The version/capability id is not the byte authority here; it is only a selector label. The byte authority is the full `candidate_digest` tied to the frozen source and assessment. A different source cannot pass the freeze/digest/evidence checks through the public path unless it collides with the full SHA-256.

### Hop 5 — release resolution and child STEP

`_resolve_policy_consumer` loads the active binding for the explicit release, obtains its provenance, loads the proposal's freeze, requires the provenance digest to equal the frozen digest, hashes the frozen source again, rebuilds an artifact from that source, verifies it, and passes that record to `step_policy_consumer` (`trajectory.py:890-932`). Rebuilding the artifact is the second explicit re-derivation; the source bytes are still carried from durable freeze storage.

`StepPolicyConsumer` stores the verified artifact and source (`agenda_policy.py:383-401`). Each policy decision invokes `policy_step.run_policy_step` with the stored `policy_source`; the returned result includes the source digest (`agenda_policy.py:527-557`, `method_exec.py:440-507`). `method_exec.run_step_out_of_process` hashes the source, writes exactly that source to `policy.py`, and includes the digest in the child identity (`method_exec.py:452-477`). The child driver imports that `policy.py` and calls the requested entry (`method_exec.py:367-408`). Durable STEP state records the source digest beside the results (`policy_step.py:248-312`).

`_activate_bound_policy` replaces the incumbent consumer only after a durable `bound` episode and successful release resolution (`trajectory.py:934-943`). `run_campaign` also resolves an explicit `policy_release` before driving a fresh campaign, rather than accepting an injected consumer when the release is supplied (`trajectory.py:986-1027`).

### Fresh-process result

The fresh-process probe created a real bound release, stopped the first process after the revision boundary, then launched a separate Python process with the DSN, campaign id and release id. The resumed row had:

```text
first_bound_digest=615006744f74078c27dcff53f555acf6c2f6e68a7a8f6b622a66fec80bc245bd
source_digest=615006744f74078c27dcff53f555acf6c2f6e68a7a8f6b622a66fec80bc245bd
digest_matches=true
action_kinds=["construct_method"]
child_returncode=0
```

The incumbent source in the probe would emit `propose_revision` after its first step; the fresh row emitted `construct_method`. A legacy consumer would not produce a `policy_output.source_digest` for the bound policy row. This is concrete evidence that the fresh process executed the bound candidate bytes.

## 2. Is the assessment really measuring the policy?

Yes in the narrow sense: `_run_arm` materializes a view, executes the supplied record as `STEP` in a child, records the returned action and state digest, maps that action through `_effect`, runs the candidate checker, and accumulates per-arm resources (`policy_assess.py:264-335`). Candidate and incumbent arms are invoked in separate calls (`policy_assess.py:447-450`); their decisions, effects, quality and resources are not copied between arms. Quality is recomputed from each arm's per-task reports (`policy_assess.py:330-337`).

No in the stronger sense required by the claim of useful policy improvement. `_candidate_from_action` has a direct branch: if `inputs["candidate"]` is a dict, it returns that artifact with zero queries and zero model calls, without `run_member_out_of_process` or `seeds.run_seed` (`policy_assess.py:200-240`). `_effect` then marks that action accepted and sends the returned object to `_check` (`policy_assess.py:242-261`). The view passed to STEP contains the full `task` dictionary (`policy_assess.py:276-282`; `policy_step.materialize_view` copies `task` into `task_content` at `policy_step.py:115-134`). For software tasks, that includes `ops`, `fault`, `witness`, and `seed` in the frozen task JSON.

### Demonstrated no-useful-work bind

The candidate source used in the probe did only this inside `STEP`: read `view['task_content']`, construct a candidate with `task['ops'][:-1]` plus the task's existing witness, and return it in `action.inputs['candidate']`. It did not call a method, an oracle, or a query-producing adapter. The trivial incumbent returned `stop`.

Probe result:

```json
{
  "outcome": "bind",
  "candidate_quality": {"tasks": 2, "preserved": 2, "reduced": 2, "failed": 0},
  "incumbent_quality": {"tasks": 2, "preserved": 0, "reduced": 0, "failed": 2},
  "candidate_resources": {"step_calls": 2, "queries": 0, "model_calls": 0, "child_wall_ms": 66},
  "incumbent_resources": {"step_calls": 2, "queries": 0, "model_calls": 0, "child_wall_ms": 65},
  "candidate_kinds": ["construct_method", "construct_method"]
}
```

The panel was `ad01-w0-within-sw-00` and `ad01-w0-transfer-sw-01`. The action was genuinely produced by each child STEP, but the task-producing effect was a policy-supplied artifact. This is **EXPLOITABLE** against the claim that assessment establishes useful task-method work.

Other assessor observations:

* `request_model` is not executed in the sealed assessor; `_effect` rejects it as unavailable (`policy_assess.py:242-249`).
* A source supplied in `inputs['method_source']` is actually validated and run out of process, and a seed method id is actually executed through `seeds.run_seed` (`policy_assess.py:212-240`). Those legitimate paths do not close the direct-artifact branch.
* A malformed candidate source is recorded as `unavailable` with empty arms rather than being silently scored (`policy_assess.py:405-437`).

## 3. Is the incumbent comparison real?

In the public revision path, the incumbent comes from the current consumer. `run_campaign` stores `_policy_record_for_consumer(consumer)` in the model-construction context (`trajectory.py:1028-1044`); `_construct_policy_revision` takes `construction["incumbent_policy"]`, extracts its `policy_source`, hashes it, and passes that record as the incumbent arm (`trajectory.py:809-832`). If no incumbent policy record exists, the revision is durably marked unavailable (`trajectory.py:812-820`).

Assessment independently verifies the incumbent source digest and artifact, then executes it as its own arm (`policy_assess.py:349-361`, `policy_assess.py:438-450`). The comparison uses candidate and incumbent preserved/reduced quality and candidate/incumbent query-plus-model-call resources; ties reject (`policy_assess.py:339-365`).

I probed three incumbent cases:

```text
trivial {"incumbent_steps": 2, "outcome": "bind", "reason": "candidate preserved 2/2 and reduced 2/2 within resource ceiling"}
same    {"incumbent_steps": 2, "outcome": "reject", "reason": "reduction margin 0 is below 1; tie rejects"}
empty   {"exception": "MethodExecutionError", "reason": "refused: empty-policy-source"}
```

Therefore:

* The incumbent arm is not a copied/defaulted candidate arm; it really executes its source.
* A trivial but valid incumbent can be beaten and produce `bind`. That is not an identity substitution; it means the public caller's incumbent quality is the baseline being assessed.
* Byte-identical candidate and incumbent arms tie and reject under the margin rule.
* Empty incumbent source cannot bind: artifact creation itself rejects empty source (`policy_step.py:151-157`), and a manually forged empty record fails `verify_policy_record`/child source validation (`policy_step.py:178-198`, `method_exec.py:340-365`).

## 4. Does fresh-process continuation use the bound bytes?

Yes. The public path requires the release id, resolves only the active binding for that release, checks the binding provenance against the frozen source and full digest, reconstructs/verifies the artifact, and constructs a `StepPolicyConsumer` from that source (`trajectory.py:890-932`). A fresh campaign process with `policy_release` follows that resolver before its loop (`trajectory.py:1014-1027`).

The second-process probe's child command was equivalent to:

```python
from experiments.ad01 import trajectory
out = trajectory.resume_campaign(
    dsn, cid, CHARTER, RESUME_CAPS, policy_release=release)
row = trajectory._s09_get(dsn, cid, 2)
p = dict(row["policy_output"])
assert p["source_digest"] == bound_digest
assert [r["action"]["kind"] for r in p["results"]] == ["construct_method"]
```

It returned zero and proved the exact candidate digest. Substituting the incumbent would have produced its `propose_revision` behavior; substituting the legacy consumer would not produce the candidate `policy_output.source_digest`. I did not find a byte substitution point in this path other than a cryptographic digest collision or direct database tampering.

## 5. Cost honesty

The assessment's execution is not charged as campaign broker work. `_run_arm` calls `policy_step.run_policy_step(policy_record, view, state)` without `dsn`, `allocation_id`, or `operation_id` (`policy_assess.py:285`; `policy_step.py:300-337`). With no DSN, the child launcher uses a local broker operation and a temporary directory rather than `broker.ensure_operation` against PostgreSQL (`method_exec.py:478-507`). The assessment API itself accepts only `dsn`, proposal/protocol data, source records, panel, rule and scope; it has no campaign/allocation argument (`policy_assess.py:381-388`).

A query-producing candidate using `seed-sw-greedy` on the same two-task panel returned:

```json
{
  "outcome": "bind",
  "candidate_resources": {"step_calls": 2, "queries": 8, "model_calls": 0, "child_wall_ms": 67},
  "incumbent_resources": {"step_calls": 2, "queries": 0, "model_calls": 0, "child_wall_ms": 69},
  "operation_rows": 0,
  "operation_effects": [],
  "command_journal_rows": 3
}
```

So local assessment queries are measured by the assessor and copied into the revision episode (`trajectory.py:824-831`), and the public result/export carries the episode's `queries` as `witness_queries` (`records.py:382-389`). They are not, however, represented by settlement operations or allocation reservations. Assessment step calls and child wall time sit in the nested assessment record; they are not part of `costs_measured` and are not subjected to the comparison's resource ceiling, which only adds queries and model calls (`policy_assess.py:355-365`).

Assessment model calls are currently not a hidden spend path: `_effect` rejects `request_model` and every `_candidate_from_action` return path reports model calls as zero (`policy_assess.py:200-240`, `242-249`). The public revision code still sums the recorded arm model-call fields (`trajectory.py:824-831`), but the current assessor cannot produce a nonzero value. The uncharged local child/query work is nevertheless real resource consumption and can exceed what settlement operation accounting sees.

## Exact probe commands

All probes used this common PowerShell wrapper. The Python body shown under each label was the exact body passed through the base64 transport; the wrapper avoided Windows-to-WSL heredoc expansion:

```powershell
$code = @'
<the Python body below>
'@
$b64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($code))
wsl.exe -u ubuntu -- bash -lc "echo $b64 | base64 -d | PYTHONPATH=/mnt/d/AI/s09o/snapshot-c3e8566:/mnt/d/AI/s09o/snapshot-c3e8566/src:/mnt/d/AI/s09o/snapshot-c3e8566/experiments /home/ubuntu/.venvs/as9/bin/python -"
```

### Direct-artifact assessment probe

The body created/dropped `s09o_rev2_assess`, froze `s09o-direct`, used panel seed `s09o-rev2-direct`, and called `policy_assess.assess_policy` with this candidate core:

```python
candidate_source=(
    "def STEP(view, state):\n"
    "    task = view['task_content']\n"
    "    candidate = {'family': 'software', 'task_id': task['task_id'],\n"
    "                 'fault': task['fault'], 'ops': task['ops'][:-1],\n"
    "                 'witness': task['witness'], 'seed': task['seed']}\n"
    "    action = {'kind': 'construct_method', 'target': task['task_id'],\n"
    "              'inputs': {'candidate': candidate}, 'evidence_refs': [],\n"
    "              'requested_resources': {}}\n"
    "    return {'action': action, 'state': state}\n")
```

The full driver used `createdb ... s09o_rev2_assess`, `db.apply_migrations`, `records.open_revision_proposal`, `freeze_protocol`, `make_policy_artifact`, `assess_policy`, JSON output, and `dropdb ... s09o_rev2_assess` in a `finally` block.

### Incumbent matrix probe

The body created/dropped `s09o_rev2_incumbent`, used the same direct candidate, then called the same assessor three times with incumbent sources `S` (stop), `C` (identical candidate), and `""` with a manually forged empty artifact. The exact result was:

```python
trivial {"incumbent_steps": 2, "outcome": "bind", ...}
same {"incumbent_steps": 2, "outcome": "reject", ...}
empty {"exception": "MethodExecutionError", ...}
```

### Fresh-process continuation probe

The body created/dropped `s09o_rev2_cycle`, used a real provider double returning a JSON envelope containing `CANDIDATE`, ran:

```python
first = trajectory.run_campaign(
    0, 'I', CHARTER, CAPS, tasks=[TASK,TASK,TASK], campaign_seq=0,
    dsn=DSN, consumer=consumer(cid), constructor='model',
    gateway=provider, model='rev2', study_root=cid)
```

Then it launched a second interpreter with:

```python
child = (
    "import json,sys\n"
    "from experiments.ad01 import trajectory\n"
    "dsn,cid,release=sys.argv[1:]\n"
    "out=trajectory.resume_campaign(dsn,cid,CHARTER,RESUME_CAPS,"
    "policy_release=release)\n"
    "row=trajectory._s09_get(dsn,cid,2)\n"
    "p=dict(row['policy_output'])\n"
    "print(json.dumps({'source_digest':p.get('source_digest'),"
    "'action_kinds':[r['action']['kind'] for r in p.get('results',[])],"
    "'digest_matches':p.get('source_digest')==BOUND_DIGEST}))"
)
subprocess.run([sys.executable, '-c', child, DSN, cid, release], ...)
```

The actual run used the complete `CHARTER`, `RESUME_CAPS`, and bound digest values in the child code; it returned `child_returncode=0`, `digest_matches=true`, and `action_kinds=["construct_method"]`.

### Cost probe

The body created/dropped `s09o_rev2_cost`, used a query-producing candidate with:

```python
"inputs": {
    "method_id": "seed-sw-greedy",
    "max_queries": 4,
},
```

It called `assess_policy`, then queried:

```python
ops = conn.execute(
    "SELECT id,payload->>'effect' AS effect FROM operations ORDER BY id"
).fetchall()
journals = conn.execute("SELECT count(*) FROM command_journal").fetchone()[0]
```

and printed arm resources, operation count/effects, and journal count. Output was `candidate queries=8`, `child_wall_ms=67`, `model_calls=0`, `operation_rows=0`, `command_journal_rows=3`, `outcome=bind`.

## Ranked findings

1. **EXPLOITABLE — direct policy-supplied candidate bypasses useful task-method execution.** `policy_assess.py:200-240` accepts `inputs["candidate"]`, while `policy_assess.py:242-261` scores it and `policy_assess.py:276-282` gives STEP the full task. The exact probe bound a policy with zero queries/model calls after it copied the task witness and dropped one operation. This most directly defeats the claim that the revised policy was genuinely assessed for useful investigation behavior.

2. **EXPLOITABLE — assessment child/query work is outside settlement charging.** `policy_assess.py:285` calls STEP with no DSN/operation identity; `method_exec.py:478-507` therefore uses local execution. The cost probe measured eight candidate queries and 67 ms of child wall time while PostgreSQL had zero operation rows. Query totals are copied into the episode, but no allocation/operation charge represents the assessment work; step/wall resources are not in the comparison cost rule (`policy_assess.py:355-365`).

3. **CLOSED — candidate bytes are substituted between freeze, bind, release resolution and fresh STEP.** Freeze stores source plus full digest and refuses replacement (`records.py:910-945`); assessment checks the source/digest (`policy_assess.py:389-404`); bind rechecks the freeze and evidence (`selection.py:95-141`); resolver rehashes the frozen source and verifies a rebuilt artifact (`trajectory.py:890-932`); child identity includes the source digest (`method_exec.py:452-477`). The fresh-process probe observed the exact bound digest and candidate-only action.

4. **CLOSED — incumbent arm is not copied or skipped.** The public path obtains incumbent bytes from the current consumer (`trajectory.py:1028-1044`), verifies them, runs candidate and incumbent separately, and compares their independently accumulated records (`policy_assess.py:349-361`, `438-461`). The edge probe showed trivial incumbent `bind`, identical bytes `reject`, and empty bytes verification failure.

No additional byte-path exploit was demonstrated. The direct-artifact assessment and uncharged assessment execution are the material findings for this remit.
