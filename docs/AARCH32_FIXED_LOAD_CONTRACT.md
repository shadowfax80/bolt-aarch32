# AArch32 fixed-load ELF contract

Overlay 0042 supports the initial fixed-address ET_EXEC subset for both ordinary
rewriting and instrumentation. It rejects ET_DYN (including static PIE and shared
objects), ET_REL, ET_CORE and other ELF types before creating a BinaryContext or
publishing output. `IsStaticExecutable` cannot establish this boundary: static
PIE without an interpreter previously set that flag and admitted absolute
instrumentation pointers without a rebasing model.

At least one PT_LOAD is required. LOAD file extents must be within the input,
file size must not exceed memory size, and virtual memory ranges must fit ELF32.
Every nonempty allocated section must have a nonzero virtual address and fit a
LOAD memory range; file-backed sections must also have matching file offsets and
fit its file extent. NOBITS sections require memory coverage. A LOAD may start at
zero while actual loaded sections reside above zero.

Nonempty loaded sections at zero are a conservative support exclusion. A fresh
zero-address ARM code fixture reached an assertion in relocation analysis because
BOLT's address map omits zero-address sections. The input and failure log are
retained; the new gate rejects that fixture before analysis in both build modes.
This does not claim zero-address ELF sections are forbidden by the ABI.

PT_INTERP, PT_DYNAMIC and PT_TLS are unsupported, even with an ET_EXEC header.
Dynamic/dynsym section types or names, SHF_TLS, allocated REL/RELA/RELR tables,
recognized dynamic relocation-section names and allocated GOT/PLT sections also
reject. This covers misleading ET_EXEC headers and removal of a PIE's dynamic
segment. Static nonallocated relocation sections retained by `--emit-relocs`
remain supported. All dynamic tags are excluded through the dynamic machinery
boundary; no tag subset or dynamic init/fini hook is certified.

The loader must place sections at their declared VMAs with zero load bias and
initialize data as required by the ELF. No runtime rebasing is implemented.
Counter and runtime MOVW/MOVT materializations remain absolute. ELF metadata
cannot prove actual loader placement, privilege, concurrency, mapping-symbol
truth or arbitrary instruction/reference correctness. The ISA/ABI and quiet
instrumentation contracts still apply separately.

## Verification

Both builds pass 192 cases: 12 admissions and 180 clean rejections. ARM/Thumb and
ordinary/instrumented paths include fixed VMAs 0x1000, 0x8000 and 0x100000;
PIE/shared objects at multiple VMAs; misleading ELF types; missing/invalid LOAD
mappings; interpreter/dynamic/TLS markers; dynamic sections, loaded relocations
and GOT/PLT. Four checks across both ISA modes/options preserve existing output
and map bytes after a PIE rejection, per build.

For each of six instrumented fixed-address controls per build, the test decodes
actual runtime-entry/trampoline targets and compares the entry counter's address
materialization against independent MC bytes. Simulated biases 0x1000/0x10000
show those absolute pointers are not rebased; this is a host check, not execution
under another loader. Output remains ET_EXEC and has no allocated relocation
section. The original F4 review case now rejects before output in both modes.

Focused suites pass 51/50 (one expected release skip), CoreTests 58 with 31
expected skips, and the prior 358-case ISA matrix stays green. The 40 startup
cases now have four fixed-load admissions and 36 rejections: the 20 previously
admitted static-PIE DT_FINI variants now reject. Supported fresh startup (three)
and nested/IT/reset (five) payloads per build equal the exact bytes executed at
0041, including the deliberate reset fault. No new Pi execution is claimed.

All 42 overlays replay exactly to live source. This is source-content identity,
not clean full-build certification. Broader relocation/reference routes, active
interrupts, profile/artifact identity and result gates remain open.

See [evidence](results/correctness_fixed_load_20261003.json),
[ISA/ABI contract](AARCH32_ISA_ABI_CONTRACT.md) and
[priority queue](CORRECTNESS_PRIORITY_TODO.md).
ELF reference: [ELF for the Arm architecture](https://github.com/ARM-software/abi-aa/blob/main/aaelf32/aaelf32.rst).
