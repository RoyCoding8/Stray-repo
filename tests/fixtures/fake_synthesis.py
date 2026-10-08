"""Candidate task output; qualification uses real verifier subprocesses."""

import json
import runpy
import sys
from pathlib import Path

mode, args = sys.argv[1], sys.argv[2:]
if args[0] == "exec":
    ws = Path(args[args.index("-C") + 1])
    if "task.json" in args[-1]:
        data = {
            "name": "double",
            "instruction": "Implement double(n), returning twice an integer.",
            "workspace": {"double.py": "def double(n): pass\n"},
            "reference": {"double.py": "def double(n): return 2*n\n"},
            "verifier": {
                "double_test.py": "import unittest\nfrom double import double\nclass Test(unittest.TestCase):\n"
                "    def test_values(self):\n        self.assertEqual(double(3),6)\n"
                "        self.assertEqual(double(-2),-4)\n        self.assertEqual(double(0),0)\n"
            },
            "test_files": ["double_test.py"],
        }
        if mode == "bad-reference":
            data["reference"] = data["workspace"]
        if mode == "passing-stub":
            data["workspace"] = data["reference"]
        (ws / "task.json").write_text(json.dumps(data), encoding="utf-8")
sys.argv[1] = "ok"
runpy.run_path(str(Path(__file__).with_name("fake_codex.py")), run_name="__main__")
