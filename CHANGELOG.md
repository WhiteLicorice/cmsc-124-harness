# Changelog

Groups pin a tag, so anything that changes how `run_tests.py` grades gets an
entry here and an announcement through the usual channels.

## v1.1

The release the course runs on. Everything below came out of building a
language implementation and pointing the harness at it, which is now part of
this repository as `reference/`.

### Test files that asserted nothing now fail

An inline test whose annotations were typo'd parsed to zero expectations, so it
expected no output and exit 0. Any silent program passed it. A group could ship
broken annotations and CI would agree with them all semester.

A file with no expectations now fails, and so does a comment that reads like an
annotation but did not parse, such as `// expect : 1`. A file that really is
meant to produce nothing says `// expect nothing`.

### Several expected diagnostics are matched one at a time

They used to be joined together and looked for as a single block of text, which
demanded they appear adjacent and in order, and reported the whole block as
missing when only one of them was.

### A runaway test is killed outright

The fifteen second timeout stopped the process the harness had launched, which
on Windows is bash, and left the interpreter bash had started still running
with the output pipe open. The harness then waited on that pipe forever. A single infinite loop in a test would have hung grading rather than failing it.

### Everything is read and written as UTF-8

Python's default is the platform encoding, so a test file with an accented
character in it crashed on Windows and passed on the Linux runner.

### Unknown manifest settings are rejected

A misspelled `run_entryoint` used to fall back to `./run` in silence.

### Malformed input explains itself

A `.exit` file that does not hold a number, a `manifest.json` that is not valid JSON, and a `manifest.json` that is not an object each used to raise a Python traceback. They now name the file and say what is wrong with it.

### The self-test is a Python suite

`selftest.sh` still works and still does what the manuals say it does. The
checks behind it moved into `tests/`, written with `unittest`, and grew from
eight to well over a hundred. They run on Linux, Windows, and macOS.

## v1.0

First release. Language-agnostic runner, sidecar and inline annotation modes, configurable comment syntax, and a Windows launcher for shell entrypoints.
