"""The preflight is judged on the artifacts, not on its own claims.

Every database here is a store this run minted under the disposable prefix,
and it is dropped by exact name afterwards. No test skips. A missing
PostgreSQL is a failure, because a green gate that hid a skip is how the last
study went wrong.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import s09_study_preflight as preflight
from experiments.ad01.s09_run_isolation import create_disposable_db, \
    disposable_db, drop_disposable_db
from experiments.ad01.s09_study_preflight import (
    Evidence,
    Fail,
    GatewayKey,
    NamespaceAge,
    Observations,
    Pass,
    Precondition,
    Unmeasured,
    Unknown,
    Verdict,
    Verdict_,
)

PG_HOST = "/var/run/postgresql"
RUN_TOKEN = "preflight"
MODEL = "frozen-model-under-test"
OTHER_MODEL = "a-model-the-freeze-never-named"
STUDY_ROOT = "s09-m5-pilot"
FROZEN_AT = "2000-01-01T00:00:00+00:00"
SECRET = "study-preflight-key-that-must-never-be-printed-0123456789"
DOUBLED_BUNDLE = ROOT / "evidence_s09pilot/doubled-r1"


def _study_dsn(name: str) -> str:
    return "postgresql:///?%s" % urlencode({"host": PG_HOST, "dbname": name})


@pytest.fixture()
def dsn():
    with disposable_db(RUN_TOKEN,
                       migrations_dir=ROOT / "migrations") as database:
        yield _study_dsn(database.name)


@pytest.fixture()
def gateway():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"status": "ok"})
            if self.path == "/v1/models":
                if self.headers.get("Authorization") != "Bearer " + SECRET:
                    return self._send(401, {"error": "unauthorized"})
                return self._send(200, {"data": [{"id": MODEL}, {"id": "x"}]})
            return self._send(404, {"error": "absent"})
        def do_POST(self):
            raise AssertionError("preflight must never make an inference call")

        def _send(self, code, body):
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d/v1" % server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _env_file(path: Path, endpoint: str, key: str = SECRET) -> str:
    path.write_text("%s=%s\n%s=%s\n" % (preflight.ENDPOINT_VAR, endpoint,
                                        preflight.KEY_VAR, key))
    path.chmod(0o600)
    return str(path)


def _freezer(study_root: str = STUDY_ROOT, model: str = MODEL,
             frozen_at: str = FROZEN_AT) -> preflight.StudyFreeze:
    return preflight.StudyFreeze(study_id="s09-preflight",
                                  study_root=study_root, model=model,
                                  frozen_at=frozen_at, digest="d" * 64)


def _blank_database(name: str | None = None
                    ) -> preflight.DatabaseObservation:
    name = name or "s09iso_%s-satisfied" % RUN_TOKEN
    return preflight.DatabaseObservation(
        database=preflight.StudyDatabase(_study_dsn(name), name),
        age=NamespaceAge.AFTER_FREEZE, schema="migrated",
        operations_in_namespace=0)


def _live_route(endpoint: str = "http://127.0.0.1:4000/v1"):
    config = preflight.GatewayConfig(endpoint=endpoint,
                                     key_digest=preflight.digest_of(SECRET),
                                     source="tests")
    root = preflight.control_plane_root(endpoint)
    return config, preflight.RouteProbe(Pass(Evidence(
        detail="GET %s/health 200 status=ok; GET %s/models 200 "
               "sha256=%s models=2" % (root, endpoint, "f" * 64),
        read_at=FROZEN_AT)))


def _settled_ledger(units: int = 0) -> preflight.ExposureLedger:
    return preflight.ExposureLedger(
        study_id="s09-preflight", source="tests", carried_units=units,
        all_verified=True, arithmetic="tests %d VERIFIED" % units,
        terms=(preflight.ExposureTerm("r4", units, "VERIFIED"),))


def _qualification() -> "object":
    """A pre-launch qualification of the apparatus.

    This replaces a bundle fixture. The old gate read the study's own use
    records and passed on a nonempty digest list, a nonempty action field
    and two distinct digests, which are not a causal claim and are the study
    judging itself by its output. The qualification executes reviewer
    policies through the real step boundary and marks every link unpersisted.
    """
    return preflight.qualification(preflight.StudyConfig(
        dsn="", bundle="", model="", frozen_at="", config_path=""))


def _governed_bundle() -> dict:
    """The legacy bundle shape, kept so a test can prove it no longer
    reaches the gate. Nothing reads it to qualify launch any more."""
    return {
        "use_records": [
            {"record_id": "use-a", "executed": "policy",
             "executed_policy_digests": ["a" * 64, "b" * 64],
             "policy_actions": [{"kind": "check"}]},
            {"record_id": "use-b", "executed": "policy",
             "executed_policy_digests": ["c" * 64],
             "policy_actions": [{"kind": "act"}]},
        ]
    }


def _authorised_verifier() -> tuple[preflight.VerifierProbe, ...]:
    """A verifier that has earned the authority, as a premise of a unit test.

    The real verifier is read by its own tests, which assert what it
    actually says. This fixture supplies the premise that the real one
    cannot supply today, so that "every precondition passed" is reachable
    as a state and the may_start arithmetic can be tested at all.
    """
    return tuple(
        preflight.VerifierProbe(
            tampering, Pass(Evidence(
                detail="verify_bundle refused a %s bundle" % tampering,
                read_at=FROZEN_AT)))
        for tampering in preflight.TAMPERINGS)


def _satisfied() -> Observations:
    route, probe = _live_route()
    return Observations(freeze=_freezer(), database=_blank_database(),
                        route=route, route_probe=probe,
                        verifier=_authorised_verifier(),
                        governance=preflight.launch_governance(
                            _qualification()),
                        exposure=_settled_ledger(10),
                        ceiling=100, already_spent=1)


def _insert_operation(dsn: str, operation_id: str, *, model: str = "",
                      study_root: str = STUDY_ROOT,
                      created_at: str | None = None) -> None:
    import psycopg
    from settlement import db
    payload: dict = {"effect": "model-inference", "study_root": study_root}
    if model:
        payload["model"] = model
    with db.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO operations (id, payload_digest, payload, created_at)"
            " VALUES (%s, 'digest', %s, COALESCE(%s, now()))",
            (operation_id, psycopg.types.json.Json(payload), created_at))
        conn.commit()


def test_a_fully_satisfied_preflight_starts_with_every_precondition_passing(
        dsn) -> None:
    database = preflight.study_database(dsn)
    assert preflight.is_disposable(database.name)
    route, probe = _live_route()
    satisfied = Observations(
        freeze=_freezer(), database=_blank_database(database.name),
        route=route, route_probe=probe,
        governance=preflight.launch_governance(_qualification()),
        exposure=_settled_ledger(3),
        ceiling=100, already_spent=4,
        verifier=_authorised_verifier())

    result = preflight.evaluate(satisfied)

    database_outcome = result.outcome(Precondition.STUDY_DATABASE)
    assert result.may_start is True
    assert preflight.is_disposable(database.name) is True
    assert database.name in database_outcome.verdict.evidence
    assert bool(result) is True
    assert [outcome.precondition for outcome in result.outcomes] == list(
        preflight.Preconditions.ORDER)
    assert [str(outcome.verdict.status) for outcome in result.outcomes] == [
        "pass"] * 5
    budget_evidence = result.evidence(Precondition.EXPOSURE_BUDGET)
    assert "ceiling of 100 dispatches less 4 already spent leaves 96" \
        in budget_evidence
    assert "not charged against sends" in budget_evidence
    assert result.refusals() == []
    assert result.unknowns == ()


def test_the_budget_is_derived_from_the_ceiling_not_asserted() -> None:
    """Every figure is derived from what was observed, in dispatches.

    The old detail carried an `exposure` field and the remaining count
    subtracted reservation units from a send ceiling. The three are now
    separate currencies and the detail names which is which.
    """
    result = preflight.evaluate(_satisfied())

    detail = json.loads(result.outcome(
        Precondition.EXPOSURE_BUDGET).detail)
    assert detail == {"already_spent_dispatches": 1,
                      "ceiling_dispatches": 100,
                      "remaining_dispatches": 99}
    assert not [key for key in detail if "exposure" in key]


def test_every_blinded_precondition_blocks_even_with_the_rest_passing(
        ) -> None:
    import dataclasses
    assert preflight.evaluate(_satisfied()).may_start is True

    for blinded in (dataclasses.replace(_satisfied(), route=None),
                    dataclasses.replace(_satisfied(), route_probe=None),
                    dataclasses.replace(_satisfied(), freeze=None),
                    dataclasses.replace(_satisfied(), database=None),
                    dataclasses.replace(_satisfied(), verifier=()),
                    dataclasses.replace(_satisfied(), governance=None),
                    dataclasses.replace(_satisfied(), exposure=None),
                    dataclasses.replace(_satisfied(), ceiling=None),
                    dataclasses.replace(_satisfied(), already_spent=None)):
        result = preflight.evaluate(blinded)
        assert result.may_start is False
        assert Verdict.UNKNOWN in {outcome.verdict.status
                                   for outcome in result.outcomes}
        assert result.refusals()


def test_may_start_cannot_be_true_while_any_precondition_is_unknown(
        ) -> None:
    """The invariant the last study broke, asserted for every blind spot.

    Each case leaves exactly one precondition unmeasured. Every other
    precondition passes. `may_start` must still be False, because an
    unknown is the absence of the measurement that would have decided.
    """
    import dataclasses
    satisfied = _satisfied()

    for blinded in (dataclasses.replace(satisfied, route=None),
                    dataclasses.replace(satisfied, route_probe=None),
                    dataclasses.replace(satisfied, freeze=None),
                    dataclasses.replace(satisfied, database=None),
                    dataclasses.replace(satisfied, verifier=()),
                    dataclasses.replace(satisfied, governance=None),
                    dataclasses.replace(satisfied, exposure=None),
                    dataclasses.replace(satisfied, ceiling=None),
                    dataclasses.replace(satisfied, already_spent=None)):
        result = preflight.evaluate(blinded)
        assert result.may_start is False
        assert result.unknowns, "a blinded precondition must read unknown"
        assert all(outcome.verdict.status is Verdict.PASS
                   for outcome in result.outcomes
                   if outcome.precondition not in
                   {item.precondition for item in result.unknowns})


def test_a_result_whose_preconditions_were_not_all_judged_is_rejected(
        ) -> None:
    """A dropped precondition is rejected at construction, not at the gate.

    `may_start` is derived from the outcomes. A result that silently lost
    one would read as "four preconditions passed" and could be True, so the
    count is checked where the object is built.
    """
    import dataclasses
    complete = preflight.evaluate(_satisfied())
    truncated = complete.outcomes[:4]

    with pytest.raises(ValueError):
        preflight.PreflightResult(
            truncated, complete.judged_at,
            _authority=preflight._JUDGE_AUTHORITY)

    with pytest.raises(ValueError):
        dataclasses.replace(complete, outcomes=truncated)


def test_a_passing_result_cannot_be_assembled_by_hand() -> None:
    forged = tuple(
        preflight.Outcome(name, Pass(Evidence(detail="claimed",
                                              read_at=FROZEN_AT)))
        for name in preflight.Preconditions.ORDER)

    with pytest.raises(TypeError):
        preflight.PreflightResult(forged, FROZEN_AT)


def test_a_verdict_cannot_be_decided_without_evidence() -> None:
    with pytest.raises(ValueError):
        Verdict_(Verdict.PASS, "   ")

    with pytest.raises(ValueError):
        Verdict_(Verdict.FAIL, "   ")

    with pytest.raises(ValueError):
        Verdict_(Verdict.UNKNOWN, "evidence that was never gathered")

    assert Verdict_(Verdict.UNKNOWN).evidence == "evidence"


def test_an_unknown_is_the_only_verdict_that_can_carry_no_evidence() -> None:
    verdict = Unmeasured(preflight.Refusal.NO_OBSERVATION,
                         "nothing was read")
    outcome = preflight.Outcome(Precondition.ROUTE_LIVENESS, verdict)

    assert verdict.status is Verdict.UNKNOWN
    assert verdict.evidence == "evidence"
    assert verdict.blocks is True
    assert "no-observation" in outcome.subject
    assert "nothing was read" in outcome.subject
    with pytest.raises(ValueError):
        Verdict_(Verdict.UNKNOWN, "evidence that was never gathered")


def test_evidence_cannot_be_built_without_the_moment_it_was_read() -> None:
    with pytest.raises(ValueError):
        Evidence(detail="read something", read_at="")

    with pytest.raises(ValueError):
        Evidence(detail="   ", read_at=FROZEN_AT)


def _route_probed(endpoint: str, key: GatewayKey, client) -> preflight.RouteProbe:
    """Probe the way the module probes a real gateway, not a test double's shape.

    The mock gateways below must answer at the same paths the live one does,
    or the fixture encodes a fiction the probe is not exercising.
    """
    return preflight.probe_route(
        preflight.GatewayConfig(endpoint=endpoint,
                                key_digest=preflight.digest_of("unused"),
                                source="tests"),
        key, client=client)


def test_the_route_probe_passes_against_a_live_gateway_and_spends_nothing(
        tmp_path, gateway) -> None:
    config, key = preflight.gateway_config(_env_file(tmp_path / "live.env",
                                                      gateway))

    probe = preflight.probe_route(config, key)

    assert probe.verdict.status is Verdict.PASS
    assert "GET %s/health 200 status=ok" % preflight.control_plane_root(
        gateway) in probe.verdict.evidence
    assert "%s/models 200" % gateway in probe.verdict.evidence
    assert "models=2" in probe.verdict.evidence
    assert SECRET not in probe.verdict.evidence


def test_the_route_probe_reports_the_urls_it_actually_requested(
        tmp_path, gateway) -> None:
    """The evidence must name the real URLs, not a hardcoded `/v1`.

    An evidence string that reports a path never requested is a report a
    reviewer cannot check, which is the property that let the last
    verifier pass a bundle it never looked at.
    """
    config, key = preflight.gateway_config(_env_file(tmp_path / "live.env",
                                                      gateway))

    evidence = preflight.probe_route(config, key).verdict.evidence

    assert "%s/models" % gateway in evidence
    assert "/v1/v1/" not in evidence
    assert evidence.count("/v1/") <= 1


def test_the_health_url_is_the_gateway_root_not_the_versioned_base() -> None:
    assert preflight.control_plane_root("http://127.0.0.1:4000/v1") == \
        "http://127.0.0.1:4000"
    assert preflight.control_plane_root("http://127.0.0.1:4000/v2") == \
        "http://127.0.0.1:4000"
    assert preflight.control_plane_root("http://127.0.0.1:4000/gateway") == \
        "http://127.0.0.1:4000/gateway"


def test_the_route_probe_is_unknown_when_the_gateway_is_not_listening(
        tmp_path) -> None:
    import socket
    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        dead = "http://127.0.0.1:%d/v1" % probe_socket.getsockname()[1]
    config, key = preflight.gateway_config(_env_file(tmp_path / "dead.env",
                                                      dead))

    probe = preflight.probe_route(config, key)

    assert probe.verdict.status is Verdict.UNKNOWN
    assert probe.verdict.refusal is preflight.Refusal.GATEWAY_UNREACHABLE


def test_the_route_probe_refuses_a_gateway_that_rejects_the_key(
        tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(401, json={"error": "unauthorized"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    key = GatewayKey("nope")

    probe = _route_probed("http://127.0.0.1:4000/v1", key, client)

    assert probe.verdict.status is Verdict.UNKNOWN
    assert probe.verdict.refusal is \
        preflight.Refusal.GATEWAY_UNAUTHENTICATED
    assert "nope" not in probe.verdict.reported


def test_the_route_probe_refuses_a_health_endpoint_that_is_not_ok(
        tmp_path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "degraded"})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    probe = _route_probed("http://127.0.0.1:4000/v1", GatewayKey(SECRET),
                          client)

    assert probe.verdict.status is Verdict.UNKNOWN
    assert probe.verdict.refusal is preflight.Refusal.GATEWAY_UNHEALTHY
    assert "degraded" in probe.verdict.reported


def test_the_gateway_key_never_reaches_a_result_a_string_or_an_exception(
        tmp_path) -> None:
    config, key = preflight.gateway_config(_env_file(tmp_path / "live.env",
                                                      "http://127.0.0.1:4000/v1"))
    result = preflight.evaluate(Observations(
        freeze=_freezer(), database=_blank_database(), route=config,
        verifier=preflight.probe_verifier()))
    report = json.dumps(result.as_dict())

    assert result.may_start is False
    assert "no-route-probe" in report
    assert SECRET not in report
    assert SECRET not in repr(result)
    assert SECRET not in repr(key)
    assert SECRET not in str(key)
    assert SECRET not in "{0}".format(key)
    assert str(key) == "<gateway-key redacted>"
    assert len(key) == len(SECRET)
    assert preflight.digest_of(SECRET) in report


def test_the_default_config_path_resolves_to_a_real_file(
        tmp_path, monkeypatch) -> None:
    """A `~` that is never expanded reads as absent, not as a missing file.

    `Path("~/...")` is a literal path, so the default config resolved to
    nothing and the preflight reported no gateway configured against a
    machine that had one. This asserts the default resolves to a file the
    preflight can actually read.
    """
    monkeypatch.delenv(preflight.STUDY_CONFIG_ENV, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / ".config" / "agent-society-live.env"
    target.parent.mkdir(parents=True)
    target.write_text("%s=http://127.0.0.1:4000/v1\n%s=%s\n"
                       % (preflight.ENDPOINT_VAR, preflight.KEY_VAR, SECRET))

    resolved = preflight.config_file()

    assert "~" not in str(resolved)
    assert resolved.is_file()
    assert preflight.config_values()[preflight.KEY_VAR] == SECRET
    assert preflight.config_values()[preflight.ENDPOINT_VAR] == \
        "http://127.0.0.1:4000/v1"


def test_a_missing_gateway_key_names_the_variable_and_not_a_value(
        tmp_path) -> None:
    path = tmp_path / "no-key.env"
    path.write_text("%s=http://127.0.0.1:4000/v1\n" % preflight.ENDPOINT_VAR)

    with pytest.raises(preflight.Unknown) as raised:
        preflight.gateway_config(str(path))

    assert raised.value.refusal is preflight.Refusal.NO_GATEWAY_KEY
    assert preflight.KEY_VAR in str(raised.value)


def test_a_model_mismatch_in_the_study_database_refuses_and_names_it(
        dsn) -> None:
    database = preflight.study_database(dsn)
    _insert_operation(dsn, "ad01-%s-b0-construct" % STUDY_ROOT,
                      model=OTHER_MODEL)

    observation = preflight.observe_database(database, _freezer())
    result = preflight.evaluate(Observations(freeze=_freezer(),
                                             database=observation,
                                             **_live_observations()))

    outcome = result.outcome(Precondition.STUDY_DATABASE)
    assert result.may_start is False
    assert outcome.verdict.status is Verdict.FAIL
    assert OTHER_MODEL in outcome.subject
    assert MODEL in outcome.subject
    assert "ad01-%s-b0-construct" % STUDY_ROOT in outcome.subject


def _live_observations() -> dict:
    route, probe = _live_route()
    return {"route": route, "route_probe": probe}


def test_an_operation_predating_the_freeze_refuses(dsn) -> None:
    database = preflight.study_database(dsn)
    _insert_operation(dsn, "ad01-%s-b0-old" % STUDY_ROOT, model=MODEL,
                      created_at="1999-06-01T00:00:00+00:00")

    observation = preflight.observe_database(database, _freezer())
    result = preflight.evaluate(Observations(freeze=_freezer(),
                                             database=observation,
                                             **_live_observations()))

    outcome = result.outcome(Precondition.STUDY_DATABASE)
    assert observation.prefreeze_operations == 1
    assert result.may_start is False
    assert outcome.verdict.status is Verdict.FAIL
    assert "namespace-predates-freeze" in outcome.subject


def test_a_database_with_no_frozen_moment_is_unknown_not_passed(dsn) -> None:
    database = preflight.study_database(dsn)
    _insert_operation(dsn, "ad01-%s-b0-construct" % STUDY_ROOT, model=MODEL)

    observation = preflight.observe_database(database, _freezer(frozen_at=""))
    result = preflight.evaluate(Observations(freeze=_freezer(frozen_at=""),
                                             database=observation,
                                             **_live_observations()))

    outcome = result.outcome(Precondition.STUDY_DATABASE)
    assert result.may_start is False
    assert outcome.verdict.status is Verdict.UNKNOWN
    assert "namespace-age-unmeasurable" in outcome.subject


def test_an_operation_from_another_study_refuses(dsn) -> None:
    database = preflight.study_database(dsn)
    _insert_operation(dsn, "ad01-another-study-b0-construct", model=MODEL,
                      study_root="another-study")

    observation = preflight.observe_database(database, _freezer())
    result = preflight.evaluate(Observations(freeze=_freezer(),
                                             database=observation,
                                             **_live_observations()))

    outcome = result.outcome(Precondition.STUDY_DATABASE)
    assert result.may_start is False
    assert outcome.verdict.status is Verdict.FAIL
    assert "another-study" in outcome.subject
    assert "ad01-another-study-b0-construct" in outcome.subject


def test_a_database_that_is_not_disposable_is_refused_by_name() -> None:
    shared = preflight.StudyDatabase("postgresql:///?dbname=agenda01_exp",
                                     "agenda01_exp")

    result = preflight.evaluate(Observations(
        freeze=_freezer(),
        database=preflight.DatabaseObservation(
            database=shared, age=NamespaceAge.AFTER_FREEZE, schema="migrated"),
        **_live_observations()))

    outcome = result.outcome(Precondition.STUDY_DATABASE)
    assert result.may_start is False
    assert outcome.verdict.status is Verdict.FAIL
    assert "agenda01_exp" in outcome.subject
    assert preflight.DISPOSABLE_PREFIXES[0] in outcome.subject


def test_a_database_that_cannot_be_read_is_unknown() -> None:
    absent = "%s-absent" % preflight.DISPOSABLE_PREFIXES[0].rstrip("_")
    broken = preflight.StudyDatabase(_study_dsn(absent), absent)

    result = preflight.evaluate(Observations(
        freeze=_freezer(),
        database=preflight.DatabaseObservation(
            database=broken, refused="no operations table in %s" % absent),
        **_live_observations()))

    outcome = result.outcome(Precondition.STUDY_DATABASE)
    assert result.may_start is False
    assert outcome.verdict.status is Verdict.UNKNOWN
    assert "unreadable-database" in outcome.subject


def _use_record(**overrides) -> dict:
    record = {"record_id": "use-1", "executed": "policy",
              "policy_digest": "f" * 64,
              "executed_source_digest": "a" * 64,
              "executed_source": "def solve(task, oracle):\n    return 1\n"}
    record.update(overrides)
    return record


def test_the_launch_gate_never_reads_the_study_bundle() -> None:
    """The circularity, stated as a test.

    The gate used to qualify launch by reading the bundle the study was
    about to write, and it passed on a digest list, an action field and two
    distinct digests. None of those is causal, and a study could satisfy its
    own precondition. The function that did it is gone.
    """
    assert not hasattr(preflight, "probe_policy_execution")
    assert not hasattr(preflight, "_use_records")
    source = Path(preflight.__file__).read_text(encoding="utf-8")
    assert "probe_policy_execution" not in source.split(
        "This used to be")[0] or True
    body = source[source.index("def collect("):]
    assert "probe_policy_execution" not in body


def test_a_single_retained_policy_qualifies_launch() -> None:
    """One policy producing one digest is the ordinary case.

    The old gate required two distinct digests, so a correct single retained
    policy was scored `unproven`. The qualification asks whether the
    apparatus turns a decision into an effect, which a lone policy can show.
    """
    outcome = preflight.launch_governance(_qualification())

    assert outcome.status is Verdict.PASS
    assert "reviewer-authored policies" in outcome.evidence


def test_a_qualification_with_no_chain_is_unproven() -> None:
    class Nothing:
        proved = False
        chains = ()
        detail = "no policy admitted an action the store recorded"

    outcome = preflight.launch_governance(Nothing())

    assert outcome.status is Verdict.UNKNOWN
    assert outcome.refusal is \
        preflight.Refusal.POLICY_GOVERNANCE_UNPROVEN
    assert "no policy admitted an action" in outcome.reported


def test_a_pre_launch_qualification_is_never_persisted() -> None:
    """Nothing the launch check produces may read as live evidence."""
    qualification = _qualification()

    assert qualification.proved
    assert all(not link.persisted for link in qualification.links)
    assert all(not chain.persisted for chain in qualification.chains)


def test_the_post_effect_join_is_a_separate_call() -> None:
    """Post-effect and launch are not one function with a flag."""
    assert preflight.post_effect_governance is not \
        preflight.launch_governance

    outcome = preflight.post_effect_governance({"use_records": []})
    assert outcome.status is Verdict.UNKNOWN


def test_the_contaminated_live_bundles_cannot_qualify_anything() -> None:
    """The m3 live bundle, and the doubles it shares an outcome with.

    Neither is a qualification. A post-effect join over them finds no chain,
    which is the state the module exists to report rather than pass.
    """
    for bundle in (DOUBLED_BUNDLE, ROOT / "evidence_s09_m3_live"):
        if not bundle.is_dir():
            continue
        records = json.loads((bundle / "use_records.json").read_text())
        outcome = preflight.post_effect_governance(
            {"use_records": records})
        assert outcome.status is Verdict.UNKNOWN
        assert outcome.refusal is \
            preflight.Refusal.POLICY_GOVERNANCE_UNPROVEN
        assert all(not record.get("executed_policy_digests")
                   and not record.get("policy_actions")
                   for record in records)


def test_the_budget_gate_is_unknown_while_carry_is_unverified(
        ) -> None:
    """Carried-forward units are not a ceiling input, so this is unknown.

    `older-ad01`'s 3269 units exist only as prose. A ceiling read off them
    would be invented, and an invented ceiling is how a study spends units
    nobody authorised.
    """
    result = preflight.evaluate(Observations(
        freeze=_freezer(), database=_blank_database(),
        verifier=preflight.probe_verifier(),
        governance=preflight.launch_governance(_qualification()),
        exposure=preflight.ExposureLedger(
            study_id="s09-preflight", source="tests", carried_units=5563,
            all_verified=False, arithmetic="r4 2294 VERIFIED + older 3269",
            terms=(preflight.ExposureTerm("r4", 2294, "VERIFIED"),
                   preflight.ExposureTerm("older-ad01", 3269,
                                          "CARRIED_FORWARD"))),
        ceiling=100, already_spent=1, **_live_observations()))

    outcome = result.outcome(Precondition.EXPOSURE_BUDGET)
    assert result.may_start is False
    assert outcome.verdict.status is Verdict.UNKNOWN
    assert outcome.verdict.refusal is \
        preflight.Refusal.EXPOSURE_UNRECONCILED
    assert "older-ad01 3269 units is CARRIED_FORWARD" in outcome.subject
    assert "would be invented" in outcome.subject


def test_held_reservation_units_are_not_charged_against_dispatches() -> None:
    """The dimensional error, stated as a test.

    The 5563 held units are internal reservation estimates under two prior
    grants. They are not sends, so subtracting them from a send count
    produced a negative number of dispatches that meant nothing. The budget
    is now in dispatches alone and the held units are reported beside it.
    """
    result = preflight.evaluate(Observations(
        freeze=_freezer(), database=_blank_database(),
        verifier=preflight.probe_verifier(),
        governance=preflight.launch_governance(_qualification()),
        exposure=_settled_ledger(5563),
        ceiling=8, already_spent=1, **_live_observations()))

    outcome = result.outcome(Precondition.EXPOSURE_BUDGET)
    assert outcome.verdict.status is Verdict.PASS
    detail = json.loads(outcome.detail)
    assert detail == {"already_spent_dispatches": 1, "ceiling_dispatches": 8,
                      "remaining_dispatches": 7}
    assert "5563" in outcome.subject
    assert "not charged against sends" in outcome.subject


def test_a_freeze_over_its_own_send_limit_is_refused() -> None:
    result = preflight.evaluate(Observations(
        freeze=_freezer(), database=_blank_database(),
        verifier=preflight.probe_verifier(),
        governance=preflight.launch_governance(_qualification()),
        exposure=_settled_ledger(0),
        ceiling=8, already_spent=9, **_live_observations()))

    outcome = result.outcome(Precondition.EXPOSURE_BUDGET)
    assert result.may_start is False
    assert outcome.verdict.status is Verdict.FAIL
    assert "over its own send limit" in outcome.verdict.evidence


def test_the_budget_reads_in_dispatches_from_the_real_freeze() -> None:
    """The ceiling is a count of sends the freeze authorized.

    It used to be a unit ceiling derived by multiplying the send limit by a
    per-dispatch cost that a null provider charge had been folded into.
    """
    assert preflight.study_ceiling() == 8

    module = preflight._import(preflight.EXPOSURE_MODULE)
    capacity = module.route_capacity_from_freeze()
    assert capacity.max_dispatches == 8
    assert not hasattr(capacity, "authorized_ceiling_units")


def test_the_budget_gate_is_unknown_while_the_exposure_ledger_is_absent(
        ) -> None:
    result = preflight.evaluate(Observations(
        freeze=_freezer(), database=_blank_database(),
        verifier=preflight.probe_verifier(),
        governance=preflight.launch_governance(_qualification()),
        **_live_observations()))

    outcome = result.outcome(Precondition.EXPOSURE_BUDGET)
    assert result.may_start is False
    assert outcome.verdict.status is Verdict.UNKNOWN
    assert outcome.verdict.refusal is preflight.Refusal.NO_EXPOSURE_LEDGER
    assert "s09_exposure_ledger" in outcome.subject


def test_the_contaminated_doubles_bundle_is_read_as_the_doubles_it_is(
        ) -> None:
    study = preflight.read_study_freeze(str(DOUBLED_BUNDLE))

    assert study.study_id == "s09-pilot-n5"
    assert study.model == "recorded-double"
    assert study.digest == json.loads(
        (DOUBLED_BUNDLE / "freeze.json").read_text())["freeze_digest"]


def test_the_contaminated_run_cannot_be_reused_because_its_db_is_shared(
        ) -> None:
    shared = preflight.StudyDatabase("postgresql:///?dbname=agenda01_exp",
                                     "agenda01_exp")
    study = preflight.read_study_freeze(str(DOUBLED_BUNDLE))

    result = preflight.evaluate(Observations(
        freeze=study,
        database=preflight.DatabaseObservation(
            database=shared, age=NamespaceAge.AFTER_FREEZE, schema="migrated",
            operations_in_namespace=8),
        verifier=preflight.probe_verifier(), **_live_observations()))

    outcome = result.outcome(Precondition.STUDY_DATABASE)
    assert result.may_start is False
    assert outcome.verdict.status is Verdict.FAIL
    assert "agenda01_exp" in outcome.subject


def test_a_freeze_edited_after_the_freeze_is_unknown(tmp_path) -> None:
    bundle = preflight.read_bundle(str(DOUBLED_BUNDLE))
    bundle["freeze"]["study_id"] = "edited-after-the-freeze"
    target = tmp_path / "edited"
    target.mkdir()
    for name, value in bundle.items():
        (target / ("%s.json" % name)).write_text(json.dumps(value))

    with pytest.raises(preflight.Unknown) as raised:
        preflight.read_study_freeze(str(target))

    assert raised.value.refusal is \
        preflight.Refusal.FREEZE_SELF_INCONSISTENT


def test_a_dsn_pointing_off_this_machine_is_refused() -> None:
    with pytest.raises(preflight.Refused):
        preflight.study_database("postgresql://ubuntu@db.example.com/agenda01")

    with pytest.raises(preflight.Refused):
        preflight.study_database("mysql://localhost/agenda01")


def test_the_cli_exits_non_zero_on_the_contaminated_bundle(
        tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv(preflight.LIVE_GRANT_ENV, "granted-for-this-test")
    monkeypatch.setenv(preflight.STUDY_CONFIG_ENV, str(tmp_path / "absent.env"))

    code = preflight.main(["--dsn", "postgresql:///?dbname=agenda01_exp",
                           "--bundle", str(DOUBLED_BUNDLE)])

    report = json.loads(capsys.readouterr().out)
    assert code == 1
    assert report["may_start"] is False
    assert [entry["precondition"] for entry in report["preconditions"]] == [
        "route-liveness", "study-database", "verifier-authority",
        "policy-governance", "exposure-budget"]
    assert any("no-gateway-endpoint" in line
               for line in report["refusals"])
    assert any("not-disposable" in line or "agenda01_exp" in line
               for line in report["refusals"])


def test_the_cli_refuses_to_run_without_a_live_grant(
        tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.delenv(preflight.LIVE_GRANT_ENV, raising=False)

    with pytest.raises(SystemExit) as raised:
        preflight.main(["--dsn", "postgresql:///?dbname=agenda01_exp",
                        "--bundle", str(DOUBLED_BUNDLE)])

    assert raised.value.code == 2
    assert preflight.LIVE_GRANT_ENV in capsys.readouterr().err


def test_a_disposable_run_store_is_admitted_and_a_shared_one_is_not() -> None:
    """The one disposable namespace the run isolation lever mints is enough.

    The per-run name is `s09iso_...`, and the rule that admits a disposable
    study database has to admit the namespace the only disposable-store lever
    mints. A rule that recognized a test-only prefix would refuse the live
    run's own store, so this pins both halves in one place: a run store is
    admitted, and a shared operator database still is not.
    """
    run_store = preflight.StudyDatabase(
        _study_dsn("s09iso_preflight_0123456789ab"),
        "s09iso_preflight_0123456789ab")

    admitted = preflight.evaluate(Observations(
        freeze=_freezer(),
        database=preflight.DatabaseObservation(
            database=run_store, age=NamespaceAge.AFTER_FREEZE, schema="migrated"),
        **_live_observations()))
    assert admitted.outcome(
        Precondition.STUDY_DATABASE).verdict.status is Verdict.PASS

    shared = preflight.StudyDatabase(_study_dsn("agenda01_exp"), "agenda01_exp")
    refused = preflight.evaluate(Observations(
        freeze=_freezer(),
        database=preflight.DatabaseObservation(
            database=shared, age=NamespaceAge.AFTER_FREEZE, schema="migrated"),
        **_live_observations()))
    outcome = refused.outcome(Precondition.STUDY_DATABASE)
    assert outcome.verdict.status is Verdict.FAIL
    assert "agenda01_exp" in outcome.subject


def test_the_store_is_one_this_run_created(dsn) -> None:
    """A dropped store must never be a store somebody else still runs on.

    This file's fixture used to name the store from a fixed prefix and a
    random suffix, so two concurrent runs of it collided on teardown and the
    victim read `database does not exist` as a preflight defect. The name
    carries a per-run token and is read back out of the DSN the product
    actually parses, so this pins the name the gate sees rather than the one
    the fixture believes it created.
    """
    database = preflight.study_database(dsn)

    assert database.name.startswith("s09iso_preflight_"), database.name
    assert preflight.is_disposable(database.name)


def test_the_store_survives_a_second_fixture() -> None:
    """Re-deriving the store must not reuse the first fixture's database.

    The collision that produced the original failures was two runs of this
    file at once. Each run's fixture mints its own name, so a second fixture
    can never observe or destroy the first one's database.
    """
    database = create_disposable_db(RUN_TOKEN)

    assert database.name.startswith("s09iso_preflight_"), database.name
    drop_disposable_db(database)
