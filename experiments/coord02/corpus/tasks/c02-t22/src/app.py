import json
import sys
from pathlib import Path

import emit
import render


def main(argv):
    here = Path(__file__).resolve().parent
    spec = json.loads((here.parent / "spec.json").read_text())
    conv = json.loads((here.parent / "convention.json").read_text())
    payload = json.loads(Path(argv[1]).read_text())
    packets = [emit.packet(row, conv) for row in payload["deliveries"]]
    out = {"total": render.total(packets, conv, spec.get("discount", 0))}
    if spec.get("notes", False):
        out["notes"] = [row.get("note", "")
                        for row in payload["deliveries"]]
    Path(argv[2]).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
