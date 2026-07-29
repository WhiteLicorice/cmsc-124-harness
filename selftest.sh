#!/usr/bin/env bash
# selftest.sh -- fast sanity check that run_tests.py itself works correctly.
#
# Run this after cloning the repo, or after editing run_tests.py, to confirm:
#   1. The bundled sidecar-mode example passes (exit 0).
#   2. The bundled inline-mode example passes (exit 0), including the
#      runtime-error / exit-70 / stderr-matching path.
#   3. A deliberately broken test is correctly detected as a FAILURE
#      (i.e. run_tests.py doesn't just always report success).
#
# Takes a few seconds. No network access or per-language toolchains required --
# everything here uses tiny bash stand-ins for a real pair's ./run script.
#
# Usage: ./selftest.sh
# Exit code: 0 if all self-checks behave as expected, 1 otherwise.

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILURES=0

pass() { echo "  ok  - $1"; }
fail() { echo "  ✗   - $1"; FAILURES=$((FAILURES + 1)); }

echo "== 1. sidecar-mode example (expect: PASS) =="
cd "$SCRIPT_DIR/examples/sidecar-mode" || exit 1
if python3 "$SCRIPT_DIR/run_tests.py" tests/lab0 > /tmp/selftest_out_1.txt 2>&1; then
  pass "sidecar-mode example passed as expected"
else
  fail "sidecar-mode example should have passed but didn't"
  cat /tmp/selftest_out_1.txt
fi

echo
echo "== 2. inline-mode example, incl. runtime error path (expect: PASS) =="
cd "$SCRIPT_DIR/examples/inline-mode" || exit 1
if python3 "$SCRIPT_DIR/run_tests.py" tests/lab3 > /tmp/selftest_out_2.txt 2>&1; then
  pass "inline-mode example passed as expected"
else
  fail "inline-mode example should have passed but didn't"
  cat /tmp/selftest_out_2.txt
fi

echo
echo "== 3. deliberately broken test (expect: FAIL, i.e. run_tests.py must catch it) =="
TMP_BROKEN="$(mktemp -d)"
mkdir -p "$TMP_BROKEN/tests/lab0"
cp "$SCRIPT_DIR/examples/sidecar-mode/run" "$TMP_BROKEN/run"
chmod +x "$TMP_BROKEN/run"
echo "actual output" > "$TMP_BROKEN/tests/lab0/broken.src"
echo "a completely different expected line" > "$TMP_BROKEN/tests/lab0/broken.expected"
cd "$TMP_BROKEN" || exit 1
if python3 "$SCRIPT_DIR/run_tests.py" tests/lab0 > /tmp/selftest_out_3.txt 2>&1; then
  fail "run_tests.py reported PASS on a test it should have flagged as broken -- this is a real bug"
  cat /tmp/selftest_out_3.txt
else
  pass "run_tests.py correctly detected the deliberately broken test as a FAILURE"
fi
rm -rf "$TMP_BROKEN"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "All self-checks behaved as expected. run_tests.py is working correctly."
  exit 0
else
  echo "$FAILURES self-check(s) did NOT behave as expected. Do not trust run_tests.py until this is fixed."
  exit 1
fi
