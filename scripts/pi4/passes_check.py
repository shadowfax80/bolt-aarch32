#!/usr/bin/env python3
"""Run `bolt_bench all` on several images on the Pi and compare every workload's result
(the `sink=` / `acc=` lines) with the first image. Any difference, missing line or failed
boot is an error.

This is a baseline-result comparison. It does not observe rewritten execution;
use full_image_verify.py or a bounded independent fixture for that claim.

usage: passes_check.py name=image.bin [name=image.bin ...]      (Windows Python, COM5)
"""
import argparse
import os
import re
import sys
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proc_util import run_bounded  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from profile_identity import sha256, write_json

HERE = os.path.dirname(os.path.abspath(__file__))
RESULT_RE = re.compile(r"bolt_bench: (\w+) (?:sink|acc)=(0x[0-9a-f]+)")
EXPECTED_WORKLOADS = (
    "hot_loop", "hot_cold", "branch_chain", "memcpy", "far_call", "it_cond",
    "interwork", "switch", "spill_ret", "litpool", "indirect_call",
    "interwork_tail", "regpressure", "hotcold_split", "icf", "shrinkwrap",
    "composite", "stair",
)


def parse_results(text: str, repetitions: int = 1) -> dict[str, str]:
    if not 1 <= repetitions <= 32:
        raise ValueError('workload repetitions must be 1..32')
    if re.search(r"bolt_bench: \w+ FAIL\b", text):
        raise ValueError("workload reported a correctness failure")
    found: dict[str, str] = {}
    for name, value in RESULT_RE.findall(text):
        value = f"0x{int(value, 16):08x}"
        if name in found and found[name] != value:
            raise ValueError(f"conflicting results for {name}: {found[name]} and {value}")
        found[name] = value
    missing = set(EXPECTED_WORKLOADS) - found.keys()
    extra = found.keys() - set(EXPECTED_WORKLOADS)
    if missing or extra:
        raise ValueError(f"incomplete workload set: missing={sorted(missing)}, extra={sorted(extra)}")
    completed = re.findall(r'bolt_bench: (\w+) sink=0x[0-9a-f]+', text)
    if completed != list(EXPECTED_WORKLOADS) * repetitions:
        raise ValueError('workload completion order/count does not match requested repetitions')
    commands = list(re.finditer(r'^\$ ([^\r\n]*)\r?$', text, re.M))
    runs = [i for i, command in enumerate(commands) if command[1].strip() == 'bolt_bench all']
    if commands:
        if len(runs) != repetitions:
            raise ValueError('missing/extra workload command frame')
        for i in runs:
            stop = commands[i + 1].start() if i + 1 < len(commands) else len(text)
            if parse_results(text[commands[i].end():stop]) != found:
                raise ValueError('workload command frame has inconsistent results')
    return found


def results(image: str, port: str = "COM5", log_prefix: str | None = None) -> dict[str, str]:
    cmd = [sys.executable, os.path.join(HERE, "pi4_run.py"), image, "--port", port,
           "--reboot", "--wait", "60", "--max-wait", "240", "bolt_bench all"]
    for attempt in range(2):
        out = run_bounded(cmd, 420)
        text = out.stdout.decode("utf-8", "replace").replace("\r", "\n")
        if log_prefix:
            with open(f"{log_prefix}.{attempt + 1}.log", "w", encoding="utf-8") as log:
                log.write(text)
        reason = f"child exit {out.returncode}"
        if out.returncode == 0:
            try:
                return parse_results(text)
            except ValueError as error:
                reason = str(error)
        print(f"  attempt {attempt + 1} failed for {image}: rc={out.returncode}, "
              f"{reason}; {text.strip()[-300:]}", file=sys.stderr)
    raise SystemExit(f"error: no complete valid results from {image}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", metavar="NAME=IMAGE")
    parser.add_argument("--port", default="COM5")
    parser.add_argument("--log-dir", help="save complete output from each boot attempt")
    args = parser.parse_args()
    if len(args.images) < 2 or any("=" not in item for item in args.images):
        parser.error("provide at least two NAME=IMAGE arguments")
    images = [item.split("=", 1) for item in args.images]
    if any(not name or not path for name, path in images) or len({name for name, _ in images}) != len(images):
        parser.error("image names and paths must be nonempty; names must be unique")
    if any(not Path(path).is_file() for _, path in images):
        parser.error('every image must be an existing file')
    parent = Path(args.log_dir) if args.log_dir else Path(__file__).resolve().parents[2] / 'out/pi4'
    parent.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix='result-consistency-', dir=parent))
    sources, snapshots = {}, []
    for index, (name, path) in enumerate(images):
        digest = sha256(path)
        snapshot = evidence / f'image-{index}.bin'
        shutil.copyfile(path, snapshot)
        if sha256(snapshot) != digest:
            raise ValueError('image changed while snapshotting: ' + name)
        sources[name] = dict(path=str(Path(path).resolve()), sha256=digest)
        snapshots.append((name, str(snapshot)))
    ref_name, ref = images[0][0], None
    bad = 0
    observations = {}
    for index, (name, path) in enumerate(snapshots):
        print(f"== {name}", flush=True)
        prefix = str(evidence / f"image-{index}")
        got = results(path, args.port, prefix)
        observations[name] = got
        if ref is None:
            ref = got
            print(f"   {len(got)} workload results: " + " ".join(f"{k}={v}" for k, v in got.items()))
            continue
        image_bad = 0
        for k, v in ref.items():
            if got.get(k) != v:
                image_bad += 1
                print(f"   MISMATCH {k}: {ref_name}={v} {name}={got.get(k)}")
        extra = set(got) - set(ref)
        if extra:
            image_bad += 1
            print(f"   extra results: {sorted(extra)}")
        bad += image_bad
        if not image_bad:
            print(f"   all {len(ref)} results identical to {ref_name}")
    for name, path in snapshots:
        if sha256(path) != sources[name]['sha256'] or sha256(sources[name]['path']) != sources[name]['sha256']:
            raise ValueError('image changed during result comparison: ' + name)
    write_json(evidence / 'comparison.json', dict(schema=1, result_consistency=not bool(bad),
        execution_verified=False, scope='baseline output agreement only; rewritten execution is not observed',
        images=sources, workload_results=observations, expected_workload_results=ref,
        verifier_sha256=sha256(__file__), logs={p.name: sha256(p) for p in evidence.glob('*.log')}))
    print("RESULT CONSISTENCY:", "PASS" if not bad else f"FAIL ({bad} differences)")
    print('Rewritten execution is not verified; evidence:', evidence)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
