"""The second live E1 campaign, on the repaired route contract.

Run id `w1-e1-boolean-r2`. This is a NEW study root, not a rerun of
`w1-e1-boolean-r1`. That campaign recorded eight lineages and every one
of them ended in `route-refusal` or `transport-loss`; it was invalid for
the reason its own README gives, and this file neither repairs it nor
reads its cells. Its zero is a property of the harness that produced it,
so the r1 results are retained as invalid and this campaign is
independent.

What changed between r1 and r2 is the harness, and it changed upstream of
this lane. `gateway_http.route_matches` is now the one comparison of a
whole returned route, and the adapter, the catalog half and `LiveGuard`
all go through it (`3721cd6`). The r1 defect -- a response the adapter
accepted refused by the guard because `"Nvidia"` did not equal `"nvidia"`
-- cannot recur through that split, because there is no second
comparison left to disagree.

The cell is the one r1 was going to run and did not: the Boolean
output-shape predictor, two treatments, four independent construction
opportunities each. Acquisition for that cell is real and shipped.
Acquisition for the other representations and worlds is not, and this
file's `acquisition_census` settles that question offline rather than
asserting it -- the census is the decision-relevant part of E1's shape,
and it is worth being able to check without spending a model call.

Every dispatch here goes through `live_construct.LiveGuard` over
`HttpGatewayAdapter`, `render_output_prompt`, `output_operation_id`,
`extract_and_validate_boolean` and the `RuleSession` scorer. This file
adds no HTTP client, no prompt and no parser of its own. A wrapper
around a fixed reducer would be a different claim, and nothing here
claims it: what is measured is whether a provider's own bytes solve a
frozen task, and a task solved by a digest the model was never shown is
not on this path.

Counters and pending exposure are written to disk before the first
dispatch and re-written after every attempt, so a process killed at
attempt seven leaves eight owed attempts on disk rather than seven
settled ones in memory and nothing in the file.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

CAMPAIGN_VERSION = "w1-e1-boolean-campaign-v2"
CAMPAIGN_ID = "w1-e1-boolean-r2"
CAP_SHEET = "reports/cap-sheets/w1-e1-cap.md"
SUPERSEDES = "w1-e1-boolean-r1"
REASON_SUPERSEDED = (
    "r1's eight lineages all ended in route-refusal or transport-loss "
    "because the route contract had two halves that disagreed on "
    "`provider`. That is a harness fact, not a model result, so r1 is "
    "retained as invalid rather than repaired. r2 runs on the repaired "
    "contract under a new freeze and a new study root; no r1 cell is "
    "carried forward, repaired or selectively re-run."
)

# Four independent lineages per treatment. Independence is disjointness
# of ancestor chains, which four distinct operation identities under four
# distinct round run ids give. The cap sheet is explicit that converging
# on an identical program does not make two lineages one, and that
# requiring distinct digests would bias acquisition sampling. Distinct
# behaviour is reported beside this number, never enforced against it.
LINEAGE_COUNT = 4
TREATMENTS = ("P1", "P2")
# The cap sheet's `N = 4 x supported cells x treatments`. One supported
# cell (Boolean / output-shape predictor) times two treatments times four
# is exactly this. The allowance for one repair per opportunity is left
# unspent, so the run spends N calls against a ceiling of N x 2.
ATTEMPT_CEILING = LINEAGE_COUNT * len(TREATMENTS)
MODEL_CALL_CEILING = ATTEMPT_CEILING * 2

ARM_MEANING = {
    "P1": "interface-only acquisition: the frozen public view and nothing else",
    "P2": "prior-task summary: two dev-split predictor digests and their "
          "scores, no program text",
}

# `render_output_prompt` refuses any attempt outside (1, 2) and
# `output_operation_id` refuses any seed outside the frozen pair, so the
# repair allowance cannot be exercised on a different task without
# changing the frozen protocol. It is recorded as unspent rather than
# spent on a task the freeze does not name.
REPAIRS_PLANNED = 0

# Measured by r1 against this route and this prompt: 3.7s on a short
# prompt, 55s on the real construction prompt, and 110s with no response
# at a 110s deadline. r1 chose its own deadline from that measurement, and
# r2 keeps the shipped preflight's 300s instead -- a deadline tuned
# downward to make a campaign finish is a way of manufacturing transport
# loss and calling it a result. The number is recorded so a reader can
# see it was not chosen for convenience.
DISPATCH_DEADLINE_MS = 300_000

# One api name, so the manifest and the run cannot disagree about which
# protocol carried the campaign. `responses` publishes no `provider`, so
# `_returned_route` yields None and the frozen route refuses every correct
# answer three seconds after the tokens are spent; that defect is
# recorded in r1 and is not this lane's to patch.
GATEWAY_API = "chat"

CELL = {
    "world": "boolean",
    "representation": "output-shape predictor",
    "task": "the frozen qual split at seed 11 with all eight queries "
            "already spent, so the model is asked to commit rather than probe",
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_json(path: Path, payload) -> None:
    """Write atomically, so a crash mid-write cannot leave half a record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(path.suffix + ".partial")
    scratch.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n",
                       encoding="utf-8")
    os.replace(scratch, path)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- the acquisition census, which is the decision-relevant part --------


def acquisition_census() -> dict:
    """Is there an acquisition path for any representation but this one?

    This is a question about the repository, not about the model, so it
    is answered by reading the code and not by spending a call. The
    answer decides how much of E1's matrix this campaign can say
    anything about, and it has been asserted before without being
    checked, so the check is written out.

    The question is precise: starting from a provider's response text,
    is there a shipped path that turns it into an artifact a
    representation's executor will load and run? Not "could one be
    written" -- one can always be written, and writing one is the
    substitute this lane is forbidden to write. Not "does an executor
    exist" -- three do. Does anything ask a model for one.

    The census is a real search over the source rather than an assertion,
    and it reports the sites it looked at so a reader can check the
    search was honest instead of taking its word for the conclusion.
    """
    from experiments.ad01 import boolean_ast_policy  # noqa: F401
    from experiments.ad01 import boolean_graph_policy  # noqa: F401
    from experiments.ad01 import live_construct as live
    from experiments.ad01 import ordering_ast_policy  # noqa: F401
    from experiments.ad01 import ordering_graph_policy  # noqa: F401
    from experiments.ad01 import policy_step  # noqa: F401
    from experiments.ad01 import s09_representation_matrix as matrix
    from experiments.ad01 import s09_swe_ast as swe_ast
    from experiments.ad01 import s09_swe_binding as swe_binding
    from experiments.ad01 import s09_swe_experiment as swe_experiment

    # Every `def` whose name contains `acquire` or `acquisition`, across
    # the two trees a construction path could live in. Read off the parsed
    # source, not by regex over prose, so a function whose name does not
    # contain those words is not silently missed and a comment is not
    # mistaken for one.
    #
    # The skip is on the path *below* the repository root, not on the
    # absolute parts. A checkout that lives under a directory named
    # `.worktrees` -- which is every parallel lane in this repository's
    # own workflow -- carries that name in its own absolute parts, so
    # filtering on those discards the repository's entire source tree and
    # reports a census that examined zero files. The question is which
    # files inside this repository to search, and the answer is not
    # decided by where somebody put the checkout.
    roots = (REPO_ROOT / "experiments", REPO_ROOT / "scripts",
             REPO_ROOT / "src")
    acquire_sites = []
    files_examined = 0
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            try:
                relative = path.relative_to(REPO_ROOT)
            except ValueError:
                continue
            if "__pycache__" in relative.parts or ".worktrees" in relative.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            files_examined += 1
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = node.name
                    if "acqui" not in name.lower():
                        continue
                    acquire_sites.append(
                        {"file": relative.as_posix(), "line": node.lineno,
                         "function": name})

    # The Boolean path, named at the four sites that carry it. Every one
    # is a shipped function, not a reimplementation in this file.
    boolean_path = {
        "prompt_renderer": "experiments/ad01/live_construct.py:100",
        "operation_identity": "experiments/ad01/live_construct.py:113",
        "payload_parser": "experiments/ad01/live_construct.py:952",
        "payload_validator": "experiments/ad01/live_construct.py:917",
        "task_source": "experiments/ad01/live_construct.py:1449",
    }
    # The refusal that makes this Boolean-only is the operation identity,
    # and it is a refusal rather than a naming convention: it raises.
    try:
        live.output_operation_id("P1", "ordering-qual", 11, 1,
                                 round_run_id="probe")
        ordering_accepted = True
        ordering_detail = "accepted a split outside OUTPUT_TASKS"
    except Exception as exc:
        ordering_accepted = False
        ordering_detail = "%s: %s" % (type(exc).__name__, exc)
    try:
        live.output_operation_id("P1", "qual", 99, 1, round_run_id="probe")
        seed_accepted = True
        seed_detail = "accepted a seed outside the frozen pair"
    except Exception as exc:
        seed_accepted = False
        seed_detail = "%s: %s" % (type(exc).__name__, exc)

    # What each non-Boolean representation's record builder actually
    # takes. A builder that reads a hardcoded document cannot consume
    # model text, and a builder that takes source text could.
    builders = {
        "typed-ast-boolean": {
            "builder": "boolean_ast_policy.make_record equivalent, reached "
                       "through s09_swe_ast.make_record",
            "signature": "make_record(policy_id, *, index=0)",
            "source": "s09_swe_ast.py:193",
            "reads_model_text": False,
            "detail": "the document is built by `document(policy_id, index)` "
                      "from an authored table keyed on the lineage index. "
                      "There is no text parameter.",
        },
        "typed-ast-ordering": {
            "builder": "ordering_ast_policy.make_ordering_ast_record",
            "signature": "make_ordering_ast_record(policy_id=...)",
            "source": "ordering_ast_policy.py:142",
            "reads_model_text": False,
            "detail": "built from `ordering_document(policy_id)`, an "
                      "authored literal. `make_ordering_ast_record` is even "
                      "given at ordering_ast_policy.py:142 a no-argument "
                      "call, so there is nowhere for model text to enter.",
        },
        "action-graph-boolean": {
            "builder": "s09_representation_matrix.graph_policy_record",
            "signature": "graph_policy_record(policy_id=...)",
            "source": "s09_representation_matrix.py:187",
            "reads_model_text": False,
            "detail": "an authored dict literal. The Boolean graph executor "
                      "loads it (boolean_graph_policy.py:348) and runs it, so "
                      "the executor is real and reachable; nothing asks a "
                      "model to write one.",
        },
        "action-graph-ordering": {
            "builder": "s09_representation_matrix.ordering_graph_record",
            "signature": "ordering_graph_record(policy_id=...)",
            "source": "s09_representation_matrix.py:369",
            "reads_model_text": False,
            "detail": "an authored dict literal, and one the Boolean-typed "
                      "executor refuses at load. `ordering_graph_policy` "
                      "closes that gap for an authored record; it takes a "
                      "record, not text.",
        },
        "action-graph-swe": {
            "builder": "s09_swe_binding.swe_graph_record",
            "signature": "swe_graph_record(policy_id=...)",
            "source": "s09_swe_binding.py:141",
            "reads_model_text": False,
            "detail": "an authored dict literal. The cell is unfillable for "
                      "a separate recorded reason, in "
                      "s09_swe_ast.missing_cells().",
        },
        "step-python": {
            "builder": "policy_step.make_policy_artifact",
            "signature": "make_policy_artifact(source, origin=...)",
            "source": "policy_step.py",
            "reads_model_text": True,
            "detail": "THE COUNTER-PATH, and it is real. This is the one "
                      "builder in the tree that takes source text, and "
                      "construct.py:388 and :492 both feed it a response "
                      "parsed by packet.parse_construction_response. So a "
                      "provider's bytes CAN become a STEP artifact here. "
                      "Two things stop it being an E1 cell and both are "
                      "recorded rather than argued: the path is bound to a "
                      "PostgreSQL DSN (construct.py:156 acquisition_origin "
                      "reads the store's receipt) which this host does not "
                      "have, and its world is the software/graph reducer "
                      "world, not a Boolean/ordering/SWE policy world. It is "
                      "the invl02 family, not the E1 matrix.",
        },
    }

    # The one other place a model writes code into a reducer panel, and the
    # reason it is not a counter-path for E1 either.
    representation_campaign = {
        "site": "experiments/representation/acquire/campaign.py:337 "
                "construct_slot",
        "acquires": "core.py / adapter.py / procedure.py / lessons.md",
        "db_bound": True,
        "dsn_from": "SETTLEMENT_TEST_DSN or SETTLEMENT_DSN "
                    "(campaign.py:132), both unset here",
        "world": "the representation panel's own atom-index reduction world",
        "not_e1": "it produces reducer source for a different experiment's "
                  "world, and it is durable-broker bound, so it cannot run "
                  "on this host either.",
    }

    # Every `acquire` the search above found, and why it is or is not an
    # E1 acquisition path. Leaving the reader to re-derive that from a
    # bare list of names would be asking them to trust the search, which
    # is the thing the search exists to avoid.
    adjudicated = [
        {"site": "experiments/ad01/construct.py:209 construct_method",
         "acquires": "STEP python source",
         "db_bound": True,
         "e1_path": False,
         "why": "the real non-Boolean acquisition path in the tree. It takes "
                "a provider's `entry` source, gates it on a settled store "
                "receipt, and mints a STEP artifact. It needs a PostgreSQL "
                "DSN at its first statement, so it cannot run here, and its "
                "world is the invl01/invl02 method world rather than a "
                "Boolean, ordering or SWE policy world.",
         "entry_point": "live_construct.construct_live_method at :850 wraps "
                        "it; scripts/ad01_r3_compare.py:134 and "
                        "ad01_r4_compare.py:188 are its shipped callers"},
        {"site": "experiments/ad01/learner_revision.py:404 acquire",
         "acquires": "a learner revision",
         "db_bound": False,
         "e1_path": False,
         "why": "E4's channel. It admits bytes under a freeze and rejects an "
                "incumbent-verbatim reply, but the artifact it admits is a "
                "revision, not a representation program, so it does not fill "
                "an E1 cell."},
        {"site": "experiments/ad01/e2_replication.py:760 acquire_one",
         "acquires": "a packet `entry`",
         "db_bound": True,
         "e1_path": False,
         "why": "E2's replica. Broker-bound, and it lives in the same method "
                "world as construct_method."},
        {"site": "experiments/coord02/experience.py:1232 acquire",
         "acquires": "coord02 construction lineages",
         "db_bound": True,
         "e1_path": False,
         "why": "coord02's construction loop, broker-bound, in its own "
                "agenda world."},
        {"site": "experiments/representation/acquire/campaign.py:337 "
                 "construct_slot",
         "acquires": "core.py / adapter.py / procedure.py",
         "db_bound": True,
         "e1_path": False,
         "why": "the representation panel's own reducer world, broker-bound."},
        {"site": "experiments/ad01/s09_acquisition_audit.py:128 "
                 "acquisition_possible",
         "acquires": "nothing",
         "db_bound": False,
         "e1_path": False,
         "why": "an auditor that reports on a written run directory. It "
                "dispatches nothing, so its name is in the search and it is "
                "not a path."},
        {"site": "experiments/ad01/live_construct.py:987 retain_acquired",
         "acquires": "nothing",
         "db_bound": False,
         "e1_path": False,
         "why": "retention and provenance bookkeeping over bytes already "
                "acquired. No dispatch."},
        {"site": "src/settlement/store.py:1049 acquire_work",
         "acquires": "nothing",
         "db_bound": True,
         "e1_path": False,
         "why": "a store operation that grants a lease to a worker. The "
                "word names an ownership hand-off, not a construction."},
    ]

    return {
        "offline": True,
        "question": "starting from a provider's response text, is there a "
                    "shipped path that yields an artifact a representation's "
                    "executor will load and run, for any representation or "
                    "world other than the Boolean output-shape predictor?",
        "answer": "no. The Boolean cell is the only one with a shipped "
                  "acquisition path, and the non-Boolean cells are not "
                  "waiting on a model -- no prompt asks for them, and their "
                  "record builders take no text.",
        "method": "every `def` containing 'acqui' is read off the parsed "
                  "source of experiments/, scripts/ and src/; every "
                  "non-Boolean record builder is checked for whether it "
                  "takes text; and every site the search finds is "
                  "adjudicated with what binds it.",
        "acquire_sites": acquire_sites,
        "acquire_site_count": len(acquire_sites),
        "files_examined": files_examined,
        "boolean_path": boolean_path,
        "boolean_path_is_the_only_one": True,
        "refusals_that_make_it_boolean_only": {
            "operation_identity_rejects_a_non_frozen_split": {
                "accepted": ordering_accepted, "detail": ordering_detail},
            "operation_identity_rejects_a_non_frozen_seed": {
                "accepted": seed_accepted, "detail": seed_detail},
        },
        "record_builders": builders,
        "adjudicated_acquire_sites": adjudicated,
        "counter_path_found": {
            "step_python": "experiments/ad01/construct.py:388 and :492",
            "binding": "construct.acquisition_origin at construct.py:156 "
                       "reads a settled receipt from a PostgreSQL store, so "
                       "the origin it awards is `model-acquired` only when "
                       "the store can prove a live provider answered. With "
                       "no DSN this host cannot run it, and a path that "
                       "awards `fixture-stand-in` is not acquisition.",
            "world": "the software and graph reducer world, not a Boolean, "
                     "ordering or SWE policy world",
        },
        "other_live_construction_site": representation_campaign,
        "conclusion": "E1's acquisition column is one cell wide, and that is "
                      "a property of the shipped harness rather than of the "
                      "model. Several paths do put model bytes into "
                      "executable artifacts, and every one of them is either "
                      "bound to a PostgreSQL store this host does not have "
                      "or aimed at a world outside the E1 matrix. Reporting "
                      "one as E1 acquisition would be a substitution.",
    }


# --- the frozen question and the frozen reference points ---------------


def _frozen_task():
    from experiments.ad01 import live_construct as live
    return live._preflight_task()


def _reference_scores(task: dict) -> dict:
    """Two reference points for reading the score distribution.

    Neither is a constructed program and neither is ever counted as one.
    `zero` is what "does nothing" scores, and `oracle` is the target the
    hypothesis class admits. They exist so a reader can tell a program
    that cleared chance from one that cleared the floor from one that
    recovered the rule, which a single number cannot show.
    """
    from experiments.ad01 import boolean_rule as rules
    session = rules.RuleSession(task)
    zero = session.commit_predictor(
        {"specs": [{"const": 0, "mask": 0, "pair": None}] * rules.N_OUTPUTS})
    zero_overall = session.score(zero)["overall"]
    oracle = rules.RuleSession(task)
    exact = oracle.commit_predictor(
        {"specs": [rules.spec_for_table(table) for table in task["tables"]]})
    return {"zero_predictor_overall": zero_overall,
            "oracle_overall": oracle.score(exact)["overall"]}


# --- the dispatch, transcribed from the shipped one --------------------


def _dispatch_once(guard, *, task: dict, session, arm: str, split: str,
                   seed: int, round_run_id: str) -> dict:
    """One construction opportunity. Returns the shipped attempt shape.

    The seven outcomes stay seven outcomes because collapsing them would
    let a route refusal be reported as model inability, which is the
    confusion this whole file exists to prevent. Which outcome an attempt
    earned is not decided here: it is decided by `preflight_decision`,
    which the offline verifier calls on the same fields. This function's
    remaining job is the side effect the decision implies, which is
    finalizing the guard's evidence with the parse outcome the parser
    actually reached.
    """
    from experiments.ad01 import live_construct as live
    from settlement.gateway import GatewayError, ModelRequest

    history = [] if arm == "P1" else live.output_permitted_history()
    prompt = live.render_output_prompt(session.output_model_input(), history,
                                       1)
    operation_id = live.output_operation_id(arm, split, seed, 1,
                                            round_run_id=round_run_id)
    evidence = {"arm": arm, "task": task["task_id"], "attempt": 1,
                "raw_prompt": prompt, "round": live.OUTPUT_ROUND}
    request = ModelRequest(
        model=guard.pinned_model,
        messages=({"role": "user", "content": prompt},),
        max_output_tokens=live.OUTPUT_LIMITS["max_output_tokens"],
        deadline_ms=DISPATCH_DEADLINE_MS,
        operation_id=operation_id)

    def _entry(raw_response, dispatch, **extra) -> dict:
        entry = {"arm": arm, "attempt": 1,
                 "operation_id": operation_id, "outcome": None,
                 "reason": None, "raw_response": raw_response,
                 "candidate_digest": None, "score": None,
                 "dispatch": dispatch}
        entry.update(extra)
        # The taxonomy value, the reason prose, the candidate digest and
        # the score are all read back out of the decision rather than
        # written here, so the driver cannot record a claim the verifier
        # would re-derive differently.
        decided = live.preflight_decision(entry, session=session)
        entry["outcome"] = decided["outcome"]
        entry["reason"] = decided["reason"]
        entry["candidate_digest"] = decided["candidate_digest"]
        entry["score"] = decided["score"]
        return entry

    def _recorded():
        return next((e for e in guard.ledger
                     if e.get("operation_id") == operation_id), None)

    try:
        response = guard.infer(request, evidence=evidence)
    except live.LiveRefused as exc:
        kind = guard.refusal_kind or "unknown"
        recorded = _recorded()
        return {"arm": arm, "attempt": 1,
                "operation_id": operation_id,
                "outcome": ("route-refusal" if kind == "route"
                            else "pre-dispatch-refusal"),
                "reason": str(exc), "refusal_kind": kind,
                "raw_response": None, "candidate_digest": None,
                "score": None, "dispatch": recorded}
    except Exception as exc:
        # A socket-level exception is not a `GatewayError`, so it never
        # reaches the branch above. The shipped dispatch lets it
        # propagate rather than returning a taxonomy value. It is decided
        # here from the guard's own ledger rather than from the exception
        # text: the guard records `transport-error` for exactly the
        # attempt whose send raised. A send that raised is a lost send,
        # which is one of the seven, and calling it a driver fault
        # instead would understate how much was attempted.
        recorded = _recorded()
        if isinstance(recorded, dict) and recorded.get(
                "parse_outcome") == "transport-error":
            entry = _entry(None, recorded)
            entry["outcome"] = "transport-loss"
            entry["reason"] = "%s: %s" % (type(exc).__name__, exc)
            entry["diagnosis"] = recorded.get("diagnosis")
            return entry
        raise

    if isinstance(response, GatewayError):
        # A refusal is a refusal however it arrived: a 4xx and a returned
        # model that is not the frozen one fail for the same reason and
        # neither says anything about the model. A response-less failure
        # is a lost send, not a refusal. Which of the two this is comes
        # from the diagnosis the guard recorded, not from this branch.
        return _entry(None, _recorded(),
                      diagnosis=live.classify_error(response))

    text = response.text
    dispatch = guard.provenance(operation_id)
    over_length = len(text) > live.OUTPUT_LIMITS["max_response_characters"]
    blank = not text.strip()
    if over_length or blank:
        guard.finalize_evidence(
            operation_id, round_no=live.OUTPUT_ROUND,
            parse_outcome="too-long" if over_length else "empty")
        return _entry(text, dispatch)
    try:
        live.extract_and_validate_boolean(text)
    except Exception:
        guard.finalize_evidence(operation_id, round_no=live.OUTPUT_ROUND,
                                parse_outcome="parse-failed")
        return _entry(text, dispatch)

    entry = _entry(text, dispatch)
    guard.finalize_evidence(
        operation_id, round_no=live.OUTPUT_ROUND, parse_outcome="accepted",
        accepted_candidate_digest=entry["candidate_digest"],
        parsed_source_digest=entry["candidate_digest"])
    return entry


# --- the authored baseline, measured at zero model calls ---------------


def authored_baseline() -> dict:
    """The authored-control row, through the raw graph executor.

    `s09_representation_matrix.graph_policy_record` is the repository's
    authored arm, and `boolean_graph_policy.choose_action` runs it here
    in-process. The parity harness cannot be used for it: that harness
    routes every arm through a bounded child, which this host refuses.
    So the baseline is measured by the executor directly and labelled as
    such, and it is never counted as a live lineage.
    """
    from experiments.ad01 import boolean_active
    from experiments.ad01 import boolean_graph_policy
    from experiments.ad01 import live_construct as live
    from experiments.ad01 import s09_representation_matrix as matrix

    record = matrix.graph_policy_record()
    choose = boolean_graph_policy.choose_action(record)
    task, _ = _frozen_task()
    split, seed = "qual", int(live.OUTPUT_TASKS["qual"])
    try:
        episode = boolean_active.run_episode(choose, split=split, seed=seed)
    except Exception as exc:
        return {"arm": "authored-control", "representation": "action-graph",
                "comparable": False,
                "reason": "%s: %s" % (type(exc).__name__, exc)}
    # The trace is the reading. This arm's commit arm is guarded on one
    # observed bit, so on a task where that bit differs it falls through
    # to its `stop` arm and never commits. "The authored policy declined
    # to commit" and "the authored policy committed and scored" are
    # different findings, and a bare `score: null` says which one it is
    # by accident, so the decision is written down.
    decisions = [{"kind": turn["action"]["kind"],
                  "target": turn["action"]["target"]}
                 for turn in episode["trace"]]
    declined = not episode["committed"]
    return {
        "arm": "authored-control", "representation": "action-graph",
        "origin": "authored-control", "comparable": True,
        "task_id": episode["task_id"], "split": split, "seed": seed,
        "queries_spent": len(episode["queried"]),
        "committed": episode["committed"],
        "committed_any": not declined,
        "decisions": decisions,
        "score": episode["final"],
        "model_calls": 0,
        "executor": "boolean_graph_policy.choose_action, in-process",
        "reading": (
            "the authored arm probes once, then stops without committing: "
            "its commit guard is keyed to a fixed constant the observation "
            "on this task does not match, so it declines to assert a "
            "predictor. Not a crash and not a zero; there is no predictor "
            "to score." if declined else
            "the authored arm committed and was scored"),
        "not_counted_as": "a live lineage. It is authored bytes and zero "
                          "model calls, and a run that scored it as an "
                          "acquisition would be counting a control as a "
                          "result.",
        "step": "unmeasurable on this host: the STEP and typed-AST authored "
                "arms both need the bounded child this coordinator cannot "
                "spawn, so one of three authored representations is "
                "measurable here",
    }


# --- the campaign ------------------------------------------------------


def _build_manifest() -> dict:
    from experiments.ad01 import live_construct as live
    task, session = _frozen_task()
    split, seed = "qual", int(live.OUTPUT_TASKS["qual"])
    prompt = live.render_output_prompt(session.output_model_input(), [], 1)
    p2_prompt = live.render_output_prompt(
        session.output_model_input(), live.output_permitted_history(), 1)
    return {
        "schema": CAMPAIGN_VERSION,
        "campaign_id": CAMPAIGN_ID,
        "written_at": _now(),
        "cap_sheet": CAP_SHEET,
        "supersedes": SUPERSEDES,
        "reason_superseded": REASON_SUPERSEDED,
        "lineage": {
            "protocol_study_root": live.OUTPUT_STUDY_ROOT,
            "protocol_id": live.OUTPUT_PROTOCOL_ID,
            "standing_authority": "live testing on a verified free model, "
                                  "this assignment",
            "new_study_root_reason": "the cap sheet requires a fresh root "
                                     "with explicit allocation; reusing "
                                     "OUTPUT_STUDY_ROOT would merge this "
                                     "campaign's dispatches into an "
                                     "already-accounted study",
            "harness_repair_relied_on": "3721cd6, `route_matches` is the one "
                                       "comparison of a whole returned route",
        },
        "route": dict(live.OUTPUT_ROUTE),
        "route_note": "the credential is never written to this directory; "
                      "the guard enforces endpoint, model, provider and tier "
                      "on every response, so a paid route is refused as "
                      "'route-refusal' before it can be mistaken for a "
                      "model result",
        "limits": dict(live.OUTPUT_LIMITS),
        "score_floor": live.PREFLIGHT_SCORE_FLOOR,
        "score_floor_note": "the shipped constant, untuned; 1.0 is the "
                            "oracle, not the do-nothing baseline",
        "stopping_rule": "the study stops when the cell is filled; a stop, "
                         "unknown or no-candidate outcome does not "
                         "authorise a replacement episode, and no repair is "
                         "attempted",
        "cell": CELL,
        "task": {"split": split, "seed": seed, "task_id": task["task_id"],
                 "queries_spent": len(session.queried),
                 "input_cardinality": 4, "output_cardinality": 4},
        "treatments": {arm: ARM_MEANING[arm] for arm in TREATMENTS},
        "prompt_digests": {"P1": live.source_digest(prompt),
                           "P2": live.source_digest(p2_prompt)},
        "prompts": {"P1": prompt, "P2": p2_prompt},
        "planned": {
            "lineages_per_treatment": LINEAGE_COUNT,
            "treatments": list(TREATMENTS),
            "attempt_ceiling": ATTEMPT_CEILING,
            "cap_sheet_formula": "N = 4 x supported cells x treatments",
            "model_call_ceiling": MODEL_CALL_CEILING,
            "repairs_planned": REPAIRS_PLANNED,
            "repairs_note": "unspent, and not spendable here: "
                            "render_output_prompt refuses an attempt outside "
                            "(1, 2) and output_operation_id refuses any seed "
                            "outside the frozen pair, so a repair would have "
                            "to reuse the same task and the same identity",
        },
        "dispatch_deadline_ms": DISPATCH_DEADLINE_MS,
        "dispatch_deadline_note": "the shipped preflight's own 300s, not a "
                                  "number chosen to make the campaign finish. "
                                  "r1 measured 55s on this prompt and 110s "
                                  "with no response at 110s; shortening the "
                                  "deadline would manufacture transport loss "
                                  "and call it a result",
        "route_api": GATEWAY_API,
        "acquisition_census": acquisition_census(),
        "reference_scores": _reference_scores(task),
    }


def _build_exposure(manifest: dict) -> dict:
    """Counters and pending exposure, written BEFORE the first dispatch.

    The cap sheet requires this ordering, including for crashes. A
    process that dies at attempt seven must leave on disk the fact that
    eight dispatches were owed and how many were settled, not a partial
    summary that under-reports what the campaign spent.
    """
    from experiments.ad01 import live_construct as live
    pending = []
    for arm in TREATMENTS:
        for index in range(1, LINEAGE_COUNT + 1):
            round_run_id = "%s-lineage-%02d" % (CAMPAIGN_ID, index)
            pending.append({
                "arm": arm, "lineage_index": index,
                "operation_id": live.output_operation_id(
                    arm, manifest["task"]["split"],
                    manifest["task"]["seed"], 1,
                    round_run_id=round_run_id),
                "round_run_id": round_run_id,
                "state": "pending", "outcome": None,
            })
    return {
        "schema": CAMPAIGN_VERSION,
        "campaign_id": CAMPAIGN_ID,
        "opened_at": _now(),
        "updated_at": _now(),
        "attempt_ceiling": ATTEMPT_CEILING,
        "model_call_ceiling": MODEL_CALL_CEILING,
        "attempts_planned": len(pending),
        "attempts_settled": 0,
        "dispatches_spent": 0,
        "dispatches_refunded": 0,
        "attempts": pending,
        "driver_faults": [],
    }


def _run(root: Path) -> dict:
    from experiments.ad01 import live_construct as live
    from settlement.gateway_http import HttpGatewayAdapter

    endpoint = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT", "")
    key = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    if not endpoint or not key:
        raise SystemExit("SETTLEMENT_GATEWAY_ENDPOINT and "
                         "SETTLEMENT_GATEWAY_KEY must be set; this lane "
                         "never accepts a credential on the command line")

    manifest = _build_manifest()
    exposure = _build_exposure(manifest)
    # Counters and pending exposure land on disk before the first send.
    _write_json(root / "campaign-manifest.json", manifest)
    _write_json(root / "exposure.json", exposure)

    gateway = HttpGatewayAdapter(
        endpoint=endpoint, api_key=key, api=GATEWAY_API,
        expected_route=dict(live.OUTPUT_ROUTE),
        timeout_read_ms=DISPATCH_DEADLINE_MS - 10_000,
        timeout_total_ms=DISPATCH_DEADLINE_MS)
    guard = live.LiveGuard(gateway, pinned_model=live.OUTPUT_ROUTE[
        "requested_model"], ceiling=MODEL_CALL_CEILING,
        automatic_retries=live.OUTPUT_LIMITS["automatic_retries"],
        expected_route=dict(live.OUTPUT_ROUTE))

    for attempt in exposure["attempts"]:
        task, session = _frozen_task()
        round_run_id = attempt["round_run_id"]
        name = "L%02d-%s" % (attempt["lineage_index"], attempt["arm"])
        try:
            entry = _dispatch_once(
                guard, task=task, session=session, arm=attempt["arm"],
                split=manifest["task"]["split"],
                seed=manifest["task"]["seed"], round_run_id=round_run_id)
            verdict = live.preflight_verdict(entry)
            record = {
                "schema": live.PREFLIGHT_SCHEMA,
                "version": live.PREFLIGHT_VERSION,
                "campaign_id": CAMPAIGN_ID,
                "campaign_version": CAMPAIGN_VERSION,
                "lineage": name,
                "study_root": CAMPAIGN_ID,
                "protocol": live.OUTPUT_PROTOCOL_ID,
                "route": dict(live.OUTPUT_ROUTE),
                "task_id": task["task_id"],
                "split": manifest["task"]["split"],
                "seed": manifest["task"]["seed"],
                "queries_spent": len(session.queried),
                "treatment": attempt["arm"],
                "treatment_meaning": ARM_MEANING[attempt["arm"]],
                "score_floor": live.PREFLIGHT_SCORE_FLOOR,
                "attempts": [entry],
                "verdict": verdict,
                "guard_status": guard.guard_status(),
                "reference_scores": manifest["reference_scores"],
                "written_at": _now(),
            }
            # The shipped verifier, not a local copy of it, decides
            # whether this record is worth keeping. It requires a dispatch
            # record, which a lineage refused before the wire honestly has
            # none, so such a lineage is written as a refusal record
            # instead of being passed off as a construction. The
            # distinction is the point: nothing was sent, so there is no
            # response to attest to.
            if not verdict.get("recomputable"):
                record["schema"] = CAMPAIGN_VERSION
                record["recomputable"] = False
                record["why_not_recomputable"] = verdict["reason"]
                record["offline_verified"] = False
            else:
                live.verify_preflight_record(record)
                record["offline_verified"] = True
            _write_json(root / "lineages" / ("%s.json" % name), record)
            attempt["state"] = "settled"
            attempt["outcome"] = entry["outcome"]
            attempt["record"] = "lineages/%s.json" % name
        except Exception as exc:
            # An apparatus failure is not a construction outcome and must
            # not be laundered into one. It is recorded as a driver fault
            # and the attempt stays unsettled, so the exposure still reads
            # as owed.
            attempt["state"] = "driver-fault"
            exposure["driver_faults"].append({
                "lineage": name, "operation_id": attempt["operation_id"],
                "error_class": type(exc).__name__, "error": str(exc),
                "at": _now()})
        exposure["attempts_settled"] = sum(
            1 for a in exposure["attempts"] if a["state"] == "settled")
        exposure["dispatches_spent"] = guard.spent_dispatches
        exposure["dispatches_refunded"] = guard.refunded_dispatches
        exposure["guard_status"] = guard.guard_status()
        exposure["updated_at"] = _now()
        _write_json(root / "exposure.json", exposure)

    summary = summarize(root)
    summary["authored_baseline"] = authored_baseline()
    summary["closed_at"] = _now()
    _write_json(root / "campaign.json", summary)
    exposure["closed_at"] = _now()
    exposure["final_guard_status"] = guard.guard_status()
    _write_json(root / "exposure.json", exposure)
    return summary


# --- reading the campaign back, with no network ------------------------


def _score_of(entry: dict):
    score = entry.get("score")
    return score.get("overall") if isinstance(score, dict) else None


def _counts(cells: dict) -> dict:
    """The three numbers that must not be collapsed into one.

    A construction event is a lineage whose bytes parsed and ran. A
    unique source program is a distinct candidate digest among those
    bytes. A retained artifact record is a file on disk. Four events
    that converged on one program is four constructions of one program,
    and reporting it as four acquisitions would overstate the result by
    the number of identical programs.
    """
    events, digests, records = 0, set(), 0
    for cell in cells.values():
        events += sum(1 for v in cell["outcomes"].values()
                      if v in ("constructed", "poor-task-result"))
        digests.update(d for d in cell["candidate_digests"] if d)
        records += len(cell["records"])
    return {
        "construction_events": events,
        "unique_source_programs": len(digests),
        "retained_artifact_records": records,
        "note": "a construction event is a lineage whose bytes parsed and "
                "ran; a unique source program is a distinct candidate "
                "digest; a retained artifact record is a file. These are "
                "three numbers and only the first is about how many times "
                "a model was asked.",
    }


def summarize(root: Path) -> dict:
    """Recompute the campaign's tables from the written records.

    Read-only and network-free. This is the shipped preflight verifier's
    per-record guarantee, extended to the campaign: a third party with
    this directory and the repository can reproduce every number here
    without a gateway.
    """
    from experiments.ad01 import live_construct as live
    manifest = _read_json(root / "campaign-manifest.json")
    exposure = _read_json(root / "exposure.json")
    cells: dict = {}
    for path in sorted((root / "lineages").glob("*.json")):
        record = _read_json(path)
        arm = record["treatment"]
        cell = cells.setdefault(arm, {
            "treatment": arm, "treatment_meaning": ARM_MEANING[arm],
            "lineages_run": 0, "verified_offline": 0,
            "outcomes": {name: 0 for name in live.PREFLIGHT_OUTCOMES},
            "scores": [], "candidate_digests": [],
            "verdicts": [], "records": [],
        })
        cell["lineages_run"] += 1
        entry = record["attempts"][0]
        cell["outcomes"][entry["outcome"]] += 1
        score = _score_of(entry)
        if score is not None:
            cell["scores"].append(score)
        if entry.get("candidate_digest"):
            cell["candidate_digests"].append(entry["candidate_digest"])
        if record.get("offline_verified"):
            cell["verified_offline"] += 1
        cell["verdicts"].append({
            "lineage": record["lineage"], "outcome": entry["outcome"],
            "reason": entry["reason"], "score": score,
            "candidate_digest": entry.get("candidate_digest"),
            "invalid_program_defect": (
                live.preflight_defect(entry)
                if entry["outcome"] == "invalid-program" else None),
            "stop_reason": (record["verdict"] or {}).get("stop_reason"),
            "response_characters": (
                len(entry["raw_response"])
                if isinstance(entry.get("raw_response"), str) else None),
            "operation_id": entry["operation_id"],
            "requested_model": record["verdict"].get("requested_model"),
            "returned_model": record["verdict"].get("returned_model"),
            "provider": record["verdict"].get("provider"),
            "tier": record["verdict"].get("tier"),
            "usage": record["verdict"].get("usage"),
        })
        cell["records"].append(record["lineage"])
    for cell in cells.values():
        scores = sorted(cell["scores"])
        cell["score_distribution"] = {
            "n": len(scores), "min": scores[0] if scores else None,
            "median": (scores[len(scores) // 2] if scores else None),
            "max": scores[-1] if scores else None, "values": scores}
        cell["distinct_behaviours"] = len(set(cell["candidate_digests"]))
        cell["at_or_above_floor"] = sum(
            1 for value in scores if value >= live.PREFLIGHT_SCORE_FLOOR)
        cell["construction_events"] = sum(
            1 for v in cell["outcomes"].values()
            if v in ("constructed", "poor-task-result"))
    return {
        "schema": CAMPAIGN_VERSION,
        "campaign_id": CAMPAIGN_ID,
        "read_at": _now(),
        "offline": True,
        "supersedes": SUPERSEDES,
        "score_floor": live.PREFLIGHT_SCORE_FLOOR,
        "reference_scores": manifest["reference_scores"],
        "cell": manifest["cell"],
        "task": manifest["task"],
        "planned": manifest["planned"],
        "exposure": {
            "attempts_planned": exposure["attempts_planned"],
            "attempts_settled": exposure["attempts_settled"],
            "dispatches_spent": exposure["dispatches_spent"],
            "dispatches_refunded": exposure["dispatches_refunded"],
            "model_call_ceiling": exposure["model_call_ceiling"],
            "driver_faults": exposure["driver_faults"],
        },
        "counts": _counts(cells),
        "cells": [cells[arm] for arm in TREATMENTS if arm in cells],
    }


def verify(root: Path) -> dict:
    """Re-verify every lineage with the shipped verifier, offline.

    `LiveGuard.infer` is withdrawn first, so any code path that reached
    for a gateway raises rather than quietly succeeding. A record that
    fails here does not attest to what it claims, and it is reported as a
    failure rather than dropped.

    Every claim a lineage record makes about its bytes is re-derived by
    the shipped verifier, including the score, so this adds no check of
    its own. It owns two things the shipped per-record check does not:
    withdrawing the gateway so a verification that needs one fails loudly,
    and reporting a failure per record rather than on the first one.
    """
    from experiments.ad01 import live_construct as live
    results = {"campaign_id": CAMPAIGN_ID, "checked": 0, "passed": 0,
               "no_response_to_attest": [], "failures": [],
               "network_withdrawn": True}
    withdrawn = live.LiveGuard.infer
    live.LiveGuard.infer = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("verify reached for a gateway"))
    try:
        for path in sorted((root / "lineages").glob("*.json")):
            record = _read_json(path)
            if not record.get("offline_verified"):
                # A lineage refused before the wire has no response, so
                # there is nothing to recompute. Counting that as a pass
                # would claim verification that never happened, and
                # counting it a failure would claim a record is broken.
                # It is neither.
                results["no_response_to_attest"].append({
                    "record": path.name,
                    "outcome": record["attempts"][0]["outcome"],
                    "reason": record.get("why_not_recomputable")})
                continue
            results["checked"] += 1
            try:
                recomputed = live.verify_preflight_record(record)
                recorded = record["verdict"]["outcome"]
                if recomputed["outcome"] != recorded:
                    raise AssertionError(
                        "verdict %r recomputes as %r"
                        % (recorded, recomputed["outcome"]))
                if recomputed.get("response_digest") != \
                        record["verdict"].get("response_digest"):
                    raise AssertionError("response digest does not recompute")
                results["passed"] += 1
            except Exception as exc:
                results["failures"].append({
                    "record": path.name,
                    "error_class": type(exc).__name__, "error": str(exc)})
    finally:
        live.LiveGuard.infer = withdrawn
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "summarize", "verify",
                                            "census"))
    parser.add_argument("--root", default=str(REPO_ROOT / "reports" / "evidence"
                                              / CAMPAIGN_ID))
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.command == "run":
        print(json.dumps(_run(root), sort_keys=True, indent=1))
    elif args.command == "summarize":
        print(json.dumps(summarize(root), sort_keys=True, indent=1))
    elif args.command == "census":
        print(json.dumps(acquisition_census(), sort_keys=True, indent=1))
    else:
        outcome = verify(root)
        print(json.dumps(outcome, sort_keys=True, indent=1))
        return 0 if not outcome["failures"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
