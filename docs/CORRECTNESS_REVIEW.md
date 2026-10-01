# ATFE correctness review — 2026-10-01

## Assessment

The project implements an experimental AArch32 ARM/Thumb BOLT backend as overlays
on a pinned ATFE tree. Little Kernel provides the bare-metal execution harness;
host tools extract RAM counters and feed profiles back into BOLT. The Pi pipeline
can execute selected rewritten benchmarks, but this does not establish general
ELF rewriting or full-kernel correctness.

The original 12-item tracker remains useful: **#2, #8 and #10 are complete within
their documented boundaries; the other nine remain open.** The review found
additional defects within #4/#5/#9/#12. The actionable list and closure criteria
are [CORRECTNESS_TODO.md](CORRECTNESS_TODO.md). No backend fix was made in this review.

## Reviewed state and evidence

- Windows overlay repository: `29debf1`, patches ATFE `0001`–`0019`.
- WSL source: `/home/user/bolt-aarch32/third_party/llvm-project-atfe`, base
  `bcc08884995ff3cbee70749524621803b9bd258a`, with existing uncommitted overlays.
- WSL parent checkout reports `eab1e71` plus local changes; it is not a clean
  checkout of the Windows revision. The version banner reports the LLVM base,
  not the overlay digest. A clean replay remains required under #12.
- Existing `build-atfe/bin/llvm-bolt`: LLVM 24.0.0git, optimized with assertions.
- Source inspection covered the ARM builder, core relocations/CFG/emitter,
  rewrite and JITLink paths, instrumentation, runtime, ELF postprocessing,
  redirection, dump conversion, verification, synchronization and patch application.
- Fresh host run: **BOLT ARM 16/16 + JITLink AArch32 14/14 = 30/30 passed**.
  Lit warned about missing optional `psutil`; no tests in these two suites were skipped.
- Failure-propagation fixtures passed: failed child gates remain failures and
  mismatched/missing Pi checksums return nonzero. Serial observations in those
  tests are mocked; they are not new hardware results.
- New small repros below ran against the live ATFE executable. This review did
  not rerun Pi workloads, the full QEMU gates, an assertions-disabled build, or a
  clean ATFE build. Previous hardware evidence is in [CORRECTNESS_FIXES.md](CORRECTNESS_FIXES.md).
- Upstream sources/builds were not modified or tested.

## Confirmed findings

### R1 — CBZ/CBNZ expansion changes live flags (#4, P0)

`ARMMCPlusBuilder::prepareForEmission()` replaces every symbolized CBZ/CBNZ with
`tCMPi8` and `t2Bcc`, without checking flag liveness. The review fixture emitted:

```asm
; original
cmp r1, #0
cbz r0, target
bne wrong

; rewritten
cmp r1, #0
cmp r0, #0
beq.w target
bne wrong
```

The extra CMP is observed in emitted bytes, decoded separately because the output
mapping symbols are defective (R3). For input `r1=0, r0=1`, instruction semantics
imply return 7 originally and return 3 after rewriting. That result difference
is a semantic deduction from the bytes, **not a measured Pi result**. Arm documents
that CBZ/CBNZ preserve condition flags in its [assembler reference](https://documentation-service.arm.com/static/5ea689299931941038ded38c).
Fix the expansion or gate it on proven dead flags, and execute both paths on Pi.

### R2 — valid Thumb ELF entry aborts (#9, P0)

The Thumb-entry variant assembled and linked successfully, then llvm-bolt exited
with SIGABRT at `RewriteInstance::patchELFSectionHeaderTable()`:

```text
Assertion `(NewEhdr.e_entry || !Obj.getHeader().e_entry) &&
"cannot find new address for entry point"' failed.
```

The function passes raw `e_entry` to `getNewFunctionAddress()` before asserting.
Audit Thumb-bit normalization/restoration and assertions-disabled behavior; do not
merely suppress the assertion. Converting the fixture entry to ARM allowed rewrite
to complete, isolating this failure from R1.

### R3 — odd mapping symbol and missing moved function symbol (#9)

The ARM-entry fixture's function map contains:

```text
_start 10000 22000 8
probe 10008 22008 1e
```

The output symbol table has `$t` at **0x22009**, size 30, while code begins at
**0x22008**. The moved `probe` function symbol is absent. Ordinary disassembly
therefore starts Thumb decoding one byte late. This is observed output, not only
an inherited report. The [Arm ELF ABI mapping-symbol rules](https://github.com/ARM-software/abi-aa/blob/main/aaelf32/aaelf32.rst#mapping-symbols)
distinguish code/data mapping addresses from Thumb function state bits.

### R4 — incomplete dump silently supplies zero counters (#12, P0)

`scripts/ram-dump-to-fdata.py::load_counters()` slices bytes without validating
the declared count or available range. A 16-byte blob containing count=2, four
padding bytes and a single 64-bit value 7 is accepted as **`[7, 0]`**. Python's
`int.from_bytes(b'', 'little')` yields zero, hiding the missing second counter.
UART chunk validation is useful but does not make the standalone converter safe
for truncated, misplaced or stale input. Validate before producing fdata.

### R5 — ARM counter increment does not carry to the high word (#5, P0)

Source-confirmed: `createInstrIncMemory()` loads R1 from offset 0, adds one, and
stores R1 back at offset 0. Instrumentation reserves 8-byte counters; the runtime
uses `uint64_t`, and the converter reads 8 bytes. No high-word update is present.
Consequently repeated increments wrap the low word; the overflow consequence is
inferred from the sequence, not a new hardware observation. A seeded carry test
is required. #8's ELF data-width fix does not address this separate issue.

### R6 — unsupported instrumentation can appear available (#6, P0)

`createInstrumentedIndirectCall()` ignores the handler and site ID and returns
the original call. The bare-metal indirect handlers immediately return. Current
wrappers disable call instrumentation, but backend admission must reject unsupported
requests. The counter sequence saves CPSR, masks IRQ, increments and restores
the control field. It assumes privileged single-core operation and does not mask
FIQ or provide multicore atomicity. Older comments claiming LDREX/STREX are stale.

### R7 — relocation declarations disagree (#1, P0)

Extracted from `isSupportedARM()` and `getJITLinkEdgeKind()` in the live source:

| Declaration set | Types beyond the common set |
|---|---|
| Core only (5) | ALU_PC_G0, PC24, PLT32, TARGET2, V4BX |
| JITLink only (5) | GOT_PREL, LDR_PC_G0, THM_MOVT_PREL, THM_MOVW_PREL_NC, THM_PC12 |
| Common (13) | NONE, ABS32, REL32, CALL, JUMP24, PREL31, TARGET1, MOVW_ABS_NC, MOVT_ABS, THM_CALL, THM_JUMP24, THM_MOVW_ABS_NC, THM_MOVT_ABS |

All names carry the `R_ARM_` prefix. Intentional no-op relocations need separate
classification; a set difference alone is not proof that each row is broken.
`createRelocation()` also maps narrow Thumb branches and `fixup_t2_condbranch`
to THM_JUMP24. THM_JUMP19 is absent from both sets. The recently fixed LDR path
does not establish complete input-to-output relocation support.

### R8 — debug/release CFG behavior differs (#3, P0)

`BinaryBasicBlock::getNumPseudos()` checks/recomputes ARM pseudo counts and marks
functions ignored only inside `#ifndef NDEBUG`. The unchecked build retains the
cached value. `postProcessBranches()` also warns and ignores invalid ARM CFGs.
Fix the mutations and safe fallback, then test both build modes. Current passing
tests use assertions and cannot close this item.

### R9 — test success can overstate transformed-code coverage (#11/#12)

`fix-kernel-elf-sections.py` restores original text/data. The Pi staging path adds
explicit redirection, but `verify-bolt-workloads.sh` calls the generic optimizer
and checks console messages without invoking `redirect-bolt-entries.py`. Its boot
success alone cannot prove selected rewritten functions ran. Hook installation
also has warning-only skips and scratch-space assumptions requiring bounds checks.

The earlier seven-function Pi comparisons are useful, but memcpy/interwork do not
update the shared sink: matching those dumps is not an independent output oracle.
Report selected/emitted/redirected/executed functions separately and checksum actual
results. Do not present historical 7% full-image coverage as a current measurement.

### R10 — source/build provenance needs a stronger gate (#12)

ATFE applies file-slice patches and records filenames in `.applied-overlay-patches`.
A matching name does not detect a changed patch body. The dirty WSL parent/source
trees make base hashes alone insufficient. Also, `wsl-setup.sh sync` uses
`rsync --delete` without excluding `.git` or `out`; review that before syncing over
the recovered workspace. These are source-confirmed risks, not a claim that files
were lost in this review. Use an isolated clean replay and digest manifest.

## Reproduce the instruction/ELF findings

Fixtures are in [correctness-review](../scripts/tests/Inputs/correctness-review/).
Run from the Windows checkout mounted in WSL, pointing `TC` at the existing ATFE
tools. Use an ignored output directory; no backend edit is required.

```bash
TC=/home/user/bolt-aarch32/build-atfe/bin
F=scripts/tests/Inputs/correctness-review
mkdir -p out/correctness/repro
$TC/llvm-mc -triple=thumbv7-none-eabi -filetype=obj "$F/cbz-flags.s" -o out/correctness/repro/probe.o
$TC/ld.lld --emit-relocs -T "$F/probe.ld" out/correctness/repro/probe.o -o out/correctness/repro/probe.elf
$TC/llvm-bolt out/correctness/repro/probe.elf -o out/correctness/repro/probe.bolt --no-huge-pages --emit-function-map=out/correctness/repro/probe.funcmap
$TC/llvm-readelf -s out/correctness/repro/probe.bolt
```

For R2, assemble with `-defsym THUMB_ENTRY=1` and repeat link/rewrite. This currently
aborts; it is a repro, not a passing regression. For R1, extract the rewritten
`probe` bytes using the function map and decode them with `llvm-mc --disassemble
--triple=thumbv7-none-eabi`; ordinary objdump is affected by R3. The entry wrapper
is only an ELF rewriting fixture, not a bootable hardware harness.

The review's local source snapshot, commands, disassembly and logs are under
`out/correctness/review-source/` and `out/correctness/review-evidence/` (ignored).
Before closing each bug, turn its repro into a maintained failing-then-passing
regression and add the required execution evidence.
