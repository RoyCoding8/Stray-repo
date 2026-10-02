REVISED check set, version 2. Changes from version 1 are marked. Run by scripts/s09_verify.py with no provider and no live database, reading the exported JSON plus the committed frozen task corpus, which is deterministic offline data and not runtime output.

Unchanged from v1:
V1. Recompute SHA-256 of the exported policy source and require equality with the exported candidate_digest, the freeze candidate_digest, and the binding provenance candidate_digest.
V2. Re-verify the exported policy artifact offline: kind == learning-policy, entry == STEP, declared ABI, parent_digest, and applicability equal to the proposal scope.
V3. Re-run the static STEP source validation offline without executing the source.
V4. Require the exported assessment to name the panel task ids and the frozen rule, and require the panel/rule freeze journal position to precede every executed assessment step.
V6. Require both arms to carry non-zero measured step_calls and a decisions list whose length equals step_calls.
V7. Require the exported binding row to cite the exported assessment attempt id in evidence refs, with protocol, evaluator version and scope equal to the assessment's.
V8. Require every exported use record with a release id to name an executed source digest equal to the bound candidate digest, or carry a non-empty fallback_reason.
V10. Require exported panel task ids disjoint from exported development task ids and from the campaign's own task list.

CHANGED, addressing the circularity objection:
V5a. Do not merely re-apply the rule to runtime-supplied counts. Require the export to carry, per arm per panel task, the produced task output. Recompute the quality counts from the FROZEN CORPUS offline by re-running the deterministic checker and size measure on those outputs, and require the recomputed preserved and reduced counts to equal the exported per-arm quality. Then re-apply the exported frozen rule to the RECOMPUTED counts and require the resulting outcome to equal the recorded outcome. Quality therefore no longer depends on trusting the runtime; only the resource measurements do, and that limit is stated explicitly rather than hidden.

NEW, addressing the missing incumbent comparison evidence:
V11. Require the exported assessment to record, for the incumbent arm and the candidate arm, the identical ordered panel task id list, and require that list to equal the frozen panel task ids. Require both arms to name the same rule_id and the same evaluator_version. Require the incumbent arm to carry its own non-zero step_calls and its own recomputable outputs under V5a. A verdict whose incumbent arm has an empty or differing panel, or zero executed steps, must fail verification. This makes a comparison against nothing detectable.

NEW, addressing the missing decision sequence export:
V12. Require the export to carry, per arm, the ordered executed action-kind sequence and the per-step returned state digest. Require the sequence length to equal step_calls and the recorded effects to be consistent with it, so behaviour is visible to a reviewer rather than only counted. When the outcome is bind, require the candidate and incumbent sequences to be present and comparable so a reader can see what changed. Do not require them to differ, because a policy may legitimately bind on resource cost with the same action sequence; require only that both are exported and internally consistent.

REPLACED, addressing the inadequate key-name leakage check:
V9a. Replace key-name checking with value checking. Load the panel tasks' sealed and protected values from the committed frozen corpus offline, then require that none of those literal values appears anywhere in the serialized export, at any depth, under any key. Keep the key-name check as an additional cheap guard, but the value check is the binding one. This detects a leaked answer that appears as a plain value under an innocuous key.