#!/usr/bin/env bash
# Builds the reference implementation from a clean checkout, the same way the
# laboratory activities ask every group to.
#
# Needs GHC 9.6.5 or newer and cabal. Neither is needed to use the harness
# itself: this is instructor tooling, and groups never build it.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -f xolsh/xolsh.cabal ]; then
  echo "ERROR: the xolsh submodule is empty. Run:" >&2
  echo "  git submodule update --init reference/xolsh" >&2
  exit 1
fi

# GHC's linker on Windows hands the build directory to llvm-ar without quoting
# it, so a path with a space in it fails at the very last step. The course
# materials live under "CMSC 124", which has one. Building somewhere else is
# the fix; there is nothing to do about it on GHC's side.
build_arguments=()
case "$PWD" in
  *\ *)
    elsewhere="${CMSC124_BUILD_DIR:-${LOCALAPPDATA:-$HOME}/cmsc124-ref-build}"
    elsewhere="${elsewhere//\\//}"
    echo "This path has a space in it, so building in $elsewhere instead."
    build_arguments+=("--builddir=$elsewhere")
    ;;
esac

cabal build "${build_arguments[@]}" cmsc124-ref

# Copy the binary somewhere with a stable name, so ./run does not pay cabal's
# resolution cost on every one of a few hundred test files.
mkdir -p bin
binary="$(cabal list-bin "${build_arguments[@]}" cmsc124-ref)"
cp "$binary" "bin/$(basename "$binary")"

echo "Built bin/$(basename "$binary")"
