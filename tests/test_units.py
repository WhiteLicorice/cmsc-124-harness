"""
Unit tests for run_tests.py, one function at a time, no subprocesses.

The end-to-end tests prove the harness grades correctly. These prove the pieces
it grades with behave at their edges, which is where a grading bug hides: an
annotation that silently does not parse, a comment token that shadows a longer
one, a Windows launch path that nobody on Linux ever runs.
"""

import unittest
from unittest import mock

from support import run_tests, ScratchRepo


class AsTokenListTests(unittest.TestCase):
    def test_none_is_empty(self):
        self.assertEqual(run_tests.as_token_list(None), [])

    def test_empty_string_is_empty(self):
        self.assertEqual(run_tests.as_token_list(""), [])

    def test_single_token_is_wrapped(self):
        self.assertEqual(run_tests.as_token_list("//"), ["//"])

    def test_list_is_passed_through(self):
        self.assertEqual(run_tests.as_token_list(["#", "--"]), ["#", "--"])

    def test_empty_entries_are_dropped(self):
        self.assertEqual(run_tests.as_token_list(["#", "", None]), ["#"])


class CommentPatternTests(unittest.TestCase):
    def pattern(self, prefix, suffix=None):
        return run_tests.build_comment_pattern(
            {"comment_prefix": prefix, "comment_suffix": suffix}
        )

    def test_default_slashes(self):
        m = self.pattern("//").search("print 1; // expect: 1")
        self.assertEqual(m.group(1), "expect: 1")

    def test_longer_prefix_wins_over_shorter(self):
        # A language with both // and /// must not have /// parsed as a //
        # comment whose body starts with a stray slash.
        m = self.pattern(["//", "///"]).search("code /// expect: 1")
        self.assertEqual(m.group(1), "expect: 1")

    def test_regex_metacharacters_are_literal(self):
        m = self.pattern("(*").search("code (* expect: 1")
        self.assertEqual(m.group(1), "expect: 1")

    def test_multiple_prefixes(self):
        pattern = self.pattern(["#", "--"])
        self.assertEqual(pattern.search("x # expect: 7").group(1), "expect: 7")
        self.assertEqual(pattern.search("x -- expect: 8").group(1), "expect: 8")

    def test_empty_prefix_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.pattern("")
        self.assertIn("comment_prefix", str(caught.exception))

    def test_missing_prefix_is_rejected(self):
        with self.assertRaises(ValueError):
            run_tests.build_comment_pattern({})


class InlineExpectationTests(unittest.TestCase):
    def parse(self, source, **manifest_overrides):
        manifest = dict(run_tests.DEFAULT_MANIFEST)
        manifest.update(manifest_overrides)
        with ScratchRepo() as repo:
            path = repo.write("tests/lab3/case.src", source)
            return run_tests.parse_inline_expectations(path, manifest)

    def test_plain_expectations(self):
        found = self.parse("print 1;\n// expect: 1\nprint 2;\n// expect: 2\n")
        self.assertEqual(found.stdout_lines, ["1", "2"])
        self.assertEqual(found.stderr_substrings, [])
        self.assertEqual(found.exit_code, run_tests.EXIT_OK)
        self.assertFalse(found.is_empty)

    def test_trailing_annotation_on_the_same_line(self):
        self.assertEqual(self.parse("print 1; // expect: 1\n").stdout_lines, ["1"])

    def test_runtime_error_sets_exit_70(self):
        found = self.parse(
            'print "before";\n// expect: before\n'
            '"a" - 1;\n// expect runtime error: Operands must be numbers.\n'
        )
        self.assertEqual(found.stdout_lines, ["before"])
        self.assertEqual(found.stderr_substrings, ["Operands must be numbers."])
        self.assertEqual(found.exit_code, run_tests.EXIT_RUNTIME_ERROR)

    def test_compile_error_sets_exit_65(self):
        found = self.parse("var 1 = 2;\n// expect error: Expect variable name.\n")
        self.assertEqual(found.stderr_substrings, ["Expect variable name."])
        self.assertEqual(found.exit_code, run_tests.EXIT_STATIC_ERROR)

    def test_several_diagnostics_are_kept_apart(self):
        found = self.parse(
            "();\n// expect error: Expect expression.\n"
            "}\n// expect error: Expect ';'.\n"
        )
        self.assertEqual(
            found.stderr_substrings, ["Expect expression.", "Expect ';'."]
        )

    def test_ordinary_comments_are_ignored(self):
        found = self.parse("// this explains the test\nprint 1;\n// expect: 1\n")
        self.assertEqual(found.stdout_lines, ["1"])
        self.assertEqual(found.malformed, [])
        self.assertEqual(found.exit_code, run_tests.EXIT_OK)

    def test_bracketed_comment_suffix_is_stripped(self):
        found = self.parse(
            "print 1; (* expect: 1 *)\n",
            comment_prefix="(*",
            comment_suffix="*)",
        )
        self.assertEqual(found.stdout_lines, ["1"])

    def test_custom_expect_prefix(self):
        found = self.parse("print 1;\n// prints: 1\n", expect_prefix="prints:")
        self.assertEqual(found.stdout_lines, ["1"])

    def test_annotation_value_is_stripped_of_surrounding_space(self):
        self.assertEqual(self.parse("print 1;\n//    expect:    1   \n").stdout_lines, ["1"])

    def test_empty_expected_value_is_kept(self):
        # A program that prints a blank line is a legitimate expectation.
        self.assertEqual(self.parse('print "";\n// expect:\n').stdout_lines, [""])

    def test_declared_silence_is_recorded(self):
        found = self.parse("fun unused() {}\n// expect nothing\n")
        self.assertTrue(found.declared_silent)
        self.assertTrue(found.is_empty)

    def test_a_file_with_no_annotations_is_empty(self):
        found = self.parse("print 1;\n")
        self.assertTrue(found.is_empty)
        self.assertFalse(found.declared_silent)
        self.assertEqual(found.malformed, [])

    def test_malformed_annotations_are_collected(self):
        found = self.parse("print 1;\n// expect : 1\n// Expect: 2\n// expected: 3\n")
        self.assertEqual(found.malformed, ["expect : 1", "Expect: 2", "expected: 3"])
        self.assertEqual(found.stdout_lines, [])


class NearMissTests(unittest.TestCase):
    PREFIXES = ["expect runtime error:", "expect error:", "expect nothing", "expect:"]

    def looks_like(self, comment):
        return run_tests.looks_like_annotation(comment, self.PREFIXES)

    def test_spacing_typo(self):
        self.assertTrue(self.looks_like("expect : 1"))

    def test_case_typo(self):
        self.assertTrue(self.looks_like("EXPECT: 1"))

    def test_misspelled_keyword(self):
        self.assertTrue(self.looks_like("expected: 1"))

    def test_spaced_error_annotation(self):
        self.assertTrue(self.looks_like("expect runtime error : boom"))

    def test_prose_comment_with_a_colon(self):
        self.assertFalse(self.looks_like("note: we expect this to be slow"))

    def test_prose_comment_without_a_colon(self):
        self.assertFalse(self.looks_like("this expects a lot of the reader"))

    def test_unrelated_annotation_vocabulary(self):
        self.assertFalse(
            run_tests.looks_like_annotation("expect: 1", ["muestra:"])
        )


class SidecarExpectationTests(unittest.TestCase):
    def test_expected_without_exit_defaults_to_zero(self):
        with ScratchRepo() as repo:
            test = repo.write("tests/lab1/a.src", "source\n")
            repo.write("tests/lab1/a.expected", "output\n")
            stdout, exit_code = run_tests.parse_sidecar_expectations(test)
        self.assertEqual(stdout, "output\n")
        self.assertEqual(exit_code, run_tests.EXIT_OK)

    def test_exit_file_is_honoured(self):
        with ScratchRepo() as repo:
            test = repo.write("tests/lab1/a.src", "source\n")
            repo.write("tests/lab1/a.expected", "")
            repo.write("tests/lab1/a.exit", "65\n")
            _, exit_code = run_tests.parse_sidecar_expectations(test)
        self.assertEqual(exit_code, run_tests.EXIT_STATIC_ERROR)

    def test_missing_expected_signals_absence(self):
        with ScratchRepo() as repo:
            test = repo.write("tests/lab1/a.src", "source\n")
            stdout, exit_code = run_tests.parse_sidecar_expectations(test)
        self.assertIsNone(stdout)
        self.assertIsNone(exit_code)


class OrphanDetectionTests(unittest.TestCase):
    def test_paired_expectation_is_not_an_orphan(self):
        with ScratchRepo() as repo:
            folder = repo.root / "tests" / "lab1"
            test = repo.write("tests/lab1/a.src", "")
            repo.write("tests/lab1/a.expected", "")
            orphans = run_tests.find_orphaned_expectations(folder, [test], repo.root)
        self.assertEqual(orphans, [])

    def test_renamed_test_leaves_an_orphan(self):
        with ScratchRepo() as repo:
            folder = repo.root / "tests" / "lab1"
            test = repo.write("tests/lab1/a.src", "")
            repo.write("tests/lab1/a.expected", "")
            repo.write("tests/lab1/old_name.expected", "")
            orphans = run_tests.find_orphaned_expectations(folder, [test], repo.root)
        self.assertEqual(len(orphans), 1)
        self.assertIn("old_name.expected", orphans[0])

    def test_orphaned_exit_file_is_reported(self):
        with ScratchRepo() as repo:
            folder = repo.root / "tests" / "lab1"
            test = repo.write("tests/lab1/a.src", "")
            repo.write("tests/lab1/a.expected", "")
            repo.write("tests/lab1/gone.exit", "65")
            orphans = run_tests.find_orphaned_expectations(folder, [test], repo.root)
        self.assertEqual(len(orphans), 1)
        self.assertIn("gone.exit", orphans[0])


class ShebangTests(unittest.TestCase):
    def sniff(self, content, binary=False):
        with ScratchRepo() as repo:
            path = repo.root / "run"
            if binary:
                path.write_bytes(content)
            else:
                repo.write("run", content)
            return run_tests.read_shebang_interpreter(path)

    def test_absolute_interpreter(self):
        self.assertEqual(self.sniff("#!/bin/bash\n"), "bash")

    def test_env_is_unwrapped(self):
        self.assertEqual(self.sniff("#!/usr/bin/env python3\n"), "python3")

    def test_backslash_path(self):
        self.assertEqual(self.sniff("#!C:\\tools\\bash.exe\n"), "bash.exe")

    def test_no_shebang(self):
        self.assertIsNone(self.sniff("echo hello\n"))

    def test_empty_file(self):
        self.assertIsNone(self.sniff(""))

    def test_bare_shebang(self):
        self.assertIsNone(self.sniff("#!\n"))

    def test_binary_file_does_not_raise(self):
        self.assertIsNone(self.sniff(b"\x00\x01\x02\xff", binary=True))

    def test_missing_file_returns_none(self):
        with ScratchRepo() as repo:
            self.assertIsNone(
                run_tests.read_shebang_interpreter(repo.root / "nonexistent")
            )


class LaunchCommandTests(unittest.TestCase):
    """
    The Windows branch is the one nobody runs by accident, so it gets exercised
    on every platform by patching the flag the real code reads.
    """

    def build(self, entrypoint, root, windows):
        with mock.patch.object(run_tests, "IS_WINDOWS", windows):
            return run_tests.build_launch_command(entrypoint, root)

    def test_posix_runs_the_entrypoint_directly(self):
        with ScratchRepo() as repo:
            repo.write_run()
            cmd, error = self.build("./run", repo.root, windows=False)
        self.assertEqual(cmd, ["./run"])
        self.assertIsNone(error)

    def test_windows_native_executable_runs_directly(self):
        with ScratchRepo() as repo:
            repo.write("run.exe", "")
            cmd, error = self.build("./run.exe", repo.root, windows=True)
        self.assertEqual(cmd, ["./run.exe"])
        self.assertIsNone(error)

    def test_windows_batch_file_runs_directly(self):
        with ScratchRepo() as repo:
            repo.write("run.bat", "@echo off\n")
            cmd, error = self.build("./run.bat", repo.root, windows=True)
        self.assertEqual(cmd, ["./run.bat"])
        self.assertIsNone(error)

    def test_windows_python_entrypoint_uses_this_interpreter(self):
        import sys

        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env python3\n")
            cmd, error = self.build("./run", repo.root, windows=True)
        self.assertEqual(cmd, [sys.executable, "./run"])
        self.assertIsNone(error)

    def test_windows_shell_entrypoint_is_prefixed_with_bash(self):
        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env bash\n")
            with mock.patch.object(
                run_tests, "find_windows_bash", return_value="C:/git/bash.exe"
            ):
                cmd, error = self.build("./run", repo.root, windows=True)
        self.assertEqual(cmd, ["C:/git/bash.exe", "./run"])
        self.assertIsNone(error)

    def test_windows_entrypoint_without_shebang_is_assumed_shell(self):
        with ScratchRepo() as repo:
            repo.write_run("echo hello\n")
            with mock.patch.object(
                run_tests, "find_windows_bash", return_value="C:/git/bash.exe"
            ):
                cmd, _ = self.build("./run", repo.root, windows=True)
        self.assertEqual(cmd, ["C:/git/bash.exe", "./run"])

    def test_windows_without_bash_explains_itself(self):
        with ScratchRepo() as repo:
            repo.write_run("#!/bin/sh\n")
            with mock.patch.object(run_tests, "find_windows_bash", return_value=None):
                cmd, error = self.build("./run", repo.root, windows=True)
        self.assertIsNone(cmd)
        self.assertIn("bash", error)
        self.assertNotIn("Traceback", error)

    def test_windows_unknown_interpreter_off_path_is_named(self):
        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env nonesuch\n")
            with mock.patch.object(run_tests.shutil, "which", return_value=None):
                cmd, error = self.build("./run", repo.root, windows=True)
        self.assertIsNone(cmd)
        self.assertIn("nonesuch", error)

    def test_windows_known_interpreter_is_resolved_to_a_full_path(self):
        with ScratchRepo() as repo:
            repo.write_run("#!/usr/bin/env node\n")
            with mock.patch.object(
                run_tests.shutil, "which", return_value="C:/node/node.exe"
            ):
                cmd, error = self.build("./run", repo.root, windows=True)
        self.assertEqual(cmd, ["C:/node/node.exe", "./run"])
        self.assertIsNone(error)


class ManifestTests(unittest.TestCase):
    def test_missing_manifest_yields_defaults(self):
        with ScratchRepo() as repo:
            folder = repo.root / "tests" / "lab1"
            folder.mkdir(parents=True)
            manifest = run_tests.load_manifest(folder)
        self.assertEqual(manifest, run_tests.DEFAULT_MANIFEST)

    def test_manifest_overrides_merge_onto_defaults(self):
        with ScratchRepo() as repo:
            repo.write(
                "tests/lab1/manifest.json",
                '{"ext": ".lox", "flag": "--tokenize"}',
            )
            manifest = run_tests.load_manifest(repo.root / "tests" / "lab1")
        self.assertEqual(manifest["ext"], ".lox")
        self.assertEqual(manifest["flag"], "--tokenize")
        # Untouched keys keep their documented defaults.
        self.assertEqual(manifest["mode"], "sidecar")
        self.assertEqual(manifest["run_entrypoint"], "./run")

    def test_invalid_json_names_the_file_and_position(self):
        with ScratchRepo() as repo:
            repo.write("tests/lab1/manifest.json", '{"ext": ".src",}')
            with self.assertRaises(run_tests.ConfigError) as caught:
                run_tests.load_manifest(repo.root / "tests" / "lab1")
        message = str(caught.exception)
        self.assertIn("manifest.json", message)
        self.assertIn("line 1", message)

    def test_non_object_manifest_is_rejected(self):
        with ScratchRepo() as repo:
            repo.write("tests/lab1/manifest.json", "[1, 2]")
            with self.assertRaises(run_tests.ConfigError):
                run_tests.load_manifest(repo.root / "tests" / "lab1")

    def test_unknown_key_is_rejected_and_the_valid_ones_listed(self):
        with ScratchRepo() as repo:
            repo.write("tests/lab1/manifest.json", '{"run_entryoint": "./launch"}')
            with self.assertRaises(run_tests.ConfigError) as caught:
                run_tests.load_manifest(repo.root / "tests" / "lab1")
        message = str(caught.exception)
        self.assertIn("run_entryoint", message)
        self.assertIn("run_entrypoint", message)


class ExitFileTests(unittest.TestCase):
    def parse(self, contents):
        with ScratchRepo() as repo:
            test = repo.write("tests/lab1/a.src", "")
            repo.write("tests/lab1/a.expected", "")
            repo.write("tests/lab1/a.exit", contents)
            return run_tests.parse_sidecar_expectations(test)

    def test_whitespace_is_tolerated(self):
        _, exit_code = self.parse("  65  \n")
        self.assertEqual(exit_code, 65)

    def test_words_are_rejected_with_the_filename(self):
        with self.assertRaises(run_tests.ConfigError) as caught:
            self.parse("sixty-five\n")
        self.assertIn("a.exit", str(caught.exception))

    def test_empty_exit_file_is_rejected(self):
        with self.assertRaises(run_tests.ConfigError):
            self.parse("")


class DiscoveryTests(unittest.TestCase):
    def test_discovery_is_recursive_and_sorted(self):
        with ScratchRepo() as repo:
            repo.write("tests/lab1/b.src", "")
            repo.write("tests/lab1/a.src", "")
            repo.write("tests/lab1/nested/c.src", "")
            repo.write("tests/lab1/ignored.txt", "")
            found = run_tests.find_test_files(repo.root / "tests" / "lab1", ".src")
        self.assertEqual([p.name for p in found], ["a.src", "b.src", "c.src"])

    def test_extension_is_respected(self):
        with ScratchRepo() as repo:
            repo.write("tests/lab1/a.lox", "")
            repo.write("tests/lab1/a.src", "")
            found = run_tests.find_test_files(repo.root / "tests" / "lab1", ".lox")
        self.assertEqual([p.name for p in found], ["a.lox"])


if __name__ == "__main__":
    unittest.main()
