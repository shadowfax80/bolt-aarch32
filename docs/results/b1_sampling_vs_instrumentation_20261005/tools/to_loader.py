"""Send the running LK (at the given baud) back to the serial chainloader."""
import sys
sys.path.insert(0, r'C:\Users\User\CURSOR\ClaudeProjects\lk-perf\scripts')
import serial
from pi4_serial_boot import Console, reboot_to_chainloader
baud = int(sys.argv[1]) if len(sys.argv) > 1 else 6000000
with serial.Serial('COM5', 115200, timeout=0.1) as port:
    reboot_to_chainloader(port, Console(None), baud)
print('\nat chainloader')
