from __future__ import annotations

import json
import sys
from pathlib import Path

import detect
import operate


def main(argv):
    here = Path(__file__).resolve().parent
    spec = json.loads((here.parent / "spec.json").read_text())
    payload = json.loads(Path(argv[1]).read_text())
    mode = detect.mode(spec["rule"], spec, payload)
    values = operate.operands(spec["rule"], spec, payload, mode)
    out = {"mode": mode, "result": operate.apply(spec["ops"][mode], values)}
    Path(argv[2]).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
