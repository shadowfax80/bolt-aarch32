# BOLT AArch32 Backend — design, implementation, and user guide

This document is the reference for the ARM/Thumb (AArch32) backend added to
LLVM BOLT in this repo. For the rung-by-rung upstreaming checklist and dated
verification log, see [aarch32-bolt.md](aarch32-bolt.md); this doc is the
"what it is and how to use it" complement to that plan.

Scope: BOLT itself gained no AArch32 target before this work —
`bolt/lib/Target/` shipped only AArch64, X86, and RISC-V. Everything below
is new.

---

## 1. Design principles

**Function-granularity ISA mode, not instruction-granularity.** ARM32 code
exists in one of two encodings — 32-bit-fixed ARM or 16/32-bit-variable
Thumb(-2) — selected by the CPU's CPSR T-bit and switched only via a
mode-changing branch (`BX`/`BLX`). A function commits to one mode for its
whole body; there is no per-instruction mixing (unlike, say, RISC-V's
compressed-instruction extension). The backend models this as a
`BinaryFunction`-level property (`isARMThumb()`/`setARMThumb()`), decided at
disassembly time from the entry symbol's LSB and `$a`/`$t` mapping symbols,
never re-derived mid-function.

**Two full `MCPlusBuilder` instances, selected per function, never mutated
in place.** This is the central architectural decision the backend is built
around. An earlier design temporarily mutated a single shared
`MCPlusBuilder`'s subtarget (`MIB->setSTI()`) to switch between ARM and
Thumb encoding, then restored it. That pattern is a `BinaryContext`-wide
data race: BOLT runs passes with `parallel::for_each`, so one thread mid-call
on a Thumb function could have its STI reset to ARM by another thread
finishing a call on an ARM function. The fix, now the backend's standing
rule, is `BinaryContext::getMIBFor(bool IsThumb)` — a second, fully separate
`MCPlusBuilder` (`ThumbMIB`) constructed once alongside the primary one, with
every call site selecting the right instance explicitly:

```cpp
MCPlusBuilder *MIB = BC.getMIBFor(BC.isARM() && Function.isARMThumb());
```

Any new pass touching ARM code must follow this pattern. A helper that is
shared, target-generic BOLT-core code (like the instrumentation
counter-snippet builder) cannot infer the right instance on its own — it
must be handed the caller's already-selected `MIB` explicitly. Forgetting
this is exactly the bug behind defect D6 below.

**Reuse the AArch64 bare-metal profiling path unchanged; only ARM32 probe
emission is new.** Phase 2 already solved "how does BOLT collect a profile
with no `perf`, no filesystem, no Linux syscalls" for AArch64 bare-metal LK:
counters in a fixed `.bolt.instr.counters` region, read out of the guest
over QMP, converted to `.fdata` on the host. That whole pipeline —
`dump-bolt-counters.py`, `ram-dump-to-fdata.py`, the `--no-lse-atomics` /
`--runtime-instrumentation-lib` flags — is architecture-agnostic and is
reused verbatim. AArch32 only had to add the *encoding* of ARM/Thumb counter
probes and its own cross-built runtime.

**Scoped instrumentation only — never LK kernel/boot code.** Every rung
instruments and rewrites only the synthetic `bolt_bench_*` workload
functions, never LK itself. This keeps the kernel's own boot/scheduler code
out of the blast radius of an experimental backend and makes every failure
attributable to the workload under test, not to host-OS code nobody
intended to touch.

**Two independent LLVM bases verified in parallel.** The overlay patch sets
are built and tested against both `llvm/llvm-project` (the actual
upstreaming target, pinned) and `arm/arm-toolchain`'s `arm-software` branch
(Arm's own continuously-synced integration branch), via `BASE=upstream|atfe`
(see `scripts/resolve-base.sh`). A fix is not considered done until it
passes on both — this has repeatedly caught base-specific illusions (a
"backend gap" that was really a stale patch, and vice versa) before they
were reported as ARM32 defects. See the "History: merged from a sibling
repo" section of [aarch32-bolt.md](aarch32-bolt.md) for how this dual-base
setup came about.

**Small, independently-gated rungs (P0–P11), each with a lit test and a
QEMU/LK check.** RISC-V (`bolt/lib/Target/RISCV/`) — the smallest existing
BOLT target — is the scaffolding reference. Nothing advances to the next
rung without both a passing FileCheck lit test (for eventual upstream
review) and a green boot on the actual bare-metal workload.

---

## 2. Major files and interfaces

### LLVM/BOLT-side patches (`overlay/llvm/patches/{upstream,atfe}/`)

| Patch | Files | What it adds |
|---|---|---|
| `0001-emit-bolt-instr-tables-on-elf.patch` | `RuntimeLibs/InstrumentationRuntimeLibrary.cpp` | Emits `.bolt.instr.tables` even when linking a custom (non-stock) runtime — needed since the bare-metal runtime isn't the stock `libbolt_rt_instr` |
| `0002-tolerate-secondary-entrypoint-outside-code-section.patch` | `Rewrite/RewriteInstance.cpp` | Bare-metal ELFs can have a secondary entry point outside `.text`; upstream assumed otherwise |
| `0003-bolt-arm-elf32-and-target.patch` | `bolt/CMakeLists.txt`, `Core/BinaryContext.{h,cpp}`, `Core/BinaryFunction.{h,cpp}`, `Core/BinaryBasicBlock.cpp`, `Core/BinaryEmitter.cpp`, `Core/BinarySection.cpp`, `Core/AddressMap.cpp` | ELF32 reader, `Triple::arm` acceptance, `BinaryContext::isARM()`, `BinaryFunction::isARMThumb()`/`setARMThumb()`, `getMIBFor()` + `ThumbMIB`, `$a`/`$t`/`$d` mapping-symbol dispatch |
| `0004-bolt-arm-mcplusbuilder.patch` | `Core/MCPlusBuilder.h`, `Target/ARM/ARMMCPlusBuilder.cpp`, `Target/ARM/ARMMCSymbolizer.{cpp,h}`, `Target/ARM/CMakeLists.txt` | The new ARM32 backend itself — `bolt/lib/Target/ARM/` (see interfaces below) |
| `0005-bolt-arm-relocations.patch` | `Core/Relocation.cpp` | ARM-family relocation classification: `isSupportedARM`, `isPCRelativeARM`, `canEncodeValueARM`, `encodeValueARM`, `extractValueARM`, `getSizeForTypeARM`, `skipRelocationTypeARM` |
| `0006-bolt-arm-rewrite-dispatch.patch` | `Rewrite/RewriteInstance.{h,cpp}`, `Rewrite/JITLinkLinker.cpp` | Arch dispatch through the rewrite pipeline (`createMCPlusBuilder()` factory, JITLink linker path for ARM) |
| `0007-bolt-arm-lit-tests.patch` | `bolt/test/ARM/*`, `bolt/test/Inputs/elf32-basic.yaml`, `bolt/test/elf32-basic.test` | The upstream-shaped lit test suite (10 `.test` files + fixtures) — see §Verification below |
| `0008-jitlink-arm-generic-archkind.patch` | `JITLink/aarch32.h`, `JITLink/ELF_aarch32.cpp`, `JITLink/aarch32.cpp`, `Target/ARM/MCTargetDesc/ARMELFObjectWriter.cpp` | New JITLink relocation kind `Thumb_LdrPcRel` (Thumb-32 `LDR Rt,[pc,#imm]` literal-pool load, `R_ARM_THM_PC12`); maps a generic `arm`/`thumb` triple (no explicit arch version) to `ARMV7A` instead of failing |
| `0009-bolt-arm-longjmp-veneers.patch` | `Passes/LongJmp.cpp`, `Passes/VeneerElimination.cpp`, `Rewrite/BinaryPassManager.cpp` | Out-of-range branch veneers and linker-inserted-veneer elimination, extended to ARM (previously AArch64/X86-only in places) |
| `0010-bolt-arm-instrumentation.patch` | `Passes/Instrumentation.{h,cpp}`, `Passes/BinaryPasses.cpp`, `RuntimeLibs/InstrumentationRuntimeLibrary.cpp` | Threads the caller's selected `MCPlusBuilder` into the shared, target-generic instrumentation-snippet builder instead of it reaching for `BC.MIB` directly (see D6 below) |

`overlay/lk/patches/0001-emit-relocs-for-bolt.patch` is the one LK-side
patch (`--emit-relocs` at link time, needed for BOLT's relocation-mode
rewrite; base-agnostic, applies to both AArch64 and AArch32 LK builds).

### Key new interfaces

```cpp
// BinaryContext.h
bool isARM() const;
MCPlusBuilder *getMIBFor(bool IsThumb) const;   // ThumbMIB or primary MIB
void initializeThumbTarget(std::unique_ptr<MCPlusBuilder>);

// BinaryFunction.h
bool isARMThumb() const;
void setARMThumb(bool V = true);
```

`bolt/lib/Target/ARM/ARMMCPlusBuilder.cpp` implements the standard
`MCPlusBuilder` surface for both ISA modes: `analyzeBranch`,
`createDirectBranch/Call`, `createUncondBranch`, `createLongJmp` /
`createLongTailCall` / `createLongUncondBranch` (veneer forms),
`createTailCall`, `convertJmpToTailCall`, `isIndirectBranch` /
`isIndirectCall`, `isReturn`, `isLiteralLoad`, `isThumbInst`/`isThumbMode`/
`InThumbMode`, `isITInstruction`/`isITOpcode`/`getITBlockSize` (IT-bundle
handling), `isSafeToEncodeARM`, `adjustCallForTargetMode` (rewrites
`BL`↔`BLX` after a veneer redirects a call across ISA modes),
`getFramePointer`/`getStackPointer`, `createStackPointerIncrement`/
`Decrement`, `loadReg`, plus the usual `createNoop`/`createTrap`/
`createBreakpoint`/`createReturn` family.

### Bare-metal side

- `overlay/llvm/bolt-rt-baremetal/` — `libbolt_rt_baremetal.a`, cross-built
  per architecture (`aarch64-none-elf` and, new for this backend,
  `arm-none-eabi`) by `scripts/build-bolt-rt-baremetal.sh`. Same symbol
  contract as the AArch64 stage-1 runtime (`__bolt_instr_start/fini/setup/
  clear_counters/data_dump`); ARM32's counter-increment path additionally
  has to avoid LSE atomics (`ldrex`/`strex` retry loop instead of `stadd`) —
  see §4.
- `overlay/lk/files/app/bolt_bench/` — the synthetic workload app
  (`bolt_bench.c`, `rules.mk`), 16 benchmarks covering every ARM32-specific
  code shape BOLT needs to handle (literal pools, far calls, IT blocks,
  direct/indirect/tail-call interworking, register pressure, hot/cold
  splitting, ICF-eligible duplicates — see §5's optimization-pass table for
  which of these actually exercise a working pass).
- `scripts/instrument-lk-bolt.sh`, `scripts/optimize-lk-bolt.sh` —
  base-aware (`BASE=upstream|atfe`) and arch-aware (`ARCH=arm32|aarch64`)
  drivers for the instrument→profile→optimize pipeline.
- `scripts/fix-kernel-elf-sections.py` — ELF32-safe post-processing after
  BOLT's rewrite: restores the sections BOLT's relocation-mode trampolines
  clobber (`.bolt.org.text`, `.data`, `.rodata`, `lk_init`, `commands`,
  `apps`, `fs_impl`, `.ctors`), and implements the **org.text counter-hook**
  mechanism — since BOLT's own instrumentation trampolines land in a region
  that smashes ARM32 literal pools, counter bumps are instead patched
  directly into unused space in the original hot `.text`, one small Thumb
  or ARM stub per hooked function (`patch_orgtext_counter_hook_thumb`/
  `_arm32`).
- `scripts/fix-kernel-elf-entry.py`, `scripts/fix-kernel-elf-paddr.py` —
  ELF32 entry-point and physical-address-skew fixups equivalent to the
  AArch64 ones, ported to 32-bit ELF fields.
- `scripts/dump-bolt-counters.py`, `scripts/ram-dump-to-fdata.py` — reused
  from AArch64 Phase 2 unmodified except for 32-bit virtual-address decode
  in the fdata converter.

---

## 3. Main aspects taken care of

**The `setSTI()` race → dual-`MCPlusBuilder` fix.** Covered in §1; the
concrete failure mode when this goes wrong is silent ISA-mode
mis-encoding under concurrent multi-function processing, not a clean crash
— the kind of bug that passes single-threaded testing and fails
intermittently once `parallel::for_each` is doing real work.

**Defect D6 — instrumentation snippet built with the wrong `MIB`.**
`instrumentFunction()` correctly selects the per-function builder via
`getMIBFor()`, but that selection was never threaded through to
`createInstrumentationSnippet()` — the shared, target-generic (X86/AArch64/
RISC-V/ARM) helper that actually emits the counter-bump sequence. Both call
sites (`instrumentLeafNode`, `instrumentOneTarget`) reached for `BC.MIB`
directly — always the ARM-mode instance — so every Thumb function's counter
snippet was materialized with ARM-mode encoding assumptions. Symptom:
`materializeAddress`'s `movw`/`movt` pair got built against the wrong
subtarget, JITLink applied the relocation at a fixup site that decoded as a
16-bit Thumb `B` instead of the expected 32-bit `MOVW`, and the instrumented
image failed with a JITLink error before ever booting. Fixed by giving
`createInstrumentationSnippet()` an explicit `MCPlusBuilder *` parameter.

**Defect: Thumb instruction-boundary split in the org.text counter hook**
(found and fixed 2026-09-16).
`patch_orgtext_counter_hook_thumb()` in `fix-kernel-elf-sections.py`
originally displaced a hardcoded 4 bytes from a Thumb function's entry into
its counter stub — correct only when those 4 bytes are a whole number of
instructions. Thumb-2 freely mixes 2- and 4-byte encodings; a function
starting with a 2-byte instruction followed by a 4-byte one had its second
instruction split in half, and the orphaned halfword decoded as garbage
against whatever followed it (in the observed case, an undefined
coprocessor access that faulted immediately at boot). Fixed by walking real
instruction boundaries and refusing to displace a PC-relative instruction
into a stub (which would silently compute against the wrong PC).

**IT-block atomicity.** `IT`/`ITT`/`ITE`/… headers plus their 1–4
predicated instructions must move, split, or get skipped as one unit —
never partially. `isPrefix(t2IT)` + `getITBlockSize()` (decoded from the
`IT` mask) identify the whole bundle; instrumentation hooks are only
inserted before an IT block, never inside one.

**ARM↔Thumb interworking correctness.** `BLX`, `BX rm`, `LDR pc,[...]`
with an odd/even LSB, and `POP {pc}` all potentially change ISA mode.
Veneers inserted for out-of-range branches must set the correct target
state (Thumb bit in the veneer's own branch target), and
`adjustCallForTargetMode` rewrites `BL`↔`BLX` when a veneer redirects a call
across the ARM/Thumb boundary. Full-image (unscoped) veneer rewriting still
has known trampoline-leftover issues outside the `bolt_bench_*` functions —
tracked as an open item, not a P8 gate.

**Literal-pool correctness under relocation-mode rewrite.** JITLink's new
`Thumb_LdrPcRel` fixup kind (patch 0008) is what makes Thumb `LDR Rt,
[pc, #imm]` constant-pool loads survive a rewrite; without it, JITLink had
no relocation entry to apply and the instrumented/rewritten binary's literal
loads pointed at stale addresses.

**Non-LSE atomic counters.** The QEMU `cortex-a15` model this backend has
been validated against has no Large System Extensions, so counter
increments use an `ldrex`/`strex` retry loop instead of `stadd`
(`--no-lse-atomics`, same flag AArch64 bare-metal already needed for
`cortex-a53`). See §5 for why this may not be the right default on real
ARMv8.2-A hardware.

**Cross-base verification discipline.** Every fix above was independently
re-tested against both `BASE=upstream` and `BASE=atfe` before being
considered closed — this caught, for example, that the two BOLT
optimize-pass gaps below (§5) are genuine ARM32-backend gaps and not
`arm-toolchain`-specific drift, since they reproduce identically on
upstream LLVM.

---

## 4. Differences from the AArch64 BOLT backend

| Aspect | AArch64 | AArch32 (this backend) |
|---|---|---|
| Instruction encoding | Single, fixed 4-byte | **Two** encodings (ARM 32-bit fixed, Thumb(-2) 16/32-bit variable), selected by a CPU mode bit, not inferable from the triple alone |
| `MCPlusBuilder` | One instance for the whole `BinaryContext` | **Two** full instances (`MIB`, `ThumbMIB`), selected per function via `getMIBFor()` — required specifically because a single mutable-subtarget instance is unsafe under BOLT's threaded pass model |
| Basic-block / hook displacement | Every instruction is 4 bytes — displacing N bytes is always a whole number of instructions | Must walk real instruction boundaries (2 vs 4 byte) before displacing bytes into a stub; getting this wrong produces exactly the boot-time undefined-instruction fault documented in §3 |
| ISA-mode switching | None — no equivalent concept | Explicit interworking (`BLX`/`BX`/veneers), each crossing requiring correct mode-bit handling; AArch64 has nothing analogous to "wrong mode" as a failure class |
| Predicated instruction bundles | None | `IT`/`ITT`/`ITE`… bundles (Thumb-2 only) must be treated as atomic, indivisible units |
| Branch range | ~128 MB reach (`B`/`BL` with 26-bit imm) | Much smaller: ARM `B`/`BL` ±32 MB, Thumb `BL`/`BLX` ±16 MB (T2) or less for short forms — veneers are needed far more often in practice |
| Mapping symbols | `$x` (code) / `$d` (data) — two-way | `$a` (ARM) / `$t` (Thumb) / `$d` (data) — **three-way**, and getting the disambiguation wrong (e.g. `llvm-nm`'s default output silently drops `$t`/`$d`, requiring `-a`/`--special-syms`) was a real bug found during this project's own tooling, not a hypothetical |
| JITLink backend maturity | Mature, upstream, no gaps hit by this project | Required adding a new relocation kind (`Thumb_LdrPcRel`) for literal pools, and still has an open gap: `R_ARM_THM_JUMP19` has no handler, which blocks `-split-functions` once `-reorder-blocks` actually widens a Thumb conditional branch to `B<cond>.W` |
| Optimization pass coverage | `-indirect-call-promotion`, `-reg-reassign`, `-frame-opt` all supported | These three are **hard-gated to X86/AArch64 only** in upstream BOLT (each errors immediately: `"... is supported only on X86 and AArch64"` / `"... is specific to X86"`), not merely untested on ARM |
| `-peepholes` / `-split-functions` | Fully supported alongside `-reorder-blocks` | Both run clean **in isolation** but break once a real profile makes `-reorder-blocks` actually move blocks — peepholes corrupts pseudo-instruction accounting on ARM-mode functions (`calculated pseudos 1, set pseudos 0`, then an assert), split-functions hits the `R_ARM_THM_JUMP19` gap above. Genuine backend gaps, confirmed on both LLVM bases, not environment artifacts |
| Instrumentation counter atomics | `stadd` (LSE) by default | `ldrex`/`strex` loop (`--no-lse-atomics`) — driven by the QEMU `cortex-a15` validation target's lack of LSE, not an ARM32 architectural requirement (see next section for real-hardware implications) |
| Register spill/reload in generated snippets | N/A (AArch64-specific encoding) | Needed its own operand-order fix specific to ARM's spill/reload encoding — a distinct bug class from anything AArch64 hit |
| Jump-table dispatch | Standard AArch64 indirect-branch forms | Thumb `TBB`/`TBH` (byte/halfword table branch) are Thumb-specific instructions with no AArch64 analogue; needed their own `isIndirectBranch` classification |
| Runtime library target triple | `aarch64-none-elf`, `-mgeneral-regs-only` | `arm-none-eabi`, same `-ffreestanding -mgeneral-regs-only` discipline (no FP/SIMD state assumed live — the runtime executes inside interrupt-like paths) |

---

## 5. User guide — BOLT workflow on bare-metal LK, Cortex-A55 target

This walks through instrumenting and optimizing an LK image the way this
project validates the AArch32 backend. Every step below has been run and
verified against **QEMU's `cortex-a15` model** (`-machine virt -cpu
cortex-a15`) on both LLVM bases. The final subsection calls out specifically
what changes for a real Cortex-A55-based SoC subsystem, since that target
has not itself been validated here.

### 5.1 Prerequisites

```bash
git clone https://github.com/shadowfax80/bolt-aarch32.git
cd bolt-aarch32
cp .env.example .env        # set NETWORK_VOLUME_ID if resuming a RunPod volume
./scripts/install-deps.sh   # ninja, ccache, lld, qemu-system-arm, etc.
```

Pick a base: `export BASE=upstream` (the actual upstreaming target,
`llvm/llvm-project` pinned) or `export BASE=atfe` (`arm/arm-toolchain`'s
`arm-software`, Arm's own integration branch). Everything below is
identical either way; `scripts/resolve-base.sh` is the single place that
maps `BASE` to a source tree, build dir, and patch set.

### 5.2 Build the toolchain

```bash
./scripts/fetch-sources.sh          # clone LLVM (pinned commit) + LK
./scripts/apply-overlays.sh         # apply overlay/llvm/patches/$BASE/*
./scripts/build-llvm-bolt.sh        # clang + lld + llvm-bolt, once
ARCH=arm32 ./scripts/build-bolt-rt-baremetal.sh   # cross-build the bare-metal runtime
```

### 5.3 Build the LK image under test

```bash
./scripts/build-lk-aarch32.sh
```

Default (no `BOLT_BENCH_ISA` set): the `bolt_bench` module compiles with
LK's global default, which is Thumb (`-mthumb`, `arch/arm/rules.mk`'s
`THUMBCFLAGS`) — a handful of functions are pinned to ARM via
`__attribute__((target("arm")))` to create interworking boundaries. This
is the shape most real embedded workloads want (Thumb's denser encoding
for code size and i-cache locality, ARM only where needed) and is what
every step below assumes. `BOLT_BENCH_ISA=arm` flips the default for just
that module (`overlay/lk/files/app/bolt_bench/rules.mk` adds `-marm`),
useful for exercising the ARM-mode-specific rewrite path (P4) in
isolation, not the primary target.

This produces `third_party/lk/build-qemu-virt-arm32-test/lk.elf` — a plain,
non-instrumented image. Sanity-check it boots before going further:

```bash
qemu-system-arm -machine virt -cpu cortex-a15 -m 512 -smp 1 -nographic \
  -kernel third_party/lk/build-qemu-virt-arm32-test/lk.elf \
  -append "lk.bolt_bench=all"
# expect: 16 "bolt_bench: ... done" lines, then "entering main console loop"
```

### 5.4 Instrument

```bash
export BASE=upstream ARCH=arm32   # or BASE=atfe
export INSTRUMENT_FUNCS="bolt_bench_hot_loop,bolt_bench_hot_cold,..."  # comma list
OUT="build-$BASE/lk.instr.arm32.elf" ./scripts/instrument-lk-bolt.sh
```

This runs `llvm-bolt -instrument --no-lse-atomics
--runtime-instrumentation-lib=libbolt_rt_baremetal.a`, then
`fix-kernel-elf-{paddr,entry,sections}.py` to restore the sections BOLT's
trampolines clobber and install the org.text counter hooks.

### 5.5 Collect a profile

No `perf`, no filesystem — the instrumented image runs under QEMU, the
workload executes, and the counter region is read straight out of guest
memory over QMP:

```bash
python3 scripts/dump-bolt-counters.py \
  --elf build-$BASE/lk.instr.arm32.elf \
  --out build-$BASE/bolt-counters-arm32.bin \
  --serial-log /tmp/counters-serial.log \
  --toolchain build-$BASE/bin \
  --qemu qemu-system-arm --machine virt --cpu cortex-a15 --smp 1 \
  --append "lk.bolt_bench=all" \
  --boot-timeout 60 --settle 4
```

Confirm every counter you expect actually incremented (`N/N counters
non-zero` in the output) before trusting the profile — a silent 1/32 here
is exactly the symptom that flagged the instruction-boundary bug in §3.

### 5.6 Convert to `.fdata`

```bash
python3 scripts/ram-dump-to-fdata.py \
  --elf build-$BASE/lk.instr.arm32.elf \
  --dump build-$BASE/bolt-counters-arm32.bin \
  --toolchain build-$BASE/bin \
  --funcs "$INSTRUMENT_FUNCS" \
  -o build-$BASE/prof-arm32.fdata
```

### 5.7 Optimize

```bash
BASE=$BASE ARCH=arm32 \
  ELF=third_party/lk/build-qemu-virt-arm32-test/lk.elf \
  FDATA=build-$BASE/prof-arm32.fdata \
  OUT=build-$BASE/lk.bolt.arm32.elf \
  ./scripts/optimize-lk-bolt.sh
```

The default pass set is `-reorder-blocks=ext-tsp -reorder-functions=hfsort+
-icf=all` — deliberately **not** the full X86/AArch64 pass list; see §4's
table for why `-indirect-call-promotion`/`-reg-reassign`/`-frame-opt` are
absent (hard-gated off-target) and why `-peepholes`/`-split-functions` are
currently excluded too (break in combination with real reordering).

### 5.8 Boot and verify the optimized image

```bash
qemu-system-arm -machine virt -cpu cortex-a15 -m 512 -smp 1 -nographic \
  -kernel build-$BASE/lk.bolt.arm32.elf -append "lk.bolt_bench=all"
```

Same pass criterion as 5.3 — all workloads complete, console reached. This
is a **functional** gate. Do not read cycle-count deltas from a QEMU run as
a performance result: QEMU's TCG models no instruction cache at all, and
i-cache/iTLB locality is precisely where BOLT's layout optimizations earn
their benefit. Meaningful before/after numbers require real hardware.

### 5.9 End-to-end in one script

`ARCH=arm32 ./scripts/verify-bolt-workloads.sh` runs 5.3–5.8 as one gate,
mirroring the equivalent AArch64 script.

### 5.10 Porting to a real Cortex-A55-based SoC subsystem

The workflow above is unchanged in shape on real hardware, but several
things this project has only exercised against QEMU's `cortex-a15` model
need to be revisited:

- **AArch32 state must actually be entered.** `cortex-a15` is an
  AArch32-only core, so QEMU never raises the question of *which*
  execution state LK boots into. Cortex-A55 is ARMv8.2-A and bi-modal —
  it supports AArch32 at EL0/EL1 (and EL2 in some configurations) but
  firmware must explicitly leave it in that state (e.g. `SCR_EL3.RW=0` if
  your boot path starts at EL3, or an equivalent decision in whatever ROM/
  first-stage bootloader hands off to LK). Confirm this is arranged by your
  platform's reset/boot code before any of the above applies — it is
  outside BOLT's and this repo's control.
- **LSE atomics are very likely available and worth evaluating.**
  `--no-lse-atomics` here is a concession to `cortex-a15` (ARMv7-A, no LSE),
  not an ARM32-architectural requirement. Cortex-A55 (ARMv8.2-A) supports
  LSE. The current `libbolt_rt_baremetal.a` ARM32 counter path has only
  been built and tested with the `ldrex`/`strex` retry loop — using `stadd`
  instead would need its own runtime variant and validation, but should be
  a strict win on real hardware (fewer instructions per counter bump, no
  retry-loop contention under multi-core).
- **Multi-core counter contention.** A55 SoC subsystems are typically
  multi-core (DynamIQ clusters of 2–8 A55s). If your profiled workload runs
  concurrently on more than one core, `ldrex`/`strex` (or `stadd`) exclusive
  monitors handle correctness, but expect more retry contention on shared
  counters than the single-core QEMU validation here ever exercised —
  budget profiling runs accordingly, and consider whether your workload
  should pin to one core for a first profiling pass.
- **Profile collection has no QMP equivalent.** `dump-bolt-counters.py`
  reads the counter region out of the guest over QEMU's QMP protocol — real
  hardware has no such channel. Stage 2 of the bare-metal runtime (see
  [aarch64-bare-metal.md](aarch64-bare-metal.md)'s "on-target serialization"
  section — reused unmodified here) is exactly the path designed for this:
  port `readDescriptions()`/`writeFunctionProfile()` and drain the
  `.bolt_profile` RAM region over UART (or JTAG memory read, or whatever
  debug-access path your subsystem exposes) instead of QMP. This stage was
  scaffolded for AArch64 bare-metal but not exercised end-to-end there
  either — treat it as the first real gap to close for hardware bring-up.
- **No self-modifying-code / icache-coherency concern at runtime.** BOLT
  rewrites the ELF **on the host**, between boots — the target never
  patches its own code in place, so there is no I-cache invalidation step
  needed on the target beyond whatever your platform already does on a
  normal fresh boot/reset. This only becomes a concern if you build
  something on top of this that patches code live in memory, which is out
  of scope for everything described here.
- **Branch-range and veneer behavior is unaffected by the core**, since it
  follows purely from the ARM/Thumb ISA encoding, not the microarchitecture
  — no changes expected there moving from `cortex-a15` to Cortex-A55.
- **Re-run the full lit suite (`overlay/llvm/patches/*/0007-bolt-arm-lit-tests.patch`)
  and this project's QEMU gates against whatever toolchain/BOLT build you
  use for the real target**, even if it is nominally the same LLVM pin —
  don't assume QEMU-`cortex-a15` green implies real-A55 green without
  re-verifying at least once.
