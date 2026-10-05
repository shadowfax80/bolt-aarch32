# RFC draft — AArch32 (ARM/Thumb) target for BOLT

> **Status: draft, not yet posted.** Intended for
> [LLVM Discourse → Subprojects → BOLT](https://discourse.llvm.org/c/subprojects/bolt/).
> Everything below the line is the post body. Before posting, fill in the
> `TODO` links once the branch is public, and strip the `Co-Authored-By` /
> `Claude-Session` trailers from the commits if you prefer upstream-style
> messages.

---

## [RFC][BOLT] Add an AArch32 (ARM/Thumb) target

### Summary

We have a working AArch32 target for BOLT: ELF32 input, ARM and Thumb-2
disassembly, CFG construction, relocation-mode rewrite, long-branch veneers,
instrumentation, and profile-guided layout (`-reorder-blocks=ext-tsp`,
`-reorder-functions=hfsort+`, `-icf`). It is validated with lit tests and
end to end on a bare-metal Little Kernel image under QEMU, where a
freestanding runtime keeps counters in RAM and the host reads them out.

Before sending patches, we'd like agreement on the one change that touches
shared infrastructure: **how BOLT core selects an `MCPlusBuilder` when a
single binary contains two instruction sets.**

### The problem

An AArch32 binary mixes ARM functions (fixed 32-bit encoding) and Thumb
functions (16/32-bit encoding). A function uses one instruction set for its
whole body, determined by the symbol's low bit and the `$a`/`$t` mapping
symbols. Decoding, analysing and emitting a function each need the
disassembler, subtarget and `MCPlusBuilder` that match its instruction set.

`BinaryContext` has one of each. Our first implementation switched the shared
`MCPlusBuilder`'s subtarget in place (`setSTI()`) around each use. That is a
data race: passes run under `parallel::for_each`, and a thread working on a
Thumb function can have its subtarget reset by a thread finishing an ARM
function. The failure mode is silently wrong encodings, not a crash.

### Proposal

`BinaryContext` holds a second, Thumb-mode disassembler, subtarget and
`MCPlusBuilder`, constructed once and never mutated. Core code asks for the
builder by function:

```cpp
/// Return the MCPlusBuilder that matches BF's instruction set.
MCPlusBuilder *BinaryContext::getMIBFor(const BinaryFunction &BF) const;

/// Return the subtarget to encode BF with.
const MCSubtargetInfo &BinaryContext::getSTIFor(const BinaryFunction &BF) const;
```

On every target other than ARM these return the existing `MIB` and `STI`,
so behaviour elsewhere is unchanged. Core code never names ARM or Thumb to
make the choice. Target-generic helpers that build instructions for a
function (for example `createInstrumentationSnippet()`) take the selected
builder rather than reaching for `BC.MIB`; using `BC.MIB` there is exactly
how Thumb functions were once instrumented with ARM encodings.

Questions for reviewers:

1. Is a second builder instance acceptable, or would you prefer the
   instruction set to be a parameter on the `MCPlusBuilder` methods that
   encode?
2. Existing call sites that use `BC.MIB` directly remain correct for every
   non-ARM target. Should they migrate to `getMIBFor()` wholesale, or only
   where ARM is reachable?

### Proposed patch series

1. `[BOLT] Emit __bolt_instr_tables on ELF` (target-independent)
2. `[BOLT] Warn instead of asserting on out-of-section secondary entry`
   (target-independent)
3. `[JITLink][AArch32] Support Thumb literal loads, Thumb-bit absolutes,
   generic triples`
4. `[ARM][MC] Accept BOLT's MOVW/MOVT and 8-byte data fixups in ELF`
5. `[BOLT][ARM] Add AArch32 target` — core plumbing, `ARMMCPlusBuilder`,
   relocations, 12 lit tests
6. `[BOLT][ARM] Support long-branch veneers`
7. `[BOLT][ARM] Support instrumentation`

Each commit builds on its own, and each commit's tests pass at that commit.
Patches 3 and 4 touch JITLink and ARM MC, and can go to their owners
separately.

Branch: `TODO`

### Declared scope for the first landing

Static, little-endian, ARMv7-A-class executables linked with LLD and
`--emit-relocs`, built without C++ exceptions or TLS. Specifically *not*
yet supported:

- `.ARM.exidx` / `.ARM.extab` unwind tables (not rewritten)
- TBB/TBH table-branch jump tables (recognised; such functions are left
  unmodified)
- `-split-functions` (needs `R_ARM_THM_JUMP19` in JITLink) and
  `-peepholes` on ARM-mode functions
- GOT/TLS relocations, shared libraries, big-endian, M-profile
- Byte-reproducible output: the layout of JITLink's aarch32 stubs still
  varies between runs (every variant is correct). This must be fixed before
  landing; we are raising it here in case the cause is already known.
- Coverage: on a real bare-metal image, BOLT currently rewrites about 7% of
  functions and skips the rest, mostly on instructions it cannot
  disassemble.

`-indirect-call-promotion`, `-reg-reassign` and `-frame-opt` are already
restricted to X86/AArch64 in BOLT and stay that way.

We'd rather land a narrow, correct target and grow it than claim general
support. The full list of known gaps is `TODO: link to KNOWN_LIMITATIONS`.

### Testing

- lit: `bolt/test/ARM/` (12 tests) plus `bolt/test/elf32-basic.test`, all
  passing at the tip and at each intermediate commit that carries them.
- End to end: instrument → run → collect counters → `.fdata` → optimize →
  run, on a bare-metal LK image under `qemu-system-arm -cpu cortex-a15`,
  on both current `main` and Arm's `arm-toolchain` integration branch.
- QEMU does not model caches, so we make no performance claims from those
  runs; measurements on hardware will follow.
