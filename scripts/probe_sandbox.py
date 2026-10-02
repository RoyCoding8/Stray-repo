from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    from settlement import exec_profile

    probe = exec_profile.probe_gvisor()
    print(
        json.dumps(
            {
                "profile": probe.name,
                "available": probe.available,
                "code": probe.code.value,
                "reason": probe.reason,
                "detail": probe.detail,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
