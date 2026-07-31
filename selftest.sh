#!/usr/bin/env bash
# selftest.sh -- sanity check that run_tests.py itself works correctly.
#
# Run this after cloning the repo, or after editing run_tests.py, to confirm
# the runner grades correctly: that it passes what should pass, fails what
# should fail, and explains itself instead of raising a traceback.
#
# The checks themselves live in tests/, written with Python's unittest, so they
# run the same way on Linux, macOS, and native Windows. This script is here
# because the name is what the manuals tell you to run.
#
# Usage: ./selftest.sh
# Exit code: 0 if all self-checks behave as expected, 1 otherwise.

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" > /dev/null 2>&1; then
  PYTHON=python
fi

cd "$SCRIPT_DIR" || exit 1
exec "$PYTHON" -m unittest discover --start-directory tests --top-level-directory tests --verbose
