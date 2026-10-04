# AArch32 profile identity contract — overlay 0043

> Commands/contracts and dated evidence below retain their stated scope.
> Current overlay inventory, item status and any later extensions are in
> [HANDOFF.md](HANDOFF.md); old "next" or stop statements are historical.

Consolidated queue item 5 is verified within the repository's sealed ARM counter
and PC-sampling pipelines. This is an artifact identity and source-range check.
Execution coverage, workload semantics, PMU ownership and clean build provenance
remain in items 6, 10 and 14. Original workstream #12 remains active.

## Counter ownership and exact input

ARM instrumentation emits two host-only, non-loaded ELF notes. Neither changes
the runtime table format or the uploaded code:

- `.bolt.arm.source`: vendor `BOLTARM`, type `0x41524d02`, descriptor containing
  the SHA-256 of the exact input buffer BOLT read, including symbols and data.
- `.bolt.arm.profile`: vendor `BOLTARM`, type `0x41524d01`, descriptor `BAP1`,
  a little-endian u32 function count, then descriptor-order records of original
  address u64, size u64, Thumb flag u8, name length u32 and name bytes.

The binder compares source functions, emitted functions, map addresses/sizes/ISA
and explicit descriptor owners. Missing, duplicate or ambiguous names fail.
BOLT's `/number` suffix may resolve to an original local symbol only when the
source symbol is unique. Leaf-only descriptors use the owner note; a caller's
`--funcs` order cannot establish or override ownership.

Every CFG location must name its descriptor owner and have an offset inside the
exact original function. Every counter has exactly one metadata owner, the array
and count word fit the exact counter section without overlap, and the dumped
count agrees with the sealed ELF. Getter instructions and note framing are
validated. Call/entry-node and indirect-call profiling metadata are excluded
from the initial verified counter contract. Use `--instrument-calls=false`.
Profiles with no measured locations fail rather than representing successful
training. Published counter counts must fit a positive unsigned 64-bit value.
Counter wraparound and concurrent/torn snapshots cannot be certified from a dump;
reset/read quiescence remains in item 9. Range checks do not prove instruction boundaries or semantic CFG
correctness; wider code/reference proof remains open.

## Seal, collect, convert, consume

Use the same toolchain and successful source replay report throughout. Preserve
the exact original ELF, final instrumented ELF, emitted map and upload image.
Create the seal before collecting any counters. For example, in WSL:

```bash
python3 scripts/profile_identity.py seal-counters \
  --original original.elf --elf instrumented.elf --map instrumented.funcmap \
  --image instrumented.bin --toolchain /home/user/bolt-aarch32/build-atfe/bin \
  --patch-dir overlay/llvm/patches/atfe \
  --source-replay out/correctness/profile-identity-20261003/replay/replay.json
```

The build receipt binds SHA-256 identities for the original ELF, instrumented
ELF, map, image, replay report, complete patch series and five LLVM tools. It also
records the validated owners, map and counter layout. The binary's loaded section
bytes and length must agree with the ELF's physical load image. The replay report
must identify the complete patch series and exact replayed source contents.

Run the collector where the serial port is available; paths and toolchain must
be accessible there. A Linux-side example uses the appropriate `/dev/tty…` port:

```bash
python3 scripts/pi4/pi4_bolt_profile.py instrumented.bin counters.bin \
  --original original.elf --elf instrumented.elf \
  --function-map instrumented.funcmap \
  --toolchain /home/user/bolt-aarch32/build-atfe/bin \
  --source-replay out/correctness/profile-identity-20261003/replay/replay.json \
  --port /dev/ttyUSB0
python3 scripts/ram-dump-to-fdata.py --original original.elf \
  --elf instrumented.elf --function-map instrumented.funcmap --dump counters.bin \
  --toolchain /home/user/bolt-aarch32/build-atfe/bin \
  --source-replay out/correctness/profile-identity-20261003/replay/replay.json \
  -o profile.fdata
python3 scripts/profile_identity.py check-profile \
  --elf original.elf --profile profile.fdata
```

Default sidecars are `IMAGE.manifest.json`, `DUMP.manifest.json` and
`PROFILE.manifest.json`. The collector checks the pre-capture seal, uploads an
immutable copy, requires successful child completion, checks exact BEGIN/END
order/range/total and chunk sequence/length/checksum, and rechecks artifacts
before publishing. Durable evidence includes the uploaded copy and serial log.
Conversion validates actual metadata, counter flow and locations, then rechecks
all capture identities immediately before publishing. Consumers check the exact
source ELF, profile hash, receipt shape/owners and profile offsets again.

The full-image builder and ARM `optimize-lk-bolt.sh` enforce this consumer gate
for both sampling and counter profiles. `bolt-variant.sh` validates a supplied
profile before replacing its previous copy. Its counter path requires
`SOURCE_REPLAY`; `ram-dump-to-fdata.sh` additionally requires `ORIGINAL_ELF` and
`FUNCTION_MAP`. Direct manual `llvm-bolt -data=…` calls do not enforce these
repository sidecars and cannot claim verified pipeline status.

## Publication and exclusions

Counter/sampling collectors and converters stage the entire output bundle before
replacement. Caught publication errors roll back replaced files. Validation and
child failures preserve existing output and identity files. Separate filesystem
replacements are not a crash/power-loss transaction: consumers reject a mixed
generation using its hashes. Rollback itself still depends on functioning I/O.

Old unsealed Pi/QEMU dumps and legacy manual hooks cannot be retrospectively
certified. `--debug-unbound` is an explicit diagnostic path; its receipt has
`verified_binding=false` and verified optimization rejects it. Legacy QEMU
workload wrappers do not acquire verified counter status merely by booting or
producing a dump. Migration requires a pre-capture seal and a bound collector;
the unsupported legacy paths remain excluded. A seal can bind a final manually
modified image but does not prove that modification correct.

Manifests detect accidental stale or mixed artifacts; they are not signatures
and do not resist a caller fabricating a coherent receipt. Identity binding
cannot prove which code actually executed, successful workload results, quiet
cores, valid privilege, reset/snapshot quiescence or clean compiler provenance.
Source replay verifies source contents; it does not prove these incrementally
built LLVM binaries came from a clean rebuild.

## Verification on 2026-10-03

Both assertion modes pass 300 host cases each: 12 valid ARM/Thumb/mixed-ISA
fixtures across normal, reverse and conservative instrumentation, and 288
rejections. Negative cases include wrong input/image/map/dump/tool/patch/source,
missing receipt fields, wrong count with a matching dump hash, owner/source note
mutations, metadata offsets at the excluded end boundary and late dump changes.
Captures are generated on the host and explicitly labelled synthetic; no fresh
hardware capture or workload execution is claimed.

All 65 Python tests pass, including transport framing, late validation, failed
counter/sampling children and publication rollback. Four shell-wrapper rejection
checks preserve existing artifacts; three shell syntax checks pass. Focused
backend suites pass 51/50 (one expected skip off); CoreTests pass 58 with 31 skips
in each mode. The 17-case boundary review passes its expected outcomes. All 43
overlays replay exactly to the live source. Fresh startup (3) and IT/nested/reset
(5) payloads per build equal the previously executed 0041 bytes. The Pi separately
responded `SBOOT?` on COM5; that is loader liveness only.

See [compact evidence](results/correctness_profile_identity_20261003.json) and
[the active queue](CORRECTNESS_PRIORITY_TODO.md). Item 6 is next. Retained automatic
v7 thunk targets remain an open caveat in items 7/11.
