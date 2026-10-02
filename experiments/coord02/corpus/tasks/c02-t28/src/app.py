import json
import sys
from pathlib import Path

import producer
import consumer


def main(argv):
    here = Path(__file__).resolve().parent
    spec = json.loads((here.parent / "spec.json").read_text())
    payload = json.loads(Path(argv[1]).read_text())
    values = producer.scale(payload["cells"], payload["factor"])
    out = {"values": values, "total": consumer.summarize(values)}
    Path(argv[2]).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
