# The reference implementation

This folder holds a real, working language implementation and a few hundred
tests against it. Neither is course material. Groups never build this, never
read it, and never need it. It exists for one reason: so that `run_tests.py` is
proven against a language instead of against stand-in scripts.

The problem it solves is narrow and worth stating plainly. Before this existed,
the harness was checked by pointing it at two-line bash scripts that echoed
their input. Those scripts cannot produce a scanner's token stream, cannot emit
a parse error on stderr and exit 65, cannot die partway through a program with
exit 70, and cannot be slow. So the parts of the harness that handle all of
that were, in effect, untested. A grading tool nobody has stress-tested is a
patch waiting to happen in week nine, which is the worst possible week for it.

## What is here

`xolsh/` is a submodule: a tree-walking Lox interpreter written in Haskell by
0rphee, BSD-3 licensed. Haskell is not an accident. Every group in this course
writes their interpreter in something imperative, so a reference in a
functional language cannot be quietly lifted into a submission.

`driver/` is about two hundred lines that put the course's command line
contract on top of xolsh's library. It reuses xolsh's scanner, parser, AST
printer, resolver, and interpreter, and implements none of them. That matters:
if the driver reimplemented anything, the suite would be testing the driver's
opinion of Lox rather than a real one.

`tests/` is the corpus, one folder per laboratory activity.

`tools/adapt_corpus.py` records how most of lab3, lab4, and lab5 were derived
from Bob Nystrom's own Lox test suite.

`NOTICE` names both upstreams and the exact commits they came from.

## The four stages

The reference answers to the same contract the laboratory activities ask groups
for, with the flag spellings this implementation chose.

| Command | Activity | What comes out |
| --- | --- | --- |
| `./run --tokenize <file>` | 1 | one token per line |
| `./run --parse <file>` | 2 | one parenthesized expression tree per line |
| `./run --eval <file>` | 3 | the value of each expression, one per line |
| `./run <file>` | 4 and 5 | whatever the program prints |

A token looks like this, with the line first because the line is what scanner
tests get wrong most often:

```
[line 1] VAR var null
[line 1] IDENTIFIER a null
[line 1] EQUAL = null
[line 1] NUMBER 1 1.0
[line 1] SEMICOLON ; null
[line 2] EOF <eof> null
```

A parsed expression looks like the book's:

```
(+ (group (- 5.0 (group (- 3.0 1.0)))) (- 1.0))
```

Two things about that output are worth knowing before you write a test against
it. `--parse` prints numbers the way Haskell shows a `Double`, so `5` appears
as `5.0`, while `--eval` prints them the way Lox does, so `5.0` appears as `5`.
That is not an inconsistency to fix: an AST printer is showing you the literal
the parser built, and an interpreter is showing you a value.

The other is that Lox needs its semicolons. The book's own chapter tests write
a bare expression with no semicolon, because the book swaps in a
one-expression parser for those chapters. This reference does not: `--parse`
and `--eval` run the real parser and then require every statement in the file
to be an expression statement, rejecting anything else with exit 65. So a
test file for those stages is a list of expressions, each ending in `;`.

## Building it

You need GHC 9.6.5 or newer and cabal. Nothing else here needs a toolchain, and
the harness itself needs neither.

```bash
git submodule update --init reference/xolsh
cd reference
./build.sh
./run tests/lab0/hello.lox
```

`build.sh` puts the binary in `bin/`, and `run` executes it from there rather
than through `cabal run`, which would otherwise pay cabal's resolution cost on
every one of a few hundred test files.

## Running the tests

From the repository root, one folder at a time, exactly the way a group's CI
workflow does it:

```bash
python3 run_tests.py reference/tests/lab1 --repo-root reference
```

The folders divide the way the course does. Activities 0 through 2 keep their
expectations in sidecar `.expected` files, because their output is
line-sensitive and inline annotation comments would shift the very line numbers
being asserted. Activities 3 through 5 use inline `// expect:` comments.
`crossmode/` holds the same programs written both ways, which is how a
mode-specific bug in the harness gets caught: sidecar and inline have to agree
about identical programs.

## Regenerating sidecar expectations

Sidecar `.expected` files are generated from the reference rather than typed by
hand:

```bash
python3 reference/tools/regen_expected.py reference/tests/lab1
```

Read the diff before committing it. A generated expectation that nobody looks
at records whatever the implementation happened to do that day, including its
bugs, and that is how a corpus quietly stops meaning anything.
