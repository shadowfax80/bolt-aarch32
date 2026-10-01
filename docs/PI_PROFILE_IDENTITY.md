# Pi sampling profile identity

Seal the exact ARM ELF/binary pair before collecting samples. Run on the build
host with the ATFE toolchain; this checks every allocated file-backed ELF section
against the binary and records source functions, the sample buffer, tool digests
and ATFE patch digests. The binary must have the exact objcopy image length.

```sh
python3 scripts/profile_identity.py seal-samples \
  --elf IMAGE.elf --image IMAGE.bin --toolchain /home/user/bolt-aarch32/build-atfe/bin \
  --patch-dir overlay/llvm/patches/atfe
```

On the Windows serial host, collect a fresh run using the corresponding ELF and
the generated `IMAGE.bin.manifest.json`. Both files may be copied between hosts;
the binding uses hashes rather than host-specific paths.

```sh
python3 scripts/pi4/pi4_sample_profile.py IMAGE.bin training.samples \
  --elf IMAGE.elf --workload all --repeat 2 --port COM5 \
  --fast-loader tools/pi4-serialboot-fast/kernel7l_fast.img
```

The collector uploads isolated session copies, validates requested repetitions,
sample counts, buffer range, checksums, completion and PMU/core reports, and saves
the complete log and `training.samples.manifest.json`. A failed run cannot publish
a new profile payload. Session copies and failure logs remain in `pi-samples-*`.

Convert on the ATFE host:

```sh
python3 scripts/samples_to_fdata.py IMAGE.elf training.samples \
  --toolchain /home/user/bolt-aarch32/build-atfe/bin -o training.fdata \
  --functions bolt_bench_memcpy,bolt_bench_far_call,bolt_bench_it_cond,bolt_bench_interwork
python3 scripts/profile_identity.py check-profile --elf IMAGE.elf --profile training.fdata
```

The converter verifies the captured payload and ELF hashes, matches perf2bolt to
the sealed toolchain, bounds each named profile location against the source ELF,
and publishes `training.fdata.manifest.json`. Duplicate local source names are
rejected until an unambiguous address map is available. A failure or stale
sidecar makes the consumer reject the profile. Copy the sidecar together with
the fdata; `bolt-variant.sh` preserves it and `optimize-lk-bolt.sh` requires it for
ARM `no_lbr` profiles. Direct llvm-bolt and other drivers are not yet covered.

`full_image_build.py --profile training.fdata` accepts an explicitly bound profile,
copies both profile and sidecar into its fresh artifact directory and records
their hashes. `full_image_verify.py` rechecks them before and after the Pi run.

`--debug-unbound` allows converter diagnostics on synthetic/legacy sample words.
Its sidecar explicitly has `verified_binding: false`; the optimization identity
gate rejects it. Never use it to certify a production capture.

Without `--functions`, every named profile location must have an unambiguous,
bounded source function symbol. Some assembly code, such as `arch_idle` in the
tested ELF, has no such symbol and is rejected. An explicit function list projects
the profile onto that source scope and records every excluded function's profile
count in the sidecar. The selected offsets are still checked; an empty projection
fails. These exclusions are visible and do not establish validity for the omitted
locations. In `all` runs, repetition checks count the final sink per workload;
composite/stair's additional acc reports are not extra executions.

Windows may reassign the serial adapter after reconnecting it. The verified
2026-10-02 run used COM6, found under `HKLM:\\HARDWARE\\DEVICEMAP\\SERIALCOMM`.
Use the current port instead of assuming COM5.

These manifests detect accidentally mixed or stale artifacts; they are not
cryptographic signatures against a malicious party editing the entire chain.
Patch digests record the overlay files, not proof of clean source replay or that
the tool binaries were built from those files. That verification remains open.

The current runtime arms PMU counter 5 on all cores. Core IRQ counts are retained
and migration reports rejected, but PCs from other cores cannot be individually
attributed. IRQ-masked code is invisible, so this is a sampling profile rather
than exact measured edges. Single-core ownership remains a separate #12 task.
Counter dumps and their source-location binding also remain open.
