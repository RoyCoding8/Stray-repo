"""Every Score.measure / reader_echoer / score_response call carries authority.

`Score.measure` executes policy source, so a call without a store is a
measurement of the refusal rather than of the policy. Reading that as a
property of the policy is what finding (c) was: eighteen tests in
`test_s09_e2_scored.py` scored no policy at all and reported the result as a
verdict about the model.

Migrating those call sites was a column-addressed edit across four files, and
two of the passes silently dropped the keyword from twenty-one calls while
leaving the file parseable. A check that only asserts the file parses would
have called that green. This asserts the property the edits were for, and it
is here rather than in the lane's history because the next caller to add a
`measure(` can get it wrong the same way.

Run it directly: `python tests/check_execution_authority.py` from the
repository root.
"""
import ast
import pathlib
import sys

TARGETS = {"measure", "reader_echoer", "score_response"}
FILES = [
    "tests/test_s09_e2_scored.py",
    "tests/test_inv_b13b_replseed.py",
    "tests/test_ad01_panel_variation.py",
    "tests/test_ad01_experience_axis.py",
]


def main() -> int:
    problems = []
    counts = {}
    for name in FILES:
        path = pathlib.Path(name)
        raw = path.read_bytes()
        crlf = raw.count(b"\r\n")
        bare = raw.count(b"\n") - crlf
        if bare:
            problems.append("%s: %d bare LF, expected CRLF throughout"
                            % (name, bare))
        text = raw.decode("utf-8").replace("\r\n", "\n")
        tree = ast.parse(text)
        calls = missing = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            label = getattr(node.func, "attr", None) \
                or getattr(node.func, "id", None)
            if label not in TARGETS:
                continue
            calls += 1
            if not any(kw.arg == "authority" for kw in node.keywords):
                missing += 1
                problems.append(
                    "%s:%d %s( has no authority= keyword"
                    % (name, node.lineno, label))
        counts[name] = (calls, missing)

    for name, (calls, missing) in counts.items():
        print("%s: %d calls, %d without authority" % (name, calls, missing))
    if problems:
        print("PROBLEMS:")
        for problem in problems:
            print("  " + problem)
        return 1
    print("OK: every call carries authority, every file is CRLF")
    return 0


if __name__ == "__main__":
    sys.exit(main())