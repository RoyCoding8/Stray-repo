"""Count the action vocabularies that do not meet the shared contract.

Five vocabularies were in play. `policy_step` is now translated onto the
contract, so a policy written to one is usable where the other is expected.
`frontier.OPERATE_KINDS` and `improve_channel.IMPROVE_KINDS` are not, and
this module makes the size of that gap countable.

`wait` is the interesting one. It appears in both remaining vocabularies and
has no equivalent among the six contract kinds, so it is not a mapping
problem to solve by choosing a closer word. It is either a seventh kind or a
scheduling concern that does not belong in the action vocabulary at all, and
deciding which is a design call rather than a refactor.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import improve_channel, frontier, policy_action, policy_step

CONTRACT = frozenset(policy_action.ACTION_KINDS)
TRANSLATED = frozenset(policy_step.STEP_KIND_TO_CONTRACT)


def vocabularies() -> dict:
    return {
        "contract": sorted(CONTRACT),
        "policy_step": sorted(policy_step.ACTION_KINDS),
        "frontier_operate": sorted(frontier.OPERATE_KINDS),
        "improve_channel": sorted(improve_channel.IMPROVE_KINDS),
    }


def coverage() -> dict:
    """Which vocabularies reach the contract, and which do not."""
    operate = frozenset(frontier.OPERATE_KINDS)
    improve = frozenset(improve_channel.IMPROVE_KINDS)
    return {
        "contract_is_six": len(CONTRACT) == 6,
        "policy_step_translated": policy_step.STEP_KIND_TO_CONTRACT,
        "operate_unmapped": sorted(operate - CONTRACT),
        "improve_unmapped": sorted(improve - CONTRACT),
        "kinds_with_no_contract_equivalent": sorted(
            {kind for vocabulary in (operate, improve)
             for kind in vocabulary} - CONTRACT),
    }


def kinds_missing_from_every_vocabulary() -> list[str]:
    """Contract kinds no other vocabulary names, which is where meaning hides."""
    named = set(policy_step.ACTION_KINDS) | set(frontier.OPERATE_KINDS) \
        | set(improve_channel.IMPROVE_KINDS)
    return sorted(CONTRACT - named)
