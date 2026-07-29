# cmsc-124-harness

A single, language-agnostic test runner (`run_tests.py`) shared by every pair in
CMSC 124, regardless of which host language or invented syntax they're using.

**What it does not do:** parse anyone's grammar, know anyone's token vocabulary,
or contain anything language-specific. It only ever calls a pair's own `./run`
entrypoint on committed test files, then diffs stdout + exit code against
expectations the pair themselves committed. Same script, zero edits, works for
every lab and every language in the course's pool (Rust, Kotlin, Dart, C#, C++,
Go, Julia).

---

## 1. How your pair fetches this

Do **not** vendor or submodule this repo into your own. Fetch the pinned script
directly in CI (this is what the CI wiring in the Lab 0 manual already does for
every language):

```bash
curl -sSL https://raw.githubusercontent.com/WhiteLicorice/cmsc-124-harness/v1.0/run_tests.py -o run_tests.py
python3 run_tests.py tests/lab0
```

**Why a pinned tag (`v1.0`) and not `main`:** if the harness gets a bugfix
mid-semester, that fix should not retroactively change what "passing" meant for
a defense you already completed. When the instructor bumps the tag, it'll be
announced on the course Messenger channel along with a changelog entry — update
the tag in your own CI workflow only when told to.

You can also just download `run_tests.py` locally to run it on your own machine
before pushing, exactly as CI would:

```bash
curl -sSL https://raw.githubusercontent.com/WhiteLicorice/cmsc-124-harness/v1.0/run_tests.py -o run_tests.py
python3 run_tests.py tests/lab1
```

Requires Python 3.8+ and nothing else (standard library only — no `pip install`
needed).

Windows, Linux, and macOS are all supported. Windows cannot execute a file
with a shebang line, so on Windows the harness reads your entrypoint's shebang
and names the interpreter itself: a `run` starting with `#!/usr/bin/env bash`
gets launched as `bash run`, using the bash that Git for Windows installs. You
do not have to do anything for this, and you do not need WSL. If your `run` is
a native `.exe`, `.bat`, or `.cmd`, it is launched directly.

Your entrypoint always receives the test file as a repo-relative path with
forward slashes, so shell scripts do not have to deal with backslashes.

---

## 2. What your repo needs to provide

1. A `./run <path-to-source-file>` entrypoint at your repo root (or wherever you
   pass via `--repo-root`) that:
   - prints your program's output to **stdout**
   - prints diagnostics (parse errors, runtime errors) to **stderr**
   - exits **0** on success, **65** on a static/compile-time error, **70** on a
     runtime error
2. A `manifest.json` in each test folder (e.g. `tests/lab1/manifest.json`)
   describing that folder's conventions — see §3.
3. Your actual test files, following whichever annotation format that lab
   stage calls for — see §4.

---

## 3. `manifest.json`

Every field is optional; any you omit fall back to these defaults:

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
| `ext` | Extension of your test/source files under this folder, e.g. `.src`, `.lox`, `.mylang`. |
| `flag` | Optional CLI flag passed to `./run` before the file path, e.g. `--tokenize` for Lab 1's scanner stage. `null` for plain execution. |
| `mode` | `"sidecar"` or `"inline"` — see §4. |
| `expect_prefix` / `expect_error_prefix` / `expect_compile_error_prefix` | Only used in `"inline"` mode — the comment prefixes your test files use. Defaults match the *Crafting Interpreters* convention exactly. |
| `run_entrypoint` | Path to your run script, if not `./run` at the repo root. |

Different lab folders can use different manifests (e.g. `tests/lab1/` in
sidecar mode, `tests/lab3/` in inline mode) — the harness reads whichever
`manifest.json` sits in the folder you point it at.

---

## 4. Two annotation modes

### Sidecar mode (`"mode": "sidecar"`)

Use this whenever your output is inherently syntax-dependent and there's no
external oracle to compare against — the canonical case is the Scanner in
Lab 1, where the token type names are your own invented vocabulary. Grading
here is a **regression check**: your output today vs. the output your own pair
committed earlier, not a ground-truth comparison against anyone else's answer.

For a test file `tests/lab1/foo.src`, commit:
- `tests/lab1/foo.expected` — the exact stdout your `./run` should produce
- `tests/lab1/foo.exit` — *(optional)* the expected exit code as plain text; if
  omitted, `0` is assumed

```
tests/lab1/
  foo.src
  foo.expected
  foo.exit       <- optional, only needed for non-zero exit codes
  manifest.json
```

### Inline mode (`"mode": "inline"`)

Use this from the interpreter/runtime labs onward, once program *output
values* are semantically determined and syntax-independent regardless of your
invented grammar. This is the exact `// expect:` convention from
*Crafting Interpreters* itself:

```
PRINT 3 + 4
// expect: 7
```

- `// expect: <value>` — checks **stdout**, line by line, in order.
- `// expect runtime error: <message>` — checks that the message appears in
  **stderr** (not stdout — diagnostics are diagnostics) and that the exit code
  is **70**.
- `// expect error: <message>` — same, but exit code **65** (static/compile-time
  errors caught before execution even starts).

Comment syntax is assumed to be `//`. If your invented language doesn't use
`//` for comments, use sidecar mode instead for that lab — don't fight the
harness's assumption, route around it.

---

## 5. Fast way to verify the harness works before you trust it

Don't take `run_tests.py`'s correctness on faith — run the bundled self-test,
which exercises both modes and, critically, checks that the script actually
*fails* a test that should fail (not just that it passes tests that should
pass):

```bash
git clone https://github.com/WhiteLicorice/cmsc-124-harness.git
cd cmsc-124-harness
./selftest.sh
```

Takes a few seconds, needs nothing but Python 3 and bash — no per-language
toolchain required, since `examples/*/run` are tiny bash stand-ins, not real
interpreters. Expected output ends with:

```
All self-checks behaved as expected. run_tests.py is working correctly.
```

If you've made a change to `run_tests.py` itself (instructor use — pairs
should never need to edit this file), run `./selftest.sh` before tagging a new
release. CI also runs this automatically on every push via
`.github/workflows/selftest.yml`.

See `examples/sidecar-mode/` and `examples/inline-mode/` for minimal worked
repos in both modes, including their `run` scripts, if you want to see the
whole shape end to end rather than piecing it together from this README.

---

## 6. Versioning

- `main` — active development; **do not** point your CI at this branch.
- Tags (`v1.0`, `v1.1`, ...) — what pairs actually pin to. Bumped and announced
  via the course Messenger channel with a changelog entry when the harness
  changes mid-semester.

## 7. Repo layout

```
run_tests.py                       <- the only file pairs actually fetch
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
