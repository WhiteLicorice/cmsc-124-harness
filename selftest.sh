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
echo "== 4. python entrypoint instead of a shell one (expect: PASS) =="
TMP_PY="$(mktemp -d)"
mkdir -p "$TMP_PY/tests/lab0"
printf '#!/usr/bin/env python3\nimport sys\nprint(open(sys.argv[1]).read(), end="")\n' > "$TMP_PY/run"
chmod +x "$TMP_PY/run"
echo "python entrypoint works" > "$TMP_PY/tests/lab0/hello.src"
echo "python entrypoint works" > "$TMP_PY/tests/lab0/hello.expected"
cd "$TMP_PY" || exit 1
if python3 "$SCRIPT_DIR/run_tests.py" tests/lab0 > /tmp/selftest_out_4.txt 2>&1; then
  pass "python entrypoint launched correctly"
else
  fail "python entrypoint should have passed but didn't -- check interpreter resolution"
  cat /tmp/selftest_out_4.txt
fi
rm -rf "$TMP_PY"

echo
echo "== 5. orphaned .expected file (expect: a warning, but still PASS) =="
TMP_ORPHAN="$(mktemp -d)"
mkdir -p "$TMP_ORPHAN/tests/lab0"
cp "$SCRIPT_DIR/examples/sidecar-mode/run" "$TMP_ORPHAN/run"
chmod +x "$TMP_ORPHAN/run"
echo "kept" > "$TMP_ORPHAN/tests/lab0/kept.src"
echo "kept" > "$TMP_ORPHAN/tests/lab0/kept.expected"
echo "stale" > "$TMP_ORPHAN/tests/lab0/renamed_away.expected"
cd "$TMP_ORPHAN" || exit 1
if python3 "$SCRIPT_DIR/run_tests.py" tests/lab0 > /tmp/selftest_out_5.txt 2>&1 &&
   grep -q "renamed_away.expected" /tmp/selftest_out_5.txt; then
  pass "orphaned expectation was reported without failing the run"
else
  fail "an orphaned .expected file should warn while the real test still passes"
  cat /tmp/selftest_out_5.txt
fi
rm -rf "$TMP_ORPHAN"

echo
echo "== 6. non-zero .exit with empty .expected (expect: PASS) =="
TMP_EXIT="$(mktemp -d)"
mkdir -p "$TMP_EXIT/tests/lab1"
cat > "$TMP_EXIT/run" <<'RUNEOF'
#!/usr/bin/env bash
# Stands in for an interpreter rejecting a file: diagnostics on stderr, exit 65.
set -e
echo "[line 1] Error: Unterminated string." >&2
exit 65
RUNEOF
chmod +x "$TMP_EXIT/run"
echo '{"ext": ".src", "mode": "sidecar"}' > "$TMP_EXIT/tests/lab1/manifest.json"
echo 'var broken = "no closing quote' > "$TMP_EXIT/tests/lab1/unterminated.src"
: > "$TMP_EXIT/tests/lab1/unterminated.expected"
echo "65" > "$TMP_EXIT/tests/lab1/unterminated.exit"
cd "$TMP_EXIT" || exit 1
if python3 "$SCRIPT_DIR/run_tests.py" tests/lab1 > /tmp/selftest_out_6.txt 2>&1; then
  pass "static-error test matched its .exit file and empty .expected"
else
  fail "a test with .exit 65 and empty .expected should have passed"
  cat /tmp/selftest_out_6.txt
fi
rm -rf "$TMP_EXIT"

echo
echo "== 7. inline mode with non-// comment syntax (expect: PASS) =="
TMP_COMMENT="$(mktemp -d)"
mkdir -p "$TMP_COMMENT/tests/lab3"
cp "$SCRIPT_DIR/examples/inline-mode/run" "$TMP_COMMENT/run"
chmod +x "$TMP_COMMENT/run"
printf '{"ext": ".src", "mode": "inline", "comment_prefix": ["#", "--"]}\n' \
  > "$TMP_COMMENT/tests/lab3/manifest.json"
printf 'PRINT 7\n# expect: 7\nPRINT 8\n-- expect: 8\n' > "$TMP_COMMENT/tests/lab3/hash.src"
cd "$TMP_COMMENT" || exit 1
if python3 "$SCRIPT_DIR/run_tests.py" tests/lab3 > /tmp/selftest_out_7.txt 2>&1; then
  pass "a language using # and -- for comments works in inline mode"
else
  fail "configurable comment_prefix should have matched # and -- annotations"
  cat /tmp/selftest_out_7.txt
fi
rm -rf "$TMP_COMMENT"

echo
echo "== 8. inline mode with no comment_prefix (expect: clean error, not a traceback) =="
TMP_NOPREFIX="$(mktemp -d)"
mkdir -p "$TMP_NOPREFIX/tests/lab3"
cp "$SCRIPT_DIR/examples/inline-mode/run" "$TMP_NOPREFIX/run"
chmod +x "$TMP_NOPREFIX/run"
printf '{"ext": ".src", "mode": "inline", "comment_prefix": ""}\n' \
  > "$TMP_NOPREFIX/tests/lab3/manifest.json"
printf 'PRINT 7\n' > "$TMP_NOPREFIX/tests/lab3/a.src"
cd "$TMP_NOPREFIX" || exit 1
python3 "$SCRIPT_DIR/run_tests.py" tests/lab3 > /tmp/selftest_out_8.txt 2>&1
if grep -q "comment_prefix" /tmp/selftest_out_8.txt && ! grep -q "Traceback" /tmp/selftest_out_8.txt; then
  pass "an empty comment_prefix is reported as a configuration error"
else
  fail "an empty comment_prefix should produce a readable error, not a traceback"
  cat /tmp/selftest_out_8.txt
fi
rm -rf "$TMP_NOPREFIX"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "All self-checks behaved as expected. run_tests.py is working correctly."
  exit 0
else
  echo "$FAILURES self-check(s) did NOT behave as expected. Do not trust run_tests.py until this is fixed."
  exit 1
fi
