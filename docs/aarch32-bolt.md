# AArch32 BOLT — implementation and verification plan

**Goal:** add an ARM/Thumb backend to LLVM BOLT, prove it on bare-metal LK in QEMU, then merge incremental PRs to llvm-project `main`.

**What Phase 2 already solved (reuse, do not redo):**

- LK is the **host platform only**. BOLT never instruments kernel/boot code.
- Synthetic `bolt_bench_*` functions are the only profiled targets.
- Counters live in `.bolt.instr.counters`; host reads them over **QMP**.
- `ram-dump-to-fdata.py` turns the dump into `.fdata`; `llvm-bolt -data=` optimizes.

**What Phase 3 must invent:** BOLT has no AArch32 target. `bolt/lib/Target/` is AArch64, X86, RISC-V only. `LLVM_TARGETS_TO_BUILD=…;ARM` gives clang/lld an ARM compiler, not a BOLT backend.

**Base branch:** rebase LLVM onto `main` before backend work. Feature PRs go to `main`, not `release/23.x`.

---

## Complexity ladder

Each rung is independently testable. Do not start the next rung until the previous one has lit tests **and** a QEMU check (except P0, which is harness only).

```text
P0  Harness (no BOLT backend)
P1  Read ELF32
P2  Disassemble ARM-mode only
P3  Build CFG (ARM)
P4  Identity rewrite (MCPlusBuilder)
P5  Branch range / veneers
P6  Thumb-2, no IT
P7  IT blocks
P8  ARM↔Thumb interworking
P9  Instrumentation + RAM profile
P10 Layout optimize
P11 Upstream docs + first PRs
```

---

## Implementation plan

### P0 — ARM32 harness (complexity: low)

No BOLT backend yet. Proves the AArch64 collection path ports.

| Work | Where |
|------|--------|
| Rebase `third_party/llvm-project` to `main`; rebuild clang/lld/llvm-bolt with `X86;AArch64;ARM` | `scripts/build-llvm-bolt.sh` |
| Build LK `qemu-virt-arm32-test` with `--emit-relocs` | `scripts/build-lk-aarch32.sh` (new) |
| Boot in `qemu-system-arm -machine virt -cpu cortex-a15` | `scripts/run-qemu-lk.sh` variant |
| Port `bolt_bench` as ARM32 C (same four functions; no kernel hooks) | `overlay/lk/files/app/bolt_bench/` |
| Cross-build `libbolt_rt_baremetal.a` for `arm-none-eabi` | `scripts/build-bolt-rt-baremetal.sh` (`--target` switch) |

**Pass:** original `lk.elf` reaches `entering main console loop`; `lk.bolt_bench=all` prints all four `bolt_bench: … done` lines.

### P1 — ELF32 reader (low)

BOLT today assumes ELF64 in several `BinaryContext` paths.

- 32-bit addresses, `Elf32_Rel` (addend in-place) and `Elf32_Rela`
- Mapping symbols `$a` / `$t` / `$d` stored per-section
- `.ARM.attributes` recorded (arch, Thumb ISA) but not yet enforced
- Triple `arm-none-eabi` / `armv7-unknown-none-eabi` accepted

**Pass:** `llvm-bolt --print-cfg` on a tiny ARM ELF prints functions without aborting. Lit: checked-in `arm32-empty.s` ET_EXEC.

### P2 — ARM-mode disassembly (low–medium)

ARM state only (LSB=0). No Thumb.

- Use LLVM ARM disassembler with explicit ARM mode
- Skip `$d` islands (literal pools) as data, not instructions
- Reject Thumb functions with a clear error

**Pass:** FileCheck on a `.s` with `add`/`b`/`bl`/`ldr pc-rel`. Wrong-mode input fails loudly.

### P3 — CFG, ARM only (medium)

- Basic blocks from branches (`B`, `BL`, `BX`, `LDR pc`, `POP {pc}`)
- Direct call vs tail vs conditional
- One function = one ISA state

**Pass:** `--print-cfg` on `hot_loop` / `hot_cold` assembly matches expected edges.

### P4 — `MCPlusBuilder` + identity rewrite (medium)

The first “BOLT did something” milestone: rewrite the binary and it still runs.

- Encode/decode ARM branches and PC-relative `LDR`
- Relocs: `R_ARM_CALL`, `R_ARM_JUMP24`, `R_ARM_ABS32`, `R_ARM_REL32`
- Identity layout: `llvm-bolt in.elf -o out.elf` (no `-instrument`, no `-data`)

**Pass:** rewritten ELF boots LK and `bolt_bench all` still completes. No profile required.

### P5 — Branch range / veneers (medium)

ARM `B`/`BL` are ±32 MB. After layout, some edges will miss.

- Insert veneers (`B` → far stub → target)
- Treat existing `.glue_7` as synthetic blocks

**Pass:** lit binary with a deliberately distant call; rewritten ELF still links/runs the call.

### P6 — Thumb-2 without IT (high)

Most LK user code and `bolt_bench` compiled `-mthumb` will land here.

- Entry state from symbol LSB / `$t`
- 16- and 32-bit mixed sizes; BB ends only from the disassembler
- Relocs: `R_ARM_THM_CALL`, `R_ARM_THM_JUMP24`, `R_ARM_THM_JUMP11`, `R_ARM_THM_JUMP19`
- Thumb `BL` ±16 MB — veneers from P5 reused
- Functions that contain `IT` are **skipped** with a warning

**Pass:** Thumb `hot_loop` identity-rewritten ELF runs on QEMU.

### P7 — IT blocks (high)

`IT` / `ITT` / `ITE` … make a 1–4 instruction bundle. Splitting or inserting a hook inside is illegal.

- Detect `IT` header; treat the bundle as one atomic unit
- Instrumentation (P9) may only attach **before** the `IT` or skip the function
- Layout may move the whole bundle, never a subset

**Pass:** FileCheck on IT-heavy `.s`; identity rewrite does not split the bundle.

### P8 — Interworking (high)

Edges that change ARM↔Thumb: `BLX`, `BX rm`, `LDR pc` with LSB, `POP {pc}`.

- CFG edge carries **target state**
- Veneers must set the correct state (`BX` / Thumb bit)
- Linker `.glue_7` / `.glue_7t` followed, not ignored

**Pass:** ARM caller → Thumb callee and reverse, both identity-rewritten, both run.

### P9 — Instrumentation + RAM profile (high)

Reuse Phase 2 collection. New work is **AArch32 probe emission**.

- Insert counter bump at each leaf/edge site (outside IT)
- 32-bit atomics: `ldrex`/`strex` loop (no LSE)
- Link `libbolt_rt_baremetal.a` built for `arm-none-eabi`
- `--instrument-funcs-file` lists **only** `bolt_bench_*`
- Host: existing `dump-bolt-counters.py` + `ram-dump-to-fdata.py` (32-bit VA decode)

Org.text / hot-text boot fixes from AArch64 may need an ARM32 twin if BOLT still relocates `.text`. Keep the same rule: **do not instrument LK**.

**Pass:** QMP dump shows **N/N counters non-zero** across all four `bolt_bench` functions; `.fdata` names all four.

### P10 — Layout optimize (medium, depends on P9)

Stock passes: `-reorder-blocks=ext-tsp`, `-reorder-functions=hfsort+`.

- Consume `.fdata` from P9
- Re-apply ELF paddr/entry/section restore if LK still requires it
- Measure with guest timer (`arch_cycle_count()` already in `bolt_bench`)

**Pass:** `lk.bolt.elf` boots, reruns `bolt_bench all`, guest cycles for `hot_loop` / `hot_cold` are recorded (improvement is nice-to-have, not a gate).

### P11 — Upstream (process, not ISA)

| Rule | Why |
|------|-----|
| One PR per rung P1–P8 first | Reviews stay small; instrumentation can wait |
| Lit tests in `llvm/test/tools/llvm-bolt/` | No LK in llvm-project |
| RFC on Discourse (BOLT) before P4 API shape | `MCPlusBuilder` is shared |
| Delete overlay patch when it merges | Overlay shrinks |

---

## Verification plan (synthetic workloads)

Two layers at every rung: **lit ELF snippets** (upstream-shaped) and **LK `bolt_bench` on QEMU** (this repo).

### Workload set

Keep the four Phase 2 functions. Add ARM-specific benches only when a rung needs them. Still **no LK kernel functions**.

| Workload | Compiles as | Stresses | First required at |
|----------|-------------|----------|-------------------|
| `bolt_bench_hot_loop` | ARM then Thumb | One back-edge, dense loop | P3 / P6 |
| `bolt_bench_hot_cold` | ARM then Thumb | Rare taken branch | P3 / P6 |
| `bolt_bench_branch_chain` | ARM then Thumb | Many conditional edges | P3 / P6 |
| `bolt_bench_memcpy` | ARM then Thumb | Straight-line + `bl` to libc | P4 / P6 |
| `bolt_bench_it_cond` (new) | Thumb-2 | `IT`/`ITE` predicates | P7 |
| `bolt_bench_interwork` (new) | ARM caller, Thumb callee | `blx` / state change | P8 |
| `bolt_bench_far_call` (new) | either | Veneer / range | P5 |
| `bolt_bench_literal` (new) | either | `$d` pool + `ldr [pc]` | P2 / P6 |

Lit equivalents live as `.s` under `overlay/llvm/` until they move into llvm-project tests.

### Per-rung gate

| Rung | Lit | QEMU / LK |
|------|-----|-----------|
| P0 | — | `qemu-system-arm` boots; `bolt_bench all` prints four done lines |
| P1 | Parse ARM32 ET_EXEC | `llvm-bolt --print-sections` on `lk.elf` lists `.text` |
| P2 | Disasm ARM `.s` | Dump ARM-compiled `hot_loop` bytes match objdump |
| P3 | CFG FileCheck ARM | `--print-cfg` on ARM `hot_loop`/`hot_cold`/`branch_chain` |
| P4 | Identity rewrite lit ELF | Rewritten `lk.elf` boots + `bolt_bench all` |
| P5 | Out-of-range `bl` gets veneer | `far_call` still returns |
| P6 | Thumb `.s` CFG + rewrite | Rebuild `bolt_bench` `-mthumb`; identity rewrite boots |
| P7 | IT bundle not split | `it_cond` identity rewrite + correct result |
| P8 | ARM↔Thumb call CFG | `interwork` identity rewrite |
| P9 | Counter sites FileCheck | `verify-bolt-workloads.sh` ARM32: all bench counters non-zero, `.fdata` has every `bolt_bench_*` |
| P10 | Optimize lit with fake `.fdata` | `lk.bolt.elf` boots and reruns `all`; cycle lines printed |

### End-to-end script (add when P9 starts)

Mirror AArch64:

```bash
./scripts/verify-bolt-workloads.sh   # detect ARCH=arm32
# build LK arm32 + bolt_bench
# instrument only bolt_bench_*
# QEMU + QMP dump
# ram-dump-to-fdata
# llvm-bolt -data=prof.fdata
# boot lk.bolt.elf -append lk.bolt_bench=all
```

### Out of scope for first complete pass

- Cortex-M / Thumb-only M-profile
- ThumbEE, Jazelle
- ARMv8 AArch32 BTI/PAC
- Shared libraries / PLT
- Instrumenting any LK function outside `bolt_bench_*`
- Making hot `.text` executable inside LK (AArch64 workaround stays host-side hooks if needed)

---

## Suggested calendar (serial)

| Slice | Rungs | Outcome |
|-------|-------|---------|
| 1 | P0 | ARM32 LK + QEMU + `bolt_bench` green without BOLT |
| 2 | P1–P4 | BOLT can **read, CFG, rewrite** ARM-mode binaries |
| 3 | P5–P6 | Thumb-2 identity rewrite of the four original benches |
| 4 | P7–P8 | IT + interworking benches |
| 5 | P9–P10 | Full instrument → QMP → `.fdata` → optimize |
| 6 | P11 | First upstream PRs (P1–P3), then the rest |

---

## Success criteria

- [ ] `llvm-bolt` identity-rewrites ARM and Thumb-2 `bolt_bench` ELFs that boot on QEMU
- [ ] Instrumentation + QMP profile covers all `bolt_bench_*` sites
- [ ] Optimized `lk.bolt.elf` boots and reruns the same workloads
- [ ] Lit coverage for ARM, Thumb-2, IT, interworking, veneers
- [ ] Core backend (at least P1–P4) submitted to llvm-project `main`
