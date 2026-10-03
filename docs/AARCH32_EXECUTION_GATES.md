# AArch32 execution gates — item 6, first checkpoint

The execution/result gate hardening stage is verified. Consolidated item 6
remains active; this checkpoint does not close the wider execution work or
original workstream #12. LLVM source remains at overlay 0043.

## Reproduced defects and fixes

Five host reproductions were admitted before the changes:

| Reproduction | Previous behavior | Current behavior |
|---|---|---|
| Incomplete second workload repetition | Combined names looked complete | Reject incomplete completion count/order |
| Duplicate PC dump chunk | Merge parser overwrote the duplicate | Reject duplicate chunk |
| Wrong dump END total | END total was ignored | Reject mismatched total |
| Chunk before BEGIN | Merge parser accepted it | Reject record order |
| ARM PC-dependent prologue with insufficient scratch | Hook relocated the instruction and grew a 12-byte buffer to 40 bytes | Legacy ARM/Thumb hooks reject before modification |

`parse_results` requires every requested repetition of `bolt_bench all` to have
all 18 final sink reports in order. When serial command frames are present, each
command must have its own complete results; an empty command and a command with
two result sets cannot be merged into two successful runs. Internal accumulator
reports do not count as another completed workload. Conflicting values and
reported workload failures still reject.

`validate_single_dump` checks exactly one BEGIN and END, exact address/size/total,
all chunk sequence numbers, offsets and lengths, record order, checksums and
completeness. Malformed records and duplicate chunks reject. Counter collection,
PC collection and the full-image execution gate use this common strict path.
The older merge/retry parser remains available for diagnostic reassembly; its
success alone cannot certify a capture.

## Coverage and artifact identity

`full_image_verify.py` requires PC evidence for every selected redirect. The
default is the entire redirect set. An explicit `--require-executed` must name
that exact set; a subset cannot hide an unobserved selected function. Duplicate
emitted coverage, missing execution, wrong ISA and unaligned ARM PCs reject.
Other emitted functions remain outside the execution claim.

The verifier snapshots the exact manifest, baseline and candidate upload bytes,
and optional fast loader into its fresh evidence directory. It resolves both
`--fast-loader` and `PI4_FAST_LOADER`, verifies snapshot identities, and checks
source artifacts, the manifest, upload copies, verifier scripts and repository
revision again before issuing a receipt. The sampling completion, requested
period, complete workload repetitions and core/PMU reports must also validate.
The receipt preserves selected/emitted/redirected/observed sets, expected and
observed baseline results, options/provenance, uploaded-image hashes and logs.

The builder records and rechecks the LLVM tool hashes, including `llvm-nm`, the
patch series, scripts and repository revision around construction. Revision plus
script hashes describes the actual working files; a revision string does not
claim a clean worktree or a clean compiler build. The existing profile identity
gate remains mandatory for supplied sampling or counter profiles.

These checks detect accidental changes and mixed artifacts. They are not
signatures, adversarial attestation, proof of every instruction boundary, or
proof that every code path in a sampled function ran. PC sampling still has the
runtime's all-core and IRQ-masking limitations. PMU ownership remains item 10.
Baseline agreement is not an independent mathematical oracle for every workload.

## Legacy helpers and result-only comparisons

Legacy ARM/Thumb entry-bump counter hooks are excluded. They assign entry bumps
to CFG counters, update only low counter words, and do not establish safe scratch
ownership or prologue relocation; the Thumb path also changes flags. Use
BOLT-generated instrumentation under its documented admission contract. A seal
of a manually modified image cannot turn these operations into a correctness
proof. This checkpoint makes no AArch64 hook claim.

Section restoration requires matching source/destination addresses and sizes,
bounded file extents and unique section names. Missing required destinations or
truncation reject. Restoration stages the output before replacement instead of
writing a partly validated ELF. Absent original optional sections need no restore.
The serial runner now fails if watchdog disarming fails, even after workloads
printed complete results.

`passes_check.py` snapshots its images and saves logs and `comparison.json` in a
fresh evidence directory, even without `--log-dir`. Its result is explicitly
baseline-output consistency with `execution_verified=false`. It does not certify
that rewritten bodies ran. Timing/comparison and remaining legacy verification
paths still require their own coverage/oracle audit; they do not acquire a wider
execution claim from this checkpoint.

## Verification on 2026-10-03

All five reproduced admissions now reject; the hook reproduction leaves its
12-byte buffer unchanged. The strict transport matrix passes seven valid sizes
(1/8/63/64/65/127/128 bytes) and 80 malformed cases. The Python suite passes 80
tests, including per-command repetitions, selected-set coverage, changed
manifest/upload rejection, child failure, loader environment binding, exact
restoration and result-only receipt scope.

Real mixed ARM/Thumb full-gate artifact construction and structural checks pass
in both assertion modes. These small host fixtures were not executed on the Pi
and have no workload execution claim.

Fresh bounded Pi pass-matrix fixtures execute in both modes: baseline, normal,
reverse, automatic inlining, size-based inlining and reverse-layout peepholes
each pass 70 independent result/stack/branch/flag cases. Both deliberate faults
(wrong result and broken CBZ flags) are detected, and all eight images per build
return to the loader. This is 420 positive cases and two expected fault outcomes
per build. Its scope remains HYP core zero with masked interrupts and the
recorded fixture matrix; it does not certify the full-image sampling gate on LK.

The fresh whole-LK attempt stops before certification at the backend's existing
unsupported PC-writing control-transfer check in `arm_reset(*2)` at `0x8000809c`.
The guard remains enforced. No new whole-LK execution or rewritten far-call
coverage is claimed.

See [evidence](results/correctness_execution_integrity_20261003.json) and
[the active queue](CORRECTNESS_PRIORITY_TODO.md).

## Next stage within item 6

- Extend independent ARM/Thumb/mixed-ISA result, flag, memory and return checks
  across additional inputs, faults and timeouts; add direct execution witnesses
  for rewritten far-call routes. Keep the retained v7 thunk caveat open in 7/11.
- Audit the remaining comparison/raw-grep/manual postprocessing paths and their
  coverage, result association and failure propagation. Excluded legacy hooks
  must not re-enter the verified pipeline through another wrapper.
- Extend durable selected/emitted/redirected/executed and independent-oracle
  receipts to every supported optimization gate.
- Investigate the whole-LK control-transfer boundary under items 8/11 without
  bypassing admission checks. PMU ownership and clean-build proof remain 10/14.
