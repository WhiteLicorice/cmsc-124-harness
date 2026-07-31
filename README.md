# cmsc-124-harness

A language-agnostic test runner shared by every group in
CMSC 124 Laboratory no matter which host language they picked or what syntax they invented.

It does not parse anyone's grammar, know anyone's token vocabulary, or contain
anything specific to one language. All it ever does is call your own `./run`
entrypoint on the test files you committed, then compare stdout and the exit
code against the expectations you committed alongside them. The same script,
with no edits, covers every lab and every language in the course pool.

---

## 1. How your group fetches this

Do not vendor this repository into your own, and do not add it as a submodule.
Fetch the pinned script in CI, which is what the CI wiring in the Laboratory Activity 0 manual
already does for every language:

```bash
curl -sSL https://raw.githubusercontent.com/WhiteLicorice/cmsc-124-harness/v1.1/run_tests.py -o run_tests.py
python3 run_tests.py tests/lab0
```

The URL names a tag rather than `main` on purpose. If the harness picks up a
bugfix halfway through the semester, that fix should not retroactively change
what passing meant for a defense you already finished. When the instructor
bumps the tag, it gets announced through channels with a
changelog entry. Update the tag in your own workflow only when you are told to.

You can also download `run_tests.py` and run it on your own machine before
pushing, the same way CI would:

```bash
curl -sSL https://raw.githubusercontent.com/WhiteLicorice/cmsc-124-harness/v1.1/run_tests.py -o run_tests.py
python3 run_tests.py tests/lab1
```

It needs Python 3.9 or newer and nothing else. Standard library only, so there
is no `pip install` step, no `venv` requirements.

Windows, Linux, and macOS all work. Windows cannot execute a file whose
executability comes from a shebang line, so on Windows the harness reads that
line and names the interpreter itself: a `run` beginning with
`#!/usr/bin/env bash` gets launched as `bash run`, using the bash that Git for
Windows installs (Git for Windows is a course requirement). This needs nothing from you. It does not need WSL. A native
`.exe`, `.bat`, or `.cmd` entrypoint is launched directly.

Your entrypoint always receives the test file as a repo-relative path with
forward slashes, so shell scripts never have to deal with backslashes.

---

## 2. What your repo needs to provide

1. A `./run <path-to-source-file>` entrypoint at your repo root, or wherever
   you point `--repo-root`, that:
   - prints your program's output to stdout.
   - prints diagnostics such as parse errors and runtime errors to stderr.
   - exits 0 on success, 65 on a static or compile-time error, and 70 on a
     runtime error.
2. A `manifest.json` in each test folder, for example
   `tests/lab1/manifest.json`, describing that folder's conventions. See §3.
3. Your actual test files, in whichever annotation format that stage of the
   labs calls for. See §4.

---

## 3. `manifest.json`

Every field is optional. Anything you leave out falls back to these defaults:

```json
{
  "ext": ".src",
  "flag": null,
  "mode": "sidecar",
  "expect_prefix": "expect:",
  "expect_error_prefix": "expect runtime error:",
  "expect_compile_error_prefix": "expect error:",
  "expect_nothing_prefix": "expect nothing",
  "comment_prefix": "//",
  "comment_suffix": null,
  "run_entrypoint": "./run"
}
```

| Field | Meaning |
|---|---|
| `ext` | Extension of your test and source files under this folder, e.g. `.src`, `.lox`, `.mylang`. |
| `flag` | Optional CLI flag passed to `./run` before the file path, e.g. `--tokenize` for Laboratory Activity 1's scanner stage. `null` for plain execution. |
| `mode` | `"sidecar"` or `"inline"`. See §4. |
| `expect_prefix` / `expect_error_prefix` / `expect_compile_error_prefix` | Used in `"inline"` mode only: the annotation prefixes your test files use, written inside a comment. The defaults match the *Crafting Interpreters* convention exactly. |
| `expect_nothing_prefix` | Used in `"inline"` mode only: how a test file says it produces no output on purpose. See §4. |
| `comment_prefix` | Used in `"inline"` mode only: how a comment starts in the language you invented. One token, or a list if your language has several. |
| `comment_suffix` | Used in `"inline"` mode only: how a comment ends, for bracketed comments such as `(* ... *)`. `null` when comments run to end of line. |
| `run_entrypoint` | Path to your run script, if it is not `./run` at the repo root. |

Those are all the fields there are. A field the harness does not recognize is an
error rather than something it quietly ignores, because a manifest that says
`run_entryoint` would otherwise fall back to `./run` without a word. You would
spend an afternoon debugging an entrypoint that was never being read.

Different lab folders can use different manifests, so `tests/lab1/` might be in
sidecar mode while `tests/lab3/` is in inline mode. The harness reads whichever
`manifest.json` sits in the folder you point it at.

Every file the harness reads is UTF-8, on every platform, so accented
characters and anything else outside ASCII are fine in your test files, your
expectations, and your manifests.

---

## 4. Two annotation modes

### Sidecar mode (`"mode": "sidecar"`)

Use this whenever your output depends on your own syntax and there is no
external oracle to compare it against. The canonical case is the Scanner in
Laboratory Activity 1, where the token type names are vocabulary you invented. Checking here is
a **regression check**: your output today against the output your own group
committed earlier, not a comparison with anyone else's answer.

For a test file `tests/lab1/foo.src`, commit:

- `tests/lab1/foo.expected`, the exact stdout your `./run` should produce.
- `tests/lab1/foo.exit`, optional, the expected exit code as plain text. If you
  omit it, 0 is assumed.

```
tests/lab1/
  foo.src
  foo.expected
  foo.exit       <- optional, only needed for non-zero exit codes
  manifest.json
```

Nothing here needs registering anywhere. Discovery is recursive, so every file
matching `ext` anywhere under the folder you point at becomes a test, including
files in subfolders you invent for your own organization. Expectations are
paired by filename stem, so `foo.src` looks for `foo.expected` sitting next to
it. One `manifest.json` at the top of the folder governs everything beneath it.
Adding your hundredth test case means adding files and nothing else:

```
tests/lab1/
  manifest.json
  keywords.src
  keywords.expected
  numbers.src
  numbers.expected
  strings/
    escapes.src
    escapes.expected
    unterminated.src
    unterminated.expected
    unterminated.exit      <- contains: 65
```

A test file with no matching `.expected` is reported as a failure rather than
skipped, so you cannot lose a test case by forgetting its expectation. The
reverse case, an `.expected` left behind after you renamed or deleted its test,
is reported as a warning: it does not fail the run, but it does get named, since
a stale expectation is invisible otherwise.

### Inline mode (`"mode": "inline"`)

Use this from the interpreter and runtime labs onward, once the *values* your
program produces are determined by semantics rather than by your grammar. This
is the `// expect:` convention from *Crafting Interpreters* itself:

```
PRINT 3 + 4
// expect: 7
```

- `// expect: <value>` checks stdout, line by line, in order.
- `// expect runtime error: <message>` checks that the message appears on
  stderr and that the exit code is 70, since a diagnostic belongs there rather
  than in program output.
- `// expect error: <message>` does the same but expects exit code 65, for
  static errors caught before execution starts.
- `// expect nothing` says the file produces no output at all, on purpose.

A file can carry as many diagnostics as it likes. Each one is looked for in
stderr on its own, so a parser that prints three errors before giving up can be
tested for all three, in any order, with anything else it prints in between.

That last annotation closes a hole. An inline test with no annotations expects
no output and exit 0, which any silent program satisfies. So a file whose
annotations are all typo'd, or that lost them in a bad merge, would pass no
matter what your interpreter did. The harness now fails a file that asserts
nothing. It also fails a comment that looks like an annotation but did not
parse:

```
print 1;
// expect : 1
```

That is one space away from being correct. It used to be worth nothing, and now
it gets reported by name. If a file is supposed to be silent, say so with
`// expect nothing` and the harness will hold you to it.

Annotations live in comments, so the harness has to know what a comment looks
like in the language you invented. It defaults to `//`, and you override it with
`comment_prefix`. A language using `#`:

```json
{
  "ext": ".mila",
  "mode": "inline",
  "comment_prefix": "#"
}
```

```
print 3 + 4
# expect: 7
```

If your language has more than one comment token, list them all. Tokens are
matched literally and longest first, so a `//` token cannot shadow a `///` one:

```json
{
  "comment_prefix": ["#", "--"]
}
```

If your comments are bracketed rather than running to end of line, name the
closing token too and it gets stripped off the annotation:

```json
{
  "comment_prefix": "(*",
  "comment_suffix": "*)"
}
```

```
print 3 + 4
(* expect: 7 *)
```

There is no comment syntax that forces you out of inline mode. If you set
`comment_prefix` to nothing at all, the harness stops with a configuration
error rather than silently treating every line as an annotation.

### Which mode to reach for

Inline mode is the better default wherever it fits. It is what *Crafting
Interpreters* does. One file is one test case. It holds the program, the output it should produce, and the exit code it should end on. A reviewer sees the
whole claim at once. Your commit history shows one new file per new test
instead of two or three.

Sidecar mode earns its place when your expected output reports positions in the
source, which in practice means the scanner lab. The reason is worth
understanding before you choose, because it is not obvious. Annotation comments
are themselves lines in the file, so they push the code below them further down.
Given this test:

```
var x
// expect: TOKEN(var, line=1)
// expect: TOKEN(x, line=1)
var y
// expect: TOKEN(var, line=4)
// expect: TOKEN(y, line=4)
```

`var y` is on line 4, not line 2, because two comments sit above it. Writing the
intuitive `line=2` produces a mismatch:

```
       stdout mismatch:
       --- expected
       +++ actual
       -TOKEN(var, line=2)
       +TOKEN(var, line=4)
```

Your scanner is right and your test is wrong, which is a miserable way to spend
an afternoon. Sidecar mode keeps expectations out of the source file entirely, so
line numbers stay where you wrote them.

You can dodge the problem in inline mode by putting the annotation at the end of
the line it describes, since a trailing comment adds no lines of its own:

```
print 3 + 4   // expect: 7
```

That works cleanly when one source line produces exactly one line of output. A
scanner emits a token per lexeme, so a single line of source becomes several
lines of output, and once you need more annotations than you have source lines
the shifting comes back. Hence the split: sidecar for the
scanner, inline for the labs after it, where output is values rather than
positions.

---

## 5. A worked example, start to finish

Here is a complete repository, small enough to read in one sitting, that goes
from nothing to a passing run. Say your group invented a language called `mila`
and chose Go as the host.

Start with the two scripts the run contract asks for. `build.sh` compiles your
interpreter once:

```bash
#!/usr/bin/env bash
# build.sh
set -e
mkdir -p build
go build -o build/interpreter ./cmd/interpreter
```

`run` executes what `build.sh` produced, forwarding its arguments:

```bash
#!/usr/bin/env bash
# run
exec ./build/interpreter "$@"
```

Mark both executable, or nothing downstream works:

```bash
chmod +x build.sh run
```

Now declare your conventions. Your source files end in `.mila`, and for the
scanner lab you want expectations kept out of the source, so:

```json
{
  "ext": ".mila",
  "mode": "sidecar"
}
```

Save that as `tests/lab1/manifest.json`. The fields you left out keep their
defaults, which is why `run_entrypoint` and the rest are absent.

Write your first test. `tests/lab1/keywords.mila` holds a program in your own
syntax:

```
var greeting = "hello"
print greeting
```

Run your interpreter on it once by hand, look hard at the output, and decide
whether it is what you meant. Once you believe it, that output becomes
`tests/lab1/keywords.expected`:

```
TOKEN(VAR, "var", line=1)
TOKEN(IDENTIFIER, "greeting", line=1)
TOKEN(EQUAL, "=", line=1)
TOKEN(STRING, "hello", line=1)
TOKEN(PRINT, "print", line=2)
TOKEN(IDENTIFIER, "greeting", line=2)
TOKEN(EOF, "", line=2)
```

This test expects a clean exit, so it needs no `.exit` file. The tree so far:

```
build.sh
run
go.mod
cmd/interpreter/main.go
tests/lab1/
  manifest.json
  keywords.mila
  keywords.expected
```

Run it the way CI will:

```bash
curl -sSL https://raw.githubusercontent.com/WhiteLicorice/cmsc-124-harness/v1.1/run_tests.py -o run_tests.py
./build.sh
python3 run_tests.py tests/lab1
```

```
[PASS] tests/lab1/keywords.mila

1/1 tests passed.
```

Now add a test for input your scanner should reject. `tests/lab1/unterminated.mila`
holds a string with no closing quote:

```
var broken = "no closing quote
```

Your scanner should report the problem on stderr and exit 65, so
`tests/lab1/unterminated.expected` is empty (nothing legitimate reached stdout)
and `tests/lab1/unterminated.exit` contains one line:

```
65
```

You added a test case by adding files. No list to update, no registration step:

```
python3 run_tests.py tests/lab1
```

```
[PASS] tests/lab1/keywords.mila
[PASS] tests/lab1/unterminated.mila

2/2 tests passed.
```

When something does break, you get the diff rather than a bare failure. Suppose
you refactor your scanner and it starts emitting `STR` where it used to emit
`STRING`:

```
[PASS] tests/lab1/keywords.mila
[FAIL] tests/lab1/unterminated.mila
       exit code: expected 65, got 70
       (stderr was: panic: index out of range)

1/2 tests passed.
```

That tells you the refactor turned a clean rejection into a crash, a regression
the committed expectations exist to catch.

Later, once you are past the scanner and your tests are about computed values
rather than token positions, switch that lab's folder to inline mode. The
manifest becomes:

```json
{
  "ext": ".mila",
  "mode": "inline"
}
```

And a whole test case is one file, `tests/lab3/arithmetic.mila`:

```
print 3 + 4
// expect: 7
print 2 * 5
// expect: 10
print 1 / 0
// expect runtime error: Division by zero.
```

That last line also asserts the exit code is 70, since a runtime error is
expected. Nothing else needs to exist for that test.

---

## 6. Fast way to verify the harness works before you trust it

Do not take `run_tests.py` on faith. Run the bundled self-test, which exercises
both modes and, more importantly, confirms that the script *fails* a test that
deserves to fail, rather than only passing tests that deserve to pass:

```bash
git clone https://github.com/WhiteLicorice/cmsc-124-harness.git
cd cmsc-124-harness
./selftest.sh
```

It takes about twenty seconds and needs nothing but Python 3. The checks live in
`tests/`, written with Python's own `unittest`, so `python3 -m unittest discover
--start-directory tests --top-level-directory tests` does the same thing if you
would rather not go through bash. Around a hundred of them run against stand-in
entrypoints, which is why no per-language toolchain is involved.

`examples/sidecar-mode/` and `examples/inline-mode/` hold minimal worked repos
in both modes, including their `run` scripts, if you would rather see the whole
structure at once than assemble it from this README.

A grading tool is only as trustworthy as what it has been tested against.
`reference/` holds a Lox interpreter and a few hundred tests across all
five activities, so the harness has been run against an actual
scanner's token stream, actual parse errors on stderr, actual exit 70s, and an
actual interpreter that might run forever. The interpreter is written in
Haskell, a functional language. Every group in this course writes theirs in something imperative, so
the reference cannot be lifted into a submission.

You do not need any of this to use the harness. It is proof, not plumbing. But
you can build the reference locally and watch the same suite that CI runs
against it grade your own tests:

```bash
# One-time. ghcup puts GHC and cabal on your PATH.
curl --proto '=https' --tlsv1.2 -sSf https://get-ghcup.haskell.org | sh

# Clone with the nested submodule and build the interpreter.
git clone --recurse-submodules https://github.com/WhiteLicorice/cmsc-124-harness.git
cd cmsc-124-harness/reference
./build.sh

# Run the harness against the reference, one activity at a time.
cd ..
python3 run_tests.py reference/tests/lab1 --repo-root reference
python3 run_tests.py reference/tests/lab3 --repo-root reference
python3 run_tests.py reference/tests/lab5 --repo-root reference

# With the reference built, the mutation suite runs: each test breaks
# something on purpose and insists the harness catches it.
python3 -m unittest discover --start-directory tests --top-level-directory tests
```

On Windows, GHC's linker breaks on a path with a space. The course materials
live under `CMSC 124`, so `build.sh` detects that and builds somewhere else.

If you are setting up from Windows itself rather than WSL, install Git Bash
first (it is a course requirement) and launch it from there. Then fetch GHCup
through its Windows installer instead of `curl`:

```powershell
# PowerShell, one time.
Invoke-WebRequest -Uri "https://downloads.haskell.org/~ghcup/x86_64-mingw64-ghcup.exe" -OutFile ghcup.exe
./ghcup.exe install ghc 9.6.5 --set
./ghcup.exe install cabal latest --set
```

After that, the build and test steps above work from Git Bash. The harness and
the reference need the same things on every platform.

CI runs the unittest suite on Linux, Windows, and macOS through
`.github/workflows/selftest.yml`. The reference suite runs on Linux and Windows
through `.github/workflows/reference.yml`.

---

## 7. Versioning

- `main` is active development. Do not point your CI at this branch.
- Tags (`v1.0`, `v1.1`, and so on) are what groups pin to. They get bumped and
  announced through channels, with a changelog entry, whenever
  the harness changes mid-semester.

## 8. Repo layout

```
run_tests.py                       <- the only file groups actually fetch
selftest.sh                        <- runs the suite below
tests/                             <- the correctness gate for this repo itself
  test_units.py                      one function at a time
  test_e2e_fakes.py                  the whole runner, against stand-in entrypoints
  test_hardening.py                  the failure modes that used to be silent
  test_e2e_reference.py              the whole runner, against a real interpreter
examples/
  sidecar-mode/
    run
    tests/lab0/
      hello.src
      hello.expected
      manifest.json
  inline-mode/
    run
    tests/lab3/
      arithmetic.src
      runtime_error.src
      manifest.json
reference/                         <- instructor tooling; see reference/README.md
  xolsh/                             a Lox interpreter, as a submodule
  driver/                            the four laboratory stages on top of it
  tests/lab0 ... lab5, crossmode     a few hundred tests to grade it with
.github/workflows/
  selftest.yml                     <- the unittest suite, three platforms
  reference.yml                    <- the reference suite, Linux and Windows
```
