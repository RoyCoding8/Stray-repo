import json
import sys
from pathlib import Path

import names
import scores
import tags
import stats


def main(argv):
    here = Path(__file__).resolve().parent
    spec = json.loads((here.parent / "spec.json").read_text())
    payload = json.loads(Path(argv[1]).read_text())
    lo, hi = spec["bounds"]
    out = {"names": names.transform(payload["names"]),
           "scores": scores.adjust(payload["scores"], lo, hi),
           "tags": tags.tidy(payload["tags"]),
           "stat": stats.describe(payload["values"])}
    Path(argv[2]).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
