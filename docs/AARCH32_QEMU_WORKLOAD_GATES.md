# QEMU workload gate integrity

The item 6 audit preserved an old WSL LK boot that passes the legacy hot-loop,
hot/cold, branch-chain, memcpy and console banner checks but has no per-workload
sink records. It now rejects. Those banners did not prove correct outputs.
The legacy scripts also suppressed QEMU failures with `|| true` and reused
fixed serial-log paths.

`qemu_workload_gate.py` requires exactly one all-workload startup marker and
console marker, all eighteen ordered sink records, bounded 32-bit results and
consistent optional accumulator records. Missing, repeated, reordered, malformed,
unexpected or conflicting results and explicit workload failures reject. A
candidate must match a freshly booted baseline's complete result dictionary.
Timing banners are diagnostic: they can be interleaved by LK threads and the
far-call banner has no cycle value. They are not used as correctness records.

The runner owns the QEMU lifetime under WSL/Linux. Nonzero child exits and
incomplete output at the deadline reject. Complete output is observed for a
short settling interval before deliberately stopping a kernel at its console.
The final log is checked again, including shutdown output. Failed runs retain
their images and serial logs and cannot create a success receipt. Serial data
is spooled locally because concurrent reads of a DrvFS file produced ENODATA
in the preserved first attempt; the closed log is copied into durable evidence.

Each invocation uses a fresh evidence directory and exact baseline/candidate
ELF snapshots. Receipts bind images, QEMU executable, requested command/options,
verifier dependencies, repository revision, complete results and logs. Sources,
snapshots, QEMU and scripts must remain stable through receipt creation. An
environment-specific receipt is an identity check, not a signature or clean
compiler/source-build certificate.

The harness, P0/P4 milestone, conditional identity-boot and workload scripts now
use this runner. Instrumented profile logs must also contain the complete
workload. Their runtime messages explicitly report complete workloads/output
consistency. P1/P2/P3 and overwrite-count artifact diagnostics retain their
older log-format checks; those checks still need a separate admission audit.

An isolated copy of dirty live LK with current overlay files was built without
changing live LK or ATFE. It completes all eighteen workloads. A hot-loop
candidate produced by each assertion-mode BOLT build matches its fresh baseline:
36 candidate and 36 baseline results overall. The six simulated-child integration
cases accept one complete control and reject markers-only output, child failure,
wrong candidate result, duplicated results and timeout without a receipt.
All 118 Python tests pass under WSL. Windows passes 118 tests with the three
Linux process-ownership tests skipped; native Windows boot capture is excluded.

This is complete workload/output consistency, not an independent oracle or
proof that every selected rewritten function executed. No new Pi execution or
performance claim is made. Selected/emitted/redirected/executed coverage,
independent outputs, manual hooks, remaining artifact admissions, PMU ownership
and clean-build provenance remain open. LLVM source remains at 0044. Item 6
and original #12 stay active. See [evidence](results/correctness_qemu_gates_20261004.json)
and the [queue](CORRECTNESS_PRIORITY_TODO.md).
