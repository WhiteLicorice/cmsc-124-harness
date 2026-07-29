#!/usr/bin/env python3
"""
cmsc124-grader: a language-agnostic test runner for CMSC 124 laboratory activities.

This script never parses a pair's grammar. It only ever invokes the pair's own
`./run` entrypoint on committed test files, then diffs stdout + exit code against
expectations the pair themselves committed (either inline `// expect:` comments,
or sidecar .expected/.exit files). It is identical across every pair and every
host language -- see manifest.json in each test folder for the per-folder knobs.

Usage:
    python3 run_tests.py <test-folder> [--run <path-to-run-script>]

Exit code of this script itself: 0 if every test in the folder passed, 1 otherwise.
This is deliberate -- CI can gate on this script's own exit code directly.
"""

import argparse
import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MANIFEST = {
    # Extension of source files under this folder that count as test cases.
    "ext": ".src",
    # Optional CLI flag passed to `./run` before the test file path, e.g. "--tokenize".
    # Omit (null) for plain-execution labs.
    "flag": None,
    # "inline"  -> read `// expect:` style comments out of the source file itself.
    # "sidecar" -> read a matching .expected / .exit file next to the source file.
    "mode": "sidecar",
    # Only used when mode == "inline". The comment prefix the pair uses.
    # Matches the Crafting Interpreters convention by default.
    "expect_prefix": "expect:",
    "expect_error_prefix": "expect runtime error:",
    "expect_compile_error_prefix": "expect error:",
    # Path (relative to repo root) to the pair's run entrypoint.
    "run_entrypoint": "./run",
}

EXIT_OK = 0
EXIT_STATIC_ERROR = 65
EXIT_RUNTIME_ERROR = 70


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Summary:
    results: list = field(default_factory=list)

    def add(self, r: TestResult):
        self.results.append(r)

    @property
    def failed(self):
        return [r for r in self.results if not r.passed]

    def print_report(self):
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            print(f"[{status}] {r.name}")
            if not r.passed and r.detail:
                for line in r.detail.splitlines():
                    print(f"       {line}")
        total = len(self.results)
        ok = total - len(self.failed)
        print(f"\n{ok}/{total} tests passed.")


def load_manifest(folder: Path) -> dict:
    manifest = dict(DEFAULT_MANIFEST)
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            user_manifest = json.load(f)
        manifest.update(user_manifest)
    return manifest


def find_test_files(folder: Path, ext: str):
    return sorted(folder.rglob(f"*{ext}"))


def run_program(run_entrypoint: str, flag, test_file: Path, repo_root: Path):
    cmd = [run_entrypoint]
    if flag:
        cmd.append(flag)
    cmd.append(str(test_file))
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT: process exceeded 15s", -1
    except FileNotFoundError:
        return "", f"ERROR: could not execute '{run_entrypoint}' -- is it committed and chmod +x?", -1


def parse_inline_expectations(test_file: Path, manifest: dict):
    """
    Scans a source file for trailing `// expect:` style comments and returns
    (expected_stdout_lines, expected_stderr_substring_or_None, expected_exit_code).

    `expect:` lines check stdout (program output). `expect runtime error:` and
    `expect error:` lines check stderr (diagnostics) and set the exit code
    accordingly -- matching the convention that runtime/static errors are
    diagnostics, not program output, and so belong on stderr per the run
    contract. Comment syntax is assumed to be `//` since every language in
    this course's pool supports it; if a pair's invented language uses
    different comment syntax, they should use sidecar mode instead (see
    manifest.json "mode").
    """
    expect_prefix = manifest["expect_prefix"]
    error_prefix = manifest["expect_error_prefix"]
    compile_error_prefix = manifest["expect_compile_error_prefix"]

    expected_lines = []
    expected_stderr_lines = []
    expected_exit = EXIT_OK

    line_re = re.compile(r"//\s*(.*)$")

    text = test_file.read_text()
    for line in text.splitlines():
        m = line_re.search(line)
        if not m:
            continue
        comment = m.group(1).strip()
        if comment.startswith(error_prefix):
            expected_stderr_lines.append(comment[len(error_prefix):].strip())
            expected_exit = EXIT_RUNTIME_ERROR
        elif comment.startswith(compile_error_prefix):
            expected_stderr_lines.append(comment[len(compile_error_prefix):].strip())
            expected_exit = EXIT_STATIC_ERROR
        elif comment.startswith(expect_prefix):
            expected_lines.append(comment[len(expect_prefix):].strip())

    expected_stderr = "\n".join(expected_stderr_lines) if expected_stderr_lines else None
    return expected_lines, expected_stderr, expected_exit


def parse_sidecar_expectations(test_file: Path):
    """
    Looks for <test_file_stem>.expected and <test_file_stem>.exit next to the
    test file. .expected is compared verbatim against stdout. .exit is an
    integer exit code; if absent, 0 (success) is assumed.
    """
    expected_path = test_file.with_suffix(".expected")
    exit_path = test_file.with_suffix(".exit")

    if not expected_path.exists():
        return None, None  # signals "no sidecar found"

    expected_stdout = expected_path.read_text()

    expected_exit = EXIT_OK
    if exit_path.exists():
        expected_exit = int(exit_path.read_text().strip())

    return expected_stdout, expected_exit


def run_single_test(test_file: Path, manifest: dict, repo_root: Path) -> TestResult:
    name = str(test_file.relative_to(repo_root)) if test_file.is_relative_to(repo_root) else str(test_file)

    mode = manifest["mode"]
    expected_stderr_substring = None

    if mode == "inline":
        expected_lines, expected_stderr_substring, expected_exit = parse_inline_expectations(test_file, manifest)
        expected_stdout = "\n".join(expected_lines) + ("\n" if expected_lines else "")
    elif mode == "sidecar":
        expected_stdout, expected_exit = parse_sidecar_expectations(test_file)
        if expected_stdout is None:
            return TestResult(name, False, "No .expected sidecar file found next to this test.")
    else:
        return TestResult(name, False, f"Unknown mode '{mode}' in manifest.json.")

    stdout, stderr, actual_exit = run_program(
        manifest["run_entrypoint"], manifest.get("flag"), test_file, repo_root
    )

    problems = []

    if actual_exit != expected_exit:
        problems.append(f"exit code: expected {expected_exit}, got {actual_exit}")

    if stdout.strip("\n") != expected_stdout.strip("\n"):
        diff = "\n".join(
            difflib.unified_diff(
                expected_stdout.splitlines(),
                stdout.splitlines(),
                fromfile="expected",
                tofile="actual",
                lineterm="",
            )
        )
        problems.append(f"stdout mismatch:\n{diff}")

    if expected_stderr_substring is not None and expected_stderr_substring not in stderr:
        problems.append(
            f"stderr mismatch: expected to find:\n  {expected_stderr_substring}\ngot stderr:\n  {stderr.strip()}"
        )

    if problems:
        detail = "\n".join(problems)
        if stderr.strip() and expected_stderr_substring is None:
            detail += f"\n(stderr was: {stderr.strip()})"
        return TestResult(name, False, detail)

    return TestResult(name, True)


def main():
    parser = argparse.ArgumentParser(description="CMSC 124 language-agnostic test runner.")
    parser.add_argument("test_folder", help="Path to the folder of test files, e.g. tests/lab1")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repo root, used to resolve the run entrypoint and relative test names. Defaults to cwd.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    test_folder = Path(args.test_folder).resolve()

    if not test_folder.exists():
        print(f"ERROR: test folder '{test_folder}' does not exist.", file=sys.stderr)
        sys.exit(1)

    manifest = load_manifest(test_folder)
    test_files = find_test_files(test_folder, manifest["ext"])

    if not test_files:
        print(f"ERROR: no test files with extension '{manifest['ext']}' found under '{test_folder}'.", file=sys.stderr)
        sys.exit(1)

    summary = Summary()
    for test_file in test_files:
        result = run_single_test(test_file, manifest, repo_root)
        summary.add(result)

    summary.print_report()

    sys.exit(0 if not summary.failed else 1)


if __name__ == "__main__":
    main()
