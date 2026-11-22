#!/usr/bin/env bash
# Check that every dynamic dependency of the given ELF files resolves inside /nix/store
# (criterion C1.3: the SDK runs without nix-ld, steam-run or FHS library folders).
#
# Usage: check_elf_deps.sh <dynamic loader> <file>...
#   The loader is the ELF interpreter the files were linked for, such as
#   /nix/store/...-glibc-2.42/lib/ld-linux-x86-64.so.2. Files that are not ELF are
#   skipped; every ELF file must be analysable.
#
# A file fails when:
#   - `<loader> --list <file>` exits with a non-zero status (the loader cannot load or
#     analyse it: truncated or corrupt file, unreadable file, static executable, ...);
#   - a dependency is reported "not found";
#   - a dependency, or the loader itself, resolves outside /nix/store.
# Exit status: 0 when every ELF file passes, 1 otherwise, 2 on usage error.
set -uo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: $0 <dynamic loader> <file>..." >&2
  exit 2
fi
loader=$1
shift

checked=0
failed=0
for f in "$@"; do
  [ -f "$f" ] || continue
  file -L "$f" | grep -q ELF || continue
  checked=$((checked + 1))

  deps=$("$loader" --list "$f" 2>&1)
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "FAIL $f: '$loader --list' exited with status $status:"
    printf '%s\n' "$deps" | sed 's/^/    /'
    failed=$((failed + 1))
    continue
  fi

  problems=$(
    printf '%s\n' "$deps" | grep -E 'not found'
    # "libfoo.so.1 => /nix/store/.../libfoo.so.1 (0x...)": the target must be in the store.
    printf '%s\n' "$deps" | grep -E '=> /' | grep -vE '=> /nix/store/'
    # A bare path line (the loader itself) must be in the store too.
    printf '%s\n' "$deps" | grep -E '^[[:space:]]*/' | grep -vE '^[[:space:]]*/nix/store/'
  )
  if [ -n "$problems" ]; then
    echo "FAIL $f: dependency not found or outside /nix/store:"
    printf '%s\n' "$problems" | sed 's/^/    /'
    failed=$((failed + 1))
  fi
done

if [ "$checked" -eq 0 ]; then
  echo "FAIL: no ELF file among the arguments"
  exit 1
fi
if [ "$failed" -ne 0 ]; then
  echo "FAIL: $failed of $checked ELF files"
  exit 1
fi
echo "$checked ELF files, every dependency resolved inside /nix/store"
