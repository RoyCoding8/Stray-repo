# B-ACQ workstream

Slice 1 green: outside-menu retention (A4). Constructed a retained
repertoire with one member whose capability_id is not in
SEED_CAPABILITIES but whose bytes are executable (greedy reducer source,
behavior-neutral rename), froze it, loaded it, ran use on a software
task. The use record executes that member (selected == member id,
executed_source == member bytes) rather than seed lookup or incumbent
fallback. Failed first with StopIteration at the seed-only lookup, then
passed after the fix.

Fix: new `_run_member` in the use region of `trajectory.py` executes
retained member bytes directly (seed lookup only for authored
incumbents); `run_use` records `executed_source`; freeze/load preserve
the full member dict untouched.

No seam needed from the coordinator. Packet/dispatch/resume regions
untouched (B-INIT owned). Model construction deferred to slice 2.

Verification: `tests/test_bacq_method.py` 1 passed; neighbors
`test_ad01_traj.py` + `test_binit_action.py` + `test_ad01_env.py`
51 passed; checker `_verify_record` clean on the new record shape.

Commit: feff380
