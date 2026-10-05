# AArch32 position-dependent PC-read admission

Overlay 0045 rejects unmodeled architectural PC reads in selected, decoded ARM
and Thumb functions before transformation/output. Moving these instructions can
change a computed address or stored value without producing a relocation error.
This is a conservative admission fix, not support for relocating arbitrary PC
values. Evidence: [0045 results](../results/correctness_pc_reads_20261004.json).

## Reproduced defect and fix

ARM and Thumb probes read a fixed data word through `MOV register,PC` followed
by a load. Both originals exit 42. Before 0045, both assertion modes emit the
probes at a new address and all eight normal/reverse candidates fault with
SIGSEGV. The PC-derived address moves away from the original data. After 0045,
all eight inputs reject with a position-dependent-PC diagnostic and no output
image or function map; their original executions still exit 42.

The guard checks explicit PC operands, implicit uses, ADR forms whose MC operands
omit PC, and the Thumb literal address mode that hides PC even from implicit-use
lists. It rejects unmodeled MOV/ADD/store-PC, byte/halfword/signed and VFP literal
loads, PC prefetches, dead/predicated reads and register branches through PC.
Existing modeled word literal loads, ordinary calls/returns and modeled inline
TBB/TBH PC bases retain their existing admission rules. PC writes are checked by
the earlier independent guard. Mapping-symbol data is not treated as code merely
because its bits resemble a PC-reading instruction.

Each build passes 189 focused cases: 145 rejections and 44 admissions, including
ordinary/reverse/instrumented variants and preservation of existing artifacts on
rejection. The broader ARM/JITLink suite passes 53 tests with assertions, and 52
with one expected unsupported test without assertions. CoreTests pass 58 with
31 target-specific skips per build. All 45 overlays replay exactly from the
pinned ATFE base; this certifies source contents, not clean compiler provenance.
The older inline test now requires eight PC-read rejections while retaining its
84 other inlining cases and four Thumb IT-call rejections.

## memcpy and execution scope

The original NEON benchmark memcpy contains PC-derived constant-pool setup and
is not emitted by the existing fixture. It remains excluded from a successful
exact-selection receipt. 0045 does not add ADR/NEON relocation support or certify
that input.

A separate isolated LK copy explicitly compiles the benchmark module with
`-mfpu=none` and retains a linked 64 KiB protected reservation. In both builds,
the strict QEMU producer emits, redirects and executes all four selected ARM
entries: hot_loop, hot_cold, branch_chain and this integer-only memcpy. Live
original/emitted entry pairs retain ISA, SVC mode and input register/CPSR state.
All eighteen outputs match fresh baselines. This changes the input shape; it
does not repair or certify the original NEON memcpy. Independent output oracles,
whole-LK rewriting and wider ISA/pass/reference coverage remain open.

## Remaining limits

The guard applies to decoded functions selected for transformation. Functions
kept or ignored by existing disassembly/admission policy are not certified by
this guard; exact selected/emitted/executed gates must reject missing coverage.
No new Pi execution is claimed. The older sparse Pi far-safety fixture itself
uses MOV-PC witnesses and cannot be rebuilt under this contract. Its recorded
0044 execution remains historical evidence; a compatible live execution witness
and fresh hardware verification are pending. Interrupts, PMU ownership, manual
hooks, independent oracles and clean build provenance remain open under item 6
and original workstream #12.
