#!/bin/sh
# Prove each of run_bounded.py's load-bearing checks can actually fail.
#
# A test that has never gone red is not evidence. Each case below breaks
# exactly one mechanism in scripts/run_bounded.py, runs the one test that pins
# that mechanism, and requires the test to FAIL. The original is restored by
# `git stash`-free means: the file is copied to a temp path and moved back, so
# nothing touches the index and no history is rewritten.
#
# The mechanisms, and the defect each one exists to prevent:
#   1. SummaryScanner.is_summary   a completion test that fires early
#   2. the timeout path            a bound that does not bound
#   3. Slot.acquire                a concurrency cap that is only advice
#   4. Slot.release                a refused runner clearing a foreign slot
#   5. exit_code                   a child's own status swallowed
#   6. exit_code with no status    an unreaped child read as a zero
#
# Usage: sh tools/test_run_bounded_mutations.sh
#
# It rewrites scripts/run_bounded.py in place, so do not run it while
# another lane is editing that file.
set -u
REPO=$(git rev-parse --show-toplevel)
TOOL="$REPO/scripts/run_bounded.py"
BACKUP=$(mktemp "${TMPDIR:-/tmp}/run_bounded.XXXXXX.py")
PY="$REPO/.venv/bin/python"
FAILURES=0
# The isolation harness creates and migrates a database per redirectable seam
# it finds under tests/, which is 58 seconds before a single test runs. Each
# check below runs one node out of one file, so pointing the scanner at a
# directory holding only that file creates only the store that file needs.
SCAN=$(mktemp -d "${TMPDIR:-/tmp}/rb_mut_scan.XXXXXX")
export S09ISO_SCAN_DIR="$SCAN"
ln -sf "$REPO/tests/test_run_bounded.py" "$SCAN/test_run_bounded.py"

cp "$TOOL" "$BACKUP"
restore() { cp "$BACKUP" "$TOOL"; }
trap 'restore; rm -f "$BACKUP"; rm -rf "$SCAN"' EXIT

check() {  # check <label> <expected-outcome> <test-node>
  local label="$1" want="$2" node="$3" out rc
  out=$(cd "$REPO" && timeout 200 "$PY" -m pytest -p no:cacheprovider -q \
        --no-header -x "$node" 2>&1)
  rc=$?
  if [ "$want" = "red" ] && [ "$rc" -eq 0 ]; then
    echo "MUTATION NOT CAUGHT: $label -- the test still passed"
    FAILURES=$((FAILURES+1))
  elif [ "$want" = "red" ] && [ "$rc" -eq 5 ]; then
    echo "MUTATION NOT CAUGHT: $label -- the test did not even collect"
    FAILURES=$((FAILURES+1))
  elif [ "$want" = "green" ] && [ "$rc" -ne 0 ]; then
    echo "BASELINE BROKEN: $label -- the unmutated test failed"
    FAILURES=$((FAILURES+1))
  else
    echo "caught: $label (rc=$rc)"
  fi
}

echo "=== baseline, unmutated, all three must be green ==="
check "completion test" green tests/test_run_bounded.py::test_the_false_completion_log_is_rejected_and_the_real_one_is_not
check "timeout path"   green tests/test_run_bounded.py::test_a_bound_that_is_reached_reports_a_timeout_and_not_a_pass
check "slot cap"       green tests/test_run_bounded.py::test_a_second_runner_on_a_held_slot_is_refused

echo
echo "=== mutation 1: the completion test becomes the bug it replaced ==="
# Replace the summary regex with the keyword search the fourth lane used.
"$PY" - "$TOOL" <<'PYEOF'
import re, sys
path = sys.argv[1]
src = open(path).read()
mutant = (
    '    @staticmethod\n'
    '    def is_summary(line: str) -> bool:\n'
    '        return re.search(r"passed|failed|error", line) is not None\n')
start = src.index("    @staticmethod\n    def is_summary")
end = src.index("    def feed(self, line: str) -> bool:")
open(path, "w").write(src[:start] + mutant + "\n" + src[end:])
PYEOF
check "completion test" red tests/test_run_bounded.py::test_the_false_completion_log_is_rejected_and_the_real_one_is_not
check "parametrised non-summaries" red "tests/test_run_bounded.py::test_a_line_that_is_not_a_pytest_summary_is_not_told_apart"
check "the incomplete case" red tests/test_run_bounded.py::test_a_pytest_that_exits_zero_without_a_summary_is_not_a_pass
restore

echo
echo "=== mutation 2: the timeout path stops bounding ==="
# The bound is made unreachable, so the runner waits on a child it would
# otherwise have killed. That child sleeps 120s, so an unbounded runner
# overruns the check's own 200s timeout rather than failing its assertion.
# A killed-by-timeout check is still a caught mutant, so this is reported as
# one, but it costs 200s instead of 3s.
"$PY" - "$TOOL" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = "        try:\n            status = proc.wait(timeout=timeout_s)\n        except subprocess.TimeoutExpired:\n            reached_bound = True"
new = "        try:\n            status = proc.wait(timeout=timeout_s * 1000)\n        except subprocess.TimeoutExpired:\n            reached_bound = True"
assert old in src, "the timeout site did not match; the mutation is a no-op"
open(path, "w").write(src.replace(old, new, 1))
PYEOF
check "timeout path" red tests/test_run_bounded.py::test_a_bound_that_is_reached_reports_a_timeout_and_not_a_pass
check "the group kill" red tests/test_run_bounded.py::test_the_timeout_kills_the_whole_process_group_not_just_the_child
restore

echo
echo "=== mutation 3: the slot cap becomes advice ==="
# Acquire nothing: the cap now only records that it was asked for.
"$PY" - "$TOOL" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = "        refusal = slot.acquire(\" \".join(argv[:3]))"
new = "        refusal = None"
assert old in src, "the acquire site did not match; the mutation is a no-op"
open(path, "w").write(src.replace(old, new, 1))
PYEOF
check "slot cap" red tests/test_run_bounded.py::test_a_second_runner_on_a_held_slot_is_refused
restore

echo
echo
echo "=== mutation 4: release clears a slot unconditionally ==="
# `run` returns on a refusal before it reaches the `finally` that calls
# `release`, so this guard is not reachable through the CLI and a
# subprocess test cannot catch it. The mutation below is applied to
# `Slot.release` and the check calls the method directly, which is the only
# way to reach the branch at all. It is kept because the guard is the right
# shape for a method that clears a directory named by someone else, and a
# future caller of `release` need not rediscover that.
"$PY" - "$TOOL" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = "    def release(self) -> None:\n        if self._holder().get(\"pid\") == os.getpid():\n            self._clear()"
new = "    def release(self) -> None:\n        self._clear()"
assert old in src, "the release site did not match; the mutation is a no-op"
open(path, "w").write(src.replace(old, new, 1))
PYEOF
check "release clears only the slot it holds" red \
  tests/test_run_bounded.py::test_release_only_clears_a_slot_this_process_holds
restore

echo
echo "=== mutation 5: a child's own status is swallowed ==="
"$PY" - "$TOOL" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = "    if outcome.kind == \"exited\":\n        if outcome.status is None:"
new = "    if outcome.kind == \"exited\":\n        return EXIT_OK if outcome.status in (0, None) else EXIT_INCOMPLETE"
assert old in src, "the exit-code site did not match; the mutation is a no-op"
open(path, "w").write(src.replace(old, new, 1))
PYEOF
check "a child's own status" red tests/test_run_bounded.py::test_a_child_that_fails_keeps_its_own_status
check "the reserved-status remap" red "tests/test_run_bounded.py::test_a_child_status_is_reported_unless_it_collides_with_ours"
restore

echo
echo "=== mutation 6: an unreaped child is read as a zero ==="
# The guard `if outcome.status is None: raise` is deleted, so a None status
# falls through to _remap(None) and the caller exits 0. This is the one path
# by which the tool could report a pass it has no evidence for.
"$PY" - "$TOOL" <<'PYEOF'
import re, sys
path = sys.argv[1]
src = open(path).read()
start = src.index("    if outcome.kind == \"exited\":")
end = src.index("    if outcome.kind == \"timeout\":")
mutant = (
    '    if outcome.kind == "exited":\n'
    '        return _remap(outcome.status)\n')
open(path, "w").write(src[:start] + mutant + src[end:])
PYEOF
check "an unreaped child is not a zero" red tests/test_run_bounded.py::test_an_unreaped_child_is_never_reported_as_a_zero
restore

echo
echo "=== final check: the restored original is green again ==="
check "completion test" green tests/test_run_bounded.py::test_the_false_completion_log_is_rejected_and_the_real_one_is_not
check "timeout path"   green tests/test_run_bounded.py::test_a_bound_that_is_reached_reports_a_timeout_and_not_a_pass
check "slot cap"       green tests/test_run_bounded.py::test_a_second_runner_on_a_held_slot_is_refused

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "ALL MUTATIONS CAUGHT, and the original is green"
  exit 0
fi
echo "$FAILURES mutation(s) not caught"
exit 1
