"""Kernel-owned driver. Staged with pristine verifier files, never agent files."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest


def main():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    sys.path.insert(0, str(root))
    log = io.StringIO()
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        suite = unittest.TestSuite()
        loader = unittest.TestLoader()
        for rel in sys.argv[1:]:
            suite.addTests(loader.loadTestsFromName(rel[:-3].replace("/", ".")))
        result = unittest.TextTestRunner(stream=log).run(suite)
    passed = result.testsRun > 0 and result.wasSuccessful() and not result.skipped
    print(json.dumps({"status": "ok" if passed else "error", "data": {
        "tests": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "log": log.getvalue()[-16000:]}}))


if __name__ == "__main__":
    main()
