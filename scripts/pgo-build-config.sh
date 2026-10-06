#!/usr/bin/env bash
# Sourced before source installation or compilation; fills PGO_MAKE_ARGS.
PGO_MAKE_ARGS=()
BOLT_PGO_KIND="${BOLT_PGO_KIND:-frontend}"
case "$BOLT_PGO_KIND" in frontend|ir) ;; *) echo 'error: BOLT_PGO_KIND must be frontend or ir' >&2; exit 1 ;; esac
collect=false
if [[ "${WITH_BOLT_CSPGO:-}" == true ]]; then
  if [[ "$BOLT_PGO_KIND" != ir || "${WITH_BOLT_THINLTO:-}" != true || -z "${WITH_BOLT_PGO_USE:-}" || "${WITH_BOLT_PGO:-}" == true ]]; then
    echo 'error: CS collection requires IR profile use + ThinLTO, without ordinary collection' >&2
    exit 1
  fi
  collect=true
  PGO_MAKE_ARGS+=(WITH_BOLT_CSPGO=true)
elif [[ "${WITH_BOLT_PGO:-}" == true ]]; then
  if [[ -n "${WITH_BOLT_PGO_USE:-}" ]]; then
    echo 'error: ordinary profile collection and use are mutually exclusive' >&2
    exit 1
  fi
  collect=true
  PGO_MAKE_ARGS+=(WITH_BOLT_PGO=true)
fi
PGO_MAKE_ARGS+=("BOLT_PGO_KIND=$BOLT_PGO_KIND")
if [[ -n "${WITH_BOLT_PGO_USE:-}" ]]; then
  if [[ ! -f "$WITH_BOLT_PGO_USE" ]]; then
    echo "error: profile $WITH_BOLT_PGO_USE not found" >&2; exit 1
  fi
  python3 "$ROOT/scripts/pgo_profile.py" validate "$WITH_BOLT_PGO_USE" \
    --kind "$BOLT_PGO_KIND" --profdata "$CLANG_BINDIR/llvm-profdata"
  PGO_MAKE_ARGS+=("WITH_BOLT_PGO_USE=$WITH_BOLT_PGO_USE")
fi
if [[ "$collect" == true ]]; then
  PGO_RT_LIB="${PGO_RT_LIB:-$ROOT/build-${BASE:-upstream}/pgo-rt-baremetal-arm/libpgo_rt_baremetal.a}"
  if [[ ! -f "$PGO_RT_LIB" ]]; then
    echo "error: $PGO_RT_LIB not found -- run scripts/build-pgo-rt-baremetal.sh first" >&2; exit 1
  fi
  PGO_MAKE_ARGS+=("EXTRA_OBJS=$PGO_RT_LIB")
fi
if [[ -n "${BOLT_PGO_BUFFER_SIZE:-}" ]]; then
  if [[ ! "$BOLT_PGO_BUFFER_SIZE" =~ ^[1-9][0-9]*$ ]] || (( BOLT_PGO_BUFFER_SIZE < 64 || BOLT_PGO_BUFFER_SIZE > 16777216 )); then
    echo 'error: BOLT_PGO_BUFFER_SIZE must be 64..16777216 bytes' >&2; exit 1
  fi
  PGO_MAKE_ARGS+=("BOLT_PGO_BUFFER_SIZE=$BOLT_PGO_BUFFER_SIZE")
fi
