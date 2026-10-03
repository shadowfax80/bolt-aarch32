#!/usr/bin/env python3
"""Load an image onto the Pi 4B via the serial chainloader, then run a
scripted sequence of shell commands and capture everything printed.

Reuses pi4_serial_boot.py's image-transfer/baud-switch logic, then
sends each command (with a CR) and waits for LK's own shell prompt
("] ", fputs'd by lib/console/console.c right before it reads the next
line) to come back before sending the next one.

Review finding #7, fixed: this used to wait for `--idle` seconds of
silence instead, capped at `--max-wait` overall -- a real bug, not
just imprecision. A full `profiler dump` can run for tens of seconds
with no gap anywhere near that long (measured: ~6MB at the calibrated
~213 KiB/s is ~29s), so the old defaults (0.5s idle, 15s max) silently
cut it off mid-stream and then typed the *next* command straight into
LK's still-busy 16-byte UART receive buffer, corrupting or dropping
bytes with no error from either side. Waiting for the real prompt has
no such ceiling for a well-behaved command; `--max-wait` is now a much
larger hard safety timeout for a genuine hang, not the normal
completion signal.

Usage:
    python scripts/pi4_run.py build/lk/build-rpi4-test/lk.bin --log pi4.log \
        -- "profiler start" "profiler bench 5000000" "profiler stop" "profiler dump"
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    sys.exit("error: pyserial is required (python -m pip install pyserial)")

sys.path.insert(0, str(Path(__file__).parent))
from pi4_serial_boot import Console, reboot_to_chainloader, resolve_port, send_image, switch_baud

PROMPT = b"] "


def run_command(port: serial.Serial, console: Console, cmd: str, max_wait: float) -> bool:
    """Send one command, wait for LK's own "] " prompt to reappear.
    Returns False (and warns) if it doesn't within max_wait -- a real
    hang or a crash, not just a slow command."""
    console.write(f"\n$ {cmd}\n".encode())
    port.write(cmd.encode() + b"\r")
    port.flush()

    deadline = time.monotonic() + max_wait
    tail = b""
    while time.monotonic() < deadline:
        chunk = port.read(port.in_waiting or 1)
        if not chunk:
            continue
        console.write(chunk)
        tail = (tail + chunk)[-len(PROMPT):]
        if tail == PROMPT:
            return True

    print(f"warning: no prompt within {max_wait}s after {cmd!r} -- "
          f"the Pi may be hung or still mid-command; stopping here "
          f"rather than typing the next command into a busy shell",
          file=sys.stderr)
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image", help="raw binary to load at 0x8000")
    ap.add_argument("commands", nargs="*", help="shell commands to run in order")
    ap.add_argument("--port", default="auto")
    ap.add_argument("--baud", type=int, default=115200,
                    help="initial link speed matching the chainloader (default: 115200)")
    ap.add_argument("--post-jump-baud", type=int, default=3000000,
                    help="baud after the payload jumps and runs (default: 3000000)")
    ap.add_argument("--log", help="append everything received to this file")
    ap.add_argument("--wait", type=float, default=None,
                    help="seconds to wait for the SBOOT? prompt (default: forever)")
    ap.add_argument("--max-wait", type=float, default=90.0,
                    help="hard timeout per command if LK's prompt never comes back "
                         "(default: 90s, generous enough for a full profiler dump)")
    ap.add_argument("--fast", action="store_true",
                    help="upload at 3 Mbaud (needs the fast chainloader installed on the SD card); "
                         "falls back to the slow upload if the fast one fails")
    ap.add_argument("--fast-loader", metavar="IMG",
                    help="hot-load this fast chainloader image through the SD card's chainloader "
                         "first (no SD-card change), then upload the payload at 3 Mbaud")
    ap.add_argument("--reboot", action="store_true",
                    help="if LK is running (no SBOOT? prompt), send it `reboot` "
                         "first instead of waiting for a manual power-cycle")
    ap.add_argument("--wdog", type=int, default=int(os.environ.get("PI4_WDOG", "0") or 0),
                    help="arm the image's watchdog for this many seconds around the commands, "
                         "so a hang resets the Pi instead of needing a power cycle "
                         "(default: $PI4_WDOG or off)")
    args = ap.parse_args()
    # PI4_FAST_LOADER=<img> turns on the 3 Mbaud upload for every script that shells out to
    # this one (pi4_compare.py, pgo_lab_measure.py, pi4_bolt_profile.py, ...): no per-script flag.
    if not args.fast_loader and os.environ.get("PI4_FAST_LOADER"):
        args.fast_loader = os.environ["PI4_FAST_LOADER"]

    with open(args.image, "rb") as f:
        image = f.read()
    if not image:
        sys.exit(f"error: {args.image} is empty")

    console = Console(args.log)
    port_name = resolve_port(args.port)
    try:
        # write_timeout: without it a stalled USB-serial adapter blocks port.write() in the
        # driver forever (a measurement run hung for 31 minutes and the process could not even
        # be killed). With it a stall raises SerialTimeoutException, the run exits non-zero
        # and pi4_compare.py / pgo_lab_measure.py retry that boot.
        port = serial.Serial(port_name, args.baud, timeout=0.1, write_timeout=20)
    except serial.SerialException as e:
        sys.exit(f"error: can't open {port_name} ({e}). Is PuTTY still holding it?")

    with port:
        port.reset_input_buffer()
        if args.reboot:
            reboot_to_chainloader(port, console, args.post_jump_baud)
        if args.fast_loader:
            # Hot-load the fast chainloader as a payload of the one on the SD card (both are
            # entered at 0x8000 in the same state), then talk to *it*. No SD-card change needed.
            with open(args.fast_loader, "rb") as fh:
                send_image(port, console, fh.read(), args.wait)
        if args.fast or args.fast_loader:
            try:
                send_image(port, console, image, args.wait, fast=True)
            except SystemExit as e:
                print(f"fast upload failed ({e}); retrying at the slow baud", file=sys.stderr)
                send_image(port, console, image, args.wait)
        else:
            send_image(port, console, image, args.wait)

        if args.post_jump_baud != args.baud:
            switch_baud(port, args.post_jump_baud)

        # Let the boot banner settle before the first command.
        if not run_command(port, console, "", args.max_wait):
            sys.exit(1)

        # Hang guard: the image resets itself back to the chainloader if the commands
        # do not finish within --wdog seconds (bolt_bench's `wdog`; no-op on images
        # without it). Disarmed again after the last command.
        if args.wdog and not run_command(port, console, f"wdog {args.wdog}", args.max_wait):
            sys.exit(1)

        for cmd in args.commands:
            if not run_command(port, console, cmd, args.max_wait):
                sys.exit(1)

        if args.wdog:
            if not run_command(port, console, "wdog 0", args.max_wait):
                sys.exit(1)


if __name__ == "__main__":
    main()
