# AArch64 bare-metal BOLT — delta from stock

Stock BOLT assumes a **Linux process** profiled with `perf`, or instrumented with **bolt-rt** which flushes a `.fdata` file at exit. Bare-metal LK has no kernel, no `perf`, and no filesystem.

## Delta summary

| Area | Stock BOLT | Required for bare-metal |
|------|------------|-------------------------|
| Profile source | `perf` or bolt-rt → file | bolt-rt → **fixed RAM region** |
| Runtime library | `libbolt_rt_instr.a`, **host arch** | Own `.a` cross-built for `aarch64-none-elf` |
| Link | PIE or relocatable ET_EXEC | **`--emit-relocs`** |
| Flush trigger | `exit()` / `atexit` | Explicit call or halt hook |
| fdata on host | Read file | **Convert RAM dump** → `.fdata` |
| Counter increment | `stadd` (LSE) | **`--no-lse-atomics`** — QEMU cortex-a53 has no LSE |

Everything else — CFG recovery, edge counting, reordering, emitting the optimized ELF — reuses upstream AArch64 BOLT unchanged.

## The runtime library is the hard part

BOLT builds `libbolt_rt_instr.a` **for the host architecture only**. On our x86_64 build pod cmake reports:

```
-- Building BOLT runtime libraries for X86
```

Instrumenting an AArch64 binary from that toolchain would link an x86 runtime. Upstream is aware — [llvm/llvm-project#187308](https://github.com/llvm/llvm-project/pull/187308) moves `bolt-rt` into the runtimes build so it can be built per-triple — but **that PR is still open**, so no LLVM release solves this for us.

This costs us nothing, because the stock runtime is unusable here regardless: `bolt/runtime/instr.cpp` issues Linux syscalls. The plan is to build our own and point BOLT at it:

```bash
llvm-bolt lk.elf -instrument --no-lse-atomics \
  --runtime-instrumentation-lib=/path/to/libbolt_rt_baremetal.a \
  -o lk.instr.elf
```

`--runtime-instrumentation-lib` is an existing upstream option, so **no BOLT source patch is needed** to select the library — only to write it. This is why the overlay stays small.

## Overlay work items

### 1. Bare-metal runtime — `overlay/llvm/bolt-rt-baremetal/`

Built in two stages, because the symbol contract and the profile serializer fail
for completely different reasons and are worth de-risking separately.

**Stage 1 — symbol contract only** (`instr_baremetal.cpp`, built by
`scripts/build-bolt-rt-baremetal.sh`). Defines just what
`RewriteInstance::linkRuntime()` validates and what the instrumentation pass
branches to: `__bolt_instr_start`, `__bolt_instr_fini`, `__bolt_instr_setup`,
`__bolt_instr_clear_counters`, `__bolt_instr_data_dump`.

- Counters stay in `.bolt.instr.counters` where BOLT emits them. Upstream mmaps
  MAP_FIXED over that range so forked children can share it; a bare-metal image
  loads it as ordinary writable data, so setup has nothing to do.
- No `open`/`write`/`mmap`, no `malloc`, and no `.bss` — BOLT's ORC linker
  cannot place it. The build script fails the archive if either appears.
- Cross-built with the freshly built clang: `--target=aarch64-none-elf
  -ffreestanding -mgeneral-regs-only`.

`-mgeneral-regs-only` matters: the runtime runs inside interrupt paths where
FP/SIMD state is not saved.

This stage proves instrumentation links, boots and increments counters without
writing a single line of LK patch, because `scripts/dump-bolt-counters.py` reads
the counter range out of the guest over QMP instead of the target writing it.

**Stage 2 — on-target serialization.** Port upstream's `readDescriptions()` and
`writeFunctionProfile()` (which reconstruct the CFG from `.bolt.instr.tables`
and infer the edge counts BOLT expects) and send the resulting `.fdata` text to
the UART instead of a file descriptor. Reusing that logic rather than
reimplementing it on the host keeps the profile correct by construction — the
edge inference and call-flow balancing are the parts most likely to be got
subtly wrong.

### 2. LK — `overlay/lk/patches/`

**`linker-bolt-profile.patch`:**

```text
.bolt_profile (NOLOAD) : {
  __bolt_profile_start = .;
  . += BOLT_PROFILE_SIZE;
  __bolt_profile_end = .;
} > DRAM
```

**`platform-dump-profile.patch`** — copy that region out after the workload. Start with QEMU `dump-guest-memory` plus symbol offsets; a UART framing path can come later.

**`app-bolt-bench.patch`** — the workloads below.

### 3. Host — `scripts/ram-dump-to-fdata.sh`

Takes the instrumented ELF plus the raw dump, emits `.fdata`. Harness glue; not upstream material.

## Validation strategy (beyond boot)

Booting proves the instrumented image links and runs. It does **not** prove the optimization works: boot is short, cold-cache, and mostly one-shot code, so there is almost no hot-edge mass for BOLT to act on.

| Tier | Workload | Validates |
|------|----------|-----------|
| T0 | Boot to shell prompt | No crash; counters non-zero |
| T1 | `bolt_bench hot_loop` | Dominant edge counts match source |
| T2 | `bolt_bench memcpy` | Function-level hot spots |
| T3 | `bolt_bench threads` | Counter integrity across contexts |
| T4 | Timer / IRQ handler | Short hot paths, not just `main` |
| T5 | Re-run T1–T4 on `lk.bolt.elf` | Wall-clock and counter stability |

T0–T2 are Phase 2 scope; T3–T4 are stretch. **Faster boot is not the success criterion.**

Measure inside the guest with the ARM generic timer (`CNTVCT_EL0`), not host wall-clock — QEMU's scheduling makes host timing far too noisy.

## Pipeline

```bash
# 1. Build with relocations
./scripts/build-lk-aarch64.sh                  # LDFLAGS=--emit-relocs

# 2. Cross-build the bare-metal runtime (see overlay/llvm/patches)
# 3. Instrument
llvm-bolt lk.elf -instrument --no-lse-atomics \
  --runtime-instrumentation-lib=libbolt_rt_baremetal.a -o lk.instr.elf

# 4. Boot in QEMU, run bolt_bench, dump the profile region
# 5. ./scripts/ram-dump-to-fdata.sh lk.instr.elf dump.bin > prof.fdata

# 6. Optimize
llvm-bolt lk.elf -o lk.bolt.elf -data=prof.fdata

# 7. Re-run T1–T4 on lk.bolt.elf
```

## Success criteria

- [ ] Counters in RAM match expected edges for `bolt_bench hot_loop`
- [ ] `llvm-bolt` accepts the generated `.fdata`
- [ ] `lk.bolt.elf` measurably improves T1/T2 by guest-timer measurement
- [ ] Overlay stays minimal enough that the runtime could be offered upstream
