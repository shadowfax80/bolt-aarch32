# Pi instrumentation-state verification

> Reserve the Pi and shared build resources under [HANDOFF.md](../HANDOFF.md)
> before running commands. Hardware receipts below are dated and scoped;
> current status and later contract extensions belong to the handoff.

This fixture checks actual ATFE-generated ARM and Thumb leaf counter bodies on
Pi 4. The temporary firmware runs with MMU/caches off, a private aligned stack,
other cores parked by the serial loader and no active interrupt sources. It
watchdog-reboots into the resident loader after every result. It changes no SD
files and does not change the dirty WSL LK source.

Build in WSL with the existing assertions-enabled ATFE toolchain:

```sh
python3 scripts/pi4/build_counter_state.py --out out/correctness/counter-state-pi
```

The builder prints a fresh build directory. Run it from Windows with pyserial:

```powershell
& out/correctness/pi-venv/Scripts/python.exe scripts/pi4/verify_counter_state.py --build out/correctness/counter-state-pi/build-NAME --port auto
```

When Windows and WSL use separate checkouts, run the builder script from the
Windows checkout's `/mnt/c/...` path and point `--out` there too. The default
toolchain is `/home/user/bolt-aarch32/build-atfe/bin`; override `--toolchain`
when appropriate. Only an ATFE build with overlay 0026 is expected to pass.

Add `--return-pop` to check the standard single-register POP-to-PC forms decoded
as ARM LDR_POST_IMM and Thumb t2LDR_POST. This variant requires overlay 0030.
It uses generated `start-pop.s`/`reference-pop.s` files in the build directory,
and runs the same full register/CPSR/counter matrix and three fault images.
Both assertions-on/off Pi runs pass, with byte-identical payloads; see
[return/fallthrough evidence](../results/correctness_cfg_fallthrough_20261002.json).

Alternatively add `--flag-self-move` (requires overlay 0031) to include ARM MOVS
and Thumb MOVS.W self-moves in both leaf bodies. For the negative R0 sentinel,
the independent oracle expects N=1/Z=0 and unchanged C/V/Q/GE/control bits.
The variant adds a fourth `bad-flags` image that replaces MOVS with NOP and must
fail at the CPSR check. Both modes pass all 512 baseline/512 generated cases and
four fault images. See [self-move evidence](../results/correctness_self_move_flags_20261002.json).
The two variant options are mutually exclusive.

The independent assembly oracle must match both complete generated functions.
Original firmware code, data and entry are restored with exact section-size and
address checks. Two explicit, decoded redirects enter the generated bodies.
All ELF/raw section bytes and image hashes are checked before/after execution.
Each build and run retains a fresh evidence directory, including failures.

Each baseline and instrumented image runs 512 cases: two instruction modes,
32 NZCV/Q patterns, both IRQ-mask states and four counter seeds. The probe
captures all R0-R12, LR, SP and the entire CPSR immediately after returning.
GE takes all sixteen patterns; this does not exhaust all independent NZCV/GE
combinations. Each call must add exactly one to its own slot, including low-word
overflow and full uint64 wrap. Entry SP is eight-byte aligned; independent bytes
prove the generated sequence uses a sixteen-byte frame.

Three fault images deliberately remove carry, retain a masked IRQ or clobber R0.
They must fail at the specified case/field; a passing, missing or different failure
is rejected. The host parser also rejects incomplete, duplicate, malformed and
contradictory results. A successful run requires every payload to return to the
loader, preserving remote access for subsequent tests.

The 2026-10-02 Pi run passes both 512-case images in HYP mode on COM5 and catches
all three faults. Six parser tests pass. See
[recorded evidence](../results/correctness_counter_state_20261002.json).
This closes dedicated quiet single-core leaf state checks under item #5. It does
not certify active IRQ/FIQ handling, reentrancy, SMP, IT insertion, other stack
alignments or the enforced operating contract under #6. Whole item #5 stays open.
