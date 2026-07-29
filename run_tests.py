#!/usr/bin/env python3
"""
cmsc-124-harness: a language-agnostic test runner for CMSC 124 laboratory activities.

This script never parses a pair's grammar. It only ever invokes the pair's own
`./run` entrypoint on committed test files, then diffs stdout + exit code against
expectations the pair themselves committed (either inline `// expect:` comments,
or sidecar .expected/.exit files). It is identical across every pair and every
host language -- see manifest.json in each test folder for the per-folder knobs.

Usage:
    python3 run_tests.py <test-folder> [--repo-root <path-to-repo-root>]

Exit code of this script itself: 0 if every test in the folder passed, 1 otherwise.
This is deliberate -- CI can gate on this script's own exit code directly.
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

IS_WINDOWS = os.name == "nt"

# Extensions Windows can hand to CreateProcess directly. Anything else is a
# script that needs its interpreter named explicitly.
WINDOWS_NATIVE_SUFFIXES = {".exe", ".com", ".bat", ".cmd"}

# Where Git for Windows puts bash when its bin directory is not on PATH, which
# is the default for the "Git from the command line" install option.
WINDOWS_BASH_FALLBACKS = (
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
)

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


def find_windows_bash():
    """Locates a bash Windows can execute, or returns None."""
    found = shutil.which("bash")
    if found:
        return found
    for candidate in WINDOWS_BASH_FALLBACKS:
        if Path(candidate).exists():
            return candidate
    return None


def read_shebang_interpreter(script: Path):
    """
    Returns the interpreter named on a script's shebang line, e.g. "bash" for
    both `#!/bin/bash` and `#!/usr/bin/env bash`. Returns None when the file has
    no shebang or cannot be read as text.
    """
    try:
        with open(script, "rb") as f:
            first_line = f.readline(256).decode("utf-8", errors="replace")
    except OSError:
        return None

    if not first_line.startswith("#!"):
        return None

    parts = first_line[2:].strip().split()
    if not parts:
        return None

    interpreter = Path(parts[0].replace("\\", "/")).name
    if interpreter == "env" and len(parts) > 1:
        interpreter = Path(parts[1].replace("\\", "/")).name
    return interpreter


def build_launch_command(run_entrypoint: str, repo_root: Path):
    """
    Turns a pair's run entrypoint into an argv prefix the host OS can actually
    execute, and returns (argv_prefix, error_message).

    On Linux and macOS the entrypoint runs directly, exactly as the run contract
    describes. Windows cannot execute a file with a shebang line, so the
    interpreter has to be named explicitly: `run` becomes `bash run`. Without
    this, every pair working on native Windows gets WinError 193 instead of test
    results, even though their entrypoint is perfectly correct.
    """
    if not IS_WINDOWS:
        return [run_entrypoint], None

    entrypoint_path = (repo_root / run_entrypoint).resolve()
    if entrypoint_path.suffix.lower() in WINDOWS_NATIVE_SUFFIXES:
        return [run_entrypoint], None

    interpreter = read_shebang_interpreter(entrypoint_path) or "bash"

    if interpreter in ("bash", "sh", "dash", "zsh"):
        bash = find_windows_bash()
        if not bash:
            return None, (
                "ERROR: this looks like a shell script, and Windows cannot run one without bash.\n"
                "Install Git for Windows (it ships bash), or run this harness from WSL."
            )
        return [bash, run_entrypoint], None

    if interpreter.startswith("python"):
        return [sys.executable, run_entrypoint], None

    resolved = shutil.which(interpreter)
    if not resolved:
        return None, (
            f"ERROR: '{run_entrypoint}' asks for interpreter '{interpreter}', "
            "which is not on PATH on this machine."
        )
    return [resolved, run_entrypoint], None


def run_program(run_entrypoint: str, flag, test_file: Path, repo_root: Path):
    cmd, error = build_launch_command(run_entrypoint, repo_root)
    if error:
        return "", error, -1

    if flag:
        cmd.append(flag)

    # Hand the entrypoint a repo-relative POSIX path. Absolute Windows paths
    # with backslashes do not survive being passed into a shell script, and
    # relative paths keep failure output identical on every platform.
    try:
        test_argument = test_file.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        test_argument = str(test_file)
    cmd.append(test_argument)

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
    except OSError as exc:
        return "", f"ERROR: could not execute '{run_entrypoint}' -- {exc}", -1


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
