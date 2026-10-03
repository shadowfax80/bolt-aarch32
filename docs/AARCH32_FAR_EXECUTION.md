# A32 far-call execution gate — item 6, second checkpoint

The legacy P5 gate now requires a bounded execution certificate. Item 6 and
original workstream #12 remain active. No LLVM source changes were made;
the backend remains at overlay 0043.

## Reproduced gap

The old far-call fixture set its exit value to 42 after the call regardless of
the callee's result. A preserved host reproduction replaces the rewritten
call with a NOP: QEMU still exits with 42, the generated veneer remains in the
ELF, and the far callee is absent from the executed trace. The old result check
would accept it. Its structural-only fallback also printed PASS when QEMU was
absent. That fallback is removed; missing QEMU is a hard failure.

## Enforced certificate

`scripts/verify-bolt-arm32-veneer.sh` delegates to
`scripts/verify_far_execution.py`. Each invocation creates a fresh evidence
directory instead of reusing shared `/tmp` artifacts. `OUT_DIR`, `TOOLCHAIN`
and `QEMU_ARM` select its output parent, compiler tools and emulator.

The generated fixed-address ARMv7-A ELF has an explicit legacy literal veneer,
an A32 caller and a far A32 callee. BOLT must remove the literal veneer, move
both functions, select the new ELF entry and insert a MOVW/MOVT/BX veneer.
The gate independently decodes the call and veneer bytes, requires the absolute
target to equal the emitted callee, and checks that the call is beyond direct
A32 BL range. The emitted function map must contain exactly the caller and
callee; the eliminated original veneer is recorded separately.
The direct-branch boundary includes the negative -32 MiB endpoint; the gate
tests the exact signed displacement range relative to PC + 8.

An independently computed table contains the five inputs
`0`, `1`, `17`, `0x7fffffff`, and `0xffffffff`, with expected return and memory
values `(input + 7) mod 2^32`. The candidate must preserve the table and data
address exactly. The fixture checks the returned result, memory store, unchanged
NZCV, and unchanged SP. Its checker runs inside the rewritten caller; the
negative controls below test the checker on the produced executable. This is
a bounded functional oracle, not an independent proof of every instruction.

QEMU `exec,nochain` traces must witness the rewritten caller, generated veneer
and emitted callee. The veneer and callee must each execute exactly five times.
The original callee must not execute. Exit 42 alone, a translated disassembly,
or one successful callee visit cannot issue the certificate. Baseline execution
also requires all five callee visits and the independent result checks.

Both normal and reverse block layouts must detect these executable mutations:

| Mutation | Required outcome |
|---|---|
| ADD immediate 7 changed to 8 | Result failure, exit 71 |
| Memory store removed | Memory failure, exit 72 |
| ADD changed to ADDS | NZCV failure, exit 73 |
| Callee changes SP | Stack failure, exit 74 |
| Far call replaced with NOP | Result failure, exit 71 |
| Loop shortened to one input | Exit 42, rejected for missing repetitions |
| Callee loops forever | Timeout, rejected |

Timeouts never count as successful execution. Failed builds or validation
retain diagnostics and do not produce `verification.json`.

The receipt records selected, emitted, eliminated and observed routes;
entry selection; expected exit; actual exits, timeouts and guest-PC visit
counts; BOLT options; repository revision; tool, verifier, wrapper and QEMU
hashes; emulator version; and artifact/log digests. Image hashes are checked
before and after execution, artifact hashes before publication, and tool,
script and repository identities across the run. Hashes establish recorded
identity; they do not certify a clean compiler build.

## Verified scope and remaining work

On 2026-10-03 both assertion modes pass normal and reverse layouts: five
positive inputs and seven rejected faults per layout, giving 20 transformed
input cases and 28 rejected faults overall. The two baseline runs add ten
input cases. All 86 Python tests pass. The pre-fix bypass reproduction is
preserved with its executed guest PCs and image/log hashes.

This is QEMU cortex-a15 Linux user-mode execution of the explicit legacy A32
literal-veneer removal and generated far-call route. No new Pi execution,
Thumb or mixed-ISA far-call route, automatic v7 linker thunk, interrupt/PMU,
or whole-LK execution is claimed. The retained automatic v7 thunk caveat stays
open under items 7/11. The whole-LK `arm_reset` admission rejection is unchanged.

Next within item 6: extend these witnesses to Thumb/mixed routes and hardware,
audit the remaining raw-grep/comparison/legacy verification paths, and extend
durable coverage and oracle receipts to the remaining supported gates.
See [the queue](CORRECTNESS_PRIORITY_TODO.md) and
[evidence](results/correctness_far_execution_20261003.json).
