"""A supersession marker is worth nothing unless a check can say it stopped being true.

`reports/evidence/` carries five `RETRACTED.md` notices and, as of this pass,
machine-readable markers beside the artifacts they describe. Measured
before the markers existed: zero of the five directories had any sibling
artifact mentioning the retraction, and `e3-postfix-ladder.json` contained
none of `retract`, `withdrawn`, `invalid` or `superseded` across 165045
bytes. An annotation nobody reaches is not a correction.

The prohibition on editing committed evidence bytes is why the marker is a
sibling and not a field. A sibling is decorative unless something binds it
to the file it describes, so `artifact_sha256` is load-bearing and every
claim below is a way of making it fail.

Each test is paired with a mutation: read the assertion, then read the test
that breaks it. A test here that could not fail is a test of nothing.
"""

from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import evidence_supersession as sup

LADDER = "reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json"
MATRIX = "reports/evidence/inv_r1_e1_swe_ceiling/matrix.json"
WITNESS = "reports/evidence/inv_r1_e3_selection/e3-store-witness.json"
OUTPUT_RUN = "reports/evidence/inv_r1_m4_baseline/output-run.json"

LADDER_MARKER = "reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.supersession.json"
MATRIX_MARKER = "reports/evidence/inv_r1_e1_swe_ceiling/matrix.supersession.json"
WITNESS_MARKER = "reports/evidence/inv_r1_e3_selection/e3-store-witness.supersession.json"
OUTPUT_RUN_MARKER = "reports/evidence/inv_r1_m4_baseline/output-run.supersession.json"


def _marker(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _study(tmp_path, artifact_bytes=b"{}"):
    """A tmp repo holding one artifact, and the path to write a marker beside it."""
    directory = tmp_path / "reports/evidence/study"
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / "artifact.json"
    artifact.write_bytes(artifact_bytes)
    annotation = directory / "annotation.md"
    annotation.write_text("synthetic annotation\n", encoding="utf-8")
    return directory / "artifact.supersession.json", artifact


def _rebase(marker, artifact):
    """Re-point a committed marker at the fixture's artifact, digest included."""
    rebased = dict(marker)
    rebased["artifact"] = "reports/evidence/study/artifact.json"
    rebased["artifact_sha256"] = sup.sha256_file(artifact)
    rebased["annotation"] = "reports/evidence/study/annotation.md"
    return rebased


# --- every marker is checked; unavailable historical bytes remain UNKNOWN ---

def test_unavailable_history_is_unknown_and_never_a_clean_tree(capsys):
    """Unavailable backward edges stay UNKNOWN and keep the CLI nonzero."""
    markers = sup.iter_markers(ROOT)
    expected = []
    for path in markers:
        marker = sup.load_marker(path)
        ref = marker.get("intact_at_ref")
        if ref and marker["shape"] in sup.BACKWARD_EDGES \
                and sup._ref_missing(ROOT, ref):
            expected.append(
                "%s: UNKNOWN intact_at_ref %r is not available in this repository"
                % (path.name, ref))

    assert sup.check_evidence_tree(ROOT) == expected
    status = sup.main(["--repo-root", str(ROOT)])
    assert status == (1 if expected else 0)
    output = capsys.readouterr().out
    if expected:
        assert "UNKNOWN intact_at_ref" in output
        assert "%d problem(s)" % len(expected) in output
        assert status != 0, "UNKNOWN history must not qualify as validation PASS"



def test_every_marked_artifact_exists_and_the_digest_is_the_ones_on_disk():
    markers = sup.iter_markers(ROOT)

    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=str(ROOT), capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    tracked_markers = {
        path.decode("utf-8") for path in tracked if path
        and path.decode("utf-8").endswith(".supersession.json")
        and path.decode("utf-8").startswith(
            ("reports/evidence/", "evidence-ad01/"))
    }
    discovered = {path.relative_to(ROOT).as_posix() for path in markers}
    assert discovered == tracked_markers
    for path in markers:
        marker = sup.load_marker(path)
        artifact = ROOT / marker["artifact"]

        assert artifact.is_file()
        assert marker["artifact_sha256"] == sup.sha256_file(artifact)


def test_the_ladder_marker_is_discoverable_from_the_ladder_without_being_told_to_look():
    """The reachability claim itself, as an assertion.

    The rule is: a marker must sit beside the artifact and be named after
    it, so that a reader who lists the directory or a machine that globs
    `*.supersession.json` reaches it starting from the artifact. The naming
    is the whole mechanism, so it is asserted rather than assumed.
    """
    siblings = sorted(p.name for p in (ROOT / Path(LADDER)).parent.iterdir())

    assert "e3-postfix-ladder.supersession.json" in siblings
    assert Path(LADDER_MARKER).name == Path(LADDER).name.replace(
        ".json", sup.MARKER_SUFFIX)


@pytest.mark.parametrize("artifact,marker", [
    (LADDER, LADDER_MARKER),
    (MATRIX, MATRIX_MARKER),
    (WITNESS, WITNESS_MARKER),
    (OUTPUT_RUN, OUTPUT_RUN_MARKER),
])
def test_every_marker_sorts_beside_the_artifact_it_describes(artifact, marker):
    """A sidecar with a name that does not sort beside its artifact is a
    sidecar a reader listing the directory has to know to look for."""
    assert Path(marker).parent == Path(artifact).parent
    assert (Path(marker).name < Path(artifact).name) or (
        Path(artifact).stem + sup.MARKER_SUFFIX == Path(marker).name)


# --- the four rows are four relations, and the shapes keep them apart ---

def test_the_ladder_is_scoped_and_the_rest_of_the_file_survives():
    """B6. The verdict is on one pointer, not on the artifact."""
    marker = _marker(LADDER_MARKER)

    assert marker["shape"] == "SCOPE"
    assert [entry["pointer"] for entry in marker["void_scope"]] == ["$.committed_ladder"]
    assert marker["surviving_claim"]
    assert marker["container_mislabelled"] is False


def test_the_ladder_pointer_resolves_in_the_artifact_it_describes():
    document = json.loads((ROOT / LADDER).read_text(encoding="utf-8"))
    entry = _marker(LADDER_MARKER)["void_scope"][0]

    assert isinstance(sup.resolve_pointer(document, entry["pointer"]), dict)


def test_the_witness_is_scoped_to_the_severed_block_only():
    """B1. Only the unreachable block is void; $.connected is untouched."""
    marker = _marker(WITNESS_MARKER)
    document = json.loads((ROOT / WITNESS).read_text(encoding="utf-8"))

    assert marker["void_scope"][0]["pointer"] == "$.severed"
    assert marker["surviving_claim"].count("$.connected") == 1
    assert sup.resolve_pointer(document, "$.connected")["bindings"]


def test_the_matrix_is_void_and_carries_the_backward_edge():
    """B2. Wrong now, correct at a ref. No existing convention carries this."""
    marker = _marker(MATRIX_MARKER)

    assert marker["shape"] == "EDITS"
    assert marker["verdict"] == "VOID"
    assert marker["void_scope"][0]["pointer"] == "$"
    assert marker["intact_at_ref"] == "d422c93"


def test_the_matrix_is_intact_at_the_ref_or_exactly_unknown():
    """Verify preserved bytes when possible; unavailable ancestry is UNKNOWN."""
    marker = _marker(MATRIX_MARKER)
    ref = marker["intact_at_ref"]
    commit = subprocess.run(
        ["git", "cat-file", "-e", "%s^{commit}" % ref], cwd=str(ROOT),
        capture_output=True,
    )
    if commit.returncode:
        assert sup.check_marker(ROOT, ROOT / MATRIX_MARKER) == [
            "%s: UNKNOWN intact_at_ref %r is not available in this repository"
            % (Path(MATRIX_MARKER).name, ref),
        ]
        return
    pre = subprocess.run(["git", "cat-file", "blob",
                          "%s:%s" % (ref, MATRIX)], cwd=str(ROOT),
                         capture_output=True).stdout

    assert pre
    assert len(pre) == 5167881
    assert hashlib.sha256(pre).hexdigest().startswith("5928d4e1f66119")



def test_the_container_is_mislabelled_and_voids_nothing():
    """B8. The referent is a directory name; the file is right."""
    marker = _marker(OUTPUT_RUN_MARKER)

    assert marker["shape"] == "VESSEL"
    assert marker["verdict"] == "CONTAINER_MISLABELLED"
    assert marker["container_mislabelled"] is True
    assert marker["void_scope"] == []


def test_a_mislabelled_container_is_not_allowed_to_void_anything():
    """The one shape where voiding would destroy the only copy of the data."""
    marker = _marker(OUTPUT_RUN_MARKER)
    marker["void_scope"] = [{"pointer": "$", "reason": "wrong"}]

    with pytest.raises(sup.MarkerError, match="must have an empty void_scope"):
        sup.validate_marker(marker)


def test_the_four_rows_four_shapes_and_no_shape_collapses():
    shapes = {sup.load_marker(p)["shape"] for p in sup.iter_markers(ROOT)}

    assert shapes == {"SCOPE", "EDITS", "VESSEL"}


# --- each falsifiable claim, paired with what would break it ---

def _problems(tmp_path, marker, artifact_bytes=b"{}"):
    """Write `marker` beside a fixture artifact and report what it fails on."""
    path, _ = _study(tmp_path, artifact_bytes)
    path.write_text(json.dumps(marker), encoding="utf-8")
    return sup.check_marker(tmp_path, path)


def test_a_marker_whose_digest_does_not_match_the_artifact_is_reported_stale(tmp_path):
    """This is the assertion that makes a sibling worth more than prose."""
    path, artifact = _study(tmp_path, b'{"committed_ladder": {}}')
    marker = _rebase(_marker(LADDER_MARKER), artifact)
    marker["artifact_sha256"] = "0" * 64
    path.write_text(json.dumps(marker), encoding="utf-8")

    problems = sup.check_marker(tmp_path, path)

    assert any("stale marker" in p for p in problems)


def test_a_pointer_that_no_longer_resolves_is_reported(tmp_path):
    path, artifact = _study(tmp_path, b'{"committed_ladder": {}}')
    marker = _rebase(_marker(LADDER_MARKER), artifact)
    marker["void_scope"] = [{"pointer": "$.no_such_key", "reason": "x"}]
    path.write_text(json.dumps(marker), encoding="utf-8")

    assert any("no such key" in p for p in sup.check_marker(tmp_path, path))


def test_a_marker_naming_an_artifact_that_is_gone_is_reported(tmp_path):
    marker = dict(_marker(LADDER_MARKER))
    marker["artifact"] = "reports/evidence/study/vanished.json"
    path = tmp_path / "reports/evidence/study"
    path.mkdir(parents=True)
    (path / "artifact.supersession.json").write_text(json.dumps(marker),
                                                     encoding="utf-8")

    assert any("does not exist" in p
               for p in sup.check_marker(tmp_path, path / "artifact.supersession.json"))


def test_a_backward_edge_to_a_commit_that_does_not_exist_is_reported(tmp_path):
    path, artifact = _study(tmp_path)
    marker = _rebase(_marker(MATRIX_MARKER), artifact)
    marker["intact_at_ref"] = "deadbee" * 5
    path.write_text(json.dumps(marker), encoding="utf-8")

    assert sup.check_marker(tmp_path, path) == [
        "%s: UNKNOWN intact_at_ref %r is not available in this repository"
        % (path.name, marker["intact_at_ref"]),
    ]


def test_an_unknown_key_is_refused_rather_than_ignored(tmp_path):
    """A typo in a field name must not pass silently as an unrecorded claim."""
    path, artifact = _study(tmp_path, b'{"committed_ladder": {}}')
    marker = _rebase(_marker(LADDER_MARKER), artifact)
    marker["void_scpoe"] = []
    path.write_text(json.dumps(marker), encoding="utf-8")

    problems = sup.check_marker(tmp_path, path)

    assert len(problems) == 1
    assert "unknown key" in problems[0]


@pytest.mark.parametrize("shape,scope,mutation,message", [
    ("SCOPE", [], lambda m: None, "SCOPE needs a non-empty void_scope"),
    ("DATA", [], lambda m: None, "DATA needs a non-empty void_scope"),
    ("VESSEL", [{"pointer": "$", "reason": "x"}], lambda m: None,
     "VESSEL must have an empty void_scope"),
    ("VESSEL", [], lambda m: m.update(surviving_claim="x"),
     "must not carry surviving_claim"),
    ("SCOPE", [{"pointer": "$.committed_ladder", "reason": "x"}],
     lambda m: m.update(surviving_claim=""), "missing 'surviving_claim'"),
])
def test_the_schema_refuses_a_marker_missing_what_its_shape_owes(
        tmp_path, shape, scope, mutation, message):
    """Each shape owes a different set of fields; the schema owes to say so.

    The scope is supplied per case rather than derived, because a marker
    carrying the wrong scope for its shape must be refused for *that*
    reason and not for whichever rule happens to be checked first.
    """
    path, artifact = _study(tmp_path, b'{"committed_ladder": {}}')
    marker = _rebase(_marker(LADDER_MARKER), artifact)
    marker["shape"] = shape
    marker["void_scope"] = scope
    mutation(marker)
    path.write_text(json.dumps(marker), encoding="utf-8")

    problems = sup.check_marker(tmp_path, path)

    assert problems and message in problems[0]


def test_a_backward_edge_on_a_shape_that_has_no_past_is_refused(tmp_path):
    """Only EDITS carries time. On SCOPE it would imply a recovery that
    does not exist, which is worse than leaving it out."""
    path, artifact = _study(tmp_path, b'{"committed_ladder": {}}')
    marker = _rebase(_marker(LADDER_MARKER), artifact)
    marker["intact_at_ref"] = "d422c93"
    path.write_text(json.dumps(marker), encoding="utf-8")

    problems = sup.check_marker(tmp_path, path)

    assert problems and "intact_at_ref is only meaningful for EDITS" in problems[0]


def test_an_unknown_shape_is_refused(tmp_path):
    path, artifact = _study(tmp_path, b'{"committed_ladder": {}}')
    marker = _rebase(_marker(LADDER_MARKER), artifact)
    marker["shape"] = "WRONG"
    path.write_text(json.dumps(marker), encoding="utf-8")

    assert any("not in" in p for p in sup.check_marker(tmp_path, path))


# --- pointer resolution is total over what these artifacts actually contain ---

def test_a_pointer_that_descends_into_a_scalar_is_refused_not_crashed():
    document = json.loads((ROOT / OUTPUT_RUN).read_text(encoding="utf-8"))

    with pytest.raises(sup.MarkerError, match="descends into str"):
        sup.resolve_pointer(document, "$.run_id.deeper")


def test_an_index_past_the_end_of_a_list_is_refused():
    with pytest.raises(sup.MarkerError, match="no such index"):
        sup.resolve_pointer({"rows": [1, 2]}, "$.rows.9")


def test_a_pointer_that_does_not_start_at_the_root_is_refused():
    with pytest.raises(sup.MarkerError, match="must start with"):
        sup.resolve_pointer({"a": 1}, "a")
