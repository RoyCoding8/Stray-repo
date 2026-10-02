import json
import sys
from pathlib import Path

import names
import tags
import pconv
import cconv


def main(argv):
    here = Path(__file__).resolve().parent
    spec = json.loads((here.parent / "spec.json").read_text())
    payload = json.loads(Path(argv[1]).read_text())
    values = pconv.convert(payload["readings"], spec["units"],
                           payload["want"])
    lo, hi = spec["cbounds"]
    out = {"names": names.transform(payload["names"]),
           "tags": tags.tidy(payload["tags"]),
           "values": values,
           "flags": cconv.label(values, lo, hi)}
    Path(argv[2]).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
