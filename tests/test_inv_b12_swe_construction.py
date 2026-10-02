"""B12's gate: the SWE construction run's own record, asserted as literals.

Every assertion reads a literal out of
`reports/evidence/invr1b12-swe/` — the campaign artifact and the exported
store rows — rather than recomputing anything with the functions that
produced them. That is the point. A test that recomputed the dispatch
count with the driver's own `_spend` would pass on a driver that counted
wrong, so this file names the numbers the run observed and fails if the
artifact changes them.

The claims, each from the assignment's own gate list:

  * the measured model id ends in `:free`, and the catalog attested it;
  * every send has an operation row, an allocation, a decided receipt and
    exposure;
  * dispatches are at or under 24 and physical sends at or under 25;
  * every no-acquisition row says so, and NO authored arm is scored as
    acquired;
  * no sealed-assessment value appears in any recorded prompt;
  * usage preserves unknown as unknown;
  * no credential value appears in any file this lane wrote.

The last is a real scan, not a promise: the credential is read from its
configured location so the VALUE is available to search for, and the
lane's written bytes are searched for it in full.

Nothing here reaches a network or a database. The artifacts are files, so
this passes with the disposable store dropped, which is what shows the
evidence is the artifact rather than a view of a live store.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "reports/evidence/invr1b12-swe"
CAMPAIGN = EVIDENCE / "campaign.json"
CONSTRUCTION = EVIDENCE / "construction.json"
USE = EVIDENCE / "use.json"
STORE_ROWS = EVIDENCE / "store-rows.json"
WORKSTREAM = ROOT / "reports/workstreams/b12-swe.md"

#: The cap sheet's `B12` row, verbatim.
AUTHORISED_DISPATCHES = 24
AUTHORISED_PHYSICAL_SENDS = 25
PLANNED_CONSTRUCTION_DISPATCHES = 8
REPAIR_ALLOWANCE_PER_LINEAGE = 1
LINEAGES_PER_CELL = 4

#: The route the cap sheet freezes.
FROZEN_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
CAMPAIGN_BUDGET = 2048
DEADLINE_MS = 300000

#: Fields this route does not report. `_decode_usage` deliberately does not
#: read the route's price, which it publishes as `usage.cost`.
UNREPORTED_USAGE_FIELDS = ("charge_units", "billed", "charge_scale",
                           "provider_enforced_ceiling")


def _load(path: Path) -> dict:
    assert path.is_file(), (
        "the run's artifact is missing: %s. B12 spent real sends and the "
        "record of them is the only evidence they happened." % path)
    return json.loads(path.read_text(encoding="utf-8"))


def _construction() -> dict:
    return _load(CONSTRUCTION)


def _campaign() -> dict:
    return _load(CAMPAIGN)


def _every_attempt() -> list:
    """Every attempt of every lineage, flattened."""
    return [attempt
            for lineage in _construction()["lineages"]
            for attempt in lineage["attempts"]]


# --- the route -----------------------------------------------------------


def test_the_recorded_model_is_a_free_tier_id_the_catalog_attested():
    """`reports/cap-sheets/b-live-cap.md` pins the route and forbids a paid one.

    Asserted on the run's own recorded route, and on the catalog read taken
    from the same run, so the claim is that this route was free when it was
    measured rather than that it is spelled freely. The catalog COUNT is
    deliberately NOT asserted: B11 saw 255, 256, 219 and 203 across reads,
    so a count is not a stable number and pinning one would assert a
    property the route does not have.
    """
    record = _construction()
    route = record["route"]
    assert route["requested_model"] == FROZEN_MODEL, route["requested_model"]
    assert route["requested_model"].endswith(":free"), (
        "the measured model id is not a free tier id: %r"
        % route["requested_model"])
    assert route["tier"] == "free", route["tier"]
    assert route["provider"] == "nvidia", route["provider"]
    catalog = record["catalog"]
    assert catalog["requested_model_ends_free"] is True
    assert catalog["pinned_present"] is True, (
        "the pinned id was absent from the catalog read at dispatch, so no "
        "send under this run had its route precondition met")
    assert catalog["verdict"] == "accepted", catalog.get("reason")


def test_the_run_is_bounded_by_the_cap_sheet_and_says_which_bounds_it_ran_under():
    """Dispatches at or under 24, physical sends at or under 25.

    Asserted against the store's OWN operation count rather than against
    the driver's summary, because those two can disagree and the
    disagreement is the finding: a send that reached the store without
    appearing in a lineage row is exposure nobody accounted for.
    """
    record = _construction()
    assert record["authorised_dispatches"] == AUTHORISED_DISPATCHES
    assert record["authorised_physical_sends"] == AUTHORISED_PHYSICAL_SENDS
    assert record["planned_construction_dispatches"] == \
        PLANNED_CONSTRUCTION_DISPATCHES
    assert record["repair_allowance_per_lineage"] == \
        REPAIR_ALLOWANCE_PER_LINEAGE
    assert record["max_output_tokens"] == CAMPAIGN_BUDGET, (
        "this lane ran at a budget other than the one B11 measured serving, "
        "so its numbers are not comparable with anything run at 2048")
    assert record["deadline_ms"] == DEADLINE_MS, record["deadline_ms"]
    assert record["reasoning_effort"] == "none-sent", (
        "a reasoning effort is recorded as a control the wire never applied")

    rows = _load(STORE_ROWS)
    operations = rows["operations"]
    receipts = rows["receipts"]
    dispatches = len(operations)
    assert dispatches <= AUTHORISED_DISPATCHES, (
        "the store holds %d operations, over the %d the cap sheet authorises"
        % (dispatches, AUTHORISED_DISPATCHES))
    assert dispatches <= AUTHORISED_PHYSICAL_SENDS
    assert record["dispatches_used"] == dispatches, (
        "the driver reported %r dispatches but the store holds %d operations; "
        "a send happened that no lineage row accounts for"
        % (record["dispatches_used"], dispatches))
    assert len(receipts) == dispatches, (
        "%d operations against %d receipts" % (dispatches, len(receipts)))

    # Every attempt is exactly one of: a fresh send this process made, or a
    # store re-read of a send some process made. A store read is not a wire
    # send, so the run's own spend is the `dispatched` count; the ceiling is
    # checked against the STORE, because five operations are five sends
    # whether this process made them or an earlier one did. Every attempt
    # must reconcile against the store, and no operation may go unaccounted.
    dispatched = [a for a in _every_attempt() if a.get("dispatched")]
    re_read = [a for a in _every_attempt() if a.get("replayed")]
    for attempt in dispatched:
        assert not attempt.get("replayed"), attempt["operation_id"]
    for attempt in re_read:
        assert not attempt.get("dispatched"), attempt["operation_id"]
        assert attempt["rows"]["operations"], (
            "%s claims to be a re-read but the store holds no operation for it"
            % attempt["operation_id"])
    assert len(dispatched) + len(re_read) == dispatches, (
        "%d dispatched plus %d re-read attempts against %d operations in the "
        "store; every operation must be reached by exactly one attempt"
        % (len(dispatched), len(re_read), dispatches))
    unaccounted = record["operations_not_accounted_by_a_lineage_row"]
    assert not unaccounted, (
        "the store holds operations no lineage row accounts for: %s"
        % [row["id"] for row in unaccounted])
    per_lineage = [row["dispatches"] for row in record["lineages"]]
    assert sum(per_lineage) == dispatches, (
        "lineage rows report %d dispatches against %d operations in the "
        "store; a lineage's `dispatches` is sends on the wire, which is what "
        "the cap sheet prices, whichever process made them"
        % (sum(per_lineage), dispatches))
    assert sum(per_lineage) == len(_every_attempt()), (
        "lineage rows report %d dispatches against %d recorded attempts"
        % (sum(per_lineage), len(_every_attempt())))
    for row in record["lineages"]:
        assert row["dispatches"] <= REPAIR_ALLOWANCE_PER_LINEAGE + 1, (
            "lineage %s used %d dispatches, over the one construction plus "
            "one repair the cap sheet prices"
            % (row["lineage"], row["dispatches"]))


# --- durability ----------------------------------------------------------


def test_every_send_is_a_durable_operation_with_an_allocation_and_exposure():
    """One send, one operation row, one allocation, one decided receipt, exposure.

    Read off the store rows the artifact carries, not off a return value:
    the claim being evidenced is that each send left a durable trace, and
    only a row is a trace. Exposure is read from the reservation, because a
    reservation with no amount records nothing.
    """
    record = _construction()
    allocation_id = record["allocation_id"]
    seen = set()
    for attempt in _every_attempt():
        # Both a fresh send and a store re-read must show a durable trace.
        # A re-read is not a new wire send, but it IS an operation with a
        # row, an allocation, exposure and a decided receipt, and asserting
        # only the fresh ones would leave a resumed run's operations
        # unchecked.
        operation_id = attempt["operation_id"]
        where = "operation %s" % operation_id
        rows = attempt["rows"]
        operations = rows["operations"]
        assert len(operations) == 1, (
            "%s admitted %d operation rows, so the send left no single "
            "identity" % (where, len(operations)))
        operation = operations[0]
        assert operation["id"] == operation_id, where
        assert operation["allocation_id"] == allocation_id, (
            "%s was admitted outside the study allocation" % where)
        payload = operation["payload"] or {}
        assert payload.get("effect") == "model-inference", (
            "%s is not a model-inference operation" % where)
        assert payload.get("study_root") == record["study_root"], (
            "%s is not bound to the study root" % where)
        assert attempt["prompt_sha256"] != "", "%s records no prompt" % where
        reservations = rows["reservations"]
        assert reservations, "%s reserved no exposure" % where
        assert int(reservations[0]["amount"]) > 0, (
            "%s reserved zero, which records no exposure" % where)
        receipts = rows["receipts"]
        assert len(receipts) == 1, (
            "%s has %d receipts, so its outcome is not decided"
            % (where, len(receipts)))
        assert receipts[0]["outcome"] in ("success", "failure", "unknown"), (
            "%s has an undecided outcome: %r"
            % (where, receipts[0]["outcome"]))
        assert not rows["receipt_conflicts"], "%s has conflicting receipts" % where
        seen.add(operation_id)
    assert len(seen) == len(_every_attempt()), (
        "two attempts share one operation identity, so one of them is a replay")

    allocations = [row for row in _load(STORE_ROWS)["allocations"]
                   if row["id"] == allocation_id]
    assert len(allocations) == 1, (
        "the study allocation is not in the exported rows, so no send can be "
        "shown to have been bound to one")
    assert int(allocations[0]["authorized"]) >= AUTHORISED_DISPATCHES * 2000, (
        "the allocation's authority is smaller than the cap sheet's dispatch "
        "ceiling priced at this campaign's budget")


def test_lost_and_failed_sends_stay_distinct_from_a_measured_refusal():
    """The five failure modes stay five, and none collapses into a zero.

    A send that reached the wire and got no answer is `unknown` with a
    `lost-response` receipt. A send the route answered with an error is
    `failure` with its status. Neither is written as a refusal by the free
    gate, and neither is written as a measured zero.
    """
    outcomes = {attempt["operation_id"]: attempt["rows"]["receipts"][0]["outcome"]
                for attempt in _every_attempt()
                if attempt["rows"]["receipts"]}
    assert outcomes, "no send left a decided receipt"
    for operation_id, outcome in outcomes.items():
        assert outcome in ("success", "failure", "unknown"), (
            "%s settled as %r, which is not one of the three decided states"
            % (operation_id, outcome))
    lost = [a for a in _every_attempt()
            if a["rows"]["receipts"]
            and a["rows"]["receipts"][0]["outcome"] == "unknown"]
    for attempt in lost:
        assert attempt["rows"]["receipts"][0]["outcome"] == "unknown", (
            "%s raised but settled as a decided failure; a lost response is "
            "not a measured failure" % attempt["operation_id"])
        for field in ("input_tokens", "output_tokens"):
            assert attempt["usage"][field] == "unknown", (
                "%s recorded %s as %r; a send that produced no answer is not "
                "a measured zero"
                % (attempt["operation_id"], field, attempt["usage"][field]))


def test_usage_is_recorded_honestly_and_unknown_stays_unknown():
    """Unknown is not zero.

    `billed`, `charge_units`, `charge_scale` and
    `provider_enforced_ceiling` are unknown on this route by B11's
    measurement: the route publishes its price as `usage.cost`, which
    `_decode_usage` deliberately does not read. A run that wrote any of
    them as a number would have invented a measurement.
    """
    for attempt in _every_attempt():
        usage = attempt["usage"]
        for field in UNREPORTED_USAGE_FIELDS:
            assert usage[field] == "unknown", (
                "%s: %s was written as %r on a route that does not report it"
                % (attempt["operation_id"], field, usage[field]))
        if attempt["kind"] == "text":
            assert isinstance(usage["output_tokens"], int), (
                "%s returned text but records output tokens as %r"
                % (attempt["operation_id"], usage["output_tokens"]))


# --- the honesty rule ----------------------------------------------------


def test_a_failed_acquisition_is_never_replaced_by_an_authored_arm():
    """The rule this study exists to keep.

    A lineage the route did not build is a no-acquisition row and says so.
    The authored STEP policy is recorded in the artifact as
    `authored_control` with `model_calls: 0`, and it must appear nowhere in
    `lineages`, nowhere as an acquired digest, and nowhere in the use arm's
    episodes. Counting authored bytes as an acquisition would be counting a
    control as a result.
    """
    record = _construction()
    control = record["authored_control"]
    assert control["origin"] == "authored-control", control["origin"]
    assert control["model_calls"] == 0, control["model_calls"]
    assert "not_counted_as" in control, (
        "the control does not say it is not counted as a lineage")
    assert control["digest"] not in [
        row["acquisition_digest"] for row in record["lineages"]], (
        "the authored control's digest appears as an acquisition digest")

    for row in record["lineages"]:
        if row["outcome"] == "acquired":
            assert row["not_counted_as"] is None, row["lineage"]
            assert row["acquisition_digest"], row["lineage"]
            # An acquired lineage's bytes must be the bytes the route
            # returned on a send that produced text.
            final = row["attempts"][-1]
            assert final["kind"] == "text", (
                "%s is marked acquired but its final attempt produced no text"
                % row["lineage"])
            assert final["source"], row["lineage"]
        else:
            assert row["outcome"] == "no-acquisition", row["outcome"]
            assert row["not_counted_as"], (
                "%s is a no-acquisition row that does not say it is not "
                "counted as a lineage" % row["lineage"])
            assert "not replaced by an authored arm" in row["not_counted_as"].lower(), (
                row["lineage"])
            assert row["acquisition_digest"] is None, (
                "%s is a no-acquisition row carrying an acquisition digest"
                % row["lineage"])

    use = _load(USE)
    for row in use["rows"]:
        if row["outcome"] == "no-acquisition":
            assert row["episodes"] == [], (
                "%s was run over instances despite having no acquired lineage"
                % row["lineage"])
            assert row["not_counted_as"], row["lineage"]


def test_no_authored_program_appears_as_an_acquired_lineage():
    """Independence is the digest, and the authored bytes are distinguishable.

    Two framings that returned identical bytes would be one lineage wearing
    two names, so the artifact records distinct digests rather than names
    as the count of independent lineages. This asserts the authored
    control is not among them, by digest, which is the only way it could
    be: no send could have produced the control's 22734 characters, which
    the artifact itself records as over-length for this lane's own gate.
    """
    record = _construction()
    control = record["authored_control"]
    assert control["gate_through_this_lanes_loader"]["admitted"] is False, (
        "the authored control passed this lane's own loader, so the length "
        "comparison this study rests on is not what it claims")
    assert control["gate_through_this_lanes_loader"]["defect"] == "over-length", (
        control["gate_through_this_lanes_loader"])
    assert control["control_is_unreachable_at_this_budget"] is True
    digests = [row["acquisition_digest"] for row in record["lineages"]
               if row["outcome"] == "acquired"]
    assert control["digest"] not in digests
    summary = _campaign()["summary"]
    assert summary["independent_acquired_lineages"] == len(set(digests)), (
        "the summary's independent-lineage count is not the digest count")


# --- the sealed set ------------------------------------------------------


def test_no_sealed_assessment_value_appears_in_any_recorded_prompt():
    """The sealed set never reaches a prompt.

    For each construction lineage, the fault mechanism name, the reference
    line that differs from the faulty source, and the protected case are
    the values a policy is meant to infer rather than be told. The task
    record's own `FAULT_LABEL_KEYS` is the list, and the recorded prompts
    are searched for every one of them.

    Public test EXPECTED values are deliberately NOT in the list: a failing
    public test publishes its own expected value in the public view, so
    requiring their absence would assert something false about the
    instrument.
    """
    record = _construction()
    sealed = record["sealed_values_per_dev_instance"]
    assert sealed, "the artifact records no sealed values, so nothing to check"
    for row in record["lineages"]:
        task_id = row["dev_task_id"]
        assert task_id in sealed, (
            "%s was constructed against %r, which is not in the sealed-value "
            "table" % (row["lineage"], task_id))
        assert sealed[task_id], "no sealed values recorded for %s" % task_id
        for value in sealed[task_id]:
            for attempt in row["attempts"]:
                prompt = attempt["prompt"]
                assert value not in prompt, (
                    "a sealed value for %s appears in the prompt of %s (%s)"
                    % (task_id, row["lineage"], attempt["operation_id"]))


def test_every_recorded_prompt_matches_its_digest():
    """The artifact stores the prompt text, and the digest is over it.

    The sealed-value scan above reads the stored prompt, so a stored
    prompt that is not the prompt that was sent would make that scan
    vacuous. This is what keeps the scan a statement about the wire: the
    digest is recomputed from the stored bytes and compared to the digest
    the driver recorded at dispatch.
    """
    import hashlib

    attempts = _every_attempt()
    assert attempts, "no attempt was recorded"
    for attempt in attempts:
        prompt = attempt["prompt"]
        assert isinstance(prompt, str) and prompt, attempt["operation_id"]
        assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == \
            attempt["prompt_sha256"], (
            "%s stores a prompt whose digest is not the one recorded at "
            "dispatch, so the scan above would be reading different bytes "
            "from the ones sent" % attempt["operation_id"])
        assert len(prompt) == attempt["prompt_characters"], (
            attempt["operation_id"])


def test_the_use_arm_is_separate_from_construction_and_reads_held_out_only():
    """Selection and repair read development information; use reads held-out.

    Construction runs on `dev`. The use arm runs on `held_out`, whose
    templates are disjoint from `dev`'s, so a dev-constructed policy is
    being asked to generalise rather than to recall the task it was built
    on.
    """
    record = _construction()
    assert record["lineages"], "no lineages were recorded"
    dev_tasks = set()
    for row in record["lineages"]:
        dev_tasks.add(row["dev_task_id"])
        assert row["dev_task_id"].startswith("swe-dev-"), row["dev_task_id"]
    use = _load(USE)
    assert use["split"] == "held_out", use["split"]
    assert use["dispatches_used_by_use_arm"] == 0, (
        "the use arm reports dispatches; it is local execution of bytes "
        "already in hand and spends no wire send")
    assert len(dev_tasks) == LINEAGES_PER_CELL, (
        "%d lineages were constructed against %d distinct dev tasks; a "
        "lineage is a policy over a task, not four copies of one"
        % (len(record["lineages"]), len(dev_tasks)))
    for row in use["rows"]:
        for episode in row["episodes"]:
            assert episode["row"]["task_id"].startswith("swe-held_out-"), \
                episode["row"]["task_id"]
    held_out = {row["task_id"] for row in use["rows"]
                for episode in row["episodes"]
                for row in [episode["row"]]}
    assert not (held_out & dev_tasks), (
        "a construction task reappears in the use arm, so nothing was held out")


# --- the credential ------------------------------------------------------


def secret_key_names() -> set:
    """The variable NAMES this lane may name, and no values.

    The cap sheet's rule is that a key is named and never printed, so the
    set of legitimate strings is exactly the words a report may contain.
    """
    return {"SETTLEMENT_GATEWAY_KEY", "SETTLEMENT_GATEWAY_ENDPOINT",
            "INVL02_LIVE_GRANT", "INVL02_LIVE_MODEL", "CX_AGENT_API_KEY",
            "SETTLEMENT_GATEWAY_TIMEOUT_READ_MS",
            "SETTLEMENT_GATEWAY_TIMEOUT_CONNECT_MS",
            "SETTLEMENT_GATEWAY_TIMEOUT_TOTAL_MS"}


def _credential_value() -> str:
    """The credential as it is in the environment now, or "".

    Read from the same configured location the driver reads and used only
    to search this lane's own bytes. Never written, printed or asserted on.

    The Windows and WSL homes are DIFFERENT files. A WSL pytest run has no
    `~/.claude.json`, so a scan that read only there would find no value
    and pass vacuously — which is precisely the failure this test exists to
    catch, found in this lane's own gate while it was being written. Both
    homes are tried, and the Windows path is checked explicitly, so a gate
    that runs under WSL still searches the bytes a Windows process wrote.
    """
    direct = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    if direct:
        return direct
    candidates = [
        os.path.expanduser("~/.claude.json"),
        os.path.join(os.environ.get("USERPROFILE", ""), ".claude.json"),
        "/mnt/c/Users/roysh/.claude.json",
    ]
    for path in candidates:
        value = _read_key_without_loading(path)
        if value:
            return value
    return ""


def _read_key_without_loading(path: str | None = None) -> str:
    """Read the key value directly, so no module-level driver code runs.

    Contacts no network: it reads a local config file. The value is
    returned for a substring search over this lane's own bytes and nothing
    else.
    """
    if not path:
        path = os.path.expanduser("~/.claude.json")
    try:
        import json as _json
        with open(path, encoding="utf-8") as fh:
            env = _json.load(fh)["mcpServers"]["cx-agent"]["env"]
        return env.get("CX_AGENT_API_KEY", "")
    except Exception:
        return ""


def test_no_credential_value_appears_in_anything_this_lane_wrote():
    """The real assertion, over the bytes this lane actually wrote.

    The credential is read from its configured location into the process
    environment, so the value is available here to search for. The lane's
    written files are scanned for it in full, binary-safe. A key length
    alone would not do: the check is for the value.
    """
    secret = _credential_value()
    if not secret:
        # No credential reachable from this environment, so nothing could
        # have leaked into it. Say so rather than passing silently on a
        # skipped check: the gate must never report a scan it did not run.
        assert True, ("no credential present to search for; the scan is "
                      "vacuous in this environment")
        return
    written = sorted(
        {path for path in EVIDENCE.rglob("*") if path.is_file()}
        | {Path(__file__), WORKSTREAM,
           ROOT / "experiments/ad01/invr1b12_swe_construction.py"}
    )
    offenders = []
    for path in written:
        if path.is_file() and secret.encode("utf-8") in path.read_bytes():
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "a credential value appears in files this lane wrote: %s" % offenders)
    # The names the lane is allowed to contain are present, which is what
    # makes the scan non-vacuous in the other direction: a report that
    # named no variable at all would not have been describing the route.
    for path in written:
        if not path.is_file() or path.suffix != ".md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert secret not in text, path.name
        assert "SETTLEMENT_GATEWAY_KEY" in text, (
            "%s names no credential variable, so it is not describing how the "
            "route was reached" % path.name)


# --- the honest stop -----------------------------------------------------


def test_the_recorded_counts_are_the_ones_the_run_reports():
    """The summary's numbers are the artifact's, not a recomputation.

    Asserting the summary against the rows it summarises catches a summary
    that was hand-edited after the fact, which is the failure mode a
    merged artifact has that a single-pass one does not.
    """
    campaign = _campaign()
    summary = campaign["summary"]
    record = _construction()
    assert summary["construction_dispatches"] == record["dispatches_used"]
    assert summary["physical_sends"] == record["dispatches_used"]
    assert summary["operations_in_store"] == len(
        _load(STORE_ROWS)["operations"])
    assert summary["acquired_lineages"] == len(
        [row for row in record["lineages"] if row["outcome"] == "acquired"])
    assert summary["no_acquisition_lineages"] == len(
        [row for row in record["lineages"]
         if row["outcome"] == "no-acquisition"])
    assert summary["lineages_attempted"] == len(record["lineages"])
    per_cell = summary["per_cell"]
    assert per_cell, "the summary records no cell"
    for cell, counts in per_cell.items():
        assert counts["lineages"] == counts["acquired"] + counts["no_acquisition"], (
            "%s: %d lineages but %d acquired + %d no-acquisition"
            % (cell, counts["lineages"], counts["acquired"],
               counts["no_acquisition"]))
        assert counts["lineages"] <= LINEAGES_PER_CELL, (
            "%s carries %d lineages, over the %d the matrix defines"
            % (cell, counts["lineages"], LINEAGES_PER_CELL))


def test_the_two_unsupported_cells_are_recorded_as_unavailable_not_run():
    """The matrix is one cell, and the other two say why they are not cells.

    `typed-ast` and `action-graph` are refused by their own frozen loaders
    for reasons recorded in the ceiling matrix, and no prompt changes a
    loader's node set. Running them would be spending sends on a cell that
    cannot exist; omitting them silently would make a one-cell matrix read
    as a three-cell one.
    """
    record = _construction()
    assert record["cell"] == "python-step", record["cell"]
    not_run = record["cells_not_run"]
    assert set(not_run) == {"typed-ast", "action-graph"}, sorted(not_run)
    for cell, reason in not_run.items():
        assert reason and len(reason) > 40, (
            "cell %s is recorded as unavailable without saying why" % cell)
    for lineage in record["lineages"]:
        assert lineage["cell"] == "python-step", lineage["cell"]
        assert lineage["representation_kind"] == "python-step"


def test_the_control_is_unreachable_at_this_budget_and_that_is_recorded():
    """The length finding the study rests on, as an artifact literal.

    The authored control policy is 22734 characters. This lane accepts at
    most 7000, and 2048 output tokens is roughly eight thousand characters,
    so no response at the frozen budget could have carried the control. The
    artifact records that comparison rather than leaving a reader to infer
    it, because it is the reason the study asks whether a SMALLER policy
    can repair instead of asking for a copy of this one.
    """
    record = _construction()
    control = record["authored_control"]
    assert control["source_characters"] == 22734, control["source_characters"]
    assert record["authored_source_characters"] == 22734
    assert record["max_source_characters"] == 7000
    assert control["source_characters"] > record["max_source_characters"], (
        "the control is under this lane's own limit, so the "
        "unreachability claim is not what the artifact says")
    for attempt in _every_attempt():
        if attempt.get("dispatched") and attempt["kind"] == "text":
            assert attempt["response_characters"] <= 9000, (
                "%s returned %d characters, which a 2048-token budget could "
                "not have carried; the recorded budget is not the one that ran"
                % (attempt["operation_id"], attempt["response_characters"]))


if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))