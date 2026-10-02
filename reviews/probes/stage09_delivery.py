"""Read-only replay check for the stage 9 delivery at 1d90c2e."""

import copy
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "experiments")]

from experiments import doubles


def main():
    counts, instruments = Counter(), Counter()
    for path in sorted((ROOT / "evidence_inv01_live/exports").glob("*.json")):
        records = doubles.recorded_from_export(json.loads(path.read_text(encoding="utf-8")))
        for index, rec in enumerate(records):
            action = copy.deepcopy(rec["proposal"])
            inputs = action.get("inputs", {})
            probe = {"index": index, "packet_digest": rec["packet_digest"],
                     "action": action, "versions": {k: inputs.get(k) for k in doubles.VERSION_FIELDS},
                     "observations": []}
            identity = doubles.check_replay_prefix(records, probe)
            assert identity["verdict"] == "supported"
            assert identity["results"] == rec["results"]
            counts["identity_supported"] += 1
            instruments[action.get("instrument")] += 1
            changed = copy.deepcopy(probe)
            changed["action"]["instrument"] = "stop" if action.get("instrument") != "stop" else "development"
            result = doubles.check_replay_prefix(records, changed)
            assert result["verdict"] == "unsupported"
            assert result["reason"].startswith("unsupported-decision")
            assert not result["results"]
            counts["changed_instrument_unsupported"] += 1
    assert dict(counts) == {"identity_supported": 28, "changed_instrument_unsupported": 28}
    assert dict(instruments) == {"diagnostic": 23, "development": 5}
    print(json.dumps({"reviewed_commit": "1d90c2e6c553f6ad1b03cfd6145fe4cad86c7821",
                      "checks": dict(counts), "recorded_instruments": dict(instruments),
                      "scope": "Exact recorded actions versus changed instruments. No alternate execution, policy ranking, provider calls or database effects."}, indent=2))


if __name__ == "__main__":
    main()
