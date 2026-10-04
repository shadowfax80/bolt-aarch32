# Secure-SVC armstub for the Pi 4 (T3)

Makes the Pi PoC run LK in **Secure SVC**, like the target (Cortex-A55,
Secure, always SVC, no FPU/NEON, PMU sampling on IRQ).

Raspberry Pi's stock 32-bit stub (`armstub7.S`, built as
`armstub8-32-gic.bin`) switches every core to **Non-secure HYP** before the
kernel runs; LK then drops HYP→SVC. `armstub7-secure.S` is that stub with
three changes (each marked `SECURE`):

- no switch to Non-secure: the kernel is entered in Secure SVC;
- all interrupts stay in GIC Group 0, signalled as IRQ (`FIQEn=0`). LK's GIC
  driver writes `GICD_CTLR=1`/`GICC_CTLR=1`, which in the Secure view enable
  Group 0, so no LK GIC change is needed;
- `CNTVOFF` is zeroed from Monitor mode with `SCR.NS` set briefly (Secure
  state has no HYP mode to do it).

Everything after the stub already handles an SVC entry: the SD chainloader,
the fast loader (`tools/pi4-serialboot-fast/start.S` checks for HYP) and LK
(`arch/arm/arm/start.S` drops HYP→SVC only when entered in HYP).

## Build

```sh
bash tools/pi4-armstub-secure/build.sh      # in WSL; prints the .bin sha256
```

Output: `tools/pi4-armstub-secure/out/armstub8-32-gic-secure.bin` (256 bytes,
magic `0x5afe570b` at 0xf0 as upstream, 0 FP/NEON).

## Install (SD card, done by the user)

1. Power the Pi off; put the SD card in the PC.
2. Copy `armstub8-32-gic-secure.bin` to the boot partition (FAT, next to
   `config.txt`).
3. In `config.txt` add (keep everything else unchanged):

   ```
   armstub=armstub8-32-gic-secure.bin
   ```

4. Put the card back, power on, and run the usual `pi4_run.py` flow.

## Rollback

If the Pi does not reach the chainloader/LK banner: power off, card into the
PC, delete (or comment with `#`) the `armstub=` line, power on. Nothing else
on the card is touched.

## Verification after install

LK must report it runs in Secure state (planned boot-time check: entry mode
plus a Secure-only register read), then the certified gates are re-run in
Secure SVC: `full_image_verify.py`, `smp_verify.py`, bolt_edge.
