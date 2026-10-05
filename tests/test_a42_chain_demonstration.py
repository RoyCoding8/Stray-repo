"""The chain, walked stage by stage, with the gaps named.

`test_inv_a_chain.py` asserts the seven arrows against durable rows and
`test_a40_admission_wired.py` proves the crash-and-resume identity. Neither
walks the chain as one run and reports where it stops, and neither reaches
the use half through `experiments.ad01.cli` -- the argv surface a
researcher types. This file enters there for the use and through
`run_campaign` for the acquisition, and records what each stage produced.

Two properties keep the walk from being a diagram. Every stage is read
from a row a finished process wrote, so a stage cannot report success from
memory; and the stages that did not happen are asserted as counts against
the tree's own behaviour, so a gap is a reported stage rather than an
omitted one.

The policy bytes are this file's own, so a failure here is about the chain
rather than about a neighbouring lane's fixture.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "a42chain"
SEQ = 42
TASKS = ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01", "ad01-w0-dev-sw-00"]
USE_TASK = "ad01-w0-within-sw-00"
CHARTER = {"objective": "reduce examples while preserving their witness",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 4, "diagnostic_queries": 16, "model_calls": 20}

# The policy that walks the chain: probe, then construct, then use. It is
# this file's bytes and nothing else's.
STEP_KINDS = ("diagnose", "construct_method", "use_method")

WALK_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    stage = int(state.get('stage', 0))\n"
    "    if stage == 0:\n"
    "        return {'action': {'kind': 'diagnose', 'target': target,\n"
    "                           'inputs': {'diagnostic': 'software',\n"
    "                                      'unknown': 'does the seed hold',\n"
    "                                      'question': 'why this verdict'},\n"
    "                           'evidence_refs': [],\n"
    "                           'requested_resources': {'queries': 1}},\n"
    "                'state': {'stage': 1}}\n"
    "    if stage == 1:\n"
    "        return {'action': {'kind': 'construct_method',\n"
    "                           'target': target,\n"
    "                           'inputs': {'method_id': '', 'max_queries': 4},\n"
    "                           'evidence_refs': [],\n"
    "                           'requested_resources': {'queries': 4}},\n"
    "                'state': {'stage': 2}}\n"
    "    methods = list(view.get('eligible_methods') or [])\n"
    "    if not methods:\n"
    "        return {'action': {'kind': 'stop', 'target': target,\n"
    "                           'inputs': {'reason': 'nothing retained yet'},\n"
    "                           'evidence_refs': [],\n"
    "                           'requested_resources': {}},\n"
    "                'state': {'stage': 2}}\n"
    "    return {'action': {'kind': 'use_method', 'target': target,\n"
    "                       'inputs': {'method_id': methods[0],\n"
    "                                  'max_queries': 4},\n"
    "                       'evidence_refs': [],\n"
    "                       'requested_resources': {'queries': 4}},\n"
    "            'state': {'stage': 3}}\n"
)

ACQUIRED_METHOD = (
    "def carried(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method='greedy',"
    " max_queries=max_queries)\n"
)

USE_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    method = list(view.get('eligible_methods') or ['%s'])[0]\n"
    "    return {'action': {'kind': 'use_method', 'target': target,\n"
    "                       'inputs': {'method_id': method,\n"
    "                                  'max_queries': 4},\n"
    "                       'evidence_refs': [],\n"
    "                       'requested_resources': {'queries': 4}},\n"
    "            'state': {'selected': method}}\n"
)


@pytest.fixture(scope="module")
def store():
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = iso.create_disposable_db(RUN_TOKEN, admin_dsn=admin_dsn,
                                        migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database, admin_dsn=admin_dsn)


class Constructor:
    """The offline fixture gateway. No network, no credentials."""

    def __init__(self, source=ACQUIRED_METHOD):
        from settlement.gateway import Usage

        self.calls = []
        self.source = source
        self.usage = Usage(input_tokens=10, output_tokens=20)

    def check_discovery(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse

        self.calls.append(request)
        return ModelResponse(
            request.operation_id,
            json.dumps({"entry": self.source, "notes": "a42 walk"}),
            {}, self.usage, "stop")

    def cancel(self, operation_id):
        return False


def _cli(*args: str) -> str:
    """`experiments.ad01.cli` in its own interpreter, through argv."""
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s%s%s" % (ROOT, os.pathsep, ROOT / "src")
    env.pop("S09ISO_TOKEN", None)
    done = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", *args],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, "ad01-traj %s refused:\n%s%s" % (
        " ".join(args), done.stderr, done.stdout)
    return done.stdout


def _rows(dsn, sql, params=()):
    from experiments.ad01 import trajectory

    with trajectory._read_conn(dsn) as conn:
        rows = conn.execute(sql, params).fetchall()
        conn.commit()
        return rows


def _consumer(dsn, cid, gateway):
    from experiments.ad01 import agenda_policy, policy_step, trajectory

    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    return agenda_policy.step_policy_consumer(
        policy_step.make_policy_artifact(WALK_SOURCE,
                                         origin="authored-control"),
        dsn=dsn, cid=cid, charter=dict(CHARTER), world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid), study_root=cid,
        gateway=gateway, model="a42-walk-double")


@pytest.fixture(scope="module")
def walk(store, tmp_path_factory):
    """One acquisition campaign, then the use half through the CLI.

    The CLI's constructor is gated behind a model gateway supplied as a
    flag this lane cannot name honestly, so the acquisition half is entered
    through `run_campaign` with a consumer built from this file's policy
    bytes. The use half is entered through argv, because that is where the
    fresh-process claim lives.
    """
    from experiments.ad01 import trajectory

    cid = trajectory.campaign_id(0, "I", SEQ)
    gateway = Constructor()
    out = trajectory.run_campaign(
        0, "I", CHARTER, CAPS, tasks=list(TASKS), campaign_seq=SEQ,
        dsn=store, consumer=_consumer(store, cid, gateway),
        constructor="model", gateway=gateway, model="a42-walk-double")

    root = tmp_path_factory.mktemp("a42")
    repertoire_path = root / ("repertoire-%d.json" % SEQ)
    trajectory.freeze_repertoire(out, repertoire_path)
    repertoire = trajectory.load_repertoire(repertoire_path)

    member_id = (repertoire.get("members") or [{}])[0].get("capability_id")
    policy_path = root / "use_policy.py"
    policy_path.write_text(USE_SOURCE % member_id, encoding="utf-8")

    use = json.loads(_cli(
        "use", "--repertoire", str(repertoire_path), "--dsn", store,
        "--allocation-id", trajectory._alloc_id(cid), "--world", "0",
        "--arm", "I", "--tasks", USE_TASK, "--policy-source",
        str(policy_path)))
    return {"cid": cid, "campaign": out, "store": store, "use": use,
            "repertoire": repertoire, "member": (repertoire.get("members")
                                                or [{}])[0]}


STAGES = ("permitted experience", "program decision", "admitted effect",
          "observation", "checked artifact", "retention/binding",
          "fresh-process use")


def _report(walk) -> dict:
    """Each stage's evidence, read from rows a finished process wrote."""
    cid, dsn = walk["cid"], walk["store"]
    policy = _rows(dsn,
                   "SELECT seq, policy_output, accepted_action,"
                   " effect_record FROM s09_policy_state"
                   " WHERE investigation_id = %s ORDER BY seq", (cid,))
    step_kinds, stored_kinds, effects = [], [], []
    for row in policy:
        step_kinds.extend(r["action"]["kind"]
                          for r in dict(row["policy_output"] or {})
                          .get("results", []))
        stored_kinds.append(dict(dict(row["accepted_action"] or {})
                                 .get("next_action") or {}).get("kind"))
        if row["effect_record"] is not None:
            effects.append(dict(row["effect_record"]))
    episodes = [dict(e.get("episode") or {}) for e in effects]
    boundaries = _rows(
        dsn, "SELECT content FROM attempt_observations"
             " WHERE content->>'kind' = 'boundary' ORDER BY id")
    ops = _rows(dsn, "SELECT id, settled FROM operations WHERE id LIKE %s",
                ("ad01-%s%%" % cid,))
    releases = _rows(dsn, "SELECT id, disposition FROM capability_releases")
    use = walk["use"][0] if walk["use"] else {}
    member = walk["member"]
    return {
        "permitted experience": {
            "policy steps ran": len(step_kinds),
            "first episode kind": walk["campaign"]["episodes"][0].get("kind"),
            "operations": len(ops),
            "settled": sum(1 for r in ops if r["settled"])},
        "program decision": {
            "step kinds": step_kinds,
            "stored kinds": stored_kinds,
            "one policy digest": len({dict(r["policy_output"] or {})
                                      .get("source_digest")
                                      for r in policy}) == 1},
        "admitted effect": {
            "effect records": len(effects),
            "with ran_under": sum(1 for e in effects if e.get("ran_under")),
            "with effect_operation_id": sum(
                1 for e in effects if e.get("effect_operation_id"))},
        "observation": {
            "boundary rows": len(boundaries),
            "distinct ids": len({dict(r["content"])["observation_id"]
                                 for r in boundaries})},
        "checked artifact": {
            "episodes with a check": sum(1 for e in episodes
                                         if e.get("check")),
            "verdicts": [e["check"]["verdict"] for e in episodes
                         if e.get("check")]},
        "retention/binding": {
            "repertoire members": len(walk["repertoire"].get("members") or []),
            "releases": len(releases),
            "release ids": [dict(r)["id"] for r in releases]},
        "fresh-process use": {
            "records": len(walk["use"]),
            "selected": use.get("selected"),
            "executed": use.get("executed"),
            "verdict": use.get("verdict"),
            "release_id": use.get("release_id"),
            "policy digest": (use.get("policy_source_digest") or "")[:12],
            "method digest": (member.get("source_digest") or "")[:12],
            "operations": use.get("operation_ids")},
    }


# --- the stages ----------------------------------------------------------

def test_the_campaign_ran_three_boundaries_through_run_campaign(walk):
    report = _report(walk)
    assert walk["campaign"]["campaign_id"] == walk["cid"]
    assert [b["seq"] for b in walk["campaign"]["boundaries"]] == [0, 1, 2]
    assert walk["campaign"]["stop"].get("reason"), walk["campaign"]["stop"]
    assert report["permitted experience"]["first episode kind"] == "diagnostic"


def test_permitted_experience_reached_the_program_as_admitted_operations(
        walk):
    report = _report(walk)
    stage = report["permitted experience"]
    assert stage["policy steps ran"] == 3, report
    assert stage["operations"] > 0, report
    assert stage["settled"] == stage["operations"], (
        "an admitted operation has no receipt: %r" % report)


def test_the_decision_is_durable_in_both_vocabularies(walk):
    """The STEP kind and the stored kind, held apart rather than merged.

    `policy_step.STEP_KIND_TO_CONTRACT` and `agenda_policy._STEP_TO_LEGACY`
    are two more vocabularies; what the walk shows is that the decision the
    policy admitted and the decision the campaign ran under are two
    separately durable spellings of one boundary, not one string.
    """
    from experiments.ad01 import agenda_policy

    report = _report(walk)
    stage = report["program decision"]
    assert stage["step kinds"] == list(STEP_KINDS), report
    assert stage["stored kinds"] == [agenda_policy._STEP_TO_LEGACY[k]
                                     for k in STEP_KINDS], report
    assert stage["one policy digest"], report


def test_the_admitted_effect_is_recorded_and_names_its_operation(walk):
    """`ran_under` is absent here, and that is the measurement.

    `ran_under` is written only by `execute_pending`, and a clean campaign
    does not reach it: `run_campaign` incorporates the fresh boundary
    without an `effect_record` argument. So the chain's own admission
    window carries `in_flight` while it is open and leaves nothing behind
    naming the program once the effect lands. A40's resume test is where
    `ran_under` is proved.
    """
    report = _report(walk)
    stage = report["admitted effect"]
    assert stage["effect records"] == 3, report
    assert stage["with effect_operation_id"] == 3, report
    assert stage["with ran_under"] == 0, report
    assert _rows(walk["store"],
                 "SELECT in_flight FROM investigations WHERE id = %s",
                 (walk["cid"],))[0]["in_flight"] == [], (
        "a completed campaign still holds its operation")


def test_the_observation_is_a_row_the_campaign_read_back(walk):
    report = _report(walk)
    assert report["observation"]["boundary rows"] == 3, report
    assert report["observation"]["distinct ids"] == 3, report


def test_the_checker_preserved_what_the_construction_produced(walk):
    report = _report(walk)
    stage = report["checked artifact"]
    assert stage["episodes with a check"] == 2, report
    assert "preserved" in stage["verdicts"], report
    member = walk["member"]
    assert member["authored"] is False, member
    assert member["method_source"] == ACQUIRED_METHOD


def test_retention_happened_and_no_release_was_minted(walk):
    """Arrow 6's binding half does not happen, and this is the finding.

    `freeze_repertoire` retains the member and `run_use` selects it by
    scope, but `selection.select_member` consults `capability_releases` only
    when `release_id` is named and the CLI was given none. So the bytes
    that ran are pinned to nothing the store holds. Asserting the count is
    zero turns that into a reported stage rather than an implied one.
    """
    report = _report(walk)
    stage = report["retention/binding"]
    assert stage["repertoire members"] == 1, report
    assert stage["releases"] == 0, report
    assert stage["release ids"] == [], report


def test_the_fresh_process_ran_the_method_bytes_not_the_policy_bytes(walk):
    report = _report(walk)
    stage = report["fresh-process use"]
    assert stage["records"] == 1, report
    assert "status" not in walk["use"][0], walk["use"][0]
    assert stage["selected"] == walk["member"]["capability_id"], report
    assert stage["executed"] == walk["member"]["capability_id"], report
    assert stage["verdict"] == "preserved", report
    assert stage["policy digest"] and stage["method digest"], report
    assert stage["policy digest"] != stage["method digest"], report
    assert len(stage["operations"]) == 2, report
    for operation_id in stage["operations"]:
        settled = _rows(walk["store"],
                        "SELECT settled FROM operations WHERE id = %s",
                        (operation_id,))
        assert settled and dict(settled[0])["settled"] is True, operation_id


def test_the_walk_reports_all_seven_stages(walk):
    """Seven stages in, seven stages out.

    A stage that produced no row would otherwise drop out of the report and
    read as absent rather than unmeasured, so the report's keys are compared
    against the chain's own names rather than against a snapshot.
    """
    assert tuple(_report(walk)) == STAGES


def test_the_walk_is_printed_for_a_reader_who_disagrees(walk, capsys):
    print(json.dumps({"stages": _report(walk), "gaps": GAPS}, indent=2,
                     sort_keys=True, default=str))
    assert capsys.readouterr().out.strip()


GAPS = [
    {"stage": "retention/binding",
     "observed": "1 repertoire member, 0 capability_releases",
     "reason": "`selection.select_member` reads `capability_releases` only "
               "when `release_id` is named; the CLI `use` command was given "
               "none and `freeze_repertoire` mints no release, so the bytes "
               "that ran are pinned to nothing the store holds."},
    {"stage": "admitted effect",
     "observed": "3 effect records, 0 with ran_under",
     "reason": "`ran_under` is written only by `execute_pending`, and a "
               "clean campaign does not reach it: `run_campaign` "
               "incorporates the fresh boundary with no `effect_record` "
               "argument. The admission window is real and "
               "`test_a40_admission_wired.py` proves it, but a campaign that "
               "does not crash leaves nothing naming the program it ran "
               "under."},
    {"stage": "fresh-process use",
     "observed": "2 operation ids, no InFlightOperation",
     "reason": "the method runs out of process and the two operations "
               "settle, but the decision that selected it runs in the CLI "
               "process and `run_use` never calls `trajectory.admit_boundary`, "
               "so no held operation covers a crash between the policy "
               "operation and the method execution."},
]


# --- method release against policy identity -----------------------------

def test_a_package_digest_is_accepted_where_a_program_digest_is_required():
    """The hazard A36 named, measured rather than restated.

    `mission.seed_program_digest` and `frontier.package_digest` are both
    64 lowercase hex, and `trajectory._admitting_program_digest` checks
    length and alphabet only. A digest of the wrong kind is therefore
    admitted under the other kind's name, and `InFlightOperation` holds it
    without complaint.
    """
    from experiments.ad01 import frontier, mission, trajectory

    seed = mission.seed_program_digest()
    package = frontier.package_digest("def m(c):\n    return c\n",
                                      imp_source="def i():\n    pass\n")
    assert seed != package, "the two digest spaces collapsed into one"
    assert len(seed) == len(package) == 64
    assert all(c in "0123456789abcdef" for c in seed + package)
    assert trajectory._admitting_program_digest(package) == package, (
        "a frontier package digest is refused where a program digest is "
        "required; the hazard this measures is gone")
    assert trajectory._admitting_program_digest("0" * 64) == "0" * 64, (
        "a digest of no bytes at all is admitted as a program identity")
    with pytest.raises(mission.MissionRefused):
        trajectory._admitting_program_digest("A" * 64)


def test_the_walk_separates_the_method_from_the_policy(walk):
    """What the chain does separate, and where the separation stops.

    The policy that admitted the use and the method that ran are two
    operations with two receipts and two different digests, so neither can
    stand in for the other. What the chain does not do is give the method a
    release identity: `capability_releases` is empty and `release_id` is
    null, so "retained" here names repertoire bytes and nothing durable
    binds them.
    """
    use = walk["use"][0]
    assert use["policy_source_digest"] != walk["member"]["source_digest"]
    assert len(use["operation_ids"]) == 2
    assert use["release_id"] is None
    assert _rows(walk["store"], "SELECT id FROM capability_releases") == []


# --- the census ----------------------------------------------------------

PROD_TREES = ("src", "experiments", "scripts")
TEST_TREES = ("tests",)
EXPECTED_PROD_FILES = 468

CAPABILITIES = (
    ("admission", "admit an operation with durable identity",
     "experiments.ad01.mission", "admit_operation"),
    ("admission", "public accept_action entry",
     "experiments.ad01.trajectory", "accept_action"),
    ("admission", "seed program identity",
     "experiments.ad01.mission", "seed_program_digest"),
    ("identity", "mission entry writer",
     "experiments.ad01.mission", "record_mission"),
    ("identity", "mission entry reader",
     "experiments.ad01.mission", "read_mission"),
    ("identity", "declaration projection",
     "experiments.ad01.mission", "read_declaration"),
    ("identity", "improvement-mode projection",
     "experiments.ad01.mission", "read_improvement_mode"),
    ("continuation", "read the in-flight column",
     "experiments.ad01.mission", "read_in_flight"),
    ("continuation", "quiescence predicate",
     "experiments.ad01.mission", "is_quiescent"),
    ("continuation", "held-operation lookup",
     "experiments.ad01.mission", "held_operation"),
    ("continuation", "resume a held operation",
     "experiments.ad01.mission", "resume_operation"),
    ("continuation", "release a settled operation",
     "experiments.ad01.mission", "release_operation"),
    ("continuation", "trajectory mission-entry read",
     "experiments.ad01.trajectory", "mission_held"),
    ("barrier", "register broker operations",
     "settlement.run", "register_ops"),
    ("barrier", "record a continuation",
     "settlement.run", "record_continuation"),
    ("barrier", "fresh continuation",
     "settlement.run", "fresh_continuation"),
    ("barrier", "migrate a continuation",
     "settlement.run", "migrate_continuation"),
    ("barrier", "pending invokes", "settlement.run", "pending_invokes"),
    ("improvement", "fresh improvement round",
     "experiments.ad01.improve_channel", "fresh_round"),
    ("improvement", "admit a revision under freeze",
     "experiments.ad01.improve_channel", "admit_revision_under_freeze"),
    ("improvement", "revision acquire entry",
     "experiments.ad01.learner_revision", "acquire"),
    ("improvement", "frozen-state read",
     "experiments.ad01.improve_channel", "frozen_state"),
    ("policy", "persist a step transition",
     "experiments.ad01.policy_step", "persist_step_transition"),
    ("policy", "run a bounded policy step",
     "experiments.ad01.policy_step", "run_policy_step"),
    ("policy", "action-vocabulary coverage",
     "experiments.ad01.policy_step", "vocabulary_coverage"),
    ("control", "execute a pending operation",
     "experiments.ad01.trajectory", "execute_pending"),
)


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[0] == "src":
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _chain(parents, node):
    cur, out = node, []
    while cur in parents:
        cur = parents[cur]
        out.append(cur)
    return out


def _scope(chain, modname):
    fns = [n for n in chain
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not fns:
        return "%s:<module>" % modname
    n = fns[0]
    cls = [c for c in chain if isinstance(c, ast.ClassDef)
           and c.lineno < n.lineno]
    inner = "%s.%s" % (max(cls, key=lambda c: c.lineno).name, n.name) \
        if cls else n.name
    outer = [c for c in fns if c.lineno > n.lineno]
    if outer:
        inner = ".".join([c.name for c in outer] + [inner])
    return "%s:%s" % (modname, inner)


class _Module:
    def __init__(self, name, is_prod):
        self.name = name
        self.is_prod = is_prod
        # binding name -> (module, None) when the binding names a module,
        # (base module, symbol) when it names something inside one.
        self.aliases = {}
        self.defs = {}
        self.sites = []
        self.has_main = False
        self.star_imports = []


def _load(path: Path, is_prod: bool) -> _Module:
    name = _module_name(path)
    mod = _Module(name, is_prod)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        outer = [c for c in _chain(parents, node)
                 if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef))]
        if not outer:
            mod.defs["%s:%s" % (name, node.name)] = node
        elif len(outer) == 1:
            mod.defs["%s:%s.%s" % (name, outer[0].name, node.name)] = node
        else:
            mod.defs["%s:%s.%s" % (name,
                                   ".".join(o.name for o in outer[:-1]),
                                   "%s.%s" % (outer[-1].name, node.name))] \
                = node

    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
            mod.has_main = True

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mod.aliases[a.asname or a.name] = (
                    a.name if a.asname else a.name.split(".")[0], None)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                pkg = name.split(".")
                keep = max(0, len(pkg) - node.level)
                bm = ".".join(pkg[:keep])
                base = "%s.%s" % (bm, base) if base else bm
            for a in node.names:
                if a.name == "*":
                    mod.star_imports.append(base)
                else:
                    mod.aliases[a.asname or a.name] = (base, a.name)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        scope = _scope(_chain(parents, node), name)
        f = node.func
        if isinstance(f, ast.Name):
            mod.sites.append((scope, "local", None, f.id))
        elif isinstance(f, ast.Attribute):
            recv = f.value
            if isinstance(recv, ast.Name) and recv.id in ("self", "cls"):
                cls = [c for c in _chain(parents, node)
                       if isinstance(c, ast.ClassDef)]
                if cls:
                    mod.sites.append((scope, "method",
                                      max(cls, key=lambda c: c.lineno).name,
                                      f.attr))
                    continue
            if isinstance(recv, ast.Name):
                mod.sites.append((scope, "alias", recv.id, f.attr))
            else:
                mod.sites.append((scope, "expr", None, f.attr))
    return mod


def _census() -> dict:
    mods = {}
    prod_files = test_files = 0
    parse_errors = {}
    for tree_name, is_prod in [(t, True) for t in PROD_TREES] \
            + [(t, False) for t in TEST_TREES]:
        base = ROOT / tree_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(ROOT).parts
            if any(p.startswith(".") or p == "__pycache__" for p in rel):
                continue
            try:
                mod = _load(path, is_prod)
            except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
                parse_errors[_module_name(path)] = repr(exc)
                continue
            mods[mod.name] = mod
            if is_prod:
                prod_files += 1
            else:
                test_files += 1

    module_set = set(mods)
    edges = defaultdict(set)
    for m in mods.values():
        for scope, kind, key, attr in m.sites:
            if kind == "local":
                cand = "%s:%s" % (m.name, attr)
                if cand in m.defs:
                    edges[scope].add(cand)
            elif kind == "method":
                cand = "%s:%s.%s" % (m.name, key, attr)
                if cand in m.defs:
                    edges[scope].add(cand)
            elif kind == "alias":
                al = m.aliases.get(key)
                if al is None:
                    continue
                base, sym = al
                if sym is None:
                    if base in module_set and "%s:%s" % (base, attr) \
                            in mods[base].defs:
                        edges[scope].add("%s:%s" % (base, attr))
                    continue
                submod = "%s.%s" % (base, sym)
                if submod in module_set:
                    # The binding is a module however it was spelled, so an
                    # attribute on it is a call into that module.
                    if "%s:%s" % (submod, attr) in mods[submod].defs:
                        edges[scope].add("%s:%s" % (submod, attr))
                    continue
                parent = "%s:%s" % (base, sym)
                if base in mods and parent in mods[base].defs:
                    sub = "%s:%s" % (parent, attr)
                    if sub in mods[base].defs:
                        edges[scope].add(sub)
                elif base in mods and "%s:%s" % (base, attr) \
                        in mods[base].defs:
                    edges[scope].add("%s:%s" % (base, attr))

    seeds = set()
    for m in mods.values():
        if m.is_prod and m.has_main:
            seeds.add("%s:<module>" % m.name)
            seeds.update(m.defs)
    seen, queue = set(), list(seeds)
    while queue:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        queue.extend(edges.get(cur, ()))

    rev = defaultdict(set)
    for scope, targets in edges.items():
        for target in targets:
            rev[target].add(scope)

    rows = []
    for area, capability, mod, fn in CAPABILITIES:
        qual = "%s:%s" % (mod, fn)
        loaded = mods.get(mod)
        exists = loaded is not None and qual in loaded.defs
        callers = rev.get(qual, set()) if exists else set()
        prod_callers = sorted(
            s for s in callers
            if mods.get(s.partition(":")[0])
            and mods[s.partition(":")[0]].is_prod)
        test_modules = len({s.partition(":")[0] for s in callers
                            if mods.get(s.partition(":")[0])
                            and not mods[s.partition(":")[0]].is_prod})
        rows.append({"area": area, "capability": capability, "impl": qual,
                     "exists": exists, "prod_callers": len(prod_callers),
                     "test_modules": test_modules,
                     "reachable_from_main": exists and qual in seen})
    return {"prod_files": prod_files, "test_files": test_files,
            "prod_functions": sum(len(m.defs) for m in mods.values()
                                  if m.is_prod),
            "star_imports": sum(len(m.star_imports) for m in mods.values()
                                if m.is_prod),
            "parse_errors": parse_errors, "rows": rows}


def test_the_census_walked_the_tree_it_claims():
    """A census that reads nothing reports every capability dead.

    The file count is pinned, so a walk that silently stopped or a tree that
    moved shows here rather than in the numbers the census prints.
    """
    report = _census()
    assert report["prod_files"] == EXPECTED_PROD_FILES, report["prod_files"]
    assert report["prod_functions"] > 5000, report["prod_functions"]
    assert not report["parse_errors"], report["parse_errors"]
    assert report["star_imports"] == 0, (
        "a star import appeared; `from x import *` cannot be resolved and "
        "its names would read as unreferenced")


def test_the_resolver_sees_a_known_production_caller():
    """The permissive direction: a resolver that finds nothing is broken."""
    report = _census()
    rows = {r["impl"]: r for r in report["rows"]}
    control = rows["experiments.ad01.trajectory:execute_pending"]
    assert control["exists"] and control["reachable_from_main"]
    assert control["prod_callers"], (
        "execute_pending is reached from run_campaign and resume_campaign; "
        "a resolver that cannot see that sees nothing")


def test_admission_and_quiescence_are_both_live():
    """What the wiring made reachable, which used to be half-dead.

    Admission is entered from `run_campaign` and its column is written on the
    live path. `is_quiescent` used to be called from nothing in production —
    the campaign knew it held work by reading the row, not by asking, and the
    live arm's own predicate was a file read. M1 requires one definition of
    quiescence for live admission and program adoption, so `live_construct` now
    gates both of its `adopt_revision` call sites on the SQL predicate.

    `is_quiescent` is reachable from a `__main__` through
    `scripts.invl02_live._run_frontier_investigation` ->
    `live_construct.activate_control_revision` ->
    `live_construct._require_quiescent` -> `mission.is_quiescent`. Three hops,
    and the second is the aliased-import seam this census used to read as
    solid. So the count and the reachability are both asserted: a wiring that
    counted callers but sat outside `main` would satisfy the first alone.
    """
    report = _census()
    rows = {r["impl"]: r for r in report["rows"]}
    accept = rows["experiments.ad01.trajectory:accept_action"]
    admit = rows["experiments.ad01.mission:admit_operation"]
    quiescent = rows["experiments.ad01.mission:is_quiescent"]
    assert accept["reachable_from_main"], (
        "accept_action has no __main__-reachable caller again")
    assert admit["reachable_from_main"] and admit["prod_callers"]
    assert quiescent["test_modules"] > 0, (
        "is_quiescent is neither reachable nor tested; the census cannot "
        "tell those apart")
    assert quiescent["prod_callers"] > 0, (
        "is_quiescent has no production caller again, so nothing governs "
        "readiness: %r" % quiescent)
    assert quiescent["reachable_from_main"], (
        "is_quiescent has production callers but none reachable from a "
        "__main__, so nothing that ships asks it: %r" % quiescent)


def test_the_census_is_reported_not_baked_in(capsys):
    report = _census()
    live = [r for r in report["rows"]
            if r["exists"] and r["reachable_from_main"]]
    dead = [{"capability": r["capability"],
             "production_callers": r["prod_callers"],
             "test_modules": r["test_modules"]}
            for r in report["rows"]
            if r["exists"] and not r["reachable_from_main"]]
    print(json.dumps({
        "prod_files_walked": report["prod_files"],
        "test_files_walked": report["test_files"],
        "prod_functions_indexed": report["prod_functions"],
        "reachable_from_main": len(live),
        "still_dead": dead}, indent=2, sort_keys=True))
    assert len(live) + len(dead) == len(
        [r for r in report["rows"] if r["exists"]])


# --- an opener that fails shut -------------------------------------------

def test_fresh_round_cannot_open_a_store_that_names_a_durable_owner(tmp_path):
    """A live-adjacent opener measured rather than cited.

    `improve_channel.fresh_round` opened namelessly, and `_check_identity`
    refuses that for any document that recorded an owner. So the improvement
    path's fresh process could not open any store a durable owner created. This
    test still holds, and still describes the guard: the nameless open is
    refused, and a nameless document still refuses an owned open. What changed
    is that the opener now takes the two names, so the refusal is something a
    correct caller can answer rather than a dead end. See
    `tests/test_a55_continuation_owner.py`.
    """
    from experiments.ad01 import frontier

    owned = frontier.StoreIdentity(investigation_id="ad01-w0-I-42",
                                   dsn="postgresql:///probe")
    env = [{"split": "fit", "seed": 1}]
    path = tmp_path / "owned.json"
    frontier.create_store(
        path, namespace=frontier.NAMESPACE,
        mission={"objective": "probe", "environments": env},
        authority={"queries": 16, "steps": 12}, identity=owned).save()
    with pytest.raises(frontier.Refused) as caught:
        frontier.FrontierStore(str(path))
    assert "owned by investigation" in str(caught.value), str(caught.value)

    nameless = tmp_path / "nameless.json"
    frontier.create_store(
        nameless, namespace=frontier.NAMESPACE,
        mission={"objective": "probe", "environments": env},
        authority={"queries": 16, "steps": 12}).save()
    frontier.FrontierStore(str(nameless))
    with pytest.raises(frontier.Refused):
        frontier.FrontierStore(str(nameless), identity=owned)


def test_fresh_round_names_the_owner_it_was_given():
    """The opener is the shape, read from the source rather than assumed.

    This pinned `FrontierStore(store_path)` with no identity, which is the
    defect `test_fresh_round_cannot_open_a_store_that_names_a_durable_owner`
    measures and declined to fix on the grounds that which investigation owns
    the store is not a measurement's call. WORKER-PROMPT.md §A assigns that
    decision to the ownership migration, so the opener now carries the two
    names and still opens namelessly when given neither.
    """
    from experiments.ad01 import improve_channel

    source = Path(improve_channel.__file__).read_text(encoding="utf-8")
    start = source.index("def fresh_round(")
    body = source[start:source.index("def main(", start)]
    calls = [line.strip() for line in body.splitlines()
             if "FrontierStore(" in line]
    assert len(calls) == 1, calls
    assert "identity=" in body, body
    assert "dsn: str | None = None" in body
    assert "investigation_id: str | None = None" in body
    opener = calls[0]
    assert opener.startswith("store = _frontier.FrontierStore("), opener