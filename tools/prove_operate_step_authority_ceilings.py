"""The ceiling arithmetic must fail if the authority is unthreaded.

Threading the authority does not add executions; it MOVES three of them onto
the study's own allocation, where a ceiling counts them. A ceiling sized before
the thread therefore understates what the study spends, and the run that has to
happen is the run that gets refused.

This proves the arithmetic in `tools/prove_operate_step_authority.py` is load
bearing rather than decorative: it re-derives the per-investigation cost and the
two study ceilings, then checks that the OLD ceilings (19 and 30, the figures
`reports/cap-sheets/e0-e12-child-execution-caps.md` froze when the choices
settled elsewhere) no longer fit once the choices are charged.

    python tools/prove_operate_step_authority_ceilings.py

Exits nonzero if the old ceilings would still fit, which would mean the thread
moved nothing and the new figures are padding.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in ("", "src", "scripts"):
    sys.path.insert(0, str(ROOT / extra) if extra else str(ROOT))

import prove_operate_step_authority as census  # noqa: E402

#: The figures the cap sheet froze, before the authority was threaded.
FROZEN_E0 = 19
FROZEN_E12 = 30


def main() -> int:
    figures = census.ceilings()
    per = figures["sandbox_calls_per_investigation"]
    # The sheet's own arithmetic: E0 pays for two investigations plus one
    # retained-acquisition binding the live arm alone can reach; E12 for three
    # plus one binding per retained arm.
    e0_spends = 2 * per + 3
    e12_spends = 3 * per + 6
    report = {
        "sandbox_calls_per_investigation": per,
        "E0_spends": e0_spends,
        "E0_SANDBOX_CALLS": figures["E0_SANDBOX_CALLS"],
        "E0_frozen_was": FROZEN_E0,
        "E0_frozen_would_fit": e0_spends <= FROZEN_E0,
        "E12_spends": e12_spends,
        "E12_SANDBOX_CALLS": figures["E12_SANDBOX_CALLS"],
        "E12_frozen_was": FROZEN_E12,
        "E12_frozen_would_fit": e12_spends <= FROZEN_E12,
    }
    print(__doc__.strip())
    for key in sorted(report):
        print("%-28s %s" % (key, report[key]))
    # The frozen ceilings MUST stop fitting. If they still fit, the thread
    # moved no cost onto the study and raising them was padding.
    stale = report["E0_frozen_would_fit"] or report["E12_frozen_would_fit"]
    if stale:
        print("\nFAIL: the frozen ceilings still fit, so the thread moved no "
              "cost onto the study allocation and the new figures are "
              "padding rather than a recount.")
        return 1
    print("\nOK: the frozen ceilings no longer fit, so they were a real "
          "undercount once the choices settled under the study allocation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())