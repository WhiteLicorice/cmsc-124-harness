"""
Shared scaffolding for the harness's own test suite.

Nothing here knows anything about Lox or about any group's language. These are
just the pieces every test needs: a way to import run_tests.py as a module, and
a way to build a throwaway repo that looks like a group's repo from the outside.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parent.parent
RUN_TESTS_PATH = HARNESS_ROOT / "run_tests.py"


def _import_run_tests():
    """
    Imports run_tests.py by path.

    It lives at the repo root and is deliberately not a package, because groups
    fetch it as one loose file. Importing it by path keeps the suite working
    without adding packaging that the shipped artifact does not have.
    """
    spec = importlib.util.spec_from_file_location("run_tests", RUN_TESTS_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_tests"] = module
    spec.loader.exec_module(module)
    return module


run_tests = _import_run_tests()


# A python entrypoint is the portable choice for a fake ./run: run_tests.py maps
# a python shebang onto sys.executable, so it launches on Windows too, with no
# bash anywhere in the picture.
PYTHON_ECHO_RUN = """\
#!/usr/bin/env python3
import sys
print(open(sys.argv[-1]).read(), end="")
"""

BASH_ECHO_RUN = """\
#!/usr/bin/env bash
cat "${@: -1}"
"""


def bash_available():
    if os.name != "nt":
        return True
    return run_tests.find_windows_bash() is not None


skip_without_bash = unittest.skipUnless(
    bash_available(), "no bash on this machine, so shell entrypoints cannot launch"
)


class ScratchRepo:
    """
    A temporary directory shaped like a group's repo: a ./run entrypoint at the
    root and one or more test folders under tests/.

    Used as a context manager so nothing survives a failed assertion.
    """

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._tmp.cleanup()
        return False

    def write(self, relative_path, content):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        # Explicit newline="" keeps LF endings intact on Windows. Path.write_text
        # only grew a newline argument in 3.10, and the harness floor is 3.9.
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return path

    def write_run(self, content=PYTHON_ECHO_RUN, name="run"):
        path = self.write(name, content)
        path.chmod(0o755)
        return path

    def run_harness(self, test_folder, extra_args=()):
        """Invokes run_tests.py exactly the way a group's CI workflow does."""
        return subprocess.run(
            [sys.executable, str(RUN_TESTS_PATH), test_folder, *extra_args],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=120,
        )


def copy_example(name, into):
    """Copies one of the bundled examples/ folders into a scratch repo root."""
    source = HARNESS_ROOT / "examples" / name
    for entry in source.iterdir():
        target = into / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target)
        else:
            shutil.copy2(entry, target)
            if entry.name == "run":
                target.chmod(0o755)
