import json
import shutil
import tempfile
from pathlib import Path

from experiments.ad01 import s09_panel_inventory as inventory_tool
from experiments.representation import splits


PANEL = Path(__file__).parents[1] / "experiments" / "ad01" / "worlds"


def test_inventory_reports_generator_clusters_and_iso_pairs():
    inventory = inventory_tool.build_inventory(PANEL)

    assert inventory.cell_count == 54
    assert inventory.cluster_count == 10
    assert inventory.family_cluster_count("software") == 4
    assert inventory.family_cluster_count("graph") == 6
    assert inventory.isomorphic_pair_count == 9
    assert [(pair.dev_task_id, pair.within_task_id)
            for pair in inventory.isomorphic_pairs] == [
        ("ad01-w0-dev-gr-00", "ad01-w0-within-gr-00"),
        ("ad01-w0-dev-gr-01", "ad01-w0-within-gr-01"),
        ("ad01-w0-dev-gr-02", "ad01-w0-within-gr-02"),
        ("ad01-w1-dev-gr-00", "ad01-w1-within-gr-00"),
        ("ad01-w1-dev-gr-01", "ad01-w1-within-gr-01"),
        ("ad01-w1-dev-gr-02", "ad01-w1-within-gr-02"),
        ("ad01-w2-dev-gr-00", "ad01-w2-within-gr-00"),
        ("ad01-w2-dev-gr-01", "ad01-w2-within-gr-01"),
        ("ad01-w2-dev-gr-02", "ad01-w2-within-gr-02"),
    ]


def test_inventory_decision_reports_unreachable_software_power():
    decision = inventory_tool.build_inventory(PANEL).decision()

    assert decision["verdict"] == "cannot_be_powered"
    assert decision["power"]["software"] == {
        "cluster_count": 4,
        "minimum_p": 0.125,
        "powered": False,
        "required_clusters": 6,
    }
    assert decision["power"]["graph"] == {
        "cluster_count": 6,
        "minimum_p": 0.03125,
        "powered": True,
        "required_clusters": 6,
    }
    assert decision["power"]["all"]["cluster_count"] == 10
    assert decision["power"]["all"]["minimum_p"] == 0.001953125
    assert decision["power"]["additional_generation_families_required"] == {
        "software": 2,
        "graph": 0,
    }


def test_added_cell_in_existing_template_does_not_add_cluster():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "worlds"
        shutil.copytree(PANEL, root)
        generated = splits.generate_ad01("software", 0, "dev", 3)
        target = root / "world-0" / "dev" / "ad01-w0-dev-sw-03.json"
        target.write_text(json.dumps(generated, sort_keys=True) + "\n")

        inventory = inventory_tool.build_inventory(root)

    assert inventory.cell_count == 55
    assert inventory.cluster_count == 10
    assert inventory.family_cluster_count("software") == 4


def test_alpha_decision_uses_minimum_sign_flip_count():
    assert inventory_tool.minimum_sign_flip_p(0) is None
    assert inventory_tool.minimum_sign_flip_p(4) == 0.125
    assert inventory_tool.minimum_clusters_for_alpha(0.05) == 6
    assert inventory_tool.minimum_clusters_for_alpha(0.01) == 8
