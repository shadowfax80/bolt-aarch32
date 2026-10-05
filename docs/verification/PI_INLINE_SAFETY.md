# Pi 4 inlining and branch semantics fixture

> Reserve the Pi and shared build resources under [HANDOFF.md](../HANDOFF.md)
> before running commands. Hardware receipts below are dated and scoped;
> current status and later contract extensions belong to the handoff.

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
forms; general PC writes, active interrupts and broader pass combinations
remain separate work.

Recorded run: [correctness_inline_safety_20261002.json](../results/correctness_inline_safety_20261002.json).

## Expanded pass and call-site matrix

Add `--pass-matrix` to the builder for seventy cases through fourteen wrapper
redirects. Three extra ARM wrappers exercise predicated, indirect and mixed-ISA
calls, which must retain their calls. The emitted-code checks distinguish those
calls from ordinary conditional branches. Safe same-ISA leaf calls must inline.
The baseline and five generated variants run all seventy cases: forced normal,
forced reverse, `--inline-all`, `--inline-small-functions` with a 10000-byte limit,
and forced reverse with `--peepholes=double-jumps`. The last variant tests the
option combination; it does not establish that every peephole made a change.
The same two fault payloads must fail their original case/result checks.

Overlay 0034 expands the host inlining gate to 92 emitted cases and four Thumb
IT-call rejection cases, under forced, reversed, automatic and size-based
inlining. Unsupported IT calls must fail before output is created. Hardware
does not execute rejected IT calls. General predicated exits, privileged
transfers and profile-driven splitting remain open under item #4.

Recorded expanded run:
[correctness_inline_passes_20261002.json](../results/correctness_inline_passes_20261002.json).
Both build modes pass 840 positive cases in total, detect four fault runs and
return all sixteen firmware runs to the loader. All eight payloads match across
the independently built BOLT assertion configurations.
