#!/usr/bin/env bash
# Reproducibility check (run inside WSL): the everyday tree (~/bolt-aarch32) against a tree
# built from a fresh GitHub clone (~/repro/tree, see docs/WSL_BUILD.md). With the same inputs
# (same STAIR sizes, same pgo.profdata, same BOLT counters) both must produce the same bytes.
#
#   bash scripts/repro-compare.sh <counters.bin>
set -uo pipefail
E="$HOME/bolt-aarch32"; R="$HOME/repro/tree"
COUNTERS="${1:?usage: $0 <counters.bin from the BOLT profile run on the Pi>}"
LOG="$HOME/repro-compare.log"; : > "$LOG"
say() { echo "$*" | tee -a "$LOG"; }
pass=0; fail=0
check() { # name, hash-a, hash-b
  if [[ -n "$2" && "$2" == "$3" ]]; then say "SAME  $1  (${2:0:16})"; pass=$((pass + 1))
  else say "DIFF  $1  everyday=${2:0:16}  fresh=${3:0:16}"; fail=$((fail + 1)); fi
}

# .bin: byte-identical. .elf: embeds each tree's absolute path in its debug info (different
# lengths, so every later offset shifts) and ThinLTO names promoted locals after a path hash
# (foo.llvm.<hash>); compare its symbol addresses/sizes with that hash normalised instead.
check_file() { # name relative to build-atfe/variants
  local f="$1" a b
  if [[ "$f" == *.elf ]]; then
    a=$(nm -S -n "$E/build-atfe/variants/$f" | sed "s/.llvm.[0-9]*/.llvm.N/" | sha256sum | cut -d' ' -f1); b=$(nm -S -n "$R/build-atfe/variants/$f" | sed "s/.llvm.[0-9]*/.llvm.N/" | sha256sum | cut -d' ' -f1)
    check "$f (symbol table)" "$a" "$b"
  else
    check "$f" "$(sha256sum "$E/build-atfe/variants/$f" | cut -d' ' -f1)" "$(sha256sum "$R/build-atfe/variants/$f" | cut -d' ' -f1)"
  fi
}

say "== 1. patched source trees (git diff + untracked file list, after overlay patches)"
for name in llvm-project-atfe lk; do
  ha=$(cd "$E/third_party/$name" && { git diff --full-index HEAD; git status --porcelain | sort; } | sha256sum | cut -d' ' -f1)
  hb=$(cd "$R/third_party/$name" && { git diff --full-index HEAD; git status --porcelain | sort; } | sha256sum | cut -d' ' -f1)
  check "third_party/$name" "$ha" "$hb"
done

build_in() { # tree
  cd "$1" || return 1
  unset VARIANTS_DIR LK_PROJECT BOLT_EXTRA_ARGS BOLT_FUNC BOLT_OUT_SUFFIX BOLT_REORDER_BLOCKS
  export BASE=atfe LK_MAKE_ARGS="STAIR_M=6 STAIR_X=3"
  mkdir -p build-atfe/pgo
  [[ "$1" == "$R" ]] && cp "$E/build-atfe/pgo/pgo.profdata" "$R/build-atfe/pgo/pgo.profdata"
  ./scripts/build-variants.sh baseline pgo_thinlto > "$LOG.build.$(basename "$1")" 2>&1 || say "BUILD FAILED in $1 (see $LOG.build.*)"
}
say "== 2. LK images built from the same source, flags and PGO profile"
sha_e=$(sha256sum "$E/build-atfe/pgo/pgo.profdata" | cut -c1-16); say "   pgo.profdata (input, copied to the fresh tree): $sha_e"
build_in "$E"; build_in "$R"
for v in baseline pgo_thinlto; do
  for ext in bin elf; do
    check_file "$v.$ext"
  done
done

instr_in() { # tree
  cd "$1" || return 1
  export BASE=atfe BOLT_FUNC=bolt_bench_stair_kernel BOLT_PROFILE_MODE=edges
  ./scripts/bolt-variant.sh instrument pgo_thinlto > "$LOG.instr.$(basename "$1")" 2>&1 || say "INSTRUMENT FAILED in $1"
}
say "== 3. BOLT edge-instrumented image"
instr_in "$E"; instr_in "$R"
for ext in bin elf; do
  check_file "pgo_thinlto.instr.$ext"
done

opt_in() { # tree
  cd "$1" || return 1
  export BASE=atfe BOLT_FUNC=bolt_bench_stair_kernel BOLT_PROFILE_MODE=edges
  ./scripts/bolt-variant.sh optimize pgo_thinlto "$COUNTERS" > "$LOG.opt.$(basename "$1")" 2>&1 || say "OPTIMIZE FAILED in $1"
}
say "== 4. BOLT output from the same counters (the profile collected on the Pi)"
opt_in "$E"; opt_in "$R"
for f in pgo_thinlto.fdata pgo_thinlto_bolt.elf.funcmap pgo_thinlto_bolt.bin pgo_thinlto_bolt.elf; do
  check_file "$f"
done
say ""
say "RESULT: $pass identical, $fail different"
[[ $fail -eq 0 ]]
