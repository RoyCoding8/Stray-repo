"""Record M1's eight required behaviour checks as a result, not a claim.

`WORKER-STAGE-09-CONNECTED-STUDY.md:43` enumerates eight behaviours the budget
boundary must exhibit. Tests that pin them exist, but a test file is source:
nothing in the tree records that they were executed, which is why the M1 row
of `reports/STAGE-09-COMPLETION-MATRIX.md` is PARTIAL.

So this runs them, and then does the part a run alone does not do. A passing
test proves nothing unless it could have gone red, so each check that has a
covering test is re-run against a deliberately reinstated defect. The
mutations are applied to a copy of the tree under the system temp directory
and the checkout is never touched. A check whose mutation leaves the mapped
test green is reported as `mutation_silent`, which is a finding about the test
rather than about the code.

Determinism is a requirement, not a nicety: a reviewer re-runs this and
diffs the artifact against the committed one. Wall-clock time, temp paths and
run order are therefore excluded, and the failing-test set is sorted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = REPO_ROOT / "reports/evidence/inv_r1_m1_behaviour/gate-results.json"

LEDGER = "experiments/ad01/s09_exposure_ledger.py"
LIVE = "experiments/ad01/live_construct.py"
RECOMPUTE = "experiments/ad01/offline_recompute.py"
BROKER = "src/settlement/broker.py"
GATE = "experiments/ad01/m1_behaviour_gate.py"

# Per-file command lines. Kept separate because the M1 file is the one named
# by the milestone and the other three are the files that turn out to carry
# checks 7 and 8, which the milestone file does not reach at all.
GATE_FILES: dict[str, str] = {
    "m1": "tests/test_s09cs01_budget_denominations.py",
    "dispatch_ceiling": "tests/test_s09_n203_dispatch_ceiling.py",
    "broker_dispatch": "tests/test_broker_dispatch.py",
    "bundle_authority": "tests/test_r4_verify_bundle_authority.py",
    "offline_recompute": "tests/test_m4_offline_recompute.py",
}
DIGEST_FILES = (LEDGER, LIVE, RECOMPUTE, BROKER, *GATE_FILES.values(), GATE)

PYTEST_ARGS = ("-q", "-p", "no:randomly")

# `experiments/ad01/offline_recompute.py` and the bundle-authority tests import
# `test_output_evidence` by bare module name, which only resolves when the
# tests directory is on the path. `PYTHONPATH=$PWD:src` alone does not put it
# there, so every invocation below carries it explicitly.
TESTS_ON_PATH = "tests"


def pytest_command(files: Sequence[str]) -> str:
    return "PYTHONPATH=$PWD:src:%s .venv/bin/python -m pytest %s %s" % (
        TESTS_ON_PATH, " ".join(files), " ".join(PYTEST_ARGS))


# --- the eight checks -----------------------------------------------------


@dataclass(frozen=True)
class Check:
    key: str
    requirement: str
    where: str
    tests: tuple[str, ...]
    mutation_name: str = ""
    mutation: str | None = None
    anchor: str | None = None
    note: str = ""


# Each mutation is the inverse of the behaviour its check requires, reinstated
# at the point the original defect lived. A mutation that merely broke
# something would prove nothing about what the check is for.
NULL_RETURNS_ZERO = '''\
    amount = usage.get("charge_units")
    if amount is None:
        return ProviderCharge(ChargeState.REPORTED, units=0,
                              billed=usage.get("billed"),
                              charge_scale=usage.get("charge_scale"),
                              source=source)
'''

NULL_ANCHOR = ('    amount = usage.get("charge_units")\n'
               "    if amount is None:\n"
               "        return ProviderCharge.not_reported(source)\n")

RESERVATION_USES_A_CONSTANT = '''\
        units, kind = _broker_exposure(payload, retries)
        units = 25 * (retries + 1)
'''
RESERVATION_ANCHOR = "        units, kind = _broker_exposure(payload, retries)\n"

ALLOWANCE_EXPOSES_A_UNIT = '''\
    @property
    def unit_ceiling(self) -> int:
        """The dimensional error, restored: a send count read as a sum."""
        return (self.max_dispatches or 0) * 25

'''
ALLOWANCE_ANCHOR = "@dataclass(frozen=True)\nclass DispatchAllowance:\n"

HOLDS_ARE_ALWAYS_COUNTED = '''\
    def contributes_to_liability(self) -> bool:
        return True
'''
HOLDS_ANCHOR = ("    def contributes_to_liability(self) -> bool:\n"
                "        return not self.settled\n")

RESUME_GOES_NEGATIVE = '''\
    if remaining < 0:
        return DispatchBudget(
            ceiling_dispatches=allowance.max_dispatches,
            spent_dispatches=spent, remaining_dispatches=remaining,
            arithmetic="%d spent against a ceiling of %d" % (
                spent, allowance.max_dispatches),
            refusal_reason="")
'''
RESUME_ANCHOR = ("    remaining = allowance.max_dispatches - spent\n"
                 "    if remaining < 0:\n"
                 "        return DispatchBudget(\n"
                 "            ceiling_dispatches=allowance.max_dispatches,\n"
                 "            spent_dispatches=spent, remaining_dispatches=None,\n"
                 '            arithmetic="%d spent against a ceiling of %d" % (\n'
                 "                spent, allowance.max_dispatches),\n"
                 '            refusal_reason=("%d dispatches were already '
                 'spent against a "\n'
                 '                            "ceiling of %d, so the run is '
                 'over its allowance"\n'
                 '                            % (spent, allowance.max_dispatches)))\n')

CEILING_ANCHOR = "    def is_ceiling_reached(self) -> bool:\n        return self.spent_dispatches >= self.ceiling\n"

# N-203's defect exactly: the ceiling read the raw attempt counter, so a
# store-side refusal decided before any gateway contact burned allowance, and
# a campaign could be halted by refusals it did not cause. Distinct from the
# dispatch-vs-unit error this milestone repairs, and the enforcement the
# milestone's own file never reaches.
CEILING_COUNTS_ATTEMPTS = '''\
    def is_ceiling_reached(self) -> bool:
        return self.dispatch_count >= self.ceiling
'''

LOSS_BECOMES_A_SUCCESS_RECEIPT = '''\
    if response is None:
        return _record_model_receipt(
            dsn,
            op.operation_id,
            ReceiptProposal(
                receipt_identity=f"gw:{op.operation_id}:success",
                content={"operation_id": op.operation_id,
                         "response_class": "success",
                         "response_received": True,
                         "error": loss_detail},
                outcome="success",
                provenance="gateway",
            ),
            True,
        )
'''
LOSS_ANCHOR = '''\
    if response is None:
        return _record_model_receipt(
            dsn,
            op.operation_id,
            ReceiptProposal(
                receipt_identity=f"gw:{op.operation_id}:lost-response",
                content={"operation_id": op.operation_id,
                         "response_class": "lost-response",
                         "response_received": False,
                         "error": loss_detail},
                outcome="unknown",
                provenance="gateway",
            ),
            True,
        )
'''

FABRICATED_LOSS_ACCEPTED = '''\
    if (receipt.get("response_class") == "lost-response"
            and receipt.get("outcome") == "unresolved"):
        return True
    return (
        receipt.get("outcome") == "unresolved"
'''
FABRICATED_LOSS_ANCHOR = '''\
    return (
        receipt.get("outcome") == "unresolved"
'''


CHECKS: tuple[Check, ...] = (
    Check(
        key="null_versus_zero_billing",
        requirement="a missing provider report is not a measured zero, and a "
                    "reported zero stays a reported zero",
        where="m1",
        tests=("test_a_settled_receipt_with_no_charge_field_reads_as_not_reported",
               "test_a_reported_zero_and_an_unreported_charge_are_different_states",
               "test_no_committed_receipt_is_unmeasured_rather_than_not_reported",
               "test_a_reported_charge_cannot_be_constructed_without_its_amount"),
        mutation_name="null_charge_reported_as_zero",
        mutation=NULL_RETURNS_ZERO,
        anchor=NULL_ANCHOR,
        note="the `int(charge or 0)` collapse, reinstated at the receipt "
             "reader where the zero was born",
    ),
    Check(
        key="request_dependent_reservation_estimates",
        requirement="the reservation is sized from the real request bounds, "
                    "not a stand-in per-dispatch constant",
        where="m1",
        tests=("test_two_different_output_allowances_reserve_differently",
               "test_a_campaign_is_sized_by_its_own_request_bounds",
               "test_the_estimate_matches_the_broker_schedule_exactly",
               "test_the_broker_schedule_reproduces_the_reservation_r4_actually_held"),
        mutation_name="reservation_priced_at_a_fixed_25_units",
        mutation=RESERVATION_USES_A_CONSTANT,
        anchor=RESERVATION_ANCHOR,
        note="the fixed 25-unit smoke estimate named in the brief, "
             "reinstated over the broker's own exposure schedule",
    ),
    Check(
        key="dimensional_separation",
        requirement="dispatch counts and reservation units cannot be added to "
                    "one another",
        where="m1",
        tests=("test_subtracting_reservation_units_from_a_dispatch_allowance_is_impossible",
               "test_dispatches_and_reservation_units_are_different_types",
               "test_a_dispatch_allowance_answers_dispatches_only",
               "test_the_module_exposes_no_ceiling_minus_carry_headroom"),
        mutation_name="dispatch_allowance_gains_a_unit_ceiling_field",
        mutation=ALLOWANCE_EXPOSES_A_UNIT,
        anchor=ALLOWANCE_ANCHOR,
        note="a single unit-bearing field on the dispatch type is the whole "
             "dimensional error, so the field alone must turn the test red",
    ),
    Check(
        key="durable_resume_consumes_remaining_count_only",
        requirement="a resume reads the remaining dispatch count and no unit "
                    "figure reaches it",
        where="m1",
        tests=("test_resume_spends_dispatches_and_never_looks_at_units",
               "test_no_unit_figure_reaches_the_resume_path",
               "test_a_new_campaign_gets_a_finite_allowance_while_the_holds_stand"),
        mutation_name="resume_reports_negative_remaining_instead_of_refusing",
        mutation=RESUME_GOES_NEGATIVE,
        anchor=RESUME_ANCHOR,
        note="the resume path has no unit to read, so the mutation inverts the "
             "one thing it can get wrong: a negative remainder for an "
             "over-limit count",
    ),
    Check(
        key="old_uncertain_holds_survive",
        requirement="the 5563 held units keep their grant, root and uncertain "
                    "state, and are never released or settled",
        where="m1",
        tests=("test_the_prior_exposure_is_still_5563_in_the_same_terms",
               "test_each_held_unit_carries_its_grant_and_study_root",
               "test_the_holds_are_counted_once_and_never_released_or_settled",
               "test_the_older_hold_honors_the_reconciliation_agrees_flag"),
        mutation_name="every_study_contributes_regardless_of_settlement",
        mutation=HOLDS_ARE_ALWAYS_COUNTED,
        anchor=HOLDS_ANCHOR,
        note="dropping the unsettled filter releases the settled studies "
             "without touching a single held row, which is the settlement the "
             "brief forbids",
    ),
    Check(
        key="finite_new_allowance_launches_without_settling_holds",
        requirement="a new campaign launches on its own finite allowance with "
                    "the old holds untouched",
        where="m1",
        tests=("test_a_new_campaign_gets_a_finite_allowance_while_the_holds_stand",
               "test_launching_a_new_campaign_needs_no_settlement_of_the_old_holds",
               "test_a_launch_plan_refuses_when_the_reservation_cannot_be_sized",
               "test_a_launch_plan_refuses_a_dispatch_allowance_with_no_frozen_count"),
        mutation_name=None,
        note="Not mutated, and the reason is recorded rather than hidden. The "
             "mapped test takes a before/after reading of the same computed "
             "prior, so it can only detect a caller that mutates that object. "
             "Nothing in the production call path does. The check is "
             "self-certifying by construction and would need a process-level "
             "or persistent-store test to be falsifiable; that is a real "
             "limitation of this check, not a claim that it holds.",
    ),
    Check(
        key="launches_cannot_exceed_the_allowance",
        requirement="no launch may exceed the frozen dispatch count",
        where="dispatch_ceiling + m1",
        tests=("test_ceiling_refusal_never_reaches_the_delegate",
               "test_already_spent_opens_as_a_spent_count_not_an_attempt_count",
               "test_a_store_refusal_does_not_burn_the_ceiling",
               "test_a_spent_count_beyond_the_allowance_refuses_rather_than_going_negative"),
        mutation_name="ceiling_counts_attempts_not_durable_sends",
        mutation=CEILING_COUNTS_ATTEMPTS,
        anchor=CEILING_ANCHOR,
        note="M1's own file reaches this check only arithmetically, through "
             "the resume reading. The enforcement is `LiveGuard.infer` in "
             "live_construct.py, pinned by the N-203 file, so the mutation "
             "sits there rather than in the ledger",
    ),
    Check(
        key="unsuccessful_response_is_an_attributable_attempted_effect",
        requirement="an unsuccessful response is an attempt attributable to "
                    "one operation; a transport loss stays uncertain and must "
                    "not become a fabricated response receipt",
        where="broker_dispatch + bundle_authority + offline_recompute",
        tests=("test_model_lost_response_stays_unresolved",
               "test_lost_response_retains_exposure_and_blocks_resend",
               "test_output_honest_lost_response_has_no_receipt_contract_problem",
               "test_output_failed_outcome_cannot_claim_lost_response"),
        mutation_name="transport_loss_admitted_as_a_success_receipt",
        mutation=LOSS_BECOMES_A_SUCCESS_RECEIPT,
        anchor=LOSS_ANCHOR,
        note="the brief's own sentence, taken literally: the loss is turned "
             "into a success receipt for the same operation, and the "
             "operation is still attributable to it, so only the fabricated "
             "receipt can catch it. The mirror mutation in the verifier, "
             "which would accept any receipt merely claiming an unresolved "
             "outcome, is reported as `second_mutation` below",
    ),
)

SECOND_MUTATION = Check(
    key="unsuccessful_response_is_an_attributable_attempted_effect",
    requirement="the verifier must reject a receipt that merely claims an "
                "unresolved outcome",
    where="offline_recompute + bundle_authority",
    tests=("test_output_failed_outcome_cannot_claim_lost_response",
           "test_malformed_lost_response_marker_still_fails"),
    mutation_name="verifier_accepts_any_unresolved_claim",
    mutation=FABRICATED_LOSS_ACCEPTED,
    anchor=FABRICATED_LOSS_ANCHOR,
    note="the read side of the same check: `_is_lost_response_receipt` is the "
         "only thing separating a proven loss from an asserted one",
)


# --- running --------------------------------------------------------------

STATUS_RUN = re.compile(r"^[.sxXFE]+", re.MULTILINE)
DROPPED = re.compile(r"S09ISO: dropped (\d+) database")
FAILED_NODE = re.compile(r"^FAILED (\S+)", re.MULTILINE)
COLLECT_ERROR = re.compile(r"^ERROR (\S+)", re.MULTILINE)


class RunFailure(RuntimeError):
    pass


def venv_python() -> str:
    candidate = REPO_ROOT / ".venv/bin/python"
    if not candidate.exists():
        raise RunFailure("no .venv in this checkout; the gate needs one")
    return str(candidate)


def count_tally(text: str) -> dict[str, int]:
    """Count the status characters, not a summary regex.

    pytest's `-q` summary omits zero-valued categories, so `3 passed, 2
    failed` carries no `errors` key at all, and a skip is only ever visible in
    the character stream. The run is anchored to the leading row of status
    characters so a letter inside a test name is never counted.
    """
    runs = STATUS_RUN.findall(text)
    line = runs[0] if runs else ""
    return {"passed": line.count("."),
            "failed": line.count("F"),
            "errors": line.count("E"),
            "skipped": line.count("s") + line.count("x"),
            "xfailed": line.count("X")}


def run_pytest(root: Path, files: Sequence[str]) -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root), str(root / "src"), str(root / "tests")])
    completed = subprocess.run(
        [venv_python(), "-m", "pytest", *files, *PYTEST_ARGS],
        cwd=str(root), env=env, capture_output=True, text=True, timeout=1800)
    combined = completed.stdout + completed.stderr
    tally = count_tally(combined)
    if not any(tally.values()):
        raise RunFailure("pytest reported no status characters:\n%s" % combined)
    dropped = DROPPED.search(combined)
    return {
        "exit_code": completed.returncode,
        "result": tally,
        "failed_node_ids": sorted(set(FAILED_NODE.findall(combined))),
        "collection_errors": sorted(set(COLLECT_ERROR.findall(combined))),
        "databases_dropped": int(dropped.group(1)) if dropped else 0,
    }


# --- the mutation sandbox -------------------------------------------------


SKIP_TOP_LEVEL = frozenset({".git", ".venv", "node_modules", "docs", "reviews",
                            "static", "templates", "__pycache__", ".pytest_cache"})


def build_sandbox(destination: Path) -> None:
    """Copy the whole checkout, not a hand-picked subset.

    A hand-picked subset is how the first version of this harness went wrong:
    it copied `reports` but not the root-level `evidence_*` directories, so
    the ledger read the route's price as absent and every mutation was
    really measuring that. A missing directory fails as a collection error,
    which is now reported as one rather than as a red test.
    """
    destination.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    for source in sorted(REPO_ROOT.iterdir()):
        if source.name in SKIP_TOP_LEVEL or source.name.startswith("."):
            continue
        if source.is_dir():
            shutil.copytree(source, destination / source.name, symlinks=True,
                            ignore=ignore)
        else:
            shutil.copy2(source, destination / source.name)


def node_name(node_id: str) -> str:
    """The test's own name, with any pytest parametrize suffix removed.

    A parametrised node id ends in `[receipt_updates3]`, which is a case
    index rather than a name, so matching it against the test function would
    never find the mapping and a genuinely red test would read as silent.
    """
    return node_id.rsplit("::", 1)[-1].split("[", 1)[0]


MUTATION_TARGETS = {
    "dispatch_allowance_gains_a_unit_ceiling_field": LEDGER,
    "null_charge_reported_as_zero": LEDGER,
    "reservation_priced_at_a_fixed_25_units": LEDGER,
    "every_study_contributes_regardless_of_settlement": LEDGER,
    "resume_reports_negative_remaining_instead_of_refusing": LEDGER,
    "ceiling_counts_attempts_not_durable_sends": LIVE,
    "transport_loss_admitted_as_a_success_receipt": BROKER,
    "verifier_accepts_any_unresolved_claim": RECOMPUTE,
}


def gate_files(check: Check) -> list[str]:
    return sorted({GATE_FILES[part] for part in check.where.split(" + ")})


def mutation_target(check: Check) -> str:
    return MUTATION_TARGETS[check.mutation_name]


def run_mutation(check: Check) -> dict[str, Any]:
    if not check.mutation or not check.anchor:
        raise RunFailure("check %s has no mutation to run" % check.key)
    relative = mutation_target(check)
    with tempfile.TemporaryDirectory(prefix="m1behaviour-") as scratch:
        sandbox = Path(scratch) / "tree"
        build_sandbox(sandbox)
        target = sandbox / relative
        source = target.read_text()
        if check.anchor not in source:
            return {"mutation": check.mutation_name, "applied": False,
                    "file": relative,
                    "detail": "anchor text absent from %s at this tip; the "
                              "mutation needs re-deriving" % relative,
                    "red_tests": [], "red_node_ids": []}
        target.write_text(source.replace(check.anchor, check.mutation, 1))
        run = run_pytest(sandbox, gate_files(check))
        if run["collection_errors"]:
            return {
                "mutation": check.mutation_name,
                "applied": True,
                "file": relative,
                "detail": "the mutation did not import; the sandbox broke "
                          "instead of the behaviour",
                "red_tests": [],
                "red_node_ids": list(run["collection_errors"]),
            }
        return {
            "mutation": check.mutation_name,
            "applied": True,
            "file": relative,
            "red_tests": sorted({node_name(node)
                                 for node in run["failed_node_ids"]}),
            "red_node_ids": list(run["failed_node_ids"]),
            "result": run["result"],
        }


# --- artifact -------------------------------------------------------------


def digest(relative: str) -> str:
    return hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()


def source_tip() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                          capture_output=True, text=True,
                          check=True).stdout.strip()


def verdict(check: Check, outcome: dict[str, Any]) -> str:
    if not outcome["applied"]:
        return "not_applied: " + outcome["detail"]
    if not outcome["red_tests"]:
        return ("mutation_silent: the defect was reinstated and no test fired. "
                "A check that cannot fail is not a check")
    hit = [name for name in check.tests
           if name in outcome["red_tests"]]
    if hit:
        return ("proven: %d mapped test(s) turned red under the reinstated "
                "defect" % len(hit))
    return ("mutation_silent_for_this_check: %d test(s) turned red but none is "
            "mapped to it" % len(outcome["red_tests"]))


def build() -> dict[str, Any]:
    by_name = {name: run_pytest(REPO_ROOT, [path])
               for name, path in sorted(GATE_FILES.items())}
    for name, run in by_name.items():
        tally = run["result"]
        if tally["skipped"] or tally["xfailed"] or tally["errors"]:
            raise RunFailure(
                "%s has a skip, xfail or collection error, and none of those "
                "is a pass: %s" % (name, tally))
    baseline = {GATE_FILES[name]: run for name, run in by_name.items()}

    mutations = {check.key: run_mutation(check) for check in CHECKS
                 if check.mutation}
    second = run_mutation(SECOND_MUTATION)

    checks: list[dict[str, Any]] = []
    for check in CHECKS:
        covered = gate_files(check)
        failing = sorted(
            {node_name(node) for path in covered
             for node in baseline[path]["failed_node_ids"]} & set(check.tests))
        entry: dict[str, Any] = {
            "check": check.key,
            "status": "FAIL" if failing else "PASS",
            "requirement": check.requirement,
            "covered_by": covered,
            "tests": list(check.tests),
            "note": check.note,
        }
        if failing:
            entry["failing_tests"] = failing
        mutation = mutations.get(check.key)
        if mutation is not None:
            entry["can_fail"] = dict(mutation, proves=verdict(check, mutation))
        else:
            entry["can_fail"] = {
                "mutation": None, "applied": False, "red_tests": [],
                "red_node_ids": [],
                "proves": "not exercised: see the note on this check",
            }
        checks.append(entry)

    checks[-1]["can_fail"]["second_mutation"] = dict(
        second, proves=verdict(SECOND_MUTATION, second))

    combined = {name: dict(run["result"]) for name, run in by_name.items()}
    totals = {key: sum(counts[key] for counts in combined.values())
              for key in ("passed", "failed", "errors", "skipped", "xfailed")}
    dropped = sum(run["databases_dropped"] for run in by_name.values())

    return {
        "command": "; ".join(pytest_command([path])
                             for path in sorted(set(GATE_FILES.values()))),
        "commit": source_tip(),
        "database_note": (
            "S09ISO dropped %d disposable database(s) across these %d runs. "
            "Each run builds its own plan in pytest_configure before the test "
            "modules import, so no name is shared between them and none is "
            "handwritten here. The mutation runs execute inside a temp copy of "
            "the tree, whose tests/conftest_isolation.py resolves its repo "
            "root under /tmp, so they cannot reach a shared ec02test_* store "
            "either." % (dropped, len(GATE_FILES))),
        "exposure_added": 0,
        "live_dispatches": 0,
        "checks": checks,
        "file_digests": {relative: digest(relative) for relative in DIGEST_FILES},
        "note": (
            "The eight checks are the eight required behaviour checks at "
            "WORKER-STAGE-09-CONNECTED-STUDY.md:43. `tests` names the "
            "committed test that pins each; `covered_by` names which of the "
            "%d gate files hold it. The milestone file "
            "test_s09cs01_budget_denominations.py covers six of the eight. "
            "Check 7 is enforced by LiveGuard.infer in live_construct.py and "
            "pinned by test_s09_n203_dispatch_ceiling.py, and check 8 lives in "
            "the broker and the bundle verifier, neither of which the "
            "milestone file reaches. `can_fail.red_tests` is what a "
            "deliberately reinstated defect actually turned red, measured in a "
            "throwaway copy; the checkout is never mutated. A check whose "
            "`proves` reads mutation_silent is reported, not smoothed over. No "
            "wall-clock figure is recorded, so a re-run diffs clean."
            % len(GATE_FILES)),
        "per_file_runs": {name: {
            "file": GATE_FILES[name],
            "command": pytest_command([GATE_FILES[name]]),
            "exit_code": run["exit_code"],
            **run["result"],
        } for name, run in by_name.items()},
        "result": totals,
        "schema": "inv-r1-m1-behaviour-gate-v1",
    }


def render(artifact: dict[str, Any]) -> str:
    return json.dumps(artifact, indent=1, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    rendered = render(build())
    if arguments == ["--check"]:
        existing = ARTIFACT.read_text() if ARTIFACT.exists() else ""
        if existing == rendered:
            print("gate-results.json reproduced byte for byte")
            return 0
        recorded = json.loads(existing).get("commit") if existing else None
        print("MISMATCH against the committed artifact"
              + ("\n  the artifact records commit %s but HEAD is %s; a lane "
                 "landed after this run, so re-generate at the new tip"
                 % (recorded, source_tip()) if recorded != source_tip()
                 else "\n  HEAD has not moved, so a value in the run is not "
                      "deterministic and the artifact is not reproducible"))
        return 1
    if arguments:
        print("usage: m1_behaviour_gate.py [--check]")
        return 2
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(rendered)
    print("wrote %s" % ARTIFACT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
