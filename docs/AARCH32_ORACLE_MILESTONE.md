# Independent oracle and wider Pi execution milestone

2026-10-04, ATFE through overlay 0045. This is the requested stopping milestone;
consolidated P0 item 6 and original #12 remain open. See the
[review](CORRECTNESS_REVIEW_0045.md), [fresh prioritized table](CORRECTNESS_PRIORITY_TODO.md)
and [compact evidence](results/correctness_oracle_milestone_20261004.json).

## Approved QEMU contract

`scripts/qemu_bench_oracle.py` independently derives all eighteen sink values from
the reviewed uint32 source arithmetic. It does not learn expected results from
baseline execution. The approved original ELF is
`e13fa5f45c1b9f970ac29221b15b6efad73c490e291cebd9b06493704f20db20`,
the isolated integer-only ARM QEMU fixture with a linked 64 KiB protected
reservation. Source/configuration hashes and the deliberately defined `__thumb__`
macro are recorded in the contract. Original NEON memcpy is a different,
unsupported input. Unknown input hashes and wrong platforms reject.

Fresh assertions-on/off captures each emit, redirect and execute the four exact
selected ARM entries (hot_loop, hot_cold, branch_chain, memcpy), check their
entry/ISA/input-state witnesses, and independently validate eighteen baseline
and eighteen candidate results. Across both builds: eight selected-entry
observations, 36 baseline sinks and 36 candidate sinks. These are bounded entry
and sink checks, not proof of every instruction, alias, register, or memory effect.

The independent model includes the full stair warm-up/timed sequence and PRNG
state. Unit controls alter each of the eighteen sinks identically in baseline
and candidate and require oracle rejection; missing/extra results, unknown
inputs, and platform mismatches also reject. ARM workload verification uses this
contract. Non-ARM workload and `--check-log` paths remain diagnostics, with no
selected-execution claim. The legacy full profiling wrapper's new final route
still needs end-to-end validation; shell syntax and helper tests do not close it.

Pi whole-image verification now requires a reviewed **Pi** contract before
upload. There are currently no approved Pi whole-LK contracts, so that route is
conservatively unavailable. Mock tests of a synthetic approved Pi contract do
not establish a real hardware oracle.

## Compatible Pi far-call witnesses

The earlier MOV-PC witness is excluded by 0045. The replacement uses modeled
local BL calls and reads their live LR values, including the Thumb state bit.
Caller/callee/return captures are bound to decoded incoming calls and stored
fields; block reversal can separate the BL continuation from its capture block.
Callee LR is saved and restored explicitly. These are live return-link position
witnesses, not the PC of the MOV instruction or embedded constant addresses.

Both assertion modes now verify ARM→ARM, ARM→Thumb, Thumb→ARM and Thumb→Thumb in
baseline, normal and reverse layouts. Nine seeds per pair include zero, equality,
signed overflow endpoints, unsigned wraparound, and a zero arithmetic result:
`0, 1, 2, 17, 7fffffff, 80000000, 80000001, fffffff9, ffffffff`.
Expected result/memory and comparison NZCV are independent; the checker validates
both before/after flags, rather than accepting shared wrong flags. It also checks
live call/return links, stub target/ISA, SP equality and alignment, ordered records
and the quiet entry contract.

| Final hardware observation | Assertions on | Assertions off | Total |
|---|---:|---:|---:|
| Baseline positive cases | 36 | 36 | 72 |
| Normal + reverse transformed positive cases | 72 | 72 | 144 |
| Deliberate result/flags/retained-callee failures | 3 | 3 | 6 |
| Deliberate hang, no completion, watchdog return | 1 | 1 | 2 |
| Uploaded images returning to resident loader | 7 | 7 | 14 |

The retained-callee control preserves arithmetic but fails the live emitted
callee witness. The hang replaces the first ARM callee instruction with a
self-loop; BEGIN followed by loader return must contain no CASE/PASS/FAIL.
This proves observed return without completion, not precise watchdog timing.
Upload/chunk reconstruction, protected regions, unchanged artifacts/scripts/
revision, log hashes, patch/tool identities, options and selected/emitted/
eliminated/executed sets are required before the final receipt is published.
There is no training profile in this milestone (`profile: null`).

Final verification roots are `wider-on/build-dqpxie5s/pi-verify-4sas_0wj` and
`wider-off/build-zoyyerjb/pi-verify-lolistaj`, under
`out/correctness/p0-completion-20261004`. The first wider ON run's execution
checks passed but receipt construction failed; it remains a failed diagnostic.
Earlier 20-case BL/LR runs are precursor evidence, not the final wider matrix.

## Verification and limits

All 141 Python tests pass in WSL. The Windows suite uses the pyserial-enabled
environment; four Linux process-ownership cases are expected platform skips.
Changed shell wrappers pass syntax checks. LLVM source remains at 0045; its
previous both-mode admission/lit/CoreTests and exact 45-overlay source replay
evidence are retained, not counted as fresh runs in this script-only milestone.

Four-byte manual redirects now reject Thumb prefixes that split a wide
instruction. Manual entry-counter hooks remain excluded. Legacy no-map redirects,
unnamed/interior targets and the complete manual/wrapper publication audit remain
open. Pi checks use core 0 HYP, masked IRQ/FIQ, MMU/caches off and explicit supported
literal veneers. Whole-LK, automatic v7 retained thunks, active ISR/SMP, general
state, broader pass/configuration oracles, profile capture and clean compiler
provenance remain unproved. Preserve all failed logs, preimages and dirty trees.
