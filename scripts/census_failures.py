"""Parse a pytest -q run log into a joined failure census.

Joins the short-summary `FAILED path::test` lines to the report bodies above
them, then emits one row per failure: file, test, terminal exception class,
and a verbatim message line.
"""
import re
import sys
from collections import defaultdict

HDR = re.compile(r"^_{2,}(\s.*\s)_{2,}$")
SUMMARY = re.compile(r"^(FAILED|ERROR) (\S+?)::(.*?)(?: - (.*))?$")
# pytest ends every report body with "<path>:<lineno>: <ExcClass>"
FOOTER = re.compile(r"^([\w./\-]+\.py):(\d+): (\w+)$")


def parse(path):
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    blocks, cur = [], None
    for i, l in enumerate(lines):
        m = HDR.match(l)
        if m and len(l) >= 60:
            cur = {"line": i, "title": m.group(1).strip(), "body": []}
            blocks.append(cur)
            continue
        if cur is not None:
            cur["body"].append(l)

    summary = []
    for i, l in enumerate(lines):
        m = SUMMARY.match(l)
        if m:
            summary.append({
                "kind": m.group(1), "file": m.group(2),
                "test": m.group(3), "tail": m.group(4), "line": i,
            })

    by_test = {}
    for b in blocks:
        t = b["title"]
        m = re.match(r"^ERROR at setup of (.+)$", t)
        by_test.setdefault(m.group(1) if m else t, []).append(b)

    rows = []
    for s in summary:
        cands = by_test.get(s["test"], [])
        b = cands[0] if cands else None
        exc, msg, where = "(no report body)", s["tail"] or "", ""
        if b is not None:
            footer = None
            for l in reversed(b["body"]):
                fm = FOOTER.match(l.strip())
                if fm:
                    footer = fm
                    break
            exc = footer.group(3) if footer else "(unknown)"
            where = footer.group(1) + ":" + footer.group(2) if footer else ""
            e_lines = [l[4:] if l.startswith("E   ") else l[2:]
                       for l in b["body"] if re.match(r"^E\s{2,}\S", l)]
            # first E line that is not the bare class repeat and not a diff aside
            pick = None
            for t in e_lines:
                if t.startswith("assert ") or (
                        re.match(r"^[\w.]+\w*(Error|Exception|Exit|Interrupt):", t)
                        and "assert" not in t):
                    pick = t
                    break
            msg = pick or (e_lines[0] if e_lines else "")
        rows.append({
            "kind": s["kind"], "file": s["file"], "test": s["test"],
            "exc": exc, "where": where, "msg": " ".join(msg.split())[:300],
        })
    return rows


if __name__ == "__main__":
    rows = parse(sys.argv[1])
    by_file = defaultdict(list)
    for r in rows:
        by_file[r["file"]].append(r)
    print("TOTAL", len(rows))
    for f in sorted(by_file, key=lambda k: -len(by_file[k])):
        print("\n## %s  (%d)" % (f, len(by_file[f])))
        for r in by_file[f]:
            print("  [%s] %s :: %s" % (r["exc"], r["test"], r["msg"][:220]))
