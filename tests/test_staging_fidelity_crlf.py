"""Staged bytes and frozen digests are the same bytes on every host.

Two defects, one cause. `method_exec` hashed driver text in memory and
re-hashed it from disk, but wrote the file in text mode, which translates
`\n` to `os.linesep` on Windows: the two digests differ, provenance
verification refuses, and `_execute` swallows that into `{"scored": False}`
with `candidates_moved` never written. The same host policy rewrites the
frozen worlds to CRLF on checkout, so a freeze manifest verified a digest of
the checkout rather than of the source.

Every assertion here reads bytes off disk or a literal digest. None of them
would pass if the staged write or the freeze write were reverted.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import method_exec, policy_step, worlds  # noqa: E402
from settlement import launcher_local  # noqa: E402

# The venv's editable install puts the main checkout on `sys.path`, so an
# import can silently resolve there and every assertion below would measure
# the main checkout's source instead of this one. A test that runs against
# someone else's bytes proves nothing, so the import is checked rather than
# assumed.
assert Path(method_exec.__file__).is_relative_to(ROOT), (
    "method_exec resolved to %s, outside %s" % (method_exec.__file__, ROOT))
assert Path(worlds.FROZEN_DIR).is_relative_to(ROOT), (
    "the frozen world resolved to %s, outside %s"
    % (worlds.FROZEN_DIR, ROOT))

TASK = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00")

STEP_SOURCE = (
    "def STEP(view, state):\n"
    "    action = {\"kind\": \"diagnose\", \"target\": \"requested\",\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"unknown\": \"u\", \"question\": \"q\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {\"source\": \"requested\"}}\n"
)


def _view() -> dict:
    return policy_step.materialize_view(
        task=TASK, observations=[], open_questions=[], last_result=None,
        eligible_methods=[], remaining={"steps": 1})


def _check_attr_command(paths: list[str]) -> list[str]:
    """`git check-attr` pointed at this worktree in a way any git can run.

    A linked worktree's `.git` is a file holding a gitdir path. In a
    checkout made on Windows that path is spelled `D:/...`, which git
    running under WSL on `/mnt/d` cannot resolve: it is not a repository
    there, and the check dies with exit 128 before it reads an attribute.
    Rewriting the drive letter to its mount point names the same directory
    in the running platform's syntax, so the command measures git's
    attribute resolution rather than the caller's platform.
    """
    command = ["git"]
    git_file = ROOT / ".git"
    if git_file.is_file():
        declared = git_file.read_text(encoding="utf-8").split(":", 1)[1].strip()
        command += ["--git-dir", _local_path(declared),
                    "--work-tree", str(ROOT)]
    return command + ["check-attr", "--all", "--"] + paths


def _local_path(declared: str) -> str:
    """`D:/rest` under a POSIX host is `/mnt/d/rest`; anything else is itself."""
    drive, separator, rest = declared.replace("\\", "/").partition("/")
    if separator and len(drive.rstrip(":")) == 1 and drive[0].isalpha():
        return "/mnt/%s/%s" % (drive[0].lower(), rest)
    return declared


@pytest.fixture(scope="module")
def authority():
    """A real store and allocation for the step executor to resolve.

    Staging is host-side work that happens only after the executor accepts
    its authority, so proving the staged bytes needs a store, an allocation
    and an operation id that exist. The child itself is still replaced by
    `_NoChild` inside the test that uses this; nothing executes here.
    """
    import uuid

    from experiments.ad01 import trajectory
    from experiments.ad01.s09_run_isolation import create_disposable_db, \
        drop_disposable_db

    database = create_disposable_db("staging-fidelity",
                                    migrations_dir=ROOT / "migrations")
    try:
        trajectory.set_namespace_token("")
        campaign = "staging-fidelity-%s" % uuid.uuid4().hex[:8]
        allocation = trajectory.authorize_campaign(
            database.dsn, campaign, authorized=100000)
        counter = {"n": 0}

        def run(source, view, state, **kwargs):
            counter["n"] += 1
            return method_exec.run_step_out_of_process(
                source, view, state, dsn=database.dsn,
                allocation_id=allocation["allocation_id"],
                operation_id="%s-op%d" % (campaign, counter["n"]), **kwargs)

        yield type("Authority", (), {"run": staticmethod(run),
                                     "dsn": database.dsn})()
    finally:
        drop_disposable_db(database)


class _NoChild:
    """Stands in for the child process, recording what was staged.

    The staging and provenance work all happens before `Popen`, so a host
    that cannot spawn still stages the bytes this test is about. It used to
    be assumed the refusal always arrived from `Popen`; that stopped being
    true when the launcher began refusing a child whose caps it cannot
    install, so the capture now also runs from `_stage_text` itself. A test
    that depends on one particular refusal arriving last is a test of the
    refusal order, not of the bytes.
    """

    def __init__(self) -> None:
        self.staged: dict[str, bytes] = {}

    def record(self, work: Path) -> None:
        for name in ("driver.py", "policy.py", "step.json"):
            path = Path(work) / name
            if path.is_file():
                self.staged[name] = path.read_bytes()

    def __call__(self, argv, **kwargs):
        self.record(Path(argv[1]).parent)
        raise ValueError("preexec_fn is not supported on Windows platforms")


# ---------------------------------------------------------------------------
# Defect 1: the staged driver is byte-identical to the text that was hashed
# ---------------------------------------------------------------------------


def test_staged_driver_bytes_equal_the_source_that_was_hashed(
        monkeypatch, authority):
    """The file `run_step_out_of_process` stages hashes to the in-memory
    driver digest. This is the literal assertion the defect violated: with a
    text-mode write the on-disk digest was `05ef7fa4...` where provenance
    expected `e6a19a22...` on this host.

    The bytes are captured at `_stage_text`, which is the boundary that
    writes them, rather than at `Popen`. Capturing at `Popen` only worked
    while the refusal to launch was the last thing that happened; the
    launcher now refuses earlier when it cannot install the child's caps,
    and the test failed on a missing dict key while asserting nothing about
    staging. Reading at the writer makes the assertion depend on the write
    and not on the order of unrelated refusals.

    The call holds real authority on purpose. Without it the executor
    refuses before a byte is staged, so `child.staged` would be empty and
    `assert "driver.py" in child.staged` would fail on a refusal rather than
    on a staging defect. The child is still replaced by `_NoChild`, so no
    candidate code runs here; what is measured is the host's own bytes.
    """
    child = _NoChild()
    real_stage = method_exec._stage_text

    def capturing_stage(path, text, expected):
        real_stage(path, text, expected)
        child.record(Path(path).parent)

    monkeypatch.setattr(method_exec, "_stage_text", capturing_stage)
    monkeypatch.setattr(launcher_local.subprocess, "Popen", child)

    with pytest.raises((ValueError, method_exec.MethodExecutionError)):
        authority.run(STEP_SOURCE, _view(), {})

    expected = hashlib.sha256(
        (method_exec._STEP_DRIVER % (policy_step.STEP_ENTRY,))
        .encode("utf-8")).hexdigest()
    assert "driver.py" in child.staged, "the driver was never staged"
    staged = child.staged["driver.py"]
    assert hashlib.sha256(staged).hexdigest() == expected
    assert b"\r\n" not in staged, (
        "the staged driver carries CRLF, so its digest is the checkout's"
        " digest and not the source's")
    assert staged.decode("utf-8") == \
        method_exec._STEP_DRIVER % (policy_step.STEP_ENTRY,)


def test_step_provenance_accepts_the_bytes_it_just_staged(tmp_path):
    """`_verify_operation_provenance` is the boundary that refused. Given
    the bytes the staging function wrote, it returns None rather than
    raising. Asserted against the literal digest of the literal text."""
    source = "def STEP(view, state):\n    return {}\n"
    driver = method_exec._STEP_DRIVER % ("step",)
    work = tmp_path
    (work / "policy.py").write_bytes(source.encode("utf-8"))
    (work / "step.json").write_bytes(method_exec._canonical_input(
        {"view": {}, "state": {}}))
    provenance = method_exec._operation_provenance(
        source, driver, {"view": {}, "state": {}},
        source_path="policy.py", driver_path="driver.py",
        input_path="step.json")
    method_exec._stage_text(work / "driver.py", driver,
                            provenance["driver_digest"])

    assert (work / "driver.py").read_bytes() == driver.encode("utf-8")
    assert method_exec._verify_operation_provenance(work, provenance) is None


def test_staging_text_refuses_a_digest_it_cannot_produce(tmp_path):
    """`_stage_text` checks the bytes it encoded against the digest it was
    given, so a caller that passes a digest of different text is refused
    before anything is written."""
    target = tmp_path / "driver.py"

    with pytest.raises(method_exec.MethodExecutionError,
                       match="staged text digest mismatch"):
        method_exec._stage_text(target, "a = 1\n",
                                hashlib.sha256(b"a = 2\n").hexdigest())

    assert not target.exists()


def test_member_driver_is_staged_byte_exactly(tmp_path):
    """The member path had the identical `write_text` call, so the same
    contract applies to it. The host cannot run a member at all (no
    `AF_UNIX`), so the staging step is driven directly with the values
    `run_member_out_of_process` computes, and the bytes are read back."""
    member_source = (
        "def carried(task, oracle):\n"
        "    return {\"candidate\": {\"family\": \"software\","
        " \"task_id\": task[\"task_id\"]}, \"queries\": 0}\n")
    driver_source = method_exec._DRIVER % ("carried", 2)
    provenance = method_exec._operation_provenance(
        member_source, driver_source, {"task": TASK, "max_queries": 1},
        source_path="member.py", driver_path="driver.py",
        input_path="task.json")

    method_exec._stage_text(tmp_path / "member.py", member_source,
                            provenance["source_digest"])
    method_exec._stage_text(tmp_path / "driver.py", driver_source,
                            provenance["driver_digest"])

    assert (tmp_path / "member.py").read_bytes() == \
        member_source.encode("utf-8")
    staged = (tmp_path / "driver.py").read_bytes()
    assert hashlib.sha256(staged).hexdigest() == provenance["driver_digest"]
    assert b"\r\n" not in staged


# ---------------------------------------------------------------------------
# Defect 2: the committed freeze hashes the source, not the checkout
# ---------------------------------------------------------------------------


def test_committed_freeze_verifies_on_this_host():
    """The literal value: the committed `ad01` freeze verifies clean. Before
    the `.gitattributes` rule this returned `['manifest-hash-mismatch']`
    because `core.autocrlf=true` checked the manifest out as CRLF."""
    assert worlds.verify_committed() == []


def test_frozen_manifest_bytes_carry_no_carriage_returns():
    """The pinned digest is the LF digest. A CRLF byte in the file would mean
    the file on disk is not the file that was hashed."""
    manifest = (worlds.FROZEN_DIR / "manifest.json").read_bytes()
    pinned = (worlds.FROZEN_DIR / "manifest.sha256").read_text().strip()

    assert b"\r\n" not in manifest
    assert hashlib.sha256(manifest).hexdigest() == pinned


def test_gitattributes_pins_every_content_hashed_tree_to_lf():
    """`.gitattributes` is the mechanism, and a rule that names a directory
    git does not attribute to is a rule that does not run. Read off the real
    attributes git resolves, not off the file's text.

    The git directory is named explicitly. A linked worktree's `.git` file
    carries a Windows path (`D:/...`), which git under WSL on `/mnt/d`
    cannot resolve, so `git -C` there dies with "not a git repository" and
    the test reported a git failure rather than an attribute failure. The
    attributes this asserts are the same either way; only the way git is
    pointed at them changed.
    """
    freeze_dirs = sorted(
        str(p.relative_to(ROOT)).replace("\\", "/") + "/**"
        for p in ROOT.glob("experiments/*/**/manifest.sha256")
        for p in [p.parent]
    )
    attributes = subprocess.run(
        _check_attr_command([d.replace("/**", "/manifest.json")
                             for d in freeze_dirs]),
        capture_output=True, text=True, check=True).stdout

    resolved: dict[str, dict[str, str]] = {}
    for line in attributes.splitlines():
        probe_path, attribute, value = line.split(": ")
        resolved.setdefault(probe_path, {})[attribute] = value

    assert freeze_dirs, "no content-hashed tree was found to check"
    for directory in freeze_dirs:
        probe = directory.replace("/**", "/manifest.json")
        assert resolved[probe] == {"text": "set", "eol": "lf"}, (
            "%s is content-hashed but git resolves %s, so its digest is the"
            " checkout's" % (directory, resolved[probe]))


def test_a_crlf_checkout_of_the_freeze_fails_verification(tmp_path):
    """A freeze that verifies on this host must fail when the bytes change,
    or it is verifying nothing. Rebuild the frozen tree with CRLF endings and
    the verifier must name the mismatch."""
    root = tmp_path / "worlds"
    for path in sorted(worlds.FROZEN_DIR.rglob("*.json")):
        target = root / path.relative_to(worlds.FROZEN_DIR)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    (root / "manifest.sha256").write_text(
        (worlds.FROZEN_DIR / "manifest.sha256").read_text(encoding="utf-8"))

    problems = worlds.verify_freeze(root)

    assert problems == ["manifest-hash-mismatch"]
