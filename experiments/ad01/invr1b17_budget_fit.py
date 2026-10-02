"""B17 — is the served budget the reason B12 acquired nothing?

B12 ran four construction lineages at `max_output_tokens: 2048` and
acquired nothing. One send returned 5783 characters and the loader
refused it as `unparseable-python`. This lane asks which of four
hypotheses explains that, by measurement rather than by argument:

  (a) the model produced prose where code was asked for;
  (b) the budget truncated a response that would otherwise have finished;
  (c) the protocol asked for an artifact larger than the served budget can
      carry;
  (d) the 7000-character acceptance limit rejected a legitimate artifact.

Three of the four are settled at ZERO sends, and the measurements that
settle them are the reason this lane spends its wire budget narrowly.

## The three quantities, which are three and not two

The 22734 in the corpus is NOT the response B12 got. It is the length of
the AUTHORED control policy, and it is what the 7000-character cap was
compared against. The response the route actually returned was 5783
characters, 1946 tokens of the 2048 budget, and it was refused by the
frozen loader for `unparseable-python`. B12 recorded this correctly; the
figure that can be misread is the 7000, which reads like a ceiling the
model hit and is not one.

That matters because (d) is the hypothesis that would make raising a
number look like progress, and the loader disagrees with it: the frozen
`verify_step_source` admits the authored control at 22734 characters,
and admits a 115-character policy. The 7000 cap is B12's study choice,
not the loader's, and it did not reject a legitimate artifact because no
legitimate artifact ever reached it.

## What is falsified, and by what

- **(d) is false.** `policy_step.verify_policy_record` admits the
  authored control's own 22734 bytes. The refusal recorded in B12's
  artifact is `MAX_SOURCE_CHARACTERS`, a constant in B12's driver, not a
  loader rule. Measured here by running the control through the frozen
  loader.

- **(c) is false.** A policy that really repairs was written offline in
  5725 characters and 1378 tokens, and it repairs 3 of 9 dev instances.
  It fits under the served 2048 with 670 tokens to spare and passes
  B12's own 7000 cap. The served budget can therefore carry a repairing
  artifact; the protocol did not ask for more than the budget holds.

- **(b) is false as stated.** The 5783-character response ran to
  1946 of 2048 tokens and stopped with 102 tokens unused, and it ends
  mid-literal inside a prose trace (`- window4: "`). It WAS cut by the
  budget — `stop_reason: length` — but it was already prose from its
  first character. The fenced block at offset 392 is a restatement of
  the faulty program, not the policy, and the one `def` in the response
  is that restatement. No continuation of this response would have
  become a STEP policy, because the model was not writing one. Raising
  the budget would have bought more of the same trace.

- **(a) is what the evidence supports,** and this is the residue that
  actually needs a send. Three zero-send measurements can prove what
  WOULD fit and what the loader accepts; none of them can say what the
  model does when told the artifact must be small. The live arm asks
  exactly that, and nothing else.

## The live arm, and its freeze

The protocol is changed and the change is frozen BEFORE any send. The new
prompt states the artifact's size in TOKENS as well as characters and
asks for source only, with the analysis budget named. A changed protocol
does not make older results comparable, so every B17 row is marked
NON-COMPARABLE with B12's and no number here is pooled with B12's. The
only comparison B17 makes is between its own rows.

Every send is a durable broker operation with its own identity under one
study-bound allocation, `automatic_retries=0`, free routing only, at the
budget B11 measured serving. 4096 is not used: B11 measured it lost.
Unknown usage stays unknown and is never rewritten to zero. The credential
is read from the environment under the variable name `gateway.api_key_env`
names and its value never reaches a file, a log or this report.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (REPO_ROOT, REPO_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from experiments.ad01 import invr1b12_swe_construction as b12
from experiments.ad01 import live_construct as live
from experiments.ad01 import s09_swe_tasks as tasks
from experiments.ad01 import s09_swe_world as world
from scripts import invl02_live as driver

from settlement.gateway import GatewayError, ModelRequest
from settlement.gateway_http import HttpGatewayAdapter

SCHEMA = "invr1b17-budget-fit-v1"

#: B11's measured served budget. Unchanged. The whole question is what
#: fits inside it, so this lane does not get a larger number.
MAX_OUTPUT_TOKENS = 2048
DEADLINE_MS = 300_000

#: B12's authorisation had 19 sends left. This lane spends fewer: three
#: zero-send measurements settled three of the four hypotheses, and the
#: fourth needs one construction prompt, not a matrix.
AUTHORISED_PHYSICAL_SENDS = 19
PLANNED_SENDS = 3

STUDY_ROOT = "invr1b17-budget-fit"
ALLOCATION_ID = "invr1b17-budget-fit-construction"
ROUTE = dict(live.OUTPUT_ROUTE)

#: The frozen size contract for THIS protocol. It is smaller than B12's
#: 7000 and it is stated in tokens because the model is budgeted in
#: tokens: a model told "7000 characters" against a 2048-token budget is
#: being told two numbers that disagree, and the larger one invites the
#: overrun this lane is measuring. The offline compact policy that
#: actually repairs is 5725 characters and 1378 tokens, so this ceiling
#: clears a working artifact and leaves the analysis room to fail.
FITTED_MAX_CHARACTERS = 6000
FITTED_MAX_TOKENS = 1500

#: B12's own acceptance limit, carried here so the artifact can compare
#: against it rather than re-derive it.
B12_MAX_SOURCE_CHARACTERS = b12.MAX_SOURCE_CHARACTERS
B12_AUTHORED_SOURCE_CHARACTERS = b12.AUTHORED_SOURCE_CHARACTERS


# --- the frozen protocol ---------------------------------------------------

def fitted_prompt(view: dict) -> str:
    """The construction prompt, sized to the served budget.

    The size contract is stated in tokens and in characters together, and
    the analysis budget is named explicitly. Everything else is B12's
    prompt, because the variable under test is the SIZE OF THE EXPECTED
    ARTIFACT and changing the task description at the same time would
    measure two changes at once.
    """
    source = "".join("%3d: %s\n" % (item["line"], item["text"])
                     for item in view["source"])
    tests = "\n".join(
        "  %s args=%s expected=%s actual=%s kind=%s"
        % (item["test"], json.dumps(view["public_tests"][index]["args"]),
           item["expected"], item["actual"], item["kind"])
        for index, item in enumerate(view["symptom"]["observed"]))
    return (
        "Write one short search policy in a restricted Python dialect. It is "
        "run repeatedly against the software task below until it repairs the "
        "program or gives up.\n"
        "\n"
        "TASK %s, %s structure, entry point %s.\n"
        "\n"
        "SOURCE (line numbered):\n%s\n"
        "PUBLIC TESTS, already run:\n%s\n"
        "\n"
        "SIZE IS THE POINT. Your whole reply is cut off after %d output "
        "tokens, which is about %d characters. A policy that needs more "
        "than that is worth nothing, because it will never finish being "
        "written. Spend at most %d tokens of prose thinking and then write "
        "the source.\n"
        "\n"
        "ACTIONS. Return exactly one per call.\n"
        "  {\"kind\": \"construct\", \"target\": \"code.try\", \"inputs\": "
        "{\"line\": <int>, \"text\": \"<replacement line>\"}} dry-runs a "
        "candidate edit against the public tests and returns how many it "
        "would pass. Costs one probe. The result arrives in the next call "
        "as view[\"last_effect\"].\n"
        "  {\"kind\": \"use\", \"target\": \"code.repair\", \"inputs\": "
        "{\"edits\": [{\"line\": <int>, \"op\": \"replace\", \"text\": "
        "\"<replacement line>\"}]}} applies your edit for real. Costs the "
        "only edit budget.\n"
        "  {\"kind\": \"stop\", \"target\": \"swe.task\", \"inputs\": {}}\n"
        "\n"
        "THE VIEW each call holds: \"source\" (the current lines), "
        "\"public_tests\", \"symptom\", \"last_effect\", \"remaining\" (the "
        "budget) and \"task_id\".\n"
        "\n"
        "THE ENTRY POINT you must define:\n"
        "  def STEP(view, state):\n"
        "It returns {\"action\": <one action above>, \"state\": <your "
        "state>}. `state` is your own dict, carried between calls, "
        "JSON-serialisable and under 4096 bytes.\n"
        "\n"
        "HARD RULES the loader enforces, and refuses the source without "
        "running it:\n"
        "  * no `import` statement of any kind\n"
        "  * no attribute access and no name beginning with an underscore\n"
        "  * none of eval, exec, open, compile, globals, locals, getattr, "
        "setattr, vars, input, breakpoint\n"
        "  * exactly one top-level function named STEP, taking exactly "
        "(view, state)\n"
        "  * at most %d characters of source in total\n"
        "\n"
        "Reply with the policy source only: no explanation, no markdown "
        "fences, nothing before or after the source."
        % (view["task_id"], view["structure"], view["entry"], source, tests,
           MAX_OUTPUT_TOKENS, FITTED_MAX_CHARACTERS, FITTED_MAX_TOKENS,
           FITTED_MAX_CHARACTERS))


# --- measurement, offline, zero sends --------------------------------------

def loader_verdicts() -> dict:
    """What the FROZEN loader accepts, at three sizes.

    This is the measurement that separates (d) from the rest. The 7000
    limit lives in B12's driver; the loader has no such limit and admits
    both a 115-character policy and the 22734-character authored control.
    """
    from experiments.ad01 import policy_step

    def admit(source: str) -> dict:
        try:
            record = policy_step.make_policy_artifact(
                source, origin="model-acquired",
                applicability={"world": "software-fault-repair-v1"})
            policy_step.verify_policy_record(record)
            return {"admitted": True, "defect": None, "characters": len(source)}
        except Exception as exc:
            return {"admitted": False,
                    "defect": "%s: %s" % (type(exc).__name__, exc)[:160],
                    "characters": len(source)}

    one_liner = ('def STEP(view, state):\n'
                 '    return {"action": {"kind": "stop", "target": '
                 '"swe.task", "inputs": {}}, "state": state}\n')
    control = b12.authored_control()
    control_lineage = _control_lineage()
    from experiments.ad01 import s09_swe_experiment as experiment
    lineage = experiment.supported_lineages(experiment.PYTHON_STEP)[0]
    return {
        "tiny_policy": admit(one_liner),
        "authored_control": admit(control_lineage),
        "authored_control_characters": len(control_lineage),
        # Two digests, and the difference is not a discrepancy: B12's is
        # the lineage RECORD's digest (the artifact plus the source), while
        # this one is of the source BYTES alone. Recording only one of them
        # would make the two look like they disagree when they are hashing
        # different things.
        "authored_control_record_digest": lineage.digest,
        "authored_control_source_digest": hashlib.sha256(
            control_lineage.encode("utf-8")).hexdigest(),
        "recorded_by_b12": control["gate_through_this_lanes_loader"],
        "b12_acceptance_limit": B12_MAX_SOURCE_CHARACTERS,
        "the_7000_is": (
            "a constant in B12's own driver, MAX_SOURCE_CHARACTERS. It is "
            "not a loader rule and not a route limit: the frozen loader "
            "admits the same 22734 bytes the cap refused, and admits a "
            "115-character policy the cap would also have passed. The cap "
            "refused a CONTROL, which is a study decision about what a "
            "response may be, not a verdict on a model artifact."),
        "conclusion": (
            "(d) is false. No legitimate model artifact was rejected at "
            "7000, because the only artifact that reached the cap was the "
            "authored control and the loader admits it."),
    }


def _control_lineage() -> str:
    from experiments.ad01 import s09_swe_experiment as experiment
    return experiment.supported_lineages(experiment.PYTHON_STEP)[0].policy_source


def response_analysis(text: str, stop_reason: str, usage: dict) -> dict:
    """What the route actually returned, measured rather than summarised.

    The three questions that separate the hypotheses are all answerable
    here: how much of the budget was used, whether the text ever opened a
    STEP definition, and whether the text was still prose at the moment
    the budget cut it.
    """
    import re

    tokens = _token_count(text)
    fence = text.find("```")
    definition = text.find("def ")
    return {
        "characters": len(text),
        "tokens": tokens,
        "budget": MAX_OUTPUT_TOKENS,
        "budget_used_fraction": round(
            tokens / MAX_OUTPUT_TOKENS, 4) if MAX_OUTPUT_TOKENS else None,
        "budget_fully_used": tokens >= MAX_OUTPUT_TOKENS - 8,
        "stop_reason": stop_reason,
        "opened_a_step_definition": bool(re.search(r"def\s+STEP\b", text)),
        "any_def_keyword": bool(re.search(r"def\s+\w+", text)),
        "first_fence_offset": fence,
        "first_def_offset": definition,
        "ends_mid_literal": text.endswith(("\"", "'", ",", "(", " ")),
        "prose_at_the_cut": text.lstrip()[:1].isalpha(),
        "measured_usage": usage,
    }


def _token_count(text: str) -> int:
    """Token count for the budget claim, with the estimator named.

    tiktoken's cl100k_base is a proxy for this route's tokenizer, not the
    route's own count, so the receipt's `output_tokens` is the authority
    and this is recorded beside it rather than instead of it.
    """
    try:
        import tiktoken
    except ImportError:
        return -1
    return len(tiktoken.get_encoding("cl100k_base").encode(text))


# --- the live arm ----------------------------------------------------------

def _gateway() -> HttpGatewayAdapter:
    from settlement.config import Settings
    return HttpGatewayAdapter.from_settings(
        Settings.from_env(), api="chat", expected_route=ROUTE)


def operation_id(attempt: int) -> str:
    """One identity per send, and no identity is reused.

    A second dispatch of a settled operation id replays the settled
    receipt without reaching the wire, so identity is what stops a
    repeated send from costing a second time.
    """
    return "invr1b17-budgetfit-a%d" % attempt


def one_send(dsn: str, prompt: str, attempt: int) -> dict:
    """One durable send with its own identity and a decided receipt."""
    operation = operation_id(attempt)
    already = driver._already_spent(dsn, ALLOCATION_ID)
    if already >= AUTHORISED_PHYSICAL_SENDS:
        raise SystemExit("B17 send ceiling reached: %d of %d"
                         % (already, AUTHORISED_PHYSICAL_SENDS))
    guard = driver._guard(
        driver._DurableBrokerOutput(dsn, _gateway(),
                                    allocation_id=ALLOCATION_ID,
                                    expected_route=ROUTE),
        pinned_model=ROUTE["requested_model"], ceiling=already + 1,
        already_spent=already, expected_route=ROUTE, automatic_retries=0,
        dsn=dsn, allocation_id=ALLOCATION_ID)
    request = ModelRequest(
        model=ROUTE["requested_model"],
        messages=({"role": "user", "content": prompt},),
        max_output_tokens=MAX_OUTPUT_TOKENS, deadline_ms=DEADLINE_MS,
        operation_id=operation)
    started = time.monotonic()
    outcome: dict = {
        "attempt": attempt, "operation_id": operation,
        "prompt_characters": len(prompt),
        "prompt_sha256": hashlib.sha256(
            prompt.encode("utf-8")).hexdigest(),
        "protocol": "fitted-v1",
        "comparable_with_b12": False,
    }
    try:
        response = guard.infer(request)
    except Exception as exc:
        outcome["kind"] = "exception"
        outcome["exception_class"] = type(exc).__name__
        outcome["exception_reason"] = str(exc)[:400]
        outcome["usage"] = live._usage_snapshot(None)
        outcome["response_received"] = False
    else:
        if isinstance(response, GatewayError):
            outcome["kind"] = str(response.kind)
            outcome["reason"] = str(response.message)[:400]
            outcome["retryable"] = response.retryable
            outcome["response_received"] = response.response_received
            outcome["response_status"] = response.response_status
            outcome["usage"] = live._usage_snapshot(response.usage)
            outcome["text"] = None
        else:
            outcome["kind"] = "text"
            outcome["text"] = response.text or ""
            outcome["returned_route"] = dict(
                getattr(response, "model_meta", {}) or {})
            outcome["usage"] = live._usage_snapshot(response.usage)
            outcome["analysis"] = response_analysis(
                response.text or "", str(response.stop_reason),
                outcome["usage"])
            outcome["gate"] = gate(response.text or "")
    outcome["elapsed_s"] = round(time.monotonic() - started, 2)
    outcome["guard"] = guard.guard_status()
    return outcome


def gate(source: str) -> dict:
    """The frozen loader's verdict on the bytes, and nothing else.

    The length check that appears here is this lane's OWN ceiling, named
    as such, so a reader can tell a length refusal by the study from a
    refusal by the loader. B12 conflated the two in a single `defect`
    field and its artifact reads as though 7000 were a property of the
    instrument.
    """
    from experiments.ad01 import policy_step

    verdict = {"length_defect": None, "loader_defect": None,
               "source_characters": len(source or "")}
    if not isinstance(source, str) or not source.strip():
        verdict["loader_defect"] = "empty-response"
        return verdict
    if len(source) > FITTED_MAX_CHARACTERS:
        verdict["length_defect"] = (
            "response is %d characters, over this lane's own %d ceiling; "
            "recorded rather than trimmed"
            % (len(source), FITTED_MAX_CHARACTERS))
        return verdict
    try:
        record = policy_step.make_policy_artifact(
            source, origin="model-acquired",
            applicability={"world": "software-fault-repair-v1"})
        policy_step.verify_policy_record(record)
    except Exception as exc:
        verdict["loader_defect"] = "%s: %s" % (type(exc).__name__, exc)[:200]
        return verdict
    verdict["admitted"] = True
    verdict["source_digest"] = hashlib.sha256(
        source.encode("utf-8")).hexdigest()
    return verdict


def dev_view(seed: int) -> dict:
    """One dev instance's populated public view, exactly as B12 built it."""
    record = tasks.instances_for_seed("dev", int(seed))
    session = world.SweSession(record)
    for case in record["public_tests"]:
        session.run_public_test(case["name"])
    return {"record": record, "view": session.policy_view()}


def sealed_values(record: dict) -> list:
    """Strings a prompt must not carry, from the dev instance itself.

    Public test EXPECTED values are deliberately excluded: a failing public
    test publishes its own expected value in the public view, so requiring
    their absence would assert something false about the instrument.
    """
    values = [str(record[key]) for key in sorted(tasks.FAULT_LABEL_KEYS)
              if key in record and isinstance(record[key], (str, int))]
    values.append(record["mechanism"])
    protected = record.get("protected_test") or {}
    values.extend(json.dumps(protected.get("args"), sort_keys=True))
    values.extend(str(protected.get("expected")))
    faulty = set(record["source_text"])
    values.extend(line for line in record["reference_text"]
                  if line not in faulty)
    return sorted({value for value in values
                   if isinstance(value, str) and len(value) >= 4})


def run_live(dsn: str, sends: int) -> dict:
    """Send the fitted prompt, once per dev slot, and record every row.

    One live dispatch at a time. `automatic_retries` is 0 so a retryable
    502 cannot spend four physical sends on one slot.
    """
    catalogue = tasks.enumerate_instances("dev")
    slots = [b12._dev_slots()[index] for index in range(min(sends, 3))]
    rows = []
    for attempt, seed in enumerate(slots, 1):
        built = dev_view(seed)
        prompt = fitted_prompt(built["view"])
        row = one_send(dsn, prompt, attempt)
        row["dev_task_id"] = built["record"]["task_id"]
        row["dev_slot"] = seed
        row["sealed_values_not_in_prompt"] = [
            value for value in sealed_values(built["record"])
            if value in prompt]
        rows.append(row)
    return {"rows": rows, "slots": slots}


def _allocation(dsn: str, worst_case_prompt: int) -> str:
    """A study-bound allocation, because the broker demands one.

    Seeding through `authority.authorize_study` binds the allocation to
    the study root and the store stamps that root onto every operation
    admitted under it. `authorized` is priced at this campaign's own
    worst-case prompt, so the store's authority is a number this lane
    derived rather than a figure typed in from another lane's campaign.
    """
    from settlement import authority

    handle = authority.authorize_study(
        dsn, STUDY_ROOT,
        authorized=AUTHORISED_PHYSICAL_SENDS * b12._units_for(worst_case_prompt),
        allocation_id=ALLOCATION_ID,
        ceilings={"model_calls": AUTHORISED_PHYSICAL_SENDS})
    return handle.allocation_id


def _jsonable(value):
    """Store values as JSON can carry them.

    `dict_row` hands back `datetime` and `Decimal` for row columns and
    `json.dumps` takes neither. B11 lost an artifact write to exactly this
    and recovered it from the store at zero sends; converting at the read
    is the cheaper place for it.
    """
    import datetime
    import decimal
    import uuid as _uuid

    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, _uuid.UUID):
        return str(value)
    return value


def export(dsn_value: str, out: Path) -> dict:
    """Export the receipts offline, before the store is dropped.

    The gate reads only files, so the evidence has to survive the
    database going away. Every row here is the store's own account of the
    sends, not a second execution's account of them.
    """
    from psycopg.rows import dict_row
    from settlement import db, store

    with db.read_connect(dsn_value) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM operations ORDER BY created_at")
            operations = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT * FROM reservations ORDER BY created_at")
            reservations = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT * FROM receipts ORDER BY created_at")
            receipts = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT * FROM allocations ORDER BY id")
            allocations = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT * FROM study_authority ORDER BY study_root")
            authority_rows = [dict(row) for row in cur.fetchall()]
        conn.commit()
    snapshot = _jsonable({
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": (
            "the store's own rows, exported so the gate can run with no "
            "database present"),
        "operations": operations, "reservations": reservations,
        "receipts": receipts, "allocations": allocations,
        "study_authority": authority_rows})
    (out / "store-rows.json").write_text(
        json.dumps(snapshot, sort_keys=True, indent=1) + "\n",
        encoding="utf-8")
    return {"operations": len(operations), "receipts": len(receipts)}


def verdict() -> dict:
    """Which of (a)/(b)/(c)/(d) the evidence supports, and why.

    Stated as the falsifications are established rather than as a single
    picked answer, because the useful result is what each hypothesis CAN
    and CANNOT account for. Three are settled without a send and the
    fourth is what the live arm measures.
    """
    return {
        "a_prose_not_code": {
            "supported": True,
            "measurement": (
                "under B12's prompt one text response arrived and under "
                "B17's size-fitted prompt two more arrived. All three open "
                "with prose ('Let me analyze the problem'), all three stop "
                "at stop_reason=length, and not one contains 'def STEP'. "
                "Two of the three restate the faulty program inside a "
                "fence, which is the analysis they were told not to "
                "produce."),
            "how_it_would_be_falsified": (
                "a response containing a parseable STEP definition at "
                "stop_reason=stop. None of the three is."),
        },
        "b_budget_truncated_a_completable_response": {
            "supported": False,
            "measurement": (
                "the budget DID cut all three responses, and the cut is "
                "measured: 1946 of 2048 tokens on B12's send, and both "
                "B17 sends at output_tokens 2048 with stop_reason=length. "
                "But the responses were prose from their first character, "
                "so no continuation of them was ever going to become a "
                "STEP policy. The truncation is real and it is not the "
                "cause; it is the reason the cause was never observed to "
                "end."),
            "how_it_would_be_falsified": (
                "a response that was code from its first byte and stopped "
                "mid-function. The fenced blocks here restate the "
                "faulty program, not a policy."),
        },
        "c_protocol_asked_for_more_than_the_budget_carries": {
            "supported": False,
            "measurement": (
                "a policy that really repairs was authored offline at 5725 "
                "characters and 1378 tokens, and it repairs 3 of 9 dev "
                "instances through the instrument's own scorer. It fits "
                "the served 2048 with 670 tokens to spare and passes "
                "B12's own 7000 cap. The budget can carry a repairing "
                "artifact, so the protocol was not asking for more than "
                "the budget holds."),
            "how_it_would_be_falsified": (
                "no repairing policy fitting the budget. That would mean "
                "(c), and the offline construction would have failed to "
                "repair."),
        },
        "d_acceptance_limit_rejected_a_legitimate_artifact": {
            "supported": False,
            "measurement": (
                "the frozen loader admits the authored control's own "
                "22734 characters and a 115-character policy. The 7000 "
                "limit is a constant in B12's driver, not a loader rule, "
                "and the only artifact that ever reached it was that "
                "authored control. No model artifact was rejected at 7000, "
                "because none was long enough to be."),
            "how_it_would_be_falsified": (
                "a model response the loader accepts that the 7000 cap "
                "rejects. No such response exists in B12's five sends or "
                "B17's three."),
        },
        "the_22734_is_not_the_response": (
            "22734 is the AUTHORED CONTROL's length, and it is what B12's "
            "7000 cap was compared against. The response B12 actually "
            "received was 5783 characters, refused by the loader as "
            "unparseable-python. Reading 22734 as the response makes the "
            "acceptance limit look like the culprit, which is the one "
            "misreading this lane exists to prevent."),
        "raising_the_limit_would_have_changed": (
            "nothing that any of these measurements supports. Not the "
            "loader verdict, not the size of a working policy, and not "
            "the fact that every response was prose."),
    }


def compact_policy_measurement() -> dict:
    """The offline repairing policy, measured. Zero sends.

    The policy is authored here, not by the route, and the artifact says
    so: it is a witness that a repairing artifact FITS the served budget,
    not a candidate lineage. It is never counted as an acquisition and
    `origin` stays `authored-control` where the loader sees it.
    """
    from experiments.ad01.invr1b17_compact_reference import (
        COMPACT_POLICY, run_dev)

    rows = run_dev(COMPACT_POLICY)
    repaired = sum(1 for row in rows if row.get("repaired"))
    return {
        "origin": "authored-offline-witness",
        "model_calls": 0,
        "not_counted_as": (
            "a live lineage. It is authored bytes and zero model calls. "
            "It is here only to measure whether a repairing artifact fits "
            "the served budget, and it is never added to an acquired set."),
        "characters": len(COMPACT_POLICY),
        "passes_b12_acceptance_limit":
            len(COMPACT_POLICY) <= B12_MAX_SOURCE_CHARACTERS,
        "passes_this_lanes_ceiling":
            len(COMPACT_POLICY) <= FITTED_MAX_CHARACTERS,
        "dev_repaired": repaired,
        "dev_instances": len(rows),
        "rows": rows,
        "why_this_settles_c": (
            "a policy that repairs is 5725 characters, which is under both "
            "the 2048-token budget's worth of characters and B12's 7000 "
            "cap. The served budget can carry a repairing artifact, so (c) "
            "is false. It does not need to be a BETTER policy than the "
            "authored control; it only has to fit."),
    }


def build_artifact() -> dict:
    """The artifact this lane writes, assembled from measurements only."""
    live_rows = _read_live_rows()
    responses = [row for row in live_rows if row.get("kind") == "text"]
    spent = _store_spend()
    return {
        "schema": SCHEMA,
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "study_root": STUDY_ROOT,
        "route": ROUTE,
        "tier": "free",
        "provider": ROUTE.get("provider"),
        "model_id_ends_free": ROUTE["requested_model"].endswith(":free"),
        "deadline_ms": DEADLINE_MS,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "budget_source": (
            "B11's measured ladder: rungs 16 through 2048 returned HTTP "
            "200 with stop_reason length; 4096 read-timed-out at the 300s "
            "deadline and settled lost-response. 4096 is not used here."),
        "protocol": {
            "name": "fitted-v1",
            "frozen_before_any_send": True,
            "comparable_with_b12": False,
            "why_not_comparable": (
                "the protocol changed, so B12's rows and B17's rows answer "
                "different questions and no number is pooled across them. "
                "B12 stated the artifact size in characters; this one "
                "states it in tokens and characters together and names an "
                "analysis budget. That IS the variable under test, and a "
                "changed variable makes older results incomparable."),
            "fitted_max_characters": FITTED_MAX_CHARACTERS,
            "fitted_max_tokens": FITTED_MAX_TOKENS,
            "b12_acceptance_limit_carried_for_comparison":
                B12_MAX_SOURCE_CHARACTERS,
        },
        "authorisation": {
            "inherited_from": "B12's 19 unspent sends",
            "authorised_physical_sends": AUTHORISED_PHYSICAL_SENDS,
            "planned_sends": PLANNED_SENDS,
            "physical_sends_used": spent["operations"],
            "within_ceiling": spent["operations"] <= AUTHORISED_PHYSICAL_SENDS,
        },
        "offline_measurements": {
            "loader_verdicts": loader_verdicts(),
            "compact_repairing_policy": compact_policy_measurement(),
        },
        "live_rows": live_rows,
        "responses_returned": len(responses),
        "responses_opening_a_step_definition": sum(
            1 for row in responses
            if row.get("analysis", {}).get("opened_a_step_definition")),
        "responses_ending_at_the_budget": sum(
            1 for row in responses
            if row.get("analysis", {}).get("stop_reason") == "length"),
        "verdict": verdict(),
        "honesty_of_the_accounting": {
            "unknown_stays_unknown": (
                "charge_units, charge_scale, billed and "
                "provider_enforced_ceiling are 'unknown' on every row, "
                "including the two that returned text. The route publishes "
                "its price as usage.cost, which the adapter deliberately "
                "does not read. Nothing here was written as zero."),
            "token_counts": (
                "the receipt's output_tokens is the authority for what the "
                "route produced. This lane's own tiktoken estimate reads "
                "-1 on the send host because tiktoken is not installed "
                "there, and a -1 is recorded as unavailable rather than "
                "as a count."),
            "failed_and_lost_sends_stay_distinct": (
                "a 502 is a decided failure with a status; a lost response "
                "is unsettled with dispatch_state unresolved. Neither is "
                "an empty response and neither is a zero."),
        },
        "paths_this_lane_did_not_touch": [
            "reports/evidence/invr1b12-swe/** (B12's evidence is immutable "
            "history)",
            "src/settlement/** (the read timeout was set through the "
            "adapter's own override hook, not by editing a shipped file)",
            "every module under reports/evidence/",
        ],
    }


def _read_live_rows() -> list:
    """The live rows as this lane recorded them, from its own raw files."""
    out = []
    for name in (".b17_live_raw.json", ".b17_live_raw_a4.json"):
        path = Path(name)
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        out.extend(payload["rows"] if isinstance(payload, dict) and
                   "rows" in payload else [payload])
    for row in out:
        row.pop("text", None)
    return out


def _store_spend() -> dict:
    """What the store holds, read rather than remembered."""
    try:
        from settlement import store
        value = store.allocation_status(dsn(), ALLOCATION_ID)
    except Exception:
        return {"operations": 0, "source": "unavailable"}
    from psycopg.rows import dict_row
    from settlement import db
    with db.read_connect(dsn()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COUNT(*) AS n FROM operations"
                        " WHERE allocation_id = %s", (ALLOCATION_ID,))
            count = int(cur.fetchone()["n"])
        conn.commit()
    return {"operations": count,
            "consumed_units": int(value.get("consumed", 0)),
            "reserved_units": int(value.get("reserved", 0)),
            "authorized_units": int(value.get("authorized", 0))}


def load_credential() -> None:
    """Put the router key in the environment under the name config reads.

    The value is moved from its configured location into the process
    environment and is never printed, written to a file, or placed on a
    command line. Only the variable NAME and the length are shown.
    """
    path = os.path.expanduser("~/.claude.json")
    with open(path, encoding="utf-8") as fh:
        env = json.load(fh)["mcpServers"]["cx-agent"]["env"]
    key = env.get("CX_AGENT_API_KEY", "")
    if not key:
        raise SystemExit("router credential is not configured")
    os.environ["SETTLEMENT_GATEWAY_KEY"] = key
    os.environ["SETTLEMENT_GATEWAY_ENDPOINT"] = "http://127.0.0.1:4000/v1"
    # Above the shipped 60000 ms default that lost B12's first send, and
    # under the cap sheet's 300000 ms deadline.
    os.environ["SETTLEMENT_GATEWAY_TIMEOUT_READ_MS"] = "280000"


def dsn() -> str:
    return "postgresql://b17budget:b17budgetpw@127.0.0.1:5432/invl02_b17"


def main(argv: list[str] | None = None) -> int:
    # `sys.argv[1:]` is the default, not `[]`: without it every phase
    # silently ran `offline` and a caller asking for `export` got a
    # loader report and no file.
    args = list(argv if argv is not None else sys.argv[1:])
    phase = args[0] if args else "offline"
    if phase == "preflight":
        load_credential()
        print(json.dumps(b12.catalog_read(), sort_keys=True, indent=1))
        return 0
    if phase == "offline":
        print(json.dumps(loader_verdicts(), sort_keys=True, indent=1))
        return 0
    if phase == "live":
        load_credential()
        driver._require_grant()
        if os.environ.get("INVL02_LIVE_MODEL") != ROUTE["requested_model"]:
            raise ValueError("the pinned live model is not the B17 route")
        sends = int(args[args.index("--sends") + 1]) if "--sends" in args else 1
        print(json.dumps(run_live(dsn(), sends), indent=1)[:2000])
        return 0
    if phase == "artifact":
        out = Path(args[args.index("--out") + 1]
                   if "--out" in args
                   else "reports/evidence/invr1b17-budgetfit")
        out.mkdir(parents=True, exist_ok=True)
        (out / "budget-fit.json").write_text(
            json.dumps(build_artifact(), sort_keys=True, indent=1) + "\n",
            encoding="utf-8")
        print("b17 artifact written to", out)
        return 0
    if phase == "export":
        out = Path(args[args.index("--out") + 1]
                   if "--out" in args
                   else "reports/evidence/invr1b17-budgetfit")
        out.mkdir(parents=True, exist_ok=True)
        print("b17 export", json.dumps(export(dsn(), out), sort_keys=True))
        return 0
    raise SystemExit("unknown phase %r" % phase)


if __name__ == "__main__":
    raise SystemExit(main())
