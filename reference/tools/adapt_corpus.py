#!/usr/bin/env python3
"""
Adapts Bob Nystrom's Lox test corpus into this repo's lab folders.

Run once, against a checkout of munificent/craftinginterpreters:

    python3 reference/tools/adapt_corpus.py <path-to-craftinginterpreters/test>

The adapted files are committed, so nobody needs to run this to use the suite.
It is here so the next person can see exactly which files were taken, what was
changed, and why, rather than finding 200 tests of unclear provenance.

Three things happen to a file on the way in.

Bucketing. The course stops at functions, so anything touching classes,
inheritance, `this`, or `super` is dropped, as are the clox-specific limit and
benchmark suites. What is left maps onto the labs by feature: expressions to
lab3, statements and variables to lab4, control flow and functions to lab5.

Annotation rewriting. Upstream writes static errors as `// Error at 'x': msg`
and `// [line N] Error: msg`, which this harness does not recognize. They
become `// expect error: msg`. Interpreter-specific annotations, `[c line N]`
and `[java line N]`, are dropped: they describe how clox and jlox differ from
each other, which is not something this suite has an opinion about.

Statement stripping for lab3. Lab 3 evaluates expressions and prints each
value, so `print 1 + 2;` becomes `1 + 2;`, which produces the same output
through a pipeline that has no statements in it yet.

Nothing here is trusted. Every expectation is checked against the built
reference afterwards, and the adapted file is what gets reviewed in the diff.
"""

import argparse
import re
import sys
from pathlib import Path

# Features the course never reaches. Checked against code only: plenty of these
# tests say "this" in a comment or hold the word in a string literal, and an
# unterminated-string test is about scanning, not about objects.
BEYOND_THE_COURSE = re.compile(r"\b(class|this|super)\b")

STRING_LITERAL = re.compile(r'"[^"]*"?')
LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)


def code_only(text: str) -> str:
    """Blanks out comments and string literals so keyword checks see code."""
    return STRING_LITERAL.sub('""', LINE_COMMENT.sub("", text))

# Whole suites that are out: clox implementation limits, timing benchmarks, and
# everything about objects.
SKIPPED_DIRECTORIES = {
    "benchmark",
    "class",
    "constructor",
    "field",
    "inheritance",
    "limit",
    "method",
    "super",
    "this",
    # Scanner and parser material, handled as sidecar tests rather than inline.
    "scanning",
}

# Which lab each upstream suite belongs to, by the feature it exercises.
LAB_BY_DIRECTORY = {
    "bool": "lab3",
    "comments": "lab3",
    "nil": "lab3",
    "number": "lab3",
    "operator": "lab3",
    "string": "lab3",
    "assignment": "lab4",
    "block": "lab4",
    "print": "lab4",
    "variable": "lab4",
    "call": "lab5",
    "closure": "lab5",
    "for": "lab5",
    "function": "lab5",
    "if": "lab5",
    "logical_operator": "lab5",
    "regression": "lab5",
    "return": "lab5",
    "while": "lab5",
}

# Files at the corpus root, which have no directory to classify them.
LAB_BY_ROOT_FILE = {
    "precedence.lox": "lab3",
}

# Individual files left behind, with the reason.
SKIPPED_FILES = {
    # Upstream skips this one too, in tool/bin/test.dart. jlox compares numbers
    # with Java's Double.equals, which says NaN equals itself, while clox
    # follows IEEE-754, which says it does not. The expectations in the file are
    # clox's. This course leaves that decision to each group, so the suite has
    # no opinion to encode here.
    "number/nan_equality.lox": "implementation-defined NaN identity, skipped upstream too",
}

# lab3 has no statements yet, so a file that declares or names things cannot be
# expressed as a list of expressions. Such a file is not thrown away, it moves
# to the first lab that can express it.
NEEDS_STATEMENTS = re.compile(r"\b(var|fun|while|for|if|return)\b")
NEEDS_FUNCTIONS = re.compile(r"\b(fun|while|for|if|return)\b")

PRINT_STATEMENT = re.compile(r"^(\s*)print\s+")

# `// Error at 'x': msg`, `// [line 4] Error: msg`, `// [line 4] Error at 'x': msg`
STATIC_ERROR = re.compile(r"^(?:\[line \d+\]\s*)?Error(?: at [^:]*)?:\s*(.*)$")
# `// [c line 4] Error...` and `// [java line 4] Error...`
IMPLEMENTATION_SPECIFIC = re.compile(r"^\[(?:c|java) line \d+\]")

COMMENT = re.compile(r"//\s*(.*)$")
ANNOTATION_KEYWORD = re.compile(r"expect\b")


def classify(path: Path, root: Path):
    """Returns the lab a corpus file belongs to, or None to leave it behind."""
    relative = path.relative_to(root)
    parts = relative.parts

    if relative.as_posix() in SKIPPED_FILES:
        return None

    if len(parts) == 1:
        return LAB_BY_ROOT_FILE.get(parts[0])

    directory = parts[0]
    if directory in SKIPPED_DIRECTORIES:
        return None
    return LAB_BY_DIRECTORY.get(directory)


def rewrite_annotations(text: str):
    """
    Translates upstream's annotation vocabulary into this harness's.

    Returns the rewritten text and a list of notes about anything dropped, so
    the caller can report it rather than losing it quietly.
    """
    out_lines = []
    notes = []

    for line in text.splitlines():
        match = COMMENT.search(line)
        if not match:
            out_lines.append(line)
            continue

        comment = match.group(1).strip()
        start = match.start()

        # Upstream has at least one annotation that is itself commented out, so
        # the test it belongs to asserts nothing and always passes. Unwrap it
        # rather than carrying a dead test forward.
        if comment.startswith("//") and ANNOTATION_KEYWORD.match(comment.lstrip("/ ")):
            comment = comment.lstrip("/ ")
            notes.append(f"revived a commented-out annotation: {comment}")
            out_lines.append(f"{line[:start]}// {comment}")
            continue

        if IMPLEMENTATION_SPECIFIC.match(comment):
            # A note about how clox and jlox differ. Not our business, and
            # keeping it would assert a diagnostic we never expect to see.
            notes.append(f"dropped implementation-specific note: {comment}")
            stripped = line[:start].rstrip()
            if stripped:
                out_lines.append(stripped)
            continue

        error = STATIC_ERROR.match(comment)
        if error:
            out_lines.append(f"{line[:start]}// expect error: {error.group(1).strip()}")
            continue

        out_lines.append(line)

    return "\n".join(out_lines) + "\n", notes


def strip_print_statements(text: str):
    """
    Turns `print <expr>;` into `<expr>;` for the lab that has no statements.

    The value printed is the same either way: lab 3's entry point evaluates
    every expression in the file and prints what each one came to.
    """
    return "\n".join(PRINT_STATEMENT.sub(r"\1", line) for line in text.splitlines()) + "\n"


ANY_ANNOTATION = re.compile(r"//\s*expect\b")


def declare_silence_if_needed(text: str) -> str:
    """
    Adds `// expect nothing` to a file that asserts nothing.

    Upstream has a few tests that are only comments, and whose whole point is
    that the interpreter prints nothing. This harness rejects a file with no
    expectations, because in every other case that means the annotations are
    broken. Saying it out loud is the difference.
    """
    if ANY_ANNOTATION.search(text):
        return text
    return text.rstrip("\n") + "\n// expect nothing\n"


def adapt(source_root: Path, destination_root: Path, dry_run: bool):
    counts = {}
    skipped = []
    # Upstream distinguishes a couple of tests only by whether the file ends in
    # a newline, which stops being a distinction once annotations are appended.
    # Keeping both would put two byte-identical tests in the corpus under
    # different names, which is worse than keeping one.
    already_written = {}

    for path in sorted(source_root.rglob("*.lox")):
        lab = classify(path, source_root)
        if lab is None:
            continue

        text = path.read_text(encoding="utf-8")
        code = code_only(text)

        if BEYOND_THE_COURSE.search(code):
            skipped.append((path.relative_to(source_root), "uses classes"))
            continue

        text, notes = rewrite_annotations(text)

        if lab == "lab3":
            if NEEDS_FUNCTIONS.search(code):
                lab = "lab5"
                notes.append("moved to lab5: needs control flow or functions")
            elif NEEDS_STATEMENTS.search(code):
                lab = "lab4"
                notes.append("moved to lab4: needs statements")
            else:
                text = strip_print_statements(text)

        text = declare_silence_if_needed(text)

        relative = path.relative_to(source_root)

        seen = already_written.get((lab, text))
        if seen is not None:
            skipped.append((relative, f"identical to {seen} once adapted"))
            continue
        already_written[(lab, text)] = relative

        # Flatten one level, so operator/add.lox becomes operator_add.lox and
        # every test in a lab folder has a name that says where it came from.
        name = "_".join(relative.parts)
        target = destination_root / lab / name

        counts[lab] = counts.get(lab, 0) + 1
        for note in notes:
            print(f"  {relative}: {note}")

        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(text)

    print()
    for lab in sorted(counts):
        print(f"{lab}: {counts[lab]} files")
    print(f"left behind: {len(skipped)}")
    for relative, reason in skipped:
        print(f"  {relative} ({reason})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", help="Path to craftinginterpreters/test")
    parser.add_argument(
        "--into",
        default=str(Path(__file__).resolve().parent.parent / "tests"),
        help="Where the lab folders live. Defaults to reference/tests.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source_root = Path(args.corpus).resolve()
    if not source_root.is_dir():
        print(f"ERROR: '{source_root}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    adapt(source_root, Path(args.into).resolve(), args.dry_run)


if __name__ == "__main__":
    main()
