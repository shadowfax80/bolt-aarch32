# Pi 4 inlining and branch semantics fixture

Requires ATFE overlays through 0032. This isolated fixture executes generated
ARM/Thumb wrappers through eleven explicit original-entry redirects; firmware
startup and caller data stay at their original addresses. Fifty-five independent
expected results cover safe leaf/multiple-block inlining, retained stack/LR
callees, both ARM conditional-return paths and both Thumb CBZ/CBNZ successor
paths. Both CBZ expansions are checked in emitted code; their caller compares
the flags before and after the call/inlined body. Every case checks stack balance
and eight-byte alignment. Execution is quiet HYP/core zero, MMU/caches off,
with masked interrupts and parked secondary cores.

Build in WSL:

```sh
python3 /mnt/c/Users/User/CURSOR/CodexProjects/BOLT_AARCH32/scripts/pi4/build_inline_safety.py \
  --out /mnt/c/Users/User/CURSOR/CodexProjects/BOLT_AARCH32/out/correctness/inline-safety-pi
```

For the independent assertions-disabled build, add:

```sh
--toolchain /home/user/bolt-aarch32/out/correctness/build-atfe-noasserts-20261002/bin
```

The builder prints a fresh build directory. Run from Windows:

```powershell
& out/correctness/pi-venv/Scripts/python.exe scripts/pi4/verify_inline_safety.py --build <build-directory> --port COM5
& out/correctness/pi-venv/Scripts/python.exe scripts/tests/test_inline_safety.py -v
```

The verifier checks hashes, ELF/raw load bytes, boot address and redirect targets
before upload and after execution. Baseline, normal and reverse must each report
all 55 cases. `bad-result` must fail case 0/result field; `bad-cbz-flags` changes
the inlined CBZ nonzero-path ADD to ADDS and must fail case 46/result field because
the caller detects changed flags. Every payload must reboot through the watchdog
to the serial loader. This fixture checks the listed transforms and instruction
forms; general PC writes, active interrupts, IT call sites and other pass
combinations remain separate work.

Recorded run: [correctness_inline_safety_20261002.json](results/correctness_inline_safety_20261002.json).
