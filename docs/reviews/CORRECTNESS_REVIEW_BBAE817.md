# ATFE correctness re-evaluation at bbae817

> Dated reference/history. Current ATFE status, ownership, limitations and work
> order are in [HANDOFF.md](../HANDOFF.md), with the
> [latest reconciled review](CORRECTNESS_REVIEW_ASTRA_0057.md). Older phase,
> runtime-contract and verification statements below retain their original scope.

> Historical review through overlay 0024. See the current
> [0038 review](CORRECTNESS_REVIEW_0038.md) and
> [ordered work items](../HANDOFF.md#claims-consolidated-todo).

Reviewed 2026-10-01 after fetching and fast-forwarding the Windows checkout from
`ff7d544` to GitHub `origin/main` at `bbae817`. Scope is ATFE, through overlay 0024.
This review changes the work list; it does not implement backend fixes.

## Assessment

The backend is substantially more capable than at the previous review. Conditional
Thumb branch relocation and hot/cold splitting, ARM conditional branches, tail
calls, restricted inlining, literal-load simplification, and inline TBB/TBH tables
have new implementations and regressions. Sampling profiles and watchdog recovery
have also been added. It is inaccurate to keep listing these as wholly absent.

Nevertheless, **3 of the 12 correctness items remain complete within their stated
scope (#2, #8, #10); the other 9 need work**. Feature completion in
[FUNCTIONALITY_REVIEW.md](FUNCTIONALITY_REVIEW.md) does not establish all of the
correctness closure criteria. The most urgent work is now reliable execution and
result verification, followed by instrumentation and transformation boundaries.

## Evidence and limits

- Fresh run: **36/36** BOLT ARM and LLVM JITLink AArch32 tests passed against the
  existing WSL ATFE build. The optional psutil warning remains; all 36 tests passed.
- Live ATFE is the dirty tree at base `bcc08884995ff3cbee70749524621803b9bd258a`;
  overlay 0024 passes a reverse-apply check. The WSL parent still reports
  `eab1e71`, with local changes. This is not a clean replay of GitHub `bbae817`.
- Reviewed overlays 0022-0024, live builder/CFG/emitter/inliner/relocation/linker
  source, sampling code, Pi gates, redirection, restoration and sync scripts.
- Fresh full-image emission plus the same postprocessing used by
  `full_image_wsl.sh` succeeded in an isolated output directory. The result
  comparison below uses the same input throughout.
- Fresh negative probes reproduce truncated-counter acceptance and a Pi result
  gate accepting a one-workload baseline. Serial output in the latter is mocked.
- Existing Pi evidence is credited from the committed result files. **No new Pi
  execution occurred during this review.** The 403/411 figure is reported emitted
  symbol coverage for one LK image, not proven execution of all those functions.
- The preexisting `baseline.elf` and `baseline_full.elf` in WSL have different
  original-section sizes, so they cannot be assumed to be a matching pair. The
  isolated reproduction avoids that ambiguity. Exact artifact manifests are needed.
- Repro output: [recorded results](../results/correctness_bbae817_review.json).
  Full logs, source snapshots and ELF files are under ignored
  `out/correctness/review-bbae817/`. No WSL source was changed.

## Findings in priority order

### 1. Full-image boot gate does not establish rewritten execution (#12/#11, P0)

[full_image_wsl.sh](../../scripts/pi4/full_image_wsl.sh) restores the original entry
and invokes `fix-kernel-elf-sections.py` without hooks or a subsequent redirect
step. It then counts symbols in the new text section. Those symbols demonstrate
emission, but do not establish that the boot or workloads enter them.

Fresh reproduction confirms that the output entry equals the original entry,
and these restored sections are byte-identical to the matching input:

| Section | Bytes |
|---|---:|
| Original text, restored into `.bolt.org.text` | 175524 |
| `.data` | 260 |
| `.rodata` | 15164 |
| `commands` | 144 |
| `apps` | 40 |

Require verified transfers into rewritten functions, including startup and
preserved callers, and record selected/emitted/redirected/executed coverage
separately. Repeat the full-image Pi check after that gate is in place.

### 2. Pi pass comparison accepts incomplete baselines (#12, P0)

[passes_check.py](../../scripts/pi4/passes_check.py) accepts any nonempty result map
as a baseline, then compares candidates only against its keys. A fresh mocked run
with just `hot_loop=0x1234` for both images reports `RESULT: PASS` and exits zero.
The checker must require an explicit expected workload set, reject conflicting
duplicates, and fail if execution stops before all expected results are produced.
The committed 18-result logs are not disproved by this probe; the gate itself is
too weak to guarantee complete future runs.

### 3. Several workload outputs remain stale shared values (#12, P0)

`bolt_bench all` now prints 18 named results, an improvement in visibility. However,
`memcpy`, `far_call`, `it_cond`, and `interwork` still do not set the shared sink
before it is printed. Their recorded value equals the preceding branch-chain
result. Add independent memory/return/flag checks; printing the shared variable
under another workload name does not close the previous oracle gap.

### 4. Truncated and mismatched profiles remain accepted (#12, P0)

Fresh `ram-dump-to-fdata.py::load_counters()` probe still returns `[7, 0]` for two
declared counters with only one present. Validate all ranges and declared counts
before emitting output. The new `samples_to_fdata.py` also slices input to a
multiple of four bytes, silently dropping a partial final PC. Its input has no
image identity, and the collector accepts a caller-supplied buffer address.
Bind images, buffer metadata, samples/counters, profiles and tools with hashes;
validate sample counts, saturation/loss and exact workload completion. A sampled
profile is useful statistical evidence, not an exact edge-count oracle.

### 5. Instrumentation correctness and admission remain open (#5/#6, P0)

The live ARM counter sequence still updates only offset zero of an eight-byte
counter. Sampling avoids that instrumentation path but does not repair it.
Implement and verify carry or enforce a bounded counter contract. Indirect-call
instrumentation still returns the original call. Enforce supported privilege,
single-core and IRQ/FIQ behavior at admission, including direct tool invocation.
Test live registers, flags, IT blocks, exact edge counts and interrupt restoration.

### 6. CFG recovery differs between assertion modes (#3, P0)

Overlay 0023 fixes the ARM `B` pseudo that caused the reported peephole failure;
the current pass tests pass. But `getNumPseudos()` still recomputes and marks an
ARM function ignored only under `#ifndef NDEBUG`. Do not close #3 until the
remaining recovery is safe and assertions-on/off behavior is verified.

### 7. Wider transformations need boundary coverage (#1/#4/#9/#11, P1)

- THM_JUMP19 now works in focused relocation/splitting fixtures. Complete the
  relocation matrix, signed range/alignment/addend boundaries, BLX H-bit cases
  and unsupported-relocation diagnostics.
- Inline tables now work in normal/reversed layouts. Validate large table reach,
  malformed/ambiguous data islands, duplicate/shared cases, splitting and
  instrumentation interactions. ARM-mode and non-PC-based tables remain outside
  the implemented path and need explicit safe rejection/preservation.
- Conditional returns and wider PC-writing instructions remain incompletely
  modeled. Check flag-setting self moves, IT transformations and tail-call state.
- Restricted inlining is a useful boundary; the hidden `--force-inline` option
  bypasses `isSafeToInlineARM`. Prevent unsupported overrides from silently
  bypassing correctness checks or document and reject them for supported use.
- Split-fragment and constant-island mapping fixes improve #9. Still cover aliases,
  secondary entries, skipped functions, pointer targets and data labels in mixed
  ARM/Thumb JITLink blocks. Audit redirect source bounds and duplicate local names.
- Enforce the actual ISA/ABI/endianness and static-image contract. Feature docs
  alone do not reject incompatible inputs or unsafe pass combinations.

## Closed subitems and retained deferrals

Credit THM_JUMP19/split support, ARM Bcc target operands, branch-based tail calls,
the reported peephole root cause, restricted pass hooks, TBB/TBH, mapping-marker
selection, and ARM/Thumb call-kind marking. The WSL sync script now excludes
`.git/` and `out/` in both sync and build: that specific earlier risk is fixed.

Clean replay and content-based overlay stamps remain open. Upstream work, full
EHABI rewriting, PIC/dynamic ELF, general userspace/SMP instrumentation, and
architecture-specific pass ports remain deferred as recorded in the functionality
review. Rejection or safe preservation of excluded inputs is still correctness work.

The actionable list is [CORRECTNESS_TODO.md](../HANDOFF.md#claims-consolidated-todo), with stable IDs
in [CORRECTNESS_STATUS.md](../HANDOFF.md#claims-consolidated-todo).
