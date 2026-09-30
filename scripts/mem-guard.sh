#!/usr/bin/env bash
# Keep a long WSL build from starving Windows. Run from Windows Git Bash while a build runs.
#
#   scripts/mem-guard.sh [drop_below_GB=3.5] [freeze_below_GB=1.5] [thaw_above_GB=2.5]
#
# Every 15 s it reads the free physical RAM of *Windows* (the WSL VM is capped by
# .wslconfig, but Windows itself and the tools running on it are what run out). What eats it
# during a build is mostly WSL's PAGE CACHE (file data from clones, object files): it grows
# to the VM cap and Windows cannot take it back on its own (measured: VM 6.4 GB while WSL
# itself used 0.7 GB). So:
#   free < drop     -> drop WSL's page cache (sync; drop_caches; the VM shrinks, Windows
#                      gets the memory back within seconds)
#   still < freeze  -> SIGSTOP the compiler/linker processes in WSL (last resort)
#   free > thaw     -> SIGCONT them
# Prints one line per action, so a monitor can show it.
set -uo pipefail
DROP="${1:-3.5}"; FREEZE="${2:-1.5}"; THAW="${3:-2.5}"
export MSYS_NO_PATHCONV=1
state=running
free_gb() {
  powershell -NoProfile -Command '[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)' | tr -d '\r'
}
sig() { wsl.exe -d Ubuntu -- bash -c "pkill -$1 -x cc1plus; pkill -$1 -x clang; pkill -$1 -x clang++; pkill -$1 -x ld.lld; pkill -$1 -x ninja; pkill -$1 -x ld64.lld; true" >/dev/null 2>&1; }
dropc() { wsl.exe -d Ubuntu -u root -- bash -c 'sync; echo 3 > /proc/sys/vm/drop_caches' >/dev/null 2>&1; }
echo "$(date +%H:%M:%S) mem-guard up: drop cache below ${DROP} GB free, freeze below ${FREEZE}, thaw above ${THAW} (now $(free_gb) GB)"
while true; do
  f="$(free_gb)"
  if awk "BEGIN{exit !($f < $DROP)}"; then
    dropc; sleep 8; f2="$(free_gb)"
    echo "$(date +%H:%M:%S) dropped WSL page cache: Windows free ${f} -> ${f2} GB"
    f="$f2"
  fi
  if [[ "$state" == running ]] && awk "BEGIN{exit !($f < $FREEZE)}"; then
    sig STOP; state=frozen
    echo "$(date +%H:%M:%S) FROZEN build: Windows free RAM ${f} GB"
  elif [[ "$state" == frozen ]] && awk "BEGIN{exit !($f > $THAW)}"; then
    sig CONT; state=running
    echo "$(date +%H:%M:%S) resumed build: Windows free RAM ${f} GB"
  fi
  sleep 15
done
