# Draft `pi4` oracle contract for the full LK image (6b) — needs user review

Status: **draft, not active.** Nothing is added to
`scripts/qemu_bench_oracle.py` `CONTRACTS` until the user approves it.

## What the contract binds

| Field | Value |
|---|---|
| Input ELF | `out/correctness/lk-oracles/build-rpi4-bolt-test/lk.elf` |
| Input sha256 | `424606a869c34b5be5f3c97f66a9cec8ea16844ac788c14c77839edcfef2459b` |
| Platform | `pi4` (Raspberry Pi 4B, Non-secure SVC, one core measured) |
| `bolt_bench.c` sha256 (LF) | `a48247945d47b359c04f40883361b72c1be87a4a7983aecc299d7c121d0d96d0` |
| `composite.c` sha256 (LF) | `8d830b9ca2a3884270f81cc3b00811f16d6744d5ac838d754664e2ec0ea12adb` |
| `rules.mk` sha256 (LF) | `c34149eda9808d114cdc8da415a0863ed5de2d2effa3de3c133ed385d3b5a38e` |
| Configuration | LK project `rpi4-bolt-test` (target `rpi4`, `ARM_CPU_CORTEX_A15`, Thumb-2 kernel); bolt_bench module `-marm`; `WITH_BOLT_PGO` off; `STAIR_M=10`, `STAIR_X=0`, input variant 0; 0 FP/NEON instructions (`scripts/check-no-fpu.sh`) |

Source hashes are over LF-normalized text. The build copy has CRLF line
endings; its content equals `overlay/lk/files/app/bolt_bench/` at `main`.

## Why the expected values are independent

`reference_results()` in `scripts/qemu_bench_oracle.py` computes all 18 sink
values from the reviewed arithmetic of these sources. It is the same model
approved for the QEMU fixture (`e13fa5f4…`), which uses the same benchmark
source operations. No value is learned from Pi output.

Consistency evidence, not the basis of the values: 7 Pi runs of this input
today (baseline and BOLT candidates, 1–3 repetitions each) all printed 18/18
values equal to `reference_results()`.

## What the reviewer is asked to confirm

1. These sources and this configuration are the ones to certify against.
2. `reference_results()` describes this build's workloads. In particular,
   `it_cond` is built `-marm` here, while the QEMU fixture defined
   `__thumb__`; the Pi values still match the model.
3. The contract may be added as `CONTRACTS['424606a8…'] = {platform: 'pi4', …}`.

Once approved, `scripts/pi4/full_image_verify.py` can certify full-image Pi
runs (item 6a).
