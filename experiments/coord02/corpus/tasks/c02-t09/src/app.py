import json
import sys
from pathlib import Path

import producer
import consumer


def main(argv):
    here = Path(__file__).resolve().parent
    spec = json.loads((here.parent / "spec.json").read_text())
    payload = json.loads(Path(argv[1]).read_text())
    units = spec["units"]
    base = [producer.to_base(r["v"], r["u"], units)
            for r in payload["readings"]]
    lo, hi = spec["bounds"]
    out = {"values": [consumer.from_base(x, payload["want"], units)
                      for x in base],
           "flags": []}
    out["flags"] = [consumer.flag(v, lo, hi) for v in out["values"]]
    Path(argv[2]).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
