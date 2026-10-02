import json
import sys
from pathlib import Path

import intake
import convert
import finalize


def main(argv):
    here = Path(__file__).resolve().parent
    spec = json.loads((here.parent / "spec.json").read_text())
    payload = json.loads(Path(argv[1]).read_text())
    pairs = intake.extract(payload["parcels"])
    values = convert.to_want(pairs, spec["units"], payload["want"])
    lo, hi = spec["bounds"]
    out = {"values": values,
           "flags": finalize.check(values, lo, hi)}
    Path(argv[2]).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
