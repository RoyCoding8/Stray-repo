# CLOSE-2 recorded smoke provenance

- task: panel-triangular (visible-regression, same as historical smoke)
- source_revision: 35c3fef26333927d48e0f7d3a5c5d2c544642a64 (tree clean at run)
- solver_contract_sha256: 770e258b3ce62824c3c566a35a5a61208a2d36fb9e3e3ae8dc4ccdc178663aae
- reference_sha256: 042c915d433330d25cd5e8f6ce6917fb386cb92c836a43b95eca3b6bfc81befe
- gateway: http://localhost:6446/v1 api=responses discovery=GatewayStatus.REACHABLE auth=GatewayStatus.AUTHENTICATED
- env names only: SETTLEMENT_GATEWAY_URL, META_API_KEY, SETTLEMENT_MODEL, SETTLEMENT_MODEL_TOKENS
- model_requested: muse-spark-1.3-contributor-free
- launcher: local --allow-uncontained (explicit smoke LS-01) profile=local-process
- outcome: success solver=ok grade=pass (3/3 cases passed)
- unique operations: 2 ['grade-close2-use-panel-triangular', 'model-close2-use-panel-triangular']
- consumed 0 -> 8455 (delta 8455); settled sum 8455; reconciled=True

Historical 8344/111/111/8455 reads under the integrated accounting as: model reservation 8344 released-or-settled per reservation row, grade 111 settled, consumed delta equal to the settled sum over unique operations. See reconciliation.json; the original reports/evidence/eng-solv/smoke_result.json is preserved untouched.
