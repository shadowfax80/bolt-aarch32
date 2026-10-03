# Selected LK rewrite execution in QEMU

The previous complete-output stage deliberately made no rewritten-execution
claim. Its hot-loop candidates retained the original entry bytes. Filtered live
QEMU traces confirm execution at the original entry without visiting the emitted
entry. Restoring original text and seeing eighteen matching outputs cannot
establish that a moved function ran.

Explicitly redirecting the unreserved hot-loop image reaches the emitted entry,
then LK raises an undefined abort. The emitted code starts at `0x801f8000`, beyond
the input kernel's `_end=0x801f6ca0`; the retained boot allocator boundaries still
refer to the original end. This is an observed unsupported placement, not a
proved attribution of the abort to one backend instruction or allocator write.
Extending an ELF LOAD alone does not establish kernel memory ownership.

`qemu_rewrite_build.py` uses BOLT's existing linked `__bolt_reserved_start` and
`__bolt_reserved_end` mechanism. It snapshots the input, emits an exact selection
and map, restores retained kernel sections, installs scoped entry branches and
invokes `qemu_rewrite_gate.py`. Every step must succeed. No new LLVM overlay or
live LK change is needed. Builds require an executable zero-filled reservation
inside the original kernel allocation boundary. They never automatically grow
that boundary or alter allocator state.

The verifier checks these conditions before boot:

- The explicit selection and map match exactly, with no missing or extra names.
  Map ranges match unique input/output function symbols, sizes and ISA bits.
- Emitted bodies fit inside the linked reservation. Original and emitted code
  are executable; prologues match. Original four-byte entries contain an aligned
  unconditional ARM B or Thumb B.W to the mapped emitted entry. Overlapping
  bodies/redirects and overwritten secondary entries reject.
- Kernel entry, reservation boundaries, `_end`, LOAD virtual/physical addresses,
  sizes, flags and alignment remain unchanged. All loaded bytes outside the
  reservation and selected entry branches remain identical, including callers
  and boot allocator data. `_end` must match the original loaded memory boundary;
  the reservation cannot overlap original function code. Malformed/overlapping
  LOAD extents and executable sections without executable LOADs reject.

The runner boots a fresh baseline and candidate with one Cortex-A15 CPU on QEMU
`virt`. Both must finish all eighteen ordered workload results without failures,
exceptions, timeout or child errors, and their result dictionaries must match.
Candidate tracing uses `exec,cpu,nochain` and one-byte filters at every original
and emitted entry. Every selected function needs an adjacent original/emitted
CPU frame pair with the same R0-R14 and full numeric CPSR, matching guest PC/R15,
ARM/Thumb state and SVC mode. Frames must be complete, ordered and bounded;
translation addresses, partial registers and another CPU or privilege mode
cannot provide a witness. QEMU reports CPU state before the translated block
executes: this witnesses entry execution, not retirement of every instruction.

Fresh-directory receipts bind input/candidate/map snapshots, exact options,
tool and verifier hashes, repository revision, serial results and CPU traces.
The producer also binds BOLT/nm/readelf, redirect/restoration scripts, child logs
and the live verification receipt. Source and tool changes reject publication.
Failures preserve diagnostics and create no success receipt. Imported traces
have no CLI path to issue a runtime receipt. Hashes establish identity, not
signatures or clean compiler provenance.

The isolated ARM fixture reserves 64 KiB at `0x80199000..0x801a9000` inside
`_end=0x80206ca0`. Use zero-sized boundary labels, as in the upstream reservation
contract; a sized object spanning a reservation section that BOLT shrinks to zero
leaves invalid section-relative symbol metadata. The fixture is a copy of dirty
LK with current overlay files; it is not a clean-source rebuild.

The isolated fixture appends this assembly to its benchmark source and retains
the section with linker option `--undefined=__bolt_reserved_start`:

```asm
.pushsection .bolt.reserve,"ax",%progbits
.balign 4096
.global __bolt_reserved_start
__bolt_reserved_start:
.space 65536
.global __bolt_reserved_end
__bolt_reserved_end:
.popsection
```

Both assertion-mode builds emit, redirect and execute `bolt_bench_hot_loop`,
`bolt_bench_hot_cold` and `bolt_bench_branch_chain`. All eighteen candidate outputs
match fresh baselines in each build. The default four-function selection also
requests `bolt_bench_memcpy`, which this fixture's BOLT run does not emit. That
request rejects; it is not silently reduced to three. The identity wrapper and
milestone P4 now use the strict producer instead of an overwrite-count banner.
Identity requires live boot; disabling boot rejects. P1/P2/P3 remain separate
artifact diagnostics and may reject excluded whole-LK instructions.

Example for the explicitly bounded three-function scope:

```sh
python3 scripts/qemu_rewrite_build.py --elf /path/to/reserved/lk.elf \
  --toolchain /path/to/build-atfe/bin \
  --funcs bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain \
  --out out/scoped-qemu
```

No whole-LK correctness, independent eighteen-result oracle, Thumb kernel fixture,
interrupt/reentrancy safety, optimization/pass matrix, PMU, new Pi execution or
clean-build provenance is certified here. Existing general workload/PGO scripts
still provide their stated output-consistency scope; this stage does not upgrade
them to selected-execution certificates. Automatic v7 retained-thunk and wider
placement/reference routes remain open. Item 6 and original #12 stay active.
See [evidence](results/correctness_rewrite_coverage_20261004.json) and
[priority queue](CORRECTNESS_PRIORITY_TODO.md).
