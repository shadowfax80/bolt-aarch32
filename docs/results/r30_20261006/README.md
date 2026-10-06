# R30: AArch32 mapping symbols in BOLT outputs (overlay 0072, 2026-10-06)

Found by item 14's no-FPU guard. It reported 1,943 "FP/NEON instructions" in
the G1 image (`out/g1_0071/baseline_full.elf`): 1,939 in the kept original
section and 4 in the new `.text`. None of them were real instructions. They
were code and data decoded in the wrong instruction set, because the
output's mapping symbols were wrong.

## Defect

AArch32 tools (objdump, debuggers, our guard) take the instruction set at an
address from the last `$a`/`$t`/`$d` before it. BOLT 0001–0071:

1. **New code:** carried an input mark to the new code only where the input
   had one at the function's entry. An ARM function that followed another
   ARM function in the input has no `$a` of its own. After reordering it
   followed Thumb code unmarked: `memcpy`/`memmove`/`memset` after
   `cmd_page_alloc` decoded as Thumb.
2. **Island marks:** after a function's trailing literal pool BOLT put a
   "code resumes" mark in the function's state at the function's end, which
   is the next function's entry. In the lit input two Thumb functions
   started under `$a`.
3. **Original section:** dropped every mark inside emitted functions, so the
   kept `.bolt.org.text`, which still runs (non-emitted callers, redirect
   entries), had 3 marks for 176 KB. 70,438 of 63,998 input units decoded
   differently.
4. **Stubs:** JITLink stubs (`__llvm_jitlink_aarch32_STUBS_v7`) had no marks.
5. **Fragment symbols:** split-fragment `foo.cold.N` STT_FUNC symbols (and
   the non-relocation `foo.icf.0` alias) had bit 0 clear for Thumb code.
   Found by the stricter guard on a split build of the bolt_bench image,
   after the first 0072 commit (2a629c5); 0072 was extended (same item).
6. **Runtime library:** the instrumentation runtime's `.text`, linked into
   `.text.bolt.extra.1`, had no marks; tools fell back to their default ISA
   (Thumb for the LK input), so the runtime (ARM) misdecoded in every
   instrumented LK output. Found by item 14's parity scenarios after
   bdcac1e; 0072 extended again.

Execution was never affected: mapping symbols are not in the loaded image.

## Fix (0072)

- `RewriteInstance::updateELFSymbolTable`:
  - marks every emitted fragment's start with its own state;
  - keeps the input's marks (entry and interior) at their original addresses
    when the original bytes survive: the function was not rewritten, or it
    was moved in relocation mode without `--use-old-text`;
  - on ARM, emits a "code resumes" mark after an island or inline table only
    when code of the function actually follows inside the fragment.
- `JITLinkLinker` records the mapping symbols of linked code: each aarch32
  stub's address and ISA (from the stub symbol's `ThumbSymbol` flag) and the
  `$a`/`$t`/`$d` symbols that linked objects (the instrumentation runtime)
  bring. The rewriter adds them for executable sections it does not mark
  itself, sorted (JITLink holds a section's symbols in a pointer-keyed set;
  unsorted, the symbol order changed from run to run, found by item 14's
  determinism check).
- Split-fragment and ICF alias STT_FUNC values carry the Thumb bit.

## Evidence

| Check | 0071 | 0072 |
|---|---|---|
| `arm-mapping-symbols.test` (new; reordering, stubs, a split Thumb function, an ICF pair, an instrumentation runtime) | FAIL: functions in the wrong state, original units misdecoded, pools not data, stubs and runtime unmarked ([log](test_on_0071.txt)); 0072 as of bdcac1e fails on the runtime section ([log](test_on_0072_bdcac1e.txt)) | PASS ([log](test_on_0072.txt)) |
| G1 image: functions starting in the wrong state | 3 (`memcpy`, `memmove`, `memset`) | 0 of 417 |
| G1 image: original section decoding vs input `.text` | 70,438 differences | 3: the two redirected entries (`b`/`b.w`) ([details](lk_image_mapping.txt)) |
| G1 image: no-FPU guard | 1,943 false hits | 0 |
| LK input instrumented (SMP / single-core contract), random split + ICF, stricter guard (item 14) | runtime misdecoded: 8 false FP hits each | ok / ok / ok |
| G1 image `baseline_full.bin` | `2181dffe…` | `2181dffe…` (identical: G1's Pi certification carries over) |
| ARM lit, assertions on / off | 60/60 | 61/61 / 61/61 |
| Replay 0001–0072 | | exact ([replay.json](replay_0001_0072.json)) |
| LK coverage | 401/417 | 401/417 ([json](../lk_coverage_r30_20261006.json)) |

`arm-thumb-entry.test`'s checker assumed a single `$t` in the output; it now
requires a `$t` at the moved entry and no odd mapping-symbol value.
