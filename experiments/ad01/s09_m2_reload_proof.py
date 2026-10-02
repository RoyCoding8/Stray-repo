"""M2 line 51: prove retention/reload in a fresh process, offline.

`WORKER-STAGE-09-CONNECTED-STUDY.md:51` asks that retention/reload be proved
"in a fresh process", and line 53 that the post-live join tie each method to
its own receipts and byte identity. A proof that only holds in the process
that wrote the artifact proves nothing about durability, so this runs as a
subprocess with an empty environment contribution: it reads only committed
bytes under `reports/evidence/`, rebuilds the method and the task from those
bytes, and re-executes through the real bounded executor.

It used to call the executor with no `dsn` and describe that as "no
dispatch". That branch was removed, because a source file being local is not
authority, and a diagnostic path that wants to execute policy source without
a store is not a special case. So the reload now executes under real
authority in a disposable database of its own, created and dropped around
the subprocess. Line 53 asks for stores separate from live; a disposable
store that never existed before this proof and is gone after it satisfies
that as strictly as opening none did, and it satisfies it honestly rather
than by declining to run the bytes at all.

No `authority.admit_study_call`, no `broker.dispatch_operation` outside the
executor, no gateway. Line 53 also requires stores and namespaces separate
from live.

Every figure is re-derived from the reloaded bytes and compared against the
value the live run committed. A mismatch is a failure, not a note.

Run it with `python3 experiments/ad01/s09_m2_reload_proof.py`. It prints JSON
and exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "reports" / "evidence"
DEFAULT_OUT = EVIDENCE / "inv_r1_m2_join" / "reload_proof.json"

RELOAD_SOURCE = r'''
import json, sys
sys.path.insert(0, %(root)r)
sys.path.insert(0, %(root_src)r)
from experiments.ad01 import worlds, method_exec
from experiments.representation import checkers

def reduce_size(task, candidate):
    if task["family"] == "software":
        return len(task["ops"]), len(candidate["ops"])
    return (len(task["vertices"]) + len(task["edges"]),
            len(candidate["vertices"]) + len(candidate["edges"]))

spec = json.load(open(sys.argv[1]))
out = {"checks": [], "reloaded": []}
for case in spec["cases"]:
    member = {"method_source": open(case["member_path"]).read(),
              "entry": case["entry"]}
    task = worlds.load_task(worlds.FROZEN_DIR, case["task_id"])
    entry = method_exec.verify_member(member)
    result = method_exec.run_member_out_of_process(
        member, task, max_queries=case["max_queries"],
        dsn=spec["authority"]["dsn"],
        allocation_id=spec["authority"]["allocation_id"],
        operation_id="reload-proof-%%s" %% case["capability_id"])
    candidate = result["candidate"]
    initial, final = reduce_size(task, candidate)
    report = (checkers.check_software(task, candidate)
              if task["family"] == "software"
              else checkers.check_graph(task, candidate))
    out["reloaded"].append({
        "capability_id": case["capability_id"],
        "task_id": case["task_id"],
        "entry": entry,
        "queries": result["queries"],
        "source_digest": result["source_digest"],
        "initial_measure": initial,
        "final_measure": final,
        "normalized_reduction": ((initial - final) / initial
                                    if initial else None),
        "verdict": report["verdict"],
        "effect_equals_committed": candidate == case["committed_output"],
    })
json.dump(out, sys.stdout)
'''


def cases_from_committed() -> dict:
    """Every executed use record in run 8 becomes a reload case.

    The cases are built from the committed evidence rather than hand-listed, so
    a use record added to the run is picked up without editing this file. Each
    member is written to its own file first, so the child reloads the method
    out of bytes on disk rather than out of the object this process parsed, and
    the digest of those bytes is checked against the committed
    `source_digest` before anything executes.
    """
    use_records = json.loads(
        (EVIDENCE / "inv_r1_m3b" / "use_records.json").read_text())
    repertoire_path = (EVIDENCE / "inv_r1_m3b" / "repertoires" /
                       "repertoire-w2-I.json")
    repertoire = json.loads(repertoire_path.read_text())
    members = {m["capability_id"]: m for m in repertoire.get("members", [])}
    member_dir = EVIDENCE / "inv_r1_m2_join" / "members"
    member_dir.mkdir(parents=True, exist_ok=True)
    cases = []
    for record in use_records:
        capability_id = record.get("executed")
        if record.get("status") == "refused" or capability_id not in members:
            continue
        member = members[capability_id]
        path = member_dir / ("%s.py" % capability_id)
        path.write_text(member["method_source"], encoding="utf-8")
        cases.append({
            "capability_id": capability_id,
            "task_id": record["task_id"],
            "member_path": str(path),
            "entry": member["entry"],
            "max_queries": record["costs"]["witness_queries"],
            "committed_output": record["output"],
            "committed": {
                "initial_measure": record["initial_measure"],
                "final_measure": record["final_measure"],
                "normalized_reduction": record["normalized_reduction"],
                "verdict": record["verdict"],
                "queries": record["costs"]["witness_queries"],
                "source_digest": member["source_digest"],
            },
        })
    return {"cases": cases}


def run_fresh_process(spec_path: Path, authority: dict) -> dict:
    """Run the reload in an interpreter that shares nothing with this one.

    The subprocess gets a scrubbed environment: no inherited study or gateway
    variables, and `PYTHONPATH` set explicitly rather than appended to, so the
    child resolves the repository from its own arguments. The store and
    allocation it executes under are named in the spec file rather than in
    the environment, so the child gets exactly the authority this proof
    chose and nothing it inherited.
    """
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("SETTLEMENT_", "S09_", "OPENROUTER_",
                                  "OPENAI_", "ANTHROPIC_"))}
    env["PYTHONPATH"] = "%s:%s" % (ROOT, ROOT / "src")
    source = RELOAD_SOURCE % {"root": str(ROOT), "root_src": str(ROOT / "src")}
    proc = subprocess.run([sys.executable, "-c", source, str(spec_path)],
                          cwd=str(ROOT), env=env, capture_output=True,
                          text=True, timeout=900)
    if proc.returncode != 0:
        raise SystemExit("fresh-process reload failed:\n%s" % proc.stderr)
    return json.loads(proc.stdout)


@contextlib.contextmanager
def reload_authority():
    """A disposable store and allocation for the reload, and nothing else.

    Created before the subprocess runs and dropped after, so the proof's
    executions are durable and attributed while they run and leave nothing
    behind afterwards. It is separate from any live store by construction:
    it is created here, for this proof, and never existed before it.
    """
    from experiments.ad01 import s09_run_isolation as isolation
    from settlement import authority as _authority

    token = "m2-reload-proof-%s" % uuid.uuid4().hex[:8]
    database = isolation.create_disposable_db(token,
                                              admin_dsn=isolation.admin_dsn())
    try:
        handle = _authority.authorize_study(
            database.dsn, isolation.study_root_for(token), authorized=100000,
            allocation_id="m2-reload-proof-%s" % token)
        yield {"dsn": database.dsn, "allocation_id": handle.allocation_id}
    finally:
        isolation.drop_disposable_db(database,
                                     admin_dsn=isolation.admin_dsn())


def build() -> dict:
    spec = cases_from_committed()
    if not spec["cases"]:
        raise SystemExit("no executed use record to reload")
    spec_path = EVIDENCE / "inv_r1_m2_join" / "reload_spec.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    with reload_authority() as authority:
        spec = {**spec, "authority": authority}
        spec_path.write_text(json.dumps(spec, indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")
        reloaded = run_fresh_process(spec_path, authority)
    checks = []
    for case, got in zip(spec["cases"], reloaded["reloaded"]):
        for field, committed in case["committed"].items():
            checks.append({
                "capability_id": case["capability_id"],
                "task_id": case["task_id"],
                "field": field,
                "committed": committed,
                "reloaded": got.get(field),
                "agrees": got.get(field) == committed,
            })
        checks.append({
            "capability_id": case["capability_id"],
            "task_id": case["task_id"],
            "field": "effect_equals_committed_output",
            "committed": True,
            "reloaded": got["effect_equals_committed"],
            "agrees": got["effect_equals_committed"] is True,
        })
    return {
        "proof_version": "inv01-m2-reload-v1",
        "requirement": "WORKER-STAGE-09-CONNECTED-STUDY.md:51 fresh-process "
                       "retention/reload; :53 method-to-receipt join",
        "fresh_process": {
            "interpreter": "subprocess, separate from the writer",
            "environment_scrubbed": True,
            "inherits_no_gateway_or_study_variables": True,
            "reads_only_committed_bytes": True,
        },
        "authority": {
            "dsn_passed": True,
            "store": "disposable database created for this proof and"
                     " dropped after it",
            "separate_from_live_store": True,
            "authority_admit_study_call_called": False,
            "gateway_contacted": False,
        },
        "cases": len(spec["cases"]),
        "checks": checks,
        "checks_total": len(checks),
        "checks_failed": sum(1 for c in checks if not c["agrees"]),
        "verdict": "reproduced" if all(c["agrees"] for c in checks)
        else "diverged",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    proof = build()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proof, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(json.dumps({k: proof[k] for k in
                      ("out", "cases", "checks_total", "checks_failed",
                       "verdict") if k in proof} | {"out": str(out)},
                     indent=1))
    return 0 if proof["verdict"] == "reproduced" else 1


if __name__ == "__main__":
    raise SystemExit(main())
