#!/usr/bin/env python3
"""Read this Sony controller's raw stick values alongside evdev for 40 seconds.

Read-only: no feature reports, device grabs, pairing changes, or permission edits.
"""
import fcntl
import json
import os
from pathlib import Path
import select
import struct
import sys
import time

if sys.argv[1:] != ['capture']:
    raise SystemExit('Expected action capture.')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/navcon'))
from linux_input import discover, ior

matches = [device for device in discover()
           if device['transport'] == 'Bluetooth' and device['raw_path']]
if len(matches) != 1:
    raise SystemExit('Connect exactly one Bluetooth Navigation Controller for this diagnostic.')
info = matches[0]
raw = os.open(info['raw_path'], os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
event = os.open(info['path'], os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
samples = []
start = time.monotonic()
print('Raw stick capture ready; hold right ten seconds, then left ten seconds, then release.', flush=True)
try:
    while time.monotonic() - start < 40:
        if not select.select([raw], [], [], .5)[0]:
            continue
        data = os.read(raw, 128)
        if not data:
            raise SystemExit('Controller disconnected.')
        if len(data) < 10 or data[0] != 1:
            continue
        axes = []
        for code in (0, 1):
            buf = bytearray(24)
            fcntl.ioctl(event, ior(0x40 + code, 24), buf, True)
            axes.append(struct.unpack('6i', buf)[0])
        samples.append([round(time.monotonic()-start, 3), data[6], data[7], *axes])
finally:
    os.close(event)
    os.close(raw)
print(json.dumps({'columns': ['seconds', 'raw_x', 'raw_y', 'evdev_x', 'evdev_y'], 'samples': samples}), flush=True)
