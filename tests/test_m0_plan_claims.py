"""The connected-study table stays tied to current source evidence."""
from __future__ import annotations

import ast
import subprocess
from types import SimpleNamespace

import experiments.ad01.s09_plan_claims as claims
from experiments.ad01.s09_plan_claims import (
    CITATIONS,
    LAST_VERIFIED,
    REPO_ROOT,
    main,
    re_read_needed,
)


def _definition_line(text: str, symbol: str) -> int | None:
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and node.name == symbol:
            return node.lineno
    return None


def test_the_table_covers_ten_edges_and_reports_current_line_pins():
    assert {citation.row for citation in CITATIONS} == set(range(1, 11))
    assert claims.check_citations() == []

    plan = (REPO_ROOT / "reports/PLAN-STAGE-09-CONNECTED.md").read_text(
        encoding="utf-8")
    for reference in (
        "live_construct.py:874", "construct.py:427", "policy_step.py:457",
        "method_exec.run_step_out_of_process:1633", "parse_action:80",
        "s09_arm_parity.py:615", "checker.py:138",
        "agenda_policy._step_remaining:784", "s09_study_preflight.py:1294",
        "s09_exposure_ledger.py:544", "s09_arm_parity.py:708", ":737",
        ":811", "s09_causal_proof.qualify_pre_launch:574", ":1193",
    ):
        assert reference in plan, reference


def test_the_current_checker_has_no_unqualified_failures(capsys):
    assert claims._is_ancestor(LAST_VERIFIED, "HEAD")
    assert re_read_needed() == []
    assert main() == 0
    output = capsys.readouterr().out
    assert "all 20 citations hold" in output
    assert "no commit after" in output


def test_the_re_read_trigger_reports_a_post_pin_source_change(
        tmp_path, monkeypatch):
    """A real source edit after verification creates visible re-read debt."""
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True,
            text=True).stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    source = tmp_path / "source.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    git("add", "source.py")
    git("commit", "-qm", "baseline")
    baseline = git("rev-parse", "HEAD")
    source.write_text("VALUE = 2\n", encoding="utf-8")
    git("commit", "-qam", "change cited source")
    changed = git("rev-parse", "HEAD")

    monkeypatch.setattr(claims, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(claims, "LAST_VERIFIED", baseline)
    monkeypatch.setattr(claims, "CITATIONS", (SimpleNamespace(path="source.py"),))
    monkeypatch.setattr(claims, "ABSENT_SYMBOLS", ())
    monkeypatch.setattr(claims, "UNIMPORTED_MODULES", ())
    monkeypatch.setattr(claims, "UNCONNECTED_PAIRS", ())
    assert len(claims.re_read_needed(tip=changed)) == 1


def test_definition_lookup_ignores_docstring_mentions():
    assert _definition_line("def present():\n    pass\n", "present") == 1
    source = "'''mentions absent_function only as prose.'''\n"
    assert _definition_line(source, "absent_function") is None
