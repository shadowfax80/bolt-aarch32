#!/usr/bin/env bash
# List every function perf2bolt refuses in an image (beyond the fixed skip list).
cd /home/user/bolt-b1
ELF=$1; OUT=$2
SKIP=_start,arm_reset,arm_undefined,arm_swi,arm_prefetch_abort,arm_data_abort,arm_reserved,arm_irq,arm_fiq,platform_early_init,arch_early_init,bcopy,bzero
printf 'S 80008000 1\n' > /tmp/b1_probe.preagg
for i in $(seq 1 400); do
  out=$(build-atfe/bin/perf2bolt "$ELF" -nl -pa -p /tmp/b1_probe.preagg -o /tmp/b1_probe.fdata -skip-funcs="$SKIP" 2>&1 || true)
  line=$(grep -o "FATAL BOLT-ERROR: .*" <<<"$out" | head -1 || true)
  f=$(grep -o " in [^ ]*" <<<"$line" | head -1 | sed 's/ in \([^ (]*\).*/\1/' || true)
  [[ -z "$f" ]] && break
  echo "refused: $line"
  SKIP="$SKIP,$f"
done
echo "$SKIP" > "$OUT"
echo "skip list: $(tr , '\n' < "$OUT" | wc -l) functions"
