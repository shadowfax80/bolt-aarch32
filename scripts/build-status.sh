#!/usr/bin/env bash
# Report toolchain build progress. Run on the build machine.
#
#   ./scripts/build-status.sh          one-shot summary
#   ./scripts/build-status.sh -f       follow the live log
set -uo pipefail

LOG="${LOG:-/workspace/build-llvm.log}"
BUILD_DIR="${BUILD_DIR:-$(cd "$(dirname "$0")/.." && pwd)/build}"

if [[ "${1:-}" == "-f" || "${1:-}" == "--follow" ]]; then
  exec tail -f "$LOG"
fi

if [[ ! -f "$LOG" ]]; then
  echo "no log at $LOG"
  exit 1
fi

# Ninja writes "[done/total] description" per completed edge.
last="$(grep -oE '^\[[0-9]+/[0-9]+\]' "$LOG" | tail -1)"

if [[ -z "$last" ]]; then
  echo "stage:    configuring (no ninja progress lines yet)"
else
  done_n="${last%%/*}"; done_n="${done_n#[}"
  total_n="${last##*/}"; total_n="${total_n%]}"
  pct=$(( done_n * 100 / total_n ))
  # Rough bar; ninja edge counts are not uniform in cost, so treat as indicative.
  filled=$(( pct / 5 ))
  printf 'stage:    compiling\n'
  printf 'progress: %d/%d (%d%%) [%s%s]\n' "$done_n" "$total_n" "$pct" \
    "$(printf '#%.0s' $(seq 1 $filled 2>/dev/null))" \
    "$(printf '.%.0s' $(seq 1 $((20 - filled)) 2>/dev/null))"
fi

if pgrep -x ninja >/dev/null; then
  echo "ninja:    running (pid $(pgrep -x ninja | head -1))"
elif pgrep -f 'cmake -G' >/dev/null; then
  echo "ninja:    not started; cmake still configuring"
else
  echo "ninja:    not running"
fi

echo "errors:   $(grep -ciE '^(FAILED|ninja: build stopped)' "$LOG" || true)"
echo "objects:  $(find "$BUILD_DIR" -name '*.o' 2>/dev/null | wc -l)"
echo "disk:     $(du -sh "$BUILD_DIR" 2>/dev/null | cut -f1)"
echo
echo "last:     $(tail -1 "$LOG")"
