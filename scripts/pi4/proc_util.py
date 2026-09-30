"""Run a Pi-facing subprocess with a timeout that actually works on Windows.

subprocess.run(cmd, capture_output=True, timeout=N) does not: on timeout it kills only the
direct child. Here that child is the Microsoft Store `python3.exe` launcher stub, the real
python.exe it started keeps the output pipes open, and communicate() then blocks forever
(observed: measurement runs frozen for 30+ minutes, 'unkillable' processes that vanished when
the parent died). run_bounded() writes the child's output to a temp FILE (no pipes to block
on), polls with a deadline, and on timeout kills the whole process tree with taskkill /T.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from types import SimpleNamespace


def run_bounded(cmd: list[str], timeout: float) -> SimpleNamespace:
    """Like subprocess.run(cmd, capture_output=True, timeout=timeout) but never hangs.
    Returns .returncode (-9 on timeout), .stdout (stdout+stderr merged, bytes), .stderr (b"")."""
    with tempfile.TemporaryFile() as out:
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        try:
            proc.wait(timeout=timeout)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.kill()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
            rc = -9
        out.seek(0)
        data = out.read()
    if rc == -9:
        data += f"\n[run_bounded: killed after {timeout:.0f}s]\n".encode()
    return SimpleNamespace(returncode=rc, stdout=data, stderr=b"")
