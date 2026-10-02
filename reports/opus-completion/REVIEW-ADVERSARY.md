# Adversarial review: stage 09 completion

Target: `8e05c148add0b59aeb29d486eeed79a234700306` (`codex/stage-09-opus-completion`). The checkout was already dirty before review, including tracked source and evidence files; I made no changes there. `git diff --ignore-all-space --stat HEAD` was empty for the inspected `experiments/ad01` files, so the committed line references below match the imported probe code. The only file written by this review is this report.

Runtime probes ran as WSL user `ubuntu` with `/home/ubuntu/.venvs/as9/bin/python`, PostgreSQL over `/var/run/postgresql`, and `PYTHONPATH` set to the checkout, `src`, and `experiments`. The only databases created/dropped were `s09o_adv_authority` and `s09o_adv_matrix`. `evidence_inv01_live/` was not touched.

## 1. AUTHORITY

### 1.1 The public revision path never assesses or binds a constructed policy — EXPLOITABLE

**Location:** `experiments/ad01/trajectory.py:711-761`, especially `734-753`; public dispatch is `experiments/ad01/cli.py:229-265`.

**Attack / observation:** A public `run` or `resume` with a policy revision can open a proposal and freeze model-produced bytes, then return an episode with `assessment_status: "pending"`. `_construct_policy_revision` never calls `records.assess_frozen` and never calls `selection.bind_revision`. A call-site census found the only production definitions/usages are:

```text
experiments/ad01/records.py:1002:def assess_frozen(...)
experiments/ad01/selection.py:62:def bind_revision(...)
```

The other `assess_frozen` and `bind_revision` call sites are tests. The CLI only calls `trajectory.run_campaign` / `resume_campaign` and export. Therefore the public lifecycle cannot produce a promoting release or a public rejection after assessment; the assessment/bind lifecycle is test-supplied and disconnected from the command that acquired the policy.

**Existing test:** No existing test catches the missing production continuation. `tests/test_s09c2a_actions.py` asserts the returned revision has `assessment_status == "pending"` (the disconnected intermediate state), while `tests/test_s09m34_cycle.py` manually calls `records.assess_frozen` and `selection.bind_revision` outside the public trajectory.

### 1.2 Promoting release can select an unassessed fallback — EXPLOITABLE

**Location:** `experiments/ad01/selection.py:217-230` and `260-264`; bind validation is `62-214`.

**Attack:** Supply a real qualifying assessment and its exact frozen digest, but set `versions` to an ID absent from the repertoire and set `fallback` to an incumbent that was not assessed. `bind_revision` never checks that a version is present in the repertoire or that `fallback` is the assessed candidate. `select_member` first fails `_bound_member` and then returns any repertoire member whose `capability_id` equals `fallback`, without checking the pinned digest, scope, or assessment provenance.

Probe result from a fresh `s09o_adv_authority` database:

```text
assessment_outcome= bind
bound_disposition= default
selected_capability= seed-sw-greedy
selected_member_method= unassessed-incumbent
```

The release was `default`, the assessment was genuine and `bind`, but the selected member was the deliberately unassessed fallback.

**Existing test:** No existing test catches this. `tests/test_s09c2b_bind.py:152-175` checks absent assessment, and `:145-162` checks stale selection with versions that are present. `tests/test_s09c2b_bind.py:300-312` checks caller labels without a proposal. None binds an absent version and then exercises fallback selection.

### 1.3 The requested authority attack matrix

The following outcomes were obtained in `s09o_adv_matrix`:

| Attack | Result | Code that decides it |
|---|---|---|
| Caller-chosen `request_id` | **CLOSED**: `ValueError: bind request id must be canonical` | `selection.py:142-154`; `payload_digest` uses sorted-key compact JSON at `src/settlement/common.py:71-75` |
| Evidence list containing only a non-assessment reference | **CLOSED**: `bind evidence must cite assessment ...` | `selection.py:112-121` |
| Evidence list containing the real attempt plus an unrelated reference | **Accepted**, but it does not bypass the genuine-assessment requirement; arbitrary extras are not rejected | `selection.py:86-90`, `118-121` |
| Protocol changed after assessment | **CLOSED**: proposal/assessment protocol checks | `selection.py:109-126`; repeat assessment context is also checked at `records.py:1016-1022` |
| Scope key order changed | **CLOSED as an attack**: dict equality and sorted payload hashing treat key order as equivalent | `selection.py:133-136`, `142-154`; `records.py:843-849` |
| Extra scope key against an assessment of the old scope | **CLOSED**: exact dict equality rejects it | `selection.py:133-136` |
| Extra scope key included consistently in a newly opened proposal | Accepted as an unsupported scope shape; `active_binding_for` only filters `family` (`selection.py:43-50`). This does not by itself remove assessment, but scope schema is not enforced. | `records.py:863-889`, `selection.py:43-55` |
| Stale `expected_versions` race | **CLOSED**: row lock and exact current-version comparison | `selection.py:158-184`, with `FOR UPDATE` at `159-161` |
| Absent qualifying assessment | **CLOSED** | `selection.py:100-120`, `137-141` |

The exact matrix probe payload was:

```bash
cd /mnt/d/AI/Agent-Society-v2-investigation-review
export PYTHONPATH=/mnt/d/AI/Agent-Society-v2-investigation-review:/mnt/d/AI/Agent-Society-v2-investigation-review/src:/mnt/d/AI/Agent-Society-v2-investigation-review/experiments
/home/ubuntu/.venvs/as9/bin/python - <<'PY'
from experiments.ad01 import records, selection
from settlement import db
DSN='dbname=s09o_adv_matrix host=/var/run/postgresql user=ubuntu'
db.apply_migrations(DSN, '/mnt/d/AI/Agent-Society-v2-investigation-review/migrations')
source=('def adv_matrix(task, oracle, max_queries=16):\n'
        '    return reducers.reduce_software(task, oracle, method="greedy", max_queries=max_queries)\n')
proposal=records.open_revision_proposal(DSN, investigation_id='adv-matrix', parent_digest='seed-sw-greedy', failure_record={'task_id':'ad01-w0-within-sw-00','parent_digest':'seed-sw-greedy'}, scope={'family':'software'})
freeze=records.freeze_candidate(DSN, proposal_id=proposal['proposal_id'], source_bytes=source, entry='adv_matrix')
assessment=records.assess_frozen(DSN, proposal_id=proposal['proposal_id'], tasks=['ad01-w0-dev-sw-00'], evaluator_version='adv-eval', protocol_id='s09-revision-v1')
base=dict(release_id='matrix-base', versions=['v-matrix'], scope={'family':'software'}, disposition='default', fallback='seed-sw-greedy', expected_versions=None, policy_version='p', protocol_id='s09-revision-v1', evaluator_version='adv-eval', evidence_refs=[assessment['attempt_id']], proposal_id=proposal['proposal_id'], candidate_digest=freeze['candidate_digest'])
def attempt(label, **over):
    args=dict(base); args['release_id']='matrix-'+label; args.update(over)
    try:
        out=selection.bind_revision(DSN, **args)
        print(label, 'ACCEPTED', out.get('disposition'), out.get('versions'))
    except Exception as exc:
        print(label, 'REJECTED', type(exc).__name__, str(exc))
attempt('caller-request', request_id='caller-chosen')
attempt('wrong-evidence', evidence_refs=['not-the-assessment'])
attempt('extra-evidence', evidence_refs=[assessment['attempt_id'],'unrelated-ref'])
attempt('changed-protocol', protocol_id='changed-protocol')
attempt('scope-key-order', scope={'family':'software'})
attempt('scope-extra', scope={'family':'software','extra':'x'})
attempt('stale-initial', release_id='matrix-stale', versions=['v-old'], expected_versions=None)
attempt('stale-new', release_id='matrix-stale', versions=['v-new'], expected_versions=['v-old'])
attempt('stale-race', release_id='matrix-stale', versions=['v-race'], expected_versions=['v-old'])
PY
```

## 2. LEAKAGE

### 2.1 Construction prompt path is closed for the tested sealed fields

**Location:** `experiments/ad01/construct.py:52-63`; `experiments/ad01/packet.py:66-83`, `202-224`, and renderer `237-284`.

`construct._prompt` does pass `task=task` into `construction_packet`, but `construction_packet` immediately applies `strip_task`; stripping is recursive for the listed sealed keys and `access_label`. The task and example candidate rendered at `packet.py:244-252` therefore use the cleaned copy. `project_observations` also drops sealed observations and strips sealed keys at `113-122`.

`construct_policy` does not pass raw task content to `_policy_prompt` (`construct.py:431-435`). That is not an exposure: `_policy_prompt` uses only a task digest at `construct.py:303-308` and a reduced `{task_id, verdict}` observation view at `333-337`. The difference between `_prompt` and `_policy_prompt` is therefore real but safe on those construction-call paths.

The targeted existing visibility tests passed:

```text
3 passed, 1 deselected, 1 warning in 3.89s
```

Command:

```bash
wsl.exe -u ubuntu bash -lc "cd /mnt/d/AI/Agent-Society-v2-investigation-review && export PYTHONPATH=/mnt/d/AI/Agent-Society-v2-investigation-review:/mnt/d/AI/Agent-Society-v2-investigation-review/src:/mnt/d/AI/Agent-Society-v2-investigation-review/experiments && /home/ubuntu/.venvs/as9/bin/python -m pytest -q tests/test_s09m34_visibility.py -k 'hidden_answer_perturbation or sealed_observation_excluded or protected_reference_refused'"
```

### 2.2 Runtime STEP view lets sealed feedback reach a model prompt and durable journal — EXPLOITABLE

**Location:** `experiments/ad01/policy_step.py:115-134`; `experiments/ad01/agenda_policy.py:488-506`, `511-528`, `546-549`, `585-610`; prompt admission/dispatch is `agenda_policy.py:403-475`.

`materialize_view` copies `observations` verbatim at `policy_step.py:122-123`; it does not call `packet.project_observations` or reject sealed observations. `StepPolicyConsumer.decide` passes its raw `seen["observations"]` to that function. An untrusted policy can copy a sealed field into `request_model.inputs.prompt`. `_model_request` accepts that prompt and places it into the broker message at `agenda_policy.py:438-445`; there is no sealed-content check.

The same action is stored in `results` at `agenda_policy.py:578-579`, and `persist_step_transition` stores `results` in `s09_policy_state.policy_output` (`policy_step.py:289-312`). Thus the secret can reach both the model prompt and a journal payload. `records.export_campaign` additionally exports receipt text at `records.py:334-344`, full receipts at `390`, and full operation rows at `420-422`; it provides no redaction layer.

The probe used a policy source that copies `view["observations"][0]["detail"]["sealed_answer"]` into a model prompt. Output:

```text
secret_in_policy_view= True
secret_in_construction_prompt= False
secret_in_model_prompt_argument= True
captured_prompt= sealed-answer-probe-9f3c
```

Exact Python payload:

```bash
cd /mnt/d/AI/Agent-Society-v2-investigation-review
export PYTHONPATH=/mnt/d/AI/Agent-Society-v2-investigation-review:/mnt/d/AI/Agent-Society-v2-investigation-review/src:/mnt/d/AI/Agent-Society-v2-investigation-review/experiments
/home/ubuntu/.venvs/as9/bin/python - <<'PY'
import json
from experiments.ad01 import packet, policy_step
from experiments.ad01.agenda_policy import step_policy_consumer
SECRET='sealed-answer-probe-9f3c'
TASK='ad01-w0-dev-sw-00'
sealed={'observation_id':'obs-sealed-probe','task_id':TASK,'capability_id':'seed-sw-greedy','verdict':'preserved','detail':{'access_label':'hidden','sealed_answer':SECRET}}
view=policy_step.materialize_view(task={'task_id':TASK,'family':'software'}, observations=[sealed], open_questions=[], last_result=None, eligible_methods=[], remaining={'model_calls':1})
print('secret_in_policy_view=', SECRET in json.dumps(view, sort_keys=True))
task={'task_id':TASK,'family':'software','hidden_answer':SECRET}
construction=packet.construction_packet(task=task, experience={'observations':[]}, budget={'max_queries':1}, prior_failure=None)
prompt_safe=packet.render_construction_prompt(construction)
print('secret_in_construction_prompt=', SECRET in prompt_safe)
source=('def STEP(view, state):\n'
'    secret = view["observations"][0]["detail"]["sealed_answer"]\n'
'    action = {"kind":"request_model", "target":"probe", "inputs":{"prompt":secret, "max_output_tokens":1}, "evidence_refs":[], "requested_resources":{"model_calls":1}}\n'
'    return {"action":action, "state":{}}\n')
artifact=policy_step.make_policy_artifact(source, origin='authored-control')
consumer=step_policy_consumer(artifact, dsn=None, cid='adv-leak', world=0, arm='I', max_policy_steps=1)
captured=[]
def capture(action, remaining, step_index):
    captured.append(action['inputs']['prompt'])
    return None, {'status':'refused','reason':'probe'}
consumer._model_request=capture
try:
    consumer.decide({'observations':[sealed], 'retained':[], 'remaining':{'model_calls':1}}, {}, boundary={'seq':0}, experience={})
except Exception as exc:
    print('decision_exception=', type(exc).__name__, str(exc))
print('secret_in_model_prompt_argument=', SECRET in captured)
print('captured_prompt=', captured[0] if captured else None)
PY
```

Existing visibility tests (`tests/test_s09m34_visibility.py:63-112` and `tests/test_s09m34_exposure.py:47-61`) cover `construction_packet` and `learner.visible_prompt`, not `materialize_view`, an untrusted STEP copying a sealed field, `request_model`, or journal/export redaction. They would not catch this.

## 3. IDENTITY

### 3.1 Reachable lifecycle identity checks are CLOSED; there is a residual truncated helper identity

**Location:** `experiments/ad01/records.py:839-849`, `910-959`; `experiments/ad01/selection.py:217-229`.

`proposal_id_for` canonicalizes scope key order with `sort_keys=True`; extra keys change the digest. `open_revision_proposal` converts the public failure task ID to `str` at `879-881`. `freeze_candidate` computes the full SHA-256 of the exact UTF-8 source bytes at `920-921`, uses the proposal-scoped request ID at `935-945`, and refuses different bytes for an existing proposal at `927-934`. `_bound_member` recomputes the full source digest and requires both the member digest and computed digest to equal the pinned full digest at `223-229`.

The canonicalization probe output was:

```text
scope_order = True
scope_extra_changes = True
task_int_vs_string_distinct = True
assessment_prefix_alias = True
proposal_string_a= s09-rev-inv-2165d377a4af
proposal_string_b= s09-rev-inv-dbc86f1db072
```

The first three results close the requested scope-order, extra-scope, and task-ID collision cases for the reachable API. The `assessment_prefix_alias` result deliberately passed synthetic non-digest strings with the same first 12 characters; it demonstrates that `assessment_attempt_id` truncates at `957-959`, but it is not a valid frozen candidate digest. In the real path, `assess_frozen` supplies the full digest from the freeze (`records.py:1009-1016`), and a second byte sequence cannot replace that proposal's freeze (`927-934`). A real SHA-256 prefix collision was not claimed or demonstrated. Existing freeze tests cover replacement rejection (`tests/test_s09m34_cycle.py:232-240`). No identity exploit was demonstrated.

Exact probe:

```bash
/home/ubuntu/.venvs/as9/bin/python - <<'PY'
from experiments.ad01.records import proposal_id_for, assessment_attempt_id
cases=[
 ('scope_order', proposal_id_for('inv','parent','task', {'family':'software','z':1}) == proposal_id_for('inv','parent','task', {'z':1,'family':'software'})),
 ('scope_extra_changes', proposal_id_for('inv','parent','task', {'family':'software'}) != proposal_id_for('inv','parent','task', {'family':'software','extra':'x'})),
 ('task_int_vs_string_distinct', proposal_id_for('inv','parent',1, {'family':'software'}) != proposal_id_for('inv','parent','1', {'family':'software'})),
 ('assessment_prefix_alias', assessment_attempt_id('p','a'*12+'X') == assessment_attempt_id('p','a'*12+'Y')),
]
for name,value in cases: print(name, '=', value)
print('proposal_string_a=', proposal_id_for('inv','parent',1, {'family':'software'}))
print('proposal_string_b=', proposal_id_for('inv','parent','1', {'family':'software'}))
PY
```

**Status:** CLOSED for the reachable lifecycle, with a plausible hardening concern around the 48-bit assessment-attempt suffix. Existing tests would catch freeze replacement but not the synthetic helper truncation case.

## 4. RESUME

### 4.1 Settled effects and pending policy steps are restart-safe — CLOSED

**Location:** `experiments/ad01/trajectory.py:295-325`, `240-266`, `867-942`, `1236-1259`; `experiments/ad01/agenda_policy.py:347-367`, `498-528`; model operation reuse is `agenda_policy.py:418-459`.

`execute_pending` returns the durable `effect_record` before running anything at `302-308`. When it runs a pending effect, it writes the effect record at `316-325`; `_s09_ensure_incorporated` uses insert-once plus `COALESCE` at `247-265`. `run_campaign` reconciles already-settled boundaries at `867-895` and drains accepted pending state at `897-942`. `resume_campaign` validates the campaign ID and delegates to the same driver at `1236-1259`.

For a cached STEP decision, `_cached_policy_decision` checks the source digest and distinguishes pending from admitted/refused at `347-367`. Pending state resumes from the cached action at `518-528`; the same model operation ID is derived at `418-420`. Even if a receipt is already success or failure, broker dispatch checks `_decided_receipt` and parks instead of calling the gateway again (`src/settlement/broker.py:489-526`).

Existing tests directly cover this axis: `tests/test_s09m2_policy.py:177-205` checks fresh-process restart with no new operations; `tests/test_s09c1_continuity.py:276-300` covers a preparation crash; `341-415` covers a crash before effect dispatch; `418-490` covers crash after settlement; and `492-563` covers a prepared operation. No second model call or lost attributable pending effect was demonstrated.

A concurrent caller can enter `execute_pending` before the first caller writes `effect_record` because the method does not hold a row lock across `_run_boundary` (`trajectory.py:302-324`). That is a possible duplicate computation, but stable operation IDs and broker decided-receipt handling prevent a second settled model call in the tested paths. It is not promoted to an exploit here.

## RANKED FINDINGS

1. **EXPLOITABLE — disconnected public revision lifecycle.** `trajectory._construct_policy_revision` stops after opening/freezing and marks assessment pending (`trajectory.py:734-753`); the public CLI has no assessment/bind continuation (`cli.py:229-265`). This directly defeats the required complete revision cycle and is the greatest threat to the conclusion that the revised policy improved behavior.
2. **EXPLOITABLE — unassessed fallback can execute under a promoting release.** `selection.py:260-264` returns an arbitrary fallback after the pinned version fails, while `bind_revision` never validates fallback provenance. The `s09o_adv_authority` probe accepted `default` and selected `unassessed-incumbent`.
3. **EXPLOITABLE — sealed runtime feedback can reach a model prompt and journal.** `policy_step.py:122-123` copies raw observations into the policy view; `agenda_policy.py:438-459` forwards policy-controlled prompt text; `policy_step.py:289-312` persists the action. The probe captured `sealed-answer-probe-9f3c` as the model prompt argument. Constructor prompt sanitization is CLOSED, but it does not protect this runtime STEP path.
4. **CLOSED — identity collisions in the reachable proposal/freeze/bind path.** Scope order is canonicalized, task IDs are string-normalized by the public proposal path, freeze identity uses full source SHA-256, and selection checks the full digest. The assessment helper's 12-character truncation is a hardening concern, not a demonstrated valid-candidate collision.
5. **CLOSED — restart duplicate-model-call/lost-pending attack.** Durable effect records, cached STEP actions, stable operation IDs, broker receipt checks, and the existing crash/restart tests prevent the specified second-call or attribution failure. The remaining unlocked duplicate-computation window was not shown to produce a second model call.
