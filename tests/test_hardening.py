"""
Tests for the failure modes that used to be silent.

Every case here was, at some point, a way for run_tests.py to report the wrong
thing: a green PASS on a test that asserted nothing, an opaque diff when a
diagnostic moved by one line, or a Python traceback in place of an error
message. A grading tool gets exactly one chance to be trusted, so each of these
is pinned.
"""

import subprocess
import time
import unittest

from support import ScratchRepo

INLINE_MANIFEST = '{"ext": ".src", "mode": "inline"}'
SILENT_RUN = "#!/usr/bin/env python3\n"


class VacuousInlineTestTests(unittest.TestCase):
    """
    An inline test whose annotations do not parse expects nothing, and a program
    that prints nothing satisfies it. That is a group shipping broken
    annotations and CI telling them everything is fine.
    """

    def test_typo_in_the_annotation_is_caught(self):
        with ScratchRepo() as repo:
            repo.write_run(SILENT_RUN)
            repo.write("tests/lab3/manifest.json", INLINE_MANIFEST)
            repo.write("tests/lab3/a.src", "print 1;\n// expect : 1\n")
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("expect : 1", result.stdout)

    def test_capitalised_annotation_is_caught(self):
        with ScratchRepo() as repo:
            repo.write_run(SILENT_RUN)
            repo.write("tests/lab3/manifest.json", INLINE_MANIFEST)
            repo.write("tests/lab3/a.src", "print 1;\n// Expect: 1\n")
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_misspelled_annotation_is_caught(self):
        with ScratchRepo() as repo:
            repo.write_run(SILENT_RUN)
            repo.write("tests/lab3/manifest.json", INLINE_MANIFEST)
            repo.write("tests/lab3/a.src", "print 1;\n// expected: 1\n")
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_file_with_no_annotations_at_all_is_caught(self):
        with ScratchRepo() as repo:
            repo.write_run(SILENT_RUN)
            repo.write("tests/lab3/manifest.json", INLINE_MANIFEST)
            repo.write("tests/lab3/a.src", "print 1;\n")
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("no expectations", result.stdout.lower())

    def test_deliberately_silent_test_can_say_so(self):
        # Some programs legitimately produce nothing, so there has to be a way
        # to assert that on purpose rather than by accident.
        with ScratchRepo() as repo:
            repo.write_run(SILENT_RUN)
            repo.write("tests/lab3/manifest.json", INLINE_MANIFEST)
            repo.write("tests/lab3/a.src", "fun unused() {}\n// expect nothing\n")
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_silent_claim_still_has_to_be_true(self):
        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env python3\nprint('surprise')\n")
            repo.write("tests/lab3/manifest.json", INLINE_MANIFEST)
            repo.write("tests/lab3/a.src", "noisy();\n// expect nothing\n")
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("stdout mismatch", result.stdout)

    def test_ordinary_prose_comments_are_not_mistaken_for_annotations(self):
        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env python3\nprint('1')\n")
            repo.write("tests/lab3/manifest.json", INLINE_MANIFEST)
            repo.write(
                "tests/lab3/a.src",
                "// note: we expect this one to be slow\nprint 1;\n// expect: 1\n",
            )
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class MultipleStderrExpectationTests(unittest.TestCase):
    """
    A file can expect several diagnostics. Joining them into one blob and
    checking for that blob means an interleaved line, or a reordering, fails
    with a diff that points nowhere useful.
    """

    def test_each_expectation_is_matched_independently(self):
        with ScratchRepo() as repo:
            repo.write_run(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "print(\"[line 1] Error at ')': Expect expression.\", file=sys.stderr)\n"
                'print("[line 2] Note: parser resynchronised.", file=sys.stderr)\n'
                "print(\"[line 3] Error at '}': Expect ';'.\", file=sys.stderr)\n"
                "sys.exit(65)\n"
            )
            repo.write("tests/lab2/manifest.json", INLINE_MANIFEST)
            repo.write(
                "tests/lab2/a.src",
                "();\n// expect error: Expect expression.\n"
                "}\n// expect error: Expect ';'.\n",
            )
            result = repo.run_harness("tests/lab2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_missing_diagnostic_names_itself(self):
        with ScratchRepo() as repo:
            repo.write_run(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "print(\"[line 1] Error at ')': Expect expression.\", file=sys.stderr)\n"
                "sys.exit(65)\n"
            )
            repo.write("tests/lab2/manifest.json", INLINE_MANIFEST)
            repo.write(
                "tests/lab2/a.src",
                "();\n// expect error: Expect expression.\n"
                "}\n// expect error: Expect ';'.\n",
            )
            result = repo.run_harness("tests/lab2")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Expect ';'.", result.stdout)
        self.assertNotIn("Expect expression.", result.stdout.split("stderr")[0])


class MalformedInputTests(unittest.TestCase):
    """A group's typo should produce an error message, never a traceback."""

    def test_unparseable_exit_file(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab1/a.src", "")
            repo.write("tests/lab1/a.expected", "")
            repo.write("tests/lab1/a.exit", "sixty-five\n")
            result = repo.run_harness("tests/lab1")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", output)
        self.assertIn("a.exit", output)

    def test_empty_exit_file(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab1/a.src", "")
            repo.write("tests/lab1/a.expected", "")
            repo.write("tests/lab1/a.exit", "")
            result = repo.run_harness("tests/lab1")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", output)

    def test_unparseable_manifest(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab1/manifest.json", '{"ext": ".src",}')
            repo.write("tests/lab1/a.src", "")
            result = repo.run_harness("tests/lab1")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", output)
        self.assertIn("manifest.json", output)

    def test_manifest_that_is_not_an_object(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab1/manifest.json", '["ext"]')
            repo.write("tests/lab1/a.src", "")
            result = repo.run_harness("tests/lab1")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", output)


class EncodingTests(unittest.TestCase):
    """
    Everything is UTF-8, on every platform.

    Python's read_text defaults to the platform encoding, which is cp1252 on a
    Windows machine and UTF-8 on the Linux runner. A group with an accented
    character in a string literal would watch CI go green and their own machine
    raise a UnicodeDecodeError, which is the worst way to learn about this.
    """

    ECHO_RUN = (
        "#!/usr/bin/env python3\n"
        "import io, sys\n"
        "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')\n"
        "sys.stdout.write(open(sys.argv[-1], encoding='utf-8').read().split('//')[0].strip() + '\\n')\n"
    )

    def test_non_ascii_in_an_inline_test_file(self):
        with ScratchRepo() as repo:
            repo.write_run(self.ECHO_RUN)
            repo.write("tests/lab3/manifest.json", INLINE_MANIFEST)
            repo.write("tests/lab3/a.src", "sayõ  // expect: sayõ\n")
            result = repo.run_harness("tests/lab3")
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_non_ascii_in_a_sidecar_expectation(self):
        with ScratchRepo() as repo:
            repo.write_run(self.ECHO_RUN)
            repo.write("tests/lab1/a.src", "façade\n")
            repo.write("tests/lab1/a.expected", "façade\n")
            result = repo.run_harness("tests/lab1")
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_non_ascii_in_a_manifest(self):
        with ScratchRepo() as repo:
            repo.write_run(self.ECHO_RUN)
            repo.write(
                "tests/lab3/manifest.json",
                '{"ext": ".src", "mode": "inline", "expect_prefix": "espérable:"}',
            )
            repo.write("tests/lab3/a.src", "ok  // espérable: ok\n")
            result = repo.run_harness("tests/lab3")
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TimeoutTests(unittest.TestCase):
    """
    A runaway test has to be killed outright, not just let go of.

    Killing only the process the harness started leaves anything it spawned
    still holding the output pipe, and reading that pipe is what the harness
    does next, so it waits forever. On Windows that is the normal shape of a
    run: the entrypoint is a shell script, so bash is the child and the
    interpreter is the grandchild.

    An infinite loop in a group's test then hangs grading instead of failing
    it, which is a worse outcome than any wrong answer.
    """

    # A child that outlives its parent and keeps stdout open, which is exactly
    # what a shell entrypoint plus a real interpreter looks like.
    ORPHAN_MAKER = (
        "#!/usr/bin/env python3\n"
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "time.sleep(300)\n"
    )

    def test_a_runaway_grandchild_does_not_hang_the_harness(self):
        with ScratchRepo() as repo:
            repo.write_run(self.ORPHAN_MAKER)
            repo.write("tests/lab0/runaway.src", "")
            repo.write("tests/lab0/runaway.expected", "")
            started = time.monotonic()
            try:
                result = repo.run_harness("tests/lab0")
            except subprocess.TimeoutExpired:
                self.fail("the harness hung instead of timing the test out")
            elapsed = time.monotonic() - started

        self.assertEqual(result.returncode, 1)
        self.assertIn("TIMEOUT", result.stdout)
        # The limit is 15 seconds. Anything near a minute means it waited for
        # the orphan rather than killing it.
        self.assertLess(elapsed, 60, "the timeout did not take effect promptly")


class UnknownManifestKeyTests(unittest.TestCase):
    """
    A typo'd key silently falls back to the default, and the group spends an
    afternoon debugging an entrypoint that was never being read.
    """

    def test_misspelled_key_is_rejected(self):
        with ScratchRepo() as repo:
            repo.write_run(name="launch")
            repo.write(
                "tests/lab1/manifest.json",
                '{"ext": ".src", "run_entryoint": "./launch"}',
            )
            repo.write("tests/lab1/a.src", "")
            repo.write("tests/lab1/a.expected", "")
            result = repo.run_harness("tests/lab1")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("run_entryoint", output)
        self.assertIn("run_entrypoint", output)
        self.assertNotIn("Traceback", output)

    def test_every_documented_key_is_accepted(self):
        manifest = (
            "{"
            '"ext": ".src", "flag": null, "mode": "inline", '
            '"expect_prefix": "expect:", '
            '"expect_error_prefix": "expect runtime error:", '
            '"expect_compile_error_prefix": "expect error:", '
            '"expect_nothing_prefix": "expect nothing", '
            '"comment_prefix": "//", "comment_suffix": null, '
            '"run_entrypoint": "./run"'
            "}"
        )
        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env python3\nprint('1')\n")
            repo.write("tests/lab3/manifest.json", manifest)
            repo.write("tests/lab3/a.src", "print 1;\n// expect: 1\n")
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
