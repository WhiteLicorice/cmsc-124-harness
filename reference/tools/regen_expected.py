#!/usr/bin/env python3
"""
Regenerates the sidecar .expected and .exit files for a lab folder.

    python3 reference/tools/regen_expected.py reference/tests/lab1

Sidecar expectations are exact stdout, down to the line numbers in a token
dump. Typing a few hundred of those by hand produces typos, and typos in a
grading corpus are worse than no corpus: they teach you to ignore red.

So they are generated, and then read. Run this, look at the diff, and only
commit output you believe. A generated expectation nobody reviews records
whatever the implementation did that day, bugs included.

An .exit file is only written when the exit code is not zero, so a folder full
of .exit files reading 0 does not obscure the handful that matter.
"""

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REFERENCE_ROOT = Path(__file__).resolve().parent.parent
HARNESS_ROOT = REFERENCE_ROOT.parent


def _import_run_tests():
    """
    Borrows the harness's own launcher.

    Generating expectations with a different launch path than the one that
    grades them is how you produce a corpus that only passes on one operating
    system. Windows in particular cannot execute a file with a shebang line, and
    run_tests.py already knows what to do about that.
    """
    path = HARNESS_ROOT / "run_tests.py"
    spec = importlib.util.spec_from_file_location("run_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_tests = _import_run_tests()


def load_manifest(folder: Path) -> dict:
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        return {"ext": ".lox", "flag": None}
    with open(manifest_path) as f:
        return json.load(f)


def regenerate(folder: Path, check_only: bool) -> int:
    manifest = load_manifest(folder)
    if manifest.get("mode") != "sidecar":
        print(
            f"ERROR: '{folder}' is not a sidecar-mode folder. Inline expectations "
            "live in the test files themselves and are written by hand.",
            file=sys.stderr,
        )
        return 1

    flag = manifest.get("flag")
    extension = manifest.get("ext", ".lox")

    entrypoint = manifest.get("run_entrypoint", "./run")
    launch, error = run_tests.build_launch_command(entrypoint, REFERENCE_ROOT)
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    changed = []
    for test in sorted(folder.rglob(f"*{extension}")):
        relative = test.resolve().relative_to(REFERENCE_ROOT).as_posix()
        command = launch + ([flag] if flag else []) + [relative]
        result = subprocess.run(
            command,
            cwd=REFERENCE_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )

        expected_path = test.with_suffix(".expected")
        exit_path = test.with_suffix(".exit")

        previous = expected_path.read_text() if expected_path.exists() else None
        if previous != result.stdout:
            changed.append(expected_path.name)
            if not check_only:
                with open(expected_path, "w", encoding="utf-8", newline="") as f:
                    f.write(result.stdout)

        if result.returncode == 0:
            if exit_path.exists():
                changed.append(f"{exit_path.name} (removed)")
                if not check_only:
                    exit_path.unlink()
        else:
            wanted = f"{result.returncode}\n"
            previous_exit = exit_path.read_text() if exit_path.exists() else None
            if previous_exit != wanted:
                changed.append(exit_path.name)
                if not check_only:
                    with open(exit_path, "w", encoding="utf-8", newline="") as f:
                        f.write(wanted)

    verb = "would change" if check_only else "wrote"
    print(f"{verb} {len(changed)} file(s) in {folder}")
    for name in changed:
        print(f"  {name}")
    return 1 if (check_only and changed) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", help="A sidecar-mode test folder, e.g. reference/tests/lab1")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report what would change without writing anything. Exits 1 if anything would.",
    )
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"ERROR: '{folder}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    sys.exit(regenerate(folder, args.check))


if __name__ == "__main__":
    main()
