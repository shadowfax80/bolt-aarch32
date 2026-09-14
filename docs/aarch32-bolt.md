# AArch32 BOLT — plan (P0–P11)

**Goal:** add an ARM/Thumb backend to LLVM BOLT, prove it on bare-metal LK in QEMU, and land it in llvm-project `main` as a series of small, reviewable PRs.

**Authoritative checklist:** [PROJECT_PLAN.md](PROJECT_PLAN.md) Phase 3 table.

---

## Principles

| Rule | Why |
|------|-----|
| **One upstream PR per rung (P1–P10)** | Small reviews; each PR has lit tests and a clear pass gate |
| **Develop on the volume, stage in overlay** | Backend code lives in `third_party/llvm-project/` on the pod; export to `overlay/llvm/patches/` until merged |
| **Lit in llvm-project; LK in this repo** | Upstream tests are `.s` snippets; QEMU/`bolt_bench` verification stays here |
| **LK is host only** | Never instrument LK kernel/boot code — only synthetic `bolt_bench_*` workloads |
| **Rebase to `main` before P1** | Phase 1–2 used `release/23.x`; upstream reviews target `main` |
| **Delete overlay patch when merged** | Overlay repo shrinks as slices land upstream |

**Phase 2 reuse (do not redo):** counters in `.bolt.instr.counters`, host reads via **QMP** (`dump-bolt-counters.py`), `ram-dump-to-fdata.py` → `.fdata`, `llvm-bolt -data=` optimizes.

**What Phase 3 must invent:** BOLT has no AArch32 target. `bolt/lib/Target/` is AArch64, X86, RISC-V only. `LLVM_TARGETS_TO_BUILD=…;ARM` gives clang/lld ARM32 support, **not** a BOLT backend.

---

## Master status (P0–P11)

| Rung | Focus | Upstream PR (draft title) | Lit | QEMU / LK | Status |
|------|-------|---------------------------|-----|-------------|--------|
| **P0** | ARM32 harness (no BOLT backend) | — (this repo only) | — | `verify-bolt-arm32-harness.sh` | **Done** |
| **P1** | ELF32 reader | `[BOLT][ARM] Add ELF32 support for ARM executables` | Parse ARM32 ET_EXEC | `--print-sections` on `lk.elf` lists `.text` | **Done** — full-image exit 0 |
| **P2** | ARM-mode disassembly | `[BOLT][ARM] Disassemble ARM-mode functions` | FileCheck on ARM `.s` | ARM `hot_loop` bytes match objdump | **Done** — `0004`; lit + QEMU CFG |
| **P3** | CFG (ARM only) | `[BOLT][ARM] Build CFG for ARM-mode code` | `--print-cfg` FileCheck | CFG on ARM `hot_loop`/`hot_cold`/`branch_chain` | **Done** — `0004`; lit + benches |
| **P4** | Identity rewrite | `[BOLT][ARM] Identity rewrite for ARM-mode binaries` | Rewritten lit ELF runs | Rewritten `lk.elf` boots + `bolt_bench all` | **Done** — `BOLT_BENCH_ISA=arm`, 4 funcs overwritten, QEMU green |
| **P5** | Branch range / veneers | `[BOLT][ARM] Insert veneers for out-of-range branches` | Far `bl` lit test | `verify-bolt-arm32-veneer.sh` | **Done** — stub in ELF + `qemu-arm` exit 42 |
| **P6** | Thumb-2 (no IT) | `[BOLT][ARM] Thumb-2 disassembly, CFG, and rewrite` | Thumb `.s` CFG + rewrite | `-mthumb` `bolt_bench` identity rewrite boots | **Done** — lit 8/8; QEMU `hot_loop` + console |
| **P7** | IT blocks | `[BOLT][ARM] Treat IT bundles as atomic units` | IT bundle not split | `it_cond` identity rewrite correct | **Done** — lit 9/9; QEMU `it_cond` + `all` |
| **P8** | ARM↔Thumb interworking | `[BOLT][ARM] Interworking edges and veneers` | ARM↔Thumb CFG lit | `interwork` identity rewrite runs | **Done** — lit 10/10; QEMU `interwork` + narrow `all` |
| **P9** | Instrumentation + RAM profile | `[BOLT][ARM] Instrumentation for ARM/Thumb` | Counter-site FileCheck | `verify-bolt-workloads.sh` ARM32: all counters + `.fdata` | **Done** — 5/5 counters + named `.fdata` (2026-09-14) |
| **P10** | Layout optimize | `[BOLT][ARM] Profile-guided layout on ARM/Thumb` | Optimize lit + fake `.fdata` | `lk.bolt.elf` boots, reruns `all`, cycles logged | Pending |
| **P11** | Upstream landing | Track/rebase/merge; overlay cleanup | All lit in tree | Full ARM32 pipeline green on `main` | Pending |

**RFC:** post on [LLVM Discourse (BOLT)](https://discourse.llvm.org/c/subprojects/bolt/) **before opening P4** — `MCPlusBuilder` API shape is shared infrastructure.

---

## Complexity ladder

Each rung is independently testable. Do not start the next until the previous has **lit tests and a QEMU check** (P0 is harness-only).

```text
P0  Harness (no BOLT backend)          ✓ Done
P1  Read ELF32                         ✓ Done (full-image --print-sections)
P2  Disassemble ARM-mode only          ✓ Done (lit + benches)
P3  Build CFG (ARM)                    ✓ Done (lit + benches)
P4  Identity rewrite (MCPlusBuilder)   ✓ Done (ARM-mode benches)

P5  Branch range / veneers             ✓ Done (stub in ELF + qemu 42)
P6  Thumb-2, no IT
P7  IT blocks
P8  ARM↔Thumb interworking             ✓ Done (lit 10/10; QEMU interwork)
P9  Instrumentation + RAM profile
P10 Layout optimize
P11 Upstream landing (merge tracking, overlay cleanup)
```

---

## Where code lives

### Volume (persistent workspace)

```
/workspace/bolt-lk-overlay/third_party/llvm-project/   ← branch + implement here
/workspace/bolt-lk-overlay/build/                      ← rebuilt llvm-bolt after each slice
/workspace/bolt-lk-overlay/third_party/lk/               ← ARM32/AArch64 harness builds
```

Verify layout: `./scripts/verify-workspace.sh`

### Overlay repo (GitHub)

```
overlay/llvm/patches/
  0003-bolt-arm-elf32-and-target.patch   ← P1
  0004-bolt-arm-mcplusbuilder.patch      ← P2–P6 (ARMMCPlusBuilder)
  0005-bolt-arm-relocations.patch        ← P4 relocations
  0006-bolt-arm-rewrite-dispatch.patch   ← RewriteInstance ARM dispatch
  0007-bolt-arm-lit-tests.patch          ← bolt/test/ARM/
  0008-jitlink-arm-generic-archkind.patch ← JITLink generic `arm` → ARMv7-A
overlay/llvm/tests/       ← legacy placeholder; lit tests now in 0007
overlay/lk/files/app/bolt_bench/   ← synthetic workloads (never upstreamed)
scripts/                    ← harness, verify, QMP dump, fdata conversion
```

### Upstream insertion points (llvm-project)

| Component | Path |
|-----------|------|
| Target registration | `bolt/CMakeLists.txt` — add `ARM` to `BOLT_TARGETS_TO_BUILD_all` |
| New backend tree | `bolt/lib/Target/ARM/` — `ARMMCPlusBuilder.cpp`, `ARMMCSymbolizer.{cpp,h}`, `CMakeLists.txt` |
| Arch dispatch | `bolt/lib/Core/BinaryContext.cpp` — accept `Triple::arm` |
| MCPlusBuilder factory | `bolt/lib/Rewrite/RewriteInstance.cpp` — `createMCPlusBuilder()` |
| Mapping symbols | `BinaryContext::getMarkerType()` — `$a` / `$t` / `$d` |
| Relocations | `bolt/lib/Core/Relocation.cpp` — `R_ARM_*` |
| Lit tests | `llvm/test/tools/llvm-bolt/ARM/` |

Reference backend for scaffolding: **RISC-V** (`bolt/lib/Target/RISCV/`) — smallest existing target.

---

## P0 — ARM32 harness ✓

No BOLT backend. Proves the AArch64 collection path ports to ARM32.

| Work | Where | Status |
|------|--------|--------|
| Build LK `qemu-virt-arm32-test` with `--emit-relocs` | `scripts/build-lk-aarch32.sh` | Done |
| Boot `qemu-system-arm -machine virt -cpu cortex-a15` | `scripts/run-qemu-lk.sh` (`LK_PROJECT=qemu-virt-arm32-test`) | Done |
| `bolt_bench` overlay on ARM32 project mk | `scripts/apply-overlays.sh` | Done |
| P0 verify script | `scripts/verify-bolt-arm32-harness.sh` | Done |
| P0–P4 milestone gate | `scripts/verify-bolt-arm32-milestones.sh` | Done — all pass on pod |
| Cross-build runtime for `arm-none-eabi` | `scripts/build-bolt-rt-baremetal.sh` | **Done** (`ARCH=arm32`) |
| Rebase llvm-project to `main` | `scripts/ensure-llvm-source.sh` `LLVM_COMMIT=<main tip>` | Pending (before upstream PRs) |

**Pass:** original `lk.elf` reaches `entering main console loop`; `lk.bolt_bench=all` prints all four `bolt_bench: … done` lines.

---

## P1 — ELF32 reader

BOLT today rejects `Triple::arm` in `BinaryContext::createBinaryContext()` (`BOLT-ERROR: Unrecognized machine in ELF file`). ELF32 LE paths partially exist in `RewriteInstance.cpp`.

| Work | Upstream files |
|------|----------------|
| Accept `Triple::arm`; `ArchName = "arm"` | `BinaryContext.cpp` |
| Add `isARM()` | `BinaryContext.h` |
| Mapping symbols `$a` / `$t` / `$d` | `BinaryContext::getMarkerType()` |
| `Elf32_Rel` / `Elf32_Rela` (addend in-place vs explicit) | `RewriteInstance.cpp` (extend existing ELF32 paths) |
| Record `.ARM.attributes` (arch, Thumb ISA); do not enforce yet | `BinaryContext` / section metadata |
| Minimal `ARMMCPlusBuilder` stub (enough to construct `BinaryContext`) | `bolt/lib/Target/ARM/` skeleton |
| Add `ARM` to `BOLT_TARGETS_TO_BUILD` | `bolt/CMakeLists.txt` |

**Overlay staging:** `overlay/llvm/patches/0003-bolt-arm-elf32-and-target.patch`  
**Lit fixture:** `overlay/llvm/tests/arm32-empty.s` → upstream `llvm/test/tools/llvm-bolt/ARM/elf32-parse.test`

**Pass (lit):** `llvm-bolt --print-sections -o /dev/null` on tiny ARM ET_EXEC lists `.text` without abort.  
**Pass (QEMU):** same on `third_party/lk/build-qemu-virt-arm32-test/lk.elf`.

---

## P2 — ARM-mode disassembly

ARM state only (symbol LSB = 0). No Thumb yet.

| Work | Detail |
|------|--------|
| LLVM ARM disassembler with explicit ARM mode | `ARMMCPlusBuilder` |
| Skip `$d` literal pools as data | Mapping symbols from P1 |
| Reject Thumb functions with clear error | Fail loud, not silent mis-decode |
| New bench (optional) | `bolt_bench_literal` — `$d` pool + `ldr [pc]` |

**Lit fixture:** `overlay/llvm/tests/arm32-add-bl.s` — `add`/`b`/`bl`/`ldr` pc-rel; wrong-mode input fails.

**Pass:** FileCheck disassembly output; ARM-compiled `hot_loop` bytes match `llvm-objdump`.

---

## P3 — CFG (ARM only)

| Work | Detail |
|------|--------|
| BB boundaries from branches | `B`, `BL`, `BX`, `LDR pc`, `POP {pc}` |
| Edge kinds | Direct call, tail call, conditional branch |
| One function = one ISA state | ARM only at this rung |

**Pass:** `--print-cfg` on ARM `hot_loop` / `hot_cold` / `branch_chain` matches expected edges (lit FileCheck).

---

## P4 — Identity rewrite

First “BOLT did something” milestone: rewrite the binary and it still runs.

| Work | Detail |
|------|--------|
| Encode/decode ARM branches and PC-relative `LDR` | `ARMMCPlusBuilder` |
| Relocations | `R_ARM_CALL`, `R_ARM_JUMP24`, `R_ARM_ABS32`, `R_ARM_REL32` |
| Identity layout | `llvm-bolt in.elf -o out.elf` (no `-instrument`, no `-data`) |

**Pass (lit):** rewritten lit ELF executes correctly.  
**Pass (QEMU):** rewritten `lk.elf` boots; `lk.bolt_bench=all` completes.

P4 rewrites **ARM-mode** functions. Default `qemu-virt-arm32-test` compiles `bolt_bench_*` as Thumb; rebuild with `BOLT_BENCH_ISA=arm` for the P4 gate (Thumb rewrite is P6).

```bash
# One-shot P0–P4 (expects ARM-mode benches already built)
./scripts/verify-bolt-arm32-milestones.sh

# Or identity rewrite only
BOLT_BENCH_ISA=arm REQUIRE_OVERWRITE=1 BOOT_REWRITTEN=1 \
  ./scripts/verify-bolt-arm32-identity.sh
```

---

## P5 — Branch range / veneers

ARM `B`/`BL` are ±32 MB. After layout, some edges miss.

| Work | Detail |
|------|--------|
| Insert veneers | `B` → far stub → target |
| Linker glue | Treat `.glue_7` as synthetic blocks |
| New bench | `bolt_bench_far_call` — deliberately distant call |

**Pass:** rewritten far ELF contains a LongJmp stub (`movw`/`movt`/`bx` or encoding), `qemu-arm` exit 42, and lit `arm-longjmp-veneer.test` FileChecks both. Gate: `verify-bolt-arm32-veneer.sh` (uses `--pad-funcs-before=far_away:0x2100000` so the final layout stays OOR).

```bash
./scripts/verify-bolt-arm32-veneer.sh
```

Optional LK `bolt_bench_far_call` exists for smoke; the ±33MB pad is lit-only (`arm32-far.ld`), not in the default LK image.

---

## P6 — Thumb-2 (no IT)

Most LK user code and `bolt_bench` compiled `-mthumb` lands here.

| Work | Detail |
|------|--------|
| Entry state | Symbol LSB / `$t` mapping symbol |
| Mixed 16/32-bit insn sizes | BB ends from disassembler only |
| Relocations | `R_ARM_THM_CALL`, `R_ARM_THM_JUMP24`, `R_ARM_THM_JUMP11`, `R_ARM_THM_JUMP19` |
| Thumb `BL` ±16 MB | Reuse P5 veneers |
| Functions with `IT` | Deferred to P7 (now supported) |

**Pass:** Thumb `hot_loop` identity-rewritten ELF runs on QEMU; rebuild `bolt_bench` with `-mthumb`.

**Verified (2026-09-14):** default `-mthumb` LK benches; `llvm-bolt --funcs-file=bolt_bench_*` → `/tmp/lk.bolt.thumb`; qemu-system-arm prints all `bolt_bench: … done` and `entering main console loop`. ARM lit `bolt/test/ARM` 8/8. Fixes included Thumb ABS32 LSB, new-segment `p_paddr` skew, Thumb/ARM branch reloc encode, skip force-rewrite of LLD ARM veneers, JITLink aarch32 stubs + Thumb bit on pointers.

---

## P7 — IT blocks

`IT` / `ITT` / `ITE` … form a 1–4 instruction bundle. Splitting or hooking inside is illegal.

| Work | Detail |
|------|--------|
| Detect `IT` header | `isPrefix(t2IT)` + `getITBlockSize()` (1..4 from PredBlockMask) |
| Stop skipping | `isUnsupportedInstruction` no longer rejects IT |
| Instrumentation (P9) | Hooks only **before** `IT`, or skip function |
| Layout | Move whole bundle, never a subset |
| New bench | `bolt_bench_it_cond` — Thumb-2 inline `ite`/`itt` |
| Lit | `thumb-it.test` — CFG sees IT; rewritten `.text` keeps `0cbf`/`1cbf` |

**Pass:** FileCheck on IT-heavy `.s`; identity rewrite does not split the bundle; `it_cond` runs correctly.

**Verified (2026-09-14):** ARM lit 9/9 (`thumb-it` included); `--funcs-file-no-regex` rewrite of `bolt_bench_*` (incl. `it_cond`); qemu-system-arm `lk.bolt_bench=it_cond` and `=all` print `done` + console. New `.text` retains `ite`/`itt` encodings (`0cbf`/`1cbf`).

---

## P8 — ARM↔Thumb interworking

| Work | Detail |
|------|--------|
| Interworking edges | `BLX`, `BX rm`, `LDR pc` with LSB, `POP {pc}` |
| CFG edge metadata | Target state (ARM vs Thumb) |
| Veneers | Set correct state (`BX` / Thumb bit) |
| Linker glue | Follow `.glue_7` / `.glue_7t` |
| New bench | `bolt_bench_interwork` — ARM caller, Thumb callee |

**Pass:** ARM→Thumb and Thumb→ARM calls identity-rewritten and both run.

**Verified (2026-09-14):** ARM lit 10/10 (`arm-interwork` + longjmp veneer). `matchAbsLongVeneer` uses symbol size + resolves only to real functions (avoids MaxSize fill). `adjustCallForTargetMode` rebuilds BL/BLX after veneer redirect. QEMU: `--funcs-file-no-regex` of `bolt_bench_interwork` + callees → `interwork done` + console; same narrow set runs `lk.bolt_bench=all`. Full `bolt_bench_*` rewrite still breaks sequential `all` (trampoline leftover; not a P8 gate).

---

## P9 — Instrumentation + RAM profile

Reuse Phase 2 QMP collection path. New work is **AArch32 probe emission**.

| Work | Where |
|------|--------|
| Counter bump at leaf/edge sites (outside IT) | `ARMMCPlusBuilder` |
| 32-bit atomics (`ldrex`/`strex` loop; no LSE) | Instrumentation + runtime |
| `libbolt_rt_baremetal.a` for `arm-none-eabi` | `scripts/build-bolt-rt-baremetal.sh` |
| Instrument **only** `bolt_bench_*` | `scripts/instrument-lk-bolt.sh` (ARM32 paths) |
| 32-bit VA decode in fdata converter | `scripts/ram-dump-to-fdata.py` |
| End-to-end verify | `scripts/verify-bolt-workloads.sh` (ARM32 mode) |
| Org.text counter hooks if hot `.text` not executable | `scripts/fix-kernel-elf-sections.py` ARM32 twin |

**Pass:** QMP dump shows **N/N counters non-zero** for all four `bolt_bench` functions; `.fdata` names all four.

**Verified (2026-09-14):** BOLT `-instrument` emits ARM32 probes; post-pass restores `.bolt.org.text`/`.data` (BOLT trampolines smash ARM literal pools) and installs Thumb org.text counter hooks into unused hot `.text`. ELF32-safe `fix-kernel-elf-entry.py` / `fix-kernel-elf-paddr.py`. Gate: `dump-bolt-counters.py` → **5/5** non-zero; `ram-dump-to-fdata.py --funcs=…` names `hot_loop`/`hot_cold`/`branch_chain`/`memcpy`. `ARCH=arm32 ./scripts/verify-bolt-workloads.sh` (stops after `.fdata`; optimize = P10).

---

## P10 — Layout optimize

| Work | Detail |
|------|--------|
| Stock passes | `-reorder-blocks=ext-tsp`, `-reorder-functions=hfsort+` |
| Input | `.fdata` from P9 |
| ELF fixes | Re-apply paddr/entry/section restore if LK requires (same as AArch64) |
| Measurement | Guest timer via `arch_cycle_count()` in `bolt_bench` |

**Pass:** `lk.bolt.elf` boots, reruns `bolt_bench all`; cycle lines printed (improvement nice-to-have, not a gate).

---

## P11 — Upstream landing

Process rung — not new ISA features. PRs for P1–P10 are **opened as each rung completes**; P11 tracks them through merge.

| Task | Detail |
|------|--------|
| RFC on Discourse | Before P4 (see above) |
| PR hygiene | One rung per PR; lit + commit message explains pass gate |
| Review feedback | Rebase slices onto llvm-project `main` |
| Overlay cleanup | Delete `overlay/llvm/patches/000N-bolt-arm-*.patch` as each merges |
| Volume rebase | Point volume checkout at merged `main`; rebuild toolchain |
| Final gate | Full ARM32 pipeline green on upstream `main` + overlay bare-metal patches only |

**Pass:** All P1–P10 PRs merged; no AArch32 backend patches remain in overlay; `verify-bolt-workloads.sh` ARM32 passes against volume-built upstream `llvm-bolt`.

---

## Verification layers

Two layers at every rung (except P0):

1. **Lit** — upstream-shaped `.s` / `.test` in `llvm/test/tools/llvm-bolt/ARM/`
2. **QEMU / LK** — `bolt_bench` on `qemu-virt-arm32-test` (this repo)

### Workload set

| Workload | Compiles as | Stresses | First at |
|----------|-------------|----------|----------|
| `bolt_bench_hot_loop` | ARM then Thumb | Dense back-edge loop | P3 / P6 |
| `bolt_bench_hot_cold` | ARM then Thumb | Rare taken branch | P3 / P6 |
| `bolt_bench_branch_chain` | ARM then Thumb | Many conditional edges | P3 / P6 |
| `bolt_bench_memcpy` | ARM then Thumb | Straight-line + `bl` | P4 / P6 |
| `bolt_bench_literal` (new) | either | `$d` pool + `ldr [pc]` | P2 |
| `bolt_bench_far_call` (new) | either | Veneer / range | P5 |
| `bolt_bench_it_cond` (new) | Thumb-2 | `IT`/`ITE` | P7 |
| `bolt_bench_interwork` (new) | ARM caller, Thumb callee | `blx` / state change | P8 |

Still **no LK kernel functions** as instrumentation targets.

### End-to-end script (from P9)

Mirror AArch64:

```bash
ARCH=arm32 ./scripts/verify-bolt-workloads.sh
# build LK arm32 + bolt_bench → instrument → QMP counters → .fdata
# instrument only bolt_bench_*
# QEMU + QMP dump
# ram-dump-to-fdata
# llvm-bolt -data=prof.fdata
# boot lk.bolt.elf -append lk.bolt_bench=all
```

---

## Suggested calendar (serial)

| Slice | Rungs | Outcome |
|-------|-------|---------|
| 1 | P0 | ARM32 LK + QEMU + `bolt_bench` green without BOLT — **done** |
| 2 | P1–P4 | BOLT reads, CFG-builds, identity-rewrites ARM-mode binaries |
| 3 | P5–P6 | Veneers + Thumb-2 identity rewrite of four benches |
| 4 | P8 | Interworking |
| 5 | P9–P10 | Instrument → QMP → `.fdata` → optimize |
| 6 | P11 | All PRs merged; overlay backend patches deleted |

---

## Out of scope (first complete pass)

- Cortex-M / Thumb-only M-profile
- ThumbEE, Jazelle
- ARMv8 AArch32 BTI/PAC
- Shared libraries / PLT
- Instrumenting any LK function outside `bolt_bench_*`
- Making hot `.text` executable inside LK (AArch64 org.text workaround applies if needed)

---

## Success criteria

- [x] P0: ARM32 LK boots; `bolt_bench all` prints four done lines
- [x] P1: `llvm-bolt --print-sections` on ARM32 `lk.elf` lists `.text`
- [x] P2–P4: `llvm-bolt` identity-rewrites ARM-mode `bolt_bench` (`BOLT_BENCH_ISA=arm`) and that ELF boots on QEMU
  - Lit FileCheck still weak / not confirmed `check-bolt` green
- [x] P5: LongJmp veneers — `verify-bolt-arm32-veneer.sh` (linker veneer elim + stub insert)
- [x] P6: Thumb-2 identity rewrite on QEMU (no IT)
- [x] P7: IT bundles atomic; `bolt_bench_it_cond` identity rewrite on QEMU
- [x] P8: Interworking identity rewrite on QEMU
- [x] P9: Instrumentation + QMP profile (5/5 counters + named `.fdata`)
- [ ] P10: Optimized `lk.bolt.elf` boots and reruns workloads
- [x] Lit coverage for ARM, Thumb-2, IT, interworking, veneers in llvm-project
- [ ] P11: Core backend (P1–P10) merged to llvm-project `main`; overlay backend patches gone
