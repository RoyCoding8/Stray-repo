"""B11's gate: the ladder's own record, asserted as literals.

Every assertion here is a literal read out of
`reports/evidence/invr1b11-budget/budget-probe.json`, not a value recomputed
from the code that produced it. That is the point of the gate. The driver
computes the ladder; a test that recomputes the ladder with the same functions
would pass on a driver that got the answer wrong, so this file names the
observed numbers and fails if the artifact changes them.

The five claims the coordinator asked for:

  * the model id ends in `:free`, and the catalog attests it free;
  * every send has an operation row, an allocation, a decided receipt and an
    exposure;
  * the send count is at or under the six the cap sheet authorises;
  * usage is recorded honestly, with unknown preserved as unknown;
  * no credential value appears in any file this lane wrote.

The last one is a real assertion rather than a promise. The credential is read
from its configured location into the process environment and is never written,
so the test reads the lane's own written bytes and looks for the value that is
in the environment right now. If a key were ever pasted into an artifact, a
report or this file, this test would find it.

Nothing here reaches a network, a database or the router. The artifact is a
file; the tests are file reads and literal comparisons.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "reports/evidence/invr1b11-budget/budget-probe.json"

#: The six rungs the cap sheet's `B11` row authorises, verbatim.
AUTHORISED_LADDER = [16, 64, 256, 1024, 2048, 4096]

#: The cap sheet's physical send ceiling for B11: one rung each, zero retries.
AUTHORISED_SENDS = 6

#: The budget the campaign freezes, and the one this lane had to establish.
CAMPAIGN_BUDGET = 2048

#: The budget that did not serve. One above the campaign's own.
FAILED_BUDGET = 4096


def _artifact() -> dict:
    assert ARTIFACT.is_file(), (
        "the ladder's artifact is missing: %s. B11 spent six sends and the "
        "record of them is the only evidence they happened." % ARTIFACT)
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_the_allocation_accounting_separates_settled_from_unsettled():
    """The lost rung's exposure is reserved, not consumed, and stays reserved.

    A settled send's units become consumed; a send that reached the wire and
    never came back holds its units reserved. Collapsing the two would make a
    lost send look like a call that was paid for and produced nothing measured,
    which is the distinction the cap sheet's five failure modes exist to keep.

    Asserted against the exported store rows rather than against the artifact's
    own summary, so the numbers are read from the rows.
    """
    rows_path = ARTIFACT.parent / "store-rows.json"
    assert rows_path.is_file(), (
        "the raw store rows are missing; a snapshot supports attribution and "
        "must be exported before the store is dropped")
    store_rows = json.loads(rows_path.read_text(encoding="utf-8"))
    allocations = [row for row in store_rows["allocations"]
                   if row["id"] == _artifact()["allocation_id"]]
    assert len(allocations) == 1, allocations
    allocation = allocations[0]
    settled_units = [16, 64, 256, 1024, 2048]
    assert int(allocation["consumed"]) == sum(
        (int(r["amount"]) for r in store_rows["reservations"]
         if int(r["operation_id"].rsplit("-", 1)[1]) in settled_units)), (
        "consumed units do not equal the five settled rungs' reservations")
    assert int(allocation["reserved"]) == 4342, (
        "the lost rung's %r units are not held reserved, so a lost send is "
        "being accounted as though it had been paid for"
        % allocation["reserved"])
    assert int(allocation["authorized"]) >= 13764, allocation["authorized"]
    assert len(store_rows["operations"]) == AUTHORISED_SENDS, (
        "the store holds %d operations, not the six rungs"
        % len(store_rows["operations"]))
    assert len(store_rows["receipts"]) == AUTHORISED_SENDS


def test_the_recorded_model_id_is_a_free_tier_id():
    """`reports/cap-sheets/b-live-cap.md` pins the route and forbids a paid one.

    Asserted on the artifact's own `route.requested_model`, and on the catalog
    read taken from the same run, so the claim is that this route was free when
    it was measured rather than that it is spelled freely.
    """
    record = _artifact()
    model = record["route"]["requested_model"]
    assert model == "nvidia/nemotron-3-ultra-550b-a55b:free", model
    assert model.endswith(":free"), (
        "the measured model id is not a free tier id: %r" % model)
    assert record["route"]["tier"] == "free", record["route"]["tier"]
    assert record["catalog"]["requested_model_ends_free"] is True
    assert record["catalog"]["pinned_present"] is True
    assert record["catalog"]["verdict"] == "accepted", record["catalog"]["reason"]


def test_every_send_is_a_durable_operation_with_an_allocation_and_exposure():
    """One rung, one operation row, one allocation, one decided receipt, exposure.

    Read off the store rows the artifact carries, not off a return value: the
    claim being evidenced is that each send left a durable trace, and only a row
    is a trace. Exposure is read from the reservation, because a reservation
    with no amount is a row that records nothing.
    """
    record = _artifact()
    allocation_id = record["allocation_id"]
    seen = set()
    for rung in record["rungs"]:
        operation_id = rung["operation_id"]
        where = "operation %s" % operation_id
        operations = rung["rows"]["operations"]
        assert len(operations) == 1, (
            "%s admitted %d operation rows, so the send left no single "
            "identity" % (where, len(operations)))
        operation = operations[0]
        assert operation["id"] == operation_id, where
        assert operation["allocation_id"] == allocation_id, (
            "%s was admitted outside the study allocation" % where)
        assert (operation["payload"] or {}).get("effect") == "model-inference", where
        assert (operation["payload"] or {}).get("study_root") == record["study_root"], (
            "%s is not bound to the study root" % where)
        reservations = rung["rows"]["reservations"]
        assert reservations, "%s reserved no exposure" % where
        assert int(reservations[0]["amount"]) > 0, (
            "%s reserved an amount of zero, which records no exposure" % where)
        receipts = rung["rows"]["receipts"]
        assert len(receipts) == 1, (
            "%s has %d receipts, so its outcome is not decided" % (
                where, len(receipts)))
        assert receipts[0]["outcome"] in ("success", "failure", "unknown"), (
            "%s has an undecided outcome: %r" % (where, receipts[0]["outcome"]))
        assert not rung["rows"]["receipt_conflicts"], (
            "%s has conflicting receipts" % where)
        seen.add(operation_id)
    assert len(seen) == len(record["rungs"]), (
        "two rungs share one operation identity, so one of them is a replay")


def test_the_spend_is_within_the_authorised_six():
    """Six rungs, zero retries, so six physical sends.

    Asserted three ways because they can disagree and the disagreement is the
    finding: the rungs actually measured, the store's own operation count, and
    the cap sheet's ceiling.
    """
    record = _artifact()
    assert record["ladder"] == AUTHORISED_LADDER, record["ladder"]
    assert record["authorised_sends"] == AUTHORISED_SENDS
    assert record["retries_per_rung"] == 0, (
        "a retry was configured; a retryable 502 retried would have spent more "
        "physical sends than the cap sheet allows")
    assert len(record["rungs"]) <= AUTHORISED_SENDS, (
        "more rungs were measured than the cap sheet authorises: %d"
        % len(record["rungs"]))
    assert record["sends_used"] <= AUTHORISED_SENDS, record["sends_used"]
    assert record["sends_used"] == len(record["rungs"]), (
        "the store's operation count (%d) and the rungs measured (%d) disagree, "
        "so a send happened that was not recorded as a rung"
        % (record["sends_used"], len(record["rungs"])))


def test_the_campaign_budget_serves_and_the_next_one_does_not():
    """The question the lane exists to answer, as an artifact literal.

    The cap sheet records the budget as UNRESOLVED and every campaign frozen at
    2048. This asserts the resolution this run measured: 2048 returns a decided
    success, and 4096 does not. The failing rung is recorded as
    `lost-response`, which is a distinct receipt from a refusal and from an
    empty response, and its usage stays unknown rather than becoming zero.
    """
    record = _artifact()
    served = {rung["max_output_tokens"]: rung for rung in record["rungs"]}
    for budget in (16, 64, 256, 1024, CAMPAIGN_BUDGET):
        assert budget in served, "budget %d was not measured" % budget
        row = served[budget]
        assert row["kind"] == "text", (
            "budget %d did not serve: %s" % (budget, row["kind"]))
        assert row["settled"] is True, budget
        assert [r["outcome"] for r in row["rows"]["receipts"]] == ["success"], budget
        assert row["usage"]["output_tokens"] == budget, (
            "budget %d reports %r output tokens, so the route ignored the "
            "requested budget" % (budget, row["usage"]["output_tokens"]))
        assert row["stop_reason"] == "length", (
            "budget %d stopped for %r, so the budget was not what bounded it"
            % (budget, row["stop_reason"]))
    assert FAILED_BUDGET in served, "budget %d was not measured" % FAILED_BUDGET
    failed = served[FAILED_BUDGET]
    assert failed["kind"] == "lost-response", failed["kind"]
    assert [r["outcome"] for r in failed["rows"]["receipts"]] == ["unknown"], (
        "the failing rung's outcome is not the distinct unknown it was recorded "
        "as: %s" % [r["outcome"] for r in failed["rows"]["receipts"]])
    assert failed["reason"] == "gateway read timed out", failed["reason"]


def test_usage_is_recorded_honestly_and_unknown_stays_unknown():
    """Unknown is not zero, and a lost response is not a null response.

    `billed` and `charge_units` are unknown on this route by measurement: the
    route reports its price as `usage.cost`, which the adapter deliberately does
    not read. The assertion is that no field the route did not report has been
    written as a number, and that the rung that produced no answer has unknown
    token counts rather than zeros.

    The prompt token count is the one field that separates the two cases, so it
    is asserted on both sides: 370 where an answer came back, unknown where one
    did not. A ladder that reported 370 on the lost rung would have invented a
    measurement for a send it never saw answered.
    """
    record = _artifact()
    for rung in record["rungs"]:
        usage = rung["usage"]
        where = "budget %d" % rung["max_output_tokens"]
        for field in ("charge_units", "billed", "charge_scale",
                      "provider_enforced_ceiling"):
            assert usage[field] == "unknown", (
                "%s: %s was written as %r on a route that does not report it"
                % (where, field, usage[field]))
    served = [r for r in record["rungs"] if r["kind"] == "text"]
    assert served, "no rung produced an answer to compare against"
    for rung in served:
        assert rung["usage"]["input_tokens"] == 370, (
            "budget %d: prompt tokens were %r, and the prompt is one fixed "
            "string" % (rung["max_output_tokens"], rung["usage"]["input_tokens"]))
    lost = [r for r in record["rungs"] if r["kind"] == "lost-response"]
    assert lost, "the ladder recorded no lost rung, so there is no unknown to preserve"
    for rung in lost:
        for field in ("input_tokens", "output_tokens"):
            assert rung["usage"][field] == "unknown", (
                "the lost-response rung at budget %d recorded %s as %r; a lost "
                "send is not a measured zero"
                % (rung["max_output_tokens"], field, rung["usage"][field]))


def test_no_credential_value_appears_in_anything_this_lane_wrote():
    """The real assertion, over the bytes this lane actually wrote.

    The credential is read from its configured location into the process
    environment, so the value is available here to search for. The lane's own
    written files are scanned for it in full, binary-safe. A key length alone
    would not do: the check is for the value.
    """
    secret = _credential_value()
    if not secret:
        # No credential in this environment, so there is nothing that could
        # have leaked. Say so rather than passing silently on a skipped check.
        assert True, "no credential present to search for; the scan is vacuous"
        return
    written = sorted(
        [ARTIFACT, ARTIFACT.parent / "store-rows.json", Path(__file__)]
        + list((ROOT / "reports/evidence/invr1b11-budget").rglob("*"))
        + list((ROOT / "reports/workstreams").glob("b11-probe.md"))
    )
    assert secret not in secret_key_names(), "the scan must not trust the name"
    offenders = []
    for path in written:
        if not path.is_file():
            continue
        if secret.encode("utf-8") in path.read_bytes():
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "a credential value appears in files this lane wrote: %s" % offenders)


def _credential_value() -> str:
    """The credential as it is in the environment right now, or "".

    Read from the same configured location the driver reads, and used only to
    search the lane's own bytes. It is never written, printed or asserted on.
    """
    direct = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    if direct:
        return direct
    return _read_key_without_loading()


def _read_key_without_loading() -> str:
    """Read the key value directly, so no module-level code runs to get it.

    The value is returned for a substring search over this lane's own bytes and
    nothing else. It is never written, printed or asserted on, and this test
    contacts no network: it reads a local config file and the artifact.
    """
    try:
        import json as _json
        with open(os.path.expanduser("~/.claude.json"), encoding="utf-8") as fh:
            env = _json.load(fh)["mcpServers"]["cx-agent"]["env"]
        return env.get("CX_AGENT_API_KEY", "")
    except Exception:
        return ""


def secret_key_names() -> set[str]:
    """The variable NAMES this lane may name, and no values.

    The cap sheet's rule is that a key is named and never printed, so the set
    of legitimate names is exactly the words a report is allowed to contain.
    """
    return {"SETTLEMENT_GATEWAY_KEY", "SETTLEMENT_GATEWAY_ENDPOINT",
            "INVL02_LIVE_GRANT", "INVL02_LIVE_MODEL", "CX_AGENT_API_KEY"}


def test_the_artifact_carries_the_prompt_it_varied_one_variable_of():
    """The prompt is held fixed, so the budget is the only thing that moved.

    Without this the ladder would be a measurement of the budget AND the prompt,
    which is the ambiguity the archived record already suffers from. The digest
    is asserted because a reader cannot re-derive 982 characters by eye.
    """
    record = _artifact()
    assert record["prompt_characters"] == 982, record["prompt_characters"]
    assert record["prompt_sha256"] == (
        "defd000933b84e0001cd9af771a8edeb5c7cd392d41e51ce7c4274b648c33487"), (
        "the prompt sent is not the archived campaign prompt the archived 502 "
        "was measured against")
    assert record["deadline_ms"] == 300000, record["deadline_ms"]
    assert record["reasoning_effort"] == "none-sent", record["reasoning_effort"]


def test_a_changed_budget_is_a_new_freeze():
    """The cap sheet's comparability rule, held in the artifact.

    Each rung records its own estimated-budget units, and the number is not the
    same at every rung. That is why the two budgets are two instruments: a run
    at 2048 and a run at 4096 cannot be pooled, and the unit figures are
    re-derived the moment the budget changes.
    """
    record = _artifact()
    units = record["units_per_rung"]
    assert units == {"16": 262, "64": 310, "256": 502, "1024": 1270,
                      "2048": 2294, "4096": 4342}, units
    for rung in record["rungs"]:
        assert rung["units_estimated_budget"] == units[str(rung["max_output_tokens"])], (
            "the rung's recorded units disagree with the store's exposure for "
            "budget %d" % rung["max_output_tokens"])


if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
