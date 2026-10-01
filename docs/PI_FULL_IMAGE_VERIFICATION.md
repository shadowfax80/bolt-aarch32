# Scoped full-image verification on Pi

Use ATFE and a relocatable LK fixture with the sampler and watchdog. Whole-image
emission does not mean every function executes. Choose exact map names for original
entries to redirect; retain startup in its original code. The builder checks every
requested redirect and refuses changed prologues, short or ambiguous functions and
inconsistent section restoration. Use a fresh output directory.

In WSL, run the Windows checkout's script against the intended input/toolchain:

```sh
python3 scripts/pi4/full_image_build.py out/full-check \
  --input /path/to/lk.elf --toolchain /home/user/bolt-aarch32/build-atfe/bin \
  --redirect-functions bolt_bench_it_cond,bolt_bench_interwork,bolt_bench_memcpy,bolt_bench_far_call
```

`full_image_wsl.sh` is an equivalent wrapper. Its old implicit-profile/variants
output behavior was removed because a nearby profile could belong to another image.
This builder currently accepts no profile; profile binding is still being completed.
Extra BOLT transformation options follow `--`; input selection, instrumentation,
profile and output overrides are rejected.

From Windows Python with pyserial installed, point to the same output directory:

```powershell
python scripts/pi4/full_image_verify.py out/full-check `
  --require-executed bolt_bench_it_cond,bolt_bench_interwork,bolt_bench_memcpy `
  --repeat 10 --port COM5 `
  --fast-loader tools/pi4-serialboot-fast/kernel7l_fast.img
```

The harness reboots/uploads baseline and candidate, checks all 18 named results,
verifies every artifact against the build manifest, and requires sampled PCs inside
each required rewritten function in the correct ISA state. Too few samples cause
failure; a short far-call may never be sampled and is not certified by this fixture.
The requirement set is explicit and recorded. IRQ sampling is execution evidence,
not an exact edge-frequency measurement; code running with IRQs masked is invisible.

Complete attempt logs and `verification.json` are saved under a fresh `pi-verify-*`
directory. A failed attempt produces no successful verification manifest. Hardware
faults/timeouts fail the child and the gate; the watchdog provides automatic reset
where the running payload supports it. A nonresponsive older payload may still
require a physical power cycle.
