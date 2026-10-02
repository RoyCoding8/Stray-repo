"""A frozen field written in a form the freeze does not name is still a write.

`_attempts_frozen_write` is the static half of the freeze. It walks an
AST and matches two node types, `ast.Assign` and `ast.AugAssign`. Python has
three more statements that bind a name, and a candidate that selects one of
them passes a check that reads as a guarantee:

    grant: dict = {}          ast.AnnAssign
    (grant := view["grant"])  ast.NamedExpr

Both write a `FROZEN_FIELDS` entry. `ast.AnnAssign` is not rarer than the
form it replaces -- an annotated local is ordinary Python -- and
`ast.NamedExpr` is the natural way to write a value into a name inside a
conditional expression, which is how a menu is picked at run time.

The check is a whitelist of node types, and a whitelist of the two forms
that happened to be written first is what turns "does not write frozen
state" into "does not write frozen state with `=`, `+=` or a call". The
fix is at that boundary: ask whether a node binds a name at all rather than
enumerating the syntaxes that do.

`admit_revision_under_freeze` is the caller. The frozen state is compared
before and after the bytes run, but a candidate is refused *before* it runs,
so the dynamic check cannot see a write that the static check let past.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def test_an_annotated_binding_of_a_frozen_field_is_a_frozen_write():
    """`grant: dict = {}` writes the grant.

    `ast.AnnAssign` is the annotated-binding form. A candidate that writes the
    grant this way is refused by the same check that refuses `grant = {}`.
    """
    from experiments.ad01 import improve_channel as channel

    assert not channel._attempts_frozen_write(
        "def f(view, state):\n    return state.remaining\n"), (
        "the control is not a clean read, so this proves nothing")

    assert channel._attempts_frozen_write(
        "def f(view, state):\n    grant: dict = {}\n    return grant\n"), (
        "an annotated binding of a frozen field passed the freeze")


def test_a_walrus_binding_of_a_frozen_field_is_a_frozen_write():
    """`(grant := x)` writes the grant.

    `ast.NamedExpr` is the walrus form, and it is how a name is bound inside a
    conditional expression. A candidate that writes the grant this way is
    refused by the same check.
    """
    from experiments.ad01 import improve_channel as channel

    assert channel._attempts_frozen_write(
        "def f(view, state):\n"
        "    value = view.get('grant', {})\n"
        "    (grant := value)\n"
        "    return grant\n"), (
        "a walrus binding of a frozen field passed the freeze")


def test_the_freeze_still_admits_a_reader_and_still_refuses_the_plain_forms():
    """The widening does not turn the check into a blanket refusal.

    Read access is legitimate and stays legitimate, and the two forms the
    check already caught are still caught. A check that refuses everything
    would satisfy both tests above, so this is what distinguishes a correct
    widening from a blanket one.
    """
    from experiments.ad01 import improve_channel as channel

    assert not channel._attempts_frozen_write(
        "def f(view, state):\n    return view['grant'], state['used']\n"), (
        "reading a frozen field was refused, so the freeze is not a write check")

    for source, label in (
            ("def f(state):\n    state.used = 1\n", "Assign"),
            ("def f(state, v):\n    setattr(state, 'used', v)\n", "setattr")):
        assert channel._attempts_frozen_write(source), (
            f"{label} stopped being a frozen write after the widening")