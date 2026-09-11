# AArch64 bare-metal BOLT — delta from stock

Stock BOLT assumes a **Linux process** with `perf` or **bolt-rt** flushing to a file at exit. Bare-metal LK has no kernel, no `perf`, no filesystem.

## Delta summary

| Area | Stock BOLT | Required for bare-metal |
|------|------------|-------------------------|
| Profile source | `perf` or bolt-rt → file | bolt-rt → **fixed RAM** |
| Link | PIE or relocatable ET_EXEC | **`-Wl,-q`** (`--emit-relocs`) |
| Flush trigger | `exit()` / `atexit` | Explicit call or **halt hook** |
| fdata on host | Read file | **Convert RAM dump** → `.fdata` |
| Atomics | LSE on modern ARM64 | **`--no-lse-atomics`** for QEMU cortex-a53 |

Everything else (instrument, collect edges, reorder, emit optimized ELF) reuses upstream AArch64 BOLT.

## Overlay work items

### 1. LLVM — `overlay/llvm/patches/`

**`bolt-rt-baremetal.patch`** (or split commits for upstream):

- Replace / gate `writeProfile()` syscalls behind `#ifdef BOLT_BAREMETAL`
- Map counter table to linker symbols `__bolt_profile_start` / `__bolt_profile_end`
- Serialize `.fdata` layout into a sub-region of that buffer (or emit raw layout + host converter)
- Export `bolt_profile_reset()`, `bolt_profile_serialize()`, `bolt_profile_fini()`

**Optional host flags:**

- `--bare-metal-profile` — document RAM layout expectations
- Default `--no-lse-atomics` when target triple is bare-metal ELF

### 2. LK — `overlay/lk/patches/`

**`linker-bolt-profile.patch`:**

```text
.bolt_profile (NOLOAD) : {
  __bolt_profile_start = .;
  . += BOLT_PROFILE_SIZE;   /* counters + fdata scratch */
  __bolt_profile_end = .;
} > DRAM
```

**`platform-dump-profile.patch`:**

- After workload: copy `[__bolt_profile_start, __bolt_profile_end)` out via chosen transport (start with QEMU memory dump + symbol offsets)

**`app-bolt-bench.patch`:**

- New `app/bolt_bench/` — not boot-only validation

### 3. Host — `scripts/` (overlay repo only)

**`ram-dump-to-fdata.sh`** (TBD): input = ELF + dump offset/length → output = `prof.fdata`

No need to upstream this; it is harness glue.

## Validation strategy (beyond boot)

Boot proves **link + run**. Optimization needs **profile mass on hot edges**.

| Tier | Workload | Validates |
|------|----------|-----------|
| T0 | Boot to shell prompt | No crash; counters non-zero |
| T1 | `bolt_bench hot_loop` | Dominant edge counts match source |
| T2 | `bolt_bench memcpy` | Function-level hot spots |
| T3 | `bolt_bench threads` | Multi-context counter integrity |
| T4 | Timer / IRQ handler | Short hot paths, not just `main` |
| T5 | Re-run T1–T4 on `lk.bolt.elf` | Wall-clock + counter stability |

Implement T0–T2 in Phase 2; T3–T4 as stretch. **Do not** treat faster boot as success criterion.

## Build / run pipeline

```bash
# 1. Build with relocs
./scripts/build-lk-aarch64.sh          # LDFLAGS=-Wl,-q

# 2. Instrument
llvm-bolt lk.elf -instrument -o lk.instr.elf --no-lse-atomics

# 3. QEMU run + workload
#    (run bolt_bench commands, then dump profile region)

# 4. Host convert
# ./scripts/ram-dump-to-fdata.sh lk.instr.elf dump.bin > prof.fdata

# 5. Optimize
llvm-bolt lk.elf -o lk.bolt.elf -data=prof.fdata --no-lse-atomics

# 6. Re-run T1–T4 on lk.bolt.elf
```

## Success criteria (Phase 2)

- [ ] Counters in RAM match expected edges for `bolt_bench hot_loop`
- [ ] Host produces valid `.fdata` (llvm-bolt accepts it)
- [ ] `lk.bolt.elf` shows measurable improvement on T1/T2 (≥5% or clear icache footprint reduction)
- [ ] Overlay patches are minimal and documented for optional upstream bolt-rt contribution
