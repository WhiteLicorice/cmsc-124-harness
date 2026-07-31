"""
End-to-end tests against the real reference implementation.

Everything else in this suite drives fake entrypoints. These drive a working
Lox interpreter over a few hundred committed tests, which is the only way to
find out whether the harness handles a real scanner's output, a real parse
error on stderr, and a real program that dies partway through.

The suite runs in two directions. Forwards: every lab folder passes, untouched.
Backwards: each mutation below breaks exactly one thing about a test folder,
and the harness has to notice and say what. A grading tool that has only ever
been observed agreeing with a correct implementation has not been tested.

Skipped unless the reference is built. See reference/README.md.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import HARNESS_ROOT, RUN_TESTS_PATH

REFERENCE_ROOT = HARNESS_ROOT / "reference"
LAB_FOLDERS = ["lab0", "lab1", "lab2", "lab3", "lab4", "lab5"]
CROSSMODE_FOLDERS = ["crossmode/inline", "crossmode/sidecar"]


def reference_binary():
    for name in ("cmsc124-ref", "cmsc124-ref.exe"):
        candidate = REFERENCE_ROOT / "bin" / name
        if candidate.exists():
            return candidate
    return None


needs_reference = unittest.skipUnless(
    reference_binary() is not None,
    "the reference implementation is not built; see reference/README.md",
)


def grade(folder, cwd=REFERENCE_ROOT):
    """Runs the harness over a folder the way the reference CI job does."""
    return subprocess.run(
        [sys.executable, str(RUN_TESTS_PATH), str(folder), "--repo-root", str(REFERENCE_ROOT)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=900,
    )


@needs_reference
class ConformanceTests(unittest.TestCase):
    """The reference passes its own corpus. If it does not, one of them is wrong."""

    def check(self, folder):
        result = grade(REFERENCE_ROOT / "tests" / folder)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("[FAIL]", result.stdout)
        # An orphaned expectation never fails a run, so it has to be asserted
        # separately or a renamed test would silently stop being checked.
        self.assertNotIn("WARNING", result.stderr)

    def test_lab0(self):
        self.check("lab0")

    def test_lab1(self):
        self.check("lab1")

    def test_lab2(self):
        self.check("lab2")

    def test_lab3(self):
        self.check("lab3")

    def test_lab4(self):
        self.check("lab4")

    def test_lab5(self):
        self.check("lab5")

    def test_crossmode_inline(self):
        self.check("crossmode/inline")

    def test_crossmode_sidecar(self):
        self.check("crossmode/sidecar")


class CrossmodeTests(unittest.TestCase):
    """
    The two crossmode folders hold the same programs, graded two different ways.

    That only proves anything if they really are the same programs, so the
    identity is asserted rather than assumed. Editing one and forgetting the
    other would quietly turn the comparison into two unrelated test suites.
    """

    INLINE = REFERENCE_ROOT / "tests" / "crossmode" / "inline"
    SIDECAR = REFERENCE_ROOT / "tests" / "crossmode" / "sidecar"

    @unittest.skipUnless((REFERENCE_ROOT / "tests" / "crossmode").is_dir(), "no corpus")
    def test_the_same_files_are_present_in_both_modes(self):
        inline = {p.name for p in self.INLINE.glob("*.lox")}
        sidecar = {p.name for p in self.SIDECAR.glob("*.lox")}
        self.assertEqual(inline, sidecar)
        self.assertTrue(inline, "the crossmode folders are empty")

    @unittest.skipUnless((REFERENCE_ROOT / "tests" / "crossmode").is_dir(), "no corpus")
    def test_the_files_are_byte_for_byte_identical(self):
        for test in sorted(self.INLINE.glob("*.lox")):
            with self.subTest(test.name):
                self.assertEqual(
                    test.read_bytes(),
                    (self.SIDECAR / test.name).read_bytes(),
                )


@needs_reference
class MutationTests(unittest.TestCase):
    """
    Each test breaks one thing and insists the harness notices.

    The scratch copy lives inside reference/ because run_tests.py resolves test
    paths against the repo root it was given, and the entrypoint has to stay
    reachable from there.
    """

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix=".mutation-", dir=REFERENCE_ROOT))
        self.addCleanup(shutil.rmtree, self.scratch, ignore_errors=True)

    def copy_lab(self, lab):
        target = self.scratch / lab
        shutil.copytree(REFERENCE_ROOT / "tests" / lab, target)
        return target

    def assert_caught(self, folder, *expected_fragments):
        result = grade(folder)
        output = result.stdout + result.stderr
        self.assertEqual(
            result.returncode, 1, f"the harness did not catch this:\n{output}"
        )
        for fragment in expected_fragments:
            self.assertIn(fragment, output)
        self.assertNotIn("Traceback", output)

    def first_test(self, folder, suffix=".lox"):
        return sorted(folder.glob(f"*{suffix}"))[0]

    def rewrite(self, path, text):
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)

    # Sidecar mutations.

    def test_corrupted_expected_output(self):
        folder = self.copy_lab("lab1")
        expected = sorted(folder.glob("*.expected"))[0]
        self.rewrite(expected, "this is not what the scanner prints\n")
        self.assert_caught(folder, "stdout mismatch", "this is not what the scanner prints")

    def test_expected_output_off_by_one_line_number(self):
        # The whole reason lab1 uses sidecar mode is that line numbers matter,
        # so a wrong line number had better fail.
        folder = self.copy_lab("lab1")
        expected = folder / "line_counting.expected"
        self.rewrite(expected, expected.read_text().replace("[line 2]", "[line 3]", 1))
        self.assert_caught(folder, "stdout mismatch")

    def test_flipped_exit_code(self):
        folder = self.copy_lab("lab1")
        exit_file = sorted(folder.glob("*.exit"))[0]
        self.rewrite(exit_file, "0\n")
        self.assert_caught(folder, "exit code: expected 0, got 65")

    def test_deleted_sidecar(self):
        folder = self.copy_lab("lab1")
        sorted(folder.glob("*.expected"))[0].unlink()
        self.assert_caught(folder, "No .expected sidecar file found")

    def test_renamed_test_leaves_an_orphan(self):
        folder = self.copy_lab("lab1")
        test = self.first_test(folder)
        test.rename(test.with_name("renamed" + test.suffix))
        result = grade(folder)
        # The renamed test has no expectation, so the run fails, and the old
        # expectation is now unpaired, so it is reported too.
        self.assertEqual(result.returncode, 1)
        self.assertIn(test.with_suffix(".expected").name, result.stderr)

    def test_malformed_exit_file(self):
        folder = self.copy_lab("lab1")
        exit_file = sorted(folder.glob("*.exit"))[0]
        self.rewrite(exit_file, "sixty five\n")
        self.assert_caught(folder, exit_file.name)

    # Inline mutations.

    def test_changed_expected_value(self):
        folder = self.copy_lab("lab3")
        test = folder / "operator_add.lox"
        self.rewrite(test, test.read_text().replace("expect: 579", "expect: 580"))
        self.assert_caught(folder, "stdout mismatch", "580")

    def test_runtime_error_downgraded_to_output(self):
        folder = self.copy_lab("lab3")
        test = folder / "operator_add_bool_nil.lox"
        self.rewrite(
            test,
            test.read_text().replace("expect runtime error:", "expect:"),
        )
        self.assert_caught(folder, "exit code: expected 0, got 70")

    def test_typo_in_an_annotation(self):
        folder = self.copy_lab("lab3")
        test = folder / "operator_add.lox"
        self.rewrite(test, test.read_text().replace("// expect:", "// expect :"))
        self.assert_caught(folder, "did not parse")

    def test_annotations_removed_entirely(self):
        folder = self.copy_lab("lab4")
        test = folder / "print_missing_argument.lox"
        self.rewrite(test, "var a = 1;\n")
        self.assert_caught(folder, "no expectations found")

    def test_wrong_diagnostic_text(self):
        folder = self.copy_lab("lab4")
        test = folder / "variable_undefined_global.lox"
        self.rewrite(
            test,
            test.read_text().replace("Undefined variable", "Undeclared variable"),
        )
        self.assert_caught(folder, "stderr mismatch", "Undeclared variable")

    # Configuration mutations.

    def test_entrypoint_that_does_not_exist(self):
        folder = self.copy_lab("lab0")
        self.rewrite(
            folder / "manifest.json",
            '{"ext": ".lox", "mode": "sidecar", "run_entrypoint": "./no-such-run"}',
        )
        self.assert_caught(folder, "no-such-run")

    def test_misspelled_manifest_key(self):
        folder = self.copy_lab("lab0")
        self.rewrite(
            folder / "manifest.json",
            '{"ext": ".lox", "mode": "sidecar", "run_entryoint": "./run"}',
        )
        self.assert_caught(folder, "run_entryoint", "run_entrypoint")

    def test_wrong_stage_flag(self):
        # lab2 graded as though it were lab1: same files, wrong pipeline stage.
        folder = self.copy_lab("lab2")
        self.rewrite(
            folder / "manifest.json",
            '{"ext": ".lox", "mode": "sidecar", "flag": "--tokenize"}',
        )
        self.assert_caught(folder, "stdout mismatch")

    def test_a_program_that_never_finishes(self):
        folder = self.copy_lab("lab5")
        for stale in folder.glob("*.lox"):
            stale.unlink()
        self.rewrite(
            folder / "spin.lox",
            "// A loop with no exit, to prove the harness gives up rather than hangs.\n"
            "while (true) {}\n"
            "// expect nothing\n",
        )
        self.assert_caught(folder, "TIMEOUT")


if __name__ == "__main__":
    unittest.main()
