# pi4-serialboot-fast: chainloader with a 3 Mbaud upload mode

Derived from lk-perf's `experiments/pi4-serialboot` (commit `b40f57e`, kept as `main.c.orig`;
`patch_main.py` regenerates `main.c` from it). The Pi's chainloader accepted images at a fixed
115200 baud (~11 KiB/s: a 416 KB image took 38 s). This variant adds **`LKB3`**: the handshake
and every reply stay at 115200, only the payload goes at 3,000,000 baud (48 MHz UART clock,
divisor 1/0, exact). The old `LKBT` path is unchanged, so it is a drop-in replacement.

Why the receive loop is different: the loader runs with both caches off, and a bitwise CRC per
byte cannot keep up with a byte every 3.3 us. The fast path stores bytes with no per-byte work,
records UART overrun/framing flags, and CRCs from memory afterwards with a lookup table.

## Two ways to use it
1. **Hot-load, no SD-card change (used for all measurements):** `pi4_run.py --fast-loader
   tools/pi4-serialboot-fast/kernel7l_fast.img ...` (or `PI4_FAST_LOADER=<that file>` for every
   script). It is uploaded as a payload through the SD card's chainloader (both start at 0x8000
   in the same state), then the real payload goes at 3 Mbaud. Costs ~1 s per boot.
2. **Install it on the SD card** as `kernel7l.img` (keep the old one as a rollback), then use
   `pi4_run.py --fast`. Not needed for speed; only saves the 1 s hot-load.

## Verification (2026-09-30)
- `qemu_test.py` (raspi2b, protocol only): fast and slow uploads, a flipped bit and a truncated
  upload both give `ER` and the loader recovers, 5/5.
- `hw_test.py` (real Pi 4B, Non-secure SVC, hot-loaded): 51/51 back-to-back cycles correct
  (soft reset, hot-load, fast upload of a 182-416 KB image, boot, run, result checksum checked),
  0 fallbacks to the slow path; whole cycle 12-13 s for any image size.
- No FPU/NEON: built with `-mfpu=none` and checked by `scripts/check-no-fpu.sh`.

Build (in WSL): `tools/pi4-serialboot-fast/build.sh`.
