"""
End-to-end tests driven by fake ./run entrypoints.

These invoke run_tests.py as a subprocess against throwaway repos, exactly the
way a group's CI workflow invokes it. Every check selftest.sh used to make lives
here, plus the failure paths it never covered.

Half of these assert the harness reports FAILURE. A grader that can only be
shown saying PASS has not been tested at all.
"""

import unittest

from support import (
    BASH_ECHO_RUN,
    PYTHON_ECHO_RUN,
    ScratchRepo,
    copy_example,
    skip_without_bash,
)


class BundledExampleTests(unittest.TestCase):
    """The examples/ folders are documentation, so they have to stay correct."""

    @skip_without_bash
    def test_sidecar_example_passes(self):
        with ScratchRepo() as repo:
            copy_example("sidecar-mode", repo.root)
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1/1 tests passed", result.stdout)

    @skip_without_bash
    def test_inline_example_passes_including_the_runtime_error_path(self):
        with ScratchRepo() as repo:
            copy_example("inline-mode", repo.root)
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("2/2 tests passed", result.stdout)


class SidecarModeTests(unittest.TestCase):
    def test_matching_output_passes(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab0/hello.src", "hello\n")
            repo.write("tests/lab0/hello.expected", "hello\n")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("1/1 tests passed", result.stdout)

    def test_mismatched_output_fails_with_a_diff(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab0/broken.src", "actual output\n")
            repo.write("tests/lab0/broken.expected", "something else entirely\n")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("[FAIL]", result.stdout)
        self.assertIn("stdout mismatch", result.stdout)
        self.assertIn("something else entirely", result.stdout)
        self.assertIn("0/1 tests passed", result.stdout)

    def test_missing_sidecar_fails_rather_than_skipping(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab0/lonely.src", "hello\n")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("No .expected sidecar file found", result.stdout)

    def test_orphaned_expectation_warns_without_failing(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab0/kept.src", "kept\n")
            repo.write("tests/lab0/kept.expected", "kept\n")
            repo.write("tests/lab0/renamed_away.expected", "stale\n")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("renamed_away.expected", result.stderr)
        self.assertIn("WARNING", result.stderr)

    def test_nonzero_exit_with_empty_expected_passes(self):
        with ScratchRepo() as repo:
            repo.write_run(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                'print("[line 1] Error: Unterminated string.", file=sys.stderr)\n'
                "sys.exit(65)\n"
            )
            repo.write("tests/lab1/manifest.json", '{"ext": ".src", "mode": "sidecar"}')
            repo.write("tests/lab1/unterminated.src", 'var broken = "no close\n')
            repo.write("tests/lab1/unterminated.expected", "")
            repo.write("tests/lab1/unterminated.exit", "65\n")
            result = repo.run_harness("tests/lab1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_wrong_exit_code_is_reported(self):
        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env python3\nimport sys\nsys.exit(70)\n")
            repo.write("tests/lab1/a.src", "")
            repo.write("tests/lab1/a.expected", "")
            repo.write("tests/lab1/a.exit", "65\n")
            result = repo.run_harness("tests/lab1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("exit code: expected 65, got 70", result.stdout)


class InlineModeTests(unittest.TestCase):
    INLINE_MANIFEST = '{"ext": ".src", "mode": "inline"}'

    def test_inline_expectations_pass(self):
        with ScratchRepo() as repo:
            repo.write_run(
                "#!/usr/bin/env python3\nprint('1')\nprint('2')\n"
            )
            repo.write("tests/lab3/manifest.json", self.INLINE_MANIFEST)
            repo.write("tests/lab3/a.src", "print 1;\n// expect: 1\nprint 2;\n// expect: 2\n")
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_wrong_inline_value_fails(self):
        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env python3\nprint('1')\n")
            repo.write("tests/lab3/manifest.json", self.INLINE_MANIFEST)
            repo.write("tests/lab3/a.src", "print 1;\n// expect: 999\n")
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 1)
        self.assertIn("stdout mismatch", result.stdout)

    def test_runtime_error_path(self):
        with ScratchRepo() as repo:
            repo.write_run(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "print('before')\n"
                'print("Operands must be numbers.\\n[line 2]", file=sys.stderr)\n'
                "sys.exit(70)\n"
            )
            repo.write("tests/lab3/manifest.json", self.INLINE_MANIFEST)
            repo.write(
                "tests/lab3/a.src",
                'print "before";\n// expect: before\n'
                '"a" - 1;\n// expect runtime error: Operands must be numbers.\n',
            )
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_error_expected_but_program_succeeds(self):
        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env python3\n")
            repo.write("tests/lab3/manifest.json", self.INLINE_MANIFEST)
            repo.write(
                "tests/lab3/a.src",
                '"a" - 1;\n// expect runtime error: Operands must be numbers.\n',
            )
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 1)
        self.assertIn("exit code: expected 70, got 0", result.stdout)
        self.assertIn("stderr mismatch", result.stdout)

    def test_static_error_path(self):
        with ScratchRepo() as repo:
            repo.write_run(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "print(\"[line 1] Error at ')': Expect expression.\", file=sys.stderr)\n"
                "sys.exit(65)\n"
            )
            repo.write("tests/lab3/manifest.json", self.INLINE_MANIFEST)
            repo.write(
                "tests/lab3/a.src",
                "();\n// expect error: Expect expression.\n",
            )
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_configurable_comment_syntax(self):
        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env python3\nprint('7')\nprint('8')\n")
            repo.write(
                "tests/lab3/manifest.json",
                '{"ext": ".src", "mode": "inline", "comment_prefix": ["#", "--"]}',
            )
            repo.write("tests/lab3/a.src", "PRINT 7\n# expect: 7\nPRINT 8\n-- expect: 8\n")
            result = repo.run_harness("tests/lab3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_empty_comment_prefix_is_a_clean_error(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write(
                "tests/lab3/manifest.json",
                '{"ext": ".src", "mode": "inline", "comment_prefix": ""}',
            )
            repo.write("tests/lab3/a.src", "print 1;\n")
            result = repo.run_harness("tests/lab3")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("comment_prefix", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class EntrypointTests(unittest.TestCase):
    def test_python_entrypoint_launches(self):
        with ScratchRepo() as repo:
            repo.write_run(PYTHON_ECHO_RUN)
            repo.write("tests/lab0/hello.src", "python entrypoint works\n")
            repo.write("tests/lab0/hello.expected", "python entrypoint works\n")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @skip_without_bash
    def test_bash_entrypoint_launches(self):
        with ScratchRepo() as repo:
            repo.write_run(BASH_ECHO_RUN)
            repo.write("tests/lab0/hello.src", "bash entrypoint works\n")
            repo.write("tests/lab0/hello.expected", "bash entrypoint works\n")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_entrypoint_is_explained(self):
        with ScratchRepo() as repo:
            repo.write("tests/lab0/a.src", "")
            repo.write("tests/lab0/a.expected", "")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        self.assertIn("run", result.stdout)

    def test_entrypoint_named_in_the_manifest_is_used(self):
        with ScratchRepo() as repo:
            repo.write_run(PYTHON_ECHO_RUN, name="scripts/launch")
            repo.write(
                "tests/lab0/manifest.json",
                '{"ext": ".src", "run_entrypoint": "./scripts/launch"}',
            )
            repo.write("tests/lab0/a.src", "hello\n")
            repo.write("tests/lab0/a.expected", "hello\n")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_flag_is_passed_before_the_file(self):
        with ScratchRepo() as repo:
            repo.write_run(
                "#!/usr/bin/env python3\nimport sys\nprint(' '.join(sys.argv[1:-1]))\n"
            )
            repo.write(
                "tests/lab1/manifest.json",
                '{"ext": ".src", "flag": "--tokenize"}',
            )
            repo.write("tests/lab1/a.src", "")
            repo.write("tests/lab1/a.expected", "--tokenize\n")
            result = repo.run_harness("tests/lab1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_timeout_is_reported_rather_than_hanging(self):
        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env python3\nimport time\ntime.sleep(60)\n")
            repo.write("tests/lab0/slow.src", "")
            repo.write("tests/lab0/slow.expected", "")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("TIMEOUT", result.stdout)


class InvocationTests(unittest.TestCase):
    def test_missing_test_folder_is_a_clean_error(self):
        with ScratchRepo() as repo:
            repo.write_run()
            result = repo.run_harness("tests/nonexistent")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_folder_with_no_matching_files_is_a_clean_error(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab0/notes.txt", "")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no test files", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_unknown_mode_is_reported_per_test(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab0/manifest.json", '{"ext": ".src", "mode": "telepathy"}')
            repo.write("tests/lab0/a.src", "")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Unknown mode 'telepathy'", result.stdout)

    def test_repo_root_flag_resolves_the_entrypoint(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab0/a.src", "hello\n")
            repo.write("tests/lab0/a.expected", "hello\n")
            result = repo.run_harness("tests/lab0", extra_args=["--repo-root", "."])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nested_test_folders_are_discovered(self):
        with ScratchRepo() as repo:
            repo.write_run()
            repo.write("tests/lab0/a.src", "a\n")
            repo.write("tests/lab0/a.expected", "a\n")
            repo.write("tests/lab0/deep/b.src", "b\n")
            repo.write("tests/lab0/deep/b.expected", "b\n")
            result = repo.run_harness("tests/lab0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("2/2 tests passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
