from __future__ import annotations

import json
import sys
from pathlib import Path

import textops
import numops


def main(argv):
    here = Path(__file__).resolve().parent
    spec = json.loads((here.parent / "spec.json").read_text())
    payload = json.loads(Path(argv[1]).read_text())
    out = {"texts": textops.transform(spec["text_op"], payload["texts"]),
           "numbers": numops.summarize(spec["num_op"], payload["numbers"])}
    Path(argv[2]).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
