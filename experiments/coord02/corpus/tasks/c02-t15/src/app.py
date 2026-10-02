import json
import sys
from pathlib import Path

import detect
import operate


def main(argv):
    here = Path(__file__).resolve().parent
    spec = json.loads((here.parent / "spec.json").read_text())
    payload = json.loads(Path(argv[1]).read_text())
    mode = detect.classify(spec["rule"], payload)
    out = {"mode": mode,
           "result": operate.compute(spec["rule"], spec, payload, mode)}
    Path(argv[2]).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
