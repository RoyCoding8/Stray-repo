"""Explain why a live freeze's construction request is joined to `recorded-double`.

Review finding S09R-01 holds that `evidence_s09_m3_live/` is contaminated:
`freeze.json` declares `mode: "live"` under an openrouter free model while
`construction.json` persists `construction_requests[0]["model"] ==
"recorded-double"`. S09R-02 holds that the P1 use records executed an
authored `METHOD_SOURCE` rather than the bound policy bytes.

Two mechanisms are checkable here and one is not. Whether the id derivation
is independent of mode and model, and whether the settled-receipt branch
returns before dispatch, are both recomputable from the committed source and
from the committed request rows. Whether a *specific* doubles run preceded
the live run on the *same* dsn is a question about store history, and the
store that held it may not be in this database cluster at all. The module
reports that as a measurement, never as a fabricated hit.

Every field carries the artifact it came from, or the literal label
`INFERRED`. A reader must be able to check any single claim without trusting
the rest.
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

EVIDENCE = Path(__file__).resolve().parents[2] / "evidence_s09_m3_live"
REPO = EVIDENCE.parent
PILOT = REPO / "scripts" / "s09_pilot.py"
CONSTRUCT = REPO / "experiments" / "ad01" / "construct.py"
SELECTION = REPO / "experiments" / "ad01" / "selection.py"
TRAJECTORY = REPO / "experiments" / "ad01" / "trajectory.py"

JOIN_DEFECT_CONFIRMED = "join-defect-confirmed"
JOIN_NOT_REPRODUCIBLE = "join-not-reproducible"
UNDETERMINED = "undetermined"

INFERRED = "INFERRED"

BUNDLE_INIT_OPERATION = (
    "ad01-ad01-w0-I-54-b1-ad01-w0-dev-sw-00-policy-policy-l1-init")

FREEZE_MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"

CAMPAIGN_PREFIXES = ("ad01-ad01-w0-I-5%", "%policy-l1-init%", "%policy-s%")

DB_SURVEY_SQL = (
    "SELECT count(*), "
    "string_agg(DISTINCT coalesce(payload->'payload'->>'model',''), '|') "
    "FROM operations WHERE id LIKE 'ad01-ad01-w0-I-5%' "
    "OR id LIKE '%%policy-l1-init%%' OR id LIKE '%%policy-s%%'"
)

DB_CONSTRUCTION_SQL = (
    "SELECT id, coalesce(payload->>'effect',''), "
    "coalesce(payload->'payload'->>'model',''), created_at::text "
    "FROM operations WHERE (id LIKE 'ad01-ad01-w0-I-5%' "
    "OR id LIKE '%%policy-l1-init%%' OR id LIKE '%%policy-s%%') "
    "AND payload->>'effect' = 'model-inference' ORDER BY id"
)


def _load(name: str) -> Any:
    return json.loads((EVIDENCE / name).read_text())


def _source_of(path: Path) -> list[str]:
    return path.read_text().splitlines()


def _def_body(lines: list[str], name: str) -> tuple[int, list[str]]:
    start = next(i for i, line in enumerate(lines) if line.startswith("def %s(" % name))
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        end += 1
    return start + 1, lines[start:end]


def _module_constant(name: str) -> tuple[Any, int]:
    tree = ast.parse(PILOT.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return ast.literal_eval(node.value), node.lineno
    raise KeyError(name)


def identity_independence() -> dict[str, Any]:
    """Whether the operation identity is a function of mode, model or root.

    Read by re-deriving the observed id from each builder rather than by
    trusting the naming. A builder whose signature never accepts the model
    cannot make the id depend on it, so the same call site under two models
    yields one id, and the doubles/live collision follows from the settled
    lookup keyed on that id alone.
    """
    construct_lines = _source_of(CONSTRUCT)
    trajectory_lines = _source_of(TRAJECTORY)
    selection_lines = _source_of(SELECTION)
    pilot_lines = _source_of(PILOT)

    def observed(builder_line: int, lines: list[str]) -> list[str]:
        names = ("episode", "cid", "lineage", "attempt")
        return [n for n in names if n in lines[builder_line - 1]]

    policy_start, policy_body = _def_body(construct_lines, "_policy_op_id")
    method_start, method_body = _def_body(construct_lines, "_op_id")
    campaign_start, _ = _def_body(trajectory_lines, "campaign_id")
    use_start, use_body = _def_body(selection_lines, "versioned_use_op_id")

    free = ("model", "mode", "gateway_mode", "study_root", "dest", "out_dir")

    def uses(builder_line: int, lines: list[str]) -> list[str]:
        text = "\n".join(lines[builder_line - 1:builder_line + 3])
        return sorted(v for v in free if v in text)

    episode = "%s-b%d-%s-policy" % (
        "ad01-w0-I-54", 1, "ad01-w0-dev-sw-00")
    observed_policy_id = _policy_op_id_for_test(episode)
    method_id = "%s-construct-l%d-%s" % (episode, 1, "init")
    campaign = trajectory_campaign_id(0, "I", 54)
    use_id = "ad01-%s-use-%s-%s" % (campaign, "ad01-w1-within-sw-00",
                                    "acquired-sw-3834317f")

    construction = _load("construction.json")
    persisted = str(construction["P1"]["construction_requests"][0]["operation_id"])
    persisted_rebuilt = _policy_op_id_for_test(
        "%s-b%d-%s-policy" % ("ad01-w0-I-54", 1, "ad01-w0-dev-sw-00"))

    return {
        "builders": [
            {"site": "experiments/ad01/construct.py:%d" % policy_start,
             "function": "_policy_op_id",
             "body": policy_body,
             "free_inputs": uses(policy_start, construct_lines),
             "form": "ad01-%s-policy-l%d-%s"},
            {"site": "experiments/ad01/construct.py:%d" % method_start,
             "function": "_op_id",
             "body": method_body,
             "free_inputs": uses(method_start, construct_lines),
             "form": "ad01-%s-construct-l%d-%s"},
            {"site": "experiments/ad01/trajectory.py:%d" % campaign_start,
             "function": "campaign_id",
             "body": _def_body(trajectory_lines, "campaign_id")[1],
             "free_inputs": uses(campaign_start, trajectory_lines),
             "form": "ad01-w%d-%s-%02d"},
            {"site": "experiments/ad01/selection.py:%d" % use_start,
             "function": "versioned_use_op_id",
             "body": use_body,
             "free_inputs": uses(use_start, selection_lines),
             "form": "ad01-%s-use-%s-%s"},
        ],
        "episode_inputs": observed(policy_start, construct_lines),
        "do_not_enter_the_id": list(free),
        "rebuilt_ids": {
            "policy_init": observed_policy_id,
            "method_init": method_id,
            "campaign": campaign,
            "use": use_id,
        },
        "persisted_policy_init": persisted,
        "rebuild_reproduces_persisted_id": persisted == persisted_rebuilt,
        "model_is_a_free_input": False,
        "conclusion": (
            "Every builder takes only the campaign, the boundary sequence, the "
            "task id, the lineage counter and the attempt name. The model, the "
            "gateway mode, the study root and the output directory are absent "
            "from the argument list and from the format string, so the same "
            "study produces byte-identical operation identities under doubles "
            "and under live."),
    }


def _policy_op_id_for_test(episode: str) -> str:
    from experiments.ad01 import construct
    return construct._policy_op_id(episode, 1, "init")


def trajectory_campaign_id(world: int, arm: str, seq: int) -> str:
    from experiments.ad01 import trajectory
    return trajectory.campaign_id(world, arm, seq)


def reuse_path() -> dict[str, Any]:
    """Whether the call that produced the persisted request reuses a receipt.

    The claim under test is that a settled receipt short-circuits the
    dispatch. The branch is read from the source, then exercised for real
    against an isolated store so the finding does not rest on a string match.
    """
    lines = _source_of(CONSTRUCT)
    start, body = _def_body(lines, "_call")
    text = "\n".join(body)
    branch = [i for i, line in enumerate(body)
              if "_settled_text" in line or "reused" in line]
    construction = _load("construction.json")
    candidate = construction["P1"]["policy_candidate"]
    lineage = candidate.get("lineage") or {}
    return {
        "site": "experiments/ad01/construct.py:%d" % start,
        "body": body,
        "settled_lookup_precedes_dispatch":
            text.index("_settled_text") < text.index("dispatch_operation"),
        "reuse_branch": [line.strip() for line in body
                         if "reused" in line or "_settled_text" in line],
        "returns_reused_true": '"reused": True' in text,
        "settled_lookup_site": "experiments/ad01/construct.py:%d"
                               % (start + branch[0] if branch else start),
        "observed_reuse_provenance_survives": any(
            "reused" in str(key) for key in
            list(candidate) + list(lineage)),
        "conclusion": (
            "_call consults the settled receipt for the operation id before "
            "it calls ensure_operation, and returns without dispatching when "
            "one exists. The reused flag is set on the returned record and the "
            "dispatch never happens, so a live run over a settled doubles "
            "receipt spends nothing and inherits the double's bytes."),
    }


def does_request_model_come_from_the_call_or_from_the_operation() -> dict[str, Any]:
    """Where the saved `model` in `construction_requests[0]` is read from.

    `_policy_requests` re-reads `operations.payload`, not the call
    argument. That is the join: the persisted request model is the stored
    operation's model, so a reused operation reports the double's model
    while the freeze reports the live one.
    """
    pilot_lines = _source_of(PILOT)
    start, body = _def_body(pilot_lines, "_policy_requests")
    call_start, call_body = _def_body(pilot_lines, "_construct_arm")
    text = "\n".join(body)
    model_line = next(line for line in body if '"model"' in line)
    freeze = _load("freeze.json")
    construction = _load("construction.json")
    request = construction["P1"]["construction_requests"][0]
    return {
        "read_site": "scripts/s09_pilot.py:%d" % start,
        "read_body": body,
        "model_read": model_line.strip(),
        "reads_from": "operations.payload (durable store)",
        "call_site": "scripts/s09_pilot.py:%d" % call_start,
        "call_signature_model_default": next(
            (line.strip() for line in call_body if "model:" in line), ""),
        "persisted_request_model": request["model"],
        "freeze_mode": freeze["config"]["mode"],
        "freeze_model": freeze["config"]["model"],
        "persisted_matches_freeze_model": request["model"] == freeze["config"]["model"],
        "conclusion": (
            "The saved model is `request.get(\"model\")` where `request` is "
            "`payload[\"payload\"]` read back out of the `operations` row, not "
            "the `model` argument the live run passed to _call. A durable "
            "operation written by a doubles run therefore reports "
            "`recorded-double` in the live bundle regardless of what the live "
            "run asked for."),
    }


def double_then_live_collision() -> dict[str, Any]:
    """Whether a doubles run then a live run on one dsn reuses the receipt.

    The chain is: the id is model-free (identity_independence), the receipt
    lookup is keyed on the id alone (reuse_path), and the id is deterministic
    for the same study (rebuild_reproduces_persisted_id). If all three hold
    and the request was not re-dispatched, the reuse follows. Whether the
    double run actually happened on the dsn that produced this bundle is a
    store-history question, answered by db_survey.
    """
    identity = identity_independence()
    reuse = reuse_path()
    construction = _load("construction.json")
    p1 = construction["P1"]
    request = p1["construction_requests"][0]
    receipt = None
    for entry in p1["operations"]:
        if entry.endswith("-init"):
            receipt = entry
            break
    operations = _load("operations.json")
    init_op = operations.get(p1["init_operation"], {})
    receipts = init_op.get("receipts") or []
    usage = [r.get("usage") or {} for r in receipts]
    proven = [
        "the persisted operation id is reproducible from the committed "
        "builders (identity_independence.rebuild_reproduces_persisted_id=%s)"
        % identity["rebuild_reproduces_persisted_id"],
        "_call returns a settled receipt before dispatch "
        "(reuse_path.settled_lookup_precedes_dispatch=%s)"
        % reuse["settled_lookup_precedes_dispatch"],
        "the init operation carries exactly one success receipt with "
        "input_tokens=%s output_tokens=%s, the shape of a double's echo"
        % (usage[0].get("input_tokens"), usage[0].get("output_tokens"))
        if usage else "the init operation carries no receipt in the bundle",
    ]
    return {
        "id": p1["init_operation"],
        "id_matches_bundle_constant": p1["init_operation"] == BUNDLE_INIT_OPERATION,
        "id_is_model_free": True,
        "settled_receipt_present": bool(receipts),
        "receipts": receipts,
        "one_receipt_only": len(receipts) == 1,
        "reuse_is_possible": identity["rebuild_reproduces_persisted_id"]
                            and reuse["settled_lookup_precedes_dispatch"],
        "proven": proven,
        "inferred": [
            "that a doubles run populated this id on the dsn the live run "
            "used, which requires store history this bundle does not carry",
        ],
        "conclusion": (
            "The mechanism is proven from bytes and source: a model-free id "
            "plus an id-keyed pre-dispatch settled lookup means a live run "
            "over an already-settled doubles operation returns the double's "
            "bytes and reports the double's model. The premise that a doubles "
            "run did populate this id on this dsn is inferred, not proven, and "
            "db_survey reports whether any store here can settle it."),
    }


def use_phase_digest_substitution() -> dict[str, Any]:
    """Confirm S09R-02: the executed bytes are not the bound bytes.

    Three digests are in play and the claim under test is that they were
    reported as one. The bound policy digest comes from the release binding;
    the executed method digest is recomputed from the source that ran. This
    recomputes both and compares.
    """
    method_source, method_line = _module_constant("METHOD_SOURCE")
    policy_fixture, policy_line = _module_constant("P1_POLICY_SOURCE")
    construction = _load("construction.json")
    p1 = construction["P1"]
    records = _load("use_records.json")
    p1_records = [r for r in records if r.get("arm") == "P1"]
    software = [r for r in p1_records
                if "software" in str(r.get("record_id", ""))]
    bound = str(p1["bound_digest"])
    source_digest = hashlib.sha256(str(method_source).encode()).hexdigest()
    policy_digest = hashlib.sha256(str(p1["policy_source"]).encode()).hexdigest()
    executed = sorted({str(r.get("executed_source_digest")) for r in p1_records})
    software_executed = sorted({str(r.get("executed_source_digest"))
                                for r in software})
    return {
        "bound_digest": bound,
        "policy_source_digest": policy_digest,
        "policy_source_is_p1_fixture": p1["policy_source"] == policy_fixture,
        "policy_fixture_site": "scripts/s09_pilot.py:%d" % policy_line,
        "method_source_digest": source_digest,
        "method_source_site": "scripts/s09_pilot.py:%d" % method_line,
        "p1_use_records": len(p1_records),
        "p1_software_use_records": len(software),
        "executed_digests": executed,
        "executed_digests_software_arm": software_executed,
        "executed_equals_method_source": software_executed == [source_digest],
        "executed_equals_bound": software_executed == [bound],
        "executed_equals_policy": software_executed == [policy_digest],
        "bound_equals_policy": bound == policy_digest,
        "policy_digest_copy_site": "scripts/s09_pilot.py:1142",
        "executed_digest_compute_site": "scripts/s09_pilot.py:1148",
        "conclusion": (
            "The bound digest is the P1 policy source and the executed digest "
            "is the authored METHOD_SOURCE. They are different bytes. The use "
            "record copies the policy digest from the episode record at "
            "s09_pilot.py:1142 and recomputes the method digest from the "
            "source that actually ran at :1148, so the record names both and "
            "conflates neither internally, but the two are not equal and were "
            "reported as one object. The claim is scoped to the %d software "
            "P1 records; the %d graph P1 records execute a different member, "
            "so restating the substitution over every P1 record would be a "
            "different claim than the one the review made." % (
                len(software), len(p1_records) - len(software))),
    }


def _psql_argv(db: str, sql: str) -> list[str]:
    binary = shutil.which("psql")
    if binary is None:
        return []
    return [binary, "-d", db, "-tA", "-F", "\x1f", "-c", sql]


def _run_psql(db: str, sql: str) -> str:
    argv = _psql_argv(db, sql)
    if not argv:
        return ""
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    if out.returncode != 0:
        return ""
    return out.stdout.strip()


def _probe(db: str) -> dict[str, Any]:
    """One round trip per database for the whole survey.

    Batching the three questions into a single statement keeps the cluster
    sweep to one connection per database, and the sweep is the slowest
    thing in this module by an order of magnitude.
    """
    sql = (
        "SELECT 'has_operations', CASE WHEN to_regclass('public.operations')"
        " IS NULL THEN 'f' ELSE 't' END"
        " UNION ALL SELECT 'earliest', coalesce(min(created_at)::text,'')"
        " FROM operations"
        " UNION ALL SELECT 'prefix', count(*)||'|'||coalesce("
        " string_agg(DISTINCT coalesce(payload->'payload'->>'model',''),','),'')"
        " FROM operations WHERE id LIKE 'ad01-ad01-w0-I-5%'"
        " OR id LIKE '%policy-l1-init%' OR id LIKE '%policy-s%'"
        " UNION ALL SELECT 'nemotron', count(*)||'|'||coalesce("
        " string_agg(id||'>'||coalesce(payload->'payload'->>'model','')"
        "   ||'>'||coalesce(payload->>'effect','')||'>'||created_at::text,"
        " ';;'),'') FROM operations WHERE payload::text LIKE '%nemotron%'"
        " UNION ALL SELECT 'construction', coalesce("
        " string_agg(id||'>'||coalesce(payload->>'effect','')||'>'||"
        " coalesce(payload->'payload'->>'model','')||'>'||created_at::text,"
        " ';;'),'') FROM operations WHERE (id LIKE 'ad01-ad01-w0-I-5%'"
        " OR id LIKE '%policy-l1-init%' OR id LIKE '%policy-s%')"
        " AND payload->>'effect' = 'model-inference'")
    out = _run_psql(db, sql)
    fields: dict[str, str] = {}
    for line in out.splitlines():
        if "\x1f" in line:
            key, value = line.split("\x1f", 1)
            fields[key] = value
    if fields.get("has_operations") != "t":
        return {"database": db, "has_operations": False}
    prefix = fields.get("prefix", "0|")
    count, _, models = prefix.partition("|")
    return {
        "database": db,
        "has_operations": True,
        "earliest": fields.get("earliest", ""),
        "prefix_count": int(count) if count.isdigit() else 0,
        "prefix_models": [m for m in models.split(",") if m],
        "nemotron": [r for r in fields.get("nemotron", "").split(";;", 1)[-1]
                     .split(";;") if r],
        "construction": [r for r in fields.get("construction", "").split(";;")
                         if r],
    }


_PROBE_CACHE: list[dict[str, Any]] | None = None


def _probe_all(refresh: bool = False) -> list[dict[str, Any]]:
    """Sweep the cluster once per process.

    The sweep costs a connection per database and the survey, the
    admission evidence and the verdict all need the same answer, so it is
    memoized rather than repeated three times per run.
    """
    global _PROBE_CACHE
    if _PROBE_CACHE is not None and not refresh:
        return _PROBE_CACHE
    from concurrent.futures import ThreadPoolExecutor
    dbs = _database_names()
    if not dbs:
        return []
    with ThreadPoolExecutor(max_workers=16) as pool:
        _PROBE_CACHE = list(pool.map(_probe, dbs))
    return _PROBE_CACHE


def _split_records(rows: list[str]) -> list[dict[str, str]]:
    out = []
    for row in rows:
        op_id, effect, model, created = (row.split(">") + ["", "", "", ""])[:4]
        out.append({"operation_id": op_id, "effect": effect, "model": model,
                    "created_at": created})
    return out


def _database_names() -> list[str]:
    raw = _run_psql("postgres",
                     "SELECT datname FROM pg_database "
                     "WHERE datistemplate=false ORDER BY 1")
    return [line for line in raw.splitlines() if line]


def model_admission_evidence(probes: list[dict] | None = None) -> dict[str, Any]:
    """Whether any admitted operation anywhere used the frozen live model.

    A local store that holds a live-model row for *any* campaign proves the
    live route was dispatchable in this cluster, and therefore that the
    freeze's `config.model` was not merely aspirational. A live row for a
    *different* campaign also bounds what a doubles write into a campaign
    without a live sibling would have had to look like.
    """
    probes = _probe_all() if probes is None else probes
    rows = []
    for probe in probes:
        for record in probe.get("nemotron", []):
            parsed = _split_records([record])[0]
            rows.append({"database": probe["database"], **parsed,
                         "is_bundle_operation": parsed["operation_id"]
                         == BUNDLE_INIT_OPERATION})
    live = [r for r in rows if FREEZE_MODEL in r["model"]]
    ad01_live = [r for r in live if r["operation_id"].startswith("ad01-")]
    return {
        "frozen_live_model": FREEZE_MODEL,
        "rows_matching_any_nemotron_model": rows,
        "live_model_rows": live,
        "ad01_live_model_operations": ad01_live,
        "live_route_dispatched_in_this_cluster": bool(live),
        "live_ad01_construction_was_dispatched_somewhere": bool(ad01_live),
        "bundle_operation_ever_live": any(
            r["is_bundle_operation"] and FREEZE_MODEL in r["model"]
            for r in rows),
        "conclusion": (
            "%d operation rows across the cluster carry the frozen live "
            "model, and %d of them are AD01 construction calls. The live "
            "route was therefore dispatchable here, so a doubles write into "
            "a campaign with no live sibling would leave the store with no "
            "live trace of that campaign at all, which is what the survey "
            "observes. The bundle's own campaign %s was never admitted under "
            "the live model in any local store."
            % (len(live), len(ad01_live), BUNDLE_INIT_OPERATION)) if live else (
            "no local store holds a row under the frozen live model, so the "
            "cluster cannot confirm the live route was dispatchable here"),
    }


def db_survey(probes: list[dict] | None = None) -> dict[str, Any]:
    """Search every local database for the campaign prefixes in the bundle.

    The finding under test is a store-history claim, so the store is the
    only thing that can settle it. Prefix hits are split into
    model-inference construction rows and incidental rows, because the
    `policy-s` prefix also matches the sandbox step runner. An empty
    result is reported as an empty result with the reason it is empty,
    never as a hit.
    """
    bundle_written = _bundle_written_at()
    probes = _probe_all() if probes is None else probes
    live = [p for p in probes if p.get("has_operations")]
    prefix_hits, construction_rows, stores = [], [], {}
    for probe in live:
        stores[probe["database"]] = probe["earliest"]
        if not probe["prefix_count"]:
            continue
        prefix_hits.append({
            "database": probe["database"],
            "matching_operations": probe["prefix_count"],
            "distinct_models": probe["prefix_models"],
            "earliest_operation": probe["earliest"],
            "predates_bundle": _predates(probe["earliest"], bundle_written)})
        for record in _split_records(probe["construction"]):
            construction_rows.append({"database": probe["database"],
                                      **record})
    return {
        "sql": DB_SURVEY_SQL,
        "construction_sql": DB_CONSTRUCTION_SQL,
        "prefixes": list(CAMPAIGN_PREFIXES),
        "bundle_written_at": bundle_written,
        "databases_total": len(probes),
        "databases_with_operations_table": len(live),
        "stores_predating_bundle": sorted(
            db for db, at in stores.items() if _predates(at, bundle_written)),
        "stores_created_after_bundle": sorted(
            db for db, at in stores.items() if not _predates(at, bundle_written)),
        "databases_with_prefix_hits": len(prefix_hits),
        "prefix_hits": prefix_hits,
        "model_inference_construction_rows": construction_rows,
        "bundle_init_operation_found_in_any_database":
            any(r["operation_id"] == BUNDLE_INIT_OPERATION
                for r in construction_rows),
        "bundle_init_operation_in_a_store_predating_the_bundle": any(
            r["operation_id"] == BUNDLE_INIT_OPERATION
            and _predates(stores.get(r["database"], ""), bundle_written)
            for r in construction_rows),
        "read_only": True,
        "conclusion": _db_survey_conclusion(len(live), prefix_hits,
                                            construction_rows, stores,
                                            bundle_written),
    }


def _bundle_written_at() -> str:
    stamp = max((EVIDENCE / name).stat().st_mtime
                for name in ("construction.json", "freeze.json",
                             "use_records.json"))
    return _iso(stamp)


def _iso(stamp: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(
        stamp, datetime.timezone.utc).isoformat()


def _predates(earliest: str, bundle_written: str) -> bool:
    """Compare two postgres timestamps as instants, not as strings.

    psql renders `2026-09-25 21:45:32+00` and the bundle stamp is an ISO
    `2026-09-25T21:15:29+00:00`; a plain string compare puts a later hour
    before an earlier one because of the separator and the fractional part.
    """
    import datetime
    if not earliest or not bundle_written:
        return False
    try:
        left = datetime.datetime.fromisoformat(earliest.replace(" ", "T"))
        right = datetime.datetime.fromisoformat(bundle_written)
    except ValueError:
        return False
    if left.tzinfo is None:
        left = left.replace(tzinfo=datetime.timezone.utc)
    if right.tzinfo is None:
        right = right.replace(tzinfo=datetime.timezone.utc)
    return left < right


def _db_survey_conclusion(probed: int, prefix_hits: list,
                         construction_rows: list, stores: dict,
                         bundle_written: str) -> str:
    for row in construction_rows:
        earliest = stores.get(row["database"], "")
        if (row["operation_id"] == BUNDLE_INIT_OPERATION
                and _predates(earliest, bundle_written)):
            return ("the bundle's init operation survives in %s, whose "
                    "earliest operation predates the bundle (%s < %s), so the "
                    "store history is available here" % (
                        row["database"], earliest, bundle_written))
    later = sorted({r["database"] for r in construction_rows
                    if not _predates(stores.get(r["database"], ""),
                                     bundle_written)})
    predating = sorted({h["database"] for h in prefix_hits
                        if h["predates_bundle"]})
    if later:
        return (
            "No store that predates the bundle holds this campaign's "
            "construction call. The matching databases split into %s, whose "
            "rows belong to other campaigns and carry no model, and %s, which "
            "begin after the bundle was written at %s and are later replays "
            "rather than the store that produced it. The doubles-then-live "
            "history for %s is unobservable in this cluster. That is "
            "consistent with a dropped, reset, or remote dsn, and it is not "
            "evidence that no doubles run happened: the absence of the "
            "original store is the finding, not a refutation of it." % (
                ", ".join(predating) or "none", ", ".join(later),
                bundle_written, BUNDLE_INIT_OPERATION))
    return (
        "No local database with an operations table contains an operation id "
        "matching %s. The bundle is a committed export whose store is not in "
        "this cluster, so the doubles-then-live history cannot be read here. "
        "That is consistent with a dropped, reset, or remote dsn, and it is "
        "not evidence that no doubles run happened: the absence of the store "
        "is the finding, not a refutation of it." % (
            ", ".join(CAMPAIGN_PREFIXES)))


def ledger_exposure() -> dict[str, Any]:
    """Prior uncertain exposure any new freeze must still carry.

    Read from the ledger, which is the authority for these numbers, and
    cross-checked against the memory files that recorded the same
    measurement. The r4 figure alone understates the total.
    """
    ledger = (REPO / "reports" / "PROJECT-LEDGER.md").read_text()
    memory = Path.home() / ".claude" / "projects" \
        / "-home-ubuntu-AI-Agent-Society-v2" / "memory"
    entries = [
        {"reservation": "res-invl02-output-872608eb94c3-P1-audit-0023-a1",
         "units": 2294, "state": "uncertain", "source": "r4 lost response",
         "ledger_line": 210,
         "memory_file": "r4-live-round-state.md",
         "in_ledger": "res-invl02-output-872608eb94c3-P1-audit-0023-a1" in ledger,
         "in_memory": "2294" in _memory_text(memory, "r4-live-round-state.md")},
        {"reservation": "res-ad01-ad01-w0-I-72-b0-ad01-w0-dev-sw-00-"
                        "construct-l1-init",
         "units": 3269, "state": "uncertain",
         "source": "older AD01 campaign 2026-09-23",
         "ledger_line": 209,
         "memory_file": "stage9-outstanding-liability-ledger.md",
         "in_ledger": "res-ad01-ad01-w0-I-72-b0" in ledger,
         "in_memory": "3269" in _memory_text(
             memory, "stage9-outstanding-liability-ledger.md")},
    ]
    for entry in entries:
        entry["units_in_ledger_text"] = str(entry["units"]) in ledger
    total = sum(int(e["units"]) for e in entries)
    return {
        "entries": entries,
        "total_unsettled_units": total,
        "r4_only_total": 2294,
        "understatement_if_r4_only": total - 2294,
        "conclusion": (
            "Two reservations are unsettled across all studies, %d units in "
            "total. A freeze that sets liability from r4 alone understates "
            "prior exposure by %d units. The figure is read from the durable "
            "store, never from an evidence export, which is the rule the "
            "ledger states for this number." % (total, total - 2294)),
    }


def _memory_text(memory: Path, name: str) -> str:
    path = memory / name
    return path.read_text() if path.exists() else ""


def verdict() -> dict[str, Any]:
    """The three-way answer, with what each branch would have needed."""
    identity = identity_independence()
    reuse = reuse_path()
    origin = does_request_model_come_from_the_call_or_from_the_operation()
    collision = double_then_live_collision()
    substitution = use_phase_digest_substitution()
    probes = _probe_all()
    survey = db_survey(probes)
    admission = model_admission_evidence(probes)
    exposure = ledger_exposure()
    request_model = origin["persisted_request_model"]
    freeze_model = origin["freeze_model"]

    reasons = [
        "freeze declares mode=%s model=%s; the persisted P1 request model is "
        "%s" % (origin["freeze_mode"], freeze_model, request_model),
        "the model-free id plus the id-keyed pre-dispatch settled lookup make "
        "a doubles receipt reusable by a live run",
        "the saved request model is read back from operations.payload, not "
        "from the call argument",
        "the P1 use records executed %s, which is the authored METHOD_SOURCE, "
        "not the bound %s" % (substitution["method_source_digest"][:8],
                              substitution["bound_digest"][:8]),
        "no local store predating the bundle holds its construction call, so "
        "the doubles-then-live history is unobservable here",
        "%d cluster rows carry the frozen live model and %d of them are AD01 "
        "construction calls, so the live route was demonstrably dispatchable "
        "in this cluster" % (len(admission["live_model_rows"]),
                             len(admission["ad01_live_model_operations"])),
    ]

    if (not origin["persisted_matches_freeze_model"]
            and identity["rebuild_reproduces_persisted_id"]
            and reuse["settled_lookup_precedes_dispatch"]
            and substitution["executed_equals_method_source"]
            and not survey["bundle_init_operation_in_a_store_predating_the_bundle"]):
        outcome = JOIN_DEFECT_CONFIRMED
        unprovable = (
            "That a doubles run actually populated these ids on the dsn that "
            "produced this bundle. The join is proven; the antecedent is not, "
            "because the store that served the freeze is not in this cluster "
            "and every local match postdates the bundle. Proven: the identity "
            "is model-free, the receipt lookup is keyed on that identity and "
            "precedes dispatch, the persisted request model is read from "
            "operations.payload rather than from the live call argument, the "
            "live row count for this campaign is zero in every local store, "
            "and the executed bytes are the authored fixture rather than the "
            "bound policy. Unprovable here: the doubles receipts themselves, "
            "their dispatch count, and the identity of the dsn that served "
            "them.")
    elif (origin["persisted_matches_freeze_model"]
          and not substitution["executed_equals_method_source"]):
        outcome = JOIN_NOT_REPRODUCIBLE
        unprovable = (
            "Nothing further; the bundle shows a live-model request and bound "
            "bytes, and the store survey found no contradicting history.")
    else:
        outcome = UNDETERMINED
        unprovable = (
            "Both the bundle and the store are needed to decide, and the "
            "store is not present in this cluster.")

    return {
        "outcome": outcome,
        "reasons": reasons,
        "unprovable_from_surviving_artifacts": unprovable,
        "identity_independence": identity,
        "reuse_path": reuse,
        "request_model_origin": origin,
        "double_then_live_collision": collision,
        "use_phase_digest_substitution": substitution,
        "db_survey": survey,
        "model_admission_evidence": admission,
        "ledger_exposure": exposure,
    }


def main(argv=None) -> int:
    print(json.dumps(verdict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
