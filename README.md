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
curl -sSL https://raw.githubusercontent.com/WhiteLicorice/cmsc-124-harness/v1.0/run_tests.py -o run_tests.py
python3 run_tests.py tests/lab0
```

The URL names a tag rather than `main` on purpose. If the harness picks up a
bugfix halfway through the semester, that fix should not retroactively change
what passing meant for a defense you already finished. When the instructor
bumps the tag, it gets announced through channels with a
changelog entry. Update the tag in your own workflow only when you are told to.

You can also download `run_tests.py` and run it on your own machine before
pushing, exactly as CI would:

```bash
curl -sSL https://raw.githubusercontent.com/WhiteLicorice/cmsc-124-harness/v1.0/run_tests.py -o run_tests.py
python3 run_tests.py tests/lab1
```

It needs Python 3.8 or newer and nothing else. Standard library only, so there
is no `pip install` step, no `venv` requirements.

Windows, Linux, and macOS all work. Windows cannot execute a file whose
executability comes from a shebang line, so on Windows the harness reads that
line and names the interpreter itself: a `run` beginning with
`#!/usr/bin/env bash` gets launched as `bash run`, using the bash that Git for
Windows installs (Git for Windows is a course requirement). This needs nothing from you, and it does not need WSL. A
native `.exe`, `.bat`, or `.cmd` entrypoint is launched directly.

Your entrypoint always receives the test file as a repo-relative path with
forward slashes, so shell scripts never have to deal with backslashes.

---

## 2. What your repo needs to provide

1. A `./run <path-to-source-file>` entrypoint at your repo root, or wherever
   you point `--repo-root`, that:
   - prints your program's output to stdout;
   - prints diagnostics such as parse errors and runtime errors to stderr;
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
  "run_entrypoint": "./run"
}
```

| Field | Meaning |
|---|---|
| `ext` | Extension of your test and source files under this folder, e.g. `.src`, `.lox`, `.mylang`. |
| `flag` | Optional CLI flag passed to `./run` before the file path, e.g. `--tokenize` for Laboratory Activity 1's scanner stage. `null` for plain execution. |
| `mode` | `"sidecar"` or `"inline"`. See §4. |
| `expect_prefix` / `expect_error_prefix` / `expect_compile_error_prefix` | Used in `"inline"` mode only: the comment prefixes your test files use. The defaults match the *Crafting Interpreters* convention exactly. |
| `run_entrypoint` | Path to your run script, if it is not `./run` at the repo root. |

Different lab folders can use different manifests, so `tests/lab1/` might be in
sidecar mode while `tests/lab3/` is in inline mode. The harness reads whichever
`manifest.json` sits in the folder you point it at.

---

## 4. Two annotation modes

### Sidecar mode (`"mode": "sidecar"`)

Use this whenever your output depends on your own syntax and there is no
external oracle to compare it against. The canonical case is the Scanner in
Laboratory Activity 1, where the token type names are vocabulary you invented. Checking here is
a **regression check**: your output today against the output your own group
committed earlier, not a comparison with anyone else's answer.

For a test file `tests/lab1/foo.src`, commit:

- `tests/lab1/foo.expected`, the exact stdout your `./run` should produce;
- `tests/lab1/foo.exit`, optional, the expected exit code as plain text. If you
  omit it, 0 is assumed.

```
tests/lab1/
  foo.src
  foo.expected
  foo.exit       <- optional, only needed for non-zero exit codes
  manifest.json
```

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
  stderr, since diagnostics are diagnostics and do not belong in program
  output, and that the exit code is 70.
- `// expect error: <message>` does the same but expects exit code 65, for
  static errors caught before execution starts.

Comment syntax is assumed to be `//`. If your invented language uses something
else for comments, put that lab in sidecar mode instead and route around the
assumption rather than fighting it.

---

## 5. Fast way to verify the harness works before you trust it

Do not take `run_tests.py` on faith. Run the bundled self-test, which exercises
both modes and, more importantly, confirms that the script actually *fails* a
test that deserves to fail, rather than only passing tests that deserve to pass:

```bash
git clone https://github.com/WhiteLicorice/cmsc-124-harness.git
cd cmsc-124-harness
./selftest.sh
```

It takes a few seconds and needs nothing but Python 3 and bash. No per-language
toolchain is involved, because `examples/*/run` are tiny bash stand-ins rather
than real interpreters. The output ends with:

```
All self-checks behaved as expected. run_tests.py is working correctly.
```

If you have changed `run_tests.py` itself, which is instructor work that groups
should never need to do, run `./selftest.sh` before tagging a release. CI also
runs it on every push through `.github/workflows/selftest.yml`.

`examples/sidecar-mode/` and `examples/inline-mode/` hold minimal worked repos
in both modes, including their `run` scripts, if you would rather see the whole
shape at once than assemble it from this README.

---

## 6. Versioning

- `main` is active development. Do not point your CI at this branch.
- Tags (`v1.0`, `v1.1`, and so on) are what groups pin to. They get bumped and
  announced on the course Messenger channel, with a changelog entry, whenever
  the harness changes mid-semester.

## 7. Repo layout

```
run_tests.py                       <- the only file groups actually fetch
selftest.sh                        <- fast correctness check for this repo itself
.github/workflows/selftest.yml     <- runs selftest.sh in CI on every push
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
```
