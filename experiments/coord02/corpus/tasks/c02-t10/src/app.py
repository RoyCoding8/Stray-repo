import json
import sys
from pathlib import Path

import maker
import shaper
import judge


def main(argv):
    here = Path(__file__).resolve().parent
    spec = json.loads((here.parent / "spec.json").read_text())
    payload = json.loads(Path(argv[1]).read_text())
    units = spec["units"]
    base = [maker.to_base(r["v"], r["u"], units)
            for r in payload["readings"]]
    values = [shaper.from_base(x, payload["want"], units) for x in base]
    lo, hi = spec["bounds"]
    out = {"values": values,
           "flags": [judge.flag(v, lo, hi) for v in values]}
    Path(argv[2]).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
