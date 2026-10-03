# Measurement record integrity

The item 6 audit reproduced two admissions in the older Pi measurement tools.
`pi4_compare.py` gathered cycles, PMU records and checksums into independent
lists. With two completed runs and the first PMU line missing, it attached the
second run's counters to the first run. `pgo_lab_measure.py` printed mismatched
checksums for all four kernels but returned zero.

Both tools now use `measurement_records.py`. Each requested command frame must
contain exactly one ordered cycle/PMU/checksum triple for every requested kernel.
The PGO-lab order is pl_a, pl_b, pl_c, pl_d in each repetition. Missing, duplicate,
reordered, malformed, out-of-frame or unexpected records reject. Zero cycles,
values outside the printed hardware widths, invalid PMU/migration reports and
unsupported PMU sets also reject. The supported PMU record is set 0; optional
`taken` is retained when present. Checksums are normalized numerically and must
agree across all requested variants/repetitions for each kernel before summaries.

Malformed output and child failures propagate without an automatic retry that
could replace a failed observation. Every capture saves its exact image snapshot
and full child output in a fresh `out/pi4/measure-*` directory, including failures.
An environment-selected fast loader is also snapshotted and explicitly supplied.
Original and uploaded images/loaders must remain byte-identical during capture.
Successful parsing produces a measurement association receipt with image/log
hashes, requested command and observed rows. The CSV preserves measured rows;
failed comparisons leave diagnostic data and exit unsuccessfully.

This certifies record association and baseline output consistency only. Matching
checksums are not an independent correctness oracle and do not establish that
selected BOLT functions executed. There is no new hardware or performance result
in this parser-only stage. Cross-round artifact identity, full tool/revision
receipts, independent outputs, PMU ownership and execution coverage remain open.
The legacy raw-grep QEMU workload/milestone scripts also still require an audit;
their banners alone cannot establish backend correctness.

Both preserved before/after reproductions now reject. All 111 Python tests pass,
including thirteen new tests for framing, record association, checksums, widths,
failure retention and changed-image rejection. LLVM source remains at 0044.
Item 6 and original #12 remain active. See [evidence](results/correctness_measurement_gates_20261003.json)
and the [consolidated queue](CORRECTNESS_PRIORITY_TODO.md).
