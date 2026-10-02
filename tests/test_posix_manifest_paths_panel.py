"""A repository-relative path in machine-consumed data is host-independent.

`str(path.relative_to(root))` renders with the host separator, so a manifest
built on Windows names `world-0\\dev\\task.json` where the committed manifest
names `world-0/dev/task.json`. The digest of each file is then still correct,
but the manifest that describes them is a different byte string on each
operating system, so a freeze verifies on Linux and refuses on Windows. A
digest that depends on the host is not a digest of the content.

The same shape reaches two artifacts that are not digests, and both are held to
the same rule here. `production_callers` names files only inside a message a
reviewer reads. `_grep_ddmin` names them inside a `result.json` this repo
commits. The first would merely read wrong. The second would be the same
host-dependent value one level up.

Every assertion below is a literal separator, so each one fails if a builder
goes back to the host-native form.
"""

import json
import tempfile
from pathlib import Path

from experiments.ad01 import experience_axis, panel_variation, s09_e1_gates_probe
from experiments.ad01 import s09_plan_claims, worlds

PANEL_FIRST = "world-0/dev/panel-w0-dev-gr-00.json"
WORLDS_FIRST = "world-0/dev/ad01-w0-dev-gr-00.json"
AXIS_FIRST = "world-0/dev/exp-w0-dev-gr-00.json"


def test_a_built_panel_manifest_names_its_files_with_forward_slashes():
    with tempfile.TemporaryDirectory() as root:
        built = panel_variation.build_freeze(Path(root))
    assert built["files"][0]["path"] == PANEL_FIRST
    assert [entry["path"] for entry in built["files"]][:2] == [
        PANEL_FIRST, "world-0/dev/panel-w0-dev-gr-01.json"]


def test_the_committed_panel_manifest_is_what_a_host_rebuilds():
    directory = Path(panel_variation.FROZEN_DIR)
    committed = json.loads((directory / "manifest.json").read_bytes())
    assert committed["files"][0]["path"] == PANEL_FIRST
    assert panel_variation.build_manifest(directory) == committed


def test_the_panel_freeze_verifies_and_its_pin_covers_its_manifest():
    directory = Path(panel_variation.FROZEN_DIR)
    assert panel_variation.verify_freeze(directory) == []
    raw = (directory / "manifest.json").read_bytes()
    assert (directory / "manifest.sha256").read_text().strip() == \
        panel_variation._digest(raw)


def test_a_built_worlds_manifest_names_its_files_with_forward_slashes():
    with tempfile.TemporaryDirectory() as root:
        built = worlds.build_freeze(Path(root))
        assert built["files"][0]["path"] == WORLDS_FIRST
        assert worlds.verify_freeze(Path(root)) == []


def test_the_committed_worlds_manifest_is_what_a_host_rebuilds():
    directory = Path(worlds.FROZEN_DIR)
    committed = json.loads((directory / "manifest.json").read_bytes())
    assert committed["files"][0]["path"] == WORLDS_FIRST
    with tempfile.TemporaryDirectory() as root:
        built = worlds.build_freeze(Path(root))
    assert [entry["path"] for entry in built["files"]] == \
        [entry["path"] for entry in committed["files"]]
    assert worlds.verify_freeze(directory) == []


def test_a_built_experience_axis_manifest_names_its_files_with_forward_slashes():
    with tempfile.TemporaryDirectory() as root:
        built = experience_axis.build_freeze(Path(root))
        assert built["files"][0]["path"] == AXIS_FIRST
        assert experience_axis.verify_freeze(Path(root)) == []


def test_a_production_caller_is_named_with_forward_slashes():
    """The list is interpolated into a message, so only its form is at risk.

    `check_uncallable` renders `callers[0]` into a sentence a reviewer reads,
    and `production_callers` is also called by `test_m0_plan_claims`, which
    asserts `== []` and so cannot see a separator. Nothing hashes this list,
    which is why it is a different concern from the three manifest sites.
    """
    cit = s09_plan_claims.Citation(
        "experiments/ad01/live_construct.py", 1, "construct_policy", 0, "e")
    assert s09_plan_claims.production_callers(cit) == [
        "experiments/ad01/trajectory.py", "scripts/s09_pilot.py"]


def test_a_ddmin_hit_is_recorded_with_forward_slashes(monkeypatch):
    """`_grep_ddmin` feeds a written evidence file, not a printed line.

    `control_column_state` puts the list into the probe payload and `main`
    writes that payload to `reports/evidence/**/result.json`. An evidence file
    that records `worlds\\x.json` on one host and `worlds/x.json` on another is
    the same host-dependent value the manifests had.
    """
    with tempfile.TemporaryDirectory() as root:
        nested = Path(root) / "evidence-ad01"
        (nested / "worlds").mkdir(parents=True)
        (nested / "worlds" / "plan.md").write_text(
            "the ddmin split is unattested", encoding="utf-8")
        (nested / "worlds" / "quiet.md").write_text("nothing here",
                                                    encoding="utf-8")
        monkeypatch.setattr(s09_e1_gates_probe, "EVIDENCE", nested)
        monkeypatch.setattr(s09_e1_gates_probe, "ROOT", Path(root))
        assert s09_e1_gates_probe._grep_ddmin() == [
            "evidence-ad01/worlds/plan.md"]
