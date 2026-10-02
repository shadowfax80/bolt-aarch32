# Pi IT-mask and exact-count verification

Run the isolated fixture in WSL using the assertions-enabled ATFE toolchain:

```sh
python3 scripts/pi4/build_it_counts.py --out out/correctness/it-counts-pi
```

From Windows, pass its printed fresh build directory to:

```powershell
& out/correctness/pi-venv/Scripts/python.exe scripts/pi4/verify_it_counts.py --build out/correctness/it-counts-pi/build-... --port auto
```

The fixture contains fifteen data IT masks, fifteen terminal branch masks in
both instruction widths, and two loops: 47 selected functions and 100 inputs.
Each input runs with zero, low-carry and full-wrap seeds, yielding 300 cases per
image. The baseline and three instrumented layouts check independent returns;
instrumented images also compare every measured slot with the independent CFG
path model. Other functions' slots must stay at their seed. Counters reset
before every case. Function-map addresses and actual redirects are checked.
Residual IT groups must contain only their original predicated additions.

The narrow branch cases are patched to architectural B16 within IT, followed
by a NOP; object-only trace labels avoid creating artificial secondary entries.
The narrow loop's separate NOP exit block is part of the expected count model.
Metadata locations bind counter indices to that model; independently assembled
counter prefixes validate emitted slot ownership. No descriptor-order shortcut
is used for unnamed leaf descriptors.

Firmware runs privileged on one core with IRQ/FIQ disabled and MMU/caches off.
The verifier uses the temporary fast serial loader and requires watchdog return
after each image. This verifies quiet IT/branch/loop counts and reset, with no
claim about nested execution, active interrupts, SMP, live snapshots, other
predicate conditions or all pass combinations. Full source/build provenance
remains part of paused item #12.

Recorded hardware evidence is
[correctness_it_counts_20261002.json](results/correctness_it_counts_20261002.json).
