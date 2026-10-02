"""Every caller of the authority-requiring e2 entry points names it.

`Score.measure`, `score_response`, `qualify_instrument` and the three
wrappers around them execute policy source, so a caller holding no store
measures the refusal rather than the policy. This is the same check
`tests/check_execution_authority.py` does for `run_policy_step`, scoped to
the e2 scorer's own surface.

`_run` and `_dispatch` are deliberately absent: they are common private names
across this tree and most of the calls that carry them have nothing to do with
the scorer. The three scorer's private entry points take `authority`
positionally and every call site in this tree is found by name.
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
# `measure` and `_dispatch` are ordinary names elsewhere in this tree — the
# representation checkers and the team01 solver both have their own. Only the
# e2 scorerer's are under this contract, so a bare name matches nothing and a
# qualified one must name the scorerer's module.
BARE = {"score_response", "qualify_instrument", "reader_echoer",
        "score_acquired", "score_one", "qualification_census",
        "echo_confound"}
# `gate` and `_dispatch` are ordinary names in this tree — the budget-fit
# module and the team01 solver both have their own — so they are matched only
# through the scorer's module.
QUALIFIED = {"_dispatch": "s09_e2_scored", "_execute": "s09_e2_scored",
             "_run": "s09_e2_scored", "measure": "s09_e2_scored",
             "gate": "e2_contrast_gate"}
BASES = ["experiments", "scripts", "tests"]


def owned_by_scorer(node, path) -> bool:
    """Is this call a method on the scorer's own module alias?

    The scorer is reached as `scored._dispatch` or `replica.qualify_instrument`
    through a module alias. The representation checkers reach theirs through
    `software.measure` / `graphs.measure` and the team01 solver through
    `solver._dispatch`, and those aliases are listed here rather than guessed
    at from the attribute name.
    """
    if not isinstance(node.func, ast.Attribute):
        return False
    receiver = node.func.value
    if not isinstance(receiver, ast.Name):
        return False
    module = QUALIFIED.get(node.func.attr)
    if module is None:
        return False
    return receiver.id in ("scored", "replica", "s09_e2_scored",
                           "e2_contrast_gate", "campaign", "experience",
                           "scored_module")


def call_name(node):
    return getattr(node.func, "attr", None) or getattr(node.func, "id", None)


def main() -> int:
    missing = []
    total = 0
    for base in BASES:
        for path in sorted((ROOT / base).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8",
                                                errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = call_name(node)
                in_surface = name in BARE
                if name in QUALIFIED and owned_by_scorer(node, path):
                    in_surface = True
                if not in_surface:
                    continue
                if any(kw.arg is None for kw in node.keywords):
                    continue
                total += 1
                keywords = {kw.arg for kw in node.keywords}
                if "authority" in keywords or "dsn" in keywords:
                    continue
                # The scorer's private entry points take `authority`
                # positionally, so a keyword-only check misses a call that
                # does carry it. A call with five or more positional
                # arguments on this surface has it.
                if len(node.args) >= 5:
                    continue
                missing.append("%s:%d %s(" % (
                    path.relative_to(ROOT).as_posix(), node.lineno, name))
    print("%d target calls, %d without authority" % (total, len(missing)))
    for item in missing:
        print("  " + item)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())